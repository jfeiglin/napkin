"""The sparse integrator: a connected set whose rates move, of any size (D3), on one network.

A set runs here when a request or a capacity of its flows or endpoints reads a store that moves (or
the time), and it is no component of the continuous engine (`plan.py`, `Connected.way`): it shares
stores between flows, has endpoint settings, or holds more stores than a component may. Its state is
the vector of its stores; its rates at a time and a state are the local sharing of the network
(`network.Instant`) of what its flows and endpoints ask there. One evaluation touches only the
nonzeros: the settings are evaluated as arrays (`Vector`: a formula that a template's members share
is evaluated once over their rows, with `napkin/core/arrays`), the sharing of the flows that meet no
bound is one array operation, and the change of each store is one product with the sparse incidence.

SciPy's Radau integrates it step by step, with the sparse pattern of its Jacobian: the stores that the
settings of a flow read, joined across each coupled part. The flags of the bounds hold through a
segment. A segment ends where a store reaches a bound, or where a store held on a bound leaves it;
the step is cut at that time, found in the step's dense output to within the crossing tolerance of
the run, the store is put on its bound, and a new segment starts from there with its flags. A failure
in an evaluation is timed at the step where it happens.

The recorder takes the pieces of the stores and of the actual rates that the record keeps, fitted
step by step to the step's dense output (`record.fitted`).
"""

from __future__ import annotations

import math

import numpy as np
import scipy.sparse as sp
from scipy.integrate import Radau

from ...core import arrays
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ..errors import SimulationError
from .collections import combined
from .network import SIDES, Asked, Instant, Network
from .plan import FORMULA, LOOKUP, REDUCE
from .record import fitted


class Vector:
    """The values of engine names at a time and a state of a set's stores, as arrays (see the
    module). `stores` are the names of the state, in its order."""

    def __init__(self, run, stores):
        self.run, self.plan = run, run.plan
        self.place = {name: k for k, name in enumerate(stores)}

    def compiled(self, names):
        """A function (t, y) -> the array of the values of `names`, in their order."""
        plan, run, place = self.plan, self.run, self.place
        unique = list(dict.fromkeys(names))
        back = np.array([unique.index(name) for name in names], dtype=np.int64)
        held_at, held_from, constant_at, constants, steps = [], [], [], [], []
        groups = {}
        for k, name in enumerate(unique):
            value = plan.values.get(name)
            kind = value.kind if value is not None else None
            if name in place:
                held_at.append(k)
                held_from.append(place[name])
            elif name == 't':
                steps.append(([k], lambda t, y: t))
            elif kind == FORMULA and value.shape is not None:
                groups.setdefault(id(value.shape), []).append((k, name))
            elif kind == FORMULA:
                steps.append(([k], self._single(name)))
            elif kind == REDUCE:
                steps.append(([k], self._reduction(name)))
            elif kind == LOOKUP and plan.keyed[name].by_time:
                stepped = run.stepped_of(name)
                steps.append(([k], lambda t, y, stepped=stepped: stepped.at(t)))
            else:
                constant_at.append(k)
                constants.append(float(run.value_of(name)))
        for members in groups.values():
            steps.append(([k for k, _ in members], self._group([name for _, name in members])))
        held_at, held_from = np.array(held_at, dtype=np.int64), np.array(held_from, dtype=np.int64)
        constant_at, constants = np.array(constant_at, dtype=np.int64), np.array(constants)
        size = len(unique)

        def values(t, y):
            found = np.empty(size)
            found[held_at] = y[held_from]
            found[constant_at] = constants
            for at, step in steps:
                found[at] = step(t, y)
            return found[back]

        return values

    def _group(self, members):
        """The members of a template that share one formula, evaluated once over their rows."""
        plan = self.plan
        first = plan.values[members[0]]
        reads = [read for read, _ in first.binding]
        columns = {read: [dict(plan.values[name].binding)[read] for name in members] for read in reads}
        timed = {read for read, column in columns.items() if all(name == 't' for name in column)}
        subs = {read: self.compiled(column) for read, column in columns.items() if read not in timed}
        count, units, shape = len(members), plan.units, first.shape

        def values(t, y):
            env = {read: sub(t, y) for read, sub in subs.items()}
            env.update({read: float(t) for read in timed})
            return np.broadcast_to(np.asarray(arrays.values(shape, env, units, count), dtype=float), (count,))

        return values

    def _single(self, name):
        """A formula that no template shares (it reads an entity): evaluated by itself."""
        plan = self.plan
        reads = sorted(plan.reads(name))
        sub = self.compiled(reads) if reads else None
        node = plan.values[name].node

        def value(t, y):
            env = dict(zip(reads, sub(t, y).tolist())) if sub is not None else {}
            env['t'] = float(t)
            return float(evaluate(node, env, plan.units))

        return value

    def _reduction(self, name):
        """A reduction of the values of its kept entries."""
        plan, run = self.plan, self.run
        reduction = plan.reductions[name]
        entries = run.kept_of(name)
        if reduction.names is None:
            found = float(combined(reduction.op, [None] * len(entries), reduction.spelled))
            return lambda t, y: found
        sub = self.compiled([reduction.names[k] for k in entries]) if entries else None

        def value(t, y):
            values = sub(t, y).tolist() if sub is not None else []
            return float(combined(reduction.op, values, reduction.spelled))

        return value


