"""Morris screening and Sobol indices (napkin/dynamics/sensitivity.py).

Exact properties need no tolerance: a linear function has the same elementary effect everywhere, and
an input that a function does not read has a first-order and a total index of exactly zero. The
estimators are checked against the analytic indices of two test functions, the Ishigami function and
the Sobol G function, at fixed seeds, within six of their bootstrap standard errors. A run function
reads a value of a real run, which a drain's closed form gives."""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin.dynamics import Factor, input_factors, morris, run_function, sobol
from tests.dynamics.models import drain, fold

PI = math.pi
ISHIGAMI = [Factor(f'x{i}', -PI, PI) for i in (1, 2, 3)]


def ishigami(values, a=7.0, b=0.1):
    x1, x2, x3 = values['x1'], values['x2'], values['x3']
    return math.sin(x1) + a * math.sin(x2) ** 2 + b * x3**4 * math.sin(x1)


def ishigami_indices(a=7.0, b=0.1):
    """The analytic first-order and total indices of the Ishigami function."""
    v1 = 0.5 * (1 + b * PI**4 / 5) ** 2
    v2 = a**2 / 8
    v13 = b**2 * PI**8 * (1 / 18 - 1 / 50)
    variance = v1 + v2 + v13
    return [v1 / variance, v2 / variance, 0.0], [(v1 + v13) / variance, v2 / variance, v13 / variance]


def test_morris_gives_a_linear_function_one_effect_for_each_input():
    factors = [Factor('a', 0, 2), Factor('b', -1, 3), Factor('c', 10, 11)]
    weights = {'a': 3.0, 'b': -0.5, 'c': 0.0}
    result = morris(
        lambda v: sum(weights[k] * v[k] for k in weights), factors, trajectories=12, levels=4, seed=5
    )
    for i, factor in enumerate(factors):
        effect = weights[factor.name] * (factor.high - factor.low)
        assert result.mu[i] == pytest.approx(effect, abs=1e-12)
        assert result.mu_star[i] == pytest.approx(abs(effect), abs=1e-12)
        assert result.sigma[i] == pytest.approx(0.0, abs=1e-12)
    assert result.ranking()[:2] == ['a', 'b']
    assert result.evaluations == 12 * (len(factors) + 1)


def test_an_input_that_the_function_does_not_read_has_indices_of_zero():
    factors = [*ISHIGAMI, Factor('unused', 0, 1)]
    result = sobol(ishigami, factors, samples=256, seed=2, bootstrap=50)
    assert result.first[3] == 0.0
    assert result.total[3] == 0.0


def test_an_extra_input_changes_no_index_of_the_others():
    small = sobol(ishigami, ISHIGAMI, samples=256, seed=4, bootstrap=20)
    large = sobol(ishigami, [*ISHIGAMI, Factor('unused', 0, 1)], samples=256, seed=4, bootstrap=20)
    assert np.array_equal(small.first, large.first[:3])
    assert np.array_equal(small.total, large.total[:3])


def test_one_seed_gives_one_result():
    once = sobol(ishigami, ISHIGAMI, samples=128, seed=9, bootstrap=20)
    again = sobol(ishigami, ISHIGAMI, samples=128, seed=9, bootstrap=20)
    other = sobol(ishigami, ISHIGAMI, samples=128, seed=10, bootstrap=20)
    assert np.array_equal(once.first, again.first) and np.array_equal(
        once.total_interval, again.total_interval
    )
    assert not np.array_equal(once.first, other.first)


def test_a_constant_function_has_no_indices():
    result = sobol(lambda v: 1.0, ISHIGAMI, samples=32, seed=0, bootstrap=10)
    assert result.status == 'constant' and result.first is None


def test_the_ishigami_indices_match_their_closed_form():
    first, total = ishigami_indices()
    result = sobol(ishigami, ISHIGAMI, samples=2**13, seed=11, bootstrap=200)
    for i in range(3):
        assert abs(result.first[i] - first[i]) <= 6 * result.first_error[i] + 1e-12
        assert abs(result.total[i] - total[i]) <= 6 * result.total_error[i] + 1e-12


def test_the_sobol_g_indices_match_their_closed_form():
    a = [0.0, 1.0, 4.5, 9.0, 99.0]
    factors = [Factor(f'g{i}', 0.0, 1.0) for i in range(len(a))]

    def g(values):
        return math.prod((abs(4 * values[f'g{i}'] - 2) + a[i]) / (1 + a[i]) for i in range(len(a)))

    partial = [1 / (3 * (1 + ai) ** 2) for ai in a]
    variance = math.prod(1 + v for v in partial) - 1
    first = [v / variance for v in partial]
    total = [
        v * math.prod(1 + w for j, w in enumerate(partial) if j != i) / variance
        for i, v in enumerate(partial)
    ]
    result = sobol(g, factors, samples=2**12, seed=13, bootstrap=200)
    for i in range(len(a)):
        assert abs(result.first[i] - first[i]) <= 6 * result.first_error[i] + 1e-12
        assert abs(result.total[i] - total[i]) <= 6 * result.total_error[i] + 1e-12


def test_a_run_function_gives_a_value_of_a_run_with_the_input_values():
    # A tank that drains at k x from 10 people holds 10 exp(-k T) at the horizon T = 10 h, and
    # 10 exp(-k 4) at 4 h. The admitted range of k is its factor.
    program, configuration = drain(0.2, start=10.0, horizon=10)
    (factor,) = input_factors(program, configuration, ['tank.k'])
    assert (factor.name, factor.low, factor.high) == ('tank.k', 0.0, 1.0)
    f = run_function(program, configuration, 'tank.x')
    at_four = run_function(program, configuration, 'tank.x', time=4)
    for k in (0.05, 0.5):
        assert f({'tank.k': k}) == pytest.approx(10 * math.exp(-k * 10), rel=1e-7)
        assert at_four({'tank.k': k}) == pytest.approx(10 * math.exp(-k * 4), rel=1e-7)


def test_a_factor_needs_a_number_input_with_a_range():
    program, configuration = fold()
    with pytest.raises(ValueError):
        input_factors(program, configuration, ['tank.x'])  # a stored value
    with pytest.raises(KeyError):
        input_factors(program, configuration, ['tank.nothing'])
