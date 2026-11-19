"""The family: every connected set of one flow whose rate reads nothing that moves, run together on
arrays (R-A4a-04, "arrays").

Such a flow asks one rate from moment to moment: `min(request, capacity)` holds between the moments
of the run, since its request and its capacity read inputs, fixed values and keyed reads that change
only at their key times. So each of its stores is a line between moments, and the flow delivers what
it asks until a store at one of its ends reaches the bound that holds it back: its source at a lower
bound, or its sink at an upper bound. From then on the flow delivers nothing, as the continuous
engine has it for one flow at a bound. A flow that asks something of a full store, into a store at
its upper bound, passes room upstream through two full stores, where local sharing has no answer:
the run stops there (`network.py`). Each flow is a row of the family:

- `begin(t)` evaluates the rates of every row as columns (`Columns`) and starts their lines;
- `advance(until)` takes, in time order, each row whose store reaches its bound before `until`: the
  store is put on its bound exactly, and the flow stops;
- `refresh(t)` evaluates the rates again at a key time and starts again the lines of the rows whose
  rate changed.

The recorder takes a piece of each store and of each actual rate at each change of its line, and a
piece of a request or a capacity that is a formula at each change of its value: all are exact.

`Columns` gives the values of engine names at a time as arrays: a formula that the members of a
template share is evaluated once over the rows (`napkin/core/arrays.values`) with each of its names
read as a column, and any other value is read from the start of the run, or from the keyed read by
the time that holds it.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

from ...core import arrays
from ...expressions import evaluate
from ..errors import SimulationError
from .collections import combined
from .plan import FORMULA, LOOKUP, REDUCE


class Columns:
    """The values of engine names at a time (see the module), for one run."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan

    def one(self, name, t):
        """The value of one engine name at time t."""
        plan, run = self.plan, self.run
        if name == 't':
            return float(t)
        value = plan.values.get(name)
        kind = value.kind if value is not None else None
        if kind == FORMULA:
            env = {read: self.one(read, t) for read in sorted(plan.reads(name))}
            env['t'] = float(t)
            return evaluate(value.node, env, plan.units)
        if kind == REDUCE:
            reduction = plan.reductions[name]
            entries = run.kept_of(name)
            if reduction.names is None:
                return combined(reduction.op, [None] * len(entries), reduction.spelled)
            found = self.at([reduction.names[k] for k in entries], t)
            return combined(reduction.op, list(found), reduction.spelled)
        if kind == LOOKUP and plan.keyed[name].by_time:
            return run.stepped_of(name).at(t)
        return run.value_of(name)

    def at(self, names, t):
        """The values of engine names at time t, as an array in their order."""
        plan = self.plan
        unique = list(dict.fromkeys(names))
        found, groups = {}, {}
        for name in unique:
            value = plan.values.get(name)
            if value is not None and value.kind == FORMULA and value.shape is not None:
                groups.setdefault(id(value.shape), []).append(name)
            else:
                found[name] = self.one(name, t)
        for members in groups.values():
            first = plan.values[members[0]]
            env = {}
            for read, _ in first.binding:
                column = self.at([dict(plan.values[name].binding)[read] for name in members], t)
                env[read] = column
            computed = arrays.values(first.shape, env, plan.units, len(members))
            computed = np.broadcast_to(np.asarray(computed), (len(members),))
            for name, number in zip(members, computed.tolist()):
                found[name] = number
        return np.array([found[name] for name in names])


