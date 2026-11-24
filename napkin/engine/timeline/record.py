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
  no ledger of it, and an edit adds to the budget
  of pieces at its own time, never before.
- **The time of a change** that `elapsed` reads starts with the value's creation time. The
  value's history carries the time of every commit that changed it, including separate commits
  at one time and exact stock postings smaller than a floating-point unit.
- **An occurrence that a failed commit started** holds no value in the record: the record holds the
  occurrences that its trace starts, and the commit that failed is not in it (`moment.py`).
- **A formula, and a request or a capacity written as one,** is fitted on each completed interval from the
  histories of what it reads (a formula of an occurrence from its start, and from its finish the
  frozen value that the run gave it, D7): between two times at which one of them has a piece, it is one piece
  where each of them holds its value, else it is fitted as a curve is, and a yes/no takes a piece at
  each change, located to within the crossing tolerance of the run (`Numerics.crossing`). A formula
  that only names another value has that value's history. A formula that cannot be evaluated holds
  `Unavailable` with the reason, from where it cannot be, found as a change of a yes/no is, also
  inside a piece (a membership whose moving end passes the other): its values before are kept.

**What a record holds** follows from its request and trace (`requested`): every value, or the values that the request
names, what their formulas read under each definition that the trace's commits gave them
(`needed`), and the ledgers of the books, each history in the order of its key; a piece that starts
at the record's end holds its value there (`_finished`). The budget counts trajectory pieces and
actual postings. A stock can have one extra point for its exact balance at the cutoff.
The record ends before the first piece that exceeds the budget (`Record.within`).
This rule also applies when the run stops for a checkpoint (`checkpoints.Breaks`).

