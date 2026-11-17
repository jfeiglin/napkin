"""The map of the system (docs/draw.md): what each part reads of another thing, changes and
moves, from the semantic model.

Each model of these tests writes its relations in its own lines, so each expectation follows from the
text of the test: a part relates to a value of another thing when one of its lines names the value.
The catalogue test checks properties of every scenario's map, and that the map covers each link
between two things that the builder derives in its own way (`structure.links`). The map of one
model with every kind of card, part and relation is frozen in `system-map.json`, an independent
expectation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from napkin.core import expr
from napkin.draw import style
from napkin.draw.model_map import (
    ACTOR_NAMES,
    COLUMNS,
    map_payload,
    references,
    system_map,
    variant_of,
)
from napkin.model import resolved
from napkin.model.resolved import Ref
from napkin.model.semantic import flat_entity
from tests.build import (
    DEFAULT_OPTIONS,
    check,
    compiled,
    document,
    entity,
    event,
    flow,
    formula,
    named,
    named_event,
    option,
    options,
    output,
    parameter,
    runs,
    share,
    start,
    status,
    stock,
    template,
    text_value,
)
from tests.helpers import SCENARIO_IDS, catalogue_model


def world(*declarations, option_groups=(DEFAULT_OPTIONS,), run_lines=None):
    return compiled(document('Map fixture', *declarations, option_groups=option_groups, run_lines=run_lines))


def the_map(model, sheet=None):
    """The map of a model, with a stylesheet (the text of a `style.toml`) that its model accepts."""
    sheet = style.read(sheet) if sheet else style.Style()
    assert style.check(sheet, model) == []
    return system_map(model, sheet)


def rows(found):
    """{(kind, by, of, value, part kind, part name, how)} of a map's relations."""
    parts = found['parts']
    return {
        (
            r['kind'],
            r['by'],
            r['of'],
            r['value'],
            parts[r['part']]['kind'],
            parts[r['part']]['name'],
            r.get('how'),
        )
        for r in found['relations']
    }


PLANT = entity(
    'plant',
    named('valve', 'closed', 'open', records='@fixture'),
    stock('store', 100),
    stock('spare', 50),
    stock('released', kind='tally'),
    parameter('delay', 2, 'h', 1, 5),
    parameter('ready', 'true', 'bool'),
    flow('escape', 'store -> released', '0.5 per_h * store', condition='valve is "open"'),
    role='operator',
)


def test_each_part_reads_changes_and_moves_what_its_lines_name():
    model = world(
        PLANT,
        entity(
            'town',
            stock('shelter'),
            flow('evacuate', 'plant.spare -> shelter', '0.1 per_h * plant.spare'),
            role='community',
        ),
        entity(
            'operators',
            event(
                'isolate',
                'plant.valve is "open"',
                'plant.valve = "closed"',
                do_records='@fixture',
            ),
            role='responder',
        ),
    )
    assert rows(the_map(model)) == {
        ('moves', 'town', 'plant', 'plant.spare', 'flow', 'town.evacuate', 'from'),
        ('reads', 'town', 'plant', 'plant.spare', 'flow', 'town.evacuate', None),
        ('reads', 'operators', 'plant', 'plant.valve', 'event', 'operators.isolate', None),
        ('changes', 'operators', 'plant', 'plant.valve', 'event', 'operators.isolate', 'sets'),
    }


def test_an_event_that_waits_reads_its_wait_its_while_and_its_if():
    model = world(
        PLANT,
        entity(
            'operators',
            event(
                'repair',
                't >= 1 h',
                'plant.store += 5 people',
                after='plant.delay',
                keep='plant.valve is "closed"',
                condition='plant.ready',
                do_records='@fixture',
            ),
            role='responder',
        ),
    )
    found = {row[:4] for row in rows(the_map(model))}
    # `+=` changes its target and does not read it.
    assert found == {
        ('reads', 'operators', 'plant', 'plant.delay'),
        ('reads', 'operators', 'plant', 'plant.valve'),
        ('reads', 'operators', 'plant', 'plant.ready'),
        ('changes', 'operators', 'plant', 'plant.store'),
    }
    assert {row[6] for row in rows(the_map(model)) if row[0] == 'changes'} == {'adds'}


