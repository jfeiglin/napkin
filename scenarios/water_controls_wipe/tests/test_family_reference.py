"""The places of the package against their independent reference mathematics: the water balance that decides when a
system's stored water runs out, the processor sharing that decides when the shared crews finish each
system's controls, the value-added loss in closed form and the smallest capacity that bounds emergency
water. Each runs on the places whose shape it needs; the inputs come from the run, under the oracle's own
names (each place's oracle-inputs.json) and, for each system, under the names that the model gives it."""

import math

import pytest

from napkin.engine import sample_result
from scenarios.tests.sources import oracle_inputs
from scenarios.water_controls_wipe.tests import family
from scenarios.water_controls_wipe.tests.water_service import (
    gross_loss,
    net_loss,
    relief_throughput,
    shared_completion_times,
    store_empty_time,
)
from tests.helpers import catalogue_study

pytestmark = pytest.mark.deep

RUN = 'delayed_kept'
QUIET = 'delayed_none'
PLACES = family.places()
ONE_SYSTEM = [sid for sid in PLACES if len(family.systems(sid)) == 1]
MANY_SYSTEMS = [sid for sid in PLACES if len(family.systems(sid)) >= 3]


def solved(sid, edits, run=RUN):
    study = catalogue_study(sid, edits, runs=[run]) if edits else catalogue_study(sid)
    assert study.admissible, [d for d in study.diagnostics if d.get('severity') == 'error']
    values = study.runs[run]['resolved'].values
    return study, values, oracle_inputs(sid, values), sample_result(study)['runs'][run]


def first_time(report, name):
    """The time of the first occurrence of an event's outcome (`x.e.done`) in a run's story."""
    for entry in report['trace']:
        if entry.get('semantic') and entry.get('event') == name:
            return entry['t']
    raise AssertionError(f'{name} did not occur')


@pytest.mark.parametrize('sid', ONE_SYSTEM[:3])
def test_the_stored_water_runs_out_as_the_balance_says(sid):
    """With nobody able to run the plant by hand and the pumps still moving water, a system's plants stop
    and it delivers in full from its usable stored water, with its losses, its sales and its purchases from
    outside, until the balance empties it."""
    (system,) = family.systems(sid)
    edits = {'set': {f'{system}.manual_ready': False, f'{system}.pump_disabled': 0}}
    _study, values, _inputs, report = solved(sid, edits, run=QUIET)
    inflow = (
        values[f'{system}.nameplate'] * (1 - values[f'{system}.treat_disabled']) + values[f'{system}.bought']
    )
    expected = store_empty_time(
        values[f'{system}.usable_share'] * values[f'{system}.storage'],
        values[f'{system}.demand'],
        values[f'{system}.loss_share'],
        values[f'{system}.sold'],
        inflow,
    )
    assert math.isfinite(expected)
    assert first_time(report, f'{system}.pressure_lost.done') == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize('sid', MANY_SYSTEMS[:2])
def test_the_shared_crews_finish_the_systems_as_processor_sharing_says(sid):
    """Without hidden access, with nobody's manual operation taking crews away and with spares in stock,
    each pool gives every system's job the same share of its hours once it is at work, so the smallest job
    finishes first and each system's controls come back when its last job is done."""
    systems = family.systems(sid)
    edits = {'set': {**{f'{s}.operator_duty': 0 for s in systems}, 'parts.spares_on_hand': 1000}}
    _study, values, inputs, report = solved(sid, edits, run=QUIET)

    def start(pool):
        return inputs['recognition_time'] + sum(
            inputs[f'{pool}_{stage}_time'] for stage in ('request', 'approval', 'travel', 'orientation')
        )

    controls = shared_completion_times(
        [values[f'{s}.controls_load'] for s in systems], inputs['controls_capacity']
    )
    field_jobs = [
        (s, kind) for s in systems for kind in ('field_load', 'replace_load') if values[f'{s}.{kind}'] > 0
    ]
    field = shared_completion_times(
        [values[f'{s}.{kind}'] for s, kind in field_jobs], inputs['field_capacity']
    )
    for i, system in enumerate(systems):
        done = [start('controls') + controls[i]]
        done += [start('field') + t for (s, _kind), t in zip(field_jobs, field, strict=True) if s == system]
        assert first_time(report, f'{system}.controls_back.done') == pytest.approx(max(done), rel=1e-6), (
            system
        )


@pytest.mark.parametrize('sid', ONE_SYSTEM[:3])
def test_the_value_added_loss_follows_the_closed_form(sid):
    """With nobody able to run the plant by hand, the pumps still moving water and no strike on the
    restored controls, the loss accrues only while the system's service is short, and the part that
    businesses can make up decays from the moment its controls come back."""
    (system,) = family.systems(sid)
    edits = {'set': {f'{system}.manual_ready': False, f'{system}.pump_disabled': 0}}
    study, values, _inputs, report = solved(sid, edits, run=QUIET)
    horizon = study.model.time['horizon']
    env = study.runs[QUIET]['trajectory'].env_at(horizon)
    interrupted = env[f'{system}.unserved'] / values[f'{system}.demand']
    assert interrupted > 0
    gross = gross_loss(
        values[f'{system}.va_rate'],
        values[f'{system}.water_dependence'],
        values[f'{system}.activity_kept'],
        values[f'{system}.recovery_factor'],
        interrupted,
    )
    back = first_time(report, f'{system}.controls_back.done')
    expected = net_loss(
        gross, values[f'{system}.catch_up_share'], values[f'{system}.catch_up_time'], horizon - back
    )
    assert env[f'{system}.direct_loss'] + env[f'{system}.recoverable'] == pytest.approx(expected, rel=1e-6)
    assert report['reporting_points']['final']['values']['economic_loss'] * 1e9 == pytest.approx(
        expected, rel=1e-6
    )


@pytest.mark.parametrize('sid', MANY_SYSTEMS[:2])
def test_emergency_water_moves_at_the_smallest_capacity(sid):
    """Emergency water starts after the start delay and never moves faster than the smallest of the
    approved supply, the tankers, the receiving points and the staff; what the people without service needed
    and did not get is the deficit."""
    study, _values, inputs, report = solved(sid, None)
    horizon = study.model.time['horizon']
    env = study.runs[RUN]['trajectory'].env_at(horizon)
    homes = list(family.homes(sid).values())
    received = sum(env[f'{h}.trucked'] for h in family.hospitals(sid).values())
    received += sum(env[f'{home}.received'] for home in homes)
    throughput = relief_throughput(
        inputs['approved_supply'], inputs['transport'], inputs['receiving'], inputs['staffing']
    )
    active = horizon - (inputs['recognition_time'] + inputs['relief_start_delay'])
    assert 0 <= received <= throughput * active * (1 + 1e-9)
    need = sum(env[f'{home}.need_total'] for home in homes)
    households = sum(env[f'{home}.received'] for home in homes)
    values = report['reporting_points']['final']['values']
    assert values['emergency_water_deficit'] == pytest.approx(
        (need - households) / 3785411.784, rel=1e-6, abs=1e-9
    )
