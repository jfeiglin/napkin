"""A played run, one decision at a time (`napkin/session.py`), and `napkin play` on the reservoir example.

There are three ways to give the picks of a played run: live, with a resolver, in one simulation; step
by step, with `advance()` and `pick()`, which simulates the run again from t = 0 for each pick; and
`evaluate_study(…, play=…)` with the log. They give one run, bit for bit. The fixtures are the guard of
`tests/build.py` (two decisions), the decision boundaries of `tests/engine/test_pause.py` (a decision
beside other steps of its moment, a delayed decision, a decision inside a chain of events) and the
reservoir example, whose names the tests read from the model.
"""

from __future__ import annotations

import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from napkin import session as session_module
from napkin.commands import common
from napkin.commands import play as play_command
from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.model import ModelError, load_scenario
from napkin.model.views import actors
from napkin.session import CONTEXT, OtherContext, Session
from napkin.store import fingerprint
from tests.build import (
    DEFAULT_OPTIONS,
    PLAY_WORLD,
    compiled,
    document,
    option,
    options,
    play_guard,
    play_scenario,
    runs,
)
from tests.engine.test_pause import nested_model, timed_model

ROOT = Path(__file__).resolve().parents[1]
RESERVOIR = ROOT / 'examples' / 'reservoir'
CONTROL = {'guard': 'reader'}
# The delay of the world's alarm under the option `Slow alarm`, in days (the fixture's own value).
SLOW = 3


def guard_model(**chances):
    return compiled(play_scenario(**chances))


def optioned_model():
    """The guard with a second group of options: `Slow alarm` sets the delay. Run `b` takes it, run `a`
    does not."""
    groups = (
        DEFAULT_OPTIONS,
        options('Alarm', option('Slow alarm', 'A slower alarm.', f'world.delay = {SLOW} days  @fixture')),
    )
    text = document(
        'Play fixture',
        PLAY_WORLD,
        play_guard(),
        horizon=10,
        option_groups=groups,
        run_lines=runs(a=['Default'], b=['Default', 'Slow alarm']),
    )
    return compiled(text)


# The guard's decision `first` has an outcome that cannot happen: with the alarm on, it cannot wait.
WHEN = {'shut': 'world.alarm is "on"', 'wait': 'else when world.alarm is "off"'}


def available(decision):
    return [item['name'] for item in decision['outcomes'] if item['available']]


# How a scripted reader picks, by the decision alone.
POLICIES = {
    'first': lambda decision: available(decision)[0],
    'last': lambda decision: available(decision)[-1],
    'by turns': lambda decision: available(decision)[decision['pick'] % len(available(decision))],
}


@pytest.fixture(scope='module')
def reservoir():
    """(the model of the reservoir, checked for its only run as `napkin play` checks it; the run; the
    control of its actor)."""
    entry = RESERVOIR / 'model.scn'
    (run,) = load_scenario(entry).runs
    model = load_scenario(entry, admission_runs=[run])
    (actor,) = actors(model)
    return model, run, {actor['name']: 'reader'}


def cases(reservoir):
    """{name: (model, run, control)} of the played runs of the fixtures."""
    return {
        'guard': (guard_model(), 'a', CONTROL),
        'one event of the guard': (guard_model(), 'a', {'guard.second': 'reader'}),
        'a decision beside its moment': (timed_model(), 'a', {'actor': 'reader'}),
        'a delayed decision': (timed_model(delayed=True), 'a', {'actor': 'reader'}),
        'a decision in a chain': (nested_model(), 'a', {'actor': 'reader'}),
        'the reservoir': reservoir,
    }


CASES = (
    'guard',
    'one event of the guard',
    'a decision beside its moment',
    'a delayed decision',
    'a decision in a chain',
    'the reservoir',
)


def live_session(model, run, control, policy, **kwargs):
    return Session(
        model, run, control=control, resolver=lambda decision: (policy(decision), 'live'), **kwargs
    )