class Sparse:
    """One connected set on the sparse integrator (see the module)."""

    def __init__(self, run, connected, values, sizes):
        plan = self.plan = run.plan
        self.run, self.recorder = run, run.recorder
        stores, flows = list(connected.stores), list(connected.flows)
        place = {name: k for k, name in enumerate(stores)}
        number = {name: k for k, name in enumerate(flows)}
        source = [place[plan.flows[f].source] if plan.flows[f].source else -1 for f in flows]
        sink = [place[plan.flows[f].sink] if plan.flows[f].sink else -1 for f in flows]
        classes = {}
        for (store, side), items in plan.rankings.items():
            if store in place:
                classes[(SIDES.index(side), place[store])] = run.classes_of(store, side, items, number)
        self.net = Network(flows, stores, source, sink, classes, np.zeros(len(flows)), np.zeros(len(stores)))
        self.stores, self.flows = stores, flows
        self.stepped = frozenset(connected.stepped)
        self.capped = [k for k, f in enumerate(flows) if plan.flows[f].capacity is not None]
        self.end_settings = []  # (side, store, which)
        names = [plan.flows[f].request for f in flows] + [plan.flows[flows[k]].capacity for k in self.capped]
        for (store, side), end in plan.ends.items():
            if store in place:
                for which in ('request', 'capacity'):
                    if getattr(end, which) is not None:
                        self.end_settings.append((SIDES.index(side), place[store], which))
                        names.append(getattr(end, which))
        self.settings = Vector(run, stores).compiled(names)
        self.y = np.array([float(values[name]) for name in stores])
        self.lower = np.array([run.bounds[name][0] for name in stores])
        self.upper = np.array([run.bounds[name][1] for name in stores])
        self.atol = np.array([plan.numerics.atol_factor * sizes[name] for name in stores])
        self.t = 0.0
        self.incidence = sp.csr_array(
            (
                np.r_[-np.ones(np.sum(self.net.source >= 0)), np.ones(np.sum(self.net.sink >= 0))],
                (
                    np.r_[self.net.source[self.net.source >= 0], self.net.sink[self.net.sink >= 0]],
                    np.r_[np.flatnonzero(self.net.source >= 0), np.flatnonzero(self.net.sink >= 0)],
                ),
            ),
            shape=(len(stores), len(flows)),
        )
        # The stores that the settings of each flow read, and those of the endpoints at its ends.
        self.reads = []
        for f in flows:
            found = plan.expansion_of(plan.settings_of(plan.flows[f]))
            self.reads.append(sorted(place[name] for name in found.leaves if name in place))
        self.evaluations = 0
        self.lower_flags = np.zeros(len(stores), dtype=bool)
        self.upper_flags = np.zeros(len(stores), dtype=bool)
        wanted = run.recorder.wanted
        self.kept_stores = [k for k, name in enumerate(stores) if wanted(name)]
        self.kept_flows = [k for k, name in enumerate(flows) if wanted(f'{name}.actual_rate')]

    # ---- the field --------------------------------------------------------------------------------

    def asked(self, t, y):
        """What the flows and the endpoints ask at time t and state y."""
        count, flows = len(self.stores), len(self.flows)
        found = self.settings(t, y)
        request = found[:flows]
        capacity = np.full(flows, math.inf)
        capacity[self.capped] = found[flows : flows + len(self.capped)]
        end_request, end_capacity = np.zeros((2, count)), np.full((2, count), math.inf)
        for (side, s, which), number in zip(self.end_settings, found[flows + len(self.capped) :].tolist()):
            (end_request if which == 'request' else end_capacity)[side, s] = number
        if not (np.isfinite(request) & (request >= 0)).all():
            bad = int(np.flatnonzero(~(np.isfinite(request) & (request >= 0)))[0])
            raise SimulationError(f'Negative flow rates: {self.flows[bad]} asks {request[bad]:g} at {t:g} h')
        if (
            np.isnan(found).any()
            or (capacity < 0).any()
            or (end_capacity < 0).any()
            or not (np.isfinite(end_request) & (end_request >= 0)).all()
        ):
            raise SimulationError(f'{self.stores[0]}: a capacity or a request below zero at {t:g} h')
        return Asked(request, capacity, end_request, end_capacity)

    def rates(self, t, y):
        """The rate of each flow at time t and state y, with the flags of the segment."""
        self.evaluations += 1
        if self.evaluations > self.plan.numerics.max_evaluations:
            raise SimulationError('Numerical evaluation budget exceeded')
        trial = np.minimum(np.maximum(y, self.lower), self.upper)
        instant = Instant(self.net, self.asked(t, trial), self.lower_flags, self.upper_flags)
        return instant.rates()

    def field(self, t, y):
        return self.incidence @ self.rates(t, y)

    def pattern(self):
        """The sparse pattern of the Jacobian for the flags of the segment."""
        net, count = self.net, len(self.stores)
        instant = Instant(
            net,
            self.asked(self.t, np.minimum(np.maximum(self.y, self.lower), self.upper)),
            self.lower_flags,
            self.upper_flags,
        )
        reads = [list(found) for found in self.reads]
        coupled = [f for f in range(len(self.flows)) if instant.coupled(f)]
        for part in instant.parts(coupled):
            joined = sorted({s for f in part for s in self.reads[f]})
            for f in part:
                reads[f] = joined
        rows, columns = [], []
        for f, found in enumerate(reads):
            for end in (net.source[f], net.sink[f]):
                if end >= 0:
                    rows += [end] * len(found)
                    columns += found
        rows += list(range(count))
        columns += list(range(count))
        return sp.csr_array((np.ones(len(rows)), (rows, columns)), shape=(count, count))

    # ---- the segments -----------------------------------------------------------------------------

    def _flags(self):
        """The flags of a new segment: a store on a bound is held there while its sharing keeps it."""
        y, lower, upper = self.y, self.lower, self.upper
        at_lower, at_upper = y <= lower + self.atol, y >= upper - self.atol
        y[at_lower] = lower[at_lower]
        y[at_upper] = upper[at_upper]
        self.lower_flags[:], self.upper_flags[:] = at_lower, at_upper
        for _ in range(len(y) + 1):
            change = self.field(self.t, y)
            leaving = (self.lower_flags & (change > self.atol)) | (self.upper_flags & (change < -self.atol))
            if not leaving.any():
                break
            self.lower_flags &= ~leaving
            self.upper_flags &= ~leaving

    def _record(self, solution, start, end):
        """The pieces of the kept stores and actual rates from start to end."""
        recorder = self.recorder
        if end <= start:
            return
        if self.kept_stores:
            tolerance = np.maximum(self.atol[self.kept_stores], 1e-300)
            states = lambda times: np.array([solution(at)[self.kept_stores] for at in times])  # noqa: E731
            for k, pieces in zip(self.kept_stores, fitted(states, start, end, tolerance)):
                recorder.add_pieces(self.stores[k], pieces)
        if self.kept_flows:
            evaluations = self.evaluations
            tolerance = np.array(
                [recorder.tolerance.get(f'{self.flows[k]}.actual_rate', 1e-9) for k in self.kept_flows]
            )

            def delivered(times):
                return np.array([self.rates(at, solution(at))[self.kept_flows] for at in times])

            for k, pieces in zip(self.kept_flows, fitted(delivered, start, end, tolerance)):
                recorder.add_pieces(f'{self.flows[k]}.actual_rate', pieces)
            self.evaluations = evaluations

    def _crossing(self, solution, start, end, k, level):
        """The first time in [start, end] at which store k's dense value passes `level`."""
        crossing = self.plan.numerics.crossing
        below = solution(start)[k] < level
        left, right = start, end
        while right - left > crossing:
            middle = 0.5 * (left + right)
            if (solution(middle)[k] < level) == below:
                left = middle
            else:
                right = middle
        return right

    def advance(self, until):
        """The set from its time to `until`, segment by segment."""
        if until <= self.t:
            return
        numerics = self.plan.numerics
        while self.t < until:
            self._flags()
            first = self.t
            solver = Radau(
                self.field,
                self.t,
                self.y.copy(),
                until,
                rtol=numerics.rtol,
                atol=self.atol,
                jac_sparsity=self.pattern(),
            )
            ended = False
            while solver.status == 'running' and not ended:
                self.run.now = solver.t
                try:
                    message = solver.step()
                except (ExpressionError, ArithmeticError, ValueError) as problem:
                    raise SimulationError(f'Rate evaluation failed at {solver.t:g} h: {problem}') from None
                if solver.status == 'failed':
                    raise SimulationError(f'The integration failed at {solver.t:g} h: {message}')
                start, end = solver.t_old, solver.t
                solution = solver.dense_output()
                y = solution(end)
                free = ~(self.lower_flags | self.upper_flags)
                events = []
                for k in np.flatnonzero(free & (y < self.lower)).tolist():
                    events.append((self._crossing(solution, start, end, k, self.lower[k]), k))
                for k in np.flatnonzero(free & (y > self.upper)).tolist():
                    events.append((self._crossing(solution, start, end, k, self.upper[k]), k))
                for k in np.flatnonzero(self.lower_flags & (y > self.lower + self.atol)).tolist():
                    events.append((self._crossing(solution, start, end, k, self.lower[k] + self.atol[k]), k))
                for k in np.flatnonzero(self.upper_flags & (y < self.upper - self.atol)).tolist():
                    events.append((self._crossing(solution, start, end, k, self.upper[k] - self.atol[k]), k))
                if events:
                    end = min(at for at, _ in events)
                    y = solution(end)
                    ended = True
                self._record(solution, start, end)
                self.t, self.y = end, np.array(y, dtype=float)
                self.run.now = end
            if not ended and self.t <= first:
                raise SimulationError(f'Integration made no progress at {self.t:g} h')
            if self.t >= until:
                break
        self.t = until
