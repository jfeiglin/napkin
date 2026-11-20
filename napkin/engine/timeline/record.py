"""The record of a run (`napkin/program/record.py`): the history of each value as pieces, the trace,
and the reader of named paths at chosen times.

A piece reads `value + rate * (time - t)` from its time until the next piece. The recorder makes the
pieces of each value of a run:

- **An input, a stored value that does not move, a draw and a captured request or capacity** has one
  constant piece at the start, and a piece at each commit that writes it. A value of an occurrence
  has its pieces from the occurrence's start; a store that a flow of an occurrence meets has the
  pieces of its set while it moves and holds its value after.
- **A store and the actual rate of a flow** take their pieces from the segments of their component,
  as the run makes them, while the bounds and the faces of each segment hold (`Recorder.segment`).
  On a straight segment (a closed form of constant rates) a store has one exact piece of its rate,
  and a flow one constant piece. A curved segment (an exponential closed form, or the solver) gives
  pieces with a `Curve` (`napkin/program/record.py`): the value follows a Chebyshev series of
  degree `DEGREE` over the piece, within the tolerance of the value, and a piece is cut in two until
  it does; a fit that comes out a line of a slope other than zero is a series of degree one, since
  its slope is the fit's over its span (`fitted`). A solver's segment is fitted step by step: its
  dense output is a cubic in each step, which the series holds exactly. The state that a segment
  starts from opens its pieces, so a settled bound is a jump.
- **The family** (`family.py`) gives exact lines: a piece of each store and of each actual rate at
  each change of its line, and a piece of a request or a capacity that is a formula at each change
  of its value.
- **A status display** of a member (`member.status`) is a formula whose value is the text `case[k]`
  of the case that applies (`plan.py`), made as a formula of a text is.
- **A keyed read by the time on fixed keys** has, over each of its key intervals, the pieces of the
  value of the member that it selects there; below its first key it holds `Unavailable`. Any other
  keyed read is made from the histories of what can change of what it reads (its key, and what its
  members read that the inputs do not fix), as a formula is. A reduction has its
  pieces from the histories of its kept entries (`collections.history_of`): a sum of lines, a count,
  an any, an all, a least or a greatest value of values that hold between moments are exact; any
  other is fitted as a formula is. Neither has a key in the record: the formulas that read them read
  their histories.
- **A dynamic read** (the occurrences of an event, the flows present at an endpoint) has its pieces
  from the histories of what its members project and of the fields that say when each is a member:
  an occurrence is a member from its start, a flow of an occurrence while it is active.
- **An edit of a store** at a stop (`checkpoints.py`) is a transfer from or to outside in its books:
  the store's history `external` (`tank.water.external`, in the store's unit) is what edits brought
  into it so far, a piece at each edit, the first at the first edit (before it, nothing came from
  outside: the ledger reads 0); a withdrawal lowers it. The record keeps the ledger of every store
  that an edit changed by its end, whatever its request names, and holds it with the store or alone
  (`Manifest.names`); a store with no ledger took nothing from outside. So a ledger has a piece only
  where an edit made one, as the run goes: a record that ends before the first edit of a store holds
  no ledger of it, fresh or cut from a longer record (`store.served`), and an edit adds to the budget
  of pieces at its own time, never before.
- **The time of a change** that `elapsed` reads has a piece at the start of its value and at each
  commit that changed it. It has no key in the record: the reader finds it from the history of the
  value that it reads.
- **An occurrence that a failed commit started** holds no value in the record: the record holds the
  occurrences that its trace starts, and the commit that failed is not in it (`moment.py`).
- **A formula, and a request or a capacity written as one,** is made after the run from the
  histories of what it reads (a formula of an occurrence from its start, and from its finish the
  frozen value that the run gave it, D7): between two times at which one of them has a piece, it is one piece
  where each of them holds its value, else it is fitted as a curve is, and a yes/no takes a piece at
  each change, located to within the crossing tolerance of the run (`Numerics.crossing`). A formula
  that only names another value has that value's history. A formula that cannot be evaluated holds
  `Unavailable` with the reason, from where it cannot be, found as a change of a yes/no is, also
  inside a piece (a membership whose moving end passes the other): its values before are kept.

**What a record holds** is one function of its request and its trace (`requested`), for a run's
record and for a cut of a longer one (`store.served`): every value, or the values that the request
names, what their formulas read under each definition that the trace's commits gave them
(`needed`), and the ledgers of the books, each history in the order of its key; a piece that starts
at the record's end holds its value there (`_finished`). Whether a cut of a longer record at an end
is what a run to that end makes is `settled`: no piece that it keeps is a fit or a change that the
record found by bisection after the run. The values that a record holds have at most the request's
budget of pieces: a record that would hold more ends before the time of the first piece that does
not fit, naming the budget (`Record.within`), and a run whose record so far would hold more at a
stop ends there by its budget, before any checkpoint (`checkpoints.Breaks`).

Numbers are in the canonical unit of their dimension. `read` gives them in the declared unit of each
path, from what the record holds and from nothing else (`Record.unavailable`): any other value is
`Unavailable` with the reason, never a default. Its `Reader` evaluates a formula, a reduction, a keyed
read and a dynamic read at each time that it is asked from the recorded values of what it reads (a
formula of a finished occurrence reads its frozen piece; the time of the last change of a value is
its last piece that differs from the one before), depth first with no recursion, and keeps what each
evaluation read, which a report's evidence trail follows. It never reads a formula's fitted pieces: a
fit is checked at a few points of each piece only, so it could lose a kink between two of them, or a
yes/no that changes and changes back. It reads a record with the plan of the run that made it, or
makes the record's occurrences again from the starts of its trace (`Plan.replay`).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

import numpy as np
from numpy.polynomial import chebyshev

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.config import Configuration, Request
from ...program.parts import DistributionType, OccurrenceType
from ...program.proofs import always
from ...program.record import Curve, Entry, History, Key, Manifest, Piece, Record, Unavailable
from ..continuous.kernels import Affine, MatrixExponential
from ..errors import SimulationError
from .collections import dynamic_value, history_of, index_of, kept, known, looked_up, reduced
from .plan import CHANGED, DYNAMIC, FORMULA, LOOKUP, REDUCE, Plan, name_of
from .reads import Reads

# What evaluating a formula can raise: it then holds `Unavailable` with the reason.
FAILURES = (ExpressionError, ArithmeticError, ValueError, LookupError, SimulationError)

DEGREE = 8
# The points of a fit on [-1, 1], and the points between them at which a fit is checked, with the
# start of the piece. The end of a piece is the start of the next, whose value can jump there.
_NODES = np.cos(np.pi * (np.arange(DEGREE + 1) + 0.5) / (DEGREE + 1))[::-1]
_CHECKS = np.cos(np.pi * np.arange(1, DEGREE + 2) / (DEGREE + 1))[::-1]
# A piece shorter than this, in hours, is not cut again: it holds what the fit gives.
SHORTEST = 1e-9
# A fit holds a value to its tolerance, or to this part of its largest size in the piece, which
# the roundoff of a value far from zero allows.
RELATIVE = 1e-12
# The most cuts of one fit: after them, each piece holds what its fit gives.
MOST = 4096


def _times(start, end, points):
    return start + (points + 1.0) * 0.5 * (end - start)


def fitted(values, start, end, tolerance):
    """The pieces of k values from `start` to `end`: one list for each value, each piece a (time,
    value, rate). `values(times)` gives an array of one row for each time; `tolerance` holds one
    number for each value, which a fit may widen to `RELATIVE` of the value's largest size in the
    piece. A value that the series holds as a constant has the rate 0, and any other a `Curve` in
    its place, which the record's piece keeps in its own field (`_history`): a line too, as a series
    of degree one, since its slope is the fit's over the span that it was fitted to, and so follows
    where the run ended in its last digits, as a curve does (`settled`)."""
    found = [[] for _ in tolerance]
    pending, cuts = [(start, end)], 0
    while pending:
        a, b = pending.pop()
        nodes = values(_times(a, b, _NODES))
        coefficients = chebyshev.chebfit(_NODES, nodes, DEGREE)
        allowed = np.maximum(tolerance, RELATIVE * np.max(np.abs(nodes), axis=0))
        if b - a > SHORTEST and cuts < MOST:
            checks = values(_times(a, b, _CHECKS))
            first = checks[0]
            allowed = np.maximum(allowed, RELATIVE * np.max(np.abs(checks), axis=0))
            made = chebyshev.chebval(_CHECKS, coefficients).T
            made = made - chebyshev.chebval(-1.0, coefficients) + first
            if np.any(np.abs(made - checks) > allowed):
                middle = 0.5 * (a + b)
                pending += [(middle, b), (a, middle)]
                cuts += 1
                continue
        else:
            first = values(np.array([a]))[0]
        for k, at in enumerate(found):
            series = coefficients[:, k] if coefficients.ndim > 1 else coefficients
            curved = series[2:]
            if np.all(np.abs(curved) <= allowed[k] / 16):
                # A line: its slope is the first coefficient over the half of the span; a constant is
                # what any fit of it gives, and a line of another slope is the fit's (see above).
                slope = float(series[1]) * 2.0 / (b - a) if b > a else 0.0
                line = Curve(b - a, (float(series[0]), float(series[1])))
                at.append((a, float(first[k]), 0.0 if slope == 0 else line))
            else:
                at.append((a, float(first[k]), Curve(b - a, tuple(float(c) for c in series))))
    return [sorted(pieces, key=lambda piece: piece[0]) for pieces in found]


def _compact(pieces):
    """The pieces with each that continues the line of the one before it left out."""
    if len(pieces) < 2:
        return pieces
    kept = []
    for t, value, rate in pieces:
        if kept and not isinstance(rate, Curve) and not isinstance(value, (bool, str, Unavailable)):
            t0, v0, r0 = kept[-1]
            if not isinstance(r0, Curve) and not isinstance(v0, (bool, str, Unavailable)):
                scale = max(abs(v0), abs(value), 1e-300)
                if rate == r0 and abs(v0 + r0 * (t - t0) - value) <= 1e-13 * scale:
                    continue
        elif kept and isinstance(value, (bool, str, Unavailable)) and kept[-1][1] == value:
            continue
        kept.append((t, value, rate))
    return kept


class Recorder:
    """The pieces of each value of one run, and its trace (see the module). `constants` holds the
    value of each input, draw, stored value and captured property at the start."""

    def __init__(self, plan, constants, tolerance):
        self.plan, self.constants, self.tolerance = plan, constants, tolerance
        self.pieces = {}  # engine name -> [(t, value, rate)]
        self.trace = []
        self.formulas = set()  # the formulas whose pieces the run gives (the family's settings)
        self.run = None  # the run, which knows the entries that each collection keeps
        self.round = 0  # the round of the moment where the run is
        self._wanted = None  # the engine names whose histories a record of some keys needs
        # A store that edits changed -> (its start, [(time, amount from outside)]) (`external`).
        self.transfers = {}

    def entry(self, t, kind, part, owner='', **details):
        """One entry of the trace, in the round where the run is (`round`: 0 is the setup)."""
        self.trace.append(Entry(t, self.round, kind, part, owner, tuple(details.items())))

    def failure(self, t, message):
        """The entry of the failure that stopped a run at time t."""
        return Entry(t, self.round, 'failure', '', '', (('message', message),))

    def external(self, store, t, amount, start):
        """An edit at a stop moved `amount` into a store from outside (a withdrawal is negative): its
        books hold it as an external transfer, the history `external` beside the store, what edits
        brought in so far, a piece at each edit. `start` is when the store started, which the run's
        savepoint keeps with the transfers (`moment._Savepoint`); the ledger reads 0 from then to its
        first edit without a piece of its own."""
        self.transfers.setdefault(store, (start, []))[1].append((t, amount))

    def segment(self, component, segment, stores, flows):
        """The pieces of the stores and the flows of a component over one of its segments."""
        start, end, solution = segment.start, segment.end, segment.solution
        if end <= start:
            for k, name in enumerate(stores):
                self._add(name, [(start, float(segment.last[k]), 0.0)])
            return
        context = component.context
        if isinstance(solution, (Affine, MatrixExponential)):
            curved = set()
            if isinstance(solution, MatrixExponential):
                curved = {int(i) for i in solution.columns[solution.rows]}
            for k, name in enumerate(stores):
                if k not in curved:
                    self._add(name, [(start, float(segment.first[k]), float(solution.slope[k]))])
            spans = [(start, end)]
        else:
            curved = set(range(len(stores)))
            steps = segment.numerical.t
            spans = list(pairwise(steps))
        if curved:
            order = sorted(curved)
            tolerance = np.array([self.tolerance[stores[k]] for k in order])

            def states(times):
                return np.array([context.project(solution(at))[order] for at in times])

            for a, b in spans:
                for k, pieces in zip(order, fitted(states, float(a), float(b), tolerance)):
                    if a == start:
                        pieces[0] = (start, float(segment.first[k]), pieces[0][2])
                    self._add(stores[k], pieces)
        if not flows:
            return
        if isinstance(solution, Affine):
            rates = component.delivered(segment, [0.5 * (start + end)])[0]
            for k, name in enumerate(flows):
                self._add(name, [(start, float(rates[k]), 0.0)])
            return
        tolerance = np.array([self.tolerance[name] for name in flows])
        for a, b in spans:
            for name, pieces in zip(
                flows,
                fitted(lambda times: component.delivered(segment, times), float(a), float(b), tolerance),
            ):
                self._add(name, pieces)

    def _add(self, name, pieces):
        self.pieces.setdefault(name, []).extend(pieces)

    def add(self, name, t, value, rate):
        """One piece of a value, which a run gives as it goes."""
        self.pieces.setdefault(name, []).append((t, value, rate))

    def add_pieces(self, name, pieces):
        """Pieces of a value, which a run gives as it goes."""
        self._add(name, pieces)

    def defined(self, name):
        """A commit gave a value a new definition: a record of some keys that needs the value keeps
        what the new definition reads from now on. Gives the names that it keeps now and did not."""
        if self._wanted is None or name not in self._wanted:
            return set()
        found = self._needed_names([name]) - self._wanted
        self._wanted |= found
        return found

    def wanted(self, name):
        """Whether the record keeps the history of an engine name (or what a kept formula reads)."""
        request = self.plan.configuration.request
        if request.everything:
            return True
        if self._wanted is None:
            self._wanted = self._needed(request.keys)
            for key in request.keys:
                value = self.plan.values.get(name_of(key))
                if value is not None and value.kind == FORMULA:
                    self._wanted |= self.plan.formula_reads(value.node)[0]
        return name in self._wanted

    # ---- after the run ----------------------------------------------------------------------------

    def record(self, end, failure=None, pause=None):
        """The record of the run, to the time `end` at which it stopped (the horizon, or the time of
        its failure or of its stop at a breakpoint, whose entry ends the trace)."""
        plan, run = self.plan, self.run
        request = plan.configuration.request
        last = failure if failure is not None else pause
        trace = tuple(self.trace) + ((last,) if last is not None else ())
        needed = None if request.everything else _needed_by(plan.program, request.keys, trace, plan)[1]
        # The occurrences that the trace starts (None: no occurrence's): a start that a failed commit
        # discarded is in the plan, and its values are in no record (`moment._Savepoint`).
        started = {entry.owner for entry in self.trace if entry.kind == 'start'} | {None}
        histories = {}
        for name, value in plan.values.items():
            if needed is not None and name not in needed:
                continue
            if plan.occurrence_of(name) not in started:
                continue
            if value.kind in (FORMULA, REDUCE, LOOKUP, DYNAMIC, CHANGED) or name in plan.defined:
                continue
            # The value at the start, then the pieces that the run gave it: a store's lines and
            # curves, a value that a commit wrote, an occurrence's values from its start.
            pieces = [(0.0, self.constants[name], 0.0)] if name in self.constants else []
            pieces += [piece for piece in self.pieces.get(name, ()) if piece[0] <= end]
            histories[name] = self._history(value.key, pieces)
        for name, stored in plan.changed.items():
            if stored in histories:
                # The time of the last change at a commit: a constant piece at the start and at each.
                times = [run.changed_start(stored), *run.changes.get(stored, ())]
                histories[name] = self._history(None, [(at, at, 0.0) for at in times if at <= end])
        calculated = {
            name
            for name, value in plan.values.items()
            if (value.kind in (FORMULA, REDUCE, LOOKUP, DYNAMIC) or name in plan.defined)
            and (needed is None or name in needed)
            and plan.occurrence_of(name) in started
        }
        for name in plan.ordered(calculated, ever=True):
            value = plan.values[name]
            owner = plan.occurrence_of(name)
            start = 0.0
            if owner is not None:
                # A formula of an occurrence exists from its start, and keeps after its finish the
                # value that it had then (D7).
                start = histories[f'{owner}.started'].pieces[0].t
            if name in plan.defined:
                histories[name] = self._history(value.key, self._defined(name, histories, end))
                continue
            if name in self.formulas:
                pieces = [piece for piece in self.pieces.get(name, ()) if piece[0] <= end]
            elif value.kind == REDUCE:
                pieces = self._reduction(name, histories, end)
            elif value.kind == LOOKUP:
                pieces = self._lookup(name, histories, end)
            elif value.kind == DYNAMIC:
                pieces = self._dynamic(name, histories, end)
            elif (
                isinstance(value.node, nodes.Ref) and value.node.name in histories and name not in run.frozen
            ):
                # A formula that names another value has its history.
                found = histories[value.node.name].pieces
                histories[name] = History(
                    value.key, tuple(piece for piece in found if piece.t >= start) or found
                )
                continue
            else:
                pieces = self.formula(name, histories, end, start=start)
            if name in run.frozen:
                finish = next(piece[0] for piece in self.pieces[name])
                pieces = [piece for piece in pieces if piece[0] < finish] + [(finish, run.frozen[name], 0.0)]
            histories[name] = self._history(value.key, pieces)
        # What a kept formula, reduction or dynamic read reads is kept too, so that `read` can
        # evaluate it (`_needed`).
        keys = set(request.keys)
        if needed is not None:
            keys |= {plan.values[name].key for name in needed if plan.values[name].key is not None}
        # The ledger of every store that an edit changed by the end, whatever the request names: the
        # books of the store, which a record that holds the store, or the ledger, reads. Its first
        # piece is at the first edit, so a record that ends before it holds none (see the module).
        for name, (_, moved) in self.transfers.items():
            key = plan.values[name].key
            if key is None or plan.occurrence_of(name) not in started:
                continue
            total, pieces = 0.0, []
            for at, amount in moved:
                if at <= end:
                    total += amount
                    pieces.append((at, total, 0.0))
            if not pieces:
                continue
            ledger = Key(key.owner, (*key.steps, 'external'))
            histories[f'{name}.external'] = self._history(ledger, pieces)
            keys.add(ledger)
        held = [
            history
            for history in histories.values()
            if history.key is not None and history.pieces and (request.everything or history.key in keys)
        ]
        manifest = Manifest(request.horizon, request.everything, request.keys)
        made = _finished(Record(manifest, tuple(held), trace, failure))
        # The values that the record holds stay within the request's budget of pieces (R-A4a-07); a
        # record that its budget ends keeps what a record to that end keeps (`requested`), as a cut
        # of a longer record does.
        bounded = made.within(request.pieces)
        return bounded if bounded is made else requested(bounded, plan.program, plan)

    @staticmethod
    def _history(key, pieces):
        """The history of a value from its pieces (t, value, rate), a `Curve` in place of the rate of
        a curved piece."""
        if len(pieces) == 1 and not isinstance(pieces[0][2], Curve):
            return History(key, (Piece(*pieces[0]),))
        return History(
            key,
            tuple(
                Piece(t, value, curve=rate) if isinstance(rate, Curve) else Piece(t, value, rate)
                for t, value, rate in _compact(pieces)
            ),
        )

    def _lookup(self, name, histories, end):
        """The pieces of a keyed read: of a stepped one, over each of its key intervals, the pieces of
        the value of the member that it selects there (below its first key `Unavailable`); of any
        other, from the histories of what it reads, as a formula's."""
        plan, run = self.plan, self.run
        keyed = plan.keyed[name]
        boolean = plan.values[name].boolean
        try:
            stepped = run.stepped_of(name) if plan.stepped(name) else None
            if stepped is None:
                run.kept_of(name)
        except FAILURES as problem:
            return [(0.0, Unavailable(str(problem)), 0.0)]
        if stepped is None:
            # What can change of what it reads has a history; what the inputs fix holds its start. A
            # constant key over the natural keys reads the entry that it selects alone (`Plan.reads`),
            # so a chain of such reads reads one history a link.
            index = run.index_for(name)

            def compute(env):
                value = lambda read: env[read] if read in env else run.value_of(read)  # noqa: E731
                return looked_up(keyed, value, plan.units, env['t'], index)

            return self.formula(
                name,
                histories,
                end,
                sorted(plan.reads(name)),
                compute,
                boolean,
                timed=plan.lookup_reads(name).time,
            )
        times = stepped.times.tolist()
        pieces = []
        try:
            stepped.place(0.0)
        except ExpressionError as problem:
            pieces.append((0.0, Unavailable(str(problem)), 0.0))
        for k, at in enumerate(times):
            a = max(float(at), 0.0)
            b = min(float(times[k + 1]), end) if k + 1 < len(times) else end
            if a > end or (b <= a and k + 1 < len(times)):
                continue
            selected = stepped.names[k]
            found = self.formula(
                name, histories, b, [selected], lambda env, selected=selected: env[selected], boolean, start=a
            )
            pieces += [piece for piece in found if piece[0] < b or k + 1 == len(times)]
        return pieces

    def _reduction(self, name, histories, end):
        """The pieces of a reduction from the histories of its kept entries."""
        plan, run = self.plan, self.run
        reduction = plan.reductions[name]
        try:
            entries = run.kept_of(name)
        except FAILURES as problem:
            return [(0.0, Unavailable(str(problem)), 0.0)]
        if reduction.names is None:
            return [(0.0, len(entries), 0.0)]
        reads = [reduction.names[k] for k in entries]
        own = [
            [
                (piece.t, piece.value, piece.rate if piece.curve is None else piece.curve)
                for piece in histories[read].pieces
            ]
            for read in reads
        ]
        exact = history_of(reduction, entries, own, end)
        if exact is not None:
            return exact
        if not reads:
            try:
                return [(0.0, reduced(reduction, histories.__getitem__, plan.units, entries), 0.0)]
            except FAILURES as problem:
                return [(0.0, Unavailable(str(problem)), 0.0)]
        boolean = plan.values[name].boolean
        return self.formula(
            name,
            histories,
            end,
            reads,
            lambda env: reduced(reduction, env.__getitem__, plan.units, entries),
            boolean,
        )

    def _dynamic(self, name, histories, end):
        """The pieces of a dynamic read from the histories of what its members project and of the
        fields that say when each is a member."""
        plan = self.plan
        dynamic = plan.dynamic[name]

        def point(t, readers):
            def value(read):
                if read not in readers:
                    raise LookupError(f'the record holds no value of {read}')
                return known(readers[read](t))

            members = plan.members_at(dynamic.source, value)
            return dynamic_value(dynamic, members, lambda each: plan.project(each, dynamic.steps), value, t)

        return self.formula(name, histories, end, sorted(plan.dynamic_reads(name)), point=point)

    def formula(
        self,
        name,
        histories,
        end,
        reads=None,
        compute=None,
        boolean=None,
        start=0.0,
        point=None,
        node=None,
        timed=None,
    ):
        """The pieces of a formula from the histories of what it reads, from `start` on (of a
        reduction or a keyed read, when `reads` and `compute` are given: the names that it reads,
        and its value from theirs, `timed` when it reads the time; of a dynamic read, when `point`
        gives its value at a time; of one definition that a commit gave the value, when `node` is its
        node)."""
        plan = self.plan
        value = plan.values[name]
        node = value.node if node is None else node
        if timed is None:
            timed = compute is None and point is None and 't' in nodes.names(node)
        if reads is None:
            reads = sorted(set(nodes.names(node)) - {'t'})
        reads = [read for read in reads if read in histories]
        if compute is None:

            def compute(env):
                return evaluate(node, env, plan.units)

        boolean = value.boolean if boolean is None else boolean
        times = sorted(
            {
                float(start),
                *(piece.t for read in reads for piece in histories[read].pieces if start <= piece.t <= end),
            }
        )
        bounds = [*times, max(end, times[-1])]
        readers = {read: _reader(histories[read]) for read in reads}
        holders = {read: _holder(histories[read]) for read in reads}

        names = frozenset(reads)

        def at(t):
            if point is not None:
                return point(t, readers)
            # Each read is taken from its history where the evaluation asks for it (`reads.py`).
            return compute(Reads(names, lambda read: readers[read](t), t))

        def tried(t):
            """The value at t, or `Unavailable` with the reason where it cannot be evaluated."""
            try:
                return at(t)
            except FAILURES as problem:
                return Unavailable(str(problem))

        firsts = [tried(time) for time in times]
        # A yes/no and a text (an enum member) change by steps; a number is fitted.
        discrete = boolean or any(isinstance(found, str) for found in firsts)

        def cast(found):
            if isinstance(found, Unavailable | str):
                return found
            return bool(found) if boolean else float(found)

        # The size of the formula, as a store's: the largest magnitude that it takes at a time at
        # which what it reads has a piece.
        size = 1.0
        if not discrete:
            for found in firsts:
                if not isinstance(found, Unavailable):
                    size = max(size, abs(float(found)))
        tolerance = np.array([plan.numerics.atol_factor * size])
        crossing = plan.numerics.crossing
        pieces = []
        for (a, b), first in zip(pairwise(bounds), firsts):
            if b <= a or (not timed and all(holders[read](a) for read in reads)):
                # What the formula reads holds its value from a to b: so does the formula.
                pieces.append((a, cast(first), 0.0))
            elif discrete:
                # Where it cannot be evaluated is one more value of the yes/no or the text.
                pieces += _switches(lambda time: cast(tried(time)), a, b, cast(first), crossing)
            else:
                pieces += _numbers(at, tried, a, b, first, tolerance, crossing)
        return pieces

    def _defined(self, name, histories, end):
        """The pieces of a value that commits gave new definitions (`Plan.defined`): over the time of
        each definition, a formula's from the histories of what it reads, and a captured number's
        from what the run wrote; from the finish of its occurrence, the value that froze then (D7)."""
        plan, run = self.plan, self.run
        definitions = plan.defined[name]
        owner = plan.occurrence_of(name)
        finish = None
        if name in run.frozen:
            active = histories[f'{owner}.active'].pieces
            finish = next(piece.t for piece in active if piece.value is False)
        stop = end if finish is None else min(end, finish)
        written = [(0.0, self.constants[name], 0.0)] if name in self.constants else []
        written += self.pieces.get(name, ())
        pieces = []
        for k, (a, value) in enumerate(definitions):
            last = k + 1 == len(definitions)
            b = stop if last else min(definitions[k + 1][0], stop)
            if a > stop or (b <= a and not last):
                continue  # replaced at the time that it was given, or after the finish
            if value.kind == FORMULA:
                found = self.formula(name, histories, b, start=a, node=value.node)
            else:
                found = [piece for piece in written if a <= piece[0] <= b]
            pieces += [piece for piece in found if piece[0] < b or (last and piece[0] <= b)]
        if finish is not None and finish <= end:
            pieces = [piece for piece in pieces if piece[0] < finish] + [(finish, run.frozen[name], 0.0)]
        return pieces


