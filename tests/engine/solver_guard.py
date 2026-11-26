"""Verify each continued Radau step against a fresh sharing at the settled moment."""

from collections import ChainMap
from copy import copy
from math import isfinite
from unittest.mock import patch

from napkin.core.comparisons import Comparisons
from napkin.engine.solvers import radau_rate
from napkin.engine.timeline.plan import RATE, RESULT, STATE
from napkin.engine.timeline.run import Run
from napkin.engine.timeline.sparse import Sparse
from napkin.engine.timeline.ways import Ways

RATE_TOLERANCE = 1e-4


class _MomentState(Run):
    """Read the accepted balances and published external rates without stepping any live solver."""

    def __init__(self, live, t):
        self.__dict__ = vars(live).copy()
        self.now = t
        self.balance = live.stock_balance
        # The authored plan is shared, but lazy lookups from this probe must not fill live caches.
        self.plan = copy(live.plan)
        for name, values in vars(self.plan).items():
            if name.startswith('_') and isinstance(values, dict):
                setattr(self.plan, name, ChainMap({}, values))
        units = self.plan.units = copy(live.plan.units)
        self.plan.units.comparisons = Comparisons(
            units,
            live.plan.units.comparisons.factor,
            lambda name: self.plan.comparison_quantity(name, self.plan.comparison_scales),
        )
        units.comparisons.concrete_definitions = True
        self._kept, self._stepped, self._indexes, self._known = {}, {}, {}, {}
        self.recorder = copy(live.recorder)
        self.recorder.trace = []
        self.recorder.run = self
        self.chance = copy(live.chance)
        self.chance.run = self
        self.chance.plan = self.plan
        self.chance.made = []
        self.stock_state = copy(live.stock_state)
        self.stock_state.run = self

    def value(self, name, t=None, tx=None, *, observations=None):
        part = self.plan.values.get(name)
        kind = part.kind if part is not None else None
        if kind == STATE and name in self.stock_state.balances:
            return self.balance(name, self.now)
        if name in self.plan.shared or kind in (RATE, RESULT):
            # Moving rates within the group are calculated by the fresh Sparse field itself.
            # Other sets supply their settled, published answers at this instant.
            return self.published[name] if kind == RESULT else self.published.get(name, 0.0)
        return super().value(name, t, tx, observations=observations)


def _current_field(way, t):
    state = _MomentState(way.run, t)
    values = {store: state.value(store) for store in way.stores}
    sets = [state.ways.sets[state.ways.set_of[part.flows[0]]][0] for part in way.sets]
    fresh = Sparse(state, sets, values, t, way.key, levels=way.set_levels)
    fresh._start()  # choose outgoing branches and allocate on the accepted stock faces
    return fresh.field(t, fresh.y)


class Guard:
    """Patch only the diagnostic callback in the restart decision. Report the first failed store."""

    def __init__(self):
        self.groups = self.stores = self.interiors = self.endpoints = 0
        self.first_failure = None
        self._patch = patch.object(Ways, '_check_continuation', staticmethod(self.check_continuation))
        self._patch.start()

    def close(self):
        self._patch.stop()

    def report(self):
        return dict(
            groups=self.groups,
            stores=self.stores,
            interiors=self.interiors,
            endpoints=self.endpoints,
            first_failure=self.first_failure,
        )

    def check_continuation(self, way, t):
        if way.pending is not None:
            start, end, dense, _, _ = way.pending
        else:
            dense = way.solver.dense_output()
            start, end = dense.t_old, dense.t
        assert start <= t <= end, (t, start, end, way.stores)
        if t in (start, end):
            self.endpoints += 1
        else:
            self.interiors += 1
        self.groups += 1
        continued = radau_rate(dense, t)
        fresh = _current_field(way, t)
        for name, dense_rate, fresh_rate in zip(way.stores, continued, fresh, strict=True):
            self.stores += 1
            # Time is in hours, so the absolute floor is one stock scale per hour.
            scale = max(way.run.own_scale(name), abs(dense_rate), abs(fresh_rate))
            limit = RATE_TOLERANCE * scale
            if not isfinite(dense_rate - fresh_rate) or abs(dense_rate - fresh_rate) > limit:
                self.first_failure = dict(
                    time=t,
                    group=tuple(way.stores),
                    store=name,
                    dense_rate=float(dense_rate),
                    fresh_rate=float(fresh_rate),
                    limit=float(limit),
                    step=(dense.t_old, dense.t),
                )
                raise AssertionError(
                    f'Continued Radau derivative differs at the moment: {self.first_failure}'
                )


def install():
    """Enable the derivative guard for runs in this process. Call guard.close() after the runs."""
    return Guard()
