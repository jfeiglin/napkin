"""The reader's menu and observations against public current-language compilation and simulation."""

import json
from dataclasses import replace

import pytest

import napkin
from napkin.program.record import Entry
from scenarios.water_controls_wipe.tests import family
from scenarios.water_controls_wipe.ui import view
from tests.helpers import catalogue_model


@pytest.mark.parametrize('sid', family.places())
def test_each_authored_service_area_system_and_response_is_available(sid):
    model = catalogue_model(sid)
    description = view.describe(model, sid)
    assert description['key'] == sid.split(':')[1]
    assert description['model_hash'] == model.model_hash
    assert {s['id'] for s in description['systems']} == set(family.systems(sid))
    assert len(description['systems']) == len(family.systems(sid))
    assert all(s['name'] for s in description['systems'])
    assert [r['name'] for r in description['runs'][:3]] == [
        'Early response',
        'Standard response',
        'Delayed response',
    ]
    assert [r['id'] for r in description['runs']] == [
        'early',
        'standard',
        'delayed_none',
        'support_single',
        'support_single_rapid',
        'support_daily',
        'support_daily_rapid',
        'support_frequent',
        'support_frequent_rapid',
        'support_recovery',
        'support_recovery_rapid',
    ]
    assert description['featured'] in [r.name for r in model.declared.runs]


def test_the_map_has_a_point_for_each_place_and_no_other():
    points = json.loads((view.FOLDER / 'ui/web/src/places.json').read_text())
    assert set(points) == {name.split(':', 1)[1] for name in view.places()}
    assert all(-180 <= p['lon'] <= 180 and -90 <= p['lat'] <= 90 for p in points.values())


@pytest.fixture(scope='module')
def recorded():
    sid = 'water_controls_wipe:lumberton'
    model = catalogue_model(sid)
    run = 'early'
    config = model.configure(run)
    # A fractional end tests both exact-hour reads and correct inclusion of a non-grid horizon.
    record = napkin.run(model.program, replace(config, request=replace(config.request, horizon=51.25)))
    assert record.failure is None
    return model, record, run


def test_the_six_hour_frames_and_fractional_time_match_public_readings(recorded):
    model, record, run = recorded
    overview = view.frame(model, record, run)
    assert overview['hours'] == [0, 6, 12, 18, 24, 30, 36, 42, 48, 51.25]
    for frame in [overview, view.frame(model, record, run, 3.375)]:
        assert frame['run'] == run and frame['model_hash'] == model.model_hash
        keys = [*view.AREA, 'lumberton.delivered', 'lumberton.service']
        assert set(frame['readings']) == set(keys)
        for row in napkin.read(record, model.program, keys, frame['hours']):
            measured = frame['readings'][row.path]
            assert measured['unit'] == row.unit
            assert measured['values'] == pytest.approx(row.values), row.path
    assert view.frame(model, record, run, 3.375)['hours'] == [3.375]
    assert record.failure is None and record.end == 51.25


def test_an_incomplete_record_is_reported_even_at_the_horizon(recorded):
    model, record, run = recorded
    stopped = replace(
        record, failure=Entry(record.end, 0, 'failure', '', details=(('message', 'model check failed'),))
    )
    assert view.frame(model, stopped, run) == {'errors': [{'message': stopped.stopped()}]}
