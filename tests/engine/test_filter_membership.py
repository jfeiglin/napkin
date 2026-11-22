"""A moving enclosing operand selects the members of a reduction in the same physical state."""

from unittest.mock import patch

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
MODEL = """scenario "An enclosing stock crosses a selection threshold"
    horizon 2 h
Site:
    input limit: L = 1 L
    input rate: L/h = 2 L/h
early: Site
late: Site
    limit = 4 L
    rate = 3 L/h
yard:
    clock: L = 0 L
    stock: L = 0 L
    flow tick: SOURCE -> this.clock
        request = 1 L/h
    flow fill: SOURCE -> this.stock
        request = formula(sum(Site.instances.where(limit > this.clock).rate))
"""


@pytest.mark.parametrize('limit', [150, 0], ids=['component', 'sparse'])
def test_flow_uses_the_members_selected_by_its_trial_state(limit):
    model = compile_text(MODEL, UNITS)
    with patch('napkin.engine.timeline.plan.LIMIT', limit):
        record = run(model.program, model.configuration)
    assert record.failure is None, record.failure
    rate, stock = read(record, model.program, ['yard.fill.actual_rate', 'yard.stock'], [0.5, 1.5, 2])
    assert rate.values == pytest.approx([5, 3, 3])
    assert stock.values == pytest.approx([2.5, 6.5, 8], abs=3e-7)


@pytest.mark.parametrize(('operation', 'amount'), [('min', 5), ('max', 6)])
def test_filtered_extrema_follow_the_surviving_members(operation, amount):
    model = compile_text(MODEL.replace('sum(Site', f'{operation}(Site'), UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is None, record.failure
    (stock,) = read(record, model.program, ['yard.stock'], [2])
    assert stock.values == pytest.approx([amount], abs=3e-7)


def test_empty_filtered_extremum_has_no_value():
    source = MODEL.replace(
        'flow fill: SOURCE -> this.stock\n        request = formula(sum(Site.instances.where(limit > this.clock).rate))',
        'minimum = formula(min(Site.instances.where(limit < this.clock).rate))',
    )
    model = compile_text(source, UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is None, record.failure
    (minimum,) = read(record, model.program, ['yard.minimum'], [0, 1.5])
    assert 'empty collection' in minimum.values[0].reason
    assert minimum.values[1] == 2