def needed(plan, names, definitions):
    """The engine names whose histories a record of only these names needs: theirs, what their
    formulas, reductions, keyed and dynamic reads read under each definition that they have
    (`definitions`, {name: [(time, value)]}, as `Plan.definitions_of` gives them), the value that the
    time of a change follows, and the fields that say when each occurrence among them is. Each name
    adds what it reads directly (`Plan.reads` of its declared value, and the node of each
    definition), which the walk follows in turn, so a chain is walked once, and not once for each of
    its links."""
    found = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in found or name not in plan.values:
            continue
        found.add(name)
        kind = plan.values[name].kind
        if kind in (FORMULA, REDUCE, LOOKUP) or name in definitions:
            if kind in (FORMULA, REDUCE, LOOKUP):
                pending.extend(plan.reads(name))
            for _, value in definitions.get(name, ()):
                if value.kind == FORMULA:
                    pending.extend(set(nodes.names(value.node)) - {'t'})
        elif kind == CHANGED:
            pending += sorted(plan.reads(name))  # the value that it follows
        elif kind == DYNAMIC:
            pending += sorted(plan.dynamic_reads(name))  # what its members project, and when
        owner = plan.occurrence_of(name)
        if owner is not None:
            pending += [f'{owner}.started', f'{owner}.active']
    return found


