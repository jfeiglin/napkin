"""Equilibria and their stability (napkin/dynamics/equilibria.py).

The fold X' = mu - (X - c)^2 has the equilibria c + sqrt(mu), stable with eigenvalue -2 sqrt(mu), and
c - sqrt(mu), unstable with eigenvalue 2 sqrt(mu), for mu > 0, and none for mu < 0. A linear field has
one equilibrium, whose eigenvalues are those of its matrix.

The search must cross what stops Newton's line search: a kink where the residual has a local minimum,
and a smooth local minimum of the residual. A line of equilibria is one equilibrium with one neutral
mode, and a fold point with the same linear part is not. A rest on a kink takes the class of its less
stable side, and a smooth rest, however curved, is no kink. Each expectation is a closed form of the
field (tests/dynamics/models.py)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin.dynamics import (
    NONHYPERBOLIC,
    SADDLE,
    STABLE,
    UNSTABLE,
    classify,
    equilibria,
    equilibrium_at,
    newton,
    vector_field,
)
from tests.build import compiled
from tests.dynamics.models import (
    CENTRE,
    cubic,
    fold,
    fold_and_decay,
    kinked_stall,
    linear,
    ridge,
    semistable,
)


def cubic_root():
    """The real root of y^3 - 2 y + 2 = 0, by Cardano's formula (one real root: q^2/4 + p^3/27 > 0)."""
    p, q = -2.0, 2.0
    d = math.sqrt(q**2 / 4 + p**3 / 27)
    return sum(math.copysign(abs(v) ** (1 / 3), v) for v in (-q / 2 + d, -q / 2 - d))


@pytest.mark.parametrize('mu', [0.25, 1.0, 4.0])
def test_the_fold_has_two_equilibria_of_opposite_stability(mu):
    field = vector_field(compiled(fold(mu)), 'a')
    found = equilibria(field, starts=16, seed=3, box={'s.x': (CENTRE - 4, CENTRE + 4)})
    assert len(found) == 2
    low, high = found
    root = math.sqrt(mu)
    assert low.value('s.x') == pytest.approx(CENTRE - root, abs=1e-8)
    assert high.value('s.x') == pytest.approx(CENTRE + root, abs=1e-8)
    assert (low.stability, high.stability) == (UNSTABLE, STABLE)
    assert low.eigenvalues[0].real == pytest.approx(2 * root, rel=1e-5)
    assert high.eigenvalues[0].real == pytest.approx(-2 * root, rel=1e-5)
    assert max(low.residual, high.residual) <= 1e-10


def test_the_fold_has_no_equilibrium_below_its_fold():
    field = vector_field(compiled(fold(-1.0)), 'a')
    assert equilibria(field, starts=16, seed=3, box={'s.x': (CENTRE - 4, CENTRE + 4)}) == []
    _, converged = newton(field, np.array([CENTRE]))
    assert not converged


def test_a_linear_field_has_one_equilibrium_with_the_eigenvalues_of_its_matrix():
    a = ((-1.0, -2.0), (2.0, -1.0))
    field = vector_field(compiled(linear(a)), 'a')
    (found,) = equilibria(field, starts=8, seed=1)
    assert found.state == pytest.approx([CENTRE, CENTRE], abs=1e-9)
    assert sorted(found.eigenvalues, key=lambda z: z.imag) == pytest.approx(
        sorted(np.linalg.eigvals(np.array(a)), key=lambda z: z.imag), abs=1e-6
    )
    assert found.stability == STABLE


@pytest.mark.parametrize(
    ('eigenvalues', 'stability'),
    [
        ([-1.0, -2.0], STABLE),
        ([1.0, 2.0], UNSTABLE),
        ([-1.0, 1.0], SADDLE),
        ([0.0, -1.0], NONHYPERBOLIC),
        ([complex(-0.5, 2), complex(-0.5, -2)], STABLE),
        ([complex(1e-12, 2), complex(1e-12, -2)], NONHYPERBOLIC),
    ],
)
def test_stability_follows_the_real_parts_of_the_eigenvalues(eigenvalues, stability):
    assert classify(eigenvalues) == stability


@pytest.mark.parametrize('y0', [0.0, 0.5, 1.0, 3.0])
def test_the_search_crosses_a_kink_where_the_residual_has_a_local_minimum(y0):
    # Above y = -5/6, X' = -1/2 - |y|. From any start above the kink, Newton's steps on each linear piece
    # overshoot to the other piece, and the line search ends on the kink y = 0, where |X'| has its least
    # value 1/2 and the central difference is zero. The flow X' < 0 carries the state down to the rest.
    field = vector_field(compiled(kinked_stall(start=CENTRE + y0)), 'a')
    x, converged = newton(field, field.start)
    assert converged
    assert x[0] == pytest.approx(CENTRE - 1.5, abs=1e-9)
    (found,) = equilibria(field, starts=0)
    assert found.value('s.x') == pytest.approx(CENTRE - 1.5, abs=1e-9)
    assert found.stability == STABLE and not found.kink
    assert found.eigenvalues[0].real == pytest.approx(-2.0, rel=1e-6)


