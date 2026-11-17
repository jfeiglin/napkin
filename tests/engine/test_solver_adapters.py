"""The conformance suite of the solver adapters (`napkin/engine/solvers.py`).

Each test states one guarantee of the interface and checks it for every adapter. The oracles are
closed forms: the solution of each problem here is known, so an adapter is judged against the
mathematics, never against another solver. A solver that fails one of these is no candidate for the
engine, whatever its speed.
"""

import itertools
import math
import pickle

import numpy as np
import pytest

from napkin.engine import solvers
from napkin.engine.solvers import SolverFailure

RTOL, ATOL = 1e-8, 1e-10
# How far a solution may be from the closed form, in units of the error that the tolerances ask for at
# each step. The global error of a run adds the errors of its steps, so the factor is above 1.
SLACK = 200


# ---- the problems: each with its closed form ------------------------------------------------------


class Problem:
    """`y' = fun(t, y)` from `y0` at `t0` to `t_end`, whose solution `exact(t)` is known."""

    def __init__(self, name, fun, t0, y0, t_end, exact, jac=None):
        self.name, self.fun, self.t0, self.t_end, self.exact, self.jac = name, fun, t0, t_end, exact, jac
        self.y0 = np.asarray(y0, dtype=float)


def decay():
    """One value that decays: y = y0 e^(-k t)."""
    k = 0.7
    return Problem(
        'decay', lambda t, y: -k * y, 0.0, [3.0], 5.0, lambda t: np.array([3.0 * math.exp(-k * t)])
    )


def stiff():
    """Two values with rates of -1 and -10,000, mixed by a matrix that is not orthogonal: the closed
    form is the sum of the two modes. An explicit method needs steps of 1e-4; a stiff solver does not."""
    v = np.array([[1.0, 1.0], [0.3, -2.0]])
    lam = np.array([-1.0, -1.0e4])
    a = v @ np.diag(lam) @ np.linalg.inv(v)
    c = np.linalg.solve(v, np.array([2.0, 1.0]))
    return Problem(
        'stiff',
        lambda t, y: a @ y,
        0.0,
        [2.0, 1.0],
        4.0,
        lambda t: v @ (c * np.exp(lam * t)),
        jac=lambda t, y: a,
    )


def logistic():
    """A value that grows to a limit: y = K / (1 + (K / y0 - 1) e^(-r t))."""
    r, cap, y0 = 1.3, 8.0, 0.25
    return Problem(
        'logistic',
        lambda t, y: r * y * (1 - y / cap),
        0.0,
        [y0],
        9.0,
        lambda t: np.array([cap / (1 + (cap / y0 - 1) * math.exp(-r * t))]),
        jac=lambda t, y: np.array([[r * (1 - 2 * y[0] / cap)]]),
    )


def forced():
    """A decay that a sine drives, from a time that is not zero: y' = -a y + sin(t)."""
    a, t0, y0 = 2.0, 1.0, 0.4

    def particular(t):
        return (a * math.sin(t) - math.cos(t)) / (a * a + 1)

    c = (y0 - particular(t0)) * math.exp(a * t0)
    return Problem(
        'forced',
        lambda t, y: -a * y + math.sin(t),
        t0,
        [y0],
        7.5,
        lambda t: np.array([c * math.exp(-a * t) + particular(t)]),
    )


def cubic():
    """A rate that reads only the time: y = t^3, with a second value that reads the first."""
    return Problem(
        'cubic',
        lambda t, y: np.array([3 * t * t, y[0]]),
        0.0,
        [0.0, 1.0],
        2.0,
        lambda t: np.array([t**3, 1 + t**4 / 4]),
    )


PROBLEMS = [decay, stiff, logistic, forced, cubic]
ADAPTERS = sorted(solvers.ADAPTERS)


def run_of(adapter, problem, **options):
    options = {'rtol': RTOL, 'atol': ATOL, **options}
    return solvers.ADAPTERS[adapter].start(problem.fun, problem.t0, problem.y0, problem.t_end, **options)


