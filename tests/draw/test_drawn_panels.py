"""The drawing of the panels under the map (napkin/draw/layout.py and svg.py; D-53, D-55, D-57): the
Equations, the Symbols table, the References list, the note on a chosen range, and the symbol tags of
the stock rows.

`check` (tests/draw/test_layout.py) and `check_svg` (tests/draw/test_svg.py) hold every property of a
picture with panels: no box on another, every row inside its panel and the panels under the legend; the
links only in the References, to their own `http` or `https` addresses; each mark a number of an entry
in the colour of its kind; the `data-latex` of each line its LaTeX; the tags exactly on the shown stock
rows of `tags`; "chosen range" exactly on the chosen ranges, and the note exactly when one shows.
`check_model` adds that no visible text shows an ID of the library.

The pictures: the synthetic model of `test_panels.py` with its library of records of every kind, under
stylesheets that turn each key of `[equations]` and `[references]`; pictures that Hypothesis makes, with
panels of random trees, words, marks and addresses; and counterexamples. Every catalogue model with every
drawn card in `[equations] things` and the references shown waits for stage M (`test_catalogue.py`).
"""

from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

import pytest
from hypothesis import given
from hypothesis import strategies as st

from napkin.draw import layout as layouts
from napkin.draw import notation, panels
from napkin.draw.layout import layout
from napkin.draw.notation import Assign, Call, Cases, Cmp, Count, Deriv, In, Neg, Num, Op, Since, Sym, Time
from napkin.draw.references import COLOURS as MARK_COLOURS
from napkin.draw.references import KIND_WORDS, KINDS
from napkin.draw.svg import COLOURS, NAMESPACE, svg
from tests.draw.test_layout import SHAPE, WORDS, arrow, check, contains, picture_of, pictures
from tests.draw.test_layout import card as sample_card
from tests.draw.test_panels import CARDS, check_latex, equations
from tests.draw.test_panels import drawn as drawn_picture
from tests.draw.test_panels import model as model  # the fixture of the synthetic model
from tests.draw.test_svg import (
    check_model,
    check_svg,
    contrast,
    marks_in,
    parts,
    same_bytes_in_other_processes,
    visible,
)

SVG = f'{{{NAMESPACE}}}'
REFERENCES = '\n[references]\nshow = true\n'
# Stylesheets that turn each key of `[equations]` and `[references]` of the fixture.
SHEETS = (
    equations(*CARDS) + REFERENCES,
    equations('Zone', 'hub', more='instances = "each"\ndepth = 3\nchecks = true\n') + REFERENCES,
    equations('hub', more='symbols = false\n') + REFERENCES,
    equations('zebra'),
    equations(*CARDS, more='tags = false\nwidth = 320\nlines = 1\n') + REFERENCES,
    equations(*CARDS, more='width = 2400\nlines = 8\n') + REFERENCES + 'kinds = ["assumption"]\n',
)


def drawn(doc):
    """The layout and the SVG of a picture, with every property of both."""
    found = layout(doc)
    check(doc, found)
    text = svg(doc, found)
    check_svg(doc, found, text)
    return found, text


def map_of(found):
    """What a layout places above its legend, and the legend."""
    return (found.cards, found.machines, found.routes, found.frames, found.legend, found.bundles)


# ---- the fixture ----------------------------------------------------------------------------------


@pytest.mark.parametrize('run', [None, 'busy'])
@pytest.mark.parametrize('sheet', SHEETS)
def test_every_panel_of_the_fixture_holds_every_property(model, sheet, run):
    doc = drawn_picture(model, sheet, run)
    found, text = drawn(doc)
    root = ET.fromstring(text)
    check_model(model, root)
    # The LaTeX of each line, which `data-latex` holds, reads back to the line's trees.
    assert check_latex(doc) > 0
    settings = doc['panels']['settings']
    assert found.width >= settings['width'] + 2 * layouts.MARGIN
    assert all(panel.box.width == settings['width'] for panel in found.panels)


