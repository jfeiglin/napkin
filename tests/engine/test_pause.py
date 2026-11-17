"""A true decision boundary retains past steps and never simulates the unanswered future."""

import pickle
from dataclasses import replace

import pytest

from napkin.engine.runtime import simulate
from tests.build import block, compiled, document, entity


def timed_model(at=2, *, delayed=False):
    return compiled(timed_text(at, delayed=delayed))


def timed_text(at=2, *, delayed=False):
    event = (
        'event decide once after 2 h when t >= 0 h:' if delayed else f'event decide once when t >= {at} h:'
    )
    return document(
        'Decision boundary',
        entity(
            'actor',
            'sees value, chosen, later, accumulated',
            'var value: fraction = 0  @fixture',
            'var chosen: fraction = 0  @fixture',
            'var later: fraction = 0  @fixture',
            'var accumulated: h = 0 h size 4 h  @fixture',
            'flow accumulate: -> accumulated at 1  @fixture',
            block(f'event prior once when t >= {at} h:  @fixture', 'value = 7'),
            block(
                event + '  @fixture',
                'choice',
                block('yes 0.4:', 'chosen = 1'),
                block('no else:', 'chosen = 2'),
            ),
            block(f'event following once when t >= {at} h:  @fixture', 'later = 1'),
            block(f'event future once when t >= {at + 1} h:  @fixture', 'later = 2'),
            role='operator',
        ),
        horizon=4,
    )


def played(model, picks=(), **kwargs):
    play = {'control': {'actor': 'reader'}, 'picks': list(picks)}
    return simulate(model.resolve('a'), model.library, play=play, **kwargs)


@pytest.mark.parametrize('at', [0, 2, 4])
def test_pause_preserves_prior_same_time_changes_without_committing_decision(at):
    model = timed_model(at)
    trajectory = played(model, pause_at_decision=True)
    assert trajectory.paused
    assert trajectory.horizon == 4
    assert trajectory.end_time == at
    assert trajectory.decision['t'] == at
    assert trajectory.decision['view']['value'] == 7
    state = trajectory.env_at(at)
    assert state['actor.value'] == 7
    assert state['actor.chosen'] == state['actor.later'] == 0
    assert state['actor.accumulated'] == pytest.approx(at)
    assert state['actor.decide__count'] == 0
    assert not any(
        row['rule'] in {'actor.decide', 'actor.following', 'actor.future'} for row in trajectory.trace
    )
    assert all(segment.end <= at for segment in trajectory._segments)
    assert len(trajectory.trace) == len(trajectory._steps)
    with pytest.raises(ValueError, match='outside'):
        trajectory.env_at(at + 0.001)
    restored = pickle.loads(pickle.dumps(trajectory))
    assert restored.paused and restored.end_time == at
    assert restored.env_at(at)['actor.value'] == 7


def test_default_preview_is_unchanged_and_answered_pause_run_reaches_original_horizon():
    model = timed_model()
    preview = played(model)
    assert not preview.paused and preview.end_time == preview.horizon == 4
    assert preview.decision['event'] == 'actor.decide'
    assert preview.env_at(4)['actor.chosen'] == 2
    assert preview.env_at(4)['actor.later'] == 2
    answer = [{'event': 'actor.decide', 'outcome': 'yes'}]
    finished = played(model, answer, pause_at_decision=True)
    ordinary = played(model, answer)
    assert not finished.paused and finished.decision is None
    assert finished.end_time == 4
    assert finished.trace == ordinary.trace
    assert finished.env_at(4) == ordinary.env_at(4)


def test_a_delayed_decision_retains_its_past_trigger_but_not_an_unanswered_outcome():
    trajectory = played(timed_model(delayed=True), pause_at_decision=True)
    assert trajectory.end_time == 2
    trace = [row for row in trajectory.trace if row['rule'] == 'actor.decide']
    assert [(row['t'], row['outcome']) for row in trace] == [(0, None)]
    assert trajectory.env_at(2)['actor.decide__count'] == 1
    assert trajectory.env_at(2)['actor.chosen'] == 0


def nested_model():
    return compiled(nested_text())


