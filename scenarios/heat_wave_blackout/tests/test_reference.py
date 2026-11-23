"""The recovery model against independent work, temperature, population and cost calculations."""

import math

import pytest
from scipy.integrate import quad

from scenarios.heat_wave_blackout.tests.outage import (
    BANDS,
    BUILDINGS,
    Blackout,
    Heat,
    Ledger,
    closed_form_heat,
    customer_cost,
    customer_cost_total,
    device_admissions_without_heat,
    exposure_without_heat,
    interruption_costs,
)
from scenarios.heat_wave_blackout.tests.support import oracle_values, readings, study

pytestmark = pytest.mark.deep

RUN = 'standard'
# The engine's solver tolerance is 1e-9 relative. The oracle's closed forms are exact to rounding and its
# quadratures reach 1e-12, so a relative difference above REL is a disagreement.
REL = 1e-6
# Floors for values near zero. The solver's absolute tolerance is 1e-10 times each quantity's scale
# (docs/engine/README.md, "Tolerances and reproducibility"); the measured differences in counts of people stay below 1e-7.
PEOPLE_FLOOR = 1e-6
LEDGER_FLOOR = {
    'supply.resident_hours': 1e-6,
    'outstanding_work': 1e-9,
    'crews.work_left': 1e-9,
    'extra.work_left': 1e-9,
    'crews.restoration_cost': 1e-14,
}
COST_FLOOR = 1e-12
GROUPS = ('under_65', 'aged_65_to_74', 'aged_75_and_over')
AGES = ('under_65', '65_to_74', '75_and_over')


def solve(run, edits):
    record = study(run, edits.get('set', {}))
    return record, oracle_values(record)


def observe(record, run, times):
    del run
    names = (
        'deaths',
        'heatstroke_survivors',
        'casualties',
        'late_deaths',
        'device_admissions',
        'thermal_exposure',
        *(f'{kind}_{age}.deaths' for kind in ('residents', 'device_users', 'confined') for age in AGES),
    )
    columns = readings(record, names, times)
    return {
        t: {name: values[i] for name, values in columns.items()} for i, t in enumerate(times)
    }, record.trace


def agrees(value, expected, floor):
    return value == pytest.approx(expected, rel=REL, abs=floor)


def default_values(key):
    return readings(study(RUN), [key], [0])[key][0]


LEDGER_BASE = {'utility.check_time': 24, 'crews.work': 12}
HOLD = {'incident.hold': True, 'incident.hold_at': 10, 'incident.hold_duration': 5, 'incident.repeat_work': 3}
EXTRA = {'extra.recorded': True, 'extra.recorded_at': 8, 'extra.hours': 2}


@pytest.mark.parametrize(
    'edits',
    [
        {},
        HOLD,
        EXTRA,
        {**HOLD, **EXTRA},
        {**EXTRA, 'extra.recorded_at': 37},
        {**HOLD, 'incident.hold_at': 0},
        {**HOLD, **EXTRA, 'incident.hold_at': 30, 'extra.recorded_at': 32},
    ],
)
def test_restoration_ledger_and_interruption_cost(edits):
    record, p = solve(RUN, {'set': {**LEDGER_BASE, **edits}})
    ledger = Ledger(p)
    times = sorted({0, 1, 8, 10, 15, 24, 25, 28, 37, 70, 1800, *ledger.marks()})
    names = {**ledger.report(0), **interruption_costs(p, ledger.profile, 0), 'supply.share_restored': 0}
    actual = readings(record, names, times)
    for i, t in enumerate(times):
        expected = {
            **ledger.report(t),
            **interruption_costs(p, ledger.profile, t),
            'supply.share_restored': ledger.service(t),
        }
        for name, v in expected.items():
            assert agrees(actual[name][i], v, LEDGER_FLOOR.get(name, COST_FLOOR)), (t, name)
    assert [event.t for event in record.entries('fire') if event.part == 'crews.repairs_start.when[0]'] == [
        ledger.start
    ]
    assert [event.t for event in record.entries('start') if event.part == 'crews.repairs_complete'] == [
        ledger.full
    ]


