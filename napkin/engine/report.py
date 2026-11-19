"""The report of a run: the values that a caller selects, at the times that it selects, read from the
record of the run (D10), each with its unit, its label, its lag, its evidence trail, and the
near-ties of the run.

`report(record, program, configuration, paths, times, lags=None, model=None)` reads one record. The
model has no report of its own: any named value can be reported, and the caller chooses which.

- **A value** is read as `napkin.engine.read` reads it, in its declared unit: a number, a yes/no, a
  text, or `Unavailable` with the reason (D7). Its label is the first text under its declaration in
  the declared model (`model`; of the flow for a field of a flow, of the store for an endpoint's).
- **A status display** (`member.status`) reads, at each time, the case that the record holds as
  applying (`Shown`): its rating, its text, and its origin, so that two cases with one rating keep
  their own explanations.
- **A reporting lag** (`Lag`) is a transformation that the caller selects. A uniform lag from S to L
  hours gives the mean of the value's history from L hours before to S hours before, and draws
  nothing; equal ends are a fixed delay. Before time 0 the history holds its value at time 0: the
  record has no history before the run. The mean is read over the pieces of the value's history,
  five Gauss-Legendre points in each, which is exact for a store's lines and curves (`DEGREE` 8 of
  `timeline/record.py`). A lag is valid only when a proof says that the value never falls over the
  run (`napkin.program.proofs.never_falls`); then its note is the proof's reason, else the note is
  the diagnostic and the values are the plain read. An edit at a stop (an entry `edit` of the trace,
  `napkin/program/checkpoint.py`) is a change from outside of the stored number that it edits, which
  the proof takes as one more writer of known sign (`_changes`): an edit that lowers what the value
  counts, or raises what it subtracts, withdraws the proof for the run, for the edited value and
  for every formula that rests on it, and the note says which edit.
- **The evidence trail** of a value (`Used`) lists the parts that it can read (`proofs.reads`), each
  with the records that its evidence cites for its member under the options that the run takes
  (`DeclaredModel.evidence`), whether this run exercised it and why: a flow that moved material, an
  event that started, a trigger that fired, a stage that committed, a solver that solved, and every
  value read through exercised parts. An event that cannot start under the configuration is never
  exercised, and says so; "could have and did not" is what the trace says (D16). An edit at a stop
  withdraws those proofs for the run, and the trail of such an event says which edit. A part reached
  only through parts that the run did not exercise is not exercised either. A flow whose rate a
  record of some values does not hold is `not recorded`: the record cannot say whether it moved,
  and the trail says neither (`exercised` is None).
- **Near-ties** (change 10): each decision that the engine made within tolerance of its boundary
  (`Record.near_ties`), with a message by the kind of its entry: a trigger that fired (`fire`), or
  that came within tolerance of its threshold and did not fire (`miss`); a test of a stage that
  committed (`commit`), or a false guard of a stage that ran nothing (`skip`); a gate that released
  its occurrence (`release`); a split of who is served at a settling (`settle`). The report lists
  them and computes nothing more precisely.
- **A run that stopped**: a failure, or the stop at a breakpoint, ends the record (`Record.stop`). The
  report reads up to that time, each time after it is `Unavailable` with the reason, and `stopped`
  says when and why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from ..program import parts as p
from ..program.proofs import Change, Part, Proofs
from ..program.record import Key, Unavailable
from .timeline import read
from .timeline.record import key_of, unit_of

# Gauss-Legendre points and weights on [-1, 1]: five points integrate a polynomial of degree 9 exactly.
_POINTS, _WEIGHTS = np.polynomial.legendre.leggauss(5)


@dataclass(frozen=True)
class Lag:
    """A uniform reporting lag: the value at a time t is the mean of its history from t - `longest`
    to t - `shortest`, in hours; equal ends are a fixed delay."""

    shortest: float
    longest: float

    def __post_init__(self):
        if not (
            all(
                isinstance(end, (int, float)) and not isinstance(end, bool)
                for end in (self.shortest, self.longest)
            )
            and 0 <= self.shortest <= self.longest < math.inf
        ):
            raise ValueError(f'a lag runs from 0 h or more to a longer finite delay, not {self!r}')


@dataclass(frozen=True)
class Shown:
    """A status display at a time: the rating and the text of the case that applies, and its origin."""

    rating: str
    text: str | None
    case: str


@dataclass(frozen=True)
class Used:
    """A part of an evidence trail: its kind, its origin, the member that runs it, the records that
    its evidence cites, whether the run exercised it (None when the record cannot say: a flow whose
    rate it does not hold), and why."""

    kind: str
    origin: str
    owner: str
    records: tuple[str, ...]
    exercised: bool | None
    why: str


@dataclass(frozen=True)
class Reported:
    """One selected value: its path, its unit, its label, its values at the times of the report, its
    lag (None for a plain read), its note (why the lag holds, or the diagnostic of a lag that does
    not, whose values are then the plain read), and its evidence trail."""

    path: str
    unit: str
    label: str | None
    values: tuple
    lag: Lag | None = None
    note: str | None = None
    trail: tuple[Used, ...] = ()


@dataclass(frozen=True)
class NearTie:
    """A decision of the run within tolerance of its boundary: when, the kind of its entry (`fire`,
    `miss`, `commit`, `skip`, `release` or `settle`), the part that decided, the member or
    occurrence, the comparison, its difference and its tolerance in canonical units, and the
    message."""

    t: float
    kind: str
    part: str
    owner: str
    comparison: str
    difference: float
    tolerance: float
    message: str


@dataclass(frozen=True)
class Report:
    """The report of one run: its times, its values in the order of the paths, its near-ties, the
    time to which the record reaches, why it stopped there (None for a run to its horizon), and each
    record that a trail cites, (name, kind, text)."""

    times: tuple[float, ...]
    values: tuple[Reported, ...]
    near_ties: tuple[NearTie, ...]
    end: float
    stopped: str | None = None
    records: tuple[tuple[str, str, str], ...] = ()


def report(record, program, configuration, paths, times, lags=None, model=None, options=()):
    """The report of a run (see the module): `paths` and `times` are the caller's, `lags` maps a path
    to its `Lag`, `model` is the declared model whose texts and evidence the report shows (None for a
    program built by hand), and `options` the names of the model's options that the run takes, whose
    settings a trail cites. A time outside [0, horizon] is a ValueError."""
    lags = dict(lags or {})
    times = tuple(float(t) for t in times)
    horizon = float(record.manifest.horizon)
    for t in times:
        if not 0 <= t <= horizon:
            raise ValueError(f'a report reads times from 0 h to the horizon, {horizon:g} h, not {t:g} h')
    unknown = sorted(set(lags) - set(paths))
    if unknown:
        raise ValueError(f'a lag of {unknown[0]}, which the report does not select')
    end, stopped = _end(record, horizon)
    proofs = Proofs(program, configuration)
    trail = _Trail(record, program, model, proofs, tuple(options))
    reported = []
    for path in paths:
        key = key_of(program, path)
        unit, _ = unit_of(program, key)
        origin = _origin(program, key)
        label = _text(model, origin)
        within = [t for t in times if t <= end]
        lag, note = lags.get(path), None
        if _is_display(program, key):
            values = _shown(record, program, model, key, within)
            if lag is not None:
                lag, note = (
                    None,
                    f'the lag is refused: {path} is a status display, and a lag averages a number',
                )
        elif lag is not None:
            proof = proofs.never_falls(key, _changes(record, program, key))
            if proof.holds:
                values, note = _lagged(record, program, key, within, lag), proof.reason
            else:
                lag, note = None, f'the lag is refused: {path} can fall: {proof.reason}'
                values = read(record, program, [key], within)[0].values
        else:
            values = read(record, program, [key], within)[0].values
        values = tuple(values) + (Unavailable(stopped),) * (len(times) - len(within))
        reported.append(Reported(path, unit, label, values, lag, note, trail.of(key)))
    return Report(times, tuple(reported), _near_ties(record), end, stopped, trail.records())


def _changes(record, program, key):
    """The edits of a record as changes from outside of the numbers that they edit, for the proof
    that the value of `key` never falls (`Proofs.never_falls`), in the order of the trace: each with
    what it did, in the edited value's declared unit ("it" for the value itself)."""
    found = []
    for entry in record.entries('edit'):
        old, new = entry.detail('old'), entry.detail('new')
        if not all(isinstance(each, int | float) and not isinstance(each, bool) for each in (old, new)):
            continue
        if new == old:
            continue
        target = key_of(program, entry.detail('target'))
        spelling, scale = unit_of(program, target)
        name = 'it' if target == key else entry.detail('target')
        verb = 'lowered' if new < old else 'raised'
        numbers = f'from {old / scale:g} to {new / scale:g} {spelling}'.rstrip()
        why = f'an edit at {float(entry.t):g} h, at {entry.part}, {verb} {name} {numbers}'
        found.append(Change(target, float(new) - float(old), why))
    return tuple(found)


