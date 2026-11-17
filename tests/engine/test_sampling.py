"""The uniform numbers of a Monte Carlo study (napkin/engine/sampling.py), with no engine run.

The structural properties are exact. Randomness itself is tested only where it must be, with
vectorized draws and thresholds from the DKW and Hoeffding bounds at a false-failure probability of
1e-9 (tests/engine/distribution_oracles.py). The seeds are fixed, so the result never varies.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin import distributions
from napkin.engine.sampling import RESOLUTION, SamplingSettings, _open, uniforms
from tests.engine import distribution_oracles as oracle


def test_sample_k_does_not_depend_on_the_number_of_samples():
    few = uniforms(['a.x'], SamplingSettings(4, seed=11))['a.x']
    many = uniforms(['a.x'], SamplingSettings(100, seed=11))['a.x']
    assert np.array_equal(few, many[:4])


def test_each_value_has_a_stream_of_its_own():
    """Adding or removing an uncertain value never changes the numbers of another, and two values
    never share their numbers."""
    alone = uniforms(['a.x'], SamplingSettings(50, seed=3))
    together = uniforms(['b.y', 'a.x', 'c.z'], SamplingSettings(50, seed=3))
    assert np.array_equal(alone['a.x'], together['a.x'])
    assert not np.array_equal(together['a.x'], together['b.y'])


def test_a_seed_gives_the_same_numbers_and_another_seed_others():
    first, again = (uniforms(['a.x'], SamplingSettings(20, seed=5))['a.x'] for _ in range(2))
    other = uniforms(['a.x'], SamplingSettings(20, seed=6))['a.x']
    assert np.array_equal(first, again) and not np.array_equal(first, other)


class Extremes:
    """A generator that gives the lowest and the highest whole numbers that a uniform number reads."""

    def integers(self, low, high, size, dtype):
        return np.array([low, high - 1] * (size // 2), dtype=dtype)


def test_a_uniform_number_is_never_0_or_1():
    low, high = _open(Extremes(), 2)
    assert (low, high) == (2**-53, 1 - 2**-53) and low > 0 and high < 1
    for method in ('random', 'latin'):
        u = uniforms(['a.x'], SamplingSettings(1000, seed=1, method=method))['a.x']
        assert np.all((u > 0) & (u < 1))
    assert RESOLUTION == 2**52


@pytest.mark.parametrize('n', [1, 7, 64, 1000])
def test_latin_puts_one_sample_in_each_stratum(n):
    u = uniforms(['a.x', 'b.y'], SamplingSettings(n, seed=9, method='latin'))
    for numbers in u.values():
        assert sorted(np.floor(numbers * n).astype(int).tolist()) == list(range(n))


def test_random_numbers_follow_the_uniform_law():
    """The empirical cdf of 20,000 numbers stays within the DKW bound of the identity."""
    n = 20_000
    u = np.sort(uniforms(['a.x'], SamplingSettings(n, seed=2))['a.x'])
    ranks = np.arange(1, n + 1) / n
    distance = max(np.max(ranks - u), np.max(u - (ranks - 1 / n)))
    assert distance < oracle.dkw_epsilon(n)


def test_bernoulli_and_categorical_draws_keep_their_probabilities():
    """The share of true draws is within Hoeffding's bound of p, and so is the share of each named
    value of a categorical: the bound of each of the k shares holds at 1e-9 / k."""
    n = 20_000
    u = uniforms(['a.flag', 'a.curve'], SamplingSettings(n, seed=4))
    p = 0.3
    share = distributions.quantile('bernoulli', {'p': p}, u['a.flag']).mean()
    assert abs(share - p) < oracle.hoeffding_epsilon(n)
    probabilities = {'low': 0.1, 'middle': 0.6, 'high': 0.3}
    picked = distributions.quantile('categorical', probabilities, u['a.curve'])
    for code, q in enumerate(probabilities.values()):
        assert abs((picked == code).mean() - q) < oracle.hoeffding_epsilon(n, 1e-9 / len(probabilities))


@pytest.mark.parametrize(
    'arguments',
    [
        {'samples': 0},
        {'samples': 1.5},
        {'samples': True},
        {'samples': 100_001},
        {'seed': -1},
        {'seed': 2**63},
        {'method': 'halton'},
        # Sobol' sampling: blocks of a power of two each, two blocks or more.
        {'method': 'sobol'},
        {'method': 'sobol', 'samples': 8 * 24},
        {'method': 'sobol', 'samples': 64, 'replicates': 1},
        {'method': 'sobol', 'samples': 64, 'replicates': 3},
        {'method': 'sobol', 'samples': 64, 'replicates': 2.0},
        {'method': 'random', 'replicates': 8},
    ],
)
def test_the_settings_say_what_they_take(arguments):
    with pytest.raises(ValueError):
        SamplingSettings(**arguments)


# ---- scrambled Sobol' points ------------------------------------------------------------------------

PLACES = {'a.x': 0, 'b.y': 1, 'c.z': 2, 'd.w': 3}


def test_sobol_settings_are_blocks_of_a_power_of_two_and_say_their_blocks():
    assert SamplingSettings(512, method='sobol').record() == {
        'samples': 512,
        'seed': 0,
        'method': 'sobol',
        'replicates': 8,
    }
    assert SamplingSettings(48, seed=2, method='sobol', replicates=3).replicates == 3
    # The settings of the other methods say nothing of blocks, as before.
    assert SamplingSettings(48).record() == {'samples': 48, 'seed': 0, 'method': 'random'}
    assert SamplingSettings(**SamplingSettings(512, method='sobol').record()).replicates == 8


def test_each_block_of_sobol_points_has_one_number_in_each_stratum_of_each_value():
    """A block of 2^k scrambled Sobol' points is a net in base 2: each value has exactly one of its
    64 numbers in each of 64 equal strata, and the first two values together have exactly one point
    in each square of the 8 by 8 grid of their plane. Random numbers have neither."""
    settings = SamplingSettings(8 * 64, seed=3, method='sobol')
    numbers = uniforms(list(PLACES), settings, PLACES)
    for name in PLACES:
        assert numbers[name].shape == (512,) and numbers[name].min() > 0 and numbers[name].max() < 1
        for block in np.split(numbers[name], 8):
            assert sorted(np.floor(block * 64).astype(int)) == list(range(64))
    for first, second in zip(np.split(numbers['a.x'], 8), np.split(numbers['b.y'], 8)):
        squares = sorted(zip(np.floor(first * 8).astype(int), np.floor(second * 8).astype(int)))
        assert squares == [(i, j) for i in range(8) for j in range(8)]
    random = uniforms(['a.x'], SamplingSettings(64, seed=3))['a.x']
    assert sorted(np.floor(random * 64).astype(int)) != list(range(64))


def test_the_sobol_numbers_of_a_value_follow_its_place_and_not_the_other_values():
    """A value has one dimension of the points, its place among the inputs of the model. Its
    numbers are the same when other values are drawn with it or not; at another place, or with
    another seed, they are other numbers; and each block has a scramble of its own."""
    settings = SamplingSettings(4 * 32, seed=5, method='sobol', replicates=4)
    alone = uniforms(['b.y'], settings, PLACES)['b.y']
    together = uniforms(['d.w', 'b.y', 'a.x'], settings, PLACES)
    assert np.array_equal(alone, together['b.y'])
    assert np.array_equal(alone, uniforms(['b.y'], settings, PLACES)['b.y'])
    moved = uniforms(['b.y'], settings, {**PLACES, 'b.y': 2, 'c.z': 1})['b.y']
    assert not np.array_equal(alone, moved)
    assert np.array_equal(moved, uniforms(['c.z'], settings, PLACES)['c.z'])
    other = uniforms(['b.y'], SamplingSettings(4 * 32, seed=6, method='sobol', replicates=4), PLACES)['b.y']
    assert not np.array_equal(alone, other)
    blocks = np.split(alone, 4)
    assert all(not np.array_equal(blocks[0], block) for block in blocks[1:])
    assert uniforms([], settings, PLACES) == {}


def test_the_mean_of_a_smooth_function_of_sobol_points_has_no_bias_and_a_far_smaller_error():
    """The product of `1 + (u - 1/2)` over three values has the mean 1 and the variance
    `(1 + 1/12)^3 - 1`. With 16 blocks of 256 Sobol' points, the mean of the blocks is within four
    of its standard errors of 1, and that standard error (from how the means of the blocks differ)
    is less than a twentieth of the standard error of as many random numbers, which is
    `sqrt(variance / n)`."""
    from napkin.engine.estimators import replicate_interval

    settings = SamplingSettings(16 * 256, seed=1, method='sobol', replicates=16)
    numbers = uniforms(['a.x', 'b.y', 'c.z'], settings, PLACES)
    values = np.prod([1 + (numbers[name] - 0.5) for name in ('a.x', 'b.y', 'c.z')], axis=0)
    found = replicate_interval(np.split(values, 16))
    random_error = math.sqrt(((1 + 1 / 12) ** 3 - 1) / len(values))
    assert abs(found['mean'] - 1.0) <= 4 * found['se']
    assert 0 < found['se'] < random_error / 20


def test_the_bounds_of_the_statistical_tests_are_the_published_ones():
    """2 exp(-2 n eps^2) is the failure probability that each bound leaves."""
    for bound in (oracle.dkw_epsilon, oracle.hoeffding_epsilon):
        eps = bound(20_000)
        assert 2 * math.exp(-2 * 20_000 * eps**2) == pytest.approx(1e-9)
