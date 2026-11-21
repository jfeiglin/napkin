"""Both ends of two directed legs can reach their bounds at one contact."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.model.compile import compile_text


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('top', ['', '2 L'], ids=['unbounded-above', 'bounded-above'])
def test_an_empty_donor_and_its_two_full_receivers_keep_the_same_legs(method, top, monkeypatch):
    # With rates 7 and 14, all three stocks reach their faces at 2/35 h.
    # Emptying the donor must not turn that same contact into its upper bound.
    text = f"""scenario "Three stock bounds"
    horizon 0.2 h
yard:
    reserve: L = 1.2 L in [0 L,{top}]
    left: L = 0 L in [0 L,0.4 L]
    right: L = 0 L in [0 L,0.8 L]
    flow small: this.reserve -> this.left
        request = 7 L/h
    flow large: this.reserve -> this.right
        request = 14 L/h
"""
    if method == 'moving_declared':
        text += '        capacity = formula(100 L/h + t * 1 L/h/h)\n'
    if method in ('declared', 'moving_declared'):
        text += """owner:
    share = solver:
        inputs:
            small = yard.small
        solve_for:
            small.actual_rate
"""
    else:
        connect = Plan.connect

        def force(plan, *args, **kwargs):
            return [replace(group, way=method) for group in connect(plan, *args, **kwargs)]

        monkeypatch.setattr(Plan, 'connect', force)
    model = compile_text(text, {'h': {'time': 1}, 'L': {'volume': 1}})
    engine = Run(Plan.of(model.program, model.configuration))
    record = engine.run()
    assert record.failure is None, record.failure
    way = engine.ways.instance_of('yard.small')
    assert (
        type(way).__name__
        == {
            'lines': 'Lines',
            'component': 'ComponentWay',
            'sparse': 'Sparse',
            'declared': 'DeclaredWay',
            'moving_declared': 'MovingDeclared',
        }[method]
    )
    at = float(model.configuration.request.horizon)
    for store, amount in [('reserve', 0), ('left', Fraction(2, 5)), ('right', Fraction(4, 5))]:
        name = f'yard.{store}'
        assert engine.stock_balance(name, at) == amount
        assert read(record, model.program, [name], [at])[0].values == (float(amount),)
    assert way.transferred('yard.small', at) == Fraction(2, 5)
    assert way.transferred('yard.large', at) == Fraction(4, 5)
