"""Hand-worked solver ownership and inventory cases from the readiness audit of 6f297e5."""

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.engine.timeline import selection
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    constraint,
    flow,
    given,
    local,
    q,
    route,
    solve_for,
    solver,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.program.examples import UNITS
from tests.reference.from_program import run_of, value_at


def test_declared_solver_shares_two_source_to_sink_flows():
    """Each pipe gets 8/2 L/h. A third, unowned boundary pipe gets its own 3 L/h."""
    b = Builder(UNITS)
    pipes = b.entity(
        'pipes',
        *(
            flow(name, SOURCE, SINK, request=q(wanted, 'L/h'), unit='L/h')
            for name, wanted in [('one', 6), ('two', 6), ('free', 3)]
        ),
    )
    b.entity(
        'provider',
        solver(
            'dispatch',
            given('one', pipes.one),
            given('two', pipes.two),
            solve_for(local.one.actual_rate),
            solve_for(local.two.actual_rate),
            constraint(local.one.actual_rate + local.two.actual_rate <= q(8, 'L/h')),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    assert [
        r.values
        for r in read(
            record, program, [f'pipes.{name}.actual_rate' for name in ('one', 'two', 'free')], [0, 1]
        )
    ] == [(4, 4), (4, 4), (3, 3)]
    oracle, error = run_of(program, Configuration(Request(1)))
    assert error is None
    for name, expected in [('one', 4), ('two', 4), ('free', 3)]:
        assert value_at(oracle, program, Key('pipes', (name, 'actual_rate')), 1) == expected


@pytest.mark.parametrize(
    'amount_unit,rate_unit,large_unit,factor', [('L', 'L/h', 'L/h', 1000000), ('Wh', 'W', 'MW', 1)]
)
def test_publishing_an_idle_route_preserves_its_stock(amount_unit, rate_unit, large_unit, factor):
    """The main request gets its capacity of 10 million. The last row then allows an idle
    flow of up to 1. Its target is zero and zero is feasible, so no inventory leaves the stock."""
    units = {**UNITS, 'MW': ({'energy': 1, 'time': -1}, 1000000)}
    b = Builder(units)
    stock = b.entity('stock', value('water', amount_unit, 10, lower=0))
    receiver = b.entity('receiver', value('water', amount_unit, 10, lower=0))
    pipes = b.entity(
        'pipes',
        flow(
            'supply',
            SOURCE,
            receiver.water,
            request=q(30 * factor, large_unit),
            capacity=q(10 * factor, large_unit),
        ),
        route('idle', stock.water, receiver.water),
    )
    b.entity(
        'provider',
        solver(
            'dispatch',
            given('supply', pipes.supply),
            given('idle', pipes.idle),
            solve_for(local.supply.actual_rate),
            solve_for(local.idle.actual_rate),
            constraint(
                10_000_000 * (local.supply.actual_rate - q(10 * factor, large_unit)) + local.idle.actual_rate
                <= q(1, rate_unit)
            ),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    idle, stock = read(record, program, ['pipes.idle.actual_rate', 'stock.water'], [0, 1])
    assert idle.values == (0, 0)
    assert stock.values == (10, 10)


def test_local_sharing_keeps_an_idle_rate_zero_beside_a_large_unserved_request():
    """For targets (30 million, 0), a cap of 10 million on the first fixes the nearest answer
    at (10 million, 0). The first delivery stays put, so 1 on the second worsens the distance."""
    rows = selection.Rows(2)
    lower, upper = np.zeros(2), np.array([10_000_000, np.inf])
    target = np.array([30_000_000, 0])
    answer = np.array([10_000_000, 0])
    candidate = np.array([10_000_000, 1])
    kept = selection._kept(rows, lower, upper, target, [], answer, (candidate,))
    assert kept.tolist() == [10_000_000, 0]