def test_the_fixture_shows_marks_of_every_colour_and_each_entry_says_its_kind(model):
    doc = drawn_picture(model, equations(*CARDS) + REFERENCES)
    _, text = drawn(doc)
    root = ET.fromstring(text)
    colours = {cls.removeprefix('mark-') for _, found in marks_in(root) for cls in found if cls != 'mark'}
    assert colours == set(MARK_COLOURS)
    # Without colour, the words of each entry say its kind: they start with the words of the kind (an
    # assumption's from its review status).
    for element, entry in zip(
        (e for kind, e, _, _ in parts(root) if kind == 'reference'), doc['panels']['references']
    ):
        words = visible(element).split(' ', 1)[1]
        assert words.startswith(entry['label'])
        if entry['kind'] != 'assumption':
            assert entry['label'] == KIND_WORDS[entry['kind']]


@pytest.mark.parametrize('theme', [0, 1])
def test_the_colours_of_the_marks_differ_and_read_on_the_paper_and_the_stripes(theme):
    # Each mark is a small number: WCAG's least contrast for small text, 4.5 to 1, on the paper and on
    # the stripe of a row of the table; and each kind has a colour of its own.
    colours = [COLOURS[f'mark-{colour}'][theme] for colour in MARK_COLOURS]
    assert len(set(colours)) == len(MARK_COLOURS) == 4
    # A colour means one thing in the picture: no mark has the colour of a kind of arrow or of the
    # start.
    taken = {COLOURS[name][theme] for name in (*layouts.KINDS, 'start')}
    assert not set(colours) & taken
    for colour in (*colours, COLOURS['link'][theme]):
        for ground in ('paper', 'card'):
            assert contrast(colour, COLOURS[ground][theme]) >= 4.5, (colour, ground)


def test_without_tags_the_panels_move_nothing_of_the_map(model):
    plain = drawn_picture(model, '')
    shown = drawn_picture(model, equations(*CARDS, more='tags = false\n') + REFERENCES)
    found, _ = drawn(shown)
    assert map_of(found) == map_of(layout(plain))
    assert found.height > layout(plain).height


def test_the_svg_of_a_picture_with_panels_has_the_same_bytes_in_other_processes(model, tmp_path):
    doc = drawn_picture(model, equations(*CARDS) + REFERENCES)
    same_bytes_in_other_processes(doc, tmp_path / 'picture.json')


# ---- counterexamples ------------------------------------------------------------------------------


def edited(model, change):
    doc = drawn_picture(model, equations(*CARDS) + REFERENCES)
    change(doc['panels'])
    return doc


@pytest.mark.parametrize(
    'url',
    ['javascript:alert(1)', 'ftp://files.example/a', 'mailto:a@b.example', '//no.scheme.example', 'https://'],
)
def test_an_address_that_is_not_http_or_https_has_no_link(model, url):
    doc = edited(model, lambda panels: panels['references'][0].update(url=url, link_text='a link'))
    _, text = drawn(doc)
    root = ET.fromstring(text)
    (first,) = [e for kind, e, _, _ in parts(root) if kind == 'reference' and e.get('data-number') == '1']
    assert not list(first.iter(f'{SVG}a'))
    assert all(a.get('href') != url for a in root.iter(f'{SVG}a'))


def test_a_link_keeps_its_address_and_a_text_never_makes_an_element(model):
    url = 'https://a.example/p?q="1"&r=<2>#s'

    def change(panels):
        panels['references'][0].update(url=url, link_text='a.example', text='See <a href="x">this</a> & that')

    doc = edited(model, change)
    _, text = drawn(doc)
    root = ET.fromstring(text)
    (link,) = [a for a in root.iter(f'{SVG}a') if a.get('href') == url]
    assert ''.join(link.itertext()) == 'a.example'
    # The text shows as text: no element comes from it.
    entries = [e for kind, e, _, _ in parts(root) if kind == 'reference']
    assert '<a href="x">this</a>' in visible(entries[0])
    linked = [e.get('data-number') for e in entries if list(e.iter(f'{SVG}a'))]
    assert linked == [str(e['number']) for e in doc['panels']['references'] if e['url']]


def test_data_latex_keeps_every_character_of_the_latex(model):
    latex = 'a"b<c>&d\ne\tf\r\\frac{1}{2}\'s'
    doc = edited(model, lambda panels: panels['equations'][0]['lines'][0].update(latex=latex))
    _, text = drawn(doc)
    (first, *_) = [e for kind, e, _, _ in parts(ET.fromstring(text)) if kind == 'equation']
    assert first.get('data-latex') == latex


