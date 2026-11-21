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
        if name in ('declared', 'moving_declared'):
            return [
                replace(group, moves=name == 'moving_declared') if group.way == 'declared' else group
                for group in groups
            ]
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


@pytest.mark.parametrize('method', ['family', 'lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('threshold', ['0.9999999999', '1', '1.0000000001'])
def test_placement_uses_the_same_gross_allowance_as_the_frozen_donor(method, threshold, monkeypatch):
    text = f"""scenario "A grouped threshold draws from a finished lot"
    horizon 1 h
yard:
    basin: L = 0 L
    separate: L = 0 L
    flow fill: SOURCE -> this.separate
        request = 2 L/h
    old = event():
        saved: L = 100 L scale 10000000000 L
        after 0 h
    use = event():
        lot = this.old.occurrences.at(t)
        flow draw: lot.saved -> this.basin
            request = 1 L/h
        after 2 h
    launch = event():
        after 0 h:
            this.use.start()
    watch = event():
        when this.basin >= {threshold} L:
            this.watch.start()
        after 0 h
    other = event():
        when this.separate >= 1.9999999999 L:
            this.other.start()
        after 0 h
yard.old.start()
yard.launch.start()
"""
    if method in ('declared', 'moving_declared'):
        text = text.replace(
            '    old = event():',
            '    flow idle: SOURCE -> this.basin\n        request = 0 L/h\n    old = event():',
        )
    model = use_method(text, method, monkeypatch, 'idle')
    oracle, error = run_of(model.program, model.configuration)
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    leg = 'yard.use#0.draw'
    assert (
        type(run.ways.instance_of(leg)).__name__
        == {
            'family': 'Family',
            'lines': 'Lines',
            'component': 'ComponentWay',
            'sparse': 'Sparse',
            'declared': 'DeclaredWay',
            'moving_declared': 'MovingDeclared',
        }[method]
    )
    assert oracle.view.t == record.end == 1
    if Fraction(threshold) > 1:
        expected = (('yard.old#0.saved', 'outflow', leg),)
        assert error is not None and error.violations == expected
        assert record.failure is not None and record.failure.detail('violations') == expected
        ((stock, side, pipe, attempted, allowance),) = record.failure.detail('attempts')
        assert (stock, side, pipe) == expected[0]
        assert attempted == pytest.approx(1e-10, rel=0, abs=1e-15)
        assert allowance == 1
        assert error.attempts == ((*expected[0], Fraction(1, 10**10), 1),)
        assert 'allowance' in str(error) and 'allowance' in record.failure.detail('message')
        for key, value in ((Key('yard', ('basin',)), 1), (Key('yard', ('separate',)), 2)):
            assert value_at(oracle, model.program, key, 1) == value
            assert run.stock_balance('yard.' + key.steps[0], 1) == value
            assert record.history(key).at(1) == value
        assert next(iter(oracle.transferred.values())) == 1
        assert run.stock_balance('yard.old#0.saved', 1) == 99
        assert run.ways.instance_of(leg).transferred(leg, 1) == 1
        assert not [e for e in record.entries('fire') if e.t == 1]
        assert not [e for e in oracle.trace if e.kind == 'fire' and e.t == 1]
    else:
        assert error is None and record.failure is None
        assert next(iter(oracle.transferred.values())) == Fraction(threshold)
        assert float(run.stock_balance('yard.basin', 1)) == float(threshold)
        assert float(run.stock_balance('yard.separate', 1)) == 1.9999999999


@pytest.mark.parametrize('method', ['family', 'lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('within', [True, False], ids=['within-band', 'outside-band'])
@pytest.mark.parametrize('same', [False, True], ids=['two-ends', 'same-end'])
def test_incompatible_placements_keep_the_trajectory_and_report_both_targets(
    method, within, same, monkeypatch
):
    late = Fraction(1, 10**10) if within else Fraction(5, 10**9)
    second = 3 + late if same else 1 - late
    comparison = f'this.a <= {float(second)}' if same else f'this.b >= {float(second)}'
    text = f"""scenario "Contacts on a closed pipe"
    horizon 1 h
yard:
    a: L = 4 L
    b: L = 0 L
    separate: L = 0 L
    flow ab: this.a -> this.b
        request = 1 L/h
    flow independent: SOURCE -> this.separate
        request = 2 L/h
    watcha = event():
        when this.a <= 3 L:
            this.watcha.start()
        after 0 h
    watchb = event():
        when {comparison} L:
            this.watchb.start()
        after 0 h
    watchother = event():
        when this.separate >= 1.9999999999 L:
            this.watchother.start()
        after 0 h
    clock = event():
        after 1 h
yard.clock.start()
"""
    model = use_method(text, method, monkeypatch, 'ab')
    oracle, problem = run_of(model.program, model.configuration)
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.end == oracle.view.t == 1
    expected = {('yard.a', 3, 3), ('yard.a' if same else 'yard.b', 3 if same else 1, second)}
    (oracle_tie,) = [e for e in oracle.trace if e.kind == 'near-tie' and e.label == 'stock placement']
    assert set(oracle_tie.placements) == expected
    (tie,) = [e for e in record.entries('settle') if e.part == 'stock placement']
    public = {(name, float(actual), float(target)) for name, actual, target in expected}
    assert {tuple(p) for p in tie.detail('placements')} == public
    assert tie.t == oracle_tie.t == 1 and tie.detail('near')
    if within:
        assert problem is None and record.failure is None
    else:
        assert {tuple(p) for p in record.failure.detail('placements')} == public
        assert set(problem.placements) == expected
        assert all(
            name in record.failure.detail('message') and name in str(problem) for name, _, _ in expected
        )
        assert not [entry for entry in record.entries('fire') if entry.t == 1]
    for name, amount in [('a', 3), ('b', 1), ('separate', Fraction('1.9999999999') if within else 2)]:
        key = Key('yard', (name,))
        assert value_at(oracle, model.program, key, 1) == amount
        assert float(run.stock_balance('yard.' + name, 1)) == float(amount)
        assert record.history(key).at(1) == float(amount)
    assert run.ways.instance_of('yard.ab').transferred('yard.ab', 1) == 1


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('upper', [False, True], ids=['other-end-floor', 'other-end-capacity'])
def test_a_grouped_placement_checks_the_other_endpoint_before_posting_any_leg(method, upper, monkeypatch):
    stock = '0.999999999 L in [, 1 L]' if upper else '0.000000001 L in [0 L,]'
    through = 'this.basin -> this.other' if upper else 'this.other -> this.basin'
    keep = 'this.other -> SINK' if upper else 'SOURCE -> this.other'
    threshold = 'this.basin <= 0.999999995 L' if upper else 'this.basin >= 1.000000005 L'
    text = f"""scenario "Room at the opposite endpoint"
    horizon 1 h
yard:
    other: L = {stock}
    basin: L = {2 if upper else 0} L
    separate: L = 0 L
    flow through: {through}
        request = 1 L/h
    flow steady: {keep}
        request = 1 L/h
    flow additional: SOURCE -> this.separate
        request = 2 L/h
    watch = event():
        when {threshold}:
            this.watch.start()
        after 0 h
    separate_watch = event():
        when this.separate >= 1.9999999999 L:
            this.separate_watch.start()
        after 0 h
    clock = event():
        after 1 h
yard.clock.start()
"""
    model = use_method(text, method, monkeypatch, 'through')
    oracle, error = run_of(model.program, model.configuration)
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.end == oracle.view.t == 1
    assert 'yard.other' in str(error) and 'yard.other' in record.failure.detail('message')
    for name, expected in [('basin', 1), ('other', Fraction(stock.split()[0])), ('separate', 2)]:
        key = Key('yard', (name,))
        assert value_at(oracle, model.program, key, 1) == expected
        assert run.stock_balance('yard.' + name, 1) == expected
        assert record.history(key).at(1) == float(expected)
    assert not [entry for entry in record.entries('fire') if entry.t == 1]


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
def test_a_resting_neighbor_keeps_room_smaller_than_a_float_at_its_ceiling(method, monkeypatch):
    text = """scenario "A pass-through stock with a carried remainder"
    horizon 1.25 h
yard:
    a: L = 1 L in [0, 1 L]
    b: L = 4000000 L in [0, 4000000 L]
    receipt: L = 0 L
    flow ab: this.a -> this.b
        request = 1 L/h
        capacity = 1 L/h
    flow drain: this.b -> SINK
        request = 1 L/h
        capacity = 1 L/h
    collect = event():
        after 0 h:
            move 0.0000000001 L from this.b to this.receipt
        after 0.9999999999 h
yard.collect.start()
"""
    model = use_method(text, method, monkeypatch, 'ab')
    at, gap = Fraction('0.9999999999'), Fraction('0.0000000001')
    pool = 4_000_000 - gap
    assert float(pool) == 4_000_000
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and oracle.conservation()['balanced']
    run = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.collect.step[1]'),))
    stopped = run.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == float(at)
    for name, balance in [('b', pool), ('receipt', gap), ('a', gap)]:
        assert value_at(oracle, model.program, Key('yard', (name,)), at) == balance
    assert run.stock_balance('yard.b', float(at)) == pool
    assert run.stock_balance('yard.receipt', float(at)) == gap
    retained = run.stock_balance('yard.a', float(at))
    assert float(retained) == pytest.approx(float(gap), rel=0, abs=2e-15)
    record = run.resume()
    assert record.failure is None and record.end == 1.25
    assert run.stock_balance('yard.a', record.end) == retained
