"""The sparse integrator: a connected set whose rates move, of any size (D3), on one network.

A set runs here when a request or a capacity of its flows or endpoints reads a store that moves (or
the time), and it is no component of the continuous engine (`plan.py`, `Connected.way`): it shares
stores between flows, has endpoint settings, has a route or a flow with legs, or holds more stores
than a component may. Its state is the vector of its stores; its rates at a time and a state are
the local sharing of the network (`network.Instant`) of what its connections and endpoints ask
there. One evaluation touches only the nonzeros: the settings are evaluated as arrays (`Vector`: a
formula that a template's members share is evaluated once over their rows, with
`napkin/core/arrays`), the sharing of the flows that meet no bound is one array operation, and the
change of each store is one product with the sparse incidence of the connections. A route's signed
request may cross zero: its legs carry the positive parts of its rate, which stays continuous.

SciPy's Radau integrates it step by step, with the sparse pattern of its Jacobian: the stores that the
settings of a flow read, joined across each coupled part. The flags of the bounds hold through a
segment, and a store held on a bound is read at its bound. A segment ends where a store reaches a
bound, or where a store held on a bound leaves it; the step is cut at that time, found in the step's
dense output to within the crossing tolerance of the run, the store is put on its bound, and a new
segment starts from there with its flags. A failure in an evaluation is timed at the step where it
happens. A failure of the solver, or `integrate.STALLED_STEPS` steps in a row each shorter than the
crossing tolerance, stops the run; where a setting reads a store through a condition, the failure
says that the rates chatter there and names the stores and the flows.

The recorder takes the pieces of the stores and of what the network gives of each flow (an actual
rate, a route's signed rate, a served fraction) that the record keeps, fitted step by step to the
step's dense output (`record.fitted`).
"""

from __future__ import annotations

import math

import numpy as np
import scipy.sparse as sp
from scipy.integrate import Radau

