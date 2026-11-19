"""The report of a run: the values that a caller selects, at the times that it selects, read from the
record of the run (D10), each with its unit, its label, its lag, its evidence trail, and the
near-ties of the run.

`report(record, program, configuration, paths, times, lags=None, model=None)` reads one record. The
model has no report of its own: any named value can be reported, and the caller chooses which. A
report claims nothing that the record does not show.

- **A value** is read as `napkin.engine.read` reads it, in its declared unit: a number, a yes/no, a
  text, or `Unavailable` with the reason (D7), from what the record holds and from nothing else
  (`Record.unavailable`). Each value is read at its own time, so the values follow the times in the
  caller's order, whatever that order is. Its label is the first text under its declaration in the
  declared model (`model`; of the flow for a field of a flow, of the store for an endpoint's). Where
  the report names a member (the owner of a value's path, of a part of a trail, of a near-tie; of an
  occurrence, its receiver), it gives the member's title too (`DeclaredModel.title`: "DC Water"), a
  label that no value depends on.
- **A status display** (`member.status`) reads, at each time, the case that the record holds as
  applying (`Shown`): its rating, its text, and its origin, so that two cases with one rating keep
  their own explanations.
- **A reporting lag** (`Lag`) is a transformation that the caller selects. A uniform lag from S to L
  hours gives the mean of the value's history from L hours before to S hours before, and draws
  nothing; equal ends are a fixed delay. A window that begins before 0 h is `Unavailable`: the
  record has no history before the run. The mean is read over the pieces of the value's history,
  five Gauss-Legendre points in each, which is exact for a store's lines and curves (`DEGREE` 8 of
  `timeline/record.py`). A lag is valid only for a number (a yes/no, a text, an enum member, a status
  display is refused by name) that a proof says never falls over the run
  (`napkin.program.proofs.never_falls`); then its note is the proof's reason, else the note is the
  diagnostic and the values are the plain read.
- **An edited run.** The proofs of a run with edits at its stops (entries `edit` of the trace,
  `napkin/program/checkpoint.py`) are derived for that run, with each edit one more writer of it
  (`_changes`, `Proofs`): an edit that lowers what the value counts, or raises what it subtracts,
  withdraws the proof that it never falls, for the edited value and for every formula that rests on
  it, and an edit of a yes/no or an enum member that lets an event start withdraws the proof that it
  cannot start; the note and the trail say which edit.
- **The evidence trail** of a value (`Used`) lists the parts that it can read (`proofs.reads`), each
  with the records that its evidence cites for its member under the options that the run takes
  (`DeclaredModel.evidence`), whether this run exercised it and why. A part is reached through what
  was read: what the value's own evaluation read at the report's times (`timeline.record.Reader`;
  a side of a choice that it did not take, a case of a status display after the one that applied, is
  not read), and through that, what the run evaluated: a flow that existed, an event that started, a
  trigger's condition, a stage that committed, a solver that solved. Such a part's expression read on
  every evaluation what lies outside its branches; a part that it reads only on a branch the record
  cannot say the run read (`exercised` None). A reached part is exercised when it acted: a flow that
  moved material, an event that started, a trigger that fired, a stage that committed, a solver that
  solved, a value that was read, a case that applied. An event that cannot start under the
  configuration is never exercised, and says so; "could have and did not" is what the trace says
  (D16). A flow whose rate the record does not hold is `not recorded`: the record cannot say whether
  it moved, and the trail says neither (`exercised` is None).
- **Near-ties** (change 10): each decision that the engine made within tolerance of its boundary
  (`Record.near_ties`), with a message by the kind of its entry: a trigger that fired (`fire`), or
  that came within tolerance of its threshold and did not fire (`miss`); a test of a stage that
  committed (`commit`), or a false guard of a stage that ran nothing (`skip`); a gate that released
  its occurrence (`release`); a split of who is served at a settling (`settle`). The report lists
  them and computes nothing more precisely.
- **A run that stopped**: a failure, a stop at a breakpoint or the budget of its record ends the
  record (`Record.stop`). The report reads up to that time, each time after it is `Unavailable` with
  the reason, and `stopped` says when and why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from ..program import parts as p
from ..program.proofs import Change, Part, Proofs, kind_of
from ..program.record import Key, Unavailable
from .timeline.plan import FORMULA, name_of
from .timeline.record import Reader, declared, in_unit, key_of

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
    title: str | None = None  # the title of the member that runs it


@dataclass(frozen=True)
class Reported:
    """One selected value: its path, its unit, its label, its values at the times of the report, its
    lag (None for a plain read), its note (why the lag holds, or the diagnostic of a lag that does
    not, whose values are then the plain read), its evidence trail, and the title of the member of
    its path."""

    path: str
    unit: str
    label: str | None
    values: tuple
    lag: Lag | None = None
    note: str | None = None
    trail: tuple[Used, ...] = ()
    title: str | None = None


@dataclass(frozen=True)
class NearTie:
    """A decision of the run within tolerance of its boundary: when, the kind of its entry (`fire`,
    `miss`, `commit`, `skip`, `release` or `settle`), the part that decided, the member or
    occurrence, the comparison, its difference and its tolerance in canonical units, the message,
    and the title of the member."""

    t: float
    kind: str
    part: str
    owner: str
    comparison: str
    difference: float
    tolerance: float
    message: str
    title: str | None = None


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
    reader = Reader(record, program)
    proofs = Proofs(program, configuration, _changes(record, program))
    trail = _Trail(record, program, model, proofs, reader, tuple(options))
    reported = []
    for path in paths:
        key = key_of(program, path)
        unit, scale = declared(program, key)
        label = _text(model, _origin(program, key))
        lag, note = lags.get(path), None
        if lag is not None:
            kind = _kind(program, proofs, key)
            proof = proofs.never_falls(key) if kind == 'a number' else None
            if proof is None:
                lag, note = None, f'the lag is refused: {path} is {kind}, and a lag averages a number'
            elif proof.holds:
                note = proof.reason
            else:
                lag, note = None, f'the lag is refused: {path} can fall: {proof.reason}'
        # The times at which the report reads the value: its own, or the points of the windows of
        # its lag. Its trail follows what it read then.
        read_at = []
        if _is_display(program, key):
            values = tuple(_shown(reader, program, model, key, t) for t in times)
            read_at = list(times)
        elif lag is not None:
            values = tuple(_lagged(record, reader, key, scale, t, lag, read_at) for t in times)
        else:
            values = tuple(in_unit(reader.value(key, t), scale) for t in times)
            read_at = list(times)
        title = _title(model, key.owner)
        reported.append(Reported(path, unit, label, values, lag, note, trail.of(key, read_at), title))
    return Report(times, tuple(reported), _near_ties(record, model), end, stopped, trail.records())


def _kind(program, proofs, key):
    """What the value of a key is, in words (`proofs.kind_of`): `a status display`, `a number`, `a
    yes/no`, `a text`, `a member of the enum ...`; a field of a flow, a ledger and a property of a
    distribution are numbers."""
    if _is_display(program, key):
        return 'a status display'
    point = proofs.value_point(key.owner, key.steps[0]) if len(key.steps) == 1 else None
    return 'a number' if point is None else kind_of(point[2].type)


def _title(model, owner):
    """The title of the member that an owner names (`DeclaredModel.title`): a member, or the receiver
    of an occurrence or of an event's occurrences (`tank.receive#0`, `tank.receive#`); None for the
    root, a member with none, or no declared model."""
    if model is None or not owner:
        return None
    return model.title(owner.rsplit('#', 1)[0].rsplit('.', 1)[0] if '#' in owner else owner)


def _changes(record, program):
    """The edits of a record as changes from outside of the values that they edit (`proofs.Change`),
    in the order of the trace: every edit that changed its value, of any type, each with what it did,
    in the edited value's declared unit. The proofs of the run follow from them (`Proofs`)."""
    found = []
    for entry in record.entries('edit'):
        old, new = entry.detail('old'), entry.detail('new')
        if new == old and type(new) is type(old):
            continue
        target = key_of(program, entry.detail('target'))
        numbers = all(isinstance(each, int | float) and not isinstance(each, bool) for each in (old, new))
        if numbers:
            spelling, scale = declared(program, target)
            verb = 'lowered' if new < old else 'raised'
            what = (
                f'{verb} {target} from {in_unit(old, scale):g} to {in_unit(new, scale):g} {spelling}'.rstrip()
            )
        else:
            what = f'set {target} from {_spelled(old)} to {_spelled(new)}'
        found.append(Change(target, old, new, f'an edit at {float(entry.t):g} h, at {entry.part}, {what}'))
    return tuple(found)


