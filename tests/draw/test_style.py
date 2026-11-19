"""A scenario's stylesheet (`style.toml`, the picture): its keys, its defaults, the checks that name the
file and the key, and that the model and its runs never read it.

The model of the test writes its own things and templates, and each expectation follows from them and
from the rule of the reader that it names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from napkin.draw import style
from napkin.draw.style import StyleError
from napkin.draw.things import Things
from napkin.engine import run
from napkin.model.compile import load_scenario
from tests.draw.models import package

MODEL = """\
scenario "A test"
    summary "A file for tests only."
    horizon 10 h
    scope "The test."

options "Response":
    "Fast":
        "Fast."
        west.y = 2 h  @counts
    "Slow":
        "Slow."
        north.x = 4 h  @counts

options "Attacker":
    "AI":
        "AI."
    "Human":
        "Human."
        east.y = 3 h  @counts

runs:
    fast = "Fast" + "AI"
    slow = "Slow" + "AI"
    slow_human = "Slow" + "Human"
        "The slow response against a human team"

north:  @counts
    "A district."
    role community
    input x: h = 2 h in [1 h, 5 h]  @counts
        "X"
    people: person = 10 person  @counts
        "People"
    grow = event():
        after 1 h:
            this.people += 1 person

Ward:  @counts
    "A ward."
    role community
    input y: h = 1 h in [0 h, 3 h]  @counts
        "Y"
    level: enum[LOW, HIGH] = LOW
    floods = event():
        "The ward floods."
        when t >= this.y:
            this.floods.start()
            reset when false
        after 0 h:
            this.level = HIGH

Depot:  @counts
    "A template that no thing is made of."
    role operator

east: Ward

west: Ward

attacker:  @counts
    "An attacker."
    role adversary
    access: enum[NONE, KEPT] = NONE
    enters = event():
        "The attacker gets in."
        when this.access == KEPT:
            this.enters.start()
            reset when false
    start = event():
        "The attacker gets in."
        after 0 h:
            this.access = KEPT

north.grow.start()
attacker.start.start()

record counts: identity "The test counts."
"""

STYLE = """\
# The picture of the map.
[layout]
hide = ["Ward"]

