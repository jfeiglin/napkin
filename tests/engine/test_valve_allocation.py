"""Compare the physical rates and integrated deliveries on either side of a valve switch."""

from fractions import Fraction as F

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.declared import MovingDeclared
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
TIMES = (F(49, 100), F(51, 100), F(1), F(2))
SOLVER = """provider:
    share = solver:
        inputs:
            tap = plant.tap
        solve_for:
            tap.actual_rate
"""


def check(model, method, monkeypatch, rates, volumes, *, solver=SOLVER):
    # Force the same local Program through both eligible steppers. Declared expressly owns its tap.
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    program = compile_text(model + (solver if method is MovingDeclared else ''), UNITS).program
    config = Configuration(Request(2))
    # The reference handles smooth polynomial requests on local flows. For the two-flow
    # moving solver control, compare its unconstrained motions to that exact local solution.
    reference = (
        compile_text(model, UNITS).program if solver != SOLVER and method is MovingDeclared else program
    )
    oracle, failure = run_of(reference, config)
    assert failure is None
    machine = Run(Plan.of(program, config))
    record = machine.run()
    assert record.failure is None
    assert isinstance(machine.ways.instance_of('plant.tap'), method)
    keys = [Key('plant', ('tap', 'actual_rate')), Key('plant', ('water',))]
    for key, row, expected in zip(
        keys, read(record, program, keys, list(map(float, TIMES))), (rates, volumes)
    ):
        assert [value_at(oracle, reference, key, t) for t in TIMES] == expected
        assert row.values == pytest.approx(tuple(map(float, expected)), abs=1e-9, rel=1e-9)


@pytest.mark.parametrize('method', [ComponentWay, Sparse, MovingDeclared])
@pytest.mark.parametrize('cap', ['pipe', 'min'])
def test_a_valve_opening_across_its_capacity(method, cap, monkeypatch):
    opening = '2 L/h if t > 0.5 h else 0 L/h'
    model = 'plant:\n    water: L = 0 L\n    flow tap: SOURCE -> this.water\n'
    if cap == 'pipe':
        model += '        capacity = 1 L/h\n'
    else:
        opening = f'min({opening}, 1 L/h)'
    model += f'        request = formula({opening})\n'
    check(model, method, monkeypatch, [0, 1, 1, 1], [0, F(1, 100), F(1, 2), F(3, 2)])


@pytest.mark.parametrize('method', [ComponentWay, Sparse, MovingDeclared])
def test_a_stock_switch_reselects_each_enclosing_operand_and_keeps_the_outgoing_slope(method, monkeypatch):
    # driver = t². At the switch, max jumps from 1/4 to 2, min from 1/4 to 1,
    # and the outer if selects the moving rate t + 1/2. Neither outer limit was crossed on approach.
    model = """plant:
    driver: L = 0 L
    water: L = 0 L
    gate = formula(2 L/h if this.driver > 0.25 L else 0 L/h)
    limited = formula(min(max(this.gate, 0.25 L/h), 1 L/h))
    flow fill: SOURCE -> this.driver
        request = formula(2 L/h * t / (1 h))
    flow tap: SOURCE -> this.water
        request = formula((1 L/h + (t - 0.5 h) / (1 h) * 1 L/h) if this.limited > 0.75 L/h else 0 L/h)
"""
    solver = """provider:
    share = solver:
        inputs:
            tap = plant.tap
            fill = plant.fill
        solve_for:
            tap.actual_rate
            fill.actual_rate
"""
    check(
        model,
        method,
        monkeypatch,
        [0, F(101, 100), F(3, 2), F(5, 2)],
        [0, F(201, 20000), F(5, 8), F(21, 8)],
        solver=solver,
    )


@pytest.mark.parametrize('method', [ComponentWay, Sparse, MovingDeclared])
def test_a_closing_valve_can_remain_on_its_outer_floor(method, monkeypatch):
    # The outer max jumps to a tie and stays there. The other arm of the conditional
    # would divide by zero at closing time and must never be evaluated.
    model = """plant:
    water: L = 0 L
    flow tap: SOURCE -> this.water
        capacity = 4 L/h
        request = formula(max(0 L/h, 0 L/h if t > 0.625 h else (7 L/h if t <= 0.625 h else 1 L/h / ((t - 0.625 h) / (1 h)))))
"""
    check(model, method, monkeypatch, [4, 4, 0, 0], [4 * TIMES[0], 4 * TIMES[1], F(5, 2), F(5, 2)])
