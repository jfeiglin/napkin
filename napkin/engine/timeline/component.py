"""A component: one connected set of stores and flows, which the continuous engine runs.

The continuous engine (`engine/continuous/`) runs it: the field and the allocation, the bounds and
the stock faces, the closed forms of a segment and the numerical segment
(`continuous/segment.advance`). This module gives that engine what it reads of a system, and makes
the segments of the set one after the other.

- `Network`: what the continuous engine reads of a system, for the stores, flows and formulas of
  one connected set. A plan's set gives it (`run.py`), with its expressions over engine names: the
  stores are its state, the inputs and the other values that do not move between moments are
  literals, and each formula that a rate reads is in `computed`. `Network.of` gives the system of
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
  reaches settled. While the segment is the present one, `delivered` gives the rates that its flows
  deliver at times inside it: the bounds and faces of the segment hold then.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from ..allocation import Allocation
from ..continuous.bounds import check_bounds, correct_boundary_roundoff, refresh_bounds
from ..continuous.fields import Field
from ..continuous.segment import advance
from ..continuous.system import Run as State
from ..errors import SimulationError


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
        """The names that an expression reads, through formulas, as one shared frozen set."""
        found = self._expanded.get(expr)
        if found is None:
            found = self._expanded[expr] = frozenset(self.expanded_names(expr, ()))
        return found

    def expanded_names(self, expr, seen=None):
        """The names that an expression reads, through formulas."""
        if seen is None:
            if expr not in self._expanded:
                self._expanded[expr] = frozenset(self._expand(expr, frozenset())[0])
            return set(self._expanded[expr])
        return self._expand(expr, frozenset(seen))[0]

    def _expand(self, expr, seen):
        """The names that `expr` reads through formulas, and whether a formula on the path reached
        itself (a plan refuses such a formula, so this is a guard)."""
        from ...expressions import names_in

        names = set(names_in(expr))
        cyclic = False
        for name in list(names):
            if name not in self.computed:
                continue
            if name in seen:
                cyclic = True
                continue
            kept = self._reads.get(name)
            if kept is None:
                found, hit = self._expand(self.computed[name]['expr'], seen | {name})
                names |= found
                cyclic |= hit
                if hit:
                    continue
                kept = self._reads[name] = frozenset(found)
            names |= kept
        return names, cyclic


@dataclass
class Segment:
    """One segment of a component: from `start` to `end`, the function of the time that gives the
    state (`solution`), the states at its two ends, the last with the bounds that it reaches settled,
    and the solver's result for a numerical segment (`numerical`: its accepted times are `t`)."""

    start: float
    end: float
    solution: object
    first: np.ndarray
    last: np.ndarray
    numerical: object = None


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
        refresh_bounds(s, state, field)
        start = state.time
        state.right_faces.clear()
        state.zero_faces.clear()
        found = advance(s, state, field, self, self.context, horizon)
        first = state.y.copy()
        if found.rounded:
            correct_boundary_roundoff(s, diagnostics, start, state.y, found.rounded)
            check_bounds(s, state.y)
            return Segment(start, start, None, first, state.y.copy())
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
        return Segment(start, found.end, solution, first, last, numerical)

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
