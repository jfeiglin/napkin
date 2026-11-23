"""A request may switch across a constant capacity. The pump still obeys that capacity."""

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request

MODEL = """plant:
    level: L = 0
    delivered: L = 0
    flow fill: SOURCE -> this.level
        request = formula(2 L/h * t / (1 h))
    flow tap: SOURCE -> this.delivered
        capacity = 1 L/h
        request = formula(2 L/h if this.level > 0.25 L else 0 L/h)
"""


def test_a_pump_keeps_its_hard_cap_when_demand_switches_on():
    program = compile_text(MODEL, {'L': {'volume': 1}, 'h': {'time': 1}}).program
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    paths = [
        'plant.level',
        'plant.tap.request',
        'plant.tap.capacity',
        'plant.tap.actual_rate',
        'plant.delivered',
    ]
    level, request, capacity, actual, delivered = read(record, program, paths, [1.0, 2.0])
    assert level.values == pytest.approx((1, 4))
    assert request.values == pytest.approx((2, 2))
    assert capacity.values == pytest.approx((1, 1))
    # level = t² reaches 0.25 at 0.5 h. The remaining 0.5/1.5 hours use at most 1 L/h.
    assert actual.values == pytest.approx((1, 1))
    assert delivered.values == pytest.approx((0.5, 1.5))


@pytest.mark.parametrize('location', ['tap', 'inflow'])
def test_time_switched_demand_respects_either_ceiling(location):
    endpoint = '        inflow.capacity = 1 L/h\n' if location == 'inflow' else ''
    pipe = '        capacity = 1 L/h\n' if location == 'tap' else ''
    source = (
        'plant:\n    water: L = 0 L\n'
        + endpoint
        + '    flow tap: SOURCE -> this.water\n'
        + pipe
        + '        request = formula(2 L/h if t > 0.5 h else 0 L/h)\n'
    )
    m = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    rec = run(m.program, Configuration(Request(2)))
    assert rec.failure is None
    rate, water = read(rec, m.program, ['plant.tap.actual_rate', 'plant.water'], [1, 2])
    assert (rate.values[0], water.values[-1]) == pytest.approx((1, 1.5))
