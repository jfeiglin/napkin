"""Compare the three local implementations of simultaneous flow through a stock at a bound."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


@pytest.mark.parametrize('initial, upper', [(0, 10), (10, 10), (0, 0)], ids=['empty', 'full', 'zero-width'])
@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared'])
def test_a_store_at_its_bound_allows_equal_gross_flows(initial, upper, method, monkeypatch):
    source = f"""tank:
    water: L = {initial} L in [0 L, {upper} L]
    received: L = 0 L
    flow supply: SOURCE -> this.water
        request = 1 L/h
    flow serve: this.water -> this.received
        request = 1 L/h
"""
    if method == 'declared':
        source += """provider:
    share = solver:
        inputs:
            pipe = tank.supply
        solve_for:
            pipe.actual_rate
"""
    program = compile_text(source, UNITS).program
    config = Configuration(Request(2))
    oracle, error = run_of(program, config)
    assert error is None
    if method != 'declared':
        # The requests are held. Each of the three local implementations can integrate this
        # network of directed one-to-one connections. Exercise the same Program on each.
        connect = Plan.connect

        def choose(plan, *args, **kwargs):
            return [replace(group, way=method) for group in connect(plan, *args, **kwargs)]

        monkeypatch.setattr(Plan, 'connect', choose)
    runner = Run(Plan.of(program, config))
    assert [s.way for s in runner.plan.sets] == [method]
    record = runner.run()
    assert record.failure is None, record.failure
    times = (Fraction(0), Fraction(1, 2), Fraction(2))
    for path, expected in [
        ('water', [initial] * 3),
        ('supply.actual_rate', [1] * 3),
        ('serve.actual_rate', [1] * 3),
        ('received', times),
    ]:
        key = Key('tank', tuple(path.split('.')))
        assert [value_at(oracle, program, key, t) for t in times] == list(expected)
        assert read(record, program, [key], list(map(float, times)))[0].values == pytest.approx(
            list(map(float, expected)), rel=1e-9, abs=1e-10
        )
