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


@pytest.mark.deep
@pytest.mark.parametrize('name', ['standard', 'early_cooling', 'powered_places'])
def test_civilian_outputs_match_saved_legacy_precision(name):
    expected = json.loads(Path(__file__).with_name('legacy-outcomes.json').read_text())[name]
    record = study(name)
    observed = readings(record, expected, [record.end])
    for path, archived in expected.items():
        value = observed[path][0]
        # The old publisher reports six significant figures and displays values below 1e-6 as zero.
        shown = 0.0 if abs(value) < 1e-6 and archived == 0 else float(format(value, '.6g'))
        assert shown == archived, (name, path, value, archived)
