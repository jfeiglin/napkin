"""A played run on the timeline engine (docs/engine.md, "Play"; `napkin/engine/timeline/run.py`).

The scenarios are those of the tests of the engine of today: the world and its guard
(`tests/build.play_scenario`), a decision at a fixed time and one after a delay, a decision that an
event names between two other events, decisions among events that chance takes, and the cascade of
events of one moment (`test_pause`, `test_settled_decisions`). Two oracles:

- what each scenario says of itself: the time of its decision, what its actor sees there, what the
  events before the decision wrote, and that no step of the decision or after it is taken;
- the engine of today on the flat structure of the same text, with the same control, picks and
  luck: every entry of the trace, the decision, the time at which the run stops and the state there.
"""

from dataclasses import replace

import pytest

from napkin.engine import timeline
from napkin.engine.errors import SimulationError
from napkin.engine.runtime import simulate
from napkin.model import hybrid
from tests.build import PLAY_WORLD, compiled, document, library, play_guard, play_scenario
from tests.engine.test_pause import nested_text, random_text, timed_text
from tests.engine.test_settled_decisions import cascade_text

READER = {'actor': 'reader'}
SETTLED = {'settled_decisions': True, 'decision_events': {'actor.decide', 'actor.next_choice'}}


def both(tmp_path, text, control, picks=(), luck=None, **options):
    """The run of the engine of today and the run of the timeline engine of one played run."""
    model = compiled(text)
    resolved = replace(model.resolve('a'), luck=luck)
    old = simulate(resolved, model.library, play={'control': control, 'picks': list(picks)}, **options)
    return old, played(tmp_path, text, control, picks, luck, **options)


def played(tmp_path, text, control, picks=(), luck=None, **options):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / 'model.scn'
    path.write_text(text, encoding='utf-8')
    plan = timeline.Plan.of(hybrid.compile(path, library()), 'a')
    return timeline.run(plan, play={'control': control, 'picks': list(picks)}, luck=luck, **options)


def same(old, new, names=()):
    """The two runs have the same trace, entry by entry, the same decision, and stop at the same
    time with the same values of `names`."""
    assert new.entries == old.trace
    assert new.decision == old.decision
    assert (new.paused, new.end_time, new.horizon) == (old.paused, old.end_time, old.horizon)
    state = old.env_at(old.end_time)
    for name in names:
        assert new.final(name)[0] == state[name], name


# ---- a decision that waits: what its actor sees -------------------------------------------------------

GUARD = {'guard': 'reader'}
CHOICES = ('guard.first_choice', 'guard.second_choice', 'world.level', 'world.alarm')


def test_the_first_decision_shows_what_its_actor_sees(tmp_path):
    """The guard decides at 3 h. The level rises at 0.1 an hour from 0: 0.3. The alarm went on at
    1 h; the hum is not seen, and the late event has not happened."""
    old, new = both(tmp_path, play_scenario(), GUARD)
    decision = new.decision
    assert (decision['t'], decision['event'], decision['by']) == (3.0, 'guard.first', 'reader')
    assert decision['view']['world.alarm'] == 'on'
    assert decision['view']['world.level'] == pytest.approx(0.3, rel=1e-9)
    assert (decision['view']['world.delay'], decision['units']['world.delay']) == (pytest.approx(2), 'days')
    assert (decision['view']['world.ring'], decision['view']['world.late']) == (1, 0)
    assert [(item['t'], item['event']) for item in decision['seen']] == [(1.0, 'world.ring.done')]
    assert [(item['name'], item['available']) for item in decision['outcomes']] == [
        ('shut', True),
        ('wait', True),
    ]
    # With no pause, the run goes on with the choice of the model, and the first decision still waits.
    assert not new.paused and new.end_time == new.horizon
    same(old, new, CHOICES)


@pytest.mark.parametrize(
    'control, waits',
    [
        ({'guard.second': 'reader'}, (6.0, 'guard.second')),
        ({'guard': 'reader', 'guard.first': 'chance'}, (6.0, 'guard.second')),
        ({'guard': 'agent', 'guard.second': 'chance'}, (3.0, 'guard.first')),
        ({'guard': 'chance'}, None),
    ],
)
def test_the_method_of_an_event_comes_before_that_of_its_actor(tmp_path, control, waits):
    old, new = both(tmp_path, play_scenario(), control, pause_at_decision=True)
    assert (new.decision and (new.decision['t'], new.decision['event'])) == waits
    assert new.paused == (waits is not None)
    same(old, new, CHOICES)


