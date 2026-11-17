"""F5: one fixture that writes every construct of the language once (docs/language.md).

The file formats to itself and reads back to the same parts, and each run's story and outputs match
the values that F5.expect.yaml works out by hand.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.model.ir import thaw
from napkin.model.language import parse
from napkin.model.language.evidence import meaning
from napkin.model.language.format import format_text
from tests.acceptance.helpers import LIBRARY, expectations, fixture
from tests.build import compiled

EXPECTED = expectations('F5')
TIMES = {'mid': 5.0, 'final': 10.0}


def test_the_file_formats_to_itself_and_reads_back_the_same():
    text = fixture('F5')
    assert format_text(text) == text
    written = parse.parse(text)
    again = parse.parse(format_text(text))
    assert meaning(written) == meaning(again)


@pytest.fixture(scope='module')
def model():
    return compiled(fixture('F5'), LIBRARY)


@pytest.mark.parametrize('run', sorted(EXPECTED['runs']))
def test_each_run_has_its_story_outputs_and_health(model, run):
    expected = EXPECTED['runs'][run]
    resolved = model.resolve(run)
    trajectory = simulate(resolved, thaw(LIBRARY))
    assert trajectory.settings['max_step'] == EXPECTED['step_h']
    story = [{'t': entry['t'], 'event': entry['event']} for entry in trajectory.trace if entry['semantic']]
    assert story == expected['story']
    rows = {
        row['t']: row
        for row in evaluate_outputs(
            {'resolved': resolved, 'trajectory': trajectory}, thaw(LIBRARY), sorted(TIMES.values())
        )
    }
    for point, t in TIMES.items():
        for name, value in expected[point].items():
            assert math.isclose(rows[t]['values'][name], value, rel_tol=1e-9, abs_tol=1e-9), (point, name)
        assert rows[t]['statuses']['harm'] == 'unestimated'
    final = trajectory.env_at(TIMES['final'])
    for entity, health in expected['health'].items():
        assert final[f'{entity}.health'] == health
