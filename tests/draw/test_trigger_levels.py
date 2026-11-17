"""What a card shows of its events (`[triggers]`, D-56): the keys of the stylesheet and their checks,
the `triggers` of each card of the picture, the rows of the layout, and the SVG with its tooltips.

The synthetic models are those of test_triggers.py and test_style.py, and each expectation comes from the
model (its events in the order of the file, and their lines from `triggers.card_lines`) or from the rule
of the level that the test names. The properties of every layout and SVG (`check`, `check_svg`) hold the
rows too: each row inside its card and apart from its other parts, each line within the width of the
card. The catalogue test puts every card at `rules`. No test reads a text of the catalogue.
"""

from __future__ import annotations

import copy
import dataclasses
import xml.etree.ElementTree as ET

import pytest
from hypothesis import given
from hypothesis import strategies as st

from napkin import cli
from napkin.draw import layout as layouts
from napkin.draw import model_map, style
from napkin.draw.layout import layout
from napkin.draw.model_map import map_payload, picture
from napkin.draw.style import StyleError
from napkin.draw.svg import svg
from napkin.draw.triggers import ELLIPSIS, card_lines, words
from tests.draw.test_layout import SHAPE, check, pictures
from tests.draw.test_model_map import fixture_model
from tests.draw.test_picture import picture_problems
from tests.draw.test_style import built
from tests.draw.test_svg import SVG, check_model, check_svg, parts
from tests.draw.test_triggers import lists, outcomes, switching
from tests.helpers import SCENARIO_IDS, catalogue_model
from tests.test_cli import write_shop


def drawn(model, sheet, run=None):
    """The picture of a model with a stylesheet, its layout and its SVG, each with every property."""
    assert style.check(sheet, model) == []
    doc = picture(model, sheet, run)
    assert picture_problems(doc) == []
    found = layout(doc)
    text = svg(doc, found)
    check(doc, found)
    check_svg(doc, found, text)
    return doc, found, text


def placed(found, card_id):
    return next(card for card in found.cards if card.id == card_id)


def tooltip(text, card_id):
    """The tooltip of a card of an SVG."""
    root = ET.fromstring(text)
    return next(e for kind, e, _, _ in parts(root) if kind == 'card' and e.get('data-thing') == card_id)[
        0
    ].text


def keys_of(model, card_id):
    """The events of a card as the picture names them, `card.event`, in the order of the file."""
    return [f'{card_id}.{event.name}' for event in model.scenario.entity(card_id).events]


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


@pytest.mark.parametrize('build', (outcomes, lists, switching), ids=lambda build: build.__name__)
def test_without_triggers_no_card_shows_its_events(build):
    doc, found, text = drawn(build(), style.Style())
    assert all(card['triggers'] is None for card in doc['cards'])
    assert all(card.triggers == () and card.events == () for card in found.cards)
    # The layout is the one of the picture without the key, and the SVG draws no row.
    assert layout(without_key(doc)) == found
    assert not [kind for kind, *_ in parts(ET.fromstring(text)) if kind == 'trigger']


# ---- the levels -----------------------------------------------------------------------------------


def test_count_shows_one_row_with_the_number_of_the_card_s_events():
    model = outcomes()
    _, found, _ = drawn(model, style.read('[triggers]\ncount = ["a", "b"]\n'))
    for card_id in ('a', 'b'):
        (row,) = placed(found, card_id).triggers
        assert row.kind == 'count' and row.events == tuple(keys_of(model, card_id))
        assert str(len(model.scenario.entity(card_id).events)) in row.lines[0].split()


def test_names_shows_each_event_s_name_in_the_order_of_the_file():
    model = outcomes()
    _, found, _ = drawn(model, style.read('[triggers]\nnames = ["a", "c"]\nevents = 20\n'))
    for card_id in ('a', 'c'):
        events = model.scenario.entity(card_id).events
        rows = placed(found, card_id).triggers
        assert [row.lines for row in rows] == [(words(event.name),) for event in events]
        assert [row.events for row in rows] == [(key,) for key in keys_of(model, card_id)]


@pytest.mark.parametrize('lines', [1, 2, 3, 4])
def test_rules_shows_each_line_in_at_most_lines_rows_within_the_card(lines):
    model = outcomes()
    _, found, text = drawn(
        model, style.read(f'[triggers]\nrules = ["a", "c"]\nlines = {lines}\nevents = 20\n')
    )
    cut = []
    for card_id in ('a', 'c'):
        card = placed(found, card_id)
        assert card.box.width >= layouts.RULES_WIDTH
        width = row_width(card)
        full = {f'{card_id}.{line.event}': line for line in card_lines(model, card_id)}
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
    model = outcomes()
    _, _, text = drawn(model, style.read('[triggers]\nrules = ["a"]\nevents = 20\n'))
    lines = {f'a.{line.event}': line for line in card_lines(model, 'a')}
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
    model = outcomes()
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
    model = outcomes()
    _, found, text = drawn(model, style.read('[triggers]\nhover = ["a", "b", "c"]\n'))
    _, bare, _ = drawn(model, style.Style())
    # The layout is the one without [triggers]; only the tooltips gain the lines.
    assert [dataclasses.replace(card, events=()) for card in found.cards] == list(bare.cards)
    for card_id in ('a', 'b', 'c'):
        assert placed(found, card_id).triggers == ()
        tip = tooltip(text, card_id)
        for line in card_lines(model, card_id):
            assert line.full in tip
            assert line.rule is None or f'Rule: {line.rule}' in tip


