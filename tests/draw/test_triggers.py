"""The trigger lines of the cards (D-56, napkin/draw/triggers.py): the words of each form, the words of
each part of an event, and their properties on every event of the synthetic models.

Each expected text follows from the rule of the module that it names, written by hand from the model's
own names: no test pins the words of a run of the code. Two lines that the rules say differ (a time
that has passed against a time within a delay, `p or (q and r)` against `(p or q) and r`) must read
differently. The catalogue test checks properties of every event of every scenario: each name that a
line reads shows in its words, and the line is its parts (`test_catalogue.py`, for stage M).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.draw.things import Things, event_statements
from napkin.draw.triggers import (
    ELLIPSIS,
    _reads,
    _shown,
    card_events,
    card_lines,
    condition_words,
    namer,
    number,
    shorten,
    words,
)
from napkin.model import semantic as s
from tests.draw.models import compiled
from tests.draw.test_notation import MEMBERSHIP


def world(text):
    return Things(compiled(text))


def line_of(found, card, event):
    """The `Line` of one event of a card."""
    return next(line for line in card_lines(found, card) if line.event == event)


def formula_words(found, card, value):
    """The words of the expression of a formula of a card."""
    part = found.part(found.cards[card].template, value)
    return condition_words(part.init, namer(found, card, (part.init,)))


def title(found, card):
    return found.cards[card].title


# ---- the synthetic models -------------------------------------------------------------------------

# Each form of the words, as a formula of `a`, and the clocks, counts and times as the triggers of its
# events; `b` has a mode of its own, so that two names read alike.
BASIC = """\
a:
    "The first thing."
    title "The first thing"
    mode: enum[IDLE, RUNNING, COMING_BACK] = IDLE
    input limit: people = 4 people
    input share = 0.5
    input delay: h = 2 h
    input p: bool = true
    input q: bool = false
    input r: bool = true
    state = formula(this.mode == COMING_BACK)
    negated_is = formula(not (this.mode == IDLE))
    below = formula(this.limit < 2 people)
    at_most = formula(this.limit <= 2 people)
    above = formula(this.limit > 2 people)
    at_least = formula(this.limit >= 2 people)
    soon = formula(since(this.begin) < this.delay)
    soon_or_now = formula(since(this.begin) <= this.delay)
    mixed = formula(this.p or this.q and this.r)
    grouped = formula((this.p or this.q) and this.r)
    flat = formula(this.p and (this.q and this.r))
    two = formula(this.p and this.q)
    either = formula(this.p or (this.q or this.r))
    negated = formula(not (this.p and this.q))
    negated_name = formula(not this.p)
    arith = formula((this.limit + 2 people) * this.share - this.limit / (this.share * 2) ** 2)
    right = formula(this.limit - (this.limit - 1 people))
    left = formula(this.limit - this.limit - 1 people)
    sign = formula(-this.limit + 1 people)
    tiny = formula(this.delay >= 1e-9 h and this.delay >= 0.5 h)
    yes = formula(this.p == true)
    no = formula(this.p == false)
    begin = event():
        when t >= 1 h:
            this.begin.start()
            reset when false
    passed = event():
        when since(this.begin) >= this.delay:
            this.passed.start()
            reset when false
    counted = event():
        when count(this.begin.occurrences) > 0:
            this.counted.start()
            reset when false
    counted_n = event():
        when count(this.passed.occurrences) > 2:
            this.counted_n.start()
    changed = event():
        when this.mode == RUNNING and elapsed(this.mode) >= this.delay:
            this.changed.start()
    pair = event():
        when this.mode == RUNNING and b.mode != IDLE:
            this.pair.start()
    wrapped = event():
        when (this.mode == IDLE and this.p):
            this.wrapped.start()
            reset after 1 h

b:
    "The second thing."
    title "The second thing"
    mode: enum[IDLE, BUSY] = IDLE
"""

# Collections: of the members of a template, a literal and a filter; and a start on each member.
LISTS = """\
Zone:
    input flag: bool = false
    input n: people = 1 people
    full = event():
        when this.n >= 2 people:
            this.full.start()
            reset when false
    alarm = event():
        after 0 h

z1: Zone

z2: Zone
    n = 3 people

hub:
    "The hub."
    title "The hub"
    any_flag = formula(any(Zone.instances.flag))
    all_flag = formula(all(Zone.instances.flag))
    total = formula(sum(Zone.instances.n))
    least = formula(min(Zone.instances.n))
    most = formula(max(Zone.instances.n))
    least_two = formula(min(min(Zone.instances.n), 2 people))
    flagged = formula(count(Zone.instances.flag) > 1)
    pair = formula(sum(<z1, z2>.n))
    chosen = formula(sum(Zone.instances.where(flag).n))
    ring = event():
        after 0 h:
            Zone.instances.alarm.start()