def test_the_time_since_an_event_and_its_count_are_drawn_as_their_symbols(model):
    # As the LaTeX writes them (`panels.line_latex`): the symbol of the event and the symbol of its
    # count, never the clock letter of the typesetter under them.
    doc = drawn_picture(model, equations('hub'))
    rows = {row['key']: row for row in doc['panels']['symbols']}
    found, _ = drawn(doc)
    lines = [row for panel in found.panels for row in panel.rows if isinstance(row, layouts.EquationLine)]
    given = [line for block in doc['panels']['equations'] for line in block['lines']]
    clocked = 0
    for row, line in zip(lines, given):
        trees = [line['lhs'], line['rhs']] if line['lhs'] is not None else line['math']
        nodes = [node for tree in trees for node in notation.nodes(notation.from_dict(tree))]
        # The time since an event is its symbol (τ), and its count the symbol of the count (N).
        wanted = {
            (node.target, 'count' if isinstance(node, Count) else 'symbol')
            for node in nodes
            if isinstance(node, (Since, Count))
        }
        if not wanted:
            continue
        clocked += 1
        reading = ''.join(item.equation.reading() for item in row.items if isinstance(item, layouts.Math))
        for event, field in wanted:
            assert notation_reading(rows[event][field]) in reading
        assert 'ττ' not in reading and 'Nτ' not in reading
    assert clocked


def test_a_yes_no_formula_is_drawn_with_iff(model):
    doc = drawn_picture(model, equations('hub'))
    _, text = drawn(doc)
    root = ET.fromstring(text)
    readings = {
        element.get('data-part'): ''.join(element.itertext())
        for element in root.iter(f'{SVG}g')
        if element.get('class') == 'equation' and element.get('data-part')
    }
    given = {line['part']: line for block in doc['panels']['equations'] for line in block['lines']}
    for part, line in given.items():
        if line['kind'] in ('balance', 'rate', 'formula'):
            relation = line['relation']
            assert relation in readings[part], part
            assert ('⇔' in readings[part]) == (relation == '⇔'), part
    assert any(line['relation'] == '⇔' for line in given.values())


def test_a_jump_says_its_event_by_name_and_an_event_that_only_jumps_name_has_no_row(model):
    doc = drawn_picture(model, equations('hub'))
    _, text = drawn(doc)
    root = ET.fromstring(text)
    jumps = [
        line for block in doc['panels']['equations'] for line in block['lines'] if line['kind'] == 'jump'
    ]
    # The fixture's events `go`, `later` and `turn`, each in words.
    assert {line['event'] for line in jumps} == {'hub.go', 'hub.later', 'hub.turn'}
    for line in jumps:
        assert line['when'] == line['event'].split('.')[-1]
    drawn_lines = [
        ''.join(element.itertext())
        for element in root.iter(f'{SVG}g')
        if element.get('class') == 'equation'
        and element.get('data-latex') in {line['latex'] for line in jumps}
    ]
    assert len(drawn_lines) == len(jumps)
    assert all(any(f'at {line["when"]}' in reading for reading in drawn_lines) for line in jumps)
    fragment = panels.latex(doc)
    assert all(rf'\text{{at {line["when"]}}}' in fragment for line in jumps)
    # `go` is read by a time since and a count, so it has a row; `later` only jumps name: no row, and
    # no τ = 0 in the picture.
    rows = {row['key'] for row in doc['panels']['symbols']}
    assert 'hub.go' in rows and 'hub.later' not in rows and 'hub.turn' not in rows
    assert '= 0' not in ' '.join(drawn_lines)


