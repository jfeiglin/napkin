"""The numerical segment's own Radau loop and its roots (`napkin/engine/continuous/integrate.py`).

`radau` must give the result of `solve_ivp` with Radau and dense output, bit for bit, for roots
that each end the integration, with one change: root location takes a root's values at the two
accepted states that bracket its crossing, not at the dense solution there, which can miss those
states by roundoff and lose the bracket. A SciPy event that gives back its accepted values
(`Endpoints`) makes solve_ivp the oracle of that claim. Agreement between two loops of one solver
says nothing about where a root lies, so closed forms locate roots too. `Roots` must give each
root's value together, at a step, as it gives it alone, to locate the root.
"""

import math

import numpy as np
import pytest
from scipy.integrate import DenseOutput, Radau, solve_ivp

import napkin.engine.continuous.integrate as integrate
from napkin.core.expr import read
from napkin.engine.continuous.integrate import Root, Roots, release_root
from napkin.engine.timeline import Plan, Run
from napkin.expressions import ExpressionError
from napkin.program import build as b
from napkin.program.config import Configuration, InputValue, Request


class Endpoints:
    """A root as a SciPy event that, at the two latest times at which solve_ivp evaluated it on
    accepted states, gives back the values that it gave there."""

    terminal = True

    def __init__(self, function, direction):
        self.function, self.direction, self.accepted = function, direction, []

    def __call__(self, t, state):
        for at, value in self.accepted:
            if t == at:
                return value
        value = self.function(t, state)
        if not self.accepted or t > self.accepted[-1][0]:
            self.accepted = [*self.accepted, (t, value)][-2:]
        return value


class Functions:
    """Roots that are functions of the time and the state, for `radau`."""

    def __init__(self, functions, directions):
        self.functions = functions
        self.direction = np.array(directions, dtype=float)

    def __len__(self):
        return len(self.functions)

    def value(self, k, at, state):
        return self.functions[k](at, state)

    def values(self, at, state):
        return np.array([function(at, state) for function in self.functions], dtype=float)


def problem(rng):
    """A small nonlinear system with forcing, crossings of levels and of a time, and solver options."""
    n = int(rng.integers(1, 4))
    a = rng.normal(0, 1, (n, n)) - 2 * np.eye(n)
    b, c = rng.normal(0, 1, n), float(rng.normal(0, 0.2))

    def fun(t, y):
        return a @ y + b + c * y * y + math.sin(3 * t)

    functions, directions = [], []
    for _ in range(int(rng.integers(0, 4))):
        i, level = int(rng.integers(n)), float(rng.normal(0, 0.5))
        functions.append(lambda t, y, i=i, level=level: y[i] - level)
        directions.append(int(rng.choice([-1, 0, 1])))
    end = float(rng.uniform(0.5, 3))
    if rng.random() < 0.3:
        stop = float(rng.uniform(0, end))
        functions.append(lambda t, y, stop=stop: t - stop)
        directions.append(1)
    options = {
        'rtol': 10 ** -rng.uniform(4, 9),
        'atol': 10 ** -rng.uniform(6, 11),
        'max_step': float(rng.choice([np.inf, end / 7])),
        'jac_sparsity': None if rng.random() < 0.5 else np.ones((n, n)),
    }
    return fun, (0.0, end), rng.normal(0, 1, n), functions, directions, options


def assert_same(got, want):
    assert (got.status, got.message, got.success) == (want.status, want.message, want.success)
    assert (got.nfev, got.njev, got.nlu) == (want.nfev, want.njev, want.nlu)
    assert got.t.tobytes() == want.t.tobytes()
    assert got.y.tobytes() == want.y.tobytes()
    if want.t_events is None:
        assert got.t_events is None and got.y_events is None
    else:
        for mine, theirs in zip(got.t_events + got.y_events, want.t_events + want.y_events, strict=True):
            assert mine.shape == theirs.shape and mine.tobytes() == theirs.tobytes()
    grid = np.linspace(want.t[0], want.t[-1], 41)
    assert got.sol(grid).tobytes() == want.sol(grid).tobytes()