def story(trajectory):
    """Each step's time, event and changes, and the state at each of 11 times: the run without its log."""
    steps = [(entry['t'], entry['event'], entry['changes']) for entry in trajectory.trace]
    end = trajectory.end_time
    states = [
        {name: value for name, value in trajectory.env_at(end * k / 10).items() if not callable(value)}
        for k in range(11)
    ]
    return steps, states


def unmarked(run):
    """A run of a report without the marks of its picks: its trace entries without `picked`."""
    return {
        **run,
        'trace': [{key: value for key, value in entry.items() if key != 'picked'} for entry in run['trace']],
    }


# --- One run, three ways ------------------------------------------------------------------------


@pytest.mark.parametrize('policy', POLICIES)
@pytest.mark.parametrize('case', CASES)
def test_the_live_path_the_step_path_and_the_study_give_one_run(reservoir, case, policy, monkeypatch):
    model, run, control = cases(reservoir)[case]
    choose = POLICIES[policy]
    calls = []
    engine = session_module.simulate
    monkeypatch.setattr(
        session_module, 'simulate', lambda *args, **kwargs: calls.append(1) or engine(*args, **kwargs)
    )
    live = live_session(model, run, control, choose)
    assert live.advance() is None and live.decision is None
    # The live path simulates the run once, however many decisions it has.
    assert len(calls) == 1 and live.picks
    step = Session(model, run, control=control)
    while (decision := step.advance()) is not None:
        assert step.trajectory.paused and step.trajectory.end_time == decision['t']
        step.pick(choose(decision), 'live')
    assert len(calls) == 1 + len(step.picks) + 1
    assert step.picks == live.picks
    study = evaluate_study(model, runs=[run], play={'run': run, 'control': control, 'picks': live.picks})
    assert study.admissible and study.decision is None, study.diagnostics
    trajectories = [live.trajectory, step.trajectory, study.runs[run]['trajectory']]
    assert len({fingerprint(trajectory) for trajectory in trajectories}) == 1
    assert not live.trajectory.paused and live.trajectory.end_time == live.trajectory.horizon
    assert live.result() == step.result() == sample_result(study)


def test_a_resolver_that_gives_no_answer_stops_the_run_where_the_step_path_does():
    model = guard_model()
    asked = []
    live = Session(model, 'a', control=CONTROL, resolver=lambda decision: asked.append(decision) or None)
    step = Session(model, 'a', control=CONTROL)
    decision = live.advance()
    assert decision == step.advance() == asked[0] and len(asked) == 1
    assert 'pick_index' not in decision and decision['pick'] == 0
    assert fingerprint(live.trajectory) == fingerprint(step.trajectory) and live.trajectory.paused
    assert live.picks == []


def test_a_reader_who_always_shuts_gives_the_run_of_the_model_that_always_shuts():
    """`shut 1` gives `wait` no chance: the model's run shuts at each decision, as the reader does."""
    model = guard_model()
    session = live_session(model, 'a', CONTROL, lambda decision: 'shut')
    assert session.advance() is None
    assert [(item['event'], item['outcome'], item['by']) for item in session.picks] == [
        ('guard.first', 'shut', 'reader'),
        ('guard.second', 'shut', 'reader'),
    ]
    sure = evaluate_study(guard_model(shut='1'))
    assert story(session.trajectory) == story(sure.runs['a']['trajectory'])
    played, chosen = session.result()['runs']['a'], sample_result(sure)['runs']['a']
    assert unmarked(played) == unmarked(chosen)
    picked = [
        entry['picked'] for entry in played['trace'] if entry['rule'] in ('guard.first', 'guard.second')
    ]
    assert picked == ['reader', 'reader']
    assert all(entry['picked'] is None for entry in chosen['trace'])
    # The same log again gives the same run, bit for bit.
    again = evaluate_study(model, play={'run': 'a', 'control': CONTROL, 'picks': session.picks})
    assert again.admissible and again.decision is None, again.diagnostics
    assert fingerprint(again.runs['a']['trajectory']) == fingerprint(session.trajectory)


