"""The trigger lines of the cards (D-56): the words of a condition, the line of an event, and the
shortening of a text.

Each synthetic model writes its rules in its own lines, so each expectation follows from the text of
the test: the words are the names that the test writes, in the rule's order, joined by the generic
words of `triggers`. The counterexamples are pairs of rules that mean different things and must read
differently. The catalogue test checks properties of every event of every scenario: each name that a
rule reads shows in its words, two names never read the same, the rule is kept as written, and the
callers and the options agree with what the builder finds in its own way (`model.index['callers']`
and the rules of each structure). No test reads a text of the catalogue.
"""

from __future__ import annotations

import dataclasses
from functools import cache

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.draw import layout, style
from napkin.draw.model_map import card_title
from napkin.draw.triggers import (
    ELLIPSIS,
    card_events,
    card_lines,
    condition_words,
    event_line,
    event_namer,
    namer,
    number,
    shorten,
    words,
)
from napkin.model.resolved import EventRef, Ref, Terms
from napkin.model.semantic import flat_entity
from tests.build import (
    block,
    compiled,
    document,
    entity,
    event,
    formula,
    named,
    named_event,
    option,
    options,
    parameter,
    runs,
    stock,
    template,
)
from tests.helpers import SCENARIO_IDS, catalogue_model


def world(*declarations, **lines):
    return compiled(document('Trigger fixture', *declarations, **lines))


def line_of(model, entity_name, event_name):
    found = model.scenario.entity(entity_name)
    return event_line(model, found, next(e for e in found.events if e.name == event_name))


def formula_words(model, entity_name, value_name):
    """The words of a formula of `entity_name`, with the names of that formula."""
    found = model.scenario.entity(entity_name)
    expression = found.value(value_name).formula
    return condition_words(expression.node, namer(model, found, [expression]))


def title(model, entity_name):
    """The title of the card of an entity, as the model gives it."""
    return card_title(style.entity_lines(model)[model.scenario.entity(entity_name).entry])


def names_in(node):
    """The names of the typed nodes of an expression: each `Ref` and `EventRef`, and each list (`Terms`)
    as one name."""
    if isinstance(node, (Ref, EventRef, Terms)):
        yield node
    else:
        for child in node.children:
            yield from names_in(child)


def read_parts(event):
    """The expressions of an event that its line reads out."""
    return [item for item in (event.when, event.after, *event.each, event.keep) if item is not None]


# ---- the synthetic models -------------------------------------------------------------------------


@cache
def basic():
    """Two things with a state of one name, the forms of comparisons, groups and arithmetic as
    formulas, and the clocks, counts and the time as rules."""
    return world(
        entity(
            'a',
            named('mode', 'idle', 'running', 'coming_back', records='@fixture'),
            parameter('delay', 2, 'h', 1, 5),
            parameter('limit', 3, 'people', 0, 10),
            parameter('share', 0.3, 'fraction', 0, 1),
            parameter('p', 'true', 'bool'),
            parameter('q', 'false', 'bool'),
            parameter('r', 'true', 'bool'),
            formula('mixed', 'p or q and r', 'bool'),
            formula('grouped', '(p or q) and r', 'bool'),
            formula('flat', 'p and (q and r)', 'bool'),
            formula('two', 'p and q', 'bool'),
            formula('either', 'p or (q or r)', 'bool'),
            formula('negated', 'not (p and q)', 'bool'),
            formula('negated_name', 'not p', 'bool'),
            formula('negated_is', 'not (mode is "idle")', 'bool'),
            formula('state', 'mode is "coming_back"', 'bool'),
            formula('below', 'limit < 2 people', 'bool'),
            formula('at_most', 'limit <= 2 people', 'bool'),
            formula('above', 'limit > 2 people', 'bool'),
            formula('at_least', 'limit >= 2 people', 'bool'),
            formula('arith', '(limit + 2 people) * share - limit / (share * 2) ** 2', 'people'),
            formula('right', 'limit - (limit - 1 people)', 'people'),
            formula('left', 'limit - limit - 1 people', 'people'),
            formula('sign', '-limit + 1 people', 'people'),
            formula('tiny', 'delay >= 1e-9 h and delay >= 0.5 h', 'bool'),
            formula('yes', 'p is true', 'bool'),
            formula('no', 'p is false', 'bool'),
            formula('soon', 'since(begin) < delay', 'bool'),
            formula('soon_or_now', 'since(begin) <= delay', 'bool'),
            event('begin', 't >= 1 h', 'mode = "running"', do_records='@fixture'),
            event('passed', 'since(begin) >= delay'),
            event('counted', 'count(begin) > 0'),
            event('counted_n', 'count(passed) > 2'),
            event('changed', 'mode is "running" and since(mode) >= delay'),
            event('pair', 'mode is "running" and b.mode is not "idle"'),
            block('event wrapped once when (mode is "idle"\n        and p):  @fixture'),
            role='operator',
        ),
        entity(
            'b',
            named('mode', 'idle', 'on', records='@fixture'),
            named_event('go', 'mode = "on"'),
            role='responder',
        ),
    )