def test_a_result_is_that_of_solve_ivp_bit_for_bit():
    rng = np.random.default_rng(20261025)
    statuses = set()
    for _ in range(60):
        fun, interval, y0, functions, directions, options = problem(rng)
        events = [Endpoints(f, d) for f, d in zip(functions, directions)] or None
        want = solve_ivp(fun, interval, y0, method='Radau', dense_output=True, events=events, **options)
        statuses.add(want.status)
        roots = Functions(functions, directions) if functions else None
        # A second integration with the same roots keeps nothing of the first.
        for _ in range(2):
            assert_same(integrate.radau(fun, interval, y0, roots=roots, **options), want)
        # A check interval that no step is longer than changes nothing: each step is read at its end.
        whole = interval[1] - interval[0]
        assert_same(integrate.radau(fun, interval, y0, roots=roots, check=whole, **options), want)
    assert statuses == {0, 1}


# ---- a check interval: the solver's steps can be longer than the interval of the roots ----------------

TIGHT = {'rtol': 1e-9, 'atol': 1e-12}


def test_the_rate_of_the_dense_solution_is_the_derivative_of_the_dense_solution():
    """`slope` reads the polynomial of SciPy's dense output of a Radau step. The oracle is a
    difference quotient of the dense solution itself."""
    solver = Radau(lambda t, y: [-y[0] * y[0], math.cos(t) - y[1]], 0.0, [1.0, 0.5], 10.0, **TIGHT)
    for _ in range(12):
        solver.step()
    solution = solver.dense_output()
    width = solution.t - solution.t_old
    for part in (0.1, 0.37, 0.5, 0.82, 0.99):
        at, h = solution.t_old + part * width, 1e-6 * width
        quotient = (solution(at + h) - solution(at - h)) / (2 * h)
        assert integrate.slope(solution, at) == pytest.approx(quotient, rel=1e-6, abs=1e-9)


def test_the_difference_of_a_step_is_the_step_times_the_gap_between_field_and_rate_in_tolerances():
    """`departure` for one quantity, by hand. The dense solution is 3 + 2x + x² - x³ with x the part
    of a step of length 4 from t = 10: at t = 12, x = 1/2, its value is 4.125 and its rate is
    (2 + 2x - 3x²) / 4 = 0.5625. With a field of 0.6 there, the gap is 0.0375; over the step that is
    0.15; the tolerance of the value is 1e-3 + 1e-2 × 4.125 = 0.04225."""
    from types import SimpleNamespace

    solution = SimpleNamespace(t_old=10.0, h=4.0, order=2, Q=np.array([[2.0, 1.0, -1.0]]))
    state = np.array([4.125])
    assert integrate.slope(solution, 12.0) == pytest.approx([0.5625], rel=1e-14)
    far = integrate.departure(lambda t, y: np.array([0.6]), solution, 12.0, state, 1e-2, 1e-3)
    assert far == pytest.approx(4.0 * 0.0375 / 0.04225, rel=1e-12)
    # Two quantities: the root of the mean of the squares of the two.
    two = SimpleNamespace(t_old=10.0, h=4.0, order=2, Q=np.array([[2.0, 1.0, -1.0], [0.0, 0.0, 0.0]]))
    far = integrate.departure(
        lambda t, y: np.array([0.6, 0.0]), two, 12.0, np.array([4.125, 1.0]), 1e-2, 1e-3
    )
    assert far == pytest.approx(4.0 * 0.0375 / 0.04225 / math.sqrt(2), rel=1e-12)


def test_the_next_step_brings_the_difference_to_its_aim_by_the_fourth_power_of_the_step():
    """The difference of a step grows as the fourth power of its length. So after a step of 100
    with a difference of 16 times the aim, the next one is half as long, with the margin of 0.9;
    with a difference at the aim it is as long, with the margin. A longest step of less than two
    check intervals is not worth its checks: the limit is the check interval. The limit of the
    solver itself is the most."""
    aim = integrate.AIM
    assert integrate.next_limit(100.0, 16 * aim, 1.0, math.inf) == pytest.approx(0.9 * 50.0)
    assert integrate.next_limit(100.0, aim, 1.0, math.inf) == pytest.approx(0.9 * 100.0)
    assert integrate.next_limit(100.0, aim, 1.0, 30.0) == 30.0
    assert integrate.next_limit(2.0, 16 * aim, 1.0, math.inf) == 1.0
    assert integrate.next_limit(100.0, math.inf, 1.0, math.inf) == 1.0
    assert integrate.next_limit(100.0, math.nan, 1.0, math.inf) == 1.0


