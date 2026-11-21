"""A stock's physical balance and its eligibility for bound allocation are distinct."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import use_method
from tests.reference.from_program import run_of, value_at

CONNECTED = ('lines', 'component', 'sparse', 'declared', 'moving_declared')
SINGLE = ('family', *CONNECTED)


@pytest.mark.parametrize('method', CONNECTED)
@pytest.mark.parametrize(
    ('opening', 'contact', 'horizon'),
    [('0.9', '0.5999999999', 1), ('4', '2.6666666666666665', 4)],
    ids=['subhour', 'eight-thirds'],
)
def test_a_drain_through_a_full_store_moves_past_contact_and_keeps_its_crumb(
    method, opening, contact, horizon, monkeypatch
):
    source = f"""scenario "Pass through a full stock"
    horizon {horizon} h
yard:
    a: L = {opening} L in [0, 4 L]
    b: L = 9 L in [0, 9 L]
    flow ab: this.a -> this.b
        request = 1.5 L/h
        capacity = 1.5 L/h
    flow drain: this.b -> SINK
        request = 1.5 L/h
        capacity = 1.5 L/h
    wake = event():
        after {contact} h
        after 0.1 h
yard.wake.start()
"""
    model = use_method(source, method, monkeypatch, 'ab')
    run = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.wake.step[0]'),))
    stopped = run.run()
    assert isinstance(stopped, Checkpoint), stopped
    at = stopped.stop.t
    assert at == float(contact)
    retained = run.stock_balance('yard.a', at)
    # The incoming physical prefix of the two held pipes is exact. Radau may
    # arrive one ULP away, which remains on the books for the rest of the run.
    if horizon == 1:
        assert float(retained) == pytest.approx(1.5e-10, rel=0, abs=2e-15)
    else:
        assert abs(float(retained)) <= 2e-15
    restored = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(stopped)))
    record = run.resume()
    assert restored.resume() == record
    assert record.failure is None and record.end == horizon
    assert run.stock_balance('yard.a', horizon) == retained == restored.stock_balance('yard.a', horizon)
    paths = ['yard.b', 'yard.ab.actual_rate', 'yard.drain.actual_rate']
    pool, inlet, outlet = read(record, model.program, paths, [0.25, at, horizon])
    assert inlet.values == (1.5, 0, 0)
    assert outlet.values == (1.5, 1.5, 1.5)
    assert pool.values == pytest.approx((9, 9, 9 - 1.5 * (horizon - at)), abs=1e-13)


@pytest.mark.parametrize('method', SINGLE)
@pytest.mark.parametrize('upper', [False, True], ids=['lower', 'upper'])
@pytest.mark.parametrize('inside', [False, True], ids=['outside-band', 'inside-band'])
def test_only_the_named_stocks_own_band_can_close_a_single_pipe(method, upper, inside, monkeypatch):
    opening = '0.999' if upper else '0.001'
    ends = 'SOURCE -> this.a' if upper else 'this.a -> SINK'
    source = f"""scenario "Scale and allocation"
    horizon 1 h
yard:
    a: L = {opening} L in [0, 1 L] scale {10000000 if inside else 1} L
    flow pipe: {ends}
        request = 0.00025 L/h
        capacity = 0.00025 L/h
"""
    model = use_method(source, method, monkeypatch, 'pipe')
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None, record.failure
    speed = 0 if inside else 0.00025
    (rate,) = read(record, model.program, ['yard.pipe.actual_rate'], [0, 0.5, 1])
    assert rate.values == pytest.approx((speed,) * 3, abs=1e-15)
    change = (1 if upper else -1) * Fraction(str(speed))
    expected = Fraction(opening) + change
    physical = run.stock_balance('yard.a', 1)
    if inside:
        assert physical == Fraction(opening)
    else:
        assert float(physical) == pytest.approx(float(expected), rel=0, abs=1e-14)
    oracle, error = run_of(model.program, model.configuration)
    assert error is None, error
    assert value_at(oracle, model.program, Key('yard', ('a',)), 1) == expected


@pytest.mark.parametrize('method', CONNECTED)
@pytest.mark.parametrize('cap', [False, True], ids=['soft-request', 'hard-capacity'])
def test_a_lower_bound_can_raise_a_soft_supply_only_as_far_as_its_capacity(method, cap, monkeypatch):
    capacity = '        capacity = 0.1 L/h\n' if cap else ''
    source = f"""scenario "Pass two nearly equal requests"
    horizon 1 h
