"""The events of a card (D-56, `[triggers]`): what each level shows on the card and in its tooltip, the
limits of `lines` and `events`, the options of an event, the runs, and the stylesheet's checks.

The models are the synthetic models of the trigger lines (`test_trigger_levels` reads the texts of
`test_triggers.py`), and each expectation follows from the lines of `triggers.card_lines`, which those
tests check. Every picture, layout and SVG of these tests holds every property of `test_picture.py`,
`test_layout.py` and `test_svg.py`. The catalogue test puts every card at `rules` (`test_catalogue.py`,
for stage M).
"""

from __future__ import annotations

import copy
import dataclasses
import xml.etree.ElementTree as ET

import pytest
from hypothesis import given
from hypothesis import strategies as st

from napkin.draw import layout as layouts
from napkin.draw import model_map, style
from napkin.draw.layout import layout
from napkin.draw.model_map import picture
from napkin.draw.style import StyleError
from napkin.draw.svg import svg
from napkin.draw.things import Things
from napkin.draw.triggers import ELLIPSIS, card_lines, words
from tests.draw.models import compiled, package
from tests.draw.test_layout import SHAPE, check, pictures
from tests.draw.test_picture import picture_problems
from tests.draw.test_svg import SVG, check_svg, parts
from tests.draw.test_triggers import EVENTS, LISTS, SWITCHING

MODELS = {'events': EVENTS, 'lists': LISTS, 'switching': SWITCHING}


def model_of(name):
    return Things(compiled(MODELS[name]))


def drawn(found, sheet, run=None):
    """The picture of a model with a stylesheet, its layout and its SVG, each with every property."""
    assert style.check(sheet, found) == []
    doc = picture(found, sheet, run)
    assert picture_problems(doc) == []
    placed_layout = layout(doc)
    text = svg(doc, placed_layout)
    check(doc, placed_layout)
    check_svg(doc, placed_layout, text)
    return doc, placed_layout, text


def placed(found, card_id):
    return next(card for card in found.cards if card.id == card_id)


def tooltip(text, card_id):
    """The tooltip of a card of an SVG."""
    root = ET.fromstring(text)
    return next(e for kind, e, _, _ in parts(root) if kind == 'card' and e.get('data-thing') == card_id)[
        0
    ].text


def keys_of(found, card_id, runs=None):
    """The events of a card that one of the runs can start, as the picture names them, `card.event`, in
    written order."""
    runs = found.runs if runs is None else runs
    return [
        f'{card_id}.{event.name}'
        for event in found.events(card_id)
        if any(found.startable(run).get(event.path, True) for run in runs)
    ]


def lines_of(found, card_id, runs=None):
    keys = keys_of(found, card_id, runs)
    return [line for line in card_lines(found, card_id) if line.key in keys]


def without_key(doc):
    """The picture without the key `triggers`: as it was before `[triggers]`."""
    bare = copy.deepcopy(doc)
    for card in bare['cards']:
        del card['triggers']
    return bare


def row_width(card):
    """The width of the text of a row of the events of a card."""
    return card.box.width - 2 * layouts.PAD - layouts.TRIGGER_MARK


def measure(text):
    return layouts.text_width(text, layouts.SMALL_SIZE)


# ---- off by default -------------------------------------------------------------------------------


@pytest.mark.parametrize('name', sorted(MODELS))
def test_without_triggers_no_card_shows_its_events(name):
    doc, found, text = drawn(model_of(name), style.Style())
    assert all(card['triggers'] is None for card in doc['cards'])
    assert all(card.triggers == () and card.events == () for card in found.cards)
    # The layout is the one of the picture without the key, and the SVG draws no row.
    assert layout(without_key(doc)) == found
    assert not [kind for kind, *_ in parts(ET.fromstring(text)) if kind == 'trigger']


# ---- the levels -----------------------------------------------------------------------------------


def test_count_shows_one_row_with_the_number_of_the_card_s_events():
    model = model_of('events')
    _, found, _ = drawn(model, style.read('[triggers]\ncount = ["a", "b"]\n'))
    for card_id in ('a', 'b'):
        (row,) = placed(found, card_id).triggers
        assert row.kind == 'count' and row.events == tuple(keys_of(model, card_id))
        assert str(len(keys_of(model, card_id))) in row.lines[0].split()