def test_a_list_that_leaves_out_kinds_says_which(model):
    from napkin.draw.references import KINDS as REFERENCE_KINDS
    from napkin.draw.references import LEFT_OUT_WORDS

    every = drawn_picture(model, equations(*CARDS) + REFERENCES)
    some = drawn_picture(model, equations(*CARDS) + REFERENCES + 'kinds = ["assumption"]\n')
    # With every kind, nothing is left out; with assumptions only, exactly the other kinds that the
    # full list holds, in the order of the kinds.
    assert every['panels']['left_out'] == []
    held = {entry['kind'] for entry in every['panels']['references']}
    expected = [kind for kind in REFERENCE_KINDS if kind in held and kind != 'assumption']
    assert expected and some['panels']['left_out'] == expected
    # The SVG says it under the heading of the References, and so does the LaTeX, before the list.
    _, text = drawn(some)
    root = ET.fromstring(text)
    (line,) = [g for g in root.iter(f'{SVG}g') if g.get('class') == 'left-out']
    said = ' '.join(''.join(line.itertext()).split())
    assert said.startswith('Not listed:') and all(LEFT_OUT_WORDS[kind] in said for kind in expected)
    fragment = panels.latex(some)
    assert fragment.index('Not listed:') < fragment.index(r'\begin{enumerate}')
    assert 'Not listed' not in panels.latex(every)


def notation_reading(symbol):
    from napkin.draw import typeset

    return typeset.letters(symbol['base']) + typeset.primes(symbol['prime']) + (symbol['sub'] or '')


def test_a_tag_widens_its_card_and_keeps_the_whole_name():
    name = 'A stock whose long name fills the widest tank of a card'
    stock = {'key': 'a.s', 'name': name, 'kind': 'stock'}
    plain = picture_of([sample_card('a', stocks=[stock])])
    tagged = copy.deepcopy(plain)
    tagged['panels'] = panels_of(tagged, tags={'a.s': ('W', "'", 'a,b')})
    before, after = layout(plain), layout(tagged)
    check(tagged, after)
    (old,), (new,) = before.cards[0].stocks, after.cards[0].stocks
    assert new.text == old.text
    assert after.cards[0].box.width == before.cards[0].box.width + layouts_tag_room(new)


def layouts_tag_room(stock):
    return stock.box.right - stock.tag.box.x + layouts.TAG_GAP


def test_a_start_too_wide_for_its_column_is_its_text_and_a_short_start_under_it_is_math():
    # A narrow table with every column: the Value column is too narrow for a sum of six stocks, also
    # when the sum is cut. So the row's own start reads as the file writes it. The short start that an
    # option gives fits, and it is typeset. The one math of the cell is then the option's start, and no
    # check can read it as the row's own.
    stocks = [{'key': f'a.v{k}', 'name': f'stock {k}', 'kind': 'stock'} for k in range(6)]
    doc = picture_of([sample_card('a', stocks=stocks)])
    doc['panels'] = panels_of(doc, width=320, lines=1)
    first, *others = (stock['key'] for stock in stocks)

    def total(keys):
        node = Op('*', Num(2), Sym(keys[0]))
        for key in keys[1:]:
            node = Op('+', node, Op('*', Num(2), Sym(key)))
        return notation.as_dict(node)

    own, other = ('W', "'", None), ('x', '', 'jhos,c')
    text = 'the start as the file writes it'
    row = row_of(
        first,
        own,
        'stock',
        value_math=total([first, *others]),
        value=text,
        options=[{'option': 'an option', 'value': 'its start', 'math': total([first]), 'marks': []}],
        option_count=1,
        unit='people/h',
        range=['from 1 to 20 of them', '5 h'],
        range_status='declared',
        distribution='pert(1 h, 3 h, 12 h)',
    )
    doc['panels']['symbols'] = [row, *(row_of(key, other, 'stock') for key in others)]
    found, _ = drawn(doc)
    (table,) = [panel for panel in found.panels if panel.kind == 'symbols']
    (shown,) = [item for item in table.rows if item.key == first]
    (cell,) = [item for item in shown.cells if item.column == 'value']
    assert contains(cell.items, text)
    (reading,) = [item.equation.reading() for item in cell.items if isinstance(item, layouts.Math)]
    assert notation_reading(symbol_of(*own)) in reading
    assert notation_reading(symbol_of(*other)) not in reading


def room_for_two(width):
    """The least width of a picture that holds two panels of `width` side by side."""
    return 2 * layouts.MARGIN + 2 * width + layouts.PANEL_GAP


def with_two_panels(doc, width):
    """A picture with an Equations panel and a Symbols table, each `width` wide, and no tag."""
    doc = copy.deepcopy(doc)
    doc['panels'] = panels_of(doc, width=width)
    doc['panels']['symbols'] = [row_of(f'{doc["cards"][0]["id"]}.v', ('W', '', None))]
    return doc


