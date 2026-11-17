"""The live view's frames (`ui/view.py`) against the model, its evidence and the engine's own report.

Each expected value comes from the model, from the package's tests' own finder of the parts of a place
(`family.py`), from the evidence or from the engine's report of the run (`sample_result`), never from the
view's code. The view must show what the run holds, within the rounding of what it sends."""

import bisect
import json
from functools import cache

import pytest
from hypothesis import given
from hypothesis import strategies as st

from napkin import evaluate_study, sample_result
from napkin.package import entries
from scenarios.water_controls_wipe.tests import family
from scenarios.water_controls_wipe.ui import view
from tests.helpers import catalogue_model

ROUNDING = 1e-3  # the view sends rates and volumes to four decimals
PLACES_FILE = view.FOLDER / 'ui/web/src/places.json'


@cache
def described(sid):
    return view.describe(catalogue_model(sid), sid)


@cache
def featured(sid):
    """The engine's study of the run that the page opens with, and the view's frame of it."""
    model = catalogue_model(sid)
    run = described(sid)['featured']
    study = evaluate_study(model, None, runs=[run])
    assert study.admissible, study.diagnostics
    return run, study, view.frame(model, study, run)


@pytest.mark.parametrize('sid', family.places())
def test_each_part_of_a_place_is_shown_once(sid):
    place = described(sid)
    shown = [s['id'] for s in place['systems']]
    assert sorted(shown) == sorted(family.systems(sid))
    assert {t['id']: (t['seller'], t['buyer']) for t in place['ties']} == family.ties(sid)
    homes, hospitals = family.homes(sid), family.hospitals(sid)
    model = catalogue_model(sid)
    for system in place['systems']:
        assert system['hospital_entity'] == hospitals.get(system['id'], '')
        home = homes.get(system['id'])
        expected = model.inputs[f'{home}.population']['value'] if home else 0
        assert system['people'] == pytest.approx(expected, abs=0.5)
    # A seller comes before each of its buyers.
    for tie in place['ties']:
        assert shown.index(tie['seller']) < shown.index(tie['buyer'])


@pytest.mark.parametrize('sid', family.places())
def test_the_hospitals_named_from_the_evidence_are_the_ones_the_model_counts(sid):
    model = catalogue_model(sid)
    for system in described(sid)['systems']:
        if not system['hospital_entity']:
            assert system['hospitals'] == []
            continue
        count = model.inputs[f'{system["hospital_entity"]}.facilities']['value']
        ccns = [h['ccn'] for h in system['hospitals']]
        assert len(ccns) == len(set(ccns)) == count
        assert all(h['name'] for h in system['hospitals'])


def test_the_map_has_a_point_for_each_place_and_no_other():
    points = json.loads(PLACES_FILE.read_text())
    names = {name.split(':', 1)[1] for name in entries(view.FOLDER)}
    assert set(points) == names
    for point in points.values():
        assert -180 <= point['lon'] <= 180 and -90 <= point['lat'] <= 90


def stepped(series, t):
    """The value of a stepped series at `t`: that of its last point at or before `t`."""
    times = [p[0] for p in series]
    return series[max(0, bisect.bisect_right(times, t) - 1)][1]


def straight(series, t):
    """The value of a series read straight between its points, at `t`."""
    times = [p[0] for p in series]
    i = bisect.bisect_right(times, t)
    if i == 0:
        return series[0][1]
    if i == len(series):
        return series[-1][1]
    (t0, v0), (t1, v1) = series[i - 1], series[i]
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1


@pytest.mark.parametrize('sid', family.places())
def test_a_frame_shows_what_its_run_holds(sid):
    run, study, frame = featured(sid)
    place = described(sid)
    horizon = study.runs[run]['trajectory'].horizon
    assert 24 <= frame['t_end'] <= horizon
    for end in (frame['back'], frame['advisory_end']):
        if end is not None:
            assert frame['t_end'] >= min(horizon, end) - ROUNDING

    # The people without water and under an advisory are the model's own outputs at those times. The view
    # sends its times to four decimals, so a point at an event reads the model at the event's own time.
    times = [t for t, _ in frame['out']]
    assert times == sorted(times) and times[0] >= 0 and times[-1] <= frame['t_end']
    events = {e['t'] for e in study.runs[run]['trajectory'].trace}
    exact = {t: [t, *(e for e in events if round(e, 4) == t)] for t in times + [t for t, _ in frame['adv']]}
    asked = sorted({t for found in exact.values() for t in found if t <= horizon})
    report = sample_result(study, asked)['runs'][run]
    rows = {row['t']: row['values'] for row in report['samples']}
    for series, outcome in (
        (frame['out'], 'people_interrupted_now'),
        (frame['adv'], 'people_under_advisory'),
    ):
        for t, people in series:
            assert any(abs(people - rows[u][outcome]) <= 0.5 for u in exact[t] if u in rows), (t, people)
    final = report['reporting_points']['final']['values']
    assert all(0 <= people <= final['people_followed'] + 0.5 for _, people in frame['out'])
    assert frame['person_days'] == final['person_days_lost']
    assert frame['unserved'] == final['unserved_volume']
    assert frame['econ'] == final['economic_loss']
    assert frame['hospital'] == final['hospital_hours_constrained']

    # Each system stays within what it can make, hold, buy and needs; each sale within its connection.
    capacity = {t['id']: t['capacity'] for t in place['ties']}
    for system, flows in frame['flows'].items():
        fixed = frame['fixed'][system]
        assert all(v <= fixed['cap'] + ROUNDING for _, v in flows['prod'])
        assert all(v <= fixed['use'] + ROUNDING for _, v in flows['del'])
        assert all(-ROUNDING <= v <= fixed['full'] + ROUNDING for _, v in flows['stored'])
        # Before the attack, each system meets its own use.
        assert frame['before']['flows'][system]['del'] == pytest.approx(fixed['use'], abs=ROUNDING)
    for tie, series in frame['ties'].items():
        assert all(-ROUNDING <= v <= capacity[tie] + ROUNDING for _, v in series)
    states = set(place['hospital_states'])
    assert all(v in states for series in frame['hospitals'].values() for _, v in series)

    # Each moment happens at a time of the run's trace, in order.
    traced = {round(e['t'], 3) for e in study.runs[run]['trajectory'].trace}
    assert [m['t'] for m in frame['moments']] == sorted(m['t'] for m in frame['moments'])
    assert all(m['t'] in traced and m['last'] in traced and m['times'] >= 1 for m in frame['moments'])


points = st.lists(st.tuples(st.integers(0, 50), st.integers(-3, 3)), min_size=1, max_size=40)


@given(points)
def test_a_compressed_stepped_series_reads_the_same_at_every_time(pairs):
    series = [[float(t), v] for t, v in sorted(dict(pairs).items())]
    kept = view.compress(series, False)
    assert all(stepped(kept, t) == v for t, v in series)


@given(points)
def test_a_compressed_straight_series_reads_the_same_at_every_time(pairs):
    series = [[float(t), float(v)] for t, v in sorted(dict(pairs).items())]
    kept = view.compress(series, True)
    assert all(straight(kept, t) == pytest.approx(v, abs=1e-6) for t, v in series)