def test_names_shows_each_event_s_name_in_the_order_of_the_file():
    model = model_of('events')
    _, found, _ = drawn(model, style.read('[triggers]\nnames = ["a", "depot"]\nevents = 20\n'))
    for card_id in ('a', 'depot'):
        keys = keys_of(model, card_id)
        rows = placed(found, card_id).triggers
        assert [row.lines for row in rows] == [(words(key.rpartition('.')[2]),) for key in keys]
        assert [row.events for row in rows] == [(key,) for key in keys]


@pytest.mark.parametrize('lines', [1, 2, 3, 4])
def test_rules_shows_each_line_in_at_most_lines_rows_within_the_card(lines):
    model = model_of('events')
    _, found, text = drawn(
        model, style.read(f'[triggers]\nrules = ["a", "depot"]\nlines = {lines}\nevents = 20\n')
    )
    cut = []
    for card_id in ('a', 'depot'):
        card = placed(found, card_id)
        assert card.box.width >= layouts.RULES_WIDTH
        width = row_width(card)
        full = {line.key: line for line in lines_of(model, card_id)}
        assert [row.events[0] for row in card.triggers] == list(full)
        for row in card.triggers:
            line = full[row.events[0]]
            assert 1 <= len(row.lines) <= lines
            assert all(measure(found_line) <= width for found_line in row.lines)
            joined = ' '.join(row.lines)
            if row.lines[-1].endswith(ELLIPSIS):
                # A cut line shows the start of the line, and the line is too long for its rows.
                cut.append(row)
                assert line.full.startswith(joined[: -len(ELLIPSIS)].rstrip())
                assert measure(line.full) > width
            else:
                assert joined == line.full
            if measure(line.full) <= width:
                assert row.lines == (line.full,)
            # Rows that break at spaces hold at most this much of a line.
            if measure(line.full) > lines * width + (lines - 1) * measure(' '):
                assert row in cut
            # The name of the event starts the row, in bold.
            assert row.lines[0][: row.strong[0]] == line.name
        assert tooltip(text, card_id).count('Rule: ') == sum(line.rule is not None for line in full.values())
    assert cut or lines > 1


def test_the_rows_of_a_rule_start_with_the_name_in_bold_and_their_tooltips_give_the_line():
    model = model_of('events')
    _, _, text = drawn(model, style.read('[triggers]\nrules = ["a"]\nevents = 20\n'))
    lines = {line.key: line for line in lines_of(model, 'a')}
    rows = [e for kind, e, card, _ in parts(ET.fromstring(text)) if kind == 'trigger' and card == 'a']
    assert [row.get('data-event') for row in rows] == list(lines)
    for row in rows:
        line = lines[row.get('data-event')]
        assert row[0].text.startswith(line.full)
        bold = row.find(f'{SVG}text').find(f'{SVG}tspan')
        assert bold is not None and bold.text == line.name


@pytest.mark.parametrize('level', ['names', 'rules'])
@pytest.mark.parametrize('limit', [None, 1, 4, 20])
def test_events_limits_the_rows_and_a_last_row_counts_the_rest(level, limit):
    model = model_of('events')
    text = f'[triggers]\n{level} = ["a"]\n' + ('' if limit is None else f'events = {limit}\n')
    _, found, _ = drawn(model, style.read(text))
    keys = keys_of(model, 'a')
    shown = min(limit or model_map.DEFAULT_TRIGGER_EVENTS, len(keys))
    rows = placed(found, 'a').triggers
    assert [row.events for row in rows[:shown]] == [(key,) for key in keys[:shown]]
    rest = len(keys) - shown
    assert len(rows) == shown + (1 if rest else 0)
    if rest:
        assert rows[-1].kind == 'more' and rows[-1].events == tuple(keys[shown:])
        assert str(rest) in rows[-1].lines[0]
    # The tooltip of the card names every event, those after the last row too.
    assert [line.event for line in placed(found, 'a').events] == keys


