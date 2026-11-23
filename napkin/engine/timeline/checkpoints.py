"""Breakpoints, checkpoints and exact resume (docs/design/decisions.md, change 15; `napkin/program/checkpoint.py`).

**Breakpoints.** A run with breakpoints (`Run(plan, breakpoints)`) counts each hit: a stage that comes
due whose step a breakpoint names, or whose event when it is the occurrence's first step, before its
guard is read, and a statement of a stage or of the setup that a breakpoint names, before it runs,
each for the breakpoint's member or occurrence. The first hit after the `passing` ones stops the run
(`Stopped`) with a checkpoint (`Breaks.checkpoint`): the stage and the stages after it in its round
are held (`moment.Moment.held`), and nothing of the stage is visible, since a stage commits only at
its end. A firing belongs to the conditions of a round, so a breakpoint in a trigger's body is
refused by name, and so is a location that the program does not have.

**Resume in place.** `Run.resume()` passes the stop and runs the held stage again from its start,
then the rest of the run: its hits are counted again from the stage's start, so a hit before the stop
passes and the next stops; the draws that the stage made before the stop are keyed (`chance.py`), so
they are the same and are traced once. Nothing else of the run changed at the stop.

**Resume in a fresh process** (`timeline.resume`) makes the run again from the checkpoint's saved
state (`saved.py`) and goes on from the stop, as in place: nothing before the stop runs twice. What a
run carries across a moment that its future reads is in that state, or starts again at each moment
on every path (`saved.py` says which), so the run that goes on is the run straight through, number
for number. The restored run's logical state must be the checkpoint's (`State`), or the resume is
refused by name (`CheckpointError`), so a checkpoint never goes on as another run.

**The budget of the record** holds at every stop. If the checkpoint's record exceeds its budget,
`HistoryFull` returns the prefix ending at the first excess piece (`Record.within`).

The checkpoint's logical state (`State`) is what a caller inspects and edits.
"""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from ...core.units import rational
from ...program import parts as p
from ...program.artifact import Artifact
from ...program.checkpoint import (
    Breakpoint,
    Checkpoint,
    CheckpointError,
    Occurrence,
    State,
    Stop,
    Trigger,
    encode,
)
from ...program.record import Entry, Key
from .moment import quantity, span
from .plan import BUILTINS, STARTS, STATE, _statements, name_of
from .record import HistoryFull, declared
from .saved import at_stop, save

_SOURCES = ('engine', 'program', 'core')  # the folders of the package whose code a run runs
_FILES = ('__init__.py', 'expressions.py', 'distributions.py')


def _engine_version():
    """The SHA-256 of the code that a run runs: the files of `engine/`, `program/` and `core/`, and
    the modules of expressions and distributions, as they are when the engine is imported."""
    root = Path(__file__).resolve().parents[2]
    files = sorted(
        [path for folder in _SOURCES for path in (root / folder).rglob('*.py')]
        + [root / name for name in _FILES]
    )
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


_VERSION = _engine_version()


def engine_version():
    """The version of the engine that runs (`_engine_version`), which a checkpoint names."""
    return _VERSION


def program_digest(program):
    """The identity of a program, which a checkpoint names: its artifact's digest, the SHA-256 of its
    canonical bytes (`napkin/program/artifact.py`)."""
    return Artifact(program).digest


class Stopped(Exception):
    """A hit that stops the run: its `Stop`."""

    def __init__(self, stop):
        super().__init__(f'stopped before {stop.at} at t = {stop.t:g} h')
        self.stop = stop


def _locations(program):
    """(the origins of the events and the stages, the origins of the statements of the stages and the
    setup, the origins of the statements of the triggers' bodies)."""
    stages, statements, firings = set(), set(), set()
    statements.update(statement.origin for statement in _statements(program.setup))
    for template in program.templates:
        for event in template.events:
            stages.add(event.origin)
            for step in event.steps:
                if isinstance(step, p.After):
                    stages.add(step.origin)
                    statements.update(statement.origin for statement in _statements(step.body))
            for trigger in event.triggers:
                firings.update(statement.origin for statement in _statements(trigger.body))
    return stages, statements, firings


