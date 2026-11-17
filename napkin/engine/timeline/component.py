"""A component: one instance of a space whose flows need the allocation in full.

The continuous engine (`engine/continuous/`) runs it: the field and the allocation, the bounds
and the stock faces, the closed forms of a segment and the numerical segment
(`continuous/segment.advance`). This module gives that engine what it reads of a system, for the
quantities of the one instance, and gives the timeline what it reads of a block.

- `Network`: what the continuous engine reads of a system (`continuous/system.System`), for the
  quantities, flows, groups and formulas of one space. A plan makes one for each such space
  (`Plan._nets`), with the expressions as that engine reads them: the texts of the file, where a
  list over a family is the name of its aggregate and a formula of another space is in the place of
  its name. `Network.of` gives the system of one instance: its tolerances and its inputs.
- `Component`: the block of one instance in a run. The timeline starts it again at each moment that
  writes something that it reads (`start`), and reads its state at a time (`at`). Between two such
  moments the component makes its segments one after the other, each from where the one before it
  ended: a segment ends where a quantity reaches or leaves a bound, where a rate changes its branch,
  or where a watched crossing reaches its value. The end of a segment is a moment of the timeline
  for the rules and the checks that read the component (`Run.ends`), and the time of a watched
  crossing is the time of its rule (D-65). The component goes no further until the timeline has
  been at that end.

What does not move in a segment comes from the run when the component starts again: the values
that only steps change, as the store and the pinned quantities of that engine.
"""

from __future__ import annotations

import copy
from bisect import bisect_left
from dataclasses import dataclass

import numpy as np

from ..continuous.bounds import check_bounds, check_conditions, correct_boundary_roundoff, refresh_bounds
from ..continuous.fields import Field
from ..continuous.segment import advance
from ..continuous.system import Run as State
from ..continuous.system import System, run_settings
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
    """The parts that the continuous engine reads of a resolved run. The checks of the state and the
    partitions are the timeline's own: it reads them where a step or a segment changes what they
    read. A space of one instance also has here the ones that read nothing outside it
    (`Network.local`): the component reads them at each state that a solver accepts, with one
    generated program on that state (`continuous/bounds.check_conditions`)."""

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
    """See the module. The names are those of the representative of the space: each instance reads
    its own values under them."""

    # The names that an expression reads through formulas, and the code that reads a name in a
    # generated program, are those of a system.
    expanded_frozen = System.expanded_frozen
    expanded_names = System.expanded_names
    _expand = System._expand
    read = System.read

    def __init__(
        self,
        space,
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
        local=(),
    ):
        self.space = space
        # The checks and partitions of the plan that this network reads itself: ('check' or
        # 'partition', index).
        self.local = frozenset(local)
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
        # Every instance reads the same expressions: the names that each reads are found once.
        self._expanded, self._reads = {}, {}

    def of(self, run, j):
        """The system of the instance j of the space in a run: with its tolerances and its inputs."""
        own = copy.copy(self)
        own.cfg, own.units, own.horizon = run.cfg, run.registry, run.horizon
        own.max_step, own.solver_step = run.max_step, run.solver_step
        own.settings = run_settings(run.plan.resolved.time, run.cfg, run.max_step, list(run.timescales))
        own.atol = np.array([run.atol[name][j] for name in self.state_ids])
        own.ledger_slack = np.array([run.slack[name][j] for name in self.state_ids])
        own.values = {name: run.static(name, self.space, j, 0.0) for name in self.resolved.parameters}
        # One instance alone has its inputs as literals in its programs.
        # The instances of a family share the text of their programs, so they read their inputs.
        hidden = set(self.state_ids) | self.store_names | set(self.computed) | {'t'}
        alone = run.plan.spaces[self.space].count == 1
        own.known = {name: value for name, value in own.values.items() if alone and name not in hidden}
        own.analysis, own.face_proofs = {}, {}
        return own

    @property
    def bounds(self):
        return self.lower, self.upper, self.ledger_slack, self.atol


@dataclass
class Piece:
    """One segment of a component: from `start` to `end`, the function of the time that gives the
    state of the system, and the states at its two ends, the last with the bounds that it reaches
    settled."""

    start: float
    end: float
    solution: object
    first: np.ndarray
    last: np.ndarray
    waits: bool = False  # a watched crossing is at its end: the timeline goes there first
    store: dict | None = None  # with the whole record of a run: the store through the segment
    made: int = 0  # the moment of the timeline in or after which the segment was made


