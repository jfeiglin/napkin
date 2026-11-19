"""Each named failure of a solve, and the problems that the library refuses as malformed.

A solve that cannot give the answer of the selection order raises `SolveFailure` with a name, the
step that stopped and what it reached, and never gives another answer in its place (G0, D0). A
budget is forced small here where a budget is meant. A run of HiGHS whose status says nothing of
the program, or whose optimum misses it, is run again on fresh instances first (`kept.Kept.run`);
such a status and such an optimum are forced here.
"""

import itertools
import math
from fractions import Fraction as F

import numpy as np
import pytest

from napkin.engine.solve import (
    DISTANCE_BUDGET,
    FAIR_BUDGET,
    FLOW,
    INFEASIBLE,
    INTERNAL,
    NUMERICAL,
    OTHER,
    UNBOUNDED,
    Budget,
    Problem,
    SolveFailure,
    Solver,
    distance,
)
from napkin.engine.solve.kept import Kept, Status

from . import cases


def failure(problem, **budget):
    with pytest.raises(SolveFailure) as caught:
        Solver(Budget(**budget)).solve(problem)
    return caught.value


def test_crossed_bounds_are_infeasible_before_any_program():
    p = Problem()
    p.unknown('outreach', 30.0, 20.0, OTHER)
    stopped = failure(p)
    assert (stopped.name, stopped.step) == (INFEASIBLE, 'the hard constraints')
    assert stopped.reached == {'unknown': 'outreach'}


def test_contradictory_rows_are_infeasible():
    p = Problem()
    x, y = p.unknown('x', 0.0, 10.0), p.unknown('y', 0.0, 10.0)
    p.at_least('at least five', {x: 1.0, y: 1.0}, 5.0)
    p.at_most('at most four', {x: 1.0, y: 1.0}, 4.0)
    assert failure(p).name == INFEASIBLE
    # with a written objective the first program is the objective's, and the failure is the same
    p.minimize({x: 1.0})
    stopped = failure(p)
    assert (stopped.name, stopped.step) == (INFEASIBLE, 'the hard constraints')


def test_an_empty_row_that_cannot_hold_is_infeasible():
    p = Problem()
    p.unknown('x', 0.0, 1.0)
    p.at_least('nothing at least one', {}, 1.0)
    stopped = failure(p)
    assert (stopped.name, stopped.reached) == (INFEASIBLE, {'row': 'nothing at least one'})


def test_an_unbounded_first_objective():
    p = Problem()
    x = p.unknown('x', 0.0, math.inf, OTHER)
    p.maximize({x: 1.0})
    stopped = failure(p)
    assert (stopped.name, stopped.step) == (UNBOUNDED, 'objective 1')


def test_an_objective_unbounded_on_the_face_of_the_earlier_one():
    p = Problem()
    x, y = p.unknown('x', 0.0, 4.0, OTHER), p.unknown('y', -math.inf, math.inf, OTHER)
    p.at_least('tie', {x: 1.0, y: -1.0}, 0.0)
    p.maximize({x: 1.0})  # x = 4, and y <= 4 stays open below
    p.minimize({y: 1.0})
    stopped = failure(p)
    assert (stopped.name, stopped.step) == (UNBOUNDED, 'objective 2')


def test_fair_sharing_stops_by_name_at_its_budget():
    # the two bottlenecks need two programs: 1/3 for a and b, then 1/2 for c
    stopped = failure(cases.bottlenecks(objective=False), fair_programs=1)
    assert (stopped.name, stopped.step) == (FAIR_BUDGET, 'fair sharing, tier 0')
    assert stopped.reached == {'levels': 1, 'programs': 1, 'held': 2, 'pending': 1}
    assert '1 levels in 1 programs, 1 claims pending' in str(stopped)
    assert Solver(Budget(fair_programs=2)).solve(cases.bottlenecks(objective=False)).work.fair_programs == 2