def steps_of(adapter, problem, **options):
    run, steps = run_of(adapter, problem, **options), []
    while not run.finished:
        steps.append(run.step())
        assert len(steps) < 100_000
    return run, steps


def allowed(exact):
    """The distance from the closed form that the tolerances allow, with the slack of a whole run."""
    return SLACK * (RTOL * np.abs(exact) + ATOL)


cases = pytest.mark.parametrize(('adapter', 'make'), [(a, p) for a in ADAPTERS for p in PROBLEMS])


# ---- the guarantees ----------------------------------------------------------------------------------


@cases
def test_the_steps_join_and_the_last_ends_exactly_at_the_end(adapter, make):
    problem = make()
    run, steps = steps_of(adapter, problem)
    assert steps[0].t_old == problem.t0
    for before, after in itertools.pairwise(steps):
        assert after.t_old == before.t and after.t > after.t_old
    # The end itself, not a time near it: the engine's moments are exact times.
    assert steps[-1].t == problem.t_end and run.finished
    with pytest.raises(RuntimeError):
        run.step()


@cases
def test_each_accepted_state_is_the_closed_form_within_the_tolerances(adapter, make):
    problem = make()
    _, steps = steps_of(adapter, problem)
    for step in steps:
        exact = problem.exact(step.t)
        assert np.all(np.abs(step.y - exact) <= allowed(exact)), (step.t, step.y, exact)


@cases
def test_the_solution_between_two_steps_is_the_closed_form_and_meets_the_steps_at_its_ends(adapter, make):
    problem = make()
    _, steps = steps_of(adapter, problem)
    state = problem.y0
    for step in steps:
        # At its two ends the solution between the steps is the accepted states, to roundoff.
        scale = np.abs(step.y) + np.abs(state) + ATOL
        assert np.all(np.abs(step.dense(step.t) - step.y) <= 1e-9 * scale)
        assert np.all(np.abs(step.dense(step.t_old) - state) <= 1e-9 * scale)
        for part in (0.25, 0.5, 0.9):
            at = step.t_old + part * (step.t - step.t_old)
            exact = problem.exact(at)
            # The solution between the steps has a lower order than the steps: a wider slack.
            assert np.all(np.abs(step.dense(at) - exact) <= 50 * allowed(exact)), (at, step.dense(at), exact)
        state = step.y


@cases
def test_the_solution_and_its_rate_next_to_an_end_of_a_step_are_those_at_the_end(adapter, make):
    """The engine asks for the solution at the next number after a time (the first time after a
    moment). At the number next to an end of a step, also next to a start at zero, the solution
    and its rate are finite and are those at the end, to roundoff."""
    problem = make()
    _, steps = steps_of(adapter, problem)
    for step in steps[:8] + steps[-3:]:
        for end, toward in ((step.t_old, step.t), (step.t, step.t_old)):
            near = np.nextafter(end, toward)
            value, rate = step.dense(near), step.rate(near)
            assert np.all(np.isfinite(value)) and np.all(np.isfinite(rate))
            size = np.abs(step.dense(end)) + ATOL
            assert np.all(np.abs(value - step.dense(end)) <= 1e-9 * size)
            assert np.all(np.abs(rate - step.rate(end)) * (step.t - step.t_old) <= 1e-6 * size)


@cases
def test_the_solution_between_two_steps_outlives_its_run_and_goes_through_pickle(adapter, make):
    problem = make()
    run, steps = steps_of(adapter, problem)
    points = [(step, step.t_old + 0.37 * (step.t - step.t_old)) for step in steps]
    before = [step.dense(at) for step, at in points]
    kept = pickle.loads(pickle.dumps([step.dense for step in steps]))
    del run
    for (step, at), value, again in zip(points, before, kept):
        assert np.array_equal(step.dense(at), value)
        assert np.array_equal(again(at), value)


