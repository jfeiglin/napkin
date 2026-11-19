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
  it does. A solver's segment is fitted step by step: its dense output is a cubic in each step,
  which the series holds exactly. The state that a segment starts from opens its pieces, so a
  settled bound is a jump.
- **The family** (`family.py`) gives exact lines: a piece of each store and of each actual rate at
  each change of its line, and a piece of a request or a capacity that is a formula at each change
  of its value.
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
- **The time of a change** that `elapsed` reads has a piece at the start of its value and at each
  commit that changed it. It has no key in the record: the reader finds it from the history of the
  value that it reads.
- **A formula, and a request or a capacity written as one,** is made after the run from the
  histories of what it reads (a formula of an occurrence from its start, and from its finish the
  frozen value that the run gave it, D7): between two times at which one of them has a piece, it is one piece
  where each of them holds its value, else it is fitted as a curve is, and a yes/no takes a piece at
  each change, located to within the crossing tolerance of the run (`Numerics.crossing`). A formula
  that only names another value has that value's history. A formula that cannot be evaluated holds
  `Unavailable` with the reason. A record that keeps only some values keeps what their formulas read
  too.

Numbers are in the canonical unit of their dimension. `read` gives them in the declared unit of each
path. It evaluates a formula, a reduction, a keyed read and a dynamic read at each time that it is
asked from the recorded values of what it reads (a formula of a finished occurrence reads its frozen
piece; the time of the last change of a value is its last piece that differs from the one before),
and never reads a formula's fitted pieces: a fit is checked at a few points of each piece only, so it
could lose a kink between two of them, or a yes/no that changes and changes back. It reads a record
with the plan of the run that made it, or makes the record's occurrences again from the starts of its
trace (`Plan.replay`).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from numpy.polynomial import chebyshev

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.config import Configuration, Request
from ...program.parts import DistributionType
from ...program.record import Curve, Entry, History, Key, Manifest, Piece, Record, Unavailable
from ..continuous.kernels import Affine, MatrixExponential
from ..errors import SimulationError
from .collections import dynamic_value, history_of, index_of, kept, known, looked_up, reduced
from .plan import CHANGED, DYNAMIC, FORMULA, LOOKUP, REDUCE, Plan, name_of
from .reads import Reads, lazily

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
    piece. A value that the series holds as a line has a number for its rate, and any other a
    `Curve` in its place, which the record's piece keeps in its own field (`_history`)."""
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
                # A line: its slope is the first coefficient over the half of the span.
                at.append((a, float(first[k]), float(series[1]) * 2.0 / (b - a) if b > a else 0.0))
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

    def entry(self, t, kind, part, owner='', **details):
        """One entry of the trace, in the round where the run is (`round`: 0 is the setup)."""
        self.trace.append(Entry(t, self.round, kind, part, owner, tuple(details.items())))

    def failure(self, t, message):
        """The entry of the failure that stopped a run at time t."""
        return Entry(t, self.round, 'failure', '', '', (('message', message),))

    def pause(self, t, paused):
        """The entry of the pause of a run at time t (`chance.Paused`)."""
        return Entry(t, self.round, 'pause', paused.part, paused.owner, tuple(paused.details))

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
        its failure or of its pause, whose entry ends the trace)."""
        plan, run = self.plan, self.run
        request = plan.configuration.request
        needed = None if request.everything else self._needed(request.keys)
        histories = {}
        for name, value in plan.values.items():
            if needed is not None and name not in needed:
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
        kept = [
            history
            for history in histories.values()
            if history.key is not None and history.pieces and (request.everything or history.key in keys)
        ]
        manifest = Manifest(request.horizon, request.everything, request.keys)
        last = failure if failure is not None else pause
        trace = tuple(self.trace) + ((last,) if last is not None else ())
        return Record(manifest, tuple(kept), trace, failure)

    def _needed(self, keys):
        """The engine names whose histories a record of only these keys needs: theirs, and what
        their formulas and reductions read."""
        return self._needed_names([name_of(key) for key in keys])

    def _needed_names(self, names):
        """The engine names whose histories a record of these names needs (`_needed`): what their
        formulas read under every definition that they had."""
        plan, found = self.plan, set()
        pending = list(names)
        while pending:
            name = pending.pop()
            if name in found or name not in plan.values:
                continue
            found.add(name)
            kind = plan.values[name].kind
            if kind in (FORMULA, REDUCE, LOOKUP) or name in plan.defined:
                reads = plan.expanded_ever(name)
                pending += [*reads.leaves, *reads.formulas, *reads.stepped]
            elif kind == CHANGED:
                pending += sorted(plan.reads(name))  # the value that it follows
            elif kind == DYNAMIC:
                pending += sorted(plan.dynamic_reads(name))  # what its members project, and when
            owner = plan.occurrence_of(name)
            if owner is not None:
                pending += [f'{owner}.started', f'{owner}.active']
        return found

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
            # What can change of what it reads has a history; what the inputs fix holds its start.
            found = plan.lookup_reads(name)
            index = run.index_for(name)

            def compute(env):
                value = lambda read: env[read] if read in env else run.value_of(read)  # noqa: E731
                return looked_up(keyed, value, plan.units, env['t'], index)

            return self.formula(
                name,
                histories,
                end,
                sorted(found.leaves | found.formulas | found.stepped),
                compute,
                boolean,
                timed=found.time,
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

        firsts = []
        for time in times:
            try:
                firsts.append(at(time))
            except FAILURES as problem:
                firsts.append(Unavailable(str(problem)))
        # A yes/no and a text (an enum member) change by steps; a number is fitted.
        discrete = boolean or any(isinstance(found, str) for found in firsts)
        cast = bool if boolean else (lambda found: found if isinstance(found, str) else float(found))
        # The size of the formula, as a store's: the largest magnitude that it takes at a time at
        # which what it reads has a piece.
        size = 1.0
        if not discrete:
            for found in firsts:
                if not isinstance(found, Unavailable):
                    size = max(size, abs(float(found)))
        tolerance = np.array([plan.numerics.atol_factor * size])
        pieces = []
        for (a, b), first in zip(pairwise(bounds), firsts):
            if isinstance(first, Unavailable):
                pieces.append((a, first, 0.0))
                continue
            if b <= a or (not timed and all(holders[read](a) for read in reads)):
                # What the formula reads holds its value from a to b: so does the formula.
                pieces.append((a, cast(first), 0.0))
            elif discrete:
                pieces += _switches(lambda time: cast(at(time)), a, b, cast(first), plan.numerics.crossing)
            else:
                try:
                    found = fitted(lambda ts: np.array([[float(at(t))] for t in ts]), a, b, tolerance)[0]
                except FAILURES as problem:
                    found = [(a, Unavailable(str(problem)), 0.0)]
                pieces += found
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


def _switches(at, a, b, first, crossing):
    """The pieces of a yes/no or a text from a to b: one at a, and one at each change, which
    bisection locates between the points of a fit to within the crossing tolerance."""
    pieces, value = [(a, first, 0.0)], first
    points = _times(a, b, np.concatenate([[-1.0], _CHECKS[1:-1], [1.0]]))
    for before, after in pairwise(points):
        if at(after) == value:
            continue
        left, right = before, after
        while right - left > crossing:
            middle = 0.5 * (left + right)
            if at(middle) == value:
                left = middle
            else:
                right = middle
        value = at(right)
        pieces.append((right, value, 0.0))
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
    """The spelling of the declared unit of the value at a key and its scale: of a value, its type's
    unit; of a flow's actual rate, request or capacity, the flow's unit, and of a leg's, the leg's;
    of an endpoint's, its store's unit per hour (time is in hours, at scale 1); `''` for a plain
    number or a yes/no, such as a `served_fraction`."""
    if '#' in key.owner:
        receiver, event = key.owner.rsplit('#', 1)[0].rsplit('.', 1)
        found = program.member(receiver)[0].part(event)
        if key.steps[0] in ('started', 'done', 'active'):
            return '', 1.0  # the time of the start is in hours; the others are yes/no values
        part = next((each for each in (*found.params, *found.locals) if each.name == key.steps[0]), None)
    elif key.owner:
        template = program.member(key.owner)[0]
        part = template.part(key.steps[0])
    else:
        part = program.root_value(key.steps[0])
    if part is None:
        raise KeyError(f'{key}: no value of the program')
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
    scale = 1.0 if unit == '' else float(program.unit(unit).scale)
    if len(key.steps) >= 3 and key.steps[1] in ('outflow', 'inflow'):
        return (f'{unit}/h' if unit else '1/h'), scale
    return unit, scale


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


class _Values:
    """The values of a record at a time, with each formula, reduction and keyed read evaluated
    from the recorded values of what it reads, in canonical units. Which entries a collection keeps
    is read from the recorded values of the fixed fields that its tests read."""

    def __init__(self, record, program):
        self.record = record
        self.histories = {history.key: history for history in record.histories}
        self.plan = _plan_of(program, record)
        # The definitions that the commits of the run gave values, from its trace: a value is read
        # with the definition that it had at the time of the read.
        self.definitions = self.plan.definitions_of(record.trace)
        self.done = {}
        self.kept = {}

    def _value(self, name, t):
        """The plan's value of an engine name with the definition that it had at time t."""
        found = self.definitions.get(name)
        if found is None:
            return self.plan.original(name)
        place = bisect_right([at for at, _ in found], float(t)) - 1
        return found[max(place, 0)][1]

    def at(self, name, t):
        """The value of an engine name at a time: from its history, or for a formula from what it
        reads, `Unavailable` when it cannot be evaluated. A value that the record does not hold is a
        LookupError."""
        if (name, t) in self.done:
            return self.done[name, t]
        value = self._value(name, t)
        owner = self.plan.occurrence_of(name)
        if value.kind in (REDUCE, LOOKUP):
            found = self._derived(name, t)
        elif value.kind == DYNAMIC:
            found = self._dynamic(name, t)
        elif value.kind == CHANGED:
            found = self._changed(name, t)
        elif value.kind != FORMULA or (owner is not None and self._finished(owner, t)):
            # A value, or a formula of a finished occurrence, which keeps its value (D7).
            history = self.histories.get(value.key)
            if history is None:
                raise LookupError(f'the record holds no value of {name}')
            found = history.at(t)
        else:
            # What the formula reads is read where its evaluation asks for it (`reads.py`); a read
            # that the record does not hold is a LookupError of the reader, as before.
            try:
                found = lazily(value.node, lambda read: self.at(read, t), self.plan.units, t)
                found = bool(found) if value.boolean else found if isinstance(found, str) else float(found)
            except LookupError:
                raise
            except FAILURES as problem:
                found = Unavailable(str(problem))
        self.done[name, t] = found
        return found

    def _stored(self, name):
        history = self.histories.get(self.plan.values[name].key)
        if history is None:
            raise LookupError(f'the record holds no value of {name}')
        return history

    def _changed(self, name, t):
        """The time at which a stored value last changed at a commit, at time t: of the last piece of
        its history at or before t that differs from the value before it (a value that holds between
        moments has a piece at each commit that changes it; one that moves, beyond its tolerance), or
        the time of its first piece."""
        pieces = self._stored(self.plan.changed[name]).pieces
        last = bisect_right([piece.t for piece in pieces], t) - 1
        if last < 0:
            raise LookupError(f'{name} has no value at {t} h')
        for k in range(last, 0, -1):
            before, piece = pieces[k - 1].at(pieces[k].t), pieces[k].value
            if isinstance(piece, bool | str) or isinstance(before, bool | str):
                if piece != before:
                    return pieces[k].t
            elif abs(float(piece) - float(before)) > 1e-12 * max(1.0, abs(float(before))):
                return pieces[k].t
        return pieces[0].t

    def _finished(self, owner, t):
        """Whether an occurrence has finished at time t."""
        history = self.histories.get(Key(owner, ('active',)))
        try:
            return history is not None and history.at(t) is False
        except LookupError:
            return False  # it has not started

    def _dynamic(self, name, t):
        """A dynamic read at a time, from the recorded values of its members."""
        plan = self.plan
        dynamic = plan.dynamic[name]

        def value(read):
            return self.at(read, t)

        try:
            members = plan.members_at(dynamic.source, value)
            return dynamic_value(dynamic, members, lambda each: plan.project(each, dynamic.steps), value, t)
        except FAILURES as problem:
            return Unavailable(str(problem))

    def _derived(self, name, t):
        """A reduction or a keyed read at a time, from the recorded values of what it reads."""
        plan = self.plan

        def value(read):
            return self.at(read, t)

        try:
            if name not in self.kept:
                derived = plan.reductions.get(name) or plan.keyed[name]
                self.kept[name] = kept(derived.tests, value, plan.units)
            if name in plan.reductions:
                return reduced(plan.reductions[name], value, plan.units, self.kept[name])
            index = index_of(plan.keyed[name], value, plan.units, self.kept[name])
            return looked_up(plan.keyed[name], value, plan.units, t, index)
        except FAILURES as problem:
            return Unavailable(str(problem))


def read(record, program, paths, times):
    """The values of named paths at chosen times, each in its declared unit: one `Reading` for each
    path, in order. A formula, and a request, a capacity or an actual rate that is one, is evaluated
    at each time from the recorded values of what it reads (see the module). A time that the record
    does not hold is a LookupError, and so is a formula whose reads it does not hold. A value of an
    occurrence before its start is `Unavailable`."""
    values_at = _Values(record, program)
    found = []
    for path in paths:
        key = key_of(program, path)
        unit, scale = unit_of(program, key)
        values = []
        for t in times:
            if not record.manifest.holds(key, t):
                raise LookupError(f'{path}: the record holds no value at {t} h')
            try:
                value = values_at.at(name_of(key), t)
            except LookupError:
                if '#' not in key.owner:
                    raise
                value = Unavailable(f'{key.owner} has not started at {float(t):g} h')
            if not isinstance(value, (bool, str, Unavailable)):
                value = float(value) / scale
            values.append(value)
        found.append(Reading(name_of(path) if isinstance(path, Key) else path, key, unit, tuple(values)))
    return found