def _spelled(value):
    """A value of an edit as a model writes it: `true`, `false`, an enum member, a quoted text."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return f'{value}'


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


def _shown(reader, program, model, key, t):
    """The case of a member's status display at a time, as `Shown`, or `Unavailable`."""
    value = reader.value(key, t)
    if isinstance(value, Unavailable):
        return value
    case = program.member(key.owner)[0].status.cases[int(value[len('case[') : -1])]
    return Shown(case.rating, _text(model, case.origin), case.origin)


def _lagged(record, reader, key, scale, t, lag, read_at):
    """The lagged value of a key at a time (see the module), in the declared unit of its scale: the
    mean of its history over the window, read at five points in each piece of the history inside it,
    which `read_at` keeps; `Unavailable` for a time after the record's stop, a window that begins
    before 0 h, or a window with a value that is unavailable, each with its reason."""
    stopped = record.after(t)
    if stopped is not None:
        return stopped
    low, high = t - lag.longest, t - lag.shortest
    if low < 0:
        return Unavailable(
            f'the lag of {key} at {t:g} h reads it from {low:g} h, before the run starts at 0 h: the '
            'record holds no value then'
        )
    if lag.longest == lag.shortest:
        read_at.append(high)
        return in_unit(reader.value(key, high), scale)
    try:
        cuts = sorted({float(piece.t) for piece in record.history(key).pieces if low < piece.t < high})
    except KeyError:
        cuts = []  # no history to cut the window: its reads say why
    total = 0.0
    for left, right in pairwise([low, *cuts, high]):
        half, middle = 0.5 * (right - left), 0.5 * (right + left)
        points = [float(point) for point in middle + half * _POINTS]
        read_at.extend(points)
        values = [reader.value(key, point) for point in points]
        missing = next((value for value in values if isinstance(value, Unavailable)), None)
        if missing is not None:
            return missing
        total += half * float(np.dot(_WEIGHTS, [float(value) for value in values]))
    return in_unit(total / (lag.longest - lag.shortest), scale)