hub.ring.start()
"""

# The parts of an event: its starts, its steps and their changes.
EVENTS = """\
a:
    "The first thing."
    title "The first thing"
    mode: enum[IDLE, RUNNING] = IDLE
    input share = 0.5
    input ready: bool = true
    x: people = 0 people
    y: people = 0 people
    z: people = 10 people in [0 people,]
    w: people = 10 people in [0 people,]
    ok: bool = false
    respond = event():
        "The first thing responds."
        after 2 h:
            this.x += 1 people
            b.go.start()
    several = event():
        after 0 h:
            this.mode = RUNNING
            this.x += 1 people
            this.y += 1 people
            this.z -= 1 people
            move 1 people from this.w to this.y
            b.go.start()
    both = event():
        when this.mode == RUNNING:
            this.both.start()
            reset when false
    kick = event():
        after 0 h:
            this.both.start()
    timed = event():
        when t >= 1 h:
            this.timed.start()
            reset after 1 h
        after this.share * 2 h when this.ready:
            this.x += 1 people
        until this.y >= 3 people
        after 1 h
    branched = event():
        after 0 h:
            if this.ok:
                this.x += 1 people
            else:
                this.y += 1 people
    drawn = event():
        after 1 h:
            switch categorical(FIXED: 0.7, FAILED: 0.3).draw():
                FIXED:
                    this.mode = RUNNING
                FAILED:
                    this.kick.start()
    nothing = event():
        after 0 h

b:
    "The second thing."
    title "The second thing"
    go = event():
        after 0 h

boss:
    forecast = categorical(SEND: 0.25, WAIT: 0.75)

depot:
    spares = 1 in [0,]
    waits = 0
    decide = event():
        order: enum[SEND, WAIT] = WAIT
        after 0 h:
            order = boss.forecast.draw()
            switch order:
                SEND when this.spares >= 1:
                    this.spares -= 1
                WAIT:
                    this.waits += 1

a.respond.start()
a.several.start()
a.kick.start()
a.branched.start()
a.drawn.start()
depot.decide.start()
"""

# Options whose runs leave events out: the input `late` is true only with the option "Late".
SWITCHING = """\
scenario "Switching"
    horizon 10 h

options "Timing":
    "Early":
        "Early."
    "Late":
        "Late."
        a.late = true  @fixture

runs:
    early = "Early"
    late = "Late"

a:
    input late: bool = false  @fixture
    late_only = event():
        when this.late and t >= 1 h:
            this.late_only.start()
            reset when false
    early_only = event():
        when not this.late and t >= 1 h:
            this.early_only.start()
            reset when false
    any_time = event():
        when t >= 1 h:
            this.any_time.start()
            reset when false
    never = event():
        when this.late and not this.late:
            this.never.start()

