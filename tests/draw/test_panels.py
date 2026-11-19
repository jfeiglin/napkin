"""The panels under the map (D-53, D-55, D-57, napkin/draw/panels.py): the blocks of the shown cards,
the Symbols table with the facts of each value, the References with their marks, and the LaTeX
fragment.

The model is a package with the library of the references tests: a template whose members share their
trees (north, south and the rows of `waves`) and a member whose formula is its own (east); a thing with
a flow with legs, an endpoint, events that read the time since an event and its count, an assertion,
and inputs on records of every kind. The option "Busy" sets an input, with a record of its own. Each
expectation follows from the rules of the module's text and from the blocks of `equations.py`, which
`test_equations.py` checks by hand. The catalogue test (`test_catalogue.py`) waits for stage M.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from napkin.draw import layout as layouts
from napkin.draw import notation, panels, style
from napkin.draw import references as refs
from napkin.draw.equations import Equations, generic, same
from napkin.draw.model_map import picture
from napkin.draw.notation import Assign, Count, Deriv, Elapsed, Since, Sym, from_dict
from napkin.draw.style import StyleError
from napkin.draw.things import Things
from tests.draw.latex_subset import read, read_line
from tests.draw.models import package
from tests.draw.test_notation import Point, canonical, outcome, shape, value_of_node
from tests.draw.test_notation import same as same_value
from tests.draw.test_picture import picture_problems
from tests.draw.test_references import RECORDS, own_library

# ---- the model ------------------------------------------------------------------------------------

FIXTURE = """\
scenario "Panels fixture"
    horizon 10 h

options "Load":
    "Calm":
        "Calm."
    "Busy":
        "Busy."
        hub.x = 5 people/h  @rec_counted

runs:
    calm = "Calm"
    busy = "Busy"

Zone:
    "A zone."
    input k: fraction = 0.5 in [0, 1]  @rec_assumed
        "Share drained"
    level: people = 10 people in [0 people, 100 people]  @rec_counted
        "People waiting"
    done: people = this.k * 10 people in [0 people,]  @rec_counted
        "People served"
    pull = formula(this.k * this.level / (1 h))  @rec_direct_first
        "Pace of service"
    flow drain: this.level -> this.done  @rec_counted
        "Service"
        request = this.pull

north: Zone

south: Zone

east: Zone
    pull = formula(2 * this.k * this.level / (1 h))  @rec_rule

waves: Zone from "waves.csv"

zebra:
    herd: people = 4 people in [0 people,]
    flow grow: SOURCE -> this.herd
        request = this.herd / (10 h)

hub:
    "The hub."
    input x: people/h = 2 people/h in [1 people/h, 9 people/h]  @rec_transfer
        "Pace of the first pump"
    input y: people/h = 3 people/h  @rec_direct_second
    input quiet: people/h = 1 people/h in [0 people/h, 5 people/h]  @rec_hidden
    input base: people = 4 people  @rec_assumed
    mode: enum[IDLE, BUSY] = IDLE
    store: people = 50 people in [0 people,]  @rec_counted
        outflow.capacity = 3 * this.x
    spare: people = 2 * this.base in [0 people,]
    used: people = 0 people in [0 people,]
    give = formula(this.x / 2 + this.y)  @rec_rule_plain
    ready = formula(this.mode == BUSY and since(this.go) >= 1 h)  @rec_rule_plain
    flow fill:
        flow first: this.store -> this.spare
            request = this.give
        flow second: this.spare -> this.used  @other
            request = 0.5 * this.x
    flow flush: this.store -> this.used
        request = (this.x if this.ready else 0 people/h) + count(this.go.occurrences) * 1 people/h
    go = event():
        when this.mode == BUSY and t >= 1 h:
            this.go.start()
            reset when false
        after 0 h:
            this.store -= 1 people
    later = event():
        when since(this.go) >= 2 h and count(this.go.occurrences) >= 1:
            this.later.start()
            reset when false
        after 0 h:
            move 1 people from this.store to this.spare
    turn = event():
        after 1 h:
            this.mode = BUSY
    assert this.store + this.spare + this.used <= 60 people

hub.turn.start()

