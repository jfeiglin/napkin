"""Hand-worked solver ownership and inventory cases from the readiness audit of 6f297e5."""

from napkin.engine import read, run
from napkin.program.build import SINK, SOURCE, Builder, constraint, flow, given, local, q, solve_for, solver
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
