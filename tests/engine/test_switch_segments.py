"""A segment follows its incoming rate until the store reaches the switch. Each level here comes
from adding the rates on the two sides for the time spent on each. A cut, an edit and a restored
checkpoint must use the same trajectory.
"""

import math
from fractions import Fraction as F

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, sparse
from napkin.engine.timeline.sparse import Sparse
from napkin.engine.timeline.ways import Ways
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    endpoint,
    event,
    flow,
    fmax,
    formula,
    ifelse,
    input_,
    named,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.engine.test_clock_moments import UNITS, rate
from tests.engine.test_round_rate_reads import check


def tank(level, condition, first, second, *, upper=None, drain=0, pump_at=None, observation=2):
    builder = Builder(UNITS)
    parts = [
        value('water', 'L', level, lower=0, upper=upper),
        value('seen', 'L/h', -1),
        flow('fill', SOURCE, this.water, request=formula(ifelse(condition, rate(first), rate(second)))),
        event('look', after(q(observation, 'h'), assign(this.seen, this.fill.actual_rate))),
    ]
    if drain:
        parts.append(
            flow(
                'drain',
                this.water,
                SINK,
                request=formula(ifelse(this.water > q(8, 'L'), rate(2), rate(drain))),
            )
        )
    if pump_at is not None:
        parts.append(
            event(
                'pump',
                flow('draw', this.water, SINK, request=rate(2)),
                after(q(1, 'h')),
                when(t >= q(pump_at, 'h'), start(this.pump), reset=reset_when(False)),
            )
        )
    builder.entity('tank', *parts)
    builder.setup(start(named('tank').look))
    return builder.finish()


def test_fill_slows_when_the_tank_reaches_one_litre():
    """Clock seed 412. The fill reaches 1 L at 1 h and gains 1/8 L in the next quarter hour."""
    program = tank(0, this.water < q(1, 'L'), 1, F(1, 2))
    check(program, 3, [('tank.water', 1, 1), ('tank.water', F(5, 4), F(9, 8))])


def test_finishing_a_drain_sends_water_back_across_the_switch():
    """Clock seed 597. Removing the pump sends the tank back through 6 L at 20/9 h."""
    program = tank(6, this.water >= q(6, 'L'), 1, 2, drain=F(1, 2), pump_at=1)
    # The additional drain takes the tank from 13/2 to 6 at 4/3 h, then to 17/3 at 2 h.
    # After it finishes, the tank reaches 6 again at 20/9 h and gains 1/2 L/h.
    check(
        program,
        4,
        [('tank.water', 2, F(17, 3)), ('tank.water', F(20, 9), 6), ('tank.water', F(9, 4), F(433, 72))],
    )


def test_an_edit_releases_a_full_tank_and_its_fill_slows_at_one_litre():
    """Clock seed 1923. The edit at 2 h releases the fill, which reaches 1 L at 7/3 h."""
    program = tank(8, this.water <= q(1, 'L'), 3, 2, upper=8)
    check(program, 3, [('tank.water', F(5, 2), 8)])
    check(
        program,
        3,
        [('tank.water', F(7, 3), 1), ('tank.water', F(5, 2), F(4, 3))],
        (Key('tank', ('water',)), 0),
        origin='tank.look.step[0]',
    )


def test_the_fill_switches_when_the_drain_fires():
    """Clock seed 2027. The store reaches exactly 8 L when the drain fires at 3 h."""
    program = tank(2, this.water <= q(8, 'L'), 2, 1, upper=10, pump_at=3, observation=1)
    # At 3 h the rising tank reaches 8 L and the drain starts. Below 8 L the 2 L/h fill
    # balances it, so the tank stays at 8 L through the next half hour.
    check(program, 4, [('tank.water', 3, 8), ('tank.water', F(7, 2), 8)])


def test_a_component_trial_keeps_the_branch_and_reads_its_trial_state():
    """A tank starts at 1 L. Below 3 L the rate is water / 1 h, then it is 7 L/h. A Radau
    trial at 4 L still uses the first branch and therefore asks for 4 L/h. The true crossing
    occurs at log(3) h. The tank holds 3 + 7*(2 - log(3)) litres at 2 h."""
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 1, lower=0),
        flow(
            'fill',
            SOURCE,
            this.water,
            request=formula(ifelse(this.water < q(3, 'L'), this.water / q(1, 'h'), rate(7))),
        ),
    )
    program = builder.finish()
    config = Configuration(Request(2))
    _, _, (way,) = Run(Plan.of(program, config)).prepare()
    segment = way.component.next(2)
    assert segment.end == pytest.approx(math.log(3), abs=1e-8)
    field = way.component.field
    np.testing.assert_allclose(field.rates(1, np.array([4.0])), [4.0])
    # Exercise the fallback too. It still names errors on the selected side.
    field._program = False
    np.testing.assert_allclose(field.rates(1, np.array([4.0])), [4.0])
    record = run(program, config)
    assert record.failure is None
    assert read(record, program, ['tank.water'], [2])[0].values[0] == pytest.approx(3 + 7 * (2 - math.log(3)))


