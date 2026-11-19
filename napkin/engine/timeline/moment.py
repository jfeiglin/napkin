"""A moment: the rounds at one time (D5), and what a stage, a commit and a settling do.

At a time, rounds. One round is:

1. **Stages.** The stages that are due when the round begins commit one after the other, in the
   order in which their occurrences were made (D5). A stage's guard (`after D when C`) is read once,
   when it comes due; a stage whose guard is false runs nothing and commits no entry. Its statements
   run in order and each sees the writes before it (`Tx`): `=`, `+=` and `-=` on a writable value (of
   the receiver, through a link or an entity parameter, of an occurrence of the stage or of a live
   occurrence that `.occurrences.at(t)` names; a finished occurrence is frozen, and a write to it
   fails), `=` of a distribution on a distribution-valued value, which the draws after it read,
   of an allocation on an endpoint, by which it shares its flows from the settling on, and of a
   `formula(...)` on a formula, a request or a capacity, which reads the new calculation from the
   commit on (a number written to a request or a capacity that was a formula captures it; spec:
   "A scalar assignment captures a value. `formula(...)` explicitly installs a live calculation");
   `move`, which debits and credits two stores together or fails whole; `.start(...)`, whose
   arguments are evaluated at the caller left to right when the statement runs, on one event or on
   each member of a collection in the order of its keys; `if`/`else`; and `switch` on an enum value,
   whose case guards are read before the selector: a draw as the selector picks among the eligible
   outcomes (`chance.py`). A guard, an `if` and the guard of a case that were decided
   within tolerance of their boundary are marked in the entry of the commit (`near`, triggers.py).
   A value that misses a bound by less than its tolerance is
   put on the bound; one that misses it by more fails the run, and so does a move that does not fit.
   A commit publishes the stage's writes, traces its edits and its moves and registers the
   occurrences that it queued, in order; a failure discards the stage and stops the run. A breakpoint
   stops the run before a stage or a statement (`checkpoints.py`): the stage and those after it in its
   round are held (`held`), and `resume` runs them again from the stopped one.
2. **Settle.** The connected sets that the round touched are built again from the state there
   (`ways.py`): those that hold a store that a commit wrote, or read a value that changed (a written
   value, a collection of occurrences or of flows whose members changed, a rate or a result of a set
   built again, a keyed read at its key time), those that a flow joins or leaves, and the sets whose
   moving rates they read, which integrate with them. A store that no
   flow meets any more holds its value. So each declared solver that the round affected is solved
   once, after the stages commit, in dependency order, and its results are published together
   (`declared.py`); the sets of declared solvers first settle after the setup's commit. Then each
   delay that a stage reached and that reads a rate or a result takes its value: its other reads
   were captured when the stage reached it (`occurrences.py`).
3. **Conditions** (`triggers.py`): triggers, resets and gates are read on the settled state; then
   the firings start their events, and the released gates go on. Then each assertion over state
   must hold, and once the rounds of the time are done, just after it as well.

Another round follows at the same time while a stage is due there or a condition acted. The setup is
round zero: its statements commit as one stage, the sets start, and the triggers get their first
check; the rounds of time 0 follow. `max_rounds` limits the rounds at one time (D6).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...program import parts as p
from ...program.refs import Distribution, Formula
from ..errors import SimulationError
from .plan import FORMULA
from .reads import lazily

# The comparisons of a stage's test, exact, as functions of the difference of their sides.
_EXACT = {
    'le': lambda d: d <= 0,
    'ge': lambda d: d >= 0,
    'lt': lambda d: d < 0,
    'gt': lambda d: d > 0,
    'eq': lambda d: d == 0,
    'ne': lambda d: d != 0,
}

_SETUP = 'setup'  # what a stop in the setup holds


@dataclass(frozen=True)
class Defined:
    """A definition that a stage gives a value with `= formula(...)`: the node of the calculation
    over engine names, which what reads the value follows from the commit on."""

    node: nodes.Node


class Tx:
    """The uncommitted work of one stage: its writes (engine name -> value, in order), its moves, the
    starts that it queued and the edits made at its stops. `stage` says whether a breakpoint may stop
    it (a stage or the setup, not a firing); `origin` is the statement that runs."""

    def __init__(self, owner, stage=True):
        self.owner = owner  # the occurrence that runs the stage, '' for the setup, or a trigger's member
        self.stage = stage
        self.origin = ''
        self.writes = {}
        self.moves = []  # (source, destination, amount, origin)
        self.starts = []  # (member, event, arguments)
        self.allocations = []  # (store, side, allocation, scope, origin) of each new allocation
        # A value that the stage gives a definition -> the statement that gives it its last: a
        # formula, or a captured number in place of a request's or a capacity's formula.
        self.defined = {}
        self.near = ()  # the near-ties of its tests (`near_ties`)
        self.edits = []  # (part, owner, details) of the trace entry of each edit made in it

    def details(self):
        """The details of the trace entry of the commit: the definitions that it gives, by the
        statements that give them (`Plan.definitions_of`), and the near-ties of its tests."""
        found = {'defines': tuple(self.defined.items())} if self.defined else {}
        return found | ({'near': tuple(self.near)} if self.near else {})


class _Moving:
    """The stores that a flow meets after a settling: those of the sets that stay, and the ends of
    the flows of the sets that are built again."""

    def __init__(self, held, gone, ends):
        self.held, self.gone, self.ends = held, gone, ends

    def __contains__(self, store):
        return store in self.ends or (store in self.held and store not in self.gone)


class Moment:
    """The rounds of the moments of one run (see the module)."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan
        self.phase = 'between'  # 'stages', 'settle', 'conditions' or 'between'
        self.again = False
        self.round = 0
        # Where a breakpoint stopped the run: _SETUP, or (the stages of its round, the place of the
        # stopped one).
        self.held = None
        self._paths = {}

    # ---- rounds -----------------------------------------------------------------------------------

    def setup(self):
        """Round zero at time 0, then the rounds of time 0."""
        self._round(0)
        self.held = _SETUP
        self._setup()

    def _setup(self):
        run = self.run
        self.phase = 'stages'
        tx = Tx('')
        run.chance.made = []
        run.breaks.setup()
        self.execute(self.plan.program.setup, tx, None)  # a stop here holds the setup
        self.held, run.chance.kept = None, set()
        if tx.defined:
            # The definitions of the setup are in its trace, as those of a stage, for a reader.
            run.recorder.entry(run.now, 'commit', 'setup', '', **tx.details())
        self.commit(tx)
        self.settle()
        run.occurrences.delays()
        self.phase = 'conditions'
        run.triggers.conditions()
        run.triggers.check()
        self.rounds(0.0)

    def resume(self):
        """Go on where a breakpoint stopped the run (`checkpoints.py`): the stopped stage again, with
        the draws that it made, then the rest of its round and of its moment."""
        held = self.held
        if held is _SETUP:
            self._setup()
        else:
            self.rounds(self.run.now, held)

    def at(self, t, changed):
        """The moment at time t; `changed` holds what the ways changed there."""
        run = self.run
        run.now = t
        run.changed |= changed
        run.changed.update(run.keyed_changes(t))
        self._round(0)
        self.rounds(t)

    def _round(self, number):
        self.round = number
        self.run.recorder.round = number

    def rounds(self, t, held=None):
        """Round after round at time t while work is due there; `held` holds the stages of a round
        that a breakpoint stopped, and the place of the stopped one."""
        run = self.run
        limit = self.plan.configuration.limits.max_rounds
        while True:
            if held is None:
                self._round(self.round + 1)
                if self.round > limit:
                    raise SimulationError(self._round_limit(t, limit))
                self.again = False
                queue = run.occurrences.due(t)
                # A run can stop in the stages of a round: each solver takes its next solve on a fresh
                # instance with its basis, so that its state there is data (`saved.py`).
                run.ways.renew()
            else:
                queue, held = held[0][held[1] :], None
            self.phase = 'stages'
            for k, live in enumerate(queue):
                self.held = (queue, k)  # a stop in this stage holds it and the stages after it
                self.stage(live)
            self.held = None
            self.settle()
            run.occurrences.delays()
            self.phase = 'conditions'
            run.triggers.conditions()
            run.triggers.check()
            if not self.again and run.occurrences.next_due() != t:
                break
        self.phase = 'between'
        run.limit = run.discrete()
        run.triggers.predict_all()
        run.triggers.check(after=True)

    def _round_limit(self, t, limit):
        started = Counter(
            entry.part for entry in self.run.recorder.trace if entry.kind == 'start' and entry.t == t
        )
        events = ', '.join(f'{name} ({count} starts)' for name, count in started.items())
        return (
            f'more than {limit} rounds at t = {t:g} h: the limit max_rounds is {limit} rounds at one '
            f'time. Events started at this time: {events or "none"}.'
        )

    # ---- stages and statements ----------------------------------------------------------------------

    def stage(self, live):
        """The stage of an occurrence that is due: its guard, its statements and its commit."""
        run = self.run
        made = live.plan
        step = made.event.steps[live.step]
        tx = Tx(made.id)
        tx.origin = step.origin
        run.chance.made = []
        run.breaks.stage(made, step, live.step == 0)  # a breakpoint stops it before its guard is read
        ran = step.guard is None or self.test(step.guard, made.scope, step.origin, tx)
        if ran:
            try:
                self.execute(step.body, tx, made.scope)
            except (SimulationError, ExpressionError, ArithmeticError) as problem:
                raise SimulationError(
                    f'{problem} [stage {live.step + 1} of {made.id}, t = {run.now:g} h]'
                ) from None
            run.recorder.entry(run.now, 'commit', step.origin, made.id, **tx.details())
        run.chance.kept = set()  # a resumed stage has traced the draws that it kept
        self.commit(tx)
        run.occurrences.reach(live, live.step + 1)

    def truth(self, expression, scope, origin, tx=None):
        """The value of an expression of a scope now, through a stage's own writes."""
        return self.run.truth(self.run.occurrences.node(expression, scope, origin), tx)

    def test(self, expression, scope, origin, tx):
        """The answer of a test of a stage (a guard, an `if`, the guard of a case), with its near-ties
        added to the stage's (`near_ties`). They are found from the values that the answer
        read, so no draw is made again; a boolean formula's comparisons are read through it."""
        run = self.run
        node = run.occurrences.node(expression, scope, origin)
        seen = {}

        def read(name):
            seen[name] = found = run.value(name, tx=tx)
            return found

        answer = bool(lazily(node, read, self.plan.units, run.now))

        def side(part):
            return lazily(
                part,
                lambda name: seen[name] if name in seen else run.value(name, tx=tx),
                self.plan.units,
                run.now,
            )

        try:
            near = near_ties(
                node,
                origin,
                self.plan,
                run.frozen,
                side,
                lambda op, difference, left, right: _EXACT[op](difference),
                run.triggers.tolerance,
            )
        except (ExpressionError, ArithmeticError, LookupError):
            near = ()  # a side that the answer did not read
        tx.near = (*tx.near, *near)
        return answer

    def execute(self, statements, tx, scope):
        """Run statements in order (see the module); a breakpoint at one stops before it."""
        breaks = self.run.breaks
        for statement in statements:
            tx.origin = statement.origin
            if breaks.statements:
                breaks.statement(statement, tx)
            if isinstance(statement, p.Assign):
                self.assign(statement, tx, scope)
            elif isinstance(statement, p.Move):
                self.move(statement, tx, scope)
            elif isinstance(statement, p.Start):
                self.queue(statement, tx, scope)
            elif isinstance(statement, p.If):
                test = self.test(statement.test, scope, statement.origin, tx)
                self.execute(statement.then if test else statement.orelse, tx, scope)
            elif isinstance(statement, p.Switch):
                self.execute(self.select(statement, tx, scope), tx, scope)
            else:
                raise SimulationError(f'{statement!r} is no statement')

    def resolved(self, path, scope, origin):
        """What a path of a scope names, found once."""
        plan = self.plan
        key = (id(path), plan.owner_of(scope))
        found = self._paths.get(key)
        if found is None:
            size = plan.size()
            found = self._paths[key] = (plan.resolve(path, scope, origin), path)
            if plan.size() != size:
                plan.log.append(('resolve', path, key[1], origin))  # it named values (`saved.py`)
        return found[0]

    def target(self, path, scope, origin):
        """The engine name of a value that a statement writes: a value of a scope, or a value of the
        newest occurrence of an event, which must be live."""
        run, plan = self.run, self.plan
        point = self.resolved(path, scope, origin)
        if point[0] != 'value':
            raise SimulationError(f'{origin}: the target of an assignment is no value')
        name = point[1]
        dynamic = plan.dynamic.get(name)
        if dynamic is not None:
            members = plan.members(dynamic.source)
            if dynamic.op != 'at' or not members:
                raise SimulationError(f'{origin}: {dynamic.spelled} names no occurrence at t = {run.now:g} h')
            occurrence = members[-1][1]
            name = plan.project(members[-1], dynamic.steps, origin)
            if not run.occurrences.live[occurrence].active:
                raise SimulationError(
                    f'{origin}: {name} belongs to the finished occurrence {occurrence}, which is frozen'
                )
        return name

    def checked(self, name, value, origin):
        """A value that a write gives a value with bounds: on its bound when it misses it by less
        than its tolerance, a failure when it misses it by more."""
        bounds = self.run.bounds.get(name)
        if bounds is None or isinstance(value, bool) or not isinstance(value, int | float):
            return value
        value = float(value)
        if not math.isfinite(value):
            raise SimulationError(f'{origin}: {name} would take the value {value!r}')
        lower, upper = bounds
        slack = self.run.recorder.tolerance.get(name, 0.0)
        if lower - slack <= value < lower:
            return float(lower)
        if upper < value <= upper + slack:
            return float(upper)
        if not lower <= value <= upper:
            raise SimulationError(
                f'{name} = {value:g} is outside its range [{lower:g}, {upper:g}] at t = {self.run.now:g} h'
            )
        return value

    def assign(self, statement, tx, scope):
        """`=`, `+=` or `-=`."""
        run = self.run
        if isinstance(statement.value, p.Priority | p.Proportional):
            point = self.resolved(statement.target, scope, statement.origin)
            if point[0] != 'allocation':
                raise SimulationError(f'{statement.origin}: an allocation is the allocation of an endpoint')
            tx.allocations.append((point[1], point[2], statement.value, scope, statement.origin))
            return
        name = self.target(statement.target, scope, statement.origin)
        if isinstance(statement.value, Distribution):
            # A new distribution for the draws to come; what was drawn stays as it is.
            tx.writes[name] = statement.value
            return
        if isinstance(statement.value, Formula):
            # A new calculation: what reads the value follows it from the commit on.
            node = run.occurrences.node(statement.value.expr, scope, statement.origin)
            tx.writes[name] = Defined(node)
            tx.defined[name] = statement.origin
            return
        value = self.truth(statement.value, scope, statement.origin, tx)
        if statement.op != '=':
            current = run.value(name, tx=tx)
            value = current + value if statement.op == '+=' else current - value
        tx.writes[name] = self.checked(name, value, statement.origin)
        found = self.plan.values.get(name)  # none for a distribution-valued value
        if name in tx.defined or (found is not None and found.kind == FORMULA):
            # A request or a capacity that was a formula now holds the number (spec: "A scalar
            # assignment captures a value").
            tx.defined[name] = statement.origin

    def move(self, statement, tx, scope):
        """`move amount from source to destination`: both inventories are checked before anything
        changes, and a move that would leave less than the tolerance of its source moves all."""
        run, origin = self.run, statement.origin
        amount = self.truth(statement.amount, scope, origin, tx)
        if (
            isinstance(amount, bool)
            or not isinstance(amount, int | float)
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise SimulationError(f'{origin}: a move takes a finite amount from 0, not {amount!r}')
        amount = float(amount)
        source = self.target(statement.source, scope, origin)
        destination = self.target(statement.destination, scope, origin)
        had = float(run.value(source, tx=tx))
        lower = run.bounds.get(source, (-math.inf, math.inf))[0]
        left = had - amount
        atol = run.recorder.tolerance.get(source, 0.0)
        if math.isfinite(lower) and left != lower and abs(left - lower) <= atol:
            amount += left - lower
            if amount >= 0:
                left = float(lower)
            else:
                amount, left = 0.0, had
        after = {source: left, destination: float(run.value(destination, tx=tx)) + amount}
        for name, value in after.items():
            low, high = run.bounds.get(name, (-math.inf, math.inf))
            slack = run.recorder.tolerance.get(name, 0.0)
            if not low - slack <= value <= high + slack:
                raise SimulationError(
                    f'{origin}: the move of {amount:g} from {source} to {destination} fails: {name} would '
                    f'hold {value:g}, outside its range [{low:g}, {high:g}]; nothing is moved'
                )
            after[name] = min(max(value, low), high)
        tx.writes.update(after)
        tx.moves.append((source, destination, amount, origin))

    def queue(self, statement, tx, scope):
        """`.start(...)`: the arguments are evaluated at the caller, left to right, once; on a
        collection the members start in the order of its keys, and of equal keys in their order of
        creation."""
        run = self.run
        point = self.resolved(statement.event, scope, statement.origin)
        args = tuple(self.truth(arg, scope, statement.origin, tx) for arg in statement.args)
        args = tuple(
            float(arg) if isinstance(arg, int) and not isinstance(arg, bool) else arg for arg in args
        )
        if point[0] == 'event':
            tx.starts.append((point[1], point[2], args))
            return
        if point[0] != 'many' or any(each[0] != 'event' for each in point[1].points):
            raise SimulationError(f'{statement.origin}: a start of what is no event')
        entries = point[1]
        kept = run.kept_entries(entries)
        order = sorted(
            kept,
            key=lambda k: (
                float(run.value(entries.keys[k])) if isinstance(entries.keys[k], str) else entries.keys[k],
                k,
            ),
        )
        for k in order:
            tx.starts.append((entries.points[k][1], entries.points[k][2], args))

    def select(self, statement, tx, scope):
        """The body that a `switch` runs: the guards are read once, before the selector; the case of
        the selector's value runs if it is eligible, else the `else` body. A draw as the selector picks
        among the eligible outcomes (D1, `chance.py`): those that no false guard bars.
        With none eligible, the `else` body runs and nothing is drawn."""
        run, plan = self.run, self.plan
        eligible = [
            case.guard is None or self.test(case.guard, scope, case.origin, tx) for case in statement.cases
        ]
        tx.origin = statement.origin
        node = run.occurrences.node(statement.selector, scope, statement.origin)
        producer = node.name if isinstance(node, nodes.Ref) else None
        if producer in plan.draws:
            barred = {case.member for case, ok in zip(statement.cases, eligible) if not ok}
            allowed = [member for member in run.chance.outcomes(producer) if member not in barred]
            if not allowed:
                return statement.orelse
            chosen = run.chance.draw(producer, allowed)
        else:
            chosen = run.truth(node, tx)
        for case, ok in zip(statement.cases, eligible):
            if ok and case.member == chosen:
                return case.body
        return statement.orelse

    def commit(self, tx):
        """Publish the writes of a stage and register the occurrences that it queued."""
        run = self.run
        for part, owner, details in tx.edits:  # an edit at a stop in the stage (`checkpoints.py`)
            run.recorder.entry(run.now, 'edit', part, owner, **details)
            run.breaks.transferred(details)
            run.occurrences.met(details['target'])
        for source, destination, amount, origin in tx.moves:
            run.recorder.entry(
                run.now, 'move', origin, tx.owner, amount=amount, source=source, destination=destination
            )
            for end in (source, destination):
                run.occurrences.met(end)
        for store, side, allocation, scope, origin in tx.allocations:
            # The endpoint shares its flows by its new rule once its set settles again.
            self.plan.allocate(store, side, allocation, scope, origin)
            self.plan.log.append(('allocate', store, side, origin, self.plan.owner_of(scope)))
            run.changed.add(store)
        for name, value in tx.writes.items():
            run.write(name, value)
        for member, event, args in tx.starts:
            run.occurrences.register(member, event, args)

    # ---- the settling -----------------------------------------------------------------------------

    def settle(self):
        """Build again the sets that the round touched (see the module)."""
        run, ways, plan, t = self.run, self.run.ways, self.plan, self.run.now
        self.phase = 'settle'
        joined, left = list(run.joined), set(run.left)
        names = run.changed_names()
        touched = ways.touched_by(names | set(run.written))
        ends = set()
        for flow in [*joined, *left]:
            for connection in plan.flows[flow].connections:
                ends |= {end for end in (connection.source, connection.sink) if end is not None}
        touched |= {ways.set_of[end] for end in ends if end in ways.set_of}
        touched |= {ways.set_of[flow] for flow in left if flow in ways.set_of}
        waiting, run.waiting = run.waiting, []
        if not touched and not joined and not waiting:
            run.settled()
            return
        moving_before = set(ways.set_of)
        while True:
            # The sets in the order of their ids, so that the region is the same whatever the order in
            # which a set of ids was made (a restored run makes its sets of ids afresh, `saved.py`).
            region = [f for key in sorted(touched) for f in ways.sets[key][0].flows if f not in left]
            region += [f for f in joined if f not in left and f not in region]
            region += [
                f for connected in waiting for f in connected.flows if f not in left and f not in region
            ]
            solvers = {ways.sets[key][0].solver for key in touched} | {c.solver for c in waiting}
            solvers.discard(None)
            region_ends = set()
            for flow in region:
                for connection in plan.flows[flow].connections:
                    region_ends |= {end for end in (connection.source, connection.sink) if end is not None}
            gone = {store for key in touched for store in ways.sets[key][0].stores}
            moving = _Moving(ways.set_of, gone, region_ends)
            made = plan.connect(region, moving, sorted(solvers))
            extra = set()
            for connected in made:
                for store in connected.stores:
                    key = ways.set_of.get(store)
                    if key is not None and key not in touched:
                        extra.add(key)
            status = {store for store in region_ends if store not in moving_before}
            status |= {store for store in gone if store not in region_ends}
            extra |= ways.touched_by(status) - touched
            extra |= ways.readers_of_rates(touched) - touched
            # A set whose settings read a moving rate of a set that stays integrates with it: both
            # are built again, as one instance (`ways.build`).
            extra |= ways.moving_sources(made) - touched
            if not extra:
                break
            touched |= extra
        values = ways.retire(touched, t)
        values.update(run.written)
        for connected in made:
            for store in connected.stores:
                if store not in values:
                    values[store] = float(run.value(store))
                if store not in plan.moving:
                    plan.moving.add(store)
                    plan.log.append(('moving', store))
        stay = {store for connected in made for store in connected.stores}
        for store, value in values.items():
            if store not in stay:
                run.hold(store, value)
        for flow in left:
            run.flow_left(flow)
        for flow in region:
            if flow in joined:
                run.tolerate(plan.flows[flow])
        run.settled()
        ways.build(made, values, t)


def near_ties(node, origin, plan, frozen, side, holds, tolerance, later=None):
    """The near-ties of a condition (see the module): (origin, comparison, difference, tolerance) of
    each numeric comparison on the path of its answer, through boolean formulas, whose sides differ by
    no more than `tolerance(left, right)`, and with `later`, still do an instant later. `side(node)` is
    the value of a side and `holds(op, difference, left, right)` the answer of a comparison, as the
    reader of the condition gives them; `and` and `or` stop at the term that decides, a conditional
    takes its selected side."""
    found = []

    def truth(part):
        if isinstance(part, nodes.Ref):
            value = plan.values.get(part.name)
            if value is not None and value.kind == FORMULA and value.boolean and part.name not in frozen:
                return truth(value.node)
            return bool(side(part))
        if isinstance(part, nodes.BoolOp):
            results = (truth(each) for each in part.values)
            return all(results) if part.op == 'and' else any(results)
        if isinstance(part, nodes.Unary) and part.op == 'not':
            return not truth(part.operand)
        if isinstance(part, nodes.IfElse):
            return truth(part.body if truth(part.test) else part.orelse)
        if isinstance(part, nodes.Compare):
            return walk(part, keep=False)
        return bool(side(part))

    def walk(part, keep=True):
        if isinstance(part, nodes.Ref):
            value = plan.values.get(part.name)
            if value is not None and value.kind == FORMULA and value.boolean and part.name not in frozen:
                walk(value.node, keep)
            return None
        if isinstance(part, nodes.BoolOp):
            for each in part.values:
                walk(each, keep)
                if truth(each) == (part.op == 'or'):
                    break
            return None
        if isinstance(part, nodes.Unary) and part.op == 'not':
            return walk(part.operand, keep)
        if isinstance(part, nodes.IfElse):
            walk(part.test, keep)
            return walk(part.body if truth(part.test) else part.orelse, keep)
        if not isinstance(part, nodes.Compare):
            return None
        for left, op, right in zip(part.operands, part.ops, part.operands[1:], strict=False):
            a, b = side(left), side(right)
            if isinstance(a, bool | str) or isinstance(b, bool | str):
                if not ((a == b) if op == 'eq' else (a != b)):
                    return False
                continue
            difference = float(a) - float(b)
            band = tolerance(left, right)
            if (
                keep
                and band > 0
                and abs(difference) <= band
                and (later is None or abs(later(left, right)) <= band)
            ):
                found.append((origin, nodes.text(part), difference, band))
            if not holds(op, difference, left, right):
                return False
        return True

    walk(node)
    return tuple(dict.fromkeys(found))