Numbers are in the canonical unit of their dimension. `read` gives them in the declared unit of each
path, from what the record holds and from nothing else (`Record.unavailable`): any other value is
`Unavailable` with the reason, never a default. A path names a value when the program declares one
there (`declaration`, the one lookup of the part that declares a key: an unknown of a solver lives
on the solver, in its own unit) and a run of it holds it (`Reader.checked`): every endpoint of a store
that a flow meets (`Plan._declare_ends`), and the `.mean` and the `.std` of every distribution of a
member or of the root, is a value of every run, whatever reads it (spec, "Any named value can be
reported"); a capacity that the program leaves out is `Unavailable`, as the flow has no ceiling of its
own (`absent`); any other path is a KeyError that says why. Its `Reader` evaluates a formula, a reduction, a keyed
read and a dynamic read at each time that it is asked from the recorded values of what it reads (a
formula of a finished occurrence reads its frozen piece; an elapsed clock reads the time of the
last committed change), depth first with no recursion, and keeps what each
evaluation read, which a report's evidence trail follows. It never reads a formula's fitted pieces: a
fit is checked at a few points of each piece only, so it could lose a kink between two of them, or a
yes/no that changes and changes back. Its plan replays this record's starts and captures under
the comparison settings of its manifest (`Plan.replay`).
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from copy import copy
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import pairwise
from operator import attrgetter

import numpy as np
from numpy.polynomial import chebyshev

from ...core import expr as nodes
from ...core.comparisons import Comparisons
from ...core.errors import ExpressionError
from ...core.units import rational
from ...expressions import evaluate
from ...program import parts as p
from ...program.config import Configuration, Numerics, Request
from ...program.parts import DistributionType, OccurrenceType
from ...program.proofs import always
from ...program.record import ChangeHistory, Curve, Entry, History, Key, Manifest, Piece, Record, Unavailable
from ..continuous.integrate import crossing_time, switch_layers, switch_pairs
from ..continuous.kernels import Affine, MatrixExponential
from ..errors import SimulationError
from .collections import dynamic_value, history_of, index_of, kept, known, looked_up, reduced
from .family import Family
from .lines import Lines
from .plan import (
    BUILTINS,
    CHANGED,
    DYNAMIC,
    FORMULA,
    LOOKUP,
    RATE,
    REDUCE,
    SIDES,
    Plan,
    name_of,
)
from .reads import Reads, lazily

# What evaluating a formula can raise: it then holds `Unavailable` with the reason.
FAILURES = (ExpressionError, ArithmeticError, ValueError, LookupError, SimulationError)

_piece_time = attrgetter('t')


def _formula_reads(node):
    return sorted(set(nodes.names(node)) - {'t'})


def _restart_point(start, since, histories, reads, anchors=()):
    """The last boundary of the formula's own grid at or before the earliest change."""
    if since <= start:
        return start
    boundary = max((at for at in anchors if start <= at <= since), default=start)
    for name in reads:
        history = histories.get(name)
        if history is not None:
            i = bisect_right(history.pieces, since, key=_piece_time)
            if i:
                boundary = max(boundary, history.pieces[i - 1].t)
    return boundary


def _freeze_pieces(pieces, finish, value):
    """The outgoing piece at the finish holds the value captured by the run."""
    del pieces[bisect_left(pieces, finish, key=lambda piece: piece[0]) :]
    pieces.append((finish, value, 0.0))


DEGREE = 8
# The points of a fit on [-1, 1], and the points between them at which a fit is checked, with the
# start of the piece. The end of a piece is the start of the next, whose value can jump there.
_NODES = np.cos(np.pi * (np.arange(DEGREE + 1) + 0.5) / (DEGREE + 1))[::-1]
_CHECKS = np.cos(np.pi * np.arange(1, DEGREE + 2) / (DEGREE + 1))[::-1]
# The same interpolation and checks apply to every column of sampled values.
_FIT_MATRIX = np.linalg.inv(chebyshev.chebvander(_NODES, DEGREE))
_CHECK_MATRIX = chebyshev.chebvander(_CHECKS, DEGREE)
_LEFT_ROW = chebyshev.chebvander(-1.0, DEGREE)[0]
# A piece shorter than this, in hours, is not cut again: it holds what the fit gives.
SHORTEST = 1e-9
# A fit holds a value to its tolerance, or to this part of its largest size in the piece, which
# the roundoff of a value far from zero allows.
RELATIVE = 1e-12
# The most cuts of one fit: after them, each piece holds what its fit gives.
MOST = 4096
# The fields of a flow, a route and an endpoint, and of a leg of a route, which is the positive part of
# the route's rate and request in its direction (spec, "What each scope can see").
FIELDS = ('actual_rate', 'request', 'capacity')
LEGS, LEG_FIELDS = ('forward', 'backward'), ('actual_rate', 'request')


def _times(start, end, points):
    """The fit samples the segment before its endpoint. On a short span even an interior
    Chebyshev node can round to the endpoint, where the next branch may already apply."""
    return np.minimum(start + (points + 1.0) * 0.5 * (end - start), math.nextafter(end, start))


def fitted(values, start, end, tolerance):
    """The pieces of k values from `start` to `end`: one list for each value, each piece a (time,
    value, rate). `values(times)` gives an array of one row for each time; `tolerance` holds one
    number for each value, which a fit may widen to `RELATIVE` of the value's largest size in the
    piece. A value that the series holds as a constant has the rate 0, and any other a `Curve` in
    its place, which the record's piece keeps in its own field (`_history`): a line too, as a series
    of degree one, since its slope is the fit's over the span that it was fitted to, and so follows
    where the run ended in its last digits."""
    found = [[] for _ in tolerance]
    pending, cuts = [(start, end)], 0
    while pending:
        a, b = pending.pop()
        nodes = values(_times(a, b, _NODES))
        coefficients = _FIT_MATRIX @ nodes
        allowed = np.maximum(tolerance, RELATIVE * np.max(np.abs(nodes), axis=0))
        if b - a > SHORTEST and cuts < MOST:
            checks = values(_times(a, b, _CHECKS))
            first = checks[0]
            allowed = np.maximum(allowed, RELATIVE * np.max(np.abs(checks), axis=0))
            made = (_CHECK_MATRIX @ coefficients) - (_LEFT_ROW @ coefficients) + first
            if np.any(np.abs(made - checks) > allowed):
                middle = 0.5 * (a + b)
                pending += [(middle, b), (a, middle)]
                cuts += 1
                continue
        else:
            first = values(np.array([a]))[0]
        constant = np.all(nodes == first, axis=0)
        if b - a > SHORTEST and cuts < MOST:
            constant &= np.all(checks == first, axis=0)
        for k, at in enumerate(found):
            if constant[k]:
                # Interpolation roundoff can give an identically held threshold a nonzero slope.
                at.append((a, float(first[k]), 0.0))
                continue
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


def _fit_boundaries(start, end, added, crossing):
    """Keep both fixed endpoints. Between them, keep the earliest distinct added boundaries."""
    kept = [start]
    for at in sorted(set(added)):
        if at - kept[-1] > crossing and end - at > crossing:
            kept.append(at)
    kept.append(end)
    return kept


def _bend_times(layers, operand, start, end, tolerance, crossing):
    """Roots of numeric branch surfaces inside a piece, inner decisions before their users.

    The difference between two smooth operands can cross zero twice. Fit that difference,
    split at its turning points, and locate each change of sign against the actual operands.
    Sampling only the selected result can miss an entire narrow min/max arm.
    """
    roots = set()
    bounds = [start, end]
    for layer in layers:
        for left, right in layer:

            def gap(t):
                values = operand(left, t), operand(right, t)
                if any(isinstance(value, Unavailable) for value in values):
                    raise LookupError('an operand has no recorded value here')
                difference = float(values[0]) - float(values[1])
                if not math.isfinite(difference):
                    raise ValueError('a difference of branch operands is not finite')
                return difference

            def values(times):
                return np.array([[gap(t)] for t in times])

            for a, b in pairwise(bounds):
                try:
                    (pieces,) = fitted(values, a, b, tolerance)
                    for origin, _, curve in pieces:
                        if not isinstance(curve, Curve):
                            continue
                        # A piece is left-closed. At its outgoing boundary the next held
                        # value may already have jumped, so bracket from its incoming side.
                        stop = min(b, origin + curve.length)
                        if stop <= origin:
                            continue
                        extrema = (
                            chebyshev.chebroots(chebyshev.chebder(curve.coefficients))
                            if len(curve.coefficients) > 2
                            else ()
                        )
                        interior = sorted(
                            origin + 0.5 * curve.length * (1 + float(u.real))
                            for u in extrema
                            if u.imag == 0 and -1 < u.real < 1
                        )
                        for lo, hi in pairwise([origin, *interior, math.nextafter(stop, origin)]):
                            if hi <= lo:
                                continue
                            first, last = gap(lo), gap(hi)
                            if first == last or (first < 0 and last < 0) or (first > 0 and last > 0):
                                continue
                            root = crossing_time(gap, lo, hi, accepted=(first, last))
                            if root is not None and a < root < b:
                                roots.add(root)
                except FAILURES:
                    # An inactive branch need not have a value here. The ordinary fit
                    # still reports any failure of the selected expression.
                    continue
        bounds = _fit_boundaries(start, end, roots, crossing)
    # The search endpoints may themselves be optional moment ends. The caller decides
    # which of those ends and these roots to retain between the actual fixed boundaries.
    return sorted(roots)


def _line_number(value):
    return isinstance(value, (float, int, Fraction)) and not isinstance(value, bool)


def recorded_piece(t, value, rate):
    """A recorder piece as the public record holds it: on a line or on a curve."""
    return Piece(t, value, curve=rate) if isinstance(rate, Curve) else Piece(t, value, rate)


def _compact(pieces):
    """Drop a piece only when its predecessor gives the same value and outgoing rate.

    A small discontinuity can be a committed posting even on a moving stock.
    Its size relative to the opening balance does not identify a continuation.
    """
    if len(pieces) < 2:
        return pieces
    kept = []
    for t, value, rate in pieces:
        if kept:
            t0, v0, r0 = kept[-1]
            if not isinstance(rate, Curve) and rate == r0:
                if rate == 0 and value == v0:
                    continue
                if rate != 0 and _line_number(v0) and _line_number(value):
                    continued = (
                        v0 + rational(r0) * (rational(t) - rational(t0))
                        if isinstance(v0, Fraction)
                        else v0 + r0 * (t - t0)
                    )
                    if continued == value:
                        continue
        kept.append((t, value, rate))
    return kept


class Fits:
    """The committed curve pieces of a run. A moment closes the incoming interval for every
    observer, including a run without a breakpoint. No later fit reopens it. At the current
    endpoint the next interval is still open: the stages there can give it a new value."""

    def __init__(self):
        self.ends = [0.0]
        self.closed = {}

    def advance(self, end):
        if end > self.ends[-1]:
            self.ends.append(end)

    def intervals(self, start, end):
        """Known boundaries strictly inside an interval that needs a curve."""
        return self.ends[bisect_right(self.ends, start) : bisect_left(self.ends, end)]

    def cached(self, name, start, end, fit):
        """Reuse a completed fit or root search over this exact interval."""
        key = (name, start, end)
        if key not in self.closed:
            self.closed[key] = fit()
        return self.closed[key]


class _NeedsHistory(Exception):
    """Comparison scale selection consulted a field outside the held formula's direct reads."""


def _held_formula(node, names, histories, start, boolean, units):
    """One held piece when each named input already holds its last value at the start."""
    values = {}
    for name in names:
        history = histories.get(name)
        if history is None or not history.pieces:
            return None
        piece = history.pieces[-1]
        if piece.t > start or piece.rate != 0 or piece.curve is not None:
            return None
        values[name] = piece.value

    def read(name):
        if name not in values:
            raise _NeedsHistory
        return values[name]

    try:
        value = evaluate(node, Reads(names, read, start), units)
    except _NeedsHistory:
        return None
    except FAILURES as problem:
        value = Unavailable(str(problem))
    if not isinstance(value, Unavailable | str):
        value = bool(value) if boolean else float(value)
    return [(float(start), value, 0.0)]


class HistoryFull(Exception):
    """The committed prefix that used up the requested history budget."""

    def __init__(self, record):
        self.record = record


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
        self._wanted = None  # None denotes a full record.
        # A missing key has never been skipped. None marks a producer's declined
        # trajectory; its first later admission sets the start of recorded coverage.
        self._coverage_starts = {}
        self.refresh_needed()
        # A store that edits changed -> (its start, [(time, amount from outside)]) (`external`).
        self.transfers = {}
        self.fits = Fits()
        self._indexed_value_count = None
        self._indexed_version = None
        self._dirty = set()
        self._from = math.inf
        self._private = None
        self._moving = set()
        self._histories = {}
        self._flow_reads = {}  # contributors when an endpoint sum was last assembled
        self._event_ends = {}  # fitted event histories: None while live, else their assembled finish
        self._raw_positions = {}
        self._counted = {}
        self._total = 0
        self._as_of = None
        self._held_upper = None
        self._held_growth = 0

    def entry(self, t, kind, part, owner='', **details):
        """One entry of the trace, in the round where the run is (`round`: 0 is the setup)."""
        self.trace.append(Entry(t, self.round, kind, part, owner, tuple(details.items())))
        if kind == 'start':
            # A predeclared occurrence can become visible without growing plan.values.
            self._indexed_value_count = None

    def failure(self, t, message, **details):
        """The entry of the failure that stopped a run at time t."""
        return Entry(t, self.round, 'failure', '', '', (('message', message), *details.items()))

    def external(self, store, t, amount, start):
        """An edit at a stop moved `amount` into a store from outside (a withdrawal is negative): its
        books hold it as an external transfer, the history `external` beside the store, what edits
        brought in so far, a piece at each edit. `start` is when the store started, which the run's
        savepoint keeps with the transfers (`moment._Savepoint`); the ledger reads 0 from then to its
        first edit without a piece of its own."""
        self._held_upper, self._held_growth = math.inf, 0
        self.transfers.setdefault(store, (start, []))[1].append((t, amount))
        self._dirty.add(store)
        self._from = min(self._from, t)

    def segment(self, component, segment, stores, flows):
        """The pieces of the stores and the flows of a component over one of its segments."""
        start, end, solution = segment.start, segment.end, segment.solution
        if end <= start:
            for k, name in enumerate(stores):
                self.add_pieces(name, [(start, float(segment.last[k]), 0.0)])
            return
        context = component.context
        if isinstance(solution, (Affine, MatrixExponential)):
            curved = set()
            if isinstance(solution, MatrixExponential):
                curved = {int(i) for i in solution.columns[solution.rows]}
            for k, name in enumerate(stores):
                if k not in curved:
                    self.add_pieces(name, [(start, float(segment.first[k]), float(solution.slope[k]))])
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
                    self.add_pieces(stores[k], pieces)
        if not flows:
            return
        if isinstance(solution, Affine):
            rates = component.delivered(segment, [0.5 * (start + end)])[0]
            for k, name in enumerate(flows):
                self.add_pieces(name, [(start, float(rates[k]), 0.0)])
            return
        tolerance = np.array([self.tolerance[name] for name in flows])
        for a, b in spans:
            for name, pieces in zip(
                flows,
                fitted(lambda times: component.delivered(segment, times), float(a), float(b), tolerance),
            ):
                self.add_pieces(name, pieces)

    def check_budget(self, end, *, before=False, internal=False):
        """Read the pieces that the history producers have committed through this boundary."""
        ways = self.run.ways
        # Another independent solver may still be inside its own dense step. Only the
        # complete incoming histories can decide a formula that reads both trajectories.
        if (
            internal
            and (len(ways.sampled) + len(ways.moving_solvers) > 1)
            and any(
                ways.sets[key][1].recorded_through != end
                for registry in (ways.sampled, ways.moving_solvers)
                for key in registry
            )
        ):
            return
        if before and self.run.arriving and self.run.saved_arrival is None:
            for registry in (ways.sampled, ways.moving_solvers):
                for key in registry:
                    ways.sets[key][1].incoming_history(end)
        self.fits.advance(end)
        if internal and self._index_current():
            if self._held_upper is None:
                self._held_upper, self._held_growth = self._held_piece_bound()
            if self._held_upper <= self.plan.configuration.request.pieces:
                return
        self._advance(end)
        view = self._at_cutoff(end)
        if view._total <= self.plan.configuration.request.pieces:
            return
        round_ = int(not self.run.bare) if before else self.round
        prefix = view._record(end, None, Entry(end, round_, 'pause', '', ''), end != self.plan.horizon)
        if prefix.failure is not None and (not before or prefix.failure.t < end):
            raise HistoryFull(prefix)

    def _held_piece_bound(self):
        """Bound retained pieces from raw held lines, their aliases and numeric sums.

        An alias copies its input. A sum of lines has at most one new piece per input
        piece time, even when a member is projected twice. Count every path from a raw
        value to a retained history. The largest such count bounds the growth from any
        later raw line. An addition of held physical rates stays constant between their
        changes. Compaction can only reduce the count. Other formulas may split
        between input pieces, so their budget needs the ordinary committed histories.
        """
        plan = self.plan
        if (
            plan.events
            or plan.defined
            or self.transfers
            or not all(isinstance(way, (Family, Lines)) for way in self.run.ways.instances)
        ):
            return math.inf, 0
        uses, numeric = defaultdict(int), set()
        upper, growth = 0, 0
        for name in reversed(self._order):
            value = plan.values[name]
            count = uses.pop(name, 0) + int(value.key is not None)
            if not count:
                continue
            if name not in self._derived or name in self.formulas:
                raw = self.pieces.get(name, ())
                if name in numeric and (
                    (name in self.constants and not _line_number(self.constants[name]))
                    or any(not (_line_number(v) and _line_number(rate)) for _, v, rate in raw)
                ):
                    return math.inf, 0
                upper += count * (len(raw) + int(name in self.constants))
                growth = max(growth, count)
            elif value.kind == FORMULA and isinstance(value.node, nodes.Ref):
                source = value.node.name
                uses[source] += count
                if name in numeric:
                    numeric.add(source)
            elif value.kind == FORMULA and isinstance(value.node, nodes.Binary) and name not in numeric:
                # An endpoint can add several held actual rates. Each is a raw zero-slope
                # history, so formula() takes its held branch between consecutive changes.
                # A consumer that requires a numeric sum can need the ordinary overflow checks.
                pending = [value.node]
                while pending:
                    node = pending.pop()
                    if isinstance(node, nodes.Binary) and node.op == 'add':
                        pending.extend((node.left, node.right))
                    elif (
                        isinstance(node, nodes.Ref)
                        and node.name not in self._derived
                        and node.name in plan.values
                        and plan.values[node.name].kind == RATE
                    ):
                        uses[node.name] += count
                        numeric.add(node.name)
                    else:
                        return math.inf, 0
            elif value.kind == REDUCE:
                reduction = plan.reductions[name]
                upper += count  # the constant result of an empty collection or member count
                if reduction.names is not None:
                    if reduction.op != 'sum':
                        return math.inf, 0
                    try:
                        entries = self.run.kept_of(name)
                    except FAILURES:
                        return math.inf, 0  # an unavailable sum can make its reader need a fit
                    for entry in entries:
                        source = reduction.names[entry]
                        uses[source] += count
                        numeric.add(source)
            else:
                return math.inf, 0
        return (math.inf, 0) if uses else (upper, growth)

    def _posted_value(self, name, t, value):
        """Keep a physical posting's exact intercept when its public float loses a remainder."""
        if self.run is not None:
            point = self.run.stock_state.balances.get(name)
            if point is not None and point[2] == t:
                balance = point[0]
                if balance != value and float(balance) == value:
                    return balance
        return value

    def add(self, name, t, value, rate):
        """One piece of a value, which a run gives as it goes."""
        if self._held_growth:
            if _line_number(value) and _line_number(rate):
                self._held_upper += self._held_growth
            else:
                self._held_upper, self._held_growth = math.inf, 0
        self.pieces.setdefault(name, []).append((t, self._posted_value(name, t, value), rate))
        self._dirty.add(name)
        self._from = min(self._from, t)

    def add_pieces(self, name, pieces):
        """Pieces of a value, which a run gives as it goes."""
        if pieces:
            self._held_upper, self._held_growth = math.inf, 0
            if self.run is not None and name in self.run.stock_state.balances:
                pieces = [(t, self._posted_value(name, t, value), rate) for t, value, rate in pieces]
            self.pieces.setdefault(name, []).extend(pieces)
            self._dirty.add(name)
            self._from = min(self._from, pieces[0][0])

    def incoming_piece(self, name, end):
        """The last recorded piece strictly before an incoming segment ends, or None."""
        pieces = self.pieces.get(name, ())
        place = bisect_left(pieces, end, key=lambda piece: piece[0]) - 1
        return pieces[place] if place >= 0 else None

    def wanted(self, name):
        """Whether this request retains the trajectory offered by a producer."""
        if self._wanted is None or name in self._wanted:
            return True
        self._coverage_starts.setdefault(name, None)
        return False

    def refresh_needed(self):
        """Refresh a selected record after a commit changes membership or definitions."""
        request = self.plan.configuration.request
        if request.everything:
            return set()
        previous = self._wanted
        self._wanted = needed(self.plan, [name_of(key) for key in request.keys], self.plan.defined)
        added = self._wanted.difference(previous) if previous is not None else set()
        joined = added.intersection(self._coverage_starts)
        if joined:
            # Replace the mapping so a failed commit can restore its earlier coverage.
            self._coverage_starts = self._coverage_starts | dict.fromkeys(joined, self.run.now)
        return added

    # ---- the committed histories -----------------------------------------------------------------

    def _index_current(self):
        return (
            self._indexed_value_count == len(self.plan.values) and self._indexed_version == self.plan.version
        )

    def _prepare_histories(self):
        """Order the histories that this request retains and index their direct readers."""
        plan = self.plan
        request = plan.configuration.request
        wanted = self._wanted
        started = {entry.owner for entry in self.trace if entry.kind == 'start'} | {None}
        names = [
            n for n in plan.values if (wanted is None or n in wanted) and plan.occurrence_of(n) in started
        ]
        calculated = {
            n
            for n in names
            if plan.values[n].kind in (CHANGED, FORMULA, REDUCE, LOOKUP, DYNAMIC)
            or (plan.values[n].kind == RATE and plan.values[n].node is not None)
            or n in plan.defined
        }
        order = [n for n in names if n not in calculated] + plan.ordered(calculated, ever=True)
        self._order = {name: k for k, name in enumerate(order)}
        self._derived = calculated
        self._readers = defaultdict(list)
        self._clock = set()
        for name in calculated:
            value = plan.values[name]
            reads = plan.reads_ever(name)
            owner = plan.occurrence_of(name)
            if owner is not None:
                reads |= {f'{owner}.active', f'{owner}.started'} - {name}
            for key in reads:
                self._readers[key].append(name)
            if (
                (value.node is not None and 't' in nodes.names(value.node))
                or name in plan.defined
                or value.kind == DYNAMIC
                or (name in plan.keyed and plan._chosen(plan.keyed[name]) is None)
            ):
                self._clock.add(name)
        # A redefinition can change an existing formula without writing a raw piece.
        # An occurrence start only adds names and readers to the committed history.
        if self._indexed_version != plan.version:
            self._histories.clear()
            self._flow_reads.clear()
            self._event_ends.clear()
            self._raw_positions.clear()
            self._moving.clear()
            self._counted.clear()
            self._total = 0
            self._as_of = None
            self._dirty.update(self.transfers)
        self._names = Manifest(request.horizon, request.everything, request.keys).names
        for name in names:
            if name not in self._histories:
                self._dirty.add(name)
                if (key := plan.values[name].key) is not None and self._names(key):
                    self._counted[name] = 0
        self._held_upper = None
        self._held_growth = 0
        self._indexed_value_count = len(plan.values)
        self._indexed_version = plan.version

    def _advance(self, end):
        """Update only histories whose inputs changed or whose current interval moves."""
        plan = self.plan
        if not self._index_current():
            self._prepare_histories()
        dirty, self._dirty = self._dirty, set()
        since = min(self._as_of or 0.0, self._from)
        self._from = math.inf
        changed = dirty.intersection(self._order)
        if self._as_of != end:
            changed.update(self._clock)
            changed.update(self._moving)
        for name in self._affected(changed):
            value = plan.values[name]
            if name in self._derived:
                start = since if name in self._histories else plan.start_of(name)
                history = self._derived_history(name, value, end, start)
            else:
                history = self._raw_history(name, value, end)
                if not history.pieces and self._coverage_starts.get(name) is not None:
                    # At the join only the private cutoff view can see this opening.
                    self._moving.add(name)
                elif history.pieces and (history.pieces[-1].curve is not None or history.pieces[-1].rate != 0):
                    self._moving.add(name)
                else:
                    self._moving.discard(name)
            self._put(name, history)
        for name in dirty.intersection(self.transfers):
            key = plan.values[name].key
            ledger = Key(key.owner, (*key.steps, 'external'))
            ledger_name = f'{name}.external'
            if self._names(ledger):
                self._counted.setdefault(ledger_name, 0)
            total, pieces = 0, []
            for at, amount in self.transfers[name][1]:
                if at <= end:
                    total += rational(amount)
                    pieces.append((at, float(total), 0.0))
            self._put(ledger_name, self._history(ledger, pieces))
        self._as_of = end

    def _affected(self, changed):
        """The changed histories and their transitive readers, in assembly order."""
        pending = list(changed)
        while pending:
            for reader in self._readers.get(pending.pop(), ()):
                if reader not in changed:
                    changed.add(reader)
                    pending.append(reader)
        return sorted(changed, key=self._order.__getitem__)

    def _at_cutoff(self, end):
        """A check sees the settled opening even if the first outgoing segment is still pending."""
        if not self._coverage_starts:
            return self
        openings = {
            name for name, start in self._coverage_starts.items()
            if start == end and name in self._histories and not self._histories[name].pieces
        }
        if not openings:
            return self
        view = copy(self)
        view._histories = dict(self._histories)
        view._flow_reads = dict(self._flow_reads)
        view._event_ends = dict(self._event_ends)
        view._counted = dict(self._counted)
        view._private = set()
        view.fits = copy(self.fits)
        view.fits.closed = dict(self.fits.closed)
        for name in self._affected(set(openings)):
            value = self.plan.values[name]
            if name in openings:
                settled = self.run.present(name)
                history = History(value.key, (Piece(end, settled),))
            else:
                history = view._derived_history(name, value, end, end)
            view._put(name, history)
        return view

    def _put(self, name, history):
        if name in self._counted:
            self._total += len(history.pieces) - self._counted[name]
            self._counted[name] = len(history.pieces)
        self._histories[name] = history

    def _raw_history(self, name, value, end):
        """Append just the raw pieces since the previous boundary. A checkpoint projection
        owns a different raw sequence; it builds its own history without changing the run's."""
        raw = self.pieces.get(name, ())
        prior, i = self._raw_positions.get(name, (None, 0))
        if prior is raw and i <= len(raw):
            kept = self._histories[name].pieces
            if i == len(raw):
                return self._histories[name]
        else:
            start = self._coverage_starts.get(name)
            if start is None:
                i = 0
                kept = [Piece(0.0, self.constants[name])] if name in self.constants else []
            else:
                i = bisect_left(raw, start, key=lambda piece: piece[0])
                kept = []
                if end > start and i and (i == len(raw) or raw[i][0] > start):
                    # A retired producer posted its final held value before the join.
                    # Once the join has passed, retain that genuine flat interval from
                    # the coverage boundary. A pending producer still owns its opening.
                    installed = self.run.ways.set_of
                    pending = name in installed or name.rpartition('.')[0] in installed
                    if raw[i - 1][2] == 0 and (i < len(raw) or not pending):
                        kept.append(Piece(start, raw[i - 1][1]))
        j = len(raw)
        if j and raw[-1][0] > end:
            j = bisect_right(raw, end, lo=i, key=lambda piece: piece[0])
        new = raw[i:j]
        self._extend(kept, new)
        if kept:
            self._raw_positions[name] = raw, j
        return History(value.key, kept)

    @staticmethod
    def _extend(kept, new):
        if kept and new:
            last = kept.pop()
            new.insert(0, (last.t, last.value, last.curve if last.curve is not None else last.rate))
        kept.extend(recorded_piece(*piece) for piece in _compact(new))

    def _derived_history(self, name, value, end, since):
        plan, run, histories = self.plan, self.run, self._histories
        owner = plan.occurrence_of(name)
        start = 0.0 if owner is None else histories[f'{owner}.started'].pieces[0].t
        if value.kind == CHANGED:
            stored = plan.changed[name]
            times = [run.changed_start(stored), *run.changes.get(stored, ())]
            return self._history(None, [(t, t, 0.0) for t in times if t <= end])
        if name in plan.defined:
            return self._history(value.key, self._defined(name, histories, end))
        finish = None
        if name in run.frozen or (owner is not None and value.kind == RATE):
            active = histories[f'{owner}.active'].pieces
            finish = next((piece.t for piece in active if piece.value is False), None)
        if value.kind == RATE:
            # Re-shares supply the point at each switch, key and write. Between those
            # points the amount follows its request and capacity as they move.
            anchors = {
                at: (amount, slope) for at, amount, slope in self.pieces.get(name, ()) if start <= at <= end
            }
            pieces = [] if anchors else self.formula(name, histories, end, start=start)
            for at, following in pairwise([*anchors, None]):
                amount, slope = anchors[at]
                if slope is not None:
                    pieces.append((at, amount, slope))
                    continue
                until = end if following is None else following
                fitted_input = self.formula(name, histories, until, start=at, anchors={at: (amount, None)})
                pieces.extend(piece for piece in fitted_input if following is None or piece[0] < until)
        elif name in self.formulas:
            pieces = [piece for piece in self.pieces.get(name, ()) if piece[0] <= end]
        elif value.kind == REDUCE:
            pieces = self._reduction(name, histories, end)
        elif value.kind == LOOKUP:
            pieces = self._lookup(name, histories, end)
        elif value.kind == DYNAMIC:
            return self._dynamic_history(name, histories, end, since)
        elif isinstance(value.node, nodes.Ref) and value.node.name in histories and name not in run.frozen:
            # A formula that names another value has its history.
            found = histories[value.node.name].pieces
            return History(
                value.key, found if start == 0 else tuple(p for p in found if p.t >= start) or found
            )
        elif owner is None and name not in run.frozen:
            return self._formula_tail(name, end, start, since)
        else:
            if finish is not None and self._event_ends.get(name) == finish and since >= finish:
                return histories[name]
            # A live alias can borrow its source's pieces. Its first fit at retirement
            # starts at the occurrence's own beginning, just like a cold restore.
            if name not in self._event_ends:
                since = start
            history = self._formula_tail(name, end, start, since, finish=finish)
            self._event_ends[name] = finish
            return history
        if finish is not None:
            # A checkpoint can follow the finish in the same round, before the set is
            # retired. Its occurrence's rate history already ends at zero there.
            _freeze_pieces(pieces, finish, run.frozen.get(name, 0.0))
        return self._history(value.key, pieces)

    def _formula_tail(self, name, end, start, since, *, reads=None, point=None, anchors=None, finish=None):
        """Keep the prefix preceding the restart boundary and replace the remainder."""
        value = self.plan.values[name]
        inputs = _formula_reads(value.node) if reads is None else reads
        if finish is not None:
            end = min(end, finish)
            since = min(since, end)
        boundary = _restart_point(start, since, self._histories, inputs, anchors or ())
        pieces = self.formula(
            name, self._histories, end, reads=reads, start=boundary, point=point, anchors=anchors
        )
        if finish is not None:
            _freeze_pieces(pieces, finish, self.run.frozen[name])
        prior = self._histories.get(name)
        kept = [] if prior is None or boundary == start else prior.pieces
        if self._private is not None and name not in self._private:
            kept = list(kept)
            self._private.add(name)
        del kept[bisect_left(kept, boundary, key=_piece_time) :]
        self._extend(kept, pieces)
        return History(value.key, kept)

    def record(self, end, failure=None, pause=None, *, ongoing=False):
        """The run's committed histories and trace up to the stop or horizon."""
        self._advance(end)
        return self._at_cutoff(end)._record(end, failure, pause, ongoing)

    def _record(self, end, failure, pause, ongoing):
        plan, request = self.plan, self.plan.configuration.request
        last = failure if failure is not None else pause
        trace = (*self.trace, last) if last is not None else tuple(self.trace)
        held = []
        for name, history in self._histories.items():
            if history.key is None or not history.pieces:
                continue
            pieces = tuple(history.pieces)
            if plan.changed_of.get(name) in self._histories:
                changes = self.run.changes.get(name, ())
                through_end = bisect_right(changes, end)
                times = (self.run.changed_start(name), *changes[:through_end])
                held.append(ChangeHistory(history.key, pieces, times))
            else:
                held.append(History(history.key, pieces))
        manifest = Manifest(
            request.horizon,
            request.everything,
            request.keys,
            plan.units.comparisons.factor,
            tuple(sorted(plan.comparison_scales.items())),
        )
        made = Record(manifest, tuple(held), trace, failure)
        if not ongoing:
            if self.run is not None:
                made = self.run.stock_state.project(made)
            made = _finished(made)
        # At a provisional end the recorded outgoing slopes still count. At a true end
        # they become held points, as do the retained pieces when the budget ends a run.
        # Record.within charges the trajectory and real postings, including at a pause.
        bounded = made.within(request.pieces)
        return bounded if bounded is made else requested(bounded, plan.program)

    @staticmethod
    def _history(key, pieces):
        """The history of a value from its pieces (t, value, rate), a `Curve` in place of the rate of
        a curved piece."""
        if len(pieces) == 1 and not isinstance(pieces[0][2], Curve):
            return History(key, (Piece(*pieces[0]),))
        return History(key, tuple(recorded_piece(*piece) for piece in _compact(pieces)))

    def _lookup(self, name, histories, end):
        """The pieces of a keyed read: of a stepped one, over each of its key intervals, the pieces of
        the value of the member that it selects there (below its first key `Unavailable`); of any
        other, from the histories of what it reads, as a formula's."""
        plan, run = self.plan, self.run
        keyed = plan.keyed[name]
        boolean = plan.values[name].boolean
        try:
            stepped = run.stepped_of(name) if plan.stepped(name) else None
            if stepped is None and plan.fixed_filter(name):
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

    def _dynamic_history(self, name, histories, end, since):
        """The pieces of a dynamic read from the histories of what its members project and of the
        fields that say when each is a member."""
        plan = self.plan
        dynamic = plan.dynamic[name]

        def point(t, readers):
            def value(read):
                if read not in readers:
                    raise LookupError(f'the record holds no value of {read}')
                return known(readers[read](t))

            members = plan.members_at(dynamic.source, value, t)
            return dynamic_value(dynamic, members, plan, value, t, plan.units)

        reads = tuple(sorted(plan.dynamic_reads(name)))
        if (
            dynamic.source[0] == 'flows'
            and dynamic.op == 'sum'
            and dynamic.steps == ('actual_rate',)
            and dynamic.keep is None
        ):
            # The dynamic sum is defined from zero, including its empty collection.
            if self._flow_reads.get(name) != reads:
                since = 0.0
            history = self._formula_tail(name, end, 0.0, since, reads=reads, point=point)
            self._flow_reads[name] = reads
            return history
        return self._history(plan.values[name].key, self.formula(name, histories, end, reads, point=point))

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
        anchors=None,
    ):
        """The pieces of a formula from the histories of what it reads, from `start` on (of a
        reduction or a keyed read, when `reads` and `compute` are given: the names that it reads,
        and its value from theirs, `timed` when it reads the time; of a dynamic read, when `point`
        gives its value at a time; of one definition that a commit gave the value, when `node` is its
        node)."""
        plan = self.plan
        value = plan.values[name]
        node = value.node if node is None else node
        if reads is None and compute is None and point is None and not timed and not anchors:
            names = nodes.names(node)
            if 't' not in names:
                held = _held_formula(
                    node, names, histories, start, value.boolean if boolean is None else boolean, plan.units
                )
                if held is not None:
                    return held
        if timed is None:
            timed = compute is None and point is None and 't' in nodes.names(node)
        if reads is None:
            reads = _formula_reads(node)
        reads = [read for read in reads if read in histories]
        authored = compute is None and point is None
        layers = None  # built only if a numeric authored expression actually moves
        if compute is None:

            def compute(env):
                return evaluate(node, env, plan.units)

        boolean = value.boolean if boolean is None else boolean
        openings = {float(start), *(anchors or ())}
        for read in reads:
            pieces = histories[read].pieces
            left = bisect_left(pieces, start, key=_piece_time)
            right = bisect_right(pieces, end, lo=left, key=_piece_time)
            openings.update(piece.t for piece in pieces[left:right])
        times = sorted(openings)
        bounds = [*times, end]
        crossing = plan.numerics.crossing
        readers = {read: _reader(histories[read]) for read in reads}
        holders = {read: _holder(histories[read]) for read in reads}

        names = frozenset(reads)
        starts = sorted(anchors or ())

        def environment(t):
            # Resolving a comparison can also require a selector inside a named operand.
            def read(key):
                if key not in readers:
                    readers[key] = _reader(histories[key])
                return readers[key](t)

            return Reads(names, read, t)

        def at(t):
            place = bisect_right(starts, t) - 1
            if place >= 0:
                start = starts[place]
                amount, slope = anchors[start]
                if slope is not None or start == t:
                    return amount
            if point is not None:
                return point(t, readers)

            return compute(environment(t))

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

        scale = self.run.own_scale(name) if not discrete else 1.0
        def operand(expression, t):
            return evaluate(expression, environment(t), plan.units)

        def tolerance_at(t):
            begin = first if t == a else tried(t)
            size = scale if isinstance(begin, Unavailable) else max(scale, abs(float(begin)))
            return np.array([plan.numerics.atol_factor * size])

        pieces = []
        for (a, b), first in zip(pairwise(bounds), firsts):
            held = b <= a or (not timed and all(holders[read](a) for read in reads))
            if held:
                pieces.append((a, cast(first), 0.0))
                continue
            moments = self.fits.intervals(a, b)
            added = list(moments)
            if layers is None:
                pairs = dict.fromkeys(
                    pair
                    for branch in (nodes.breadth_first(node) if authored and not discrete else ())
                    if isinstance(branch, nodes.Call) and branch.function in ('min', 'max', 'clip', 'abs')
                    for pair in switch_pairs(branch)
                )
                layers = switch_layers(tuple(pairs), {})
            if layers:
                def find_roots():
                    return _bend_times(layers, operand, c, d, tolerance_at(c), crossing)

                for c, d in pairwise([a, *moments, b]):
                    added.extend(self.fits.cached(('roots', name), c, d, find_roots))

            for lo, hi in pairwise(_fit_boundaries(a, b, added, crossing)):
                def fit():
                    begin = first if lo == a else tried(lo)
                    if discrete:
                        return _switches(lambda time: cast(tried(time)), lo, hi, cast(begin), crossing)
                    # Each moment span sets the tolerance for all of its fitted branches.
                    i = bisect_right(moments, lo)
                    origin = moments[i - 1] if i else a
                    return _numbers(at, tried, lo, hi, begin, tolerance_at(origin), crossing)

                pieces.extend(self.fits.cached(name, lo, hi, fit))
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
    its links. A keyed read adds all that the reader reads of it (`Keyed.reads`: the tests of its
    entries, their keys, its key and the value of each entry that it can select), what the inputs fix
    included: `Plan.reads` gives only what can change of it, which is what a run follows, and a
    record holds a value that the inputs fix only where something needs it."""
    found = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in found or name not in plan.values:
            continue
        found.add(name)
        value = plan.values[name]
        kind = value.kind
        if kind == LOOKUP:
            pending.extend(plan.keyed[name].reads())
        elif kind in (FORMULA, REDUCE) or (kind == RATE and value.node is not None):
            pending.extend(plan.reads(name))
        if name in definitions:
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


def requested(record, program):
    """The record with what a record of its request keeps: every history, of a record of every value;
    else the histories that its manifest names, those that their values need (`needed`, under the
    occurrences that its trace starts and the definitions that its commits gave), and the ledger of
    each store that an edit changed by its end (the store's books, `Manifest.names`); each history in
    the order of its key, a piece at its end holding its value there (`_finished`)."""
    histories = record.histories
    if not record.manifest.everything:
        found = _plan_of(program, record)
        names = needed(
            found, [name_of(key) for key in record.manifest.keys], found.definitions_of(record.trace)
        )
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
            histories.append(replace(history, pieces=Recorder._history(history.key, pieces).pieces))
        else:
            histories.append(history)
    return Record(record.manifest, tuple(histories), record.trace, record.failure)


def _order(history):
    """The place of a history in a record: by its key, whatever made the record."""
    return history.key.owner, history.key.steps


def _switches(at, a, b, first, crossing):
    """The pieces of a yes/no or a text from a to b: one at a, and one at each change, which
    bisection locates between the points of a fit to within the crossing tolerance. `Unavailable` is
    one value whatever its reason: a stretch where the value cannot be evaluated keeps the reason
    that it has where it starts."""
    pieces, value = [(a, first, 0.0)], first
    points = np.concatenate([[a], _times(a, b, _CHECKS[1:-1]), [b]])
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

    def at(time):
        k = bisect_right(history.pieces, time, key=_piece_time) - 1
        if k < 0:
            raise LookupError(f'{history.key} has no value at {time} h')
        return history.pieces[k].at(time)

    return at


def _holder(history):
    """Whether the piece of a history at a time holds its value: no rate and no curve."""

    def holds(time):
        k = bisect_right(history.pieces, time, key=_piece_time) - 1
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


@dataclass(frozen=True)
class Declaration:
    """What declares the value at a key (`declaration`): the part of the program (a value of a member,
    of the root or of an occurrence, an unknown of a solver, a flow or a leg of one, a status
    display, or the event declaring a built-in occurrence field), what of it the key reads (`what`: `value`,
    `parameter`, `builtin`, `status`, `unknown`, `endpoint`, `ledger`, `distribution`, `description`,
    `flow`, `leg` or `fraction`), and the spelling of the value's unit with its exact scale (a
    Fraction)."""

    part: object
    what: str
    unit: str = ''
    scale: Fraction = Fraction(1)


def _number(program, part, what, unit):
    """The declaration of a number in a unit of the program's table."""
    return Declaration(part, what, unit, Fraction(1) if unit == '' else Fraction(program.unit(unit).scale))


