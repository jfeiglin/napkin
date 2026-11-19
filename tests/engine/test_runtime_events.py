"""The event cases of the closed-form runs of the old runtime (`tests/engine/test_runtime.py`, whose
other cases wait for their own port): supply through a stock that empties, prerequisites and clocks
at one time, moves that fit or do not fit in the order of their stages, and `since`.

Each expected value is constant-rate arithmetic worked by hand from the rules of rounds (D5): stages
due together commit in the order in which their occurrences were made, each sees what the one before
it committed, and the conditions of a round are read after its stages commit and its sets settle.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    case,
    count,
    event,
    flow,
    formula,
    if_,
    ifelse,
    local,
    move,
    named,
    param,
    q,
    reset_when,
    since,
    start,
    switch,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'person': {'people': 1}}


def people(number):
    return q(number, 'person')


def rate(number):
    return q(number, 'person/h')


def run_of(*parts, setup=(), horizon=20):
    b = Builder(UNITS)
    b.entity('s', *parts)
    b.setup(*setup)
    program = b.finish()
    return program, run(program, Configuration(Request(horizon)))


def at_time(name, hours, *body):
    """An event that a clock starts once, at `hours`, and whose stage runs `body` then."""
    return event(
        name,
        when(t >= q(hours, 'h'), start(getattr(this, name)), reset=reset_when(False)),
        after(q(0, 'h'), *body),
    )


def values(program, record, names, times):
    return [reading.values for reading in read(record, program, names, list(times))]


def test_supply_through_an_exhausted_stock_and_its_replenishment():
    # 10 people, 1 an hour in and 3 out: empty at 5 h; the outflow then takes the 1 that comes in;
    # from 10 h the supply is 4 an hour, so the stock rises by 1 an hour to 10 at 20 h. Used: 15 to
    # 5 h, 5 to 10 h, 30 to 20 h. The supply's capacity keeps it at its request (a request is soft).
    supply = formula(ifelse(this.high, rate(4), rate(1)))
    program, record = run_of(
        value('stock', 'person', 10, lower=0),
        value('used', 'person', 0, lower=0),
        value('high', BOOL, False),
        flow('inflow', SOURCE, this.stock, request=supply, capacity=supply),
        flow('use', this.stock, this.used, request=rate(3)),
        at_time('restore', 10, assign(this.high, True)),
    )
    stock, used = values(program, record, ['s.stock', 's.used'], (5.0, 10.0, 20.0))
    assert stock == pytest.approx((0, 0, 10), abs=1e-9)
    assert used[-1] == pytest.approx(50)


def test_a_prerequisite_reached_at_the_time_of_a_clock_comes_first():
    # The tally rises at 2 an hour and reaches 10 at 5 h, the time of the deadline's clock. At 5 h
    # both conditions are read in the first round: `ready` fires; the deadline needs a start of
    # `ready`, so it fires in the next round, and its stage copies the tally, 10, in the round after.
    program, record = run_of(
        value('capacity', 'person', 0, lower=0),
        value('settled', 'person', 0),
        flow('grow', SOURCE, this.capacity, request=rate(2)),
        event('ready', when(this.capacity >= people(10), start(this.ready), reset=reset_when(False))),
        event(
            'deadline',
            when(
                (t >= q(5, 'h')) & (count(this.ready.occurrences) > 0),
                start(this.deadline),
                reset=reset_when(False),
            ),
            after(q(0, 'h'), assign(this.settled, this.capacity)),
        ),
    )
    fires = [(entry.part, entry.t, entry.round) for entry in record.trace if entry.kind == 'fire']
    assert fires == [('s.ready.when[0]', 5, 1), ('s.deadline.when[0]', 5, 2)]
    assert values(program, record, ['s.settled'], (5.0,))[0][0] == pytest.approx(10)


def test_moves_of_one_moment_go_one_stage_at_a_time_and_the_one_that_does_not_fit_fails():
    # Each move fits the source of 10 on its own; at one moment the stages commit one after the
    # other: the second finds 2 people left, and its move fails.
    _, record = run_of(
        value('source', 'person', 10, lower=0),
        value('a', 'person', 0, lower=0),
        value('b', 'person', 0, lower=0),
        event('give_a', after(q(0, 'h'), move(people(8), this.source, this.a))),
        event('give_b', after(q(0, 'h'), move(people(8), this.source, this.b))),
        setup=(start(named('s').give_a), start(named('s').give_b)),
        horizon=1,
    )
    assert 'fails' in record.failure.detail('message') and record.failure.t == 0


def pool(first, second):
    """A pool of 10 and a supply of 5, and two stages at 0 h, `first` then `second`."""
    return run_of(
        value('pool', 'person', 10, lower=0),
        value('supply', 'person', 5, lower=0),
        value('out', 'person', 0, lower=0),
        event('first', after(q(0, 'h'), first)),
        event('second', after(q(0, 'h'), second)),
        setup=(start(named('s').first), start(named('s').second)),
        horizon=1,
    )


def test_two_stages_that_move_one_stock_add_up_in_their_order():
    # The first moves half of the pool out; the second moves 3 into it from the supply.
    program, record = pool(move(this.pool / 2, this.pool, this.out), move(people(3), this.supply, this.pool))
    found = values(program, record, ['s.pool', 's.out', 's.supply'], (1.0,))
    assert [each[0] for each in found] == [10 - 10 / 2 + 3, 10 / 2, 5 - 3]


def test_moves_that_together_overdraw_a_stock_stop_the_run():
    # Each move fits on its own; together they would leave the pool at -4: the second finds it empty.
    _, record = pool(move(this.pool, this.pool, this.out), move(people(4), this.pool, this.supply))
    assert 'pool would hold -4' in record.failure.detail('message')


def test_a_clock_on_the_time_since_a_start_fires_that_long_after_it():
    # An impulse at 3 h sets a to 10; four hours after its start, a trigger on `since` sets it to 20.
    program, record = run_of(
        value('a', 'person', 0),
        at_time('impulse', 3, assign(this.a, people(10))),
        event(
            'settle',
            when(
                (count(this.impulse.occurrences) > 0) & (since(this.impulse) >= q(4, 'h')),
                start(this.settle),
                reset=reset_when(False),
            ),
            after(q(0, 'h'), assign(this.a, people(20))),
        ),
        horizon=12,
    )
    (a,) = values(program, record, ['s.a'], (2.5, 3.0, 6.5, 7.0))
    assert a == (0, 10, 10, 20)
    assert [entry.t for entry in record.entries('fire')] == [3, 7]


def test_a_write_and_a_move_at_one_time_make_a_trigger_due_in_the_next_round():
    # At 1 h a stage puts one person into the level, and another closes; the trigger on the level is
    # read after the round's stages and fires in that round; its own stage commits in the next.
    for change in (add(this.level, people(1)), move(people(1), this.source, this.level)):
        _, record = run_of(
            value('source', 'person', 5, lower=0),
            value('level', 'person', 0, lower=0),
            value('seen', BOOL, False),
            value('closed', BOOL, False),
            at_time('add', 1, change),
            event(
                'watch',
                when(this.level >= people(1), start(this.watch)),
                after(q(0, 'h'), assign(this.seen, True)),
            ),
            at_time('close', 1, assign(this.closed, True)),
            horizon=2,
        )
        commits = [(entry.part, entry.round) for entry in record.entries('commit')]
        assert commits == [('s.add.step[0]', 2), ('s.close.step[0]', 2), ('s.watch.step[0]', 3)]


def test_a_stage_runs_one_branch_of_an_if_and_the_matching_case_of_a_switch():
    # At 1 h the stage tests the level: 4 L passes the test, so the stage counts a pass; its switch
    # on the mode, MID, runs the MID case, whose guard holds; the line after the branches runs too.
    b = Builder(UNITS)
    modes = b.enum('enum[LOW, MID, HIGH]', 'LOW', 'MID', 'HIGH')
    b.entity(
        's',
        value('level', 'person', 4),
        value('mode', modes, modes.MID),
        value('passes', '', 0),
        value('fails', '', 0),
        value('picked', '', 0),
        value('after', '', 0),
        event(
            'check',
            after(
                q(1, 'h'),
                if_(this.level >= people(3), [add(this.passes, 1)], [add(this.fails, 1)]),
                switch(
                    this.mode,
                    case(modes.LOW, assign(this.picked, 1)),
                    case(modes.MID, assign(this.picked, 2), when=this.level >= people(1)),
                    orelse=[assign(this.picked, 9)],
                ),
                add(this.after, 1),
            ),
        ),
    )
    b.setup(start(named('s').check))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    found = [
        reading.values[0]
        for reading in read(record, program, ['s.passes', 's.fails', 's.picked', 's.after'], [2.0])
    ]
    assert found == [1, 0, 2, 1]


def test_a_case_whose_guard_is_false_leaves_the_else_to_run():
    b = Builder(UNITS)
    modes = b.enum('enum[LOW, MID, HIGH]', 'LOW', 'MID', 'HIGH')
    b.entity(
        's',
        value('mode', modes, modes.MID),
        value('picked', '', 0),
        event(
            'check',
            after(
                q(0, 'h'),
                switch(
                    this.mode,
                    case(modes.MID, assign(this.picked, 2), when=this.picked > 5),
                    orelse=[assign(this.picked, 9)],
                ),
            ),
        ),
    )
    b.setup(start(named('s').check))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert read(record, program, ['s.picked'], [1.0])[0].values == (9.0,)


def test_a_start_on_a_collection_starts_each_member_in_the_order_of_its_keys_with_one_argument():
    # The dispatcher starts `repair` on each machine, keyed by its rank, with one duration that it
    # evaluates once: each repair takes 2 h; the machine ranked first is started first.
    b = Builder(UNITS)
    machine = b.template(
        'Machine',
        value('rank', '', 0),
        value('fixed', '', 0),
        event('repair', param('duration', 'h'), after(local.duration, assign(this.fixed, t / q(1, 'h')))),
    )
    for id_, rank in (('m1', 3), ('m2', 1), ('m3', 2)):
        b.member(machine, id_, rank=rank)
    b.entity(
        'dispatcher',
        value('duration', 'h', 2),
        event(
            'send',
            after(
                q(1, 'h'),
                start(machine.instances.by('rank').repair, this.duration),
                add(this.duration, q(5, 'h')),
            ),
        ),
    )
    b.setup(start(named('dispatcher').send))
    program = b.finish()
    record = run(program, Configuration(Request(6)))
    assert [entry.owner for entry in record.entries('start', 'Machine.repair')] == [
        'm2.repair#0',
        'm3.repair#0',
        'm1.repair#0',
    ]
    found = [
        reading.values[0] for reading in read(record, program, ['m1.fixed', 'm2.fixed', 'm3.fixed'], [6.0])
    ]
    assert found == [3, 3, 3]
