"""The historical workforce anchors, mission work accounts and institutional review."""

import json
from math import exp
from pathlib import Path

import pytest

import napkin
from napkin import store

FOLDER = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((FOLDER / 'tests/strategic-reference.json').read_bytes())
YEAR = 8760


@pytest.fixture(scope='module')
def model():
    compiled = napkin.load_scenario(FOLDER)
    assert not compiled.reports
    assert {r.name for r in compiled.declared.runs} == set(REFERENCE['runs'])
    return compiled


def completed(model, name):
    config = model.configure(name)
    record = store.run(model.program, config)
    assert record.stop is None and record.end == config.request.horizon
    return record


@pytest.mark.deep
@pytest.mark.parametrize('name', REFERENCE['runs'])
def test_payroll_and_time_paths_match_the_pinned_historical_equations(model, name):
    r = completed(model, name)
    staff = REFERENCE['payroll_at_zero'][name]
    for row in napkin.read(r, model.program, list(staff), [0]):
        assert row.values[0] == pytest.approx(staff[row.path], rel=1e-10, abs=1e-12)
    keys = [
        'ai_tools.review_progress' if k == 'ai_tools.payload_progress' else k for k in REFERENCE['outputs']
    ]
    times = [year * YEAR for year in REFERENCE['years']]
    series = napkin.read(r, model.program, keys, times)
    for i, old in enumerate(REFERENCE['runs'][name]):
        assert [row.values[i] for row in series] == pytest.approx(old, rel=1e-10, abs=1e-12)


@pytest.mark.parametrize('run,interval', [('ai_fast', 1), ('wartime', 0.25)])
def test_each_review_accounts_for_completed_work_and_updates_the_service_track_record(model, run, interval):
    record = completed(model, run)
    times = [i * interval * YEAR for i in range(round(25 / interval) + 1)]
    paths = [
        'effects_program.work_rate',
        'effects_program.completed',
        'surveillance_program.work_rate',
        'surveillance_program.completed',
        'governance.track_record',
        'governance.reliance',
        'governance.opening_rate',
        'governance.service_threshold',
    ]
    ev, ec, sv, sc, scores, reliance, opening, threshold = [
        v.values for v in napkin.read(record, model.program, paths, times)
    ]
    assert ec[0] == sc[0] == scores[0] == 0
    assert opening[0] == ev[0] > 0
    for i in range(1, len(times)):
        assert ec[i] - ec[i - 1] == pytest.approx(interval * ev[i - 1], rel=1e-8)
        assert sc[i] - sc[i - 1] == pytest.approx(interval * sv[i - 1], rel=1e-8)
        qualified = ev[i - 1] >= opening[0] * threshold[0]
        assert scores[i] == pytest.approx(
            qualified + (scores[i - 1] - qualified) * exp(-interval / 3), abs=1e-10
        )
        assert reliance[i] == (scores[i] >= 0.7)


def test_reversal_can_reduce_institutional_reliance_after_initial_uptake(model):
    record = completed(model, 'ai_reversal')
    (score,) = napkin.read(
        record, model.program, ['governance.track_record'], [12 * YEAR, 15 * YEAR, 25 * YEAR]
    )
    assert score.values[0] > 0 and score.values[2] < score.values[0]


@pytest.mark.parametrize('demand,burden,availability', [(20, 12, 0.9), (2000, 24, 0.9), (320, 12, 0)])
def test_aggregate_counts_obey_demand_labour_and_availability(model, demand, burden, availability):
    from dataclasses import replace

    from napkin.engine import edits_for

    edits = edits_for(
        model,
        {
            'set': {
                'national_volume.annual_demand': f'{demand} operations/year',
                'national_volume.work_per_case': f'{burden} staff_years/operations',
                'national_volume.availability': availability,
            }
        },
    )
    config = model.configure('ai_fast', edits)
    config = replace(config, request=replace(config.request, horizon=2 * YEAR))
    record = store.run(model.program, config)
    assert record.stop is None and record.end == 2 * YEAR
    paths = ['effects_program.work_rate', 'attacks_per_year', 'total_attacks']
    work, rate, cumulative = [
        v.values for v in napkin.read(record, model.program, paths, [0, YEAR, 2 * YEAR])
    ]
    assert rate == pytest.approx([availability * min(demand, people / burden) for people in work])
    assert cumulative == pytest.approx([0, rate[0], rate[0] + rate[1]])
