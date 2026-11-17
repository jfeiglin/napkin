"""The panels under the map (napkin/draw/panels.py, D-53, D-55, D-57): `[equations]` and `[references]`
in `style.toml`, the blocks of the shown cards, the Symbols table, the marks and the References list,
and the LaTeX of the lines and of `napkin draw --latex FILE`.

The synthetic model writes its own things and templates, and its records come from the test library of
`test_references.py`, so each expectation follows from the model, the library and the rule that the
test names: the blocks are those of the cards that `things` names (`equations.Equations`, `same`); the
symbols cover the keys of the trees, which the test reads from the trees themselves; the marks name the
entries and an input on an assumption has one; a range is the model's, read by the run table; the
LaTeX of each line reads back to its trees with the reader of the tests (`latex_subset.py`). The
catalogue test draws every card of every scenario.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from napkin import cli
from napkin.draw import layout as layouts
from napkin.draw import notation, panels, style
from napkin.draw import references as refs
from napkin.draw.equations import Equations, generic, same
from napkin.draw.model_map import picture
from napkin.draw.notation import Assign, Count, Deriv, Elapsed, Since, Sym, from_dict, split
from napkin.draw.style import StyleError
from napkin.model.runs import Runs
from napkin.model.types import number_in, written_unit
from tests.build import (
    check,
    compiled,
    document,
    entity,
    event,
    flow,
    formula,
    named,
    option,
    options,
    parameter,
    runs,
    share,
    stock,
    template,
)
from tests.draw.latex_subset import read, read_line
from tests.draw.test_notation import Point, canonical, outcome, shape, value_of_node
from tests.draw.test_notation import same as same_value
from tests.draw.test_picture import picture_problems
from tests.draw.test_references import RECORDS, own_library
from tests.draw.test_style import MODEL, built
from tests.helpers import SCENARIO_IDS, catalogue_model

# ---- the model ------------------------------------------------------------------------------------


def line(text, records='@fixture'):
    return f'{text}  {records}'


OTHER = 'record other: identity "Another record of the fixture."'

# A template whose instances share their trees (north, south and the copies of waves) and one whose
# formula is its own (east); a thing whose tag is the template's initial (zebra); and a thing with a
# flow of two pairs, one at its own rate, beside a flow of the same initial (fill, flush), events that
# read the time since an event and its count, a check, and inputs on records of every kind. The
# option Busy sets an input with a record of its own.
FIXTURE = document(
    'Panels fixture',
    template(
        'Zone',
        parameter('k', 0.5, 'fraction', 0, 1, records='@rec_assumed'),
        stock('level', 10, 'people', maximum=100, size=None, records='@rec_counted'),
        stock('done', 'k * 10 people', 'people', size=None, records='@rec_counted'),
        formula('pull', 'k * level / (1 h)', 'people/h', records='@rec_direct_first'),
        flow('drain', 'level -> done', 'pull', records='@rec_counted'),
    ),
    entity('north', template='Zone'),
    entity('south', template='Zone'),
    entity('east', line('let pull: people/h = 2 * k * level / (1 h)', '@rec_rule'), template='Zone'),
    entity('waves', template='Zone', copies=2),
    entity('zebra', stock('herd', 4, 'people', size=None, rate='0.1 per_h * herd')),
    entity(
        'hub',
        parameter('x', 2, 'people/h', 1, 9, records='@rec_transfer'),
        parameter('y', 3, 'people/h', records='@rec_direct_second'),
        parameter('quiet', 1, 'people/h', 0, 5, records='@rec_hidden'),
        parameter('base', 4, 'people', records='@rec_assumed'),
        named('mode', 'idle', 'busy'),
        stock('store', 50, 'people', size=None, records='@rec_counted'),
        stock('spare', '2 * base', 'people', size=None),
        stock('used', 0, 'people', size=None),
        formula('give', 'x / 2 + y', 'people/h', records='@rec_rule_plain'),
        formula('ready', 'mode is "busy" and since(go) >= 1 h', 'bool', records='@rec_rule_plain'),
        flow('fill', ['store -> spare', line('spare -> used at 0.5 * x', '@other')], 'give'),
        flow('flush', 'store -> used', 'x + count(go) * 1 people/h', condition='ready'),
        share('store', '3 * x'),
        event('go', 'mode is "busy" and t >= 1 h', 'store -= 1 people'),
        event('later', 'since(go) >= 2 h and count(go) >= 1', 'move 1 people from store to spare'),
        check('store + spare + used is 55 people', 'A sum', within='1 people'),
    ),
    option_groups=(
        options(
            'Response',
            option('Idle', 'It waits.'),
            option(
                'Busy', 'It works.', line('hub.mode = "busy"'), line('hub.x = 4 people/h', '@rec_assumed')
            ),
        ),
    ),
    run_lines=runs(a=['Idle'], b=['Busy']),
    records=(*RECORDS, OTHER),
)
CARDS = ('north', 'south', 'east', 'waves', 'zebra', 'hub')


@pytest.fixture(scope='module')
def model():
    return compiled(FIXTURE, own_library())


def sheet_of(text=''):
    return style.read(text)


def drawn(model, text, run=None):
    """The picture of the model with the stylesheet `text`, which keeps the picture contract."""
    sheet = sheet_of(text)
    assert style.check(sheet, model) == []
    doc = picture(model, sheet, run)
    assert picture_problems(doc) == []
    return doc


def equations(*things, more=''):
    listed = ', '.join(f'"{name}"' for name in things)
    return f'[equations]\nthings = [{listed}]\n{more}'


def test_a_yes_no_formula_is_written_with_iff_and_a_number_formula_with_equals(model):
    doc = drawn(model, equations('hub'))
    lines = {line['part']: line for block in doc['panels']['equations'] for line in block['lines']}
    ready, give = lines['hub.ready'], lines['hub.give']
    assert (ready['kind'], ready['relation']) == ('formula', '⇔')
    assert r' \iff ' in ready['latex'] and ' = ' not in ready['latex'].split(r' \iff ')[0]
    # A counterexample: a formula of a number keeps `=`.
    assert give['relation'] == '=' and ' = ' in give['latex'] and r'\iff' not in give['latex']
    # The fragment aligns each equation at its relation.
    text = panels.latex(doc)
    assert ready['latex'].replace(r' \iff ', r' &\iff ', 1) in text
    assert give['latex'].replace(' = ', ' &= ', 1) in text


def named_by(data):
    """The keys that a tree (a node of the notation as a dict) names, read here from its nodes."""
    out = set()
    for node in notation.nodes(from_dict(data)):
        if isinstance(node, (Sym, Elapsed, Deriv)):
            out.add(node.key)
        elif isinstance(node, (Since, Count)):
            out.add(node.target)
    return out


def start_trees(row):
    return [row['value_math'], *(o['math'] for o in row['options']), *(i['math'] for i in row['instances'])]


@pytest.mark.parametrize('more', ['', 'instances = "each"\n'])
def test_a_start_that_a_formula_sets_is_math_and_what_it_reads_has_a_row(model, more):
    doc = drawn(model, equations('Zone', 'hub', more=more))
    rows = {row['key']: row for row in doc['panels']['symbols']}
    starts = [(key, data) for key, row in rows.items() for data in start_trees(row) if data is not None]
    for key, data in starts:
        assert named_by(data) <= set(rows), key
    # Each stock `done` starts at `k * 10 people` of its own card, or of its template when the row
    # stands for the template's members: the start names the `k` of the row's own owner.
    dones = {key: row for key, row in rows.items() if key.endswith('.done')}
    assert dones
    for key, row in dones.items():
        owner = split(key)[0]
        assert named_by(row['value_math']) == {f'{owner}.k'}, key
    # Written once for the members that are the same, else once for each member.
    assert ('Zone.done' in dones) == (not more)


def test_a_formula_start_shows_the_values_that_it_reads_and_a_number_start_stays_text(model):
    doc = drawn(model, equations('hub') + '\n[references]\nshow = true\n')
    rows = {row['key']: row for row in doc['panels']['symbols']}
    reserve, base = rows['hub.spare'], rows['hub.base']
    assert named_by(reserve['value_math']) == {'hub.base'}
    # The value that it reads has its row, its value and the marks of its record.
    assert base['value'] is not None and base['marks']
    # A start worked out from others has no mark of its own (it leads to the marks of `base`).
    assert reserve['marks'] == []
    # Counterexamples: a number start and a named state's start stay text.
    assert rows['hub.store']['value_math'] is None and rows['hub.store']['value'] is not None
    if 'hub.mode' in rows:
        assert rows['hub.mode']['value_math'] is None
    # The LaTeX table writes the start as math with the table's symbols.
    (line,) = [
        row for row in panels.latex(doc).splitlines() if row.startswith(f'${reserve["symbol"]["latex"]}$')
    ]
    value_cell = line.split(' & ')[3]
    assert value_cell.startswith('$') and base['symbol']['latex'] in value_cell


def test_a_template_block_says_which_subscript_stands_for_which_member(model):
    doc = drawn(model, equations('Zone'))
    found = doc['panels']
    (block,) = [item for item in found['equations'] if item['name'] == 'Zone']
    assert len(block['members']) > 1 and block['subscript']
    # The template's symbols carry its subscript, and each member's is that of its own card: the tags
    # of the card's stock rows carry it.
    rows = {row['key']: row for row in found['symbols']}
    assert all(
        rows[key]['symbol']['sub'].split(',')[0] == block['subscript']
        for key in rows
        if key.startswith('Zone.')
    )
    for member in block['members']:
        # (The copies of one line share their card, and its tags.)
        tags = [text for key, text in found['tags'].items() if split(key)[0] == member['card']]
        assert tags and all(text.split('_', 1)[1].split(',')[0] == member['subscript'] for text in tags)
    said = f'({block["subscript"]}: ' + ', '.join(member['subscript'] for member in block['members']) + ').'
    assert said in panels.latex(doc)
    # A block of one member says nothing of subscripts.
    single = drawn(model, equations('east'))['panels']['equations'][0]
    assert single['subscript'] is None and len(single['members']) == 1


def members(doc):
    return [[member['entity'] for member in block['members']] for block in doc['panels']['equations']]


# ---- [equations] and [references] -----------------------------------------------------------------


def test_without_equations_there_is_no_panel_and_the_settings_have_their_defaults(model):
    assert drawn(model, '')['panels'] is None
    assert style.equation_settings(style.Style()) == {
        'depth': 1,
        'width': 720,
        'lines': 3,
        'tags': True,
        'symbols': True,
        'checks': False,
        'instances': 'together',
        'references': False,
        'kinds': list(style.REFERENCE_KINDS),
    }


def test_the_keys_of_equations_and_references_are_read_at_both_ends_of_their_ranges(model):
    for depth, width, lines in ((0, 320, 1), (5, 2400, 8)):
        text = equations(
            'hub',
            more=f'depth = {depth}\nwidth = {width}\nlines = {lines}\ntags = false\nsymbols = false\n'
            'checks = true\ninstances = "each"\n\n[references]\nshow = true\nkinds = ["assumption", "source"]\n',
        )
        found = drawn(model, text)['panels']['settings']
        assert found == {
            'depth': depth,
            'width': width,
            'lines': lines,
            'tags': False,
            'symbols': False,
            'checks': True,
            'instances': 'each',
            'references': True,
            'kinds': ['source', 'assumption'],
        }
    # The kinds of reference are those of the References list.
    assert style.REFERENCE_KINDS == panels.refs.KINDS


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('[equations]\nthing = ["north"]\n', 'equations.thing', 'not a key that this file reads'),
        ('[equations]\nthings = "north"\n', 'equations.things', 'list of names'),
        ('[equations]\nthings = ["north", "north"]\n', 'equations.things', 'names north twice'),
        ('[equations]\nthings = ["north"]\ndepth = 6\n', 'equations.depth', 'from 0 to 5'),
        ('[equations]\nthings = ["north"]\ndepth = -1\n', 'equations.depth', 'from 0 to 5'),
        ('[equations]\nthings = ["north"]\ndepth = true\n', 'equations.depth', 'from 0 to 5'),
        ('[equations]\nthings = ["north"]\ndepth = 1.5\n', 'equations.depth', 'from 0 to 5'),
        ('[equations]\nthings = ["north"]\nwidth = 319\n', 'equations.width', 'px from 320 to 2400'),
        ('[equations]\nthings = ["north"]\nwidth = 2401\n', 'equations.width', 'px from 320 to 2400'),
        ('[equations]\nthings = ["north"]\nlines = 0\n', 'equations.lines', 'from 1 to 8'),
        ('[equations]\nthings = ["north"]\nlines = 9\n', 'equations.lines', 'from 1 to 8'),
        ('[equations]\nthings = ["north"]\ntags = "yes"\n', 'equations.tags', 'true or false'),
        ('[equations]\nthings = ["north"]\nsymbols = 1\n', 'equations.symbols', 'true or false'),
        ('[equations]\nthings = ["north"]\nchecks = "no"\n', 'equations.checks', 'true or false'),
        ('[equations]\nthings = ["north"]\ninstances = "all"\n', 'equations.instances', '"together", "each"'),
        ('equations = 1\n', 'equations', 'is a table'),
        ('[references]\nshow = true\n', 'references.show', 'needs \\[equations\\]'),
        (
            '[equations]\nthings = []\n\n[references]\nshow = true\n',
            'references.show',
            'needs \\[equations\\]',
        ),
        (
            '[equations]\nthings = ["north"]\n\n[references]\nshow = "yes"\n',
            'references.show',
            'true or false',
        ),
        ('[equations]\nthings = ["north"]\n\n[references]\nlist = true\n', 'references.list', 'not a key'),
        ('[references]\nkinds = "source"\n', 'references.kinds', 'list of kinds'),
        (
            '[references]\nkinds = ["source", "claim", "assumption"]\n',
            'references.kinds',
            'claim, which is not',
        ),
        ('[references]\nkinds = ["source", "source", "assumption"]\n', 'references.kinds', 'source twice'),
        ('[references]\nkinds = ["source", "identity"]\n', 'references.kinds', 'keeps "assumption"'),
        ('[references]\nkinds = []\n', 'references.kinds', 'keeps "assumption"'),
    ],
)
def test_each_key_of_equations_and_references_has_its_form(text, key, match):
    with pytest.raises(StyleError, match=match) as caught:
        style.read(text)
    assert [d['key'] for d in caught.value.diagnostics] == [key]


@pytest.mark.parametrize(
    ('text', 'match'),
    [
        ('[equations]\nthings = ["nowhere"]\n', 'nowhere is not a template or a thing'),
        ('[equations]\nthings = ["Depot"]\n', 'Depot is not on the map: it has no instance'),
        ('[layout]\nhide = ["Ward"]\n\n[equations]\nthings = ["east"]\n', 'layout.hide hides it'),
        ('[layout]\nhide = ["east"]\n\n[equations]\nthings = ["Ward"]\n', None),
    ],
)
def test_the_things_of_equations_are_things_and_templates_that_the_picture_draws(tmp_path, text, match):
    found = built(tmp_path, text)
    if match is None:
        # A template with one instance on the map is a name that the picture draws.
        assert style.check(style.of(found), found) == []
        return
    with pytest.raises(StyleError, match=match) as caught:
        style.of(found)
    assert [d['key'] for d in caught.value.diagnostics] == ['equations.things']


@pytest.mark.parametrize(
    ('text', 'key'),
    [
        ('[equations]\nthings = ["north"]\ndepth = 9\n', 'equations.depth'),
        ('[equations]\nthings = ["nowhere"]\n', 'equations.things'),
        ('[references]\nshow = true\n', 'references.show'),
        ('[equations]\nthings = ["north"]\n\n[references]\nkinds = ["source"]\n', 'references.kinds'),
    ],
)
def test_compile_and_draw_stop_on_a_problem_of_the_panels(tmp_path, monkeypatch, capsys, text, key):
    folder = tmp_path / 'wards'
    folder.mkdir()
    (folder / 'model.scn').write_text(MODEL, encoding='utf-8')
    sheet = folder / style.STYLE_FILE
    sheet.write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    for command in ('compile', 'draw'):
        assert cli.main([command, 'wards']) == 1, command
        assert f'{Path("wards", style.STYLE_FILE)}: error: {key}: ' in capsys.readouterr().err
    assert not list(tmp_path.glob('*.svg'))
    sheet.write_text(
        '[equations]\nthings = ["north", "Ward"]\n\n[references]\nshow = true\n', encoding='utf-8'
    )
    assert cli.main(['compile', 'wards']) == 0


# ---- the blocks -----------------------------------------------------------------------------------


def entities_of(model, cards):
    return [entity.name for entity in model.scenario.entities if entity.entry in cards]


def check_blocks(model, doc, named):
    """The blocks stand for exactly the entities of the shown cards, each once, in the order of the
    cards: a card that `named` names itself, or whose template it names. A group of two or more has one
    template, and its members' blocks are the same up to the entity; with `together`, no two blocks of
    one template could be one."""
    lines = style.entity_lines(model)
    shown = [
        card['id'] for card in doc['cards'] if card['id'] in named or lines[card['id']].template in named
    ]
    listed = [name for group in members(doc) for name in group]
    assert sorted(listed) == sorted(entities_of(model, shown))
    assert len(set(listed)) == len(listed)
    order = [card['id'] for card in doc['cards']]
    firsts = [order.index(block['members'][0]['card']) for block in doc['panels']['equations']]
    assert firsts == sorted(firsts)
    eq = Equations(model, doc['run'])
    settings = doc['panels']['settings']
    built_blocks = {
        name: eq.block(name, depth=settings['depth'], checks=settings['checks']) for name in listed
    }
    for block in doc['panels']['equations']:
        names = [member['entity'] for member in block['members']]
        if len(names) > 1:
            assert block['template'] is not None
            assert all(same(built_blocks[names[0]], built_blocks[name]) for name in names)
        if settings['instances'] == 'each':
            assert len(names) == 1
    if settings['instances'] == 'together':
        # Two blocks of instances that `named` does not name itself are never the same.
        alone = [
            block
            for block in doc['panels']['equations']
            if all(member['card'] not in named for member in block['members'])
        ]
        for a in alone:
            for b in alone:
                if (
                    a is not b
                    and lines[a['members'][0]['card']].template == lines[b['members'][0]['card']].template
                ):
                    first, second = a['members'][0]['entity'], b['members'][0]['entity']
                    assert not same(built_blocks[first], built_blocks[second]), (first, second)


@pytest.mark.parametrize(
    ('things', 'instances'),
    [
        (('Zone',), 'together'),
        (('Zone',), 'each'),
        (('Zone', 'north'), 'together'),
        (('Zone', 'waves'), 'together'),
        (('waves',), 'together'),
        (('waves',), 'each'),
        (CARDS, 'together'),
        (('hub', 'zebra'), 'each'),
    ],
)
def test_the_panel_holds_the_blocks_of_the_shown_cards(model, things, instances):
    doc = drawn(model, equations(*things, more=f'instances = "{instances}"\n'))
    check_blocks(model, doc, set(things))


def test_instances_with_the_same_trees_share_a_block_and_a_thing_beats_its_template(model):
    # The instances of Zone whose trees are the same up to the instance share one block, and east,
    # whose formula is its own, has its own; a thing that the list names has its own block.
    assert members(drawn(model, equations('Zone'))) == [['north', 'south', 'waves.1', 'waves.2'], ['east']]
    assert members(drawn(model, equations('Zone', 'north'))) == [
        ['north'],
        ['south', 'waves.1', 'waves.2'],
        ['east'],
    ]
    assert members(drawn(model, equations('waves'))) == [['waves.1', 'waves.2']]
    assert members(drawn(model, equations('waves', more='instances = "each"\n'))) == [
        ['waves.1'],
        ['waves.2'],
    ]
    # A group writes the keys of its template, or of its set of copies.
    (zone, east) = drawn(model, equations('Zone'))['panels']['equations']
    assert zone['name'] == zone['template'] == 'Zone' and east['name'] == 'east' and east['template'] is None
    (waves,) = drawn(model, equations('waves'))['panels']['equations']
    keys = {key for item in waves['lines'] for key in item['keys']}
    assert waves['name'] == 'waves' and 'waves.level' in keys
    assert not any(key.startswith(('waves.1.', 'waves.2.')) for key in keys)


def test_the_lines_are_the_blocks_of_the_model(model):
    """Each line of a block of one entity is the line of `Equations.block`, in order, its trees as
    data; a group's are those of its first member's block with the keys of its name."""
    for run in (None, 'a', 'b'):
        doc = drawn(model, equations(*CARDS, more='depth = 2\nchecks = true\n'), run)
        eq = Equations(model, run)
        for block in doc['panels']['equations']:
            first = eq.block(block['members'][0]['entity'], depth=2, checks=True)
            if len(block['members']) > 1:
                first = generic(first, block['name'])
            assert [item['kind'] for item in block['lines']] == [item.kind for item in first.lines]
            for item, expected in zip(block['lines'], first.lines):
                trees = [item['lhs'], item['rhs']] if item['lhs'] is not None else item['math']
                assert [from_dict(tree) for tree in trees] == list(expected.trees)
                assert item['keys'] == list(expected.keys) and item['words'] == expected.words


def test_depth_and_checks_reach_the_lines(model):
    kinds = {
        line['kind']
        for block in drawn(model, equations('hub', more='depth = 0\n'))['panels']['equations']
        for line in block['lines']
    }
    assert 'formula' not in kinds and 'check' not in kinds
    kinds = {
        line['kind']
        for block in drawn(model, equations('hub', more='checks = true\n'))['panels']['equations']
        for line in block['lines']
    }
    assert 'check' in kinds


# ---- the symbols ----------------------------------------------------------------------------------


def tree_keys(item):
    """The keys of the symbols that a line's trees name, read from the trees. (A jump names its event
    in words, `when`, so its event is no key.)"""
    trees = [item['lhs'], item['rhs']] if item['lhs'] is not None else item['math']
    found = []
    for tree in trees:
        for node in notation.nodes(from_dict(tree)):
            if isinstance(node, (Sym, Elapsed, Deriv)):
                found.append(node.key)
            elif isinstance(node, (Assign, Since, Count)):
                found.append(node.target)
    return set(found)


def check_symbols(doc):
    """Every symbol of every line, and every tag, has one row, and so has each key that a start's
    formula names, and so on; every row is named so; no two rows have one symbol, or an event's
    count."""
    found = doc['panels']
    rows = {row['key']: row for row in found['symbols']}
    assert len(rows) == len(found['symbols'])
    named = set()
    for block in found['equations']:
        for item in block['lines']:
            assert set(item['keys']) == tree_keys(item)
            named |= tree_keys(item)
    reached = named | set(found['tags'])
    while True:
        more = {
            key
            for item in reached & set(rows)
            for data in start_trees(rows[item])
            if data
            for key in named_by(data)
        }
        if more <= reached:
            break
        reached |= more
    assert reached == set(rows)
    texts = [row['symbol']['text'] for row in found['symbols']]
    texts += [row['count']['text'] for row in found['symbols'] if row['count'] is not None]
    assert len(set(texts)) == len(texts)
    for key, text in found['tags'].items():
        assert rows[key]['symbol']['text'] == text


@pytest.mark.parametrize('instances', ['together', 'each'])
def test_every_symbol_of_every_line_has_one_row_of_its_own(model, instances):
    for run in (None, 'a', 'b'):
        doc = drawn(model, equations(*CARDS, more=f'instances = "{instances}"\n'), run)
        check_symbols(doc)


def test_a_pair_and_a_template_have_symbols_made_from_their_flow_and_their_members(model):
    from napkin.draw.symbols import symbols as made
    from napkin.draw.symbols import tags, words

    doc = drawn(model, equations('Zone', 'hub', 'zebra'))
    rows = {row['key']: row for row in doc['panels']['symbols']}
    sheet = style.Style()
    cards = [card['id'] for card in doc['cards']]
    hub_tag = tags(model, sheet, cards)['hub']
    # The pair with a rate of its own (fill, pair 1) has the base of its flow, a lower-case initial, and
    # the card's tag. The counterexample: flush, of the same initial, takes the second symbol of the
    # card, which is also the flow's symbol with the pair's number; the two still differ.
    pair, flush = rows['hub.fill[1]'], rows['hub.flush']
    assert pair['symbol']['base'] == flush['symbol']['base'] == words('fill')[0][0]
    assert pair['symbol']['sub'].split(',')[0] == hub_tag
    flows = [row['symbol']['text'] for row in rows.values() if row['kind'] == 'flow']
    assert len(set(flows)) == len(flows) and pair['symbol']['text'] != flush['symbol']['text']
    assert pair['kind'] == 'flow' and pair['marks'] == []
    # A key of the template has the base of its first member's symbol and a tag that no card has:
    # zebra's tag is the initial of Zone.
    card_tags = set(tags(model, sheet, cards).values())
    own = made(model, sheet, cards, ['north.level', 'north.pull', 'north.k'])
    for member in ('level', 'pull', 'k'):
        row = rows[f'Zone.{member}']
        assert row['symbol']['base'] == own[f'north.{member}'].base
        assert row['symbol']['sub'].split(',')[0] not in card_tags
    assert 'z' in card_tags  # the counterexample: zebra holds the template's initial
    # The tags of the shown cards are the symbols of their own stocks, and a group's rows are its
    # template's.
    assert {key.split('.')[0] for key in doc['panels']['tags']} == {
        'north',
        'south',
        'east',
        'waves',
        'hub',
        'zebra',
    }
    assert 'waves.level' in doc['panels']['tags'] and 'Zone.level' not in doc['panels']['tags']


def test_without_tags_the_rows_are_those_of_the_lines(model):
    doc = drawn(model, equations(*CARDS, more='tags = false\n'))
    assert doc['panels']['tags'] == {}
    check_symbols(doc)


def test_a_row_has_the_facts_of_its_value_for_the_run(model):
    """The meaning is the label, the value the default or the run's (the option Busy's), the unit the
    type's, and a flow's unit its stock's per hour."""
    table = Runs.from_table(model.run_table)
    hub = model.scenario.entity('hub')
    for run in ('a', 'b'):
        doc = drawn(model, equations('hub'), run)
        rows = {row['key']: row for row in doc['panels']['symbols']}
        values = table.values_of(model.runs[run]['options']).values
        for key in ('hub.x', 'hub.y'):
            row = rows[key]
            unit = table.inputs[key].unit
            assert row['unit'] == unit
            assert number_in(row['value'], unit, table.units) == values[key]
        assert rows['hub.give']['value'] is None and rows['hub.give']['kind'] == 'formula'
        store = hub.value('store')
        assert rows['hub.flush']['unit'] == rows['hub.fill[1]']['unit']
        assert rows['hub.flush']['unit'] == written_unit(store.type, hub.text_of) + '/h'
        # x has the option Busy, which the row lists with its value.
        assert [option['option'] for option in rows['hub.x']['options']] == ['Busy']
        assert rows['hub.x']['option_count'] == 1


