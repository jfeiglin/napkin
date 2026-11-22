"""Publication choices and conditional parity with the saved 8488047 civilian results."""

import json
from pathlib import Path

import pytest

from scenarios.heat_wave_blackout.tests.support import model, readings, study
from tools.publish.brief import brief_of


def test_brief_selects_cooling_responses_to_the_same_outage():
    brief = brief_of(model())
    assert tuple(brief.featured) == ('standard', 'early_cooling')
    assert brief.choice_group == 'Cooling response'
    assert {'supply.resident_hours', 'places.admissions', 'device_admissions'} <= set(brief.show)


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