def short_steps_until_longer(limit):
    """The steps of the check interval that a limit takes before it allows a longer step."""
    count = 0
    while limit.allowed == limit.check:
        limit.short()
        count += 1
        assert count < 1000
    return count


def test_the_wait_for_a_longer_step_doubles_with_each_fall_to_the_check_interval_in_a_row():
    """A step of 1.9 check intervals whose difference is 1.7 is not used, and a step that is a
    quarter as long as the fourth root of 0.25 / 1.7 gives is not worth its checks: the limit is
    the check interval. After the first such step, one step of the interval brings the limit to
    two intervals, as with no wait. After each further one in a row the wait is twice as long, to
    the longest wait; so where a longer step fails each time, the steps that are not used are one
    in that many, and not one in two."""
    limit = integrate.Limit(1.0, math.inf)
    assert limit.allowed == math.inf
    waits = []
    for _ in range(9):
        limit.unused(1.9, 1.7)
        assert limit.allowed == 1.0
        waits.append(short_steps_until_longer(limit))
        assert limit.allowed == 2.0
    assert waits == [min(2**k, integrate.LONGEST_WAIT) for k in range(9)]
    # A long run of such a part of a solution: one step in the longest wait and one is lost.
    steps = lost = 0
    for _ in range(200):
        limit.unused(1.9, 1.7)
        lost += 1
        steps += 1 + short_steps_until_longer(limit)
    assert lost / steps == pytest.approx(1 / (integrate.LONGEST_WAIT + 1))


def test_a_longer_step_that_is_used_but_allows_no_longer_step_waits_as_one_that_is_not_used():
    """A step of 1.6 intervals with a difference of 0.9 is used, but the step that its difference
    allows is shorter than two intervals: the limit is the check interval, and the wait grows as
    after a step that is not used. The two kinds count in one row."""
    limit = integrate.Limit(1.0, math.inf)
    waits = []
    for k in range(6):
        if k % 2:
            limit.unused(1.9, 1.7)
        else:
            limit.used(1.6, 0.9)
        assert limit.allowed == 1.0
        waits.append(short_steps_until_longer(limit))
    assert waits == [1, 2, 4, 8, 16, 32]


def test_a_longer_step_that_allows_a_longer_step_ends_the_wait():
    """After five falls to the check interval the wait is 32 steps. A step of 40 intervals with a
    difference at the aim is used and allows a step of 36: the limit follows it at once, and the
    next fall to the check interval waits one step again."""
    limit = integrate.Limit(1.0, math.inf)
    for _ in range(5):
        limit.unused(1.9, 1.7)
        short_steps_until_longer(limit)
    limit.unused(1.9, 1.7)
    for _ in range(7):
        limit.short()
    assert limit.allowed == 1.0  # still in its wait
    limit.used(40.0, integrate.AIM)
    assert limit.allowed == pytest.approx(36.0)
    limit.unused(1.9, 1.7)
    assert short_steps_until_longer(limit) == 1


def test_a_limit_is_never_over_the_longest_step_of_the_solver():
    """With a longest step of the solver of 30 intervals, a limit is 30 at the most; with a longest
    step of the check interval itself it stays there."""
    limit = integrate.Limit(1.0, 30.0)
    assert limit.allowed == 30.0
    limit.used(100.0, integrate.AIM / 16)
    assert limit.allowed == 30.0
    limit.unused(25.0, 16 * integrate.AIM)
    assert limit.allowed == pytest.approx(0.9 * 12.5)
    for _ in range(10):
        limit.short()
    assert limit.allowed == 30.0
    held = integrate.Limit(1.0, 1.0)
    for _ in range(10):
        held.short()
        assert held.allowed == 1.0


def steps_of(result):
    return len(result.t) - 1


