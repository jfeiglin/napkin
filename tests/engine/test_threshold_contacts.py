"""Actual crossings of an inclusive threshold. All expected inventories follow from the flows."""

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from napkin.engine.timeline import Plan, Run, read, resume, run
from napkin.model.compile import load_scenario
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    after,
    assign,
    call,
    endpoint,
    event,
    flow,
    formula,
    ifelse,
    named,
    q,
    reset_when,
    start,
    this,
    value,
    when,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, InputValue, Numerics, Quantity, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

DRAFT = Path(__file__).resolve().parents[2] / 'scratch/rewrite/a5/translated/now/examples/reservoir/model.scn'
UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


def observed(record, program, path, times):
    return read(record, program, [path], times)[0].values


@pytest.mark.parametrize('step', [1.0, 0.15])
def test_reservoir_counts_80_hours_at_its_reused_threshold(step):
    model = load_scenario(DRAFT)
    configuration = replace(
        model.configuration,
        inputs=(
            InputValue('reservoir', 'risk', Quantity(0.7, 'fraction')),
            InputValue('reservoir', 'spillway', Quantity(0.06, 'fraction/day')),
        ),
        numerics=Numerics(max_step=step),
    )
    record = run(model.program, configuration)
    assert record.failure is None
    (fire,) = record.entries('fire', 'operator.decide.when[0]')
    assert fire.t == pytest.approx(40, abs=1e-8, rel=0)
    (contact,) = record.entries('contact', 'reservoir.at_risk')
    assert contact.t == fire.t and contact.detail('near')
    assert observed(record, model.program, 'reservoir.risk_time', [120]) == pytest.approx([80], abs=1e-7)
    assert observed(record, model.program, 'reservoir.water', [41, 120]) == (0.7, 0.7)


def fast_tank(factor, switched=False):
    """Water rises from 0.6 L at k/400 L per hour until 0.7 L, then holds."""
    b = Builder(UNITS)
    limit = q(1.4, 'L')
    speed = q(factor / 400, 'L/h')
    filling = (this.twice < limit) if switched else this.filling
    b.entity(
        'tank',
        value('water', 'L', 0.6, lower=0),
        value('twice', 'L', formula(2 * this.water)),
        value('filling', BOOL, True),
        value('exposed', 'h', 0, lower=0),
        flow('rain', SOURCE, this.water, request=formula(ifelse(filling, speed, q(0, 'L/h')))),
        flow('risk', SOURCE, this.exposed, request=formula(ifelse(this.water >= q(0.7, 'L'), 1, 0))),
        *(
            ()
            if switched
            else (
                event(
                    'close',
                    when(this.twice >= limit, start(this.close), reset=reset_when(False)),
                    after(q(0, 'h'), assign(this.filling, False)),
                ),
            )
        ),
    )
    return b.finish()


@pytest.mark.parametrize('factor', [100, 10_000])
@pytest.mark.parametrize('switched', [False, True], ids=['trigger', 'switch'])
@pytest.mark.parametrize('horizon', [120, pytest.param(8760, marks=pytest.mark.deep)])
def test_fast_reservoir_stays_exactly_on_the_crossed_threshold(factor, switched, horizon):
    program = fast_tank(factor, switched)
    entered = 40 / factor
    configuration = Configuration(Request(horizon), numerics=Numerics(max_step=horizon))
    record = run(program, configuration)
    assert record.failure is None
    assert observed(record, program, 'tank.water', [1, horizon]) == (0.7, 0.7)
    oracle, failure = run_of(program, configuration)
    assert failure is None
    assert value_at(oracle, program, Key('tank', ('water',)), horizon) == Fraction(7, 10)
    assert value_at(oracle, program, Key('tank', ('exposed',)), horizon) == horizon - Fraction(40, factor)
    assert observed(record, program, 'tank.exposed', [1, horizon]) == pytest.approx(
        [1 - entered, horizon - entered], abs=1e-7, rel=0
    )