def _end(record, horizon):
    """The time to which a record reaches, and why it stops before the horizon (None at it)."""
    stopped = record.stopped()
    if stopped is None:
        return horizon, None
    if record.failure is not None:
        return float(record.end), stopped
    return float(record.end), f'{stopped}: the report reads it up to its stop'


def _origin(program, key):
    """The origin of the declared part of a record key: a value, a flow (of a field of it or of a
    leg), the store of an endpoint, a solver's unknown or a status display."""
    owner, steps = key.owner, key.steps
    if '#' in owner:
        receiver, event = owner.rsplit('#', 1)[0].rsplit('.', 1)
        found = program.member(receiver)[0].part(event)
        part = next((each for each in (*found.params, *found.locals) if each.name == steps[0]), None)
    elif owner:
        template = program.member(owner)[0]
        part = template.part(steps[0])
        if part is None and steps == ('status',) and template.status is not None:
            return template.status.origin
        if hasattr(part, 'unknowns') and len(steps) > 1:
            part = next((each for each in part.unknowns if each.name == steps[1]), part)
    else:
        part = program.root_value(steps[0])
    return getattr(part, 'origin', '')


def _text(model, origin):
    """The first text under the declared part of an origin, or None."""
    part = model.part(origin) if model is not None and origin else None
    return getattr(part, 'text', None)