# ---- the marks and the references -----------------------------------------------------------------


def assumed(records):
    """Whether records rest on an assumption: one of them is one, or names one."""
    items = records if isinstance(records, (list, tuple)) else () if records is None else (records,)
    return any(
        item.get('kind') == 'assumption' or item.get('assumption') for item in items if hasattr(item, 'get')
    )


def value_records(model, key, run):
    """The records of the value that a row of a key shows: the default's, or the run's option's."""
    entity, member = notation.split(key)
    value = model.scenario.entity(entity).value(member)
    if run is not None:
        given = {setting.profile: setting for setting in value.settings}
        for name in model.runs[run]['options']:
            if name in given:
                return given[name].records
    return value.records


def test_marks_name_entries_and_an_input_on_an_assumption_has_one(model):
    for run in (None, 'a', 'b'):
        doc = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'), run)
        found = doc['panels']
        assert found['references'], 'the fixture cites records'
        rows = {row['key']: row for row in found['symbols']}
        for key, row in rows.items():
            # A value worked out from others has no marks: a formula, a flow, an event, and a start
            # that a formula sets. A start that the file writes as a value has the marks of its
            # records, as an input has.
            worked_out = row['kind'] in ('formula', 'flow', 'event') or row['value_math'] is not None
            if worked_out:
                assert row['marks'] == [], key
            elif row['kind'] in ('stock', 'tally', 'state') and row['value'] is not None:
                plain = model.scenario.entity(notation.split(key)[0]) is not None
                if plain and value_records(model, key, run):
                    assert row['marks'], key
            plain = model.scenario.entity(notation.split(key)[0]) is not None
            if row['kind'] == 'input' and plain and assumed(value_records(model, key, run)):
                assert 'assumption' in {kind for _, kind in row['marks']}, key
        # Zone's k rests on an assumption in each member: the template's row has its mark.
        doc = drawn(model, equations('Zone', more='\n[references]\nshow = true\n'), run)
        (zone,) = [row for row in doc['panels']['symbols'] if row['key'] == 'Zone.k']
        assert 'assumption' in {kind for _, kind in zone['marks']}


