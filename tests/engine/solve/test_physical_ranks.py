"""Earlier ranks use the physical problem; the final distance uses the declared metric."""

import math

import pytest

from napkin.engine.solve import OTHER, Problem, SolveFailure, Solver
from napkin.engine.solve.failures import UNBOUNDED

LIMIT = 1_000_000_000


def two_unknowns(scale, *, upper=LIMIT):
    problem = Problem()
    x = problem.unknown('x', 0, LIMIT, OTHER, scale=LIMIT)
    y = problem.unknown('y', 0, upper, OTHER, scale=scale)
    return problem, x, y


@pytest.mark.parametrize('scale', [1, LIMIT], ids=['small-y-scale', 'matched-scales'])
@pytest.mark.parametrize('reversed_rank', [False, True], ids=['maximize', 'keep-first-rank'])
def test_each_bounded_coordinate_contributes_to_the_first_rank(scale, reversed_rank):
    problem, x, y = two_unknowns(scale)
    problem.maximize({x: 1, y: 1})
    if reversed_rank:
        problem.minimize({y: 1})
    answer = Solver().solve(problem)
    assert answer.x == pytest.approx([LIMIT, LIMIT])


@pytest.mark.parametrize('scale', [1, LIMIT], ids=['small-y-scale', 'matched-scales'])
def test_unbounded_ray_still_improves_the_first_rank(scale):
    problem, x, y = two_unknowns(scale, upper=math.inf)
    problem.maximize({x: 1, y: 1})
    with pytest.raises(SolveFailure) as failure:
        Solver().solve(problem)
    assert (failure.value.name, failure.value.step) == (UNBOUNDED, 'objective 1')


@pytest.mark.parametrize('scale', [1, LIMIT], ids=['small-y-scale', 'matched-scales'])
@pytest.mark.parametrize('tied', [False, True], ids=['unique-first-rank', 'second-rank-breaks-tie'])
def test_physical_equality_and_earlier_optimum_survive_rekeying_the_metric(scale, tied):
    problem, x, y = two_unknowns(scale)
    problem.equal('total', {x: 1, y: 1}, LIMIT)
    # With a tie the entire row is optimal; otherwise every replacement of x by y improves the cost.
    problem.maximize({x: 1, y: 1 if tied else 2})
    if tied:
        problem.maximize({y: 1})
    assert Solver().solve(problem).x == pytest.approx([0, LIMIT])


@pytest.mark.parametrize('scale', [1, LIMIT], ids=['small-y-scale', 'matched-scales'])
def test_the_only_feasible_vertex_remains_feasible(scale):
    problem, x, y = two_unknowns(scale)
    problem.at_most('ceiling', {x: 1}, 30)
    problem.at_least('floor', {x: 1, y: 1}, LIMIT + 30)
    problem.maximize({x: 1, y: 1})
    assert Solver().solve(problem).x == pytest.approx([30, LIMIT])


@pytest.mark.parametrize('scale', [1, LIMIT], ids=['small-y-scale', 'matched-scales'])
def test_equal_claims_split_a_shared_physical_resource(scale):
    problem, x, y = two_unknowns(scale)
    problem.at_most('shared', {x: 1, y: 1}, LIMIT)
    problem.claim({x: 1}, LIMIT)
    problem.claim({y: 1}, LIMIT)
    answer = Solver().solve(problem)
    assert answer.levels == pytest.approx([0.5, 0.5])
    assert answer.x == pytest.approx([LIMIT / 2, LIMIT / 2])


@pytest.mark.parametrize('scales,expected', [((1, 3), (1, 9)), ((3, 1), (9, 1))])
def test_only_the_distance_uses_the_declared_metric(scales, expected):
    problem = Problem()
    x, y = problem.unknowns(('x', 'y'), 0, 10, OTHER, target=0, scale=scales)
    problem.equal('total', {x: 1, y: 1}, 10)
    # On x+y=10, the zero-target minimizer has x:y = scale_x^2:scale_y^2.
    assert Solver().solve(problem).x == pytest.approx(expected)