def declaration(program, key):
    """What declares the value at a key (`Declaration`), from the key's owner (an occurrence, a member
    or the root), the part that its first step names and the steps after it (spec, "What each scope
    can see"): a value; a built-in field of an occurrence; a status display; an unknown of a solver,
    which lives on the solver; a field of an endpoint of a stored number (`outflow` or `inflow`), or
    its ledger `external`; a distribution, and the `.mean` or `.std` of one of numbers; a field of a
    flow, of a route or of one of their legs; the `served_fraction` of a flow with legs. A key that
    names no value is a KeyError that says why: a part that its owner does not have, a step that the
    part does not have, an event, a solver or a collection named whole, the store at an end of a flow
    (its own path names it), a reference to an occurrence (the record holds that occurrence's values
    under its own path)."""
    steps = key.steps
    receiver = key.owner.rsplit('#', 1)[0].rpartition('.')[0] if '#' in key.owner else key.owner
    try:
        template = program.member(receiver)[0] if receiver else None
    except KeyError:
        template = None
    if not steps or (key.owner and template is None):
        raise KeyError(f'{key}: no value of the program')
    head, rest = steps[0], steps[1:]
    if '#' in key.owner:
        found = template.part(key.owner.rsplit('#', 1)[0].rpartition('.')[2])
        if not isinstance(found, p.Event):
            raise KeyError(f'{key}: no value of the program: {key.owner} is no occurrence of an event')
        if head in BUILTINS and not rest:
            return Declaration(found, 'builtin', 'h' if head == 'started' else '')
        part = next((each for each in (*found.params, *found.locals) if each.name == head), None)
        if part is not None and part in found.params and not rest:
            return _number(program, part, 'parameter', getattr(part.type, 'unit', ''))
    elif key.owner:
        part = template.part(head)
        if part is None and steps == ('status',) and template.status is not None:
            return Declaration(template.status, 'status')  # the text of the case that applies
    else:
        part = program.root_value(head)
    if part is None:
        raise KeyError(f'{key}: no value of the program')
    if isinstance(part, p.Flow):
        return _flow_field(program, key, part, rest)
    if isinstance(part, p.Solver):
        unknown = next((each for each in part.unknowns if (each.name,) == rest), None)
        if unknown is None:
            names = ', '.join(each.name for each in part.unknowns) or 'none'
            raise KeyError(f'{key}: no value of the program: the solver has the unknowns {names}')
        return _number(program, unknown, 'unknown', getattr(unknown.type, 'unit', ''))
    if isinstance(part, p.Event):
        raise KeyError(f'{key}: an event, whose occurrences have their own paths ({key}#0, {key}#1, ...)')
    value_type, path = part.type, '.'.join((key.owner, head) if key.owner else (head,))
    if isinstance(value_type, OccurrenceType):
        raise KeyError(
            f'{key}: a reference to an occurrence of {value_type.template}.{value_type.event} is no value that '
            'a record holds: read the occurrence that it names by its own path'
        )
    if isinstance(value_type, p.CollectionType):
        raise KeyError(f'{key}: {path} is a collection: read a reduction of it, or one of its members')
    unit = getattr(value_type, 'unit', '')
    if isinstance(value_type, DistributionType):
        # A distribution itself is a value of a run's state (a view shows it); its numbers are its
        # `.mean` and `.std`, in the unit of what it draws.
        unit = getattr(value_type.of, 'unit', '')
        if not rest:
            return _number(program, part, 'distribution', unit)
        if isinstance(value_type.of, p.Number) and rest in (('mean',), ('std',)):
            return _number(program, part, 'description', unit)
        raise KeyError(f'{key}: no value of the program: {path} is a distribution')
    if not rest:
        return _number(program, part, 'value', unit)
    if isinstance(value_type, p.Number) and part.kind == p.STATE:
        if rest == ('external',):
            return _number(program, part, 'ledger', unit)
        if len(rest) == 2 and rest[0] in SIDES and rest[1] in FIELDS:
            # Time is in hours, at scale 1: a rate of the store's unit per hour has the store's scale.
            found = _number(program, part, 'endpoint', unit)
            return replace(found, unit=f'{unit}/h' if unit else '1/h')
    raise KeyError(f'{key}: no value of the program')