def test_the_fair_budget_counts_every_tier():
    stopped = failure(cases.reservoir((0, 1)), fair_programs=1)
    assert (stopped.name, stopped.step) == (FAIR_BUDGET, 'fair sharing, tier 1')


def test_the_distance_step_stops_by_name_at_its_budget():
    stopped = failure(cases.band(0.0), newton_steps=0, qp_iterations=0)
    assert (stopped.name, stopped.step) == (DISTANCE_BUDGET, 'distance of the others')
    assert stopped.reached['qp iterations'] == 0


def test_a_lost_optimum_is_a_numerical_failure_and_no_answer(monkeypatch):
    # a distance step that breaks the kept optimum: the end check refuses the answer
    select = distance.select

    def broken(face, w, budget, work):
        xi = select(face, w, budget, work)
        return np.where(w.kind == FLOW, 0.0, xi)

    monkeypatch.setattr(distance, 'select', broken)
    stopped = failure(cases.bottlenecks(objective=True))
    assert (stopped.name, stopped.step) == (NUMERICAL, 'objective 1')
    assert stopped.reached['lost'][0][0] == 1


def test_a_row_missed_by_a_step_is_a_numerical_failure(monkeypatch):
    select = distance.select
    monkeypatch.setattr(distance, 'select', lambda face, w, budget, work: select(face, w, budget, work) + 1.0)
    stopped = failure(cases.sum_one())
    assert (stopped.name, stopped.step) == (NUMERICAL, 'the end check')


def test_a_failure_leaves_the_kept_solver_usable():
    solver = Solver(Budget(fair_programs=1))
    with pytest.raises(SolveFailure):
        solver.solve(cases.bottlenecks(objective=False))
    answer = solver.solve(cases.shared_limit(('A',)))
    assert answer.x == pytest.approx([2.0], abs=1e-6)


def unknown(monkeypatch, failing):
    """Make the runs of HiGHS numbered `failing` (from one, over every instance) end with the status
    kUnknown after the run itself, so that HiGHS holds the basis that the run reached, as a kept
    instance did at 30,000 places (`kept`)."""
    once, count = Kept._once, itertools.count(1)

    def run(self):
        found = once(self)
        if next(count) in failing:
            found.status = Status.kUnknown
        return found

    monkeypatch.setattr(Kept, '_once', run)


def bottlenecks_answered(answer):
    # worked by hand: all three rise to 2 W, where a + b <= 4 binds; then c rises to 3 W, where
    # b + c <= 5 binds; served fractions 1/3, 1/3 and 1/2 of 6 W
    assert answer.levels == pytest.approx([F(1, 3), F(1, 3), F(1, 2)], abs=1e-6)
    assert answer.x == pytest.approx([2, 2, 3], abs=6e-6)


def test_a_fair_program_that_says_nothing_is_run_again_on_a_fresh_instance(monkeypatch):
    # the first run finds the hard constraints feasible; the second is the first fair program
    unknown(monkeypatch, {2})
    answer = Solver().solve(cases.bottlenecks(objective=False))
    bottlenecks_answered(answer)
    assert answer.work.renewals == 1


def test_a_fresh_instance_with_no_basis_comes_next(monkeypatch):
    unknown(monkeypatch, {2, 3})
    answer = Solver().solve(cases.bottlenecks(objective=False))
    bottlenecks_answered(answer)
    assert answer.work.renewals == 2


def test_an_objective_program_that_says_nothing_is_run_again(monkeypatch):
    unknown(monkeypatch, {1})
    answer = Solver().solve(cases.bottlenecks(objective=True))
    assert answer.work.renewals == 1
    # a + b <= 4 and b + c <= 5 serve at most 9 - b W of 18 W: the least unmet is 9 W, at b = 0
    assert answer.optima[0] == pytest.approx(9.0, abs=6e-6)


