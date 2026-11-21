"""Thresholds between the ends of real runs (napkin/dynamics/basins.py).

A tank that drains at k x from x0 holds x0 exp(-k T) at the horizon T, so a run ends below half of
its start when k > ln 2 / T, and above 5 people when x0 > 5 exp(k T). The record holds a value within
its tolerance, 1e-10 of its size, so each threshold is the closed form within 1e-8.

The cusp x' = mu + 3 y - y^3 with y = x - c has two stable equilibria for |mu| < 2 and an unstable one
between them: the edge of their basins. The edge is the middle root of y^3 - 3 y - mu = 0, which the
trigonometric formula gives, so a run that starts below it ends low and one that starts above ends high.
Near the edge a run leaves it at the rate of its unstable eigenvalue, 3 - 3 y^2 per hour (about 3 at the
edges below): from 1e-6 of the edge in about 5 h, so a horizon of 20 h classifies every run.
"""

from __future__ import annotations

import math

import pytest

from napkin.dynamics import configured, input_threshold, state_threshold, threshold
from napkin.engine import read, run
from tests.dynamics.models import CENTRE, cusp, drain, fold

LAM = 3.0
HORIZON = 20


def middle_root(mu, lam=LAM):
    """The middle root of y^3 - lam y - mu = 0 (three real roots when |mu| < 2 (lam / 3)^(3/2))."""
    r = 2 * math.sqrt(lam / 3)
    theta = math.acos(3 * mu / (lam * r))
    return r * math.cos(theta / 3 - 2 * math.pi / 3)


def end(program, horizon, level=CENTRE):
    """The class of a run's end: whether the level ends above `level`."""

    def classify(record):
        (reading,) = read(record, program, ['tank.x'], [horizon])
        return 'high' if reading.values[0] > level else 'low'

    return classify


def test_the_input_threshold_of_a_drain_is_its_closed_form():
    program, configuration = drain(0.1, start=10.0, horizon=10)
    found = input_threshold(program, configuration, 'tank.k', 0.01, 0.5, end(program, 10, 5.0), tol=1e-9)
    assert (found.below, found.above) == ('high', 'low')
    assert found.value == pytest.approx(math.log(2) / 10, abs=1e-8)


def test_the_start_threshold_of_a_drain_is_its_closed_form():
    program, configuration = drain(0.1, start=10.0, horizon=10)
    found = state_threshold(program, configuration, 'tank.x', 5.0, 20.0, end(program, 10, 5.0), tol=1e-9)
    assert (found.below, found.above) == ('low', 'high')
    assert found.value == pytest.approx(5 * math.exp(0.1 * 10), abs=1e-8)


@pytest.mark.deep
def test_the_start_threshold_is_the_unstable_equilibrium():
    mu = 0.5
    program, configuration = cusp(mu, LAM, horizon=HORIZON)
    found = state_threshold(
        program, configuration, 'tank.x', CENTRE - 1.5, CENTRE + 1.5, end(program, HORIZON), tol=1e-6
    )
    assert (found.below, found.above) == ('low', 'high')
    assert found.value == pytest.approx(CENTRE + middle_root(mu), abs=1e-5)


@pytest.mark.deep
def test_the_input_threshold_is_where_the_start_becomes_the_edge():
    # A run that starts at y0 = -0.5 is on the edge when mu = y0^3 - lam y0.
    y0 = -0.5
    program, configuration = cusp(0.0, LAM, start=CENTRE + y0, horizon=HORIZON)
    found = input_threshold(program, configuration, 'tank.mu', 0.0, 1.9, end(program, HORIZON), tol=1e-6)
    assert found.value == pytest.approx(y0**3 - LAM * y0, abs=1e-5)


def test_a_threshold_needs_two_classes_at_its_ends():
    with pytest.raises(ValueError):
        threshold(lambda v: v, lambda v: 'same', 0.0, 1.0, tol=1e-3)


def test_the_fold_at_its_empty_bound_serves_the_soft_outlet_from_the_inlet():
    program, configuration = fold(-5.0, horizon=10)
    record = run(program, configuration)
    assert record.failure is None and record.end == 10
    # From y = 1, y' = -5 - y² reaches y = -10 (zero stock) before 1 h.
    # The outlet then requests 500 people/h. The uncapped inlet can serve it.
    stock, requested, inlet, outlet = read(
        record,
        program,
        ['tank.x', 'tank.change_in.request', 'tank.change_in.actual_rate', 'tank.change_out.actual_rate'],
        [1, 10],
    )
    assert stock.values == (0, 0)
    assert requested.values == (395, 395)
    assert inlet.values == outlet.values == (500, 500)


def test_a_run_that_fails_stops_the_search():
    program, configuration = fold(1.0, horizon=10)
    # At mu = -5 the inlet requests 95 - y². It becomes negative while the stock
    # still holds people, before the empty bound can constrain allocation.
    configuration = configured(program, configuration, {'tank.offset': 100})
    with pytest.raises(ValueError, match=r'tank\.mu = -5\.0 fails: Negative flow rates:.*tank\.change_in'):
        input_threshold(program, configuration, 'tank.mu', -5.0, 1.0, end(program, 10), tol=1e-3)
