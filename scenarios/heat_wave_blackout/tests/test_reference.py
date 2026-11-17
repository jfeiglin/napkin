"""The scenario's runs against the independent reference mathematics in outage.py.

Every expected value comes from the oracle, applied to the inputs that the run resolved (read through
the names of the package's tests/oracle-inputs.json) or to explicit edits that the test sets. No value is
copied from an engine output, and no test reads authored wording.

The oracle reads the run's inputs in execution units (`resolved.values`: hours, people, per-hour
rates). `resolved.parameter_values` holds the authored units instead (death rates per year, emergency
visit and heat death rates per day), so it is not used here.
"""

import json
import math
from functools import cache
from itertools import pairwise

import pytest
from scipy.integrate import quad

from napkin.engine import edits_for, evaluate_study, sample_result
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
from scenarios.tests.sources import oracle_inputs
from tests.helpers import catalogue_model

pytestmark = pytest.mark.deep

RUN = 'delayed_refuses'
# The engine's solver tolerance is 1e-9 relative. The oracle's closed forms are exact to rounding and its
# quadratures reach 1e-12, so a relative difference above REL is a disagreement.
REL = 1e-6
# Floors for values near zero. The solver's absolute tolerance is 1e-10 times each quantity's scale
# (docs/engine.md); the measured differences in counts of people stay below 1e-7.
PEOPLE_FLOOR = 1e-6
LEDGER_FLOOR = {
    'supply.resident_hours': 1e-6,
    'outstanding_work': 1e-9,
    'crews.work_left': 1e-9,
    'job.remaining': 1e-9,
    'crews.restoration_cost': 1e-14,
}
COST_FLOOR = 1e-12
GROUPS = ('under_65', 'aged_65_to_74', 'aged_75_and_over')
AGES = ('under_65', '65_to_74', '75_and_over')


@cache
def _study(run, encoded):
    model = catalogue_model('heat_wave_blackout')
    study = evaluate_study(model, edits_for(model, json.loads(encoded)), runs=[run])
    assert study.admissible, study.diagnostics
    return study


def solve(run, edits):
    """The completed study of one run under an edit body, and the oracle's names for the run's inputs.

    The inputs are the run's values in execution units (see the module text).
    """
    study = _study(run, json.dumps(edits, sort_keys=True))
    return study, oracle_inputs('heat_wave_blackout', study.runs[run]['resolved'].values)


def observe(study, run, times):
    """{time: the report's values at that time} for one run, and the run's trace."""
    report = sample_result(study, list(times))['runs'][run]
    rows = {row['t']: row['values'] for row in report['samples']}
    return {t: rows[float(t)] for t in times}, report['trace']


def agrees(value, expected, floor):
    return value == pytest.approx(expected, rel=REL, abs=floor)


def default_values(key):
    """A run's input at its default, to edit another input to the same value."""
    return catalogue_model('heat_wave_blackout').resolve(RUN).values[key]


# --- 1. The restoration ledger ------------------------------------------------------------------------------