def _flow_field(program, key, flow, rest):
    """The declaration of a field of a flow (`declaration`): the actual rate, the request and the
    capacity of a directed flow or a route, in its unit; the actual rate and the request of a leg of
    a route (its positive part in that direction); the `served_fraction` of a flow with legs, a plain
    number, and each field of one of its legs, in the leg's unit."""
    if flow.kind == p.LEGS:
        if rest == ('served_fraction',):
            return Declaration(flow, 'fraction')
        leg = next((each for each in flow.legs if len(rest) == 2 and each.name == rest[0]), None)
        if leg is not None and rest[1] in FIELDS:
            return _number(program, leg, 'leg', leg.unit)
    elif len(rest) == 1 and rest[0] in FIELDS:
        return _number(program, flow, 'flow', flow.unit)
    elif flow.kind == p.REVERSIBLE and len(rest) == 2 and rest[0] in LEGS and rest[1] in LEG_FIELDS:
        return _number(program, flow, 'leg', flow.unit)
    if rest and rest[-1] in ('source', 'sink'):
        raise KeyError(f'{key}: the store at an end of a flow, which its own path names')
    raise KeyError(f'{key}: no value of the program')


def declared(program, key):
    """The spelling of the declared unit of the value at a key and its exact scale (a Fraction): of a
    value, its type's unit, and of a solver's unknown its own (`clinic.staffing.care: h`); of a flow's
    actual rate, request or capacity, the flow's unit, and of a leg's, the leg's; of an endpoint's, its
    store's unit per hour (time is in hours, at scale 1); of a distribution's `.mean` and `.std`, the
    unit of its numbers; `''` for a plain number or a yes/no, such as a `served_fraction`. A key that
    names no value is a KeyError (`declaration`)."""
    found = declaration(program, key)
    return found.unit, found.scale