def _is_display(program, key):
    if not key.owner or '#' in key.owner or key.steps != ('status',):
        return False
    template = program.member(key.owner)[0]
    return template.status is not None and template.part('status') is None


def _shown(record, program, model, key, times):
    """The case of a member's status display at each time, as `Shown`."""
    cases = program.member(key.owner)[0].status.cases
    found = []
    for value in read(record, program, [key], times)[0].values:
        if isinstance(value, Unavailable):
            found.append(value)
            continue
        case = cases[int(value[len('case[') : -1])]
        found.append(Shown(case.rating, _text(model, case.origin), case.origin))
    return tuple(found)


def _lagged(record, program, key, times, lag):
    """The lagged values of a key at each time (see the module): the mean of its history over each
    window, read at five points in each piece of the history inside the window, in the declared
    unit; a window with a value that is unavailable is unavailable with its reason."""
    try:
        cuts = sorted({float(piece.t) for piece in record.history(key).pieces})
    except KeyError:
        raise LookupError(f'{key}: the record holds no history of it to average') from None
    windows, points = [], []
    for t in times:
        low, high = t - lag.longest, t - lag.shortest
        if lag.longest == lag.shortest:
            windows.append(('at', len(points)))
            points.append(max(high, 0.0))
            continue
        # The part of the window before time 0 holds the value at time 0.
        before = max(0.0, min(high, 0.0) - low)
        spans = []
        if before > 0:
            spans.append((before, len(points)))
            points.append(0.0)
        a, b = max(low, 0.0), max(high, 0.0)
        ends = [a, *(cut for cut in cuts if a < cut < b), b] if b > a else []
        for left, right in pairwise(ends):
            half, middle = 0.5 * (right - left), 0.5 * (right + left)
            spans.append((half * _WEIGHTS, len(points)))
            points.extend(float(point) for point in middle + half * _POINTS)
        windows.append(('mean', spans))
    values = read(record, program, [key], points)[0].values if points else ()
    found = []
    for kind, spans in windows:
        if kind == 'at':
            found.append(values[spans])
            continue
        total = 0.0
        for weight, first in spans:
            weights = np.atleast_1d(weight)
            taken = values[first : first + len(weights)]
            missing = next((value for value in taken if isinstance(value, Unavailable)), None)
            if missing is not None:
                total = missing
                break
            total += float(np.dot(weights, [float(value) for value in taken]))
        found.append(total if isinstance(total, Unavailable) else total / (lag.longest - lag.shortest))
    return tuple(found)