def test_with_a_check_interval_the_steps_are_long_and_a_root_lies_where_the_closed_form_puts_it():
    """y' = -y² / 100 from 1 is 1 / (1 + t / 100): it falls to 1/100 at t = 9,900. With the solver
    held to steps of 10 the integration takes 990 steps or more. With a check interval of 10 and no
    limit on the solver, the steps are far fewer where the solution is slow. The root is where the
    closed form puts it, and the dense solution is as near to the closed form at 2,001 times as
    that of the solver that is held."""
    roots = Functions([lambda t, y: y[0] - 0.01], [-1])

    def fun(t, y):
        return np.array([-y[0] * y[0] / 100])

    def farthest(result):
        grid = np.linspace(0.0, result.t[-1], 2001)
        return float(np.max(np.abs(result.sol(grid)[0] * (1 + grid / 100) - 1)))

    held = integrate.radau(fun, (0, 200000), np.array([1.0]), roots=roots, max_step=10.0, **TIGHT)
    free = integrate.radau(fun, (0, 200000), np.array([1.0]), roots=roots, check=10.0, **TIGHT)
    assert held.status == free.status == 1
    assert steps_of(held) >= 990 and steps_of(free) < 0.75 * steps_of(held)
    for result in (held, free):
        assert result.t_events[0][0] == pytest.approx(9900.0, rel=1e-9)
        assert result.y[0, -1] == pytest.approx(0.01, rel=1e-9)
        assert farthest(result) < 1e-9
    assert farthest(free) < 2 * farthest(held)


def test_a_looser_tolerance_takes_longer_steps_between_the_check_times():
    """The same decay with a relative tolerance of 1e-6: the steps between the check times are much
    longer, and the dense solution stays within that tolerance of the closed form."""
    loose = {'rtol': 1e-6, 'atol': 1e-9}

    def fun(t, y):
        return np.array([-y[0] * y[0] / 100])

    held = integrate.radau(fun, (0, 9900), np.array([1.0]), max_step=10.0, **loose)
    free = integrate.radau(fun, (0, 9900), np.array([1.0]), check=10.0, **loose)
    assert steps_of(free) < steps_of(held) / 4
    grid = np.linspace(0.0, 9900.0, 2001)
    assert free.sol(grid)[0] == pytest.approx(1 / (1 + grid / 100), rel=1e-6)


def test_roots_between_check_times_inside_one_long_step_are_found_and_the_first_ends_it():
    """y' = 1 from 0: the solver crosses the whole interval in a few steps. Two levels lie inside one
    long step, each between two check times; the earlier one ends the integration, at its level."""
    roots = Functions([lambda t, y: y[0] - 700.5, lambda t, y: y[0] - 300.3], [0, 0])
    result = integrate.radau(lambda t, y: [1.0], (0, 1000), np.array([0.0]), roots=roots, check=1.0, **TIGHT)
    assert result.status == 1 and steps_of(result) < 30
    assert result.t_events[1].tolist() == pytest.approx([300.3], abs=1e-9)
    assert result.t_events[0].size == 0
    assert result.t[-1] == result.t_events[1][0] and result.y[0, -1] == pytest.approx(300.3, abs=1e-9)


def test_a_root_that_changes_sign_and_back_inside_one_long_step_is_found_at_a_check_time():
    """y' = 1, and a root that is below zero only from t = 300.2 to t = 303.7. The solver crosses
    that time in one long step: the root has one sign at the two ends of the step. The check times
    301, 302 and 303 are inside the window, so the root is found, at 300.2. A window that lies
    between two check times (300.2 to 300.7) is not seen, as the engine's documents say of a change
    between two samples; a shorter check interval sees it."""

    def window(low, high):
        return Functions([lambda t, y: (t - low) * (t - high)], [0])

    def run(roots, check):
        return integrate.radau(
            lambda t, y: [1.0], (0, 1000), np.array([0.0]), roots=roots, check=check, **TIGHT
        )

    seen = run(window(300.2, 303.7), 1.0)
    assert seen.status == 1 and seen.t_events[0].tolist() == pytest.approx([300.2], abs=1e-9)
    assert run(window(300.2, 300.7), 1.0).status == 0
    short = run(window(300.2, 300.7), 0.25)
    assert short.status == 1 and short.t_events[0].tolist() == pytest.approx([300.2], abs=1e-9)