# Explicit inputs of the work ledger, so that no case rests on an authored default: the checks end 24 hours
# after the cause is determined, the crews need 12 hours of work, the attacker reacts after a quarter of an
# hour and the stop order reaches it after 2.5 hours. An attacker that refuses stops 60 hours in. The
# timed job is due long after everything else.
LEDGER_BASE = {
    'utility.check_time': 24,
    'crews.work': 12,
    'ai.reaction_time': 0.25,
    'ai.rework_share': 0.3,
    'contractor.review_time': 2,
    'contractor.order_delay': 0.25,
    'contractor.order_transit': 0.25,
    'contractor.removal_time': 60,
    'contractor.cleanup_time': 2,
    'job.run_time': 200,
    'ai.obeys': False,
}
# name: (edits to the base, the attacker changes the settings during switching, what the job does)
LEDGER_CASES = {
    # The stop comes before the switching starts: nothing disturbs the crews.
    'obeys_stops_before_switching': ({'ai.obeys': True}, False, 'not listed'),
    # An attacker that obeys is told late: it changes the settings and the crews stop until it stops.
    'obeys_changes_during_switching': ({'ai.obeys': True, 'contractor.review_time': 40}, True, 'not listed'),
    'refuses_removed_before_switching': (
        {'contractor.removal_time': 6, 'contractor.review_time': 0},
        False,
        'not listed',
    ),
    'refuses_changes_during_switching': ({}, True, 'not listed'),
    # Long checks: the job runs before the switching starts, the attacker refuses until after the job.
    'job_runs_before_switching': (
        {'contractor.removal_time': 120, 'job.run_time': 10},
        True,
        'before switching',
    ),
    'job_runs_while_crews_work': (
        {'ai.obeys': True, 'contractor.cleanup_time': 40, 'job.run_time': 30},
        False,
        'while working',
    ),
    'job_runs_while_crews_stopped': (
        {'contractor.removal_time': 120, 'job.run_time': 60},
        True,
        'while stopped',
    ),
    'job_runs_after_the_stop': (
        {'contractor.removal_time': 30, 'contractor.cleanup_time': 10, 'job.run_time': 35},
        True,
        'while working',
    ),
    # Staff would not cancel the job in time, but power is back before it is due.
    'job_due_after_power_is_back': (
        {'ai.obeys': True, 'contractor.cleanup_time': 45, 'job.run_time': 40},
        False,
        'power back',
    ),
    # The attacker's stop comes after its reaction time, but power is back before the reaction.
    'power_back_before_the_change': (
        {'crews.work': 6, 'ai.reaction_time': 50, 'contractor.removal_time': 120},
        False,
        'not listed',
    ),
    # Equal times, in the order that the specification gives: the attacker's stop goes before its change of
    # the settings, and a cancellation or a completion goes before the job. The next case of each pair is the
    # control, just on the other side of the tie. The times are exact in binary arithmetic.
    'stop_at_the_moment_of_the_change': (
        {'ai.obeys': True, 'contractor.review_time': 24.75},
        False,
        'not listed',
    ),
    'stop_just_after_the_change': ({'ai.obeys': True, 'contractor.review_time': 24.8}, True, 'not listed'),
    'cancellation_at_the_moment_the_job_is_due': (
        {'ai.obeys': True, 'job.run_time': 4.5},
        False,
        'not listed',
    ),
    'cancellation_just_after_the_job_is_due': (
        {'ai.obeys': True, 'job.run_time': 4.4},
        False,
        'before switching',
    ),
    'power_back_at_the_moment_the_job_is_due': (
        {'ai.obeys': True, 'contractor.cleanup_time': 45, 'job.run_time': 37},
        False,
        'power back',
    ),
    'job_due_just_before_power_is_back': (
        {'ai.obeys': True, 'contractor.cleanup_time': 45, 'job.run_time': 36.9},
        False,
        'while working',
    ),
}


def ledger_study(overrides, base=None):
    return solve(RUN, {'set': {**(base or LEDGER_BASE), **overrides}})


def ledger_times(ledger):
    """Times just either side of every moment of the timeline, between them, and late."""
    marks = [t for t in ledger.marks() if t > 0.1]
    times = {0.0, ledger.full + 5.0, 300.0, 600.0}
    for t in marks:
        times |= {t - 0.07, t + 0.07}
    times |= {(a + b) / 2 for a, b in pairwise(marks)}
    return sorted(t for t in times if 0.0 <= t <= 1800.0)


