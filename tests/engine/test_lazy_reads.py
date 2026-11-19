"""`since(e)` moves with the time, and an evaluation reads only the sides that it takes (spec, "since(e)
is an ordinary duration": "Boolean operators short-circuit left to right and a conditional expression
evaluates only its selected side"; `timeline/reads.py`).

`since(e)` is the time less the newest start of e, so a request, a formula or a condition that reads
it moves between moments as one that reads `t` does. A read that has no value (`since(e)` before the
first start, a lookup below its first key) on a side that an evaluation does not take fails nothing:
in a stage, at the start of a run, in a condition, in a setting of each way of running, in the test of
a collection and in the reader of a record. The expected values are closed forms worked by hand: a
tank of 100 L that drains at since(e) L/h from 1 h holds 100 - (t - 1)^2 / 2 L.
"""

from __future__ import annotations

import math

import pytest

from napkin.core import expr as nodes
from napkin.engine import read, run
from napkin.engine.timeline.collections import holds
from napkin.expressions import UnitSystem
from napkin.program.build import (
    SINK,
    Builder,
    add,
    after,
    assign,
    count,
    endpoint,
    event,
    flow,
    formula,
    ifelse,
    input_,
    named,
    q,
    reset_when,
    since,
    start,
    t,
    this,
    until,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key, Unavailable
from tests.reference.from_program import run_of, traced, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TIMES = [0, 1, 3, 5, 6]


def drained(t_):
    """The tank: 100 L until 1 h, then 100 - (t - 1)^2 / 2."""
    return 100 - max(t_ - 1, 0) ** 2 / 2


def test_a_flow_of_an_occurrence_that_reads_since_moves_and_records_its_rate():
    """An event started at 1 h owns a pipe whose request is since(e) * 1 L/h/h: its rate is t - 1 L/h,
    and the tank holds 92 L at 5 h."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 100, lower=0),
        event(
            'e',
            flow('drain', this.water, SINK, request=formula(since(this.e) * q(1, 'L/h/h'))),
            after(q(10, 'h')),
        ),
        event('begin', after(q(1, 'h'), start(this.e))),
    )
    b.setup(start(named('tank').begin))
    program = b.finish()
    record = run(program, Configuration(Request(6)))
    assert record.failure is None
    water, rate = read(record, program, ['tank.water', 'tank.e#0.drain.actual_rate'], TIMES)
    assert water.values == pytest.approx([drained(at) for at in TIMES], rel=1e-9)
    assert rate.values[1:] == pytest.approx([at - 1 for at in TIMES[1:]], rel=1e-9, abs=1e-12)
    assert isinstance(rate.values[0], Unavailable)  # the occurrence has not started at 0 h
    assert record.history(Key('tank.e#0', ('drain', 'actual_rate'))).pieces  # the rate is recorded


def guarded(*extra):
    """The coordinator's tank: `go` starts at 1 h; the pipe asks since(go) * 1 L/h/h once go has
    started, and 0 L/h before, when since(go) has no value."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 100, lower=0),
        event('go', after(q(0, 'h')), when(t >= q(1, 'h'), start(this.go), reset=reset_when(False))),
        flow(
            'pipe',
            this.water,
            SINK,
            request=formula(
                ifelse(count(this.go.occurrences) > 0, since(this.go) * q(1, 'L/h/h'), q(0, 'L/h'))
            ),
        ),
        *extra,
    )
    return b.finish()


def test_a_guarded_request_reads_since_only_once_its_event_has_started():
    program = guarded()
    record = run(program, Configuration(Request(6)))
    assert record.failure is None
    water, rate = read(record, program, ['tank.water', 'tank.pipe.actual_rate'], TIMES)
    assert water.values == pytest.approx([drained(at) for at in TIMES], rel=1e-9)
    assert rate.values == pytest.approx([max(at - 1, 0) for at in TIMES], rel=1e-9, abs=1e-12)


