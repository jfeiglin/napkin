"""Breakpoints, checkpoints and exact resume (PLAN, change 15; `napkin/program/checkpoint.py`).

**Breakpoints.** A run with breakpoints (`Run(plan, breakpoints)`) counts each hit: a stage that comes
due whose step or event a breakpoint names, before its guard is read, and a statement of a stage or of
the setup that a breakpoint names, before it runs, each for the breakpoint's member or occurrence.
The first hit after the `passing` ones stops the run (`Stopped`) with a checkpoint (`Breaks.checkpoint`):
the stage and the stages after it in its round are held, as the pause of a choice holds them
(`moment.py`), and nothing of the stage is visible, since a stage commits only at its end. A firing
belongs to the conditions of a round, so a breakpoint in a trigger's body is refused by name, and so
is a location that the program does not have.

**Resume in place.** `Run.resume()` passes the stop and runs the held stage again from its start,
then the rest of the run: its hits are counted again from the stage's start, so a hit before the stop
passes and the next stops; the draws that the stage made before the stop are keyed (`chance.py`), so
they are the same and are traced once. Nothing else of the run changed at the stop.

**Resume in a fresh process** runs the program again from its start, with the checkpoint's
configuration and breakpoints, passing its hits up to the stop (`timeline.resume`): there, the stop,
the state and the record so far must equal the checkpoint's, or the resume is refused by name
(`CheckpointError`), so a checkpoint never goes on as another run. So the run that goes on is the
run straight through, number for number: the same code takes the same steps from the same state.

That is the choice for the numerical state that a run carries across a moment, which its future reads
and a checkpoint of the logical state alone would lose. What carries it today:

- the sparse integrator keeps its Radau solver (step size, Jacobian, factorizations) across a
  moment that falls on the end of one of its steps (`sparse.py`, `cut`);
- a declared solver's `solve.Solver` keeps its HiGHS instance for the run (its basis,
  factorization and scaling: a warm answer agrees with a fresh one within the tolerances, not bit
  for bit), and the last problem and answer, which decide whether a solve is made and traced;
- the family, the lines and a declared solver's lines hold each store as a line from the time at
  which it last changed, and the time at which it meets a bound; the same store rebuilt at a moment
  from its value there gives other last bits;
- each instance holds what it captured when it was built (the parameters of a component, the
  constants of the sparse integrator, what a flow asks), which the stages of a round read until the
  round's settling builds it again;
- the plan makes values as the run first reads them (reductions, keyed reads), named in that order.

Saving all of that as data, or starting it again at each moment on every path (which rebuilds every
set at every moment, and solves every declared solver cold), costs code in each way of running, or
time at each moment of every run. Running the program again costs nothing on a run that does not
stop, and the time of the run to the stop once, when a checkpoint is resumed in a fresh process.

The checkpoint's logical state (`State`) is what a caller inspects, and what the replay checks.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ...program import parts as p
from ...program.canonical import program_bytes
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
from ...program.record import Entry
from .plan import STARTS, _statements

_SOURCES = ('engine', 'program', 'core')  # the folders of the package whose code a run runs
_FILES = ('__init__.py', 'expressions.py', 'distributions.py')
_version = []


def engine_version():
    """The version of the engine: the SHA-256 of the code that a run runs (the files of `engine/`,
    `program/` and `core/`, and the modules of expressions and distributions), made once."""
    if not _version:
        root = Path(__file__).resolve().parents[2]
        files = sorted(
            [path for folder in _SOURCES for path in (root / folder).rglob('*.py')]
            + [root / name for name in _FILES]
        )
        digest = hashlib.sha256()
        for path in files:
            digest.update(path.relative_to(root).as_posix().encode() + b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        _version.append(digest.hexdigest())
    return _version[0]


def program_digest(program):
    """The SHA-256 of the canonical bytes of a program."""
    return hashlib.sha256(program_bytes(program)).hexdigest()


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
    pass; `expected`, the checkpoint that a replay checks at its stop."""

    def __init__(self, run, breakpoints, passing=0, expected=None):
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
        self.hits = 0  # the hits so far
        self.passing = passing
        self.expected = expected
        self.start = 0  # the hits before the stage that runs (or the setup)
        self.next = ''  # the stage that runs, by its origin, or `setup`

    # ---- hits -------------------------------------------------------------------------------------

    def setup(self):
        """The setup begins: a stop in it runs it again from its start."""
        self.start, self.next = self.hits, 'setup'

    def stage(self, made, step):
        """A stage of the occurrence `made` comes due: a breakpoint at it or at its event stops it."""
        self.start, self.next = self.hits, step.origin
        if not self.stages:
            return
        for at in (step.origin, made.event.origin):
            for breakpoint in self.stages.get(at, ()):
                if breakpoint.owner in ('', made.id, made.member):
                    self._hit(breakpoint, step.origin, made.id, made.member)
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
                self._hit(breakpoint, statement.origin, tx.owner, member)
                return

    def _hit(self, breakpoint, at, owner, member):
        run = self.run
        self.hits += 1
        stop = Stop('breakpoint', breakpoint, at, owner, member, run.now, run.recorder.round, self.hits, self.next)
        if self.expected is not None and self.hits == self.expected.stop.hit:
            self._check(stop)
        if self.hits <= self.passing:
            return
        # The stage runs again from its start when the run resumes: its hits are counted again.
        self.hits = self.start
        raise Stopped(stop)

    # ---- checkpoints ----------------------------------------------------------------------------

    def checkpoint(self, stop):
        """The checkpoint of a stop (`napkin/program/checkpoint.py`)."""
        run, plan = self.run, self.run.plan
        return Checkpoint(
            program_digest(plan.program),
            engine_version(),
            plan.configuration,
            self.breakpoints,
            stop,
            self.state(),
            run.recorder.record(run.now, pause=pause_entry(stop)),
        )

    def state(self):
        """The logical state of the run now (`State`)."""
        run, plan = self.run, self.run.plan
        values = []
        for name, value in plan.values.items():
            if value.kind in STARTS:
                values.append((name, _present(run, name)))
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

    def _check(self, stop):
        """A replay reaches the stop of the checkpoint that it resumes: the stop, the state and the
        record so far must be the checkpoint's."""
        expected, self.expected = self.expected, None
        found = self.checkpoint(stop)
        for what, mine, theirs in (
            ('where the run stops', found.stop, expected.stop),
            ('the state', found.state, expected.state),
            ('the record so far', found.record, expected.record),
        ):
            if encode(mine) != encode(theirs):
                raise CheckpointError(
                    f'the checkpoint does not resume: {what} differs from the run of its program '
                    f'({_difference(mine, theirs)})'
                )


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


def _present(run, name):
    """The value now of a value that the start evaluates: a store of a set on its line or curve, one
    that a commit of this round wrote, or what the run holds."""
    if name in run.written:
        return run.written[name]
    if name in run.ways.set_of:
        return run.ways.value(name, run.now)
    return run.env.get(name)


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
