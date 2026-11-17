"""Morris screening and Sobol indices (napkin/dynamics/sensitivity.py).

Exact properties need no tolerance: a linear function has the same elementary effect everywhere, and
an input that a function does not read has a first-order and a total index of exactly zero. The
estimators are checked against the analytic indices of two test functions, the Ishigami function and
the Sobol G function, at fixed seeds, within six of their bootstrap standard errors."""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin.dynamics import Factor, factors_from_model, model_function, morris, sobol
from tests.build import compiled, flow, output, parameter, stock, system

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


def decay():
    """A stock that drains at k per hour: x(T) = x0 exp(-k T)."""
    return system(
        parameter('k', 0.2, 'per_h', 0.01, 1, doc='Drain rate'),
        stock('x', 10, 'people', size=10, doc='X'),
        flow('drain', 'x ->', 'k * x'),
        outputs=(output('left', 's.x', 'people', 'level', doc='People left'),),
    )


def test_a_model_function_gives_the_output_of_a_run_with_the_values():
    model = compiled(decay())
    (factor,) = factors_from_model(model, ['s.k'])
    assert (factor.low, factor.high) == (0.01, 1)
    f = model_function(model, 'a', 'left')
    for k in (0.05, 0.5):
        assert f({'s.k': k}) == pytest.approx(10 * math.exp(-k * 10), rel=1e-7)
