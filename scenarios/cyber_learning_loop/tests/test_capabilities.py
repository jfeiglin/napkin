"""Defensive discovery and patching respond to tooling uptake."""

import pytest

from napkin import read
from tests.helpers import catalogue_study


@pytest.mark.parametrize('run_name', ['no_ai', 'ai_fast', 'ai_reversal', 'defenders_ai'])
def test_adoption_changes_the_remediation_pace(workforce_model, run_name):
    record = catalogue_study('cyber_learning_loop', runs=[run_name])[run_name]
    years = [0, 4, 12, 20, 25]
    adoption, closing = read(
        record,
        workforce_model.program,
        ['ai_tools.progress', 'defenders.closing'],
        [year * 8760 for year in years],
    )
    assert all(0 <= value <= 1 for value in adoption.values)
    assert closing.values == pytest.approx([1 + 2 * value for value in adoption.values])
    assert closing.values[0] == 1
    if run_name == 'no_ai':
        assert all(value == 1 for value in closing.values)
