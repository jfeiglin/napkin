"""The condition under which an outcome can happen (`name chance when C:`; docs/language.md §2.8).

A chance is the model's estimate, which a pick replaces; `when` says whether the outcome can happen at
all. An outcome that cannot happen is never taken, by the central run, a sample or a pick, and it may
have no chance then."""

from __future__ import annotations

import pytest

from napkin.engine import SamplingSettings, evaluate_study, evaluate_uncertainty
from napkin.model.ir import ModelError
from tests.build import compiled, play_scenario

CONTROL = {'guard': 'reader'}


def model(**chances):
    return compiled(play_scenario(**chances))


def played(m, picks):
    return evaluate_study(m, play={'run': 'a', 'control': CONTROL, 'picks': picks})


def errors(study):
    return [d['code'] for d in study.diagnostics if d.get('severity', 'error') == 'error']


def test_an_outcome_is_available_exactly_while_its_condition_holds():
    # The alarm turns on at 1 h; the first decision is at 3 h. `shut` can happen only while it is off.
    m = model(shut='0 when world.alarm is "off"', wait='else')
    decision = played(m, []).decision
    assert [(item['name'], item['available']) for item in decision['outcomes']] == [
        ('shut', False),
        ('wait', True),
    ]


def test_a_pick_of_an_outcome_that_cannot_happen_is_refused():
    m = model(shut='0 when world.alarm is "off"', wait='else')
    refused = played(m, [{'event': 'guard.first', 'outcome': 'shut'}])
    assert not refused.admissible
    assert errors(refused) == ['pick']
    accepted = played(m, [{'event': 'guard.first', 'outcome': 'wait'}])
    assert accepted.admissible, accepted.diagnostics


def test_an_outcome_that_cannot_happen_may_have_no_chance():
    # The model's estimate gives `shut` a chance while the condition rules it out: the run stops.
    stopped = evaluate_study(model(shut='0.3 when world.alarm is "off"', wait='else'))
    assert not stopped.admissible
    assert 'chances' in errors(stopped)


def test_the_else_outcome_is_checked_like_any_other():
    stopped = evaluate_study(model(shut='0.3', wait='else when world.alarm is "off"'))
    assert not stopped.admissible
    assert 'chances' in errors(stopped)


def test_central_and_sampled_runs_take_only_available_outcomes():
    m = model(shut='0 when world.alarm is "off"', wait='else')
    central = evaluate_study(m)
    assert central.admissible, central.diagnostics
    assert central.runs['a']['trajectory'].env_at(4)['guard.first_choice'] == 'wait'
    sampled = evaluate_uncertainty(m, settings=SamplingSettings(12, 3), runs=['a'])
    assert sampled.admissible, sampled.diagnostics


def test_a_choice_whose_condition_reads_what_the_actor_does_not_see_is_refused():
    # The guard does not see the hum: neither of its two choices can depend on it.
    with pytest.raises(ModelError) as raised:
        model(shut='0 when count(world.hum) > 0', wait='else')
    assert [d['code'] for d in raised.value.diagnostics] == ['sight', 'sight']


def test_the_condition_is_a_yes_or_no_value():
    with pytest.raises(ModelError) as raised:
        model(shut='0 when world.level', wait='else')
    assert raised.value.diagnostics


def test_an_event_with_one_outcome_says_no_condition():
    from tests.build import block, document, entity, quote

    world = entity(
        'world',
        block('event ring once when t >= 1 h:  @fixture', block('done when t > 0 h:', quote('Rings.'))),
    )
    with pytest.raises(ModelError) as raised:
        compiled(document('One outcome', world, horizon=2))
    assert raised.value.diagnostics
