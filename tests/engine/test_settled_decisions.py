"""Opt-in windows settle independent present work, never an unanswered consequence."""

from dataclasses import replace

import pytest

from napkin.engine.runtime import simulate
from tests.build import block, compiled, document, entity
from tests.engine.test_pause import nested_model, played, timed_model


@pytest.mark.parametrize('at', [0, 2, 4])
def test_settled_window_receives_later_same_time_report_but_not_future(at):
    model = timed_model(at)
    ordinary = played(model, pause_at_decision=True)
    settled = played(model, pause_at_decision=True, settled_decisions=True)
    assert ordinary.env_at(at)['actor.later'] == 0
    assert settled.paused and settled.end_time == at
    state = settled.env_at(at)
    assert state['actor.later'] == 1
    assert state['actor.chosen'] == state['actor.decide__count'] == 0
    assert not any(row['rule'] == 'actor.future' for row in settled.trace)


def test_delayed_control_trigger_is_bookkeeping_but_its_outcome_waits():
    model = timed_model(delayed=True)
    result = played(model, pause_at_decision=True, settled_decisions=True)
    assert result.end_time == 2
    state = result.env_at(2)
    assert state['actor.decide__count'] == 1
    assert state['actor.chosen'] == 0
    assert state['actor.later'] == 1


def test_nested_control_preserves_parent_and_earlier_siblings_without_later_sibling():
    result = played(nested_model(), pause_at_decision=True, settled_decisions=True)
    assert result.paused and result.end_time == 1
    assert result.env_at(1)['actor.value'] == 3
    assert result.env_at(1)['actor.chosen'] == 0
    assert [row['rule'] for row in result.trace if row['rule'].startswith('actor.')] == [
        'actor.parent',
        'actor.first_child',
    ]
    completed = played(
        nested_model(),
        [{'event': 'actor.decide', 'outcome': 'yes'}],
        pause_at_decision=True,
        settled_decisions=True,
    )
    assert not completed.paused
    assert completed.env_at(2)['actor.value'] == 4


def cascade_model():
    return compiled(cascade_text())


def cascade_text():
    return document(
        'Causal decision windows',
        entity(
            'actor',
            'sees report, outcome_report, chosen, sibling, random',
            'var report: fraction = 0  @fixture',
            'var outcome_report: fraction = 0  @fixture',
            'var chosen: fraction = 0  @fixture',
            'var sibling: fraction = 0  @fixture',
            'var random: fraction = 0  @fixture',
            block('event outer once when t >= 1 h:  @fixture', 'middle', 'sibling_report'),
            block('event middle:  @fixture', 'decide', 'dependent'),
            block(
                'event decide:  @fixture',
                'choice',
                block('yes 0.5:', 'chosen = 1'),
                block('no else:', 'chosen = 2'),
            ),
            block('event dependent:  @fixture', 'outcome_report = chosen'),
            block('event sibling_report:  @fixture', 'sibling = 1'),
            block('event independent once when t >= 1 h:  @fixture', 'report = 2'),
            block(
                'event cascade once when report > 0:  @fixture',
                block('heads 0.5:', 'random = 1'),
                block('tails else:', 'random = 2'),
            ),
            block('event after_choice once when chosen > 0:  @fixture', 'report = 3'),
            block(
                'event next_choice once when chosen > 0:  @fixture',
                'choice',
                block('yes 0.5:', 'chosen = 3'),
                block('no else:', 'chosen = 4'),
            ),
            role='operator',
        ),
        horizon=2,
    )


def run_cascade(picks=(), *, seed=17, pause=True, model=None):
    model = model or cascade_model()
    resolved = replace(model.resolve('a'), luck={'seed': seed, 'sample': 0})
    return simulate(
        resolved,
        model.library,
        play={'control': {'actor': 'reader'}, 'picks': list(picks)},
        settled_decisions=True,
        pause_at_decision=pause,
        decision_events={'actor.decide', 'actor.next_choice'},
    )


def test_independent_cascades_settle_but_nested_dependent_work_stays_behind_choice():
    first = run_cascade()
    state = first.env_at(1)
    assert state['actor.report'] == 2
    assert state['actor.random'] in (1, 2)
    assert state['actor.outcome_report'] == state['actor.sibling'] == state['actor.chosen'] == 0
    assert first.decision['event'] == 'actor.decide'
    second = run_cascade([{'event': 'actor.decide', 'outcome': 'yes'}])
    assert second.decision['event'] == 'actor.next_choice'
    state = second.env_at(1)
    assert state['actor.report'] == 3
    assert state['actor.sibling'] == state['actor.outcome_report'] == 1


def test_a_decision_that_a_line_names_and_that_is_also_due_by_its_own_condition_is_taken_once():
    """The decision has a condition of its own that holds at the time at which the line of `middle`
    names it. It is one decision of that moment: it is taken as the line named it, so the rest of
    the line (`dependent`, then the sibling of `middle`) comes after it, and the next decision that
    waits is the other one."""
    text = cascade_text().replace('event decide:  @fixture', 'event decide when t >= 1 h:  @fixture')
    assert text != cascade_text()
    model = compiled(text)
    first = run_cascade(model=model)
    assert first.decision['event'] == 'actor.decide'
    second = run_cascade([{'event': 'actor.decide', 'outcome': 'yes'}], model=model)
    rules = [row['rule'] for row in second.trace]
    assert rules.count('actor.decide') == 1
    at = rules.index('actor.decide')
    assert rules[at + 1 : at + 3] == ['actor.dependent', 'actor.sibling_report']
    assert second.paused and second.decision['event'] == 'actor.next_choice'
    assert second.env_at(1)['actor.outcome_report'] == second.env_at(1)['actor.chosen'] == 1


@pytest.mark.parametrize('seed', [2, 17, 91])
def test_seeded_prefix_replay_matches_full_answered_settled_execution(seed):
    picks = [{'event': 'actor.decide', 'outcome': 'yes'}, {'event': 'actor.next_choice', 'outcome': 'no'}]
    prefix = run_cascade(picks[:1], seed=seed)
    resumed = run_cascade(picks, seed=seed)
    full = run_cascade(picks, seed=seed, pause=False)
    assert resumed.trace == full.trace
    assert resumed.env_at(2) == full.env_at(2)
    assert prefix.env_at(1)['actor.random'] == full.env_at(2)['actor.random']


def test_a_second_line_that_names_a_decision_that_happens_once_does_not_hide_the_lines_after_it():
    """The decision happens once in a run. The line of `middle` names it, and the line of `outer`
    names it again before the sibling of `middle`. After the pick, the second naming has nothing
    left to do: it is dropped, and the sibling after it still happens, once."""
    text = (
        cascade_text()
        .replace('event decide:  @fixture', 'event decide once:  @fixture')
        .replace(
            block('event outer once when t >= 1 h:  @fixture', 'middle', 'sibling_report'),
            block('event outer once when t >= 1 h:  @fixture', 'middle', 'decide', 'sibling_report'),
        )
    )
    assert text.count('once') == cascade_text().count('once') + 1 and 'decide\n' in text
    model = compiled(text)
    assert run_cascade(model=model).decision['event'] == 'actor.decide'
    answered = run_cascade([{'event': 'actor.decide', 'outcome': 'yes'}], model=model)
    rules = [row['rule'] for row in answered.trace]
    assert rules.count('actor.decide') == 1 and rules.count('actor.sibling_report') == 1
    assert rules.index('actor.decide') < rules.index('actor.dependent') < rules.index('actor.sibling_report')
    assert answered.paused and answered.decision['event'] == 'actor.next_choice'
