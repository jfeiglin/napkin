"""Reads of what moves between moments: keyed reads whose key or members move, and settings that read
the moving rates of another connected set (D3: a rate may read a quantity that changes between
scheduled events, at any size; spec, "Collections, keys and projections": `.at(x)` reads the member
with the greatest key at or below x, of equal keys the later one).

A keyed read whose key, keys or members' values move is read where it is read: its rates run on the
sparse integrator, which holds the member that the read selects through a segment and ends the
segment where it selects another, so the rate steps at that time. A key that a stage writes builds
again the sets that read it. A watched condition on such a read has no first contact that the engine
can certify: the run stops with a diagnostic. Sets whose settings read a moving rate of another set
integrate with it, level by level.

The expected values are worked by hand from lines and exponentials; where the oracle can follow the
run (what the rates read holds between moments), it agrees.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    constraint,
    event,
    fany,
    flow,
    formula,
    given,
    ifelse,
    input_,
    local,
    named,
    q,
    solve_for,
    solver,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def run_for(program, horizon):
    record = run(program, Configuration(Request(horizon)))
    assert record.failure is None, record.failure.detail('message')
    return record


def values(record, program, path, times):
    (reading,) = read(record, program, [path], [float(time) for time in times])
    return list(reading.values)


def tiers(b):
    """Tiers by level: from 0 L 1 L/h, from 5 L 2 L/h, from 8 L 3 L/h."""
    tier = b.template('Tier', input_('level', 'L', 0), input_('rate', 'L/h', 1))
    for name, level, rate in (('low', 0, 1), ('mid', 5, 2), ('high', 8, 3)):
        b.member(tier, name, level=q(level, 'L'), rate=q(rate, 'L/h'))
    return tier


def test_a_rate_keyed_by_a_moving_store_steps_where_the_store_crosses_a_key():
    """The tank drains 1 L/h from 10 L; a charge fills at the rate of the tier of its water: 3 L/h
    to 2 h (8 L is in the top tier), 2 L/h to 5 h, then 1 L/h: 6, 12 and 15 L at hours 2, 5 and 8."""
    b = Builder(UNITS)
    tier = tiers(b)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('cost', 'L', 0),
        flow('out', this.water, SINK, request=q(1, 'L/h')),
        flow('charge', SOURCE, this.cost, request=formula(tier.instances.by('level').at(this.water).rate)),
    )
    program = b.finish()
    record = run_for(program, 8)
    times = [1, 2, 3, 5, 6, 8]
    assert values(record, program, 'tank.cost', times) == pytest.approx([3, 6, 8, 12, 13, 15])
    rates = values(record, program, 'tank.charge.actual_rate', [1.5, 2, 2.5, 5, 5.5])
    assert rates == pytest.approx([3, 3, 2, 2, 1])


def test_a_key_that_a_stage_writes_changes_the_rates_that_read_it():
    """The key reads `level`, 6 L, so the tier gives 2 L/h; a stage at 1 h sets 9 L, 3 L/h from
    then: 2, 5 and 8 L at hours 1, 2 and 3."""
    b = Builder(UNITS)
    tier = tiers(b)
    tank = b.entity(
        'tank',
        value('level', 'L', 6),
        value('cost', 'L', 0),
        flow('charge', SOURCE, this.cost, request=formula(tier.instances.by('level').at(this.level).rate)),
        event('raise_', after(q(1, 'h'), assign(this.level, q(9, 'L')))),
    )
    b.setup(start(tank.raise_))
    program = b.finish()
    record = run_for(program, 3)
    times = [0.5, 1, 2, 3]
    assert values(record, program, 'tank.cost', times) == pytest.approx([1, 2, 5, 8])
    oracle, failed = run_of(program, Configuration(Request(3)))
    assert failed is None
    expected = [float(value_at(oracle, program, Key('tank', ('cost',)), Fraction(time))) for time in times]
    assert values(record, program, 'tank.cost', times) == pytest.approx(expected, rel=1e-9)


def test_a_key_that_is_a_function_of_the_time_steps_at_its_own_times():
    """Readings at hours 0, 2 and 4 give factors 1, 2 and 3; `.at(2 t)` reaches them at hours 0, 1
    and 2: the tank drains 1, then 2, then 3 L/h from 20 L."""
    b = Builder(UNITS)
    reading = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    for name, hour, factor in (('r0', 0, 1), ('r2', 2, 2), ('r4', 4, 3)):
        b.member(reading, name, hour=q(hour, 'h'), factor=factor)
    request = reading.instances.by('hour').at(2 * t).factor * q(1, 'L/h')
    b.entity(
        'tank', value('water', 'L', 20, lower=0), flow('out', this.water, SINK, request=formula(request))
    )
    program = b.finish()
    record = run_for(program, 3)
    assert values(record, program, 'tank.water', [0.5, 1, 1.5, 2, 3]) == pytest.approx([19.5, 19, 18, 17, 14])


def test_a_read_by_the_time_reads_the_moving_value_of_the_member_that_it_selects():
    """Tank a (10 L, 1 L/h) is read from 0 h and tank b (20 L, 2 L/h) from 3 h: the monitor sees
    9 L at 1 h and 12 L at 4 h, and counts a tenth of what it sees each hour: 2.55 L at 3 h, then
    1.3 L more to 3.85 L at 4 h."""
    b = Builder(UNITS)
    tank = b.template(
        'Tank',
        input_('from_hour', 'h', 0),
        value('water', 'L', 10, lower=0),
        input_('pull', 'L/h', 1),
        flow('out', this.water, SINK, request=formula(this.pull)),
    )
    b.member(tank, 'a', from_hour=q(0, 'h'), water=q(10, 'L'), pull=q(1, 'L/h'))
    b.member(tank, 'b', from_hour=q(3, 'h'), water=q(20, 'L'), pull=q(2, 'L/h'))
    b.entity(
        'monitor',
        value('seen', 'L', formula(tank.instances.by('from_hour').at(t).water)),
        value('total', 'L', 0),
        flow('count', SOURCE, this.total, request=formula(this.seen / q(10, 'h'))),
    )
    program = b.finish()
    record = run_for(program, 4)
    assert values(record, program, 'monitor.seen', [1, 3, 4]) == pytest.approx([9, 14, 12])
    assert values(record, program, 'monitor.total', [1, 3, 4]) == pytest.approx([0.95, 2.55, 3.85])


def test_keys_that_move_select_the_member_whose_key_is_greatest_below_the_read():
    """Tank a falls 1 L/h from 10 L and tank b 0.5 L/h from 8 L; keyed by their water, the read at
    100 L selects the fuller: a until both hold 6 L at 4 h, then b. A counter fills at the selected
    tank's pull, 1 L/h then 2 L/h: 4 L at 4 h and 8 L at 6 h."""
    b = Builder(UNITS)
    tank = b.template(
        'Tank',
        value('water', 'L', 10, lower=0),
        input_('pull', 'L/h', 1),
        input_('drain', 'L/h', 1),
        flow('out', this.water, SINK, request=formula(this.drain)),
    )
    b.member(tank, 'a', water=q(10, 'L'), pull=q(1, 'L/h'), drain=q(1, 'L/h'))
    b.member(tank, 'b', water=q(8, 'L'), pull=q(2, 'L/h'), drain=q(0.5, 'L/h'))
    b.entity(
        'counter',
        value('total', 'L', 0),
        value('fullest', 'L/h', formula(tank.instances.by('water').at(q(100, 'L')).pull)),
        flow('count', SOURCE, this.total, request=formula(this.fullest)),
    )
    program = b.finish()
    record = run_for(program, 6)
    assert values(record, program, 'counter.fullest', [1, 3.9, 4.1, 6]) == pytest.approx([1, 1, 2, 2])
    assert values(record, program, 'counter.total', [1, 4, 5, 6]) == pytest.approx([1, 4, 6, 8])


