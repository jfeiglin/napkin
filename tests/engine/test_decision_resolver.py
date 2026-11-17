"""Resolved choices preserve the same exact boundaries and physical replay as saved picks."""

from dataclasses import replace

import pytest

from napkin.engine.errors import SimulationError
from napkin.engine.runtime import simulate
from napkin.model.structure import Resolved
from tests.build import compiled
from tests.engine.test_pause import played, timed_model
from tests.engine.test_settled_decisions import cascade_model, cascade_text


def cascade(picks=(), resolver=None, seed=17, model=None):
    model = model or cascade_model()
    resolved = replace(model.resolve('a'), luck={'seed': seed, 'sample': 0})
    return simulate(
        resolved,
        model.library,
        play={'control': {'actor': 'reader'}, 'picks': list(picks)},
        pause_at_decision=True,
        settled_decisions=True,
        decision_events={'actor.decide', 'actor.next_choice'},
        decision_resolver=resolver,
    )


def test_declined_resolution_pauses_before_outcome_with_read_only_boundary():
    captured = []

    def resolve(decision, env, trace):
        assert decision['pick_index'] == decision['pick'] == 0
        assert env['actor.report'] == 2
        assert env['actor.chosen'] == env['actor.outcome_report'] == env['actor.sibling'] == 0
        with pytest.raises(TypeError):
            env['actor.chosen'] = 9
        with pytest.raises(TypeError):
            trace[0]['rule'] = 'changed'
        captured.append(decision)
        return None

    result = cascade(resolver=resolve)
    assert result.paused and result.end_time == 1
    assert len(captured) == 1
    assert result.decision['event'] == 'actor.decide'
    assert result.env_at(1)['actor.chosen'] == 0
    assert not any(row['rule'] == 'actor.decide' for row in result.trace)


def test_a_resolver_reads_the_formulas_of_the_model_and_every_name_of_the_boundary():
    """At the first decision the report is 2 (the independent event of that time set it), so a
    formula of twice the report is 4. The values that a resolver gets are a mapping: it can be
    read by name, asked for a name, and copied whole, and the copy has the formula too."""
    text = cascade_text().replace(
        '    var random: fraction = 0  @fixture\n',
        '    var random: fraction = 0  @fixture\n    let twice: fraction = report * 2  @fixture\n',
    )
    assert text != cascade_text()
    seen = []

    def resolve(decision, env, trace):
        whole = dict(env)
        seen.append(
            (env['actor.twice'], 'actor.twice' in env, 'actor.nothing' in env, len(env) == len(whole))
        )
        assert whole['actor.twice'] == 2 * whole['actor.report'] and whole['t'] == decision['t']
        assert whole['actor.decide__count'] == 0 and whole['actor.independent__count'] == 1
        with pytest.raises(KeyError):
            env['actor.nothing']
        return None

    result = cascade(resolver=resolve, model=compiled(text))
    assert result.paused and seen == [(4, True, False, True)]


@pytest.mark.parametrize('seed', [2, 17])
def test_multiple_resolutions_match_seeded_saved_replay_without_restarting(seed):
    durable = []

    def resolve(decision, env, trace):
        ordinal = decision['pick_index']
        assert ordinal == len(durable)
        if ordinal == 0:
            assert env['actor.report'] == 2 and env['actor.outcome_report'] == 0
        else:
            assert env['actor.report'] == 3 and env['actor.outcome_report'] == 1
        pick = {'event': decision['event'], 'outcome': ('yes', 'no')[ordinal]}
        durable.append(pick)
        return pick

    live = cascade(resolver=resolve, seed=seed)
    replay = cascade(durable, seed=seed)
    assert len(durable) == 2
    assert not live.paused and live.decision is None
    assert live.trace == replay.trace
    assert live.env_at(2) == replay.env_at(2)


def test_saved_prefix_bypasses_resolver_and_next_unanswered_decision_can_pause():
    calls = []

    def resolve(decision, env, trace):
        calls.append((decision['event'], decision['pick_index']))
        return None

    result = cascade([{'event': 'actor.decide', 'outcome': 'yes'}], resolver=resolve)
    assert calls == [('actor.next_choice', 1)]
    assert result.paused and result.decision['event'] == 'actor.next_choice'
    assert result.env_at(1)['actor.chosen'] == 1


@pytest.mark.parametrize(
    'answer',
    [42, {'event': 'other.decide', 'outcome': 'yes'}, {'event': 'actor.decide', 'outcome': 'missing'}],
)
def test_invalid_resolution_is_rejected_without_a_fallback(answer):
    with pytest.raises(SimulationError):
        played(timed_model(), pause_at_decision=True, decision_resolver=lambda *args: answer)


def test_unavailable_resolution_is_rejected():
    model = timed_model()
    resolved = model.resolve('a').plain()
    # `yes` cannot happen now: no chance, and its condition fails.
    resolved['rules']['actor.decide']['outcomes'][0]['chance'] = '0'
    resolved['rules']['actor.decide']['outcomes'][0]['available'] = 'False'
    with pytest.raises(SimulationError, match='cannot happen'):
        simulate(
            Resolved.of(resolved),
            model.library,
            play={'control': {'actor': 'reader'}},
            pause_at_decision=True,
            decision_resolver=lambda *args: {'event': 'actor.decide', 'outcome': 'yes'},
        )


def test_failed_durable_save_propagates_before_any_chosen_outcome():
    captured = []

    def fail(decision, env, trace):
        captured.append(env['actor.chosen'])
        raise OSError('durable save failed')

    with pytest.raises(OSError, match='durable save failed'):
        played(timed_model(), pause_at_decision=True, decision_resolver=fail)
    assert captured == [0]


def test_resolver_requires_pause_mode_and_a_callable():
    model = timed_model()
    with pytest.raises(ValueError, match='requires pause_at_decision'):
        played(model, decision_resolver=lambda *args: None)
    with pytest.raises(ValueError, match='callable'):
        played(model, pause_at_decision=True, decision_resolver=42)