def test_sparse_template_rows_keep_their_own_branches_and_trial_values():
    """Four rows start at 1 L. Two start below their switch, two above. Their trial states of 4 L
    therefore give 4 and 7 L/h in alternate rows. Each pair uses the same vector expression."""
    builder = Builder(UNITS)
    supply = builder.entity('supply', value('stock', 'L', 100, lower=0))
    cell = builder.template(
        'Cell',
        input_('mark', 'L', 0),
        value('water', 'L', 1, lower=0, inflow=endpoint(capacity=rate(12))),
        flow(
            'fill',
            supply.stock,
            this.water,
            request=formula(ifelse(this.water < this.mark, this.water / q(1, 'h'), rate(7))),
        ),
    )
    builder.table('cells', cell, [{'mark': 3}, {'mark': 0.5}, {'mark': 4}, {'mark': 0.25}])
    program = builder.finish()
    config = Configuration(Request(2))
    model = Run(Plan.of(program, config))
    _, _, ways = model.prepare()
    assert len(ways) == 1
    seen = []
    for way in ways:
        assert isinstance(way, Sparse)
        way._start()
        seen.extend(way.values(1, np.full(len(way.stores), 4.0))[0].tolist())
    assert seen == [4, 7, 4, 7]


@pytest.mark.parametrize('way', ['ComponentWay', 'Sparse'])
@pytest.mark.parametrize(
    ('guard', 'gap'),
    [('clock', gap) for gap in (-2, -1, 0, 1, 2)] + [('level', gap) for gap in (-2, -0.5, 0, 0.5, 2)],
)
def test_a_located_switch_belongs_to_the_scheduled_moment_only_inside_its_time_band(way, gap, guard):
    """An authored binary clock time tests the closed edge exactly. A located store crossing
    tests both sides with room for roundoff in the numerical trajectory."""
    crossing = 2**-16
    located = 1 + crossing * gap
    condition = t < q(located, 'h') if guard == 'clock' else this.water < q(located, 'L')
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 0, lower=0, inflow=endpoint(capacity=rate(10)) if way == 'Sparse' else None),
        value('incoming', 'L/h', -1),
        value('outgoing', 'L/h', -1),
        flow('fill', SOURCE, this.water, request=formula(ifelse(condition, rate(1), rate(3)))),
        event(
            'look',
            after(q(1, 'h'), assign(this.incoming, this.fill.actual_rate)),
            after(q(0, 'h'), assign(this.outgoing, this.fill.actual_rate)),
        ),
    )
    builder.setup(start(named('tank').look))
    program, config = builder.finish(), Configuration(Request(2), numerics=Numerics(crossing=crossing))
    _, _, (instance,) = Run(Plan.of(program, config)).prepare()
    assert type(instance).__name__ == way
    record = run(program, config)
    assert record.failure is None
    observed = read(record, program, ['tank.incoming', 'tank.outgoing'], [1])
    assert [item.values[0] for item in observed] == [3 if gap < -1 else 1, 1 if gap > 1 else 3]
    contacts = [(entry.t, entry.part, entry.detail('located')) for entry in record.entries('contact')]
    assert contacts == ([(1, 'tank.fill', pytest.approx(located, abs=2e-14))] if abs(gap) <= 1 else [])


