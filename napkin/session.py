"""One run played through its checkpoints (docs/design/decisions.md, change 15): `Session`, its `Log`, and `play`.

A session plays one run of a program under a configuration. It sets breakpoints at locations of the
compiled program (an event, a stage or a statement, for every occurrence or for one member or one
occurrence: `napkin/program/checkpoint.py`), runs to the first stop (`advance`), shows the checkpoint
(`view`: where the run stopped, in which occurrence, what runs next and the values that the caller
asks for, each in its declared unit with its label), makes the caller's edits there (`edit`) and goes
on, to the next stop or to the end. A member's title (`title "DC Water"`, docs/design/decisions.md, change 19) comes from
the side table, for a caller that names the member (`title`, `View.title`, `Shown.title`). The
engine stops, edits and resumes (`napkin/engine/timeline/checkpoints.py`) and checks each edit; it
knows no player and no permission.
What a stop shows, and which edits a person may make, is the caller's: `napkin play` is one caller.

**The log** (`Log`) is what a session did: its breakpoints, each stop at which it waited, and each
edit that it made, at the stop of its hit. A session made with a log plays it again: it passes each
stop of the log before the last with the log's edits there, and waits at the last with its edits
made, as the logged session did. Each stop must be the log's stop of its hit again, with its time
within the tolerance in time of a crossing (`Numerics.crossing`), and the run must reach each stop
of the log up to its horizon, or up to the end of its record where its budget ends it (a run stops by
its budget where its record does, before any later stop), or the log is refused by name
(`CheckpointError`). The run of a log (`play`) continues to the end. If the original session
finished with no further edit, both runs make the same decisions in the same order. The draws
stay the same and the values agree closely. Inside a long solver step, the relative difference
between readings can exceed `rtol`. The run store keeps the run of a log under its key
(`napkin.store.run`).

**Saving.** `save` writes the checkpoint at which the session waits, with its edits, and `load`
goes on from it in a fresh process: the run is made again from the checkpoint's saved state, and
nothing before the stop runs again (`napkin/engine/timeline/saved.py`). A checkpoint of another
program, of another version of the engine or of another configuration is refused by name. The log
of a restored session retains the stop identities saved with the checkpoint.

**What a stop shows.** The values at a stop are those of the checkpoint's state, and any other value
(a formula, a rate) is read from the record so far at the time of the stop (`napkin.engine.read`),
each in its declared unit: what the run committed before the stage that stopped, since a stage
commits only at its end. An edit made at the stop is listed with the stop (`View.edits`) and takes
effect as the run goes on: one before a stage commits at once, one before a statement joins its
stage. So are the draws that the stage made before the stop (`View.drawn`), which it makes again,
with the same keys, when it runs again.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from .engine.timeline import Plan, Run, read
from .engine.timeline.checkpoints import engine_version, program_digest
from .engine.timeline.plan import name_of
from .engine.timeline.record import declaration, key_of, unit_of
from .program import parts as p
from .program.artifact import Location, SideTable
from .program.checkpoint import Breakpoint, Checkpoint, CheckpointError, Edit, Stop, dumps, loads
from .program.record import Entry

# The kinds of the values that a view shows by default: those that hold a number, a yes/no, an enum
# member, a text or a link, and not a collection or a distribution.
SHOWN = (p.INPUT, p.STATE, p.FORMULA, p.LINK)


@dataclass(frozen=True)
class Log:
    """What a session did (see the module): its breakpoints, each stop at which it waited (the stop
    of hit k is the k-th of the run), and each edit, at the stop of its hit, in order."""

    breakpoints: tuple[Breakpoint, ...] = ()
    stops: tuple[Stop, ...] = ()
    edits: tuple[Edit, ...] = ()


@dataclass(frozen=True)
class Shown:
    """A value at a stop: its path, its value in its declared unit (a number, a yes/no, an enum member,
    a text, a link's member, or `Unavailable` with its reason), its unit (`''` for none), its label
    (None for none), whether an edit can change it (a live stored value), the members of its enum
    (None for a value of no enum), and the title of its member (of an occurrence's value, its
    receiver's; None for none and for a value of the root)."""

    path: str
    value: Any
    unit: str
    label: str | None
    editable: bool
    choices: tuple[str, ...] | None = None
    title: str | None = None


@dataclass(frozen=True)
class View:
    """A stop as a session shows it: the stop (why, the breakpoint, the location that the run stopped
    before, the occurrence and its member, the time, the round, its hit and the stage that runs again
    from its start), the place of that location in the source (None without a side table), the
    stages that run next in the round from the one that stopped, as (occurrence, stage), the values
    asked for, the edits made at this stop, the trace entries of the draws that the stage made
    before the stop (each with its value as the trace holds it), which it makes again with the same
    keys when it runs again, and the title of the stop's member (None for none, and in the setup)."""

    stop: Stop
    where: Location | None
    next: tuple[tuple[str, str], ...]
    values: tuple[Shown, ...]
    edits: tuple[Edit, ...]
    drawn: tuple[Entry, ...] = ()
    title: str | None = None


class Session:
    """One run of a program under a configuration, played through its checkpoints (see the module).

    `breakpoints` are where it stops, or `log` is a log that it plays again, at the log's breakpoints;
    `table` is the program's side table (`napkin.program.artifact.SideTable`), which gives a location
    its place in the source and a value its label. An unknown location, or one in a trigger's body,
    is refused when the session is made (`CheckpointError`), and so is a part that the engine does not
    run (`Outside`), a configuration that the program cannot take, and a log with an edit after its
    last stop or at a hit with no recorded stop.

    - `checkpoint`: the checkpoint at which the run waits, or None;
    - `record`: the record of the run once it reached its end, else None;
    - `stops`: each stop at which the session waited, in order.
    """

    def __init__(self, program, configuration, breakpoints=(), *, table=None, log=None):
        if log is not None and breakpoints:
            raise ValueError('a session that plays a log again stops at the breakpoints of the log')
        log = Log(tuple(breakpoints)) if log is None else log
        self._begin(program, table, Run(Plan.of(program, configuration), log.breakpoints), log)
        self._last = max((stop.hit for stop in log.stops), default=0)
        self._expected = {stop.hit: stop for stop in log.stops}
        for edit in log.edits:
            if edit.hit > self._last:
                raise CheckpointError(f'an edit of the log at the stop {edit.hit}, after its last stop')
            if edit.hit not in self._expected:
                raise CheckpointError(f'an edit of the log at stop {edit.hit} has no recorded stop')
            self._edits_at.setdefault(edit.hit, []).append(edit)

    def _begin(self, program, table, run, log):
        self.program, self.table = program, table if table is not None else SideTable()
        self.breakpoints = tuple(log.breakpoints)
        self._run = run
        self._last, self._expected, self._edits_at = 0, {}, {}
        self._refused = None
        self.checkpoint = self.record = None
        self.stops = []
        self._edits = ()

    @classmethod
    def restored(cls, program, checkpoint, *, configuration=None, table=None):
        """The session that goes on from a checkpoint of a run of `program`, in this process or
        another, waiting at its stop: the run is made again from its saved state. A checkpoint of
        another program or of another version of the engine is refused by name (`CheckpointError`),
        as `napkin.engine.resume` refuses it, and so is one of another configuration than
        `configuration` (when it is given), with the fields that differ."""
        if program_digest(program) != checkpoint.program:
            raise CheckpointError('the checkpoint is of another program: the SHA-256 of its bytes differs')
        if engine_version() != checkpoint.engine:
            raise CheckpointError(
                'the checkpoint was made by another version of the engine: resume it with that version'
            )
        if not checkpoint.saved:
            raise CheckpointError('the checkpoint holds no saved state of the engine')
        if configuration is not None and configuration != checkpoint.configuration:
            differ = [
                item.name
                for item in fields(configuration)
                if getattr(configuration, item.name) != getattr(checkpoint.configuration, item.name)
            ]
            raise CheckpointError(
                f'the checkpoint is of another run: it differs in its {" and ".join(differ)}'
            )
        session = cls.__new__(cls)
        run = Run.restored(Plan.of(program, checkpoint.configuration), checkpoint)
        session._begin(program, table, run, Log(checkpoint.breakpoints))
        session.stops.extend(checkpoint.stops[:-1])
        session._waits(checkpoint)
        return session

    @classmethod
    def load(cls, path, program, *, configuration=None, table=None):
        """The session that goes on from the checkpoint file at `path` (`save`), as `restored`. A
        file that is no checkpoint is refused (`CheckpointError`); one that cannot be read raises
        OSError."""
        checkpoint = loads(Path(path).read_bytes())
        return cls.restored(program, checkpoint, configuration=configuration, table=table)

    # ---- playing ----------------------------------------------------------------------------------

    @property
    def configuration(self):
        """The configuration of the run."""
        return self._run.plan.configuration

    @property
    def log(self):
        """The log of the session so far (`Log`)."""
        return Log(self.breakpoints, tuple(self.stops), self._edits)

    def advance(self):
        """Go on to the next stop, from the start or from the stop at which the run waits, and give
        its checkpoint (also `checkpoint`); or None, once the run reached its end (`record`). A
        session that plays a log passes the stops of the log before its last first, each with the
        log's edits there (see the module)."""
        if self._refused is not None:
            raise CheckpointError(self._refused)
        if self.record is not None:
            raise CheckpointError('the run reached its end: no stop follows')
        found = self._run.resume() if self.checkpoint is not None else self._run.run()
        while isinstance(found, Checkpoint):
            self._waits(found)
            hit = found.stop.hit
            for edit in self._edits_at.get(hit, ()):
                # As the log holds it: a record key in declared units, or an engine name in canonical ones.
                self.checkpoint = self._run.edit(edit.target, edit.value)
            self._edits = self.checkpoint.edits
            if hit >= self._last:
                return self.checkpoint
            found = self._run.resume()
        # A stop of the log after the horizon of this run cannot come, nor one at or after the end of
        # a record that its budget ends: a run stops by its budget where its record does, before any
        # later stop (`program/record.py`, "The budget"). One before them must.
        reached, horizon = (self.stops[-1].hit if self.stops else 0), self.configuration.request.horizon
        crossing = self.configuration.numerics.crossing
        budget = found.failure is not None and found.failure.detail('budget') is not None
        missing = sorted(
            hit
            for hit, stop in self._expected.items()
            if hit > reached and stop.t <= horizon and not (budget and stop.t + crossing >= found.end)
        )
        if missing:
            self._refused = f'the log does not play again: the run ends before its stop {missing[0]}'
            raise CheckpointError(self._refused)
        self.checkpoint, self.record = None, found
        return None

    def _waits(self, checkpoint):
        """The session waits at the stop of a checkpoint, which must be the log's stop of its hit."""
        stop = checkpoint.stop
        expected = self._expected.get(stop.hit)
        if expected is not None and not _same(stop, expected, checkpoint.configuration.numerics.crossing):
            self.checkpoint = None
            self._refused = (
                f'the log does not play again: its stop {stop.hit} is before {expected.at} in '
                f'{expected.owner or "the setup"} at {expected.t:g} h, and the run stops before '
                f'{stop.at} in {stop.owner or "the setup"} at {stop.t:g} h'
            )
            raise CheckpointError(self._refused)
        self.checkpoint, self._edits = checkpoint, checkpoint.edits
        self.stops.append(stop)

    def edit(self, path, value):
        """Give a live stored value a new value at the stop at which the run waits: `path` names it as
        the model does (`depot.request_pump#0.order`, or a record key), and `value` is in its declared
        unit (a number in that unit, an enum member by its name, a yes/no, a text). The engine checks
        it (a stored value, not a parameter or a built-in field of an occurrence, of its type and
        within its bounds, not of a finished occurrence) and refuses one that does not hold
        (`CheckpointError`), with nothing changed. Gives the checkpoint with the edit."""
        self._waiting()
        self.checkpoint = self._run.edit(key_of(self.program, path), value)
        self._edits = self.checkpoint.edits
        return self.checkpoint

    def save(self, path):
        """Write the checkpoint at which the run waits, with its edits, to `path`
        (`napkin.program.checkpoint.dumps`): whole or not at all, through a new file in the same
        folder. `load` goes on from it, in this process or another."""
        data = dumps(self._waiting())
        path = Path(path)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _waiting(self):
        if self.checkpoint is None:
            raise CheckpointError('the session waits at no stop')
        return self.checkpoint

    # ---- showing ----------------------------------------------------------------------------------

    def view(self, paths=None):
        """The stop at which the run waits (`View`), with the values of `paths` (each a path as the
        model names it), or by default the values of the stop's member and of its occurrence (of the
        root, in the setup) that hold a number, a yes/no, an enum member, a text or a link, without
        the built-in fields of the occurrence. A value that the checkpoint's state holds is read
        there; any other (a formula, a rate) from the record so far at the time of the stop. A path
        that names no value is a KeyError."""
        checkpoint = self._waiting()
        stop, state = checkpoint.stop, checkpoint.state
        keys = [key_of(self.program, path) for path in (self.shown_paths(stop) if paths is None else paths)]
        held = dict(state.values)
        readings = iter(
            read(checkpoint.record, self.program, [key for key in keys if name_of(key) not in held], [stop.t])
        )
        active = {occurrence.id: occurrence.active for occurrence in state.occurrences}
        values = []
        for key in keys:
            if name_of(key) in held:
                # The state holds canonical units, and a distribution in its own unit.
                value, (unit, scale) = held[name_of(key)], unit_of(self.program, key)
                if isinstance(value, int | float) and not isinstance(value, bool):
                    value = value / scale
            else:
                reading = next(readings)
                value, unit = reading.values[0], reading.unit
            values.append(self._shown(key, value, unit, active))
        edits = tuple(edit for edit in checkpoint.edits if edit.hit == stop.hit)
        drawn = tuple(
            entry
            for entry in checkpoint.record.entries('draw')
            if (entry.t, entry.round, entry.owner) == (stop.t, stop.round, stop.owner)
        )
        return View(
            stop, self.where(stop.at), state.pending, tuple(values), edits, drawn, self.title(stop.member)
        )

    def where(self, origin):
        """The place of a location in the source (`napkin.program.artifact.Location`: its kind, its
        file, line and column, its label), or None when the side table does not have it."""
        try:
            return self.table.location(origin)
        except KeyError:
            return None

    def title(self, owner):
        """The title of a member by its id, or of an occurrence's receiver (`depot.request_pump#0` is of
        `depot`), from the side table; None for none, and for the root (`''`)."""
        member = owner.rsplit('#', 1)[0].rpartition('.')[0] if '#' in owner else owner
        return self.table.title(member) if member else None

    def shown_paths(self, stop):
        """The paths that a view shows by default at a stop (see `view`)."""
        program = self.program
        if not stop.owner:
            return [value.name for value in program.root if value.kind in SHOWN]
        template = program.member(stop.member)[0]
        found = [f'{stop.member}.{value.name}' for value in template.values if value.kind in SHOWN]
        event = template.part(stop.owner.rsplit('#', 1)[0].rsplit('.', 1)[1])
        for value in (*event.params, *event.locals):
            if isinstance(value, p.Value) and value.kind in SHOWN:
                found.append(f'{stop.owner}.{value.name}')
        return found

    def _shown(self, key, value, unit, active):
        """A value at a stop as a view shows it (`Shown`)."""
        part, fixed = _declared(self.program, key)
        location = self.where(part.origin) if part is not None else None
        # A value of an occurrence that has not started, or that finished, takes no edit.
        live = active.get(key.owner, False) if '#' in key.owner else True
        editable = (
            isinstance(part, p.Value) and part.kind == p.STATE and not fixed and len(key.steps) == 1 and live
        )
        choices = None
        if isinstance(getattr(part, 'type', None), p.EnumType):
            choices = tuple(self.program.enum(part.type.enum).members)
        label = location.label if location is not None else None
        return Shown(name_of(key), value, unit, label, editable, choices, self.title(key.owner))


def _same(stop, expected, crossing):
    """Whether a stop is the log's stop: the same in all but its time, which is within `crossing` of
    the log's, the time between two moments that the engine tells apart."""
    return replace(stop, t=expected.t) == expected and abs(stop.t - expected.t) <= crossing


def _declared(program, key):
    """(the part of the program that declares the value at a key, `declaration`: a value, a solver's
    own unknown, the store of an endpoint or a ledger, a flow or a leg, the event of a built-in
    occurrence field, or None for a status display; whether it is a parameter or a built-in field of an occurrence,
    which its start gives). A key that names no value is a KeyError."""
    found = declaration(program, key)
    part = found.part if found.what != 'status' else None
    return part, found.what in ('parameter', 'builtin')


def play(program, configuration, log):
    """The record of the run of a log (see the module): the program under the configuration, stopped
    at each hit of the log's breakpoints, edited there by the log's edits of that hit, and resumed, to
    the end; each stop of the log is checked, and every later stop passes. Raises `CheckpointError`
    for a log that does not play again."""
    session = Session(program, configuration, log=log)
    while session.advance() is not None:
        pass
    return session.record


__all__ = ['Log', 'Session', 'Shown', 'View', 'play']