@cases
def test_the_rate_between_two_steps_is_the_derivative_of_the_solution_between_them(adapter, make):
    """`rate(at)` is the derivative of `dense` at `at`. Two oracles.

    - The sum of the rate over a part of the step is the change of `dense` over that part. The
      solution between two steps is a polynomial of a degree of 5 at the most, so six points of
      Gauss and Legendre give the sum of its rate with no error but roundoff.
    - The rate of the closed form at the time, `fun(at, exact(at))`. What the engine reads is the
      rate times the length of the step (`integrate.apart`): that product is within the tolerances
      of the product for the closed form, as the solution between the steps is."""
    problem = make()
    _, steps = steps_of(adapter, problem)
    points, weights = np.polynomial.legendre.leggauss(6)
    for step in steps:
        length = step.t - step.t_old
        size = np.abs(step.dense(step.t_old)) + np.abs(step.y) + ATOL
        for first, last in ((0.0, 1.0), (0.1, 0.6), (0.5, 1.0)):
            low, high = step.t_old + first * length, step.t_old + last * length
            middle, half = (low + high) / 2, (high - low) / 2
            total = sum(w * step.rate(middle + half * x) for x, w in zip(points, weights)) * half
            assert np.all(np.abs(step.dense(high) - step.dense(low) - total) <= 1e-9 * size), (low, high)
        for part in (0.0, 0.25, 0.5, 0.9, 1.0):
            at = step.t_old + part * length
            exact = problem.exact(at)
            true = np.asarray(problem.fun(at, exact), dtype=float)
            assert np.all(np.abs(step.rate(at) - true) * length <= allowed(exact)), (at, step.rate(at), true)


@cases
def test_the_rate_between_two_steps_outlives_its_run_and_goes_through_pickle(adapter, make):
    problem = make()
    run, steps = steps_of(adapter, problem)
    points = [(step, step.t_old + 0.37 * (step.t - step.t_old)) for step in steps]
    before = [step.rate(at) for step, at in points]
    kept = pickle.loads(pickle.dumps([step.rate for step in steps]))
    del run
    for (step, at), value, again in zip(points, before, kept):
        assert np.array_equal(step.rate(at), value)
        assert np.array_equal(again(at), value)


@cases
def test_a_step_that_is_taken_again_starts_where_it_started_and_is_no_longer_than_its_limit(adapter, make):
    """`retake(limit)` forgets the last step. The next step starts at the same time from the same
    state and is no longer than the limit; the work of the forgotten step stays in the counts; the
    steps still join, the last ends exactly at the end, and the run is still the closed form within
    the tolerances. Each fourth step of the first forty is taken again here, with a quarter of its
    length, and the last step of the run twice. (A solver that keeps no step to go back to starts
    again at that time, at its lowest order: it takes more steps from there.)"""
    problem = make()
    run, steps, again, ends = run_of(adapter, problem), [], 0, 0
    state = problem.y0
    while not run.finished:
        step = run.step()
        if (len(steps) % 4 == 3 and again < 10) or (run.finished and ends < 2):
            again, ends = again + 1, ends + run.finished
            before, limit = run.counts(), (step.t - step.t_old) / 4
            run.retake(limit)
            # The work of the forgotten step stays in each count.
            assert not run.finished and run.counts() == before
            taken = run.step()
            # The length is a difference of two times: it has the roundoff of the times.
            assert taken.t_old == step.t_old and taken.t - taken.t_old <= limit + 4 * np.spacing(taken.t)
            scale = np.abs(state) + ATOL
            assert np.all(np.abs(taken.dense(taken.t_old) - state) <= 1e-9 * scale)
            after = run.counts()
            assert all(after[name] >= before[name] for name in before)
            assert after['evaluations'] > before['evaluations']
            run.limit(np.inf)
            step = taken
        steps.append(step)
        state = step.y
        assert len(steps) < 100_000
    assert again > 2 and ends == 2 and steps[0].t_old == problem.t0 and steps[-1].t == problem.t_end
    for earlier, later in itertools.pairwise(steps):
        assert later.t_old == earlier.t and later.t > later.t_old
    # The error of a run adds the errors of its steps, and each step that is taken again is
    # shorter: a run with more steps than the slack of a whole run counts has that many errors.
    slack = max(1.0, len(steps) / SLACK)
    for step in steps:
        exact = problem.exact(step.t)
        assert np.all(np.abs(step.y - exact) <= slack * allowed(exact)), (step.t, step.y, exact)