@cache
def lists():
    """A template with two instances, a thing that reads them through a link, and a line that fires
    the event of each."""
    return world(
        template(
            'Zone',
            parameter('flag', 'true', 'bool'),
            stock('n', 1, 'people', maximum=10, kind='state'),
            named_event('alarm', 'n = 2 people'),
            event('full', 'n >= 2 people', once=True),
        ),
        entity('z1', template='Zone'),
        entity('z2', template='Zone'),
        entity(
            'hub',
            'let zones = [z1, z2]',
            formula('any_flag', 'any(zones.flag)', 'bool'),
            formula('all_flag', 'all(zones.flag)', 'bool'),
            formula('total', 'sum(zones.n)', 'people'),
            formula('least', 'min(zones.n)', 'people'),
            formula('most', 'max(zones.n)', 'people'),
            formula('least_two', 'min(zones.n, 2 people)', 'people'),
            formula('flagged', 'count(zones.flag) > 1', 'bool'),
            formula('everyone', 'sum(Zone.n)', 'people'),
            event('ring', 't >= 1 h', 'zones.alarm'),
            role='operator',
        ),
    )


@cache
def outcomes():
    """Chances that are numbers, `else`, a chance that is a condition, an actor's choice, every kind of
    change, the parts of the timing, callers on two cards, and an event with a rule and a caller."""
    return world(
        entity(
            'a',
            named('mode', 'idle', 'running', records='@fixture'),
            parameter('share', 0.3, 'fraction', 0, 1),
            parameter('ready', 'true', 'bool'),
            stock('x', 5, 'people', maximum=100),
            stock('y', 5, 'people', maximum=100),
            stock('z', 5, 'people', maximum=100),
            stock('w', 5, 'people', maximum=100),
            event('always', 't >= 1 h'),
            block(
                'event respond once after 2 h when count(always) > 0:  @fixture',
                block('manual 1 - share:', 'x += 1 people'),
                block('shut share:', 'b.go'),
            ),
            block(
                'event fallback once when count(always) > 0:  @fixture',
                block('manual 0.25:', 'y -= 1 people'),
                block('shut else:', 'move 1 people from z to w'),
            ),
            block(
                'event gated once when count(always) > 0:  @fixture',
                block('done ready:', 'own_go'),
                block('skipped else:'),
            ),
            block(
                'event several once when count(always) > 0:  @fixture',
                'mode = "running"',
                'x += 1 people',
                'y += 1 people',
                'z -= 1 people',
                'move 1 people from w to y',
                'b.go',
            ),
            named_event('own_go', 'mode = "idle"'),
            block('event timed after share * 2 h each b.state when t >= 1 h while ready:  @fixture'),
            block('event both once when mode is "running":  @fixture', 'mode = "idle"'),
            event('kick', 't >= 2 h', 'both'),
            role='operator',
        ),
        entity(
            'b',
            named('state', 'off', 'on', records='@fixture'),
            named_event('go', 'state = "on"'),
            role='responder',
        ),
        block(
            'c:  @fixture',
            '"An actor."',
            'role operator',
            'sees a.mode',
            block(
                'event decide once when a.mode is "running":  @fixture',
                'choice',
                block('close 0.7:', 'a.mode = "idle"'),
                block('wait else:'),
            ),
        ),
    )


@cache
def switches():
    """Two runs whose start options give two structures: a start state that only one option sets."""
    return world(
        entity(
            'a',
            named('phase', 'early', 'late', records='@fixture'),
            event('early_only', 'phase is "early"'),
            event('late_only', 'phase is "late"'),
            event('any_time', 't >= 1 h'),
            role='operator',
        ),
        option_groups=(
            options('Response', option('Late', 'A late start.'), option('Early', 'An early start.')),
        ),
        run_lines=runs(r1=['Late'], r2=['Early']),
    )


def switched():
    """`switches` with the option `Late` setting the start state."""
    return world(
        entity(
            'a',
            named('phase', 'early', 'late', records='@fixture'),
            event('early_only', 'phase is "early"'),
            event('late_only', 'phase is "late"'),
            event('any_time', 't >= 1 h'),
            role='operator',
        ),
        option_groups=(
            options(
                'Response',
                option('Late', 'A late start.', 'a.phase = "late"'),
                option('Early', 'An early start.'),
            ),
        ),
        run_lines=runs(r1=['Late'], r2=['Early']),
    )


