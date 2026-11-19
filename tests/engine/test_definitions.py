"""A stage that gives a value a new calculation (spec, "Formulas and the values a caller can read":
"A writable `formula(T)` binding can accept another compatible formula"; "What each scope can see":
"A scalar assignment captures a value. `formula(...)` explicitly installs a live calculation").

From the commit on, what reads the value follows the new calculation: the rates that read it, a
trigger's condition, a formula that reads it, and the reader of the record, which takes each
definition from the trace and reads the value at a time with the definition that it had then. A
number written to a request or a capacity that is a formula captures that number. A formula of an
occurrence keeps, from its finish, the value of the definition that it had then (D7).

The expected values are worked by hand: a tank that drains at its level over 4 h holds
8 e^(-(t - 2)/4) L from 8 L at 2 h, and the others are lines; where the oracle can follow the run
(what the rates read holds between moments), it agrees.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    SINK,
    Builder,
    add,
    after,
    assign,
    event,
    flow,
    formula,
    local,
    param,
    q,
    start,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def values(record, program, path, times):
    (reading,) = read(record, program, [path], [float(time) for time in times])
    return list(reading.values)


def agrees_with_the_oracle(program, record, paths, times):
    """Each path at each time is the oracle's value, for a run to the record's horizon."""
    oracle, failed = run_of(program, Configuration(Request(record.manifest.horizon)))
    assert failed is None
    for path in paths:
        owner, _, name = path.partition('.')
        key = Key(owner, tuple(name.split('.')))
        expected = [float(value_at(oracle, program, key, Fraction(time))) for time in times]
        assert values(record, program, path, times) == pytest.approx(expected, rel=1e-9, abs=1e-12), path


def run_for(program, horizon, **request):
    record = run(program, Configuration(Request(horizon, **request)))
    assert record.failure is None, record.failure
    return record


def draining(*steps):
    """A tank of 10 L whose outflow asks `drain`, a formula of 1 L/h, and an event `swap` with
    `steps`, started at 0 h."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('want', 'L/h', 2),
        value('drain', 'L/h', formula(q(1, 'L/h'))),
        value('copy', 'L/h', 0),
        flow('out', this.water, SINK, request=formula(this.drain)),
        event('swap', *steps),
    )
    b.setup(start(tank.swap))
    return b.finish()


def test_a_stage_gives_a_formula_a_new_calculation_that_its_readers_follow():
    """The tank drains 1 L/h to 8 L at 2 h; then `drain` reads the water over 4 h, so the tank holds
    8 e^(-(t - 2)/4) L, and the outflow asks a quarter of it each hour."""
    program = draining(after(q(2, 'h'), assign(this.drain, formula(this.water / q(4, 'h')))))
    record = run_for(program, 6)
    water = values(record, program, 'tank.water', [1, 2, 3, 4, 6])
    expected = [9, 8] + [8 * math.exp(-(t - 2) / 4) for t in (3, 4, 6)]
    assert water == pytest.approx(expected, rel=1e-7)
    (history,) = [found for found in record.histories if found.key == Key('tank', ('drain',))]
    assert [history.at(time) for time in (1, 2, 4)] == pytest.approx([1, 2, 2 * math.exp(-0.5)], rel=1e-7)
    assert values(record, program, 'tank.drain', [1, 4]) == pytest.approx(
        [1, 8 * math.exp(-0.5) / 4], rel=1e-7
    )
    assert values(record, program, 'tank.out.request', [3]) == pytest.approx([2 * math.exp(-0.25)], rel=1e-7)
    commit = next(entry for entry in record.trace if entry.kind == 'commit')
    assert commit.detail('defines') == (('tank.drain', 'tank.swap.step[0].do[0]'),)


def test_a_later_statement_of_the_stage_reads_the_new_calculation():
    """Within a stage, statements see the writes before them: the copy is the new drain at 2 h,
    8 L over 4 h."""
    program = draining(
        after(
            q(2, 'h'),
            assign(this.drain, formula(this.water / q(4, 'h'))),
            assign(this.copy, this.drain),
        )
    )
    record = run_for(program, 3)
    assert values(record, program, 'tank.copy', [1, 2]) == pytest.approx([0, 2])


def test_a_request_takes_a_formula_then_a_number_again():
    """1 L/h to 1 h; then the request follows `want` (2 L/h, 3 L/h from 2 h); from 3 h it holds
    1 L/h again: 10, 9, 7, 4 and 2 L at hours 0, 1, 2, 3 and 5."""
    program = draining(
        after(q(1, 'h'), assign(this.out.request, formula(this.want))),
        after(q(1, 'h'), assign(this.want, q(3, 'L/h'))),
        after(q(1, 'h'), assign(this.out.request, q(1, 'L/h'))),
    )
    record = run_for(program, 5)
    times = [0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5]
    assert values(record, program, 'tank.water', times) == pytest.approx([10, 9.5, 9, 8, 7, 5.5, 4, 3, 2])
    assert values(record, program, 'tank.out.request', times) == pytest.approx([1, 1, 2, 2, 3, 3, 1, 1, 1])
    # The history that the record keeps of the request has the pieces of each definition too.
    (history,) = [found for found in record.histories if found.key == Key('tank', ('out', 'request'))]
    assert [history.at(time) for time in times] == pytest.approx([1, 1, 2, 2, 3, 3, 1, 1, 1])
    agrees_with_the_oracle(program, record, ['tank.water', 'tank.out.request', 'tank.out.actual_rate'], times)