def test_only_what_shows_is_cited(model):
    shown = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'))['panels']
    ids = {name for entry in shown['references'] for name in entry['record']}
    # The input that no line reads has no row, so its source is in no entry.
    assert 'hub.quiet' not in {row['key'] for row in shown['symbols']}
    assert 'SRC-HIDDEN' not in ids and 'CLM-HIDDEN' not in ids
    # Without the Symbols table only the lines cite: an input's own records drop out, and the rows have
    # no marks.
    lines = drawn(model, equations(*CARDS, more='symbols = false\n\n[references]\nshow = true\n'))['panels']
    marked = {
        number for block in lines['equations'] for item in block['lines'] for number, _ in item['marks']
    }
    assert {entry['number'] for entry in lines['references']} == marked
    assert all(row['marks'] == [] and row['range_marks'] == [] for row in lines['symbols'])
    assert len(lines['references']) < len(shown['references'])
    assert lines['note'] is None
    # Without show, no entry and no mark.
    plain = drawn(model, equations(*CARDS))['panels']
    assert plain['references'] == []
    assert all(item['marks'] == [] for block in plain['equations'] for item in block['lines'])
    assert all(row['marks'] == [] for row in plain['symbols'])


def test_kinds_leave_entries_out_but_never_the_assumptions(model):
    doc = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\nkinds = ["assumption"]\n'))
    found = doc['panels']
    assert {entry['kind'] for entry in found['references']} == {'assumption'}
    every = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'))['panels']
    assert {entry['kind'] for entry in every['references']} > {'assumption'}