class Breaks:
    """The breakpoints of one run and its hits (see the module). `passing` is the number of hits that
    pass."""

    def __init__(self, run, breakpoints, passing=0):
        self.run = run
        self.breakpoints = tuple(breakpoints)
        self.stages, self.statements = {}, {}
        stages, statements, firings = _locations(run.plan.program)
        for breakpoint in self.breakpoints:
            if not isinstance(breakpoint, Breakpoint):
                raise CheckpointError(f'{breakpoint!r} is no breakpoint')
            if breakpoint.at in stages:
                self.stages.setdefault(breakpoint.at, []).append(breakpoint)
            elif breakpoint.at in statements:
                self.statements.setdefault(breakpoint.at, []).append(breakpoint)
            elif breakpoint.at in firings:
                raise CheckpointError(
                    f'{breakpoint.at}: a breakpoint in the body of a trigger: a firing belongs to the '
                    'conditions of a round, and a run stops only before a stage or a statement of one'
                )
            else:
                raise CheckpointError(
                    f'{breakpoint.at}: no event, stage or statement of the program has this origin'
                )
        self.stops = []  # actual pauses, including earlier stops of a restored run
        self.hits = 0  # the hits so far
        self.passing = passing
        self.start = 0  # the hits before the stage that runs (or the setup)
        self.next = ''  # the stage that runs, by its origin, or `setup`
        # The edits of the run, in order, and the places of those made at a stop before a stage,
        # which commit once.
        self.edits, self.done = [], set()
        self.recorded = None  # the record so far at the last stop, within its budget

    # ---- hits -------------------------------------------------------------------------------------

    def setup(self):
        """The setup begins: a stop in it runs it again from its start."""
        self.start, self.next = self.hits, 'setup'

    def stage(self, made, step, first):
        """A stage of the occurrence `made` comes due: a breakpoint at it, or at its event when it is
        the occurrence's first step (`first`), stops it."""
        self.start, self.next = self.hits, step.origin
        if not self.stages:
            return
        for at in (step.origin, made.event.origin) if first else (step.origin,):
            for breakpoint in self.stages.get(at, ()):
                if breakpoint.owner in ('', made.id, made.member):
                    self._hit(breakpoint, step.origin, made.id, made.member, None)
                    return

    def statement(self, statement, tx):
        """A statement of a stage or of the setup is about to run."""
        found = self.statements.get(statement.origin)
        if not found or not tx.stage:
            return
        live = self.run.occurrences.live.get(tx.owner)
        member = live.plan.member if live is not None else ''
        for breakpoint in found:
            if breakpoint.owner in ('', tx.owner, member):
                self._hit(breakpoint, statement.origin, tx.owner, member, tx)
                return

    def _hit(self, breakpoint, at, owner, member, tx):
        """A hit before a stage (`tx` None) or before a statement of the stage `tx`: it passes, with
        the edits made at it, or it stops the run."""
        run = self.run
        self.hits += 1
        stop = Stop(
            'breakpoint', breakpoint, at, owner, member, run.now, run.recorder.round, self.hits, self.next
        )
        if self.hits <= self.passing:
            for k, edit in enumerate(self.edits):
                if edit.hit == stop.hit and (tx is not None or k not in self.done):
                    self.done.add(k)
                    self.apply(edit, stop, tx)
            return
        # The record so far is the checkpoint's; a record past its budget ends the run here instead.
        recorder, arrival = at_stop(run)
        record = recorder.record(run.now, pause=pause_entry(stop))
        if record.failure is not None:
            raise HistoryFull(record)
        self.recorded = record
        self.prefix = recorder, arrival
        # The stage runs again from its start when the run resumes: its hits are counted again.
        self.hits = self.start
        raise Stopped(stop)

    # ---- edits ----------------------------------------------------------------------------------

    def edit(self, checkpoint):
        """The last edit of a checkpoint of this run, made at its stop in place: one at a stop before a
        stage commits now; one at a stop before a statement joins the stage when it runs again."""
        edit, stop = checkpoint.edits[-1], checkpoint.stop
        self.checked(edit)
        self.edits.append(edit)
        if stop.at == stop.next:
            self.done.add(len(self.edits) - 1)
            self.apply(edit, stop, None)

    def apply(self, edit, stop, tx):
        """An edit at a stop: into the writes of the stage `tx`, traced when it commits, or committed
        now (`napkin/program/checkpoint.py`)."""
        run = self.run
        name, value = self.checked(edit)
        old = run.value(name, tx=tx)
        balance = value if name in run.plan.stocks else None
        delta = run.stock_state.external(name, value, tx)
        if balance is not None:
            value = float(balance)
        details = {'breakpoint': stop.breakpoint.at, 'target': name, 'old': old, 'new': value}
        if tx is not None:
            tx.writes[name] = value
            if balance is not None:
                tx.balances[name] = balance
            else:
                tx.balances.pop(name, None)
            tx.edits.append((stop.at, stop.owner, details, delta))
            return
        run.recorder.entry(run.now, 'edit', stop.at, stop.owner, **details)
        self.transferred(name, delta)
        run.write(name, value, balance)
        run.occurrences.met(name)

    def transferred(self, name, delta):
        """Record the committed difference from the physical balance immediately before the edit."""
        if delta:
            run = self.run
            run.recorder.external(name, run.now, delta, run.changed_start(name))

    def checked(self, edit):
        """(the engine name, the new value in canonical units) of an edit, once the engine's rules
        hold: a stored value, not of a finished occurrence, of its type (a member of its enum),
        within its bounds."""
        run, plan = self.run, self.run.plan
        name, value = edit.target, edit.value
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise CheckpointError(f'{name} takes a finite number, not {value}')
            value = Fraction(value)
        if isinstance(name, Key):
            # A value as the model names it, in its declared unit: the engine's name, in canonical units.
            key, name = name, name_of(name)
            if (
                name in plan.values
                and isinstance(value, int | float | Fraction)
                and not isinstance(value, bool)
            ):
                _, scale = declared(plan.program, key)
                if name in plan.stocks:
                    value = rational(value) * scale
                else:
                    value *= scale if isinstance(value, Fraction) else float(scale)
        found = plan.values.get(name)
        if found is None or found.kind != STATE:
            what = 'no value of the run' if found is None else f'a value of kind {found.kind}'
            raise CheckpointError(f'{name}: an edit changes a stored value, and this is {what}')
        # A finished occurrence is frozen: the one rule of every write of a run (`Occurrences.frozen`).
        finished = run.occurrences.frozen(name)
        if finished is not None:
            raise CheckpointError(f'{name} belongs to the finished occurrence {finished}, which is frozen')
        owner = plan.occurrence_of(name)
        if owner is not None and _fixed(plan, name):
            raise CheckpointError(
                f'{name}: an edit changes a stored value, and this is a parameter or a built-in field of '
                'its occurrence, which its start gives'
            )
        current = run.present(name)
        if isinstance(current, bool) or isinstance(value, bool):
            if not (isinstance(current, bool) and isinstance(value, bool)):
                raise CheckpointError(f'{name} holds {current!r}, and an edit gives it {value!r}')
            return name, value
        if isinstance(current, str):
            members = _members(plan, name)
            if not isinstance(value, str) or (members is not None and value not in members):
                allowed = f'a member of {", ".join(members)}' if members is not None else 'a text'
                raise CheckpointError(f'{name} takes {allowed}, not {value!r}')
            return name, value
        if not isinstance(value, int | float | Fraction) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            raise CheckpointError(f'{name} takes a finite number, not {value!r}')
        lower, upper = run.bounds.get(name, (-math.inf, math.inf))
        if name in plan.stocks:
            value = rational(value)
            lower, upper = run.stock_state.bounds(name)
        elif isinstance(value, Fraction):
            # Authored literal endpoints retain their exact values. A bound that read the
            # initial state, or a reversed interval collapsed at setup, keeps the run's snapshot.
            lo = run.range_endpoint(found.lower, lambda _: lower)
            hi = run.range_endpoint(found.upper, lambda _: upper)
            if lo <= hi:
                lower, upper = lo, hi
        if not lower <= value <= upper:
            # In the value's declared unit, in which the edit is given (`moment.quantity`).
            if isinstance(edit.value, Decimal) and isinstance(edit.target, Key):
                shown = f'{edit.value} {found.unit}'.rstrip()
            elif isinstance(value, Fraction):
                amount = value / plan.units.exact_scale(found.unit) if found.unit else value
                shown = f'{amount} {found.unit}'.rstrip()
            else:
                shown = quantity(plan, name, value)
            raise CheckpointError(
                f'{name} = {shown} is outside its range {span(plan, name, float(lower), float(upper))}'
            )
        try:
            number = float(value)
            return name, value if name in plan.stocks else number
        except OverflowError:
            raise CheckpointError(f'{name} takes a finite number') from None

    # ---- checkpoints ----------------------------------------------------------------------------

    def checkpoint(self, stop):
        """The checkpoint of a stop (`napkin/program/checkpoint.py`), with the record so far that the
        hit found within its budget."""
        run, plan = self.run, self.run.plan
        recorder, arrival = self.prefix
        self.prefix = None
        self.stops.append(stop)
        return Checkpoint(
            program_digest(plan.program),
            engine_version(),
            plan.configuration,
            self.breakpoints,
            stop,
            self.state(),
            self.recorded,
            tuple(self.edits),
            save(run, recorder, arrival),
            stops=tuple(self.stops),
        )

    def state(self):
        """The logical state of the run now (`State`)."""
        run, plan = self.run, self.run.plan
        values = []
        for name, value in plan.values.items():
            if value.kind in STARTS:
                values.append((name, run.present(name)))
        values += [(name, run.env[name]) for name in plan.draws if name in run.env]
        values += [(name, run.chance.distribution(name)) for name in plan.distributions]
        occurrences = tuple(
            Occurrence(
                live.id,
                live.plan.member,
                live.plan.event.name,
                float(live.started),
                live.step,
                live.due,
                live.waiting,
                live.active,
            )
            for live in run.occurrences.live.values()
        )
        held = run.moment.held
        if isinstance(held, tuple):
            queue, k = held
            pending = tuple((live.id, live.plan.event.steps[live.step].origin) for live in queue[k:])
        else:
            pending = (('', 'setup'),) if held is not None else ()
        triggers = tuple(
            Trigger(state.plan.key, state.armed, state.rearm_at, state.blocked_at, state.firings)
            for state in run.triggers.states
        )
        return State(tuple(values), occurrences, pending, triggers)

    def restored(self, checkpoint):
        """A run made again from a checkpoint (`saved.restore`) is the run that stopped there: its
        logical state is the checkpoint's, or the checkpoint does not resume here. The edits of the
        checkpoint are the run's; one at a stop before a stage commits now, once."""
        found = self.state()
        if found != checkpoint.state and encode(found) != encode(checkpoint.state):
            raise CheckpointError(
                'the checkpoint does not resume: its saved state does not make its state again '
                f'({_difference(found, checkpoint.state)})'
            )
        stop = checkpoint.stop
        self.stops = list(checkpoint.stops or (stop,))
        self.edits = list(checkpoint.edits)
        for k, edit in enumerate(self.edits):
            if edit.hit == stop.hit and stop.at == stop.next and k not in self.done:
                self.done.add(k)
                self.apply(edit, stop, None)