record fixture: assumption "A synthetic test fixture."
"""

# The membership tests of the notation's plant: in formulas, a stage's guard and a trigger's condition.
SYNTHETIC = {
    'basic': BASIC,
    'lists': LISTS,
    'events': EVENTS,
    'switching': SWITCHING,
    'membership': MEMBERSHIP,
}


@pytest.fixture(scope='module')
def models():
    return {name: world(text) for name, text in SYNTHETIC.items()}


# ---- the words of a condition ---------------------------------------------------------------------


def test_is_and_is_not_name_the_state_in_words(models):
    found = models['basic']
    assert formula_words(found, 'a', 'state') == 'mode is coming back'
    assert formula_words(found, 'a', 'negated_is') == 'not (mode is idle)'
    assert (
        line_of(found, 'a', 'pair').starts
        == f'when mode is running and mode of {title(found, "b")} is not idle'
    )


def test_each_comparison_has_its_own_words(models):
    found = {
        name: formula_words(models['basic'], 'a', name) for name in ('below', 'at_most', 'above', 'at_least')
    }
    assert found == {
        'below': 'limit is below 2 people',
        'at_most': 'limit is at most 2 people',
        'above': 'limit is above 2 people',
        'at_least': 'limit is at least 2 people',
    }
    assert len(set(found.values())) == 4


def test_clocks_counts_and_the_time(models):
    found = models['basic']
    assert line_of(found, 'a', 'passed').starts == 'when delay has passed since begin, once'
    assert line_of(found, 'a', 'counted').starts == 'when begin has started, once'
    assert line_of(found, 'a', 'counted_n').starts == 'when passed has started more than 2 times'
    assert (
        line_of(found, 'a', 'changed').starts
        == 'when mode is running and delay has passed since mode changed'
    )
    assert line_of(found, 'a', 'begin').starts == 'from 1 h, once'


def test_a_time_within_a_delay_is_not_a_time_that_has_passed(models):
    found = models['basic']
    within = formula_words(found, 'a', 'soon')
    assert within == 'within delay of begin'
    assert formula_words(found, 'a', 'soon_or_now') == within
    assert 'has passed' not in within


def test_a_count_above_zero_and_above_n_read_differently(models):
    once = line_of(models['basic'], 'a', 'counted').starts
    more = line_of(models['basic'], 'a', 'counted_n').starts
    assert 'more than' not in once and 'more than 2 times' in more


def test_groups_have_parentheses_only_where_the_meaning_needs_them(models):
    found = models['basic']
    mixed, grouped = formula_words(found, 'a', 'mixed'), formula_words(found, 'a', 'grouped')
    # `p or q and r` is `p or (q and r)`; `(p or q) and r` is another rule, and reads so.
    assert mixed == 'p or (q and r)'
    assert grouped == '(p or q) and r'
    # A group inside a group of its own kind is one list, with no parentheses.
    assert formula_words(found, 'a', 'flat') == 'p, q, and r'
    assert formula_words(found, 'a', 'two') == 'p and q'
    assert formula_words(found, 'a', 'either') == 'p or q or r'
    assert formula_words(found, 'a', 'negated') == 'not (p and q)'
    assert formula_words(found, 'a', 'negated_name') == 'not p'


def test_a_membership_test_reads_as_the_file_writes_it(models):
    # `x in [lo, hi]` is the program's `within`, a name that the file never writes: it reads as the
    # file's form with "is", as a comparison does, and a part of a lower precedence is in parentheses,
    # as is the test under `not`.
    found = models['membership']
    assert formula_words(found, 'plant', 'inside') == 'x is in [lo, hi]'
    assert formula_words(found, 'plant', 'fixed') == 'x + y is in [1 h, 3 h]'
    assert formula_words(found, 'plant', 'picked') == '(x if on, else y) is in [lo, 2 × hi]'
    go, check = line_of(found, 'plant', 'go'), line_of(found, 'plant', 'check')
    assert go.starts == 'when on and not (x is in [lo, 3 h])'
    assert go.steps == ('after 1 h when x is in [1 h, 2 h]: sets seen',)
    assert check.starts == 'when x is in [lo, hi]'
    assert check.steps == ('after 0 h when y is in [lo, hi]: sets seen',)


def test_the_outer_parentheses_of_a_rule_never_show(models):
    line = line_of(models['basic'], 'a', 'wrapped')
    assert line.rule == 'this.mode == IDLE and this.p'
    assert line.starts == 'when mode is idle and p, again after 1 h'


def test_arithmetic_reads_in_symbols_with_the_parentheses_that_its_order_needs(models):
    found = models['basic']
    assert formula_words(found, 'a', 'arith') == '(limit + 2 people) × share − limit / (share × 2) ^ 2'
    # `a - (b - c)` is not `a - b - c`.
    assert formula_words(found, 'a', 'right') == 'limit − (limit − 1 people)'
    assert formula_words(found, 'a', 'left') == 'limit − limit − 1 people'
    assert formula_words(found, 'a', 'sign') == '−limit + 1 people'


def test_numbers_and_units_read_plainly(models):
    assert (
        formula_words(models['basic'], 'a', 'tiny') == 'delay is at least 1e-9 h and delay is at least 0.5 h'
    )
    assert [number(v) for v in (2, 2.0, 0.5, 1e-9, 1e16, -3)] == ['2', '2', '0.5', '1e-9', '1e16', '−3']


@settings(derandomize=True, max_examples=200, deadline=None)
@given(st.floats(min_value=1e-300, max_value=1e300, allow_nan=False, allow_infinity=False))
def test_a_number_reads_back_as_the_same_number(value):
    assert float(number(value)) == value
    assert float(number(-value).replace('−', '-')) == -value


def test_yes_and_no(models):
    assert formula_words(models['basic'], 'a', 'yes') == 'p is yes'
    assert formula_words(models['basic'], 'a', 'no') == 'p is no'


def test_a_collection_reads_as_written(models):
    found = models['lists']
    names = ('any_flag', 'all_flag', 'total', 'least', 'most', 'least_two', 'flagged', 'pair', 'chosen')
    assert {name: formula_words(found, 'hub', name) for name in names} == {
        'any_flag': 'any flag of zone instances',
        'all_flag': 'every flag of zone instances',
        'total': 'sum of n over zone instances',
        'least': 'least n of zone instances',
        'most': 'most n of zone instances',
        'least_two': 'least of least n of zone instances and 2 people',
        'flagged': 'flag holds in more than 1 of zone instances',
        'pair': 'sum of n over z1 and z2',
        'chosen': 'sum of n over zone instances where flag',
    }
    assert line_of(found, 'hub', 'ring').steps == ('after 0 h: starts alarm of zone instances',)


def test_two_names_that_read_alike_add_the_title_of_the_other_card(models):
    found = models['basic']
    pair = next(event for event in found.events('a') if event.name == 'pair')
    name_of = namer(found, 'a', _shown(pair))
    reads = list(_reads(pair.triggers[0].test))
    assert [name_of(read) for read in reads] == ['mode', f'mode of {title(found, "b")}']


# ---- the line of an event -------------------------------------------------------------------------


def test_an_event_that_another_starts_names_its_callers(models):
    found = models['events']
    other = title(found, 'a')
    assert line_of(found, 'b', 'go').starts == f'when {other}: respond or {other}: several starts it'
    assert line_of(found, 'a', 'kick').starts == 'when drawn starts it, or the setup starts it'
    zone = models['lists']
    assert line_of(zone, 'z1', 'alarm').starts == f'when {title(zone, "hub")}: ring starts it'


def test_an_event_with_a_trigger_and_a_caller_says_both(models):
    assert (
        line_of(models['events'], 'a', 'both').starts == 'when mode is running, once, or when kick starts it'
    )


def test_an_event_that_nothing_starts_says_so(models):
    assert line_of(models['events'], 'a', 'nothing').starts == 'never: nothing starts it'
    assert line_of(models['events'], 'a', 'respond').starts == 'the setup starts it'


def test_the_options_that_switch_an_event(models):
    found = models['switching']
    assert found.runs == ('early', 'late')
    assert line_of(found, 'a', 'late_only').options == 'only with Late'
    assert line_of(found, 'a', 'early_only').options == 'not with Late'
    assert line_of(found, 'a', 'any_time').options == ''
    assert line_of(found, 'a', 'never').options == 'in no run'
    assert line_of(found, 'a', 'late_only').full.endswith('; only with Late')
    assert line_of(found, 'a', 'late_only').joined(options=False).endswith('once')


def test_one_run_gives_no_options_note_but_to_an_event_that_cannot_start(models):
    found = models['events']
    assert found.runs == (None,)
    lines = {line.event: line.options for line in card_lines(found, 'a')}
    assert lines.pop('nothing') == 'in no run'
    assert set(lines.values()) == {''}


def test_the_changes_name_each_target_with_its_verb_once(models):
    found = models['events']
    assert line_of(found, 'a', 'several').steps == (
        f'after 0 h: sets mode, adds to x, y, takes from z, moves from w to y, starts {title(found, "b")}: go',
    )
    assert line_of(found, 'a', 'respond').steps == (f'after 2 h: adds to x, starts {title(found, "b")}: go',)


def test_the_steps_of_an_event(models):
    line = line_of(models['events'], 'a', 'timed')
    assert line.starts == 'from 1 h, again after 1 h'
    assert line.steps == (
        'after share × 2 h when ready: adds to x',
        'until y is at least 3 people',
        'waits 1 h',
    )
    assert (
        line.full
        == 'timed — from 1 h, again after 1 h; after share × 2 h when ready: adds to x; until y is at least 3 people; waits 1 h'
    )


def test_a_branch_and_a_switch_say_what_each_case_changes(models):
    found = models['events']
    assert line_of(found, 'a', 'branched').steps == ('after 0 h: if ok: adds to x, else: adds to y',)
    assert line_of(found, 'a', 'drawn').steps == (
        'after 1 h: draws fixed (chance 0.7) or failed (chance 0.3), fixed: sets mode, failed: starts kick',
    )
    assert line_of(found, 'depot', 'decide').steps == (
        'after 0 h: sets order, by order, send when spares is at least 1: takes from spares, wait: adds to waits',
    )


def test_the_label_is_the_text_of_the_event_and_the_rule_its_first_condition(models):
    line = line_of(models['events'], 'a', 'respond')
    assert (line.label, line.rule) == ('The first thing responds.', None)
    assert line_of(models['events'], 'a', 'both').rule == 'this.mode == RUNNING'


def test_each_member_reads_its_own_rule_with_the_template_names(models):
    found = models['lists']
    first, second = line_of(found, 'z1', 'full'), line_of(found, 'z2', 'full')
    assert first.starts == second.starts == 'when n is at least 2 people, once'
    assert (first.key, second.key) == ('z1.full', 'z2.full')
    assert first.full == second.full


def test_the_events_of_a_card_in_written_order(models):
    found = models['events']
    assert card_events(found, 'a') == tuple(found.events('a'))
    assert [line.event for line in card_lines(found, 'a')] == [event.name for event in found.events('a')]
    with pytest.raises(ValueError):
        card_events(found, 'nothing')


def check_lines(found):
    """The properties of every line of a model: each name that its starts and its steps read shows in
    its words, the rule is the first trigger's condition, and the full line is its parts."""
    for card in found.cards:
        for line in card_lines(found, card):
            event = next(item for item in found.events(card) if item.name == line.event)
            name_of = namer(found, card, _shown(event))
            for expression in _shown(event):
                for read in _reads(expression):
                    # The time reads as "from" and "before"; a collection by its own words.
                    if read.start[0] in ('time', 'instances', 'literal', 'where', 'by', 'lookup'):
                        continue
                    assert name_of(read) in line.full, (line.full, name_of(read))
            assert line.full == line.joined(True)
            assert line.full.startswith(line.name)
            parts = [part for part in (line.starts, *line.steps, line.options) if part]
            assert line.full == line.name + ' — ' + '; '.join(parts)
            assert (line.rule is None) == (not event.triggers)
            statements = list(event_statements(event))
            assert all(
                isinstance(
                    item,
                    (
                        s.DeclaredAssign,
                        s.DeclaredMove,
                        s.DeclaredStart,
                        s.DeclaredIf,
                        s.DeclaredSwitch,
                        s.DeclaredCase,
                    ),
                )
                for item in statements
            )