# ---- the ranges -----------------------------------------------------------------------------------


def number(written, unit, units):
    text = written.strip()
    return number_in(float(text) if re.fullmatch(r'[0-9.eE+-]+', text) else text, unit, units)


def check_ranges(model, doc):
    """An input's range is its model's range (the run table's numbers), with its status; a row of
    another kind has none; the note shows exactly when the table shows a chosen range."""
    table = Runs.from_table(model.run_table)
    found = doc['panels']
    for row in found['symbols']:
        item = table.inputs.get(row['key'])
        if item is None or row['kind'] != 'input':
            if row['kind'] != 'input':
                assert row['range'] is None
            continue
        if item.range is None:
            assert row['range'] is None
            continue
        assert [
            None if edge is None else number(edge, item.unit, table.units) for edge in row['range']
        ] == list(item.range)
        assert row['range_status'] in ('chosen', 'declared')
    chosen = any(row['range'] is not None and row['range_status'] == 'chosen' for row in found['symbols'])
    assert (found['note'] is not None) == (chosen and found['settings']['symbols'])


def test_an_input_has_the_range_of_its_model_and_the_note_shows_with_it(model):
    for text in (equations(*CARDS), equations('zebra'), equations('hub', more='symbols = false\n')):
        doc = drawn(model, text)
        check_ranges(model, doc)
    assert drawn(model, equations('hub'))['panels']['note'] is not None
    # zebra has no input: no range shows, and there is no note.
    assert drawn(model, equations('zebra'))['panels']['note'] is None


