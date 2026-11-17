"""Thresholds between the ends of real runs (napkin/dynamics/basins.py).

The cusp X' = mu + 3 y - y^3 with y = X - c has two stable equilibria for |mu| < 2 and an unstable one
between them: the edge of their basins. The edge is the middle root of y^3 - 3 y - mu = 0, which the
trigonometric formula gives, so a run that starts below it ends low and one that starts above ends high.
"""

from __future__ import annotations

import math

import pytest

from napkin.dynamics import input_threshold, state_threshold, threshold
from tests.build import compiled
from tests.dynamics.models import CENTRE, cusp

LAM = 3.0


def middle_root(mu, lam=LAM):
    """The middle root of y^3 - lam y - mu = 0 (three real roots when |mu| < 2 (lam / 3)^(3/2))."""
    r = 2 * math.sqrt(lam / 3)
    theta = math.acos(3 * mu / (lam * r))
    return r * math.cos(theta / 3 - 2 * math.pi / 3)


def end(trajectory):
    return 'high' if trajectory.env_at(trajectory.horizon)['s.x'] > CENTRE else 'low'


def test_the_start_threshold_is_the_unstable_equilibrium():
    mu = 0.5
    found = state_threshold(compiled(cusp(mu, LAM)), 'a', 's.x', CENTRE - 1.5, CENTRE + 1.5, end, tol=1e-6)
    assert (found.below, found.above) == ('low', 'high')
    assert found.value == pytest.approx(CENTRE + middle_root(mu), abs=1e-5)


def test_the_input_threshold_is_where_the_start_becomes_the_edge():
    # A run that starts at y0 = -0.5 is on the edge when mu = y0^3 - lam y0.
    y0 = -0.5
    model = compiled(cusp(0.0, LAM, start=CENTRE + y0))
    found = input_threshold(model, 'a', 's.mu', 0.0, 1.9, lambda run: end(run['trajectory']), tol=1e-6)
    assert found.value == pytest.approx(y0**3 - LAM * y0, abs=1e-5)


def test_a_threshold_needs_two_classes_at_its_ends():
    with pytest.raises(ValueError):
        threshold(lambda v: v, lambda v: 'same', 0.0, 1.0, tol=1e-3)