def test_cost_integral_agrees_with_quadrature_of_the_cost_curve():
    # The closed form that the oracle uses, against adaptive quadrature of the curve itself.
    for c24, power in ((56.0, 0.66), (13_878.0, 0.55), (3.0, 1.7)):
        for hours in (0.5, 2.0, 7.3, 24.0, 90.0):
            expected = quad(
                lambda u: customer_cost(c24, power, u),
                0.0,
                hours,
                points=[2.0] if hours > 2.0 else None,
                epsabs=0.0,
                epsrel=1e-12,
            )[0]
            assert customer_cost_total(c24, power, hours) == pytest.approx(expected, rel=1e-10)


# --- 3. Heat with no power during the whole heat wave: closed forms ----------------------------------------

# Nobody has a backup, a private move or a device, so every person is in one pool at home.
UNPROTECTED = {
    **{f'residents_{age}.{field}': 0 for age in AGES for field in ('backup_share', 'private_share')},
    **{f'confined_{age}.backup_share': 0 for age in AGES},
    **{f'{group}.device_share': 0 for group in GROUPS},
}
# No power returns during the heat wave: switching starts after the 72 hour checks, the heat wave ends at 60.
NO_POWER = {'utility.check_time': 72, 'heat_wave.length': 60}
# The outdoor temperature at its highest allowed value, above every curve's top: the relative risks are then
# exponential in the temperature, and the solution has a closed form in the exponential integral.
HOT = {'heat_wave.outdoor': 45}
HEAT_TIMES = [0.5, 1.0, 3.0, 5.0, 12.0, 30.0, 59.0, 61.0, 100.0]
CLOSED_FORM_CASES = {
    # The cap is reached about three hours in, the buildings warm differently, and the three bands have
    # different death terms: the under 65s follow the heat death curve, the others the all-cause curve.
    'cap_reached': (
        {
            'heat_wave.cap': 55,
            'under_65.death_rate': 0.0001,
            'aged_65_to_74.death_rate': 0.3,
            'aged_75_and_over.death_rate': 0.3,
            'compound_buildings.iet_off_mean': 31,
            'compound_buildings.heat_up_time': 24,
            'compound_buildings.slope': 0.3,
        },
        True,
    ),
    # As above, with the lowest slope in the homes: a person at home would have far more than one heat emergency
    # visit within the heat wave, so the limit of visits for each person decides the heatstroke.
    'visits_past_the_limit': (
        {
            'heat_wave.cap': 55,
            'under_65.death_rate': 0.0001,
            'aged_65_to_74.death_rate': 0.3,
            'aged_75_and_over.death_rate': 0.3,
            'homes.slope': 0.1,
            'compound_buildings.iet_off_mean': 31,
            'compound_buildings.heat_up_time': 24,
            'compound_buildings.slope': 0.3,
        },
        True,
    ),
    # The highest allowed cap is never reached: a small rise, and four weighted curves.
    'cap_not_reached': (
        {
            'heat_wave.cap': 72,
            'homes.iet_off_mean': 29,
            'compound_buildings.iet_off_mean': 29,
            'heat_wave.gasparrini_weight': 0.4,
            'heat_wave.bobb_weight': 0.3,
            'heat_wave.nordio_weight': 0.2,
            'heat_wave.schwartz_weight': 0.1,
            'heat_wave.heat_death_slope': 0.2,
            'heat_wave.heat_death_rate': 1e-8,
            'under_65.death_rate': 0.0001,
        },
        False,
    ),
}


def closed_form_study(case):
    edits, cap_reached = CLOSED_FORM_CASES[case]
    study, p = solve(RUN, {'set': {**UNPROTECTED, **NO_POWER, **HOT, **edits}})
    heat = Heat(p)
    # The case is what its name says: the temperature reaches the cap early in the heat wave in every
    # building, or in none; and in each band one death term is the larger throughout, as the closed form needs.
    for b in BUILDINGS:
        peak = p['outdoor_c'] + heat.delta[b] / p[f'slope_{b}']
        if cap_reached:
            assert heat.reach_time(b, p['cap_c']) < p['heat_h']
        else:
            assert peak < p['cap_c']
        assert [heat.regime(b, band, p['heat_h']) for band in BANDS] == [
            'heat-death',
            'all-cause',
            'all-cause',
        ]
    return study, p, heat