@pytest.mark.parametrize('adapter', ADAPTERS)
def test_a_limit_holds_from_the_next_step_on_and_the_steps_grow_again_with_no_limit(adapter):
    """The stiff problem takes long steps when its fast mode has gone. With a limit of a fifth of
    its longest step from its sixth step on, no later step is longer, and the limit is what holds
    some of them; from the time that the limit is taken away, a step is longer again. The run is
    the closed form within the tolerances."""
    problem = stiff()
    limit = max(step.t - step.t_old for step in steps_of(adapter, problem)[1]) / 5
    run, steps, lifted = run_of(adapter, problem), [], None
    while not run.finished:
        if len(steps) == 6:
            run.limit(limit)
        if lifted is None and steps and steps[-1].t > problem.t_end / 2:
            run.limit(np.inf)
            lifted = len(steps)
        steps.append(run.step())
    lengths = [step.t - step.t_old for step in steps]
    held = lengths[6:lifted]
    assert lifted is not None and len(held) > 12
    assert max(held) <= limit + 4 * np.spacing(problem.t_end)
    assert sum(1 for length in held if length > 0.99 * limit) > 12
    assert max(lengths[lifted:]) > 2 * limit
    for step in steps:
        exact = problem.exact(step.t)
        assert np.all(np.abs(step.y - exact) <= allowed(exact)), (step.t, step.y, exact)


@cases
def test_the_same_problem_gives_the_same_steps_bit_for_bit(adapter, make):
    _, first = steps_of(adapter, make())
    _, second = steps_of(adapter, make())
    assert [(step.t_old, step.t) for step in first] == [(step.t_old, step.t) for step in second]
    assert all(np.array_equal(a.y, b.y) for a, b in zip(first, second))


