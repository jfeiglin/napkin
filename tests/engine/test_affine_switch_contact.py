"""A true moving contact, a near miss, and a branch that changes its own driving rate."""

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.comparison_bands import band_samples


def crossing_record(level, mirror, *, delivery_into='delivery', cap='', yes=1, no=0, drive='2.4'):
    source = f"""scenario "Moving crossings"
    horizon 1 h
plant:
    level: L = {level} L
{cap}    target = formula({mirror})
    delivery: L = 0 L
    flow drive: SOURCE -> this.level
        request = {drive} L/h
    flow meter: SOURCE -> this.{delivery_into}
        request = formula({yes} L/h if this.level >= this.target else {no} L/h)
"""
    model = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}}).program
    key = Key('plant', (delivery_into,))
    config = Configuration(Request(1, everything=False, keys=(key,)), numerics=Numerics(max_evaluations=512))
    record = run(model, config)
    return record, lambda: read(record, model, [key], [1])[0].values[0]


@pytest.mark.parametrize('cap', ['', '        inflow.capacity = 40 L/h\n'], ids=['component', 'sparse'])
def test_the_meter_does_not_control_the_departure_of_its_driver(cap):
    record, amount = crossing_record(6, '5.25 L + t * 3.6 L/h', cap=cap)
    assert record.failure is None
    assert amount() == pytest.approx(5 / 8, abs=2e-8, rel=0)


@pytest.mark.parametrize('initial', ['21', '21.000000000000004', '20.999999999999996'])
def test_a_coincident_moving_target_and_a_one_ulp_offset_separate_at_different_times(initial):
    source = f"""scenario "Separating trajectories"
    horizon 1 h
plant:
    level: L = 21 L
        outflow.capacity = 40 L/h
    target = formula({initial} L - t * 0.25 L/h + 0.125 L/h * max(0 h, t - 0.375 h))
    delivery: L = 0 L
    flow drive: this.level -> SINK
        request = 0.25 L/h
    flow meter: SOURCE -> this.delivery
        request = formula(1 L/h if this.level >= this.target else 0 L/h)
"""
    program = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}}).program
    key = Key('plant', ('delivery',))
    config = Configuration(Request(1, keys=(key,), everything=False), numerics=Numerics(max_evaluations=512))
    record = run(program, config)
    assert record.failure is None
    separation = Fraction(3, 8)
    offset = Fraction(initial) - 21
    if offset:
        # After separation the gap grows 1/8 L/h. The larger operand, the target, falls
        # 1/8 L/h. The meter closes when the gap reaches the configured band.
        (factor,) = band_samples(config, 1, multiples=(1,))
        band = Fraction(str(factor))
        target = Fraction(initial) - separation / 4
        separation += (band * target - offset) * 8 / (1 + band)
    actual = read(record, program, [key], [1])[0].values[0]
    assert actual == pytest.approx(float(separation), abs=1e-10, rel=0)


@pytest.mark.parametrize('yes,no,settles', [(0, 2, False), (2, 3, True)])
def test_feedback_must_support_its_own_outgoing_branch(yes, no, settles):
    record, level = crossing_record(1, '1 L + t * 1 L/h', delivery_into='level', drive='0', yes=yes, no=no)
    if settles:
        assert record.failure is None
        assert level() == pytest.approx(3, abs=1e-8)
    else:
        assert record.failure is not None