@cache
def switching():
    return switched()


SYNTHETIC = (basic, lists, outcomes, switching)


# ---- the words of a condition ---------------------------------------------------------------------


def test_is_and_is_not_name_the_state_in_words():
    model = basic()
    assert formula_words(model, 'a', 'state') == 'mode is coming back'
    assert formula_words(model, 'a', 'negated_is') == 'not (mode is idle)'
    assert (
        line_of(model, 'a', 'pair').when
        == f'when mode is running and mode of {title(model, "b")} is not idle'
    )


def test_each_comparison_has_its_own_words():
    model = basic()
    found = {name: formula_words(model, 'a', name) for name in ('below', 'at_most', 'above', 'at_least')}
    assert found == {
        'below': 'limit is below 2 people',
        'at_most': 'limit is at most 2 people',
        'above': 'limit is above 2 people',
        'at_least': 'limit is at least 2 people',
    }
    assert len(set(found.values())) == 4


def test_clocks_counts_and_the_time():
    model = basic()
    assert line_of(model, 'a', 'passed').when == 'when delay has passed since begin'
    assert line_of(model, 'a', 'counted').when == 'when begin has happened'
    assert line_of(model, 'a', 'counted_n').when == 'when passed has happened more than 2 times'
    assert (
        line_of(model, 'a', 'changed').when == 'when mode is running and delay has passed since mode changed'
    )
    assert line_of(model, 'a', 'begin').when == 'from 1 h'


def test_a_time_within_a_delay_is_not_a_time_that_has_passed():
    model = basic()
    within = formula_words(model, 'a', 'soon')
    assert within == 'within delay of begin'
    assert formula_words(model, 'a', 'soon_or_now') == within
    assert 'has passed' not in within
    assert within != line_of(model, 'a', 'passed').when.removeprefix('when ')


def test_a_count_above_zero_and_above_n_read_differently():
    model = basic()
    once = line_of(model, 'a', 'counted').when
    more = line_of(model, 'a', 'counted_n').when
    assert 'more than' not in once
    assert 'more than 2 times' in more


def test_groups_have_parentheses_only_where_the_meaning_needs_them():
    model = basic()
    mixed, grouped = formula_words(model, 'a', 'mixed'), formula_words(model, 'a', 'grouped')
    # `p or q and r` is `p or (q and r)`; `(p or q) and r` is another rule, and reads so.
    assert mixed == 'p or (q and r)'
    assert grouped == '(p or q) and r'
    assert mixed != grouped
    # A group inside a group of its own kind is one list, with no parentheses.
    assert formula_words(model, 'a', 'flat') == 'p, q, and r'
    assert formula_words(model, 'a', 'two') == 'p and q'
    assert formula_words(model, 'a', 'either') == 'p or q or r'
    assert formula_words(model, 'a', 'negated') == 'not (p and q)'
    assert formula_words(model, 'a', 'negated_name') == 'not p'


def test_the_outer_parentheses_of_a_rule_never_show():
    line = line_of(basic(), 'a', 'wrapped')
    assert line.rule.startswith('(') and line.rule.endswith(')')
    assert line.when == 'when mode is idle and p'


def test_arithmetic_reads_in_symbols_with_the_parentheses_that_its_order_needs():
    model = basic()
    assert formula_words(model, 'a', 'arith') == '(limit + 2 people) × share − limit / (share × 2) ^ 2'
    # `a - (b - c)` is not `a - b - c`.
    assert formula_words(model, 'a', 'right') == 'limit − (limit − 1 people)'
    assert formula_words(model, 'a', 'left') == 'limit − limit − 1 people'
    assert formula_words(model, 'a', 'sign') == '−limit + 1 people'


def test_numbers_and_units_read_plainly():
    model = basic()
    assert formula_words(model, 'a', 'tiny') == 'delay is at least 1e-9 h and delay is at least 0.5 h'
    assert [number(v) for v in (2, 2.0, 0.5, 1e-9, 1e16, -3)] == ['2', '2', '0.5', '1e-9', '1e16', '−3']


@settings(derandomize=True, max_examples=200, deadline=None)
@given(st.floats(min_value=1e-300, max_value=1e300, allow_nan=False, allow_infinity=False))
def test_a_number_reads_back_as_the_same_number(value):
    assert float(number(value)) == value
    assert float(number(-value).replace('−', '-')) == -value