def nested_text():
    return document(
        'Nested decision boundary',
        entity(
            'actor',
            'sees value, chosen',
            'var value: fraction = 0  @fixture',
            'var chosen: fraction = 0  @fixture',
            block(
                'event parent once when t >= 1 h:  @fixture',
                'value = 2',
                'first_child',
                'decide',
                'last_child',
            ),
            block('event first_child:  @fixture', 'value = 3'),
            block(
                'event decide:  @fixture',
                'choice',
                block('yes 0.5:', 'chosen = 1'),
                block('no else:', 'chosen = 2'),
            ),
            block('event last_child:  @fixture', 'value = 4'),
            role='operator',
        ),
        horizon=2,
    )


def test_nested_pause_retains_parent_and_sibling_commits_and_stops_remaining_fires():
    model = nested_model()
    trajectory = played(model, pause_at_decision=True)
    assert trajectory.end_time == 1
    assert trajectory.decision['view']['value'] == 3
    assert trajectory.env_at(1)['actor.value'] == 3
    assert trajectory.env_at(1, side='left')['actor.value'] == 0
    assert trajectory.env_at(1)['actor.chosen'] == 0
    assert [row['rule'] for row in trajectory.trace if row['rule'].startswith('actor.')] == [
        'actor.parent',
        'actor.first_child',
    ]
    assert trajectory.env_after_step(trajectory.layers[-1])['actor.value'] == 3
    finished = played(model, [{'event': 'actor.decide', 'outcome': 'yes'}], pause_at_decision=True)
    assert not finished.paused and finished.env_at(2)['actor.value'] == 4
    assert finished.env_at(2)['actor.chosen'] == 1


def random_model():
    return compiled(random_text())


def random_text():
    return document(
        'Seeded policy and strategic decisions',
        entity(
            'actor',
            'sees first, second, chosen',
            'var first: fraction = 0  @fixture',
            'var second: fraction = 0  @fixture',
            'var chosen: fraction = 0  @fixture',
            block(
                'event bookkeeping once when t >= 0 h:  @fixture',
                block('heads 0.5:', 'first = 1'),
                block('tails else:', 'first = 2'),
            ),
            block(
                'event decide once when t >= 1 h:  @fixture',
                'choice',
                block('yes 0.4:', 'chosen = 1'),
                block('no else:', 'chosen = 2'),
            ),
            block(
                'event later_bookkeeping once when t >= 2 h:  @fixture',
                block('heads 0.5:', 'second = 1'),
                block('tails else:', 'second = 2'),
            ),
            role='operator',
        ),
        horizon=3,
    )


@pytest.mark.parametrize('seed', [2, 17, 91])
def test_event_filter_skips_bookkeeping_without_changing_seeded_replay(seed):
    model = random_model()
    resolved = replace(model.resolve('a'), luck={'seed': seed, 'sample': 0})
    unplayed = simulate(resolved, model.library)
    play = {'control': {'actor': 'reader'}}
    asked = {'play': play, 'pause_at_decision': True, 'decision_events': {'actor.decide'}}
    partial = simulate(resolved, model.library, **asked)
    assert partial.paused and partial.decision['event'] == 'actor.decide'
    assert partial.decision['pick'] == 0
    assert partial.env_at(1)['actor.first'] == unplayed.env_at(1)['actor.first']
    assert partial.env_at(1)['actor.second'] == 0
    asked['play'] = {**play, 'picks': [{'event': 'actor.decide', 'outcome': 'yes'}]}
    finished = simulate(resolved, model.library, **asked)
    again = simulate(resolved, model.library, **asked)
    assert not finished.paused and finished.decision is None
    assert finished.trace == again.trace
    for field in ('first', 'second'):
        assert finished.env_at(3)[f'actor.{field}'] == unplayed.env_at(3)[f'actor.{field}']
    assert [row['rule'] for row in finished.trace if row['picked']] == ['actor.decide']


def test_empty_event_filter_controls_nothing():
    trajectory = played(random_model(), pause_at_decision=True, decision_events=set())
    assert not trajectory.paused and trajectory.decision is None
    assert trajectory.end_time == 3
