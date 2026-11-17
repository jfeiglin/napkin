"""The views that tooling reads of a model (docs/python-api.md, "Views")."""

from __future__ import annotations

from napkin.model.views import actors, instances
from tests.build import block, compiled, document, entity, named, play_scenario, stock, template
from tests.model.test_sight import WORLD, decision, observers


def test_actors_list_what_they_see_and_their_choices():
    (guard,) = actors(compiled(play_scenario()))
    assert guard['name'] == 'guard'
    assert guard['sees'] == ['world.alarm', 'world.level', 'world.delay', 'world.ring', 'world.late']
    assert [(c['event'], [o['name'] for o in c['outcomes']]) for c in guard['choices']] == [
        ('guard.first', ['shut', 'wait']),
        ('guard.second', ['shut', 'wait']),
    ]


def test_each_copy_lists_its_choices_and_a_mechanism_is_not_one():
    members = observers(
        decision('t >= 2 h'), block('event tally once when t >= 1 h:  @fixture', 'calls -= 1')
    )
    found = {item['name']: item['choices'] for item in actors(compiled(document('Views', WORLD, *members)))}
    assert sorted(found) == ['first', 'others.1', 'others.2']
    assert found['others.1'] == [
        {
            'event': 'others_1.decide',
            'label': None,
            'outcomes': [{'name': 'shut', 'label': None}, {'name': 'wait', 'label': None}],
        }
    ]


def test_instances_give_each_instance_its_links():
    source = document(
        'Linked views fixture',
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
    model = compiled(source)
    assert [(item['name'], item['links']) for item in instances(model, 'Reader')] == [
        ('left', {'sensor': 'left_sensor'}),
        ('right', {'sensor': 'right_sensor'}),
    ]
    assert [item['name'] for item in instances(model, 'Sensor')] == ['left_sensor', 'right_sensor']