from ...core import arrays
from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ..continuous import integrate
from ..errors import SimulationError
from .collections import combined
from .lines import asked_of
from .network import SIDES, Asked, Instant, network_of
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
    """One connected set on the sparse integrator from the time `t` on (see the module), a way of a
    run (`ways.py`): each step of the solver is made when the run first asks for its end (`peek`), as
    far as the next moment that the run knows (`run.limit`), and committed when the run reaches its
    end (`step`), or cut at a moment inside it (`cut`)."""

    def __init__(self, run, connected, values, t, key):
        plan = self.plan = run.plan
        sizes = run.sizes
        self.key, self.alive = key, True
        self.solver, self.pending = None, None
        self.run, self.recorder = run, run.recorder
        stores = list(connected.stores)
        place = self.place = {name: k for k, name in enumerate(stores)}
        self.net, connections, self.recorded = network_of(run, [connected], stores)
        self.stores, self.flows = stores, list(self.net.flows)
        self.stepped = frozenset(connected.stepped)
        self.capped = [k for k, connection in enumerate(connections) if connection.capacity is not None]
        self.end_settings = []  # (side, store, which)
        names = [connection.request for connection in connections]
        names += [connections[k].capacity for k in self.capped]
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
        self.t = float(t)
        net = self.net
        self.incidence = sp.csr_array(
            (
                np.r_[-np.ones(np.sum(net.source >= 0)), np.ones(np.sum(net.sink >= 0))],
                (
                    np.r_[net.source[net.source >= 0], net.sink[net.sink >= 0]],
                    np.r_[np.flatnonzero(net.source >= 0), np.flatnonzero(net.sink >= 0)],
                ),
            ),
            shape=(len(stores), len(connections)),
        )
        # The stores that the settings of each flow read, and those of the endpoints at its ends.
        self.reads = []
        for f in self.flows:
            found = plan.expansion_of(plan.settings_of(plan.flows[f]))
            self.reads.append(sorted(place[name] for name in found.leaves if name in place))
        self.evaluations = 0
        self.lower_flags = np.zeros(len(stores), dtype=bool)
        self.upper_flags = np.zeros(len(stores), dtype=bool)
        wanted = run.recorder.wanted
        self.kept_stores = [k for k, name in enumerate(stores) if wanted(name)]
        self.kept_flows = [k for k, name in enumerate(self.recorded) if wanted(name)]
        # The stores of the set that a setting reads through a condition, with those flows.
        self.switches = {}
        for f in self.flows:
            for store in self._conditioned(plan.settings_of(plan.flows[f])):
                if store in place:
                    self.switches.setdefault(store, []).append(f)
        self.brief, self.brief_from = 0, None  # the steps in a row shorter than a moment (`_count`)

    def _conditioned(self, names):
        """The stores that the settings `names` read through a comparison or an if/else."""
        plan, found = self.plan, set()
        for name in names:
            for formula in plan.expanded(name).formulas | {name}:
                node = getattr(plan.values.get(formula), 'node', None)
                switches = node is not None and any(
                    isinstance(part, (nodes.IfElse, nodes.Compare)) for part in nodes.walk(node)
                )
                if switches:
                    found |= plan.expanded(formula).leaves & plan.moving
        return found

    # ---- the field --------------------------------------------------------------------------------

    def asked(self, t, y):
        """What the connections and the endpoints ask at time t and state y."""
        count, size = len(self.stores), len(self.net.source)
        found = self.settings(t, y)
        request = asked_of(self.net, found[:size], t)
        capacity = np.full(size, math.inf)
        capacity[self.capped] = found[size : size + len(self.capped)]
        end_request, end_capacity = np.zeros((2, count)), np.full((2, count), math.inf)
        for (side, s, which), number in zip(self.end_settings, found[size + len(self.capped) :].tolist()):
            (end_request if which == 'request' else end_capacity)[side, s] = number
        if (
            np.isnan(found).any()
            or (capacity < 0).any()
            or (end_capacity < 0).any()
            or not (np.isfinite(end_request) & (end_request >= 0)).all()
        ):
            raise SimulationError(f'{self.stores[0]}: a capacity or a request below zero at {t:g} h')
        return Asked(request, capacity, end_request, end_capacity)

    def values(self, t, y):
        """What the network gives of each flow at time t and state y, with the flags of the segment,
        and the rate of each connection."""
        self.evaluations += 1
        if self.evaluations > self.plan.numerics.max_evaluations:
            raise SimulationError('Numerical evaluation budget exceeded')
        # A store held on a bound through the segment is on it: what its settings read of it is
        # the bound, not the roundoff of the integrator within its tolerance.
        trial = np.minimum(np.maximum(y, self.lower), self.upper)
        trial[self.lower_flags] = self.lower[self.lower_flags]
        trial[self.upper_flags] = self.upper[self.upper_flags]
        asked = self.asked(t, trial)
        values = Instant(self.net, asked, self.lower_flags, self.upper_flags).values()
        return values, self.net.carried(values, asked)

    def field(self, t, y):
        return self.incidence @ self.values(t, y)[1]

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
        for c, f in enumerate(net.of.tolist()):
            for end in (net.source[c], net.sink[c]):
                if end >= 0:
                    rows += [end] * len(reads[f])
                    columns += reads[f]
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
            tolerance = np.array([recorder.tolerance.get(self.recorded[k], 1e-9) for k in self.kept_flows])

            def delivered(times):
                return np.array([self.values(at, solution(at))[0][self.kept_flows] for at in times])

            for k, pieces in zip(self.kept_flows, fitted(delivered, start, end, tolerance)):
                recorder.add_pieces(self.recorded[k], pieces)
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

    def _count(self, start, end):
        """A step of the solver from start to end: after `integrate.STALLED_STEPS` steps in a row
        that are each shorter than the shortest time between two moments that the run tells apart
        (`Numerics.crossing`), across the segments, the run stops: it has stalled."""
        if end - start >= self.plan.numerics.crossing:
            self.brief, self.brief_from = 0, None
            return
        if not self.brief:
            self.brief_from = float(start)
        self.brief += 1
        if self.brief >= integrate.STALLED_STEPS:
            raise SimulationError(
                self._failed(
                    end,
                    f'the steps of the solver stayed shorter than {self.plan.numerics.crossing:g} h for '
                    f'{integrate.STALLED_STEPS} steps in a row, from t = {self.brief_from:g} h',
                )
            )

    def _failed(self, t, why):
        """What a failure of the solver at time t says: why, and where a setting reads a store through
        a condition, that the rates switch back and forth there (chattering), with the stores and the
        flows."""
        found = f'The run stops at t = {t:g} h: {why}'
        if not self.switches:
            return found
        stores = ', '.join(sorted(self.switches))
        flows = ', '.join(sorted({f for named in self.switches.values() for f in named}))
        return (
            f'{found}. chattering: the rates of {flows} read {stores} through a condition, and switch '
            'back and forth there: each branch takes the state back across the switch. A condition that '
            'turns the outflows of a stock off when it is empty does this when they ask for more than '
            'comes in: remove the condition, as the engine gives the outflows of an empty stock what '
            'comes in'
        )

    # ---- the interface of a way (`ways.py`) ------------------------------------------------------

    def begin(self):
        """Nothing yet: the first step is made when the run asks for it."""

    def retire(self, key):
        """The set leaves the run's ways."""
        self.alive = False

    def refresh(self, t):
        """At a key time: the steps start again there."""
        self.cut(t)

    def peek(self):
        """The end of the next step of the solver, which is made now if it is not yet: a store that
        reaches a bound, or leaves the bound that holds it, ends it there."""
        if self.pending is not None:
            return self.pending[1]
        until = self.run.limit
        if self.t >= until:
            return math.inf
        if self.solver is None:
            self._flags()
            numerics = self.plan.numerics
            self.solver = Radau(
                self.field,
                self.t,
                self.y.copy(),
                until,
                rtol=numerics.rtol,
                atol=self.atol,
                jac_sparsity=self.pattern(),
            )
            self.first = self.t
        solver = self.solver
        self.run.now = solver.t
        try:
            message = solver.step()
        except (ExpressionError, ArithmeticError, ValueError) as problem:
            raise SimulationError(f'Rate evaluation failed at {solver.t:g} h: {problem}') from None
        if solver.status == 'failed':
            raise SimulationError(self._failed(solver.t, f'the solver failed ({message})'))
        start, end = solver.t_old, solver.t
        self._count(start, end)
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
        ended = bool(events) or solver.status != 'running'
        if events:
            end = min(at for at, _ in events)
            y = solution(end)
        if ended and end <= self.first:
            raise SimulationError(f'Integration made no progress at {end:g} h')
        self.pending = (start, end, solution, np.array(y, dtype=float), ended)
        return end

    def step(self):
        """Commit the next step: the stores and the rates of the set move through it."""
        start, end, solution, y, ended = self.pending
        self.pending = None
        self._record(solution, start, end)
        self.t, self.y = end, y
        self.run.now = end
        if ended:
            self.solver = None
        return list(self.stores), list(self.recorded), ended

    def snap(self):
        """The next event at the time of a moment: committed as any other, with what it changes."""
        stores, rates, _ = self.step()
        return stores + rates

    def cut(self, t):
        """The run stands at time t inside the next step: the step up to t is committed, and the
        solver starts again from there."""
        if self.pending is None or t >= self.pending[1]:
            return
        start, _, solution, _, _ = self.pending
        self.pending, self.solver = None, None
        if t <= start:
            return
        self._record(solution, start, t)
        self.t, self.y = float(t), np.array(solution(t), dtype=float)

    def level_at(self, store, t):
        """The value of a store at time t: at the present time, or inside the next step."""
        k = self.place[store]
        if self.pending is None or t <= self.pending[0]:
            return float(self.y[k])
        return float(self.pending[2](min(t, self.pending[1]))[k])

    def rate_at(self, name, t):
        """What the network gives of a flow at time t (an actual rate, a route's signed rate or a
        served fraction)."""
        y = (
            self.y
            if self.pending is None or t <= self.pending[0]
            else self.pending[2](min(t, self.pending[1]))
        )
        evaluations = self.evaluations
        try:
            return float(self.values(t, y)[0][self.recorded.index(name)])
        finally:
            self.evaluations = evaluations

    def linear(self, store):
        """A store of the sparse integrator moves on a curve."""
        return None

    def advance(self, until):
        """The set from its time to `until`, step by step."""
        while self.peek() <= until:
            self.step()
        self.cut(until)