@pytest.mark.parametrize('case', CLOSED_FORM_CASES)
def test_heat_without_power_matches_closed_form(case):
    study, p, _heat = closed_form_study(case)
    values, _trace = observe(study, RUN, HEAT_TIMES)
    for t, row in values.items():
        for key, expected in closed_form_heat(p, t).items():
            assert agrees(row[key], expected, PEOPLE_FLOOR), (case, t, key)
    # Only residents and the confined are at risk, and their sums are what the report adds up.
    final = values[HEAT_TIMES[-1]]
    assert final['deaths'] == pytest.approx(
        sum(final[f'{kind}_{age}.deaths'] for kind in ('residents', 'confined') for age in AGES), rel=1e-9
    )
    assert final['casualties'] == pytest.approx(final['deaths'] + final['heatstroke_survivors'], rel=1e-9)
    assert final['late_deaths'] == pytest.approx(
        final['heatstroke_survivors'] * p['severe_share'] * p['late_fatality'], rel=1e-9
    )
    assert final['device_admissions'] == 0.0


def test_the_cap_limits_heat_related_deaths_only():
    # With the cap reached, the all-cause term (the 75 and over) must still follow the uncapped temperature.
    # Counterexample: capping the temperature in the all-cause curve as well gives far fewer deaths.
    study, p, heat = closed_form_study('cap_reached')
    values, _trace = observe(study, RUN, [60.0])
    n0 = (p['people'] - p['held']) * p['share_75'] * (1 - p['devshare_75'])
    assert heat.reach_time('homes', p['cap_c']) < p['heat_h']

    def capped_hazard(t):
        return p['rate_75'] * (heat.rr(min(p['cap_c'], heat.temperature('homes', t))) - heat.rr0)

    points = [x for x in heat.kinks('homes') if x < p['heat_h']]
    wrong = quad(capped_hazard, 0.0, p['heat_h'], points=points, epsabs=0.0, epsrel=1e-12, limit=200)[0]
    capped_deaths = -n0 * math.expm1(-wrong)
    actual = values[60.0]['residents_75_and_over.deaths']
    assert abs(actual - capped_deaths) > 0.5 * actual
    assert agrees(actual, closed_form_heat(p, 60.0)['residents_75_and_over.deaths'], PEOPLE_FLOOR)


def test_each_person_counts_at_most_its_limit_of_heat_emergency_visits():
    # The homes have the lowest slope, so a person at home would have far more expected visits than the limit.
    # Counterexample: heatstroke from every expected visit reaches most of the people at home, many times the
    # heatstroke share of the visits that the limit lets each person count.
    study, p, _heat = closed_form_study('visits_past_the_limit')
    values, _trace = observe(study, RUN, [60.0])
    per_visit = p['heatstroke_share'] * p['people_per_visit'] * (1 - p['heatstroke_fatality'])
    visits = Blackout(p, 60.0).visits_cum('homes')(60.0)
    assert -math.expm1(-per_visit * visits) > 10 * per_visit * p['visit_limit']
    people = sum(
        (p['people'] - p['held']) * p['share_' + band] * (1 - p['devshare_' + band])
        + p['held'] * p['share_' + band]
        for band in BANDS
    )
    assert 0 < values[60.0]['heatstroke_survivors'] <= per_visit * p['visit_limit'] * people


@pytest.mark.parametrize('case', CLOSED_FORM_CASES)
def test_numerical_oracle_matches_closed_form(case):
    # The two independent solutions in the oracle (exponential integral against Chebyshev antiderivatives
    # and pool formulas) agree to rounding.
    _study, p, _heat = closed_form_study(case)
    world = Blackout(p, 100.0)
    for t in HEAT_TIMES:
        for key, expected in closed_form_heat(p, t).items():
            assert world.outputs(t)[key] == pytest.approx(expected, rel=1e-9, abs=1e-9), (case, t, key)