@pytest.mark.parametrize(('line', 'how'), [('+=', 'adds'), ('-=', 'takes'), ('=', 'sets')])
def test_a_line_that_changes_a_number_reads_its_amount(line, how):
    model = world(
        PLANT,
        entity(
            'pump',
            parameter('rate_in', 3, 'people/h', 0, 9),
            event('run', 't >= 1 h', f'plant.store {line} rate_in * 1 h', do_records='@fixture'),
            role='operator',
        ),
        entity('meter', parameter('size', 4, 'h', 1, 9), role='environment'),
        entity(
            'gauge',
            event('read', 't >= 2 h', f'plant.spare {line} meter.size * 1 people/h', do_records='@fixture'),
            role='operator',
        ),
    )
    found = rows(the_map(model))
    assert ('changes', 'pump', 'plant', 'plant.store', 'event', 'pump.run', how) in found
    assert ('changes', 'gauge', 'plant', 'plant.spare', 'event', 'gauge.read', how) in found
    assert ('reads', 'gauge', 'meter', 'meter.size', 'event', 'gauge.read', None) in found
    # The amount reads the pump's own input, which no other thing owns, and never the target.
    assert not any(row[0] == 'reads' and row[3] in ('plant.store', 'plant.spare') for row in found)


def test_an_effect_changes_for_its_own_thing_and_its_caller_runs_it():
    # An event that only a line that names it fires is an event of its own thing: the line that names
    # it runs it.
    model = world(
        entity('a', event('go', 't >= 1 h', 'b.f', do_records='@fixture'), role='operator'),
        entity('b', named_event('f', 'c.mode = "on"'), role='operator'),
        entity('c', named('mode', 'off', 'on', records='@fixture'), role='environment'),
    )
    assert rows(the_map(model)) == {
        ('changes', 'a', 'b', 'b.f', 'event', 'a.go', 'runs'),
        ('changes', 'b', 'c', 'c.mode', 'event', 'b.f', 'sets'),
    }


def test_the_start_acts_as_its_thing_and_others_read_its_time():
    model = world(
        entity(
            'plant',
            named('valve', 'closed', 'open', records='@fixture'),
            event('opened', 'valve is "open"'),
            role='operator',
        ),
        entity('attacker', named('access', 'none', 'kept', records='@fixture'), role='adversary'),
        entity('operators', event('notice', 'since(attacker.start) >= 1 h'), role='responder'),
        start('attacker', 'plant.valve = "open"', do_records='@fixture'),
    )
    # The start is the event `start` of its thing.
    assert rows(the_map(model)) == {
        ('changes', 'attacker', 'plant', 'plant.valve', 'event', 'attacker.start', 'sets'),
        ('reads', 'operators', 'attacker', 'attacker.start', 'event', 'operators.notice', 'time'),
    }


def test_a_flow_moves_the_material_of_each_end_of_another_thing():
    model = world(
        PLANT,
        entity(
            'town',
            stock('got'),
            flow('take', ['plant.spare -> got', 'outside -> plant.released'], '1 people/h'),
            role='community',
        ),
    )
    # The town's own end and the end outside the model are not relations.
    assert rows(the_map(model)) == {
        ('moves', 'town', 'plant', 'plant.spare', 'flow', 'town.take', 'from'),
        ('moves', 'town', 'plant', 'plant.released', 'flow', 'town.take', 'to'),
    }


def test_outputs_and_checks_add_nothing_to_the_map():
    model = world(
        PLANT,
        entity(
            'town',
            stock('shelter'),
            check('shelter <= plant.store + plant.spare + 1000 people', 'The shelter holds what it can.'),
            output('watched', 'plant.store', 'people', 'level'),
            role='community',
        ),
        output('total', 'plant.store', 'people', 'level'),
    )
    assert rows(the_map(model)) == set()