def test_hover_shows_nothing_on_the_card_and_every_line_in_its_tooltip():
    model = model_of('events')
    _, found, text = drawn(model, style.read('[triggers]\nhover = ["a", "b", "depot"]\n'))
    _, bare, _ = drawn(model, style.Style())
    # The layout is the one without [triggers]; only the tooltips gain the lines.
    assert [dataclasses.replace(card, events=()) for card in found.cards] == list(bare.cards)
    for card_id in ('a', 'b', 'depot'):
        assert placed(found, card_id).triggers == ()
        tip = tooltip(text, card_id)
        for line in lines_of(model, card_id):
            assert line.full in tip
            assert line.rule is None or f'Rule: {line.rule}' in tip


def test_the_tooltip_gives_the_text_of_an_event():
    model = model_of('events')
    doc, _, text = drawn(model, style.read('[triggers]\nnames = ["a"]\n'))
    (respond,) = [event for event in doc['cards'][0]['triggers']['events'] if event['event'] == 'a.respond']
    assert respond['label'] == 'The first thing responds.'
    assert respond['label'] in tooltip(text, 'a')


def test_a_run_shows_only_the_events_that_can_act_in_it():
    # The reachability of each run's configuration: an event that a run cannot start is absent from
    # its picture, and the picture without a run joins them.
    model = model_of('switching')
    sheet = style.read('[triggers]\ncount = ["a"]\n')
    every = set()
    for run in model.runs:
        doc, found, _ = drawn(model, sheet, run)
        own = [event['event'] for event in doc['cards'][0]['triggers']['events']]
        assert own == keys_of(model, 'a', (run,))
        (row,) = placed(found, 'a').triggers
        assert row.events == tuple(own)
        every.update(own)
    assert every == {'a.late_only', 'a.early_only', 'a.any_time'}
    joined, _, _ = drawn(model, sheet)
    assert {event['event'] for event in joined['cards'][0]['triggers']['events']} == every


def test_options_false_leaves_out_the_options_that_switch_an_event():
    model = model_of('switching')
    lines = {line.key: line for line in lines_of(model, 'a')}
    assert any(line.options for line in lines.values())
    shown, _, _ = drawn(model, style.read('[triggers]\nrules = ["a"]\n'))
    hidden, _, text = drawn(model, style.read('[triggers]\nrules = ["a"]\noptions = false\n'))
    pairs = zip(
        shown['cards'][0]['triggers']['events'], hidden['cards'][0]['triggers']['events'], strict=True
    )
    for with_options, without in pairs:
        line = lines[with_options['event']]
        assert with_options['text'] == with_options['full'] == line.full
        if not line.options:
            assert without == with_options
            continue
        assert line.options in with_options['full']
        assert line.options not in without['full'] and line.options not in without['text']
        assert line.full.startswith(without['full']) and without['full'].startswith(line.name)
        assert line.options not in tooltip(text, 'a')


# ---- the stylesheet ----------------------------------------------------------------------------------


def test_a_thing_s_own_level_beats_its_template_s_in_another_list():
    model = model_of('lists')
    sheet = style.read('[triggers]\nrules = ["Zone"]\ncount = ["z2"]\n')
    assert style.check(sheet, model) == []
    assert style.trigger_levels(sheet, model) == {'z1': 'rules', 'z2': 'count'}
    doc, _, _ = drawn(model, sheet)
    assert {c['id']: (c['triggers'] or {}).get('level') for c in doc['cards']} == {
        'z1': 'rules',
        'z2': 'count',
        'hub': None,
    }


