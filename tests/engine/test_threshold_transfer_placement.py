"""A grouped stock threshold places the signed difference on its approaching physical legs."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def use_method(text, name, monkeypatch, solved_flow):
    if name in ('declared', 'moving_declared'):
        text += f"""owner:
    share = solver:
        inputs:
            pipe = yard.{solved_flow}
        solve_for:
            pipe.actual_rate
"""
    connect = Plan.connect

    def force(plan, *args, **kwargs):
        groups = connect(plan, *args, **kwargs)
        if name == 'moving_declared':
            return [replace(group, moves=True) for group in groups]
        return [replace(group, way=name) for group in groups]

    monkeypatch.setattr(Plan, 'connect', force)
    return compile_text(text, UNITS)


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize('rising', [True, False], ids=['rising', 'falling'])
@pytest.mark.parametrize('gap', [-1, 1], ids=['early', 'late'])
def test_a_grouped_threshold_posts_only_to_the_legs_approaching_it(method, rising, gap, monkeypatch):
    at = Fraction(1) + Fraction(gap, 10_000_000_000)
    time = '0.9999999999' if gap < 0 else '1.0000000001'
    direction = 'first -> this.tank', 'second -> this.tank', 'tank -> this.other'
    if not rising:
        direction = 'tank -> this.first', 'tank -> this.second', 'other -> this.tank'
    comparison = '<' if rising else '>'
    text = f"""scenario "Threshold placement"
    horizon 1.25 h
yard:
    tank: L = {1 if rising else 3} L
    first: L = 7 L
    second: L = 7 L
    other: L = 7 L
    flow small: this.{direction[0]}
        request = 0.5 L/h
    flow large: this.{direction[1]}
        request = 1.5 L/h
    flow opposed: this.{direction[2]}
        request = formula(1 L/h if this.tank {comparison} 2 L else 0.5 L/h)
    clock = event():
        after {time} h
yard.clock.start()
"""
    model = use_method(text, method, monkeypatch, 'large')
    sign = 1 if rising else -1
    correction = 1 - at
    small = at / 2 + correction / 4
    large = 3 * at / 2 + 3 * correction / 4
    expected = {'tank': 2, 'first': 7 - sign * small, 'second': 7 - sign * large, 'other': 7 + sign * at}
    oracle, error = run_of(model.program, model.configuration)
    assert error is None, error
    assert oracle.conservation()['balanced']
    for name, value in expected.items():
        assert value_at(oracle, model.program, Key('yard', (name,)), at) == value, name
    run = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.clock.step[0]'),))
    stop = run.run()
    assert isinstance(stop, Checkpoint), stop
    way = run.ways.instance_of('yard.large')
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
    for name, value in expected.items():
        assert float(run.stock_balance('yard.' + name, float(at))) == pytest.approx(
            float(value), rel=0, abs=1e-13
        ), name
    for name, value in [('small', small), ('large', large), ('opposed', at)]:
        assert float(way.transferred('yard.' + name, float(at))) == pytest.approx(
            float(value), rel=0, abs=1e-13
        ), name


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('resting', [False, True], ids=['located-threshold', 'resting-bound'])
def test_a_correction_preserves_a_second_stock_already_exactly_on_its_threshold(method, resting, monkeypatch):
    declarations = (
        """a: L = 0 L in [0 L,]
    flow refill: SOURCE -> this.a
        request = 2 L/h"""
        if resting
        else """a: L = 4 L
    watcha = event():
        when this.a <= 2 L:
            this.watcha.start()
        after 0 h"""
    )
    text = f"""scenario "Intersecting placed thresholds"
    horizon 1.1 h
yard:
    {declarations}
    b: L = 0 L
    flow ab: this.a -> this.b
        request = 1 L/h
    flow elsewhere: this.a -> SINK
        request = 1 L/h
    watchb = event():
        when this.b >= 0.9999999999 L:
            this.watchb.start()
        after 0 h
    clock = event():
        after 1 h
yard.clock.start()
"""
    model = use_method(text, method, monkeypatch, 'ab')
    oracle, error = run_of(model.program, model.configuration)
    assert error is None, error
    assert oracle.conservation()['balanced']
    approaching = Fraction('0.9999999999')
    for name, value in [('a', 0 if resting else 2), ('b', approaching)]:
        assert value_at(oracle, model.program, Key('yard', (name,)), Fraction(1)) == value
    amounts = {'yard.ab': approaching, 'yard.elsewhere': 2 - approaching}
    if resting:
        amounts['yard.refill'] = 2
    assert {row[3]: row[6] for row in oracle.ledger if row[0] == 'flow' and row[2] == 1} == amounts
    firings = [1] if resting else [1, 1]
    assert [entry.t for entry in oracle.trace if entry.kind == 'fire'] == firings
    run = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.clock.step[0]'),))
    assert isinstance(run.run(), Checkpoint)
    way = run.ways.instance_of('yard.ab')
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
    assert run.stock_balance('yard.a', 1) == (0 if resting else 2)
    assert float(run.stock_balance('yard.b', 1)) == float(approaching)
    assert float(way.transferred('yard.ab', 1)) == pytest.approx(float(approaching), abs=1e-14, rel=0)
    assert float(way.transferred('yard.elsewhere', 1)) == pytest.approx(
        float(2 - approaching), abs=1e-14, rel=0
    )
    record = run.resume()
    assert record.failure is None, record.failure
    assert [entry.t for entry in record.entries('fire')] == firings