def absent(key, found):
    """Why the program gives no number to a key that names one of its properties (`Declaration`), or
    None: a capacity that a flow, a leg or an endpoint leaves out (spec, "Capacity, request and
    bounds": "A flow that declares no capacity has no ceiling of its own"). A stage may subsequently set a ceiling."""
    if key.steps[-1] != 'capacity':
        return None
    if found.what in ('flow', 'leg') and found.part.capacity is None:
        owner = '.'.join((key.owner, *key.steps[:-1]) if key.owner else key.steps[:-1])
        return f'{owner} declares no capacity: a flow that declares none has no ceiling of its own'
    if found.what == 'endpoint':
        setting = getattr(found.part, key.steps[-2])
        if setting is None or setting.capacity is None:
            owner = '.'.join((key.owner, *key.steps[:-1]) if key.owner else key.steps[:-1])
            return f'{owner} declares no capacity: an endpoint that declares none has no ceiling of its own'
    return None


def named(program, key, plan=None):
    """The declared unit and the scale of the value at a key (`declared`), once the key is checked as
    a reader checks it (`Reader.checked`) against a plan of the program (`plan`, else a new one):
    it names a value that a run of the program holds, or a property that the program leaves out,
    whose read gives the reason (`absent`). Any other key is a KeyError that says why. A key of an
    occurrence is checked against its event, since only a run makes its occurrences."""
    found = declaration(program, key)
    if '#' not in key.owner or found.what == 'ledger':
        _checked(Plan.of(program, Configuration(Request(0))) if plan is None else plan, key, found)
    return found.unit, found.scale


