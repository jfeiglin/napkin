"""A moving declared solver follows one branch until its stores reach the switch."""

import math

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run, resume
from napkin.engine.timeline.declared import MovingDeclared
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    constraint,
    event,
    flow,
    fmax,
    formula,
    given,
    ifelse,
    input_,
    local,
    maximize,
    named,
    q,
    solve_for,
    solver,
    start,
    t,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key


@pytest.mark.parametrize('source', ['constraint', 'capacity', 'keyed store'])
@pytest.mark.parametrize(('filtered', 'fraction'), [(False, 0), (True, 0), (False, -0.5), (False, 0.5)])
def test_a_moving_solver_drains_at_the_incoming_rate_until_the_tank_reaches_two_litres(
    source, filtered, fraction
):
    """4 L drain at 2 L/h to 2 L at 1 h. Then 1 L/h leaves 1 L at 2 h."""
    stage_time = 1 + fraction * Numerics().crossing
    tank, pipe = named('tank'), named('tank').drain
    limit = ifelse(tank.water > q(2, 'L'), q(2, 'L/h'), q(1, 'L/h'))
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    if source == 'keyed store':
        bands = b.template('Band', input_('level', 'L', 0), input_('rate', 'L/h', 1))
        b.table('bands', bands, ({'level': 0, 'rate': 1}, {'level': 2, 'rate': 2}))
        limit = bands.instances.by('level').at(tank.water).rate
    row = [] if source == 'capacity' else [constraint(local.out.actual_rate <= limit)]
    cap = {} if row else {'capacity': formula(limit)}
    b.entity(
        'tank',
        value('water', 'L', 4, lower=0),
        value('before', 'L/h', -1),
        value('afterward', 'L/h', -1),
        value('note', '', 0),
        flow('drain', this.water, SINK, request=q(4, 'L/h'), **cap),
        solver(
            'share',
            given('out', pipe),
            solve_for(local.out.actual_rate),
            *row,
            maximize(local.out.actual_rate),
        ),
        event(
            'note_rates',
            after(q(stage_time, 'h'), assign(this.before, pipe.actual_rate)),
            after(q(0, 'h'), assign(this.afterward, pipe.actual_rate)),
        ),
    )
    b.setup(start(tank.note_rates))
    model = b.finish()
    names = ['tank.before', 'tank.afterward', 'tank.water']
    keys = tuple(Key('tank', (name.split('.')[1],)) for name in names)
    cfg = Configuration(Request(2, everything=not filtered, keys=keys if filtered else ()))
    work = Run(Plan.of(model, cfg))
    straight = work.run()
    assert isinstance(work.ways.instance_of('tank.water'), MovingDeclared)
    paused = Run(Plan.of(model, cfg), [Breakpoint('tank.note_rates.step[0]')])
    stop = paused.run()
    assert isinstance(stop, Checkpoint), stop
    edited = paused.edit(Key('tank', ('note',)), 1)
    for record in (straight, paused.resume(), resume(model, loads(dumps(edited)))):
        assert record.failure is None
        before, afterward, water = read(record, model, names, [stage_time, 2])
        contacts = record.entries('contact', 'tank.drain' if source == 'capacity' else 'tank.share')
        assert len(contacts) == 1 and contacts[0].t == stage_time
        assert contacts[0].detail('located') == pytest.approx(1, abs=2e-12)
        assert before.values[0] == pytest.approx(2)
        assert afterward.values[0] == pytest.approx(1)
        assert water.values == pytest.approx((2, 1))


