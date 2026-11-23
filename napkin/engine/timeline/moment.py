"""A moment: the rounds at one time (D5), and what a stage, a commit and a settling do.

At a time, rounds. One round is:

1. **Stages.** The stages that are due when the round begins commit one after the other, in the
   order in which their occurrences were made (D5); what is due is the clock's rule (`Clock`, below),
   so 0.1 h then 0.2 h is the moment of 0.3 h, the horizon's too. A stage's guard (`after D when C`) is read once,
   when it comes due; a stage whose guard is false runs nothing and commits no entry. Its statements
   run in order and each sees the writes before it (`Tx`): `=`, `+=` and `-=` on a writable value (of
   the receiver, through a link or an entity parameter, of the occurrence of the stage or of another
   that a saved reference, a copy of one or `.occurrences.at(t)` names; a finished occurrence is
   frozen, and an assignment to it fails the run, as a `move` of an amount into or out of its store
   does, where a move of nothing goes on: `Occurrences.writable`),
   `=` of a distribution on a distribution-valued value, which the draws after it read,
   of an allocation on an endpoint, by which it shares its flows from the settling on, and of a
   `formula(...)` on a formula, a request or a capacity, which reads the new calculation from the
   commit on (a number written to a request or a capacity that was a formula captures it; spec:
   "A scalar assignment captures a value. `formula(...)` explicitly installs a live calculation");
   `move`, which debits and credits two stores together or fails whole (one store at both ends
   keeps its inventory: the debit and the credit cancel); `.start(...)`, whose
   arguments are evaluated at the caller left to right when the statement runs, on one event or on
   each member of a collection in the order of its keys; `if`/`else`; and `switch` on an enum value,
   whose case guards are read before the selector: a draw as the selector picks among the eligible
   outcomes (`chance.py`). A guard, an `if` and the guard of a case that were decided
   within tolerance of their boundary are marked in the entry of the commit (`near`, triggers.py);
   a stage whose guard was false so commits nothing, and has an entry `skip` for its near-ties.
   A value that misses a bound by less than its tolerance is
   put on the bound; one that misses it by more fails the run, and so does a move that does not fit.
   A rate or a result reads the last sharing at this time. Changes of the round, including a
   store meeting its bound, a switch and a keyed step, reach the rates at the settling. The setup
   cannot read them because no sharing has taken place (docs/design/decisions.md, change 27).
   A commit publishes the stage's writes, traces its edits and its moves and registers the
   occurrences that it queued, in order; a failure discards the stage and stops the run, also a
   failure in the commit itself (a start that a limit, its arguments or its entry refuse): the
   record holds nothing of the stage, neither its writes nor its earlier starts (`_Savepoint`). A
   breakpoint stops the run before a stage or a statement (`checkpoints.py`): the stage and those
   after it in its round are held (`held`), and `resume` runs them again from the stopped one.
2. **Settle.** The connected sets that the round touched are built again from the state there
   (`ways.py`): those that hold a store that a commit wrote, whose endpoint's allocation changed or
   that the ways changed at this moment, or read a value that changed (a written
   value, a collection of occurrences or of flows whose members changed, a rate or a result of a set
   built again, a keyed read at its key time), those that a flow joins or leaves, and the sets whose
   moving rates they read, which integrate with them. A store that no
   flow meets any more holds its value. So each declared solver that the round affected is solved
   once, after the stages commit, in dependency order, and its results are published together
   (`declared.py`); the sets of declared solvers first settle after the setup's commit. A settling
   has no entry in the trace, but where it split who is served within tolerance (`split_ties`): an
   endpoint that serves its flows by priority, whose limit (its capacity, or what reaches its store
   at a bound) is within the tolerance of what it reads of the claims of the classes ahead of a
   class that claims more, has an entry `settle` with the detail `near`. The sets that it built are
   checked, and in round zero every set, which starts then. A split that a way makes between
   moments, where a store meets a bound inside its instance, is not marked. A flow present at a
   store of a finished occurrence must carry no rate there (`Occurrences.carried`). Then each
   delay that a stage reached and that reads a rate or a result takes its value: its other reads
   were captured when the stage reached it (`occurrences.py`).
3. **Conditions** (`triggers.py`): triggers, resets and gates are read on the settled state, and
   each assertion over state must hold there; then the firings start their events, and the released
   gates go on: the consequences of a further round, which settles them (spec: "New consequences
   due at the same timestamp start a further round"). Each firing reads the rates of this settling,
   including after an earlier firing started another occurrence. Once the rounds of the time are
   done, each assertion must hold just after it as well.

Another round follows at the same time while a stage is due there or a condition acted. The setup is
round zero: its statements commit as one stage, the sets start, and the triggers get their first
check; the rounds of time 0 follow. `max_rounds` limits the rounds at one time (D6).

**The clock** (re-audit 04) is the one rule for when something is due, and every path calls it: the
delay of a stage (`after D`, `occurrences.py`), the rearming of a trigger (`reset after D`), a
comparison of the time with what holds (`t >= T`, `since(e) >= D` and `elapsed(x) >= D`, in a
trigger, a reset or a gate: `triggers.py`), a contact that joins a known moment and the horizon
(`run.py`). Two parts:

- **A time built from a duration is exact.** The duration's expression is evaluated in exact
  arithmetic: each number as the decimal that it prints as (the oracle's reading of a number), each
  unit at the exact scale of the program; the sum with the time is exact and rounded once (`later`).
  So a schedule reached by any sum of durations is the very float of the schedule written directly:
  0.1 h three times from 0 h is 0.3 h, 0.1 day is 2.4 h, and the record and every reader see that
  time. The time of a moment is a float; it is read again as its decimal, so a chain of decimal
  durations never drifts, and no state but floats is kept (a checkpoint saves the same).
- **What is due is fixed when a moment begins**: a time at most the time tolerance
  (`Numerics.crossing`) after the moment's time is due at it (`due`). The first round of a moment
  takes its stages and rearms its triggers by that rule; a later round takes what the moment itself
  scheduled with no delay, so a delay above zero reached in a moment is due at a later moment; and
  the horizon is due at the first moment within the tolerance before it. So a time that carries the
  roundoff of a value computed elsewhere (a parameter computed from a product, a solver's result) is
  the moment that it is within the tolerance of, as a comparison of the time is read within it.

Exact arithmetic alone could not place such a time, and a tolerance alone would leave a time reached
by a sum one roundoff from the one written: a reader at 0.3 h would miss a commit at
0.30000000000000004 h, and a long chain of resets would drift by its roundoff. Each part does what
the other cannot.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from ...core import expr as nodes
from ...core.comparisons import against, recorded_number
from ...core.errors import ExpressionError
from ...core.units import finite_number, rational
from ...expressions import UnitSystem
from ...program import parts as p
from ...program.refs import Distribution, Formula, Lookup, spelled
from ..continuous.walk import walked
from ..errors import SimulationError
from .collections import kept, member_at
from .plan import BACKWARD, FORMULA, FORWARD
from .reads import lazily

_SETUP = 'setup'  # what a stop in the setup holds


def in_unit(units, number, unit):
    """A number of a unit as a message writes it: `5000 mL`, `3 day`; a number with no unit, or one
    that is not finite, as it is (`inf`)."""
    if isinstance(number, Fraction):
        value = number / units.exact_scale(unit) if unit else number
        shown = str(value)
        if value.denominator != 1 and finite_number(value) and rational(float(value)) == value:
            shown = str(float(value))
        return f'{shown} {unit}' if unit else shown
    if isinstance(number, bool) or not isinstance(number, int | float):
        return repr(number)
    if not unit or not math.isfinite(number):
        return f'{number:g}'
    return f'{number / units.scale(unit):g} {unit}'


def quantity(plan, name, number):
    """A number of the value `name` as every message of a run writes it (spec.md:660: the amount and
    its unit): in the value's declared unit, with the unit's name, never in canonical units."""
    found = plan.values.get(name)
    return in_unit(plan.units, number, found.unit if found is not None else '')


def span(plan, name, low, high):
    """The range of the value `name` as a message writes it: `[0 mL, 4000 mL]`."""
    return f'[{quantity(plan, name, low)}, {quantity(plan, name, high)}]'


class _ExactUnits(UnitSystem):
    """The units of a program, with each quantity converted in exact arithmetic and not rounded: the
    decimal that writes its number (`core.units.rational`) times the exact scale of its unit."""

    def normalize(self, value, name):
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float | Fraction)
            or not math.isfinite(value)
        ):
            raise ExpressionError(f'Expected a finite quantity in {name}')
        return rational(value) * self.exact_scale(name)


class Clock:
    """The one rule for when something is due (see the module)."""

    def __init__(self, plan):
        self.separate = None  # a stock contact that must precede a nearby timed stage
        self.crossing = plan.numerics.crossing
        self.units = _ExactUnits(
            {
                unit.name: {'dimensions': dict(unit.dimension), 'scale': unit.scale}
                for unit in plan.program.units
            }
        )
        self.units.comparisons = plan.units.comparisons

    @staticmethod
    def exact(x):
        """A time or a duration as an exact number: the decimal that writes it (`core.units.rational`,
        the oracle's reading of a number)."""
        return rational(x)

    def value(self, node, read, t):
        """The value of an expression at time t in exact arithmetic (see the module): of a duration,
        or of a side of a comparison of the time. A fraction, or a float where it computes what no
        fraction holds (a square root); `read(name)` gives the value of an engine name as the engine
        holds it."""

        def exact(name):
            if name == 't':
                return rational(t)
            found = read(name)
            return (
                rational(found) if isinstance(found, int | float) and not isinstance(found, bool) else found
            )

        return lazily(node, exact, self.units)

    def later(self, t, duration):
        """The time `duration` after t: their exact sum, rounded once."""
        return float(rational(t) + rational(duration))

    def due(self, at, t, opening=True):
        """Whether a time is due at the moment of time t: at most the time tolerance after it when the
        moment begins (`opening`), else at t."""
        return at <= self.apart(t) if opening and self.separate != t else at <= t

    def within(self, at, t):
        """Whether a located contact is in the closed time window around the independent moment t."""
        return t - self.crossing <= at <= self.apart(t)

    def apart(self, t):
        """The first time that the engine tells apart from t."""
        return t + self.crossing


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
        self.balances = {}  # exact physical balances written by this stage
        self.starts = []  # (member, event, arguments, argument evidence)
        self.captures = {}  # actual reads of earlier captures of this firing
        self.argument_writes = {}  # parameters assigned by this stage, including equal-value writes
        self.allocations = []  # concrete (store, side, priority items), None for proportional()
        # A value that the stage gives a definition -> the statement that gives it its last: a
        # formula, or a captured number in place of a request's or a capacity's formula.
        self.defined = {}
        self.units = None  # comparison bindings for the current definitions in this stage
        self.near = ()  # the near-ties of its tests (`near_ties`)
        self.edits = []  # (part, owner, details) of the trace entry of each edit made in it
        self.mark = None  # the length of the trace when its statements are done (`execute`)

    def details(self):
        """The details of the trace entry of the commit: the definitions that it gives, by the
        statements that give them (`Plan.definitions_of`), and the near-ties of its tests."""
        found = {'defines': tuple(self.defined.items())} if self.defined else {}
        if self.argument_writes:
            found['argument_writes'] = tuple(self.argument_writes)
        return found | ({'near': tuple(self.near)} if self.near else {})

    def define(self, name, origin):
        self.defined[name] = origin
        self.units = None


class _Savepoint:
    """What a commit changes of the record of its run, taken before it publishes anything, so that a
    failure in the commit discards the whole stage (spec: "If the stage fails, its writes and queued
    starts are discarded"). A failure ends the run, so what is taken back is what its record reads:
    the trace from the end of the stage's statements (its commit or firing entry, its edits, moves
    and starts, the draws of its children's entries), the pieces and the times of change of what it
    writes, the definitions that it gives, and the transfers of its edits. The children that it
    started stay in the plan, and the record holds only the occurrences that its trace starts
    (`Recorder.record`)."""

    def __init__(self, run, tx):
        recorder, plan = run.recorder, run.plan
        self.run = run
        self.trace = len(recorder.trace) if tx.mark is None else tx.mark
        names = set(tx.writes)
        for name in tx.writes:
            names.update(plan.described_of.get(name, ()))
        self.stock_edits = [
            (mapping, {name: mapping[name] for name in tx.writes if name in mapping})
            for mapping in (run.stock_state.balances, run.env, run.written)
        ]
        self.names = tuple(tx.writes)
        self.log = len(plan.log)
        self.rankings = {
            (store, side): plan.rankings.get((store, side)) for store, side, *_ in tx.allocations
        }
        self.pieces = {name: _length(recorder.pieces, name) for name in names}
        self.changes = {name: _length(run.changes, name) for name in tx.writes}
        self.defined = {
            name: (_length(plan.defined, name), plan.values[name])
            for name in tx.writes
            if name in plan.values
        }
        stores = {details['target'] for _, _, details, _ in tx.edits}
        self.transfers = {
            store: None if store not in recorder.transfers else len(recorder.transfers[store][1])
            for store in stores
        }

    def discard(self):
        """Take back what the commit changed of the record."""
        run, recorder, plan = self.run, self.run.recorder, self.run.plan
        for mapping, previous in self.stock_edits:
            for name in self.names:
                mapping.pop(name, None)
            mapping.update(previous)
        del recorder.trace[self.trace :]
        del plan.log[self.log :]
        for end, before in self.rankings.items():
            if before is None:
                plan.rankings.pop(end, None)
            else:
                plan.rankings[end] = before
        _cut(recorder.pieces, self.pieces)
        _cut(run.changes, self.changes)
        for store, count in self.transfers.items():
            if count is None:
                recorder.transfers.pop(store, None)
            else:
                del recorder.transfers[store][1][count:]
        for name, (count, value) in self.defined.items():
            found = plan.defined.get(name)
            if found is None or len(found) <= (count or 0):
                continue  # the commit gave it no definition
            # The value takes back its definition, so that what reads it is found again (`Plan.define`).
            plan.define(name, value.node if value.kind == FORMULA else None, run.now, found[0][0])
            if count is None:
                del plan.defined[name]
            else:
                del found[count:]
            plan.values[name] = value


def _length(lists, name):
    """The length of a list of a mapping of lists, or None when the mapping has none."""
    found = lists.get(name)
    return None if found is None else len(found)


def _cut(lists, lengths):
    """Each list of a mapping back to its length (`_length`); a list that was not there goes."""
    for name, count in lengths.items():
        if count is None:
            lists.pop(name, None)
        elif name in lists:
            del lists[name][count:]


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
        self.splits(None)  # every set has just started
        run.recorder.check_budget(0.0)
        run.occurrences.delays()
        self.phase = 'conditions'
        run.triggers.conditions()
        self.rounds(0.0)

    def resume(self):
        """Go on where a breakpoint stopped the run (`checkpoints.py`): the stopped stage again, with
        the draws that it made, then the rest of its round and of its moment."""
        held = self.held
        if held == _SETUP:  # by value: a checkpoint's saved state holds the stop as data (`saved.py`)
            self._setup()
        else:
            self.rounds(self.run.now, held)

    def at(self, t, changed, met, switched):
        """Run the moment at t. Rebuild what changed in the ways, including the stores that met
        a bound, the flows whose rates switched and the keyed reads that step there."""
        run = self.run
        run.now = t
        run.moved.update(changed)
        run.moved.update(met)
        run.moved.update(switched)
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
                if self.round == 1:
                    for at, name, kind in run.contacts:
                        comparison = f'{kind} of {name} and the moment at {t:g} h'
                        value = self.plan.values.get(name)
                        owner = (
                            value.key.owner if value is not None and value.key else name.rpartition('.')[0]
                        )
                        run.recorder.entry(
                            t,
                            'contact',
                            name,
                            owner,
                            located=at,
                            near=((name, comparison, at - t, run.clock.crossing),),
                        )
                if self.round > limit:
                    raise SimulationError(self._round_limit(t, limit))
                self.again = False
                # What is due is fixed when the moment begins: its first round opens it (`Clock`).
                queue = run.occurrences.due(t, self.round == 1)
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
            self.splits(self.settle())
            run.recorder.check_budget(t)
            run.occurrences.delays()
            self.phase = 'conditions'
            run.triggers.conditions()
            run.recorder.check_budget(t)
            due = run.occurrences.next_due()
            if not self.again and (due is None or not run.clock.due(due, t, opening=False)):
                break
        self.phase = 'between'
        run.limit = run.clock.apart(run.discrete())
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
        elif tx.near:
            # A guard that was false within tolerance of its boundary: the stage that ran nothing has
            # an entry for its near-ties alone.
            run.recorder.entry(run.now, 'skip', step.origin, made.id, near=tuple(tx.near))
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

        units = run.units_for(tx)
        answer = bool(lazily(node, read, units, run.now))

        def side(part):
            return lazily(
                part,
                lambda name: seen[name] if name in seen else run.value(name, tx=tx),
                units,
                run.now,
            )

        try:
            near = near_ties(
                node,
                origin,
                self.plan,
                run.frozen,
                side,
                comparisons=units.comparisons,
                definition=lambda name: run.definition(name, tx),
            )
        except (ExpressionError, ArithmeticError, LookupError):
            near = ()  # a side that the answer did not read
        tx.near = (*tx.near, *near)
        return answer

    def execute(self, statements, tx, scope):
        """Run statements in order (see the module); a breakpoint at one stops before it. Once they are
        done, `tx.mark` holds the length of the trace: what a failed commit takes back starts there."""
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
        tx.mark = len(self.run.recorder.trace)

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

    def statement_point(self, path, scope, origin, tx):
        """Resolve a dynamic target using the state at this statement, including prior writes."""
        if isinstance(path.start, Lookup):
            source = self.resolved(path.start.source, scope, origin)
            if source[0] == 'dynamic' and not source[2]:
                key = self.run.occurrences.node(path.start.key, scope, origin)

                def read(name):
                    return self.run.value(name, tx=tx)

                try:
                    point = member_at(
                        self.plan.members(source[1]),
                        source[1],
                        key,
                        read,
                        self.run.units_for(tx),
                        self.run.now,
                        spelled(path),
                        self.plan,
                        *source[3:],
                    )
                except ExpressionError as problem:
                    raise SimulationError(f'{origin}: {problem}') from problem
                for step in path.steps:
                    point = self.plan._step(point, step, origin)
                return point
        return self.resolved(path, scope, origin)

    def target(self, path, scope, origin, tx):
        point = self.statement_point(path, scope, origin, tx)
        if point[0] != 'value':
            raise SimulationError(f'{origin}: the target of an assignment is no value')
        return point[1]

    def checked(self, name, value, origin):
        """A value that a write gives a value with bounds: on its bound when it misses it by less
        than its tolerance, a failure when it misses it by more."""
        exact = isinstance(value, Fraction)
        bounds = self.run.stock_state.bounds(name) if exact else self.run.bounds.get(name)
        if bounds is None or isinstance(value, bool) or not isinstance(value, int | float | Fraction):
            return value
        if not finite_number(value):
            raise SimulationError(f'{origin}: {name} would take the value {value!r}')
        if not exact:
            value = float(value)
        lower, upper = bounds
        if lower <= value <= upper:
            return value
        nearest = lower if value < lower else upper
        slack = self.run.amount_tolerance(name, float(value))
        if abs(value - nearest) <= (rational(slack) if exact else slack):
            return nearest
        plan = self.plan
        raise SimulationError(
            f'{name} = {quantity(plan, name, value)} is outside its range '
            f'{span(plan, name, lower, upper)} at t = {self.run.now:g} h'
        )

    def assign(self, statement, tx, scope):
        """`=`, `+=` or `-=`."""
        run = self.run
        if isinstance(statement.value, p.Priority | p.Proportional):
            point = self.statement_point(statement.target, scope, statement.origin, tx)
            if point[0] != 'allocation':
                raise SimulationError(f'{statement.origin}: an allocation is the allocation of an endpoint')
            run.occurrences.writable(point[1], statement.origin)
            ranking = None
            if isinstance(statement.value, p.Priority):
                items = (
                    (item, self.statement_point(item, scope, statement.origin, tx))
                    for item in statement.value.items
                )
                ranking = self.plan.priority(point[1], point[2], items, statement.origin)
            tx.allocations.append((point[1], point[2], ranking))
            return
        name = self.target(statement.target, scope, statement.origin, tx)
        run.occurrences.writable(name, statement.origin)  # an assignment always writes
        if '#' in name:
            owner, _, field = name.rpartition('.')
            live = run.occurrences.live.get(owner)
            if live is not None and any(p.name == field for p in live.plan.event.params):
                tx.argument_writes[name] = None
        if isinstance(statement.value, Distribution):
            # A new distribution for the draws to come; what was drawn stays as it is.
            tx.writes[name] = statement.value
            return
        if isinstance(statement.value, Formula):
            # The following statements in this stage already see the new calculation.
            node = run.occurrences.node(statement.value.expr, scope, statement.origin)
            tx.writes[name] = Defined(node)
            tx.define(name, statement.origin)
            return
        if name in self.plan.stocks:
            node = run.occurrences.node(statement.value, scope, statement.origin)
            amount = self.amount(node, tx, exact_stocks=True)
            if not finite_number(amount):
                raise SimulationError(f'{statement.origin}: {name} would take the value {amount!r}')
            value = rational(amount)
            if statement.op != '=':
                current = self.stage_balance(name, tx)
                value = current + value if statement.op == '+=' else current - value
            balance = self.checked(name, value, statement.origin)
            tx.balances[name] = balance
            tx.writes[name] = float(balance)
        else:
            value = self.truth(statement.value, scope, statement.origin, tx)
            if statement.op != '=':
                current = run.value(name, tx=tx)
                value = current + value if statement.op == '+=' else current - value
            tx.writes[name] = self.checked(name, value, statement.origin)
        found = self.plan.values.get(name)  # none for a distribution-valued value
        if name in tx.defined or (found is not None and found.kind == FORMULA):
            # A request or a capacity that was a formula now holds the number (spec: "A scalar
            # assignment captures a value").
            tx.define(name, statement.origin)

    def move(self, statement, tx, scope):
        """`move amount from source to destination`: both inventories are checked before anything
        changes, and the exact requested amount is debited and credited together. Two ends
        that name one store (two arguments of an event that name one member) give and take the same
        amount together: the debit and the credit cancel, and its inventory stays as it is. A move of
        an amount at a store of a finished occurrence writes it, and fails; a move of nothing goes on
        (`Occurrences.writable`)."""
        run, origin, plan = self.run, statement.origin, self.plan
        node = run.occurrences.node(statement.amount, scope, origin)
        source = self.target(statement.source, scope, origin, tx)
        destination = self.target(statement.destination, scope, origin, tx)
        amount = (
            self.stage_balance(source, tx)
            if self.stock_read(node, tx) == source
            else self.amount(node, tx, exact_stocks=False)
        )
        if not finite_number(amount) or amount < 0:
            raise SimulationError(
                f'{origin}: a move takes a finite amount from 0, not {quantity(plan, source, amount)}'
            )
        requested = rational(amount)
        amount = float(amount)
        for end in (source, destination):
            run.occurrences.writable(end, origin, requested)
        if source == destination or requested == 0:
            tx.moves.append((source, destination, amount, origin))
            return
        endpoints = (
            (source, self.stage_balance(source, tx) - requested),
            (destination, self.stage_balance(destination, tx) + requested),
        )
        for name, after in endpoints:
            low, high = run.stock_state.bounds(name)
            if not low <= after <= high or not finite_number(after):
                raise SimulationError(
                    f'{origin}: the move of {quantity(plan, source, requested)} from {source} to {destination} '
                    f'fails: {name} would hold {quantity(plan, name, after)}, outside its range '
                    f'{span(plan, name, low, high)}; nothing is moved'
                )
        for name, after in endpoints:
            tx.balances[name] = after
            tx.writes[name] = float(after)
        tx.moves.append((source, destination, amount, origin))

    def stage_balance(self, store, tx):
        if store in tx.writes:
            return tx.balances[store] if store in tx.balances else rational(tx.writes[store])
        return self.run.stock_balance(store, self.run.now)

    def stock_read(self, node, tx):
        """Follow only identity reads, using definitions as they stand at this statement."""
        visited = set()
        while isinstance(node, nodes.Ref) and node.name not in visited:
            name = node.name
            visited.add(name)
            if name in self.plan.stocks:
                return name
            node = self.stock_definition(name, tx)
        return None

    def stock_definition(self, name, tx):
        """The live definition behind an amount, including its stage-selected occurrence."""
        run = self.run
        found = run.definition(name, tx)
        if found is not None and found.kind == FORMULA and name not in run.frozen:
            return found.node
        dynamic = self.plan.dynamic.get(name)
        if dynamic is not None and dynamic.op == 'at':
            point = dynamic.member_at(
                self.plan.members(dynamic.source),
                self.plan,
                lambda n: run.value(n, tx=tx),
                run.now,
                run.units_for(tx),
            )
            return nodes.ref(self.plan.project(point, dynamic.steps))
        return None

    def amount(self, node, tx, *, exact_stocks):
        """Stock assignments use physical balances throughout their arithmetic. An ordinary
        move expression uses the evaluated stock reading; an identity move spends the balance."""
        run = self.run

        def balance_of(name):
            if exact_stocks:
                if name in self.plan.stocks:
                    return self.stage_balance(name, tx)
                return self.stock_definition(name, tx)
            return None

        return run.stock_state.amount(
            node, run.units_for(tx), lambda name: run.value(name, tx=tx), balance_of
        )

    def argument(self, node, tx):
        """Read an argument or a trigger capture once, keeping its actual branches and caller."""
        run = self.run
        direct, dependencies = {}, {}

        def read(name):
            direct[name] = None
            return run.value(name, tx=tx, observations=dependencies)

        value = lazily(node, read, run.units_for(tx), run.now)
        if tx.captures:
            # Bare trigger locals hold earlier measurements in this firing. Include their
            # evaluations only when this expression consulted them, directly or through a lookup.
            names = set(direct).union(*(reads.keys() for reads in dependencies.values()))
            for capture, earlier in tx.captures.items():
                if capture in names:
                    for name, reads in earlier.items():
                        dependencies.setdefault(name, {}).update(reads)
        return value, direct, dependencies

    def queue(self, statement, tx, scope):
        """`.start(...)`: the arguments are evaluated at the caller, left to right, once; on a
        collection the members start in the order of its keys, and of equal keys in their order of
        creation."""
        run = self.run
        point = self.resolved(statement.event, scope, statement.origin)
        args, observations = [], []
        for expression in statement.args:
            node = run.occurrences.node(expression, scope, statement.origin)
            arg, direct, dependencies = self.argument(node, tx)
            args.append(float(arg) if isinstance(arg, int) and not isinstance(arg, bool) else arg)
            observations.append((tuple(direct), tuple((n, tuple(r)) for n, r in dependencies.items())))
        args = tuple(args)
        evidence = (statement.origin, self.plan.owner_of(scope), tuple(observations)) if args else None
        if point[0] == 'event':
            tx.starts.append((point[1], point[2], args, evidence))
            return
        if point[0] != 'many' or any(each[0] != 'event' for each in point[1].points):
            raise SimulationError(f'{statement.origin}: a start of what is no event')
        entries = point[1]

        def read(name):
            return run.value(name, tx=tx)

        order = sorted(
            kept(entries.tests, read, run.units_for(tx)),
            key=lambda k: (
                float(read(entries.keys[k])) if isinstance(entries.keys[k], str) else entries.keys[k],
                k,
            ),
        )
        for k in order:
            tx.starts.append((entries.points[k][1], entries.points[k][2], args, evidence))

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
            allowed = [member for member in run.chance.outcomes(producer, tx) if member not in barred]
            if not allowed:
                return statement.orelse
            chosen = run.chance.draw(producer, allowed, tx)
        else:
            chosen = run.truth(node, tx)
        for case, ok in zip(statement.cases, eligible):
            if ok and case.member == chosen:
                return case.body
        return statement.orelse

    def commit(self, tx):
        """Publish the writes of a stage and register the occurrences that it queued. A failure in it
        (a start that a limit, its arguments or its entry refuse) discards the whole stage, and the run
        fails (`_Savepoint`)."""
        saved = _Savepoint(self.run, tx)
        try:
            self._publish(tx)
        except Exception:
            saved.discard()
            raise

    def _publish(self, tx):
        run = self.run
        for part, owner, details, delta in tx.edits:  # an edit at a stop in the stage (`checkpoints.py`)
            run.recorder.entry(run.now, 'edit', part, owner, **details)
            run.breaks.transferred(details['target'], delta)
            run.occurrences.met(details['target'])
        for source, destination, amount, origin in tx.moves:
            run.recorder.entry(
                run.now, 'move', origin, tx.owner, amount=amount, source=source, destination=destination
            )
            for end in (source, destination):
                run.occurrences.met(end)
        for store, side, ranking in tx.allocations:
            # The endpoint shares its flows by its new rule once its set settles again.
            self.plan.allocate(store, side, ranking)
            self.plan.log.append(('allocate', store, side, ranking))
            run.changed.add(store)
        for name, value in tx.writes.items():
            run.write(name, value, tx.balances.get(name))
        for member, event, args, evidence in tx.starts:
            run.occurrences.register(member, event, args, evidence)

    # ---- the settling -----------------------------------------------------------------------------

    def settle(self):
        """Build again the sets that the round touched (see the module); gives the stores of the
        sets that it built."""
        run, ways, plan, t = self.run, self.run.ways, self.plan, self.run.now
        self.phase = 'settle'
        run.finish_arrival()
        joined, left = list(run.joined), set(run.left)
        joining = set(joined)
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
            run.contacts, run.bound_at = (), {}
            run.settled()
            return set()
        moving_before = ways.set_of
        while True:
            # Sets that integrate together share one numerical trajectory. Rebuild the
            # remaining producers even when the last reader of their rates departs.
            for instance in {ways.sets[key][1] for key in touched & ways.grouped}:
                touched.update(ways.set_of[name] for name in instance.flows)
            # The sets in the order of their ids, so that the region is the same whatever the order in
            # which a set of ids was made (a restored run makes its sets of ids afresh, `saved.py`).
            region = [f for key in sorted(touched) for f in ways.sets[key][0].flows if f not in left]
            additions = (*joined, *(f for connected in waiting for f in connected.flows))
            seen = set(region)
            for flow in additions:
                if flow not in left and flow not in seen:
                    region.append(flow)
                    seen.add(flow)
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
        values.update(run.bound_at)
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
            if flow in joining:
                run.tolerate(plan.flows[flow])
        run.settled()
        ways.build(made, values, t)
        run.contacts, run.bound_at = (), {}
        return stay

    def splits(self, stores):
        """Mark each split of who is served that the settling decided within tolerance (see the
        module): an entry `settle` with the near-ties (`split_ties`) of each endpoint that serves
        its flows by priority, at the stores `stores` (at every store, with None)."""
        run, plan = self.run, self.plan
        for store, side in sorted(plan.rankings):
            if stores is not None and store not in stores:
                continue
            near = split_ties(run, store, side)
            if near:
                origin = plan.ends[(store, side)].origin
                run.recorder.entry(run.now, 'settle', origin, plan.values[store].key.owner, near=near)


def split_ties(run, store, side):
    """The near-ties of the split of who is served at an endpoint that serves its flows by priority
    classes, first to last (see the module): (origin, comparison, difference, tolerance) for each
    boundary between two classes at which what the endpoint has differs from what the classes ahead
    of the boundary claim by no more than the tolerance of what it reads, while the class after it
    claims more than that. What the endpoint has is its capacity, or less: what flows into the store
    while it is at its lower bound, for its outflow, and what flows out of it while it is at its upper
    bound, for its inflow (within the store's tolerance). A connection claims its request in its
    direction within its capacity. An endpoint that nothing limits shares no split."""
    plan = run.plan
    end = plan.ends[(store, side)]
    classes = run.classes_of(store, side, plan.rankings[(store, side)], {c: c for c in end.flows})
    if len(classes) < 2:
        return ()
    limits = []
    if end.capacity is not None:
        limits.append((float(run.value(end.capacity)), end.capacity, f'the capacity of {store}.{side}'))
    lower, upper = run.bounds[store]
    bound = lower if side == 'outflow' else upper
    level = float(run.value(store))
    if math.isfinite(bound) and abs(level - bound) <= run.amount_tolerance(store, level, bound):
        other = 'inflow' if side == 'outflow' else 'outflow'
        total = sum(float(run.value(f'{c}.actual_rate')) for c in plan.incident(store, other))
        limits.append(
            (
                total,
                f'{store}.{other}.actual_rate',
                f'what flows {"into" if side == "outflow" else "out of"} {store}',
            )
        )
    if not limits:
        return ()
    limit, operand, what = min(limits, key=lambda each: each[0])
    rate = nodes.ref(f'{store}.{side}.actual_rate')
    claims = [sum(_claim(run, plan.connections[c]) for c in members) for members in classes]
    found, ahead = [], 0.0
    for k in range(len(classes) - 1):
        ahead += claims[k]
        difference = limit - ahead
        band = plan.units.comparisons.band(
            nodes.ref(operand), rate, limit, ahead, lambda n: lazily(n, run.value, plan.units, run.now)
        )
        if claims[k + 1] > band and against('eq', difference, band):
            served = [c for members in classes[: k + 1] for c in members]
            comparison = (
                f'{what} against the claims of {_listed(served)}, served before {_listed(classes[k + 1])}'
            )
            found.append((end.origin, comparison, difference, band))
    return tuple(found)


def _claim(run, connection):
    """What a connection claims: its request in its direction (a leg of a route takes the positive
    part of the route's signed request in its own), within its capacity; nothing for no request."""
    request = float(run.value(connection.request))
    if connection.role in (FORWARD, BACKWARD):
        request = max(-request if connection.role == BACKWARD else request, 0.0)
    if request <= 0:
        return 0.0
    return request if connection.capacity is None else min(request, float(run.value(connection.capacity)))


def _listed(names):
    """Connections by name, for a message: the first three, and how many more."""
    names = list(names)
    shown = ', '.join(names[:3])
    return shown if len(names) <= 3 else f'{shown} and {len(names) - 3} more'


def near_ties(node, origin, plan, frozen, side, later=None, *, comparisons=None, definition=None):
    """The near-ties of a condition (see the module): (origin, comparison, difference, tolerance) of
    each numeric comparison that decides its answer, through boolean formulas, whose sides differ by
    no more than the band of their two values, and with `later`, still do an instant later. `side(node)`
    is the value of a side, as the
    reader of the condition gives them. The terms read are those of the answer's path: `and` and `or`
    stop at the term that decides, a conditional takes its selected side. Of those, the ones that
    decide are kept: every term of a true `and` or of a false `or`, since each one turned the other
    way would turn the answer; else only the term that stopped it; of a chain of comparisons, every
    link of a true one, else the link that fails. A membership is evaluated (a reversed interval
    fails by name), then read as its chain `lo <= x <= hi`."""

    comparisons = plan.units.comparisons if comparisons is None else comparisons
    definition = plan.values.get if definition is None else definition

    def decided(part):
        """(the answer of a part, the near-ties of the comparisons that decide it), as a computation
        of `walk.walked`: each part through a boolean formula is one that it yields, so a chain of
        them is no limit of Python's."""
        if isinstance(part, nodes.Ref):
            value = definition(part.name)
            if value is not None and value.kind == FORMULA and value.boolean and part.name not in frozen:
                return (yield decided(value.node))
            return bool(side(part)), []
        if isinstance(part, nodes.BoolOp):
            stops = part.op == 'or'  # the answer of a term that decides the whole
            ties = []
            for each in part.values:
                answer, mine = yield decided(each)
                if answer == stops:
                    return answer, mine
                ties += mine
            return not stops, ties
        if isinstance(part, nodes.Unary) and part.op == 'not':
            answer, mine = yield decided(part.operand)
            return not answer, mine
        if isinstance(part, nodes.IfElse):
            test, mine = yield decided(part.test)
            answer, more = yield decided(part.body if test else part.orelse)
            return answer, mine + more
        membership = nodes.membership(part)
        if membership is not None:
            side(part)  # the membership itself, which fails by name where its interval is reversed
            return compared(membership[0])
        if isinstance(part, nodes.Compare):
            return compared(part)
        return bool(side(part)), []

    def compared(part):
        ties = []
        for left, op, right in zip(part.operands, part.ops, part.operands[1:], strict=False):
            a, b = side(left), side(right)
            if isinstance(a, bool | str) or isinstance(b, bool | str):
                if not ((a == b) if op == 'eq' else (a != b)):
                    return False, []
                continue
            difference, band = comparisons.gap_band(left, right, a, b, side)
            exact_count = (
                any(
                    isinstance(part, nodes.Ref)
                    and (
                        (part.name in plan.reductions and plan.reductions[part.name].op == 'count')
                        or (part.name in plan.dynamic and plan.dynamic[part.name].op == 'count')
                    )
                    for part in (left, right)
                )
                and a == b
                and float(a).is_integer()
            )
            tie = (
                [(origin, nodes.notation(part), recorded_number(difference), recorded_number(band))]
                if not exact_count
                and band > 0
                and against('eq', difference, band)
                and (later is None or against('eq', later(left, right), band))
                else []
            )
            if not against(op, difference, band):
                return False, tie
            ties += tie
        return True, ties

    return tuple(dict.fromkeys(walked(decided(node))[1]))