def two_guards():
    """The play fixture with two guards, the copies of one template, in the place of its guard."""
    template = play_guard().replace('guard:  @fixture', 'Guard:  @fixture', 1)
    assert template != play_guard()
    return document('Play fixture', PLAY_WORLD, template, 'guards: Guard * 2', horizon=10)


@pytest.mark.parametrize(
    'control, waits',
    [
        # The set of copies, and an event of the set: each copy has the method, and the first waits.
        ({'guards': 'reader'}, (3.0, 'guards_1.first')),
        ({'guards.first': 'reader'}, (3.0, 'guards_1.first')),
        ({'guards.second': 'reader'}, (6.0, 'guards_1.second')),
        # One copy by its own name, and the method of a copy before that of its set.
        ({'guards_2': 'reader'}, (3.0, 'guards_2.first')),
        ({'guards': 'reader', 'guards_1': 'chance'}, (3.0, 'guards_2.first')),
    ],
)
def test_the_method_of_a_set_of_copies_is_that_of_each_copy(tmp_path, control, waits):
    """Two guards are the copies of one template, `guards_1` and `guards_2`. A control names an
    actor or an event by the copy or by the set of the copies; the name of the copy comes first."""
    old, new = both(tmp_path, two_guards(), control, pause_at_decision=True)
    assert new.paused and (new.decision['t'], new.decision['event']) == waits
    same(old, new)


@pytest.mark.parametrize(
    'picks',
    [
        [('guard.first', 'wait')],
        [('guard.first', 'shut'), ('guard.second', 'wait')],
        [('guard.first', 'wait'), ('guard.second', 'shut')],
    ],
)
def test_a_pick_takes_the_place_of_the_chance_of_the_model(tmp_path, picks):
    """The model would have the guard wait (0.3 against 0.7). Each pick of the log answers the next
    decision; the entry of the trace says who picked."""
    log = [{'event': event, 'outcome': outcome} for event, outcome in picks]
    old, new = both(tmp_path, play_scenario(), GUARD, log, pause_at_decision=True)
    assert [
        (entry['rule'], entry['outcome'], entry['picked']) for entry in new.entries if entry['picked']
    ] == [(event, outcome, 'reader') for event, outcome in picks]
    assert new.paused == (len(picks) == 1)
    assert new.end_time == (6.0 if len(picks) == 1 else 10.0)
    for event, outcome in picks:
        assert list(new.final(f'{event}_choice')) == [outcome]
    same(old, new, CHOICES)


@pytest.mark.parametrize(
    'pick',
    [
        {'event': 'guard.second', 'outcome': 'shut'},
        {'event': 'guard.first', 'outcome': 'run'},
    ],
)
def test_a_log_that_answers_another_decision_stops_the_run(tmp_path, pick):
    with pytest.raises(SimulationError, match='the picks belong to another run'):
        played(tmp_path, play_scenario(), GUARD, [pick])
    with pytest.raises(SimulationError, match='the picks belong to another run'):
        both(tmp_path, play_scenario(), GUARD, [pick])


# ---- the pause: the steps before the decision are taken, and no other -----------------------------------

TIMED = ('actor.value', 'actor.chosen', 'actor.later', 'actor.accumulated')


@pytest.mark.parametrize('at', [0, 2, 4])
def test_a_pause_keeps_the_steps_of_its_moment_before_the_decision_and_takes_no_other(tmp_path, at):
    """At the time of the decision an earlier event of the file has written 7, which the actor
    sees; the decision, the event after it in the file and the event one hour later have written
    nothing. The tally of the hours is the time."""
    old, new = both(tmp_path, timed_text(at), READER, pause_at_decision=True)
    assert new.paused and (new.horizon, new.end_time, new.decision['t']) == (4, at, at)
    assert new.decision['view']['value'] == 7
    assert [list(new.final(name)) for name in TIMED[:3]] == [[7.0], [0.0], [0.0]]
    assert list(new.final('actor.accumulated')) == pytest.approx([at])
    same(old, new, TIMED)