@cases
def test_a_run_from_the_state_of_any_step_goes_on_to_the_closed_form(adapter, make):
    """The engine starts a new run at every moment, from the time and the state of a step."""
    problem = make()
    _, steps = steps_of(adapter, problem)
    middle = steps[len(steps) // 2]
    if middle.t == problem.t_end:
        return  # one step only: nothing is left to run
    again = Problem(problem.name, problem.fun, middle.t, middle.y, problem.t_end, problem.exact)
    _, rest = steps_of(adapter, again)
    assert rest[0].t_old == middle.t and rest[-1].t == problem.t_end
    exact = problem.exact(problem.t_end)
    assert np.all(np.abs(rest[-1].y - exact) <= 2 * allowed(exact))


@pytest.mark.parametrize('adapter', ADAPTERS)
def test_a_tighter_tolerance_gives_a_smaller_error(adapter):
    """The tolerances are what the solver controls: a run at 1e-10 is nearer to the closed form than a
    run at 1e-4, by orders of magnitude and not by chance."""
    problem = logistic()
    errors = []
    for rtol in (1e-4, 1e-7, 1e-10):
        _, steps = steps_of(adapter, problem, rtol=rtol, atol=rtol * 1e-2)
        errors.append(max(float(np.max(np.abs(step.y - problem.exact(step.t)))) for step in steps))
    assert errors[0] > 30 * errors[1] > 900 * errors[2] > 0


@pytest.mark.parametrize('adapter', ADAPTERS)
def test_a_given_jacobian_gives_the_same_solution_with_fewer_evaluations(adapter):
    problem = stiff()
    plain, steps = steps_of(adapter, problem)
    given, with_jac = steps_of(adapter, problem, jac=problem.jac)
    exact = problem.exact(problem.t_end)
    for found in (steps, with_jac):
        assert np.all(np.abs(found[-1].y - exact) <= allowed(exact))
    assert given.counts()['evaluations'] < plain.counts()['evaluations']
    assert {'evaluations', 'jacobians', 'factorizations'} <= set(plain.counts())
    assert plain.counts()['evaluations'] >= len(steps)


@pytest.mark.parametrize('adapter', ADAPTERS)
def test_a_given_jacobian_is_read_by_row_and_column(adapter):
    """A Jacobian that is not its own transpose, of a problem whose fast mode has the rate -10,000: a
    solver that read the transpose would iterate with a wrong matrix at each step. With the true
    matrix a run needs few evaluations for each step; the transpose needs many more, or fails."""
    problem = stiff()
    true, steps = steps_of(adapter, problem, jac=problem.jac)
    assert not np.allclose(problem.jac(0.0, problem.y0), problem.jac(0.0, problem.y0).T)
    try:
        wrong, other = steps_of(adapter, problem, jac=lambda t, y: problem.jac(t, y).T)
    except SolverFailure:
        return
    per_step = true.counts()['evaluations'] / len(steps)
    assert wrong.counts()['evaluations'] / len(other) > 1.5 * per_step or len(other) > 2 * len(steps)


@pytest.mark.parametrize('adapter', ADAPTERS)
def test_a_stiff_problem_takes_steps_far_longer_than_its_fast_rate(adapter):
    """The fast mode has a time of 1e-4. A solver that is not made for stiff problems needs steps of
    that size for the whole run: 40,000 of them. A stiff solver takes a few hundred at the most."""
    _, steps = steps_of(adapter, stiff())
    assert len(steps) < 400
    assert max(step.t - step.t_old for step in steps) > 1e-2


@pytest.mark.parametrize('adapter', ADAPTERS)
def test_a_problem_with_no_solution_to_the_end_is_a_failure_and_no_wrong_state(adapter):
    """y' = y^2 from 1 has the solution y = 1 / (1 - t), which has no value at t = 1. While the
    solution is below 1,000 each state that the solver accepts is that solution; then it fails. The
    run never finishes, and no accepted time is past the pole by more than a rounding of the time.

    How near a state must be: a solution that is late or early by a small time e differs by y' e, which
    is y^2 e here. So an error of the time, which the tolerances bound, is an error of the state that
    grows with the square of the state, for every solver. The bound is that: the slack of a whole run
    times the relative tolerance, times y^2."""
    problem = Problem('pole', lambda t, y: y * y, 0.0, [1.0], 2.0, lambda t: np.array([1 / (1 - t)]))
    run = run_of(adapter, problem)
    last = None
    with pytest.raises(SolverFailure):
        for _ in range(100_000):
            last = run.step()
            assert last.t < 1.0 + 1e-9
            exact = problem.exact(last.t)
            if last.t < 1.0 and exact[0] < 1e3:
                assert abs(last.y[0] - exact[0]) <= SLACK * RTOL * exact[0] ** 2
    assert last is not None and not run.finished


@pytest.mark.parametrize('adapter', ADAPTERS)
def test_a_root_between_two_steps_is_found_on_the_solution_between_them(adapter):
    """The engine finds the time of an event on the solution between two accepted steps. The decay
    reaches the value 1 at ln(3) / k."""
    from scipy.optimize import brentq

    problem = decay()
    _, steps = steps_of(adapter, problem)
    step = next(step for step in steps if step.y[0] <= 1.0)
    found = brentq(lambda at: step.dense(at)[0] - 1.0, step.t_old, step.t, xtol=1e-13, rtol=1e-13)
    assert found == pytest.approx(math.log(3.0) / 0.7, abs=1e-6)
