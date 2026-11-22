"""Publication choices and conditional parity with the saved 8488047 civilian results."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import napkin
from napkin.engine.study import edits_for
from scenarios.heat_wave_blackout.tests.support import model, readings, study
from tools.publish.brief import brief_of


def test_brief_selects_cooling_responses_to_the_same_outage():
    brief = brief_of(model())
    assert tuple(brief.featured) == ('standard', 'early_cooling')
    assert brief.choice_group == 'Cooling response'
    assert {'supply.resident_hours', 'places.admissions', 'device_admissions'} <= set(brief.show)


def test_private_moves_at_outage_and_outreach_at_hour_one():
    current = model()
    # Keep temperature constant in this opening-round test. The full health
    # and restoration trajectories are compared to the deep independent oracle.
    constant = {
        f'{building}.{field}': 28
        for building in ('homes', 'compound_buildings')
        for field in ('iet_on', 'iet_off_mean')
    }
    inputs = {'moves.start_time': 0, 'outreach.start_time': 1, **constant}
    config = current.configure('standard', edits_for(current, {'set': inputs}))
    record = napkin.run(current.program, replace(config, request=replace(config.request, horizon=1.01)))
    assert record.failure is None, record.failure
    assert [event.t for event in record.entries('fire') if event.part == 'moves.opens.when[0]'] == [0]
    names = [
        'supply.share_restored',
        'residents_under_65.move_well.actual_rate',
        'residents_under_65.moved_h',
    ]
    observed = readings(record, names, [0, record.end])
    assert observed[names[0]] == (0, 0)
    assert observed[names[1]][0] > 0
    assert observed[names[2]][0] == 0
    assert observed[names[2]][1] == pytest.approx(observed[names[1]][0] * record.end)
    assert [event.t for event in record.entries('fire') if event.part == 'outreach.starts.when[0]'] == [1]
    protected = 'device_users_under_65.supported'
    dark = 'device_users_under_65.dark_h'
    outreach = readings(record, [protected, dark], [0.5, 1])
    assert outreach[protected][0] == 0
    assert outreach[protected][1] == pytest.approx(outreach[dark][0] / 2)
    assert outreach[protected][1] > 0

    # Support days accrue at the current number of people away. A direct
    # initialization from this field would freeze the flow's rate at zero.
    headcount, delivered, days = napkin.read(
        record,
        current.program,
        ['moves.people_away', 'moves.add_person_days.actual_rate', 'moves.person_days'],
        [1],
    )
    assert headcount.values[0] > 0 and days.values[0] > 0
    assert delivered.values[0] * float(current.program.unit(delivered.unit).scale) == pytest.approx(
        headcount.values[0] * float(current.program.unit(headcount.unit).scale)
    )


@pytest.mark.deep
@pytest.mark.parametrize('name', ['standard', 'early_cooling', 'powered_places', 'delayed_cooling'])
def test_civilian_outputs_match_saved_legacy_precision(name):
    expected = json.loads(Path(__file__).with_name('legacy-outcomes.json').read_text())[name]
    record = study(name)
    observed = readings(record, expected, [record.end])
    for path, archived in expected.items():
        value = observed[path][0]
        # The old publisher reports six significant figures and displays values below 1e-6 as zero.
        shown = 0.0 if abs(value) < 1e-6 and archived == 0 else float(format(value, '.6g'))
        assert shown == archived, (name, path, value, archived)


@pytest.mark.deep
def test_delayed_protections_change_cooling_access_during_the_same_outage():
    paths = (
        'places.admissions',
        'compound.gates',
        'confined_under_65.formal_h',
        'residents_under_65.backup_share',
        'residents_under_65.private_share',
        'supply.share_restored',
    )

    def endpoints(name):
        return {path: row[-1] for path, row in readings(study(name), paths, [39]).items()}

    usual = endpoints('delayed_cooling')
    powered = endpoints('delayed_cooling_with_power')
    access = endpoints('delayed_cooling_with_access')
    backup = endpoints('delayed_cooling_with_backup')
    assert usual['places.admissions'] == 0
    assert powered['places.admissions'] > 0 and access['places.admissions'] > 0
    assert powered['compound.gates'] == 'CLOSED' and access['compound.gates'] == 'OPEN'
    assert powered['confined_under_65.formal_h'] == 0 < access['confined_under_65.formal_h']
    assert backup['residents_under_65.backup_share'] == backup['residents_under_65.private_share'] == 0.25
    assert all(
        state['supply.share_restored'] == pytest.approx(usual['supply.share_restored'])
        for state in (powered, access, backup)
    )


@pytest.mark.deep
@pytest.mark.parametrize(
    ('name', 'accepted', 'restored_at'),
    [
        ('standard', 0, 40),
        ('fixed_inspections', 3, 49),
        ('clearance_inspections', 2, 46),
        ('rapid_fixed_inspections', 1, 43),
        ('acknowledged_stop', 1, 43),
    ],
)
def test_named_exercises_account_for_interruption_work_in_the_time_of_service_return(
    name, accepted, restored_at
):
    record = study(name)
    # Nominal repair begins at hour 25 and takes 15 switching hours. Each separate
    # admitted report adds a two-hour hold and one hour of priority reinspection.
    found = readings(
        record, ['incident.accepted', 'crews.rework_done', 'supply.share_restored'], [record.end]
    )
    assert found['incident.accepted'] == found['crews.rework_done'] == (accepted,)
    assert found['supply.share_restored'] == (1,)
    marks = [e.t for e in record.entries('start') if e.part == 'supply.come_back']
    assert marks == pytest.approx([restored_at])