def _checked(plan, key, found):
    """KeyError, which says why, for a key that a declaration names and that a plan holds no value
    of: an endpoint of a store that no flow meets on that side (spec: a stored quantity "gains an
    `outflow` scope when it supplies a flow and an `inflow` scope when it receives one"), or a value
    that the plan does not make. A stock has a ledger from its opening."""
    if found.what == 'ledger':
        if not plan.is_stock(key.store, found.part):
            raise KeyError(
                f'{key}: {key.store} is no store, and only a store has a ledger of what came from outside'
            )
        return
    if found.what == 'distribution':
        if isinstance(found.part.type.of, p.Number):
            raise KeyError(f'{key}: a distribution, whose numbers a record holds as {key}.mean and {key}.std')
        raise KeyError(f'{key}: a distribution of the members of an enum, which no record holds')
    if found.what == 'endpoint':
        store, side = name_of(Key(key.owner, key.steps[:1])), key.steps[1]
        if (store, side) not in plan.ends:
            raise KeyError(f'{key}: no flow meets {store} on its {side} side, so it has no {side}')
        return
    if name_of(key) not in plan.values and absent(key, found) is None:
        raise KeyError(f'{key}: no value of a run of the program')


def in_unit(value, scale):
    """A number in canonical units in the unit of an exact scale, rounded once; any other value (a
    yes/no, a text, `Unavailable`) as it is."""
    if isinstance(value, (bool, str, Unavailable)):
        return value
    if scale == 1 or not math.isfinite(value):
        return float(value)
    return float(Fraction(value) / scale)


