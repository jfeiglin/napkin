"""The inclusive service standard and persistence of a workforce governance decision."""

from dataclasses import replace
from math import exp

import pytest

from napkin import read, run
from napkin.engine import edits_for
from tests.helpers import catalogue_study


@pytest.mark.parametrize(('threshold', 'qualifies'), [(1, True), (1.01, False)])
def test_opening_service_meets_an_equal_standard(workforce_model, threshold, qualifies):
    edits = edits_for(workforce_model, {'set': {'governance.threshold': threshold}})
    config = workforce_model.configure('no_ai', edits=edits)
    config = replace(config, request=replace(config.request, horizon=0))
    record = run(workforce_model.program, config)
    assert record.failure is None
    rows = read(record, workforce_model.program, ['governance.qualifying', 'governance.reliance'], [0])
    assert [row.values[0] for row in rows] == [qualifies, 0]


def test_reliance_forms_and_lapses_only_after_sufficient_review_history(workforce_model):
    name = 'ai_reversal'
    # A one-year memory gives each annual observation appreciable weight. An isolated
    # passing review from zero still scores below the adoption cutoff.
    edits = {'set': {'governance.memory': 1, 'governance.threshold': 1.1}}
    record = catalogue_study('cyber_learning_loop', edits, runs=[name])[name]
    paths = ['governance.qualifying', 'governance.track_record', 'governance.reliance']
    conditions, scores, decisions = read(
        record, workforce_model.program, paths, [i * 8760 for i in range(26)]
    )
    expected = 0
    assert scores.values[0] == decisions.values[0] == 0
    for i, condition in enumerate(conditions.values[:-1], start=1):
        expected = condition + (expected - condition) * exp(-1)
        assert scores.values[i] == pytest.approx(expected)
        assert decisions.values[i] == (expected >= 0.7)
    assert 1 in decisions.values and decisions.values[-1] == 0