@pytest.mark.parametrize('picks', [[], [{'event': 'actor.decide', 'outcome': 'yes'}]])
@pytest.mark.parametrize('pause', [False, True])
def test_an_answered_decision_goes_to_the_horizon(tmp_path, picks, pause):
    old, new = both(tmp_path, timed_text(2), READER, picks, pause_at_decision=pause)
    assert new.paused == (pause and not picks)
    if picks:
        assert list(new.final('actor.chosen')) == [1.0] and list(new.final('actor.later')) == [2.0]
    same(old, new, TIMED)


def test_a_decision_after_a_delay_keeps_its_trigger_and_waits_at_its_firing(tmp_path):
    """The rule triggers at 0 h and fires at 2 h: the run stops at 2 h, with the entry of the trigger
    in its trace and no outcome."""
    old, new = both(tmp_path, timed_text(delayed=True), READER, pause_at_decision=True)
    assert new.paused and new.end_time == 2
    assert [(entry['t'], entry['outcome']) for entry in new.entries if entry['rule'] == 'actor.decide'] == [
        (0.0, None)
    ]
    assert list(new.final('actor.chosen')) == [0.0]
    same(old, new, TIMED)


def test_a_named_decision_stops_the_events_that_its_line_names_after_it(tmp_path):
    """The parent writes 2 and names three events. The first writes 3; the second is the decision,
    which waits; the third, which would write 4, is not taken. With the pick, it is."""
    names = ('actor.value', 'actor.chosen')
    old, new = both(tmp_path, nested_text(), READER, pause_at_decision=True)
    assert new.paused and new.end_time == 1 and new.decision['view']['value'] == 3
    assert [entry['rule'] for entry in new.entries] == ['actor.parent', 'actor.first_child']
    assert [list(new.final(name)) for name in names] == [[3.0], [0.0]]
    same(old, new, names)
    pick = [{'event': 'actor.decide', 'outcome': 'yes'}]
    old, new = both(tmp_path / 'picked', nested_text(), READER, pick, pause_at_decision=True)
    assert not new.paused and [list(new.final(name)) for name in names] == [[4.0], [1.0]]
    same(old, new, names)


# ---- chance and picks together ------------------------------------------------------------------------

RANDOM = ('actor.first', 'actor.second', 'actor.chosen')


@pytest.mark.parametrize('seed', [2, 17, 91])
def test_the_events_that_chance_takes_have_the_luck_of_the_run_that_nobody_plays(tmp_path, seed):
    """Only the named event is a decision of the run. The two events that chance takes draw from the
    streams of their names, so they come out as in the run with no control."""
    luck = {'seed': seed, 'sample': 0}
    events = {'decision_events': {'actor.decide'}}
    free = played(tmp_path / 'free', random_text(), {}, luck=luck)
    old, new = both(tmp_path, random_text(), READER, luck=luck, pause_at_decision=True, **events)
    assert new.paused and (new.decision['event'], new.decision['pick']) == ('actor.decide', 0)
    assert list(new.final('actor.first')) == list(free.run.column('actor.first', 1.0))
    assert list(new.final('actor.second')) == [0.0]
    same(old, new, RANDOM)
    pick = [{'event': 'actor.decide', 'outcome': 'yes'}]
    old, new = both(tmp_path / 'picked', random_text(), READER, pick, luck, pause_at_decision=True, **events)
    assert not new.paused and new.decision is None
    for name in ('actor.first', 'actor.second'):
        assert list(new.final(name)) == list(free.final(name))
    assert [entry['rule'] for entry in new.entries if entry['picked']] == ['actor.decide']
    same(old, new, RANDOM)


def test_an_empty_set_of_decision_events_controls_nothing(tmp_path):
    old, new = both(tmp_path, random_text(), READER, pause_at_decision=True, decision_events=set())
    assert not new.paused and new.decision is None
    same(old, new, RANDOM)


# ---- the independent work of a moment goes before a decision ----------------------------------------------

CASCADE = ('actor.report', 'actor.outcome_report', 'actor.chosen', 'actor.sibling', 'actor.random')