def test_a_status_that_fresh_instances_meet_too_stops_by_name_with_the_size(monkeypatch):
    unknown(monkeypatch, {2, 3, 4})
    solver = Solver()
    with pytest.raises(SolveFailure) as caught:
        solver.solve(cases.bottlenecks(objective=False))
    stopped = caught.value
    assert (stopped.name, stopped.step) == (NUMERICAL, 'fair sharing, tier 0')
    # the program of the tier: a, b, c and the level t; the two limits and the three claim rows
    assert stopped.reached == {'status': 'kUnknown', 'rows': 5, 'columns': 4}
    assert 'kUnknown on a program of 5 rows and 4 columns, and so did two fresh instances' in str(stopped)
    # the solver holds the last fresh instance, and it answers the next solve
    monkeypatch.undo()
    bottlenecks_answered(solver.solve(cases.bottlenecks(objective=False)))


def drifted(monkeypatch, failing):
    """Make the runs of HiGHS numbered `failing` give values that miss their program, the first value
    one unit high, as the values of a kept instance drifted from its rows at 30,000 places (`kept`)."""
    once, count = Kept._once, itertools.count(1)

    def run(self):
        found = once(self)
        if next(count) in failing:
            found.x = found.x.copy()
            found.x[0] += 1.0
        return found

    monkeypatch.setattr(Kept, '_once', run)


def test_an_optimum_whose_values_miss_the_program_is_run_again(monkeypatch):
    drifted(monkeypatch, {2})
    answer = Solver().solve(cases.bottlenecks(objective=False))
    bottlenecks_answered(answer)
    assert answer.work.renewals == 1


def test_an_optimum_that_misses_on_fresh_instances_too_stops_by_name(monkeypatch):
    drifted(monkeypatch, {2, 3, 4})
    stopped = failure(cases.bottlenecks(objective=False))
    assert (stopped.name, stopped.step) == (NUMERICAL, 'fair sharing, tier 0')
    # at t* = 1/3, a = b = 2 W; a read as 3 W misses a + b <= 4 W by 1 W of 1 + 3 + 2, its size
    assert stopped.reached == {'status': 'kOptimal', 'missed': pytest.approx(1 / 6), 'rows': 5, 'columns': 4}
    assert 'misses the program by 1.7e-01 of the size of its terms on a program of 5 rows' in str(stopped)


def test_unknown_failure_names_are_refused():
    with pytest.raises(ValueError, match='no failure'):
        SolveFailure('slow', 'somewhere', 'a name that the library does not have')


@pytest.mark.parametrize(
    'build',
    [
        lambda p: p.unknown('x', math.nan, 1.0),
        lambda p: p.unknown('x', 0.0, 1.0, scale=0.0),
        lambda p: p.unknown('x', 0.0, 1.0, target=math.inf),
        lambda p: p.unknown('x', 0.0, 1.0, kind=7),
        lambda p: [p.unknown('x'), p.unknown('x')],
        lambda p: p.row('r', {3: 1.0}),
        lambda p: p.row('r', {p.unknown('x'): math.inf}),
        lambda p: p.claim({p.unknown('x'): 1.0}, -1.0),
        lambda p: p.claim({p.unknown('x'): 1.0}, 1.0, tier=-1),
        lambda p: p.maximize({p.positive_part('unmet', {p.unknown('x'): -1.0}, 2.0): 1.0}),
    ],
)
def test_malformed_problems_are_refused(build):
    with pytest.raises(ValueError):
        build(Problem())


def test_a_request_of_zero_makes_no_claim():
    p = Problem()
    x = p.unknown('x', 0.0, 1.0, FLOW, 0.0)
    assert p.claim({x: 1.0}, 0.0) is None
    assert list(p.claims([x, x], [0.0, 2.0])) == [-1, 0]
    assert p.arrays().request.tolist() == [2.0]
    assert p.arrays().kind.tolist() == [FLOW]
    assert INTERNAL not in p.arrays().kind.tolist()
