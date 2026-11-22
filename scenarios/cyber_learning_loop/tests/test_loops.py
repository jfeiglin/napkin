"""The workforce's staffing and budget and its defensive response to observed volume."""

import pytest

from napkin import read
from napkin.engine import edits_for
from napkin.engine.study import study
from tests.helpers import catalogue_study


@pytest.mark.parametrize('run_name', ['no_ai', 'surge_today'])
def test_temporary_funding_expires_without_changing_base_staff(workforce_model, run_name):
    record = catalogue_study('cyber_learning_loop', runs=[run_name])[run_name]
    paths = ['leadership.experts', 'leadership.surge_experts', 'leadership.payroll']
    years = (0, 1, 4, 12, 25)
    staff, extra, payroll = read(record, workforce_model.program, paths, [year * 8760 for year in years])
    assert staff.values == pytest.approx([40535] * len(years))
    # A quarter-billion per year pays staff at 0.42 million per person-year for four years.
    funding = [0.25 if run_name == 'surge_today' and year < 4 else 0 for year in years]
    assert extra.values == pytest.approx([amount * 1000 / 0.42 for amount in funding])
    assert payroll.values == pytest.approx([40535 * 0.42 / 1000 + amount for amount in funding])


@pytest.mark.parametrize('multiple', [1, 3, 10, 100])
def test_defensive_attention_is_bounded_under_increased_observed_volume(workforce_model, multiple):
    edits = edits_for(workforce_model, {'set': {'observations.initial': multiple}})
    record = study(workforce_model, runs=['no_ai'], edits=edits)['no_ai']
    target = read(record, workforce_model.program, ['defenders.attention_target'], [0])[0].values[0]
    initial, cap = 0.05, 6
    assert target == pytest.approx(initial * cap * multiple / (multiple + cap - 1))
    assert initial <= target < initial * cap
    if multiple > 1:
        assert target < initial * multiple
