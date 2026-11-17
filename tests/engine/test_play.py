"""Play (docs/engine.md, "Play"): in a played run the decisions of the controlled actors take
the picks of a log; the first decision without a pick shows what its actor sees. A reader who plays
the run one decision at a time is a `napkin.session.Session` (tests/test_session.py)."""

from __future__ import annotations

import pytest

from napkin.engine.study import evaluate_study
from tests.build import compiled, play_scenario


def model(**chances):
    return compiled(play_scenario(**chances))


CONTROL = {'guard': 'reader'}


def played(m, picks):
    return evaluate_study(m, play={'run': 'a', 'control': CONTROL, 'picks': picks})


def test_the_view_holds_exactly_what_the_actor_sees():
    study = played(model(), [])
    assert study.admissible, study.diagnostics
    decision = study.decision
    assert (decision['t'], decision['event']) == (3.0, 'guard.first')
    assert set(decision['view']) == {'world.alarm', 'world.level', 'world.delay', 'world.ring', 'world.late'}
    # The level rises at 0.1 an hour from 0: 0.3 at 3 h. The delay shows in its own unit, days.
    assert decision['view']['world.alarm'] == 'on'
    assert decision['view']['world.level'] == pytest.approx(0.1 * 3, rel=1e-9)
    assert decision['view']['world.delay'] == pytest.approx(2)
    assert decision['units']['world.delay'] == 'days'
    # A seen event counts the times it has happened; `seen` lists only seen events that have happened:
    # the ring, not the hum (unseen) nor the late event (after 3 h).
    assert (decision['view']['world.ring'], decision['view']['world.late']) == (1, 0)
    assert [(item['t'], item['event']) for item in decision['seen']] == [(1.0, 'world.ring.done')]
    assert [(item['name'], item['available']) for item in decision['outcomes']] == [
        ('shut', True),
        ('wait', True),
    ]


def waiting(m, control):
    """(time, event) of the first decision that waits for a pick under `control`, or the codes of the
    diagnostics that refuse the request."""
    study = evaluate_study(m, play={'run': 'a', 'control': control, 'picks': []})
    if not study.admissible:
        return [d['code'] for d in study.diagnostics if d.get('severity', 'error') == 'error']
    return study.decision and (study.decision['t'], study.decision['event'])


def test_a_run_gives_each_event_its_method_and_chance_takes_the_rest():
    m = model()
    # One event: the first decision is taken by chance, and the second waits for the reader.
    assert waiting(m, {'guard.second': 'reader'}) == (6.0, 'guard.second')
    # An event's method comes before its actor's.
    assert waiting(m, {'guard': 'reader', 'guard.first': 'chance'}) == (6.0, 'guard.second')
    assert waiting(m, {'guard': 'agent', 'guard.second': 'chance'}) == (3.0, 'guard.first')
    # Chance for every event: nothing waits.
    assert waiting(m, {'guard': 'chance'}) is None


def test_a_run_names_actors_or_their_events_with_a_method():
    m = model()
    assert waiting(m, {'guard.nothing': 'reader'}) == ['play']
    assert waiting(m, {'world': 'reader'}) == ['play']
    assert waiting(m, {'guard': 'oracle'}) == ['play']


def test_a_pick_replaces_the_model_estimate_but_not_a_condition():
    # `shut 1` leaves `wait` no chance, but a chance is the model's estimate: the reader may still wait.
    study = played(model(shut='1'), [{'event': 'guard.first', 'outcome': 'wait'}])
    assert study.admissible, study.diagnostics
    assert study.runs['a']['trajectory'].env_at(4)['guard.first_choice'] == 'wait'
    # A chance that is a condition is an estimate too: it does not say when an outcome can happen.
    estimate = model(shut='world.alarm is "on"')
    assert [item['available'] for item in played(estimate, []).decision['outcomes']] == [True, True]
    # `when` says when an outcome can happen: with the alarm on, `wait` cannot.
    m = model(shut='world.alarm is "on"', wait='else when world.alarm is "off"')
    assert [item['available'] for item in played(m, []).decision['outcomes']] == [True, False]
    refused = played(m, [{'event': 'guard.first', 'outcome': 'wait'}])
    assert not refused.admissible
    assert [d['code'] for d in refused.diagnostics if d.get('severity', 'error') == 'error'] == ['pick']


def test_a_log_that_answers_another_decision_is_refused():
    refused = played(model(), [{'event': 'guard.second', 'outcome': 'shut'}])
    assert not refused.admissible
    assert [d['code'] for d in refused.diagnostics if d.get('severity', 'error') == 'error'] == ['pick']


def test_only_an_actor_can_be_played():
    refused = evaluate_study(model(), play={'run': 'a', 'control': {'world': 'reader'}, 'picks': []})
    assert not refused.admissible
    assert {d['code'] for d in refused.diagnostics} == {'play'}