# --- 4. Heat with power returning inside the heat wave ------------------------------------------------------

# Switching starts at 7 hours; the heat wave lasts 100. Each case restores everything inside the heat wave
# and bends the return of power differently.
PARTIAL_BASE = {**LEDGER_BASE, 'utility.check_time': 6, 'heat_wave.length': 100}
PARTIAL_CASES = {'uninterrupted': {}, 'inspection_hold': HOLD, 'queued_inspection': EXTRA}
PARTIAL_TIMES = [1.0, 5.0, 7.5, 15.0, 30.0, 59.0, 70.0, 80.0, 99.0, 101.0, 200.0]


@pytest.mark.parametrize('case', PARTIAL_CASES)
def test_partial_restoration_deaths_match_quadrature(case):
    study, p = solve(RUN, {'set': {**UNPROTECTED, **PARTIAL_BASE, **PARTIAL_CASES[case]}})
    world = Blackout(p, max(PARTIAL_TIMES))
    # Service rises inside the heat wave and power is back before it ends.
    assert 0.0 < world.ledger.start < world.ledger.full < p['heat_h']
    values, _trace = observe(study, RUN, PARTIAL_TIMES)
    residents = p['people'] - p['held']
    pools = [  # (entity, building, band, people at risk)
        (f'residents_{age}', 'homes', band, residents * p['share_' + band] * (1 - p['devshare_' + band]))
        for band, age in zip(BANDS, AGES, strict=True)
    ] + [
        (f'confined_{age}', 'compound', band, p['held'] * p['share_' + band])
        for band, age in zip(BANDS, AGES, strict=True)
    ]
    for t, row in values.items():
        total = 0.0
        for entity, building, band, size in pools:
            # Deaths from the cumulative hazard, by adaptive quadrature of the hazard rate cut at its kinks.
            hazard = quad(
                lambda u: world.death_rate(building, band, u),
                0.0,
                t,
                points=[x for x in world.base_breaks if 0.0 < x < t] or None,
                epsabs=0.0,
                epsrel=1e-13,
                limit=500,
            )[0]
            deaths = -size * math.expm1(-hazard)
            total += deaths
            assert agrees(row[entity + '.deaths'], deaths, PEOPLE_FLOOR), (case, t, entity)
        assert agrees(row['deaths'], total, PEOPLE_FLOOR), (case, t)
        # Everything else, from the pools of the oracle.
        for key, expected in world.outputs(t).items():
            assert agrees(row[key], expected, PEOPLE_FLOOR), (case, t, key)


# --- 5. No heat hazard: device admissions, moves and exposure ----------------------------------------------


def no_heat():
    """Edits that give both kinds of building the same felt temperature without power as with it."""
    return {
        'homes.iet_off_mean': default_values('homes.iet_on'),
        'compound_buildings.iet_off_mean': default_values('compound_buildings.iet_on'),
    }


def private(share):
    return {f'residents_{age}.private_share': share for age in AGES}


# name: (edits to the base, what closes the private move window first, where the outreach move falls: with
# the power off everywhere, during the return, or after it). No output can show what happens to the moves
# after power is back or the heat has ended, since nobody is exposed then; the cases set the window so that
# it is still open at those moments, and the outputs depend on the moves up to them.
NO_HEAT_CASES = {
    'move_before_switching': (
        {
            'utility.check_time': 72,
            'outreach.start_time': 40,
            'moves.start_time': 4,
            'moves.end_time': 28,
        },
        'end',
        'off',
    ),
    'window_open_when_power_returns': (
        {
            'utility.check_time': 6,
            'crews.work': 6,
            'moves.start_time': 4,
            'moves.end_time': 40,
            'outreach.start_time': 10,
            **private(0.6),
        },
        'restoration',
        'during',
    ),
    'window_open_when_the_heat_ends': (
        {
            'utility.check_time': 72,
            'moves.start_time': 4,
            'moves.end_time': 100,
            'heat_wave.length': 48,
            'outreach.start_time': 90,
            **private(0.9),
        },
        'heat',
        'after',
    ),
    'outreach_after_restoration': (
        {
            'utility.check_time': 6,
            'crews.work': 6,
            'moves.start_time': 4,
            'moves.end_time': 28,
            'outreach.start_time': 40,
        },
        'restoration',
        'after',
    ),
    'move_before_battery_ends': (
        {
            'utility.check_time': 72,
            'outreach.start_time': 1,
            'devices.battery_hours': 12,
            'outreach.reach': 1,
            'devices.alternative_share': 0,
            'moves.start_time': 4,
            'moves.end_time': 28,
        },
        'end',
        'off',
    ),
}
NO_HEAT_TIMES = [0.0, 1.0, 3.0, 4.0, 10.0, 20.0, 28.0, 36.0, 47.5, 60.0, 80.0, 100.0, 130.0, 200.0, 400.0]


