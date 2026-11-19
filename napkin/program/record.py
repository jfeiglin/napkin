"""The record of a run: the interface that the engine, the oracle and the report share.

One run gives one record (D9). It holds, for each recorded value, its history as pieces that can be
read at any time; the trace of what happened; the failure that stopped the run, if one did; and a
manifest of what it holds (R-A4a-07, R-A4a-08).

- **A value** is named by a `Key`: its owner (a member's id, `''` for the root, or an occurrence's
  id such as `tank.receive#0`, the receiver's id, the event and the number of the start on that
  receiver from 0) and the steps from the owner to it, as a path writes them (`('delivery',
  'actual_rate')`, `('water', 'outflow', 'actual_rate')`).
- **A history** is a list of pieces in time order. From its time on, until the next piece, a piece
  reads `value + rate * (time - t)`: a constant has rate 0, a stored quantity between moments the
  rate of its line. A curved piece has a `Curve` instead, a Chebyshev series that the value
  follows over the piece, so a reader needs nothing of the engine that made it. A jump is a new
  piece at the same time, and a read at a time gives the last piece at or before it, so a read at
  a moment sees what its last round committed. A value that could not be read holds `Unavailable`
  with the reason (D7). Numbers are in the canonical unit of the value's dimension (a literal
  `q(n, unit)` is n times the unit's scale), times in hours.
- **The trace** has one entry for each start, finish, stage commit, firing, draw, choice, move, solve,
  pause and failure, in the order in which they happened, with the round of its time (0 is the
  setup at time 0, then 1, 2, ... at each time; a firing is in the round whose settled results it
  reads), and the member or occurrence that executes it. Its part is the origin of the event for a
  start and a finish, of the step for a commit, of the trigger for a firing, of the statement for
  a move and a pause, of the solver for a solve, and the site for a draw and a choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .refs import Number

KINDS = ('start', 'finish', 'commit', 'fire', 'draw', 'choice', 'move', 'solve', 'pause', 'failure')


@dataclass(frozen=True)
class Key:
    """A recorded value: its owner and the steps from the owner to it."""

    owner: str
    steps: tuple[str, ...]


@dataclass(frozen=True)
class Unavailable:
    """A value that could not be read, with the reason: a report can show it, and a model read of it
    raises the reason (D7)."""

    reason: str


@dataclass(frozen=True)
class Curve:
    """The shape of a curved piece over `length` hours from its time: the Chebyshev series
    `coefficients` (of T0, T1, ...) in u = 2 * elapsed / length - 1, which runs from -1 at the time
    of the piece to 1 at its end. The piece reads its value plus the increase of the series since
    its time (`increase`)."""

    length: Number
    coefficients: tuple[float, ...]

    def _series(self, u):
        # Clenshaw's recurrence: b_k = c_k + 2 u b_(k+1) - b_(k+2), and the sum is c_0 + u b_1 - b_2.
        after = latest = 0.0
        for coefficient in reversed(self.coefficients[1:]):
            latest, after = coefficient + 2.0 * u * latest - after, latest
        return self.coefficients[0] + u * latest - after if self.coefficients else 0.0

    def increase(self, elapsed):
        """The increase of the series from the time of the piece to `elapsed` hours after it."""
        u = 2.0 * float(elapsed) / float(self.length) - 1.0
        return self._series(u) - self._series(-1.0)


@dataclass(frozen=True)
class Piece:
    """From time `t` until the next piece: `value + rate * (time - t)`, or, for a piece with a
    `curve`, `value` plus the increase of its curve since `t`."""

    t: Number
    value: Any
    rate: Number = 0
    curve: Curve | None = None

    def at(self, time):
        """The value of the piece at a time at or after its own."""
        if isinstance(self.value, (bool, str, Unavailable)):
            return self.value
        if self.curve is not None:
            return self.value + self.curve.increase(time - self.t)
        return self.value if self.rate == 0 else self.value + self.rate * (time - self.t)


@dataclass(frozen=True)
class History:
    """The pieces of one value, in time order."""

    key: Key
    pieces: tuple[Piece, ...]

    def at(self, time):
        """The value at a time: the last piece at or before it. A value that did not exist yet is a
        LookupError."""
        found = None
        for piece in self.pieces:
            if piece.t > time:
                break
            found = piece
        if found is None:
            raise LookupError(f'{self.key} has no value at {time} h')
        return found.at(time)


@dataclass(frozen=True)
class Entry:
    """One line of the trace: the time, the round, the kind (one of `KINDS`), the origin of the part,
    the member or occurrence that executes it, and what it says (`('value', 'FIXED')` for a draw,
    `('amount', 3)` for a move, `('message', ...)` for a failure)."""

    t: Number
    round: int
    kind: str
    part: str
    owner: str = ''
    details: tuple[tuple[str, Any], ...] = ()

    def detail(self, name):
        """A detail of the entry, or None."""
        return next((value for found, value in self.details if found == name), None)


@dataclass(frozen=True)
class Manifest:
    """What a record holds: the horizon, and every value (`everything`) or only those of `keys`."""

    horizon: Number
    everything: bool = True
    keys: tuple[Key, ...] = ()

    def holds(self, key, time):
        """Whether the record can serve a read of a value at a time."""
        return time <= self.horizon and (self.everything or key in self.keys)


@dataclass(frozen=True)
class Record:
    """The record of one run."""

    manifest: Manifest
    histories: tuple[History, ...] = ()
    trace: tuple[Entry, ...] = ()
    failure: Entry | None = None

    def history(self, key):
        """The history of a value, or KeyError. The index by key is made on the first read and kept
        beside the record, which cannot change."""
        index = self.__dict__.get('_index')
        if index is None:
            index = {history.key: history for history in reversed(self.histories)}
            object.__setattr__(self, '_index', index)
        return index[key]

    def value(self, key, time):
        """The value of a key at a time."""
        return self.history(key).at(time)

    def entries(self, kind=None, part=None):
        """The entries of the trace of a kind, of a part, or both."""
        return tuple(
            entry
            for entry in self.trace
            if (kind is None or entry.kind == kind) and (part is None or entry.part == part)
        )
