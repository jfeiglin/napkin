"""The map of the system (docs/draw.md, napkin/draw/model_map.py): what each part of a thing reads of
another thing, changes, starts and moves (`Walk`), and the arrows of the picture between the cards.

Each model of these tests writes its relations in its own lines, so each expectation follows from the
text of the test: a part relates to a value of another thing when one of its lines names the value. The
kinds of arrow and the words of a change are those of the picture's tests (`test_picture.py`).
"""

from __future__ import annotations

import pytest

from napkin.draw import style
from napkin.draw.defaults import DEFAULT_BUNDLE, DEFAULT_LOOKS
from napkin.draw.model_map import ACTOR_NAMES, Walk, actor_name, arrow_kind, picture, settings_of
from napkin.draw.things import Things
from tests.draw.models import compiled

# A thing whose values the parts of another read: each kind of part reads `src` once in its own line.
READS = """\
src:
    input k: L = 1 L
    level: L = 5 L in [0 L,]
    total = formula(this.level + this.k)
    staff: h = 1 h
    go = event():
        after 0 h

reader:
    f = formula(src.k * 2)
    first: L = src.level
    bounded: L = 1 L in [0 L, src.k]
    sum_of = formula(src.total)
    store: L = 0 L in [0 L,]
        inflow.capacity = src.k / (1 h)
    flow pull: SOURCE -> this.store
        request = src.k / (1 h)
    act = event():
        when src.level >= 1 L:
            this.act.start()
            reset when false
        after src.staff:
            this.first = src.k
        until src.level <= 0 L
    since_go = formula(since(src.go))

Place:
    input need: L = 1 L

west: Place

Pump:
    home: Place
    need_here = formula(this.home.need)

pump: Pump
    home = west

clinic:
    staff_hours: h = 100 h
    staffing = solver:
        inputs:
            available = this.staff_hours
            least = src.staff
        solve_for:
            care: h in [least, available]
        constraints:
            care <= available
        objective:
            maximize(care)

watcher:
    care = formula(clinic.staffing.care)

assert src.k <= 5 L

src.go.start()
"""


@pytest.fixture(scope='module')
def found():
    return Things(compiled(READS))


def relations(walk, of=None, by=None):
    return [r for r in walk.relations if (of is None or r['of'] == of) and (by is None or r['by'] == by)]


def test_each_part_reads_what_its_lines_name(found):
    walk = Walk(found)
    reads = {
        (walk.parts[r['part']]['kind'], walk.parts[r['part']]['name'], r['value'])
        for r in relations(walk, 'src', 'reader')
        if r['kind'] == 'reads'
    }
    assert reads == {
        ('formula', 'f', 'src.k'),
        ('value', 'first', 'src.level'),
        ('value', 'bounded', 'src.k'),
        ('formula', 'sum_of', 'src.total'),
        ('endpoint', 'store.inflow', 'src.k'),
        ('flow', 'pull', 'src.k'),
        ('event', 'act', 'src.level'),
        ('event', 'act', 'src.staff'),
        ('event', 'act', 'src.k'),
        ('formula', 'since_go', 'src.go'),
    }
    # The time since an event is a read of its time: the arrow "follows".
    (since,) = [r for r in relations(walk, 'src', 'reader') if r['value'] == 'src.go']
    assert since.get('how') == 'time' and arrow_kind(since) == 'follows'


def test_a_part_reads_a_formula_of_another_thing_and_not_what_the_formula_reads(found):
    walk = Walk(found)
    values = {
        r['value'] for r in relations(walk, 'src', 'reader') if walk.parts[r['part']]['name'] == 'sum_of'
    }
    assert values == {'src.total'}


def test_a_read_through_a_link_reads_the_member_that_it_names(found):
    walk = Walk(found)
    assert [(r['by'], r['of'], r['value']) for r in relations(walk, 'west')] == [
        ('pump', 'west', 'west.need')
    ]


def test_a_solver_reads_its_inputs_and_a_caller_reads_its_results(found):
    walk = Walk(found)
    assert [(r['by'], r['value']) for r in relations(walk, 'src', 'clinic')] == [('clinic', 'src.staff')]
    assert [(r['by'], r['value']) for r in relations(walk, 'clinic', 'watcher')] == [
        ('watcher', 'clinic.staffing')
    ]


def test_assertions_add_nothing_to_the_map(found):
    walk = Walk(found)
    # The top level has no card: the assertion on `src.k` reads it from nowhere.
    assert {r['by'] for r in walk.relations} <= set(found.cards)
    assert not [part for part in walk.parts if part['kind'] == 'assert']


def test_one_arrow_for_each_ordered_pair_and_kind_with_the_number_of_its_values(found):
    doc = picture(found.compiled, style.Style())
    arrows = {(a['from'], a['to'], a['kind']): (a['count'], a['values']) for a in doc['arrows']}
    assert arrows[('src', 'reader', 'reads')] == (4, ['src.k', 'src.level', 'src.staff', 'src.total'])
    assert arrows[('src', 'reader', 'follows')] == (1, ['src.go'])
    assert arrows[('west', 'pump', 'reads')] == (1, ['west.need'])
    assert len(arrows) == len(doc['arrows'])
    # The arrows are sorted by their ends and kind.
    assert [(a['from'], a['to'], a['kind']) for a in doc['arrows']] == sorted(arrows)


def test_a_part_of_one_card_never_relates_to_its_own_card():
    found = Things(compiled('a:\n    x = 1\n    y = formula(this.x * 2)\n    z = formula(a.x)\n'))
    assert Walk(found).relations == []


def test_the_rows_of_a_table_relate_as_their_card():
    found = Things(
        compiled(
            'Place:\n    input need: L = 1 L\n\nplaces: Place from "places.csv"\n\nhub:\n    total = formula(sum(Place.instances.need))\n',
            tables={'places.csv': 'id\na\nb\n'},
        )
    )
    walk = Walk(found)
    assert [(r['of'], r['value']) for r in walk.relations] == [('places', 'places.need')]


def test_the_settings_of_the_picture_take_the_stylesheet_s_and_the_defaults():
    assert settings_of(style.Style()) == {
        'looks': DEFAULT_LOOKS,
        'bundle': list(DEFAULT_BUNDLE),
        'stocks': 4,
        'cards_per_column': 8,
        'card_width': None,
    }
    sheet = style.read('[arrows]\nreads = "full"\nbundle = []\n[layout]\nstocks = 2\ncard_width = 200\n')
    found = settings_of(sheet)
    assert found['looks']['reads'] == 'full' and found['bundle'] == []
    assert (found['stocks'], found['card_width']) == (2, 200)


def test_who_acts_in_the_words_of_a_card():
    assert actor_name('adversary') == ACTOR_NAMES['adversary'] == 'Attacker'
    assert actor_name('night_watch') == 'Night watch'
