"""A raw zero inside a moving comparison band cannot change a followed request."""

from decimal import Decimal
from fractions import Fraction

import pytest

from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.comparison_bands import band_samples
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TOTAL = Key('box', ('total',))
TEN_UNIT_BAND = Decimal(str(band_samples(Configuration(Request(1)), 10, multiples=(1,))[0]))
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
    # The raw gap runs from minus one eighth to three eighths of the initial band.
    origin = 10 - TEN_UNIT_BAND / 8
    speed = Decimal('1.75') + TEN_UNIT_BAND / 2
    condition = f'{origin} L + ({clock}) * {speed} L/h > 10 L + ({clock}) * 1.75 L/h'
    assert total(condition, 1) == 0


def test_a_genuine_curved_departure_from_equality_starts_immediately():
    assert total('10 L + 2 L * (t / 1 h) * (t / 1 h) > 10 L', 1) == 1


@pytest.mark.parametrize('horizon', [1, 2])
def test_curved_motion_leaves_a_band_without_a_raw_zero_at_half_an_hour(horizon):
    # A half-band opening plus two bands times t² reaches one band at half an hour.
    condition = f'{10 - TEN_UNIT_BAND / 2} L - {2 * TEN_UNIT_BAND} L * (t / 1 h) * (t / 1 h) < 10 L'
    assert total(condition, 1, horizon) == Fraction(1, 2)


def test_requesting_a_longer_run_preserves_the_prefix_before_a_real_exit():
    # The clocks begin at equality with nearly equal velocities. As they drain
    # towards zero, the band shrinks far enough to distinguish them after hour 6.
    speed = 1 - TEN_UNIT_BAND / 20
    condition = f'10 h - {speed} * t > 10 h - t'
    assert total(condition, 1, 1) == total(condition, 1, 10) == 0
    assert total(condition, 8, 10) > 0


def test_later_created_key_wins_a_moving_tie_even_after_the_older_raw_key_overtakes_it():
    model = compile_text(
        f"""scenario "Two eligible ranks"
    horizon 1 h
Row:
    input origin = 10 h
    input speed = 1
    input price = 8 L/h
    rank = formula(this.origin + this.speed * t)
older: Row
    origin = {10 - TEN_UNIT_BAND / 20} h
    speed = {1 + TEN_UNIT_BAND / 10}
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


@pytest.mark.parametrize(
    'text',
    [
        # A large stock at its threshold with no first-order motion: y = 1e6 L + t²/2.
        """    stock: L = 1000000 L
    flow fill: SOURCE -> this.stock
        request = formula(t * 1 L/h/h)
    flow tap: SOURCE -> this.other
        request = formula(1 L/h if this.stock > 1000000 L else 0 L/h)
""",
        # Two contacts at once on stocks of very different sizes, both curving from rest.
        """    big: L = 1000000000 L
    small: L = 0.001 L
    flow grow: SOURCE -> this.big
        request = formula(t * 1000 L/h/h)
    flow creep: SOURCE -> this.small
        request = formula(t * 0.000001 L/h/h)
    flow tap: SOURCE -> this.other
        request = formula(1 L/h if this.big > 1000000000 L and this.small > 0.001 L else 0 L/h)
""",
    ],
    ids=['tangency', 'two-scales'],
)
def test_a_curved_departure_from_rest_turns_the_switch_on_at_once(text):
    from napkin.engine import read
    from napkin.engine.timeline import Plan, Run

    model = compile_text(
        'scenario "A curved departure"\n    horizon 1 h\nyard:\n    other: L = 0 L\n' + text, UNITS
    )
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None
    (other,) = read(record, model.program, ['yard.other'], [1])
    assert other.values == pytest.approx((1,))


def test_two_values_that_separate_slowly_from_equality_bypass_the_equal_shortcut(monkeypatch):
    from napkin.engine import read
    from napkin.engine.continuous.integrate import CurvedMotion
    from napkin.engine.timeline import Plan, Run

    # 2a and 2b start equal; a curves up from rest, so the refined trial finds a change of about 2e-16.
    model = compile_text(
        """scenario "Two values that start equal and separate slowly"
    horizon 1 h
yard:
    a: L = 0 L
    b: L = 0 L
    other: L = 0 L
    flow fill: SOURCE -> this.a
        request = formula(t * 1 L/h/h)
    flow tap: SOURCE -> this.other
        request = formula(1 L/h if 2 * this.a > 2 * this.b else 0 L/h)
""",
        UNITS,
    )
    shortcut, change = CurvedMotion.unchanged, CurvedMotion.change
    taken, found = [], []
    monkeypatch.setattr(
        CurvedMotion, 'unchanged', staticmethod(lambda *args: taken.append(shortcut(*args)) or taken[-1])
    )
    monkeypatch.setattr(
        CurvedMotion, 'change', lambda self, *args: found.append(change(self, *args)) or found[-1]
    )
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None
    assert found and all(value > 0 for value in found)
    assert taken and not any(taken)
    (other,) = read(record, model.program, ['yard.other'], [1])
    assert other.values == pytest.approx((1,))
