"""One run of the timeline engine: the moments of a plan, from the start to the horizon.

A space (`plan.Space`) is in one of two tiers. In the **general tier** (`plan.general`), each
instance of the space is a component (`component.py`): the continuous engine (`engine/continuous/`)
runs its quantities together, with its field, its bounds and faces, its closed forms and its solver.
The things outside the tables are in this tier unless a plan says otherwise (`Plan.of`). In the
**fast tier**, the state of a space is one array over its instances for each name:

- a **value** changes only when a step writes it;
- a **line** is a quantity whose rate reads nothing that moves. Between two restarts it is
  `y0 + rate * (t - t0)`, exactly; a restart of one instance costs nothing for the others;
- a **numeric block** is integrated by a solver through its adapter (`engine/solvers.py`). An
  instance that reads no other instance is a problem of its own, with its own steps; instances that
  read one another are one problem. A block is integrated only as far as a reader asks. A step of
  its solver can be longer than the step cap of the run: the engine reads such a step inside, at
  each half and at each whole cap (`Solution.advance`);
- a **linear block** (`plan.Block.linear`) of one instance has a closed form between two moments:
  with `y' = A y + c`, the state at t is the first rows of `expm(M (t - t0)) [y0, 1]`, where M has A
  and c in its first rows and a last row of zeros. It is used when no state of it can leave its
  bounds between two moments without the timeline knowing (`Run.decide`); else the solver
  integrates the segment.

One timeline holds the times at which a rule can become due: the time of a clock, the end of a delay,
and the time at which a crossing reaches its value. A moment takes the times within 1e-8 h of the
earliest. In it, the due rules go one at a time, in the order of the file; after each step, only the
parts that read what the step wrote are brought up to date: the rules are read again, the lines and
the blocks start again from the moment (D-65). `reading='every'` reads every rule at every moment
and after every step, with the crossing due inside its tolerance band at any moment, as the engine
before D-65 did: the checking mode runs both (`check`).
"""

from __future__ import annotations

import copy
import heapq
import math
from bisect import bisect_left
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np
from scipy.linalg import expm
from scipy.optimize import brentq

from ...core import arrays, expr
from ...core.derivatives import derivative
from ...core.errors import ExpressionError
from ...core.evaluation import program as compile_program
from ...distributions import central as central_value
from ...distributions import problems, quantile
from ...expressions import names_in
from ...model.ir import COUNT, ENTERED, EVENT_TIME_TOLERANCE_H, TIME, ModelError
from .. import solvers
from ..continuous.integrate import STALLED_STEPS, Limit, apart
from ..continuous.system import solver_step, step_cap
from ..errors import SimulationError
from ..sampling import draws
from .component import Component
from .plan import ALL, SAME, SCALARS, Outside
from .trees import Pairwise

ROOT_TOLERANCE = 1e-13
# How far the chances of an event's outcomes may miss 1 when it fires.
CHANCE_TOLERANCE = 1e-9
TRIGGER, FIRE = 1, 2
RULE, BOUND, ROOT, LIMIT, FLOOR, END = 0, 1, 2, 3, 4, 5
ONE = object()  # the one instance of a space of one
NEGATIVE = object()  # in the memo of an environment: a quantity with a flow that asks less than zero
POSITIVE = object()  # in the memo of an environment: the flows that deliver material at its state
SEEN = ('value', 'line', 'numeric', 'formula')  # the kinds of the names that a resolver reads


def _basis_ref(basis):
    """The identity of a basis for a trace entry: its name, kind and the records it cites."""
    if isinstance(basis, (list, tuple)):
        return [_basis_ref(item) for item in basis]
    if not isinstance(basis, dict):
        return basis
    out = {key: basis[key] for key in ('name', 'kind', 'assumption') if key in basis}
    claims = sorted({link['claim'] for link in basis.get('links', []) if 'claim' in link})
    return out | ({'claims': claims} if claims else {})


def shares(chances):
    """The chance with which a sample takes each outcome of a firing, from the chances as the
    model gives them (they add up to 1 within the tolerance of the chances). A sample takes the
    first outcome whose running total is above its uniform number, and the last outcome that has
    a chance where no total is (`Run.chosen`): so each outcome has its chance, the running total
    stops at 1, and the last one takes what is missing to 1."""
    found, total, last = [0.0] * len(chances), 0.0, None
    for place, chance in enumerate(chances):
        if chance <= 0:
            continue
        found[place] = min(1.0, total + chance) - min(1.0, total)
        total, last = total + chance, place
    if last is not None and total < 1.0:
        found[last] += 1.0 - total
    return found


def _one(value):
    """The value of one instance from a result of `arrays.values`."""
    if isinstance(value, np.ndarray):
        return value.item(0)
    return value


def _spread(value, count):
    """A result of `arrays.values` as one value for each instance."""
    if isinstance(value, np.ndarray) and value.ndim == 1:
        return value
    return np.full(count, value)


def _span(a, c, start, bound):
    """The time that the solution of `y' = a y + c` from `start` takes to reach `bound`, or None when
    it does not reach it. Such a solution moves to one side only."""
    if not math.isfinite(bound):
        return None
    if a == 0:
        return (bound - start) / c if c != 0 and (bound - start) / c > 0 else None
    rest = -c / a
    ratio = (bound - rest) / (start - rest) if start != rest else -1.0
    return math.log(ratio) / a if ratio > 0 and math.log(ratio) / a > 0 else None


def _pairwise(values):
    return Pairwise(values).total


@dataclass
class Trial:
    """The state of a numeric block that a solver tries: {name: values}. `whole`: the values are of
    every instance of the space of each name."""

    values: dict
    whole: bool


class Env:
    """The values that the parts of one space read at one time, for the instances `J` (None: all)."""

    __slots__ = ('J', 'count', 'memo', 'run', 'space', 't', 'trial')

    def __init__(self, run, space, J, t, trial=None):
        self.run, self.space, self.J, self.t, self.trial = run, space, J, t, trial
        self.memo = {}
        self.count = run.plan.spaces[space].count if J is None else len(J)

    def __contains__(self, name):
        return name == 't' or name in self.run.plan.kind

    def get(self, name, default=None):
        if name in self:
            return self[name]
        return default

    def __getitem__(self, name):
        if name == 't':
            return self.t
        found = self.memo.get(name, self)
        if found is self:
            found = self.memo[name] = self.run.read(name, self.space, self.J, self.t, self.trial)
        return found


class Seen(Mapping):
    """The values of the one instance of an environment, as a mapping that a caller only reads: what
    the resolver of a decision gets."""

    def __init__(self, env):
        self.env = env

    def __getitem__(self, name):
        if name not in self.env:
            raise KeyError(name)
        return _one(self.env[name])

    def __contains__(self, name):
        return name in self.env

    def __iter__(self):
        return iter(('t', *self.env.run.plan.kind))

    def __len__(self):
        return 1 + len(self.env.run.plan.kind)


class View(Seen):
    """What the resolver of a decision reads: the inputs, the quantities, the states with the times
    at which they were taken, the counts and the times of the events, and the formulas and the
    statuses of the model by their names, at the time of the decision."""

    def names(self):
        plan = self.env.run.plan
        return [name for name, kind in plan.kind.items() if kind in SEEN and name not in plan.outputs]

    def __getitem__(self, name):
        env = self.env
        plan = env.run.plan
        if name != 't' and (plan.kind.get(name) not in SEEN or name in plan.outputs):
            raise KeyError(name)
        if name != 't' and plan.kind[name] == 'formula':
            # A formula or a status has no value of its own in the run: it is its expression.
            return _one(env.run.value(plan.node(expr.ref(name), env.space, f'the formula {name}'), env))
        return _one(env[name])

    def __contains__(self, name):
        plan = self.env.run.plan
        return name == 't' or (plan.kind.get(name) in SEEN and name not in plan.outputs)

    def __iter__(self):
        return iter(('t', *self.names()))

    def __len__(self):
        return 1 + len(self.names())


class Unknown(Exception):
    """An expression read an output that the model does not estimate: it has no value."""


class Pause(Exception):
    """A decision of a played run waits for a pick: the run stops before the step of that decision."""


class Past(Env):
    """The values that the parts of one space read at a time of the past, from the record of the run."""

    __slots__ = ()

    def __getitem__(self, name):
        if name == 't':
            return self.t
        found = self.memo.get(name, self)
        if found is self:
            found = self.memo[name] = self.run.read_past(name, self.space, self.J, self.t)
        return found


class RuleState:
    def __init__(self, count):
        self.armed = np.ones(count, dtype=bool)
        self.triggered = np.zeros(count, dtype=np.int64)
        self.pending = np.full(count, np.nan)
        self.version = np.zeros(count, dtype=np.int64)
        self.ready = np.zeros(count, dtype=np.int8)
        self.reached = np.zeros(count, dtype=np.int64)  # the moment at which its crossing came
        self.window = np.empty(count, dtype=object)  # the values of its window when it triggered


class Solution:
    """A numeric block from its last restart: the steps of a solver, made when a reader asks."""

    def __init__(self, run, block, instance):
        plan = run.plan
        self.run, self.block, self.instance = run, block, instance
        self.J = None if block.whole else np.array([instance])
        self.slices, at = {}, 0
        for name in block.names:
            count = plan.spaces[plan.space_of(name)].count if block.whole else 1
            self.slices[name] = slice(at, at + count)
            at += count
        self.size = at
        self.t0, self.y0, self.steps, self.ends, self.runner, self.frontier = 0.0, None, [], [], None, 0.0
        # (time, state, a flow below zero or None, the flows above zero) of each state that the
        # solver tried since its last step.
        self.tried = []
        # (time, state, what the field found there or None) of each state of the solution that is a
        # state of the run when a reader comes to it (`settle`), from `settled` on.
        self.unread, self.settled = deque(), 0.0
        # For each step, the whole caps inside it: the times at which the engine reads it.
        self.cuts = []
        self.mode, self.matrix, self.given, self.last = None, None, None, None

    def start(self, t, y):
        self.t0, self.y0, self.frontier = t, y, t
        self.steps, self.ends, self.cuts, self.runner = [], [], [], None
        self.unread, self.settled = deque(), t
        self.evaluations, self.tried = 0, []
        self.numeric_only, self.given_terms = False, None
        # How the segment is solved is decided when a reader first asks (`Run.decide`).
        self.mode, self.matrix, self.given, self.last = None, None, None, None

    def tolerances(self):
        run = self.run
        return np.concatenate(
            [run.atol[name] if self.J is None else run.atol[name][self.J] for name in self.block.names]
        )

    def advance(self):
        """One more step of the solver that the block uses. The step cap of the run is the interval
        at which the engine reads the block, and no limit of the solver's step (docs/engine.md,
        "Steps"): a step can be longer, and is then read inside, on its own solution.

        - At each half of a cap from the start of the segment, the field is compared with the rate
          of the solution (`integrate.apart`). When the two are too far apart at one of these
          times, the step is not used: the solver takes it again, with a shorter limit
          (`integrate.Limit`).
        - At each whole cap, the state of the solution is a state of the run, as the end of a step
          is: it is within its bounds, and no flow of it asks a rate below zero. A step can end
          far after the time that a reader asks for, and an event before its end starts the block
          again: a state is checked when a reader comes to it (`settle`)."""
        run = self.run
        cap, half = run.max_step, run.max_step / 2
        if self.runner is None:
            # The rates at the start of the segment are those of a state of the run: checked.
            run.field(self, self.t0, self.y0, trial=False)
            # The longest step: what the timescales of the run allow, and then what the steps
            # before allow.
            self.limit = Limit(cap, run.solver_step)
            self.halves = 0  # the halves of a cap before the next step, from the start
            self.runner = run.adapter.start(
                lambda t, y: run.field(self, t, y),
                self.t0,
                self.y0,
                run.horizon,
                rtol=run.cfg.rtol,
                atol=self.tolerances(),
                max_step=self.limit.allowed,
            )
        limit, rtol, atol = self.limit, run.cfg.rtol, None
        while True:
            self.runner.limit(limit.allowed)
            try:
                step = self.runner.step()
            except solvers.SolverFailure as problem:
                raise SimulationError(f'{self.block.names[0]}: {problem}') from problem
            run.counts['solver steps'] += 1
            length = step.t - step.t_old
            if not length > cap:
                # A step of the cap at most is read at its end, as each step was before.
                while self.t0 + (self.halves + 1) * half < step.t:
                    self.halves += 1
                limit.short()
                inside = ()
                break
            atol = self.tolerances() if atol is None else atol
            count, largest, far, inside = self.halves, 0.0, 0.0, []
            while True:
                at = self.t0 + (count + 1) * half
                if not at < step.t:
                    break
                count += 1
                if at <= step.t_old:
                    continue
                state = step.dense(at)
                far = apart(length, run.field(self, at, state), step.rate(at), state, rtol, atol)
                if not far <= 1.0:
                    break
                largest = max(largest, far)
                if count % 2 == 0:
                    inside.append((at, state, self.tried[-1][2:]))
            if far <= 1.0:
                self.halves = count
                limit.used(length, largest)
                break
            # The solution of the step is too far from the field inside the step.
            limit.unused(length, far)
            self.runner.retake(limit.allowed)
            self.tried = []
            run.counts['solver steps not used'] += 1
        if limit.accepted(step.t_old, step.t):
            # The steps of the solver no longer move the block (`integrate.STALLED_STEPS`).
            message = (
                f'The run stops at t = {step.t:g} h: the steps of the solver for {self.block.names[0]} '
                f'stayed shorter than {EVENT_TIME_TOLERANCE_H:g} h for {STALLED_STEPS} steps in a '
                f'row, from t = {limit.brief_from:g} h. A rate of the block switches back and forth '
                'at a condition: each branch takes the state back across the switch. A condition '
                'that turns the outflows of a stock off when it is empty does this when they ask for '
                'more than comes in: remove the condition, as the engine gives the outflows of an '
                'empty stock what comes in.'
            )
            item = {
                'severity': 'error',
                'code': 'chattering',
                'from_h': limit.brief_from,
                'at_h': float(step.t),
                'quantities': list(self.block.names),
            }
            raise SimulationError(message, [item])
        # A solver reads the rates at the state that it accepts, so what the field found there is
        # known; a solver that did not is asked for the rates there (`settle`).
        tried, self.tried = self.tried, []
        found = next(
            (
                (negative, positive)
                for at, state, negative, positive in reversed(tried)
                if at == step.t and np.array_equal(state, step.y)
            ),
            None,
        )
        self.unread += [*inside, (step.t, step.y, found)]
        self.steps.append(step)
        self.ends.append(step.t)
        self.cuts.append(tuple(at for at, _, _ in inside))
        self.frontier = step.t

    def settle(self, t):
        """Each state at which the engine reads the solution (the end of a step; each whole cap
        inside a step that is longer than the cap) is a state of the run when a reader comes to it:
        it is within its bounds, and no flow of it asks a rate below zero. The states up to the
        first of them at or after `t` are checked here. The states after it are those of the block
        only when no event starts the block again before them."""
        run, unread = self.run, self.unread
        while unread and self.settled < t:
            at, state, found = unread.popleft()
            run.within_bounds(self, state, at)
            if found is None:
                run.field(self, at, state, trial=False)
            else:
                negative, positive = found
                if negative is not None:
                    raise run.negative_flow(negative)
                run.flowing |= positive
            self.settled = at

    def at(self, t):
        """The state of the block at a time from its restart on."""
        if t <= self.t0:
            return self.y0
        if self.mode is None:
            self.run.decide(self)
        if self.mode == 'closed':
            if self.last is None or self.last[0] != t:
                extended = np.append(self.y0, 1.0)
                self.last = (t, (expm(self.matrix * (t - self.t0)) @ extended)[:-1])
            return self.last[1]
        while self.frontier < t:
            self.advance()
        if self.settled < t:
            self.settle(t)
        step = self.steps[bisect_left(self.ends, t)]
        return step.y if t == step.t else step.dense(t)

    def first_root(self, place, threshold, rising, after):
        """The first time after `after` at which the value at `place` reaches `threshold` from the
        side that `rising` names, or None when it does not before the horizon."""
        horizon = self.run.horizon
        if after >= horizon:
            return None
        if self.mode is None:
            self.run.decide(self)
        if self.mode == 'closed':
            name = next(name for name, cut in self.slices.items() if cut.start == place)
            if self.run.plan.quantities[name].monotone:
                # A quantity that never falls reaches its value once: the root is between two times
                # at which it is on the two sides.
                before = float(self.at(after)[place]) - threshold
                end = float(self.at(horizon)[place]) - threshold
                if not ((before < 0 <= end) if rising else (before > 0 >= end)):
                    return None
                return brentq(
                    lambda at: float(self.at(at)[place]) - threshold,
                    after,
                    horizon,
                    xtol=ROOT_TOLERANCE,
                    rtol=ROOT_TOLERANCE,
                )
            # No proof that it crosses once: the solver's steps find the first crossing.
            self.mode, self.last = 'numeric', None
        self.at(min(horizon, np.nextafter(after, np.inf)))
        k = bisect_left(self.ends, after)
        if k < len(self.ends) and self.ends[k] == after:
            k += 1
        while True:
            if k >= len(self.steps):
                if self.frontier >= horizon:
                    return None
                self.advance()
            step = self.steps[k]
            start = max(step.t_old, after)
            before = float(self.at(start)[place]) - threshold if start > step.t_old else None
            if before is None:
                before = float((self.y0 if k == 0 else self.steps[k - 1].y)[place]) - threshold
            # The value is read at the end of the step, and inside a step that is longer than the
            # cap at each whole cap from the start of the segment, as the ends of the steps of a
            # solver that the cap limits read it: the first of these parts in which it crosses
            # has the root. The states of the block up to there are states of the run.
            for cut in (*self.cuts[k], step.t):
                if cut <= start:
                    continue
                end = float((step.y if cut == step.t else step.dense(cut))[place]) - threshold
                if (before < 0 <= end) if rising else (before > 0 >= end):
                    root = cut
                    if end != 0:
                        root = brentq(
                            lambda at, step=step: float(step.dense(at)[place]) - threshold,
                            start,
                            cut,
                            xtol=ROOT_TOLERANCE,
                            rtol=ROOT_TOLERANCE,
                        )
                    self.settle(root)
                    return root
                start, before = cut, end
            self.settle(step.t)
            k += 1