# ---- the LaTeX ------------------------------------------------------------------------------------


def read_back(item, rows):
    """(the trees that the LaTeX of a line reads back to, the text that the reader read): each symbol
    of the panel in the LaTeX is written as a symbol of the reader, x_{i} for a value and e_{i} under τ
    and N for an event, in one pass."""
    trees = [
        from_dict(tree) for tree in ([item['lhs'], item['rhs']] if item['lhs'] is not None else item['math'])
    ]
    values, events, swaps = {}, {}, {}
    for tree in trees:
        for node in notation.nodes(tree):
            if isinstance(node, (Since, Count)):
                row = rows[node.target]
                written = next((w for w, pair in events.items() if pair == (node.event, node.ending)), None)
                if written is None:
                    written = f'e_{{{len(events) + 1}}}'
                    events[written] = (node.event, node.ending)
                swaps[row['symbol']['latex']] = rf'\tau_{{{written}}}'
                if row['count'] is not None:
                    swaps[row['count']['latex']] = rf'N_{{{written}}}'
            elif isinstance(node, (Sym, Elapsed, Deriv, Assign)):
                key = node.target if isinstance(node, Assign) else node.key
                written = next((w for w, k in values.items() if k == key), None)
                if written is None:
                    written = f'x_{{{len(values) + 1}}}'
                    values[written] = key
                swaps[rows[key]['symbol']['latex']] = written
    text = item['latex']
    if swaps:
        pattern = '|'.join(re.escape(real) for real in sorted(swaps, key=len, reverse=True))
        text = re.sub(rf"(?<![A-Za-z\\])(?:{pattern})(?![A-Za-z_'])", lambda m: swaps[m.group()], text)
    if item['lhs'] is not None:
        left, right = text.split(panels.LATEX_RELATIONS[item['relation']], 1)
        return [read(left, values, events), read(right, values, events)], text
    parts = text.split(panels.BETWEEN)
    reader = read_line if item['kind'] == 'jump' else read
    return [reader(part, values, events) for part in parts], text


