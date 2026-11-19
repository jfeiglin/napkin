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

import numpy as np


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