@dataclass
class Result:
    """What a run gives: the events in their order, as (time, rule, outcome), where the outcome is
    None for a rule that starts to wait; the value of each output at the horizon; and the counts of
    the work."""

    horizon: float
    trace: list
    outputs: dict
    counts: dict
    reading: str
    run: object = field(repr=False, default=None)
    # The outputs that the model does not estimate: they have no value, which is not the value 0.
    unestimated: tuple = ()
    # A played run: the first decision that waits for a pick, whether the run stopped there, and the
    # time to which the run went (the horizon, or the time of that decision).
    decision: dict | None = None
    paused: bool = False
    end_time: float | None = None
    # A run with given outcomes (`Run.taken`): each firing that went by chance, in its order.
    firings: tuple = ()

    def __post_init__(self):
        if self.end_time is None:
            self.end_time = self.horizon

    @property
    def entries(self):
        """Each step of the trace as a report reads it: its rule, thing, event, outcome
        and text, what it set and moved, its place in the file and its basis, and who picked its
        outcome. They are made when a reader asks: a run of many instances does not pay for them."""
        return [self.run.entry_at(k) for k in range(len(self.run.log))]

    def final(self, name):
        """The value of a name at the end of the run (the horizon, or the time at which a played run
        stopped), for each instance of its space."""
        return self.run.column(name, self.end_time)

    def trajectory(self):
        """The run as a trajectory (`engine/runtime.Trajectory`), which the reports, the studies and
        the tools read: for a run that kept its whole record (`keep`), of a model with no table."""
        from ..continuous.kernels import Affine, Segment
        from ..continuous.system import System
        from ..runtime import Trajectory

        run = self.run
        if not run.keep:
            raise ValueError('the run did not keep its whole record: Run(…, keep=True)')
        plan = run.plan
        s = System(run.resolved, plan.library, run.cfg)
        s.values = {**s.values, **{name: run.v[name].item(0) for name in plan.parameter_scale}}
        diagnostics, settings = [], s.settings
        for component in run.components:
            if component.system is not None:
                diagnostics, settings = component.trajectory.diagnostics, component.system.settings
        segments = [Segment(piece.start, piece.end, piece.solution, piece.store) for piece in run.pieces]
        if not run.components:
            # Nothing moves between two moments: each quantity keeps the value of the last step.
            still = np.zeros(len(s.state_ids))
            for (start, state, store), (end, _, _) in zip(run.snapshots, run.snapshots[1:]):
                if end > start:
                    segments.append(Segment(start, end, Affine(start, state.copy(), still), dict(store)))
            if run.snapshots and self.end_time > run.snapshots[-1][0]:
                start, state, store = run.snapshots[-1]
                segments.append(
                    Segment(start, self.end_time, Affine(start, state.copy(), still), dict(store))
                )
        made = Trajectory(
            s.horizon,
            self.entries,
            diagnostics,
            settings,
            s.state_ids,
            s.values,
            s.computed,
            s.units,
            s.bounds,
            _segments=segments,
            _snapshots=list(run.snapshots),
            _steps=list(run.after_steps),
            layers=list(range(len(self.entries))),
            moved=set(run.moved),
            evaluations=int(self.counts['evaluations']),
            decision=self.decision,
            paused=self.paused,
            end_time=self.end_time,
        )
        if run.snapshots:
            # The order of the formulas is a field of a trajectory: a trajectory has it whether a
            # reader asked or not.
            made._environment(*run.snapshots[0])
        return made