def test_ledger_closed_forms():
    # The ledger against closed forms that follow from the specification, on inputs set here. Each regime is
    # solved by hand. S = 10 is the start of the switching, R = 2 the reaction, X = 40 the stop of an attacker
    # that refuses, W = 10 the work and rho = 0.5 the rework share.
    base = {
        'contain_h': 1.0,
        'determination_h': 1.0,
        'check_h': 9.0,
        'work_h': 10.0,
        'obeys': 0.0,
        'react_h': 2.0,
        'rework_share': 0.5,
        'review_h': 0.0,
        'order_delay_h': 0.0,
        'order_transit_h': 0.0,
        'removal_h': 40.0,
        'cleanup_h': 1.0,
        'job_h': 500.0,
        'lineworkers': 10.0,
        'wage': 100.0,
        'cost_multiplier': 2.0,
        'people': 1000.0,
    }
    # A change, no job: c(12) = 2, so A1 = 0.5 * 8 = 4. The crews stop from 12 to 40, then do A1 and the last 8.
    ledger = Ledger(base)
    assert ledger.start == 10.0
    assert ledger.full == 40.0 + 4.0 + 8.0
    assert ledger.state(30.0)[:3] == [2.0, 4.0, 0.0]
    assert ledger.state(42.0)[:3] == [2.0, 2.0, 0.0]
    # The job runs before the switching (J = 3): A2 = 0.5 * 10 = 5. The crews do A2 from 10 to 12 (3 left),
    # so c(12) = 0 and A1 = 5. They stop until 40, then do A2 (3), A1 (5) and all the work (10).
    ledger = Ledger({**base, 'job_h': 3.0})
    assert ledger.job_phase == 'before switching'
    assert ledger.full == 40.0 + 3.0 + 5.0 + 10.0
    assert ledger.state(11.0)[2] == pytest.approx(4.0)
    # The job runs while the crews work (the stop at 11 comes before S + R, so there is no change): c(14) = 4,
    # A2 = 0.5 * 6 = 3, and the crews do A2 and then the last 6.
    ledger = Ledger({**base, 'removal_h': 11.0, 'job_h': 14.0, 'cleanup_h': 5.0})
    assert not ledger.changed
    assert ledger.job_phase == 'while working'
    assert ledger.full == 14.0 + 3.0 + 6.0
    assert ledger.report(15.0)['job.remaining'] == pytest.approx(2.0)
    # The job runs while the crews are stopped (J = 20): c(20) = 2, so A2 = 4. After the stop at 40 the crews
    # do A2 (4), A1 (4) and the last 8.
    ledger = Ledger({**base, 'job_h': 20.0, 'cleanup_h': 30.0})
    assert ledger.job_phase == 'while stopped'
    assert ledger.full == 40.0 + 4.0 + 4.0 + 8.0
    final = ledger.report(1000.0)
    # The cost counts every hour of crew work: 10 initial, 4 + 4 rework, at 10 * 100 * 2 per hour.
    assert final['crews.restoration_cost'] == pytest.approx(18.0 * 10 * 100 * 2 / 1e9)
    # Service is 0 until 10, 0.2 from 12 to 48 (two hours of work done), then rises to 1 at 56, so the deficit
    # is 10 + 2 * 0.9 + 36 * 0.8 + 8 * 0.4 = 43.8 hours.
    assert final['supply.resident_hours'] == pytest.approx(1000.0 * 43.8)
    assert final['outstanding_work'] == 0.0


@pytest.mark.parametrize('case', LEDGER_CASES)
def test_restoration_ledger(case):
    overrides, changed, job = LEDGER_CASES[case]
    study, p = ledger_study(overrides)
    ledger = Ledger(p)
    # The case is what its name says.
    assert (ledger.changed, ledger.job_phase) == (changed, job)
    values, trace = observe(study, RUN, ledger_times(ledger))
    for key, rule, moment in (
        ('start', 'crews.repairs_start', ledger.start),
        ('complete', 'crews.repairs_complete', ledger.full),
        ('back', 'supply.come_back', ledger.full),
    ):
        assert [e['t'] for e in trace if e['rule'] == rule] == [pytest.approx(moment, rel=1e-9, abs=1e-9)], (
            key
        )
    for t, row in values.items():
        for key, expected in ledger.report(t).items():
            assert agrees(row[key], expected, LEDGER_FLOOR[key]), (case, t, key)


# --- 2. Interruption costs ---------------------------------------------------------------------------------

COST_ONLY_CASES = {
    # Switching starts at the latest allowed time: the customers wait the longest.
    'ramp_from_latest_start': {'ai.obeys': True, 'utility.check_time': 72},
    # The earliest start and the shortest work: a short, early ramp.
    'earliest_start_short_ramp': {'ai.obeys': True, 'utility.check_time': 6, 'crews.work': 6},
    # The longest work: customers come back over the longest span.
    'long_ramp': {'ai.obeys': True, 'utility.check_time': 40, 'crews.work': 30},
}
COST_CASES = {**{name: case[0] for name, case in LEDGER_CASES.items()}, **COST_ONLY_CASES}