def test_a_formula_reads_only_its_selected_side_in_the_reader_of_the_record():
    """`formula(since(go) if count > 0 else 0 h)` reads 0 h before 1 h, then t - 1."""
    program = guarded(
        value('waited', 'h', formula(ifelse(count(this.go.occurrences) > 0, since(this.go), q(0, 'h'))))
    )
    record = run(program, Configuration(Request(6)))
    (waited,) = read(record, program, ['tank.waited'], TIMES)
    assert waited.values == pytest.approx([max(at - 1, 0) for at in TIMES], abs=1e-12)


def test_a_condition_short_circuits_and_is_predicted_on_since_as_on_t():
    """`count(go) > 0 and since(go) >= 2 h` is false while go has not started, and its contact is the
    time of the start plus 2 h: 3 h. The oracle agrees."""
    program = guarded(
        value('alarms', '', 0),
        event(
            'alarm',
            after(q(0, 'h'), add(this.alarms, 1)),
            when(
                (count(this.go.occurrences) > 0) & (since(this.go) >= q(2, 'h')),
                start(this.alarm),
                reset=reset_when(False),
            ),
        ),
    )
    configuration = Configuration(Request(6))
    record = run(program, configuration)
    assert [entry.t for entry in record.entries('fire', 'tank.alarm.when[0]')] == [pytest.approx(3)]
    oracle, failed = run_of(program, configuration)
    assert failed is None and [at for at, _ in traced(oracle, 'fire', 'tank.alarm.when[0]')] == [3]


def test_a_starting_value_reads_only_the_side_that_it_takes():
    """At the start no occurrence of go exists: `since(go) if count > 0 else 0 h` takes 0 h. The
    oracle agrees."""
    b = Builder(UNITS)
    b.entity(
        'clock',
        value('first', 'h', ifelse(count(this.go.occurrences) > 0, since(this.go), q(0, 'h'))),
        value('either', 'h', 0),
        event('go', after(q(0, 'h'))),
        event(
            'look',
            after(
                q(2, 'h'),
                assign(this.either, ifelse(count(this.go.occurrences) > 0, since(this.go), q(9, 'h'))),
            ),
        ),
    )
    b.setup(start(named('clock').look))
    program = b.finish()
    configuration = Configuration(Request(3))
    record = run(program, configuration)
    assert record.failure is None
    found = [reading.values[0] for reading in read(record, program, ['clock.first', 'clock.either'], [3])]
    assert found == [0, 9]
    oracle, failed = run_of(program, configuration)
    assert failed is None
    assert [value_at(oracle, program, Key('clock', (name,)), 3) for name in ('first', 'either')] == [0, 9]


