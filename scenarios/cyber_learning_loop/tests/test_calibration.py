"""Capacity gains are calibrated against the workforce model's authored role assumptions."""

import pytest

from napkin import read
from tests.helpers import catalogue_study


@pytest.mark.parametrize('name', ['no_ai', 'ai_fast', 'ai_reversal'])
def test_capacity_uplift_follows_adoption_without_changing_headcount(workforce_model, name):
    record = catalogue_study('cyber_learning_loop', runs=[name])[name]
    years = (0, 5, 15, 25)
    for role, adoption_path, gain in (
        ('researchers', 'ai_tools.review_progress', 0.5),
        ('operators', 'ai_tools.progress', 0.2),
        ('collection_specialists', 'ai_tools.progress', 0.3),
    ):
        staff, capacity, adoption = read(
            record,
            workforce_model.program,
            [f'{role}.people', f'{role}.capacity', adoption_path],
            [year * 8760 for year in years],
        )
        assert staff.values == pytest.approx([staff.values[0]] * len(years))
        assert capacity.values == pytest.approx([staff.values[0] * (1 + gain * x) for x in adoption.values])
        assert capacity.values[0] == pytest.approx(staff.values[0])