def check_latex(doc, seeds=(1,)):
    """Each line's LaTeX reads back to its trees, shape for shape, and has their value at each point."""
    rows = {row['key']: row for row in doc['panels']['symbols']}
    count = 0
    for block in doc['panels']['equations']:
        for item in block['lines']:
            trees = [
                from_dict(tree)
                for tree in ([item['lhs'], item['rhs']] if item['lhs'] is not None else item['math'])
            ]
            back, text = read_back(item, rows)
            assert [shape(canonical(node)) for node in back] == [shape(canonical(node)) for node in trees], (
                text
            )
            for seed in seeds:
                point = Point(seed)
                for node, again in zip(trees, back):
                    if not isinstance(node, Deriv):
                        assert same_value(
                            outcome(value_of_node, again, point), outcome(value_of_node, node, point)
                        ), text
            count += 1
    return count


def test_the_latex_of_each_line_reads_back_to_its_trees(model):
    for text in (
        equations(*CARDS),
        equations('Zone', 'hub', more='instances = "each"\ndepth = 3\nchecks = true\n'),
    ):
        for run in (None, 'b'):
            assert check_latex(drawn(model, text, run), seeds=(1, 2)) > 10


def test_the_since_and_the_count_of_an_event_are_its_symbols(model):
    doc = drawn(model, equations('hub'))
    rows = {row['key']: row for row in doc['panels']['symbols']}
    go = rows['hub.go']
    assert go['kind'] == 'event' and go['count'] is not None
    (later,) = [
        item
        for block in doc['panels']['equations']
        for item in block['lines']
        if item['event'] == 'hub.later' and 'hub.store' in item['keys']
    ][:1]
    assert later['kind'] == 'jump'
    texts = ' '.join(item['latex'] for block in doc['panels']['equations'] for item in block['lines'])
    # No line writes the time since an event under a second τ.
    assert rf'\tau_{{{go["symbol"]["latex"]}}}' not in texts


def environments(text):
    """The environments of a LaTeX text, in order of their ends; the text's braces and environments
    are balanced."""
    depth, stack, done = 0, [], []
    for found in re.finditer(r'\\(?:begin|end)\{([a-z*]+)\}|(?<!\\)[{}]', text):
        if found.group(1):
            if found.group().startswith('\\begin'):
                stack.append(found.group(1))
            else:
                assert stack and stack.pop() == found.group(1), found.group()
                done.append(found.group(1))
        else:
            depth += 1 if found.group() == '{' else -1
            assert depth >= 0
    assert depth == 0 and not stack
    return done


def test_the_latex_fragment_has_a_block_for_each_block_and_an_item_for_each_reference(model):
    doc = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'))
    text = panels.latex(doc)
    found = doc['panels']
    ends = environments(text)
    assert ends.count('align*') == sum(1 for block in found['equations'] if block['lines'])
    assert ends.count('longtable') == 1 and ends.count('enumerate') == 1
    assert text.count(r'\item ') == len(found['references'])
    assert r'\usepackage{amsmath}' in text and r'\usepackage{hyperref}' in text
    links = re.findall(r'\\href\{([^}]*)\}', text)
    assert links and all(re.match(r'https?://', link) for link in links)
    assert len(links) == sum(1 for entry in found['references'] if entry['url'])
    # Every line is in the fragment, and so is every symbol of the table.
    for block in found['equations']:
        for item in block['lines']:
            sign = panels.LATEX_RELATIONS[item['relation']]
            first = item['latex'].split(sign, 1)[-1] if item['lhs'] is not None else item['latex']
            assert first in text
    for row in found['symbols']:
        assert f'${row["symbol"]["latex"]}$' in text
    # Without references or without the table, the fragment leaves them out.
    plain = panels.latex(drawn(model, equations('hub', more='symbols = false\n')))
    assert 'longtable' not in environments(plain) and 'enumerate' not in environments(plain)


def test_a_picture_without_panels_gives_a_fragment_of_comments():
    found = panels.latex({'name': 'a', 'run': None, 'panels': None})
    assert found and all(row.startswith('%') for row in found.splitlines())


@pytest.mark.parametrize('text', ['A & B', '50% of #1', 'a_b {c} ~ ^ \\ <x> |y|'])
def test_every_text_of_the_fragment_is_escaped(model, text):
    doc = drawn(model, equations('hub', more='\n[references]\nshow = true\n'))
    found = doc['panels']
    found['equations'][0]['title'] = text
    found['symbols'][0]['meaning'] = text
    written = panels.latex(doc)
    environments(written)
    escaped = notation.escape(text)
    assert rf'\paragraph{{{escaped}}}' in written.splitlines()
    assert any(
        row.startswith(f'${found["symbols"][0]["symbol"]["latex"]}$') and f' & {escaped} & ' in row
        for row in written.splitlines()
    )


# The blocks of the fragment that can break across pages: an `align*` in a group that starts with
# `\allowdisplaybreaks` and ends with it, and the table.
BREAKING_BLOCK = re.compile(
    r'\{\\allowdisplaybreaks(?:\[[1-4]\])?\s*\\begin\{align\*\}.*?\\end\{align\*\}\}', re.S
)


def test_a_long_block_and_the_table_can_break_across_pages(model):
    doc = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'))
    text = panels.latex(doc)
    ends = environments(text)
    # Each `align*` is alone in its group, and the group sets `\allowdisplaybreaks`: the value of the
    # document holds again after the block.
    assert len(BREAKING_BLOCK.findall(text)) == ends.count('align*') > 1
    assert text.count(r'\allowdisplaybreaks') == ends.count('align*')
    # The table is a `longtable` (a `tabular` never breaks), and its header row repeats on each page:
    # the first row, before `\endhead`, has no symbol of the table.
    assert ends.count('longtable') == 1 and 'tabular' not in ends
    table = text.split(r'\begin{longtable}', 1)[1].split(r'\end{longtable}', 1)[0]
    head, rows = table.split('\\endhead\n', 1)
    assert '$' not in head and head.count(r' \\') == 1
    assert sum(line.endswith(r' \\') for line in rows.splitlines()) == len(doc['panels']['symbols'])
    # The comments at the top name each package that the fragment uses, hyperref last.
    named = re.findall(
        r'\\usepackage\{([a-z]+)\}', ''.join(row for row in text.splitlines() if row.startswith('%'))
    )
    assert set(named) >= {'amsmath', 'longtable', 'hyperref'} and named[-1] == 'hyperref'