def requested(record, program, plan=None):
    """The record with what a record of its request keeps: every history, of a record of every value;
    else the histories that its manifest names, those that their values need (`needed`, under the
    occurrences that its trace starts and the definitions that its commits gave), and the ledger of
    each store that an edit changed by its end (the store's books, `Manifest.names`); each history in
    the order of its key, a piece at its end holding its value there (`_finished`). It is the one rule of what a record holds, of a run's (`Recorder.record`)
    and of a cut of a longer record (`store.served`), so a cut is the record of a fresh run of the
    shorter request, its histories included. `plan` is a plan of the program that may serve
    (`plan_for`)."""
    histories = record.histories
    if not record.manifest.everything:
        found, names = _needed_by(program, record.manifest.keys, record.trace, plan)
        keys = set(record.manifest.keys) | {found.values[name].key for name in names}
        histories = [history for history in histories if history.key in keys or history.key.store is not None]
    return _finished(Record(record.manifest, tuple(histories), record.trace, record.failure))


def _finished(record):
    """A record as the rule holds it (`requested`): each history in the order of its key, whatever
    made the record, and each piece that starts at the record's end holding its value there, since the
    record holds nothing after its end: a run that ends there and one that goes on differ only in the
    rate there, which no read of the record sees. Such a piece that then continues the one before it
    is left out, as the recorder leaves it out (`_compact`)."""
    end = record.end
    histories = []
    for history in sorted(record.histories, key=_order):
        if any(piece.t == end and (piece.rate != 0 or piece.curve is not None) for piece in history.pieces):
            pieces = [
                (piece.t, piece.value, 0.0)
                if piece.t == end
                else (piece.t, piece.value, piece.rate if piece.curve is None else piece.curve)
                for piece in history.pieces
            ]
            histories.append(Recorder._history(history.key, pieces))
        else:
            histories.append(history)
    return Record(record.manifest, tuple(histories), record.trace, record.failure)