def test_an_allocation_reads_its_limit_and_shares_the_flows_of_other_things():
    model = world(
        entity(
            'plant',
            stock('store', 100),
            share('store', 'operators.capacity', ['a.take_a', 'b.take_b']),
            role='operator',
        ),
        entity('a', stock('got_a'), flow('take_a', 'plant.store -> got_a', '3 people/h'), role='community'),
        entity('b', stock('got_b'), flow('take_b', 'plant.store -> got_b', '2 people/h'), role='community'),
        entity('operators', parameter('capacity', 4, 'people/h', 0, 9), role='responder'),
    )
    found = rows(the_map(model))
    # The share of a stock is named after it: `share_store`.
    assert {row for row in found if row[1] == 'plant'} == {
        ('reads', 'plant', 'operators', 'operators.capacity', 'share', 'plant.share_store', None),
        ('changes', 'plant', 'a', 'a.take_a', 'share', 'plant.share_store', 'shares'),
        ('changes', 'plant', 'b', 'b.take_b', 'share', 'plant.share_store', 'shares'),
    }


def test_a_part_reads_a_formula_of_another_thing_and_not_what_the_formula_reads():
    model = world(
        PLANT,
        entity('plume', formula('ratio', 'plant.store / 1 h', 'people/h'), role='environment'),
        entity(
            'town', stock('exposed'), flow('expose', 'outside -> exposed', 'plume.ratio'), role='community'
        ),
    )
    assert rows(the_map(model)) == {
        ('reads', 'plume', 'plant', 'plant.store', 'formula', 'plume.ratio', None),
        ('reads', 'town', 'plume', 'plume.ratio', 'flow', 'town.expose', None),
    }


def test_a_set_of_copies_is_one_card_and_each_instance_is_a_card():
    model = world(
        PLANT,
        template(
            'Wave',
            stock('people'),
            flow('arrive', 'outside -> people', '0.01 per_h * plant.store'),
            role='community',
        ),
        entity('waves', template='Wave', copies=3),
        entity('north', template='Wave'),
        entity('south', template='Wave'),
    )
    found = the_map(model)
    nodes = {node['id']: node for node in found['nodes']}
    assert set(nodes) == {'plant', 'waves', 'north', 'south'}
    assert (nodes['waves']['members'], nodes['waves']['copies']) == (['waves_1', 'waves_2', 'waves_3'], 3)
    assert nodes['north']['copies'] is None
    # One relation for the set, whose copies share their parts, and one for each instance.
    assert {row[:4] for row in rows(found)} == {
        ('reads', card, 'plant', 'plant.store') for card in ('waves', 'north', 'south')
    }


ACCESS = options(
    'Access',
    option('None', 'No access.'),
    option(
        'Kept', 'Kept access.', 'attacker.access = "kept"  @fixture', 'town.shelter = plant.spare  @fixture'
    ),
)


def test_a_run_leaves_out_the_parts_that_its_structure_leaves_out():
    model = world(
        PLANT,
        entity(
            'attacker',
            named('access', 'none', 'kept', records='@fixture'),
            event(
                'get_in',
                't >= 1 h',
                'plant.valve = "open"',
                once=False,
                transition='access "none" -> "kept"',
                do_records='@fixture',
            ),
            role='adversary',
        ),
        entity('town', stock('shelter'), role='community'),
        option_groups=(ACCESS,),
        run_lines=runs(a=['None'], b=['Kept']),
    )
    found = the_map(model)
    parts = found['parts']
    get_in = next(i for i, part in enumerate(parts) if part['name'] == 'attacker.get_in')
    start_value = next(i for i, part in enumerate(parts) if part['kind'] == 'option')
    none, kept = (found['variants'][variant_of(model, run)] for run in ('a', 'b'))
    assert (none['starts'], kept['starts']) == ([], ['Kept'])
    # With access kept from the start, the event that gets in cannot happen; the profile's start
    # value acts only where its profile sets the start.
    assert get_in not in none['lacks'] and get_in in kept['lacks']
    assert start_value in none['lacks'] and start_value not in kept['lacks']
    arrows = lambda variant: {(a['from'], a['to'], a['kind']) for a in variant['arrows']}  # noqa: E731
    assert ('attacker', 'plant', 'changes') in arrows(none) - arrows(kept)
    assert ('plant', 'town', 'reads') in arrows(kept) - arrows(none)


