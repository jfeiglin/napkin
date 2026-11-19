"""The record of a run of a program (`napkin.engine.run`) and its reader (`napkin.engine.read`).

Each expected value is a closed form worked by hand: the median of a distribution, a line, an
exponential, the time at which a line crosses a value. Programs are built in Python; none is
parsed.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Outside
from napkin.engine.timeline.record import key_of, unit_of
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    after,
    assertion,
    assign,
    draw,
    elapsed,
    event,
    flow,
    formula,
    input_,
    legs,
    named,
    q,
    this,
    triangular,
    uniform,
    value,
)
from napkin.program.config import (
    SAMPLED,
    Configuration,
    ConfigurationError,
    InputValue,
    Quantity,
    Request,
)
from napkin.program.record import Curve, History, Key, Piece

UNITS = {
    'h': {'time': 1},
    'L': {'volume': 1},
    'Wh': {'energy': 1},
    'W': {'energy': 1, 'time': -1},
    'kW': ({'energy': 1, 'time': -1}, 1000),
}


def tank(*parts, water=8, lower=0, request=None, capacity=None, links=None):
    """A tank of `water` L that a clinic draws on at `request` (3 L/h unless given); `links` are the
    tank's own."""
    request = q(3, 'L/h') if request is None else request
    b = Builder(UNITS)
    b.entity('tank', value('water', 'L', water, lower=lower, upper=20), *parts, **(links or {}))
    b.entity('clinic', flow('delivery', named('tank').water, SINK, request=request, capacity=capacity))
    return b


def configured(horizon, **settings):
    return Configuration(Request(horizon), **settings)


def at(record, program, path, *times):
    (reading,) = read(record, program, [path], list(times))
    return reading.values


# ---- inputs and draws ---------------------------------------------------------------------------------


def machine(default, **options):
    """A machine's repair time; the root's spare water puts litres in the program's units."""
    b = Builder(UNITS)
    b.entity('machine', input_('repair_time', 'h', default, lower=1, upper=12, **options))
    b.root(value('spare', 'L', 1))
    return b.finish()


def test_a_median_run_draws_the_median_of_an_input_s_default_and_traces_the_draw():
    """The median of triangular(1, 2, 4): F(2) = 1/3 < 1/2, so it is on the right side, where
    1 - F(x) = (4 - x)^2 / 6: x = 4 - sqrt(3)."""
    program = machine(draw(triangular(1, 2, 4, 'h')))
    record = run(program, configured(1))
    assert at(record, program, 'machine.repair_time', 0, 1) == pytest.approx([4 - math.sqrt(3)] * 2)
    (entry,) = record.entries('draw')
    assert (entry.t, entry.round, entry.owner) == (0, 0, 'machine')
    assert entry.part == 'machine.repair_time.draw[0]'
    assert entry.detail('value') == pytest.approx(4 - math.sqrt(3))


def test_a_sampled_draw_is_keyed_by_its_seed_and_lies_in_its_support():
    program = machine(draw(uniform(1, 3, 'h')))
    found = {
        seed: at(run(program, configured(0, mode=SAMPLED, seed=seed)), program, 'machine.repair_time', 0)[0]
        for seed in (1, 2)
    }
    assert all(1 <= number <= 3 for number in found.values())
    assert found[1] != found[2]
    again = run(program, configured(0, mode=SAMPLED, seed=1))
    assert at(again, program, 'machine.repair_time', 0)[0] == found[1]


def test_an_input_that_the_configuration_sets_skips_its_draw_and_converts_its_unit():
    """5 h within [1 h, 12 h] (D2); the configuration may write it in another unit of time."""
    b = Builder({**UNITS, 'min': ({'time': 1}, '1/60')})
    b.entity('machine', input_('repair_time', 'h', draw(uniform(1, 3, 'h')), lower=1, upper=12))
    b.root(value('pause', 'min', 30))
    program = b.finish()
    given = (InputValue('machine', 'repair_time', Quantity(300, 'min')),)
    record = run(program, configured(0, inputs=given))
    assert at(record, program, 'machine.repair_time', 0) == pytest.approx([5])
    assert record.entries('draw') == ()