def settled(record, program, plan=None):
    """Whether every piece that a record keeps is what any run to its end makes, so that a longer
    run's record cut at that end, or ended there by its budget, is the record of a run to it
    (`store.served`): no history is on a curve, which a fit makes (`fitted`: a line of the fit's
    slope is one too) over the span that the run's end ends; and no value that the record makes after
    the run from what it reads (a formula, a reduction, a keyed or a dynamic read, a value that a
    commit gave a new definition) has a piece where nothing else that the record keeps has one: a
    change found by bisection, over a stretch that the run's end ends. What holds between the pieces
    of what it reads, and starts with them, is what any run makes."""
    if any(piece.curve is not None for history in record.histories for piece in history.pieces):
        return False
    plan = plan_for(program, record.trace, plan)
    definitions = plan.definitions_of(record.trace)
    calculated = {
        value.key
        for name, value in plan.values.items()
        if value.key is not None and (value.kind in (FORMULA, REDUCE, LOOKUP, DYNAMIC) or name in definitions)
    }
    times = {
        piece.t for history in record.histories if history.key not in calculated for piece in history.pieces
    }
    return all(
        piece.t in times
        for history in record.histories
        if history.key in calculated
        for piece in history.pieces
    )


def _needed_by(program, keys, trace, plan=None):
    """(the plan, the engine names) of what a record of only `keys` that ends with `trace` needs
    (`needed`): on a plan whose values are as the program declares them and whose occurrences are
    those that the trace starts (`plan_for`), under the definitions that the trace's commits gave."""
    plan = plan_for(program, trace, plan)
    return plan, needed(plan, [name_of(key) for key in keys], plan.definitions_of(trace))