record other: identity "Another record of the fixture."
"""
CARDS = ('north', 'south', 'east', 'waves', 'zebra', 'hub')


@pytest.fixture(scope='module')
def model(tmp_path_factory):
    folder = tmp_path_factory.mktemp('panels') / 'panels'
    text = FIXTURE + '\n' + '\n'.join(RECORDS) + '\n'
    return Things(package(folder, text, library=own_library(), tables={'waves.csv': 'id\na\nb\n'}))


def drawn(model, text, run=None):
    """The picture of the model with the stylesheet `text`, which keeps the picture contract."""
    sheet = style.read(text)
    assert style.check(sheet, model) == []
    doc = picture(model, sheet, run)
    assert picture_problems(doc) == []
    return doc


def equations(*things, more=''):
    listed = ', '.join(f'"{name}"' for name in things)
    return f'[equations]\nthings = [{listed}]\n{more}'


def members(doc):
    return [[member['entity'] for member in block['members']] for block in doc['panels']['equations']]


def rows_of(doc):
    return {row['key']: row for row in doc['panels']['symbols']}


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


def tree_keys(item):
    """The keys of the symbols that a line's trees name, read from the trees."""
    trees = [item['lhs'], item['rhs']] if item['lhs'] is not None else item['math']
    found = []
    for tree in trees:
        for node in notation.nodes(from_dict(tree)):
            if isinstance(node, (Sym, Elapsed, Deriv)):
                found.append(node.key)
            elif isinstance(node, (Assign, Since, Count)):
                found.append(node.target)
    return set(found)


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
        ('[equations]\nthings = ["Depot"]\n', 'Depot is not on the map: it has no member'),
        ('[layout]\nhide = ["Ward"]\n\n[equations]\nthings = ["east"]\n', 'layout.hide hides it'),
        ('[layout]\nhide = ["east"]\n\n[equations]\nthings = ["Ward"]\n', None),
    ],
)
def test_the_things_of_equations_are_things_and_templates_that_the_picture_draws(tmp_path, text, match):
    from tests.draw.test_style import MODEL

    found = package(tmp_path, MODEL, style=text)
    if match is None:
        # A template with one member on the map is a name that the picture draws.
        assert style.check(style.of(found), found) == []
        return
    with pytest.raises(StyleError, match=match) as caught:
        style.of(found)
    assert [d['key'] for d in caught.value.diagnostics] == ['equations.things']


# ---- the blocks -----------------------------------------------------------------------------------


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
    """The blocks stand for exactly the members of the shown cards, each once, in the order of the
    cards: a card that `things` names itself, or whose template it names. A group of two or more has
    one template, and its members' blocks are the same up to the member."""
    doc = drawn(model, equations(*things, more=f'instances = "{instances}"\n'))
    named = set(things)
    shown = [card['id'] for card in doc['cards'] if card['id'] in named or card['template'] in named]
    listed = [name for group in members(doc) for name in group]
    assert sorted(listed) == sorted(member for card in shown for member in model.cards[card].members)
    order = [card['id'] for card in doc['cards']]
    firsts = [order.index(block['members'][0]['card']) for block in doc['panels']['equations']]
    assert firsts == sorted(firsts)
    eq = Equations(model)
    for block in doc['panels']['equations']:
        names = [member['entity'] for member in block['members']]
        if len(names) > 1:
            assert block['template'] is not None
            assert all(same(eq.block(names[0]), eq.block(name)) for name in names)
        if instances == 'each':
            assert len(names) == 1


def test_members_with_the_same_trees_share_a_block_and_a_thing_beats_its_template(model):
    # The members of Zone whose trees are the same up to the member share one block, and east, whose
    # formula is its own, has its own; a thing that the list names has its own block.
    assert members(drawn(model, equations('Zone'))) == [['north', 'south', 'waves.a', 'waves.b'], ['east']]
    assert members(drawn(model, equations('Zone', 'north'))) == [
        ['north'],
        ['south', 'waves.a', 'waves.b'],
        ['east'],
    ]
    assert members(drawn(model, equations('waves'))) == [['waves.a', 'waves.b']]
    assert members(drawn(model, equations('waves', more='instances = "each"\n'))) == [
        ['waves.a'],
        ['waves.b'],
    ]
    # A group writes the keys of its template, or of its table's card.
    zone, east = drawn(model, equations('Zone'))['panels']['equations']
    assert zone['name'] == zone['template'] == 'Zone' and east['name'] == 'east' and east['template'] is None
    (waves,) = drawn(model, equations('waves'))['panels']['equations']
    keys = {key for item in waves['lines'] for key in item['keys']}
    assert waves['name'] == 'waves' and 'waves.level' in keys
    assert not any(key.startswith(('waves.a.', 'waves.b.')) for key in keys)


