"""The compiled program as a file: what a fresh process loads to run a model without the parser.

An artifact holds a program in its canonical bytes (`canonical.py`) and the program's side table,
which the compiler makes beside it (`napkin.model.lowering.side_table`). A loader gives back a
program equal to the one saved, with the same bytes, so the engine runs it to the same record.

- **The side table** maps each part of the program that has an origin (`grinder.refill.step[0]`) to
  its `Location`: its kind (`EXECUTABLE` are the kinds at which a run can stop: an event, a stage, a
  gate, a trigger and each statement and case), its name, its place in the source (file, line and
  column, from 1) and, for a value, a flow or any part with a text, its label (the first text under
  it) and its evidence (each record that it rests on, with its content). Each member written by
  hand has a location of the kind `member` under its id, and a member's title (`title "DC Water"`,
  the name that reports and playback give it) is at its location: an entity written once's at its
  template's (`SideTable.title`). The table is outside the program's identity: a label, a title, a
  record or a moved line changes the table and leaves the program's bytes, its digest, the model's
  hash and the key of a stored run.
- **The identity** of a compiled program is its digest (`Artifact.digest`), the SHA-256 of its
  canonical bytes: a checkpoint names its program by it.

The file is a header of two lines, then two sections, each a line with its size and its bytes:

    napkin program 3               the name of the format and its version
    language 0.2.1                 the version of the language of the program
    program <size> <sha256>        the program's canonical bytes, and their digest
    <the program's bytes>
    table <size>                   the side table's canonical bytes
    <the table's bytes>

The version rule. `FORMAT_VERSION` names the layout and the records of the contract that the bytes
hold (`RECORDS`): it goes up with each change of either, a field of a record added, removed, renamed
or moved included. `LANGUAGE_VERSION` names the meaning of a program, and goes up with each change of
what a program computes; the hash of a model covers it (`napkin.model.identity`). A loader reads only
its own format and language and refuses any other by name, never with a guess; the decoder also
refuses a record whose fields are not this napkin's, so a change that forgets the version is
refused too. The remedy is always to compile the model again.

Each refusal is an `ArtifactError` with its code: `not_a_program` (the bytes do not start as a
napkin program), `format_version`, `language_version` (another version than this napkin's), and
`damaged` (a header line, a size or a digest that does not hold, or bytes that are no program or no
side table).
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, fields, is_dataclass
from functools import cached_property
from pathlib import Path

from . import config, parts, record, refs
from .canonical import Malformed, decode, program_bytes, value_bytes

FORMAT = b'napkin program'
# 3: a location has its title (PLAN, change 19 after G0).
FORMAT_VERSION = 3
# The version of the language: what a program means. A model's identity changes with it, never with
# the version of the package.
LANGUAGE_VERSION = '0.2.1'

# The kind of each part of a program that has an origin, by its record.
KINDS = {
    parts.Template: 'template',
    parts.Value: 'value',
    parts.Endpoint: 'endpoint',
    parts.Flow: 'flow',
    parts.Event: 'event',
    parts.After: 'stage',
    parts.Until: 'gate',
    parts.Trigger: 'trigger',
    parts.Assign: 'assign',
    parts.Move: 'move',
    parts.Start: 'start',
    parts.If: 'if',
    parts.Switch: 'switch',
    parts.Case: 'case',
    parts.Solver: 'solver',
    parts.Binding: 'binding',
    parts.Constraint: 'constraint',
    parts.Objective: 'objective',
    parts.Status: 'status',
    parts.StatusCase: 'rating',
    parts.Assert: 'assert',
}
# The kinds of the locations at which a run can stop.
EXECUTABLE = ('event', 'stage', 'gate', 'trigger', 'assign', 'move', 'start', 'if', 'switch', 'case')
# The kind of the location of a member written by hand, under its id: no record of the program has it.
MEMBER = 'member'


class ArtifactError(ValueError):
    """Bytes that this napkin does not load as a compiled program: the code and the message."""

    def __init__(self, code, message):
        super().__init__(f'{message} [{code}]')
        self.code, self.message = code, message


# ---- the side table -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """A record that a part rests on: its name (`''` for a record written in place under the part),
    its kind (`source`, `assumption`, ...), its explanation, the IDs of the library that it rests on
    (`('assumption', 'A-TIMING')`) and its claims, each the ID of a claim and the key of one of its
    data (`''` for none)."""

    name: str
    kind: str
    explanation: str
    rests_on: tuple[tuple[str, str], ...] = ()
    claims: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Location:
    """A part of the program as its source writes it: its origin, its kind (`KINDS`, or `MEMBER`), its
    name (`''` for a statement; a case's member), its file (`''` for a text with no file), its line
    and its column (from 1, 0 for none), its label (the first text under it, or None), its evidence
    and, for a member or a template, its title (or None)."""

    origin: str
    kind: str
    name: str = ''
    file: str = ''
    line: int = 0
    column: int = 0
    label: str | None = None
    evidence: tuple[Evidence, ...] = ()
    title: str | None = None


@dataclass(frozen=True)
class SideTable:
    """The locations of a program's parts, in the order of the program."""

    locations: tuple[Location, ...] = ()

    @cached_property
    def _index(self):
        found = {}
        for location in self.locations:
            found.setdefault(location.origin, location)
        return found

    def location(self, origin):
        """The location of a part by its origin, or KeyError."""
        return self._index[origin]

    def title(self, member):
        """The title of a member by its id (of an entity written once: its template's), or None."""
        found = self._index.get(member)
        return None if found is None else found.title

    def executable(self):
        """The locations at which a run can stop (`EXECUTABLE`), in the order of the program."""
        return tuple(location for location in self.locations if location.kind in EXECUTABLE)


def _has_origin(value):
    return is_dataclass(value) and type(value) in KINDS


def origins(program):
    """Each part of a program that has an origin, by its origin, in the order of the program: its
    templates and each of their parts, then the root's values, the setup's statements and the root's
    assertions. A breakpoint names a part by its origin, and this finds the part."""
    found = {}

    def walk(part):
        found.setdefault(part.origin, part)
        for item in fields(part):
            value = getattr(part, item.name)
            for each in value if isinstance(value, tuple) else (value,):
                if _has_origin(each):
                    walk(each)

    for part in (*program.templates, *program.root, *program.setup, *program.asserts):
        walk(part)
    return found


def kind_of(part):
    """The kind of a part of a program (`KINDS`)."""
    return KINDS[type(part)]


# ---- the file -----------------------------------------------------------------------------------


def _records(*modules):
    return {
        kind.__qualname__: kind
        for module in modules
        for kind in vars(module).values()
        if isinstance(kind, type) and is_dataclass(kind) and kind.__module__ == module.__name__
    }


@dataclass(frozen=True)
class Artifact:
    """A compiled program and its side table."""

    program: parts.Program
    table: SideTable = SideTable()

    @cached_property
    def digest(self):
        """The identity of the program: the SHA-256 of its canonical bytes, in hexadecimal."""
        return hashlib.sha256(program_bytes(self.program)).hexdigest()

    def data(self):
        """The bytes of the file (see the module)."""
        program, table = program_bytes(self.program), value_bytes(self.table)
        return b''.join(
            (
                FORMAT + b' %d\n' % FORMAT_VERSION,
                b'language ' + LANGUAGE_VERSION.encode() + b'\n',
                b'program %d %s\n' % (len(program), hashlib.sha256(program).hexdigest().encode()),
                program,
                b'table %d\n' % len(table),
                table,
            )
        )

    def save(self, path):
        """Write the file at `path`."""
        Path(path).write_bytes(self.data())


class _File:
    """A cursor over the bytes of a file."""

    def __init__(self, data):
        self.data, self.at = data, 0

    def line(self, what):
        end = self.data.find(b'\n', self.at)
        if end < 0:
            raise ArtifactError('damaged', f'the file ends before its {what} line')
        found, self.at = self.data[self.at : end], end + 1
        return found

    def section(self, name, words):
        """The words of a section's line after its name, and the bytes of the section."""
        written = self.line(name).split(b' ')
        if written[0] != name.encode() or len(written) != 1 + words or not written[1].isdigit():
            raise ArtifactError(
                'damaged', f'the {name} line is not "{name} <size>": {_shown(b" ".join(written))}'
            )
        end = self.at + int(written[1])
        if end > len(self.data):
            raise ArtifactError('damaged', f'the file ends inside its {name}')
        found, self.at = self.data[self.at : end], end
        return written[2:], found


def _shown(data):
    """The start of some bytes, as a text for a message."""
    return repr(data[:40].decode('utf-8', 'replace'))


def loads(data):
    """The artifact of the bytes of a file (see the module). Raises `ArtifactError`."""
    data = bytes(data)
    file = _File(data)
    first = data[: data.find(b'\n')] if b'\n' in data else data
    if not first.startswith(FORMAT + b' '):
        raise ArtifactError(
            'not_a_program',
            f'this is no napkin program: one starts with "napkin program", this with {_shown(first)}',
        )
    version = file.line('format')[len(FORMAT) + 1 :]
    if version != str(FORMAT_VERSION).encode():
        raise ArtifactError(
            'format_version',
            f'a napkin program of format {_shown(version)}: this napkin reads format {FORMAT_VERSION}; '
            'compile the model again',
        )
    language = file.line('language')
    if not language.startswith(b'language '):
        raise ArtifactError('damaged', f'the second line names the language, not {_shown(language)}')
    language = language[len(b'language ') :].decode('utf-8', 'replace')
    if language != LANGUAGE_VERSION:
        raise ArtifactError(
            'language_version',
            f'a program of the language {language}: this napkin runs the language {LANGUAGE_VERSION}; '
            'compile the model again',
        )
    (digest,), program_data = file.section('program', 2)
    if hashlib.sha256(program_data).hexdigest().encode() != digest:
        raise ArtifactError('damaged', 'the bytes of the program do not have the digest of its line')
    _, table_data = file.section('table', 1)
    if file.at != len(data):
        raise ArtifactError('damaged', 'bytes follow the side table')
    program, table = (
        _value(program_data, parts.Program, 'program'),
        _value(table_data, SideTable, 'side table'),
    )
    return Artifact(program, table)


def _value(data, kind, what):
    try:
        found = decode(data, RECORDS)
    except Malformed as error:
        raise ArtifactError('damaged', f'the {what} is damaged: {error}') from None
    if type(found) is not kind:
        raise ArtifactError('damaged', f'the {what} section holds no {what}')
    return found


def load(path):
    """The artifact of a file. Raises `ArtifactError`, or OSError for a file that cannot be read."""
    return loads(Path(path).read_bytes())


def value_of(data):
    """A value of the contract (a program, a configuration, a record, a side table, ...) from its
    canonical bytes (`canonical.value_bytes`). Raises `canonical.Malformed`."""
    return decode(data, RECORDS)


# The records of the contract, by their names: what the bytes of a file may hold.
RECORDS = _records(parts, refs, config, record, sys.modules[__name__])