def range_cells(rows):
    """The text of the Range cell of each row of a picture that has only these rows, and the header."""
    doc = {
        'name': 'a',
        'run': None,
        'panels': {
            'settings': {'symbols': True},
            'equations': [],
            'symbols': rows,
            'references': [],
            'note': None,
        },
    }
    table = panels.latex(doc).split(r'\begin{longtable}', 1)[1].split(r'\end{longtable}', 1)[0]
    lines = [line.removesuffix(r' \\') for line in table.splitlines()[1:] if line.endswith(r' \\')]
    return lines[0].split(' & '), [line.split(' & ')[-1] for line in lines[1:]]


@pytest.mark.parametrize('status', ['chosen', 'declared'])
def test_a_range_says_chosen_range_exactly_when_the_scenario_chose_it(model, status):
    """The Range cell has the words of the SVG: "chosen range lo--hi" for a range that the scenario
    chose, "range lo--hi" for a range of `bounds: sourced`, then its marks; no range, no words."""
    doc = drawn(model, equations('hub'))
    ranged = next(row for row in doc['panels']['symbols'] if row['key'] == 'hub.x')
    assert ranged['range'] is not None and None not in ranged['range']
    low, high = (edge.split()[0] for edge in ranged['range'])
    assert low != high
    rows = [
        dict(ranged, range_status=status, range_marks=[[3, 'source'], [5, 'assumption']]),
        dict(ranged, key='hub.x2', range_status=status, range_marks=[]),
        dict(ranged, key='hub.x3', range=None, range_status=None, range_marks=[]),
    ]
    header, cells = range_cells(rows)
    assert header[-1] == 'Range' and 'chosen' not in ' '.join(header).lower()
    marked, plain, empty = cells
    for cell in (marked, plain):
        words = cell.split(r'\textsuperscript')[0]
        assert words.startswith('chosen range ' if status == 'chosen' else 'range ')
        assert ('chosen' in words) == (status == 'chosen')
        # The low edge, then the high edge, with the en dash of TeX between them: the words of the SVG.
        assert re.search(rf'{re.escape(low)}\D*--\s*{re.escape(high)}', words), words
        assert words.replace('--', '–').strip() == notation.escape(layouts.range_words(rows[0]))
    assert marked.endswith(r'\textsuperscript{3,5}') and r'\textsuperscript' not in plain
    assert empty == ''
    # A counterexample: the same row with the other status.
    other = 'declared' if status == 'chosen' else 'chosen'
    (_, (again, *_)) = range_cells([dict(ranged, range_status=other)])
    assert again.startswith('chosen range ') == (other == 'chosen')


# An address with each character that TeX or hyperref reads in its own way (`$` is the address of a
# catalogue source, an OData query). A second `#` stays in the fragment of the address.
LINKS = {
    '$': 'https://example.org/data?$filter=year&$top=5',
    '#': 'https://example.org/report#part',
    '# twice': 'https://example.org/report#part#two',
    '%': 'https://example.org/a%20b/c',
    '\\': 'https://example.org/a\\b',
    '{': 'https://example.org/{id}/a',
    '}': 'https://example.org/a}',
    '~': 'https://example.org/~user/page',
    '^': 'https://example.org/a^b',
    '_': 'https://example.org/a_b?c_d=e_f',
    '&': 'https://example.org/q?a=1&b=2',
}


def link_of(argument):
    """The address that hyperref makes from the argument of `\\href`, after a check that TeX reads the
    argument as plain characters at the top level and in the argument of another command: no brace,
    no math shift `$`, no `^` (`^^` and two hex digits are one character to TeX), no space, and a
    backslash, `%` (a comment) or `#` (a parameter) only in the escapes `\\%` and `\\#`. hyperref
    reads `\\%` and `\\#` as `%` and `#`, and `&`, `_` and `~` as themselves (`\\hyper@normalise`)."""
    assert argument.isascii() and argument.isprintable(), argument
    assert not set(argument) & set('{}$^ '), argument
    assert re.fullmatch(r'(?:\\[%#]|[^\\%#])*', argument), argument
    address = argument.replace(r'\%', '%').replace(r'\#', '#')
    # hyperref splits an address at its first `#`: what follows a second `#` is lost.
    assert address.count('#') <= 1, address
    return address


def read_alike(address, url):
    """A server reads both addresses as one: the same scheme, host, path and fragment up to percent
    escapes, and the same parameters of the query, in order."""

    def parts(text):
        found = urlsplit(text)
        query = parse_qsl(found.query, keep_blank_values=True)
        return found.scheme, found.netloc, unquote(found.path), query, unquote(found.fragment)

    return parts(address) == parts(url)


@pytest.mark.parametrize('char', list(LINKS))
def test_a_link_with_a_special_character_reads_as_its_address(model, char):
    url = LINKS[char]
    assert char.split()[0] in url and refs.web_host(url)
    doc = drawn(model, equations('hub', more='\n[references]\nshow = true\n'))
    entry = next(entry for entry in doc['panels']['references'] if entry['url'])
    doc['panels']['references'] = [dict(entry, url=url, link_text=None)]
    text = panels.latex(doc)
    environments(text)
    (argument,) = re.findall(r'\\href\{([^{}]*)\}\{', text)
    address = link_of(argument)
    assert read_alike(address, url), (address, url)
    # Counterexamples: the address as it is fails the check, unless hyperref reads the character as
    # itself; two `\#` lose the second part of the fragment; `&` as %26 no longer separates the
    # parameters of the query.
    if char.split()[0] not in '&_~':
        with pytest.raises(AssertionError):
            link_of(url)
    if char == '# twice':
        with pytest.raises(AssertionError):
            link_of(url.replace('#', r'\#'))
    if '&' in url:
        assert not read_alike(url.replace('&', '%26'), url)


def tex_engine():
    """pdflatex or lualatex with the packages of the fragment, or the reason that there is none."""
    engine = next((found for name in ('pdflatex', 'lualatex') if (found := shutil.which(name))), None)
    if engine is None:
        return None, 'no pdflatex or lualatex on PATH, so the fragment is not compiled'
    finder = shutil.which('kpsewhich')
    for package in panels.PACKAGES:
        if (
            finder
            and not subprocess.run(
                [finder, f'{package}.sty'], capture_output=True, text=True, check=False
            ).stdout.strip()
        ):
            return None, f'the TeX installation has no {package}.sty, so the fragment is not compiled'
    return engine, ''


