"""The live view's description of each place and its frame of a run, against the model and the public readings."""

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
    # A short horizon with a fractional end keeps the run short and puts the end off the grid.
    record = napkin.run(model.program, replace(config, request=replace(config.request, horizon=51.25)))
    assert record.failure is None
    return model, record, run


FRAME = {
    'run', 'name', 'actor', 't_end', 'horizon', 'model_hash', 'peak', 'back', 'advisory_end', 'person_days',
    'econ', 'hospital', 'unserved', 'out', 'adv', 'moments', 'fixed', 'before', 'flows', 'ties', 'hospitals',
}  # fmt: skip


def test_a_frame_holds_the_public_readings_of_its_run(recorded):
    model, record, run = recorded
    frame = view.frame(model, record, run)
    assert set(frame) == FRAME
    assert frame['run'] == run and frame['model_hash'] == model.model_hash
    assert 0 < frame['t_end'] <= frame['horizon'] == 51.25
    totals = napkin.read(record, model.program, list(view.SHOWN[:4]), [51.25])
    keys = ('person_days', 'econ', 'hospital', 'unserved')
    assert [frame[key] for key in keys] == [row.values[0] for row in totals]
    # Each point of a series is the reading at its time, in the unit that the page shows.
    out = frame['out']
    people = napkin.read(record, model.program, ['people_interrupted_now'], [t for t, _ in out])[0]
    assert [v for _, v in out] == [round(v) for v in people.values]
    stored = frame['flows']['lumberton']['stored']
    finished = napkin.read(record, model.program, ['lumberton.finished'], [t for t, _ in stored])[0]
    assert [v for _, v in stored] == pytest.approx(finished.values, abs=1e-4)
    delivered = frame['flows']['lumberton']['del']
    rate = napkin.read(
        record, model.program, ['lumberton.add_delivered.actual_rate'], [t for t, _ in delivered]
    )[0]
    assert rate.unit == 'Mgal/h'
    assert [v for _, v in delivered] == pytest.approx([24 * v for v in rate.values], abs=1e-4)
    moments = frame['moments']
    assert moments and [m['t'] for m in moments] == sorted(m['t'] for m in moments)
    assert all(m['text'] and '{' not in m['text'] for m in moments)
    assert frame['before']['flows']['lumberton']['ctl'] == 'intact'


def test_an_incomplete_record_is_reported_even_at_the_horizon(recorded):
    model, record, run = recorded
    stopped = replace(
        record, failure=Entry(record.end, 0, 'failure', '', details=(('message', 'model check failed'),))
    )
    assert view.frame(model, stopped, run) == {'errors': [{'message': stopped.stopped()}]}
