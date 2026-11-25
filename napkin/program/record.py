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
- **The trace** has one entry for each start, finish, stage commit, firing, draw, move, solve, edit,
  pause and failure, in the order in which they happened, with the round of its time (0 is the
  setup at time 0, then 1, 2, ... at each time; a firing is in the round whose settled results it
  reads), and the member or occurrence that executes it. Its part is the origin of the event for a
  start and a finish, of the step for a commit, of the trigger for a firing, of the statement for
  a move, of the solver for a solve, the site for a draw, and for an edit and a pause the stage or
  the statement before which a breakpoint stopped the run (`napkin/program/checkpoint.py`); an edit
  has the details `breakpoint`, `target`, `old` and `new`.
- **A near-tie** (change 10) is the detail `near` of an entry that was decided within tolerance of
  its boundary: one (origin, comparison, difference, tolerance) for each comparison of a trigger, a
  guard, an `if`, the guard of a case, a gate or a split of who is served whose sides differed by no
  more than the tolerance of what they read, in canonical units (`Record.near_ties`). A firing and a
  commit carry it in their own entry; a trigger that came within tolerance and did not fire, a
  false guard of a stage that ran nothing, a released gate and a settling have an entry of their own
  for it (`miss`, `skip`, `release`, `settle`). For a switch or a bound grouped with a scheduled
  moment, a `contact` entry gives its located time and its signed difference from the moment in
  hours. A contact exactly at the moment has difference zero.
- **The end.** A run that fails, or that a breakpoint stops, ends its record there: the failure, or
  the `pause` entry that ends its trace, says when (`Record.stop`). A value at a later time is
  `Unavailable` with the reason, on every path that reads one (`Record.value`, and the engine's
  reader), and never the value that the record held at the stop.