@pytest.mark.parametrize('y0', [1.0, 2.0])
def test_the_search_passes_a_smooth_local_minimum_of_the_residual(y0):
    # |X'| = |y^3 - 2 y + 2| has a local minimum at y = sqrt(2/3), above the root, where the derivative is
    # zero and X' is not. X' < 0 everywhere above the root, so the flow reaches it.
    field = vector_field(compiled(cubic(start=CENTRE + y0)), 'a')
    x, converged = newton(field, field.start)
    assert converged
    root = cubic_root()
    assert x[0] == pytest.approx(CENTRE + root, abs=1e-9)
    (found,) = equilibria(field, starts=0)
    assert found.stability == STABLE
    assert found.eigenvalues[0].real == pytest.approx(-(3 * root**2 - 2), rel=1e-6)


def test_a_line_of_rests_is_one_equilibrium_with_one_neutral_mode():
    mu = 1.0
    field = vector_field(compiled(ridge(mu)), 'a')
    box = {'s.x': (CENTRE - 4, CENTRE + 4), 's.w': (CENTRE - 4, CENTRE + 4)}
    # Pairs of starts that end at different points of each line: Newton's steps cross the lines along
    # (1, 1), so (c + 3, c + 1) ends at (c + 2, c) and (c + 1, c + 3) at (c, c + 2).
    include = [
        np.array([CENTRE + a, CENTRE + b]) for a, b in ((3, 1), (1, 3), (-2, -1), (-1, -2), (-2.5, 0.5))
    ]
    found = equilibria(field, starts=8, seed=2, box=box, include=include)
    assert len(found) == 2
    root = math.sqrt(mu)
    for item in found:
        s = item.state.sum() / 2 - CENTRE
        assert abs(s) == pytest.approx(root, abs=1e-8)
        assert item.neutral == 1
        # The neutral direction lies along the line: (1, -1), in units of the sizes, which are equal.
        assert abs(item.neutral_modes[:, 0] @ np.array([1.0, -1.0])) / math.sqrt(2) == pytest.approx(
            1.0, abs=1e-6
        )
        assert item.transverse == pytest.approx([-3 * s], rel=1e-5)
        assert item.stability == (STABLE if s > 0 else UNSTABLE)
        # The whole spectrum keeps the zero eigenvalue of the line.
        assert np.min(np.abs(item.eigenvalues)) <= 1e-6


def test_a_fold_point_has_a_null_direction_but_no_neutral_mode():
    # Both rests have the derivative [[0, 1], [0, -1]] or diag(0, -1): the eigenvalues 0 and -1, and the
    # null direction (1, 0). Along it, the linear field keeps a line of rests (W' = 0 at W = c, for every
    # X), and the fold X' = -(X - c)^2 has none.
    line = vector_field(compiled(linear(((0.0, 1.0), (0.0, -1.0)))), 'a')
    rest = equilibrium_at(line, np.array([CENTRE + 1, CENTRE]))
    assert (rest.neutral, rest.stability) == (1, STABLE)
    assert rest.transverse == pytest.approx([-1.0], rel=1e-6)
    fold_point = equilibrium_at(vector_field(compiled(fold_and_decay(0.0)), 'a'), np.array([CENTRE, CENTRE]))
    assert sorted(fold_point.eigenvalues.real) == pytest.approx([-1.0, 0.0], abs=1e-6)
    assert (fold_point.neutral, fold_point.stability) == (0, NONHYPERBOLIC)


@pytest.mark.parametrize(('decay', 'expected'), [(None, UNSTABLE), (1.0, SADDLE)])
def test_a_rest_on_a_kink_takes_the_class_of_its_less_stable_side(decay, expected):
    # X' = min(a y, -b y): X falls back from above the rest at the rate b and runs away below it at the
    # rate a. The central difference (a - b) / 2 < 0 alone calls the rest stable.
    a, b = 0.5, 2.0
    field = vector_field(compiled(semistable(a, b, decay=decay)), 'a')
    found = equilibrium_at(field, field.start)
    others = [] if decay is None else [-decay]
    assert sorted(found.eigenvalues.real) == pytest.approx(sorted([(a - b) / 2, *others]), rel=1e-6)
    assert classify(found.eigenvalues) == STABLE
    assert found.kink
    forward, backward = found.sides
    assert (forward.name, backward.name) == ('forward', 'backward')
    assert sorted(forward.eigenvalues.real) == pytest.approx(sorted([-b, *others]), rel=1e-6)
    assert sorted(backward.eigenvalues.real) == pytest.approx(sorted([a, *others]), rel=1e-6)
    assert (forward.stability, backward.stability) == (STABLE, expected)
    assert found.stability == expected


@pytest.mark.parametrize('mu', [1e-2, 1.0])
def test_a_smooth_rest_is_no_kink_however_curved(mu):
    # The one-sided differences of X' = mu - (X - c)^2 differ by the curvature -2 times the step: a jump
    # of 1e-4 of the slope at mu = 1e-2. The jump halves with the step, as no kink's does.
    field = vector_field(compiled(fold(mu)), 'a')
    for sign in (1.0, -1.0):
        x = np.array([CENTRE + sign * math.sqrt(mu)])
        found = equilibrium_at(field, x)
        assert not found.kink and found.sides == ()
        forward, backward, kinks = field.one_sided(x)
        assert (forward - backward)[0, 0] == pytest.approx(-2 * field.steps(x)[0], rel=1e-2)
        assert not kinks.any()