def test_a_frame_in_the_margin_makes_no_room_for_a_second_column_of_panels():
    # A frame reaches into the right margin: its right edge and a margin are more than the width of
    # the picture. Two panels that need a little more than that width go one under another.
    cards = [sample_card(name, place={'column': k, 'row': None}) for k, name in enumerate('abcd', start=1)]
    doc = picture_of(cards, groups=[{'label': 'G', 'members': ['d']}])
    plain = layout(doc)
    (frame,) = plain.frames
    width = math.floor((plain.width - room_for_two(0)) / 2) + 1
    assert plain.width < room_for_two(width) <= frame.box.right + layouts.MARGIN
    found, _ = drawn(with_two_panels(doc, width))
    assert [panel.box.x for panel in found.panels] == [layouts.MARGIN, layouts.MARGIN]


def test_the_gap_after_the_last_column_is_room_for_a_second_column_of_panels():
    # An arrow between two cards of the last column runs on a track in the gap at its right. The
    # picture is as wide as that track, the edge of the gap and a margin. Two panels that need exactly
    # that width go side by side, though the track and a margin alone are narrower.
    cards = [sample_card(name, place={'column': k, 'row': None}) for k, name in enumerate('abc', start=1)]
    cards += [sample_card(name, place={'column': 4, 'row': None}) for name in 'de']
    doc = picture_of(cards, arrows=[arrow('d', 'e')])
    plain = layout(doc)
    track = max(x for route in plain.routes for x, _ in route.points)
    assert plain.width == track + layouts.GAP_EDGE + layouts.MARGIN
    width = math.floor((plain.width - room_for_two(0)) / 2)
    assert track + layouts.MARGIN < room_for_two(width) <= plain.width
    found, _ = drawn(with_two_panels(doc, width))
    second = layouts.MARGIN + width + layouts.PANEL_GAP
    assert [panel.box.x for panel in found.panels] == [layouts.MARGIN, second]


def test_a_block_without_lines_says_so_and_a_template_names_its_members(model):
    doc = drawn_picture(model, equations(*CARDS) + REFERENCES)
    blocks = doc['panels']['equations']
    blocks[0]['lines'] = []
    found, text = drawn(doc)
    empty = [row for row in found.panels[0].rows if isinstance(row, layouts.Note)]
    assert [row.kind for row in empty] == ['empty']
    grouped = [block for block in blocks if len(block['members']) > 1]
    assert grouped
    root = ET.fromstring(text)
    heads = {e.get('data-block'): visible(e) for kind, e, _, _ in parts(root) if kind == 'block'}
    for block in grouped:
        assert all(member['title'] in heads[block['name']] for member in block['members'])


# ---- pictures that Hypothesis makes ---------------------------------------------------------------

BASES = ('W', 'x', 'S', 'delta', 'tau', 'Omega', 'β', 'q')
SUBS = (None, 'a', 'jhos,c', '2', 'a,1', 'x,y,z,12')
UNITS = (None, 'h', 'm^2', 'people/h', 'Mgal/day', 'person-days')
ADDRESSES = (None, 'https://a.example/p?q=1&r=2', 'http://b.example', 'javascript:alert(1)', 'mailto:x@y')


def text_of_symbol(base, prime, sub):
    """The text of a symbol, as `symbols.Symbol.text` writes it."""
    return base + ("'" if prime else '') + (f'_{sub}' if sub else '')


def symbol_of(base, prime, sub):
    return {'base': base, 'prime': prime, 'sub': sub, 'text': text_of_symbol(base, prime, sub), 'latex': base}


def row_of(key, symbol, kind='input', **given):
    found = {
        'key': key,
        'symbol': symbol_of(*symbol),
        'count': None,
        'meaning': f'The meaning of {key}',
        'kind': kind,
        'unit': None,
        'value': None,
        'value_math': None,
        'options': [],
        'option_count': 0,
        'instances': [],
        'range': None,
        'range_status': None,
        'distribution': None,
        'marks': [],
        'range_marks': [],
        'records': [],
    }
    return {**found, **given}


