"""The regional dispatch clock, conservation of delivered water, and paired sampling."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import napkin
from napkin.engine import edits_for
from napkin.engine.sampling import SamplingSettings, sampled
from napkin.engine.timeline import stocks
from tests.helpers import catalogue_model

AREA = 'water_controls_wipe:lumberton'


def simulate(run, horizon, settings):
    model = catalogue_model(AREA)
    config = model.configure(run, edits_for(model, {'set': settings}))
    record = napkin.run(model.program, replace(config, request=replace(config.request, horizon=horizon)))
    assert record.stop is None and record.end == horizon, record.stopped()
    return record


def readings(record, at):
    paths = [
        'support.waiting',
        'support.completed',
        'support.delivered',
        'support.accepted',
        'support.filtered',
    ]
    return {r.path: r.values[0] for r in napkin.read(record, catalogue_model(AREA).program, paths, [at])}


def batches(record):
    return [e.t for e in record.entries('start') if e.part == 'support.report_batch']


CLOCK = {'responders.recognition_time': 2, 'responders.removal_time': 22, 'relief.start_delay': 0}


def test_fixed_batches_filter_a_notification_at_the_containment_boundary_and_conserve_water():
    record = simulate('support_frequent', 35, {**CLOCK, 'support.limit': 5})
    assert batches(record) == [0, 8, 16, 24, 32]
    row = readings(record, record.end)
    assert row['support.accepted'] == 3 and row['support.filtered'] == 2
    assert row['support.waiting'] == pytest.approx(0, abs=1e-7)
    assert row['support.completed'] == pytest.approx(48)
    # One hundred gallons are actually dispatched from the shared supply for every processed work-hour.
    assert row['support.delivered'] == pytest.approx(48 * 100 / 1e6)


def test_recovery_clock_follows_the_regional_water_dispatch_queue():
    record = simulate('support_recovery', 35, CLOCK)
    assert batches(record) == pytest.approx([0, 18, 34])
    assert readings(record, 2)['support.waiting'] == 16
    assert readings(record, 10)['support.completed'] == pytest.approx(16)
    # Moving the delivery service's start moves queue clearance and the next batch.
    later = simulate('support_recovery', 25, {**CLOCK, 'relief.start_delay': 4})
    assert batches(later) == pytest.approx([0, 22])


def test_single_batch_and_window_use_the_initial_incident_as_their_time_origin():
    settings = {**CLOCK, 'incident.begins': 2, 'support.first_delay': 3, 'support.window': 11}
    assert batches(simulate('support_single', 16, settings)) == [5]
    assert batches(simulate('support_frequent', 22, settings)) == [5, 13]
    assert batches(simulate('standard', 16, settings)) == []


@pytest.mark.parametrize('probe', [-2, 2])
def test_open_cases_compete_for_actual_emergency_water_dispatch(monkeypatch, probe):
    monkeypatch.setattr(stocks, 'LEDGER_PROBE', probe)
    settings = {'responders.recognition_time': 1, 'relief.start_delay': 0, 'support.dispatch_share': 1}
    control = simulate('standard', 4, settings)
    queued = simulate('support_single', 4, settings)
    model = catalogue_model(AREA)
    paths = ['emergency_water_deficit', 'relief.throughput', 'support.delivered']
    ordinary, surge = [
        {v.path: v.values[0] for v in napkin.read(record, model.program, paths, [4])}
        for record in (control, queued)
    ]
    assert ordinary['relief.throughput'] > 0
    assert surge['relief.throughput'] == pytest.approx(0)
    assert surge['support.delivered'] > ordinary['support.delivered']
    # One hour of household demand goes unserved while all dispatch slots are reserved.
    deficit_change_gallons = 1_000_000 * (
        surge['emergency_water_deficit'] - ordinary['emergency_water_deficit']
    )
    assert deficit_change_gallons == pytest.approx(509.58, abs=0.01)


def test_paired_tempo_draws_use_the_same_sampled_spacing_and_workload():
    path = Path(__file__).parents[1] / 'variants/lumberton/spreads/dispatch.json'
    edits = json.loads(path.read_text())
    model = catalogue_model(AREA)
    values = []
    for run in ('support_recovery', 'support_recovery_rapid'):
        config = model.configure(run, edits)
        config = replace(config, request=replace(config.request, horizon=0))
        for seed in (17, 18):
            record = napkin.run(model.program, sampled(config, SamplingSettings(1, seed))[0])
            assert record.stop is None, record.stopped()
            (spacing, batch) = napkin.read(record, model.program, ['support.spacing', 'support.batch'], [0])
            values.append((spacing.values[0], batch.values[0]))
    assert values[:2] == values[2:] and values[0] != values[1]
    assert all(6.4 <= interval <= 9.6 and 12 <= work <= 20 for interval, work in values)
