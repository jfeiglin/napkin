"""A named state set from another named state, a named input or a choice between them, and a yes/no
state set from a condition (docs/language.md, §2.6)."""

from __future__ import annotations

import pytest

from napkin.model import ModelError
from tests.build import block, document, entity, library, named, run


def model(*lines, world=()):
    """A world whose alarm turns on at 1 h, and a desk that copies what it knows at 2 h."""
    return document(
        'State assignment fixture',
        entity(
            'world',
            named('alarm', 'off', 'on'),
            block('input level: "low" | "high" | "severe" = "high"  @fixture', '"Level of the world"'),
            block('event ring once when t >= 1 h:  @fixture', 'alarm = "on"'),
            *world,
        ),
        entity(
            'desk',
            named('echo', 'off', 'on'),
            named('grade', 'low', 'high', 'severe'),
            named('mixed', 'off', 'on', 'low', 'high', 'severe'),
            block('var seen = false  @fixture', '"The desk knows the alarm is on"'),
            block('event look once when t >= 2 h:  @fixture', *lines),
        ),
        horizon=4,
    )


def after(text, names):
    _, trajectory = run(text)
    env = trajectory.env_at(3)
    return [env[name] for name in names]


def test_a_named_state_takes_the_value_of_another():
    assert after(model('echo = world.alarm'), ['desk.echo']) == ['on']


def test_a_named_state_takes_the_value_of_a_named_input():
    assert after(model('grade = world.level'), ['desk.grade']) == ['high']


def test_a_choice_between_states_takes_the_branch_that_holds():
    text = model('mixed = world.level if world.alarm is "on" else "off"')
    assert after(text, ['desk.mixed']) == ['high']


def test_a_yes_no_state_takes_a_condition():
    assert after(model('seen = world.alarm is "on"'), ['desk.seen']) == [1]
    assert after(model('seen = world.alarm is "off"'), ['desk.seen']) == [0]


@pytest.mark.parametrize(
    'line',
    [
        # `world.level` can be "severe", which `echo` cannot hold.
        'echo = world.level',
        # A number is not a state.
        'echo = 1',
    ],
    ids=['a value that the target cannot hold', 'a number'],
)
def test_a_named_state_refuses_a_value_it_cannot_hold(line):
    with pytest.raises(ModelError) as raised:
        run(model(line), lib=library())
    assert any(d['code'] == 'build' for d in raised.value.diagnostics)