def test_one_arrow_for_each_ordered_pair_and_kind():
    model = world(
        PLANT,
        entity(
            'operators',
            event(
                'watch',
                'plant.valve is "open" and plant.ready',
                'plant.valve = "closed"',
                do_records='@fixture',
            ),
            event('check', 't >= plant.delay'),
            event('open_up', 't >= 1 h', 'plant.valve = "open"', do_records='@fixture'),
            role='responder',
        ),
    )
    (variant,) = the_map(model)['variants']
    # Two parts read three values of the plant, and two change one.
    assert sorted((a['from'], a['to'], a['kind'], a['values']) for a in variant['arrows']) == [
        ('operators', 'plant', 'changes', 1),
        ('plant', 'operators', 'reads', 3),
    ]


def test_the_map_draws_what_the_stylesheet_does_not_hide_in_the_order_of_the_file():
    model = world(
        PLANT,
        entity(
            'town',
            stock('shelter'),
            flow('evacuate', 'plant.spare -> shelter', '1 people/h'),
            role='community',
        ),
        entity('operators', event('look', 'plant.valve is "open"'), role='responder'),
    )
    found = the_map(model, '[layout]\nhide = ["operators"]\n')
    assert [node['id'] for node in found['nodes'] if node['drawn']] == ['plant', 'town']
    assert [node['id'] for node in found['nodes'] if not node['drawn']] == ['operators']
    # A thing that the map does not draw keeps its relations, and no arrow touches it.
    assert any(r['by'] == 'operators' for r in found['relations'])
    assert all('operators' not in (a['from'], a['to']) for v in found['variants'] for a in v['arrows'])


def test_the_columns_follow_the_roles_in_their_fixed_order():
    roles = ['community', 'clinician', 'environment', 'responder', 'crew', 'operator', 'adversary']
    model = world(*(entity(f'thing_{i}', stock('x'), role=role) for i, role in enumerate(roles)))
    found = the_map(model)
    order = [column['role'] for column in found['columns']]
    # A role that names an entity sits after the operators and before the responders.
    expected = [role for role in COLUMNS if role in roles]
    expected.insert(expected.index('operator') + 1, 'crew')
    assert order == expected
    for node in found['nodes']:
        assert found['columns'][node['column']]['role'] == node['role']


def test_each_card_has_the_icon_of_its_stylesheet_or_of_its_role():
    model = world(PLANT, entity('town', stock('shelter'), role='community'))
    found = the_map(model, '[icon]\nfactory = ["plant"]\n')
    icons = {node['id']: node['icon'] for node in found['nodes']}
    assert icons == {'plant': 'factory', 'town': style.ROLE_ICONS['community']}


def test_a_part_keeps_the_text_of_its_first_card_with_its_braces_named():
    model = world(
        entity(
            'operators',
            text_value('actor', 'The operators'),
            event('look', 't >= 1 h', doc='{actor} look at the plant.'),
            role='responder',
        ),
    )
    (part,) = [part for part in the_map(model)['parts'] if part['kind'] == 'event']
    # `map_payload` fills the brace for each run, in the label of the part.
    assert part['text'] == '{operators.actor} look at the plant.'