def plan_for(program, trace, plan=None):
    """A plan of a program whose values are as the program declares them (no commit gave one a new
    definition) and whose occurrences are those that a trace starts: `plan`, or the plan that the
    reader keeps (`remember`), when it is one; else one made again from the trace (`Plan.replay`). So
    what a record needs follows from the record, and not from the run that made the plan."""
    starts = {entry.owner for entry in trace if entry.kind == 'start'}
    kept = _PLANS.get(id(program))
    for found in (plan, kept[1] if kept is not None and kept[0] is program else None):
        if (
            found is not None
            and not found.defined
            and starts == {occurrence for made in found.occurrences.values() for occurrence in made}
        ):
            return found
    made = Plan.of(program, Configuration(Request(0)))
    made.replay(trace)
    return made


def _order(history):
    """The place of a history in a record: by its key, whatever made the record."""
    return history.key.owner, history.key.steps


def _switches(at, a, b, first, crossing):
    """The pieces of a yes/no or a text from a to b: one at a, and one at each change, which
    bisection locates between the points of a fit to within the crossing tolerance. `Unavailable` is
    one value whatever its reason: a stretch where the value cannot be evaluated keeps the reason
    that it has where it starts."""
    pieces, value = [(a, first, 0.0)], first
    points = _times(a, b, np.concatenate([[-1.0], _CHECKS[1:-1], [1.0]]))
    for before, after in pairwise(points):
        if _same(at(after), value):
            continue
        left, right = before, after
        while right - left > crossing:
            middle = 0.5 * (left + right)
            if _same(at(middle), value):
                left = middle
            else:
                right = middle
        value = at(right)
        pieces.append((right, value, 0.0))
    return pieces


