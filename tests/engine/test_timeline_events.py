"""The event cases of the old timeline tests (`tests/engine/test_timeline.py`, whose other cases wait
for their own port): a crossing that its own stage writes back, the order of the instances of a
template at one time, and writes and moves that miss a bound by roundoff.

The expected values are worked by hand from the rules of rounds (D5) and of moves (spec, "Expressions
and instantaneous transfers").
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SOURCE,
    Builder,
    add,
    after,
    assign,
    event,
    flow,
    input_,
    local,
    move,
    named,
    param,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, InputValue, Quantity, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def test_a_crossing_that_its_stage_writes_back_fires_again_at_each_visit():
    """The level rises at 1 L/h, and `drain` takes 2 L each time it reaches 2 L, while a mode says
    that it may: at 2, 4, ... 20 h. In the round after a firing, the drain's stage sets the mode high
    and empties the level, and `reset` sets the mode low again: the condition of `drain` is then
    false (the level is 0), so it does not fire a second time at that time."""
    b = Builder(UNITS)
    states = b.enum('enum[LOW, HIGH]', 'LOW', 'HIGH')
    b.entity(
        'tank',
        value('level', 'L', 0, lower=0, upper=10),
        value('total', 'L', 0),
        value('mode', states, states.LOW),
        flow('fill', SOURCE, this.level, request=q(1, 'L/h')),
        event(
            'drain',
            when((this.mode == states.LOW) & (this.level >= q(2, 'L')), start(this.drain)),
            after(
                q(0, 'h'),
                assign(this.mode, states.HIGH),
                add(this.level, q(-2, 'L')),
                add(this.total, q(2, 'L')),
            ),
        ),
        event(
            'reset',
            when(this.mode == states.HIGH, start(this.reset)),
            after(q(0, 'h'), assign(this.mode, states.LOW)),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(20)))
    assert record.failure is None, record.failure
    drains = [entry.t for entry in record.entries('fire', 'tank.drain.when[0]')]
    assert drains == pytest.approx([2.0 * k for k in range(1, 11)], abs=1e-9)
    total, level = read(record, program, ['tank.total', 'tank.level'], [20.0])
    assert total.values == (20.0,) and level.values == pytest.approx((0.0,), abs=1e-12)


def test_the_occurrences_of_the_instances_of_a_template_go_in_the_order_of_the_instances():
    """Two instances of a template start their event at the same time by their clocks, and each
    stage reads what the one before it committed. `zulu` is the first instance and `alpha` the first
    by name: with `zulu` first the pot is 0 * 2 + 1 = 1 and then 1 * 3 + 1 = 4; with `alpha` first it
    would be 1 and then 1 * 2 + 1 = 3."""
    b = Builder(UNITS)
    pot = b.entity('pot', value('level', '', 0))
    hand = b.template(
        'Hand',
        input_('factor', '', 2),
        event(
            'take',
            when(t >= q(1, 'h'), start(this.take), reset=reset_when(False)),
            after(q(0, 'h'), assign(pot.level, pot.level * this.factor + 1)),
        ),
    )
    b.member(hand, 'zulu', factor=2)
    b.member(hand, 'alpha', factor=3)
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert [entry.owner for entry in record.entries('start', 'Hand.take')] == ['zulu.take#0', 'alpha.take#0']
    assert read(record, program, ['pot.level'], [2.0])[0].values == (4.0,)


def yard(taken):
    """A yard whose stage writes `0.3 - 0.1 - 0.2` (about -2.8e-17 in doubles) into a store with a
    lower bound of 0, and moves `taken` of a store of 1 L into another."""
    b = Builder(UNITS)
    b.entity(
        'yard',
        input_('taken', 'L', 0.5),
        value('left', 'L', 1, lower=0),
        value('full', 'L', 1, lower=0),
        value('got', 'L', 0, lower=0),
        event(
            'step',
            param('amount', 'L'),
            after(
                q(0, 'h'),
                assign(this.left, q(0.3, 'L') - q(0.1, 'L') - q(0.2, 'L')),
                move(local.amount, this.full, this.got),
            ),
        ),
    )
    b.setup(start(named('yard').step, named('yard').taken))
    program = b.finish()
    configuration = Configuration(Request(1), inputs=(InputValue('yard', 'taken', Quantity(taken, 'L')),))
    return program, run(program, configuration)


def test_a_write_or_a_move_that_misses_a_bound_by_roundoff_lands_on_the_bound():
    # A move of all of a store but 1e-12 of it, less than the store's tolerance (1e-10), moves all.
    assert 0.3 - 0.1 - 0.2 < 0
    program, record = yard(1 - 1e-12)
    assert record.failure is None, record.failure
    left, full, got = read(record, program, ['yard.left', 'yard.full', 'yard.got'], [1.0])
    assert (left.values, full.values, got.values) == ((0.0,), (0.0,), (1.0,))


def test_a_move_of_more_than_a_store_holds_fails():
    _, record = yard(1.5)
    assert 'fails' in record.failure.detail('message') and record.failure.t == 0
