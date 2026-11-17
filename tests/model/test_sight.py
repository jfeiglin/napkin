"""Choices and sight (docs/language.md, §2.7): an actor, a thing with `sees`, knows what it sees, `t`,
`copy` and its own inputs, and nothing else. An event marked `choice` is one that a run can give to a
person or an agent: it belongs to an actor, has two outcomes or more, and reads only what its actor
knows in its `when`, `after`, `each`, `while`, chances and the conditions of its outcomes. Any other
event is a mechanism: chance takes its outcomes, and it may read anything."""

from __future__ import annotations

import pytest

from napkin.engine import evaluate_study
from napkin.model import ModelError
from napkin.model.structure import thawed
from tests.build import block, compiled, document, entity, named, parameter, stock, template

WORLD = entity(
    'world',
    named('alarm', 'off', 'on'),
    stock('level', 0, 'fraction', maximum=1, size=None),
    parameter('delay', 2, 'h', 1, 4),
    block('event ring once when t >= 1 h:  @fixture', 'alarm = "on"'),
)


def guard(*events, sees='world.alarm, world.ring'):
    """An operator that sees `sees`, with an input `odds`, a named state `order`, a number `calls`
    and `events`."""
    return entity(
        'guard',
        f'sees {sees}' if sees else None,
        parameter('odds', 0.5, 'fraction', 0, 1),
        named('order', 'none', 'shut', 'wait'),
        stock('calls', 3, 'fraction', maximum=3, size=None),
        *events,
        role='operator',
    )


def decision(when, chance='0.5', after=None, choice=True, each=None, keep=None):
    """An event with two outcomes, marked `choice` unless `choice` is false; with a window (`each`)
    it is not `once`, and with a waiting condition (`keep`, `while`) it waits `after`."""
    wait = f' after {after}' if after else ''
    window = f' each {each}' if each else ''
    waiting = f' while {keep}' if keep else ''
    once = '' if each else ' once'
    return block(
        f'event decide{once}{wait}{window} when {when}{waiting}:  @fixture',
        *(['choice'] if choice else []),
        block(f'shut {chance}:', 'order = "shut"'),
        block('wait else:', 'order = "wait"'),
    )


def codes(*members):
    """The codes of the diagnostics that refuse a file of the world and `members`."""
    try:
        compiled(document('Sight fixture', WORLD, *members))
    except ModelError as raised:
        return [d['code'] for d in raised.diagnostics]
    return []


def choices(*members):
    """The rules of a file of the world and `members` that a run can give to a person or an agent."""
    rules = compiled(document('Sight fixture', WORLD, *members)).resolve('a').rules
    return sorted(rid for rid, rule in rules.items() if rule.choice)


def played(control, *members):
    """The codes of the diagnostics of a play request of run `a` with this control."""
    model = compiled(document('Sight fixture', WORLD, *members))
    study = evaluate_study(model, play={'run': 'a', 'control': control, 'picks': []})
    return [d['code'] for d in study.diagnostics if d.get('severity', 'error') == 'error']


@pytest.mark.parametrize(
    'event',
    [
        decision('world.alarm is "on"'),  # a field that it sees
        decision('count(world.ring) > 0'),  # an event that it sees
        decision('t >= 2 h'),  # the time
        decision('t >= 2 h', chance='odds'),  # its own input
        decision('world.alarm is "on"', chance='0.9 if world.alarm is "on" else 0.1'),
    ],
)
def test_a_choice_reads_what_its_actor_knows(event):
    assert choices(guard(event)) == ['guard.decide']
    assert played({'guard.decide': 'reader'}, guard(event)) == []


@pytest.mark.parametrize(
    ('when', 'chance', 'after'),
    [
        ('world.level > 0.5', '0.5', None),  # a field of another thing that it does not see
        ('count(world.ring) > 0 and calls > 1', '0.5', None),  # a field of its own that it does not see
        ('t >= 2 h', 'world.level', None),  # in a chance
        ('t >= 2 h', '0.5', 'world.delay'),  # in the wait: an input of another thing
    ],
)
def test_a_choice_that_reads_what_its_actor_does_not_see_is_refused(when, chance, after):
    assert codes(guard(decision(when, chance, after))) == ['sight']
    # The same event without the mark is a mechanism of the actor: it compiles, and no run gives it to
    # a person.
    mechanism = guard(decision(when, chance, after, choice=False))
    assert choices(mechanism) == []
    assert played({'guard.decide': 'reader'}, mechanism) == ['play']


@pytest.mark.parametrize(
    ('each', 'keep', 'after'),
    [
        ('world.level', None, None),  # in the window: a field of another thing that it does not see
        ('calls', None, None),  # in the window: a field of its own that it does not see
        (None, 'world.level < 0.5', '1 h'),  # in the waiting condition: a field that it does not see
        (None, 'calls > 1', '1 h'),  # in the waiting condition: a field of its own
    ],
    ids=['each of another thing', 'each of its own', 'while of another thing', 'while of its own'],
)
def test_a_choice_whose_window_or_waiting_condition_reads_what_its_actor_does_not_see_is_refused(
    each, keep, after
):
    event = decision('t >= 2 h', after=after, each=each, keep=keep)
    assert codes(guard(event)) == ['sight']
    # The same event without the mark is a mechanism of the actor: it compiles, and no run gives it to
    # a person.
    mechanism = guard(decision('t >= 2 h', after=after, each=each, keep=keep, choice=False))
    assert choices(mechanism) == []
    assert played({'guard.decide': 'reader'}, mechanism) == ['play']