# ---- every scenario --------------------------------------------------------------------------------


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_map_of_every_scenario_holds_its_properties(scenario_id):
    model = catalogue_model(scenario_id)
    found = system_map(model)
    nodes = {node['id']: node for node in found['nodes']}
    drawn = [node['id'] for node in found['nodes'] if node['drawn']]
    lines = style.entity_lines(model)
    # Each entity line is one card, and the map draws what the stylesheet says.
    assert list(nodes) == sorted(nodes, key=lambda entry: (entry not in drawn, list(lines).index(entry)))
    assert set(nodes) == set(lines) and drawn == style.drawn(style.of(model), model)
    # An icon, or none for a thing whose role has no icon and that the stylesheet gives none.
    assert all(node['icon'] is None or node['icon'] in style.ICONS for node in nodes.values())
    for relation in found['relations']:
        assert relation['by'] != relation['of'] and relation['value'] in found['values']
        assert found['values'][relation['value']]['node'] == relation['of']
        assert found['parts'][relation['part']]['node'] == relation['by']
    assert all(part['line'] for part in found['parts'])
    for variant in found['variants']:
        held = [r for r in found['relations'] if r['part'] not in set(variant['lacks'])]
        aggregate = {}
        for r in held:
            if r['by'] in drawn and r['of'] in drawn:
                ends = (r['of'], r['by']) if r['kind'] == 'reads' else (r['by'], r['of'])
                aggregate.setdefault((*ends, r['kind']), set()).add(r['value'])
        assert {(a['from'], a['to'], a['kind']): a['values'] for a in variant['arrows']} == {
            key: len(values) for key, values in aggregate.items()
        }
    # The builder derives the links between things in its own way: each is a relation of the map.
    related = {(r['by'], r['of']) for r in found['relations']}
    card_of = {entity.name.replace('.', '_'): entity.entry for entity in model.scenario.entities}
    for starts, whole in model.whole.items():
        for host, targets in whole.links.items():
            for target in targets:
                # A link reaches a part of the entity that the first part of its name names.
                owner = target.split('.')[0]
                if host in card_of and owner in card_of and card_of[host] != card_of[owner]:
                    covered = (card_of[host], card_of[owner]) in related
                    assert covered or through_formula(model, found, card_of[host], target), (
                        starts,
                        host,
                        target,
                    )


def through_formula(model, found, card, target):
    """Whether a card reads a formula of another thing that reads `target` (`entity.value`), directly or
    through the formulas that it reads: the builder writes a yes/no formula, and each formula that it
    reads, into each part that reads it, so its link reaches what those formulas read."""
    owner, _, member = target.rpartition('.')
    by_name = {
        (flat_entity(thing.name), value.name): value
        for thing in model.scenario.entities
        for value in thing.values
    }

    def reaches(formula, seen):
        for ref in references(formula.node):
            if not isinstance(ref, Ref):
                continue
            key = (flat_entity(ref.entity), ref.member)
            if key == (owner, member):
                return True
            inner = by_name.get(key)
            if key not in seen and inner is not None and inner.formula is not None:
                seen.add(key)
                if reaches(inner.formula, seen):
                    return True
        return False

    for relation in found['relations']:
        value = found['values'][relation['value']]
        if relation['by'] != card or relation['kind'] != 'reads' or value['kind'] != 'formula':
            continue
        entry, _, name = relation['value'].rpartition('.')
        formulas = [
            thing.value(name).formula
            for thing in model.scenario.entities
            if thing.entry == entry and thing.value(name) is not None
        ]
        if any(formula is not None and reaches(formula, set()) for formula in formulas):
            return True
    return False


# ---- the map with its words ------------------------------------------------------------------------

FIXTURE = Path(__file__).with_name('system-map.json')
FIXTURE_STYLE = '[layout]\nhide = ["town"]\n\n[icon]\nfactory = ["plant"]\n'


