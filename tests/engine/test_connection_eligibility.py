"""Only connections that can carry flow contribute to the order of claims."""

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    constraint,
    endpoint,
    event,
    flow,
    given,
    legs,
    local,
    priority,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


def rate(amount):
    return q(amount, 'L/h')


def check(program, expected):
    configuration = Configuration(Request(2))
    oracle, error = run_of(program, configuration)
    assert error is None, error
    record = run(program, configuration)
    assert record.failure is None, record.failure
    # Read the priority allocation before the edit and at the stage that makes the connection eligible.
    times = (0, Fraction(1, 2), 1, Fraction(3, 2), 2)
    keys = [Key('yard', tuple(name.split('.'))) for name in expected]
    readings = read(record, program, keys, list(map(float, times)))
    for key, row, (before, following) in zip(keys, readings, expected.values(), strict=True):
        hand = (before, before, following, following, following)
        assert tuple(value_at(oracle, program, key, t) for t in times) == hand, key
        assert row.values == pytest.approx(hand, abs=1e-9, rel=0), key
    assert [entry.t for entry in record.entries('commit', 'yard.open.step[0]')] == [1]


def limit_named_pipe(builder, yard):
    # Only the named pipe is the provider's unknown. Its competing flow retains local sharing.
    builder.entity(
        'provider',
        solver(
            'plan',
            given('pipe', yard.pipe),
            solve_for(local.pipe.actual_rate),
            constraint(local.pipe.actual_rate <= rate(1.5)),
        ),
    )


@pytest.mark.parametrize('closed_at', ['pipe', 'source', 'sink'])
@pytest.mark.parametrize('declared', [False, True], ids=['local', 'one-named-unknown'])
def test_a_closed_connection_drops_out_of_the_priority_order(closed_at, declared):
    b = Builder(UNITS)
    reverse = closed_at == 'source'
    ranked = endpoint(allocation=priority(this.valve, this.pipe))
    limited = endpoint(capacity=rate(2))
    valve_end = endpoint(capacity=rate(0 if closed_at != 'pipe' else 1))
    if reverse:
        stock = value('stock', 'L', 20, inflow=ranked)
        shared = value('shared', 'L', 20, outflow=limited)
        end = value('end', 'L', 20, outflow=valve_end)
        valve, pipe, rival = (this.end, this.stock), (this.shared, this.stock), (this.shared, SINK)
        edited = this.end.outflow.capacity
    else:
        stock = value('stock', 'L', 20, outflow=ranked)
        shared = value('shared', 'L', 20, inflow=limited)
        end = value('end', 'L', 20, inflow=valve_end)
        valve, pipe, rival = (this.stock, this.end), (this.stock, this.shared), (SOURCE, this.shared)
        edited = this.valve.capacity if closed_at == 'pipe' else this.end.inflow.capacity
    yard = b.entity(
        'yard',
        stock,
        shared,
        end,
        flow('valve', *valve, capacity=rate(0 if closed_at == 'pipe' else 1)),
        flow('pipe', *pipe, request=rate(2)),
        flow('rival', *rival, request=rate(2)),
        event('open', after(q(1, 'h'), assign(edited, rate(1)))),
    )
    if declared:
        limit_named_pipe(b, yard)
    b.setup(start(yard.open))
    check(b.finish(), {'pipe.actual_rate': (1, 0), 'rival.actual_rate': (1, 2), 'valve.actual_rate': (0, 0)})


@pytest.mark.parametrize('declared', [False, True], ids=['local', 'one-named-unknown'])
def test_a_proportional_leg_enters_priority_when_it_first_asks_for_flow(declared):
    b = Builder(UNITS)
    yard = b.entity(
        'yard',
        value('stock', 'L', 20, outflow=endpoint(capacity=rate(2))),
        value('end', 'L', 0, inflow=endpoint(allocation=priority(this.pipe, this.work.second))),
        flow('pipe', this.stock, this.end, request=rate(2)),
        legs(
            'work',
            flow('first', this.stock, SINK, request=rate(2)),
            flow('second', SOURCE, this.end, request=rate(0)),
        ),
        event('open', after(q(1, 'h'), assign(this.work.second.request, rate(2)))),
    )
    if declared:
        limit_named_pipe(b, yard)
    b.setup(start(yard.open))
    served = Fraction(1, 4) if declared else 0
    check(
        b.finish(),
        {
            'pipe.actual_rate': (1, 2 * (1 - served)),
            'work.served_fraction': (Fraction(1, 2), served),
            'work.first.actual_rate': (1, 2 * served),
            'work.second.actual_rate': (0, 2 * served),
        },
    )