ENGINE, NO_ENGINE = tex_engine()
# The minimal document that holds the fragment: the packages that its comments name, and PDF objects
# without compression, so that the test reads the links of the PDF.
DOCUMENT = r"""\documentclass{article}
\ifdefined\pdfvariable \pdfvariable compresslevel=0 \pdfvariable objcompresslevel=0
\else \pdfcompresslevel=0 \pdfobjcompresslevel=0 \fi
%(packages)s
\begin{document}
\input{fragment.tex}
\typeout{AFTER: \the\interdisplaylinepenalty}
\end{document}
"""


@pytest.mark.skipif(ENGINE is None, reason=NO_ENGINE)
def test_the_fragment_compiles_and_breaks_across_pages(model, tmp_path):
    """The fragment compiles in a minimal document with the packages that its comments name. A block
    of equations and the table, each longer than a page, break across pages: no box is taller than its
    page. The document keeps its own `\\interdisplaylinepenalty` (amsmath's 10000) after the fragment,
    and each link of the PDF reads as its address."""
    doc = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'))
    found = doc['panels']
    # More lines and rows than a page holds: the lines of the longest block and the rows, repeated.
    longest = max(found['equations'], key=lambda block: len(block['lines']))
    longest['lines'] = longest['lines'] * (120 // len(longest['lines']) + 1)
    found['symbols'] = found['symbols'] * (200 // len(found['symbols']) + 1)
    entry = next(entry for entry in found['references'] if entry['url'])
    found['references'] = [
        dict(entry, number=n, url=url, link_text=None) for n, url in enumerate(LINKS.values(), 1)
    ]
    fragment = panels.latex(doc)
    named = re.findall(
        r'\\usepackage\{[a-z]+\}', ''.join(row for row in fragment.splitlines() if row.startswith('%'))
    )
    (tmp_path / 'fragment.tex').write_text(fragment, encoding='utf-8')
    (tmp_path / 'paper.tex').write_text(DOCUMENT % {'packages': '\n'.join(named)}, encoding='utf-8')
    done = subprocess.run(
        [ENGINE, '-interaction=nonstopmode', '-halt-on-error', 'paper.tex'],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    log = (tmp_path / 'paper.log').read_text(encoding='utf-8', errors='replace')
    assert done.returncode == 0, log[-3000:]
    pages = int(re.search(r'Output written on paper\.pdf \((\d+) pages?', log).group(1))
    assert pages >= 4, pages
    # An `align*` or a `tabular` that cannot break is taller than its page.
    assert 'Overfull \\vbox' not in log
    assert 'AFTER: 10000' in log
    pdf = (tmp_path / 'paper.pdf').read_bytes().decode('latin-1')
    written = {re.sub(r'\\(.)', r'\1', uri) for uri in re.findall(r'/URI\s*\(((?:\\.|[^\\)])*)\)', pdf)}
    assert len(written) == len(LINKS), written
    for url in LINKS.values():
        assert any(read_alike(address, url) for address in written), url


# ---- the contract and the rest of the picture -----------------------------------------------------


def test_the_panels_change_no_other_part_of_the_picture(model):
    whole = drawn(model, '')
    for text in (equations(*CARDS), equations('Zone', more='\n[references]\nshow = true\n')):
        doc = drawn(model, text)
        assert {key: value for key, value in doc.items() if key != 'panels'} == {
            key: value for key, value in whole.items() if key != 'panels'
        }


def test_the_contract_check_finds_each_broken_part_of_the_panels(model):
    def broken(change):
        doc = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'))
        change(doc['panels'])
        return picture_problems(doc)

    for change, found in (
        (lambda p: p.pop('note'), 'panels: has the keys'),
        (lambda p: p['settings'].update(depth=6), 'panels.settings.depth'),
        (lambda p: p['settings'].update(kinds=['source']), 'panels.settings.kinds'),
        (lambda p: p['equations'].reverse(), 'panels.equations: are in the order'),
        (lambda p: p['equations'][0]['members'][0].update(card='nowhere'), 'members[0].card'),
        (
            lambda p: p['equations'][0]['lines'][0].update(math=[{'node': 'Time'}]),
            'lines[0]: has lhs and rhs',
        ),
        (lambda p: p['symbols'].pop(), 'panels.symbols'),
        (
            lambda p: p['symbols'][1].update(symbol=dict(p['symbols'][0]['symbol'])),
            'panels.symbols: have one symbol',
        ),
        (lambda p: p['symbols'][0]['symbol'].update(text='Q'), 'symbols[0].symbol.text'),
        (lambda p: p['references'].pop(), 'mark'),
        (lambda p: p['references'][0].update(url='javascript:alert(1)'), 'references[0].url'),
        (lambda p: p.update(note=None), 'panels.note'),
        (lambda p: p['tags'].update({'hub.store': 'Q_q'}), 'panels.tags.hub.store'),
        (
            lambda p: next(row for row in p['symbols'] if row['kind'] == 'formula').update(
                marks=[[1, 'source']]
            ),
            'are marks of an input, a fixed value or a start',
        ),
    ):
        problems = broken(change)
        assert any(found in problem for problem in problems), (found, problems)


# ---- every scenario -------------------------------------------------------------------------------


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_panels_of_every_card_of_every_scenario_keep_the_contract(scenario_id):
    """With every card that the picture draws in `things` and the references shown: the panels build,
    keep the contract, change no other part of the picture, have a row for each symbol, the ranges of
    the model, and LaTeX that reads back to the trees of each line; the fragment has its blocks."""
    model = catalogue_model(scenario_id)
    sheet = style.of(model)
    whole = picture(model, sheet)
    assert whole['panels'] is None or sheet.equations
    shown = dataclasses.replace(sheet, equations=tuple(style.drawn(sheet, model)), references_show=True)
    start = time.perf_counter()
    doc = picture(model, shown)
    took = time.perf_counter() - start
    assert took < 10, took
    assert picture_problems(doc) == []
    assert {key: value for key, value in doc.items() if key != 'panels'} == {
        key: value for key, value in whole.items() if key != 'panels'
    }
    check_symbols(doc)
    check_ranges(model, doc)
    assert check_latex(doc) > 0
    text = panels.latex(doc)
    ends = environments(text)
    assert ends.count('align*') == sum(1 for block in doc['panels']['equations'] if block['lines'])
    assert text.count(r'\item ') == len(doc['panels']['references'])
    assert all(re.match(r'https?://', link) for link in re.findall(r'\\href\{([^}]*)\}', text))