def test_yes_and_no():
    model = basic()
    assert formula_words(model, 'a', 'yes') == 'p is yes'
    assert formula_words(model, 'a', 'no') == 'p is no'


def test_a_list_reads_by_its_name_as_written():
    model = lists()
    found = {
        name: formula_words(model, 'hub', name)
        for name in ('any_flag', 'all_flag', 'total', 'least', 'most', 'least_two', 'flagged', 'everyone')
    }
    assert found == {
        'any_flag': 'any flag of zones',
        'all_flag': 'every flag of zones',
        'total': 'sum of n over zones',
        'least': 'least n of zones',
        'most': 'most n of zones',
        'least_two': 'least of n of zones and 2 people',
        'flagged': 'flag holds in more than 1 of zones',
        'everyone': f'sum of n over {words("Zone")}',
    }
    assert line_of(model, 'hub', 'ring').changes == ('fires alarm of zones',)


def test_two_names_that_read_alike_add_the_title_of_the_other_card():
    model = basic()
    found = model.scenario.entity('a')
    pair = next(e for e in found.events if e.name == 'pair')
    name_of = event_namer(model, found, pair)
    names = list(names_in(pair.when.node))
    assert [name_of(n) for n in names] == ['mode', f'mode of {title(model, "b")}']


# ---- the line of an event -------------------------------------------------------------------------


def test_an_event_that_only_a_line_fires_names_its_callers():
    model = outcomes()
    other = title(model, 'a')
    assert line_of(model, 'b', 'go').when == f'when {other}: respond or {other}: several fires it'
    assert line_of(model, 'a', 'own_go').when == 'when gated fires it'
    zone = lists()
    assert line_of(zone, 'z1', 'alarm').when == f'when {title(zone, "hub")}: ring fires it'


def test_an_event_with_a_rule_and_a_caller_says_both():
    assert line_of(outcomes(), 'a', 'both').when == 'when mode is running, or when kick fires it'


def test_the_options_that_switch_an_event():
    model = switching()
    assert len(model.structures) == 2
    assert line_of(model, 'a', 'late_only').options == 'only with Late'
    assert line_of(model, 'a', 'early_only').options == 'not with Late'
    assert line_of(model, 'a', 'any_time').options == ''
    assert line_of(model, 'a', 'late_only').full.endswith('; only with Late')


def test_one_structure_gives_no_options_note():
    model = switches()
    assert len(model.structures) == 1
    assert line_of(model, 'a', 'early_only').options == line_of(model, 'a', 'any_time').options == ''
    # No option sets the start state that the event needs, so no run holds it.
    assert line_of(model, 'a', 'late_only').options == 'in no run'


def test_chances_that_are_numbers_show_and_conditions_do_not():
    model = outcomes()
    respond = line_of(model, 'a', 'respond')
    assert respond.chance == ('manual, chance 1 − share', 'shut, chance share')
    assert respond.changes == ('manual: adds to x', f'shut: fires {title(model, "b")}: go')
    assert respond.outcomes == (
        'manual, chance 1 − share: adds to x',
        f'shut, chance share: fires {title(model, "b")}: go',
    )
    fallback = line_of(model, 'a', 'fallback')
    assert fallback.chance == ('manual, chance 0.25', 'shut, chance of the rest')
    assert fallback.changes == ('manual: takes from y', 'shut: moves from z to w')
    gated = line_of(model, 'a', 'gated')
    assert gated.chance == ()
    assert gated.changes == ('done: fires own go',)


def test_a_choice_names_its_outcomes():
    line = line_of(outcomes(), 'c', 'decide')
    assert line.choice == 'chooses close or wait'
    assert line.chance == ('close, chance 0.7', 'wait, chance of the rest')
    assert line_of(outcomes(), 'a', 'respond').choice == ''


def test_the_changes_name_each_target_with_its_verb_once():
    model = outcomes()
    line = line_of(model, 'a', 'several')
    assert line.changes == (
        f'sets mode, adds to x, y, takes from z, moves from w to y, fires {title(model, "b")}: go',
    )


def test_the_timing_of_an_event():
    line = line_of(outcomes(), 'a', 'timed')
    assert line.when == 'from 1 h'
    assert line.timing == ('after share × 2 h', 'while ready', 'once for each value of state')
    assert line_of(outcomes(), 'a', 'respond').timing == ('after 2 h', 'once')


def test_each_instance_reads_its_own_rule_with_the_template_names():
    model = lists()
    first, second = line_of(model, 'z1', 'full'), line_of(model, 'z2', 'full')
    assert first.when == second.when == 'when n is at least 2 people'
    assert (first.key, second.key) == ('z1.full', 'z2.full')
    assert first.full == second.full


