"""Workforce conservation and the reference defensive steady state."""

import pytest

from napkin import read
from napkin.engine import edits_for
from napkin.engine.study import study


@pytest.mark.parametrize('staff', [5000, 40535, 100000])
def test_four_groups_conserve_the_authorized_workforce(workforce_model, staff):
    edits = edits_for(workforce_model, {'set': {'leadership.experts': staff}})
    record = study(workforce_model, runs=['no_ai'], edits=edits)['no_ai']
    paths = [
        f'{group}.people' for group in ('researchers', 'operators', 'collection_specialists', 'analysts')
    ]
    groups = read(record, workforce_model.program, paths, [0, 5 * 8760, 25 * 8760])
    for headcounts in zip(*(group.values for group in groups), strict=True):
        assert all(value > 0 for value in headcounts)
        assert sum(headcounts) == pytest.approx(staff)
        assert headcounts[0] == pytest.approx(0.03 * staff)


def test_reference_workload_keeps_attention_at_its_rest_point(workforce_model):
    record = study(workforce_model, runs=['no_ai'])['no_ai']
    attention, target = read(
        record,
        workforce_model.program,
        ['defenders.alertness', 'defenders.attention_target'],
        [year * 8760 for year in (0, 1, 4, 10, 25)],
    )
    assert attention.values == pytest.approx([0.05] * 5)
    assert attention.values == pytest.approx(target.values)
