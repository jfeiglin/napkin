"""Bool inputs and bool states keep the same domain in edits, run values and the file."""

import pytest

from napkin import SCHEMA_VERSION
from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.runs import Runs
from tests.build import block, compiled, edit, event, flow, library, member, named, rejected, scenario

ENABLED = 'service/enabled'
REPORTED = 'service/reported'


def binary_fixture(declaration='input enabled = false', *under):
    """The analytic transfer with the bool input `enabled`, which `declaration` and the lines `under`
    it declare."""
    return edit(scenario(), member('service', block(f'{declaration}  @fixture', '"Backup enabled"', *under)))


def edits(model, value):
    return {
        'schema_version': SCHEMA_VERSION,
        'model_hash': model.model_hash,
        'set': {'service.enabled': value},
    }


def edit_errors(model, value):
    """The problems of the edit that sets `enabled` to `value`, as the model's runs check an edit."""
    return Runs.from_table(model.run_table).errors(edits(model, value), model.model_hash)


def test_a_bool_edit_rejects_a_fractional_value():
    model = compiled(binary_fixture(), library())
    found = edit_errors(model, 0.5)
    assert [(d['code'], d['path']) for d in found] == [('bool', 'edits/set/service.enabled')]
    for value in (False, True):
        assert edit_errors(model, value) == []
    # The values that a run resolves: true or false, or 1 or 0, and nothing between.
    with pytest.raises(ModelError) as caught:
        model.resolve('a', {'service.enabled': 0.5})
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [
        ('binary_control', 'values/service.enabled')
    ]
    for value, number in ((False, 0), (True, 1), (0, 0), (1, 1)):
        assert model.resolve('a', {'service.enabled': value}).parameter_values['service.enabled'] == number


@pytest.mark.parametrize(
    'change, expected',
    [
        ('default', ('structure', ENABLED)),
        # A yes/no word is not a bool: the file writes true or false.
        ('yes', ('structure', ENABLED)),
        # A bool input has no bounds (docs/language.md, §2.4).
        ('range', ('structure', f'{ENABLED}/min:')),
        # A bool in a value of a library unit is not a number.
        ('unit', ('build', ENABLED)),
        ('fixed', ('structure', ENABLED)),
        # The type `yes/no` of version 2 is no type: a bool is true or false, which shows its type.
        ('yes/no', ('build', ENABLED)),
    ],
)
def test_a_bool_declaration_checks_its_value_range_and_type(change, expected):
    if change == 'default':
        sc = binary_fixture('input enabled: bool = 0.5')
    elif change == 'yes':
        sc = binary_fixture('input enabled: bool = yes')
    elif change == 'range':
        sc = binary_fixture('input enabled = false in 0 to 2')
    elif change == 'unit':
        sc = binary_fixture('input enabled: people = true in 0 people to 1 people')
    elif change == 'fixed':
        sc = binary_fixture('let enabled: bool = 0.5')
    else:
        sc = binary_fixture('input enabled: yes/no = false')
    assert expected in rejected(sc, library())


def test_a_yes_or_no_value_says_to_write_true_or_false():
    with pytest.raises(ModelError) as caught:
        compiled(binary_fixture('input enabled: bool = no'), library())
    (found,) = [d for d in caught.value.diagnostics if d['path'] == ENABLED]
    assert 'true or false' in found['message']


def bool_state_fixture(declaration='var reported = false', change='reported = true', *under, more=()):
    """The analytic transfer with the bool state `reported`, which `declaration` and the lines `under`
    it declare, and the members `more`. The step that stops the service makes `change`."""
    return edit(
        scenario(),
        member('service', block(f'{declaration}  @fixture', '"Outage reported"', *under), *more),
        member('service/stop', change),
    )


def test_a_bool_state_builds_as_the_engine_s_0_1_quantity():
    """A bool state is a number state that is 0 or 1, which the pages read Yes or No: false is 0, and
    the step that sets it to true sets 1."""
    model = compiled(bool_state_fixture(), library())
    quantity = model.structure_of('a').quantities['service.reported']
    assert (quantity.binary, quantity.unit, quantity.kind, quantity.minimum, quantity.maximum) == (
        True,
        'fraction',
        'variable',
        0,
        1,
    )
    trajectory = simulate(model.resolve('a'), library())
    # The service stops at `end`, and the step that stops it reports the outage.
    end = model.run_values('a')['service.end']
    assert trajectory.env_at(end / 2)['service.reported'] == 0
    assert trajectory.env_at(min(end * 1.5, model.time['horizon']))['service.reported'] == 1


def test_a_bool_state_reads_as_a_condition():
    """An event can wait for a bool state: `when reported` reads it as the condition `reported == 1`,
    and `not reported` as `reported == 0`."""
    sc = edit(
        bool_state_fixture(),
        member(
            'service',
            named('noticed', 'no', 'yes'),
            event('notices', 'reported', once=False, transition='noticed "no" -> "yes"'),
        ),
    )
    model = compiled(sc, library())
    trajectory = simulate(model.resolve('a'), library())
    stops = [e['t'] for e in trajectory.trace if e['rule'] == 'service.stop']
    notices = [e['t'] for e in trajectory.trace if e['rule'] == 'service.notices']
    assert stops and notices == stops


@pytest.mark.parametrize(
    'change, expected',
    [
        # A bool state starts true or false, and a step sets it to true, false or a condition, never
        # to a number such as 1. The step's first line sets the state of the stop; its second is the
        # change.
        ('start', ('build', REPORTED)),
        ('line', ('expression', 'service/stop/done/1')),
        # A var that a flow takes from is a stock, which holds a number of a unit, never a bool.
        ('stock', ('binary_state', REPORTED)),
        # A number state from 0 to 1 is a number, not a bool, so a step cannot set it to true: a bool
        # state is written `var reported = false`.
        ('binary', ('expression', 'service/stop/done/1')),
    ],
)
def test_a_bool_state_outside_true_and_false_is_rejected(change, expected):
    if change == 'start':
        sc = bool_state_fixture('var reported: bool = 0')
    elif change == 'line':
        sc = bool_state_fixture(change='reported = 1')
    elif change == 'stock':
        sc = bool_state_fixture(more=(flow('leak', 'reported ->', '0 per_h'),))
    else:
        sc = bool_state_fixture('var reported: fraction = 0 in 0 to 1', 'reported = true')
    assert expected in rejected(sc, library())
