"""Unknowns and rows that join and leave the problem of one kept solver.

A `Solver` keeps one HiGHS instance for a run and follows each problem by its keys. Each answer
must equal that of the same problem solved fresh, and a sequence of problems must be answered alike
whatever other solvers do beside it, both within the tolerances of the steps: a fair level is known
to 1e-7 of its request (`fair.FIX`), so two answers agree within 1e-6 of the size of the problem
(the owner's rule: only the same run, repeated, must agree bit for bit, and it does).
"""

import numpy as np
import pytest

from napkin.engine.solve import FLOW, Problem, Solver

from . import cases

TOLERANCE = 1e-6  # two answers of one problem agree within this, times the size of the problem


def fresh(problem):
    return Solver().solve(problem)


def same(kept, formed, size=10.0):
    assert kept.keys == formed.keys
    assert kept.x == pytest.approx(formed.x, abs=TOLERANCE * size)


def test_occurrences_join_and_leave_a_shared_limit():
    # a shared limit of 3 L/h, each occurrence requesting 2 L/h: A alone, A and B, B alone, none
    moments = [('A',), ('A', 'B'), ('B',), ()]
    expected = [[2.0], [1.5, 1.5], [2.0], []]
    solver = Solver()
    for occurrences, rates in zip(moments, expected):
        answer = solver.solve(cases.shared_limit(occurrences))
        assert answer.x == pytest.approx(rates, abs=1e-6)
        same(answer, fresh(cases.shared_limit(occurrences)))
    # the kept instance holds the last problem: its shared limit and no column
    assert solver._kept.n == 0 and solver._kept.m == 1


def test_a_route_that_closes_and_opens_changes_a_kept_row():
    # the closure sets the route's pull to zero: a new coefficient in a row that stays
    solver = Solver()
    for up in (True, False, True, False):
        problem = cases.network(garden_up=up)
        same(solver.solve(problem), fresh(cases.network(garden_up=up)))


def test_requests_and_capacities_that_change_with_the_moment():
    solver = Solver()
    for needs, supply in (((0, 6, 6), (8, 0, 0)), ((0, 3, 3), (8, 0, 0)), ((0, 2, 6), (4, 0, 0))):
        same(solver.solve(cases.network(needs, supply)), fresh(cases.network(needs, supply)))


def test_rows_that_join_and_leave():
    def moment(limits):
        p = Problem()
        pipes = [p.unknown(('pipe', k), 0.0, 5.0, FLOW, 4.0) for k in range(3)]
        for k in range(3):
            p.claim({pipes[k]: 1.0}, 4.0)
        for name, members, value in limits:
            p.at_most(name, {pipes[k]: 1.0 for k in members}, value)
        return p

    solver = Solver()
    sequence = [
        [('all', (0, 1, 2), 6.0)],
        [('all', (0, 1, 2), 6.0), ('first two', (0, 1), 2.0)],
        [('first two', (0, 1), 2.0)],
        [('first two', (0, 1), 3.0), ('last', (2,), 1.0)],
        [],
    ]
    expected = [[2, 2, 2], [1, 1, 4], [1, 1, 4], [1.5, 1.5, 1], [4, 4, 4]]
    for limits, rates in zip(sequence, expected):
        answer = solver.solve(moment(limits))
        assert answer.x == pytest.approx(rates, abs=1e-5)
        same(answer, fresh(moment(limits)))


def test_an_unknown_with_a_new_scale_is_a_new_column():
    def moment(scale):
        p = Problem()
        x = p.unknown('x', 0.0, 10.0, FLOW, 6.0, scale)
        y = p.unknown('y', 0.0, 10.0, FLOW, 6.0)
        p.at_most('limit', {x: 1.0, y: 1.0}, 8.0)
        p.claim({x: 1.0}, 6.0)
        p.claim({y: 1.0}, 6.0)
        return p

    solver = Solver()
    for scale in (1.0, 1e-3, 1e-3, 1.0):
        answer = solver.solve(moment(scale))
        assert answer.x == pytest.approx([4.0, 4.0], abs=1e-5)
        same(answer, fresh(moment(scale)))


def sequence():
    """A run's problems: the worked network through its moments, then a shortage."""
    return [
        cases.network(),
        cases.network(clinic_first=True),
        cases.network((0, 3, 3)),
        cases.network(garden_up=False),
        cases.network((0, 2, 6), (4, 0, 0)),
    ]


def run(solver, others=None):
    """The answers of one run: the sequence on `solver`, with another solver answering other
    problems between its solves when `others` is given."""
    noise = (cases.bottlenecks(True), cases.pump(), cases.provider())
    answers = []
    for k, problem in enumerate(sequence()):
        if others is not None and k < len(noise):
            others.solve(noise[k])
        answers.append(solver.solve(problem))
    return answers


def test_each_run_answers_alike_alone_and_beside_others():
    # the worked network's rates are at most 8 W: within the tolerance of the steps, not bit for bit
    for a, b in zip(run(Solver()), run(Solver(), Solver())):
        same(a, b, size=8.0)
        assert a.levels == pytest.approx(b.levels, abs=TOLERANCE)


def test_the_same_run_repeated_is_identical():
    first, second = run(Solver(), Solver()), run(Solver(), Solver())
    for a, b in zip(first, second):
        assert np.array_equal(a.x, b.x) and np.array_equal(a.levels, b.levels, equal_nan=True)
        assert a.optima == b.optima


def test_a_problem_solved_again_on_a_kept_solver():
    solver = Solver()
    first = solver.solve(cases.bottlenecks(True))
    second = solver.solve(cases.bottlenecks(True))
    same(second, first, size=6.0)