def test_a_reader_who_picks_what_the_model_picks_gives_the_models_run(reservoir):
    model, run, control = reservoir
    plain = evaluate_study(model, runs=[run])
    choices = {choice['event'] for actor in actors(model) for choice in actor['choices']}
    taken = {}
    for entry in plain.runs[run]['trajectory'].trace:
        if entry['rule'] in choices and entry['outcome'] is not None:
            taken.setdefault(entry['rule'], []).append(entry['outcome'])
    assert taken
    session = live_session(model, run, control, lambda decision: taken[decision['event']].pop(0))
    assert session.advance() is None
    assert all(not outcomes for outcomes in taken.values())
    assert story(session.trajectory) == story(plain.runs[run]['trajectory'])
    assert unmarked(session.result()['runs'][run]) == unmarked(sample_result(plain)['runs'][run])


def test_a_combination_that_a_run_makes_plays_as_that_run():
    model = optioned_model()
    first = POLICIES['first']
    combined = live_session(model, 'a', CONTROL, first, options=['Slow alarm', 'Default', 'Slow alarm'])
    declared = live_session(model, 'b', CONTROL, first)
    assert combined.options == ('Default', 'Slow alarm')
    assert combined.base is model and combined.model.runs['a']['options'] == model.runs['b']['options']
    assert combined.advance() is None and declared.advance() is None
    assert fingerprint(combined.trajectory) == fingerprint(declared.trajectory)
    assert combined.picks == declared.picks
    assert combined.result()['runs']['a'] == declared.result()['runs']['b']
    # The guard sees the delay of the option, in the unit of its input.
    decision = Session(model, 'a', control=CONTROL, options=['Slow alarm']).advance()
    assert decision['view']['world.delay'] == pytest.approx(SLOW)


def test_an_option_that_the_model_does_not_have_is_the_engines_refusal():
    model = optioned_model()
    with pytest.raises(ModelError) as raised:
        Session(model, 'a', control=CONTROL, options=['Fast alarm'])
    assert {item['code'] for item in raised.value.diagnostics} == {'reference'}


# --- Refusals -------------------------------------------------------------------------------------


def nan_edits():
    return {'set': {'world.delay': math.nan}}


# Each bad request: (the model, the run, the control, the picks, the edits, the numerical settings).
REFUSED = {
    'an unknown control': (guard_model, 'a', {'nobody': 'reader'}, [], None, None),
    'a thing that is no actor': (guard_model, 'a', {'world': 'reader'}, [], None, None),
    'a method that is none': (guard_model, 'a', {'guard': 'oracle'}, [], None, None),
    'a pick of another event': (
        guard_model,
        'a',
        CONTROL,
        [{'event': 'guard.second', 'outcome': 'shut'}],
        None,
        None,
    ),
    'a pick of no outcome': (
        guard_model,
        'a',
        CONTROL,
        [{'event': 'guard.first', 'outcome': 'run'}],
        None,
        None,
    ),
    'a pick that cannot happen': (
        lambda: guard_model(**WHEN),
        'a',
        CONTROL,
        [{'event': 'guard.first', 'outcome': 'wait'}],
        None,
        None,
    ),
    'a pick without an outcome': (guard_model, 'a', CONTROL, [{'event': 'guard.first'}], None, None),
    'an unknown run': (guard_model, 'zz', CONTROL, [], None, None),
    'edits that are no object': (guard_model, 'a', CONTROL, [], ['set'], None),
    'edits with a value that is not finite': (guard_model, 'a', CONTROL, [], nan_edits(), None),
    'an edit beyond the range of its input': (
        guard_model,
        'a',
        CONTROL,
        [],
        {'set': {'world.delay': 9}},
        None,
    ),
    'edits of another model': (
        guard_model,
        'a',
        CONTROL,
        [],
        {'schema_version': '0.0.1', 'model_hash': '0' * 64},
        None,
    ),
    'settings that stop the run': (guard_model, 'a', CONTROL, [], None, {'max_events': 1}),
}


