"""Recovery trajectories at the public scenario entry, including an edited field report."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import napkin

PACKAGE = Path(__file__).resolve().parents[1]
LEGACY = json.loads((PACKAGE / 'tests' / 'recovery-readings.json').read_text())


@pytest.mark.deep
@pytest.mark.parametrize('place', sorted(LEGACY['places']))
def test_six_dates_of_water_recovery_against_the_historical_run(place):
    model = napkin.load_scenario(PACKAGE / 'variants' / place)
    assert not model.reports
    readings = LEGACY['places'][place]
    record = napkin.run(model.program, model.configure(run=LEGACY['run']))
    assert record.failure is None and record.end == LEGACY['hours'][-1]
    for key, row in zip(readings, napkin.read(record, model.program, list(readings), LEGACY['hours'])):
        # Work is the sum of physical queues authored with 1,000-work-hour scales.
        absolute = 1e-5 if key == 'work_remaining' else 1e-8
        assert row.values == pytest.approx(readings[key], abs=absolute, rel=1e-8), (place, key)


@pytest.mark.parametrize('has_report', [False, True])
def test_a_field_report_reopens_repair_and_clearance_only_when_observed(has_report):
    model = napkin.load_scenario(PACKAGE / 'variants' / 'juneau')
    edits = {
        'schema_version': napkin.SCHEMA_VERSION,
        'model_hash': model.model_hash,
        'set': {
            'incident.begins': '4 h',
            'juneau.has_setback': has_report,
            'juneau.setback_at': '200 h',
            'juneau.setback_work': '160 work_h',
        },
    }
    config = model.configure(run='delayed_none', edits=edits)
    record = napkin.run(model.program, replace(config, request=replace(config.request, horizon=330)))
    assert record.failure is None and record.end == 330

    def starts(event):
        return [e.t for e in record.entries('start') if e.owner.split('#')[0] == event]

    assert starts('incident.reported') == [4]
    assert starts('responders.recognized') == [28]
    assert starts('juneau.observed_setback') == ([200] if has_report else [])
    restored = starts('juneau.controls_back')
    samples = starts('juneau.sampling_starts')
    assert len(restored) == len(samples) == (2 if has_report else 1)
    assert 28 < restored[0] < 200
    assert samples == pytest.approx(restored)
    assert starts('juneau.cleared') == pytest.approx([t + 48 for t in samples])
    if has_report:
        assert 200 < restored[1] < 330
    keys = ['juneau.controls', 'juneau.controls_added', 'juneau.controls_work', 'juneau.controls_done']
    state, added, pending, done = napkin.read(record, model.program, keys, [0, 4, 199, 200, 330])
    assert state.values == ('INTACT', 'WIPED', 'RESTORED', 'WIPED' if has_report else 'RESTORED', 'RESTORED')
    assert added.values == (0, 600, 600, 760 if has_report else 600, 760 if has_report else 600)
    assert [work + used for work, used in zip(pending.values, done.values)] == pytest.approx(
        added.values, abs=1e-8
    )