@pytest.mark.parametrize('capped', [False, True], ids=['component', 'sparse'])
@pytest.mark.parametrize('rebuild', [False, True], ids=['same set', 'rewritten request'])
def test_a_grouped_clock_switch_stays_consumed_through_two_short_subsequent_waits(capped, rebuild):
    """An early stage groups the 2 h switch. The two waits of 1e-9 h precede its original
    clock time. The shared rate stays 1, including across a rebuild and a restored breakpoint."""
    builder = Builder(UNITS)
    first = F(2) - F(5, 10**9)
    short = q(F(1, 10**9), 'h')
    names = ('first', 'shared', 'later', 'last')
    reset = (assign(this.want, rate(4)),) if rebuild else ()
    builder.entity(
        'tank',
        value('water', 'L', 0, lower=0, inflow=endpoint(capacity=rate(10)) if capped else None),
        value('want', 'L/h', 4),
        *(value(name, 'L/h', -1) for name in names),
        flow('fill', SOURCE, this.water, request=formula(ifelse(t < q(2, 'h'), this.want, rate(1)))),
        event(
            'look',
            after(q(first, 'h'), assign(this.first, this.fill.actual_rate)),
            after(q(0, 'h'), assign(this.shared, this.fill.actual_rate), *reset),
            after(short, assign(this.later, this.fill.actual_rate), *reset),
            after(short, assign(this.last, this.fill.actual_rate)),
        ),
    )
    builder.setup(start(named('tank').look))
    program, config = builder.finish(), Configuration(Request(3))
    paused = Run(Plan.of(program, config), [Breakpoint('tank.look.step[2]')])
    stop = paused.run()
    assert isinstance(stop, Checkpoint)
    restored = Run.restored(Plan.of(program, config), loads(dumps(stop)))
    for record in (run(program, config), paused.resume(), restored.resume()):
        readings = read(record, program, [f'tank.{name}' for name in names], [3])
        assert record.failure is None
        assert [row.values[0] for row in readings] == [4, 1, 1, 1]
        assert [(e.t, e.detail('located')) for e in record.entries('contact')] == [(float(first), 2)]


@pytest.mark.parametrize('capped', [False, True], ids=['component', 'sparse'])
def test_one_read_samples_only_its_moving_set_and_a_stop_keeps_the_samples(capped, monkeypatch):
    builder = Builder(UNITS)
    for name in ('tank', 'garden'):
        builder.entity(
            name,
            value('water', 'L', 0, lower=0, inflow=endpoint(capacity=rate(20)) if capped else None),
            flow('fill', SOURCE, this.water, request=formula(t * q(1, 'L/h/h'))),
        )
    builder.entity(
        'clinic',
        value('seen', 'L/h', -1),
        event(
            'look',
            after(q(1, 'h'), assign(this.seen, rate(0))),
            after(
                q(1, 'h'),
                assign(this.seen, named('tank').water.inflow.actual_rate + named('tank').fill.actual_rate),
            ),
            after(q(1, 'h'), assign(this.seen, named('garden').fill.actual_rate)),
        ),
    )
    builder.setup(start(named('clinic').look))
    program, config = builder.finish(), Configuration(Request(4))
    samples = []
    publish = Ways.publish

    def counted(ways, instance, at, incoming=False, flows=None):
        if incoming:
            samples.append((at, tuple(instance.flows)))
        return publish(ways, instance, at, incoming, flows)

    monkeypatch.setattr(Ways, 'publish', counted)
    direct = run(program, config)
    expected = [(2, ('tank.fill',)), (3, ('garden.fill',))]
    assert samples == expected

    samples.clear()
    paused = Run(Plan.of(program, config), [Breakpoint('clinic.look.step[1]')])
    stop = paused.run()
    assert isinstance(stop, Checkpoint)
    assert sorted(samples) == [(2, ('garden.fill',)), (2, ('tank.fill',))]
    restored = Run.restored(Plan.of(program, config), loads(dumps(stop)))
    for simulation in (paused, restored):
        samples.clear()
        result = simulation.resume()
        assert samples == expected[1:]
        assert read(result, program, ['clinic.seen'], [1, 2, 3]) == read(
            direct, program, ['clinic.seen'], [1, 2, 3]
        )
    assert list(read(direct, program, ['clinic.seen'], [1, 2, 3])[0].values) == [0, 4, 3]


@pytest.mark.parametrize('capped', [False, True], ids=['component', 'sparse'])
def test_a_departed_moving_flow_counts_in_the_opening_total_and_its_next_delay(capped):
    b = Builder(UNITS)
    tank = named('tank')
    b.entity(
        'tank',
        value('water', 'L', 0, lower=0, inflow=endpoint(capacity=rate(20)) if capped else None),
        flow('fill', SOURCE, this.water, request=formula(t * q(1, 'L/h/h'))),
        flow('copy', SOURCE, SINK, unit='L/h', request=formula(this.water.inflow.actual_rate)),
    )
    b.entity(
        'clinic',
        value('before', 'L/h', -1),
        value('inside', 'L/h', -1),
        value('shared', 'L/h', -1),
        value('done', 'h', -1),
        event('extra', flow('pipe', SOURCE, tank.water, request=rate(3)), after(q(2, 'h'))),
        event(
            'take',
            after(
                q(2, 'h'),
                assign(this.before, tank.water.inflow.actual_rate),
                assign(this.inside, tank.copy.actual_rate),
            ),
            after(q(0, 'h'), assign(this.shared, tank.copy.actual_rate)),
            after(tank.water.inflow.actual_rate / q(1, 'L/h/h'), assign(this.done, t)),
        ),
    )
    b.setup(start(named('clinic').extra), start(named('clinic').take))
    program, config = b.finish(), Configuration(Request(5))
    paused = Run(Plan.of(program, config), [Breakpoint('clinic.take.step[0]')])
    stop = paused.run()
    assert isinstance(stop, Checkpoint)
    restored = Run.restored(Plan.of(program, config), loads(dumps(stop)))
    for record in (run(program, config), paused.resume(), restored.resume()):
        assert record.failure is None
        values = read(
            record, program, [f'clinic.{name}' for name in ('before', 'inside', 'shared', 'done')], [5]
        )
        assert [row.values[0] for row in values] == [5, 5, 2, 4]


