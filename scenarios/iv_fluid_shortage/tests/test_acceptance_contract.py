"""Frozen independent acceptance and publication contracts."""

import json
import math

import pytest

from scenarios.iv_fluid_shortage.tests.adversary_acceptance_support import keeps_access as keeps_access
from scenarios.iv_fluid_shortage.tests.shortage import causal_shortage
from scenarios.tests.sources import oracle_names
from tests.helpers import ROOT, catalogue_default, catalogue_model

HARM = ('high_risk_patients.deaths', 'high_risk_patients.casualties', 'loss_bn', 'people_needing_courses')
pytestmark = pytest.mark.deep


def oracle(inputs, *, persistent):
    return causal_shortage(**inputs)


def test_frozen_values_recompute_from_their_recorded_literal_inputs():
    sid = 'iv_fluid_shortage'
    fixture = json.loads((ROOT / 'scenarios' / sid / 'tests/acceptance.json').read_text())
    model = catalogue_model(sid)
    assert set(fixture['inputs']) == set(fixture['runs'])
    names = {name: old for old, name in fixture['renamed'].items()}
    assert len(names) == len(fixture['renamed'])
    assert all((oracle_names(sid).get(old, name) == name for old, name in fixture['renamed'].items()))
    for run, inputs in fixture['inputs'].items():
        persistent = inputs['persistent']
        assert persistent == run.endswith('_persistent')
        assert persistent == (set(fixture['persistent_options']) <= set(model.runs[run]['options']))
        assert persistent == keeps_access(model, run)
        assert all(name in model.inputs for name in names.keys() & inputs.keys())
        args = {names.get(key, key): value for key, value in inputs.items() if key != 'persistent'}
        assert oracle(args, persistent=persistent) == pytest.approx(fixture['runs'][run], rel=1e-12), run


def test_rebuilt_paths_preserve_current_publication_contract():
    sid = 'iv_fluid_shortage'
    from napkin.engine import sample_result

    model = catalogue_model(sid)
    result = catalogue_default(sid)
    assert result.admissible, result.diagnostics
    report = sample_result(result)
    assert report['admissible'], report['diagnostics']
    assert len(report['runs']) == len(model.runs)
    deaths, casualties, loss, exposure = HARM
    for run in result.runs:
        final = report['runs'][run]['reporting_points']['final']
        assert final['t'] == model.time['horizon']
        for key in (deaths, casualties, loss):
            assert final['statuses'][key] == 'estimated'
            assert math.isfinite(final['values'][key]) and final['values'][key] >= 0
        assert (
            final['values'][deaths]
            <= final['values'][casualties] + 1e-06
            <= final['values'][exposure] + 1e-06
        )