def test_a_watched_condition_on_a_moving_keyed_read_stops_the_run_by_name():
    """The alarm of the tier of the water has no first contact that the engine can certify."""
    b = Builder(UNITS)
    tier = b.template('Tier', input_('level', 'L', 0), input_('alarm', BOOL, False))
    for name, level, alarm in (('low', 0, True), ('high', 5, False)):
        b.member(tier, name, level=q(level, 'L'), alarm=alarm)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('alarms', '', 0),
        flow('out', this.water, SINK, request=q(1, 'L/h')),
        event(
            'ring',
            when(tier.instances.by('level').at(this.water).alarm, start(this.ring)),
            after(q(0, 'h'), add(this.alarms, 1)),
        ),
    )
    record = run(b.finish(), Configuration(Request(8)))
    message = record.failure.detail('message')
    assert record.failure.t == 0
    assert 'cannot be certified' in message and 'a keyed read whose key or members move' in message


def test_a_trigger_on_any_of_moving_flags_fires_where_a_member_crosses():
    """`any` of the members' `water <= 5 L` becomes true at 5 h, when the tank holds 5 L."""
    b = Builder(UNITS)
    tank = b.template(
        'Tank',
        value('water', 'L', 10, lower=0),
        value('low', BOOL, formula(this.water <= q(5, 'L'))),
        flow('out', this.water, SINK, request=q(1, 'L/h')),
    )
    b.member(tank, 'a')
    b.entity(
        'watch',
        value('rings', '', 0),
        event('ring', when(fany(tank.instances.low), start(this.ring)), after(q(0, 'h'), add(this.rings, 1))),
    )
    record = run_for(b.finish(), 8)
    assert [entry.t for entry in record.trace if entry.kind == 'fire'] == [5]


