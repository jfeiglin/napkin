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

import heapq

import numpy as np

from ...model.ir import EVENT_TIME_TOLERANCE_H
from .. import solvers
from ..continuous.system import solver_step, step_cap
from ..errors import SimulationError
from .checks import Checks
from .choices import Choices, Pause
from .component import Component
from .lists import Lists
from .plan import SCALARS, Outside
from .readers import Readers
from .rules import Rules, RuleState
from .segments import Segments, Solution
from .sharing import Sharing
from .state import BOUND, END, FIRE, FLOOR, LIMIT, ROOT, Env, State, _spread
from .state import Past as Past  # timeline/reports.py imports it from here
from .state import Unknown as Unknown  # timeline/reports.py imports it from here
from .state import _one as _one  # timeline/reports.py imports it from here
from .steps import Steps
from .steps import shares as shares  # tests/engine/test_timeline_outcomes.py imports it from here
from .trace import Result as Result  # timeline/__init__.py imports it from here
from .trace import Trace


class Run(State, Lists, Sharing, Segments, Readers, Checks, Rules, Steps, Choices, Trace):
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

    def run(self):
        try:
            return self.played()
        except Pause:
            self.snapshot(self.now)
            return self.result(paused=True)

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