@pytest.mark.parametrize('name', sorted(SYNTHETIC))
def test_every_name_of_a_line_shows_in_its_words(models, name):
    check_lines(models[name])


def test_the_same_model_gives_the_same_lines():
    first, second = world(EVENTS), world(EVENTS)
    assert [card_lines(first, card) for card in first.cards] == [
        card_lines(second, card) for card in second.cards
    ]


def test_a_name_of_the_model_in_words():
    assert words('strike_again') == 'strike again'
    assert words('AIShare') == 'AI share'
    assert words('coming_back') == 'coming back'
    assert words('COMING_BACK') == 'coming back'


# ---- shortening -----------------------------------------------------------------------------------


def wide(text):
    """A measure in which some letters are wider than others."""
    return sum(3 if char in 'mwMW' else 1 for char in text)


TEXTS = st.lists(st.text(alphabet='abmw', min_size=1, max_size=14), min_size=0, max_size=30).map(' '.join)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(TEXTS, st.integers(min_value=3, max_value=40), st.integers(min_value=1, max_value=4), st.booleans())
def test_shorten_keeps_its_bounds_and_marks_a_cut(text, width, lines, weighted):
    measure = wide if weighted else len
    kept, cut = shorten(text, width, lines, measure)
    assert 1 <= len(kept) <= lines
    assert all(measure(row) <= width for row in kept)
    assert cut == any(ELLIPSIS in row for row in kept)
    assert not cut or kept[-1].endswith(ELLIPSIS)
    if measure(text) <= width:
        assert kept == [text] and not cut
    shown = ''.join(kept).replace(ELLIPSIS, '').replace(' ', '')
    whole = text.replace(' ', '')
    if cut:
        assert whole.startswith(shown) and len(shown) < len(whole)
    else:
        assert shown == whole


def test_shorten_counterexamples():
    # A text that fits is unchanged, its spaces too.
    assert shorten('a  b', 10, 1, len) == (['a  b'], False)
    # Breaks at spaces.
    assert shorten('aaa bbb ccc', 7, 2, len) == (['aaa bbb', 'ccc'], False)
    # Cuts the last line and ends it with the mark, within the width.
    assert shorten('aaa bbb ccc ddd', 7, 1, len) == (['aaa…'], True)
    # A word wider than a line breaks where it must.
    assert shorten('abcdefghij', 4, 3, len) == (['abcd', 'efgh', 'ij'], False)
    assert shorten('abcdefghij', 4, 2, len) == (['abcd', 'efg…'], True)
    # A letter wider than a line cannot show: the text stops before it.
    assert shorten('aa M bb', 5, 3, lambda text: sum(10 if char == 'M' else 1 for char in text)) == (
        ['aa…'],
        True,
    )
    with pytest.raises(ValueError):
        shorten('text', 0, 1, len)
    with pytest.raises(ValueError):
        shorten('text', 10, 0, len)
