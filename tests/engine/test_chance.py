"""Chance (docs/language.md, §2.6): the chances of an event's outcomes add up to 1, the central run takes
the likeliest outcome, and the samples of a study draw the outcomes with their chances."""

from __future__ import annotations

import math

import pytest

from napkin.engine import evaluate_uncertainty, uncertainty_report
from napkin.engine.runtime import SimulationError
from napkin.engine.sampling import SamplingSettings
from tests.build import block, compiled, named, run, system


def decision(*outcomes):
    """Entity `s` with a named state `x` and an event `decide` at t = 1 h, with `outcomes`, each
    `(head, value of x)`."""
    return system(
        named('x', 'a', 'shut', 'manual', 'wait'),
        block(
            'event decide once when t >= 1 h:  @fixture',
            *(block(f'{head}:', f'x = "{value}"') for head, value in outcomes),
        ),
    )


def outcome_of(text):
    _, trajectory = run(text)
    return trajectory.env_at(10)['s.x']


def test_chances_that_do_not_add_up_to_one_stop_the_run():
    with pytest.raises(SimulationError) as raised:
        run(decision(('shut 0.5', 'shut'), ('manual 0.4', 'manual')))
    assert next(d['code'] for d in raised.value.diagnostics if d.get('severity') == 'error') == 'chances'
    # `else` takes what the others leave: 1 - 0.5 - 0.4 = 0.1.
    assert (
        outcome_of(decision(('shut 0.5', 'shut'), ('manual 0.4', 'manual'), ('wait else', 'wait'))) == 'shut'
    )


@pytest.mark.parametrize(
    ('outcomes', 'expected'),
    [
        ((('shut 0.3', 'shut'), ('manual 0.7', 'manual')), 'manual'),  # the likeliest
        ((('shut 0.7', 'shut'), ('manual else', 'manual')), 'shut'),  # else is 0.3
        ((('shut 0.5', 'shut'), ('manual 0.5', 'manual')), 'shut'),  # a tie: the first in the file
        ((('manual 0.5', 'manual'), ('shut 0.5', 'shut')), 'manual'),
        ((('shut t >= 1 h', 'shut'), ('wait else', 'wait')), 'shut'),  # a condition is 1 when it holds
    ],
)
def test_the_central_run_takes_the_likeliest_outcome_and_the_first_on_a_tie(outcomes, expected):
    assert outcome_of(decision(*outcomes)) == expected


def test_the_samples_of_a_study_draw_each_outcome_with_its_chance():
    samples = 400
    model = compiled(decision(('shut 0.3', 'shut'), ('manual else', 'manual')))
    result = evaluate_uncertainty(model, settings=SamplingSettings(samples=samples, seed=11))
    assert result.admissible, result.diagnostics
    events = uncertainty_report(result)['uncertainty']['runs']['a']['events']['s.decide']
    # The event fires once in each sample: its outcomes add up to the samples.
    assert sum(events.values()) == samples
    # 0.3 within three standard deviations of a binomial share of 400 samples.
    spread = 3 * math.sqrt(0.3 * 0.7 / samples)
    assert 0.3 - spread <= events['shut'] / samples <= 0.3 + spread
    # The central run still takes the likeliest outcome.
    _, trajectory = run(decision(('shut 0.3', 'shut'), ('manual else', 'manual')))
    assert trajectory.env_at(10)['s.x'] == 'manual'
