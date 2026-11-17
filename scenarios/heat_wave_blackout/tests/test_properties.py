"""Properties of the scenario: no rise in the felt temperature adds no heat harm, the harm moves the right way with the
cap and the slope, each person counts at most the limit of heat emergency visits, empty groups come to no
harm, cooled places without power never open, every person on the supply is counted once, and no power is back
before the crews start to switch."""

import itertools

import pytest

from napkin.engine import sample_result
from tests.helpers import catalogue_study

RUN = 'delayed_refuses'
GROUPS = ('residents', 'device_users', 'confined')
BANDS = ('under_65', '65_to_74', '75_and_over')
ENTITIES = [f'{group}_{band}' for group, band in itertools.product(GROUPS, BANDS)]


def final(edits, run=RUN):
    study = catalogue_study('heat_wave_blackout', edits, runs=[run])
    assert study.admissible, study.diagnostics
    return study, sample_result(study)['runs'][run]['reporting_points']['final']['values']


def test_no_rise_in_the_felt_temperature_adds_no_heat_harm():
    still = {f'{b}.{f}': 28 for b in ('homes', 'compound_buildings') for f in ('iet_on', 'iet_off_mean')}
    _, values = final({'set': still})
    assert values['deaths'] == 0
    assert values['heatstroke_survivors'] == 0
    assert values['late_deaths'] == 0
    # The homes still have no power, so the people on home devices are still admitted.
    assert values['device_admissions'] > 0


@pytest.mark.parametrize(
    ('name', 'levels', 'rising'),
    [('heat_wave.cap', (55, 63, 72), True), ('homes.slope', (0.1, 0.2, 0.4), False)],
)
def test_heat_harm_moves_with_the_cap_and_against_the_slope(name, levels, rising):
    deaths = [final({'set': {name: level}})[1]['deaths'] for level in levels]
    ordered = deaths if rising else deaths[::-1]
    assert all(a < b for a, b in itertools.pairwise(ordered)), deaths


def test_each_person_counts_at_most_the_limit_of_heat_emergency_visits():
    # With the lowest slope a person at home would have far more expected visits than the limit. No group then has
    # more heatstroke survivors than the heatstroke share of the visits that its people can count. Counterexample:
    # heatstroke from every expected visit reaches most of the people at home.
    study, _values = final({'set': {'homes.slope': 0.1, 'compound_buildings.slope': 0.1}})
    inputs = study.runs[RUN]['resolved'].values
    limit = inputs['heat_wave.visit_limit']
    per_person = (
        inputs['hospitals.heatstroke_share']
        * inputs['hospitals.people_per_visit']
        * (1 - inputs['hospitals.heatstroke_fatality'])
        * limit
    )
    env = study.runs[RUN]['trajectory'].env_at(1800)
    assert env['homes.visits'] > 10 * limit and env['compound_buildings.visits'] > 10 * limit
    for entity in ENTITIES:
        assert 0 < env[f'{entity}.survivors'] <= per_person * env[f'{entity}.population'], entity


def test_empty_groups_come_to_no_harm():
    edits = {
        'set': {'compound.held': 0}
        | {f'{band}.device_share': 0 for band in ('under_65', 'aged_65_to_74', 'aged_75_and_over')}
    }
    _, values = final(edits)
    for entity in ENTITIES:
        if not entity.startswith('residents'):
            assert values[f'{entity}.deaths'] == 0, entity
    assert values['device_admissions'] == 0
    assert values['deaths'] > 0


def test_cooled_places_without_power_never_open():
    study, values = final({'set': {'places.powered_share': 0}}, run='early_refuses')
    assert values['places.admissions'] == 0
    trace = sample_result(study)['runs']['early_refuses']['trace']
    assert not any(entry['rule'] == 'places.opens' for entry in trace)


def test_cooled_places_with_power_admit_no_more_than_their_places():
    study, values = final({'set': {'places.powered_share': 1}}, run='early_refuses')
    p = study.runs['early_refuses']['resolved'].parameter_values
    places = p['places.capacity_share'] * p['places.powered_share'] * p['supply.people_served']
    assert 0 < values['places.admissions'] <= places * (1 + 1e-9)


def test_every_person_on_the_supply_is_counted_once():
    study, values = final({'set': {'supply.people_served': 50000, 'compound.held': 5000}})
    trajectory = study.runs[RUN]['trajectory']
    for t in (0, 48, 1800):
        env = trajectory.env_at(t)
        assert sum(env[f'{e}.population'] for e in ENTITIES) == pytest.approx(50000, rel=1e-12)
    assert values['casualties'] == pytest.approx(values['deaths'] + values['heatstroke_survivors'], rel=1e-12)
    assert values['late_deaths'] <= values['heatstroke_survivors']


def test_no_power_is_back_before_the_crews_start_to_switch():
    # Only the crews' switching brings a circuit back, and the crews start to switch at the event repairs_start.
    # So in every run, at each time before that event, the share of the supply restored is exactly zero and the
    # supply reads as failed. Counterexample: the share read the work done while the supply was off, and the
    # status read a solver remainder of about 1e-27 hours of work as "Power partly restored" from half an hour on.
    study = catalogue_study('heat_wave_blackout')
    report = sample_result(study, reporting_times=[k / 2 for k in range(100)])
    for run, data in report['runs'].items():
        start = next(entry['t'] for entry in data['trace'] if entry['rule'] == 'crews.repairs_start')
        before = [(row, health) for row, health in zip(data['samples'], data['health']) if row['t'] < start]
        assert len(before) > 10, run
        for row, health in before:
            assert row['values']['supply.share_restored'] == 0, (run, row['t'])
            assert health['entities']['supply']['health'] == 'failed', (run, row['t'])
