"""A component: one connected set of stores and flows, which the continuous engine runs.

The continuous engine (`engine/continuous/`) runs it: the field and the allocation, the bounds and
the stock faces, the closed forms of a segment and the numerical segment
(`continuous/segment.advance`). This module gives that engine what it reads of a system, and makes
the segments of the set one after the other.

- `Network`: what the continuous engine reads of a system, for the stores, flows and formulas of
  one connected set. A plan's set gives it (`run.py`), with its expressions over engine names: the
  stores are its state, the inputs and the other values that do not move between moments are
  literals, and each formula that a rate reads is in `computed`. A value that has none now
  (`since(e)` before the first start) is no literal: a rate fails where it reads it, on a side that
  it takes (`continuous/system.Formulas`), and nowhere else. `Network.of` gives the system of
  one run: its tolerances, its inputs and its numerical settings.
- `Held`: the allocation of a component, which cuts a flow at a bound to what the store can pass.
  That is local sharing (`network.py`) where each store meets one flow on each side, unless a flow
  into a store at its lower bound, or out of a store at its upper bound, could carry more than its
  request: local sharing would then raise it (a request is soft, D15). Where that can be, the run
  stops with a failure that names the store, never with the other answer.
- `Component`: the set in a run. From its start, it makes its segments one after the other, each
  from where the one before it ended: a segment ends at the horizon, where a store reaches or leaves
  a bound, or where a rate changes its branch. Each segment (`Segment`) has the function of the time
  that gives the state through it and the states at its two ends, the last with the bounds that it
  reaches settled. A segment that starts at a switch that its state crosses there (at a moment that
  falls on a crossing, or at the root of one, a roundoff short of it or on it) starts on its far
  side (`settle`, `integrate.starting_sides`), as one a roundoff short of a bound starts on it: a run
  is the same whether a crossing falls on a moment or not. While the segment is the present one,
  `delivered` gives the rates that its flows deliver at times inside it: the bounds and faces of
  the segment hold then.
- `ComponentWay`: the set as a way of a run. Beside the values of its next segment, it gives the
  form of that segment to the reader of a condition that watches its stores (`breaks`, `motion`;
  `continuous/dense.py`): a line, the closed form of compartments, or the solver's steps, each the
  cubic of its dense output. Between two segments its state rests on the bounds that the last one
  found (a read at a moment sees the rates that the set had there); a set built or restored at a
  moment finds the bounds of its state there before its rates are read, as its first segment finds
  them again (`refresh_bounds`), with the far sides of the switches that it crosses there, so that
  a read after the settling sees the rates that it settled (a starved flow carries nothing) and that
  hold from the moment on. At a switch reached at the time of a moment, the settling rebuilds
  its flows after the stages (`switched_at`). A set built
  at a horizon that is a moment of a run that goes
  on too records the stores and the rates of its state there on those bounds (`finish`): a read at
  the horizon of a run that ends there is the read of a run that goes on, whose first segment of
  the set starts there.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace

import numpy as np

from ...core.errors import ExpressionError
from ...expressions import names_in
from ..allocation import Allocation
from ..continuous import dense
from ..continuous.bounds import check_bounds, correct_boundary_roundoff, refresh_bounds
from ..continuous.fields import Field
from ..continuous.integrate import at_their_switch, starting_sides, surfaces_of
from ..continuous.kernels import Affine, MatrixExponential
from ..continuous.segment import advance
from ..continuous.system import Context, solver_step
from ..continuous.system import Run as State
from ..continuous.walk import walked
from ..errors import SimulationError
from .collections import node_of


@dataclass(frozen=True)
class NetFlow:
    rate: object
    source: str | None
    target: str | None
    allocation: str | None


@dataclass(frozen=True)
class NetGroup:
    policy: str
    order: tuple
    capacity: object


@dataclass(frozen=True)
class NetCoupling:
    flows: tuple


@dataclass(frozen=True)
class NetQuantity:
    kind: str


@dataclass(frozen=True)
class NetRate:
    expr: object


@dataclass(frozen=True)
class NetCheck:
    expr: object
    path: object
    message: object


@dataclass(frozen=True)
class NetSum:
    total: object
    parts: tuple
    tolerance: object
    path: object


@dataclass(frozen=True)
class NetParts:
    """The parts that the continuous engine reads of a system beside its quantities and flows: the
    explicit rates of quantities, the inputs, and the checks of the state and the sums that it
    reads at each state that a solver accepts (`continuous/bounds.check_conditions`). A program has
    no explicit rate, and this slice no check of the state, so a plan gives none of them."""

    rates: dict
    parameters: tuple
    state_checks: dict
    partitions: dict


class Crossings:
    """The watched crossings whose quantity is proved to move to one side only: (rule, instance)."""

    def __init__(self, rules):
        self.rules = frozenset(rules)

    def __contains__(self, key):
        return key[0] in self.rules


class Network:
    """See the module. `kinds` gives each store the kind that the continuous engine reads: `stock`
    (a store with a lower bound of zero that flows draw on), `cumulative` (a store that flows only
    fill: it never falls) or `state`."""

    def __init__(
        self,
        name,
        names,
        kinds,
        lower,
        upper,
        flows,
        rates,
        groups,
        couplings,
        computed,
        evolving,
        parameters,
        store_names,
        proven,
        monotone_crossings,
        checks=None,
        sums=None,
    ):
        self.name = name
        self.state_ids = tuple(names)
        self.index = index = {name: i for i, name in enumerate(self.state_ids)}
        self.quantities = {name: NetQuantity(kinds[name]) for name in names}
        self.lower, self.upper = np.array(lower, dtype=float), np.array(upper, dtype=float)
        self.monotone = np.array([kinds[name] == 'cumulative' for name in names], dtype=bool)
        self.flows = dict(flows)
        self.flow_ids = tuple(self.flows)
        self.flow_index = {key: j for j, key in enumerate(self.flow_ids)}
        self.groups, self.couplings = dict(groups), dict(couplings)
        self.computed = dict(computed)
        self.evolving = set(evolving)
        self.block = tuple(name for name in names if name in self.evolving)
        self.discrete = [i for i, name in enumerate(names) if name not in self.evolving]
        self.discrete_rows = np.array(self.discrete, dtype=int)
        self.flow_matrix = np.zeros((len(names), len(self.flows)))
        self.legs = {name: ([], [], []) for name in names}
        self.flows_of = {name: [] for name in names}
        for key, flow in self.flows.items():
            for end in dict.fromkeys((flow.source, flow.target)):
                if end:
                    self.flows_of[end].append((key, flow))
        for j, flow in enumerate(self.flows.values()):
            source, target = flow.source, flow.target
            if source:
                self.flow_matrix[index[source], j] -= 1
                self.legs[source][0].append((j, target))
                if not target:
                    self.legs[source][2].append(j)
            if target:
                self.flow_matrix[index[target], j] += 1
                self.legs[target][1].append((j, source))
                if not source:
                    self.legs[target][2].append(j)
        self.abs_flow_matrix = np.abs(self.flow_matrix)
        self.resolved = NetParts(dict(rates), tuple(parameters), dict(checks or {}), dict(sums or {}))
        self.derivative_ids = list(rates)
        self.derivative_rows = np.array([index[name] for name in self.derivative_ids], dtype=int)
        self.proven_faces = tuple(name for name in names if name in proven)
        self.proven_face_set = frozenset(self.proven_faces)
        self.monotone_crossings = Crossings(monotone_crossings)
        self.group_indices = {
            gid: [j for j, flow in enumerate(self.flows.values()) if flow.allocation == gid]
            for gid in self.groups
        }
        self.coupling_members = [
            [self.flow_index[key] for key in coupling.flows] for coupling in self.couplings.values()
        ]
        self.zero_floor_stocks = np.array(
            [self.lower[i] == 0 and kinds[name] == 'stock' for i, name in enumerate(names)], dtype=bool
        )
        self.store_names = frozenset(store_names)
        # The names that each expression reads are found once.
        self._expanded, self._reads = {}, {}

    def of(self, numerics, units, horizon, cap, solver_step, atol, slack, values):
        """The system of one run: its numerical settings, its step cap and the longest step of its
        solver, the absolute tolerance and the lower slack of each store, and the values of the
        inputs that it reads, which its generated programs hold as literals."""
        own = copy.copy(self)
        own.cfg, own.units, own.horizon = numerics, units, horizon
        own.max_step, own.solver_step = cap, solver_step
        own.atol, own.ledger_slack = np.array(atol, dtype=float), np.array(slack, dtype=float)
        own.values = {name: values[name] for name in self.resolved.parameters}
        hidden = set(self.state_ids) | self.store_names | set(self.computed) | {'t'}
        own.known = {name: value for name, value in own.values.items() if name not in hidden}
        own.analysis, own.face_proofs = {}, {}
        return own

    @property
    def bounds(self):
        return self.lower, self.upper, self.ledger_slack, self.atol

    # The names that an expression reads through formulas, as the continuous engine reads them.
    def read(self, name):
        """The code of a generated program of the run, `program(Y, T, S, V, R)`, that reads a name that
        is not a literal: the time T, an entry of the store S, a store of the state Y or an input of V."""
        if name == 't':
            return 'T', False
        if name in self.store_names:
            return f'S[{name!r}]', False
        if name in self.index:
            return f'Y[{self.index[name]}]', False
        if name in self.values:
            return f'V[{name!r}]', False
        return f'_missing({name!r})', True

    def expanded_frozen(self, expr):
        """The names other than formulas that an expression reads, through formulas, as one shared
        frozen set (`expanded_names`)."""
        found = self._expanded.get(expr)
        if found is None:
            found = self._expanded[expr] = walked(self._expand(expr, set()))[0]
        return found

    def expanded_names(self, expr):
        """The names other than formulas that an expression reads, through formulas: its stores,
        its inputs and the time, which is what its readers ask of it (whether it reads what moves).
        Followed with no recursion (`walk.walked`), so a chain of formulas is no limit, and each
        formula keeps its own once, shared with the formula above it where that adds none, so a
        chain costs no more than its links (re-audit 15)."""
        return set(self.expanded_frozen(expr))

    def _expand(self, expr, path):
        """The names other than formulas that `expr` reads through formulas, and whether a formula on
        the path reached itself (a plan refuses such a formula, so this is a guard), as a computation
        of `walk.walked`: each formula that it reads and that is not known yet (`_reads`) is one that
        it yields. `path` holds the formulas on the way to it, which the driver walks depth first."""
        leaves, found, cyclic = set(), [], False
        for name in names_in(expr):
            if name not in self.computed:
                leaves.add(name)
                continue
            if name in path:
                cyclic = True
                continue
            kept = self._reads.get(name)
            if kept is None:
                path.add(name)
                try:
                    kept, hit = yield self._expand(self.computed[name]['expr'], path)
                finally:
                    path.discard(name)
                cyclic |= hit
                if not hit:
                    self._reads[name] = kept
            found.append(kept)
        if len(found) == 1 and leaves <= found[0]:
            return found[0], cyclic
        return frozenset(leaves.union(*found)), cyclic


@dataclass
class Segment:
    """One segment of a component: from `start` to `end`, the function of the time that gives the
    state (`solution`), the states at its two ends, the last with the bounds that it reaches settled,
    the solver's result for a numerical segment (`numerical`: its accepted times are `t`), the
    places in the state of the quantities that it brings to a bound at its end (`reached`), and the
    switching surfaces at their switch at its start (`switches`)."""

    start: float
    end: float
    solution: object
    first: np.ndarray
    last: np.ndarray
    numerical: object = None
    reached: tuple = ()
    switches: frozenset = frozenset()


class Held(Allocation):
    """See the module. `rigid` holds the flows that never carry more than their request."""

    def __init__(self, system, rigid):
        super().__init__(system)
        self.rigid = frozenset(rigid)

    def bound_allocation(self, state, base, requested, unconstrained, bound_key):
        found, faces = super().bound_allocation(state, base, requested, unconstrained, bound_key)
        if found is requested:
            return found, faces
        s = self.system
        for j in np.flatnonzero(found < requested - 1e-12 * np.maximum(1.0, requested)).tolist():
            flow = s.flows[s.flow_ids[j]]
            for store, near in ((flow.source, 1), (flow.target, 0)):
                if not store:
                    continue
                # The flow on the other side of the store, which local sharing could raise.
                others = [k for k, _ in s.legs[store][near]]
                if any(s.flow_ids[k] not in self.rigid for k in others):
                    raise SimulationError(
                        f'{store}: rests on a bound between a flow in and a flow out whose rates move, '
                        'where local sharing could raise a flow above its request; give the flows of '
                        'this store capacities at their requests'
                    )
        return found, faces


class Component:
    """See the module."""

    def __init__(self, system, context, start, rigid=()):
        self.system, self.context = system, context
        self.state = State(0.0, np.array(start, dtype=float), {})
        self.field = Field(system, self.state, context)
        self.field.allocation = Held(system, rigid)

    def guards(self, env):
        """The level rules that a segment watches: none, in this slice."""
        return []

    def next(self, horizon):
        """The next segment, from the present time and state as far as the horizon at most. A store
        that reaches its face within the roundoff of the time is settled there first: that gives a
        segment of no length, whose last state has the face settled."""
        s, state, field, diagnostics = self.system, self.state, self.field, self.context.diagnostics
        self.settle()
        start = state.time
        switches = at_their_switch(s, field.environment, start, state.y)
        found = advance(s, state, field, self, self.context, horizon)
        first = state.y.copy()
        if found.rounded:
            correct_boundary_roundoff(s, diagnostics, start, state.y, found.rounded)
            check_bounds(s, state.y)
            reached = tuple(sorted(found.rounded))
            return Segment(start, start, None, first, state.y.copy(), reached=reached, switches=switches)
        solution, numerical = found.solution, found.numerical
        last = np.array(solution(found.end) if numerical is None else numerical.y[:, -1], dtype=float)
        correct_boundary_roundoff(s, diagnostics, found.end, last, found.targets)
        if numerical is not None:
            if found.end <= start:
                raise SimulationError('Integration made no progress at a boundary')
            # The accepted points of the solver are checked too: a fine output cannot hide a state
            # outside its bounds.
            for k in range(len(numerical.t) - 1):
                check_bounds(s, numerical.y[:, k])
        check_bounds(s, last)
        reached = tuple(sorted(found.targets or ()))
        return Segment(start, found.end, solution, first, last, numerical, reached, switches)

    def settle(self):
        """The state at the start of a segment, or at a moment before one: the bounds that it rests
        on (`refresh_bounds`), the faces of the segment cleared, and the sides of the switches that it
        crosses there (`integrate.starting_sides`), so that its rates are those that hold from there
        on."""
        s, state, field = self.system, self.state, self.field
        state.switches, state.clock = (), None
        refresh_bounds(s, state, field)
        state.right_faces.clear()
        state.zero_faces.clear()
        starting_sides(s, state, field)

    def switched(self, segment, t, last):
        """The switches of a segment's rates that its state reaches at time t, with the state there:
        the surfaces at their switch there that were at none at the start of the segment."""
        if t <= segment.start:
            return frozenset()
        return at_their_switch(self.system, self.field.environment, t, last) - segment.switches

    def deciding(self):
        """{a switching surface: the flows whose rates read it, through formulas}."""
        s = self.system
        if 'deciding' not in s.analysis:
            formulas = {name: found['expr'] for name, found in s.computed.items()}
            moving = s.evolving | {'t'}
            found = {}
            for key, flow in s.flows.items():
                for surface in surfaces_of(
                    [flow.rate], formulas, lambda node: s.expanded_names(node) & moving
                ):
                    found.setdefault(surface, []).append(key)
            s.analysis['deciding'] = found
        return s.analysis['deciding']

    def delivered(self, segment, times):
        """The rates that the flows deliver at times inside the present segment: one row for each
        time. The evaluations of the field that the record asks count for no budget of the run."""
        state, field = self.state, self.field
        evaluations = state.evaluations
        rows = []
        try:
            for at in times:
                field.rates(at, self.context.project(segment.solution(at)))
                rows.append(np.array(field.delivered, dtype=float))
        finally:
            state.evaluations = evaluations
        return np.array(rows).reshape(len(rows), len(self.system.flow_ids))

    def proceed(self, segment):
        """The next segment starts where this one ended."""
        self.state.time, self.state.y = segment.end, segment.last.copy()


class ComponentWay:
    """One connected set on the continuous engine, as a way of a run (`ways.py`), from the time `t`
    on. Its segments come one after the other: each is made when the run first asks for its next
    event (`peek`), as far as the next moment that the run knows (`run.limit`), and committed when
    the run reaches its end (`step`), or cut at a moment inside it (`cut`): the state there is the
    segment's at that time. The recorder takes the pieces of each segment as it is committed."""

    def __init__(self, run, connected, values, t, key, captured=None):
        plan, numerics = run.plan, run.plan.numerics
        self.run, self.key, self.connected = run, key, connected
        self.stores, self.flows = list(connected.stores), list(connected.flows)
        self.alive, self.pending, self.still = True, None, 0
        self.bounded = False  # whether its state rests on the bounds that it found (`_settle`)
        self.reached = []  # (the end of a segment, the switches that it reached there)
        self._drift = None  # the rates of the stores at the present state, once read (`drift`)
        stores = connected.stores
        sources = {plan.flows[flow].source for flow in connected.flows}
        sinks = {plan.flows[flow].sink for flow in connected.flows}
        kinds = {}
        for name in stores:
            if name in sinks and name not in sources:
                kinds[name] = 'cumulative'
            elif run.bounds[name][0] == 0:
                kinds[name] = 'stock'
            else:
                kinds[name] = 'state'
        flows = {
            name: NetFlow(plan.flows[name].rate, plan.flows[name].source, plan.flows[name].sink, None)
            for name in connected.flows
        }
        computed = {}
        for name in connected.formulas:
            if name in plan.reductions:
                try:
                    node = node_of(plan.reductions[name], run.kept_of(name))
                except ExpressionError as problem:
                    raise SimulationError(str(problem)) from None
            else:
                node = run.shared.definition(name, plan.values[name]).node
            computed[name] = {'expr': node}
        leaves = set()
        for flow in flows.values():
            leaves |= plan.expansion(flow.rate).leaves
        stepped = set(connected.stepped)
        known, missing = {name: values[name] for name in stores}, {}
        if captured is None:
            for name in sorted(name for name in leaves if name not in stores and name not in stepped):
                try:
                    known[name] = run.held(name)
                except ExpressionError as problem:
                    # A value that has none now (`since(e)` before the first start): a rate fails
                    # where it reads it, on a side that it takes (`continuous/system.Formulas`).
                    missing[name] = str(problem)
        else:
            known, missing = dict(captured[0]), dict(captured[1])  # what it had (`saved.py`)
        parameters = sorted(name for name in known if name not in stores)
        network = Network(
            stores[0],
            stores,
            kinds,
            [run.bounds[name][0] for name in stores],
            [run.bounds[name][1] for name in stores],
            flows,
            {},
            {},
            {},
            computed,
            set(stores),
            parameters,
            stepped,
            (),
            (),
        )
        sizes = run.sizes
        atol = [numerics.atol_factor * sizes[name] for name in stores]
        slack = [
            a + (numerics.rtol * sizes[name] if kinds[name] == 'cumulative' else 0.0)
            for a, name in zip(atol, stores)
        ]
        system = network.of(
            numerics, plan.units, plan.horizon, run.cap, solver_step(numerics), atol, slack, known
        )
        context = Context(
            stores,
            {name: known[name] for name in parameters},
            [(name, computed[name]['expr']) for name in connected.formulas],
            plan.units,
            system.bounds,
            run.settings,
            missing,
        )
        if captured is None:
            rigid = [name for name in connected.flows if plan.rigid(plan.flows[name], run.held)]
        else:
            rigid = list(captured[2])
        # What it read when it was built, which holds while it lasts and a checkpoint saves.
        self.captured = (known, missing, rigid)
        self.component = Component(system, context, [values[name] for name in stores], rigid)
        self.component.state.time = float(t)
        self.place = {name: k for k, name in enumerate(stores)}
        self.rates = [f'{flow}.actual_rate' for flow in system.flow_ids]
        self.flow_place = {flow: k for k, flow in enumerate(system.flow_ids)}
        self._stepped(float(t))

    def _stepped(self, t):
        """The keyed reads by the time of the component at time t, in its store. One that has no
        value there is left out: a rate that reads it fails."""
        store = self.component.state.store
        for name in self.connected.stepped:
            # The value of the member that it selects, which holds between moments here: a set whose
            # keyed read selects a value that moves runs on the sparse integrator (`plan.connect`).
            try:
                store[name] = self.run.value(self.run.stepped_of(name).name_at(t), t)
            except ExpressionError:
                store.pop(name, None)

    def begin(self):
        """Nothing yet: the first segment is made when the run asks for it."""

    def refresh(self, t):
        """At a key time: the keyed reads by the time take their values there."""
        self.cut(t)
        self._stepped(t)
        self._drift = None

    def retire(self, key):
        """The set leaves the run's ways."""
        self.alive = False

    def peek(self):
        """The end of the next segment, which is made now if it is not yet."""
        if self.pending is None:
            state = self.component.state
            if state.time >= self.run.limit:
                return math.inf
            self.pending = self.component.next(self.run.limit)
            self.bounded = True  # a segment finds the bounds of its start (`Component.next`)
        return self.pending.end

    def step(self):
        """Commit the next segment: the stores and the rates of the component change there."""
        segment, self.pending = self.pending, None
        self._commit(segment)
        self.still = self.still + 1 if segment.end <= segment.start else 0
        limit = self.run.plan.configuration.limits.max_rounds
        if self.still > limit:
            raise SimulationError(f'{self.flows[0]}: {limit} segments of no length at {segment.start:g} h')
        return list(self.stores), list(self.rates), True

    def _commit(self, segment):
        component = self.component
        shared = self.run.shared
        if segment.end > segment.start and shared.at_arrival(segment.end):
            shared.ends.setdefault(self.key, segment.end)
        self.run.recorder.segment(component, segment, component.system.state_ids, self.rates)
        component.proceed(segment)
        self._drift = None
        # The switches that its segments reached, kept while they are within the time tolerance of
        # the last end: a moment there is at them (`moment.Clock`).
        end, crossing = segment.end, self.run.plan.numerics.crossing
        self.reached = [(at, found) for at, found in self.reached if end - at <= crossing]
        found = component.switched(segment, end, segment.last)
        if found:
            self.reached.append((end, found))

    def switched_at(self, t):
        """The switches of the set's rates that its state reached at time t, a moment that falls on
        their crossing (`run.next_moment`), each with a flow whose rate reads it: those that the
        segments that ended within the time tolerance of t, or that the moment cut there, brought to
        their switch."""
        crossing, deciding = self.run.plan.numerics.crossing, self.component.deciding()
        return {
            flow
            for at, found in self.reached
            if abs(t - at) <= crossing
            for a, b in found
            for flow in deciding.get((a, b), ())
        }

    def snap(self):
        """The next event at the time of a moment: committed as any other, with what it changes, and
        the stores that its segment brings to a bound at its end."""
        ids = self.component.system.state_ids
        met = [ids[k] for k in self.pending.reached]
        stores, rates, _ = self.step()
        return stores + rates, met

    def _settle(self):
        """The state rests on the bounds that it reaches at its present time, and on the far side of
        the switches that it crosses there, as the next segment finds them (`Component.settle`): a set
        built or restored at a moment, before its rates are read, and at the horizon. The evaluations
        count for no budget of the run."""
        state = self.component.state
        evaluations = state.evaluations
        try:
            self.component.settle()
        finally:
            state.evaluations = evaluations
        self.bounded, self._drift = True, None

    def finish(self, t):
        """At the horizon, where the run stands and a run that goes on has a moment too
        (`ways.finish`): a set built there, which has made no segment (and so no evaluation of its
        field, which a checkpoint keeps), records the stores and the rates of its state there, on the
        bounds that it rests on, as its first segment in a run that goes on would from there (see the
        module): each store with its rate there, each flow's rate held. A set that has made segments
        holds its values there in their pieces."""
        component, recorder = self.component, self.run.recorder
        state = component.state
        if self.pending is not None or state.time != t or state.evaluations:
            return
        if not self.bounded:
            self._settle()
        evaluations = state.evaluations
        try:
            # The rates of the stores there, which an affine first segment takes as its slopes.
            slopes = np.array(component.field.rates(state.time, state.y), dtype=float)
            delivered = np.array(component.field.delivered, dtype=float)
        finally:
            state.evaluations = evaluations
        for k, name in enumerate(component.system.state_ids):
            recorder.add(name, t, float(state.y[k]), float(slopes[k]))
        for k, name in enumerate(self.rates):
            recorder.add(name, t, float(delivered[k]), 0.0)

    def cut(self, t):
        """Commit the segment up to the moment. A bound that the segment locates at that
        moment takes part in the re-share if the store has reached it to the solver's accuracy."""
        segment = self.pending
        if segment is None or t >= segment.end:
            return
        self.pending = None
        if t <= segment.start:
            return
        last = np.array(self._state(segment, t), dtype=float)
        numerical = _cut(segment.numerical, t)
        near = ()
        if segment.reached and self.run.clock.due(segment.end, t):
            system = self.component.system
            near = tuple(k for k in segment.reached if abs(segment.last[k] - last[k]) <= system.atol[k])
        cut = Segment(
            segment.start, t, segment.solution, segment.first, last, numerical, (), segment.switches
        )
        self._commit(cut)
        return tuple(self.stores[k] for k in near)

    @staticmethod
    def _state(segment, t):
        """The state of a segment at a time inside it."""
        return segment.last if segment.end <= segment.start else segment.solution(t)

    def level_at(self, store, t):
        """The value of a store at time t: at the present time, inside the next segment, or, before
        that segment is made (at a moment), along the store's present rate (`drift`)."""
        segment, state = self.pending, self.component.state
        k = self.place[store]
        if segment is None and t > state.time:
            return float(state.y[k] + (t - state.time) * self.drift()[k])
        if segment is None or t <= segment.start:
            return float(state.y[k])
        return float(self.component.context.project(self._state(segment, min(t, segment.end)))[k])

    def drift(self):
        """The rate of each store at the present state: what a condition read an instant after a moment
        (`triggers.AFTER`) follows before the next segment is made, as a line follows its rate. The
        evaluation counts for no budget of the run."""
        if self._drift is None:
            state = self.component.state
            evaluations = state.evaluations
            try:
                self._drift = np.array(self.component.field.rates(state.time, state.y), dtype=float)
            finally:
                state.evaluations = evaluations
        return self._drift

    def rate_at(self, name, t):
        """The actual rate of a flow at time t."""
        if not self.bounded:
            self._settle()
        segment, state, field = self.pending, self.component.state, self.component.field
        k = self.flow_place[name.rsplit('.', 1)[0]]
        evaluations = state.evaluations
        try:
            if segment is None or t <= segment.start or segment.end <= segment.start:
                field.rates(state.time, state.y)
            else:
                at = min(t, segment.end)
                field.rates(at, self.component.context.project(self._state(segment, at)))
            return float(field.delivered[k])
        finally:
            state.evaluations = evaluations

    def linear(self, store):
        """The line of a store through the next segment, or None on a curve."""
        segment = self.pending
        k = self.place[store]
        if segment is None or segment.end <= segment.start:
            return float(self.component.state.y[k]), 0.0, float(self.component.state.time)
        if isinstance(segment.solution, Affine):
            return float(segment.first[k]), float(segment.solution.slope[k]), float(segment.start)
        return None

    def breaks(self, start, end):
        """The times strictly between start and end at which the form of the next segment changes: the
        ends of the steps of its solver."""
        segment = self.pending
        if segment is None or segment.numerical is None:
            return []
        return [float(at) for at in segment.numerical.t.tolist() if start < at < end]

    def motion(self, weights, start, end):
        """How the sum of the stores of `weights` ({store: weight}) moves from start to end, a piece
        inside one form of the next segment (`continuous/dense.py`). The run reads a store within its
        slack of a bound on the bound (`Context.project`): that is the margin of what it reads."""
        segment, state = self.pending, self.component.state
        rows = np.array([self.place[name] for name in weights], dtype=np.int64)
        w = np.array(list(weights.values()), dtype=float)
        _, _, slack, atol = self.component.system.bounds
        margin = float(np.abs(w) @ np.maximum(slack[rows], atol[rows]))
        if segment is None or segment.end <= segment.start:
            found = dense.held((state.y if segment is None else segment.last)[rows], w)
        elif isinstance(segment.solution, Affine):
            rate = float(w @ segment.solution.slope[rows])
            found = replace(
                dense.held(segment.solution(start)[rows], w), rate=rate, change=abs(rate) * (end - start)
            )
        elif isinstance(segment.solution, MatrixExponential):
            found = dense.of_exponential(segment.solution, rows, w, start, end)
        else:
            # The step of the solver that holds the piece: the one around its middle.
            solution = segment.solution
            k = int(np.searchsorted(solution.ts, 0.5 * (start + end), side='right')) - 1
            output = solution.interpolants[min(max(k, 0), len(solution.interpolants) - 1)]
            found = dense.of_step(output, rows, w, start, end)
        return replace(found, margin=margin)


def _cut(numerical, t):
    """The solver's result of a numerical segment, with its accepted steps up to t."""
    if numerical is None:
        return None
    cut = copy.copy(numerical)
    steps = [at for at in numerical.t if at < t] + [t]
    cut.t = np.array(steps)
    cut.y = np.array([numerical.sol(at) for at in steps]).T
    return cut