class Component:
    """See the module. It has the attributes that the timeline reads of the solution of a block."""

    def __init__(self, run, block, instance):
        self.run, self.block, self.instance = run, block, instance
        self.J = np.array([instance])
        self.slices = {name: slice(k, k + 1) for k, name in enumerate(block.names)}
        self.size = len(block.names)
        self.net = run.plan.nets[block.space]
        self.rows = np.array([self.net.index[name] for name in block.names], dtype=int)
        self.system = None  # made at the first start, when the tolerances of the instance are known
        self.t0, self.y0 = 0.0, None
        self.current, self.done = None, []
        self.watching = {}  # (rule, instance) -> (quantity, rising, value, version of the rule)
        self.fresh, self.counted, self.evaluations = True, 0, 0
        self.numeric_only, self.mode = False, 'component'

    def make(self):
        from ..runtime import Trajectory

        run, j = self.run, self.instance
        s = self.system = self.net.of(run, j)
        state = np.array([float(run.v[name][j]) if name in run.v else np.nan for name in s.state_ids])
        self.trajectory = Trajectory(
            s.horizon, [], [], s.settings, s.state_ids, s.values, s.computed, s.units, s.bounds
        )
        self.state = State(0.0, state, {})
        self.field = Field(s, self.state, self.trajectory)

    # ---- what the timeline asks -------------------------------------------------------------------

    def start(self, t, y):
        """The component starts again at t from the state y of its block: a step wrote one of its
        quantities, or something that it reads."""
        if self.system is None:
            self.make()
        self.t0, self.y0 = t, np.array(y[: self.size], dtype=float)
        if self.current is not None and self.current.end > t >= self.current.start:
            # The segment was made further than this moment: its record ends here.
            self.current.end = t
            if t == self.current.start and self.run.pieces and self.run.pieces[-1] is self.current:
                self.run.pieces.pop()
        # New lists: a copy of the component, which the record of the run keeps, has the old ones.
        self.current, self.done = None, []
        self.fresh = True
        self.count()
        self.state.time = t
        # A new array: the solution of the segment that ends here keeps the array that it started
        # from (the first dense step of a solver is from that array), and the record reads it.
        state = self.state.y.copy()
        state[self.rows] = self.y0
        self.state.y = state

    def at(self, t):
        """The state of the block at a time from its last start on."""
        if self.y0 is None or t <= self.t0:
            return self.y0
        horizon = self.run.horizon
        while True:
            piece = self.current
            if piece is None:
                piece = self.segment(t)
            if t < piece.start:
                return self.before(t)
            if t == piece.start:
                return piece.first[self.rows]
            if piece.waits and abs(t - piece.end) <= self.run.tolerance:
                # A moment of the timeline takes the times within its tolerance: it reads the end.
                return piece.last[self.rows]
            if t < piece.end:
                return self.trajectory._project(piece.solution(t))[self.rows]
            if t == piece.end or piece.end >= horizon or self.frozen:
                return piece.last[self.rows]
            run = self.run
            if piece.waits and not (run.moment > piece.made and run.now + run.tolerance >= piece.end):
                # The timeline has not had its moment at the end of the segment yet: the component
                # waits there. An end within the tolerance of the moment before it is no part of
                # that moment: it came after it.
                return piece.last[self.rows]
            self.proceed()

    def before(self, t):
        """The state at a time before the present segment, from the segments that are done."""
        ends = [piece.end for piece in self.done]
        k = bisect_left(ends, t)
        if k >= len(self.done) or t < self.done[k].start:
            raise SimulationError(f'{self.block.names[0]}: no stored segment has the time {t:g} h')
        piece = self.done[k]
        if t == piece.end:
            return piece.last[self.rows]
        return self.trajectory._project(piece.solution(t))[self.rows]

    @property
    def frozen(self):
        """A copy that the record of the run keeps makes no new segment."""
        return self.run.single[self.block.index][self.instance] is not self

    def watch(self, rule, j, place, threshold, rising, after):
        """A rule watches a crossing of a quantity of the block. The watched crossings are part of a
        segment, so a segment that began before this moment ends here."""
        run = self.run
        self.watching[(rule, j)] = (
            self.block.names[place],
            bool(rising),
            float(threshold),
            int(run.rules[rule].version[j]),
        )
        if self.current is not None:
            run.cut(self.block, self.instance, after)

    def guards(self, env):
        """The crossings that the segment watches, as the continuous engine reads them: in the
        order of the rules."""
        rules = self.run.rules
        found = []
        for key in sorted(self.watching):
            var, rising, value, version = self.watching[key]
            if rules[key[0]].version[key[1]] != version:
                del self.watching[key]  # the rule was read again, or it triggered
                continue
            found.append((key, {'var': var, 'op': '>=' if rising else '<=', 'value': value}))
        return found

    # ---- the segments -----------------------------------------------------------------------------

    def count(self):
        if self.system is not None:
            self.run.counts['evaluations'] += self.state.evaluations - self.counted
            self.counted = self.state.evaluations

    def static(self):
        """What the component reads that does not move in a segment, from the run: its store."""
        run, s, j, state = self.run, self.system, self.instance, self.state
        state.store = {name: run.static(name, s.space, j, state.time) for name in sorted(s.store_names)}

    def pinned(self):
        """The quantities of the space that only steps change, as they are now. A step can write one
        that the component does not read: the component does not start again then, and the state
        of its next segment still has the value that the step wrote."""
        run, s, j, state = self.run, self.system, self.instance, self.state
        for i in s.discrete:
            state.y[i] = float(run.v[s.state_ids[i]][j])

    def segment(self, to):
        """Make the segment from the present time and state of the component as far as `to`."""
        run, s, state, field = self.run, self.system, self.state, self.field
        diagnostics = self.trajectory.diagnostics
        if self.fresh:
            self.static()
            self.fresh = False
        self.pinned()
        # The bounds that hold the state after the steps of a moment are found with the faces of
        # the segment that ended there; then those faces are cleared.
        refresh_bounds(s, state, field)
        start = state.time
        end = min(run.horizon, to)
        state.right_faces.clear()
        state.zero_faces.clear()
        found = advance(s, state, field, self, self.trajectory, end)
        if found.rounded:
            # A stock reaches its face within the roundoff of the time: it is settled on the face,
            # with its balancing leg, and that is a moment for the rules and the checks that read
            # the component, as the end of a segment is. The segment itself comes after that moment.
            correct_boundary_roundoff(s, diagnostics, state.time, state.y, found.rounded)
            check_bounds(s, state.y)
            self.count()
            settled = state.y.copy()
            if start == self.t0:
                self.y0 = settled[self.rows]
            piece = self.current = Piece(start, start, None, settled, settled, True, None, run.moment)
            run.segment_end(start, self.block.index, self.instance)
            return piece
        first = state.y.copy()
        if start == self.t0:
            self.y0 = first[self.rows]
        solution = found.solution
        numerical = found.numerical
        last = np.array(solution(found.end) if numerical is None else numerical.y[:, -1], dtype=float)
        if s.flows:
            # The flows that deliver material in the segment: their rates at its middle.
            middle = (start + found.end) / 2
            field.rates(middle, solution(middle))
            delivered = [key for key, rate in zip(s.flow_ids, field.delivered) if rate > 0]
            run.moved.update(run.rule_free_name(key, s.space, self.instance) for key in delivered)
            run.flowing.update(delivered)
        correct_boundary_roundoff(s, diagnostics, found.end, last, found.targets)
        if numerical is not None:
            if found.end <= start:
                raise SimulationError('Integration made no progress at a boundary')
            run.counts['solver steps'] += len(numerical.t) - 1
            # The accepted points of the solver are checked too: a fine output cannot hide a state
            # outside its bounds.
            for k in range(len(numerical.t) - 1):
                check_bounds(s, numerical.y[:, k])
        check_bounds(s, last)
        self.count()
        piece = self.current = Piece(start, found.end, solution, first, last, made=run.moment)
        if numerical is not None:
            # The checks of the state that read the component hold at each accepted point too: the
            # ones of the component itself on the accepted state, the others through the timeline.
            own = bool(s.resolved.state_checks or s.resolved.partitions)
            for k in range(1, len(numerical.t) - 1):
                at = float(numerical.t[k])
                if own:
                    check_conditions(s, field.environment(at, numerical.y[:, k]), at)
                run.check_readers(self.block.index, self.instance, at)
        if run.keep:
            piece.store = run.store_now()
            run.pieces.append(piece)
        # The crossings at the end of the segment: the kernel or the solver names them, and a
        # crossing whose quantity is on its value at the end is one too.
        due = set(found.due)
        for key, cond in state.guards.items():
            reached = last[s.index[cond['var']]]
            if (reached >= cond['value']) if cond['op'] == '>=' else (reached <= cond['value']):
                due.add(key)
        for rule, j in sorted(due):
            run.crossing_due(found.end, rule, j)
        if numerical is not None and found.end < run.horizon:
            # A crossing whose own time is within the tolerance of a moment after the end of the
            # segment is due with the rules of that end (D-65, "One moment"). A closed form names
            # such a crossing itself; a solver finds only the crossings inside its segment, so the
            # solution is read that far past its end.
            ahead = solution(found.end + run.tolerance)
            for key, cond in state.guards.items():
                if key in due:
                    continue
                i = s.index[cond['var']]
                gap, move = cond['value'] - last[i], ahead[i] - last[i]
                if (0 < gap <= move) if cond['op'] == '>=' else (move <= gap < 0):
                    run.crossing_due(found.end + run.tolerance * gap / move, *key)
        if found.end < run.horizon:
            # The end of a segment is a moment for the rules and the checks that read the component.
            run.segment_end(found.end, self.block.index, self.instance)
            piece.waits = True
        return piece

    def middle(self):
        """A time inside the segment that has just ended, or None when there is none."""
        piece = self.current
        if piece is None or piece.end <= piece.start:
            return None
        return (piece.start + piece.end) / 2

    def proceed(self):
        """The next segment starts where the present one ended: no moment of the timeline came
        between that wrote something that the component reads."""
        piece = self.current
        if self.run.record:
            self.done.append(piece)
        self.state.time, self.state.y = piece.end, piece.last.copy()
        self.current = None
