"""Separate directed amounts must keep a store exactly on a face during balanced service."""

import math
from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_a_stock_leaves_its_face_when_a_stationary_start_has_a_curved_future(method, monkeypatch):
    # All stocks downstream of a start empty. The last tank has zero initial
    # derivative and positive curvature, so its actual inflow cannot be cancelled.
    source = """scenario "Three equal tanks in series"
    horizon 1 h
p:
    a: L = 1 L in [0 L,]
    b: L = 0 L in [0 L,]
    c: L = 0 L in [0 L,]
    flow ab: this.a -> this.b
        request = formula(this.a / 1 h)
    flow bc: this.b -> this.c
        request = formula(this.b / 1 h)
    flow out: this.c -> SINK
        request = formula(this.c / 1 h)
"""
    if method == 'moving_declared':
        source += """owner:
    choose = solver:
        inputs:
            pipe = p.ab
        solve_for:
            pipe.actual_rate
"""
    else:
        connect = Plan.connect
        monkeypatch.setattr(
            Plan,
            'connect',
            lambda plan, *args, **kw: [replace(group, way=method) for group in connect(plan, *args, **kw)],
        )
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None, record.failure
    way = run.ways.instance_of('p.ab')
    assert (
        type(way).__name__
        == {'component': 'ComponentWay', 'sparse': 'Sparse', 'moving_declared': 'MovingDeclared'}[method]
    )
    delivered = way.transferred('p.bc', 1) - way.transferred('p.out', 1)
    assert run.stock_balance('p.c', 1) == delivered
    assert float(delivered) == pytest.approx(math.exp(-1) / 2, rel=1e-7)


@pytest.mark.parametrize('method', ['lines', 'sparse', 'declared', 'moving_declared'])
def test_two_outlets_share_supply_without_leaving_a_remainder_at_an_empty_store(method, monkeypatch):
    source = """scenario "Thirds through an empty store"
    horizon 1 h
p:
    central: L = 0 L in [0 L,]
    first: L = 0 L
    second: L = 0 L
    flow incoming: SOURCE -> this.central
        request = 1 L/h
        capacity = 1 L/h
    flow small: this.central -> this.first
        request = 1 L/h
    flow large: this.central -> this.second
        request = 2 L/h
"""
    if method in ('declared', 'moving_declared'):
        if method == 'moving_declared':
            source += '        capacity = formula(100 L/h + t * 1 L/h/h)\n'
        source += """owner:
    choose = solver:
        inputs:
            pipe = p.incoming
        solve_for:
            pipe.actual_rate
"""
    else:
        connect = Plan.connect

        def force(plan, *args, **kwargs):
            return [replace(group, way=method) for group in connect(plan, *args, **kwargs)]

        monkeypatch.setattr(Plan, 'connect', force)
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None, record.failure
    way = run.ways.instance_of('p.incoming')
    assert (
        type(way).__name__
        == {
            'lines': 'Lines',
            'sparse': 'Sparse',
            'declared': 'DeclaredWay',
            'moving_declared': 'MovingDeclared',
        }[method]
    )
    assert run.stock_balance('p.central', 1) == 0
    small = way.transferred('p.small', 1)
    large = way.transferred('p.large', 1)
    assert small + large == way.transferred('p.incoming', 1)
    for name, amount, expected in [('p.first', small, Fraction(1, 3)), ('p.second', large, Fraction(2, 3))]:
        assert amount == run.stock_balance(name, 1)
        assert float(amount) == pytest.approx(float(expected), rel=1e-9, abs=1e-12)


@pytest.mark.parametrize('method', ['lines', 'sparse'])
def test_an_unrelated_stage_leaves_other_resting_prefixes_lazy(method, monkeypatch):
    from napkin.engine.timeline.stocks import RestingAmounts, RestingRates
    from napkin.program.build import (
        SINK,
        SOURCE,
        Builder,
        after,
        assign,
        event,
        flow,
        named,
        q,
        start,
        this,
        value,
    )
    from napkin.program.config import Configuration, Request
    from napkin.program.record import Key

    b = Builder({'L': {'volume': 1}, 'h': {'time': 1}})
    for k in range(16):
        b.entity(
            f'tank{k}',
            value('stock', 'L', 0, lower=0),
            flow('inlet', SOURCE, this.stock, request=q(1, 'L/h')),
            flow('out_a', this.stock, SINK, request=q(1, 'L/h')),
            flow('out_b', this.stock, SINK, request=q(2, 'L/h')),
        )
    b.entity('clock', value('tick', '', 0), event('wait', after(q(0.5, 'h'), assign(this.tick, 1))))
    b.setup(start(named('clock').wait))
    connect = Plan.connect
    monkeypatch.setattr(
        Plan,
        'connect',
        lambda plan, *args, **kw: [replace(group, way=method) for group in connect(plan, *args, **kw)],
    )
    queries = []
    held_update, moving_read = RestingRates.update, RestingAmounts.amount

    def update(ledger, way, changed, rates, at):
        if at == 0.5:
            queries.extend(way.stores[s] for s in changed)
        return held_update(ledger, way, changed, rates, at)

    def amount(ledger, way, leg, at):
        if at == 0.5:
            queries.append(leg)
        return moving_read(ledger, way, leg, at)

    monkeypatch.setattr(RestingRates, 'update', update)
    monkeypatch.setattr(RestingAmounts, 'amount', amount)
    machine = Run(
        Plan.of(b.finish(), Configuration(Request(1, everything=False, keys=(Key('clock', ('tick',)),))))
    )
    result = machine.run()
    assert result.failure is None
    assert not queries
    for k in (15, 0, 15):
        name = f'tank{k}.stock'
        assert machine.stock_balance(name, 1) == 0