def _same(found, value):
    """Whether two values of a piece are one: equal, or both `Unavailable`."""
    if isinstance(found, Unavailable) or isinstance(value, Unavailable):
        return isinstance(found, Unavailable) and isinstance(value, Unavailable)
    return found == value


def _numbers(at, tried, a, b, first, tolerance, crossing):
    """The pieces of a number from a to b: fitted (`fitted`) where it can be evaluated, and
    `Unavailable` with the reason where it cannot (`at(t)` raises one of `FAILURES` there, `tried(t)`
    gives it), each change between the two found to within the crossing tolerance as a change of a
    yes/no is (`_switches`). A failure between the points of that search makes the rest of its
    stretch unavailable."""

    def fit(c, d):
        try:
            return fitted(lambda ts: np.array([[float(at(t))] for t in ts]), c, d, tolerance)[0]
        except FAILURES as problem:
            return [(c, Unavailable(str(problem)), 0.0)]

    if not isinstance(first, Unavailable):
        found = fit(a, b)
        if not any(isinstance(piece[1], Unavailable) for piece in found):
            return found
    stretches = _switches(
        lambda t: not isinstance(tried(t), Unavailable), a, b, not isinstance(first, Unavailable), crossing
    )
    pieces = []
    for (c, available, _), d in zip(stretches, [*(stretch[0] for stretch in stretches[1:]), b]):
        pieces += fit(c, d) if available else [(c, tried(c), 0.0)]
    return pieces


def _reader(history):
    """`History.at` of a history, by bisection over the times of its pieces."""
    times = [piece.t for piece in history.pieces]

    def at(time):
        k = bisect_right(times, time) - 1
        if k < 0:
            raise LookupError(f'{history.key} has no value at {time} h')
        return history.pieces[k].at(time)

    return at


def _holder(history):
    """Whether the piece of a history at a time holds its value: no rate and no curve."""
    times = [piece.t for piece in history.pieces]

    def holds(time):
        k = bisect_right(times, time) - 1
        return k >= 0 and history.pieces[k].curve is None and history.pieces[k].rate == 0

    return holds


# ---- the reader ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """The values of one path at the times that a reader asks: numbers in the declared unit `unit`,
    yes/no values, or `Unavailable` with its reason."""

    path: str
    key: Key
    unit: str
    values: tuple


def key_of(program, path):
    """The record key of a path: a `Key` as it is, or a text that starts with an occurrence's id
    (`tank.receive#0.remaining`), a member's id (the longest that matches) or a name of the root
    (`tank.water`, `clinic.delivery.actual_rate`, `effort`)."""
    if isinstance(path, Key):
        return path
    head, mark, rest = path.partition('#')
    if mark:
        number, _, steps = rest.partition('.')
        return Key(f'{head}#{number}', tuple(steps.split('.')) if steps else ())
    parts = path.split('.')
    for cut in range(len(parts) - 1, 0, -1):
        owner = '.'.join(parts[:cut])
        try:
            program.member(owner)
        except KeyError:
            continue
        return Key(owner, tuple(parts[cut:]))
    return Key('', tuple(parts))


def unit_of(program, key):
    """The spelling of the declared unit of the value at a key and its scale, a float (`declared`
    gives it exactly)."""
    unit, scale = declared(program, key)
    return unit, float(scale)


def declared(program, key):
    """The spelling of the declared unit of the value at a key and its exact scale (a Fraction): of a
    value, its type's unit; of a flow's actual rate, request or capacity, the flow's unit, and of a
    leg's, the leg's; of an endpoint's, its store's unit per hour (time is in hours, at scale 1); `''`
    for a plain number or a yes/no, such as a `served_fraction`. A key that names no value is a
    KeyError, and so is a reference to an occurrence (`parts.OccurrenceType`): it names an
    occurrence, whose values the record holds under its own path, and no record holds the reference."""
    if '#' in key.owner:
        receiver, event = key.owner.rsplit('#', 1)[0].rsplit('.', 1)
        found = program.member(receiver)[0].part(event)
        if key.steps[0] in ('started', 'done', 'active'):
            return '', Fraction(1)  # the time of the start is in hours; the others are yes/no values
        part = next((each for each in (*found.params, *found.locals) if each.name == key.steps[0]), None)
    elif key.owner:
        template = program.member(key.owner)[0]
        part = template.part(key.steps[0])
        if part is None and key.steps == ('status',) and template.status is not None:
            return '', Fraction(1)  # a status display: the text of the case that applies
    else:
        part = program.root_value(key.steps[0])
    if part is None:
        raise KeyError(f'{key}: no value of the program')
    value_type = getattr(part, 'type', None)
    if isinstance(value_type, OccurrenceType):
        raise KeyError(
            f'{key}: a reference to an occurrence of {value_type.template}.{value_type.event} is no value that '
            'a record holds: read the occurrence that it names by its own path'
        )
    if getattr(part, 'legs', ()) and len(key.steps) >= 3:
        # A field of a leg is in the leg's unit; the parent's `served_fraction` is a plain number.
        part = next((leg for leg in part.legs if leg.name == key.steps[1]), part)
        value_type = getattr(part, 'type', None)
    if hasattr(part, 'unit'):  # a flow has a unit
        unit = part.unit
    elif isinstance(value_type, DistributionType):  # `.mean` and `.std` are in its numbers' unit
        unit = getattr(value_type.of, 'unit', '')
    else:
        unit = getattr(value_type, 'unit', '')
    scale = Fraction(1) if unit == '' else Fraction(program.unit(unit).scale)
    if len(key.steps) >= 3 and key.steps[1] in ('outflow', 'inflow'):
        return (f'{unit}/h' if unit else '1/h'), scale
    return unit, scale


def in_unit(value, scale):
    """A number in canonical units in the unit of an exact scale, rounded once; any other value (a
    yes/no, a text, `Unavailable`) as it is."""
    if isinstance(value, (bool, str, Unavailable)):
        return value
    if scale == 1 or not math.isfinite(value):
        return float(value)
    return float(Fraction(value) / scale)


# The plan of the program that a reader or a run used last: a program is read again and again.
_PLANS = {}


def remember(plan):
    """Keep the plan of a run for the reader: what a configuration sets changes no formula, no
    reduction and no keyed read, so the plan of any run of a program serves every record of it. A
    definition that a commit gave a value is in the trace of its record (`Plan.definitions_of`), and
    the reader reads the plan's values as the program declares them (`Plan.original`)."""
    _PLANS.clear()
    _PLANS[id(plan.program)] = (plan.program, plan)