def _plan_of(program, record):
    """Rebuild the declarations and occurrence bindings owned by this record's trace."""
    factor = record.manifest.comparison_factor
    numerics = Numerics(rtol=factor, atol_factor=factor)
    plan = Plan.of(program, Configuration(Request(record.manifest.horizon), numerics=numerics))
    plan.comparison_scales.update(record.manifest.comparison_scales)
    plan.replay(record.trace)
    return plan


def stock_ledgers(program, record):
    """Keys of the planned stocks' ledgers that this record's manifest offers, including zeroes."""
    plan = _plan_of(program, record)
    for store in sorted(plan.stocks):
        key = plan.values[store].key
        ledger = Key(key.owner, (*key.steps, 'external'))
        if record.manifest.names(ledger):
            yield ledger


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
        self.units = self.plan.units
        self.comparison_scales = dict(record.manifest.comparison_scales)
        self.frozen_scales = {}
        self.comparison_time = None
        self.units.comparisons = Comparisons(
            self.units,
            record.manifest.comparison_factor,
            self._comparison_quantity,
        )

        # The definitions that the commits of the run gave values, from its trace: a value is read
        # with the definition that it had at the time of the read.
        self.definitions = self.plan.definitions_of(record.trace)
        # When each occurrence started, from the trace, which every record holds whole.
        self.starts = {}
        self.found = {}  # (engine name, time) -> its value, or the LookupError of a value that has none
        self.read = {}  # (engine name, time) -> the engine names that its evaluation read, in order
        # Each argument freezes what its expression actually read in the caller's transaction.
        # Use its unique parameter name as the identity of that evaluation, just as an
        # occurrence's id identifies a frozen evaluation at its finish.
        self.captures, self.replaced, self.finish_positions = {}, {}, {}
        for position, entry in enumerate(record.trace):
            if entry.kind == 'finish':
                self.finish_positions[entry.owner] = (entry.t, position)
                self.frozen_scales.update(
                    (name, (entry.t, size)) for name, size in entry.detail('scales') or ()
                )
                for name, reads in entry.detail('reads') or ():
                    self.read[name, entry.owner] = reads
            elif entry.kind in ('commit', 'fire'):
                for name in entry.detail('argument_writes') or ():
                    self.replaced.setdefault(name, (entry.t, position))
            elif entry.kind == 'edit' and entry.detail('target') in self.captures:
                self.replaced.setdefault(entry.detail('target'), (entry.t, position))
            elif entry.kind == 'start':
                self.starts[entry.owner] = float(entry.t)
                arguments = entry.detail('arguments')
                if arguments is None:
                    continue
                for field, direct, dependencies in arguments[2]:
                    param = f'{entry.owner}.{field}'
                    self.captures[param] = (entry.t, position)
                    self.read[param, param] = direct
                    for name, others in dependencies:
                        self.read[name, param] = others
        self.kept = {}
        self._always = {}  # the id of a node -> what every evaluation of it reads (`proofs.always`)
        self._checked = {}  # a key that names a value -> its `Declaration` (`checked`)

    # ---- what a caller asks -------------------------------------------------------------------------

    def readings(self, paths, times):
        """One `Reading` for each path, in order, of its values at the times in their order (see
        `read`)."""
        found = []
        for path in paths:
            key = key_of(self.program, path)
            unit, scale = self.checked(key)
            values = tuple(in_unit(self.value(key, t), scale) for t in times)
            found.append(Reading(name_of(path) if isinstance(path, Key) else path, key, unit, values))
        return found

    def checked(self, key):
        """The declared unit and the scale of a record key that names a value of the record's program
        (`declaration`): one that a run of it holds, a property that the program leaves out (`absent`),
        or a value of an occurrence that the trace never starts, which `value` gives as not started;
        any other key is a KeyError that says why (`named`). The reader's plan holds the record's
        occurrences. Each key is checked once."""
        found = self._checked.get(key)
        if found is None:
            found = declaration(self.program, key)
            if '#' not in key.owner or key.owner in self.starts or found.what == 'ledger':
                _checked(self.plan, key, found)
            self._checked[key] = found
        return found.unit, found.scale

    def value(self, key, t):
        """The value of a record key at a time in canonical units, from what the record holds, else
        `Unavailable` with the reason: a time or a value that the record does not hold
        (`Record.unavailable`), an occurrence that has not started then (from the trace), a property
        that the program leaves out (`absent`), a value that cannot be read. A key that names no value
        is a KeyError (`checked`)."""
        t = float(t)
        self.checked(key)
        reason = self.refusal(key, t)
        if reason is not None:
            return Unavailable(reason)
        try:
            if key.store is not None:
                return self.ledger(key, t)
            value = self.at(name_of(key), t)
            if key.steps[-1] == 'capacity' and value == math.inf:
                why = absent(key, self._checked[key])
                if why is not None:
                    return Unavailable(why)
            return value
        except LookupError as problem:
            stopped = self.record.stopped()
            return Unavailable(str(problem) + (f': {stopped}' if stopped else ''))

    def comparison_floor(self, key, t):
        """The comparison scale of a record key's value at a time, in canonical units (docs/design/decisions.md, change
        29): its declared scale or one declared unit, or for a formula the largest contribution of
        the quantities that it reads. None for a value that is no number then, or for a ledger."""
        t = float(t)
        if key.store is not None or not isinstance(self.value(key, t), (int, float)):
            return None

        def read(node):
            return lazily(node, lambda name: self.at(name, t), self.units, t)

        try:
            return float(self.units.comparisons.floor(nodes.ref(name_of(key)), nodes.const(0.0), read))
        except (*FAILURES, TypeError):
            return None

    def refusal(self, key, t):
        """Why the reader gives no value of a record key at a time before it reads one: a time or a
        value that the record does not hold (`Record.unavailable`), an occurrence that has not
        started then, a property that the program leaves out (`absent`); None when `value` reads it,
        from its history or by an evaluation (`at`)."""
        reason = self.record.unavailable(key, t)
        if reason is None and '#' in key.owner and not self.started(key.owner, t):
            reason = f'{key.owner} has not started at {float(t):g} h'
        if reason is None and key.store is None and name_of(key) not in self.plan.values:
            reason = absent(key, self._checked.get(key) or declaration(self.program, key))
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

    def started(self, owner, t):
        """Whether an occurrence has started at time t: its start is in the trace, at or before t."""
        start = self.starts.get(owner)
        return start is not None and start <= t

    def evidence_position(self, at):
        """A captured evaluation's place in the trace, or the settled end of a physical time."""
        if isinstance(at, str):
            return self.captures[at] if at in self.captures else self.finish_positions[at]
        return at, len(self.record.trace)

    def evidence_pair(self, name, at):
        """Identify a live evaluation by time or a frozen evaluation by its finishing occurrence."""
        if isinstance(at, str) and (name, at) in self.read:
            return name, at
        if name in self.captures:
            position = self.evidence_position(at)
            if self.captures[name] <= position and (
                name not in self.replaced or position < self.replaced[name]
            ):
                return name, name
        owner = self.plan.occurrence_of(name)
        if (name, owner) in self.read and self.finish_positions[owner] <= self.evidence_position(at):
            return name, owner
        return name, at

    def reads(self, name, t):
        """The engine names that the evaluation of an engine name at a time read, after `at` found its
        value: what its formula asked for, the members and the entries that a collection read; none
        for a value read from its history."""
        return self.read.get(self.evidence_pair(name, t), ())

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
        if (self.definitions or self.starts) and self.comparison_time != t:
            self.units.comparisons.floors.clear()
        self.comparison_time = t
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

    def _comparison_quantity(self, name):
        def latest(members):
            visible = members.through(self.comparison_time)
            return visible[-1] if visible else None

        binding = self.plan.comparison_quantity(
            name, self.comparison_scales, self._comparison_value, latest=latest, units=self.units
        )
        frozen = self.frozen_scales.get(name)
        if frozen and frozen[0] <= self.comparison_time:
            return binding._replace(floor=frozen[1], definition=None)
        return binding

    def _comparison_value(self, name):
        if name not in self.plan.values:
            return None
        return self._definition(name, self.comparison_time)

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
                found = evaluate(value.node, Reads(nodes.names(value.node), read, t), self.units)
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
        """The last commit that changed the value by t, or its creation if no commit changed it."""
        stored = self.plan.changed[name]
        read(stored)  # it has a value at t, or the change has none
        history = self._stored(self.plan.values[stored])
        if isinstance(history, ChangeHistory):
            through = bisect_right(history.changes, t)
            if through:
                return history.changes[through - 1]
            raise LookupError(f'{history.key} has no value at {t} h')
        # Earlier records have only displayed pieces. Held readings expose their jumps exactly.
        # A fitted curve's seam can differ by roundoff, so retain the earlier numerical guard there.
        pieces = history.pieces
        last = bisect_right(pieces, t, key=_piece_time) - 1
        for k in range(last, 0, -1):
            previous, piece = pieces[k - 1], pieces[k]
            before, after = previous.at(piece.t), piece.value
            held = previous.curve is piece.curve is None and previous.rate == piece.rate == 0
            if held or isinstance(before, bool | str) or isinstance(after, bool | str):
                if before != after:
                    return piece.t
            elif abs(float(after) - float(before)) > 1e-12 * max(1.0, abs(float(before))):
                return piece.t
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
        try:
            if dynamic.source[0] == 'occurrences':
                members = plan.members_at(dynamic.source, read, t)
                # A natural lookup reads just the chosen member. A reduction consults the
                # visible members, including the latest start as evidence of their membership.
                if dynamic.op != 'at' or dynamic.by is not None or dynamic.keep is not None:
                    projected = (plan.project(m, dynamic.steps) for m in members if dynamic.steps)
                    self._ready((*dynamic.controls(members, plan), *projected), t)
                if members and not dynamic.steps:
                    read(f'{members[-1][1]}.started')
            else:
                self._ready(sorted(plan.dynamic_reads(name)), t)
                members = plan.members_at(dynamic.source, read, t)
            return dynamic_value(dynamic, members, plan, read, t, self.units)
        except FAILURES as problem:
            return Unavailable(str(problem))

    def _derived(self, name, t, read):
        """A reduction or a keyed read at a time, from the recorded values of what it reads. Which
        entries it keeps is read from the predicate at the requested time. An immutable selection
        can be reused, crediting the same tested fields at each reading. What it reads
        for sure is found first: the tests, then the kept entries of a reduction,
        or the keys of a keyed read and its key; a keyed read reads only the entry that it selects."""
        plan = self.plan
        derived = plan.reductions.get(name) or plan.keyed[name]
        try:
            if name not in self.kept:
                self._ready([each for test in derived.tests if test is not None for each in always(test)], t)
                tested = []

                def selector(other):
                    tested.append(other)
                    return read(other)

                entries = kept(derived.tests, selector, self.units)
                if plan.fixed_filter(name):
                    self.kept[name] = entries, tuple(dict.fromkeys(tested))
            else:
                entries, tested = self.kept[name]
                self._ready(tested, t)
                for other in tested:
                    read(other)
            if name in plan.reductions:
                reduction = plan.reductions[name]
                self._ready([reduction.names[k] for k in entries] if reduction.names else (), t)
                return reduced(reduction, read, self.units, entries)
            keyed = plan.keyed[name]
            keys = [keyed.keys[k] for k in entries if isinstance(keyed.keys[k], str)]
            self._ready([*keys, *sorted(always(keyed.key))], t)
            index = index_of(keyed, read, self.units, entries)
            return looked_up(keyed, read, self.units, t, index)
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
