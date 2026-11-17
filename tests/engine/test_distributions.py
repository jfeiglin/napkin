"""The mathematics of the distribution families (napkin/distributions.py), with no sampling.

A distribution is fully defined by its quantile function, so these tests check each quantile against
the family's own cdf, written independently in mpmath (tests/engine/distribution_oracles.py): at
fixed probabilities, in both far tails, and at random points that Hypothesis picks with a fixed seed.
The mean and variance of a fine grid of quantiles match the closed forms, which catches a wrong
parameterization. Every test here takes milliseconds.
"""

from __future__ import annotations

import math

import mpmath as mp
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin import distributions
from tests.engine import distribution_oracles as oracle

CASES = {
    'uniform': ('uniform', {'min': 24.0, 'max': 336.0}),
    'triangular': ('triangular', {'min': 24.0, 'mode': 72.0, 'max': 336.0}),
    'triangular at its min': ('triangular', {'min': 24.0, 'mode': 24.0, 'max': 336.0}),
    'triangular at its max': ('triangular', {'min': 24.0, 'mode': 336.0, 'max': 336.0}),
    'pert': ('pert', {'min': 24.0, 'mode': 72.0, 'max': 336.0}),
    'pert at its min': ('pert', {'min': 0.0, 'mode': 0.0, 'max': 1.0}),
    'loguniform': ('loguniform', {'min': 1e-3, 'max': 1e3}),
    'normal': ('normal', {'mean': 10.0, 'sd': 2.0, 'min': 4.0, 'max': 16.0}),
    'normal, upper tail': ('normal', {'mean': 0.0, 'sd': 1.0, 'min': 8.0, 'max': 9.0}),
    'normal, lower tail': ('normal', {'mean': 0.0, 'sd': 1.0, 'min': -9.0, 'max': -8.0}),
    'normal, one wide side': ('normal', {'mean': 0.0, 'sd': 1.0, 'min': -1.0, 'max': 30.0}),
    'lognormal': ('lognormal', {'median': 48.0, 'gsd': 1.6, 'min': 6.0, 'max': 400.0}),
    'lognormal, upper tail': ('lognormal', {'median': 1.0, 'gsd': 3.0, 'min': 500.0, 'max': 1e6}),
    'beta': ('beta', {'a': 2.0, 'b': 5.0}),
    'beta, U-shaped': ('beta', {'a': 0.5, 'b': 0.5}),
}
PROBABILITIES = [1e-9, 1e-6, 0.01, 0.25, 0.5, 0.75, 0.99, 1 - 1e-6, 1 - 1e-9]


def brackets(family, args, u, x):
    """True when the true u-quantile lies within δ of x, by the independent cdf: F(x - δ) <= u <=
    F(x + δ), with the tail of u computed directly (1 - F as the survival function) so that both far
    tails keep their precision. δ is ten significant digits of x, 1e-13 of the support and four
    units in the last place of x: the precision that a double holds."""
    low, high = distributions.support(family, args)
    delta = 1e-10 * abs(x) + 1e-13 * (high - low) + 4 * np.spacing(abs(x))
    below, above = max(low, x - delta), min(high, x + delta)
    with mp.workdps(oracle.DIGITS):
        u = mp.mpf(u)
        if u <= 0.5:
            return oracle.tails(family, args, below)[0] <= u <= oracle.tails(family, args, above)[0]
        return oracle.tails(family, args, above)[1] <= 1 - u <= oracle.tails(family, args, below)[1]


@pytest.mark.parametrize('case', list(CASES))
def test_each_quantile_matches_the_family_s_own_cdf(case):
    family, args = CASES[case]
    assert distributions.problems(family, args) == []
    low, high = distributions.support(family, args)
    x = distributions.quantile(family, args, np.array(PROBABILITIES))
    assert np.all(np.diff(x) >= 0) and np.all((low <= x) & (x <= high))
    for u, value in zip(PROBABILITIES, x):
        assert brackets(family, args, u, value), (case, u, value)
    # The same, element by element: a number gives the quantile of a number.
    assert [distributions.quantile(family, args, u) for u in PROBABILITIES] == list(x)


@pytest.mark.parametrize('family', ['uniform', 'loguniform', 'triangular'])
def test_a_closed_form_quantile_holds_to_the_last_digits(family):
    for case, (name, args) in CASES.items():
        if name != family:
            continue
        for u in PROBABILITIES:
            got = distributions.quantile(family, args, u)
            want = oracle.quantile(family, args, u)
            assert abs(mp.mpf(float(got)) - want) <= 8 * 2**-52 * abs(want), (case, u)


@pytest.mark.parametrize('case', list(CASES))
def test_the_central_value_of_a_number_is_its_median(case):
    family, args = CASES[case]
    assert brackets(family, args, 0.5, distributions.central(family, args))