@pytest.mark.parametrize(
    ('each', 'keep', 'after'),
    [
        ('world.alarm', None, None),  # the window reads a field that it sees
        (None, 'world.alarm is "on"', '1 h'),  # the waiting condition reads a field that it sees
    ],
    ids=['each', 'while'],
)
def test_a_choice_with_a_window_or_a_waiting_condition_reads_what_its_actor_knows(each, keep, after):
    event = decision('t >= 2 h', after=after, each=each, keep=keep)
    assert choices(guard(event)) == ['guard.decide']
    assert played({'guard.decide': 'reader'}, guard(event)) == []


def test_the_events_of_its_own_are_unseen_until_its_list_names_them():
    # A person can be infected and not know it: owning a fact is not seeing it.
    notice = block('event notice once when t >= 1 h:  @fixture', 'calls -= 1')
    reads_notice = decision('count(notice) > 0')
    assert codes(guard(notice, reads_notice)) == ['sight']
    assert codes(guard(notice, reads_notice, sees='world.alarm, notice')) == []


def test_a_choice_belongs_to_an_actor_and_has_outcomes_to_choose_from():
    assert codes(guard(decision('t >= 2 h'), sees=None)) == ['structure']
    one = block('event decide once when t >= 2 h:  @fixture', 'choice', block('shut:', 'order = "shut"'))
    assert codes(guard(one)) == ['structure']


def test_an_actor_without_choices_is_played_by_chance_alone():
    # Naming the actor is allowed; it has nothing for a reader to choose.
    mechanism = guard(decision('t >= 2 h', choice=False))
    assert played({'guard': 'reader'}, mechanism) == []
    assert choices(mechanism) == []


def observers(*events, sees='world.alarm, world.ring'):
    """Two independently instantiated actors with the same observation contract."""
    return (
        template(
            'Observer',
            f'sees {sees}' if sees else None,
            parameter('odds', 0.5, 'fraction', 0, 1),
            parameter('delay', 2, 'h', 1, 4),
            named('order', 'none', 'shut', 'wait'),
            stock('calls', 3, 'fraction', maximum=3, size=None),
            *events,
            role='operator',
        ),
        entity('first', template='Observer'),
        entity('others', template='Observer', copies=2),
    )


def test_template_observations_bind_own_fields_and_events_for_each_instance_and_copy():
    notice = block('event notice once when t >= 1 h:  @fixture', 'calls -= 1')
    model = compiled(
        document(
            'Inherited sight fixture',
            WORLD,
            *observers(
                notice,
                decision('count(notice) > 0 and calls > 1', chance='odds', after='delay'),
                sees='calls, notice, world.alarm',
            ),
        )
    )
    entities = model.resolve('a').entities
    for name in ('first', 'others_1', 'others_2'):
        assert entities[name].kind == 'operator'
        assert thawed(entities[name].sees) == [
            {'name': 'calls', 'expr': f'{name}.calls', 'kind': 'number', 'unit': 'fraction'},
            {'name': 'notice', 'event': f'{name}.notice'},
            {'name': 'world.alarm', 'expr': 'world.alarm', 'kind': 'state'},
        ]


@pytest.mark.parametrize(
    ('when', 'chance', 'after'),
    [
        ('world.level > 0.5', '0.5', None),
        ('calls > 1', '0.5', None),
        ('t >= 2 h', 'world.level', None),
        ('t >= 2 h', '0.5', 'world.delay'),
    ],
)
def test_the_choices_of_a_template_check_hidden_guards_probabilities_and_delays(when, chance, after):
    # One error for each instance and copy.
    assert codes(*observers(decision(when, chance, after))) == ['sight'] * 3


def test_each_instance_and_copy_of_a_template_makes_its_choices():
    assert choices(*observers(decision('t >= 2 h', chance='odds', after='delay'))) == [
        'first.decide',
        'others_1.decide',
        'others_2.decide',
    ]


def test_template_observations_follow_each_instances_typed_link():
    source = document(
        'Linked observation fixture',
        template('Sensor', stock('reported', 0, 'fraction', maximum=1, size=None)),
        template(
            'Reader',
            'let sensor: Sensor',
            'sees sensor.reported',
            named('order', 'none', 'shut', 'wait'),
            decision('sensor.reported > 0.5'),
        ),
        entity('left_sensor', template='Sensor'),
        entity('right_sensor', template='Sensor'),
        entity('left', 'let sensor = left_sensor', template='Reader'),
        entity('right', 'let sensor = right_sensor', template='Reader'),
    )
    entities = compiled(source).resolve('a').entities
    for side in ('left', 'right'):
        assert thawed(entities[side].sees) == [
            {
                'name': 'sensor.reported',
                'expr': f'{side}_sensor.reported',
                'kind': 'number',
                'unit': 'fraction',
            }
        ]