[icon]
house = ["north"]
"""


def built(tmp_path, picture=None):
    """The model of MODEL, with its stylesheet beside it when it is given."""
    return package(tmp_path, MODEL, style=picture)


def test_without_a_stylesheet_the_map_draws_each_line_with_the_icon_of_its_role(tmp_path):
    model = built(tmp_path)
    sheet = style.of(model)
    assert sheet == style.Style()
    # Every entity line, in the order of the file, each with the icon of the role that the model writes.
    assert style.hidden_lines(sheet, Things(model)) == set()
    assert style.drawn(sheet, Things(model)) == ['north', 'east', 'west', 'attacker']
    roles = {'north': 'community', 'east': 'community', 'west': 'community', 'attacker': 'adversary'}
    assert style.icon_of(sheet, Things(model)) == {
        entry: style.ROLE_ICONS[role] for entry, role in roles.items()
    }


def test_the_keys_give_what_the_map_shows(tmp_path):
    model = built(tmp_path, STYLE)
    sheet = style.of(model)
    # A hidden template hides each of its instances; the map draws the others in the order of the file.
    assert style.hidden_lines(sheet, Things(model)) == {'east', 'west'}
    assert style.drawn(sheet, Things(model)) == ['north', 'attacker']
    icons = style.icon_of(sheet, Things(model))
    assert (icons['north'], icons['attacker']) == ('house', style.ROLE_ICONS['adversary'])


def test_a_file_of_comments_only_gives_the_defaults():
    assert style.read('# Nothing yet.\n', 'style.toml') == style.Style(origin='style.toml')


def test_a_template_stands_for_its_instances_and_an_instance_s_own_icon_wins(tmp_path):
    model = built(tmp_path, '[icon]\nhouse = ["Ward"]\nshop = ["east"]\n')
    icons = style.icon_of(style.of(model), Things(model))
    assert (icons['east'], icons['west']) == ('shop', 'house')


# Two things whose role has no icon: one without a role, and one whose role names a thing.
NO_ROLE = '\nplain:  @counts\n    "A thing without a role."\n\ncrew:  @counts\n    "A crew."\n    role crew\n'


@pytest.mark.parametrize(
    ('picture', 'expected'), [(None, None), ('[icon]\nbox = ["plain", "crew"]\n', 'box')]
)
def test_a_thing_whose_role_has_no_icon_has_none_unless_the_stylesheet_gives_one(tmp_path, picture, expected):
    model = package(tmp_path, MODEL.replace('west: Ward\n', 'west: Ward\n' + NO_ROLE), style=picture)
    icons = style.icon_of(style.of(model), Things(model))
    assert (icons['plain'], icons['crew']) == (expected, expected)
    assert icons['north'] == style.ROLE_ICONS['community']


def test_hide_names_any_thing_an_instance_included(tmp_path):
    # An instance that `hide` names is the one line hidden; its template's other instances stay.
    model = built(tmp_path, '[layout]\nhide = ["east"]\n')
    sheet = style.of(model)
    assert style.hidden_lines(sheet, Things(model)) == {'east'}
    assert style.drawn(sheet, Things(model)) == ['north', 'west', 'attacker']


def test_a_table_is_named_by_its_card(tmp_path):
    # The rows of a table are members of a template, and one card holds them all: the template that
    # `hide` names hides the card, and so each row of it.
    rows = '\nCrew:  @counts\n    "A crew."\n    role responder\n\ncrews: Crew from "crews.csv"\n'
    model = package(
        tmp_path,
        MODEL.replace('west: Ward\n', 'west: Ward\n' + rows),
        style='[layout]\nhide = ["Crew"]\n',
        tables={'crews.csv': 'id\na\nb\n'},
    )
    found = Things(model)
    assert found.cards['crews'].members == ('crews.a', 'crews.b')
    sheet = style.of(model)
    assert style.hidden_lines(sheet, found) == {'crews'}
    assert 'crews' not in style.drawn(sheet, found)


@pytest.mark.parametrize(
    ('text', 'key', 'line', 'match'),
    [
        ('colour = ["north"]\n', 'colour', None, 'not a key'),
        ('[layout]\nsize = 3\n', 'layout.size', None, 'not a key'),
        ('layout = ["Ward"]\n', 'layout', None, 'is a table'),
        ('icon = 3\n', 'icon', None, 'is a table'),
        ('place = 3\n', 'place', None, 'is a table'),
        ('group = ["north"]\n', 'group', None, 'is a table'),
        ('state = "inside"\n', 'state', None, 'is a table'),
        ('[layout]\nhide = "Ward"\n', 'layout.hide', None, 'list of names'),
        ('[layout]\nhide = ["Ward", "Ward"]\n', 'layout.hide', None, 'twice'),
        # The one direction of this version.
        ('[layout]\ndirection = "top-to-bottom"\n', 'layout.direction', None, 'is one of'),
        ('[layout]\ndirection = 1\n', 'layout.direction', None, 'is one of'),
        ('[icon]\nlamp = ["north"]\n', 'icon.lamp', None, 'not an icon'),
        ('[icon]\nhouse = "north"\n', 'icon.house', None, 'list of names'),
        ('[icon]\nhouse = [1]\n', 'icon.house', None, 'list of names'),
        ('[icon]\nhouse = ["north", "north"]\n', 'icon.house', None, 'twice'),
        ('[icon]\nhouse = ["north"]\nshop = ["north"]\n', 'icon.shop', None, 'icon.house also names'),
        # A place is a table with a column, and an optional row, each a whole number from 1.
        ('[place]\nnorth = 1\n', 'place.north', None, 'is a table'),
        ('[place]\nnorth = { row = 1 }\n', 'place.north', None, 'no column'),
        ('[place]\nnorth = { column = 0 }\n', 'place.north.column', None, 'whole number'),
        ('[place]\nnorth = { column = true }\n', 'place.north.column', None, 'whole number'),
        ('[place]\nnorth = { column = 1, row = 1.5 }\n', 'place.north.row', None, 'whole number'),
        ('[place]\nnorth = { column = 1, size = 2 }\n', 'place.north.size', None, 'not a key'),
        # A group is a label with a list of one name or more; a name is in one group at most.
        ('[group]\n"Area" = "north"\n', 'group.Area', None, 'list of names'),
        ('[group]\n"Area" = []\n', 'group.Area', None, 'names no thing'),
        ('[group]\n"" = ["north"]\n', 'group.', None, 'has a label'),
        ('[group]\n"A" = ["north"]\n"B" = ["north"]\n', 'group.B', None, 'group.A also names'),
        ('[group]\n"A" = ["north", "north"]\n', 'group.A', None, 'twice'),
        # A state machine is inside its thing, beside it or hidden.
        ('[state]\nattacker = "inside"\n', 'state.attacker', None, 'is a table'),
        ('[state.attacker]\naccess = "above"\n', 'state.attacker.access', None, 'is one of'),
        # D-52: the numbers of [layout] are whole numbers in their ranges, and [stocks] holds lists of names.
        ('[layout]\nstocks = 0\n', 'layout.stocks', None, 'whole number from 1 to 8'),
        ('[layout]\nstocks = 9\n', 'layout.stocks', None, 'whole number from 1 to 8'),
        ('[layout]\nstocks = true\n', 'layout.stocks', None, 'whole number from 1 to 8'),
        ('[layout]\nstocks = "4"\n', 'layout.stocks', None, 'whole number from 1 to 8'),
        ('[layout]\ncards_per_column = 1\n', 'layout.cards_per_column', None, 'whole number from 2 to 16'),
        ('[layout]\ncards_per_column = 17\n', 'layout.cards_per_column', None, 'whole number from 2 to 16'),
        ('[layout]\ncards_per_column = 4.0\n', 'layout.cards_per_column', None, 'whole number from 2'),
        ('[layout]\ncard_width = 169\n', 'layout.card_width', None, 'whole number of px from 170 to 400'),
        ('[layout]\ncard_width = 401\n', 'layout.card_width', None, 'whole number of px from 170 to 400'),
        ('[layout]\ncard_width = 250.5\n', 'layout.card_width', None, 'whole number of px'),
        ('[layout]\ncard_size = 250\n', 'layout.card_size', None, 'not a key'),
        ('stocks = ["north"]\n', 'stocks', None, 'is a table'),
        ('[stocks]\nnorth = "queue"\n', 'stocks.north', None, 'list of names'),
        ('[stocks]\nnorth = [1]\n', 'stocks.north', None, 'list of names'),
        ('[stocks]\nnorth = ["queue", "queue"]\n', 'stocks.north', None, 'twice'),
        ('[stocks]\nnorth = []\n', 'stocks.north', None, 'names no stock or tally'),
        # A text that is not TOML: the line that tomllib names.
        ('[icon\nhouse = ["north"]\n', None, 1, 'not TOML'),
        ('[icon]\nhouse = ["north"]\nhouse = ["east"]\n', None, 3, 'not TOML'),
        ('[place]\nnorth = { column = 1 }\nnorth = { column = 2 }\n', None, 3, 'not TOML'),
    ],
)
def test_a_stylesheet_has_its_keys_each_a_list_of_names(text, key, line, match):
    with pytest.raises(StyleError, match=match) as caught:
        style.read(text, 'style.toml')
    assert [(d['file'], d['key'], d.get('line')) for d in caught.value.diagnostics] == [
        ('style.toml', key, line)
    ]


def test_each_problem_of_a_file_is_reported_with_its_file_and_its_key():
    text = '[layout]\ndirection = "up"\n\n[place]\nnorth = { column = 0 }\n\n[state.attacker]\naccess = "under"\n'
    with pytest.raises(StyleError) as caught:
        style.read(text, 'style.toml')
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        ('style.toml', 'layout.direction'),
        ('style.toml', 'place.north.column'),
        ('style.toml', 'state.attacker.access'),
    ]


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('arrows = "light"\n', 'arrows', 'is a table'),
        ('[arrows]\nreads = "faint"\n', 'arrows.reads', 'is one of "full", "light", "hidden"'),
        ('[arrows]\nmoves = true\n', 'arrows.moves', 'is one of'),
        ('[arrows]\ndashes = "full"\n', 'arrows.dashes', 'not a key'),
        ('[arrows]\nbundle = "reads"\n', 'arrows.bundle', 'list of kinds'),
        (
            '[arrows]\nbundle = ["moved"]\n',
            'arrows.bundle',
            'names moved, which is not a kind of arrow; the kinds are',
        ),
        ('[arrows]\nbundle = ["reads", "reads"]\n', 'arrows.bundle', 'names reads twice'),
    ],
)
def test_arrows_gives_each_kind_a_look_and_names_the_kinds_that_bundle(text, key, match):
    # D-51: the looks are full, light and hidden; bundle is a list of the five kinds.
    with pytest.raises(StyleError, match=match) as caught:
        style.read(text, 'style.toml')
    assert [d['key'] for d in caught.value.diagnostics] == [key]


def test_the_picture_s_settings_take_the_looks_and_bundle_of_arrows(tmp_path):
    from napkin.draw.model_map import DEFAULT_LOOKS, picture

    model = built(tmp_path, '[arrows]\nreads = "full"\nmoves = "hidden"\nbundle = []\n')
    sheet = style.of(model)
    assert sheet.looks == (('reads', 'full'), ('moves', 'hidden')) and sheet.bundle == ()
    settings = picture(model, sheet)['settings']
    # The file's looks, and the default look of each kind that it does not name.
    assert settings['looks'] == DEFAULT_LOOKS | {'reads': 'full', 'moves': 'hidden'}
    assert settings['bundle'] == []
    # Without the keys, the defaults: reads and follows light and bundled.
    plain = picture(model, style.Style())['settings']
    assert plain['looks'] == DEFAULT_LOOKS and plain['bundle'] == ['reads', 'follows']


# The spec's example of style.toml, with this test's things.
EVERY_KEY = """\
[layout]
direction = "left-to-right"
hide = ["Depot"]
stocks = 3
cards_per_column = 6
card_width = 240
[place]
attacker = { column = 1 }
Ward     = { column = 2 }
north    = { column = 3, row = 2 }
[group]
"Wards" = ["Ward", "north"]
[icon]
house  = ["Ward"]
target = ["attacker"]
[state.attacker]
access = "beside"
[state.Ward]
level = "hidden"
"""


def test_each_key_of_the_picture_is_read(tmp_path):
    model = built(tmp_path, EVERY_KEY)
    sheet = style.of(model)
    assert sheet == style.Style(
        hide=('Depot',),
        icons=(('house', ('Ward',)), ('target', ('attacker',))),
        origin=str(tmp_path / style.STYLE_FILE),
        direction='left-to-right',
        places=(('attacker', 1, None), ('Ward', 2, None), ('north', 3, 2)),
        groups=(('Wards', ('Ward', 'north')),),
        states=(('attacker', (('access', 'beside'),)), ('Ward', (('level', 'hidden'),))),
        stocks=3,
        cards_per_column=6,
        card_width=240,
    )
    # A template stands for its instances, in the order of the file.
    assert style.place_of(sheet, Things(model)) == {
        'north': (3, 2),
        'east': (2, None),
        'west': (2, None),
        'attacker': (1, None),
    }
    assert style.groups_of(sheet, Things(model)) == [('Wards', ['north', 'east', 'west'])]
    assert style.state_places(sheet, Things(model)) == {
        'east': {'level': 'hidden'},
        'west': {'level': 'hidden'},
        'attacker': {'access': 'beside'},
    }
    assert style.read('', 'style.toml').direction == 'left-to-right'


def test_a_template_places_its_instances_on_its_row_and_the_rows_after_it(tmp_path):
    model = built(tmp_path, '[place]\nWard = { column = 2, row = 4 }\n')
    assert style.place_of(style.of(model), Things(model)) == {'east': (2, 4), 'west': (2, 5)}


def test_a_thing_s_own_setting_wins_over_its_template_s(tmp_path):
    text = (
        '[place]\nWard = { column = 2, row = 1 }\neast = { column = 5 }\n'
        '\n[state.Ward]\nlevel = "beside"\n\n[state.west]\nlevel = "inside"\n'
    )
    model = built(tmp_path, text)
    sheet = style.of(model)
    # The instance with a place of its own leaves its template's row to the next one.
    assert style.place_of(sheet, Things(model)) == {'east': (5, None), 'west': (2, 1)}
    assert style.state_places(sheet, Things(model)) == {
        'east': {'level': 'beside'},
        'west': {'level': 'inside'},
    }


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('[layout]\nhide = ["nowhere"]\n', 'layout.hide', 'not a template or a thing'),
        ('[icon]\nhouse = ["nowhere"]\n', 'icon.house', 'not a template or a thing'),
        ('[layout]\nhide = ["Ward"]\n\n[icon]\nhouse = ["Ward"]\n', 'icon.house', 'hides it'),
        ('[layout]\nhide = ["Ward"]\n\n[icon]\nhouse = ["east"]\n', 'icon.house', 'hides it'),
        ('[icon]\nhouse = ["Depot"]\n', 'icon.house', 'no member'),
        # A place names a thing or a template that the picture draws.
        ('[place]\nnowhere = { column = 1 }\n', 'place.nowhere', 'not a template or a thing'),
        ('[place]\nDepot = { column = 1 }\n', 'place.Depot', 'no member'),
        ('[layout]\nhide = ["Ward"]\n\n[place]\neast = { column = 1 }\n', 'place.east', 'hides it'),
        ('[layout]\nhide = ["Ward"]\n\n[place]\nWard = { column = 1 }\n', 'place.Ward', 'hides it'),
        # Two things in one cell: the later place has the problem, also through a template.
        (
            '[place]\nnorth = { column = 1, row = 1 }\nattacker = { column = 1, row = 1 }\n',
            'place.attacker',
            'where north is',
        ),
        (
            '[place]\nWard = { column = 2, row = 1 }\nnorth = { column = 2, row = 2 }\n',
            'place.north',
            'where west is',
        ),
        # A row between the rows of two things of a group, in their column, that the frame would hold:
        # a thing in no group, a thing of another group, and an instance that its template places.
        (
            '[place]\neast = { column = 1, row = 1 }\nnorth = { column = 1, row = 2 }\n'
            'west = { column = 1, row = 3 }\n\n[group]\n"Wards" = ["Ward"]\n',
            'place.north',
            'puts north in column 1, row 2, between east and west of group.Wards',
        ),
        (
            '[place]\neast = { column = 1, row = 1 }\nnorth = { column = 1, row = 4 }\n'
            'west = { column = 1, row = 9 }\n\n[group]\n"Wards" = ["Ward"]\n"North" = ["north"]\n',
            'place.north',
            'between east and west of group.Wards',
        ),
        (
            '[place]\nWard = { column = 1, row = 1 }\nattacker = { column = 1, row = 3 }\n'
            '\n[group]\n"Pair" = ["east", "attacker"]\n',
            'place.Ward',
            'puts west in column 1, row 2, between east and attacker of group.Pair',
        ),
        # A thing of a group with a row above a thing of an earlier group, in their column: the frames
        # go down in the order of [group]. Also an instance that its template places, and a thing that is
        # between two things of the earlier group, which has the one problem of its row.
        (
            '[place]\neast = { column = 1, row = 1 }\nwest = { column = 1, row = 2 }\n'
            '\n[group]\n"First" = ["west"]\n"Second" = ["east"]\n',
            'place.east',
            'puts east of group.Second in column 1, row 1, above west of group.First at row 2',
        ),
        (
            '[place]\nWard = { column = 1, row = 1 }\n\n[group]\n"First" = ["west"]\n"Second" = ["east"]\n',
            'place.Ward',
            'puts east of group.Second in column 1, row 1, above west of group.First at row 2',
        ),
        (
            '[place]\nnorth = { column = 1, row = 1 }\neast = { column = 1, row = 2 }\n'
            'attacker = { column = 1, row = 3 }\n\n[group]\n"First" = ["north", "attacker"]\n"Second" = ["east"]\n',
            'place.east',
            'between north and attacker of group.First',
        ),
        # A group names things and templates that the picture draws, and a thing is in one group.
        ('[group]\n"A" = ["nowhere"]\n', 'group.A', 'not a template or a thing'),
        ('[layout]\nhide = ["Ward"]\n\n[group]\n"A" = ["Ward"]\n', 'group.A', 'hides it'),
        ('[group]\n"A" = ["Ward"]\n"B" = ["east"]\n', 'group.B', 'group.A has it'),
        # A state machine of a thing that the picture draws, for each of its named states.
        ('[state.nowhere]\nx = "inside"\n', 'state.nowhere', 'not a template or a thing'),
        ('[state.north]\npeople = "beside"\n', 'state.north.people', 'not a named state of north'),
        ('[state.Ward]\ny = "beside"\n', 'state.Ward.y', 'not a named state of east'),
        ('[state.attacker]\nphase = "beside"\n', 'state.attacker.phase', 'not a named state'),
        ('[layout]\nhide = ["Ward"]\n\n[state.Ward]\nlevel = "beside"\n', 'state.Ward', 'hides it'),
    ],
)
def test_the_stylesheet_names_what_its_model_declares(tmp_path, text, key, match):
    model = built(tmp_path, text)
    with pytest.raises(StyleError, match=match) as caught:
        style.of(model)
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(tmp_path / style.STYLE_FILE), key)
    ]


@pytest.mark.parametrize(
    'text',
    [
        # The row is after the group's rows, the thing has no row, or it is in another column.
        '[place]\nWard = { column = 1, row = 1 }\nnorth = { column = 1, row = 3 }\n',
        '[place]\neast = { column = 1, row = 1 }\nwest = { column = 1, row = 3 }\nnorth = { column = 1 }\n',
        '[place]\neast = { column = 1, row = 1 }\nwest = { column = 1, row = 3 }\nnorth = { column = 2, row = 2 }\n',
        # One thing of the group has a row in the column, or none has a row.
        '[place]\neast = { column = 1, row = 1 }\nwest = { column = 2, row = 3 }\nnorth = { column = 1, row = 2 }\n',
        '[place]\nWard = { column = 1 }\nnorth = { column = 1, row = 2 }\n',
        # The thing between them is in the group.
        '[place]\neast = { column = 1, row = 1 }\nnorth = { column = 1, row = 2 }\nwest = { column = 1, row = 3 }\n'
        '\n[group]\n"All" = ["Ward", "north"]\n',
    ],
)
def test_a_row_that_splits_no_group_is_accepted(tmp_path, text):
    group = '' if '[group]' in text else '\n[group]\n"Wards" = ["Ward"]\n'
    model = built(tmp_path, text + group)
    assert style.check(style.of(model), model) == []


@pytest.mark.parametrize(
    'place',
    [
        # The rows of the two groups' things in the order of the groups, in other columns, or one of
        # them without a row, which the layout orders.
        'east = { column = 1, row = 1 }\nwest = { column = 1, row = 2 }\n',
        'east = { column = 2, row = 1 }\nwest = { column = 1, row = 2 }\n',
        'east = { column = 1 }\nwest = { column = 1, row = 2 }\n',
        'east = { column = 1, row = 1 }\nwest = { column = 1 }\n',
    ],
)
def test_rows_in_the_order_of_the_groups_are_accepted(tmp_path, place):
    model = built(tmp_path, f'[place]\n{place}\n[group]\n"First" = ["east"]\n"Second" = ["west"]\n')
    assert style.check(style.of(model), model) == []


def test_a_template_without_an_instance_is_still_a_name(tmp_path):
    # A module can declare a template that a scenario makes nothing of: the stylesheet may hide it.
    model = built(tmp_path, '[layout]\nhide = ["Depot"]\n')
    assert style.drawn(style.of(model), Things(model)) == ['north', 'east', 'west', 'attacker']


def test_the_model_and_its_runs_never_read_the_stylesheet(tmp_path):
    pictures = {
        'absent': None,
        'present': STYLE,
        'broken': '[icon]\nhouse = ["nowhere"]\n',
        'unreadable': '[icon\nhouse = ["north"]\n',
    }
    models = {}
    for name, picture in pictures.items():
        (tmp_path / name).mkdir()
        models[name] = built(tmp_path / name, picture)
    assert len({model.model_hash for model in models.values()}) == 1
    # A stylesheet with a problem stops the map, never a study.
    for name in ('broken', 'unreadable'):
        with pytest.raises(StyleError):
            style.of(models[name])
    broken = models['broken']
    for name in ('fast', 'slow', 'slow_human'):
        assert run(broken.program, broken.configure(name)).failure is None


def test_the_icons_are_the_ones_that_the_map_draws():
    # draw/icons.py draws each icon of the same file (tests/draw/test_icons.py).
    names = json.loads(Path(__file__).with_name('map-icons.json').read_text(encoding='utf-8'))['icons']
    assert list(style.ICONS) == names and len(set(names)) == len(names)
    assert set(style.ROLE_ICONS.values()) <= set(style.ICONS)


# ---- the rows of a card and the columns (D-52) ----------------------------------------------------

# MODEL with stocks: north's queue is a stock (a flow takes from it) and its served a tally (a flow only
# fills it); each Ward has the stock water and the tally drained. Their people and level stay states.
STOCKED = MODEL.replace(
    '        "People"\n',
    '        "People"\n'
    '    queue: person = 10 person in [0 person,]  @counts\n        "Queue"\n'
    '    served: person = 0 person in [0 person,]  @counts\n        "Served"\n'
    '    flow serve: this.queue -> this.served  @counts\n        request = 1 person/h\n',
    1,
).replace(
    '    level: enum[LOW, HIGH] = LOW\n',
    '    level: enum[LOW, HIGH] = LOW\n'
    '    water: person = 5 person in [0 person,]  @counts\n        "Water"\n'
    '    drained: person = 0 person in [0 person,]  @counts\n        "Drained"\n'
    '    flow drain: this.water -> this.drained  @counts\n        request = 1 person/h\n',
    1,
)


def stocked(tmp_path, picture=None):
    """The model of STOCKED, with its stylesheet beside it when it is given."""
    return package(tmp_path, STOCKED, style=picture)


def test_the_numbers_of_the_layout_are_read_at_both_ends_of_their_ranges():
    # The ranges of D-52: stocks 1 to 8, cards_per_column 2 to 16, card_width 170 to 400 px.
    low = style.read('[layout]\nstocks = 1\ncards_per_column = 2\ncard_width = 170\n', 'style.toml')
    high = style.read('[layout]\nstocks = 8\ncards_per_column = 16\ncard_width = 400\n', 'style.toml')
    assert (low.stocks, low.cards_per_column, low.card_width) == (1, 2, 170)
    assert (high.stocks, high.cards_per_column, high.card_width) == (8, 16, 400)
    # Without them, the picture's defaults (model_map.settings_of) apply: the file gives none.
    empty = style.read('[layout]\n', 'style.toml')
    assert empty == style.Style(origin='style.toml')
    assert empty.stocks is empty.cards_per_column is empty.card_width is None and empty.stock_order == ()


def test_a_template_s_rows_go_to_each_instance_and_an_instance_s_own_list_wins(tmp_path):
    model = stocked(tmp_path, '[stocks]\nWard = ["drained", "water"]\neast = ["water"]\nnorth = ["served"]\n')
    sheet = style.of(model)
    assert sheet.stock_order == (('Ward', ('drained', 'water')), ('east', ('water',)), ('north', ('served',)))
    # The instance's own list replaces its template's whole; nothing merges.
    assert style.stock_orders(sheet, Things(model)) == {
        'north': ('served',),
        'east': ('water',),
        'west': ('drained', 'water'),
    }
    # The stocks and tallies of each thing, by use; a state is neither.
    found = Things(model)
    assert {entry: style.stock_names(found, entry) for entry in found.cards} == {
        'north': ['queue', 'served'],
        'east': ['water', 'drained'],
        'west': ['water', 'drained'],
        'attacker': [],
    }


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        # A name that the model does not have, a value that is not a stock or a tally, and a named state.
        (
            '[stocks]\nnorth = ["flood"]\n',
            'stocks.north',
            'names flood, which is not a stock or a tally of north',
        ),
        ('[stocks]\nnorth = ["queue", "x"]\n', 'stocks.north', 'names x, which is not a stock or a tally'),
        ('[stocks]\nnorth = ["people"]\n', 'stocks.north', 'names people, which is not a stock or a tally'),
        # A template's list names the stocks of each instance: the message names the template.
        (
            '[stocks]\nWard = ["level"]\n',
            'stocks.Ward',
            'names level, which is not a stock or a tally of Ward',
        ),
        # A thing's list names its own stocks, not another thing's, nor a key of the picture.
        ('[stocks]\nattacker = ["water"]\n', 'stocks.attacker', 'not a stock or a tally of attacker'),
        ('[stocks]\neast = ["east.water"]\n', 'stocks.east', 'not a stock or a tally of east'),
        # The name is a thing or a template that the picture draws.
        ('[stocks]\nnowhere = ["water"]\n', 'stocks.nowhere', 'not a template or a thing'),
        ('[stocks]\nDepot = ["water"]\n', 'stocks.Depot', 'no member'),
        ('[layout]\nhide = ["Ward"]\n\n[stocks]\neast = ["water"]\n', 'stocks.east', 'hides it'),
        ('[layout]\nhide = ["east"]\n\n[stocks]\neast = ["water"]\n', 'stocks.east', 'hides it'),
    ],
)
def test_the_stocks_table_names_the_stocks_of_things_that_the_picture_draws(tmp_path, text, key, match):
    model = stocked(tmp_path, text)
    with pytest.raises(StyleError, match=match) as caught:
        style.of(model)
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(tmp_path / style.STYLE_FILE), key)
    ]


# ---- the stylesheet of a variant (D-22) -----------------------------------------------------------

# Two stylesheets that differ in every key: the package's and one variant's own.
PACKAGE_STYLE = '[layout]\nhide = ["Ward"]\n\n[icon]\nhouse = ["north"]\n'
OWN_STYLE = '[icon]\nshop = ["east"]\n'


def family(tmp_path, package_style=PACKAGE_STYLE, own=OWN_STYLE):
    """{variant: model} of a package whose main file is MODEL, with the stylesheet `package` in its
    folder, and two variants that change nothing: `plain`, with no stylesheet of its own, and `styled`,
    with `own` in its folder. The two variants are one model, so they have one model hash."""
    folder = tmp_path / 'family'
    package(folder, MODEL, style=package_style)
    for name, text in (('plain', None), ('styled', own)):
        (folder / 'variants' / name).mkdir(parents=True)
        (folder / 'variants' / name / 'model.scn').write_text('variant "A place"\n', encoding='utf-8')
        if text is not None:
            (folder / 'variants' / name / style.STYLE_FILE).write_text(text, encoding='utf-8')
    return {name: load_scenario(folder / 'variants' / name / 'model.scn') for name in ('plain', 'styled')}


def test_a_variant_without_a_stylesheet_takes_its_package_s(tmp_path):
    models = family(tmp_path)
    sheet = style.of(models['plain'])
    assert sheet == style.read(PACKAGE_STYLE, str(tmp_path / 'family' / style.STYLE_FILE))
    assert style.drawn(sheet, Things(models['plain'])) == ['north', 'attacker']


def test_a_variant_s_own_stylesheet_replaces_its_package_s_whole(tmp_path):
    """Nothing of the package's file merges into the variant's own: the variant hides nothing, and only
    its own icon is given."""
    models = family(tmp_path)
    sheet = style.of(models['styled'])
    assert sheet == style.read(OWN_STYLE, str(tmp_path / 'family' / 'variants' / 'styled' / style.STYLE_FILE))
    assert sheet.hide == () and dict(sheet.icons) == {'shop': ('east',)}
    assert style.icon_of(sheet, Things(models['styled']))['north'] == style.ROLE_ICONS['community']


def test_the_cache_names_the_file_that_each_model_read(tmp_path):
    """The two variants are one model hash, and each reads its own file: the cache keeps them apart, and
    a problem in the package's file stops only the variant that reads it."""
    models = family(tmp_path, package_style='[icon]\nhouse = ["nowhere"]\n')
    assert models['plain'].model_hash == models['styled'].model_hash
    with pytest.raises(StyleError) as caught:
        style.of(models['plain'])
    assert {d['file'] for d in caught.value.diagnostics} == {str(tmp_path / 'family' / style.STYLE_FILE)}
    own = tmp_path / 'family' / 'variants' / 'styled' / style.STYLE_FILE
    assert style.of(models['styled']).origin == str(own)
    # The keys of this package's files (other tests read files of the same model elsewhere).
    read = {
        key[0]
        for key in style.CHECKED
        if key[0].startswith(str(tmp_path)) and key[3] == models['plain'].model_hash
    }
    assert read == {str(tmp_path / 'family' / style.STYLE_FILE), str(own)}