_NEAR = {
    'fire': 'this trigger fired within tolerance of its threshold',
    'miss': 'this trigger came within tolerance of its threshold and did not fire',
    'commit': 'this test of a stage was decided within tolerance of its boundary',
    'skip': 'this guard was false within tolerance of its boundary, and the stage ran nothing',
    'release': 'this gate released its occurrence within tolerance of its threshold',
    'settle': 'this split of who is served was decided within tolerance of its boundary',
}


def _near_ties(record):
    """The near-ties of a record (`Record.near_ties`), each with its message."""
    found = []
    for entry, (origin, comparison, difference, tolerance) in record.near_ties():
        message = (
            f'{origin} at {float(entry.t):g} h: {_NEAR[entry.kind]}: {comparison} '
            f'(its sides differ by {difference:.3g}, within the tolerance {tolerance:.3g} of what it reads)'
        )
        found.append(
            NearTie(
                float(entry.t), entry.kind, origin, entry.owner, comparison, difference, tolerance, message
            )
        )
    return tuple(found)


class _Trail:
    """The evidence trails of the values of one record (see the module)."""

    def __init__(self, record, program, model, proofs, options=()):
        self.record, self.program, self.model, self.proofs = record, program, model, proofs
        self.options = options
        # An edit at a stop withdraws, for the run, the proofs that an event cannot start: the value
        # that the proof reads may take what it rules out (`napkin/program/checkpoint.py`).
        self.edited = record.entries('edit')
        self.started = record.entries('start')
        self.cited = {}
        self.entries = {}
        for entry in record.trace:
            self.entries.setdefault((entry.kind, entry.part), []).append(entry)
        # The histories of the actual rates of the flows, by their owner (`tank.receive#` for every
        # occurrence of an event on a receiver) and their steps.
        self.rates = {}
        for history in record.histories:
            if history.key.steps and history.key.steps[-1] == 'actual_rate':
                owner = history.key.owner
                owner = owner.rsplit('#', 1)[0] + '#' if '#' in owner else owner
                self.rates.setdefault((owner, history.key.steps), []).append(history)

    def of(self, key):
        """The trail of the value of a key: each part that it can read, ordered by origin and owner. A
        part is reached through parts whose reads the run evaluated (`evaluated`), and exercised when
        it is reached and acted itself (`acted`)."""
        found = self.proofs.reads(key)
        reached, pending = set(), [found.start]
        while pending:
            part = pending.pop()
            if part in reached:
                continue
            reached.add(part)
            if self.evaluated(part, found):
                pending.extend(found.edges.get(part, ()))
        used = []
        for part in sorted(found.edges, key=lambda each: (each.origin, each.owner, each.kind)):
            did, why = self.acted(part, found)
            if part not in reached and (part not in found.blocked or self.edited):
                did, why = False, 'it is read only through parts that the run did not exercise'
            used.append(
                Used(part.kind, part.origin, part.owner, self.cites(part.origin, part.owner), did, why)
            )
        return tuple(used)

    def evaluated(self, part, found):
        """Whether the run read what a part reads: a value's reads; a flow's while it existed (a flow of
        an event, once the event started on its receiver), and so whether it moved or not; a
        trigger's condition, read at every round; an event's, a stage's and a solver's when it acted."""
        if part.kind in ('value', 'status', 'trigger'):
            return True
        if part.kind == 'flow':
            event = self.event_of(part)
            return event is None or self.acted(event, found)[0]
        return self.acted(part, found)[0]

    def acted(self, part, found):
        """Whether a part acted in the run itself, and why: a flow moved material, an event started,
        a trigger fired, a stage committed, a solver solved; a value is read."""
        if part.kind in ('value', 'status'):
            return True, 'read'
        if part.kind == 'flow':
            moved = self.moved(part)
            if moved is None:
                return None, f'not recorded: the record of this run does not hold the rate of {part.origin}'
            return moved, 'it moved material' if moved else 'it moved nothing in this run'
        withdrawn = ''
        if part.kind == 'event' and part in found.blocked:
            if not self.edited:
                return False, f'it cannot start under this configuration: {found.blocked[part]}'
            first = self.edited[0]
            withdrawn = (
                f' (the edit at {float(first.t):g} h, at {first.part}, withdrew for this run the proof that it '
                f'cannot start: {found.blocked[part]})'
            )
        if part.kind == 'stage' and part.origin == 'setup':
            return True, 'the setup ran at 0 h'
        kind = {'event': 'start', 'trigger': 'fire', 'stage': 'commit', 'solver': 'solve'}[part.kind]
        entries = [entry for entry in self.entries.get((kind, part.origin), ()) if _runs(entry, part)]
        verb = {'start': 'started', 'fire': 'fired', 'commit': 'committed', 'solve': 'solved'}[kind]
        if not entries:
            return False, f'it did not {kind if kind != "solve" else "solve"} in this run{withdrawn}'
        if len(entries) == 1:
            return True, f'it {verb} at {float(entries[0].t):g} h{withdrawn}'
        return True, f'it {verb} {len(entries)} times from {float(entries[0].t):g} h{withdrawn}'

    def event_of(self, part):
        """The event of a flow of an event's occurrences, as a part of its receiver, or None."""
        template = self.program.member(part.owner)[0]
        name = part.origin[len(template.name) + 1 :].split('.')[0]
        event = template.part(name)
        return Part('event', event.origin, part.owner) if isinstance(event, p.Event) else None

    def moved(self, part):
        """Whether a flow moved material in the run: its actual rate is not zero on some piece. None
        when it did not on the pieces that the record holds and a record of some values does not hold
        its rate (of the flow, or of an occurrence of its event that started): it cannot say."""
        template = self.program.member(part.owner)[0]
        steps = part.origin[len(template.name) + 1 :].split('.')
        owner, rate = part.owner, (*steps, 'actual_rate')
        keys = [Key(owner, rate)]
        if self.event_of(part) is not None:  # a flow of the event's occurrences
            owner, rate = f'{owner}.{steps[0]}#', (*steps[1:], 'actual_rate')
            keys = [Key(entry.owner, rate) for entry in self.started if entry.owner.startswith(owner)]
        histories = self.rates.get((owner, rate), ())
        if any(
            not isinstance(piece.value, (bool, str, Unavailable))
            and (piece.value != 0 or piece.rate != 0 or piece.curve is not None)
            for history in histories
            for piece in history.pieces
        ):
            return True
        held = {history.key for history in histories}
        if self.record.manifest.everything or all(key in held for key in keys):
            return False
        return None

    def cites(self, origin, member=''):
        """The records of the evidence of the declared part of an origin for one member, under the
        options of the run (`DeclaredModel.evidence`: the part's own, the member's own line or its
        table's column, the settings of the options that set it): each record that it cites by name,
        and each written in place as its kind and its text."""
        if self.model is None:
            return ()
        found = []
        for item in self.model.evidence(origin, member, self.options):
            name = getattr(item, 'name', None)
            if name is not None:
                found.append(name)
                self.cited[name] = None
            else:
                found.append(f'{item.kind}: {item.text}')
        return tuple(found)

    def records(self):
        """(name, kind, text) of each record of the model that a trail cites, by name."""
        if self.model is None:
            return ()
        known = {item.name: item for item in self.model.records}
        return tuple(
            (name, known[name].kind, known[name].text) for name in sorted(self.cited) if name in known
        )


def _runs(entry, part):
    """Whether an entry of the trace is of the member that runs a part: a firing and a solve name the
    member, a start and a commit an occurrence of the member's event."""
    if entry.kind in ('fire', 'solve'):
        return entry.owner == part.owner
    return entry.owner.rsplit('#', 1)[0].rsplit('.', 1)[0] == part.owner
