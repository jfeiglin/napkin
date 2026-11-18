"""The record of a run (`napkin/program/record.py`): the history of each value as pieces, the trace,
and the reader of named paths at chosen times.

A piece reads `value + rate * (time - t)` from its time until the next piece. The recorder makes the
pieces of each value of a run:

- **An input, a stored value that does not move, a draw and a captured request or capacity** has one
  constant piece at the start.
- **A store and the actual rate of a flow** take their pieces from the segments of their component,
  as the run makes them, while the bounds and the faces of each segment hold (`Recorder.segment`).
  On a straight segment (a closed form of constant rates) a store has one exact piece of its rate,
  and a flow one constant piece. A curved segment (an exponential closed form, or the solver) gives
  pieces whose rate is a `Curve`: the value follows a Chebyshev series of degree `DEGREE` over the
  piece, within the tolerance of the value, and a piece is cut in two until it does. A solver's
  segment is fitted step by step: its dense output is a cubic in each step, which the series holds
  exactly. The state that a segment starts from opens its pieces, so a settled bound is a jump.
- **A formula, and a request or a capacity written as one,** is made after the run from the
  histories of what it reads: between two times at which one of them has a piece, it is fitted as
  a curve is, and a yes/no takes a piece at each change, located to within the time between two
  moments. A formula that cannot be evaluated holds `Unavailable` with the reason.

Numbers are in the canonical unit of their dimension. `read` gives them in the declared unit of
each path.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from numpy.polynomial import chebyshev

from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.record import Entry, History, Key, Manifest, Piece, Record, Unavailable
from ..continuous.kernels import Affine, MatrixExponential
from ..continuous.system import EVENT_TIME_TOLERANCE_H
from .plan import FORMULA, RATE, name_of

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


@dataclass(frozen=True)
class Curve:
    """The rate of a curved piece: the Chebyshev series `coefficients` of the value over `length`
    hours from the start of the piece. A piece reads `value + rate * (time - t)`, and so does a curved
    one: `rate * elapsed` is the increase of the series from the start of the piece."""

    length: float
    coefficients: tuple[float, ...]

    def __mul__(self, elapsed):
        u = 2.0 * float(elapsed) / self.length - 1.0
        return float(chebyshev.chebval(u, self.coefficients) - chebyshev.chebval(-1.0, self.coefficients))

    __rmul__ = __mul__


def _times(start, end, points):
    return start + (points + 1.0) * 0.5 * (end - start)


def fitted(values, start, end, tolerance):
    """The pieces of k values from `start` to `end`: one list for each value, each piece a (time,
    value, rate). `values(times)` gives an array of one row for each time; `tolerance` holds one
    number for each value, which a fit may widen to `RELATIVE` of the value's largest size in the
    piece. A value that the series holds as a line has a number for its rate."""
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

    def entry(self, t, kind, part, owner='', **details):
        """One entry of the trace. Its round is 0 at the setup, and 1 at a later time: this slice
        has one round at a time."""
        self.trace.append(Entry(t, 0 if t == 0 else 1, kind, part, owner, tuple(details.items())))

    @staticmethod
    def failure(t, message):
        """The entry of the failure that stopped a run at time t."""
        return Entry(t, 0 if t == 0 else 1, 'failure', '', '', (('message', message),))

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

    # ---- after the run ----------------------------------------------------------------------------

    def record(self, end, failure=None):
        """The record of the run, to the time `end` at which it stopped (the horizon, or the time of
        its failure)."""
        plan = self.plan
        histories = {}
        for name, value in plan.values.items():
            if value.kind == RATE or name in plan.moving:
                pieces = [piece for piece in self.pieces.get(name, ()) if piece[0] <= end]
                if not pieces and name in self.constants:
                    # A store whose first segment failed holds its start value.
                    pieces = [(0.0, self.constants[name], 0.0)]
            elif value.kind == FORMULA:
                continue
            else:
                pieces = [(0.0, self.constants[name], 0.0)] if name in self.constants else []
            histories[name] = self._history(value.key, pieces)
        for name in plan.ordered({name for name, value in plan.values.items() if value.kind == FORMULA}):
            histories[name] = self._history(plan.values[name].key, self.formula(name, histories, end))
        request = plan.configuration.request
        kept = [
            history
            for history in histories.values()
            if history.pieces and (request.everything or history.key in request.keys)
        ]
        manifest = Manifest(request.horizon, request.everything, request.keys)
        trace = tuple(self.trace) + ((failure,) if failure is not None else ())
        return Record(manifest, tuple(kept), trace, failure)

    @staticmethod
    def _history(key, pieces):
        return History(key, tuple(Piece(t, value, rate) for t, value, rate in _compact(pieces)))

    def formula(self, name, histories, end):
        """The pieces of a formula from the histories of what it reads."""
        plan = self.plan
        value = plan.values[name]
        reads = sorted(plan.reads(name))
        times = sorted(
            {0.0, *(piece.t for read in reads for piece in histories[read].pieces if piece.t <= end)}
        )
        bounds = [*times, max(end, times[-1])]
        readers = {read: _reader(histories[read]) for read in reads}

        def at(t):
            env = {read: readers[read](t) for read in reads}
            env['t'] = float(t)
            for found in env.values():
                if isinstance(found, Unavailable):
                    raise ExpressionError(found.reason)
            return evaluate(value.node, env, plan.units)

        # The size of the formula, as a store's: the largest magnitude that it takes at a time at
        # which what it reads has a piece.
        size = 1.0
        if not value.boolean:
            for time in times:
                try:
                    size = max(size, abs(float(at(time))))
                except (ExpressionError, ArithmeticError, ValueError, LookupError):
                    continue
        tolerance = np.array([plan.numerics.atol_factor * size])
        pieces = []
        for a, b in pairwise(bounds):
            try:
                first = at(a)
            except (ExpressionError, ArithmeticError, ValueError, LookupError) as problem:
                pieces.append((a, Unavailable(str(problem)), 0.0))
                continue
            if b <= a:
                pieces.append((a, bool(first) if value.boolean else float(first), 0.0))
            elif value.boolean:
                pieces += self._switches(at, a, b, bool(first))
            else:
                try:
                    found = fitted(lambda ts: np.array([[float(at(t))] for t in ts]), a, b, tolerance)[0]
                except (ExpressionError, ArithmeticError, ValueError, LookupError) as problem:
                    found = [(a, Unavailable(str(problem)), 0.0)]
                pieces += found
        return pieces

    @staticmethod
    def _switches(at, a, b, first):
        """The pieces of a yes/no from a to b: one at a, and one at each change, which bisection
        locates between the points of a fit."""
        pieces, value = [(a, first, 0.0)], first
        points = _times(a, b, np.concatenate([[-1.0], _CHECKS[1:-1], [1.0]]))
        for before, after in pairwise(points):
            if bool(at(after)) == value:
                continue
            left, right = before, after
            while right - left > EVENT_TIME_TOLERANCE_H:
                middle = 0.5 * (left + right)
                if bool(at(middle)) == value:
                    left = middle
                else:
                    right = middle
            value = not value
            pieces.append((right, value, 0.0))
        return pieces


def _reader(history):
    """`History.at` of a history, by bisection over the times of its pieces."""
    times = [piece.t for piece in history.pieces]

    def at(time):
        k = bisect_right(times, time) - 1
        if k < 0:
            raise LookupError(f'{history.key} has no value at {time} h')
        piece = history.pieces[k]
        if piece.rate == 0 or isinstance(piece.value, (bool, str, Unavailable)):
            return piece.value
        return piece.value + piece.rate * (time - piece.t)

    return at


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
    """The record key of a path: a `Key` as it is, or a text that starts with a member's id (the
    longest that matches) or with a name of the root (`tank.water`, `clinic.delivery.actual_rate`,
    `effort`)."""
    if isinstance(path, Key):
        return path
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
    """The spelling of the declared unit of the value at a key: of a value, its type's unit; of a
    flow's actual rate, request or capacity, the flow's unit; `''` for a plain number or a yes/no."""
    if key.owner:
        template = program.member(key.owner)[0]
        part = template.part(key.steps[0])
    else:
        part = program.root_value(key.steps[0])
    if part is None:
        raise KeyError(f'{key}: no value of the program')
    if hasattr(part, 'unit'):  # a flow
        return part.unit
    return getattr(part.type, 'unit', '')


def read(record, program, paths, times):
    """The values of named paths at chosen times, each in its declared unit: one `Reading` for each
    path, in order. A time that the record does not hold is a LookupError."""
    found = []
    for path in paths:
        key = key_of(program, path)
        unit = unit_of(program, key)
        scale = 1.0 if unit == '' else float(program.unit(unit).scale)
        history = record.history(key)
        values = []
        for t in times:
            if not record.manifest.holds(key, t):
                raise LookupError(f'{path}: the record holds no value at {t} h')
            value = history.at(t)
            if not isinstance(value, (bool, str, Unavailable)):
                value = float(value) / scale
            values.append(value)
        found.append(Reading(name_of(path) if isinstance(path, Key) else path, key, unit, tuple(values)))
    return found