def test_the_keys_of_triggers_are_read():
    sheet = style.read('[triggers]\nnames = ["b"]\nhover = ["c"]\nlines = 4\nevents = 1\noptions = false\n')
    assert (sheet.triggers, sheet.trigger_lines, sheet.trigger_events, sheet.trigger_options) == (
        (('names', ('b',)), ('hover', ('c',))),
        4,
        1,
        False,
    )
    empty = style.read('')
    assert (empty.triggers, empty.trigger_lines, empty.trigger_events, empty.trigger_options) == (
        (),
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        (
            '[triggers]\nrules = ["a"]\ncount = ["a"]\n',
            'triggers.count',
            'names a, which triggers.rules also names',
        ),
        ('[triggers]\nrules = ["a", "a"]\n', 'triggers.rules', 'names a twice'),
        ('[triggers]\nrules = "a"\n', 'triggers.rules', 'holds a list of names'),
        ('[triggers]\nlevel = ["a"]\n', 'triggers.level', 'is not a key that this file reads'),
        ('[triggers]\nlines = 0\n', 'triggers.lines', 'is a whole number from 1 to 4'),
        ('[triggers]\nlines = 5\n', 'triggers.lines', 'is a whole number from 1 to 4'),
        ('[triggers]\nlines = 2.5\n', 'triggers.lines', 'is a whole number from 1 to 4'),
        ('[triggers]\nlines = true\n', 'triggers.lines', 'is a whole number from 1 to 4'),
        ('[triggers]\nevents = 0\n', 'triggers.events', 'is a whole number from 1 to 20'),
        ('[triggers]\nevents = 21\n', 'triggers.events', 'is a whole number from 1 to 20'),
        ('[triggers]\noptions = "no"\n', 'triggers.options', 'is true or false'),
        ('triggers = ["a"]\n', 'triggers', 'is a table'),
    ],
)
def test_each_wrong_value_of_triggers_is_a_problem_at_its_key(text, key, match):
    with pytest.raises(StyleError, match=match) as caught:
        style.read(text)
    assert [d['key'] for d in caught.value.diagnostics] == [key]


# A model of the stylesheet's checks: a thing without an event, a template without a member, and a
# template whose members have events.
CHECKED = """\
scenario "Checked"
    horizon 10 h

plain:
    x = 1

Depot:
    y = 1

Ward:
    level = 0
    floods = event():
        after 1 h:
            this.level += 1

east: Ward

west: Ward

attacker:
    enters = event():
        after 0 h

attacker.enters.start()
"""


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('[triggers]\nrules = ["plain"]\n', 'triggers.rules', 'plain has no event'),
        ('[triggers]\nnames = ["Depot"]\n', 'triggers.names', 'no member'),
        ('[triggers]\ncount = ["nowhere"]\n', 'triggers.count', 'not a template or a thing'),
        ('[layout]\nhide = ["Ward"]\n\n[triggers]\nhover = ["east"]\n', 'triggers.hover', 'hides it'),
    ],
)
def test_triggers_names_a_thing_that_the_picture_draws_with_an_event(tmp_path, text, key, match):
    model = package(tmp_path, CHECKED, style=text)
    with pytest.raises(StyleError, match=match) as caught:
        style.of(model)
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(tmp_path / style.STYLE_FILE), key)
    ]


def test_a_template_whose_members_have_events_can_be_named(tmp_path):
    model = package(tmp_path, CHECKED, style='[triggers]\nrules = ["Ward"]\ncount = ["attacker"]\n')
    assert style.trigger_levels(style.of(model), Things(model)) == {
        'east': 'rules',
        'west': 'rules',
        'attacker': 'count',
    }


# ---- the layout and the SVG on pictures that Hypothesis makes --------------------------------------

NAMES = st.text(alphabet='abcdefgh ijk<&>"\'éø', min_size=1, max_size=40).map(str.strip).filter(bool)
LINES = st.text(alphabet='abcdefgh ijk<&>"\';éø', min_size=0, max_size=260)


@st.composite
def with_triggers(draw):
    """A picture of `pictures` whose cards show their events at a level, or not."""
    doc = draw(pictures(groups=True))
    for card in doc['cards']:
        if not draw(st.booleans()):
            card['triggers'] = None
            continue
        level = draw(st.sampled_from(style.TRIGGER_LEVELS))
        limit = draw(st.integers(1, 20))
        rows = level in ('names', 'rules')
        events = []
        for k, name in enumerate(draw(st.lists(NAMES, max_size=12))):
            full = f'{name} — {draw(LINES)}'
            text = (name if level == 'names' else full) if rows and k < limit else None
            event = {'event': f'{card["id"]}.e{k}', 'name': name, 'text': text, 'full': full, 'label': None}
            events.append({**event, 'rule': draw(st.one_of(st.none(), NAMES))})
        more = sum(event['text'] is None for event in events) if rows else 0
        card['triggers'] = {'level': level, 'lines': draw(st.integers(1, 4)), 'events': events, 'more': more}
    return doc


@SHAPE
@given(with_triggers())
def test_every_property_holds_with_the_rows_of_the_events(doc):
    found = layout(doc)
    check(doc, found)
    check_svg(doc, found, svg(doc, found))
