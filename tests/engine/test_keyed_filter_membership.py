"""A continuously changing filter can select a new row while the lookup key stays fixed."""

from unittest.mock import patch

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
MODEL = """scenario "A filtered lookup changes with the enclosing clock"
    horizon 2 h
Site:
    input limit: L = 1 L
    input rank = 2
    input rate: L/h = 2 L/h
early: Site
late: Site
    limit = 4 L
    rank = 1
    rate = 3 L/h
yard:
    clock: L = 0 L
    stock: L = 0 L
    flow tick: SOURCE -> this.clock
        request = 1 L/h
    flow fill: SOURCE -> this.stock
        request = formula(Site.instances.where(limit > this.clock).by(rank).at(KEY).rate)
"""


@pytest.mark.parametrize('key', ['999', '999 + t / (1 h)'], ids=['fixed-key', 'moving-key'])
@pytest.mark.parametrize('limit', [150, 0], ids=['normal', 'sparse'])
def test_filtered_lookup_switches_at_the_membership_boundary(key, limit):
    model = compile_text(MODEL.replace('KEY', key), UNITS)
    with patch('napkin.engine.timeline.plan.LIMIT', limit):
        record = run(model.program, model.configuration)
    assert record.failure is None, record.failure
    # At 1 h the higher-ranked row leaves. Both keys are always above both ranks.
    times = [0.5, 1.5, 2]
    rate, stock = read(record, model.program, ['yard.fill.actual_rate', 'yard.stock'], times)
    assert rate.values == pytest.approx([2, 3, 3])
    assert stock.values == pytest.approx([1, 3.5, 5], abs=3e-7)


def test_a_fixed_lookup_key_exposes_both_ends_of_short_eligibility():
    # The high-ranked flow is available for 0.02 h, then the starting row returns.
    source = MODEL.replace('KEY', '999').replace(
        'input limit: L = 1 L', 'input limit: L = 1.01 L\n    input opening: L = 0.99 L'
    ).replace('limit = 4 L', 'limit = 4 L\n    opening = 0 L')
    source = source.replace('limit > this.clock', 'opening <= this.clock and limit > this.clock')
    model = compile_text(source, UNITS)
    with patch('napkin.engine.timeline.plan.LIMIT', 0):
        record = run(model.program, model.configuration)
    assert record.failure is None, record.failure
    rate, stock = read(record, model.program, ['yard.fill.actual_rate', 'yard.stock'], [0.5, 1, 1.5, 2])
    assert rate.values == pytest.approx([3, 2, 3, 3])
    assert stock.values == pytest.approx([1.5, 2.99, 4.48, 5.98], abs=3e-7)
