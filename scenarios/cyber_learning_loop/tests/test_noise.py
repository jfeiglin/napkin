"""The scenario's stochastic version: the yearly assessment draws its error in each sample of a study.

The central run takes the median draw, 0, so it is the deterministic model. Each sample draws the error
of every yearly assessment from the stream of the event, so one seed gives one study, and the errors
move the split away from the central run."""

from __future__ import annotations

import pytest

from napkin.core import expr
from napkin.dynamics import vector_field
from napkin.engine import SamplingSettings, evaluate_uncertainty
from napkin.engine.study import edits_for
from tests.helpers import catalogue_model, catalogue_study

pytestmark = pytest.mark.deep

YEAR_H = 8760.0
RUN = 'ai_slow'


def at_2030(result, name):
    """Each sample's value of `name` in 2030, four years after the start."""
    return [
        next(row['values'][name] for row in rows if row['t'] == 4 * YEAR_H)
        for rows in result.samples[RUN]['rows']
    ]


def test_the_central_run_has_no_assessment_error():
    study = catalogue_study('cyber_learning_loop', runs=[RUN])
    trajectory = study.runs[RUN]['trajectory']
    for years in range(26):
        assert trajectory.env_at(years * YEAR_H)['leadership.assessment_error'] == 0


def test_one_seed_gives_one_study_and_the_errors_spread_the_split():
    model = catalogue_model('cyber_learning_loop')
    settings = SamplingSettings(samples=4, seed=7, method='random')
    times = [4 * YEAR_H, 25 * YEAR_H]
    once = evaluate_uncertainty(model, edits_for(model), settings, runs=[RUN], times=times)
    again = evaluate_uncertainty(model, edits_for(model), settings, runs=[RUN], times=times)
    assert once.admissible and again.admissible
    assert at_2030(once, 'share_on_attacks') == at_2030(again, 'share_on_attacks')
    assert len(set(at_2030(once, 'share_on_attacks'))) > 1


def test_the_spread_of_an_assessment_never_falls_below_its_common_error():
    # An average over more outcomes shrinks the error of each, but not the part that every outcome of a
    # yearly assessment shares. So the spread falls as the force assesses more and stays above that part.
    # Each attack keeps its targets, the spread of its targets and its independent outcomes, so those
    # stocks scale with the attacks that carry them.
    model = catalogue_model('cyber_learning_loop')
    field = vector_field(model, 'ai_slow')
    index = field.system.index
    program = field.field.values_program([expr.ref('effects_program.assessment_spread')])
    common = model.resolve('ai_slow').parameter_values['effects_program.common_error']
    spreads = []
    for scale in (1, 10, 100, 10000):
        y = field.base.copy()
        for name in (
            'effects_program.positioned',
            'effects_program.positioned_attacks',
            'effects_program.held_ready',
            'effects_program.held_targets',
            'effects_program.held_spread',
            'effects_program.held_outcomes',
            'effects_program.assessing',
            'effects_program.assessing_targets',
            'effects_program.assessing_outcomes',
        ):
            y[index[name]] *= scale
        spreads.append(program(10 * YEAR_H, y)[0])
    assert spreads == sorted(spreads, reverse=True)
    assert all(spread > common for spread in spreads)
    assert spreads[-1] == pytest.approx(common, rel=0.05)