def test_an_enum_formula_of_a_moving_value_changes_where_its_condition_does():
    """FULL while the tank holds 5 L or more, LOW from 5 h."""
    b = Builder(UNITS)
    level = b.enum('Level', 'FULL', 'LOW')
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('state', level, formula(ifelse(this.water >= q(5, 'L'), level.FULL, level.LOW))),
        flow('out', this.water, SINK, request=q(1, 'L/h')),
    )
    program = b.finish()
    record = run_for(program, 8)
    assert values(record, program, 'tank.state', [1, 4.9, 5.1, 8]) == ['FULL', 'FULL', 'LOW', 'LOW']
    (history,) = [found for found in record.histories if found.key == Key('tank', ('state',))]
    assert [piece.value for piece in history.pieces] == ['FULL', 'LOW']
    assert history.pieces[1].t == pytest.approx(5, abs=1e-7)


def test_a_lookup_keyed_by_an_unknown_of_a_solver_is_refused_by_name():
    """Spec, "What the first version leaves out": a lookup keyed by a solver unknown."""
    b = Builder(UNITS)
    tier = tiers(b)
    tank = b.entity(
        'tank', value('water', 'L', 10, lower=0), flow('out', this.water, SINK, request=q(2, 'L/h'))
    )
    b.entity(
        'provider',
        solver(
            'plan',
            given('x', tank.out),
            solve_for(local.x.actual_rate),
            # The tier of the rate's own number in litres an hour, as a bound of the rate.
            constraint(
                local.x.actual_rate <= tier.instances.by('level').at(local.x.actual_rate * q(1, 'h')).rate
            ),
        ),
    )
    record = run(b.finish(), Configuration(Request(1)))
    message = record.failure.detail('message')
    assert 'a lookup keyed by an unknown of the solver' in message


# ---- the moving rates of another set ------------------------------------------------------------------


