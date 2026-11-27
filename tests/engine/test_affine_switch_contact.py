"""A true moving contact, a near miss, and a branch that changes its own driving rate."""

from dataclasses import replace
from fractions import Fraction
from math import sqrt

import pytest

from napkin.core import expr as nodes
from napkin.engine import read, run
from napkin.engine.continuous import integrate
from napkin.engine.continuous.integrate import consistent_departure
from napkin.engine.errors import SimulationError
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.comparison_bands import band_samples
from tests.engine.test_threshold_transfer_placement import use_method


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


def feedback_record(target, request, method, monkeypatch, rtol):
    text = f"""scenario "Moving feedback"
    horizon 1 h
yard:
    level: L = 1 L
    target = formula({target})
    flow fill: SOURCE -> this.level
        request = formula({request})
"""
    model = use_method(text, method, monkeypatch, 'fill')
    config = replace(
        model.configuration, numerics=Numerics(rtol=rtol, atol_factor=rtol / 10, max_evaluations=512)
    )
    record = run(model.program, config)
    return record, lambda: read(record, model.program, ['yard.level'], [1])[0].values[0]


@pytest.mark.parametrize('rtol', [1e-9, 1e-7])
@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize('yes,no,end', [(0, 2, None), (2, 3, 3), (1, 3, 2)])
def test_feedback_must_support_its_own_outgoing_branch(yes, no, end, method, monkeypatch, rtol):
    request = f'{yes} L/h if this.level >= this.target else {no} L/h'
    record, level = feedback_record('1 L + t * 1 L/h', request, method, monkeypatch, rtol)
    if end is not None:
        assert record.failure is None
        assert level() == pytest.approx(end, abs=1e-8)
    else:
        assert record.failure is not None and record.failure.t == 0
        # Every method gives the same reason; Sparse adds its advice about chattering after it.
        reason = integrate.stopped(0, integrate.reversal_reason('yard.level against yard.target'))
        assert record.failure.detail('message').startswith(reason)


@pytest.mark.parametrize('rtol', [1e-9, 1e-7])
@pytest.mark.parametrize('enabled', [False, True])
def test_curved_departure_checks_the_complete_condition_on_its_own_field(enabled, monkeypatch, rtol):
    # The target has initial slope 1 L/h. The nested max follows the target;
    # the clock term can mask the feedback for the whole run.
    condition = 'this.level >= max(this.target, 0 L) and t < ' + ('2 h' if enabled else '0 h')
    record, level = feedback_record(
        '1 L * exp(t / 1 h)',
        f'0 L/h if {condition} else 2 L/h',
        'sparse',
        monkeypatch,
        rtol,
    )
    if enabled:
        assert record.failure is not None and record.failure.t == 0
        assert 'yard.target' in record.failure.detail('message')
    else:
        assert record.failure is None
        assert level() == pytest.approx(3)


@pytest.mark.parametrize('rtol', [1e-9, 1e-7])
def test_initially_tangent_feedback_rechecks_equality_after_the_band_exit(monkeypatch, rtol):
    record, _ = feedback_record(
        '1 L + (t / 1 h) ** 2 * 1 L',
        '(0 L/h if this.level >= this.target else 4 L/h) * (t / 1 h)',
        'sparse',
        monkeypatch,
        rtol,
    )
    # While equality holds the stock stays at 1. The target first leaves the
    # band at u² = rtol/(1-rtol). The other arm then gives stock = 1+2(t²-u²).
    # It meets the target again at sqrt(2)*u, with inward rates on both sides.
    assert record.failure is not None and 'chattering' in record.failure.detail('message')
    assert record.failure.t == pytest.approx(sqrt(2 * rtol / (1 - rtol)), abs=Numerics.crossing, rel=0)


@pytest.mark.parametrize('rtol', [1e-9, 1e-7])
@pytest.mark.parametrize(
    'at_equality,above,net',
    [(4, 1, 0), (4, 1.125, 0.125), (4, 0, None), (1, 2, 0)],
    ids=['stationary', 'still-rising', 'reversed', 'no-departure'],
)
def test_a_stock_already_beyond_the_probe_checks_the_rate_of_its_occupied_side(rtol, at_equality, above, net):
    # At hour 1 the stock is two floats above 1 L, still inside the comparison
    # band. A positive net at equality locates the departure. Its open field
    # may hold or continue. When equality itself holds, the offset opens nothing.
    source = f"""scenario "A stock just above its switch"
    horizon 2 h
yard:
    stock: L = 1.0000000000000004 L
    flow fill: SOURCE -> this.stock
        request = formula(0 L/h if t < 1 h else ({above} L/h if this.stock > 1 L else {at_equality} L/h))
    flow drain: this.stock -> SINK
        request = formula(0 L/h if t < 1 h else 1 L/h)
"""
    model = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}})
    config = replace(model.configuration, numerics=Numerics(rtol=rtol, atol_factor=rtol / 10))
    record = run(model.program, config)
    if net is None:
        assert record.failure is not None and record.failure.t == 1
        assert 'yard.stock' in record.failure.detail('message')
    else:
        assert record.failure is None and record.end == 2
        start, end = read(record, model.program, ['yard.stock'], [0, 2])[0].values
        assert end == pytest.approx(start + net, abs=1e-14, rel=0)


def test_one_reversing_field_with_many_independent_coincident_surfaces():
    pairs = tuple((nodes.ref(f'stock{k}'), nodes.ref(f'target{k}')) for k in range(30))
    tested = []

    def motion(sides):
        tested.append(sides)
        return (1 if sides[0] < 0 else -1, *sides[1:])

    def refuses(reason):
        raise ValueError(reason)

    with pytest.raises(SimulationError, match=r'cannot resolve .*stock0 against target0$'):
        consistent_departure(pairs, (1,) * len(pairs), motion, refuses, 0)
    assert len(tested) == 3


def test_joint_departure_checks_both_surfaces_on_the_same_field():
    pairs = ((nodes.ref('a'), nodes.ref('x')), (nodes.ref('b'), nodes.ref('y')))
    installed = []

    def motion(sides):
        installed.append(sides)
        a, b = sides
        # Simultaneous proposals alternate between two unsuitable fields.
        # Opposite signs on the two comparisons give a consistent joint field.
        return (1 if b < 0 else -1, 1 if a < 0 else -1)

    consistent_departure(pairs, (1, 1), motion, pytest.fail, 0)
    a, b = installed[-1]
    assert a == -b and a != 0


def test_unreadable_candidate_cannot_confirm_or_disprove_the_departure():
    pair = (nodes.ref('stock'), nodes.ref('target'))
    with pytest.raises(SimulationError, match='cannot resolve the departing comparisons'):
        consistent_departure(
            (pair,), (1,), lambda sides: {(1,): (-1,), (-1,): (1,), (0,): (None,)}[sides], pytest.fail, 0
        )