def test_the_lines_are_the_blocks_of_the_model(model):
    """Each line of a block of one member is the line of `Equations.block`, in order, its trees as
    data; a group's are those of its first member's block with the keys of its name."""
    for run in (None, 'calm', 'busy'):
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
                assert set(item['keys']) == tree_keys(item)


def test_depth_and_checks_reach_the_lines(model):
    def kinds(more):
        doc = drawn(model, equations('hub', more=more))
        return {line['kind'] for block in doc['panels']['equations'] for line in block['lines']}

    assert 'formula' not in kinds('depth = 0\n') and 'check' not in kinds('depth = 0\n')
    assert 'formula' in kinds('') and 'check' in kinds('checks = true\n')


def test_a_yes_no_formula_is_written_with_iff_and_a_number_formula_with_equals(model):
    doc = drawn(model, equations('hub', more='depth = 2\n'))
    (hub,) = doc['panels']['equations']
    relations = {
        item['part']: (item['relation'], item['latex']) for item in hub['lines'] if item['kind'] == 'formula'
    }
    assert relations['hub.give'][0] == '=' and ' = ' in relations['hub.give'][1]
    # `ready` is a yes/no: the line says that it holds exactly when its right side holds.
    assert relations['hub.ready'][0] == '⇔' and r' \iff ' in relations['hub.ready'][1]


def test_a_template_block_says_which_subscript_stands_for_which_member(model):
    zone = drawn(model, equations('Zone'))['panels']['equations'][0]
    assert zone['subscript'] and all(member['subscript'] for member in zone['members'])
    words = panels.for_words(zone)
    assert words.startswith('For ') and f'({zone["subscript"]}: ' in words
    assert [member['title'] for member in zone['members']] == ['North', 'South', 'Waves a', 'Waves b']


# ---- the symbols ----------------------------------------------------------------------------------


def check_symbols(doc):
    """Every symbol of every line, and every tag, has one row, and so has each key that a start's
    expression names, and so on; every row is named so; no two rows have one symbol, or an event's
    count."""
    found = doc['panels']
    rows = rows_of(doc)
    assert len(rows) == len(found['symbols'])
    named = set()
    for block in found['equations']:
        for item in block['lines']:
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
    for run in (None, 'calm', 'busy'):
        check_symbols(drawn(model, equations(*CARDS, more=f'instances = "{instances}"\n'), run))


def test_a_leg_and_a_template_have_symbols_made_from_their_flow_and_their_members(model):
    rows = rows_of(drawn(model, equations('Zone', 'hub')))
    first, second = rows['hub.fill.first']['symbol'], rows['hub.fill.second']['symbol']
    # A leg is its flow's base with the initial of the leg: the two legs differ in that initial.
    assert first['base'] == second['base'] == 'f'
    assert first['sub'].split(',')[-1] == 'f' and second['sub'].split(',')[-1] == 's'
    # A template's key has the template's own tag, and no member's.
    assert rows['Zone.level']['symbol']['base'] == 'L'
    assert rows['Zone.k']['symbol']['base'] == 'κ'


def test_without_tags_the_rows_are_those_of_the_lines(model):
    tagged = drawn(model, equations('hub'))['panels']
    bare = drawn(model, equations('hub', more='tags = false\n'))['panels']
    assert bare['tags'] == {} and set(tagged['tags']) == {'hub.store', 'hub.spare', 'hub.used'}
    assert {row['key'] for row in bare['symbols']} <= {row['key'] for row in tagged['symbols']}


def test_a_row_has_the_facts_of_its_value_for_the_run(model):
    rows = rows_of(drawn(model, equations('hub')))
    x = rows['hub.x']
    assert (x['kind'], x['meaning'], x['unit'], x['value'], x['range']) == (
        'input',
        'Pace of the first pump',
        'people/h',
        '2 people/h',
        ['1 people/h', '9 people/h'],
    )
    # The options that set it, with their values, and the run's own value with the run.
    assert x['options'] == [{'option': 'Busy', 'value': '5 people/h', 'math': None, 'marks': []}]
    busy = rows_of(drawn(model, equations('hub'), 'busy'))['hub.x']
    assert busy['value'] == '5 people/h'
    # A stock's start is its value; a formula and a flow have none, and a flow's unit is its rate's.
    assert rows['hub.store']['value'] == '50 people' and rows['hub.store']['kind'] == 'stock'
    assert rows['hub.give']['value'] is None and rows['hub.flush']['unit'] == 'people/h'
    # A start that an expression of other values sets is math: the spare starts at twice the base.
    spare = rows['hub.spare']
    assert spare['value'] == '2 * this.base' and named_by(spare['value_math']) == {'hub.base'}
    assert 'hub.base' in rows


