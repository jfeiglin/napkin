"""Independent patient, volume and delayed clinical accounting."""

import pytest

import napkin
from napkin.engine import edits_for
from napkin.engine.report import Lag, report
from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import model, readings, record

pytestmark = pytest.mark.deep


def test_fluid_patient_and_litre_ledgers_support_distinct_damage_counts():
    hours = [0, 72, 360, 366, 528, 1440]
    r = record(**{'hospitals.days_on_hand': 3, 'hospitals.rescue_capacity': 0})
    groups = ['resuscitation_patients', 'high_risk_patients']
    names = ['eligible', 'timely', 'unserved', 'eligible', 'rescued', 'unresolved']
    paths = [
        f'{group}.{quantity}'
        for group, three in zip(groups, (names[:3], names[3:]), strict=True)
        for quantity in three
    ]
    people = readings(r, paths, hours)
    for i, t in enumerate(hours):
        unserved = max(0, min(t, 528) - 360) * 2.5
        assert sum(people[k][i] for k in paths[:3]) == pytest.approx(18000)
        assert sum(people[k][i] for k in paths[3:]) == pytest.approx(1800)
        assert people[paths[2]][i] == pytest.approx(unserved)
        assert people[paths[4]][i] + people[paths[5]][i] == pytest.approx(0.1 * unserved)
    keys = [
        'high_risk_patients.deaths',
        'high_risk_patients.serious_survivors',
        'high_risk_patients.casualties',
    ]
    observed = report(
        r, model().program, model().configure('subpar'), keys, hours[1:], {k: Lag(6, 6) for k in keys}
    )
    for row, risk in zip(observed.values, (0.49, 0.10, 0.59), strict=True):
        for t, value in zip(hours[1:], row.values, strict=True):
            assert value == pytest.approx(max(0, min(t - 6, 528) - 360) * 0.25 * risk)


@pytest.mark.parametrize(('treated', 'serious'), [(0, 0.1), (0.5, 0.5)])
def test_high_risk_clinical_probability_partition_rejects_inconsistent_edits(treated, serious):
    compiled = model()
    edits = edits_for(
        compiled,
        {
            'set': {
                'high_risk_patients.untreated_risk': 1,
                'high_risk_patients.treated_risk': treated,
                'high_risk_patients.serious_share': serious,
            }
        },
    )
    trial = napkin.run(compiled.program, compiled.configure('subpar', edits))
    assert trial.end == 0 and trial.failure is not None
    assert trial.failure.detail('message') == 'assert[4]: the assertion does not hold'
