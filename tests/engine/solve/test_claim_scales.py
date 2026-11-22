"""A fair tier in physical rates, including rows with very different fractions per unit of rate."""

import pytest

from napkin.engine.solve import Problem, Solver


@pytest.mark.parametrize('large', [1e9, 1e12])
def test_unequal_requests_keep_the_same_fraction_of_the_shared_rate(large):
    problem = Problem()
    x, y = problem.unknowns(('x', 'y'), 0, large)
    available = large / 2
    problem.at_most('sharing', {x: 1, y: 1}, available)
    problem.claim({x: 1}, 1)
    problem.claim({y: 1}, large)
    answer = Solver().solve(problem)
    fraction = available / (1 + large)
    assert answer.levels == pytest.approx([fraction, fraction], rel=1e-9)
    assert answer.x == pytest.approx([fraction, large * fraction], rel=1e-9)


def test_zero_service_of_a_blocked_aggregate_leaves_another_large_claim_free():
    problem = Problem()
    large = 1e9
    x, y, z = problem.unknowns(('x', 'y', 'z'), 0, large)
    problem.at_most('sharing', {x: 1, y: 1, z: 1}, 0.75 * large)
    problem.at_most('blocked', {x: 1, y: 1}, 0)
    problem.claim({x: 1, y: 1}, large)
    problem.claim({z: 1}, large)
    answer = Solver().solve(problem)
    assert answer.levels == pytest.approx([0, 0.75])
    assert answer.x == pytest.approx([0, 0, 0.75 * large])


def test_the_later_tier_keeps_a_large_aggregate_at_its_fair_level():
    problem = Problem()
    large = 1e9
    x, y, z = problem.unknowns(('x', 'y', 'z'), 0, large)
    problem.at_most('sharing', {x: 1, y: 1, z: 1}, large)
    problem.claim({x: 1, y: 1}, 2 * large)
    problem.claim({z: 1}, 3 * large)
    problem.claim({x: 1}, large, tier=1)
    answer = Solver().solve(problem)
    assert answer.levels == pytest.approx([0.2, 0.2, 0.4], rel=1e-9)
    assert answer.x == pytest.approx([0.4 * large, 0, 0.6 * large], rel=1e-9, abs=1e-6)