def test_a_variant_whose_own_stylesheet_goes_takes_its_package_s_again(tmp_path):
    models = family(tmp_path)
    assert style.of(models['styled']).origin.endswith(f'styled/{style.STYLE_FILE}')
    (tmp_path / 'family' / 'variants' / 'styled' / style.STYLE_FILE).unlink()
    assert style.of(models['styled']).origin == str(tmp_path / 'family' / style.STYLE_FILE)


def test_without_either_file_the_picture_is_empty(tmp_path):
    models = family(tmp_path, package_style=None, own=None)
    assert style.of(models['plain']) == style.of(models['styled']) == style.Style()


def test_a_stylesheet_that_the_caller_names_comes_first(tmp_path):
    models = family(tmp_path)
    other = tmp_path / 'other.toml'
    other.write_text('[layout]\nhide = ["attacker"]\n', encoding='utf-8')
    for model in models.values():
        assert style.of(model, other) == style.read(other.read_text(encoding='utf-8'), str(other))
    with pytest.raises(StyleError) as caught:
        style.of(models['plain'], tmp_path / 'missing.toml')
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(tmp_path / 'missing.toml'), None)
    ]


def test_the_folders_of_a_model_are_its_own_then_its_package_s(tmp_path):
    family(tmp_path)
    package = tmp_path / 'family'
    variant = package / 'variants' / 'plain' / 'model.scn'
    assert style.folders(variant) == [variant.parent, package]
    assert style.folders(package / 'model.scn') == [package]
    # A file outside any package has its own folder only.
    assert style.folders(tmp_path / 'alone.scn') == [tmp_path]