@pytest.mark.parametrize('case', list(CASES))
def test_the_mean_and_variance_of_a_quantile_grid_match_the_closed_forms(case):
    """A grid of 4,096 quantiles is a sample with no randomness. Its points cluster in both tails
    (u = (1 - cos πt)/2 at the midpoints t of 4,096 equal steps, each with its weight), so the
    weighted mean and variance approach the family's closed forms even for a long tail. A wrong
    parameterization, such as another PERT weight or a standard deviation read as a variance, misses
    them by far more than the tolerance."""
    family, args = CASES[case]
    t = (np.arange(4096) + 0.5) / 4096
    u, weight = (1 - np.cos(np.pi * t)) / 2, np.pi / 2 * np.sin(np.pi * t) / 4096
    x = distributions.quantile(family, args, u)
    mean, variance = (float(v) for v in oracle.moments(family, args))
    got = (weight * x).sum()
    assert abs(got - mean) < 1e-5 * math.sqrt(variance)
    assert abs((weight * (x - got) ** 2).sum() - variance) < 1e-4 * variance


def test_a_far_truncation_keeps_every_quantile_inside_its_bounds():
    """A normal truncated 8 to 9 standard deviations above its mean holds about 6e-16 of the
    probability: each quantile still comes from its own tail, inside the bounds and in order."""
    family, args = CASES['normal, upper tail']
    u = (np.arange(1000) + 0.5) / 1000
    x = distributions.quantile(family, args, u)
    assert np.all(np.diff(x) > 0) and x[0] > 8 and x[-1] < 9
    assert all(brackets(family, args, u[k], x[k]) for k in (0, 499, 999))


def test_a_bernoulli_is_true_above_one_minus_p():
    p = 0.3
    u = np.array([1e-9, 0.5, 0.7, np.nextafter(0.7, 1), 1 - 1e-9])
    assert distributions.quantile('bernoulli', {'p': p}, u).tolist() == [False, False, False, True, True]
    assert distributions.quantile('bernoulli', {'p': 0}, u).tolist() == [False] * 5
    assert distributions.quantile('bernoulli', {'p': 1}, u).tolist() == [True] * 5
    # The central value is the more likely one; at p = 1/2 it is false.
    assert [distributions.central('bernoulli', {'p': p}) for p in (0.3, 0.5, 0.7)] == [False, False, True]


def test_a_categorical_picks_the_value_whose_share_holds_u():
    args = {'a': 0.5, 'b': 0.0, 'c': 0.25, 'd': 0.25}
    u = np.array([1e-9, 0.5, np.nextafter(0.5, 1), 0.75, np.nextafter(0.75, 1), 1 - 1e-9])
    # Each value holds its share of (0, 1) in the order listed; a value of probability 0 holds none.
    assert distributions.quantile('categorical', args, u).tolist() == [0, 0, 2, 2, 3, 3]
    # The central value is the most likely one; on a tie, the first that is listed.
    assert distributions.central('categorical', args) == 0
    assert distributions.central('categorical', {'a': 0.25, 'b': 0.375, 'c': 0.375}) == 1


@pytest.mark.parametrize(
    ('family', 'args'),
    [
        ('uniform', {'min': 2.0, 'max': 2.0}),
        ('uniform', {'min': 3.0, 'max': 2.0}),
        ('triangular', {'min': 1.0, 'mode': 4.0, 'max': 3.0}),
        ('pert', {'min': 1.0, 'mode': 0.5, 'max': 3.0}),
        ('loguniform', {'min': 0.0, 'max': 3.0}),
        ('normal', {'mean': 0.0, 'sd': 0.0, 'min': -1.0, 'max': 1.0}),
        ('normal', {'mean': 0.0, 'sd': 1.0, 'min': 1.0, 'max': -1.0}),
        # So far in the tail that a double holds none of its probability.
        ('normal', {'mean': 0.0, 'sd': 1.0, 'min': 40.0, 'max': 41.0}),
        ('lognormal', {'median': 1.0, 'gsd': 1.0, 'min': 0.5, 'max': 2.0}),
        ('lognormal', {'median': 1.0, 'gsd': 2.0, 'min': 0.0, 'max': 2.0}),
        ('beta', {'a': 0.0, 'b': 1.0}),
        ('bernoulli', {'p': 1.5}),
        ('categorical', {'a': 0.5, 'b': 0.4}),
        ('categorical', {'a': 1.5, 'b': -0.5}),
        ('uniform', {'min': 0.0, 'max': math.inf}),
    ],
)
def test_invalid_arguments_have_a_problem(family, args):
    assert distributions.problems(family, args)


@settings(derandomize=True, max_examples=100, deadline=None, database=None)
@given(
    case=st.sampled_from(sorted(CASES)),
    u=st.floats(min_value=2**-53, max_value=1 - 2**-53, allow_nan=False),
    v=st.floats(min_value=2**-53, max_value=1 - 2**-53, allow_nan=False),
)
def test_quantiles_rise_with_u_stay_inside_the_support_and_invert_the_cdf(case, u, v):
    family, args = CASES[case]
    low, high = distributions.support(family, args)
    x, y = distributions.quantile(family, args, np.array([min(u, v), max(u, v)]))
    assert low <= x <= y <= high
    assert brackets(family, args, u, float(distributions.quantile(family, args, u)))
