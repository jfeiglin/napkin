"""DC crew availability scales with the selected response under the same four draws."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import napkin
from napkin.engine.sampling import SamplingSettings, sampled
from tests.helpers import catalogue_model

DC = Path(__file__).resolve().parents[1] / 'variants' / 'washington_dc'
PATHS = (
    'controls_crew.working_capacity',
    'field_crew.working_capacity',
    'wssc_water.manual_share',
    'wssc_water.controls_load',
    'controls_crew.hours',
    'field_crew.hours',
)


def initial(model, tier, edits, seed=0):
    # The spread is drawn once when the pools and the utility are created.
    configuration = model.configure(tier, edits)
    start = replace(configuration, request=replace(configuration.request, horizon=0))
    record = napkin.run(model.program, sampled(start, SamplingSettings(1, seed))[0])
    assert record.failure is None
    readings = [row.values[0] for row in napkin.read(record, model.program, PATHS, [0])]
    draws = {row.part: row.detail('value') for row in record.entries('draw')}
    assert len(draws) == len(record.entries('draw'))
    return readings, draws


def test_four_once_per_run_draws_keep_response_tiers_and_fund_the_entire_crew_pool():
    model = catalogue_model('water_controls_wipe:washington_dc')
    edits = json.loads((DC / 'spreads' / 'uncertainty.json').read_text())
    reference_draws = None
    for tier, nominal in [('delayed_none', (40, 60)), ('standard', (80, 100)), ('early', (160, 200))]:
        actual, draws = initial(model, tier, edits)
        controls, field, manual, load = [draws[path + '.draw[0]'] for path in PATHS[:4]]
        assert len(draws) == 4
        assert 20 <= controls <= 80 and 30 <= field <= 120
        assert 0.3 <= manual <= 0.9 and 300 <= load <= 1500
        if reference_draws is None:
            reference_draws = draws
        else:
            assert draws == reference_draws
        rates = [controls * nominal[0] / 40, field * nominal[1] / 60]
        assert actual == pytest.approx([*rates, manual, load, *(rate * 2400 for rate in rates)])
    _, other = initial(model, 'early', edits, seed=1)
    assert all(other[site] != reference_draws[site] for site in other)

    # Disjoint alternatives prove that the checked edit supplies each law.
    edits['set'].update(
        {
            'uncertainty.controls_capacity': 'uniform(5 work_h/h, 10 work_h/h)',
            'uncertainty.field_capacity': 'uniform(10 work_h/h, 20 work_h/h)',
            'uncertainty.manual_share': 'uniform(0.05, 0.1)',
            'uncertainty.controls_load': 'uniform(100 work_h, 200 work_h)',
        }
    )
    actual, _ = initial(model, 'delayed_none', edits)
    for value, (low, high) in zip(actual[:4], [(5, 10), (10, 20), (0.05, 0.1), (100, 200)], strict=True):
        assert low <= value <= high


def test_runs_without_the_spread_preserve_nominal_options_and_scalar_edits():
    model = catalogue_model('water_controls_wipe:washington_dc')
    for tier, nominal in [('early', (160, 200)), ('standard', (80, 100)), ('delayed_none', (40, 60))]:
        actual, draws = initial(model, tier, None)
        assert (actual[:4], draws) == ([*nominal, 0.6, 600], {})
    edits = {
        'schema_version': napkin.SCHEMA_VERSION,
        'model_hash': model.model_hash,
        'set': {
            'controls_crew.capacity': 88,
            'field_crew.capacity': 99,
            'wssc_water.manual_share': 0.4,
            'wssc_water.controls_load': 789,
        },
    }
    actual, draws = initial(model, 'early', edits)
    assert (actual[:4], draws) == ([88, 99, 0.4, 789], {})