class Family:
    """The rows of the family of one run (see the module)."""

    def __init__(self, run, sets, values):
        plan = self.plan = run.plan
        self.run, self.recorder, self.columns = run, run.recorder, Columns(run)
        flows = [plan.flows[connected.flows[0]] for connected in sets]
        self.flows = [flow.name for flow in flows]
        stores = sorted({end for flow in flows for end in (flow.source, flow.sink) if end is not None})
        place = {name: k for k, name in enumerate(stores)}
        self.stores = stores
        self.source = np.array([place[flow.source] if flow.source else -1 for flow in flows], dtype=np.int64)
        self.sink = np.array([place[flow.sink] if flow.sink else -1 for flow in flows], dtype=np.int64)
        self.y = np.array([float(values[name]) for name in stores])
        self.since = np.zeros(len(stores))  # the time at which the line of each store starts
        self.slope = np.zeros(len(stores))
        self.lower = np.array([run.bounds[name][0] for name in stores])
        self.upper = np.array([run.bounds[name][1] for name in stores])
        self.requests = [flow.request for flow in flows]
        self.capped = [k for k, flow in enumerate(flows) if flow.capacity is not None]
        self.capacities = [flows[k].capacity for k in self.capped]
        # A request or a capacity that is a formula has its pieces from the family.
        self.recorded = [
            (k, name) for k, name in enumerate(self.requests) if plan.values[name].kind == FORMULA
        ]
        self.recorded += [
            (k, name) for k, name in zip(self.capped, self.capacities) if plan.values[name].kind == FORMULA
        ]
        self.recorder.formulas.update(name for _, name in self.recorded)
        self.stepped = frozenset(name for connected in sets for name in connected.stepped)
        self.asked = np.full(len(flows), np.nan)
        self.wanted = np.zeros(len(flows))  # the request of each flow, before its capacity
        self.rate = np.zeros(len(flows))
        self.version = np.zeros(len(flows), dtype=np.int64)
        self.due = []  # (time, row, version) of the rows whose store reaches its bound
        self.settings = {}  # the formula values recorded last, by name

    def __len__(self):
        return len(self.flows)

    # ---- the rates ------------------------------------------------------------------------------

    def _asked(self, t):
        """What each flow asks at time t: its request, within its capacity."""
        asked = np.array(self.columns.at(self.requests, t), dtype=float)
        self.wanted = asked.copy()
        if self.capped:
            capacities = np.array(self.columns.at(self.capacities, t), dtype=float)
            asked[self.capped] = np.minimum(asked[self.capped], capacities)
        if not np.all(np.isfinite(asked)):
            bad = [self.flows[k] for k in np.flatnonzero(~np.isfinite(asked))]
            raise SimulationError(f'Nonfinite flow rates at {t:g} h: {bad}')
        if np.any(asked < 0):
            bad = [self.flows[k] for k in np.flatnonzero(asked < 0)]
            raise SimulationError(f'Negative flow rates: {bad}')
        if self.recorded:
            names = [name for _, name in self.recorded]
            for name, number in zip(names, self.columns.at(names, t).tolist()):
                if self.settings.get(name) != number:
                    self.settings[name] = number
                    self.recorder.add(name, t, number, 0.0)
        return asked

    def _value(self, store, t):
        return self.y[store] + self.slope[store] * (t - self.since[store])

    def _start(self, k, t):
        """Row k delivers what it asks from time t, unless a bound holds it back: its stores start
        their lines there, and the time at which one reaches its bound is due."""
        source, sink, asked = self.source[k], self.sink[k], self.asked[k]
        ends = [end for end in (source, sink) if end >= 0]
        for end in ends:
            self.y[end], self.since[end] = self._value(end, t), t
        held = (source >= 0 and self.y[source] <= self.lower[source]) or (
            sink >= 0 and self.y[sink] >= self.upper[sink]
        )
        if (
            held
            and self.wanted[k] > 0
            and source >= 0
            and sink >= 0
            and self.lower[source] < self.y[source] >= self.upper[source]
        ):
            raise SimulationError(
                f'{self.stores[source]} and {self.stores[sink]}: room passed upstream through two full '
                'stores; local sharing settles in the direction of supply and has no answer here'
            )
        rate = 0.0 if held else float(asked)
        self.rate[k] = rate
        self.version[k] += 1
        if source >= 0:
            self.slope[source] = -rate
        if sink >= 0:
            self.slope[sink] = rate
        for end in ends:
            self.recorder.add(self.stores[end], t, float(self.y[end]), float(self.slope[end]))
        self.recorder.add(f'{self.flows[k]}.actual_rate', t, rate, 0.0)
        if rate > 0:
            # The store that reaches its bound first; on a tie, both.
            reach, bounded = math.inf, ()
            for end, room in (
                (source, self.y[source] - self.lower[source] if source >= 0 else math.inf),
                (sink, self.upper[sink] - self.y[sink] if sink >= 0 else math.inf),
            ):
                if math.isfinite(room):
                    at = float(t + room / rate)
                    if at < reach:
                        reach, bounded = at, (int(end),)
                    elif at == reach:
                        bounded += (int(end),)
            if reach <= self.plan.horizon:
                heapq.heappush(self.due, (reach, k, int(self.version[k]), bounded))

    def begin(self, t):
        """Every row from time t."""
        self.asked = self._asked(t)
        for k in range(len(self.flows)):
            self._start(k, t)

    def refresh(self, t):
        """The rows whose rate changes at the key time t start again from t."""
        asked = self._asked(t)
        changed = np.flatnonzero(asked != self.asked)
        self.asked = asked
        for k in changed.tolist():
            self._start(k, t)

    def advance(self, until):
        """Each row whose store reaches its bound at or before `until`, in time order: the store is
        put on its bound, and the flow stops there."""
        while self.due and self.due[0][0] <= until:
            reach, k, version, bounded = heapq.heappop(self.due)
            if version != self.version[k]:
                continue
            for end in (self.source[k], self.sink[k]):
                if end >= 0:
                    self.y[end], self.since[end] = self._value(end, reach), reach
            for end in bounded:
                # The store is put on its bound, so the flow is held there from now on.
                self.y[end] = self.lower[end] if end == self.source[k] else self.upper[end]
            self._start(k, reach)