- **What a record holds** (`Record.unavailable`, the one rule that every reader follows): the values
  that its manifest names (every value, or the keys of its request), from 0 h to its end. A store's
  ledger `external` (`tank.water.external`, what edits brought into it from outside) belongs to the
  books of the store: a record that holds the store holds its ledger too, and a request may name the
  ledger alone. A ledger has a piece at each edit that changed its store, from the first: before it,
  nothing came from outside, and it reads 0. A record may keep the histories of other values, which
  a formula that it holds reads (the engine's reader evaluates the formula from them); it holds them
  for that, not for a read of their own. A value that the record does not hold is `Unavailable` with
  the reason, never a default.
- **One rule, as the run goes.** A record holds the pieces that its run made up to its end, and its
  pieces up to a time are settled once the run is past that time: a ledger begins at its first edit,
  the values of an occurrence at its start, and no later edit or start adds a piece before its own
  time; a piece that starts at its end holds its value there, since nothing of the record follows
  it. The histories of a request are in key order. A record keeps the histories that its
  requested values read under the definitions and occurrences of its trace
  (`engine/timeline/record.requested`). A run past its budget stops where its record ends,
  before any later stop.
- **The budget** (`Record.within`, R-A4a-07): Count the trajectory pieces and stock postings of
  the requested values. A record can hold one extra exact-balance point per stock at the cutoff.
  A record that would exceed the budget ends at the time of the first counted piece that
  does not fit, with a failure entry there that names the budget (the detail `budget`): it holds the
  values before that time, and from it on every value is `Unavailable` with that reason. Only the
  requested values use the budget. A run whose record so far would exceed its budget at a stop
  ends there by its budget, and gives no checkpoint (`napkin/engine/timeline/checkpoints.py`): a run
  stops by its budget where its record does, before any later stop.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from ..core.units import rational
from .refs import Number

KINDS = (
    'start',
    'finish',
    'commit',
    'fire',
    'draw',
    'move',
    'solve',
    'solver_reads',  # A cached answer whose conditional inputs changed.
    'edit',
    'pause',
    'failure',
    # Near-ties that no other entry carries, each written only with its `near` detail.
    'miss',
    'skip',
    'release',
    'settle',
    'contact',
    'rate_unresolved',  # A committed step whose explicit-time input could not be bounded.
)


@dataclass(frozen=True)
class Key:
    """A recorded value: its owner and the steps from the owner to it."""

    owner: str
    steps: tuple[str, ...]

    def __str__(self):
        """The path of the value, as a caller writes it (`tank.water`, `tank.receive#0.level`)."""
        return '.'.join((self.owner, *self.steps) if self.owner else self.steps)

    @property
    def store(self):
        """The key of the store whose ledger this key names (`tank.water` of `tank.water.external`),
        or None for a key that names no ledger."""
        if len(self.steps) >= 2 and self.steps[-1] == 'external':
            return Key(self.owner, self.steps[:-1])
        return None


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
        if isinstance(self.value, Fraction):
            # Keep a posted remainder until the public value at the requested time is rounded.
            if self.curve is not None:
                increase = rational(self.curve.increase(time - self.t))
            elif self.rate:
                increase = rational(self.rate) * (rational(time) - rational(self.t))
            else:
                increase = 0
            return float(self.value + increase)
        if self.curve is not None:
            return self.value + self.curve.increase(time - self.t)
        return self.value if self.rate == 0 else self.value + self.rate * (time - self.t)


@dataclass(frozen=True)
class BalancePoint(Piece):
    """An extra held point that shows the physical balance of a stock at the record cutoff."""


@dataclass(frozen=True)
class History:
    """The pieces of one value, in time order."""

    key: Key
    pieces: tuple[Piece, ...]

    def charged_pieces(self):
        """Count the trajectory and posting pieces. A final balance point is free."""
        if self.pieces and isinstance(self.pieces[-1], BalancePoint):
            return len(self.pieces) - 1
        return len(self.pieces)

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
class ChangeHistory(History):
    """A stored value read by elapsed: its creation time, then the times of the commits that
    changed it. Two commits at one time can restore the original balance or displayed value."""

    changes: tuple[Number, ...]


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

    comparison_factor: float = 1e-9
    comparison_scales: tuple[tuple[str, float], ...] = ()
    # First committed installation at which each mixed time-dependent rate was outside the pulse guard.
    unchecked_time_rates: tuple[tuple[str, Number], ...] = ()

    def names(self, key):
        """Whether a record with this manifest holds the value of a key: every value, or a key of its
        request; the ledger of a store with the store (its books)."""
        return self.everything or key in self.keys or (key.store is not None and key.store in self.keys)

    def holds(self, key, time):
        """Whether the record can serve a read of a value at a time, from 0 h to the horizon."""
        return 0 <= time <= self.horizon and self.names(key)


@dataclass(frozen=True)
class Record:
    """The record of one run."""

    manifest: Manifest
    histories: tuple[History, ...] = ()
    trace: tuple[Entry, ...] = ()
    failure: Entry | None = None

    @property
    def rate_guard_note(self):
        """The number of distinct rate settings outside the explicit-time guard in this record."""
        count = len(self.manifest.unchecked_time_rates)
        noun = 'setting' if count == 1 else 'settings'
        return (
            f'The explicit-time rate check excluded {count} time-dependent {noun} with state or lookup reads.'
        )

    def history(self, key):
        """The history that the record keeps of a value, or KeyError: what a reader evaluates a held
        value from (a held value is read with `value`). The index by key is made on the first read and
        kept beside the record, which cannot change."""
        index = self.__dict__.get('_index')
        if index is None:
            index = {history.key: history for history in reversed(self.histories)}
            object.__setattr__(self, '_index', index)
        return index[key]

    @property
    def stop(self):
        """The entry that ends the record before its horizon: the failure, or the `pause` of a stop
        at a breakpoint, which ends the trace; None for a run to its horizon."""
        if self.failure is not None:
            return self.failure
        if self.trace and self.trace[-1].kind == 'pause':
            return self.trace[-1]
        return None

    @property
    def end(self):
        """The time to which the record reaches: the time of its stop (for a stop by the budget, the
        time before which it holds its values), or the horizon."""
        stop = self.stop
        return self.manifest.horizon if stop is None else stop.t

    def stopped(self):
        """Why the record ends before its horizon (see the module), or None."""
        stop = self.stop
        if stop is None:
            return None
        if stop.kind == 'failure' and stop.detail('budget') is not None:
            return f'the record stops at {float(stop.t):g} h: {stop.detail("message")}'
        if stop.kind == 'failure':
            return f'the run failed at {float(stop.t):g} h: {stop.detail("message") or "the run failed"}'
        return (
            f'the run stopped at {float(stop.t):g} h at the breakpoint {stop.detail("breakpoint")}, '
            f'before {stop.part}'
        )

    def after(self, time):
        """`Unavailable` with the reason for a time after the end of a record that stopped early (from
        the end on, for a stop by the budget), or None for a time that it reaches."""
        stop = self.stop
        if stop is None or time < stop.t or (time == stop.t and stop.detail('budget') is None):
            return None
        return Unavailable(f'{self.stopped()}: the record holds no value at {float(time):g} h')

    def unavailable(self, key, time):
        """Why the record holds no value of a key at a time (see the module): a time before the run
        or after its horizon, a time after its stop, a value that its manifest does not name; None
        when it holds one. Every reader asks this first."""
        time = float(time)
        if time < 0:
            return f'the record holds no value at {time:g} h: the run starts at 0 h'
        if time > self.manifest.horizon:
            return f'the record holds no value at {time:g} h: it reaches to its horizon, {float(self.manifest.horizon):g} h'
        later = self.after(time)
        if later is not None:
            return later.reason
        if not self.manifest.names(key):
            return f'the record holds no value of {key}: the request of its run names other values'
        return None

    def value(self, key, time):
        """The value of a key at a time from what the record holds, or `Unavailable` with the reason
        (`unavailable`; a value that did not exist yet; a value whose history the record does not
        keep). A ledger reads 0 before its first edit, from the start of its owner (an occurrence's,
        from the trace); the engine's reader, which knows the stores, also reads 0 for the ledger of a
        store that no edit changed (`timeline.record.Reader.ledger`)."""
        reason = self.unavailable(key, time)
        if reason is not None:
            return Unavailable(reason)
        try:
            history = self.history(key)
        except KeyError:
            stopped = self.stopped()
            return Unavailable(f'the record keeps no history of {key}' + (f': {stopped}' if stopped else ''))
        if key.store is not None and history.pieces and time < history.pieces[0].t:
            begun = [entry.t for entry in self.trace if entry.kind == 'start' and entry.owner == key.owner]
            if '#' not in key.owner or (begun and begun[0] <= time):
                return 0.0  # nothing came from outside before the first edit
        try:
            return history.at(time)
        except LookupError as problem:
            return Unavailable(str(problem))

    def within(self, pieces):
        """The record within a budget of pieces (see the module): itself, when the values that it holds
        have no more pieces; else the record before the time of the first piece that does not fit (its
        histories and its trace), which a failure entry at that time ends, naming the budget.
        The failure has round zero because the record excludes every round at that time."""
        held = [history for history in self.histories if self.manifest.names(history.key)]
        if sum(history.charged_pieces() for history in held) <= pieces:
            return self
        times = sorted(
            float(piece.t) for history in held for piece in history.pieces[: history.charged_pieces()]
        )
        end = times[pieces]
        histories = []
        for history in self.histories:
            kept = tuple(piece for piece in history.pieces if piece.t < end)
            if kept:
                if isinstance(history, ChangeHistory):
                    changes = history.changes[: bisect_left(history.changes, end)]
                    histories.append(replace(history, pieces=kept, changes=changes))
                else:
                    histories.append(replace(history, pieces=kept))
        trace = tuple(entry for entry in self.trace if entry.t < end)
        unit = 'piece' if pieces == 1 else 'pieces'
        message = (
            f'from this time the values that it holds would have more than its budget of {pieces} {unit}'
        )
        failure = Entry(
            end,
            0,
            'failure',
            '',
            '',
            (('message', message), ('budget', pieces)),
        )
        covered = tuple(row for row in self.manifest.unchecked_time_rates if row[1] < end)
        manifest = replace(self.manifest, unchecked_time_rates=covered)
        return Record(manifest, tuple(histories), (*trace, failure), failure)

    def entries(self, kind=None, part=None):
        """The entries of the trace of a kind, of a part, or both."""
        return tuple(
            entry
            for entry in self.trace
            if (kind is None or entry.kind == kind) and (part is None or entry.part == part)
        )

    def near_ties(self):
        """Each near-tie of the run, in the order of the trace: (its entry, (origin, comparison,
        difference, tolerance))."""
        return tuple((entry, tie) for entry in self.trace for tie in entry.detail('near') or ())
