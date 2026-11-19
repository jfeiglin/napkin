"""A checkpoint: a run stopped at a breakpoint, as data that a fresh process loads, inspects and
resumes (PLAN, change 15).

A caller sets breakpoints at locations of the compiled program (`Breakpoint`): an event, a stage or a
statement, named by its origin (`depot.request_pump`, `depot.request_pump.step[0]`,
`depot.request_pump.step[0].do[0]`, `setup[0]`), for every occurrence or for one member or one
occurrence. The engine stops before the stage or the statement and gives a `Checkpoint`:

- `stop` (`Stop`): why and where it stopped, which entity and occurrence, the number of the stop
  among the run's hits of its breakpoints (`hit`), and what runs next: the stage that runs again from
  its start, or the setup. A stop inside a stage discards nothing that the stage committed, since a
  stage commits only at its end; what it drew before the stop is in the trace and is drawn again with
  the same keys, so it is traced once.
- `state` (`State`): the logical state of the run at the stop: each stored value, input, link, draw
  and captured setting with its value now (a store of a connected set at its value on its line or
  curve now), the occurrences and where each waits, the stages that run next in the round, and the
  state of each trigger (armed, when it rearms, how often it fired: the number that keys the draws of
  its next firing).
- `record`: the record so far, whose trace ends with the `pause` entry of the stop.
- `program` and `engine`: the SHA-256 of the program's canonical bytes (`canonical.py`) and the
  version of the engine (the SHA-256 of its code), `configuration` and `breakpoints`: what the run
  ran with.

**Exact resume** (the owner's rule): with the same program, engine version, numerical settings and
seed, on one platform, a stopped and resumed run gives the same recorded values, draw results, event
times and event order as the run straight through, and a breakpoint alone never changes which
branch fires. The engine resumes a run that stopped in its own process in place, and a checkpoint
in a fresh process by running the program again to the stop, where the state and the record must
equal the checkpoint's (`napkin/engine/timeline/checkpoints.py` says why). A checkpoint of another
program or engine version is refused by name (`CheckpointError`).

**The representation** (`dumps`, `loads`) is text: a first line `napkin checkpoint 1`, then one JSON
value. A JSON array is a tuple; a record of the program package is an object with its class's name
under `"$"` and its fields by name (`{"$": "Piece", "t": 0.0, "value": 2.5, "rate": 0.0, "curve":
null}`); a float is a JSON number, which reads back to the same float, except a float that JSON
cannot hold, `{"float": "inf"}`, `"-inf"` or `"nan"`; a fraction is `{"fraction": [n, d]}`. Only the
records named in `RECORDS` are read, so loading builds no other object. `encode` and `decode` give
the JSON of any value made of these, such as a record.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields, is_dataclass
from fractions import Fraction
from typing import Any

from . import config, parts, record, refs

HEADER = 'napkin checkpoint 1'


class CheckpointError(ValueError):
    """A checkpoint that cannot be read or resumed here, with the reason."""


@dataclass(frozen=True)
class Breakpoint:
    """A location of the compiled program at which a run stops: the origin of an event (before each
    of its stages), of a stage, or of a statement (before it runs, inside its stage), for every
    occurrence (`owner` empty) or for one member or one occurrence (`depot.request_pump#0`)."""

    at: str
    owner: str = ''


@dataclass(frozen=True)
class Stop:
    """Why and where a run stopped: the breakpoint, the location that it stopped before (a stage or a
    statement), the occurrence (`''` in the setup) and its member, the time and the round, the number
    of the stop among the run's hits of its breakpoints (from 1), and what runs next (`next`): the
    stage, by its origin, that runs again from its start, or `setup`."""

    why: str
    breakpoint: Breakpoint
    at: str
    owner: str
    member: str
    t: float
    round: int
    hit: int
    next: str


@dataclass(frozen=True)
class Occurrence:
    """An occurrence at a stop: its id, member and event, when it started, the step that it is at
    (from 0), when that step is due (None at a gate or once it finished), whether it waits at a gate,
    and whether it is active."""

    id: str
    member: str
    event: str
    started: float
    step: int
    due: float | None
    waiting: bool
    active: bool


@dataclass(frozen=True)
class Trigger:
    """A trigger at a stop (`tank.refill.when[0]`): whether it is armed, when it rearms after a `reset
    after` and when a visit cannot fire it (None for none), and how often it fired."""

    key: str
    armed: bool
    rearm_at: float | None
    blocked_at: float | None
    firings: int


@dataclass(frozen=True)
class State:
    """The logical state of a run at a stop: `values`, (engine name, value) of each stored value,
    input, link, draw, captured setting and distribution-valued value, in the order of the plan;
    `occurrences`, in their order of creation; `pending`, (occurrence, stage) of the stages that run
    next in the round, from the one that stopped; `triggers`, in the order of the plan."""

    values: tuple[tuple[str, Any], ...]
    occurrences: tuple[Occurrence, ...]
    pending: tuple[tuple[str, str], ...]
    triggers: tuple[Trigger, ...]

    def value(self, name):
        """The value of an engine name at the stop, or KeyError."""
        for found, value in self.values:
            if found == name:
                return value
        raise KeyError(name)


@dataclass(frozen=True)
class Checkpoint:
    """A run stopped at a breakpoint (see the module)."""

    program: str
    engine: str
    configuration: config.Configuration
    breakpoints: tuple[Breakpoint, ...]
    stop: Stop
    state: State
    record: record.Record


# The records that a checkpoint is made of, by the name that the representation gives each.
RECORDS = {
    cls.__name__: cls
    for cls in (
        Breakpoint,
        Stop,
        Occurrence,
        Trigger,
        State,
        Checkpoint,
        config.Configuration,
        config.Request,
        config.InputValue,
        config.Quantity,
        config.Controller,
        config.Pick,
        config.Limits,
        config.Budgets,
        config.Numerics,
        parts.Unit,
        refs.Distribution,
        refs.EnumValue,
        record.Key,
        record.Unavailable,
        record.Curve,
        record.Piece,
        record.History,
        record.Entry,
        record.Manifest,
        record.Record,
    )
}


def _data(value):
    """The JSON data of a value (see the module)."""
    if type(value).__module__ == 'numpy' and hasattr(value, 'item'):
        value = value.item()  # a number or a yes/no of numpy, as Python's
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {'float': repr(value)}
    if isinstance(value, Fraction):
        return {'fraction': [value.numerator, value.denominator]}
    if isinstance(value, tuple | list):
        return [_data(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        name = type(value).__name__
        if RECORDS.get(name) is not type(value):
            raise TypeError(f'a checkpoint holds no {name}')
        return {'$': name, **{item.name: _data(getattr(value, item.name)) for item in fields(value)}}
    raise TypeError(f'a checkpoint holds no {type(value).__name__}')


def _value(data):
    """The value of JSON data (see the module)."""
    if isinstance(data, list):
        return tuple(_value(item) for item in data)
    if not isinstance(data, dict):
        return data
    if 'float' in data:
        return float(data['float'])
    if 'fraction' in data:
        numerator, denominator = data['fraction']
        return Fraction(numerator, denominator)
    cls = RECORDS.get(data.get('$'))
    if cls is None:
        raise CheckpointError(f'a checkpoint holds no record {data.get("$")!r}')
    return cls(**{name: _value(item) for name, item in data.items() if name != '$'})


def encode(value):
    """The JSON text of a value of the program package (see the module)."""
    return json.dumps(_data(value), allow_nan=False, separators=(',', ':'))


def decode(text):
    """The value of JSON text that `encode` gave."""
    return _value(json.loads(text))


def dumps(checkpoint):
    """The bytes of a checkpoint: the header line, then its JSON."""
    return f'{HEADER}\n{encode(checkpoint)}'.encode()


def loads(data):
    """The checkpoint of bytes that `dumps` gave; other bytes are refused by name."""
    head, _, body = bytes(data).partition(b'\n')
    if head != HEADER.encode():
        words = head.split()
        if words[:2] == [b'napkin', b'checkpoint']:
            raise CheckpointError(
                f'a checkpoint of format {b" ".join(words[2:]).decode(errors="replace")}; this napkin reads '
                f'format {HEADER.split()[-1]}'
            )
        raise CheckpointError('not a napkin checkpoint: its first line is not "napkin checkpoint"')
    try:
        found = decode(body.decode())
    except (ValueError, TypeError, KeyError) as problem:
        raise CheckpointError(f'a damaged checkpoint: {problem}') from None
    if not isinstance(found, Checkpoint):
        raise CheckpointError('not a napkin checkpoint: it holds no checkpoint')
    return found