@pytest.mark.parametrize('case', NO_HEAT_CASES)
def test_device_admissions_moves_and_exposure_without_heat_match_closed_forms(case):
    edits, window_limit, outreach = NO_HEAT_CASES[case]
    study, p = solve(RUN, {'set': {**LEDGER_BASE, **no_heat(), **edits}})
    ledger = Ledger(p)
    profile = ledger.profile
    # The case is what its name says.
    limits = {'end': p['moves_end_h'], 'restoration': ledger.full, 'heat': p['heat_h']}
    assert min(limits, key=limits.get) == window_limit
    service = profile.service(p['outreach_h'])
    assert {'off': service == 0.0, 'during': 0.0 < service < 1.0, 'after': service == 1.0}[outreach]
    values, _trace = observe(study, RUN, NO_HEAT_TIMES)
    for t, row in values.items():
        assert agrees(
            row['device_admissions'], device_admissions_without_heat(p, profile, t), PEOPLE_FLOOR
        ), (case, t)
        assert agrees(row['thermal_exposure'], exposure_without_heat(p, profile, t), PEOPLE_FLOOR), (
            case,
            t,
        )
        # With no hazard, nobody dies and nobody falls seriously ill.
        for key in ('deaths', 'heatstroke_survivors', 'casualties', 'late_deaths'):
            assert row[key] == pytest.approx(0.0, abs=1e-9), (case, t, key)


# --- 6. All mechanisms together -----------------------------------------------------------------------------

ALL_TIMES = [0.5, 2.0, 5.0, 10.0, 24.0, 28.0, 36.0, 48.0, 72.0, 100.0, 120.0, 150.0, 200.0, 400.0]
SHARES_HALF = {f'residents_{age}.private_share': 0.5 for age in AGES}
ALL_CASES = {
    'default': ('standard', {}),
    'early_outreach': ('early_cooling', {}),
    'power_back_inside_heat_wave': ('standard', {'utility.check_time': 6, 'heat_wave.length': 100}),
    'inspection_and_extra_work_inside_heat_wave': (
        'standard',
        {'utility.check_time': 6, 'heat_wave.length': 100, **HOLD, **EXTRA},
    ),
    'window_open_when_the_heat_ends': (
        'standard',
        {'moves.end_time': 100, 'heat_wave.length': 48, **SHARES_HALF},
    ),
    'window_open_when_power_returns': (
        'early_cooling',
        {'utility.check_time': 6, 'crews.work': 6, 'moves.end_time': 40, **SHARES_HALF},
    ),
    'outreach_before_battery_ends': (
        'standard',
        {
            'outreach.start_time': 1,
            'devices.battery_hours': 12,
            'outreach.reach': 1,
            'devices.alternative_share': 0,
        },
    ),
    'more_device_users_late_outreach': (
        'standard',
        {
            'outreach.start_time': 96,
            'devices.ventilator_admission': 0.08,
            **{f'{group}.device_share': 0.1 for group in GROUPS},
        },
    ),
    'thresholds_crossed_during_the_rise': ('standard', {'heat_wave.outdoor': 30, 'heat_wave.cap': 60}),
    'weighted_curves_and_other_warming': (
        'standard',
        {
            'heat_wave.gasparrini_weight': 0.4,
            'heat_wave.bobb_weight': 0.3,
            'heat_wave.nordio_weight': 0.2,
            'heat_wave.schwartz_weight': 0.1,
            'homes.heat_up_time': 6,
            'compound_buildings.heat_up_time': 48,
            'homes.slope': 0.1,
            'compound_buildings.slope': 0.4,
        },
    ),
    'cap_not_reached': (
        'standard',
        {'homes.iet_off_mean': 29, 'compound_buildings.iet_off_mean': 28, 'heat_wave.cap': 72},
    ),
    # The people per visit is 1 by default, which would hide a wrong factor of it.
    'other_hospital_and_visit_parameters': (
        'standard',
        {
            'hospitals.heatstroke_share': 0.08,
            'hospitals.people_per_visit': 0.5,
            'hospitals.heatstroke_fatality': 0.06,
            'hospitals.severe_share': 0.2,
            'heat_wave.ed_slope': 0.12,
            'heat_wave.ed_threshold': 36,
            'heat_wave.ed_rate': 2e-6,
        },
    ),
    'largest_population': (
        'standard',
        {'supply.people_served': 120000, 'compound.held': 20000, 'heat_wave.length': 240},
    ),
    'all_backup': (
        'standard',
        {
            **{f'residents_{age}.backup_share': 1 for age in AGES},
            **{f'confined_{age}.backup_share': 1 for age in AGES},
        },
    ),
}


