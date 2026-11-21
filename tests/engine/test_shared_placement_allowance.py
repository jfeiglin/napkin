"""A shared gross constraint couples placements even when the target stocks are distinct."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import use_method
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
def test_two_in_band_targets_cannot_each_spend_the_same_frozen_allowance(method, monkeypatch):
    text = """scenario "Two cuts on one frozen book"
    horizon 1 h
yard:
    a: L = 0 L
    b: L = 0 L
    old = event():
        lot: L = 100 L scale 10000000000 L
        after 0 h
    use = event():
        batch = this.old.occurrences.at(t)
        flow first: batch.lot -> this.a
            request = 0.5 L/h
        flow second: batch.lot -> this.b
            request = 0.49999999985 L/h
        after 2 h
    launch = event():
        after 0 h:
            this.use.start()
    watch_a = event():
        when this.a >= 0.5000000001 L:
            this.watch_a.start()
        after 0 h
    watch_b = event():
        when this.b >= 0.49999999995 L:
            this.watch_b.start()
        after 0 h
yard.old.start()
yard.launch.start()
"""
    if method in ('declared', 'moving_declared'):
        text = text.replace(
            '    old = event():',
            '    flow quiet: SOURCE -> this.a\n        request = 0 L/h\n    old = event():',
        )
    model = use_method(text, method, monkeypatch, 'quiet')
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and oracle.conservation()['balanced']
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None and record.end == 1
    expected = {
        'a': Fraction('0.5'),
        'b': Fraction('0.49999999985'),
    }
    for name, amount in expected.items():
        assert value_at(oracle, model.program, Key('yard', (name,)), 1) == amount
        assert float(machine.stock_balance('yard.' + name, 1)) == pytest.approx(
            float(amount), rel=0, abs=3e-15
        )
    accepted = sum(expected.values())
    assert next(iter(oracle.transferred.values())) == accepted
    assert abs(float(machine.stock_balance('yard.old#0.lot', 1) - (100 - accepted))) <= 3e-15
    targets = [('yard.a', 0.5000000001), ('yard.b', 0.49999999995)]
    (trace,) = [entry for entry in record.entries('settle') if entry.part == 'stock placement']
    assert [(name, target) for name, _, target in trace.detail('placements')] == targets
    oracle_ties = [
        entry for entry in oracle.trace if entry.kind == 'near-tie' and entry.label == 'stock placement'
    ]
    assert [(name, float(target)) for name, _, target in oracle_ties[0].placements] == targets
    assert tuple(trace.detail('violations')) == (
        ('yard.old#0.lot', 'outflow', 'yard.use#0.first'),
        ('yard.old#0.lot', 'outflow', 'yard.use#0.second'),
    )
    assert tuple(trace.detail('violations')) == oracle_ties[0].violations


@pytest.mark.parametrize('moving', [False, True], ids=['declared', 'moving-declared'])
@pytest.mark.parametrize('matching', [False, True], ids=['conflicting', 'compatible'])
def test_grouped_placements_respect_a_hard_equation_between_disjoint_pipes(moving, matching, monkeypatch):
    second = '1.0000000001' if matching else '1.0000000002'
    text = f"""scenario "Physically separate pipes in one hard equation"
    horizon 1 h
yard:
    a: L = 0 L
    b: L = 0 L
    flow left: SOURCE -> this.a
        request = 1 L/h
    flow right: SOURCE -> this.b
        request = 1 L/h
    lock = solver:
        inputs:
            left = yard.left
            right = yard.right
        solve_for:
            left.actual_rate
            right.actual_rate
        constraints:
            left.actual_rate == right.actual_rate
    watch_a = event():
        when this.a >= 1.0000000001 L:
            this.watch_a.start()
        after 0 h
    watch_b = event():
        when this.b >= {second} L:
            this.watch_b.start()
        after 0 h
"""
    model = compile_text(text, {'L': {'volume': 1}, 'h': {'time': 1}})
    connect = Plan.connect

    def force(plan, *args, **kwargs):
        return [
            replace(g, moves=moving) if g.way == 'declared' else g for g in connect(plan, *args, **kwargs)
        ]

    monkeypatch.setattr(Plan, 'connect', force)
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and oracle.conservation()['balanced']
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None and record.end == 1
    expected = Fraction('1.0000000001') if matching else Fraction(1)
    for name in ('a', 'b'):
        assert value_at(oracle, model.program, Key('yard', (name,)), 1) == expected
        assert abs(float(run.stock_balance('yard.' + name, 1) - expected)) < 3e-15
    if not matching:
        (tie,) = [entry for entry in record.entries('settle') if entry.part == 'stock placement']
        assert [(name, target) for name, _, target in tie.detail('placements')] == [
            ('yard.a', 1.0000000001),
            ('yard.b', float(second)),
        ]