def test_a_read_on_the_side_that_is_taken_still_fails_the_run():
    """Without the guard, the pipe reads since(go) at 0 h, before go starts: the run fails there."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 100, lower=0),
        event('go', after(q(0, 'h')), when(t >= q(1, 'h'), start(this.go), reset=reset_when(False))),
        flow('pipe', this.water, SINK, request=formula(since(this.go) * q(1, 'L/h/h'))),
    )
    record = run(b.finish(), Configuration(Request(6)))
    assert record.failure.t == 0
    assert 'since(this.go): the event has not started' in record.failure.detail('message')


def table(keys=(3, 7), cap=None):
    """Pumps of one template, each with a key k, and a flow that asks the rate of the row of a table at
    k when k is at least 5, else 1 L/h: the table's first key is 5, so a pump at 3 has no row there,
    on the side that it does not take. `cap` gives the tank an outflow capacity, so that the set runs
    on lines (or, with a request that reads the tank, on the sparse integrator)."""
    b = Builder(UNITS)
    row = b.template('Row', input_('key', '', 0), input_('rate', 'L/h', 0))
    b.table('rows', 'Row', [{'id': 'a', 'key': 5, 'rate': 4}, {'id': 'b', 'key': 6, 'rate': 6}])
    b.template(
        'Pump',
        input_('k', '', 0),
        value('water', 'L', 100, lower=0, outflow=None if cap is None else endpoint(capacity=cap)),
        flow(
            'out',
            this.water,
            SINK,
            request=formula(
                ifelse(
                    this.k >= 5,
                    row.instances.by('key').at(this.k).rate,
                    q(1, 'L/h'),
                )
            ),
        ),
    )
    for k in keys:
        b.member('Pump', f'p{k}', k=k)
    return b.finish()


@pytest.mark.parametrize('cap', [None, q(10, 'L/h')], ids=['arrays', 'lines'])
def test_a_setting_of_a_way_reads_only_the_side_that_it_takes(cap):
    """The pump at 3 asks 1 L/h, the pump at 7 the rate of the row at 6 (6 L/h): after 2 h they hold
    98 L and 88 L."""
    program = table(cap=cap)
    configuration = Configuration(Request(2))
    record = run(program, configuration)
    assert record.failure is None
    found = [reading.values for reading in read(record, program, ['p3.water', 'p7.water'], [2])]
    assert found == [(pytest.approx(98),), (pytest.approx(88),)]
    oracle, failed = run_of(program, configuration)
    assert failed is None
    assert [value_at(oracle, program, Key(name, ('water',)), 2) for name in ('p3', 'p7')] == [98, 88]


def test_a_collection_test_reads_only_the_side_that_it_takes():
    """`a or b` with a true reads nothing of b, which has no value."""

    def value_of(name):
        if name == 'b':
            raise AssertionError('b is read')
        return True

    node = nodes.boolean('or', [nodes.ref('a'), nodes.ref('b')])
    assert holds(node, value_of, UnitSystem({})) is True


def test_a_gate_short_circuits():
    """`until count(go) > 0 and since(go) >= 1 h`: go starts at 2 h, so the gate opens at 3 h."""
    b = Builder(UNITS)
    b.entity(
        'desk',
        value('done', '', 0),
        event('go', after(q(0, 'h'))),
        event(
            'wait',
            until((count(this.go.occurrences) > 0) & (since(this.go) >= q(1, 'h'))),
            after(q(0, 'h'), add(this.done, 1)),
        ),
        event('begin', after(q(2, 'h'), start(this.go))),
    )
    desk = named('desk')
    b.setup(start(desk.wait), start(desk.begin))
    program = b.finish()
    configuration = Configuration(Request(5))
    record = run(program, configuration)
    assert record.failure is None
    assert [entry.t for entry in record.entries('commit', 'desk.wait.step[1]')] == [pytest.approx(3)]
    oracle, failed = run_of(program, configuration)
    assert failed is None and [at for at, _ in traced(oracle, 'commit', 'desk.wait.step[1]')] == [3]


def test_a_moving_set_on_the_sparse_integrator_reads_only_the_side_that_it_takes():
    """A tank with an outflow capacity (so its set runs on the sparse integrator) leaks a hundredth of
    its water an hour until go starts at 1 h, then drains at since(go) L/h: 100 e^(-t/100) L until
    1 h, then 8 L less by 5 h."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 100, lower=0, outflow=endpoint(capacity=q(50, 'L/h'))),
        event('go', after(q(0, 'h')), when(t >= q(1, 'h'), start(this.go), reset=reset_when(False))),
        flow(
            'pipe',
            this.water,
            SINK,
            request=formula(
                ifelse(
                    count(this.go.occurrences) > 0,
                    since(this.go) * q(1, 'L/h/h'),
                    this.water / q(100, 'h'),
                )
            ),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(5)))
    assert record.failure is None
    at_one = 100 * math.exp(-1 / 100)
    (water,) = read(record, program, ['tank.water'], [0.5, 1, 3, 5])
    expected = [100 * math.exp(-0.5 / 100), at_one, at_one - 2, at_one - 8]
    assert water.values == pytest.approx(expected, rel=1e-7)