def test_a_template_row_stands_for_its_members(model):
    rows = rows_of(drawn(model, equations('Zone')))
    # The members share the start of `done`, which names their own `k`: the template's row writes it
    # with the template's keys.
    done = rows['Zone.done']
    assert named_by(done['value_math']) == {'Zone.k'} and done['instances'] == []
    assert rows['Zone.k']['value'] == '0.5 fraction'


def test_marks_name_entries_and_an_input_on_an_assumption_has_one(model):
    doc = drawn(model, equations('hub', more='\n[references]\nshow = true\n'))
    found = doc['panels']
    numbers = {entry['number']: entry for entry in found['references']}
    rows = rows_of(doc)
    for row in found['symbols']:
        for number, kind in row['marks']:
            assert numbers[number]['kind'] == kind
    # The base rests on the assumption ASM-TEMPO: its one entry, an assumption.
    (mark,) = rows['hub.base']['marks']
    assert mark[1] == 'assumption' and numbers[mark[0]]['record'] == ['ASM-TEMPO']
    # A value worked out from others has no mark: its equation leads to the cited inputs.
    assert rows['hub.give']['marks'] == []


def test_only_what_shows_is_cited(model):
    found = drawn(model, equations('hub', more='\n[references]\nshow = true\n'))['panels']
    # The input `quiet` is in no line: its record's source has no entry.
    assert 'hub.quiet' not in rows_of({'panels': found})
    assert not [entry for entry in found['references'] if 'SRC-HIDDEN' in entry['record']]


def test_kinds_leave_entries_out_but_never_the_assumptions(model):
    whole = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\n'))['panels']
    some = drawn(model, equations(*CARDS, more='\n[references]\nshow = true\nkinds = ["assumption"]\n'))[
        'panels'
    ]
    assert {entry['kind'] for entry in some['references']} == {'assumption'}
    assert set(some['left_out']) == {entry['kind'] for entry in whole['references']} - {'assumption'}
    assert [entry['text'] for entry in some['references']] == [
        entry['text'] for entry in whole['references'] if entry['kind'] == 'assumption'
    ]


def test_an_input_has_the_range_of_its_model_and_the_note_shows_with_it(model):
    found = drawn(model, equations('hub'))['panels']
    rows = {row['key']: row for row in found['symbols']}
    assert (rows['hub.x']['range'], rows['hub.x']['range_status']) == (['1 people/h', '9 people/h'], 'chosen')
    assert rows['hub.y']['range'] is None
    assert found['note'] == panels.NOTE
    # Without a range on any shown row, no note.
    assert drawn(model, equations('zebra'))['panels']['note'] is None


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
                written = next((w for w, event in events.items() if event == node.event), None)
                if written is None:
                    written = f'e_{{{len(events) + 1}}}'
                    events[written] = node.event
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
    rows = rows_of(doc)
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
        for run in (None, 'busy'):
            assert check_latex(drawn(model, text, run), seeds=(1, 2)) > 10


def test_the_since_and_the_count_of_an_event_are_its_symbols(model):
    doc = drawn(model, equations('hub', more='depth = 2\n'))
    rows = rows_of(doc)
    go = rows['hub.go']
    # `flush` asks for x plus the count of `go` once per hour: the row of `go` has its count.
    assert go['kind'] == 'event' and go['unit'] == 'h' and go['count'] is not None
    assert go['count']['base'] == 'N' and go['count']['sub'] == go['symbol']['sub']
    (hub,) = doc['panels']['equations']
    (flush,) = [item for item in hub['lines'] if item['part'] == 'hub.flush' and item['kind'] == 'rate']
    assert go['count']['latex'] in flush['latex']


# ---- the LaTeX fragment (D-57) ------------------------------------------------------------------


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
    for name in panels.PACKAGES:
        if (
            finder
            and not subprocess.run(
                [finder, f'{name}.sty'], capture_output=True, text=True, check=False
            ).stdout.strip()
        ):
            return None, f'the TeX installation has no {name}.sty, so the fragment is not compiled'
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
