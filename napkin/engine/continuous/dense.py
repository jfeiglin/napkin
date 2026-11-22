"""How a weighted sum of the stores of a segment moves over a piece of it, read from the form of the
segment's solution (`Motion`): the sum and its rate at the start of the piece, the most that its rate
can differ from that rate over the piece, and the most that the sum can move over the piece. A
reader of a condition on moving values bounds with it how far the value can move over a piece, and
whether it can turn there (`timeline/triggers.py`).

Each bound is derived from the form itself, not from samples of it:

- **A step of Radau** (`scipy.integrate.Radau`). Its dense output is the collocation polynomial,
  `y(t) = y_old + Q [x, x^2, x^3]` with `x = (t - t_old) / h`: a cubic in the time over the step,
  and the solution that the run reads there. Over a piece `[s, e]` of the step a weighted sum of
  the stores is the cubic `c0 + c1 u + c2 u^2 + c3 u^3` in `u = (t - s) / (e - s)`, exactly. As `u`
  lies in [0, 1], its rate at `s` is `c1 / (e - s)`, its rate over the piece differs from that by at
  most `(2 |c2| + 3 |c3|) / (e - s)`, and it moves by at most `|c1| + |c2| + |c3|`.
- **The closed form of a compartment segment** (`kernels.MatrixExponential`). The stores of its
  block follow `y' = A y + c`, so their rates follow `y'' = A y'`: `y'(t) = expm(A τ) y'(s)` with
  `τ = t - s`. In the largest norm `|expm(A τ)| <= exp(m τ)`, where `m`, the logarithmic norm of A,
  is the largest of `A_ii + sum_j!=i |A_ij|` (negative where every store of the block drains more
  than it takes in), and `|expm(A τ) - I| <= exp(|A| τ) - 1`. A weighted sum `S = w . y` of them has
  the rate `S'(t) = v(τ) . y'(s)` with `v(τ) = expm(A^T τ) w`, and `v(τ) - w` is the integral of
  `expm(A^T σ) A^T w`, whose norm is at most `|A^T w| exp(m σ)` (the norm of the transpose is the
  largest column sum). So with `φ(τ)`, the integral of `exp(m σ)` from 0 to τ, the rate of S
  differs from `S'(s)` by at most the smaller of `|w| (exp(|A| τ) - 1) |y'(s)|` and
  `|A^T w| φ(τ) |y'(s)|`, and S moves by at most the smaller of `|w| φ(τ) |y'(s)|` and
  `|S'(s)| τ + |A^T w| |y'(s)|` times the integral of φ. A sum that the block conserves
  (`A^T w = 0`, as for the books of a transfer) keeps its rate; a store that drains to its balance
  moves by at most `|y'(s)| / |m|`, however long the piece. A store outside the block is on a line.
- **A step of no length** holds its stores.

Each bound holds for the form in exact arithmetic. `size`, the sum of the absolute values of the
weighted terms at `s`, sets the scale of the roundoff that a reader adds, and `margin` is the most
that a value that the run reads can differ from the form (the caller's: a component reads a store
within its slack of a bound on the bound).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from scipy.optimize import brentq


@dataclass(frozen=True)
class Motion:
    """How a weighted sum moves over a piece (see the module): its value and its rate at the start of
    the piece, the most that its rate differs from that rate over the piece (`spread`), the most
    that it moves over the piece (`change`), the sum of the absolute values of its weighted terms at
    the start (`size`), and the most that a value read differs from the form (`margin`)."""

    value: float = 0.0
    rate: float = 0.0
    spread: float = 0.0
    change: float = 0.0
    size: float = 0.0
    margin: float = 0.0

    def __add__(self, other):
        return Motion(
            self.value + other.value,
            self.rate + other.rate,
            self.spread + other.spread,
            self.change + other.change,
            self.size + other.size,
            self.margin + other.margin,
        )


def line(value, rate, length):
    """The motion of a weighted store on a line, `value` at the start of a piece of `length`."""
    return Motion(value, rate, 0.0, abs(rate) * length, abs(value))


def held(values, weights):
    """The motion of weighted stores that hold their `values` through the piece."""
    return Motion(float(weights @ values), size=float(np.abs(weights) @ np.abs(values)))


def of_step(output, rows, weights, start, end):
    """The motion of the weighted stores `rows` of the dense output of one Radau step over
    [start, end], a piece of the step (see the module)."""
    if not hasattr(output, 'Q'):
        # A step of no length (`scipy.integrate.ConstantDenseOutput`).
        return held(np.asarray(output.value, dtype=float)[rows], weights)
    x = (start - output.t_old) / output.h
    span = (end - start) / output.h  # the piece in units of the step
    q = output.Q[rows]
    values = output.y_old[rows] + q @ np.array([x, x * x, x * x * x])
    p1, p2, p3 = (weights @ q).tolist()
    c1 = span * (p1 + 2 * p2 * x + 3 * p3 * x * x)
    c2 = span * span * (p2 + 3 * p3 * x)
    c3 = span**3 * p3
    length = end - start
    return Motion(
        float(weights @ values),
        c1 / length,
        (2 * abs(c2) + 3 * abs(c3)) / length,
        abs(c1) + abs(c2) + abs(c3),
        float(np.abs(weights) @ np.abs(values)),
    )


def _turns(c, b, a):
    """The extrema of c*x + b*x² + a*x³, each with whether it is a minimum."""
    scale = max(abs(a), abs(b), abs(c))
    if not scale:
        return ()
    # Normalize before forming squares. The q form of the quadratic retains
    # the finite root when the cubic term approaches zero.
    aa, bb, cc = 3 * (a / scale), b / scale, c / scale
    if aa == 0:
        return ((-cc / (2 * bb), b > 0),) if bb else ()
    discriminant = bb * bb - aa * cc
    if abs(discriminant) <= 8 * math.ulp(1.0) * (bb * bb + abs(aa * cc)):
        # A double root of the derivative is a stationary inflection, not a turn.
        exact = Fraction(b) ** 2 - 3 * Fraction(a) * Fraction(c)
        if exact <= 0:
            return ()
        discriminant = float(exact / Fraction(scale) ** 2)
    if discriminant <= 0:
        return ()
    q = -bb - math.copysign(math.sqrt(discriminant), bb)
    left, right = sorted((q / aa, cc / q))
    return ((left, a < 0), (right, a > 0))


def _turn_sign(d, c, b, a, minimum):
    """Sign of the cubic at the mathematical extremum, even for a double contact.

    Substitution of a derivative root in the cubic gives (B ± 2*D**1.5)/(27*a²),
    with B and D below. Comparing squares exactly distinguishes a touch from a
    miss narrower than the error of evaluating the polynomial at a rounded time.
    """
    d, c, b, a = map(Fraction, (d, c, b, a))
    if a == 0:
        value = d - c * c / (4 * b)
    else:
        det = b * b - 3 * a * c
        base = 27 * a * a * d - 9 * a * b * c + 2 * b**3
        if minimum:
            value = base * base - 4 * det**3 if base >= 0 else -1
        else:
            value = 4 * det**3 - base * base if base <= 0 else 1
    return (value > 0) - (value < 0)


def _distinct_turn(level, sign, c, b, a, minimum):
    """Does the extremum of a step starting on this face reach a different float?"""
    direction = -1 if minimum else 1
    neighbor = math.nextafter(level, direction * sign * math.inf)
    if math.isinf(neighbor):
        return True  # no finite neighboring face in this direction
    # Compare the exact extremum with the midpoint, even when that midpoint is
    # half the smallest subnormal. At the midpoint respect ties-to-even.
    midpoint = (Fraction(neighbor) - Fraction(level)) * int(sign) / 2
    side = _turn_sign(-midpoint, c, b, a, minimum)
    return side == direction or (not side and float((Fraction(neighbor) + Fraction(level)) / 2) != level)


def _first_arrival(initial, level, sign, c, b, a, start, end, last):
    """First arrival from the negative side of one signed coordinate cubic."""

    d = (initial - level) * sign
    exact_d = None

    def gap(x, minimum=None):
        nonlocal exact_d
        value = ((a * x + b) * x + c) * x + d
        size = ((abs(a) * x + abs(b)) * x + abs(c)) * x + abs(d)
        if abs(value) > 8 * math.ulp(1.0) * size:
            return value
        if exact_d is None:
            # Subtracting a small nonzero bound from a much larger initial
            # value can lose the bound. Retain both original operands here.
            exact_d = (Fraction(initial) - Fraction(level)) * int(sign)
        if minimum is not None:
            side = _turn_sign(exact_d, c, b, a, minimum)
            return math.copysign(max(abs(value), math.ulp(0.0)), side) if side else 0.0
        at = Fraction(x)
        exact = ((Fraction(a) * at + Fraction(b)) * at + Fraction(c)) * at + exact_d
        rounded = float(exact)
        return rounded if rounded or not exact else math.copysign(math.ulp(0.0), 1 if exact > 0 else -1)

    before = start
    first = d if start == 0 else gap(start)
    stops = [(x, minimum) for x, minimum in _turns(c, b, a) if start < x < end]
    stops.append((end, None))
    if start == 0 and initial == level:
        # A cubic fitted at an existing contact can turn outward by less than
        # half a representable stock value before really leaving inward. Arm a
        # return only after a distinguishable departure. For a true outward
        # departure, keep the mathematical root of the lobe that reaches it.
        interior = None
        for i, (x, minimum) in enumerate(stops):
            if minimum is None and last is not None:
                value, distinct = last, last != 0
            else:
                value = gap(x, minimum)
                if minimum is not None:
                    distinct = _distinct_turn(level, sign, c, b, a, minimum)
                else:
                    at = Fraction(x)
                    distance = ((Fraction(a) * at + Fraction(b)) * at + Fraction(c)) * at
                    try:
                        distinct = float(Fraction(level) + int(sign) * distance) != level
                    except OverflowError:
                        distinct = True
            if value < 0:
                interior = i, x, value
            if distinct:
                if interior is None:
                    return start
                index, before, first = interior
                stops = stops[index + 1 :]
                break
        else:
            return None
    for after, minimum in stops:
        final = last if after == end and last is not None else gap(after, minimum)
        if before == start and first == 0 and final > 0:
            return before
        if first < 0 <= final:
            if final == 0:
                return after

            # The stored step endpoints can differ from the collocation curve by
            # roundoff; preserve their signs at the ends of the monotone bracket.
            def bracket(x):
                if x == before:
                    return first
                if x == after:
                    return final
                return gap(x)

            return brentq(bracket, before, after, xtol=math.ulp(0.0), maxiter=1100)
        before, first = after, final
    return None


def bound_crossings(output, start, end, rows, levels, directions, *, accepted_end=None):
    """First outward arrivals at the supplied stock faces in a Radau step or subinterval.

    Return (physical time, position in rows), in chronological order. A repeated
    row can name both faces. Each candidate cubic is split at its extrema: its
    endpoints alone can miss a complete excursion. An exact tangency approached
    from the interior counts. A stationary face or an inward departure does not.
    When supplied, accepted_end is the accepted full state at end.
    """
    if end <= start or not len(rows) or not hasattr(output, 'Q'):
        return []
    rows, levels, directions = np.asarray(rows), np.asarray(levels), np.asarray(directions)
    coefficients = output.Q[rows]
    offsets = output.y_old[rows] - levels
    # On x in [0,1], the distance from y_old is at most the sum of the absolute
    # coefficients. Round the enclosure outward, then inspect just the nearby
    # moving rows (including ones whose accepted endpoint certifies a contact).
    reach = np.abs(coefficients).sum(axis=1)
    nearby = (reach > 0) & (np.abs(offsets) <= np.nextafter(reach * (1 + 4 * math.ulp(1.0)), np.inf))
    final = None
    if accepted_end is not None:
        final = (np.asarray(accepted_end)[rows] - levels) * directions
        incoming = offsets * directions
        nearby |= (incoming < 0) & (final >= 0)
    lo, hi = (start - output.t_old) / output.h, (end - output.t_old) / output.h
    found = []
    for k in np.flatnonzero(nearby & np.isfinite(levels)).tolist():
        c, b, a = coefficients[k].tolist()
        sign = float(directions[k])
        at = _first_arrival(
            float(output.y_old[rows[k]]),
            float(levels[k]),
            sign,
            c * sign,
            b * sign,
            a * sign,
            lo,
            hi,
            float(final[k]) if final is not None else None,
        )
        if at is not None:
            if at == lo:
                time = start
            elif at == hi:
                time = end
            else:
                # A positive elapsed time can round back to the absolute start
                # of a late step. Retain forward progress in physical time.
                time = max(math.nextafter(start, end), min(end, output.t_old + at * output.h))
            found.append((float(time), k))
    return sorted(found)


def of_exponential(solution, rows, weights, start, end):
    """The motion of the weighted stores `rows` of a compartment segment's closed form over
    [start, end] (see the module)."""
    length = end - start
    state = solution(start)
    values, slope = state[rows], solution.slope[rows]
    outside = np.ones(len(rows), dtype=bool)
    rate = spread = change = 0.0
    if len(solution.rows):
        columns, block = solution.columns, solution.block
        matrix = block[:-1, :-1]
        place = np.minimum(np.searchsorted(columns, rows), len(columns) - 1)
        outside = columns[place] != rows
        w = np.zeros(len(columns))
        np.add.at(w, place[~outside], weights[~outside])
        derivative = matrix @ state[columns] + block[:-1, -1]
        rate = float(w @ derivative)
        top = float(np.abs(derivative).max())  # |y'(s)| in the largest norm
        total, flowing = float(np.abs(w).sum()), float(np.abs(matrix.T @ w).sum())  # |w|, |A^T w|
        absolute = np.abs(matrix)
        norm = float(absolute.sum(axis=1).max())
        log_norm = float((np.diag(matrix) + absolute.sum(axis=1) - np.abs(np.diag(matrix))).max())
        phi, psi = _integrals(log_norm, length)
        spread = min(_times(total * top, _expm1(norm * length)), _times(flowing * top, phi))
        change = min(_times(total * top, phi), abs(rate) * length + _times(flowing * top, psi))
    lines = float(weights[outside] @ slope[outside])
    return Motion(
        float(weights @ values),
        rate + lines,
        spread,
        change + abs(lines) * length,
        float(np.abs(weights) @ np.abs(values)),
    )


def _integrals(m, length):
    """The integral of exp(m σ) over [0, length], and the integral of that integral."""
    x = m * length
    if abs(x) < 1e-3:
        # Their series, where the closed forms below lose their digits, each with a bound on the
        # rest of its terms (|x|^3 / 24 e^|x| and |x|^3 / 120 e^|x|), so that each stays above its integral.
        r = abs(x) ** 3
        return length * (1 + x / 2 + x * x / 6 + r / 20), length * length * (
            0.5 + x / 6 + x * x / 24 + r / 100
        )
    grown = _expm1(x)
    return grown / m, (grown - x) / (m * m)


def _times(factor, bound):
    """A factor times a bound that may be infinite: no motion where the factor is zero."""
    return factor * bound if factor else 0.0


def _expm1(x):
    """exp(x) - 1, and infinity where it overflows."""
    return math.expm1(x) if x < 709.0 else math.inf
