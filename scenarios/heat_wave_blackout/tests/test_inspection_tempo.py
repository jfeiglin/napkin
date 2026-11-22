"""Overlapping work holds and the times and sampled interval of the heat recovery exercise."""

import json
from dataclasses import replace

import pytest

import napkin
from napkin.engine import edits_for
from napkin.engine.sampling import SamplingSettings, sampled
from napkin.engine.timeline import stocks
from scenarios.heat_wave_blackout.tests.support import FOLDER, model, readings


def simulate(name, horizon, inputs, *, seed=None):
    current = model()
    # Constant indoor temperature isolates work and time while exercising the actual package.
    baseline = {
        f'{building}.{field}': 28
        for building in ('homes', 'compound_buildings')
        for field in ('iet_on', 'iet_off_mean')
    }
    body = edits_for(current, {'set': {**baseline, **inputs}})
    config = current.configure(name, body)
    config = replace(config, request=replace(config.request, horizon=horizon))
    if seed is not None:
        config = sampled(config, SamplingSettings(1, seed))[0]
    record = napkin.run(current.program, config)
    assert record.stop is None, record.stopped()
    assert record.end == horizon
    return record


def starts(record, event):
    return [e.t for e in record.entries('start') if e.part == event]


@pytest.mark.parametrize('probe', [-2, 2])
def test_calendar_overlap_and_exact_containment_time(monkeypatch, probe):
    monkeypatch.setattr(stocks, 'LEDGER_PROBE', probe)
    record = simulate(
        'fixed_inspections',
        2,
        {
            'incident.first_report': 0.25,
            'incident.interval': 0.5,
            'incident.inspection_duration': 0.75,
            'incident.inspection_work': 1,
            'incident.detection_delay': 0.5,
            'incident.containment_delay': 0.5,
            'incident.window_end': 1.75,
        },
    )
    assert starts(record, 'incident.report') == [0.25, 0.75, 1.25]
    assert starts(record, 'incident.inspection') == [0.25, 0.75]
    paths = (
        'incident.paused',
        'incident.open_holds',
        'incident.accepted',
        'incident.prevented',
        'incident.detected',
        'incident.contained',
        'crews.rework_caused',
    )
    values = readings(record, paths, [0, 0.25, 0.75, 1, 1.25, 1.5, 2])
    assert values['incident.open_holds'] == (0, 1, 2, 1, 1, 0, 0)
    assert values['incident.paused'] == (False, True, True, True, True, False, False)
    assert values['incident.detected'] == (False, False, True, True, True, True, True)
    assert values['incident.contained'] == (False, False, False, False, True, True, True)
    assert values['incident.prevented'][-1] == 1
    assert values['incident.accepted'][-1] == values['crews.rework_caused'][-1] == 2


@pytest.mark.deep
def test_follow_up_waits_for_real_clearance_of_the_first_work_order():
    record = simulate(
        'clearance_inspections',
        12,
        {
            'incident.first_report': 1,
            'incident.interval': 2,
            'incident.inspection_duration': 1,
            'incident.inspection_work': 1,
            'incident.window_end': 12,
            'incident.detection_delay': 12,
            'incident.containment_delay': 3,
            'utility.check_time': 6,
        },
    )
    # Inspection ends at 2. Repair crews start at 7 and finish its extra work at 8.
    assert starts(record, 'incident.report') == [1, 10]
    values = readings(
        record, ['crews.rework_done', 'crews.rework_left', 'incident.paused'], [2, 7, 8, 10, 12]
    )
    assert values['crews.rework_done'] == pytest.approx([0, 0, 1, 1, 2])
    assert values['crews.rework_left'] == pytest.approx([1, 1, 0, 1, 0])
    assert values['incident.paused'] == (False, False, False, True, False)


def test_each_policy_reads_the_same_interval_hold_and_work_once_per_seed():
    spread = json.loads((FOLDER / 'spreads/inspection_spacing.json').read_bytes())
    assert spread['model_hash'] == model().model_hash
    paths = ('incident.spacing', 'incident.report_duration', 'incident.report_work')
    samples = []
    for seed in (41, 42):
        by_run = []
        for name in ('fixed_inspections', 'rapid_fixed_inspections', 'acknowledged_stop'):
            record = simulate(name, 0, spread['set'], seed=seed)
            rows = readings(record, paths, [0])
            by_run.append(tuple(rows[path][0] for path in paths))
            assert len(record.entries('draw')) == len(paths)
        assert by_run[0] == by_run[1] == by_run[2]
        interval, duration, work = by_run[0]
        assert 2 <= interval <= 6 and 1 <= duration <= 3 and 0.5 <= work <= 1.5
        samples.append(by_run[0])
    assert samples[0] != samples[1]


def test_stop_order_and_report_limit_with_the_same_calendar_and_response():
    inputs = {
        'incident.first_report': 0,
        'incident.interval': 0.25,
        'incident.inspection_duration': 0.25,
        'incident.detection_delay': 0.5,
        'incident.containment_delay': 0.5,
        'incident.window_end': 2,
    }
    for name, edits, accepted in (
        ('fixed_inspections', {}, [0, 0.25, 0.5, 0.75]),
        ('acknowledged_stop', {}, [0, 0.25]),
        ('fixed_inspections', {'incident.report_limit': 1}, [0]),
        ('fixed_inspections', {'incident.report_limit': 0}, []),
    ):
        record = simulate(name, 1.1, {**inputs, **edits})
        assert starts(record, 'incident.inspection') == accepted
        if name == 'acknowledged_stop':
            assert starts(record, 'incident.report') == accepted
