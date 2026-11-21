"""A located contact closes its exact stock balance through the incoming physical rates."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.declared import DeclaredWay, MovingDeclared
from napkin.engine.timeline.family import Family
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


def touching(method, direction, monkeypatch, horizon=0.5):
    single = method is Family
    if direction == 'outflow':
        stock, other = '1 L in [0 L,]', '0 L'
        pipe = 'this.stock -> this.'
        ends = [pipe + 'one', pipe + 'two']
    else:
        stock, other = '0 L in [,1 L]', '1 L'
        ends = ['this.one -> this.stock', 'this.two -> this.stock']
    text = f"""scenario "Contact sharing"
    horizon {horizon} h
plant:
    stock: L = {stock}
    one: L = {other}
    two: L = {other}
    flow first: {ends[0]}
        request = {3 if single else 1} L/h
"""
    if not single:
        text += f'    flow second: {ends[1]}\n        request = 2 L/h\n'
    if method in (DeclaredWay, MovingDeclared):
        text += """provider:
    share = solver:
        inputs:
            pipe = plant.first
        solve_for:
            pipe.actual_rate
"""
    model = compile_text(text, UNITS)
    connect = Plan.connect
    kinds = {ComponentWay: 'component', Sparse: 'sparse'}
    if method in kinds or method is MovingDeclared:

        def force(plan, *args):
            sets = connect(plan, *args)
            if method is MovingDeclared:
                return [replace(group, moves=True) for group in sets]
            return [replace(group, way=kinds[method]) for group in sets]

        monkeypatch.setattr(Plan, 'connect', force)
    machine = Run(Plan.of(model.program, model.configuration))
    result = machine.run()
    assert result.failure is None, result.failure
    assert type(machine.ways.instance_of('plant.first')) is method
    return machine


@pytest.mark.parametrize('method', [Family, Lines, ComponentWay, Sparse, DeclaredWay, MovingDeclared])
@pytest.mark.parametrize('direction', ['outflow', 'inflow'])
def test_contact_preserves_the_unequal_incoming_shares_and_both_ends(method, direction, monkeypatch):
    machine = touching(method, direction, monkeypatch)
    end = 0.5
    parts = [Fraction(1)] if method is Family else [Fraction(1, 3), Fraction(2, 3)]
    assert machine.stock_balance('plant.stock', end) == (direction == 'inflow')
    for name, store, amount in zip(('first', 'second'), ('one', 'two'), parts):
        way = machine.ways.instance_of('plant.' + name)
        posted = way.transferred('plant.' + name, end)
        assert float(posted) == pytest.approx(float(amount), rel=0, abs=5e-16)
        assert machine.stock_balance('plant.' + store, end) == (
            posted if direction == 'outflow' else 1 - posted
        )


@pytest.mark.parametrize('method', [Lines, ComponentWay, Sparse, DeclaredWay, MovingDeclared])
def test_the_entire_contact_residual_follows_the_incoming_rates(method, monkeypatch):
    machine = touching(method, 'outflow', monkeypatch, horizon=0.2)
    state, t = machine.stock_state, machine.now
    way = machine.ways.instance_of('plant.first')
    names = ('plant.first', 'plant.second')
    before = [way.transferred(name, t) for name in names]
    # Create a known sub-ulp contact residual. Both actual rates at the instant
    # are positive (1 and 2), so the two physical legs must take exact shares of it.
    residual = Fraction(1, 10**18)
    state.replace('plant.stock', float(residual), residual)
    state.faces({'plant.stock': 0}, t)
    assert machine.stock_balance('plant.stock', t) == 0
    for k, (name, store) in enumerate(zip(names, ('plant.one', 'plant.two'))):
        amount = before[k] + (k + 1) * residual / 3
        assert way.transferred(name, t) == machine.stock_balance(store, t) == amount


def test_contact_with_zero_incoming_rates_uses_declaration_order(monkeypatch):
    machine = touching(Lines, 'outflow', monkeypatch)
    # Both pipes are idle after the empty contact. Model a newly located residual on that
    # same physical face and compare each end before and after the correction.
    state = machine.stock_state
    at = machine.now
    way = machine.ways.instance_of('plant.first')
    before = [way.transferred('plant.' + name, at) for name in ('first', 'second')]
    assert [way.rate_at('plant.' + name + '.actual_rate', at) for name in ('first', 'second')] == [0, 0]
    small = Fraction(1, 10**18)
    state.replace('plant.stock', float(small), small)
    state.faces({'plant.stock': 0}, at)
    assert machine.stock_balance('plant.stock', at) == 0
    assert machine.stock_balance('plant.one', at) == before[0] + small
    assert way.transferred('plant.first', at) == before[0] + small
    assert way.transferred('plant.second', at) == before[1]