def test_rebuilding_a_moving_solver_keeps_a_clock_switch_that_the_previous_moment_grouped():
    """A clock limit falls from 4 to 1 L/h. Two later moments still precede its raw 2 h root."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    tank = named('tank')
    t0 = 2 - Numerics().crossing / 2
    short = q(Numerics().crossing / 10, 'h')
    b.entity(
        'tank',
        value('water', 'L', 20, lower=0),
        value('want', 'L/h', 6),
        *(value(f'r{k}', 'L/h', 0) for k in range(4)),
        flow('pipe', this.water, SINK, request=formula(this.want)),
        solver(
            'share',
            given('out', tank.pipe),
            solve_for(local.out.actual_rate),
            constraint(local.out.actual_rate <= ifelse(t < q(2, 'h'), q(4, 'L/h'), q(1, 'L/h'))),
            maximize(local.out.actual_rate),
        ),
        event(
            'look',
            after(q(t0, 'h'), assign(this.r0, this.pipe.actual_rate)),
            after(q(0, 'h'), assign(this.r1, this.pipe.actual_rate), assign(this.want, q(6, 'L/h'))),
            after(short, assign(this.r2, this.pipe.actual_rate), assign(this.want, q(6, 'L/h'))),
            after(short, assign(this.r3, this.pipe.actual_rate)),
        ),
    )
    b.setup(start(tank.look))
    model = b.finish()
    config = Configuration(Request(3))
    work = Run(Plan.of(model, config), [Breakpoint('tank.look.step[2]')])
    stop = work.run()
    assert isinstance(stop, Checkpoint)
    for record in (Run(Plan.of(model, config)).run(), work.resume(), resume(model, loads(dumps(stop)))):
        assert record.failure is None
        rates = read(record, model, [f'tank.r{k}' for k in range(4)], [3])
        assert [each.values[0] for each in rates] == [4, 1, 1, 1]
        assert [e.t for e in record.entries('contact', 'tank.share')] == [t0]


@pytest.mark.parametrize('source', ['clock', 'store'])
def test_a_declared_limit_falls_to_zero_on_its_incoming_segment(source):
    """A limit falls at 1 L/h² to zero at 1 h, delivering 3/8 L by 1/2 h and 1/2 L in total."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    tank = named('tank')
    falling = q(1, 'L/h') - (t * q(1, 'L/h/h') if source == 'clock' else tank.meter / q(1, 'h'))
    b.entity(
        'tank',
        value('water', 'L', 0, lower=0),
        value('meter', 'L', 0),
        flow('counter', SOURCE, this.meter, request=q(1, 'L/h')),
        flow('pipe', SOURCE, this.water, request=q(2, 'L/h')),
        solver(
            'share',
            given('out', tank.pipe),
            given('counter', tank.counter),
            solve_for(local.out.actual_rate),
            solve_for(local.counter.actual_rate),
            constraint(local.counter.actual_rate == q(1, 'L/h')),
            constraint(local.out.actual_rate <= fmax(q(0, 'L/h'), falling)),
            maximize(local.out.actual_rate),
        ),
    )
    model = b.finish()
    record = Run(Plan.of(model, Configuration(Request(2)))).run()
    assert record.failure is None
    water, rate = read(record, model, ['tank.water', 'tank.pipe.actual_rate'], [0.5, 1, 2])
    assert water.values == pytest.approx((3 / 8, 1 / 2, 1 / 2))
    assert rate.values == pytest.approx((1 / 2, 0, 0))


def test_a_source_to_sink_pipe_follows_the_moving_rate_of_a_declared_solver():
    """The solver supplies 4 − t L/h and the independent pipe asks for that answer."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    tank = named('tank')
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        flow('drain', this.water, SINK, request=q(5, 'L/h')),
        solver(
            'share',
            given('drain', tank.drain),
            solve_for(local.drain.actual_rate),
            constraint(local.drain.actual_rate <= q(4, 'L/h') - t * q(1, 'L/h/h')),
            maximize(local.drain.actual_rate),
        ),
    )
    b.entity('tap', flow('pipe', SOURCE, SINK, unit='L/h', request=formula(tank.drain.actual_rate)))
    program = b.finish()
    work = Run(Plan.of(program, Configuration(Request(1))))
    record = work.run()
    assert record.failure is None
    assert isinstance(work.ways.instance_of('tank.water'), MovingDeclared)
    for reading in read(record, program, ['tank.drain.actual_rate', 'tap.pipe.actual_rate'], [0, 0.5, 1]):
        assert reading.values == pytest.approx((4, 3.5, 3))


@pytest.mark.parametrize('declared', [False, True], ids=['local', 'declared'])
def test_two_storeless_rates_feed_the_field_of_the_stock_they_read(declared):
    """A 4 L stock drains at its level times 1/h. Its level and rate are both 4 exp(-t)."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    tank, tap = named('tank'), named('tap')
    b.entity(
        'tap',
        flow('meter', SOURCE, SINK, unit='L/h', request=formula(tank.water * q(1, '1/h'))),
        flow('copy', SOURCE, SINK, unit='L/h', request=formula(this.meter.actual_rate)),
    )
    parts = [value('water', 'L', 4, lower=0)]
    if declared:
        parts.extend(
            [
                flow('drain', this.water, SINK, request=q(5, 'L/h')),
                solver(
                    'share',
                    given('drain', tank.drain),
                    solve_for(local.drain.actual_rate),
                    constraint(local.drain.actual_rate <= tap.copy.actual_rate),
                    maximize(local.drain.actual_rate),
                ),
            ]
        )
    else:
        parts.append(flow('drain', this.water, SINK, request=formula(tap.copy.actual_rate)))
    b.entity('tank', *parts)
    model = b.finish()
    record = Run(Plan.of(model, Configuration(Request(1)))).run()
    assert record.failure is None
    paths = ['tank.water', 'tank.drain.actual_rate', 'tap.copy.actual_rate', 'tap.meter.actual_rate']
    times = [0, 0.5, 1]
    for reading in read(record, model, paths, times):
        assert reading.values == pytest.approx([4 * math.exp(-at) for at in times])