# ---- the symbols and the subscripts (D-54) --------------------------------------------------------


def test_the_symbols_and_the_subscripts_are_read_in_the_order_of_the_file(tmp_path):
    text = (
        '[symbol.north]\nx = "chi_n"\npeople = "P"\n\n[symbol.Ward]\nlevel = "L\'"\n'
        '\n[subscript]\nnorth = "n"\neast = "e2"\n'
    )
    sheet = style.read(text, 'style.toml')
    assert sheet.symbols == (('north', (('x', 'chi_n'), ('people', 'P'))), ('Ward', (('level', "L'"),)))
    assert sheet.subscripts == (('north', 'n'), ('east', 'e2'))
    assert style.of(built(tmp_path, text)) == style.read(text, str(tmp_path / style.STYLE_FILE))
    assert style.read('', 'style.toml').symbols == style.read('', 'style.toml').subscripts == ()


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('symbol = 3\n', 'symbol', 'is a table'),
        ('subscript = ["north"]\n', 'subscript', 'is a table'),
        ('[symbol]\nnorth = "P"\n', 'symbol.north', 'is a table'),
        ('[symbol.north]\npeople = "PP"\n', 'symbol.north.people', 'not a symbol'),
        ('[symbol.north]\npeople = "P_"\n', 'symbol.north.people', 'not a symbol'),
        ('[symbol.north]\npeople = "P\'\'"\n', 'symbol.north.people', 'not a symbol'),
        ('[symbol.north]\npeople = "Alpha"\n', 'symbol.north.people', 'the shape of A'),
        ('[symbol.north]\npeople = "P_abcdefghijk"\n', 'symbol.north.people', '12 at most'),
        ('[symbol.north]\npeople = 3\n', 'symbol.north.people', 'is a symbol'),
        ('[symbol.north]\npeople.x = "P"\n', 'symbol.north.people', 'is a symbol'),
        ('[subscript]\nnorth = "n,1"\n', 'subscript.north', 'is a subscript'),
        ('[subscript]\nnorth = ""\n', 'subscript.north', 'is a subscript'),
        ('[subscript]\nnorth = 1\n', 'subscript.north', 'is a subscript'),
        ('[subscript]\nnorth = "abcdefghijk"\n', 'subscript.north', 'is a subscript'),
    ],
)
def test_a_symbol_and_a_subscript_have_their_forms(text, key, match):
    with pytest.raises(StyleError, match=match) as caught:
        style.read(text, 'style.toml')
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [('style.toml', key)]