def cost_times(ledger):
    """The first hours (the cost curve has a corner at 2 hours), then the timeline."""
    return sorted(set(ledger_times(ledger)) | {1.0, 2.0, 3.0, 6.0})


@pytest.mark.parametrize('case', COST_CASES)
def test_interruption_costs_follow_each_customers_own_outage_duration(case):
    study, p = ledger_study(COST_CASES[case])
    ledger = Ledger(p)
    values, _trace = observe(study, RUN, cost_times(ledger))
    for t, row in values.items():
        for key, expected in interruption_costs(p, ledger.profile, t).items():
            assert agrees(row[key], expected, COST_FLOOR), (case, t, key)


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
PARTIAL_CASES = {
    'obeys_without_change': {'ai.obeys': True},
    'refuses_with_change': {},
    'job_before_switching_and_change': {'job.run_time': 3},
}
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
            'ai.obeys': True,
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
            'ai.obeys': True,
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
            'moves.start_time': 4,
            'moves.end_time': 100,
            'heat_wave.length': 48,
            'outreach.start_time': 90,
            **private(0.9),
        },
        'heat',
        'after',
    ),
    'change_and_job_rework': (
        {
            'contractor.removal_time': 120,
            'job.run_time': 60,
            'moves.start_time': 10,
            'moves.end_time': 90,
            'heat_wave.length': 200,
            'outreach.start_time': 60,
            'outreach.reach': 0.8,
            'devices.battery_hours': 6,
            'devices.alternative_share': 0.4,
            **private(0.7),
        },
        'end',
        'during',
    ),
    'outreach_after_restoration': (
        {
            'ai.obeys': True,
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
            'ai.obeys': True,
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
    'default_delayed_refuses': ('delayed_refuses', {}),
    'default_standard_obeys': ('standard_obeys', {}),
    'power_back_inside_heat_wave': ('standard_refuses', {'utility.check_time': 6, 'heat_wave.length': 100}),
    'job_and_change_inside_heat_wave': (
        'delayed_refuses',
        {'utility.check_time': 6, 'heat_wave.length': 100},
    ),
    'window_open_when_the_heat_ends': (
        'standard_refuses',
        {'moves.end_time': 100, 'heat_wave.length': 48, **SHARES_HALF},
    ),
    'window_open_when_power_returns': (
        'early_obeys',
        {'utility.check_time': 6, 'crews.work': 6, 'moves.end_time': 40, **SHARES_HALF},
    ),
    'outreach_before_battery_ends': (
        'delayed_refuses',
        {
            'outreach.start_time': 1,
            'devices.battery_hours': 12,
            'outreach.reach': 1,
            'devices.alternative_share': 0,
        },
    ),
    'more_device_users_late_outreach': (
        'delayed_refuses',
        {
            'outreach.start_time': 96,
            'devices.ventilator_admission': 0.08,
            **{f'{group}.device_share': 0.1 for group in GROUPS},
        },
    ),
    'thresholds_crossed_during_the_rise': ('delayed_refuses', {'heat_wave.outdoor': 30, 'heat_wave.cap': 60}),
    'weighted_curves_and_other_warming': (
        'delayed_refuses',
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
        'delayed_refuses',
        {'homes.iet_off_mean': 29, 'compound_buildings.iet_off_mean': 28, 'heat_wave.cap': 72},
    ),
    # The people per visit is 1 by default, which would hide a wrong factor of it.
    'other_hospital_and_visit_parameters': (
        'delayed_refuses',
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
        'delayed_refuses',
        {'supply.people_served': 120000, 'compound.held': 20000, 'heat_wave.length': 240},
    ),
    'all_backup': (
        'standard_refuses',
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
    _study, p = solve('delayed_refuses', {'set': {}})
    world = Blackout(p, 400.0)
    for t in (3.0, 30.0, 100.0, 400.0):
        for pool, gap in world.conservation(t).items():
            assert gap == pytest.approx(0.0, abs=1e-6), (pool, t)


def test_cumulative_hazards_agree_with_adaptive_quadrature():
    # The Chebyshev antiderivatives in the oracle against quad on the same rates, in a run with a stop and a job.
    _study, p = solve(RUN, {'set': {**LEDGER_BASE, 'contractor.removal_time': 120, 'job.run_time': 60}})
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
