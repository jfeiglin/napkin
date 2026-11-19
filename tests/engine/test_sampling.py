"""The samples of a Monte Carlo study (`napkin/engine/sampling.py`): the settings, the seed of each sample,
the configuration of each, and the named streams of an analysis that draws its own numbers.

The structural properties are exact. Randomness itself is tested only where it must be: the draws that
the samples of a study make, with thresholds from the DKW and Hoeffding bounds at a false-failure
probability of 1e-9 (tests/engine/distribution_oracles.py). The seeds are fixed, so the result never
varies.
"""

from __future__ import annotations

import hashlib
import math
import textwrap

import numpy as np
import pytest

from napkin.engine.sampling import LIMIT, SamplingSettings, sample_seed, sampled, stream
from napkin.engine.uncertainty import monte_carlo
from napkin.model.compile import compile_text
from napkin.program.config import MEDIAN, SAMPLED, Configuration, Request
from tests.engine import distribution_oracles as oracle
from tests.program.examples import UNITS


def test_the_seed_of_a_sample_is_its_digest_and_does_not_depend_on_their_number():
    digest = hashlib.sha256(b'11|3').digest()
    assert sample_seed(11, 3) == int.from_bytes(digest[:8], 'big') // 2 and 0 <= sample_seed(11, 3) < 2**63
    few = sampled(Configuration(Request(1)), SamplingSettings(4, seed=11))
    many = sampled(Configuration(Request(1)), SamplingSettings(100, seed=11))
    assert few == many[:4] and all(item.mode == SAMPLED for item in many)
    assert [item.seed for item in many] == [sample_seed(11, k) for k in range(100)]


def test_two_studies_with_other_seeds_share_no_sample():
    first = {sample_seed(5, k) for k in range(1000)}
    second = {sample_seed(6, k) for k in range(1000)}
    assert len(first) == len(second) == 1000 and not first & second


def test_a_sample_is_its_study_s_configuration_in_sampled_mode():
    given = Configuration(Request(6), mode=MEDIAN)
    (one,) = sampled(given, SamplingSettings(1, seed=2))
    assert one == Configuration(Request(6), mode=SAMPLED, seed=sample_seed(2, 0))


@pytest.mark.parametrize(
    'arguments',
    [
        {'samples': 0},
        {'samples': 1.5},
        {'samples': True},
        {'samples': LIMIT + 1},
        {'seed': -1},
        {'seed': 2**63},
        {'seed': 1.0},
    ],
)
def test_the_settings_say_what_they_take(arguments):
    with pytest.raises(ValueError):
        SamplingSettings(**arguments)


def test_the_settings_are_plain_data():
    assert SamplingSettings(48, seed=3).record() == {'samples': 48, 'seed': 3}
    assert SamplingSettings(**SamplingSettings(48, seed=3).record()) == SamplingSettings(48, 3)


def test_a_stream_is_named_and_never_depends_on_another():
    first = stream(4, 'a.x').random(8)
    assert np.array_equal(first, stream(4, 'a.x').random(8))
    assert not np.array_equal(first, stream(4, 'b.y').random(8))
    assert not np.array_equal(first, stream(5, 'a.x').random(8))


PICKS = textwrap.dedent("""\
    scenario "Picks"
        horizon 1 h
    tank:
        input rate: L/h = uniform(1 L/h, 3 L/h).draw()
        input level = categorical(LOW: 0.1, MIDDLE: 0.6, HIGH: 0.3).draw()
        water: L = 0 L in [0 L,]
        flow fill: SOURCE -> this.water
            request = formula(this.rate if this.level == LOW else 2 L/h)
    """)


def test_the_draws_of_the_samples_follow_their_distributions():
    """The rate of 2,000 samples is uniform from 1 to 3 L/h: its empirical cdf stays within the DKW
    bound of the line. The share of each level is within Hoeffding's bound of its probability, each of
    the three at 1e-9 / 3."""
    model = compile_text(PICKS, UNITS)
    n = 2000
    found = monte_carlo(model.program, model.configuration, ['tank.water'], [1], SamplingSettings(n, 1))
    values = {site: [] for site in ('tank.rate.draw[0]', 'tank.level.draw[0]')}
    for sample in found.samples:
        for site, _, value in sample.draws:
            values[site].append(value)
    u = np.sort((np.array(values['tank.rate.draw[0]']) - 1) / 2)
    ranks = np.arange(1, n + 1) / n
    assert max(np.max(ranks - u), np.max(u - (ranks - 1 / n))) < oracle.dkw_epsilon(n)
    for level, p in (('LOW', 0.1), ('MIDDLE', 0.6), ('HIGH', 0.3)):
        share = values['tank.level.draw[0]'].count(level) / n
        assert abs(share - p) < oracle.hoeffding_epsilon(n, 1e-9 / 3)


def test_the_bounds_of_the_statistical_tests_are_the_published_ones():
    """2 exp(-2 n eps^2) is the failure probability that each bound leaves."""
    for bound in (oracle.dkw_epsilon, oracle.hoeffding_epsilon):
        eps = bound(20_000)
        assert 2 * math.exp(-2 * 20_000 * eps**2) == pytest.approx(1e-9)