def pause_entry(stop):
    """The `pause` entry that ends the record of a run that stopped."""
    return Entry(
        stop.t,
        stop.round,
        'pause',
        stop.at,
        stop.owner,
        (('breakpoint', stop.breakpoint.at), ('hit', stop.hit), ('next', stop.next)),
    )


def _fixed(plan, name):
    """Whether a value of an occurrence is a parameter of its event or a built-in field."""
    key = plan.values[name].key
    _, _, member, _ = plan.frames[key.owner]
    event = plan.events[(member.id, key.owner.rsplit('#', 1)[0].rsplit('.', 1)[1])][3]
    return key.steps[0] in BUILTINS or key.steps[0] in {param.name for param in event.params}


def _members(plan, name):
    """The members of the enum of a stored value, or None for a text: from its declaration, of the
    root, of a member's template or of an occurrence's event."""
    key = plan.values[name].key
    owner, field = key.owner, key.steps[0]
    if not owner:
        parts = plan.program.root
    elif '#' in owner:
        _, _, member, _ = plan.frames[owner]
        head = owner.rsplit('#', 1)[0]
        event = plan.events[(member.id, head.rsplit('.', 1)[1])][3]
        parts = (*event.params, *event.locals)
    else:
        parts = plan.program.member(owner)[0].values
    for part in parts:
        if part.name == field and isinstance(part.type, p.EnumType):
            return plan.program.enum(part.type.enum).members
    return None


def _difference(mine, theirs):
    """The first part in which two values differ, for a message."""
    if isinstance(mine, tuple) and isinstance(theirs, tuple):
        for k, (a, b) in enumerate(zip(mine, theirs)):
            if encode(a) != encode(b):
                return f'[{k}]: {_difference(a, b)}'
        return f'{len(mine)} parts, not {len(theirs)}'
    if hasattr(mine, '__dataclass_fields__') and type(mine) is type(theirs):
        for name in mine.__dataclass_fields__:
            a, b = getattr(mine, name), getattr(theirs, name)
            if encode(a) != encode(b):
                return f'{name}: {_difference(a, b)}'
    return f'{mine!r}, not {theirs!r}'
