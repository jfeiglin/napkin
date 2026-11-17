"""The boundary allocation's linear programs without linprog's wrapper
(`napkin/engine/continuous/highs.py`).

`solve` must give linprog's result, bit for bit: the same solution and the same success, and on a
failure linprog's own result. Agreement between two calls of one solver says nothing about the
optimum, so an optimum from the theory of linear programs checks the solver too.
"""

import math

import numpy as np
import pytest
from scipy.optimize import linprog
from scipy.sparse import csc_array

from napkin.engine.continuous import highs


def program(rng):
    """A program of the shape that the allocation makes (`fields.Field._linear_program`): served
    fractions in [0, 1] or pinned, rows that take a flow's request from a stock (-1) or give it to
    one (+1), equality ties between fractions, and an objective over every fraction or one."""
    flows, rows = int(rng.integers(1, 12)), int(rng.integers(1, 6))
    requests = rng.lognormal(0, 2, flows)
    signs = rng.choice([-1.0, 0.0, 1.0], size=(rows, flows), p=[0.3, 0.4, 0.3])
    a_ub = signs * requests
    b_ub = rng.normal(0, 1, rows) * requests.sum() * rng.choice([0.0, 0.5, 2.0])
    limits = []
    for _ in range(flows):
        pinned = rng.random() < 0.2
        value = float(rng.choice([0.0, 1.0, rng.random()]))
        limits.append((value, value) if pinned else (0.0, 1.0))
    a_eq = b_eq = None
    if flows > 1 and rng.random() < 0.4:
        j, k = rng.choice(flows, 2, replace=False)
        row = np.zeros(flows)
        row[j], row[k] = 1, -1
        a_eq, b_eq = [row], [0.0]
    c = -np.ones(flows) if rng.random() < 0.6 else -np.eye(flows)[int(rng.integers(flows))]
    return c, a_ub, b_ub, a_eq, b_eq, limits


def reference(c, a_ub, b_ub, a_eq, b_eq, bounds):
    return linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method='highs')


def test_a_solution_is_linprogs_bit_for_bit():
    rng = np.random.default_rng(20261025)
    outcomes = set()
    for _ in range(400):
        args = program(rng)
        got, want = highs.solve(*args), reference(*args)
        assert got.success == want.success
        outcomes.add(bool(want.success))
        if want.success:
            assert got.x.tobytes() == want.x.tobytes()
        else:
            # A failure is linprog's own result, with its status and message.
            assert (got.status, got.message) == (want.status, want.message)
    assert outcomes == {True, False}


def test_an_input_that_linprog_rejects_is_rejected_by_linprog():
    for bad in (math.nan, math.inf):
        args = (np.array([-1.0, bad]), np.ones((1, 2)), np.ones(1), None, None, [(0, 1), (0, 1)])
        with pytest.raises(ValueError) as want:
            reference(*args)
        with pytest.raises(ValueError) as got:
            highs.solve(*args)
        assert str(got.value) == str(want.value)


def test_the_optimum_serves_the_cheaper_request_first():
    # Requests of 2 and 3 share 4 units: maximise u1 + u2 with 2 u1 + 3 u2 <= 4 and 0 <= u <= 1.
    # The vertices are (1, 2/3), with sum 5/3, and (1/2, 1), with sum 3/2: the first is the optimum.
    result = highs.solve(-np.ones(2), np.array([[2.0, 3.0]]), np.array([4.0]), None, None, [(0, 1), (0, 1)])
    assert result.success
    assert result.x == pytest.approx([1.0, 2 / 3], abs=1e-9)


def test_the_columns_are_those_of_scipys_compressed_columns():
    rng = np.random.default_rng(7)
    for shape in [(1, 1), (3, 1), (1, 4), (5, 7), (8, 3)]:
        matrix = rng.choice([0.0, -0.0, 1.5, -2.0, 1e-300], size=shape)
        start, index, value = highs.columns(matrix)
        expected = csc_array(matrix)
        assert start.tolist() == expected.indptr.tolist()
        assert index.tolist() == expected.indices.tolist()
        assert value.tobytes() == expected.data.tobytes()