def test_the_events_of_a_card_in_the_order_of_the_file():
    model = outcomes()
    found = model.scenario.entity('a')
    assert card_events(model, 'a') == tuple(found.events)
    assert card_events(model, found) == tuple(found.events)
    assert [line.event for line in card_lines(model, 'a')] == [e.name for e in found.events]
    with pytest.raises(ValueError):
        card_events(model, 'nothing')


def check_lines(model):
    """The properties of every line of a model: each name that it reads shows in its words, two names
    never read the same, the rule is as written, and the full line is its parts."""
    for thing in model.scenario.entities:
        for found in thing.events:
            line = event_line(model, thing, found)
            name_of = event_namer(model, thing, found)
            seen = {}
            for expression in read_parts(found):
                said = condition_words(expression.node, name_of)
                assert said in line.full, (line.full, said)
                for node in names_in(expression.node):
                    if isinstance(node, Terms):
                        member, group = name_of(node)
                        assert member in said and group in said, (said, member, group)
                        continue
                    assert name_of(node) in said, (said, name_of(node))
                    key = (node.entity, node.member) if isinstance(node, Ref) else (node.key, node.ending)
                    seen.setdefault(name_of(node), set()).add(key)
            assert all(len(keys) == 1 for keys in seen.values()), seen
            if found.when is None:
                assert line.rule is None
            else:
                assert line.rule == found.when.written
                assert line.when in line.full
            parts = [line.when, *line.timing, line.choice, *line.outcomes, line.options]
            joined = '; '.join(part for part in parts if part)
            assert line.full == line.name + (f' — {joined}' if joined else '')
            assert line.name == words(found.name)
            assert line.key == f'{flat_entity(thing.name)}.{found.name}'


@pytest.mark.parametrize('build', SYNTHETIC, ids=lambda build: build.__name__)
def test_every_name_of_a_rule_shows_in_its_words(build):
    check_lines(build())


def test_the_same_model_gives_the_same_lines():
    first, second = switched(), switched()
    assert first is not second

    def lines_of(model):
        return [
            dataclasses.asdict(line) for card in style.entity_lines(model) for line in card_lines(model, card)
        ]

    assert lines_of(first) == lines_of(second)
    assert lines_of(outcomes()) == lines_of(outcomes())


def test_a_name_of_the_model_in_words():
    assert words('strike_again') == 'strike again'
    assert words('AIShare') == 'AI share'
    assert words('coming_back') == 'coming back'


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


# ---- the catalogue --------------------------------------------------------------------------------


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_every_catalogue_line(scenario_id):
    """Each event of a scenario: the properties of `check_lines`; an event without a rule names every
    caller that the builder finds (`index['callers']`); the options note agrees with the rules of each
    structure; the lines are the same each time; and each full line shortens within its bounds at the
    width of a card's text."""
    model = catalogue_model(scenario_id)
    check_lines(model)
    lines = style.entity_lines(model)
    by_flat = {flat: model.scenario.entity(name) for flat, name in model.entities.items()}
    callers = model.index['callers']
    structures = {starts: set(structure.rules) for starts, structure in model.structures.items()}

    def measure(text):
        return layout.text_width(text, 11)

    for card in lines:
        found = card_lines(model, card)
        assert found == card_lines(model, card)
        for line, item in zip(found, card_events(model, card), strict=True):
            key = f'{flat_entity(lines[card].name)}.{item.name}'
            if item.when is None and not item.each:
                for caller in callers.get(key, ()):
                    rid = caller.rpartition('.')[0]
                    flat, _, name = rid.rpartition('.')
                    by = by_flat[flat]
                    said = (
                        words(name) if by.entry == card else f'{card_title(lines[by.entry])}: {words(name)}'
                    )
                    assert said in line.when, (line.when, said)
            held = [starts for starts, rules in structures.items() if key in rules]
            lacking = [starts for starts in structures if starts not in held]
            if not lacking:
                assert line.options == ''
            elif not held:
                assert line.options == 'in no run'
            elif line.options.startswith('only with ') and line.options[10:] in model.start_options:
                option = line.options[10:]
                assert all(option in s for s in held) and not any(option in s for s in lacking)
            elif line.options.startswith('not with ') and line.options[9:] in model.start_options:
                option = line.options[9:]
                assert not any(option in s for s in held) and all(option in s for s in lacking)
            else:
                assert line.options.startswith('only with '), line.options
            kept, cut = shorten(line.full, 260, 2, measure)
            assert len(kept) <= 2 and all(measure(row) <= 260 for row in kept)
            assert cut == (len(shorten(line.full, 260, 99, measure)[0]) > 2)