@pytest.mark.parametrize(
    'given, message',
    [
        (InputValue('machine', 'repair_time', Quantity(13, 'h')), 'outside its admitted range'),
        (InputValue('machine', 'repair_time', Quantity(2, 'L')), 'does not convert'),
        (InputValue('machine', 'repair_time', True), 'takes a quantity'),
        (InputValue('machine', 'speed', Quantity(2, 'h')), 'no input'),
        (InputValue('machine', 'repair_time', Quantity(2, 'min')), 'not in the program'),
    ],
)
def test_a_configuration_that_the_program_cannot_take_is_refused(given, message):
    with pytest.raises(ConfigurationError, match=message):
        run(machine(q(2, 'h')), configured(0, inputs=(given,)))


# ---- stores, flows and formulas -----------------------------------------------------------------------


def test_a_formula_and_a_switch_of_a_yes_or_no_between_moments():
    """8 L drained at 3 L/h: `half` is water / 2 h, a line; `low` turns true where 8 - 3 t = 5, at
    t = 1, between the moments of the run (the tank empties at 8/3 h)."""
    b = tank(
        value('half', 'L/h', formula(this.water / q(2, 'h'))),
        value('low', BOOL, formula(this.water <= q(5, 'L'))),
    )
    program = b.finish()
    record = run(program, configured(3))
    assert at(record, program, 'tank.half', 0, 0.5, 2) == pytest.approx([4, 3.25, 1])
    assert at(record, program, 'tank.low', 0, 1 - 1e-6, 1 + 1e-6, 3) == (False, False, True, True)
    (switch,) = [piece.t for piece in record.history(Key('tank', ('low',))).pieces if piece.t > 0]
    assert switch == pytest.approx(1, abs=1e-8)


def test_a_drain_in_proportion_follows_its_exponential_through_curved_pieces():
    """A tank of 8 L that drains at water / 2 h: water = 8 exp(-t / 2) and the rate is half of it."""
    program = tank(request=formula(named('tank').water / q(2, 'h'))).finish()
    record = run(program, configured(4))
    times = (0.3, 1.7, 2.25, 4)
    assert at(record, program, 'tank.water', *times) == pytest.approx(
        [8 * math.exp(-t / 2) for t in times], rel=1e-9
    )
    assert at(record, program, 'clinic.delivery.actual_rate', *times) == pytest.approx(
        [4 * math.exp(-t / 2) for t in times], rel=1e-9
    )
    assert any(isinstance(piece.curve, Curve) for piece in record.history(Key('tank', ('water',))).pieces)


def test_a_capacity_holds_the_rate_until_the_request_falls_below_it():
    """Requested water / 1 h with a capacity of 2 L/h: 2 L/h until the tank holds 2 L at 3 h, then
    the request: water = 2 exp(-(t - 3)). The segment ends at the switch of `min`."""
    program = tank(request=formula(named('tank').water / q(1, 'h')), capacity=q(2, 'L/h')).finish()
    record = run(program, configured(5))
    assert at(record, program, 'tank.water', 1.5, 3, 4) == pytest.approx([5, 2, 2 * math.exp(-1)], rel=1e-9)
    assert at(record, program, 'clinic.delivery.actual_rate', 1, 4.5) == pytest.approx(
        [2, 2 * math.exp(-1.5)], rel=1e-9
    )
    assert at(record, program, 'clinic.delivery.capacity', 4) == pytest.approx([2])
    times = [piece.t for piece in record.history(Key('tank', ('water',))).pieces]
    assert min(abs(t - 3) for t in times) < 1e-9


def test_a_store_that_no_flow_touches_holds_its_start_and_the_record_keeps_what_is_asked():
    b = tank(value('spare', 'L', 4))
    program = b.finish()
    keys = (Key('tank', ('spare',)), Key('clinic', ('delivery', 'actual_rate')))
    record = run(program, Configuration(Request(3, everything=False, keys=keys)))
    assert {history.key for history in record.histories} == set(keys)
    assert record.history(keys[0]).pieces == (Piece(0.0, 4.0, 0.0),)
    with pytest.raises(KeyError):
        record.history(Key('tank', ('water',)))


# ---- the reader ---------------------------------------------------------------------------------------


