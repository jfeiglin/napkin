"""Values that an event reads when it runs (spec, "Distributions and explicit draws", "Expressions and
instantaneous transfers"; R-A2-08, R-A2-09).

A draw written in a trigger's capture, in a stage or in a delay is executed each time that it runs:
each firing draws again, from its own key. `delayed(x, D)` reads x as the run committed it D earlier
(from 0), and `delayed(x, 0 h)` in a stage the committed value, never the stage's own write.
`elapsed(x)` restarts only when a commit changes the value: a stage that writes a state away and
back leaves it running. The expected values are medians, supports and moments of the distributions,
and the constant rates of the fixtures, worked by hand.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    delayed,
    draw,
    elapsed,
    event,
    flow,
    formula,
    local,
    named,
    param,
    q,
    start,
    t,
    this,
    uniform,
    value,
    when,
)
from napkin.program.check import ProgramError
from napkin.program.config import SAMPLED, Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'person': {'people': 1}}
HOURS = 200  # one firing an hour


def clock(*parts, filled=0):
    """A clock whose trigger starts `tick` every hour from 1 h, with a draw of uniform(1, 3) people in
    its capture, which the tick adds to the total; a stock `filled` that fills at 1 person an hour from
    `filled`."""
    b = Builder(UNITS)
    b.entity(
        'clock',
        value('next', 'h', 1),
        value('total', 'person', 0),
        value('filled', 'person', filled),
        value('seen', 'person', 0),
        flow('fill', SOURCE, this.filled, request=q(1, 'person/h')),
        event(
            'tick',
            param('amount', 'person'),
            after(q(0, 'h'), add(this.total, local.amount), add(this.next, q(1, 'h'))),
            when(
                t >= this.next,
                start(this.tick, local.extra),
                captures=(value('extra', 'person', draw(uniform(1, 3, 'person'))),),
            ),
        ),
        *parts,
    )
    return b


def increments(program, configuration):
    """What each firing of `tick` added to the total, and the record."""
    record = run(program, configuration)
    assert record.failure is None, record.failure
    times = [hour + 0.5 for hour in range(1, HOURS)]
    (totals,) = read(record, program, ['clock.total'], times)
    return [b - a for a, b in zip([0.0, *totals.values[:-1]], totals.values)], record


def test_a_median_run_takes_the_median_at_each_firing():
    added, record = increments(clock().finish(), Configuration(Request(HOURS)))
    assert added == pytest.approx([2.0] * len(added))
    owners = [entry.owner for entry in record.entries('draw')][:3]
    assert owners == [f'clock.tick.when[0]!{n}' for n in (1, 2, 3)]  # each firing owns its draw


def test_a_sampled_run_draws_again_at_each_firing_from_its_own_key():
    program = clock().finish()
    first, _ = increments(program, Configuration(Request(HOURS), mode=SAMPLED, seed=11))
    again, _ = increments(program, Configuration(Request(HOURS), mode=SAMPLED, seed=11))
    other, _ = increments(program, Configuration(Request(HOURS), mode=SAMPLED, seed=12))
    assert first == again and first != other
    assert len(set(first)) == len(first)  # each firing draws again
    assert all(1.0 <= number <= 3.0 for number in first)  # the support
    # The mean of uniform(1, 3) is 2 and its standard deviation 2/sqrt(12): five standard errors.
    bound = 5 * (2 / math.sqrt(12)) / math.sqrt(len(first))
    assert abs(sum(first) / len(first) - 2.0) < bound


def test_a_sampled_firing_draws_as_the_oracle_does():
    program = clock().finish()
    configuration = Configuration(Request(6), mode=SAMPLED, seed=3)
    record = run(program, configuration)
    oracle, failed = run_of(program, configuration)
    assert failed is None
    found = read(record, program, ['clock.total'], [6])[0].values[0]
    assert found == pytest.approx(float(value_at(oracle, program, Key('clock', ('total',)), 6)), rel=1e-12)


def test_a_drawn_delay_is_captured_when_the_step_is_reached():
    """`after uniform(1 h, 3 h).draw()` from 1 h: the median delay of 2 h, so the stage runs at 3 h."""
    b = clock(
        event('late', after(draw(uniform(1, 3, 'h')), assign(this.seen, q(1, 'person')))),
        event('begin', after(q(1, 'h'), start(this.late))),
    )
    b.setup(start(named('clock').begin))
    program = b.finish()
    record = run(program, Configuration(Request(5)))
    assert [entry.t for entry in record.entries('commit', 'clock.late.step[0]')] == [3]
    (entry,) = record.entries('draw', 'clock.late.step[0].draw[0]')
    assert (entry.t, entry.owner, entry.detail('value')) == (1, 'clock.late#0', 2.0)


@pytest.mark.parametrize(('at', 'expected'), [(10, 5 + 6), (2, 5)])
def test_a_delayed_value_reads_the_run_as_it_was(at, expected):
    """The stock fills at 1 person an hour from 5: 4 h before 10 h it held 5 + 6; 4 h before 2 h is
    before the start, which reads the value at the start."""
    b = clock(event('look', after(q(at, 'h'), assign(this.seen, delayed(this.filled, q(4, 'h'))))), filled=5)
    b.setup(start(named('clock').look))
    program = b.finish()
    record = run(program, Configuration(Request(12)))
    assert read(record, program, ['clock.seen'], [12])[0].values == (pytest.approx(expected),)


def test_a_formula_of_a_delayed_value_is_read_at_each_time():
    """`formula(delayed(filled, 4 h))` reads 5 until 4 h, then 5 + (t - 4)."""
    program = clock(value('lagged', 'person', formula(delayed(this.filled, q(4, 'h')))), filled=5).finish()
    record = run(program, Configuration(Request(12)))
    (lagged,) = read(record, program, ['clock.lagged'], [0, 3, 4, 7.5, 12])
    assert lagged.values == pytest.approx((5, 5, 5, 8.5, 13))


def stages(body, delay=2):
    """A machine with a number `x`, a state, and an event whose stage at `delay` runs `body`."""
    b = Builder(UNITS)
    kind = b.enum('enum[A, B]', 'A', 'B')
    b.entity(
        'machine',
        value('x', '', 1),
        value('y', '', 0),
        value('state', kind, kind.A),
        value('quiet', 'h', 0),
        value('since', 'h', formula(elapsed(this.state))),
        event(
            'go', after(q(delay, 'h'), *body(kind)), after(q(1, 'h'), assign(this.quiet, elapsed(this.state)))
        ),
    )
    b.setup(start(named('machine').go))
    return b.finish()


def test_delayed_zero_in_a_stage_reads_the_committed_value_not_the_stages_own_write():
    """R-A2-09: x = 1; a stage sets x = 5 and then y = delayed(x, 0 h): y is 1, the committed x."""
    program = stages(lambda kind: (assign(this.x, 5), assign(this.y, delayed(this.x, q(0, 'h')))))
    found = read(run(program, Configuration(Request(4))), program, ['machine.x', 'machine.y'], [4])
    assert [reading.values for reading in found] == [(5,), (1,)]


def test_elapsed_restarts_only_when_a_commit_changes_the_value():
    """R-A2-08: state = A; at 2 h one stage writes B and then A: at 3 h elapsed(state) is 3 h. A stage
    that writes B restarts it: 1 h at 3 h."""
    away_and_back = stages(lambda kind: (assign(this.state, kind.B), assign(this.state, kind.A)))
    away = stages(lambda kind: (assign(this.state, kind.B),))
    for program, quiet in ((away_and_back, 3), (away, 1)):
        found = read(
            run(program, Configuration(Request(4))), program, ['machine.quiet', 'machine.since'], [3, 4]
        )
        assert [reading.values for reading in found] == [(quiet, quiet), (quiet, quiet + 1)]


def test_elapsed_in_a_stage_reads_its_own_change_as_now():
    """A stage that writes B and then reads elapsed(state) reads 0: the change is at this commit."""
    program = stages(
        lambda kind: (assign(this.state, kind.B), assign(this.quiet, elapsed(this.state))), delay=2
    )
    (quiet,) = read(run(program, Configuration(Request(2.5))), program, ['machine.quiet'], [2.5])
    assert quiet.values == (0,)


def test_a_trigger_on_elapsed_fires_when_the_state_has_held_long_enough():
    """The pump stops at 1 h; `when elapsed(state) >= 2 h` fires at 3 h, and again 2 h after each
    change: never again, since the state holds."""
    b = Builder(UNITS)
    kind = b.enum('enum[ON, OFF]', 'ON', 'OFF')
    b.entity(
        'pump',
        value('state', kind, kind.ON),
        value('alarms', '', 0),
        event('stop', after(q(1, 'h'), assign(this.state, kind.OFF))),
        event(
            'alarm',
            after(q(0, 'h'), add(this.alarms, 1)),
            when(elapsed(this.state) >= q(2, 'h'), start(this.alarm)),
        ),
    )
    b.setup(start(named('pump').stop))
    program = b.finish()
    record = run(program, Configuration(Request(8)))
    assert [entry.t for entry in record.entries('fire')] == [pytest.approx(3)]


def test_a_trigger_on_a_delayed_value_that_holds_fires_when_its_delay_has_passed():
    """A counter rises to 1 at 2 h; `when delayed(count, 3 h) >= 1` fires at 5 h, a moment of the run."""
    b = Builder(UNITS)
    b.entity(
        'desk',
        value('count', '', 0),
        value('late', '', 0),
        event('bump', after(q(2, 'h'), add(this.count, 1))),
        event(
            'notice',
            after(q(0, 'h'), add(this.late, 1)),
            when(delayed(this.count, q(3, 'h')) >= 1, start(this.notice)),
        ),
    )
    b.setup(start(named('desk').bump))
    program = b.finish()
    record = run(program, Configuration(Request(8)))
    assert [entry.t for entry in record.entries('fire')] == [5]
    assert read(record, program, ['desk.late'], [4.5, 5, 8])[0].values == (0, 1, 1)


def test_a_condition_on_the_past_of_a_moving_value_is_a_diagnostic():
    """The past of a stock that a flow fills moves between moments: a trigger cannot watch it."""
    program = clock(
        event(
            'look',
            after(q(0, 'h')),
            when(delayed(this.filled, q(1, 'h')) >= q(3, 'person'), start(this.look)),
        )
    ).finish()
    record = run(program, Configuration(Request(5)))
    assert 'the past of a value that moves between moments' in record.failure.detail('message')


def test_a_rate_that_reads_the_past_of_a_moving_value_is_a_diagnostic():
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'person', 10, lower=0),
        flow('leak', this.water, SINK, request=formula(delayed(this.water, q(1, 'h')) / q(10, 'h'))),
    )
    record = run(b.finish(), Configuration(Request(2)))
    assert 'a delay equation' in record.failure.detail('message')


@pytest.mark.parametrize(
    'part',
    [
        lambda: event('never', after(q(0, 'h')), when(t >= draw(uniform(1, 2, 'h')), start(this.never))),
        lambda: value('odd', 'person', formula(2 * draw(uniform(1, 3, 'person')))),
    ],
    ids=['a draw in a condition', 'a draw inside a formula'],
)
def test_a_draw_that_would_be_read_again_is_refused(part):
    with pytest.raises(ProgramError) as raised:
        clock(part()).finish()
    assert [d.code for d in raised.value.diagnostics] == ['formula_draws']