@pytest.mark.parametrize('name', REFUSED)
def test_a_session_refuses_what_the_study_refuses_with_the_same_diagnostics(name):
    build, run, control, picks, edits, settings = REFUSED[name]
    model = build()
    if isinstance(edits, dict) and 'model_hash' not in edits:
        edits = edits_for(model, edits)
    study = evaluate_study(
        model, edits, settings, runs=[run], play={'run': run, 'control': control, 'picks': picks}
    )
    assert not study.admissible
    session = Session(model, run, control=control, picks=picks, edits=edits, settings=settings)
    with pytest.raises(ModelError) as raised:
        session.advance()
    assert raised.value.diagnostics == study.diagnostics
    assert session.decision is None and session.trajectory is None


def test_numerical_settings_that_are_not_valid_are_refused_when_the_session_starts():
    with pytest.raises(ModelError) as raised:
        Session(guard_model(), 'a', control=CONTROL, settings={'rtol': 0})
    assert [item['code'] for item in raised.value.diagnostics] == ['numerical_settings']


def test_a_pick_answers_only_a_decision_that_waits_with_an_outcome_that_can_happen():
    session = Session(guard_model(**WHEN), 'a', control=CONTROL)
    with pytest.raises(ValueError):
        session.pick('shut')
    decision = session.advance()
    names = [item['name'] for item in decision['outcomes']]
    cannot = [name for name in names if name not in available(decision)]
    assert cannot, 'the fixture has an outcome that cannot happen'
    for outcome in (*cannot, 'run'):
        with pytest.raises(ValueError):
            session.pick(outcome)
    assert session.picks == [] and session.decision == decision
    session.pick(available(decision)[0], 'why')
    assert session.decision is None
    assert session.picks == [
        {
            'event': decision['event'],
            'outcome': available(decision)[0],
            't': decision['t'],
            'by': 'reader',
            'reason': 'why',
        }
    ]
    with pytest.raises(ValueError):
        session.pick(available(decision)[0])


def test_a_log_that_leaves_a_decision_has_no_result():
    session = Session(guard_model(), 'a', control=CONTROL)
    decision = session.advance()
    session.pick(available(decision)[0])
    with pytest.raises(ValueError):
        session.result()


class Stop(Exception):
    """An exception of a resolver."""


def test_a_resolver_that_raises_keeps_exactly_the_picks_before_it():
    asked = []

    def resolver(decision):
        asked.append(decision['event'])
        if len(asked) == 2:
            raise Stop
        return available(decision)[0], 'first'

    session = Session(guard_model(), 'a', control=CONTROL, resolver=resolver)
    with pytest.raises(Stop):
        session.advance()
    assert len(asked) == 2 and [item['event'] for item in session.picks] == asked[:1]
    assert session.decision is None and session.trajectory is None
    # The log goes on: without the resolver, the run stops at the decision that it did not answer.
    assert Session(guard_model(), 'a', control=CONTROL, picks=session.picks).advance()['event'] == asked[1]


def test_an_engine_error_of_a_resolver_propagates_as_it_is():
    error = ModelError([{'code': 'agent', 'path': '', 'message': 'The agent stops.', 'severity': 'error'}])

    def resolver(decision):
        raise error

    with pytest.raises(ModelError) as raised:
        Session(guard_model(), 'a', control=CONTROL, resolver=resolver).advance()
    assert raised.value is error


@pytest.mark.parametrize(
    'answer', [lambda decision: ('wait', None), lambda decision: 'shut', lambda decision: ('run', None)]
)
def test_an_answer_that_cannot_be_taken_is_no_pick(answer):
    """`wait` cannot happen at the first decision; a bare outcome is no (outcome, reason); `run` is no
    outcome."""
    session = Session(guard_model(**WHEN), 'a', control=CONTROL, resolver=answer)
    with pytest.raises(ValueError):
        session.advance()
    assert session.picks == []


# --- Logs -----------------------------------------------------------------------------------------


