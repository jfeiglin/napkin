"""A physical switch follows its trajectory on either side of an unrelated empty stage."""

import random
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.program.build import (
    SOURCE,
    Builder,
    after,
    endpoint,
    event,
    flow,
    formula,
    given,
    ifelse,
    local,
    q,
    solve_for,
    solver,
    start,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_clock_moments import HORIZON, TIMES, UNITS, network
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize('way', ['component', 'sparse', 'moving'])
@pytest.mark.parametrize('split', [False, True], ids=['whole', 'empty-stage'])
@pytest.mark.parametrize('rising', [True, False], ids=['quadratic', 'stationary-control'])
def test_an_unconstrained_pump_runs_when_its_initially_stationary_driver_departs(way, split, rising):
    """V'=2t, V(0)=0 gives V=t². Its initial velocity is zero, but for every positive
    time the pump is open and has delivered t litres. Holding the driver at zero keeps it off."""
    b = Builder(UNITS)
    forcing = 2 * t / q(1, 'h') if rising else t * 0 / q(1, 'h')
    plant = b.entity(
        'plant',
        value('driver', 'L', 0, inflow=endpoint(capacity=q(20, 'L/h')) if way == 'sparse' else None),
        value('delivery', 'L', 0),
        flow('fill', SOURCE, this.driver, request=formula(forcing * q(1, 'L/h'))),
        flow(
            'pump',
            SOURCE,
            this.delivery,
            request=formula(ifelse(this.driver > q(0, 'L'), 1, 0) * q(1, 'L/h')),
        ),
    )
    if way == 'moving':
        b.entity(
            'provider',
            solver(
                'share',
                given('fill', plant.fill),
                given('pump', plant.pump),
                solve_for(local.fill.actual_rate),
                solve_for(local.pump.actual_rate),
            ),
        )
    if split:
        other = b.entity('unrelated', event('wait', after(q(Fraction(1, 4), 'h'))))
        b.setup(start(other.wait))
    program, config = b.finish(), Configuration(Request(1))
    machine = Run(Plan.of(program, config))
    record = machine.run()
    assert record.failure is None, record.failure
    connected = machine.ways.sets[machine.ways.set_of['plant.driver']][0]
    assert ('moving' if connected.way == 'declared' and connected.moves else connected.way) == way
    times = [Fraction(1, 2), Fraction(1)]
    keys = [
        Key('plant', steps)
        for steps in [('driver',), ('pump', 'request'), ('pump', 'actual_rate'), ('delivery',)]
    ]
    expected = [[Fraction(1, 4), 1], [1, 1], [1, 1], times] if rising else [[0, 0]] * len(keys)
    if way == 'component':
        oracle, problem = run_of(program, config)
        assert problem is None
        for key, hand in zip(keys, expected):
            assert [value_at(oracle, program, key, at) for at in times] == hand
    for row, key, hand in zip(read(record, program, keys, list(map(float, times))), keys, expected):
        assert row.values == pytest.approx(tuple(map(float, hand)), rel=1e-8, abs=1e-9), key


@pytest.mark.parametrize('start_level', [0, 10])
def test_a_pump_opens_on_departure_through_a_chain_of_initially_stationary_stores(start_level):
    """A=t², B=t³ and C=start+t⁴. For every t>0 the pump delivers 1 L/h,
    including when the first step's increment is too small to add to the starting stock."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('a', 'L', 0),
        value('b', 'L', 0),
        value('c', 'L', start_level),
        value('delivery', 'L', 0),
        flow('fill_a', SOURCE, this.a, request=formula(2 * t / q(1, 'h') * q(1, 'L/h'))),
        flow('fill_b', SOURCE, this.b, request=formula(3 * this.a / q(1, 'h'))),
        flow('fill_c', SOURCE, this.c, request=formula(4 * this.b / q(1, 'h'))),
        flow(
            'pump',
            SOURCE,
            this.delivery,
            request=formula(ifelse(this.c > q(start_level, 'L'), 1, 0) * q(1, 'L/h')),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    level, delivery = read(record, program, ['plant.c', 'plant.delivery'], [0.5, 1])
    assert level.values == pytest.approx((start_level + 1 / 16, start_level + 1), abs=1e-8)
    assert delivery.values == pytest.approx((0.5, 1), abs=1e-8)


@pytest.mark.parametrize('split', [False, True])
def test_a_tangent_condition_does_not_turn_the_pump_off_for_a_segment(split):
    """The level rises at 1 L/h. Its squared distance to 0.5 L touches zero but
    stays positive on both open sides, so the pump delivers 1 L over the hour."""
    b = Builder(UNITS)
    distance = this.driver - q(0.5, 'L')
    plant = b.entity(
        'plant',
        value('driver', 'L', 0),
        value('delivery', 'L', 0),
        flow('fill', SOURCE, this.driver, request=q(1, 'L/h')),
        flow(
            'pump',
            SOURCE,
            this.delivery,
            request=formula(ifelse(distance * distance > q(0, 'L*L'), 1, 0) * q(1, 'L/h')),
        ),
        event('wait', after(q(0.5, 'h'))),
    )
    if split:
        b.setup(start(plant.wait))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    assert read(record, program, ['plant.delivery'], [0.25, 0.75, 1])[0].values == pytest.approx(
        (0.25, 0.75, 1)
    )


@pytest.mark.parametrize(
    'seed', [*range(8), *[pytest.param(k, marks=pytest.mark.deep) for k in range(8, 64)]]
)
def test_an_empty_stage_preserves_the_random_clock_models_outcome_and_readings(seed):
    """The extra event changes only its own history. The existing generator keeps all its draws."""
    moment = Fraction(random.Random(0x822DA + seed).randint(1, 127), 32)
    cfg = Configuration(Request(HORIZON))
    normal, keys, _ = network(seed)
    divided, _, _ = network(seed, empty_time=moment)
    whole, split = run(normal, cfg), run(divided, cfg)
    if whole.failure is None:
        assert split.failure is None, (moment, split.failure)
        times = TIMES
    else:
        assert split.failure is not None
        assert split.failure.t == pytest.approx(whole.failure.t, abs=cfg.numerics.crossing, rel=0)
        assert split.failure.details == whole.failure.details
        times = [at for at in TIMES if float(at) < min(split.end, whole.end)]
    for baseline, transformed in zip(read(whole, normal, keys, times), read(split, divided, keys, times)):
        assert transformed.values == pytest.approx(baseline.values, rel=1e-7, abs=1e-7), (
            moment,
            baseline.key,
        )