def test_a_checkpoint_keeps_the_exact_threshold_of_an_invertible_formula():
    program = fast_tank(10_000)
    configuration = Configuration(Request(120))
    model = Run(Plan.of(program, configuration), (Breakpoint('tank.close.step[0]'),))
    checkpoint = model.run()
    assert isinstance(checkpoint, Checkpoint)
    for record in (model.resume(), resume(program, loads(dumps(checkpoint)))):
        assert record.failure is None
        assert observed(record, program, 'tank.water', [1, 120]) == (0.7, 0.7)
        assert observed(record, program, 'tank.exposed', [120]) == pytest.approx([119.996], abs=1e-7)


def sum_model(speed, tick=None):
    b = Builder(UNITS)
    b.entity(
        'pair',
        value('a', 'L', 1, lower=0),
        value('b', 'L', 0, lower=0),
        value('arrival', 'L', 0),
        flow('first', SOURCE, this.a, request=q(speed, 'L/h')),
        flow('second', SOURCE, this.b, request=q(2 * speed, 'L/h')),
        event(
            'mark',
            when(this.a + this.b >= q(10, 'L'), start(this.mark), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.arrival, this.a + this.b)),
        ),
        event('tick', after(q(1 if tick is None else tick, 'h'))),
    )
    if tick is not None:
        b.setup(start(named('pair').tick))
    return b.finish()


@pytest.mark.parametrize('speed', [1, 200_000])
def test_a_multistore_contact_preserves_both_inventories(speed):
    program = sum_model(speed)
    at = 3 / speed
    record = run(program, Configuration(Request(2 * at)))
    assert record.failure is None
    (entry,) = record.entries('fire')
    assert entry.t == pytest.approx(at, abs=1e-12)
    assert observed(record, program, 'pair.a', [entry.t, 2 * at]) == pytest.approx([4, 7], abs=1e-12)
    assert observed(record, program, 'pair.b', [entry.t, 2 * at]) == pytest.approx([6, 12], abs=1e-12)
    assert observed(record, program, 'pair.arrival', [2 * at]) == pytest.approx([10], abs=1e-8)
    oracle, failure = run_of(program, Configuration(Request(2 * at)))
    assert failure is None
    assert value_at(oracle, program, Key('pair', ('a',)), Fraction(3, speed)) == 4
    assert value_at(oracle, program, Key('pair', ('b',)), Fraction(3, speed)) == 6


def test_a_fast_multistore_contact_fires_at_its_own_time_before_the_clock():
    # By the tick, the sum would have risen another 0.003 L. Both inventories
    # therefore reach the threshold at its own crossing, before the scheduled stage.
    speed = 200_000
    at = Fraction(3, speed)
    program = sum_model(speed, at + Fraction(5, 10**9))
    config = Configuration(Request(float(2 * at)))
    record = run(program, config)
    assert record.failure is None
    (fire,) = record.entries('fire')
    assert fire.t == pytest.approx(float(at), abs=1e-13, rel=0)
    assert observed(record, program, 'pair.arrival', [float(2 * at)]) == pytest.approx([10])
    oracle, failure = run_of(program, config)
    assert failure is None
    assert value_at(oracle, program, Key('pair', ('arrival',)), 2 * at) == 10


@pytest.mark.parametrize('upper', [1, 1_000_000_000])
def test_a_slow_fill_releases_its_empty_store_independently_of_its_upper_bound(upper):
    # The empty tank leaves its lower bound immediately. The observer integrates 0.02 t L/h.
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 0, lower=0, upper=upper, inflow=endpoint(capacity=q(1, 'L/h'))),
        value('observed', 'L', 0, lower=0),
        flow('rain', SOURCE, this.water, request=q(0.02, 'L/h')),
        flow('measure', SOURCE, this.observed, request=formula(this.water / q(1, 'h'))),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    assert observed(record, program, 'tank.water', [1]) == pytest.approx([0.02])
    assert observed(record, program, 'tank.observed', [1]) == pytest.approx([0.01])