_NEAR = {
    'fire': 'this trigger fired within tolerance of its threshold',
    'miss': 'this trigger came within tolerance of its threshold and did not fire',
    'commit': 'this test of a stage was decided within tolerance of its boundary',
    'skip': 'this guard was false within tolerance of its boundary, and the stage ran nothing',
    'release': 'this gate released its occurrence within tolerance of its threshold',
    'settle': 'this split of who is served was decided within tolerance of its boundary',
}


def _near_ties(record, model=None):
    """The near-ties of a record (`Record.near_ties`), each with its message and its member's title."""
    found = []
    for entry, (origin, comparison, difference, tolerance) in record.near_ties():
        message = (
            f'{origin} at {float(entry.t):g} h: {_NEAR[entry.kind]}: {comparison} '
            f'(its sides differ by {difference:.3g}, within the tolerance {tolerance:.3g} of what it reads)'
        )
        title = _title(model, entry.owner)
        found.append(
            NearTie(
                float(entry.t),
                entry.kind,
                origin,
                entry.owner,
                comparison,
                difference,
                tolerance,
                message,
                title,
            )
        )
    return tuple(found)


class _Trail:
    """The evidence trails of the values of one record (see the module). `reader` read the values,
    and keeps what each evaluation read."""

    def __init__(self, record, program, model, proofs, reader, options=()):
        self.record, self.program, self.model, self.proofs = record, program, model, proofs
        self.reader, self.options = reader, options
        self.started = record.entries('start')
        self._ran = {}  # what each flow's settings read in the run, as the record shows it (`ran`)
        self.cited = {}
        self.entries = {}
        for entry in record.trace:
            self.entries.setdefault((entry.kind, entry.part), []).append(entry)
        # The histories of the actual rates of the flows that the record holds, by their owner
        # (`tank.receive#` for every occurrence of an event on a receiver) and their steps.
        self.rates = {}
        for history in record.histories:
            if (
                history.key.steps
                and history.key.steps[-1] == 'actual_rate'
                and record.manifest.names(history.key)
            ):
                owner = history.key.owner
                owner = owner.rsplit('#', 1)[0] + '#' if '#' in owner else owner
                self.rates.setdefault((owner, history.key.steps), []).append(history)

    def of(self, key, times):
        """The trail of the value of a key that the report read at `times`: each part that it can read,
        ordered by origin and owner, reached through what was read (`reached`), and exercised when it
        is reached and acted. Only the times at which the report's read of the value reached the
        reader's evaluation count (`Reader.refusal`): at another, the report holds no value of it,
        whatever another value of the report read of it then."""
        found = self.proofs.reads(key)
        times = sorted({t for t in times if self.reader.refusal(key, t) is None})
        sure, maybe, unread, applied = self.reached(key, found, times)
        used = []
        for part in sorted(found.edges, key=lambda each: (each.origin, each.owner, each.kind)):
            if part in sure:
                did, why = self.acted(part, found, applied)
            elif part in maybe:
                did, why = (
                    None,
                    (
                        'it is read only on a branch of an expression that the run evaluated, and the record '
                        'does not show whether the run took that branch'
                    ),
                )
            elif part.kind == 'event' and part in found.blocked:
                did, why = self.acted(part, found, applied)
            elif part in unread:
                did, why = False, unread[part]
            else:
                did, why = False, 'it is read only through parts that the run did not exercise'
            records = self.cites(part.origin, part.owner)
            used.append(
                Used(part.kind, part.origin, part.owner, records, did, why, _title(self.model, part.owner))
            )
        return tuple(used)

    def reached(self, key, found, times):
        """The parts that the value of a key reaches surely and those that it reaches only on a branch
        that the record does not show; the parts that an evaluation of the reader could read and did
        not, each with why; and, of each case of a status display that it reaches, the times at which
        it applied. A part that the reader evaluated reaches what that evaluation read, each read
        with its own time (`read`): what the value read at a time is followed at that time and at no
        other, so what another value of the report read, at its times or at these, takes no part in
        this trail. Any other part that the run evaluated (`evaluated`) reaches what it reads, on a
        branch only maybe (`Reads.sometimes`). `times` are those at which the report read the value
        through an evaluation of the reader (`Reader.refusal`)."""
        evaluated = self.reader.read
        start = name_of(key)
        pairs = frozenset((start, t) for t in times if (start, t) in evaluated)
        sure, maybe, unread, applied, seen = set(), set(), {}, {}, set()
        if not pairs and self.reader.evaluates(start):
            # The report read no value of the formula at its times (each was unavailable before it
            # was evaluated): it read nothing through it.
            why = 'it was not read at the reported times: the report holds no value of the value there'
            return {found.start}, maybe, dict.fromkeys(found.edges.get(found.start, ()), why), applied
        another = 'it was not read at the reported times: the evaluation took another branch'
        pending = [(found.start, True, pairs)]
        while pending:
            state = pending.pop()
            part, certain, inner = state
            if state in seen or (not certain and (part, True, inner) in seen):
                continue
            seen.add(state)
            (sure if certain else maybe).add(part)
            edges = found.edges.get(part, ())
            if inner and part.kind == 'status':
                # Its cases in order, each read until one applies: the case at each time is its value,
                # and a case was read at the times at which no case before it applied.
                places = {at: self.case_at(key, at) for _, at in inner}
                for k, case in enumerate(edges):
                    read_at = {at for at, place in places.items() if place is not None and k <= place}
                    if read_at:
                        applied[case] = [at for at in times if places.get(at) == k]
                        pending.append(
                            (case, certain, frozenset(pair for pair in inner if pair[1] in read_at))
                        )
                    else:
                        unread[case] = another
            elif inner:
                read = self.read(inner)
                names = {name for name, _ in read}
                for other in edges:
                    hit = self.names_of(other, names)
                    if hit is None:
                        pending.append((other, False, frozenset()))
                    elif hit:
                        # What the part read, at the times at which this value's evaluations read it.
                        again = frozenset(pair for pair in read if pair[0] in hit and pair in evaluated)
                        pending.append((other, certain, again))
                    else:
                        unread[other] = another
            elif self.evaluated(part, found):
                branch = found.sometimes.get(part, frozenset())
                # What a flow's settings read on a branch, the record may show (`ran`).
                shown = self.ran(part) if branch and part.kind == 'flow' else None
                for other in edges:
                    hit = None if other not in branch or shown is None else self.names_of(other, shown)
                    if other not in branch or hit:
                        pending.append((other, certain, frozenset()))
                    elif hit is None:
                        pending.append((other, False, frozenset()))
                    else:
                        unread[other] = (
                            'the run did not read it: the record shows that each evaluation that could read it '
                            'took another branch'
                        )
        maybe -= sure
        return sure, maybe, {part: why for part, why in unread.items() if part not in sure | maybe}, applied

    def read(self, pairs):
        """Each (engine name, time) that the reader read in evaluating `pairs`, each an (engine name,
        time) that it evaluated, through the values that it evaluated in turn, each at the time of
        the evaluation that read it."""
        found, done = set(), set()
        pending = list(pairs)
        while pending:
            name, t = pending.pop()
            if (name, t) in done:
                continue
            done.add((name, t))
            for other in self.reader.reads(name, t):
                found.add((other, t))
                if (other, t) in self.reader.read:
                    pending.append((other, t))
        return found

    def ran(self, part):
        """The engine names that the run's evaluations of a flow's request and capacity read, as the
        record shows them, or None when it cannot. Each is evaluated at every time from the flow's
        start at which what it reads has a piece or it takes a new definition: that is exact when all
        of what it reads holds its value between pieces (no line, no curve, no time, no keyed read by
        the time), since nothing it reads changes in between; a value that moves between moments can
        change a branch between two pieces, and the record does not show it."""
        if part not in self._ran:
            self._ran[part] = self._settings_read(part)
        return self._ran[part]

    def _settings_read(self, part):
        """What `ran` gives, found once for each flow."""
        plan, record = self.reader.plan, self.record
        template = self.program.member(part.owner)[0]
        steps = part.origin[len(template.name) + 1 :].split('.')
        if self.event_of(part) is not None:
            head = f'{part.owner}.{steps[0]}#'
            owners = [(entry.owner, float(entry.t)) for entry in self.started if entry.owner.startswith(head)]
            steps = steps[1:]
        else:
            owners = [(part.owner, 0.0)]
        found = set()
        for owner, start in owners:
            for which in ('request', 'capacity'):
                name = name_of(Key(owner, (*steps, which)))
                if name not in plan.values:
                    continue
                definitions = self.reader.definitions.get(name, [(start, plan.original(name))])
                times = {start, *(float(at) for at, _ in definitions if start <= at <= record.end)}
                for _, value in definitions:
                    if value.kind != FORMULA:
                        continue
                    expanded = plan.expansion(value.node)
                    if expanded.time or expanded.stepped:
                        return None
                    for leaf in expanded.leaves:
                        held = self._held_times(plan.values[leaf].key, start)
                        if held is None:
                            return None
                        times |= held
                for t in sorted(times):
                    try:
                        self.reader.at(name, t)
                    except LookupError:
                        continue
                    found |= {name} | {other for other, _ in self.read({(name, t)})}
        return found

    def _held_times(self, key, start):
        """The times of the pieces of a history from `start` to the end of the record, when each holds
        its value until the next; None when one moves, or the record does not keep the history."""
        try:
            pieces = self.record.history(key).pieces
        except KeyError:
            return None
        if any(piece.curve is not None or piece.rate != 0 for piece in pieces if piece.t >= start):
            return None
        return {float(piece.t) for piece in pieces if start <= piece.t <= self.record.end}

    def case_at(self, key, t):
        """The place of the case of a status display that applies at a time, or None."""
        value = self.reader.value(key, t)
        return None if isinstance(value, Unavailable) else int(value[len('case[') : -1])

    def names_of(self, part, read):
        """The engine names of a part among those that an evaluation read (`read`), or None when its
        engine names are not ones that a formula reads (a stage, a trigger)."""
        owner = part.owner
        if part.kind == 'value':
            name = part.origin.rsplit('.', 1)[-1]
            if owner.endswith('#'):
                return {each for each in read if _field(each, owner) == name}
            return {each for each in read if each == (f'{owner}.{name}' if owner else name)}
        if part.kind in ('flow', 'event', 'solver'):
            template = self.program.member(owner)[0]
            steps = part.origin[len(template.name) + 1 :].split('.')
            if part.kind == 'event' or (part.kind == 'flow' and self.event_of(part) is not None):
                # An occurrence's fields: `tank.receive#0.level`, `tank.receive#0.pipe.actual_rate`.
                head, rest = f'{owner}.{steps[0]}#', '.'.join(steps[1:])
                return {
                    each
                    for each in read
                    if (field := _field(each, head)) is not None
                    and (not rest or field.startswith(rest + '.'))
                }
            prefix = f'{owner}.{".".join(steps)}.'
            return {each for each in read if each.startswith(prefix)}
        return None

    def evaluated(self, part, found):
        """Whether the run read what a part reads: a value's reads; a case's condition, read until a
        case applies; a flow's while it existed (a flow of an event, once the event started on its
        receiver), and so whether it moved or not; a trigger's condition, read at every round; an
        event's, a stage's and a solver's when it acted."""
        if part.kind in ('value', 'status', 'case', 'trigger'):
            return True
        if part.kind == 'flow':
            event = self.event_of(part)
            return event is None or self.acted(event, found, {})[0]
        return self.acted(part, found, {})[0]

    def acted(self, part, found, applied):
        """Whether a part acted in the run itself, and why: a flow moved material, an event started,
        a trigger fired, a stage committed, a solver solved; a value is read; a case applied at a
        reported time (`applied`)."""
        if part.kind in ('value', 'status'):
            return True, 'read'
        if part.kind == 'case':
            times = applied.get(part, ())
            if not times:
                return False, 'its condition was read and did not hold at the reported times'
            return True, f'it applied at {", ".join(f"{t:g} h" for t in times)}'
        if part.kind == 'flow':
            moved = self.moved(part)
            if moved is None:
                return None, f'not recorded: the record of this run does not hold the rate of {part.origin}'
            return moved, 'it moved material' if moved else 'it moved nothing in this run'
        withdrawn = ''
        if part.kind == 'event':
            if part in found.blocked:
                return False, f'it cannot start under this configuration: {found.blocked[part]}'
            why = self.proofs.withdrawn(part.origin)
            withdrawn = f' ({why})' if why is not None else ''
        if part.kind == 'stage' and part.origin == 'setup':
            return True, 'the setup ran at 0 h'
        kind = {'event': 'start', 'trigger': 'fire', 'stage': 'commit', 'solver': 'solve'}[part.kind]
        entries = [entry for entry in self.entries.get((kind, part.origin), ()) if _runs(entry, part)]
        verb = {'start': 'started', 'fire': 'fired', 'commit': 'committed', 'solve': 'solved'}[kind]
        if not entries:
            return False, f'it did not {kind} in this run{withdrawn}'
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
        """Whether a flow moved material in the run: its actual rate is not zero on some piece that the
        record holds. None when it did not on those and the record does not hold its rate (of the
        flow, or of an occurrence of its event that started): it cannot say."""
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
        if all(self.record.manifest.names(key) for key in keys):
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


def _field(name, owner):
    """The steps of an engine name of an occurrence of the owner `tank.receive#` after its number
    (`level` of `tank.receive#0.level`), or None for a name of no occurrence of it."""
    if not name.startswith(owner):
        return None
    number, _, steps = name[len(owner) :].partition('.')
    return steps if number.isdigit() else None


def _runs(entry, part):
    """Whether an entry of the trace is of the member that runs a part: a firing and a solve name the
    member, a start and a commit an occurrence of the member's event."""
    if entry.kind in ('fire', 'solve'):
        return entry.owner == part.owner
    return entry.owner.rsplit('#', 1)[0].rsplit('.', 1)[0] == part.owner