def fixture_model():
    """A map with every kind of card, part and relation, two variants and a run that changes a text."""
    return world(
        entity(
            'attacker',
            text_value('actor', 'The AI'),
            named('access', 'none', 'kept', records='@fixture'),
            event(
                'strike',
                't >= 1 h',
                'plant.valve = "open"',
                once=False,
                transition='access "none" -> "kept"',
                doc='{actor} opens the valve.',
                do_records='@fixture',
            ),
            role='adversary',
        ),
        entity(
            'plant',
            named('valve', 'closed', 'open', records='@fixture'),
            stock('store', 100),
            stock('spare', 50),
            stock('released', kind='tally'),
            flow(
                'escape',
                'store -> released',
                '0.5 per_h * store',
                condition='valve is "open"',
                doc='Gas escapes.',
            ),
            status(('failed', 'valve is "open"', 'Leaking'), ('ok', None, 'Closed')),
            role='operator',
        ),
        entity(
            'operators',
            parameter('reaction', 2, 'h', 1, 5),
            event(
                'isolate',
                'since(attacker.strike) >= reaction',
                'plant.valve = "closed"',
                doc='The operators close the valve.',
                do_records='@fixture',
            ),
            role='responder',
        ),
        template(
            'Ward',
            stock('people'),
            flow('arrive', 'outside -> people', '0.01 per_h * plant.store'),
            role='community',
        ),
        entity('wards', template='Ward', copies=2),
        entity(
            'town',
            stock('shelter'),
            flow('evacuate', 'plant.spare -> shelter', '1 people/h'),
            role='community',
        ),
        option_groups=(
            options(
                'Attacker',
                option('AI', 'An AI agent.'),
                option('Human', 'A human team.', 'attacker.actor = "The human team"'),
            ),
            options(
                'Access',
                option('None', 'No access.'),
                option('Kept', 'Kept access.', 'attacker.access = "kept"  @fixture'),
            ),
        ),
        run_lines=runs(a=['AI', 'None'], b=['Human', 'Kept']),
    )


def test_the_map_of_the_fixture_model_is_the_frozen_map():
    model = fixture_model()
    sheet = style.read(FIXTURE_STYLE)
    assert style.check(sheet, model) == []
    found, run_maps = map_payload(model, sheet)
    assert json.loads(FIXTURE.read_text(encoding='utf-8')) == {'map': found, 'runs': run_maps}


def test_the_words_of_the_map_name_who_acts_and_each_run_names_its_variant_and_its_labels():
    model = fixture_model()
    found, run_maps = map_payload(model)
    # No thing of the model is named after a role: each column takes the words for its role.
    assert [column['label'] for column in found['columns']] == [
        ACTOR_NAMES[column['role']] for column in found['columns']
    ]
    # Each run names the variant of its start-state options: only b's option Kept sets a start value.
    starts = {run: found['variants'][item['variant']]['starts'] for run, item in run_maps.items()}
    assert starts == {'a': [], 'b': ['Kept']}
    # The test's own texts: the model's actor in the part's label, and the run whose profile gives the
    # actor another text has its own label for the part.
    strike = next(i for i, part in enumerate(found['parts']) if part['name'] == 'attacker.strike')
    assert found['parts'][strike]['label'] == 'The AI opens the valve.'
    assert run_maps['a']['labels'] == {}
    assert run_maps['b']['labels'] == {str(strike): 'The human team opens the valve.'}


def test_a_column_of_a_role_that_names_a_thing_takes_the_title_of_the_thing():
    model = world(
        entity('crew', stock('x'), title='Line crew', role='responder'),
        entity('truck', stock('y'), role='crew'),
        entity('meter', stock('z'), role='field_team'),
    )
    found, _ = map_payload(model)
    # A role that names no thing reads as its name in words.
    assert {column['role']: column['label'] for column in found['columns']} == {
        'responder': ACTOR_NAMES['responder'],
        'crew': 'Line crew',
        'field_team': 'Field team',
    }


def test_the_names_that_an_expression_reads_hold_those_of_an_argument_by_name():
    """A call with arguments by name reads the values of its arguments: by position first, then by
    name, each in its order."""
    low, wide, high = (resolved.ref('plant', member, member) for member in ('low', 'wide', 'high'))
    call = resolved.named(
        'normal',
        [expr.binary('add', low, expr.const(1))],
        [('max', high), ('sd', expr.call('abs', [wide]))],
    )
    assert list(references(expr.binary('mul', expr.const(2), call))) == [low, high, wide]