def panels_of(doc, tags=None, **settings):
    """Small panels for a picture of the layout's tests: an empty block for its first card, a row for
    each tag, and the tags (`{stock key: (base, prime, sub)}`)."""
    tags = tags or {}
    first = doc['cards'][0]
    return {
        'settings': {
            'depth': 1,
            'width': 720,
            'lines': 3,
            'tags': True,
            'symbols': True,
            'checks': False,
            'instances': 'together',
            'references': False,
            'kinds': list(KINDS),
            **settings,
        },
        'equations': [
            {
                'name': first['id'],
                'title': first['title'],
                'template': None,
                'members': [{'entity': first['id'], 'card': first['id'], 'title': first['title']}],
                'lines': [],
            }
        ],
        'symbols': [row_of(key, symbol, 'stock') for key, symbol in tags.items()],
        'references': [],
        'tags': {key: text_of_symbol(*symbol) for key, symbol in tags.items()},
        'note': None,
    }


def leaves(keys, events):
    found = [
        st.sampled_from(keys).map(Sym),
        st.builds(Num, st.integers(0, 10**7), st.sampled_from(UNITS)),
        st.builds(Num, st.floats(0, 1e9, allow_nan=False, allow_infinity=False), st.sampled_from(UNITS)),
        st.just(Time()),
    ]
    if events:
        found += [st.sampled_from(events).map(Since), st.sampled_from(events).map(Count)]
    return st.one_of(*found)


def trees(keys, events):
    return st.recursive(
        leaves(keys, events),
        lambda inner: st.one_of(
            st.builds(Op, st.sampled_from(('+', '-', '*', '/', '**')), inner, inner),
            st.builds(lambda a, b: Cmp(('<=',), (a, b)), inner, inner),
            st.builds(In, inner, inner, inner),
            st.builds(lambda c, a, b: Cases(((Cmp(('>',), (c, Num(0))), a),), b), inner, inner, inner),
            st.builds(Neg, inner),
            st.builds(lambda a, b: Call('min', (a, b)), inner, inner),
        ),
        max_leaves=10,
    )