yard:
    a: L = 0.001 L in [0,] scale 1000000000 L
    flow supply: SOURCE -> this.a
        request = 0.1 L/h
{capacity}    flow use: this.a -> SINK
        request = 0.100000000001 L/h
"""
    model = use_method(source, method, monkeypatch, 'use')
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None, record.failure
    desired = Fraction('0.1' if cap else '0.100000000001')
    paths = ['yard.supply.actual_rate', 'yard.use.actual_rate']
    oracle, error = run_of(model.program, model.configuration)
    assert error is None, error
    for pipe, reading in zip(('supply', 'use'), read(record, model.program, paths, [0.5, 1]), strict=True):
        assert reading.values == pytest.approx((float(desired),) * 2, rel=0, abs=1e-15)
        assert value_at(oracle, model.program, Key('yard', (pipe, 'actual_rate')), 1) == desired
    assert run.stock_balance('yard.a', 1) == Fraction('0.001')


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_a_rate_switch_rechecks_the_new_balance_against_its_bound(method, monkeypatch):
    source = """scenario "A time switch reallocates a nearby floor"
    horizon 1.5 h
yard:
    a: L = 0.4 L in [0,] scale 300000000 L
    flow drain: this.a -> SINK
        request = formula(0.5 L/h if t > 1 h else 0.2 L/h)
        capacity = 0.5 L/h
"""
    model = use_method(source, method, monkeypatch, 'drain')
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None, record.failure
    stock, rate = read(record, model.program, ['yard.a', 'yard.drain.actual_rate'], [0, 1, 1.25, 1.5])
    assert stock.values == pytest.approx((0.4, 0.2, 0.2, 0.2), rel=0, abs=1e-15)
    assert rate.values == pytest.approx((0.2, 0, 0, 0), rel=0, abs=1e-15)


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize(
    ('capacity', 'rates', 'meters'),
    [
        ('0.12 L/h if t > 0.5 h else 0.11 L/h', (0.11, 0.12, 0.12), (0.0275, 0.055, 0.115)),
        ('(0.11 + 0.01 * t/(1 h)) * (1 L/h)', (0.1125, 0.115, 0.12), (0.0278125, 0.05625, 0.115)),
    ],
    ids=['step', 'ramp'],
)
def test_soft_pass_through_obeys_the_actual_capacity_on_each_branch(
    method, capacity, rates, meters, monkeypatch
):
    source = f"""scenario "Increasing pass-through capacity"
    horizon 1 h
yard:
    a: L = 0.001 L in [0,] scale 1000000000 L
    meter: L = 0 L in [0,]
    flow supply: SOURCE -> this.a
        request = 0.1 L/h
        capacity = formula({capacity})
    flow use: this.a -> this.meter
        request = 0.15 L/h
"""
    model = use_method(source, method, monkeypatch, 'use')
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None, record.failure
    stock, meter, inlet, outlet = read(
        record,
        model.program,
        ['yard.a', 'yard.meter', 'yard.supply.actual_rate', 'yard.use.actual_rate'],
        [0.25, 0.5, 1],
    )
    assert stock.values == (0.001,) * 3
    assert meter.values == pytest.approx(meters, abs=1e-14)
    assert inlet.values == pytest.approx(rates, abs=1e-15)
    assert outlet.values == pytest.approx(rates, abs=1e-15)
    assert run.stock_balance('yard.a', 1) == Fraction('0.001')
