"""The exact interpreter may reuse only the identical numerical LP inside its ranked solve."""

import pytest

from tests.reference import order
from tests.reference.errors import Infeasible


def test_only_identical_scipy_inputs_share_an_optimum_and_each_caller_gets_its_own_point(monkeypatch):
    calls = []
    actual = order.linprog

    def counted(c, **kwargs):
        calls.append((c, kwargs))
        return actual(c, **kwargs)

    monkeypatch.setattr(order, 'linprog', counted)
    order._cached_optimum.cache_clear()
    x, y = order.Lin.var('x'), order.Lin.var('y')
    rows = [order.relation(x, '==', 2), order.relation(y, '>=', 1), order.relation(y, '<=', 3)]
    status, best, point = order._lp(['x', 'y'], rows, y)
    assert (status, best, tuple(point)) == ('optimal', 1, (2, 1))
    point[:] = 100
    assert order._lp(['x', 'y'], rows, y + 7)[1] == 8
    assert tuple(order._lp(['x', 'y'], rows, y)[2]) == (2, 1)
    assert len(calls) == 1

    for variables, constraints, objective, expected in [
        (['y', 'x'], rows, y, (1, (1, 2))),
        (['x', 'y'], list(reversed(rows)), y, (1, (2, 1))),
        (['x', 'y'], rows, -y, (-3, (2, 3))),
        (['x', 'y'], [order.relation(x, '==', 4), *rows[1:]], y, (1, (4, 1))),
        (['x', 'y'], [rows[0], order.relation(2 * y, '>=', 1), rows[2]], y, (0.5, (2, 0.5))),
        (['x', 'y'], [rows[0], rows[1], order.relation(y, '==', 3)], y, (3, (2, 3))),
    ]:
        count = len(calls)
        status, best, point = order._lp(variables, constraints, objective)
        assert status == 'optimal' and (best, tuple(point)) == expected
        assert len(calls) == count + 1
    assert order._lp(['y'], [], y) == ('unbounded', None, None)
    with pytest.raises(Infeasible, match='hard conditions'):
        order._lp(['x', 'y'], [*rows, order.relation(y, '==', 5)], y)


def test_cached_and_uncached_oracles_agree_across_an_edited_stage(monkeypatch):
    from napkin.program.config import Configuration, Request
    from tests.engine.test_clock_moments import HORIZON, LOOK, TIMES, network
    from tests.reference.from_program import run_of, values_at

    program, keys, change = network(1)
    configuration = Configuration(Request(HORIZON))

    def observations():
        found = []
        for stops in ([], [(LOOK, None, [change])]):
            oracle, failure = run_of(program, configuration, stops)
            assert failure is None
            found.append((oracle.trace, values_at(oracle, program, keys, TIMES)))
        return found

    cached = observations()
    monkeypatch.setattr(order, '_cached_optimum', order._float_optimum)
    assert cached == observations()
