"""A value in a message is written in its declared unit, with the unit's name, at every place (spec.md:660:
a failure "reports the stock, amount, unit, occurrence and time"; spec.md:572 and 899; PLAN, change 15:
an edit is in the value's declared unit).

A run fails, or an edit is refused, where a value would leave its range: a move into or out of a
store, an argument outside its parameter's range, an assignment, an edit at a stop, an input that a
configuration sets outside its admitted range, and a store that an occurrence leaves unretired. Each
message writes its numbers as the model declares them: `would hold 5000 mL, outside its range [0 mL,
4000 mL]`, `right.level = 3 day is outside its range [0 day, 2 day]`, never the canonical 5 or 72.

The rule test: each of those places, for each of several units (mL, L and kL of volume; min, h and day
of time), with numbers chosen in that unit: the message holds each number in that unit with its name.
The expected texts are the numbers that the test writes in the model.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.build import (
    Builder,
    after,
    assign,
    event,
    input_,
    local,
    move,
    named,
    param,
    q,
    start,
    value,
)
from napkin.program.checkpoint import Breakpoint, CheckpointError
from napkin.program.config import Configuration, ConfigurationError, InputValue, Quantity, Request
from napkin.program.parts import Unit
from napkin.program.record import Key

UNITS = {
    'h': {'time': 1},
    'min': ({'time': 1}, Fraction(1, 60)),
    'day': ({'time': 1}, 24),
    'L': {'volume': 1},
    'mL': ({'volume': 1}, Fraction(1, 1000)),
    'kL': ({'volume': 1}, 1000),
}
VOLUMES = ('mL', 'L', 'kL')
TIMES = ('min', 'h', 'day')


def program(unit, *stages, setup=(), amount=None, extra=()):
    """`left.water` 8 of `unit` in [0,], `right.water` 0 in [0, 4] and `right.level` 1 of a time unit
    in [0, 2], in the units that `unit` gives; `mover.shift(amount)` in [0, 6] runs `stages`."""
    time = unit if unit in TIMES else 'h'
    volume = unit if unit in VOLUMES else 'L'
    b = Builder(UNITS)
    b.entity('left', value('water', volume, q(8, volume), lower=q(0, volume)))
    b.entity(
        'right',
        value('water', volume, q(0, volume), lower=q(0, volume), upper=q(4, volume)),
        value('level', time, q(1, time), lower=q(0, time), upper=q(2, time)),
        input_('cap', time, q(1, time), lower=q(0, time), upper=q(2, time)),
        *extra,
    )
    b.entity(
        'mover',
        event('shift', param('amount', volume, lower=q(0, volume), upper=q(6, volume)), *stages),
    )
    b.setup(start(named('mover').shift, amount if amount is not None else q(1, volume)), *setup)
    return b.finish()


def message(record):
    assert record.failure is not None
    return record.failure.detail('message')


@pytest.mark.parametrize('unit', VOLUMES)
def test_a_move_that_would_leave_a_range_writes_its_numbers_in_the_stores_unit(unit):
    """Moving 5 into a store of [0, 4]: `the move of 5 mL ... would hold 5 mL, outside its range [0 mL,
    4 mL]` (on 2cd1751 the numbers were canonical, with no unit)."""
    stage = after(q(1, 'h'), move(q(5, unit), named('left').water, named('right').water))
    found = message(run(program(unit, stage, amount=q(5, unit)), Configuration(Request(2))))
    assert f'the move of 5 {unit}' in found
    assert f'right.water would hold 5 {unit}, outside its range [0 {unit}, 4 {unit}]' in found
    stage = after(q(1, 'h'), move(q(9, unit), named('left').water, named('right').water))
    found = message(run(program(unit, stage, amount=q(5, unit)), Configuration(Request(2))))
    assert f'left.water would hold -1 {unit}, outside its range [0 {unit}, inf]' in found


@pytest.mark.parametrize('unit', VOLUMES)
def test_an_argument_outside_its_parameter_s_range_writes_it_in_its_unit(unit):
    """`shift(7)` against [0, 6]: `mover.shift#0.amount = 7 mL is outside its range [0 mL, 6 mL]`."""
    found = message(run(program(unit, after(q(1, 'h')), amount=q(7, unit)), Configuration(Request(2))))
    assert f'mover.shift#0.amount = 7 {unit} is outside its range [0 {unit}, 6 {unit}]' in found


@pytest.mark.parametrize('unit', VOLUMES + TIMES)
def test_an_assignment_outside_a_range_writes_it_in_its_unit(unit):
    """`right.water = 5` or `right.level = 3` against [0, 4] or [0, 2]."""
    name, number, high = ('water', 5, 4) if unit in VOLUMES else ('level', 3, 2)
    stage = after(q(1, 'h'), assign(getattr(named('right'), name), q(number, unit)))
    found = message(run(program(unit, stage), Configuration(Request(2))))
    assert f'right.{name} = {number} {unit} is outside its range [0 {unit}, {high} {unit}]' in found


@pytest.mark.parametrize('unit', VOLUMES + TIMES)
def test_an_edit_at_a_stop_outside_a_range_writes_it_in_its_unit(unit):
    """An edit is in the value's declared unit, and so is its refusal: `right.level = 3 day is outside
    its range [0 day, 2 day]` (on 2cd1751: `right.level = 72 ... [0, 48]`)."""
    name, number, high = ('water', 5, 4) if unit in VOLUMES else ('level', 3, 2)
    program_ = program(unit, after(q(1, 'h')))
    made = Run(Plan.of(program_, Configuration(Request(2))), (Breakpoint('mover.shift.step[0]'),))
    made.run()
    with pytest.raises(CheckpointError) as refused:
        made.edit(Key('right', (name,)), number)
    assert f'right.{name} = {number} {unit} is outside its range [0 {unit}, {high} {unit}]' in str(
        refused.value
    )


@pytest.mark.parametrize('unit', TIMES)
def test_an_input_set_outside_its_admitted_range_writes_it_in_its_unit(unit):
    """`right.cap` set to 3 against [0, 2]: `right.cap = 3 day is outside its admitted range`."""
    program_ = program(unit, after(q(1, 'h')))
    configuration = Configuration(Request(2), inputs=(InputValue('right', 'cap', Quantity(3, unit)),))
    try:
        record = run(program_, configuration)
    except ConfigurationError as problem:
        found = str(problem)
    else:
        found = message(record)
    assert f'right.cap = 3 {unit} is outside its admitted range [0 {unit}, 2 {unit}]' in found


@pytest.mark.parametrize('unit', VOLUMES)
def test_a_store_that_an_occurrence_leaves_unretired_writes_what_it_holds_in_its_unit(unit):
    """The retirement already said `still holds 8000 mL`: it keeps saying so."""
    b = Builder(UNITS)
    batch = value('batch', unit, q(3, unit), lower=q(0, unit))
    b.entity('job', event('run', batch, after(q(1, 'h'), move(q(0, unit), local.batch, local.batch))))
    b.setup(start(named('job').run))
    found = message(run(b.finish(), Configuration(Request(2))))
    assert f'its store job.run#0.batch still holds 3 {unit}' in found


def test_an_input_given_in_days_has_the_same_canonical_rate_as_its_authored_default():
    model = compile_text(
        """scenario "A rate in daily units"
    horizon 2 h
yard:
    input rate: L/h = 0.06 L/day
    water: L = 0 L
    flow feed: SOURCE -> this.water
        request = formula(this.rate)
""",
        UNITS,
    )
    by_day = model.program.unit('L/day')
    library_unit = Unit('volume per civil day', by_day.dimension, Fraction(1, 24))
    expected = [(0.0025, 0.0025), (0.0025, 0.0025), (0.0025, 0.005)]
    for supplied in (None, Quantity(0.06, 'L/day'), Quantity(Fraction(3, 50), library_unit)):
        inputs = () if supplied is None else (InputValue('yard', 'rate', supplied),)
        record = run(model.program, Configuration(Request(2), inputs))
        assert record.failure is None
        keys = [Key('yard', ('rate',)), Key('yard', ('feed', 'actual_rate')), Key('yard', ('water',))]
        assert [row.values for row in read(record, model.program, keys, [1, 2])] == expected