def test_grouping_a_multistore_contact_inside_its_band_keeps_each_inventory():
    # At this moment, one nanosecond after the raw contact, 3e-9 L has entered.
    at = Fraction(3) + Fraction(1, 10**9)
    program = sum_model(1, at)
    configuration = Configuration(Request(4))
    engine = run(program, configuration)
    assert engine.failure is None
    assert engine.entries('fire')[0].t == float(at)
    oracle, failure = run_of(program, configuration)
    assert failure is None
    for name, expected in (('a', 1 + at), ('b', 2 * at), ('arrival', 1 + 3 * at)):
        path = 'pair.' + name
        assert observed(engine, program, path, [float(at)]) == pytest.approx(
            [float(expected)], abs=1e-13, rel=0
        )
        assert value_at(oracle, program, Key('pair', (name,)), at) == expected


def test_an_invertible_single_store_switch_places_its_store_on_the_threshold():
    # A tank on the positive branch of water squared stops filling at 0.7 L,
    # so its later clock reads exactly that inverse level.
    at = Fraction(1, 250) + Fraction(5, 10**9)
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 0.6, lower=0),
        value('seen', 'L', 0),
        flow(
            'rain',
            SOURCE,
            this.water,
            request=formula(ifelse(this.water * this.water < q(0.49, 'L*L'), q(25, 'L/h'), q(0, 'L/h'))),
        ),
        event('look', after(q(at, 'h'), assign(this.seen, this.water))),
    )
    b.setup(start(named('tank').look))
    program = b.finish()
    configuration = Configuration(Request(1))
    engine = run(program, configuration)
    assert engine.failure is None
    assert observed(engine, program, 'tank.seen', [1]) == (0.7,)
    assert observed(engine, program, 'tank.water', [1]) == (0.7,)
    oracle, failure = run_of(program, configuration)
    assert failure is None
    assert value_at(oracle, program, Key('tank', ('seen',)), Fraction(1)) == Fraction(7, 10)


def test_a_threshold_before_a_different_stock_bound_has_its_own_moment():
    # The tank reaches 0.99 L at 9.9e-8 h and its 1 L bound at the 1e-7 h clock.
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 0, lower=0, upper=1),
        flow('rain', SOURCE, this.water, request=q(10_000_000, 'L/h')),
        event(
            'mark',
            when(this.water >= q(0.99, 'L'), start(this.mark), reset=reset_when(False)),
            after(q(0, 'h')),
        ),
        event('tick', after(q(1e-7, 'h'))),
    )
    b.setup(start(named('tank').tick))
    program = b.finish()
    configuration = Configuration(Request(2e-7))
    record = run(program, configuration)
    assert record.failure is None
    (fire,) = record.entries('fire')
    assert fire.t == pytest.approx(9.9e-8, abs=1e-14, rel=0)
    assert observed(record, program, 'tank.water', [1e-7, 2e-7]) == pytest.approx([1, 1], rel=0, abs=1e-12)
    oracle, failure = run_of(program, configuration)
    assert failure is None
    assert value_at(oracle, program, Key('tank', ('water',)), Fraction(1, 10**7)) == 1


@pytest.mark.parametrize('function', ['abs', 'min', 'max', 'clip'])
def test_a_piecewise_arithmetic_rate_switches_before_a_clock_outside_the_stock_band(function):
    at = Fraction(1, 250) + Fraction(5, 10**9)
    limit = q(0.7, 'L')
    args = {
        'abs': (this.water - limit,),
        'min': (this.water, limit),
        'max': (this.water, limit),
        'clip': (this.water, limit, q(10, 'L')),
    }[function]
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 0.6, lower=0),
        value('seen', 'L', 0),
        value('total', 'L', 0, lower=0),
        flow('rain', SOURCE, this.water, request=q(25, 'L/h')),
        flow('reading', SOURCE, this.total, request=formula(call(function, *args) / q(1, 'h'))),
        event('look', after(q(at, 'h'), assign(this.seen, this.water))),
    )
    b.setup(start(named('tank').look))
    program = b.finish()
    configuration = Configuration(Request(0.008))
    engine = run(program, configuration)
    assert engine.failure is None
    expected = Fraction(3, 5) + 25 * at
    assert observed(engine, program, 'tank.seen', [0.008]) == pytest.approx(
        [float(expected)], abs=1e-12, rel=0
    )
    oracle, failure = run_of(program, configuration)
    assert failure is None
    assert value_at(oracle, program, Key('tank', ('seen',)), Fraction(1, 125)) == expected