@pytest.mark.parametrize('capped', [False, True])
def test_a_segment_can_leave_a_switch_and_return_to_it(capped):
    """The tank starts at 1 L. Its fill carries it above that switch; the drain asks for t L/h.
    The level is 1 + t - t²/2 on the far side, returning to 1 L at 2 h. The fill then drops to
    one half. At 9/4 h the level is 1 + (1/2)(1/4) - ((9/4)² - 2²)/2 = 19/32 L."""
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 1, lower=0, inflow=endpoint(capacity=rate(10)) if capped else None),
        flow(
            'fill', SOURCE, this.water, request=formula(ifelse(this.water <= q(1, 'L'), rate(0.5), rate(1)))
        ),
        flow('drain', this.water, SINK, request=formula(t * q(1, 'L/h/h'))),
    )
    program = builder.finish()
    record = run(program, Configuration(Request(2.25)))
    assert record.failure is None
    assert read(record, program, ['tank.water'], [1, 2, 2.25])[0].values == pytest.approx([1.5, 1, 19 / 32])


@pytest.mark.parametrize('capped', [False, True])
def test_nearness_in_litres_cannot_make_a_later_switch_due(capped):
    """At 1 h the slowly rising store is just below the switch by 2e-9 L, within the relative
    tolerance of its 100 L level. It takes another 2e-5 h to get there, outside the time band."""
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 100, lower=0, inflow=endpoint(capacity=rate(10)) if capped else None),
        value('again', 'L/h', -1),
        flow(
            'fill',
            SOURCE,
            this.water,
            request=formula(ifelse(this.water < q(100.000100002, 'L'), rate(0.0001), rate(1))),
        ),
        event('look', after(q(1, 'h')), after(q(0, 'h'), assign(this.again, this.fill.actual_rate))),
    )
    builder.setup(start(named('tank').look))
    program = builder.finish()
    record = run(program, Configuration(Request(1.1)))
    assert record.failure is None
    assert read(record, program, ['tank.again'], [1])[0].values == pytest.approx([0.0001])
    assert not record.entries('contact')


@pytest.mark.parametrize('capped', [False, True])
def test_nearness_in_litres_cannot_close_a_pipe_at_an_uncrossed_bound(capped):
    """At 1 h the tank still has 2e-9 L of room, more than 1e-5 h of the new request. An
    absolute store tolerance cannot close the pipe before a physical upper-bound contact."""
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value(
            'water',
            'L',
            100,
            lower=0,
            upper=100.000100002,
            inflow=endpoint(capacity=rate(10)) if capped else None,
        ),
        value('want', 'L/h', 0.0001),
        value('again', 'L/h', -1),
        flow('fill', SOURCE, this.water, request=formula(this.want + t * q(0, 'L/h/h'))),
        event(
            'look',
            after(q(1, 'h'), assign(this.want, rate(0.0002))),
            after(q(0, 'h'), assign(this.again, this.fill.actual_rate)),
        ),
    )
    builder.setup(start(named('tank').look))
    program = builder.finish()
    record = run(program, Configuration(Request(1.1)))
    assert record.failure is None
    assert read(record, program, ['tank.again'], [1])[0].values == pytest.approx([0.0002])
    assert not record.entries('contact')


@pytest.mark.parametrize('capped', [False, True])
def test_a_falling_request_reaches_zero_without_spending_negative_water(capped):
    """The fill asks for max(0, 1 - t) L/h. The area it delivers is 1/2 L by 1 h, then it stops."""
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 0, lower=0, inflow=endpoint(capacity=rate(10)) if capped else None),
        flow('fill', SOURCE, this.water, request=formula(fmax(rate(0), rate(1) - t * q(1, 'L/h/h')))),
    )
    program = builder.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert read(record, program, ['tank.water'], [0.5, 1, 2])[0].values == pytest.approx([3 / 8, 0.5, 0.5])


