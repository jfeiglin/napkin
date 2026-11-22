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