def test_a_saved_log_replays_the_run_exactly(tmp_path):
    model = guard_model()
    live = live_session(model, 'a', CONTROL, POLICIES['by turns'])
    assert live.advance() is None
    path = tmp_path / 'log.json'
    live.save(path)
    log = json.loads(path.read_text(encoding='utf-8'))
    assert log == live.log() and set(CONTEXT) <= set(log)
    assert (log['schema_version'], log['kind'], log['picks']) == ('0.0.1', 'play', live.picks)
    assert list(tmp_path.iterdir()) == [path]
    again = Session.load(path, model, 'a', control=CONTROL)
    assert again.picks == live.picks
    # No resolver: each decision takes its pick of the log.
    assert again.advance() is None
    assert fingerprint(again.trajectory) == fingerprint(live.trajectory)
    assert again.result() == live.result()


def test_a_log_saved_at_a_decision_goes_on_from_it(tmp_path):
    model, choose = guard_model(), POLICIES['last']
    whole = live_session(model, 'a', CONTROL, choose)
    whole.advance()
    first = Session(model, 'a', control=CONTROL)
    first.pick(choose(first.advance()), 'live')
    path = tmp_path / 'log.json'
    first.save(path)
    rest = Session.load(
        path, model, 'a', control=CONTROL, resolver=lambda decision: (choose(decision), 'live')
    )
    assert rest.advance() is None
    assert rest.picks == whole.picks
    assert fingerprint(rest.trajectory) == fingerprint(whole.trajectory)


# What a session changes in the context of a log of run `a` of the optioned model, by the field of the
# log that then differs.
CHANGED = {
    'run': {'run': 'b'},
    'options': {'options': ['Slow alarm']},
    'control': {'control': {'guard.first': 'reader'}},
    'edits': {'edits': {'set': {'world.delay': SLOW}}},
    'numerical_settings': {'settings': {'rtol': 1e-8}},
}


@pytest.mark.parametrize('field', CHANGED)
def test_a_log_is_refused_in_another_context_and_the_refusal_names_what_differs(field, tmp_path):
    model = optioned_model()
    path = tmp_path / 'log.json'
    session = Session(model, 'a', control=CONTROL)
    session.pick(available(session.advance())[0])
    session.save(path)
    given = {'run': 'a', 'control': CONTROL, **CHANGED[field]}
    if 'edits' in given:
        given['edits'] = edits_for(model, given['edits'])
    run = given.pop('run')
    with pytest.raises(OtherContext) as raised:
        Session.load(path, model, run, **given)
    assert raised.value.fields == (field,)
    assert field in str(raised.value).replace(str(path), '')


def test_a_log_is_refused_by_another_model_and_by_another_engine(tmp_path):
    model, other = guard_model(), guard_model(shut='0.4')
    assert other.model_hash != model.model_hash
    path = tmp_path / 'log.json'
    Session(model, 'a', control=CONTROL).save(path)
    with pytest.raises(OtherContext) as raised:
        Session.load(path, other, 'a', control=CONTROL)
    assert raised.value.fields == ('model_hash',)
    log = json.loads(path.read_text(encoding='utf-8'))
    path.write_text(json.dumps({**log, 'implementation_hash': '0' * 64, 'run': 'b'}), encoding='utf-8')
    with pytest.raises(OtherContext) as raised:
        Session.load(path, model, 'a', control=CONTROL)
    assert raised.value.fields == ('implementation_hash', 'run')
    del log['edits']
    path.write_text(json.dumps(log), encoding='utf-8')
    with pytest.raises(OtherContext) as raised:
        Session.load(path, model, 'a', control=CONTROL)
    assert raised.value.fields == ('edits',)


@pytest.mark.parametrize(
    'change',
    [{'kind': 'study'}, {'schema_version': '2'}, {'picks': {}}, {'picks': ['guard.first']}],
    ids=['another kind', 'another schema', 'picks that are no list', 'a pick that is no object'],
)
def test_a_file_that_is_not_a_play_log_is_refused(change, tmp_path):
    model = guard_model()
    path = tmp_path / 'log.json'
    path.write_text(json.dumps({**Session(model, 'a', control=CONTROL).log(), **change}), encoding='utf-8')
    with pytest.raises(ValueError) as raised:
        Session.load(path, model, 'a', control=CONTROL)
    assert not isinstance(raised.value, OtherContext)


# --- `napkin play` on the reservoir -----------------------------------------------------------------


