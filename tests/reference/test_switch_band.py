"""A raw zero inside a moving comparison band cannot change a followed request."""

from fractions import Fraction

import pytest

from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TOTAL = Key('box', ('total',))
MODEL = """scenario "An in-band clock crossing"
    horizon {horizon} h
box:
    total: L = 0 L
    flow add: SOURCE -> this.total
        request = formula(1 L/h if {condition} else 0 L/h)
"""


def total(condition, at, horizon=1):
    model = compile_text(MODEL.format(condition=condition, horizon=horizon), UNITS)
    run, failure = run_of(model.program, model.configuration)
    assert failure is None, failure
    return value_at(run, model.program, TOTAL, at)


@pytest.mark.parametrize('clock', ['t', 't * (t / 1 h)'])
def test_the_clocks_can_swap_raw_order_while_the_strict_comparison_stays_false(clock):
    # The audited linear model previously delivered 3/4 L. Its gap is between
    # -1.25e-9 and 3.75e-9 L, inside the band throughout the hour. The quadratic
    # spelling reaches exactly the same maximum gap after crossing zero at 1/2 h.
    condition = f'9.99999999875 L + ({clock}) * 1.750000005 L/h > 10 L + ({clock}) * 1.75 L/h'
    assert total(condition, 1) == 0


def test_a_genuine_curved_departure_from_equality_starts_immediately():
    assert total('10 L + 2 L * (t / 1 h) * (t / 1 h) > 10 L', 1) == 1


@pytest.mark.parametrize('horizon', [1, 2])
def test_curved_motion_leaves_a_band_without_a_raw_zero_at_half_an_hour(horizon):
    # The larger operand remains 10 L and its band is exactly 1e-8 L.
    condition = '9.999999995 L - 0.00000002 L * (t / 1 h) * (t / 1 h) < 10 L'
    assert total(condition, 1, horizon) == Fraction(1, 2)


def test_requesting_a_longer_run_preserves_the_prefix_before_a_real_exit():
    # The clocks begin at equality with nearly equal velocities. As they drain
    # towards zero, the band shrinks far enough to distinguish them after hour 6.
    condition = '10 h - 0.9999999995 * t > 10 h - t'
    assert total(condition, 1, 1) == total(condition, 1, 10) == 0
    assert total(condition, 8, 10) > 0


def test_later_created_key_wins_a_moving_tie_even_after_the_older_raw_key_overtakes_it():
    model = compile_text(
        """scenario "Two eligible ranks"
    horizon 1 h
Row:
    input origin = 10 h
    input speed = 1
    input price = 8 L/h
    rank = formula(this.origin + this.speed * t)
older: Row
    origin = 9.9999999995 h
    speed = 1.000000001
    price = 5 L/h
later: Row
box:
    total: L = 0 L
    flow add: SOURCE -> this.total
        request = formula(Row.instances.by(rank).at(20 h).price)
""",
        UNITS,
    )
    run, failure = run_of(model.program, model.configuration)
    assert failure is None, failure
    assert value_at(run, model.program, TOTAL, 1) == 8