@pytest.mark.parametrize('capped', [False, True])
def test_a_clock_switch_and_an_independent_bound_both_reach_the_same_stage(capped):
    """The fill of the supply switches at 1 h. Its pipe, delivering a steady litre per hour,
    fills a second tank half a time tolerance later. Both contacts belong to the 1 h round."""
    crossing = 2**-16
    upper = 1 + crossing / 2
    builder = Builder(UNITS)
    builder.entity(
        'plant',
        value('supply', 'L', 3, lower=0, inflow=endpoint(capacity=rate(10)) if capped else None),
        value('tank', 'L', 0, lower=0, upper=upper),
        value('level', 'L', -1),
        value('again', 'L/h', -1),
        flow(
            'fill',
            SOURCE,
            this.supply,
            request=formula(ifelse(t < q(1, 'h'), rate(3), rate(4))),
            capacity=formula(ifelse(t < q(1, 'h'), rate(3), rate(4))),
        ),
        flow('pipe', this.supply, this.tank, request=rate(1), capacity=rate(1)),
        event(
            'look',
            after(q(1, 'h'), assign(this.level, this.tank)),
            after(q(0, 'h'), assign(this.again, this.pipe.actual_rate)),
        ),
    )
    builder.setup(start(named('plant').look))
    program = builder.finish()
    record = run(program, Configuration(Request(2), numerics=Numerics(crossing=crossing)))
    assert record.failure is None
    assert [v.values[0] for v in read(record, program, ['plant.level', 'plant.again'], [1])] == [upper, 0]
    assert {entry.part for entry in record.entries('contact')} == {'plant.fill', 'plant.tank'}


@pytest.mark.parametrize('capped', [False, True])
def test_an_authored_negative_request_on_the_new_side_still_fails(capped):
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 0, lower=0, inflow=endpoint(capacity=rate(10)) if capped else None),
        flow('fill', SOURCE, this.water, request=formula(ifelse(this.water < q(1, 'L'), rate(1), rate(-1)))),
    )
    record = run(builder.finish(), Configuration(Request(2)))
    assert record.failure is not None
    assert record.failure.t == pytest.approx(1, abs=1e-8)
    assert 'Negative flow rates' in record.failure.detail('message')
    assert 'tank.fill' in record.failure.detail('message')


def test_an_internal_solver_endpoint_cannot_hide_a_bound_in_the_rest_of_the_time_band(monkeypatch):
    """The stage at 1 h precedes the upper bound by 3/64 h, inside its 1/16 h band. Set
    Radau's first step to 1 + 1/64 h: this ordinary numerical endpoint precedes the actual bound."""
    radau = sparse.Radau

    def one_step(*args, **kwargs):
        span = args[3] - args[1]
        return radau(*args, first_step=min(1 + 1 / 64, span), **kwargs)

    monkeypatch.setattr(sparse, 'Radau', one_step)
    upper = 1 + 3 / 64
    builder = Builder(UNITS)
    builder.entity(
        'tank',
        value('water', 'L', 0, lower=0, upper=upper, inflow=endpoint(capacity=rate(10))),
        value('seen', 'L', -1),
        value('outgoing', 'L/h', -1),
        flow('fill', SOURCE, this.water, request=formula(rate(1) + t * q(0, 'L/h/h'))),
        event(
            'look',
            after(q(1, 'h'), assign(this.seen, this.water)),
            after(q(0, 'h'), assign(this.outgoing, this.fill.actual_rate)),
        ),
    )
    builder.setup(start(named('tank').look))
    program = builder.finish()
    record = run(program, Configuration(Request(2), numerics=Numerics(crossing=1 / 16)))
    assert record.failure is None
    assert [v.values[0] for v in read(record, program, ['tank.seen', 'tank.outgoing'], [1])] == [upper, 0]
    (contact,) = record.entries('contact')
    assert (contact.t, contact.part, contact.detail('located')) == (1, 'tank.water', pytest.approx(upper))


def test_a_switch_at_an_accepted_step_end_is_consumed_by_the_following_step():
    from napkin.engine.continuous.integrate import crossing_time

    # Dense interpolation can round above zero at both endpoints. The solver accepted
    # zero at the shared endpoint, so the incoming step owns the crossing exactly once.
    def gap(at):
        return 2 - at + 2**-51

    assert crossing_time(gap, 1, 2, side=1, accepted=(1, 0)) == 2
    assert crossing_time(gap, 2, 3, side=1, accepted=(0, -1)) is None