def test_a_number_written_to_a_request_that_is_a_formula_captures_it():
    """The request follows `want` until a stage writes 1 L/h to it at 1 h; the write of 4 L/h to
    `want` at 2 h then changes nothing of the flow: 10, 8, 7 and 5 L at hours 0, 1, 2 and 4."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('want', 'L/h', 2),
        flow('out', this.water, SINK, request=formula(this.want)),
        event(
            'swap',
            after(q(1, 'h'), assign(this.out.request, q(1, 'L/h'))),
            after(q(1, 'h'), assign(this.want, q(4, 'L/h'))),
        ),
    )
    b.setup(start(tank.swap))
    program = b.finish()
    record = run_for(program, 4)
    times = [0, 1, 2, 3, 4]
    assert values(record, program, 'tank.water', times) == pytest.approx([10, 8, 7, 6, 5])
    assert values(record, program, 'tank.out.request', [0.5, 1, 3]) == pytest.approx([2, 1, 1])
    agrees_with_the_oracle(program, record, ['tank.water', 'tank.out.request'], times)


def test_a_number_written_to_a_moving_request_captures_it():
    """The request reads the water over 10 h: 10 e^(-t/10) L at 2 h; then 2 L/h."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        flow('out', this.water, SINK, request=formula(this.water / q(10, 'h'))),
        event('swap', after(q(2, 'h'), assign(this.out.request, q(2, 'L/h')))),
    )
    b.setup(start(tank.swap))
    program = b.finish()
    record = run_for(program, 4)
    level = 10 * math.exp(-0.2)
    assert values(record, program, 'tank.water', [2, 3, 4]) == pytest.approx([level, level - 2, level - 4])
    assert values(record, program, 'tank.out.request', [1, 3]) == pytest.approx([math.exp(-0.1), 2])


def test_a_trigger_reads_the_new_definition_of_its_condition():
    """The tank drains 1 L/h from 10 L. `low` is `water <= 2 L` until a stage at 1 h makes it
    `water <= 6 L`: the refill (4 L at once) fires at 4 h, when the tank holds 6 L, and again at
    8 h, not at 8 h first as the old definition would."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('low', BOOL, formula(this.water <= q(2, 'L'))),
        flow('out', this.water, SINK, request=q(1, 'L/h')),
        event('relax', after(q(1, 'h'), assign(this.low, formula(this.water <= q(6, 'L'))))),
        event('refill', when(this.low, start(this.refill)), after(q(0, 'h'), add(this.water, q(4, 'L')))),
    )
    b.setup(start(tank.relax))
    program = b.finish()
    record = run_for(program, 9)
    assert [entry.t for entry in record.trace if entry.kind == 'fire'] == [4, 8]
    times = [1, 3, 4, 5, 8, 9]
    assert values(record, program, 'tank.water', times) == pytest.approx([9, 7, 10, 9, 10, 9])
    agrees_with_the_oracle(program, record, ['tank.water'], times)


def test_a_formula_of_an_occurrence_freezes_with_the_definition_that_it_has_at_its_finish():
    """A delivery of 6 L asks `pace`: 1 L/h, then from 1 h the amount over 2 h, 3 L/h; it finishes
    at 3 h, and `pace` and the pipe's request keep 3 L/h from then on (D7). The tank holds 20, 19
    and 13 L at hours 0, 1 and 3, and 13 L after."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 20, lower=0),
        event(
            'deliver',
            param('amount', 'L'),
            value('pace', 'L/h', formula(q(1, 'L/h'))),
            flow('pipe', this.water, SINK, request=formula(local.pace)),
            after(q(1, 'h'), assign(local.pace, formula(local.amount / q(2, 'h')))),
            after(q(2, 'h')),
        ),
    )
    b.setup(start(tank.deliver, q(6, 'L')))
    program = b.finish()
    record = run_for(program, 4)
    assert values(record, program, 'tank.water', [0, 1, 2, 3, 4]) == pytest.approx([20, 19, 16, 13, 13])
    for path in ('tank.deliver#0.pace', 'tank.deliver#0.pipe.request'):
        assert values(record, program, path, [0.5, 2, 3.5]) == pytest.approx([1, 3, 3])
    assert values(record, program, 'tank.deliver#0.pipe.actual_rate', [2, 3.5]) == pytest.approx([3, 0])
    agrees_with_the_oracle(program, record, ['tank.water'], [0, 1, 2, 3, 4])


def test_a_reader_with_a_plan_of_its_own_takes_each_definition_from_the_trace():
    """The record is read the same after another program has run, with a plan made again for it."""
    program = draining(after(q(2, 'h'), assign(this.drain, formula(this.water / q(4, 'h')))))
    record = run_for(program, 6)
    times = [1, 2, 3, 6]
    first = values(record, program, 'tank.drain', times)
    run_for(draining(), 1)  # the plan that the reader keeps is now another program's
    assert values(record, program, 'tank.drain', times) == first
    assert values(record, program, 'tank.water', times) == pytest.approx(
        [9, 8, 8 * math.exp(-0.25), 8 * math.exp(-1)]
    )


def test_a_record_of_some_keys_keeps_what_a_new_definition_reads():
    """A record that keeps only the request still reads it after it follows `want`."""
    program = draining(
        after(q(1, 'h'), assign(this.out.request, formula(this.want))),
        after(q(1, 'h'), assign(this.want, q(3, 'L/h'))),
    )
    record = run_for(program, 3, everything=False, keys=(Key('tank', ('out', 'request')),))
    assert values(record, program, 'tank.out.request', [0.5, 1.5, 2.5]) == pytest.approx([1, 2, 3])