def test_a_request_that_follows_a_moving_rate_of_another_set_integrates_with_it():
    """a fills at t L/h; b copies a's actual rate, so b holds t^2 / 2: 0.5, 2 and 8 L at hours 1,
    2 and 4."""
    b = Builder(UNITS)
    b.entity(
        'a', value('water', 'L', 0), flow('fill', SOURCE, this.water, request=formula(t * q(1, 'L/h/h')))
    )
    b.entity(
        'b',
        value('water', 'L', 0),
        flow('copy', SOURCE, this.water, request=formula(named('a').fill.actual_rate)),
    )
    program = b.finish()
    record = run_for(program, 4)
    assert values(record, program, 'b.water', [1, 2, 4]) == pytest.approx([0.5, 2, 8])
    assert values(record, program, 'b.copy.actual_rate', [1, 2, 4]) == pytest.approx([1, 2, 4])


def test_a_chain_of_sets_that_follow_moving_rates_integrates_level_by_level():
    """a drains at its level over 2 h from 10 L; b counts what a lets out, 10 (1 - e^(-t/2)); c counts
    twice b's rate, twice that."""
    b = Builder(UNITS)
    b.entity(
        'a',
        value('water', 'L', 10, lower=0),
        flow('out', this.water, SINK, request=formula(this.water / q(2, 'h'))),
    )
    b.entity(
        'b',
        value('count', 'L', 0),
        flow('copy', SOURCE, this.count, request=formula(named('a').out.actual_rate)),
    )
    b.entity(
        'c',
        value('count', 'L', 0),
        flow('copy', SOURCE, this.count, request=formula(2 * named('b').copy.actual_rate)),
    )
    program = b.finish()
    record = run_for(program, 4)
    counted = [10 * (1 - math.exp(-time / 2)) for time in (1, 2, 4)]
    assert values(record, program, 'b.count', [1, 2, 4]) == pytest.approx(counted, rel=1e-7)
    assert values(record, program, 'c.count', [1, 2, 4]) == pytest.approx([2 * x for x in counted], rel=1e-7)


def test_a_flow_that_joins_at_a_moment_and_follows_a_moving_rate_integrates_with_its_set():
    """An occurrence from 1 h to 4 h counts what a lets out: 10 (e^(-1/2) - e^(-t/2)), and holds it
    after its finish."""
    b = Builder(UNITS)
    b.entity(
        'a',
        value('water', 'L', 10, lower=0),
        flow('out', this.water, SINK, request=formula(this.water / q(2, 'h'))),
    )
    b.entity(
        'b',
        value('count', 'L', 0),
        event(
            'watch',
            flow('copy', SOURCE, this.count, request=formula(named('a').out.actual_rate)),
            after(q(3, 'h')),
        ),
    )
    b.entity('kick', event('go', after(q(1, 'h'), start(named('b').watch))))
    b.setup(start(named('kick').go))
    program = b.finish()
    record = run_for(program, 5)
    counted = [10 * (math.exp(-0.5) - math.exp(-time / 2)) for time in (2, 4)]
    assert values(record, program, 'b.count', [1, 2, 4, 5]) == pytest.approx(
        [0, *counted, counted[-1]], rel=1e-7
    )
    assert values(record, program, 'a.water', [4]) == pytest.approx([10 * math.exp(-2)], rel=1e-7)


def test_a_set_that_follows_a_moving_solver_stops_the_run_by_name():
    """The rate that a solver chooses follows its tank; the engine integrates the set of a moving
    solver alone."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 0, lower=0),
        flow(
            'fill',
            SOURCE,
            this.water,
            request=formula((q(10, 'L') - this.water) / q(1, 'h')),
            capacity=q(6, 'L/h'),
        ),
    )
    b.entity('provider', solver('share', given('f', tank.fill), solve_for(local.f.actual_rate)))
    b.entity(
        'copy',
        value('count', 'L', 0),
        flow('take', SOURCE, this.count, request=formula(tank.fill.actual_rate)),
    )
    record = run(b.finish(), Configuration(Request(1)))
    message = record.failure.detail('message')
    assert record.failure.t == 0
    assert 'tank.fill.actual_rate' in message and 'integrates the set of a moving solver alone' in message