@pytest.mark.parametrize('case', ALL_CASES)
def test_all_mechanisms_match_the_oracle(case):
    run, edits = ALL_CASES[case]
    study, p = solve(run, {'set': edits})
    world = Blackout(p, max(ALL_TIMES))
    values, _trace = observe(study, run, ALL_TIMES)
    for t, row in values.items():
        for key, expected in world.outputs(t).items():
            assert agrees(row[key], expected, PEOPLE_FLOOR), (case, t, key)


# --- 7. Checks of the oracle itself, without the engine's results -------------------------------------------


def test_oracle_accounts_for_every_person():
    # Each pool's people at home, dead, admitted, moved and gone add up to the pool's size, although the
    # deaths are integrated separately from the survivors.
    _study, p = solve('standard', {'set': {}})
    world = Blackout(p, 400.0)
    for t in (3.0, 30.0, 100.0, 400.0):
        for pool, gap in world.conservation(t).items():
            assert gap == pytest.approx(0.0, abs=1e-6), (pool, t)


def test_cumulative_hazards_agree_with_adaptive_quadrature():
    # The Chebyshev antiderivatives in the oracle against quad on the same rates, in a run with a hold and extra work.
    _study, p = solve(RUN, {'set': {**LEDGER_BASE, **HOLD, **EXTRA}})
    world = Blackout(p, 300.0)
    for building, band in (('homes', 'under_65'), ('homes', '75'), ('compound', '65_74')):
        cumulative = world.death_cum(building, band)
        for t in (2.0, 17.0, 90.0, 300.0):
            expected = quad(
                lambda u: world.death_rate(building, band, u),
                0.0,
                t,
                points=[x for x in world.base_breaks if 0.0 < x < t] or None,
                epsabs=0.0,
                epsrel=1e-13,
                limit=500,
            )[0]
            assert cumulative(t) == pytest.approx(expected, rel=1e-10, abs=1e-14)
    # The expected visits in each building, and the heatstroke hazard, which is the closed form of the visits
    # that count: each against the quadrature of its rate.
    for name, building in (('visits', 'homes'), ('visits', 'compound'), ('illness', 'homes')):
        cumulative = world.visits_cum(building) if name == 'visits' else world.illness_cum(building)
        rate = world.visit_rate if name == 'visits' else world.illness_rate
        for t in (4.0, 50.0):
            expected = quad(
                lambda u: rate(building, u),
                0.0,
                t,
                points=[x for x in world.base_breaks if 0.0 < x < t] or None,
                epsabs=0.0,
                epsrel=1e-13,
                limit=500,
            )[0]
            assert cumulative(t) == pytest.approx(expected, rel=1e-10, abs=1e-14), (name, building, t)
