"""Cumulative amounts use the allocated rate, including a declared restriction on one pipe."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.declared import DeclaredWay, MovingDeclared
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from tests.engine.resume_parity import assert_resume_parity


@pytest.mark.parametrize('method', [Lines, ComponentWay, Sparse, DeclaredWay, MovingDeclared])
def test_accepted_leg_amounts_use_the_actual_allocation_through_resume(method, monkeypatch):
    moving = method in (ComponentWay, Sparse, MovingDeclared)
    declared = method in (DeclaredWay, MovingDeclared)
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    if method is ComponentWay:
        connect = Plan.connect

        def component(plan, *args, **kwargs):
            return [replace(group, way='component') for group in connect(plan, *args, **kwargs)]

        monkeypatch.setattr(Plan, 'connect', component)
    ceiling = 'formula(1 L/h + t * 1 L/h/h)' if moving else '1 L/h'
    source = f"""scenario "Constrained delivery"
    horizon 1 h
plant:
    stock: L = 10 L in [0,]
    paid: L = 0 L
    local: L = 0 L
    limit = {ceiling}
    flow main: this.stock -> this.paid
        request = 4 L/h
"""
    if not declared:
        source += '        capacity = formula(this.limit)\n'
    source += """    flow other: this.stock -> this.local
        request = 0.25 L/h
    pause = event():
        after 0.5 h
"""
    if declared:
        source += """provider:
    share = solver:
        inputs:
            main = plant.main
            room = plant.limit
        solve_for:
            main.actual_rate
        constraints:
            main.actual_rate <= room
"""
    model = compile_text(source + 'plant.pause.start()\n', {'L': {'volume': 1}, 'h': {'time': 1}})
    direct = Run(Plan.of(model.program, model.configuration))
    record = direct.run()
    assert record.failure is None, record.failure
    pay = (Fraction(5, 8), Fraction(3, 2)) if moving else (Fraction(1, 2), 1)
    local = (Fraction(1, 8), Fraction(1, 4))
    stock = [10 - a - b for a, b in zip(pay, local, strict=True)]
    paths = ['plant.paid', 'plant.local', 'plant.stock', 'plant.main.actual_rate', 'plant.other.actual_rate']
    expected = [pay, local, stock, (1.5, 2) if moving else (1, 1), (0.25, 0.25)]
    for row, amounts in zip(read(record, model.program, paths, [0.5, 1]), expected, strict=True):
        assert row.values == pytest.approx(tuple(map(float, amounts)), rel=0, abs=1e-9)
    live = Run(Plan.of(model.program, model.configuration), [Breakpoint('plant.pause.step[0]')])
    stopped = live.run()
    restored = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(stopped)))
    for machine in (live, restored):
        for at, k in ((0.5, 0), (1, 1)):
            if at == 1:
                assert_resume_parity(model.program, model.configuration, record, machine.resume())
            way = machine.ways.instance_of('plant.main')
            assert type(way) is method
            for leg, amount in [('main', pay[k]), ('other', local[k])]:
                posted = way.transferred(f'plant.{leg}', at)
                assert float(posted) == pytest.approx(float(amount), rel=0, abs=1e-10)