def test_the_reader_names_each_path_by_its_member_and_gives_its_declared_unit():
    b = Builder(UNITS)
    b.entity('panel', value('stored', 'Wh', 2000), flow('feed', SOURCE, this.stored, request=q(1, 'kW')))
    b.root(value('peak', 'kW', 3))
    program = b.finish()
    record = run(program, configured(2))
    assert key_of(program, 'panel.feed.actual_rate') == Key('panel', ('feed', 'actual_rate'))
    assert key_of(program, 'peak') == Key('', ('peak',))
    assert unit_of(program, Key('panel', ('feed', 'request'))) == ('kW', 1000.0)
    feed, peak, stored = read(record, program, ['panel.feed.actual_rate', 'peak', 'panel.stored'], [0, 2])
    assert (feed.unit, feed.values) == ('kW', pytest.approx((1, 1)))
    assert (peak.unit, peak.values) == ('kW', pytest.approx((3, 3)))
    assert stored.values == pytest.approx((2000, 2000 + 2000))
    with pytest.raises(LookupError, match='no value at 3'):
        read(record, program, ['peak'], [3])


def test_the_fields_of_a_leg_read_in_the_legs_own_unit():
    """Legs of 4 L/h and 8 kW at half service carry 2 L/h and 4 kW, each in its own unit; the
    served fraction is a plain number."""
    b = Builder(UNITS)
    b.entity(
        'site',
        value('water', 'L', 100, lower=0),
        value('used', 'L', 0, lower=0),
        value('work', 'Wh', 10_000, lower=0),
        value('done', 'Wh', 0, lower=0),
        legs(
            'restore',
            flow('labor', this.water, this.used, request=q(4, 'L/h'), capacity=q(2, 'L/h')),
            flow('job', this.work, this.done, request=q(8, 'kW')),
        ),
    )
    program = b.finish()
    record = run(program, configured(2))
    assert unit_of(program, Key('site', ('restore', 'job', 'request'))) == ('kW', 1000.0)
    paths = ['site.restore.served_fraction', 'site.restore.labor.actual_rate', 'site.restore.job.actual_rate']
    fraction, labor, job = read(record, program, paths, [0, 2])
    assert (fraction.unit, fraction.values) == ('', pytest.approx((0.5, 0.5)))
    assert (labor.unit, labor.values) == ('L/h', pytest.approx((2, 2)))
    assert (job.unit, job.values) == ('kW', pytest.approx((4, 4)))


def test_a_curved_piece_reads_the_increase_of_its_series():
    """T2(u) = 2u^2 - 1 over 2 h: from u = -1 (1) to u = 0 (-1) it falls by 2."""
    history = History(Key('', ('x',)), (Piece(0, 1.0, curve=Curve(2.0, (0.0, 0.0, 1.0))),))
    assert history.at(1.0) == pytest.approx(-1.0)
    assert history.at(2.0) == pytest.approx(1.0)


# ---- failures and refusals ----------------------------------------------------------------------------


def test_a_run_that_fails_keeps_its_failure_in_the_record():
    program = tank(water=-1).finish()
    record = run(program, configured(3))
    assert 'State bounds violated' in record.failure.detail('message')
    assert record.failure.kind == 'failure' and record.trace[-1] == record.failure


def test_a_negative_request_stops_the_run():
    program = tank(request=q(-1, 'L/h')).finish()
    assert 'Negative flow rates' in run(program, configured(3)).failure.detail('message')


@pytest.mark.parametrize(
    'parts, slice_, links',
    [
        ((event('refill', after(q(1, 'h'), assign(this.water, draw(uniform(1, 2, 'L'))))),), 'S4', None),
        ((value('quiet', 'h', formula(elapsed(this.water))),), 'S4', None),
        ((assertion(this.water >= q(0, 'L')),), 'S4', None),
        (
            (flow('echo', SOURCE, this.water, request=formula(named('clinic').delivery.actual_rate)),),
            'S5',
            None,
        ),
    ],
)
def test_a_part_of_a_later_slice_is_refused_by_name(parts, slice_, links):
    with pytest.raises(Outside, match=slice_):
        run(tank(*parts, links=links).finish(), configured(1))
