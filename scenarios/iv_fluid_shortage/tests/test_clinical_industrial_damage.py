"""Independent clinical, toxic-load and resource accounting for this scenario.

Expected values use fixed reference mathematics and math.erf, independently of
production expressions, source adapters, trajectories and presentation builders.
"""

import pytest

from napkin.engine import edits_for, evaluate_study
from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import model as model
from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import run as run
from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import (
    subpar_response as subpar_response,
)

pytestmark = pytest.mark.deep

CLINICAL_PARTITION = 'simulate.4'


def fluid_expected(checkpoint, receipt=528, buffer_days=3, rescue_day=0):
    # 600L/day required;480L/day independent supply;2L/course;10%high-risk.
    end = min(max(0, checkpoint - 6), receipt)
    unserved_high_risk = max(0, end - 120 * buffer_days) * 0.25
    rescued = max(0, end - 120 * buffer_days) * min(0.25, rescue_day / 24)
    unresolved = unserved_high_risk - rescued
    return unresolved * 0.49, unresolved * 0.59


def test_fluid_patient_and_litre_ledgers_support_distinct_damage_counts():
    result, tr = run(
        'iv_fluid_shortage',
        set={'hospitals.days_on_hand': 3},
        options={subpar_response('iv_fluid_shortage'): {'hospitals.rescue_capacity': 0}},
    )
    p = result.runs['subpar']['resolved'].parameter_values
    # Every complete course of the study period's resuscitation demand is eligible, timely or unserved,
    # and the fluid-dependent share of the unserved courses is rescued or unresolved.
    courses = (
        p['resuscitation_reserve.daily_need']
        / 24
        * p['manufacturer.study_length']
        / p['resuscitation_patients.course_volume']
    )
    share = p['high_risk_patients.share']
    for hour in (0, 72, 360, 366, 528, 1440):
        e = tr.env_at(hour)
        assert e['resuscitation_patients.eligible'] + e['resuscitation_patients.timely'] + e[
            'resuscitation_patients.unserved'
        ] == pytest.approx(courses)
        assert e['high_risk_patients.eligible'] + e['high_risk_patients.rescued'] + e[
            'high_risk_patients.unresolved'
        ] == pytest.approx(share * courses)
        assert e['high_risk_patients.rescued'] + e['high_risk_patients.unresolved'] == pytest.approx(
            share * e['resuscitation_patients.unserved']
        )


def test_high_risk_clinical_probability_partition_rejects_inconsistent_edits():
    compiled = model('iv_fluid_shortage')
    result = evaluate_study(
        compiled,
        edits_for(
            compiled,
            {
                'set': {
                    'high_risk_patients.untreated_risk': 1,
                    'high_risk_patients.treated_risk': 0,
                    'high_risk_patients.serious_share': 0.1,
                },
            },
        ),
    )
    assert not result.admissible
    assert any(d.get('code') == f'check:{CLINICAL_PARTITION}' for d in result.diagnostics)


def test_serious_living_cases_fit_actual_untreated_survival():
    compiled = model('iv_fluid_shortage')
    result = evaluate_study(
        compiled,
        edits_for(
            compiled,
            {
                'set': {
                    'hospitals.days_on_hand': 3,
                    'high_risk_patients.untreated_risk': 1,
                    'high_risk_patients.treated_risk': 0.5,
                    'high_risk_patients.serious_share': 0.5,
                },
                'options': {subpar_response('iv_fluid_shortage'): {'hospitals.rescue_capacity': 0}},
            },
        ),
    )
    # Untreated people with fatality probability one leave no survivors to become serious cases.
    assert not result.admissible
    assert any(d.get('code') == f'check:{CLINICAL_PARTITION}' for d in result.diagnostics)