# The model of the tests with a text value in north, which has no symbol.
TEXT_MODEL = MODEL.replace('        "People"\n', '        "People"\n    input label: text = "The north"\n', 1)


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        # A name is a template or a thing that the picture draws.
        ('[symbol.nowhere]\nx = "X"\n', 'symbol.nowhere', 'not a template or a thing'),
        ('[symbol.Depot]\nx = "X"\n', 'symbol.Depot', 'no member'),
        ('[layout]\nhide = ["Ward"]\n\n[symbol.east]\ny = "Y"\n', 'symbol.east', 'hides it'),
        ('[subscript]\nnowhere = "n"\n', 'subscript.nowhere', 'not a template or a thing'),
        ('[layout]\nhide = ["east"]\n\n[subscript]\neast = "e"\n', 'subscript.east', 'hides it'),
        # A member is a value, a flow or an event of each thing that the name stands for, and has a
        # symbol: a text has none.
        (
            '[symbol.north]\nflood = "F"\n',
            'symbol.north.flood',
            'flood is not a value, a flow or an event of north',
        ),
        (
            '[symbol.Ward]\nflood = "F"\n',
            'symbol.Ward.flood',
            'flood is not a value, a flow or an event of Ward',
        ),
        (
            '[symbol.north]\nlabel = "L"\n',
            'symbol.north.label',
            'label is a text of north, which has no symbol',
        ),
        # A template's symbol is a base only, and a template has no subscript of its own.
        ('[symbol.Ward]\nlevel = "L_w"\n', 'symbol.Ward.level', "a template's symbol has no subscript"),
        (
            '[subscript]\nWard = "w"\n',
            'subscript.Ward',
            'Ward is a template; give each member its own subscript',
        ),
        ('[subscript]\nDepot = "d"\n', 'subscript.Depot', 'Depot is a template'),
        # Two cards never have one subscript, and two values never have one symbol of the file: the
        # later name has the problem, once, also when a template stands for several instances.
        (
            '[subscript]\nnorth = "s"\nattacker = "s"\n',
            'subscript.attacker',
            's is also the subscript of north',
        ),
        (
            '[symbol.north]\nx = "W_s"\npeople = "W_s"\n',
            'symbol.north.people',
            'W_s is also the symbol of north.x',
        ),
        (
            '[symbol.north]\nx = "delta_s"\n\n[symbol.attacker]\naccess = "δ_s"\n',
            'symbol.attacker.access',
            'δ_s is also the symbol of north.x',
        ),
        ('[symbol.Ward]\ny = "Y"\nlevel = "Y"\n', 'symbol.Ward.level', 'Y_e is also the symbol of east.y'),
        # A template's base with the instance's subscript, against an instance's own symbol.
        (
            '[symbol.Ward]\nlevel = "L"\n\n[symbol.east]\nlevel = "L_w"\n',
            'symbol.east.level',
            'L_w is also the symbol of west.level',
        ),
        (
            '[symbol.Ward]\nlevel = "L"\n\n[subscript]\neast = "q"\n\n[symbol.west]\nlevel = "L_q"\n',
            'symbol.west.level',
            'L_q is also the symbol of east.level',
        ),
        # The count of an event is N with the subscript of its symbol.
        (
            '[symbol.attacker]\nenters = "T_a"\naccess = "N_a"\n',
            'symbol.attacker.access',
            'N_a is also the count of attacker.enters',
        ),
        (
            '[symbol.attacker]\naccess = "N_a"\nenters = "T_a"\n',
            'symbol.attacker.enters',
            'its count N_a is also the symbol of attacker.access',
        ),
    ],
)
def test_the_symbols_and_the_subscripts_name_what_the_picture_draws(tmp_path, text, key, match):
    model = package(tmp_path, TEXT_MODEL, style=text)
    with pytest.raises(StyleError, match=match) as caught:
        style.of(model)
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(tmp_path / style.STYLE_FILE), key)
    ]


@pytest.mark.parametrize(
    'text',
    [
        # A symbol that a made symbol would have: the made one takes another.
        '[symbol.north]\nx = "P_n"\n',
        # A subscript that a made tag would be: the made one takes another.
        '[subscript]\nnorth = "e"\n',
        # A template's base, and an instance's own symbol in its place.
        '[symbol.Ward]\nlevel = "L"\n\n[symbol.east]\nlevel = "M_e"\n',
        # An event's time and count, and a symbol without a subscript.
        '[symbol.attacker]\nenters = "tau_x"\nstart = "T"\naccess = "N_y"\n',
    ],
)
def test_symbols_and_subscripts_that_no_other_value_has_are_accepted(tmp_path, text):
    model = built(tmp_path, text)
    assert style.check(style.of(model), model) == []