@pytest.mark.parametrize(
    'center, width', [(500.25, 0.1), (500.0, 0.1), (499.75, 0.1), (123.4, 0.1), (500.5, 0.05)]
)
def test_a_short_pulse_of_the_field_inside_a_long_quiet_time_is_not_jumped_over(center, width):
    """y' is a pulse of `width` at `center`, and nothing else, for 1,000 time units: y ends at the
    area of the pulse, width × √π. A solver with no limit and no check takes a long step over the
    pulse and never reads the field inside it, so y stays 0: the hazard is real. A solver that steps
    of 1 limit finds the pulse. With a check interval of 1, the field is read at each half interval
    inside a long step: the step over the pulse is not used, and the result is the area. The last
    case is a pulse that only the half of an interval sees: it is narrow, and in the middle between
    two check times."""
    area = width * math.sqrt(math.pi)

    def fun(t, y):
        return np.array([math.exp(-(((t - center) / width) ** 2))])

    start = np.array([0.0])
    alone = integrate.radau(fun, (0, 1000), start, **TIGHT)
    held = integrate.radau(fun, (0, 1000), start, max_step=1.0, **TIGHT)
    checked = integrate.radau(fun, (0, 1000), start, check=1.0, **TIGHT)
    assert alone.y[0, -1] < 0.5 * area
    assert held.y[0, -1] == pytest.approx(area, rel=1e-7)
    assert checked.y[0, -1] == pytest.approx(area, rel=1e-7)
    # The quiet time before the pulse still goes in long steps.
    assert steps_of(checked) < steps_of(held)


def test_a_root_lies_where_the_closed_form_puts_it():
    # y' = -1 from 1 falls to 1/4 at t = 3/4.
    roots = Functions([lambda t, y: y[0] - 0.25], [-1])
    result = integrate.radau(lambda t, y: [-1.0], (0, 2), np.array([1.0]), roots=roots, rtol=1e-9, atol=1e-10)
    assert result.status == 1
    assert result.t_events[0].tolist() == pytest.approx([0.75], abs=1e-12)
    assert result.t[-1] == result.t_events[0][0]
    assert result.y[0, -1] == pytest.approx(0.25, abs=1e-12)


def test_the_first_root_in_time_ends_the_integration_within_one_step():
    # y' = 1 from 0 in one step of length 1 crosses 3/4 and 1/4: the earlier crossing ends it.
    roots = Functions([lambda t, y: y[0] - 0.75, lambda t, y: y[0] - 0.25], [0, 0])
    result = integrate.radau(
        lambda t, y: [1.0],
        (0, 2),
        np.array([0.0]),
        roots=roots,
        first_step=1,
        max_step=1,
        rtol=1e-9,
        atol=1e-10,
    )
    assert result.status == 1
    assert result.t[-1] == pytest.approx(0.25, abs=1e-12)
    assert result.t_events[0].tolist() == []
    assert result.t_events[1].tolist() == pytest.approx([0.25], abs=1e-12)


class RoundedDense(DenseOutput):
    """A step's dense solution that misses the accepted state at the end of the step by 1e-12."""

    def __init__(self, dense):
        super().__init__(dense.t_old, dense.t)
        self.dense = dense

    def _call_impl(self, t):
        values = np.array(self.dense(t), copy=True)
        if values.ndim == 1 and t == self.t:
            values[0] += 1e-12
        return values


class RoundedRadau(Radau):
    def dense_output(self):
        return RoundedDense(super().dense_output())


def test_root_location_takes_the_accepted_states_at_the_ends_of_its_bracket(monkeypatch):
    # y' = -1 from 1 in one step of length 1 crosses 1e-14 just before t = 1. At t = 1 the accepted
    # state is 0, below the level, and the rounded dense solution is 1e-12, above it.
    settings = {'first_step': 1, 'max_step': 1, 'rtol': 1e-9, 'atol': 1e-10}

    def level(t, y):
        return y[0] - 1e-14

    level.terminal, level.direction = True, -1
    # SciPy's own root location reads the dense solution at both ends, and loses the bracket.
    with pytest.raises(ValueError, match='different signs'):
        solve_ivp(
            lambda t, y: [-1.0],
            (0, 1),
            [1.0],
            method=RoundedRadau,
            dense_output=True,
            events=level,
            **settings,
        )
    monkeypatch.setattr(integrate, 'Radau', RoundedRadau)
    result = integrate.radau(
        lambda t, y: [-1.0], (0, 1), np.array([1.0]), roots=Functions([level], [-1]), **settings
    )
    assert result.status == 1
    assert result.t_events[0].tolist() == pytest.approx([1], abs=1e-12)