@pytest.mark.parametrize('seed', [3, 17, 40])
def test_the_independent_events_of_a_moment_settle_before_a_decision_waits(tmp_path, seed):
    """At 1 h an event names a line of events with a decision in it, and other events are due. With
    `settled_decisions` the events that no pick decides are taken first (the report is 2, chance has
    taken its event), and the events that the line names after the decision wait behind it (no
    outcome report, no sibling report)."""
    luck = {'seed': seed, 'sample': 0}
    old, new = both(tmp_path, cascade_text(), READER, luck=luck, pause_at_decision=True, **SETTLED)
    assert new.paused and (new.decision['t'], new.decision['event']) == (1.0, 'actor.decide')
    assert list(new.final('actor.report')) == [2.0] and list(new.final('actor.random')) != [0.0]
    assert [list(new.final(name)) for name in CASCADE[1:4]] == [[0.0], [0.0], [0.0]]
    same(old, new, CASCADE)


@pytest.mark.parametrize('seed', [3, 17, 40])
@pytest.mark.parametrize('first', ['yes', 'no'])
@pytest.mark.parametrize('second', [None, 'yes', 'no'])
def test_each_pick_of_a_log_goes_on_from_the_same_run(tmp_path, seed, first, second):
    """With the first pick the run goes to the next decision of the same moment, and with both to
    the horizon; the steps before a decision are the same whatever the picks after it."""
    luck = {'seed': seed, 'sample': 0}
    picks = [{'event': 'actor.decide', 'outcome': first}]
    if second:
        picks.append({'event': 'actor.next_choice', 'outcome': second})
    old, new = both(tmp_path, cascade_text(), READER, picks, luck, pause_at_decision=True, **SETTLED)
    assert new.paused == (second is None)
    assert list(new.final('actor.outcome_report')) == [1.0 if first == 'yes' else 2.0]
    assert list(new.final('actor.sibling')) == [1.0]
    if second:
        assert list(new.final('actor.chosen')) == [3.0 if second == 'yes' else 4.0]
    else:
        assert (new.decision['event'], new.decision['pick']) == ('actor.next_choice', 1)
    same(old, new, CASCADE)
    before = played(tmp_path / 'before', cascade_text(), READER, luck=luck, pause_at_decision=True, **SETTLED)
    assert new.entries[: len(before.entries)] == before.entries


# ---- a resolver answers a decision at its boundary -----------------------------------------------------


def test_a_resolver_answers_at_the_boundary_and_a_declined_decision_waits(tmp_path):
    """The resolver gets the decision with the place of its pick, the values at the boundary and the
    trace so far. Its answer is the pick; with None the run stops there."""
    luck = {'seed': 17, 'sample': 0}
    asked = []

    def resolver(decision, env, trace):
        asked.append((decision['event'], decision['pick_index'], env['actor.report'], len(trace)))
        return {'event': decision['event'], 'outcome': 'yes'} if decision['event'] == 'actor.decide' else None

    options = {'pause_at_decision': True, 'decision_resolver': resolver, **SETTLED}
    new = played(tmp_path, cascade_text(), READER, luck=luck, **options)
    first = list(asked)
    assert [item[:2] for item in first] == [('actor.decide', 0), ('actor.next_choice', 1)]
    assert first[0][2] == 2.0
    assert new.paused and new.decision['event'] == 'actor.next_choice'
    model = compiled(cascade_text())
    resolved = replace(model.resolve('a'), luck=luck)
    asked.clear()
    old = simulate(resolved, model.library, play={'control': READER}, **options)
    assert asked == first
    same(old, new, CASCADE)
    # The pick that the resolver gave is the pick of a log.
    logged = played(
        tmp_path / 'logged',
        cascade_text(),
        READER,
        [{'event': 'actor.decide', 'outcome': 'yes'}],
        luck,
        pause_at_decision=True,
        **SETTLED,
    )
    assert logged.entries == new.entries and logged.decision == new.decision


def test_a_resolver_needs_the_pause_and_a_mapping(tmp_path):
    with pytest.raises(ValueError, match='requires pause_at_decision'):
        played(tmp_path, timed_text(2), READER, decision_resolver=lambda *_: None)
    with pytest.raises(SimulationError, match='must return a pick mapping or None'):
        played(tmp_path, timed_text(2), READER, pause_at_decision=True, decision_resolver=lambda *_: 'yes')