@pytest.mark.parametrize('face', ['terminal', 'json'])
def test_play_writes_the_log_before_each_prompt(face, tmp_path, monkeypatch):
    """When a decision is asked, the log on disk holds each pick before it: the answer that the engine
    took is saved before the next question."""
    model, log = guard_model(), tmp_path / 'log.json'
    seen = []

    class Reader(io.StringIO):
        def readline(self, *args):
            seen.append(json.loads(log.read_text(encoding='utf-8'))['picks'])
            return json.dumps({'pick': 'shut'}) + '\n' if face == 'json' else 'shut\n'

    session = Session(model, 'a', control=CONTROL)
    if face == 'json':
        prompts = play_command.Lines(Reader(), io.StringIO(), log)
    else:
        monkeypatch.setattr(sys, 'stdin', Reader())
        monkeypatch.setattr(sys, 'stdout', io.StringIO())
        prompts = play_command.Terminal(sys.stdout, log)
    session.resolver = prompts.asker(session)
    assert session.advance() is None and len(session.picks) == 2
    # The terminal reads a reason after each pick, the JSON lines read none.
    asked = seen if face == 'json' else seen[::2]
    assert asked == [[], session.picks[:1]]


def napkin(*argv, **kwargs):
    """A `napkin` process at the root of the checkout, with no run store."""
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'NAPKIN_STORE': 'off'}
    return subprocess.Popen(
        [sys.executable, '-B', '-m', 'napkin', *map(str, argv)],
        cwd=ROOT,
        env=env,
        text=True,
        **kwargs,
    )


def test_play_json_on_the_reservoir_plays_to_the_end(reservoir):
    model, run, control = reservoir
    (actor,) = control
    child = napkin(
        'play',
        RESERVOIR,
        '--control',
        actor,
        '--json',
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    lines, answers = [], []
    try:
        while True:
            text = child.stdout.readline()
            assert text, child.stderr.read()
            line = json.loads(text)
            assert line['schema_version'] == '0.0.1'
            lines.append(line)
            if line['type'] == 'result':
                break
            assert line['type'] == 'decision'
            answers.append(available(line)[0])
            child.stdin.write(json.dumps({'pick': answers[-1], 'reason': 'the first'}) + '\n')
            child.stdin.flush()
        child.stdin.close()
        assert child.wait(timeout=120) == 0, child.stderr.read()
    finally:
        child.kill()
        child.wait()
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()
    result = lines[-1]
    assert result['finished'] is True and result['report']['admissible'] is True
    assert 'decision' not in result and answers
    assert [(item['outcome'], item['reason']) for item in result['picks']] == [
        (name, 'the first') for name in answers
    ]
    # The report is the session's, as `napkin run --json` would write it, checked for the run only.
    session = live_session(model, run, control, POLICIES['first'])
    assert session.advance() is None
    assert result['report'] == common.compact(session.result(), admitted=model.admission_runs)
    assert result['report']['admitted_runs'] == [run]


def test_play_at_the_terminal_exits_3_when_the_input_ends_and_saves_the_log(reservoir, tmp_path):
    model, run, control = reservoir
    (actor,) = control
    path = tmp_path / 'log.json'
    child = napkin(
        'play',
        RESERVOIR,
        '--control',
        actor,
        '--save',
        path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _, err = child.communicate('', timeout=120)
    assert child.returncode == 3, err
    paused = Session.load(path, model, run, control=control)
    assert paused.picks == []
    decision = paused.advance()
    # The log goes on at the terminal: the number 1 picks the first outcome that can happen.
    child = napkin(
        'play',
        RESERVOIR,
        '--control',
        actor,
        '--picks',
        path,
        '--save',
        path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _, err = child.communicate('1\nthe first\n', timeout=120)
    assert child.returncode == 0, err
    done = Session.load(path, model, run, control=control)
    assert done.picks[:1] == [
        {
            'event': decision['event'],
            'outcome': available(decision)[0],
            't': decision['t'],
            'by': 'reader',
            'reason': 'the first',
        }
    ]
    assert done.advance() is None