@st.composite
def panel_pictures(draw):
    """A picture of the layout's tests with panels: blocks of lines of every kind with random trees,
    words, marks and LaTeX; a row for each key, with random words, values, options, ranges and marks; a
    References list with random kinds, words and addresses; tags on some stock rows; any width, number of
    lines, and the table on or off."""
    doc = draw(pictures(groups=True))
    stocks = [stock['key'] for card in doc['cards'] for stock in card['stocks']]
    keys = [*stocks, *(f'{card["id"]}.v' for card in doc['cards'])]
    events = [f'{card["id"]}.e' for card in doc['cards']]
    symbols = st.tuples(st.sampled_from(BASES), st.sampled_from(("'", '')), st.sampled_from(SUBS))
    count = draw(st.integers(0, 6))
    entries = []
    for number in range(1, count + 1):
        kind = draw(st.sampled_from(KINDS))
        entries.append(
            {
                'number': number,
                'kind': kind,
                'label': KIND_WORDS[kind],
                'text': draw(WORDS),
                'url': draw(st.sampled_from(ADDRESSES)),
                'link_text': draw(st.one_of(st.none(), WORDS)),
                'hover': draw(WORDS),
                'record': [f'R-{number}', f'claim-{number}'],
            }
        )
    marks = (
        st.lists(st.sampled_from([[e['number'], e['kind']] for e in entries]), max_size=12)
        if entries
        else st.just([])
    )
    lines = []
    tree = trees(keys, events)
    for kind in draw(
        st.lists(st.sampled_from(('balance', 'rate', 'bound', 'together', 'jump', 'check')), max_size=8)
    ):
        line = {
            'kind': kind,
            'lhs': None,
            'rhs': None,
            'math': [],
            'words': draw(st.one_of(st.none(), WORDS)),
            'part': draw(st.sampled_from(keys)),
            'event': None,
            'outcome': None,
            'keys': [],
            'marks': draw(marks),
            'records': draw(st.lists(st.sampled_from(('R-1', 'claim-2', 'own')), max_size=3, unique=True)),
            'latex': draw(WORDS),
        }
        if kind == 'balance':
            line.update(lhs=Deriv(draw(st.sampled_from(keys))), rhs=draw(tree))
        elif kind == 'rate':
            line.update(lhs=Sym(draw(st.sampled_from(keys))), rhs=draw(tree))
        elif kind == 'jump':
            assign = Assign(draw(st.sampled_from(keys)), draw(st.sampled_from(('=', '+=', '-='))), draw(tree))
            line.update(
                math=[assign],
                event=draw(st.sampled_from(events)),
                outcome=draw(st.sampled_from((None, 'shut_down'))),
            )
        else:
            line['math'] = draw(st.lists(tree, min_size=1, max_size=4))
        for name in ('lhs', 'rhs'):
            if line[name] is not None:
                line[name] = notation.as_dict(line[name])
        line['math'] = [notation.as_dict(item) for item in line['math']]
        lines.append(line)
    first = doc['cards'][0]
    blocks = [
        {
            'name': first['id'],
            'title': draw(WORDS),
            'template': 'T' if len(doc['cards']) > 1 else None,
            'members': [{'entity': c['id'], 'card': c['id'], 'title': c['title']} for c in doc['cards'][:3]],
            'lines': lines,
        }
    ]
    rows = []

    def start(kind):
        # A start that a formula sets, of a stock: a sum of 1 to 6 terms, each 2 times a key of a row.
        if kind != 'stock' or not draw(st.booleans()):
            return None
        named = draw(st.lists(st.sampled_from(keys), min_size=1, max_size=6))
        node = Op('*', Num(2), Sym(named[0]))
        for other in named[1:]:
            node = Op('+', node, Op('*', Num(2), Sym(other)))
        return notation.as_dict(node)

    def option(kind):
        math = start(kind)
        value = draw(WORDS) if math else draw(st.one_of(st.none(), WORDS))
        return {'option': draw(WORDS), 'value': value, 'math': math, 'marks': draw(marks)}

    for key in [*keys, *events]:
        option_count = draw(st.integers(0, 5))
        shown = option_count <= 3
        status = draw(st.sampled_from((None, 'chosen', 'declared')))
        kind = 'event' if key in events else draw(st.sampled_from(('input', 'fixed', 'stock', 'formula')))
        rows.append(
            row_of(
                key,
                draw(symbols),
                kind,
                count=symbol_of('N', '', 'e') if key in events else None,
                meaning=draw(WORDS),
                unit=draw(st.sampled_from(UNITS)),
                value_math=(value_math := start(kind)),
                value=draw(WORDS) if value_math else draw(st.one_of(st.none(), WORDS)),
                options=[option(kind) for _ in range(option_count if shown else 0)],
                option_count=option_count,
                instances=[{'entity': 'x', 'title': draw(WORDS), 'value': draw(WORDS), 'math': start(kind)}]
                if draw(st.booleans())
                else [],
                range=None if status is None else [draw(WORDS), draw(st.sampled_from(('5 h', '7', None)))],
                range_status=status,
                distribution=draw(st.one_of(st.none(), WORDS)),
                marks=draw(marks),
                range_marks=draw(marks) if status else [],
                records=draw(st.lists(st.sampled_from(('R-1', 'own')), max_size=2, unique=True)),
            )
        )
    on = draw(st.booleans())
    tagged = draw(st.lists(st.sampled_from(stocks), unique=True)) if stocks and on else []
    by_key = {row['key']: row for row in rows}
    table = draw(st.booleans())
    chosen = table and any(row['range'] is not None and row['range_status'] == 'chosen' for row in rows)
    doc['panels'] = {
        'settings': {
            'depth': 1,
            'width': draw(st.integers(320, 2400)),
            'lines': draw(st.integers(1, 8)),
            'tags': on,
            'symbols': table,
            'checks': False,
            'instances': 'together',
            'references': bool(entries),
            'kinds': list(KINDS),
        },
        'equations': blocks,
        'symbols': rows,
        'references': entries,
        'tags': {key: by_key[key]['symbol']['text'] for key in tagged},
        'note': 'A note on a chosen range.' if chosen else None,
    }
    return doc


@SHAPE
@given(panel_pictures())
def test_every_property_holds_on_panels_that_hypothesis_makes(doc):
    drawn(doc)