def _plan_of(program, record=None):
    """A plan of a program, which names each formula with its node: the plan that a run of it
    kept, else the plan of a bare request. A record whose occurrences that plan does not hold has
    them made again in a plan of its own, from the starts of its trace (`Plan.replay`)."""
    found = _PLANS.get(id(program))
    if found is None or found[0] is not program:
        remember(Plan.of(program, Configuration(Request(0))))
        found = _PLANS[id(program)]
    plan = found[1]
    if record is not None:
        starts = {entry.owner for entry in record.trace if entry.kind == 'start'}
        if starts != {occ for occurrences in plan.occurrences.values() for occ in occurrences}:
            plan = Plan.of(program, Configuration(Request(0)))
            plan.replay(record.trace)
    return plan


class _Pending(Exception):
    """Reads that an evaluation of the reader asks for before the reader has their values: the reader
    finds those values first and evaluates again, so a long chain of formulas needs no recursion."""

    def __init__(self, names):
        super().__init__(names)
        self.names = tuple(names)


class Reader:
    """The values of one record at the times that a caller asks (see the module): each from what the
    record holds (`Record.unavailable`), else `Unavailable` with the reason; and, for each value that
    it evaluates at a time, what that evaluation read (`reads`). Each value at each time is found
    once, depth first with no recursion: an evaluation that asks for a read that is not known yet
    waits while the reader finds it (`_Pending`). Within the reader a value that has none at a time
    (an occurrence that has not started, a history that the record does not keep) is a LookupError,
    which a collection reads as "not a member yet"; `value` gives the reason as `Unavailable`."""

    def __init__(self, record, program):
        self.record, self.program = record, program
        self.plan = _plan_of(program, record)
        # The definitions that the commits of the run gave values, from its trace: a value is read
        # with the definition that it had at the time of the read.
        self.definitions = self.plan.definitions_of(record.trace)
        # When each occurrence started, from the trace, which every record holds whole.
        self.starts = {entry.owner: float(entry.t) for entry in record.trace if entry.kind == 'start'}
        self.found = {}  # (engine name, time) -> its value, or the LookupError of a value that has none
        self.read = {}  # (engine name, time) -> the engine names that its evaluation read, in order
        self.kept = {}
        self._stores = None
        self._always = {}  # the id of a node -> what every evaluation of it reads (`proofs.always`)

    # ---- what a caller asks -------------------------------------------------------------------------

    def readings(self, paths, times):
        """One `Reading` for each path, in order, of its values at the times in their order (see
        `read`)."""
        found = []
        for path in paths:
            key = key_of(self.program, path)
            unit, scale = declared(self.program, key)
            values = tuple(in_unit(self.value(key, t), scale) for t in times)
            found.append(Reading(name_of(path) if isinstance(path, Key) else path, key, unit, values))
        return found

    def value(self, key, t):
        """The value of a record key at a time in canonical units, from what the record holds, else
        `Unavailable` with the reason: a time or a value that the record does not hold
        (`Record.unavailable`), an occurrence that has not started then (from the trace), a value
        that cannot be read. A ledger that names no store is a KeyError: it is no value."""
        t = float(t)
        if key.store is not None and name_of(key.store) not in self.stores():
            raise KeyError(
                f'{key}: {key.store} is no store, and only a store has a ledger of what came from outside'
            )
        reason = self.refusal(key, t)
        if reason is not None:
            return Unavailable(reason)
        try:
            if key.store is not None:
                return self.ledger(key, t)
            return self.at(name_of(key), t)
        except LookupError as problem:
            stopped = self.record.stopped()
            return Unavailable(str(problem) + (f': {stopped}' if stopped else ''))

    def refusal(self, key, t):
        """Why the reader gives no value of a record key at a time before it reads one: a time or a
        value that the record does not hold (`Record.unavailable`), an occurrence that has not
        started then; None when `value` reads it, from its history or by an evaluation (`at`)."""
        reason = self.record.unavailable(key, t)
        if reason is None and '#' in key.owner and not self.started(key.owner, t):
            reason = f'{key.owner} has not started at {float(t):g} h'
        return reason

    def ledger(self, key, t):
        """What edits brought into a store from outside up to time t (`Recorder.external`): the record
        keeps the ledger of every store that an edit changed by its end, whatever its request names,
        from its first edit, so a store with none, or a time before its first edit, took nothing from
        outside."""
        try:
            history = self.record.history(key)
        except KeyError:
            return 0.0
        return history.at(t) if history.pieces[0].t <= t else 0.0

    def stores(self):
        """The engine names of the stores of the run: the stored numbers that its flows meet."""
        if self._stores is None:
            self._stores = {
                end
                for connection in self.plan.connections.values()
                for end in (connection.source, connection.sink)
                if end is not None
            }
        return self._stores

    def started(self, owner, t):
        """Whether an occurrence has started at time t: its start is in the trace, at or before t."""
        start = self.starts.get(owner)
        return start is not None and start <= t

    def reads(self, name, t):
        """The engine names that the evaluation of an engine name at a time read, after `at` found its
        value: what its formula asked for, the members and the entries that a collection read; none
        for a value read from its history."""
        return self.read.get((name, float(t)), ())

    def evaluates(self, name):
        """Whether the reader finds the value of an engine name by an evaluation of what it reads (a
        formula, a collection, the time of a change) rather than from its history."""
        value = self.plan.values.get(name)
        return value is not None and (
            self.plan.original(name).kind in (FORMULA, REDUCE, LOOKUP, DYNAMIC, CHANGED)
            or name in self.definitions
        )

    # ---- the values of engine names ---------------------------------------------------------------

    def at(self, name, t):
        """The value of an engine name at a time, from its history, or for a formula, a collection or
        the time of a change from what it reads, in canonical units; a LookupError for a value that
        has none then. Depth first, with no recursion (see the class)."""
        t = float(t)
        stack, waiting = [name], set()
        while stack:
            top = stack[-1]
            if (top, t) in self.found:
                stack.pop()
                waiting.discard(top)
                continue
            try:
                self.found[top, t] = self._evaluate(top, t)
            except _Pending as pending:
                # The reads go first; a read that waits already reads this value: a cycle, which the
                # program's check refuses, and which the reader never loops on.
                waiting.add(top)
                for other in pending.names:
                    if other in waiting:
                        raise SimulationError(f'{other} reads itself') from None
                stack.extend(pending.names)
                continue
            except LookupError as problem:
                self.found[top, t] = problem
            stack.pop()
            waiting.discard(top)
        found = self.found[name, t]
        if isinstance(found, LookupError):
            raise found
        return found

    def _known(self, name, t):
        """A read of an evaluation: its value when the reader has it, else `_Pending`."""
        found = self.found.get((name, t), _Pending)
        if found is _Pending:
            raise _Pending((name,))
        if isinstance(found, LookupError):
            raise found
        return found

    def _definition(self, name, t):
        """The plan's value of an engine name with the definition that it had at time t."""
        found = self.definitions.get(name)
        if found is None:
            return self.plan.original(name)
        place = bisect_right([at for at, _ in found], t) - 1
        return found[max(place, 0)][1]

    def _evaluate(self, name, t):
        """The value of one engine name at a time, once what it reads is known; `_Pending` names a read
        that is not (see `at`). It keeps the names that the evaluation read (`reads`)."""
        value = self._definition(name, t)
        asked = []

        def read(other):
            asked.append(other)
            return self._known(other, t)

        owner = self.plan.occurrence_of(name)
        if value.kind in (REDUCE, LOOKUP):
            found = self._derived(name, t, read)
        elif value.kind == DYNAMIC:
            found = self._dynamic(name, t, read)
        elif value.kind == CHANGED:
            found = self._changed(name, t, read)
        elif value.kind != FORMULA or (owner is not None and read(f'{owner}.active') is False):
            # A value, or a formula of a finished occurrence, which keeps its value (D7): read from
            # its history, it is no evaluation (`reads` gives none).
            return self._stored(value).at(t)
        else:
            # What the formula reads is read where its evaluation asks for it (`reads.py`): a read
            # that has no value then makes the formula unavailable, with its reason. What every
            # evaluation of it reads is found first, together.
            sure = self._always.get(id(value.node))
            if sure is None:
                sure = self._always[id(value.node)] = always(value.node)
            self._ready(sure, t)
            try:
                found = evaluate(value.node, Reads(nodes.names(value.node), read, t), self.plan.units)
                found = bool(found) if value.boolean else found if isinstance(found, str) else float(found)
            except FAILURES as problem:
                found = Unavailable(str(problem))
        self.read[name, t] = tuple(dict.fromkeys(asked))
        return found

    def _stored(self, value):
        """The history that the record keeps of a value, or LookupError."""
        try:
            return self.record.history(value.key)
        except KeyError:
            raise LookupError(f'the record keeps no history of {value.key or value.name}') from None

    def _changed(self, name, t, read):
        """The time at which a stored value last changed at a commit, at time t: of the last piece of
        its history at or before t that differs from the value before it (a value that holds between
        moments has a piece at each commit that changes it; one that moves, beyond its tolerance), or
        the time of its first piece."""
        stored = self.plan.changed[name]
        read(stored)  # it has a value at t, or the change has none
        pieces = self._stored(self.plan.values[stored]).pieces
        last = bisect_right([piece.t for piece in pieces], t) - 1
        for k in range(last, 0, -1):
            before, piece = pieces[k - 1].at(pieces[k].t), pieces[k].value
            if isinstance(piece, bool | str) or isinstance(before, bool | str):
                if piece != before:
                    return pieces[k].t
            elif abs(float(piece) - float(before)) > 1e-12 * max(1.0, abs(float(before))):
                return pieces[k].t
        return pieces[0].t

    def _ready(self, names, t):
        """`_Pending` for the reads among `names` that the reader has not found yet: what an evaluation
        reads for sure is found before it runs, together, so that it runs again once for all of them
        (a collection of many entries, a formula of many terms)."""
        missing = [other for other in names if other != 't' and (other, t) not in self.found]
        if missing:
            raise _Pending(missing)

    def _dynamic(self, name, t, read):
        """A dynamic read at a time, from the recorded values of its members: what they project and
        the fields that say when each is a member are found first."""
        plan = self.plan
        dynamic = plan.dynamic[name]
        self._ready(sorted(plan.dynamic_reads(name)), t)
        try:
            members = plan.members_at(dynamic.source, read)
            return dynamic_value(dynamic, members, lambda each: plan.project(each, dynamic.steps), read, t)
        except FAILURES as problem:
            return Unavailable(str(problem))

    def _derived(self, name, t, read):
        """A reduction or a keyed read at a time, from the recorded values of what it reads. Which
        entries it keeps is read from the recorded values of the fixed fields that its tests read,
        once. What it reads for sure is found first: the tests, then the kept entries of a reduction,
        or the keys of a keyed read and its key; a keyed read reads only the entry that it selects."""
        plan = self.plan
        derived = plan.reductions.get(name) or plan.keyed[name]
        try:
            if name not in self.kept:
                self._ready([each for test in derived.tests if test is not None for each in always(test)], t)
                self.kept[name] = kept(derived.tests, read, plan.units)
            entries = self.kept[name]
            if name in plan.reductions:
                reduction = plan.reductions[name]
                self._ready([reduction.names[k] for k in entries] if reduction.names else (), t)
                return reduced(reduction, read, plan.units, entries)
            keyed = plan.keyed[name]
            keys = [keyed.keys[k] for k in entries if isinstance(keyed.keys[k], str)]
            self._ready([*keys, *sorted(always(keyed.key))], t)
            index = index_of(keyed, read, plan.units, entries)
            return looked_up(keyed, read, plan.units, t, index)
        except FAILURES as problem:
            return Unavailable(str(problem))


def read(record, program, paths, times):
    """The values of named paths at chosen times, each in its declared unit: one `Reading` for each
    path, in order, with a value for each time, in order. A formula, and a request, a capacity or an
    actual rate that is one, is evaluated at each time from the recorded values of what it reads (see
    the module). A value comes only from what the record holds; any other is `Unavailable` with the
    reason (`Reader.value`): a time before the run, after its horizon or after its stop; a value that
    the record does not hold; a value of an occurrence before its start; a formula whose reads the
    record does not hold. A path that names no value of the program is a KeyError."""
    return Reader(record, program).readings(paths, times)