# ---- each root together and alone ----------------------------------------------------------------


def roots_of_each_kind(busy=False):
    """A run's system and environment, and roots of every kind on it. The stores a, b (at most 10
    people), cash and debt are one connected set: a fills at the pressure, b from a at 1 person/h
    while the program is busy, debt from cash at the rate; `busy` is an input."""
    people = b.q(1, 'person/h')
    p = b.Builder({'person': {'people': 1}, 'h': {'time': 1}})
    p.entity(
        's',
        b.input_('busy', b.BOOL, False),
        b.input_('rate', 'person/h', 2),
        b.value('a', 'person', 5, lower=0),
        b.value('b', 'person', 3, lower=0, upper=10),
        b.value('cash', 'person', 4, lower=0),
        b.value('debt', 'person', 2, lower=0),
        b.value('pressure', 'person/h', b.formula(b.this.a / b.q(1, 'h') + b.this.b / b.q(2, 'h'))),
        b.flow('feed', b.SOURCE, b.this.a, request=b.formula(b.this.pressure)),
        b.flow('pass', b.this.a, b.this.b, request=b.formula(b.ifelse(b.this.busy, people, 0 * people))),
        b.flow('pay', b.this.cash, b.this.debt, request=b.formula(b.this.rate + 0 * b.this.a / b.q(1, 'h'))),
    )
    configuration = Configuration(Request(10), inputs=(InputValue('s', 'busy', busy),))
    _, _, (way,) = Run(Plan.of(p.finish(), configuration)).prepare()
    component = way.component
    s = component.system

    def environment(at, state):
        return component.context.environment(at, state, {})

    i = s.index
    roots = [
        Root('guard', 1, (i['s.a'], read("s.b + q(1, 'person')"), 0.0)),
        Root('guard', -1, (i['s.b'], read("q(2, 'person') if s.busy else s.a / 2"), 0.5)),
        release_root(s, i['s.a'], 'min'),
        release_root(s, i['s.b'], 'max'),
        Root('bound', -1, (i['s.a'], s.lower[i['s.a']], 0.0)),
        Root('bound', 1, (i['s.b'], s.upper[i['s.b']], 0.0)),
        Root('repayment', 1, (i['s.cash'], i['s.debt'], 0.5)),
        Root('surface', 0, (read('s.rate'), read('s.pressure'))),
        Root('surface', 0, (read('s.a'), read("t * q(1, 'person/h')"))),
    ]
    return s, environment, component.state.y.copy(), roots


@pytest.mark.parametrize('busy', [False, True])
def test_each_root_has_the_same_value_together_as_alone(busy):
    s, environment, base, roots = roots_of_each_kind(busy)
    together = Roots(s, environment, roots)
    assert together.program  # the guards and the surfaces come from one generated program
    i, atol = s.index, s.atol
    rng = np.random.default_rng(7)
    for _ in range(200):
        at = float(rng.choice([0.0, 0.0, 2.5, 7.0]))
        state = base + rng.normal(0, 3, len(base))
        # Quantities within a tolerance of a bound at the start of the segment, on either side.
        state[i['s.a']] = float(rng.choice([state[i['s.a']], atol[i['s.a']] * rng.uniform(-1, 1)]))
        state[i['s.b']] = float(rng.choice([state[i['s.b']], 10 + atol[i['s.b']] * rng.uniform(-1, 1)]))
        alone = np.array([together.value(k, at, state) for k in range(len(roots))])
        assert together.values(at, state).tobytes() == alone.tobytes()


def test_a_root_that_cannot_be_evaluated_fails_as_it_fails_alone():
    s, environment, state, roots = roots_of_each_kind()
    failing = Root('guard', 1, (s.index['s.a'], read("ln(s.b - q(4, 'person')) * q(1, 'person')"), 0.0))
    together = Roots(s, environment, [*roots, failing])
    # b is 3 people at the start, so the logarithm has no value.
    with pytest.raises(ExpressionError) as alone:
        together.value(len(roots), 0.0, state)
    with pytest.raises(ExpressionError) as caught:
        together.values(0.0, state)
    assert str(caught.value) == str(alone.value)