def test_the_tooltip_gives_the_text_of_an_event_with_the_texts_of_the_run():
    # The labels of the map (`map_payload`) fill the braces of each part's text with the texts of each
    # run in their own way: the picture's labels of the events are the same.
    model = fixture_model()
    sheet = style.read('[triggers]\nnames = ["attacker", "operators"]\n')
    found, run_maps = map_payload(model)
    index = {part['name']: k for k, part in enumerate(found['parts'])}
    for run in (None, *model.runs):
        doc, _, text = drawn(model, sheet, run)
        for card in doc['cards']:
            for event in (card['triggers'] or {}).get('events', ()):
                k = index[event['event']]
                label = found['parts'][k]['label']
                if run is not None:
                    label = run_maps[run]['labels'].get(str(k), label)
                assert event['label'] == label
                assert label is None or label in tooltip(text, card['id'])


def test_a_run_shows_only_the_events_that_can_act_in_it():
    # The structure of a run holds the rules of the events that can act in it; the picture without a
    # run joins them.
    model = fixture_model()
    sheet = style.read('[triggers]\ncount = ["attacker", "operators"]\n')
    every = set()
    for run in model.runs:
        doc, found, _ = drawn(model, sheet, run)
        rules = model.structures[model.runs[run]['starts']].rules
        for card in doc['cards']:
            if card['triggers'] is None:
                continue
            own = [event['event'] for event in card['triggers']['events']]
            assert own == [key for key in keys_of(model, card['id']) if key in rules]
            (row,) = placed(found, card['id']).triggers
            assert row.events == tuple(own)
            every.update(own)
    joined, _, _ = drawn(model, sheet)
    assert {
        event['event'] for card in joined['cards'] for event in (card['triggers'] or {}).get('events', ())
    } == every


def test_options_false_leaves_out_the_options_that_switch_an_event():
    model = switching()
    lines = {f'a.{line.event}': line for line in card_lines(model, 'a')}
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
    model = lists()
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


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('[triggers]\nrules = ["north"]\n', 'triggers.rules', 'north has no event'),
        ('[triggers]\nnames = ["Depot"]\n', 'triggers.names', 'no instance'),
        ('[triggers]\ncount = ["nowhere"]\n', 'triggers.count', 'not a template or a thing'),
        ('[layout]\nhide = ["Ward"]\n\n[triggers]\nhover = ["east"]\n', 'triggers.hover', 'hides it'),
    ],
)
def test_triggers_names_a_thing_that_the_picture_draws_with_an_event(tmp_path, text, key, match):
    model = built(tmp_path, text)
    with pytest.raises(StyleError, match=match) as caught:
        style.of(model)
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(tmp_path / style.STYLE_FILE), key)
    ]


def test_a_template_whose_instances_have_events_can_be_named(tmp_path):
    model = built(tmp_path, '[triggers]\nrules = ["Ward"]\ncount = ["attacker"]\n')
    assert style.trigger_levels(style.of(model), model) == {
        'east': 'rules',
        'west': 'rules',
        'attacker': 'count',
    }


def test_compile_and_draw_refuse_a_bad_triggers_table(tmp_path, monkeypatch, capsys):
    shop = write_shop(tmp_path / 'shop')
    monkeypatch.chdir(tmp_path)
    (shop / 'style.toml').write_text('[triggers]\nrules = ["shop"]\ncount = ["shop"]\n', encoding='utf-8')
    for command in ('compile', 'draw'):
        assert cli.main([command, 'shop']) == 1, command
        err = capsys.readouterr().err
        assert 'style.toml: error: triggers.count: names shop, which triggers.rules also names' in err, err
    assert not list(tmp_path.glob('*.svg'))
    (shop / 'style.toml').write_text('[triggers]\nrules = ["shop"]\n', encoding='utf-8')
    assert cli.main(['compile', 'shop']) == 0
    assert cli.main(['draw', 'shop', '-o', 'shop.svg']) == 0
    root = ET.fromstring((tmp_path / 'shop.svg').read_text(encoding='utf-8'))
    assert [e.get('data-event') for kind, e, _, _ in parts(root) if kind == 'trigger'] == ['shop.close']


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


# ---- every catalogue model ---------------------------------------------------------------------------


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_every_catalogue_model_with_every_card_at_rules(scenario_id):
    """Without `[triggers]` no card shows its events and the layout is the one before the key; with
    every card that has an event at `rules`, every property of the picture, the layout and the SVG
    holds, and each card shows the line of each of its events that can act."""
    model = catalogue_model(scenario_id)
    own = style.of(model)
    bare = dataclasses.replace(own, triggers=())
    doc = picture(model, bare)
    assert all(card['triggers'] is None for card in doc['cards'])
    assert layout(without_key(doc)) == layout(doc)
    lines = style.entity_lines(model)
    named = tuple(entry for entry in style.drawn(bare, model) if lines[entry].events)
    sheet = dataclasses.replace(bare, triggers=(('rules', named),))
    doc, found, text = drawn(model, sheet)
    check_model(model, ET.fromstring(text))
    for card in doc['cards']:
        if card['id'] not in named:
            assert card['triggers'] is None
            continue
        full = {f'{card["id"]}.{line.event}': line.full for line in card_lines(model, card['id'])}
        events = card['triggers']['events']
        keys = [event['event'] for event in events]
        assert keys == [key for key in full if key in keys]
        assert all(event['full'] == full[event['event']] for event in events)
        assert len(placed(found, card['id']).events) == len(events)
