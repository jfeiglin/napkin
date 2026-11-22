"""Archived independent arithmetic and current public outcome contracts."""

import json
import math
from pathlib import Path

import pytest

from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import model, readings, record
from scenarios.iv_fluid_shortage.tests.shortage import causal_shortage

pytestmark = pytest.mark.deep


def test_frozen_legacy_acceptance_recomputes_from_its_recorded_literal_inputs():
    fixture = json.loads(Path(__file__).with_name('acceptance.json').read_text())
    assert fixture['renamed'] == {}
    assert set(fixture['inputs']) == set(fixture['runs'])
    current = {run.name for run in model().declared.runs}
    assert set(fixture['runs']) <= current
    for run, row in fixture['inputs'].items():
        assert row['persistent'] == run.endswith('_persistent')
        inputs = {k: v for k, v in row.items() if k != 'persistent'}
        assert causal_shortage(**inputs) == pytest.approx(fixture['runs'][run], rel=1e-12), run


def test_all_current_named_outcomes_are_finite_and_count_each_person_once():
    harm = ('high_risk_patients.deaths', 'high_risk_patients.casualties', 'loss_bn', 'people_needing_courses')
    for run in model().declared.runs:
        r = record(run.name)
        assert r.end == 1440 and r.failure is None
        values = [row[0] for row in readings(r, harm, [r.end]).values()]
        assert all(math.isfinite(x) and x >= 0 for x in values), run.name
        deaths, casualties, _, exposed = values
        assert deaths <= casualties <= exposed, run.name