class Run:
    def __init__(
        self,
        plan,
        values=None,
        *,
        settings=None,
        reading='scoped',
        adapter=None,
        luck=None,
        outcomes=None,
        record=None,
        play=None,
        keep=False,
        inputs=None,
        resolved=None,
        pause_at_decision=False,
        decision_events=None,
        settled_decisions=False,
        decision_resolver=None,
    ):
        from ..runtime import NumericalSettings

        if reading not in ('scoped', 'every'):
            raise ValueError(f'reading: {reading!r} is not scoped or every')
        self.plan, self.reading = plan, reading
        # The resolved run of this run, when it is not the one that the plan was made of.
        self.resolved = resolved if resolved is not None else plan.resolved
        # The luck of a sample of a study, {seed, sample}: each firing with outcomes and each value
        # that a rule draws takes the next number of the stream of its event in that sample. With no
        # luck, the central run: the likeliest outcome and the central value.
        self.luck, self.streams = dict(luck) if luck else None, {}
        # A run with given outcomes (docs/engine.md, "The outcomes of a run, given"): the place of
        # the outcome of each firing that goes by chance, in the order of the run. A firing after
        # the last given place takes its likeliest outcome. The run keeps each such firing
        # (`taken`): a caller runs every path of the outcomes in turn, each with its weight.
        self.outcomes = None if outcomes is None else tuple(int(place) for place in outcomes)
        self.firings = []
        # The record: what each value, line and block was before each step, so that a value of the
        # past can be read. It is kept when the plan has a value of the past, or when a caller asks.
        self.record = plan.records if record is None else bool(record)
        self.undo, self.line_log, self.block_log = {}, {}, {}
        self.restart_numeric = set()
        self.flag_changes = []
        # The components: the blocks of the spaces whose flows need the allocation in full
        # (`component.py`). `moved`: the flows of them that delivered material in some segment.
        self.components, self.moved = [], set()
        # The flows that delivered material in the run, by the names of the plan (one name for the
        # rows of a class): what the evidence trail of a report reads (`reports.evidence`). A flow is
        # looked at only until it is here, so the cost ends when each flow has moved once.
        self.flowing = set()
        self.now = 0.0  # the time of the moment that the timeline is at
        # The states of the blocks at times of the past (`past_states`), and whether the run ended.
        self.past_kept, self.ended = {}, False
        # A played run (docs/engine.md, "Play"): the actors that a person or an agent controls, the
        # picks so far, and the first decision that waits for a pick. `play` is {control, picks};
        # without it, the model takes every decision.
        play = play or {}
        self.control = dict(play.get('control') or {})
        self.picks = [dict(item) for item in (play.get('picks') or ())]
        if decision_resolver is not None and (not pause_at_decision or not callable(decision_resolver)):
            raise ValueError('decision_resolver must be callable and requires pause_at_decision=True')
        self.pause_at_decision, self.decision_resolver = bool(pause_at_decision), decision_resolver
        self.decision_events = None if decision_events is None else frozenset(decision_events)
        self.settled = bool(settled_decisions)
        self.picked, self.picking, self.decision = 0, None, None
        self.controllers, self.continuations = {}, []
        self.block_checks = {}  # (block, instance) -> the checks that read the component
        self.block_programs = {}  # the program of each linear block
        self.block_made, self.wrote = (None, None), 0  # its last values, and the count of the writes
        self.log, self.written_entries = [], {}  # a short record of each step, and its entry
        # The whole record of a run (`Result.trajectory`): the state and the store at the start of
        # each moment and after each step, and the segments.
        self.keep = bool(keep)
        if self.keep and len(plan.spaces) != 1:
            raise Outside('the whole record of a run of a model with a table')
        if self.keep and plan.moving_quantities and SCALARS not in plan.general:
            # The record has the segments of a component; the fast tier keeps no such segments.
            raise Outside('the whole record of a run with the things outside the tables in the fast tier')
        self.snapshots, self.after_steps, self.pieces = [], [], []
        self.cfg = NumericalSettings.parse(settings)
        self.adapter = adapter or solvers.DEFAULT
        self.registry = plan.units
        self.horizon, self.tolerance = plan.horizon, EVENT_TIME_TOLERANCE_H
        self.v = {name: column.copy() for name, column in plan.values.items()}
        # A plan serves each run of its structure: `inputs` has the value of each input of this
        # run, in execution units.
        for name, value in (inputs or {}).items():
            if name in plan.parameter_scale:
                self.v[name][:] = float(value)
        # What the caller gave, in the unit of each input: nothing has proved the run for it.
        self.given = {}
        for name, value in (values or {}).items():
            if name not in plan.parameter_scale:
                raise KeyError(f'{name} is no input of the model')
            if name in plan.bound_reads:
                # The plan holds the bound that its own values give.
                raise ValueError(
                    f'A bound of a quantity reads {name}: a run with another value of it takes a '
                    'plan that is made with that value (Plan.of(core, run, values))'
                )
            numbers = np.asarray(value, dtype=float)
            self.v[name][:] = numbers * plan.parameter_scale[name]
            self.given[name] = (float(numbers.min()), float(numbers.max()))
        # The longest step of a numerical segment: the resolution and the timescales of the run.
        self.max_step, self.timescales = step_cap(
            plan.resolved.time,
            {name: float(self.v[name][0]) for name in plan.parameter_scale if len(self.v[name]) == 1},
            self.registry,
            self.cfg,
        )
        # The cap is the interval at which the engine reads a numeric block; the solver's own
        # limit is that of the timescales that the run declares.
        self.solver_step = solver_step(self.timescales)
        # The crossings of a value that is proved to move one way: each is watched inside its band.
        self.monotone_crossings = frozenset(
            plan.rule_index[name]
            for name in plan.resolved.proven_monotone_crossings or ()
            if name in plan.rule_index
        )
        self.y0, self.t0, self.rate, self.lversion = {}, {}, {}, {}
        self.atol, self.slack = {}, {}
        self.rules = [RuleState(plan.spaces[rule.space].count) for rule in plan.rules]
        self.order = []
        for rule in plan.rules:
            space = plan.spaces[rule.space]
            if space.family is None:
                entity = plan.s.rules[rule.name].entity
                rank = (*(plan.s.rules[rule.name].rank or ()), -1, -1, -1)[:3]
                position = rank[1] if rank[1] < 0 else plan.position.get(entity, rank[1])
                self.order.append((np.array([position]), np.array([rank[2]])))
            else:
                family = space.family
                self.order.append(
                    (np.array([plan.position[host] for host in family.hosts]), np.array(family.rows))
                )
        self.times, self.entries = [], 0
        self.ready, self.dirty = [], {}
        self.moment, self.steps = 0, 0
        self.trace = []
        self.terms = {}
        self.whole, self.single = {}, {}
        self.starting, self.starting_lines = True, False
        self.counts = dict.fromkeys(
            (
                'moments',
                'steps',
                'readings',
                'line restarts',
                'block restarts',
                'evaluations',
                'solver steps',
                'solver steps not used',
            ),
            0,
        )

    # ---- reading a name -------------------------------------------------------------------------

    def index(self, space, other, J):
        """The places, in the space `other` of a name, of the instances J of `space`."""
        plan = self.plan
        if plan.spaces[other].count == 1:
            return ONE
        if other == space:
            return J
        to = plan.spaces[space].links[other]
        return to if J is None else to[J]

    def read(self, name, space, J, t, trial):
        plan = self.plan
        kind = plan.kind[name]
        if kind == 'aggregate':
            return self.aggregate(name, t, trial)
        if kind == 'unknown':
            raise Unknown(name)
        at = self.index(space, plan.space_of(name), J)
        if kind == 'value' or self.starting:
            column = self.v[name]
        elif kind == 'line':
            if at is ONE:
                return float(self.y0[name][0] + self.rate[name][0] * (t - self.t0[name][0]))
            if at is None:
                return self.y0[name] + self.rate[name] * (t - self.t0[name])
            return self.y0[name][at] + self.rate[name][at] * (t - self.t0[name][at])
        elif trial is not None and name in trial.values:
            column = trial.values[name]
            if not trial.whole:
                return float(column[0]) if at is ONE else column
        else:
            column = self.numeric(name, at, t)
            return float(column[0]) if at is ONE else column
        if at is ONE:
            return column.item(0)
        return column if at is None else column[at]

    def read_past(self, name, space, J, t):
        """The value of a name at a time of the past (after the steps of that time), for the instances
        J of a space: the present value with each later change taken back, from the record."""
        plan = self.plan
        kind = plan.kind[name]
        if kind == 'aggregate':
            found = plan.aggregates[name]
            parts = []
            for term in found.terms:
                env = Past(self, term.space, None, t)
                parts.append(self.reduced(found.function, _spread(self.value(term.node, env), env.count)))
            return self.combined(found.function, parts)
        if kind == 'extra':
            raise SimulationError(f'{name}: a value of the past reads a value that a firing draws')
        at = self.index(space, plan.space_of(name), J)
        if kind == 'value':
            column = self.v[name].copy()
            for when, place, old in reversed(self.undo.get(name, ())):
                if when <= t:
                    break
                column[place] = old
        elif kind == 'line':
            y0, t0, rate = self.y0[name].copy(), self.t0[name].copy(), self.rate[name].copy()
            for when, places, old_y0, old_t0, old_rate in reversed(self.line_log.get(name, ())):
                if when <= t:
                    break
                y0[places], t0[places], rate[places] = old_y0, old_t0, old_rate
            column = y0 + rate * (t - t0)
        else:
            block = plan.blocks[plan.quantities[name].block]
            if block.whole:
                solution = self.segment((block.index, None), self.whole[block.index], t)
                column = solution.at(t)[solution.slices[name]]
            else:
                offset = self.single[block.index][0].slices[name].start
                column = self.past_states(block, t)[:, offset]
        if at is ONE:
            return column.item(0)
        return column if at is None else column[at]

    def past_states(self, block, t):
        """The state of each instance of a block of single instances at a time of the past: one row
        for each instance. The closed forms of the instances go together: one call gives the matrix
        exponential of each, as a call for it alone gives it. The states of a time before the
        present moment do not change, and neither do those of a run that ended, so the last ones are
        kept: a report reads several names of one block at each of its times."""
        key = (block.index, t)
        kept = self.past_kept.get(key)
        if kept is not None:
            return kept
        solutions = self.single[block.index]
        rows, closed = [None] * len(solutions), []
        for j, present in enumerate(solutions):
            solution = self.segment((block.index, j), present, t)
            if t > solution.t0:
                if solution.mode is None:
                    self.decide(solution)
                if solution.mode == 'closed':
                    closed.append((j, solution))
                    continue
            rows[j] = solution.at(t)
        if closed:
            powers = expm(np.stack([solution.matrix * (t - solution.t0) for _, solution in closed]))
            starts = np.stack([solution.y0 for _, solution in closed])
            starts = np.concatenate([starts, np.ones((len(closed), 1))], axis=1)
            for (j, _), state in zip(closed, np.einsum('nij,nj->ni', powers, starts)[:, :-1]):
                rows[j] = state
        states = np.stack(rows)
        if t < self.now or self.ended:
            self.past_kept[key] = states
            while len(self.past_kept) > 16:
                del self.past_kept[next(iter(self.past_kept))]
        return states

    def segment(self, key, solution, t):
        """The segment of a block that holds the time t: the present one, or one of the record."""
        for when, old in reversed(self.block_log.get(key, ())):
            if when <= t:
                break
            solution = old
        return solution

    def extras(self, rule, j, env, t, stage):
        """Give the environment of a firing the values that the rule reads at this stage: each value
        that it draws (the central value, or with luck the next number of the stream of its event),
        and each value of the past."""
        for item in rule.extras:
            if item.stage != stage:
                continue
            name = self.rule_name(rule, j)
            if item.kind == 'delayed':
                delay = float(_one(self.value(item.delay, env)))
                if not math.isfinite(delay) or delay < 0:
                    raise SimulationError(f'{name}: delayed() goes back a finite time from 0, not {delay} h')
                past = env if delay == 0 else Past(self, rule.space, np.array([j]), max(0.0, t - delay))
                env.memo[item.name] = _one(self.value(item.expr, past))
                continue
            args = {arg: float(_one(self.value(node, env))) for arg, node in item.args}
            wrong = problems(item.family, args)
            if wrong:
                raise SimulationError(f'{name}: {item.family}{tuple(args.values())}: {"; ".join(wrong)}')
            if not self.luck:
                env.memo[item.name] = central_value(item.family, args)
                continue
            key = (name, 'draw')
            if key not in self.streams:
                self.streams[key] = draws(self.luck['seed'], f'{name}/draw/{self.luck["sample"]}')
            env.memo[item.name] = float(quantile(item.family, args, self.streams[key]()))

    def numeric(self, name, at, t):
        """The values of a numeric quantity at the places `at` of its space."""
        plan = self.plan
        block = plan.blocks[plan.quantities[name].block]
        if block.whole:
            solution = self.whole[block.index]
            cut = solution.slices[name]
            column = solution.at(t)[cut]
            return column if at is None or at is ONE else column[at]
        solutions = self.single[block.index]
        places = range(len(solutions)) if at is None or at is ONE else at
        offset = solutions[0].slices[name].start
        return np.array([solutions[j].at(t)[offset] for j in places])

    def column(self, name, t):
        """The value of a name for each instance of its space, at a time."""
        plan = self.plan
        space = plan.space_of(name)
        count = plan.spaces[space].count
        if plan.kind[name] == 'formula':
            # A formula or a status has no value of its own in the run: it is its expression.
            env = Env(self, space, None, t)
            return _spread(self.value(plan.node(expr.ref(name), space, name), env), count)
        return _spread(self.read(name, space, None, t, None), count)

    def value(self, node, env):
        return arrays.values(node, env, self.registry, env.count)

    # ---- the lists ------------------------------------------------------------------------------

    def aggregate(self, name, t, trial):
        found = self.plan.aggregates[name]
        trial = trial if trial is not None and trial.whole else None
        parts = []
        for place, term in enumerate(found.terms):
            kept = None if found.moving else self.terms.get((name, place))
            if kept is None:
                env = Env(self, term.space, None, t, trial)
                kept = self.reduced(found.function, _spread(self.value(term.node, env), env.count))
                if not found.moving:
                    self.terms[(name, place)] = kept
            parts.append(kept)
        return self.combined(found.function, parts)

    @staticmethod
    def combined(function, parts):
        """The value of a list from what it keeps of each member (`reduced`)."""
        if function == 'sum':
            total = 0.0
            for kept in parts:
                total = total + kept.total
            return total
        if function == 'any':
            return any(count > 0 for count, _ in parts)
        if function == 'all':
            return all(count == size for count, size in ((np.count_nonzero(k[1]), len(k[1])) for k in parts))
        extreme = min if function == 'min' else max
        return extreme(float(extreme(kept)) for kept in parts)

    @staticmethod
    def reduced(function, values):
        """What a list keeps of the values of one member: a tree for a sum, the values for the others."""
        if function == 'sum':
            return Pairwise(values)
        if function in ('any', 'all'):
            values = values.astype(bool)
            return [np.count_nonzero(values), values]
        return np.array(values, dtype=float)

    def update_term(self, name, place, J, t):
        """Bring the member `place` of a list up to date for the instances J (None: all)."""
        found = self.plan.aggregates[name]
        term = found.terms[place]
        kept = self.terms.get((name, place))
        count = self.plan.spaces[term.space].count
        if kept is None or J is None or count == 1:
            self.terms.pop((name, place), None)
            self.aggregate(name, t, None)
            return
        J = np.fromiter(J, dtype=int, count=len(J))
        env = Env(self, term.space, J, t)
        values = _spread(self.value(term.node, env), len(J))
        if found.function == 'sum':
            kept.set_many(J, values)
        elif found.function in ('any', 'all'):
            kept[1][J] = values.astype(bool)
            kept[0] = np.count_nonzero(kept[1])
        else:
            kept[J] = values

    # ---- the rates ------------------------------------------------------------------------------

    def rate_of(self, name, env, trial=False):
        """The rate of a quantity. At a state of the run, a flow of it with a rate below zero is
        outside the fast tier. At a state that a solver tries (`trial`) it is no error: a trial can
        be past a bound, where the rate of a flow has no meaning. The environment keeps the name
        (`NEGATIVE`), for the case that the solver accepts that state (`Solution.advance`)."""
        total = 0.0
        plan = self.plan
        for (sign, node, is_flow), key in zip(plan.parts[name], plan.part_flows[name]):
            part = self.delivered(key, env) if key is not None else self.value(node, env)
            if is_flow and np.any(np.asarray(part) < 0):
                if not trial:
                    raise self.negative_flow(name)
                env.memo.setdefault(NEGATIVE, name)
            if key is not None and key not in self.flowing and np.any(np.asarray(part) > 0):
                # The flow delivers material at this state: at a state of the run it has moved; at
                # a state that a solver tries, it has when the solver accepts the state.
                if trial:
                    env.memo.setdefault(POSITIVE, set()).add(key)
                else:
                    self.flowing.add(key)
            total = total + sign * part
        return _spread(total, env.count).astype(float)

    def see_flows(self, names, env):
        """Mark the flows of some quantities that deliver material at the state of an environment
        (a state of the run): for a segment whose rates the engine does not read at its start."""
        plan = self.plan
        for name in names:
            for key in plan.part_flows[name]:
                if key is None or key in self.flowing:
                    continue
                if np.any(np.asarray(self.delivered(key, env)) > 0):
                    self.flowing.add(key)

    def flows_at_end(self):
        """Mark the flows that deliver material at the end of the run. With the states at which the
        engine reads the rates (the start of each segment, each state that a solver accepts), this
        is where the fast tier looks: a flow that is at zero at all of them counts as not moved."""
        plan = self.plan
        for name in plan.quantities:
            keys = [key for key in plan.part_flows[name] if key is not None and key not in self.flowing]
            if keys:
                self.see_flows([name], Env(self, plan.space_of(name), None, self.horizon))

    def negative_flow(self, name):
        """A flow cannot ask a rate below zero: the general tier gives the error of the run."""
        return Outside(f'a flow of {name} with a rate below zero', space=self.plan.space_of(name))

    def delivered(self, key, env):
        """The rate that a flow delivers for the instances of `env`: what it asks, or its share of
        the limit of its group when the flows of the group ask more than the limit together."""
        plan = self.plan
        members = plan.coupled.get(key)
        if members is not None:
            # Flows that move by one fraction: each gets its request times the smallest share that
            # any of them can have of its own request.
            found = env.memo.get(('coupled', members))
            if found is None:
                found = env.memo[('coupled', members)] = self.fraction(members, env)
            return _spread(self.value(plan.flows[key], env), env.count).astype(float) * found
        return self.alone(key, env)

    def alone(self, key, env):
        """What a flow delivers by itself: with the limit of its group and the bound of its source,
        and without the flows that move by one fraction with it."""
        plan = self.plan
        group = plan.groups.get(plan.flow_group.get(key))
        floor = plan.floors.get(plan.flow_source.get(key))
        if group is not None and (group.capacity is not None or floor is not None):
            found = env.memo.get(('group', group.name))
            if found is None:
                found = env.memo[('group', group.name)] = self.rationed(group, env)
            return found[key]
        asked = self.value(plan.flows[key], env)
        if floor is None:
            return asked
        # The one flow out of a quantity that rests on its bound gets no more than what comes in.
        rests = _spread(env[floor.flag], env.count).astype(bool)
        if not rests.any():
            return asked
        asked = _spread(asked, env.count).astype(float)
        return np.where(rests, np.minimum(asked, self.supply(floor, env)), asked)

    def fraction(self, members, env, but=None):
        """The fraction of their requests that flows that move by one fraction get: the smallest of
        what each can have of its own request (`but`: without that one). A flow that asks nothing
        while another asks something stops the run."""
        plan, count = self.plan, env.count
        asked = {key: _spread(self.value(plan.flows[key], env), count).astype(float) for key in members}
        some = np.zeros(count, dtype=bool)
        none = np.zeros(count, dtype=bool)
        for values in asked.values():
            some |= values > 0
            none |= values <= 0
        if (some & none).any():
            raise SimulationError('A coupled transaction must request every material flow together')
        found = np.ones(count)
        for key in members:
            if key == but:
                continue
            can = _spread(self.alone(key, env), count).astype(float)
            with np.errstate(divide='ignore', invalid='ignore'):
                found = np.minimum(found, np.where(asked[key] > 0, can / asked[key], 1.0))
        return found

    def supply(self, floor, env):
        """What comes into a quantity that can rest on its bound, for the instances of `env`: what
        the flows into it deliver, and the parts of its rate that are no flow."""
        found = env.memo.get(('supply', floor.name))
        if found is None:
            total = np.zeros(env.count)
            for node in floor.base:
                total = total + _spread(self.value(node, env), env.count)
            if np.any(total < 0):
                raise Outside(
                    f'{floor.name}, which can rest on its bound, with a rate below zero',
                    space=self.plan.space_of(floor.name),
                )
            for key in floor.inflows:
                total = total + _spread(self.delivered(key, env), env.count)
            found = env.memo[('supply', floor.name)] = total
        return found

    def rationed(self, group, env, resting=True):
        """{flow: the rate that it delivers} of the flows of a group with a limit. While they ask no
        more than the limit together, each delivers what it asks. Else a proportional group gives each
        the same fraction of what it asks, the limit over the sum of what they ask; and a priority
        group serves the flows of its order one after the other, each in full while the limit lasts.
        The arithmetic is that of the continuous engine (`Field._ration`), for each instance."""
        plan, count = self.plan, env.count
        asked = {key: _spread(self.value(plan.flows[key], env), count).astype(float) for key in group.flows}
        if group.capacity is None:
            capacity = np.full(count, np.inf)
        else:
            capacity = _spread(self.value(group.capacity, env), count).astype(float)
        if np.any(capacity < 0):
            raise SimulationError(f'Negative capacity for {group.name}')
        floor = plan.floor_of_group.get(group.name)
        if resting and floor is not None:
            # While the quantity that the flows drain rests on its bound, they share what comes in.
            rests = _spread(env[floor.flag], count).astype(bool)
            if rests.any():
                capacity = np.where(rests, np.minimum(capacity, self.supply(floor, env)), capacity)
        total = np.zeros(count)
        for key in group.flows:
            total = total + asked[key]
        over = total > capacity
        if not over.any():
            return asked
        if group.policy == 'proportional':
            with np.errstate(divide='ignore', invalid='ignore'):
                fraction = capacity / total
            return {key: np.where(over, asked[key] * fraction, asked[key]) for key in group.flows}
        found, remaining = dict(asked), capacity.copy()
        for key in group.order:
            cut = np.minimum(asked[key], remaining)
            remaining = remaining - cut
            found[key] = np.where(over, cut, asked[key])
        return found

    def field(self, solution, t, y, trial=True):
        """The rates of a numeric block at a state: at a state that its solver tries, or
        (`trial=False`) at a state of the run, where the rates are checked."""
        plan = self.plan
        state = Trial({name: y[cut] for name, cut in solution.slices.items()}, solution.block.whole)
        out = np.empty_like(y)
        envs = {}
        for name, cut in solution.slices.items():
            space = plan.quantities[name].space
            env = envs.get(space)
            if env is None:
                env = envs[space] = Env(self, space, solution.J, t, state)
            out[cut] = self.rate_of(name, env, trial)
        if trial:
            negative = next((env.memo[NEGATIVE] for env in envs.values() if NEGATIVE in env.memo), None)
            positive = set().union(*(env.memo.get(POSITIVE, ()) for env in envs.values()))
            solution.tried.append((t, y.copy(), negative, positive))
        self.counts['evaluations'] += 1
        solution.evaluations += 1
        if solution.evaluations > self.cfg.max_evaluations:
            raise SimulationError(
                f'{solution.block.names[0]}: more than {self.cfg.max_evaluations} evaluations of its rates '
                f'between two moments (t = {t:g} h)'
            )
        return out

    def matrices(self, block, J, start=None):
        """For the instances J (None: all) of a linear block, the matrix M of each: `y' = A y + c` as
        `[y, 1]' = M [y, 1]`, with A and c in the first rows and a last row of zeros; and, for each
        instance, whether no flow of the block can ask a rate below zero while each quantity is
        within its bounds: what the flow asks is `r + w y`, with r at or above 0 and each factor w
        at or above 0 and, where it is not 0, on a quantity whose lower bound is at or above 0.

        The closed form reads no rate at the start of its segment, so the flows that have not
        moved in the run yet (`flowing`) are looked at here. For one instance, `start` is its state
        there: a flow that delivers material at it has moved. For many, the third result has
        (flow, r, w) of each such flow, for `flows_from`."""
        plan, names = self.plan, block.names
        count = plan.spaces[block.space].count if J is None else len(J)
        size = len(names)
        zero = Trial({name: np.zeros(count) for name in names}, False)
        env = Env(self, block.space, J, 0.0, zero)
        floors = [plan.quantities[name].lower >= 0 for name in names]
        values = self.block_values(block, env) if count == 1 else None
        if values is not None:
            # One instance, from its program: plain numbers, with no array for each of them.
            asked = self.asked_alone(block, values)
            rows = [[0.0] * (size + 1) for _ in range(size + 1)]
            sure, at = True, 0
            for i, name in enumerate(names):
                row = rows[i]
                for (sign, _, is_flow), key in zip(plan.parts[name], plan.part_flows[name]):
                    if key is None or asked.get(key, False):
                        # What the part asks: no limit and no other flow cuts it at this state.
                        part = values[at]
                    else:
                        part = float(_one(self.delivered(key, env)))
                    row[size] += sign * part
                    slopes = values[at + 1 : at + 1 + size]
                    for j in range(size):
                        row[j] += sign * slopes[j]
                    if is_flow:
                        if part < 0:
                            sure = False
                        for j in range(size):
                            if not (slopes[j] == 0 or (slopes[j] > 0 and floors[j])):
                                sure = False
                    looked = start is not None and key is not None and key not in self.flowing
                    if looked and part + sum(slopes[j] * start[j] for j in range(size)) > 0:
                        self.flowing.add(key)
                    at += 1 + size
            return np.array([rows], dtype=float), np.array([sure]), []
        found = np.zeros((count, size + 1, size + 1))
        safe = np.ones(count, dtype=bool)
        at, asks = 0, []
        for i, name in enumerate(names):
            for (sign, node, is_flow), key in zip(plan.parts[name], plan.part_flows[name]):
                part = self.value(node, env) if key is None else self.delivered(key, env)
                part = _spread(part, count)
                found[:, i, size] += sign * part
                if is_flow:
                    safe &= part >= 0
                slopes = np.zeros((count, size)) if key is not None and key not in self.flowing else None
                for j, other in enumerate(names):
                    slope = _spread(self.value(derivative(node, other), env), count)
                    found[:, i, j] += sign * slope
                    if is_flow:
                        safe &= (slope == 0) | ((slope > 0) & floors[j])
                    if slopes is not None:
                        slopes[:, j] = slope
                if slopes is not None:
                    asks.append((key, part, slopes))
                at += 1 + size
        return found, safe, asks

    def flows_from(self, asks, states):
        """Mark the flows of `matrices` that deliver material at the states (one row for each
        instance) at which their segments start."""
        for key, part, slopes in asks:
            if key not in self.flowing and np.any(part + np.einsum('ij,ij->i', slopes, states) > 0):
                self.flowing.add(key)

    def asked_alone(self, block, values):
        """{flow of a part of a linear block: whether it delivers what it asks, from the values of
        `block_program`}: a flow that moves by one fraction with no other, whose source is no
        quantity that can rest on its bound, and whose group has no limit, or asks no more than its
        limit together (the test of `rationed`)."""
        plan, size = self.plan, len(block.names)
        found = {}
        for name in block.names:
            for key in plan.part_flows[name]:
                if key is None or key in found:
                    continue
                group = plan.groups.get(plan.flow_group.get(key))
                found[key] = (
                    key not in plan.coupled
                    and plan.floors.get(plan.flow_source.get(key)) is None
                    and (group is None or group.capacity is None)
                )
        at = sum(len(plan.parts[name]) for name in block.names) * (1 + size)
        for group in plan.block_groups[block.index]:
            total = 0.0
            for k in range(len(group.flows)):
                total = total + values[at + k * (1 + size)]
            capacity = values[at + len(group.flows) * (1 + size)]
            inside = capacity >= 0 and not total > capacity and plan.floor_of_group.get(group.name) is None
            for key in group.flows:
                if key in found:
                    found[key] = (
                        inside
                        and key not in plan.coupled
                        and plan.floors.get(plan.flow_source.get(key)) is None
                    )
            at += len(group.flows) * (1 + size) + 1
        return found

    def block_program(self, block):
        """One generated program for what the closed form of a linear block reads of its
        expressions (`core.evaluation.program`): for each part of each rate, its value and its
        derivative by each quantity of the block, in the order of `matrices`; then, for each flow
        of each group with a limit, the same, and the limit of the group, in the order of
        `group_terms`. False when the program cannot be made."""
        made = self.block_programs.get(block.index)
        if made is None:
            plan, names = self.plan, block.names
            outputs = []
            for name in names:
                for _, node, _ in plan.parts[name]:
                    outputs += [node, *(derivative(node, other) for other in names)]
            for group in plan.block_groups[block.index]:
                for key in group.flows:
                    node = plan.flows[key]
                    outputs += [node, *(derivative(node, name) for name in names)]
                outputs.append(group.capacity)
            try:
                made = compile_program([], outputs, units=self.registry)
            except (SyntaxError, RecursionError, ValueError, ExpressionError):
                made = False
            self.block_programs[block.index] = made
        return made

    def block_values(self, block, env):
        """The values of `block_program` for the one instance of an environment, with each quantity
        of the block at 0; None when there is no program, or when it fails: the caller then reads
        each expression by itself, which names the one that fails."""
        program = self.block_program(block)
        if not program:
            return None
        # The matrix of a block and what its groups ask are read one after the other. They read
        # values that only a step writes, so the values of the first reading serve the second while
        # no value was written between them.
        key = (block.index, 0 if env.J is None else int(env.J[0]), self.wrote)
        if self.block_made[0] == key:
            return self.block_made[1]
        try:
            values = program(Seen(env), self.registry)
        except (ArithmeticError, ValueError, TypeError, KeyError, ExpressionError):
            return None
        self.block_made = (key, values)
        return values

    def group_terms(self, block, J):
        """For each group with a limit of a linear block: what its flows ask together as
        `alpha + beta y` over the quantities y of the block, and its limit, for the instances J
        (None: all): (alpha, beta, the limit), with one row for each instance."""
        plan, names = self.plan, block.names
        count = plan.spaces[block.space].count if J is None else len(J)
        zero = Trial({name: np.zeros(count) for name in names}, False)
        env = Env(self, block.space, J, 0.0, zero)
        found = []
        values = self.block_values(block, env) if count == 1 else None
        # The values of the groups come after those of the parts of the rates (`block_program`).
        at = sum(len(plan.parts[name]) for name in names) * (1 + len(names))
        for group in plan.block_groups[block.index]:
            alpha, beta = np.zeros(count), np.zeros((count, len(names)))
            for key in group.flows:
                node = plan.flows[key]
                alpha += _spread(values[at] if values is not None else self.value(node, env), count)
                for i, name in enumerate(names):
                    slope = (
                        values[at + 1 + i] if values is not None else self.value(derivative(node, name), env)
                    )
                    beta[:, i] += _spread(slope, count)
                at += 1 + len(names)
            capacity = values[at] if values is not None else self.value(group.capacity, env)
            at += 1
            found.append((alpha, beta, _spread(capacity, count).astype(float)))
        return found

    def decide(self, solution):
        """How a segment of a block is solved: by its closed form, or by the solver.

        The closed form is used for a linear block of one instance when each quantity of it is one
        of these, so that no state leaves its bounds without the timeline knowing:

        - it has no bound;
        - its rate reads no other quantity of the block. Then it moves to one side only (the
          solution of `y' = a y + c` rises or falls, and never turns), and the time at which it would
          reach a bound goes on the timeline, as for a line;
        - its lower bound is 0, it has no upper bound, the constant of its rate is 0 or more, and so
          is the factor of each other quantity in its rate, while no quantity of the block can be
          below 0. At the value 0 its rate is then 0 or more, so it stays at or above 0.

        A group with a limit must also stay below its limit, because the closed form is of the rates
        that the flows ask. What its flows ask together is `alpha + beta y` for at most one quantity
        y of the block, whose rate reads no other quantity of the block: it then moves to one side
        only, and the time at which it would reach the limit goes on the timeline. From that time the
        solver integrates the block, with the limit shared out."""
        plan, block = self.plan, solution.block
        solution.mode = 'numeric'
        if solution.numeric_only:
            return
        if not block.linear or block.whole or solution.t0 >= self.horizon:
            return
        if solution.given is not None:
            matrix, safe = solution.given
        else:
            found, sure, asks = self.matrices(block, solution.J, solution.y0)
            matrix, safe = found[0], bool(sure[0])
            self.flows_from(asks, solution.y0[None, : len(block.names)])
        if not safe:
            # A flow of the block could ask a rate below zero inside the segment: the solver reads
            # the rates at each state that it accepts.
            return
        size, j = len(block.names), solution.instance
        floors = [plan.quantities[name].lower >= 0 for name in block.names]
        reach = []
        for i, name in enumerate(block.names):
            quantity = plan.quantities[name]
            lower, upper = quantity.lower, quantity.upper
            others = [matrix[i, k] for k in range(size) if k != i]
            if not math.isfinite(lower) and not math.isfinite(upper):
                continue
            if all(value == 0 for value in others):
                for bound in (lower, upper):
                    span = _span(matrix[i, i], matrix[i, size], float(solution.y0[i]), bound)
                    if span is not None and solution.t0 + span < self.horizon:
                        reach.append((solution.t0 + span, name))
                continue
            stays = lower == 0 and not math.isfinite(upper) and matrix[i, size] >= 0 and all(floors)
            if stays and all(value >= 0 for value in others):
                continue
            return
        limits = []
        terms = solution.given_terms
        if terms is None:
            terms = [(a[0], b[0], c[0]) for a, b, c in self.group_terms(block, solution.J)]
        for alpha, beta, capacity in terms:
            if alpha + float(beta @ solution.y0[:size]) > capacity:
                return
            reads = np.flatnonzero(beta)
            if not len(reads):
                continue
            i = int(reads[0])
            if len(reads) > 1 or any(matrix[i, k] != 0 for k in range(size) if k != i):
                return
            span = _span(matrix[i, i], matrix[i, size], float(solution.y0[i]), (capacity - alpha) / beta[i])
            if span is not None and solution.t0 + span < self.horizon:
                limits.append(solution.t0 + span)
        solution.matrix, solution.mode = matrix, 'closed'
        for at, name in reach:
            self.entries += 1
            heapq.heappush(self.times, (float(at), self.entries, BOUND, name, j, int(self.lversion[name][j])))
        for at in limits:
            self.entries += 1
            version = int(self.lversion[block.names[0]][j])
            heapq.heappush(self.times, (float(at), self.entries, LIMIT, block.index, j, version))

    def within_bounds(self, solution, y, t):
        for name, cut in solution.slices.items():
            quantity = self.plan.quantities[name]
            at = slice(None) if solution.J is None else solution.J
            values = y[cut]
            if np.any(values < quantity.lower - self.slack[name][at]) or np.any(
                values > quantity.upper + self.atol[name][at]
            ):
                raise Outside(f'{name} at a bound (t = {t:g} h)', space=quantity.space)

    # ---- the start ------------------------------------------------------------------------------

    def start(self):
        plan = self.plan
        pending = dict(plan.quantities)
        literal = {}
        while pending:
            ready = []
            for quantity in pending.values():
                nodes = quantity.start if isinstance(quantity.start, tuple) else (quantity.start,)
                reads = set().union(*(plan.reads(node) for node in set(nodes)))
                if not reads & pending.keys():
                    ready.append((quantity, nodes))
            if not ready:
                raise SimulationError(f'Unresolved initial values: {sorted(pending)}')
            for quantity, nodes in ready:
                count = plan.spaces[quantity.space].count
                env = Env(self, quantity.space, None, 0.0)
                if isinstance(quantity.start, tuple):
                    column = np.empty(count)
                    for j, node in enumerate(nodes):
                        if node not in literal:
                            found = self.value(node, env)
                            literal[node] = found
                        found = literal[node]
                        column[j] = found[j] if isinstance(found, np.ndarray) else found
                else:
                    column = _spread(self.value(quantity.start, env), count).astype(float)
                self.v[quantity.name] = column
                del pending[quantity.name]
        sizes = self.sizes()
        outside = []
        for name, quantity in plan.quantities.items():
            start = self.v[name]
            size = sizes[name]
            self.atol[name] = self.cfg.atol_factor * size
            self.slack[name] = (
                self.atol[name] + self.cfg.rtol * size if quantity.monotone else self.atol[name]
            )
            wrong = (start < quantity.lower - self.slack[name]) | (start > quantity.upper + self.atol[name])
            outside += [self.rule_free_name(name, quantity.space, int(j)) for j in np.flatnonzero(wrong)]
        if outside:
            raise SimulationError(f'State bounds violated: {outside}')
        # The lists that do not move keep their values. Those of a list in a list are made on the way.
        for name, found in plan.aggregates.items():
            if not found.moving:
                self.aggregate(name, 0.0, None)
        for name, quantity in plan.quantities.items():
            if quantity.form != 'line':
                continue
            count = len(self.v[name])
            self.y0[name], self.t0[name], self.rate[name] = self.v.pop(name), np.zeros(count), np.zeros(count)
            self.lversion[name] = np.zeros(count, dtype=np.int64)
        for block in plan.blocks:
            for name in block.names:
                self.lversion[name] = np.zeros(len(self.v[name]), dtype=np.int64)
            first = [self.v.pop(name) for name in block.names]
            if block.whole:
                solution = self.whole[block.index] = Solution(self, block, None)
                solution.start(0.0, np.concatenate(first))
            else:
                count = plan.spaces[block.space].count
                kind = Component if block.net else Solution
                made = self.single[block.index] = [kind(self, block, j) for j in range(count)]
                if block.net:
                    self.components.extend(made)
                stacked = np.array(first)
                for j, solution in enumerate(made):
                    solution.start(0.0, stacked[:, j].copy())
        self.starting = False
        self.starting_lines = True
        for name, quantity in plan.quantities.items():
            if quantity.form == 'line':
                self.restart_line(name, None, 0.0)
        self.starting_lines = False
        if self.flag_changes:
            flags, self.flag_changes = self.flag_changes, []
            self.apply([], 0.0, changed=flags)
        for block in plan.blocks:
            if block.linear and not block.whole and self.horizon > 0:
                # The matrices of all instances in one pass; each segment that starts later makes its own.
                terms = self.group_terms(block, None)
                found, sure, asks = self.matrices(block, None)
                size = len(block.names)
                self.flows_from(asks, np.array([solution.y0[:size] for solution in self.single[block.index]]))
                for j, (solution, matrix) in enumerate(zip(self.single[block.index], found)):
                    solution.given = (matrix, bool(sure[j]))
                    solution.given_terms = [
                        (alpha[j], beta[j], capacity[j]) for alpha, beta, capacity in terms
                    ]
                    self.decide(solution)
        for index in range(len(plan.rules)):
            self.mark(index, None)
        self.check_all(0.0)

    # ---- the restarts ---------------------------------------------------------------------------

    def restart_line(self, name, J, t, value=None):
        """The line of a quantity starts again at t for the instances J (None: all): from `value`, or
        from where it is."""
        plan = self.plan
        quantity = plan.quantities[name]
        at = slice(None) if J is None else J
        y0, t0, rate = self.y0[name], self.t0[name], self.rate[name]
        y = y0[at] + rate[at] * (t - t0[at]) if value is None else value
        if self.record and not self.starting_lines:
            self.line_log.setdefault(name, []).append(
                (
                    t,
                    np.arange(len(y0)) if J is None else np.array(J),
                    y0[at].copy(),
                    t0[at].copy(),
                    rate[at].copy(),
                )
            )
        y0[at], t0[at] = y, t
        env = Env(self, quantity.space, J, t)
        new = self.rate_of(name, env)
        floor = plan.floors.get(name)
        if floor is not None:
            new = self.rest(floor, J, t, env, new)
        rate[at] = new
        self.lversion[name][at] += 1
        self.counts['line restarts'] += env.count
        # A line that falls to its lower bound, or rises to its upper bound, before the horizon:
        # the time goes on the timeline, and the run is outside this engine if the line still holds then.
        places = np.arange(len(y0)) if J is None else np.asarray(J)
        now = y0[at]
        for bound, toward in ((quantity.lower, new < 0), (quantity.upper, new > 0)):
            if not math.isfinite(bound) or not toward.any():
                continue
            with np.errstate(divide='ignore', invalid='ignore'):
                reach = t + (bound - now) / new
            # A quantity that can rest on its lower bound rests there from that time (FLOOR).
            kind = FLOOR if floor is not None and bound == quantity.lower else BOUND
            for j in np.flatnonzero(toward & (reach < self.horizon)).tolist():
                place = int(places[j])
                self.entries += 1
                heapq.heappush(
                    self.times,
                    (float(reach[j]), self.entries, kind, name, place, int(self.lversion[name][place])),
                )

    def rest(self, floor, J, t, env, rate):
        """Whether each instance of a quantity that can rest on its lower bound rests there from this
        restart, and its rate. It rests when it is at the bound and the flows out of it ask more than
        what comes in; the flows then get what comes in, and its rate is 0. It leaves the bound when
        the flows ask no more than what comes in. A change of the resting is a change of a value that
        the flows out of it read: `flag_changes` keeps it for the parts that read those flows."""
        plan = self.plan
        quantity = plan.quantities[floor.name]
        at = slice(None) if J is None else J
        flag = self.v[floor.flag]
        rests = flag[at].copy()
        supply = self.supply(floor, env)
        if floor.group is not None:
            alone = self.rationed(plan.groups[floor.group], env, resting=False)
            asked = np.zeros(env.count)
            for key in floor.outflows:
                asked = asked + alone[key]
        else:
            key = floor.outflows[0]
            asked = _spread(self.value(plan.flows[key], env), env.count).astype(float)
            if key in plan.coupled:
                # What the flows that move with it leave of its request.
                asked = asked * self.fraction(plan.coupled[key], env, but=key)
        now = rests.copy()
        now[rests & (asked <= supply)] = False
        now[~rests & (self.y0[floor.name][at] <= quantity.lower) & (asked > supply)] = True
        changed = now != rests
        if changed.any():
            places = np.arange(len(flag))[at][changed]
            if self.record:
                for place in places.tolist():
                    self.undo.setdefault(floor.flag, []).append((t, place, bool(flag[place])))
            flag[places] = now[changed]
            self.flag_changes.append((floor.flag, set(places.tolist())))
            self.wrote += 1
            # The rate again, with the flows as they are now.
            rate = self.rate_of(floor.name, Env(self, quantity.space, J, t))
        if now.any():
            # At rest: on the bound itself, with no rate. What comes in is what goes out.
            self.y0[floor.name][np.arange(len(flag))[at][now]] = quantity.lower
            rate = np.where(now, 0.0, rate)
        return rate

    def cut(self, block, j, t):
        """The solution of one instance of a block starts again at t from where it is."""
        solution = self.single[block.index][j]
        prior = {(block.index, j): np.array(solution.at(t), dtype=float)}
        self.restart_block(block, {j}, t, {}, prior)

    def check_readers(self, block, j, t):
        """The checks of the state and the partitions that read a quantity of a component hold at
        the time t of its present segment, or the run stops."""
        found = self.block_checks.get((block, j))
        if found is None:
            names = [(name, {j}) for name in self.plan.blocks[block].names]
            local = self.plan.nets[self.plan.blocks[block].space].local
            found = self.block_checks[(block, j)] = [
                item for item in self.closure(names)[4].items() if item[0] not in local
            ]
        for (kind, index), J in found:
            places = None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            (self.check if kind == 'check' else self.partition)(index, places, t)

    def segment_end(self, at, block, j):
        """A segment of a component ends at a time: that time is a moment of the timeline for the
        rules and the checks that read the component."""
        self.entries += 1
        version = int(self.lversion[self.plan.blocks[block].names[0]][j])
        heapq.heappush(self.times, (float(at), self.entries, END, block, int(j), version))

    def ends(self, block, j, t):
        """A segment of a component ended: the rates of the component can change there (a quantity
        of it reached or left a bound, or a rate changed its branch), and with them the answer of a
        rule that reads it. So the rules and the checks that read a quantity of the component are
        read there.

        A condition on the quantities of the component has one answer inside the segment that ended:
        a stock is at zero through a whole segment or at no time inside it, and a crossing that was
        reached inside it ended it. Where that answer is no, the rule can trigger again, as a rule
        whose condition is false can."""
        plan = self.plan
        middle = self.single[block][j].middle()
        rules, _, _, _, checks = self.closure([(name, {j}) for name in plan.blocks[block].names])
        for index, J in rules.items():
            rule = plan.rules[index]
            if middle is None or rule.each or rule.kind not in ('face', 'crossing'):
                continue
            count = plan.spaces[rule.space].count
            places = np.arange(count) if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            inside = self.holds(rule, Env(self, rule.space, places, middle), places, middle, False)
            self.rules[index].armed[places[~inside]] = True
        for (kind, index), J in checks.items():
            places = None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            (self.check if kind == 'check' else self.partition)(index, places, t)
        for index, J in rules.items():
            self.mark(index, J)

    def crossing_due(self, at, index, j):
        """The crossing that a rule watches in a component reaches its value at a time."""
        self.later(at, index, j, ROOT)

    def static(self, name, space, j, t):
        """The value at t, for the instance j of a space, of a name that does not move between
        moments, as one value."""
        found = self.read(name, space, np.array([j]), t, None)
        if isinstance(found, np.ndarray):
            return found.item(0)
        return found.item() if isinstance(found, np.generic) else found

    def sizes(self):
        """The size of each quantity for each instance, in execution units, as the continuous engine
        finds it (`continuous/system.System.sizes_of`): the size that the file writes, else the
        largest of one of its unit, its start value, its finite bounds, the largest start value of
        the quantities that flows and transfers connect it to, and the limit of an allocation group
        that rations a flow of it, over the horizon. The size sets the tolerance of the quantity."""
        plan = self.plan
        found = {}
        for name, quantity in plan.quantities.items():
            size = np.maximum(quantity.scale, np.abs(self.v[name]))
            for bound in (quantity.lower, quantity.upper):
                if math.isfinite(bound):
                    size = np.maximum(size, abs(bound))
            found[name] = size
        # The quantities that flows and transfers connect: each takes the largest start value of them.
        parent = {name: name for name in plan.quantities}

        def root(name):
            while parent[name] != name:
                parent[name] = parent[parent[name]]
                name = parent[name]
            return name

        pairs = [(flow.source, flow.target) for flow in plan.s.flows.values()]
        for rule in plan.rules:
            for outcome in rule.outcomes:
                pairs += [(source, target) for source, target, _ in outcome.moves]
        for a, b in pairs:
            if a in parent and b in parent:
                parent[root(a)] = root(b)
        sets = {}
        for name in plan.quantities:
            sets.setdefault(root(name), []).append(name)
        for members in sets.values():
            if len(members) == 1:
                continue
            counts = {len(self.v[name]) for name in members}
            if len(counts - {1}) > 1:
                raise Outside(f'{members[0]}: flows or transfers that connect quantities of two families')
            largest = np.zeros(max(counts))
            for name in members:
                largest = np.maximum(largest, np.abs(self.v[name]))
            for name in members:
                share = largest if len(self.v[name]) == len(largest) else largest.max()
                found[name] = np.maximum(found[name], share)
        # A rationed flow moves at most the limit of its group: over the horizon, that bounds what
        # its quantities can gain or lose. A limit that reads a formula bounds nothing here.
        for name, group in plan.groups.items():
            source = plan.s.allocation[name].capacity
            if source is None or group.capacity is None:
                continue
            if any(plan.kind.get(read) == 'formula' for read in names_in(source)):
                continue
            env = Env(self, group.space, None, 0.0)
            try:
                capacity = np.abs(_spread(self.value(group.capacity, env), env.count).astype(float))
            except (ExpressionError, ArithmeticError, ValueError, TypeError, KeyError):
                continue
            capacity = capacity * self.horizon
            for key in group.flows:
                flow = plan.s.flows[key]
                for end in (flow.source, flow.target):
                    if end in found:
                        found[end] = np.where(
                            np.isfinite(capacity), np.maximum(found[end], capacity), found[end]
                        )
        for name, quantity in plan.quantities.items():
            if quantity.size is not None:
                found[name] = np.full(len(self.v[name]), quantity.size)
            found[name] = np.broadcast_to(found[name], self.v[name].shape).astype(float)
        return found

    def rule_free_name(self, name, space, j):
        """The name of a part of the instance j of a space, as the flat structure names it."""
        family = self.plan.spaces[space].family
        return name if family is None else family.hosts[j] + name[len(family.host) :]

    def restart_block(self, block, J, t, forced, prior):
        """The solutions of a block start again at t: for the whole block, or for the instances J.
        `prior` has the state of each just before the step."""
        if block.whole:
            solutions = [(None, self.whole[block.index])]
        else:
            made = self.single[block.index]
            solutions = [(j, made[j]) for j in (range(len(made)) if J is None else sorted(J))]
        for j, solution in solutions:
            y = prior[(block.index, j)]
            for name, place, value in forced.get((block.index, j), ()):
                at = solution.slices[name].start + place
                y[at] = value
            if self.record:
                # The segment that ends here, as it is: a reader of the past asks it.
                self.block_log.setdefault((block.index, j), []).append((t, copy.copy(solution)))
            solution.start(t, y)
            for name in block.names:
                self.lversion[name][slice(None) if j is None else j] += 1
            if block.net:
                self.counts['block restarts'] += 1
                continue  # a component finds its bounds and the form of its segments itself
            self.within_bounds(solution, y, t)
            # How the segment is solved is decided now, and not when a reader first asks: the
            # decision puts on the timeline the time at which a bound or a limit would be reached.
            if (block.index, j) not in self.restart_numeric:
                self.decide(solution)
            self.counts['block restarts'] += 1

    # ---- what a step wrote ----------------------------------------------------------------------

    def targets(self, space, name, J, how):
        """The instances of `space` that read the instances J of `name`: a set, or None for all."""
        if J is None or how == ALL:
            return None
        if how == SAME:
            return set(J)
        back = self.plan.spaces[space].linked_from[self.plan.space_of(name)]
        found = set()
        for k in J:
            found.update(back.get(k, ()))
        return found

    @staticmethod
    def merge(found, key, target):
        """Add the instances `target` to those of `key`. Whether that added any."""
        if key not in found:
            found[key] = None if target is None else set(target)
            return True
        kept = found[key]
        if kept is None:
            return False
        if target is None:
            found[key] = None
            return True
        size = len(kept)
        kept |= target
        return len(kept) > size

    def closure(self, written):
        """The parts that read, by any path, the names that a step writes: {rule: instances}, {line:
        instances}, {block: instances}, {(list, member): instances}. Instances: a set, or None for all."""
        plan = self.plan
        rules, lines, blocks, terms, checks = {}, {}, {}, {}, {}
        lists = set()
        queue = list(written)
        while queue:
            name, J = queue.pop()
            for reader in plan.readers.get(name, ()):
                kind, how = reader[0], reader[-1]
                if kind == 'rule':
                    self.merge(rules, reader[1], self.targets(plan.rules[reader[1]].space, name, J, how))
                elif kind == 'line':
                    target = self.targets(plan.quantities[reader[1]].space, name, J, how)
                    if self.merge(lines, reader[1], target):
                        queue.append((reader[1], target))
                elif kind in ('check', 'partition'):
                    part = (plan.checks if kind == 'check' else plan.partitions)[reader[1]]
                    self.merge(checks, (kind, reader[1]), self.targets(part.space, name, J, how))
                elif kind == 'block':
                    block = plan.blocks[reader[1]]
                    target = None if block.whole else self.targets(block.space, name, J, how)
                    if self.merge(blocks, reader[1], target):
                        queue.extend((member, target) for member in block.names)
                else:
                    term = plan.aggregates[reader[1]].terms[reader[2]]
                    self.merge(terms, (reader[1], reader[2]), self.targets(term.space, name, J, how))
                    if reader[1] not in lists:
                        lists.add(reader[1])
                        queue.append((reader[1], None))
        return rules, lines, blocks, terms, checks

    def apply(self, writes, t, restart=(), changed=()):
        """Make the writes of one step, and bring up to date the parts that read them. A write is
        (name, place in the space of the name, value). `restart` names blocks of one instance, as
        (block, instance), that start again at t with the solver: a group of theirs reached its
        limit."""
        plan = self.plan
        written = [(name, {place}) for name, place, _ in writes]
        written.extend(changed)
        for name, place, _ in writes:
            # A step wrote the quantity of a crossing: the time at which the crossing was reached
            # says nothing of the new value, so the rule holds only by that value.
            for index in plan.crossings.get(name, ()):
                reached = self.rules[index].reached
                if plan.rules[index].space == plan.space_of(name):
                    reached[place] = 0
                else:
                    reached[:] = 0
        for index, j in restart:
            written.extend((member, {j}) for member in plan.blocks[index].names)
        forced = {}
        for name, place, value in writes:
            if plan.kind[name] == 'numeric':
                block = plan.blocks[plan.quantities[name].block]
                key = (block.index, None if block.whole else place)
                forced.setdefault(key, []).append((name, place if block.whole else 0, value))
                # The block starts again from the written state, so each quantity of it takes a new
                # path: what reads any of them is read again, not only what reads the written one.
                target = None if block.whole else {place}
                written.extend((member, target) for member in block.names if member != name)
        rules, lines, blocks, terms, checks = self.closure(written)
        for index, j in (*forced, *restart):
            self.merge(blocks, index, None if j is None else {j})
        # The state of each block that starts again, just before the step: a block is integrated only
        # when a reader asks, and the values that it read up to this moment are those before the
        # step.
        prior = {}
        for index, J in blocks.items():
            block = plan.blocks[index]
            if block.whole:
                found = [(None, self.whole[index])]
            else:
                made = self.single[index]
                found = [(j, made[j]) for j in (range(len(made)) if J is None else J)]
            for j, solution in found:
                prior[(index, j)] = np.array(solution.at(t), dtype=float)
        for name, place, value in writes:
            kind = plan.kind[name]
            if kind == 'value':
                if self.record:
                    self.undo.setdefault(name, []).append((t, place, self.v[name][place]))
                self.v[name][place] = value
                self.wrote += 1
            elif kind == 'line':
                self.restart_line(name, np.array([place]), t, value)
        for (name, place), J in sorted(terms.items(), key=lambda item: (int(item[0][0][6:]), item[0][1])):
            self.update_term(name, place, J, t)
        for name, J in lines.items():
            self.restart_line(name, None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J)), t)
        self.restart_numeric = set(restart)
        for index, J in blocks.items():
            self.restart_block(plan.blocks[index], J, t, forced, prior)
        for index, j in restart:
            self.single[index][j].numeric_only = True
            self.single[index][j].mode = 'numeric'
        self.restart_numeric = set()
        # A quantity that came to rest on its bound, or left it, in these restarts: the parts that
        # read the flows out of it are brought up to date in their turn.
        while self.flag_changes:
            flags, self.flag_changes = self.flag_changes, []
            self.apply([], t, changed=flags)
        for (kind, index), J in checks.items():
            places = None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            (self.check if kind == 'check' else self.partition)(index, places, t)
        for index, J in rules.items():
            self.mark(index, J)
        if self.reading == 'every':
            for index in range(len(plan.rules)):
                self.mark(index, None)

    def holds_at_start(self, found):
        """Whether a check that reads only inputs and named states holds, for each instance of its
        space, with each state at its start value."""
        env = Env(self, found.space, None, 0.0)
        return _spread(self.value(found.node, env), env.count).astype(bool)

    def check(self, index, J, t):
        """A check of the state holds for the instances J (None: all), or the run stops."""
        found = self.plan.checks[index]
        env = Env(self, found.space, J, t)
        try:
            holds = _spread(self.value(found.node, env), env.count).astype(bool)
        except ExpressionError as problem:
            # A failure names the expression, as the evaluation of an expression of the model does.
            raise ExpressionError(f'{found.source!r}: {problem}') from problem
        if holds.all():
            return
        at = int(np.flatnonzero(~holds)[0])
        name = self.plan.check_name(found.name, found.space, at if J is None else int(J[at]))
        raise SimulationError(
            f'Check {name}: {found.message}',
            [{'code': 'check_failed', 'severity': 'error', 't': float(t), 'check': name, 'path': found.path}],
        )

    def partition(self, index, J, t):
        """The parts of a partition add up to its total for the instances J (None: all), within its
        tolerance, or within 1e-9 of the size of the total when it has none; else the run stops."""
        found = self.plan.partitions[index]
        env = Env(self, found.space, J, t)
        total = _spread(self.value(found.total, env), env.count).astype(float)
        parts = np.zeros(env.count)
        for part in found.parts:
            if self.plan.space_of(part) == found.space:
                parts = parts + _spread(env[part], env.count)
            else:
                parts = parts + _pairwise(self.column(part, t))
        if found.tolerance is None:
            limit = 1e-9 * np.maximum(1.0, np.abs(total))
        else:
            limit = _spread(self.value(found.tolerance, env), env.count).astype(float)
        wrong = np.abs(parts - total) > limit
        if not wrong.any():
            return
        at = int(np.flatnonzero(wrong)[0])
        name = self.plan.check_name(found.name, found.space, at if J is None else int(J[at]))
        raise SimulationError(
            f'Partition {name}: its parts add up to {parts[at]}, not {total[at]}',
            [
                {
                    'code': 'partition_failed',
                    'severity': 'error',
                    't': float(t),
                    'partition': name,
                    'path': found.path,
                }
            ],
        )

    def check_all(self, t):
        for found in self.plan.checks:
            self.check(found.index, None, t)
        for found in self.plan.partitions:
            self.partition(found.index, None, t)

    def mark(self, index, J):
        """The rule is read again for the instances J (None: all)."""
        if J is None:
            self.dirty[index] = None
        elif self.dirty.get(index, ()) is not None:
            self.dirty.setdefault(index, set()).update(J)

    # ---- the reading of a rule --------------------------------------------------------------------

    def holds(self, rule, env, J, t, reached):
        """Whether the condition of a rule holds for the instances J. `reached`: the time at which
        the crossing of the instance reaches its value is within the tolerance of a time of this
        moment. Then the crossing holds, as a clock within that tolerance does (D-65). With the reading
        of every rule, a crossing holds inside the tolerance band of its quantity, at any moment."""
        count = len(J)
        if rule.kind in ('discrete', 'face'):
            return _spread(self.value(rule.when, env), count).astype(bool) & ~self.spent(rule, env, J)
        found = _spread(self.value(rule.gate, env), count).astype(bool) & ~self.spent(rule, env, J)
        for node in rule.times:
            found = found & (_spread(self.value(node, env), count) <= t + self.tolerance)
        if rule.kind == 'crossing':
            value = _spread(env[rule.var], count)
            threshold = _spread(self.value(rule.value, env), count)
            if self.reading == 'every':
                band = self.atol[rule.var][J] if len(self.atol[rule.var]) > 1 else self.atol[rule.var][0]
                found = found & ((value >= threshold - band) if rule.rising else (value <= threshold + band))
            else:
                found = found & (reached | ((value >= threshold) if rule.rising else (value <= threshold)))
        return found

    def window(self, rule, env, count):
        """The values of the window (`each`) of a rule, for each instance: a list of tuples."""
        columns = [_spread(self.value(node, env), count).tolist() for node in rule.each]
        return list(zip(*columns))

    def spent(self, rule, env, J):
        """Whether each instance of a rule with a window has triggered in the window of this
        moment. A window lasts while the values of `each` stay the same: when they change, the memory
        of the trigger is spent, and a value seen before opens a new window."""
        found = np.zeros(len(J), dtype=bool)
        if not rule.each:
            return found
        kept = self.rules[rule.index].window
        now = None
        for at, j in enumerate(J.tolist()):
            if kept[j] is None:
                continue
            if now is None:
                now = self.window(rule, env, len(J))
            if kept[j] != now[at]:
                kept[j] = None
            else:
                found[at] = True
        return found

    def later(self, at, index, j, kind=RULE):
        """Put a time of a rule on the timeline: of a clock or of the end of a delay (RULE), or the
        time at which its crossing reaches its value (ROOT)."""
        self.entries += 1
        heapq.heappush(
            self.times, (float(at), self.entries, kind, index, int(j), int(self.rules[index].version[j]))
        )

    def read_rule(self, rule, J, t):
        """Read a rule for the instances J, as one moment reads it, and put on the
        timeline the time at which each instance is read again."""
        state, count = self.rules[rule.index], len(J)
        self.counts['readings'] += count
        state.version[J] += 1
        env = Env(self, rule.space, J, t)
        holds = self.holds(rule, env, J, t, state.reached[J] == self.moment)
        ends = state.pending[J]
        pending = ~np.isnan(ends)
        due = np.zeros(count, dtype=np.int8)
        cancelled = np.zeros(count, dtype=bool)
        if rule.keep is not None and pending.any():
            # The reason to wait has gone: the firing is cancelled, and the rule triggers again once
            # its condition becomes true again.
            cancelled = pending & ~_spread(self.value(rule.keep, env), count).astype(bool)
            if cancelled.any():
                state.pending[J[cancelled]] = np.nan
                state.armed[J[cancelled]] = ~holds[cancelled]
                pending = pending & ~cancelled
        if pending.any():
            fire = pending & (ends <= t + self.tolerance)
            due[fire] = FIRE
            for j, at in zip(J[pending & ~fire].tolist(), ends[pending & ~fire].tolist()):
                self.later(at, rule.index, j)
            state.armed[J[pending & holds]] = False
        free = ~pending & ~cancelled
        can = ~(rule.once & (state.triggered[J] > 0))
        due[free & holds & state.armed[J] & can] = TRIGGER
        quiet = free & ~holds
        if quiet.any():
            state.armed[J[quiet]] = True
        quiet = quiet | (cancelled & ~holds)
        if quiet.any() and not rule.named:
            # An instance whose window is spent waits for a step that changes the window, not for a time.
            self.watch(rule, J[quiet & can & ~self.spent(rule, env, J)], t)
        was = state.ready[J]
        state.ready[J] = due
        new = (due != 0) & (was == 0)
        if new.any():
            positions, copies = self.order[rule.index]
            for j in J[new].tolist():
                heapq.heappush(
                    self.ready, ((rule.line, int(positions[j]), int(copies[j]), rule.index), rule.index, j)
                )

    def watch(self, rule, J, t):
        """Instances of a rule whose condition does not hold: the time at which their clocks, or
        their crossing, can make it hold goes on the timeline."""
        if not len(J) or rule.kind == 'face':
            # A condition on stocks at zero is read where a segment of its block ends (`ends`).
            return
        env = Env(self, rule.space, J, t)
        count = len(J)
        open_ = _spread(self.value(rule.gate, env), count).astype(bool) if rule.kind != 'discrete' else None
        if open_ is None or not open_.any():
            return
        clock = np.full(count, -np.inf)
        for node in rule.times:
            clock = np.maximum(clock, _spread(self.value(node, env), count))
        waits = open_ & (clock > t + self.tolerance)
        for j, at in zip(J[waits].tolist(), clock[waits].tolist()):
            if at <= self.horizon + self.tolerance:
                self.later(at, rule.index, j)
        if rule.kind != 'crossing':
            return
        seek = open_ & ~waits
        if not seek.any():
            return
        threshold = _spread(self.value(rule.value, env), count)
        plan = self.plan
        places = self.index(rule.space, plan.space_of(rule.var), J)
        if plan.kind[rule.var] == 'line':
            y0, t0, rate = self.y0[rule.var], self.t0[rule.var], self.rate[rule.var]
            at = slice(None) if places is ONE or places is None else places
            toward = (rate[at] > 0) if rule.rising else (rate[at] < 0)
            with np.errstate(divide='ignore', invalid='ignore'):
                reach = t0[at] + (threshold - y0[at]) / rate[at]
            for k in np.flatnonzero(seek & toward & (reach <= self.horizon + self.tolerance)).tolist():
                self.later(max(float(reach[k]), t), rule.index, int(J[k]), ROOT)
            return
        block = plan.blocks[plan.quantities[rule.var].block]
        for k in np.flatnonzero(seek).tolist():
            place = 0 if places is ONE else int(places[k]) if places is not None else k
            if block.whole:
                solution = self.whole[block.index]
                at = solution.slices[rule.var].start + place
            else:
                solution = self.single[block.index][place]
                at = solution.slices[rule.var].start
            if block.net:
                # A component watches the crossing in each of its segments, as it makes them.
                solution.watch(rule.index, int(J[k]), at, float(threshold[k]), rule.rising, t)
                continue
            mark = float(threshold[k])
            if rule.index in self.monotone_crossings:
                # A value that only rises or only falls can come near its mark and never pass
                # it. Its crossing is watched half a tolerance before the mark, inside the band in
                # which the rule holds, as the general tier watches it (`integrate.root_value`).
                band = self.atol[rule.var]
                half = 0.5 * float(band[place] if len(band) > 1 else band[0])
                mark = mark - half if rule.rising else mark + half
            root = solution.first_root(at, mark, rule.rising, t)
            if root is not None:
                self.later(root, rule.index, int(J[k]), ROOT)

    # ---- the steps ------------------------------------------------------------------------------

    def rule_name(self, rule, j):
        family = self.plan.spaces[rule.space].family
        if family is None:
            return rule.name
        return family.hosts[j] + rule.name[len(family.host) :]

    def count_step(self, t, rule, j):
        # The budget is for the steps of one thing at one moment: the rows of a table can each take
        # their steps at the same moment, so the limit is that number times the rows of the largest
        # table, as the limit of the events of a run is.
        limit = self.cfg.max_steps * max(space.count for space in self.plan.spaces)
        if self.steps >= limit:
            name = self.rule_name(rule, j)
            raise SimulationError(
                f'The moment t={t:g} h does not settle within {limit} steps; next: {name}',
                [{'code': 'step_budget', 'severity': 'error', 't': t, 'next': [name]}],
            )
        self.steps += 1
        self.counts['steps'] += 1

    def place(self, space, j, name):
        """The place, in the space of `name`, of the instance that instance j of `space` reads or writes."""
        other = self.plan.space_of(name)
        if other == space:
            return j
        if self.plan.spaces[other].count == 1:
            return 0
        links = self.plan.spaces[space].links
        if other not in links:
            raise Outside(f'a step of a family that writes {name}, a value of another family')
        return int(links[other][j])

    def emitted(self, events, space, j, t, writes):
        for event in events:
            if event in self.plan.events:
                place = self.place(space, j, event)
                count = int(self.v[event + COUNT][place]) + 1
                writes.append((event + COUNT, place, count))
                writes.append((event + TIME, place, t))

    def trigger(self, rule, j, t):
        """A rule triggers for the instance j at the time t."""
        state = self.rules[rule.index]
        self.count_step(t, rule, j)
        state.armed[j] = False
        state.triggered[j] += 1
        # The crossing that brought the rule to this moment has had its trigger: from here the rule
        # holds only while its quantity is at or past its value.
        state.reached[j] = 0
        self.mark(rule.index, {j})
        env = Env(self, rule.space, np.array([j]), t)
        if rule.each:
            state.window[j] = self.window(rule, env, 1)[0]
        if rule.delay is None:
            self.fire(rule, j, t, counted=True, own=True)
            return
        self.extras(rule, j, env, t, 'trigger')
        delay = float(_one(self.value(rule.delay, env)))
        if not math.isfinite(delay) or delay < 0:
            name = self.rule_name(rule, j)
            path = rule.delay_path if rule.delay_path is not None else rule.path
            raise SimulationError(
                f'{name}: a delay is a finite time from 0, not {delay} h',
                [{'code': 'delay', 'severity': 'error', 'rule': name, 'path': path}],
            )
        state.pending[j] = t + delay
        writes = []
        self.emitted(rule.emits, rule.space, j, t, writes)
        self.trace.append((float(t), rule.index, j, None))
        self.entry(rule, j, None, t, {}, {}, [], {})
        self.apply(writes, t)
        self.snapshot(t, step=True)

    def chosen(self, rule, env, j, t):
        """The place of the outcome that a firing takes. Each chance is from 0 to 1, the chances add
        up to 1, and an outcome that cannot happen now (its condition fails) has no chance; else the
        run stops. The central run takes the likeliest outcome, the first in the file on a tie."""
        outcomes = rule.outcomes
        if len(outcomes) == 1 and outcomes[0].chance in (None, 'else'):
            return 0
        name = self.rule_name(rule, j)

        def stop(message):
            return SimulationError(
                message, [{'code': 'chances', 'severity': 'error', 'rule': name, 't': float(t)}]
            )

        chances, rest = [], None
        for place, item in enumerate(outcomes):
            if item.chance is None:
                chances.append(1.0)
            elif item.chance == 'else':
                chances.append(0.0)
                rest = place
            else:
                value = float(_one(self.value(item.chance, env)))
                if not math.isfinite(value) or value < -CHANCE_TOLERANCE or value > 1 + CHANCE_TOLERANCE:
                    raise stop(f'{name}.{item.name}: a chance is from 0 to 1, not {value:g}, at t={t:g} h')
                chances.append(min(max(value, 0.0), 1.0))
        if rest is not None:
            chances[rest] = max(0.0, 1.0 - sum(chances))
        total = sum(chances)
        if abs(total - 1.0) > CHANCE_TOLERANCE:
            raise stop(f'{name}: the chances of its outcomes add up to {total:g} at t={t:g} h, not 1')
        possible = []
        for place, item in enumerate(outcomes):
            can = item.available is None or bool(_one(self.value(item.available, env)))
            possible.append(can)
            if not can and chances[place] > CHANCE_TOLERANCE:
                raise stop(
                    f'{name}.{item.name}: an outcome that cannot happen now has the chance '
                    f'{chances[place]:g} at t={t:g} h'
                )
        controller = self.controller(rule, j)
        if controller is not None:
            # A chance is the model's estimate of what the actor does, which a pick replaces; the
            # condition under which an outcome can happen is not.
            return self.pick(rule, j, chances, possible, t, env, controller)
        if self.outcomes is not None:
            return self.taken(name, chances)
        if not self.luck:
            return max(range(len(chances)), key=lambda place: (chances[place], -place))
        # A sample of a study: one uniform number for each firing, from the stream of the event.
        if name not in self.streams:
            self.streams[name] = draws(self.luck['seed'], f'{name}/{self.luck["sample"]}')
        u, total, last = self.streams[name](), 0.0, None
        for place, chance in enumerate(chances):
            if chance <= 0:
                continue
            total, last = total + chance, place
            if u < total:
                return place
        return last

    def taken(self, name, chances):
        """The outcome of a firing of a run with given outcomes (`outcomes`): the given place, or
        the likeliest outcome after the last given place (the first in the file on a tie). The run
        keeps the firing as (the name of the rule, the chance with which a sample takes each
        outcome, the place taken). A given place is one that a sample can take."""
        found, at = shares(chances), len(self.firings)
        if at < len(self.outcomes):
            place = self.outcomes[at]
            if not 0 <= place < len(found) or found[place] <= 0:
                raise ValueError(f'{name}: no sample takes the outcome {place} of its firing number {at}')
        else:
            place = max(range(len(found)), key=lambda other: (found[other], -other))
        self.firings.append((name, tuple(found), place))
        return place

    def fire(self, rule, j, t, counted=False, own=False):
        """One step of a rule: the firing of the instance j at the time t."""
        plan = self.plan
        if not counted:
            self.count_step(t, rule, j)
        self.mark(rule.index, {j})
        env = Env(self, rule.space, np.array([j]), t)
        self.extras(rule, j, env, t, 'fire')
        outcomes = rule.outcomes
        outcome = outcomes[self.chosen(rule, env, j, t)]
        # Every value of the step is read before the step.
        writes = []

        def now(name, place):
            """The value of a quantity for one instance at the moment."""
            inner = Env(self, plan.space_of(name), np.array([place]), t)
            return float(_one(inner[name]))

        held = {}  # (quantity, place) -> its value in the step so far
        sets, modes, before, moved = {}, {}, {}, []  # what the entry of the trace says of the step

        def bounds(name, place):
            quantity = plan.quantities[name]
            return (
                quantity.lower,
                quantity.upper,
                float(self.slack[name][place]),
                float(self.atol[name][place]),
            )

        for target, node, mode in outcome.sets:
            place = self.place(rule.space, j, target)
            if node is None or target in plan.modes:
                value = mode if node is None else _one(self.value(node, env))
                if node is not None and value not in plan.modes[target]:
                    raise SimulationError(
                        f'{self.rule_name(rule, j)}: {target} cannot take the value {value!r}'
                    )
                modes[(target, place)], before[(target, place)] = value, self.v[target][place]
                if value != self.v[target][place]:
                    writes.append((target + ENTERED, place, t))
                writes.append((target, place, value))
                continue
            value = float(_one(self.value(node, env)))
            if not math.isfinite(value):
                raise SimulationError(f'{self.rule_name(rule, j)}: nonfinite value for {target}')
            if target in plan.quantities:
                # A value that misses a bound by less than the solver can resolve is on the bound, so
                # the next segment starts inside the domain.
                lower, upper, slack, atol = bounds(target, place)
                if lower - slack <= value < lower:
                    value = float(lower)
                elif upper < value <= upper + atol:
                    value = float(upper)
                held[(target, place)] = value
            else:
                writes.append((target, place, value))
            sets[(target, place)] = value
        moves = []
        for source, target, node in outcome.moves:
            amount = float(_one(self.value(node, env)))
            if not math.isfinite(amount) or amount < 0:
                raise SimulationError(
                    f'{self.rule_name(rule, j)}: a move takes a finite amount from 0, not {amount}'
                )
            moves.append(
                (
                    (source, self.place(rule.space, j, source)),
                    (target, self.place(rule.space, j, target)),
                    amount,
                )
            )
        if moves:
            # Every move must fit together with the values that the step sets: each quantity of a
            # move, and each that the step sets, stays inside its bounds.
            trial = dict(held)
            for source, target, amount in moves:
                for key, sign in ((source, -1.0), (target, 1.0)):
                    if key not in trial:
                        trial[key] = now(*key)
                    trial[key] += sign * amount
            for (name, place), value in trial.items():
                lower, upper, slack, atol = bounds(name, place)
                if not lower - slack <= value <= upper + atol:
                    raise SimulationError(
                        f'{self.rule_name(rule, j)}: a move does not fit: the stock holds less than the amount',
                        [
                            {
                                'code': 'transaction_failed',
                                'severity': 'error',
                                'rule': self.rule_name(rule, j),
                                'path': rule.path,
                            }
                        ],
                    )
        for source, target, asked in moves:
            for key in (source, target):
                if key not in held:
                    held[key] = now(*key)
            value, lower = held[source], bounds(*source)[0]
            amount = asked
            left = value - amount
            # A move that would leave less than the solver can resolve behind moves everything. A
            # stock that already sits below its bound by such an amount has nothing to move.
            if left != lower and abs(left - lower) <= bounds(*source)[3]:
                amount = amount + (left - lower)
                if amount >= 0:
                    left = lower
                else:
                    amount, left = 0.0, value
            held[source] = left
            value = held[target]
            held[target] = value + amount
            moved.append((source, target, amount))
        for (name, place), value in held.items():
            # The structure lets no step lower a tally; the run checks it all the same.
            if plan.quantities[name].monotone and value < now(name, place):
                raise SimulationError(f'A step decreases the nondecreasing quantity {name}')
        writes += [(name, place, value) for (name, place), value in held.items()]
        for name, place, value in writes:
            quantity = plan.quantities.get(name)
            if quantity is not None and not (
                quantity.lower - self.slack[name][place] <= value <= quantity.upper + self.atol[name][place]
            ):
                raise SimulationError(
                    f'{self.rule_name(rule, j)} at t={t:g} h leaves {name} outside its bounds',
                    [
                        {
                            'code': 'joint_feasibility',
                            'severity': 'error',
                            't': t,
                            'rules': [self.rule_name(rule, j)],
                        }
                    ],
                )
        self.emitted([*(rule.emits if own else ()), *outcome.emits], rule.space, j, t, writes)
        self.trace.append((float(t), rule.index, j, outcome.name))
        self.entry(rule, j, outcome, t, sets, modes, moved, before)
        self.apply(writes, t)
        self.snapshot(t, step=True)
        named = [(plan.rule_index[target], target) for target in outcome.fires if target in plan.rule_index]
        for at, (index, _) in enumerate(named):
            other = plan.rules[index]
            place = self.place(rule.space, j, other.name)
            if not self.can_trigger(index, place):
                continue
            if self.settled and self.controlled(index, place) and other.delay is None:
                # A decision that an event names waits until the independent work of the moment is
                # done; the events that the same line names after it wait behind it.
                self.continuations.append(
                    deque((k, self.place(rule.space, j, name)) for k, name in named[at:])
                )
                break
            waiting = len(self.continuations)
            self.trigger(other, place, t)
            if self.settled and len(self.continuations) > waiting:
                self.continuations[-1].extend(
                    (k, self.place(rule.space, j, name)) for k, name in named[at + 1 :]
                )
                break

    # ---- a played run ---------------------------------------------------------------------------

    def can_trigger(self, index, place):
        """A rule triggers unless it is `once` and has triggered, or it waits to fire."""
        state = self.rules[index]
        return not (self.plan.rules[index].once and state.triggered[place]) and bool(
            np.isnan(state.pending[place])
        )

    def flat_entity(self, rule, j):
        family = self.plan.spaces[rule.space].family
        return rule.entity if family is None or rule.entity != family.host else family.hosts[j]

    def controller(self, rule, j):
        """Who picks the outcomes of a rule in a played run (`reader` or `agent`), or None when chance
        takes them. The control of the run gives the method of a choice: by the event (`actor.event`,
        or the event of the set of copies of the actor), else by the actor (its name, or the name of
        its set of copies). `chance` is the default."""
        if not self.control or not rule.choice:
            return None
        key = (rule.index, j)
        if key not in self.controllers:
            name = self.rule_name(rule, j)
            found = None
            if self.decision_events is None or name in self.decision_events:
                origin = getattr(self.plan.s.entities.get(rule.entity), 'origin', None)
                event = name.rsplit('.', 1)[1]
                for item in (name, origin and f'{origin}.{event}', self.flat_entity(rule, j), origin):
                    if item and item in self.control:
                        found = None if self.control[item] == 'chance' else self.control[item]
                        break
            self.controllers[key] = found
        return self.controllers[key]

    def controlled(self, index, place):
        return self.controller(self.plan.rules[index], place) is not None

    def pick(self, rule, j, chances, possible, t, env, controller):
        """The outcome of a played decision: the next pick of the log, which must answer this
        decision with an outcome that can happen. With no pick left, the run asks for one (`decision`,
        the first that waits) and stops there, or goes on with the choice of the model."""
        name = self.rule_name(rule, j)
        names = [outcome.name for outcome in rule.outcomes]
        if self.picked >= len(self.picks):
            pending = self.decision or self.ask(rule, j, possible, t, env)
            if self.decision_resolver is not None:
                given = self.decision_resolver(
                    {**pending, 'pick_index': self.picked},
                    View(env),
                    tuple(MappingProxyType(self.entry_at(k)) for k in range(len(self.log))),
                )
                if given is not None:
                    if not isinstance(given, Mapping):
                        raise SimulationError('decision_resolver must return a pick mapping or None')
                    self.picks.append(dict(given))
            if self.picked >= len(self.picks):
                self.decision = pending
                if self.pause_at_decision:
                    raise Pause
                return max(range(len(chances)), key=lambda place: (chances[place], -place))
        given = self.picks[self.picked]
        where = {'code': 'pick', 'severity': 'error', 'rule': name, 't': t, 'pick': self.picked}
        if given.get('event') != name or given.get('outcome') not in names:
            raise SimulationError(
                f'Pick {self.picked + 1} answers {given.get("event")} with {given.get("outcome")}, '
                f'but the run asks {name} ({", ".join(names)}) at t={t:g} h: the picks belong to '
                'another run',
                [where],
            )
        k = names.index(given['outcome'])
        if not possible[k]:
            raise SimulationError(f'{name}: {given["outcome"]} cannot happen at t={t:g} h', [where])
        self.picked += 1
        self.picking = controller
        return k

    def happened(self, k, event):
        """Whether the step k of the trace is a time that `event` happened: the event of a rule (when
        it triggers) or of one of its outcomes. A rule without a delay fires as it triggers: its
        firing is its own event too."""
        entry = self.entry_at(k)
        if entry['event'] == event:
            return True
        waits = self.plan.rules[self.log[k][2]].delay is not None
        return entry['rule'] == event and entry['outcome'] is not None and not waits

    def ask(self, rule, j, possible, t, env):
        """What a decision that waits for a pick shows: its time, thing, event and text, its outcomes
        and which can happen, and what its actor sees: the value of each fact (`view`: of a field, in
        its unit, or how many times an event has happened) and the times its events happened."""
        plan = self.plan
        view, units, seen = {}, {}, set()

        def flat(name):
            space = plan.space_of(name)
            return self.rule_free_name(name, space, j) if space == rule.space else name

        for fact in plan.sees.get(rule.entity, ()):
            name = flat(fact.name)
            if fact.event is not None:
                found = [i for i in range(len(self.log)) if self.happened(i, flat(fact.event))]
                view[name] = len(found)
                seen.update(found)
                continue
            value = _one(self.value(fact.node, env))
            if fact.kind == 'choice':
                value = fact.values[int(value)]
            elif fact.kind == 'bool':
                value = bool(value)
            elif fact.kind == 'number':
                value = float(value) / (self.registry.scale(fact.unit) if fact.unit else 1.0)
                units[name] = fact.unit
            view[name] = value
        return {
            't': float(t),
            'thing': self.flat_entity(rule, j),
            'event': self.rule_name(rule, j),
            'text': rule.label,
            'outcomes': [
                {'name': outcome.name, 'text': outcome.label, 'available': possible[k]}
                for k, outcome in enumerate(rule.outcomes)
            ],
            'view': view,
            'units': units,
            'seen': [
                {
                    key: self.entry_at(i)[name]
                    for key, name in (('t', 't'), ('event', 'event'), ('text', 'label'))
                }
                for i in sorted(seen)
            ],
            'pick': self.picked,
            'by': self.controller(rule, j),
        }

    def entry(self, rule, j, outcome, t, sets, modes, moved, before):
        """Keep one step of the trace: a trigger that waits (`outcome` None), or a firing and its
        outcome, with what it set and moved and who picked its outcome (`entry_at` writes it out)."""
        picked = None
        if outcome is not None and self.picking is not None:
            picked, self.picking = self.picking, None
        self.log.append((float(t), self.steps, rule.index, j, outcome, sets, modes, moved, before, picked))

    def entry_at(self, k):
        """The step k of the trace as a report reads it."""
        made = self.written_entries.get(k)
        if made is not None:
            return made
        plan = self.plan
        t, step, index, j, outcome, sets, modes, moved, before, picked = self.log[k]
        rule = plan.rules[index]

        def flat(name):
            space = plan.space_of(name)
            return self.rule_free_name(name, space, self.place(rule.space, j, name)) if space else name

        def placed(key):
            return self.rule_free_name(key[0], plan.space_of(key[0]), key[1])

        # A firing reads as the text of its outcome; an event that fires as it triggers also as its own.
        label = rule.label
        if outcome is not None and outcome.label is not None:
            label = outcome.label
        elif outcome is not None and rule.delay is not None:
            label = None
        basis = rule.basis if outcome is None else outcome.basis or rule.basis
        name = self.rule_name(rule, j)
        made = self.written_entries[k] = {
            't': t,
            'step': step,
            'rule': name,
            'entity': self.flat_entity(rule, j),
            'event': name if outcome is None else flat(outcome.emits[0]),
            'outcome': None if outcome is None else outcome.name,
            'label': label,
            'changes': {placed(key): value for key, value in (*sets.items(), *modes.items())},
            'before': {placed(key): value for key, value in before.items()},
            'transfers': [[placed(source), placed(target), amount] for source, target, amount in moved],
            'path': rule.path if outcome is None else outcome.path,
            'basis': _basis_ref(basis),
            'fires': [] if outcome is None else [flat(target) for target in outcome.fires],
            'semantic': label is not None,
            # Who picked the outcome in a played run, or None when the model chose it.
            'picked': picked,
        }
        return made

    # ---- the moments ----------------------------------------------------------------------------

    def state_now(self, t):
        """The value of each quantity at t, in the order of the model."""
        return np.array([float(self.column(name, t)[0]) for name in self.plan.quantities])

    def store_now(self):
        """The store of a trajectory: each state with the time at which it took its value, and for
        each event how many times it happened and when."""
        plan, found = self.plan, {}
        for name in plan.s.modes:
            found[name] = self.v[name].item(0)
            found[name + ENTERED] = float(self.v[name + ENTERED][0])
        for name in plan.s.events:
            found[name + COUNT] = int(self.v[name + COUNT][0])
            found[name + TIME] = float(self.v[name + TIME][0])
        return found

    def snapshot(self, t, step=False):
        if self.keep:
            self.snapshots.append((float(t), self.state_now(t), self.store_now()))
            if step:
                self.after_steps.append(self.snapshots[-1])

    def settle(self, t):
        plan = self.plan
        self.now = t
        self.snapshot(t)
        self.moment += 1
        self.steps = 0
        self.counts['moments'] += 1
        while self.times and self.times[0][0] <= t + self.tolerance:
            _, _, kind, what, j, version = heapq.heappop(self.times)
            if kind == BOUND:
                if self.lversion[what][j] == version:
                    raise Outside(f'{what} at a bound (t = {t:g} h)', space=plan.space_of(what))
            elif kind == FLOOR:
                if self.lversion[what][j] == version:
                    # The line reached its lower bound: it starts again there, and comes to rest.
                    self.y0[what][j], self.t0[what][j], self.rate[what][j] = (
                        plan.quantities[what].lower,
                        t,
                        0.0,
                    )
                    self.apply([], t, changed=[(what, {j})])
                    self.restart_line(what, np.array([j]), t)
                    while self.flag_changes:
                        flags, self.flag_changes = self.flag_changes, []
                        self.apply([], t, changed=flags)
            elif kind == LIMIT:
                if self.lversion[plan.blocks[what].names[0]][j] == version:
                    self.apply([], t, restart=[(what, j)])
            elif kind == END:
                if self.lversion[plan.blocks[what].names[0]][j] == version:
                    self.ends(what, j, t)
            elif self.rules[what].version[j] == version:
                if kind == ROOT:
                    self.rules[what].reached[j] = self.moment
                self.mark(what, {j})
        if self.reading == 'every':
            for index in range(len(plan.rules)):
                self.mark(index, None)
        while True:
            while self.dirty:
                batch, self.dirty = self.dirty, {}
                for index, J in batch.items():
                    rule = plan.rules[index]
                    count = plan.spaces[rule.space].count
                    places = (
                        np.arange(count) if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
                    )
                    self.read_rule(rule, places, t)
            while self.ready and not self.rules[self.ready[0][1]].ready[self.ready[0][2]]:
                heapq.heappop(self.ready)
            if self.settled:
                due = self.next_settled()
                if due is None:
                    return
                named, index, j = due
            elif not self.ready:
                return
            else:
                (_, index, j), named = heapq.heappop(self.ready), False
            rule, state = plan.rules[index], self.rules[index]
            if named:
                # An event that a line named, which waited behind the independent work of the moment.
                chain = next(chain for chain in self.continuations if chain and chain[0] == (index, j))
                self.continuations.remove(chain)
                chain.popleft()
                waiting = len(self.continuations)
                self.trigger(rule, j, t)
                if len(self.continuations) > waiting:
                    self.continuations[-1].extend(chain)
                elif chain:
                    self.continuations.insert(0, chain)
                continue
            kind = int(state.ready[j])
            state.ready[j] = 0
            if kind == FIRE:
                state.pending[j] = np.nan
                self.fire(rule, j, t)
            else:
                self.trigger(rule, j, t)
            limit = self.cfg.max_events * max(space.count for space in plan.spaces)
            if len(self.trace) > limit:
                raise SimulationError(f'The run has more than {limit} events')

    def next_settled(self):
        """The next step of a moment of a played run that settles the independent work first
        (`settled_decisions`): (whether a line named it, rule, instance), or None. A due rule is
        independent when no actor that the run controls decides its step: a firing of a rule that
        chance takes, or a trigger of such a rule or of a rule with a delay. An event that a line
        named cannot pass the first controlled event of its line; the other independent work of the
        moment goes first, and then the controlled steps in the order of the file."""
        plan = self.plan
        due, seen = [], set()
        for key, index, j in sorted(self.ready):
            if self.rules[index].ready[j] and (index, j) not in seen:
                seen.add((index, j))
                due.append((key, index, j))
        self.ready = list(due)
        independent = None
        for _, index, j in due:
            kind, controlled = int(self.rules[index].ready[j]), self.controlled(index, j)
            waits = plan.rules[index].delay is not None
            if (kind == FIRE and not controlled) or (kind == TRIGGER and (not controlled or waits)):
                independent = (False, index, j)
                break
        waiting = []
        for chain in self.continuations:
            while chain and not self.can_trigger(*chain[0]):
                chain.popleft()
            if chain:
                index, place = chain[0]
                if not self.controlled(index, place) or plan.rules[index].delay is not None:
                    return True, index, place
                rule = plan.rules[index]
                positions, copies = self.order[index]
                key = (rule.line, int(positions[place]), int(copies[place]), index)
                waiting.append((key, 0, True, index, place))
        self.continuations = [chain for chain in self.continuations if chain]
        if independent is not None:
            return independent
        if due:
            # An event that a line named and that is also due by its own condition goes as the
            # line named it, once: the named one is first of the two.
            waiting.append((due[0][0], 1, False, due[0][1], due[0][2]))
        if not waiting:
            return None
        return min(waiting)[2:]

    def run(self):
        try:
            return self.played()
        except Pause:
            self.snapshot(self.now)
            return self.result(paused=True)

    def input_failures(self):
        """The failing checks of the inputs of the run (an `assert` that reads only inputs and named
        states), for every instance of each space, with the flat name of the check of each instance:
        what `analysis.values.input_check_failures` gives of a flat structure."""
        plan, found = self.plan, []
        for check_, severity, basis in plan.input_checks:
            holds = self.holds_at_start(check_)
            for j in np.flatnonzero(~holds).tolist():
                found.append(
                    {
                        'code': 'check:' + plan.check_name(check_.name, check_.space, j),
                        'severity': 'error' if severity == 'block' else 'warning',
                        'message': check_.message,
                        'path': check_.path,
                        'evidence': basis,
                    }
                )
        return found

    def admit(self):
        """A run of a model with a table is refused when its inputs fail a blocking check for some
        row, as `Model.resolve` refuses a run of a flat model: the model of the representatives has
        that check for one row of each class only. A resolved run of a model with no table comes
        from `Model.resolve`, which made the check."""
        plan = self.plan
        if not plan.core.families:
            return
        blocked = [item for item in self.input_failures() if item['severity'] == 'error']
        if blocked:
            raise ModelError(blocked)
        if self.given:
            # The plan was proved for the values of its run and of its tables. For the values that
            # this run was given, the core makes the proofs over the rows again: a failure refuses
            # the run. A proof that gives other facts than those that the plan was made with needs
            # another plan.
            proved = plan.core.proved(plan.resolved.run, plan.resolved, self.given)
            for name, found in (proved or {}).items():
                if name.startswith('proven_') and set(found) != set(getattr(plan.resolved, name)):
                    raise ModelError(
                        [
                            {
                                'code': 'rows',
                                'severity': 'error',
                                'path': f'runs/{plan.resolved.run}',
                                'message': 'The values of the run change what the compiler proves of '
                                f'the model ({name}): the plan of the run does not hold for them',
                            }
                        ]
                    )

    def played(self):
        self.admit()
        self.start()
        t = 0.0
        self.settle(t)
        while t < self.horizon:
            while self.times and self.stale(self.times[0]):
                heapq.heappop(self.times)
            t = min(self.horizon, self.times[0][0]) if self.times else self.horizon
            if self.components:
                # A component makes its segments as far as the next time before the timeline goes
                # there: a crossing that a rule watches in it puts an earlier time on the timeline.
                for component in self.components:
                    component.at(t)
                while self.times and self.stale(self.times[0]):
                    heapq.heappop(self.times)
                t = min(self.horizon, self.times[0][0]) if self.times else self.horizon
            self.settle(t)
        return self.result()

    def stale(self, entry):
        _, _, kind, what, j, version = entry
        if kind in (BOUND, FLOOR):
            return self.lversion[what][j] != version
        if kind in (LIMIT, END):
            return self.lversion[self.plan.blocks[what].names[0]][j] != version
        return self.rules[what].version[j] != version

    def result(self, paused=False):
        """What the run gives. A run that stopped at a decision (`paused`) has its trace and its
        state up to that time, and no value of an output: an output is a value at the horizon."""
        plan, t = self.plan, self.horizon
        trace = [(at, self.rule_name(plan.rules[index], j), outcome) for at, index, j, outcome in self.trace]
        outputs, unestimated = {}, list(plan.unestimated)
        if not paused:
            self.check_all(t)
            env = Env(self, SCALARS, None, t)
            for name, node in plan.outputs.items():
                # An output is one value, so only the branch of a choice that holds is read. An
                # output that reads an output with no estimate there has no value either.
                try:
                    outputs[name] = _one(self.value(node, env))
                except Unknown:
                    unestimated.append(name)
            self.ended = True  # nothing of the run changes now: a report can keep what it reads
        return Result(
            t,
            trace,
            outputs,
            dict(self.counts),
            self.reading,
            self,
            tuple(unestimated),
            self.decision,
            paused,
            self.now if paused else t,
            tuple(self.firings),
        )
