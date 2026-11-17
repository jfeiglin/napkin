"""The executable AI layer: tempo, stoppable reactions and matched comparison runs.

The fixture is sc99 (tests/build.py) with an AI reaction to the outage: after the service stops, the
AI corrupts the records `ai_retask_h` hours later, unless the defender contains its access first. The
reaction takes its outcome when its wait ends. The run `a_human` is the comparison of `a`: the same
attack at a human team's pace.
"""

import pytest

from tests.build import (
    BASIS,
    X,
    compiled,
    edit,
    entity,
    event,
    evidence_library,
    member,
    named,
    option,
    options,
    parameter,
    q,
    rejected,
    replace,
    run,
    sc99,
)
from tools.publish import brief

CONTAIN_H, STOP_H, HUMAN_H = 20.0, 12.0, 24.0
RECORDS = 'attacker.record_attack'


def adaptive():
    """sc99 plus an AI reaction to the outage: it corrupts records unless its access is contained first."""
    records = entity('records', named('state', 'trusted', 'corrupted'), doc='Records that the service keeps.')
    defender = entity(
        'defender',
        parameter('contain_h', CONTAIN_H, 'h', 0, 48, doc='Time to contain the access'),
        event(
            'contain',
            't >= contain_h and count(attacker.start) > 0',
            'control.access = "contained"',
            doc='Revoke the AI access',
            do_records=BASIS,
        ),
        doc='The defender who contains the AI access.',
        role='responder',
    )
    conduct = options(
        'Conduct',
        option(
            'Human team',
            'The same attack at a human team pace.',
            f'attacker.ai_retask_h = {q(HUMAN_H, "h")}  {BASIS}',
        ),
    )
    return edit(
        sc99(),
        member('control', named('access', 'available', 'contained')),
        member(
            'attacker',
            parameter('ai_retask_h', 0.25, 'h', 0.05, 48, doc='Time the AI takes to retask'),
            event(
                'record_attack',
                'count(service.stop) > 0',
                'records.state = "corrupted"',
                after='ai_retask_h',
                keep='control.access is "available"',
                do_records=BASIS,
                done='The AI corrupts the records after it observes the outage.',
                stopped='The defender contains the AI access first.',
            ),
        ),
        # Containment wins an exact tie with the end of the AI's wait: at one moment the events go in
        # the order of their lines, and the defender's come before the attacker's.
        replace('\nattacker:', f'\n{records}\n\n{defender}\n\nattacker:'),
        replace('\nruns:', f'\n{conduct}\n\nruns:'),
        member('runs:', 'a_human = "Default" + "Human team" versus a'),
    )


def race(stop_h, tempo_h, contain_h):
    """Independent race arithmetic: the reaction takes its outcome when its wait ends, and containment
    wins ties because the reaction's end orders after it. Access contained before the wait ends, or
    before the trigger, stops the reaction."""
    return 'done' if stop_h + tempo_h < contain_h else 'stopped'


def reaction_outcomes(trajectory):
    """{outcome: time} of the AI reaction in one run's trace."""
    return {e['outcome']: e['t'] for e in trajectory.trace if e['semantic'] and e['rule'] == RECORDS}


def test_ai_tempo_decides_the_race_against_containment():
    s = adaptive()
    model = compiled(s, evidence_library())
    for name in ('a', 'a_human'):
        tempo = model.run_values(name)['attacker.ai_retask_h']
        _, trajectory = run(s, name, evidence_library())
        semantic = {e['event']: e['t'] for e in trajectory.trace if e['semantic']}
        expected = race(STOP_H, tempo, CONTAIN_H)
        if expected == 'done':
            assert semantic[f'{RECORDS}.done'] == pytest.approx(STOP_H + tempo)
            assert trajectory.env_at(STOP_H + tempo)['records.state'] == 'corrupted'
        else:
            # The reaction is stopped when its wait ends, if that is within the run.
            if STOP_H + tempo <= trajectory.horizon:
                assert semantic[f'{RECORDS}.stopped'] == pytest.approx(STOP_H + tempo)
            else:
                assert f'{RECORDS}.stopped' not in semantic
            assert f'{RECORDS}.done' not in semantic
            assert trajectory.env_at(trajectory.horizon)['records.state'] == 'trusted'
    # The two runs differ only in the AI's tempo.
    a, human = model.run_values('a'), model.run_values('a_human')
    assert {k for k in a if a[k] != human[k]} == {'attacker.ai_retask_h'}


@pytest.mark.parametrize('tempo', [CONTAIN_H - STOP_H - 1e-3, CONTAIN_H - STOP_H, CONTAIN_H - STOP_H + 1])
def test_exact_tie_goes_to_containment(tempo):
    _, trajectory = run(adaptive(), 'a', evidence_library(), values={'attacker.ai_retask_h': tempo})
    assert set(reaction_outcomes(trajectory)) == {race(STOP_H, tempo, CONTAIN_H)}


def brief_problems(text):
    """The (code, key) of each problem of the brief settings `text` against the adaptive model."""
    model = compiled(adaptive(), evidence_library())
    return {(d['code'], d['key']) for d in brief.check_brief(brief.read_brief(text), model)}


@pytest.mark.parametrize(
    'problems, found',
    [
        # A comparison is the comparison of another run, not of itself.
        (
            lambda: rejected(edit(adaptive(), replace('versus a', 'versus a_human'))),
            ('structure', 'runs:/a_human/versus:'),
        ),
        # The run that a comparison names is no comparison itself.
        (
            lambda: rejected(
                edit(adaptive(), replace('\n    a = "Default"\n', '\n    a = "Default" versus b\n'))
            ),
            ('structure', 'runs:/a_human/versus:'),
        ),
        # The runs that the pages show first exist.
        (lambda: brief_problems('featured = ["ghost", "a_human"]\n'), ('style', 'featured')),
        # The outputs that the brief compares are outputs.
        (lambda: brief_problems('show = ["ghost"]\n'), ('style', 'show')),
    ],
    ids=[
        '<lambda>-simulate/runs/a_human/comparison_of0',
        '<lambda>-simulate/runs/a_human/comparison_of1',
        '<lambda>-simulate/default_runs/0',
        '<lambda>-simulate/show/0',
    ],
)
def test_comparison_runs_and_their_outputs_are_structural(problems, found):
    compiled(adaptive(), evidence_library())
    assert not brief_problems('featured = ["a", "a_human"]\nshow = ["delivered"]\n')
    assert found in problems()


def obedient():
    """sc99 without an AI tempo, plus an option that changes only the AI's conduct (a conduct-only comparison)."""
    conduct = options(
        'Conduct',
        option('AI obeys', 'The AI obeys the stop order.', f'service.end = {q(6, "h")}  {BASIS}'),
    )
    return edit(
        sc99(),
        replace('\nruns:', f'\n{conduct}\n\nruns:'),
        member('runs:', 'a_obeys = "Default" + "AI obeys" versus a'),
    )


def test_a_comparison_run_may_take_an_option_that_changes_only_the_ai_conduct():
    s = obedient()
    model = compiled(s, evidence_library())
    assert model.runs['a_obeys']['comparison_of'] == 'a'
    _, trajectory = run(s, 'a_obeys', evidence_library())
    assert [e['event'] for e in trajectory.trace if e['semantic']] == [X, 'service.stop.done']
    assert [e['t'] for e in trajectory.trace if e['event'] == 'service.stop.done'] == [
        model.run_values('a_obeys')['service.end']
    ]
