"""Other estimators of the expectation of an outcome (`napkin/engine/expectations.py`,
docs/engine.md, "Estimators"): the outcomes of chance events weighted, and the mean of a
distribution.

The oracles are closed forms of small models, and exact sums that each test makes again by itself:

- a clock that ticks n times, each tick a hit with the chance p that adds g to a total: the
  total is g times a binomial number, with the mean `g n p` and the variance `g^2 n p (1 - p)`;
- the same with a chance that follows the last outcome (a chain of two states), whose mean and
  variance the test adds up over every sequence of outcomes with exact fractions.
"""

from fractions import Fraction
from itertools import product

import mpmath
import numpy as np
import pytest

from napkin.engine import SamplingSettings, evaluate_uncertainty, expectations
from napkin.engine import uncertainty as study_module
from napkin.engine.uncertainty import uncertainty_report
from tests.build import (
    block,
    compiled,
    document,
    entity,
    output,
    parameter,
    stock,
    uncertain,
)

N, P, G = 6, 0.3, 2.0


def ticks(
    *members, odds='odds', hit=('next += 1 h', 'total += gain'), miss=('next += 1 h',), horizon=N, extra=()
):
    """A clock that ticks at each hour from 1 h to the horizon: with the chance `odds` (0.3) a
    tick is a hit, which adds `gain` (2 people) to the total. `members` take the place of the
    input `gain`."""
    return document(
        'Ticks',
        entity(
            'shop',
            parameter('odds', P, 'fraction', 0, 1),
            *(members or (parameter('gain', G, 'people', 0, 10),)),
            stock('next', 1, 'h', minimum=None, maximum=50, size=None, kind='state'),
            stock('streak', 0, 'fraction', minimum=None, maximum=1, size=None, kind='state'),
            stock('total', 0, 'people', size=1000),
            block(
                'event tick when t >= next:  @fixture',
                '"A tick."',
                block(f'hit {odds}:', *hit),
                block('miss else:', *miss),
            ),
            *extra,
        ),
        output('total', 'shop.total', 'people'),
        horizon=horizon,
    )


# ---- the outcomes weighted ----------------------------------------------------------------------------


def test_the_weighted_mean_of_a_binomial_total_is_exact_and_has_no_sampling_error():
    """Nothing is drawn but the outcomes: one sample, 2^6 paths, and the mean `g n p` and the
    standard deviation `g sqrt(n p (1 - p))` to roundoff. The expected number of hits is `n p`."""
    found = expectations.weighted(compiled(ticks()), 'a')
    assert found['admissible'] and (found['samples'], found['paths']) == (1, 2**N)
    total = found['outcomes']['total']
    assert total['mean'] == pytest.approx(G * N * P, rel=1e-12)
    assert total['sd'] == pytest.approx(G * (N * P * (1 - P)) ** 0.5, rel=1e-12)
    assert (total['se'], total['low'], total['high'], total['unit']) == (None, None, None, 'people')
    assert found['events']['shop.tick'] == pytest.approx({'hit': N * P, 'miss': N * (1 - P)}, rel=1e-12)


def test_a_chance_that_follows_the_last_outcome_has_the_mean_and_the_variance_of_every_sequence():
    """After a hit the chance of a hit is 0.6, after a miss 0.2 (the first tick comes after no
    hit). The test adds up every sequence of six outcomes with its exact chance."""
    source = ticks(
        odds='0.2 + 0.4 * streak',
        hit=('next += 1 h', 'total += gain', 'streak = 1'),
        miss=('next += 1 h', 'streak = 0'),
    )
    mean = square = Fraction(0)
    for sequence in product((1, 0), repeat=N):
        chance, last = Fraction(1), 0
        for hit in sequence:
            odds = Fraction(3, 5) if last else Fraction(1, 5)
            chance, last = chance * (odds if hit else 1 - odds), hit
        mean += chance * 2 * sum(sequence)
        square += chance * (2 * sum(sequence)) ** 2
    total = expectations.weighted(compiled(source), 'a')['outcomes']['total']
    assert total['mean'] == pytest.approx(float(mean), rel=1e-12)
    assert total['sd'] == pytest.approx(float(square - mean**2) ** 0.5, rel=1e-12)


def test_with_an_uncertain_value_each_sample_has_its_exact_mean_and_the_error_is_that_of_the_values():
    """The gain of a hit is uniform from 1 to 3 people. Given the gain g of a sample, the mean
    of the total over the outcomes is `g n p` exactly: the estimate is `n p` times the mean of
    the gains that the study draws, and its standard error `n p` times theirs. The Monte Carlo
    study of the same samples draws the outcomes too, so its error is larger: the variance of the
    total is `E[g^2] n p (1 - p) + var(g) (n p)^2`, of which the weighting leaves the last part."""
    model = compiled(ticks(uncertain('gain', 'people', 0, 10, 'uniform(1 people, 3 people)')))
    settings = SamplingSettings(64, 5)
    drawn = evaluate_uncertainty(model, settings=settings)
    gains = np.array([point['shop.gain'] for point in drawn.samples['a']['values']])
    found = expectations.weighted(model, 'a', settings=settings)
    total = found['outcomes']['total']
    assert (found['samples'], found['paths']) == (64, 64 * 2**N)
    assert total['mean'] == pytest.approx(N * P * gains.mean(), rel=1e-12)
    assert total['se'] == pytest.approx(N * P * gains.std(ddof=1) / 8, rel=1e-12)
    assert total['low'] < 2 * N * P < total['high']
    plain = uncertainty_report(drawn)['uncertainty']['runs']['a']['outcomes']['total']['points']['final']
    # The parts of the variance: 13/3 * 1.26 + 1/3 * 3.24 = 6.54, of which 1.08 is left.
    assert total['se'] < 0.6 * plain['sem']
    assert total['sd'] == pytest.approx(6.54**0.5, rel=0.15)


def test_a_value_that_an_event_draws_comes_from_the_stream_of_the_sample():
    """Each tick draws a number from 1 to 3 people, and a hit adds it. Given the draws of a
    sample, the mean over the outcomes is p times their sum, so the estimate has the mean
    `2 n p` and the standard error `p sqrt(n / 3) / sqrt(samples)` (the variance of one draw is
    1/3). Four ticks: 16 paths for each of 48 samples."""
    model = compiled(ticks(hit=('next += 1 h', 'total += uniform(1 people, 3 people)'), horizon=4))
    found = expectations.weighted(model, 'a', settings=SamplingSettings(48, 9))
    total = found['outcomes']['total']
    assert (found['samples'], found['paths']) == (48, 48 * 16)
    exact = P * (4 / 3) ** 0.5 / 48**0.5
    assert total['se'] == pytest.approx(exact, rel=0.35)
    assert abs(total['mean'] - 2 * 4 * P) < 4 * exact


def test_more_paths_than_the_limit_refuse_the_estimate_before_the_limit_is_passed(monkeypatch):
    runs = []
    plain = study_module.run_sample

    def counted(*args, **options):
        if options.get('outcomes') is not None:
            runs.append(options['outcomes'])
        return plain(*args, **options)

    monkeypatch.setattr(expectations, 'run_sample', counted)
    model = compiled(ticks())
    found = expectations.weighted(model, 'a', limit=20)
    assert not found['admissible']
    assert [item['code'] for item in found['diagnostics']] == ['paths']
    assert len(runs) <= 20
    assert expectations.weighted(model, 'a', limit=2**N)['admissible']


def test_a_path_whose_run_fails_refuses_the_estimate_and_names_its_outcomes():
    """A hit sets the chance of the next hit to 2, which is no chance: the run of each path with
    a hit that is not the last tick stops. The central run has no hit, and is admitted."""
    source = ticks(
        odds='0.3 + 1.7 * streak',
        hit=('next += 1 h', 'total += gain', 'streak = 1'),
        miss=('next += 1 h', 'streak = 0'),
    )
    found = expectations.weighted(compiled(source), 'a')
    assert not found['admissible']
    failed = [item for item in found['diagnostics'] if item.get('severity', 'error') == 'error']
    assert failed and all(item['run'] == 'a' and item['sample'] == 0 for item in failed)
    assert all(0 in item['outcomes'][:-1] or len(item['outcomes']) < N for item in failed)
    assert any('chance' in item['code'] for item in failed)


def test_an_outcome_that_a_path_does_not_estimate_has_no_value():
    unknown = output('unknown', None, 'people', doc='Unknown', under=('unestimated "No source gives it."',))
    source = ticks().replace('\noutput total', '\n' + unknown + '\n\noutput total')
    found = expectations.weighted(compiled(source), 'a')
    assert found['outcomes']['unknown'] == {'estimated': False, 'statuses': ['unestimated']}
    assert found['outcomes']['total']['mean'] == pytest.approx(G * N * P, rel=1e-12)


# ---- the mean of a distribution -----------------------------------------------------------------------


def mean_by_density(density, low, high):
    """The mean of a density on (low, high), at 30 digits: an integral of the density, and not of
    the quantile function as `mean_of` has it."""
    mpmath.mp.dps = 30
    mass = mpmath.quad(density, [low, high])
    return float(mpmath.quad(lambda x: x * density(x), [low, high]) / mass)


@pytest.mark.parametrize(
    ('family', 'args', 'exact'),
    [
        ('uniform', {'min': 2.0, 'max': 5.0}, 3.5),
        ('triangular', {'min': 1.0, 'mode': 2.0, 'max': 6.0}, 3.0),
        ('pert', {'min': 2.0, 'mode': 6.0, 'max': 20.0}, (2 + 4 * 6 + 20) / 6),
        ('loguniform', {'min': 1.0, 'max': 100.0}, 99 / np.log(100)),
        ('beta', {'a': 2.0, 'b': 5.0}, 2 / 7),
        ('beta', {'a': 0.5, 'b': 0.5}, 0.5),
        (
            'normal',
            {'mean': 10.0, 'sd': 2.0, 'min': 9.0, 'max': 16.0},
            mean_by_density(lambda x: mpmath.npdf(x, 10, 2), 9, 16),
        ),
        (
            'lognormal',
            {'median': 3.0, 'gsd': 2.0, 'min': 1.0, 'max': 30.0},
            mean_by_density(lambda x: mpmath.npdf(mpmath.log(x), mpmath.log(3), mpmath.log(2)) / x, 1, 30),
        ),
    ],
)
def test_the_mean_of_a_distribution_is_its_closed_form(family, args, exact):
    assert expectations.mean_of(family, args) == pytest.approx(exact, rel=1e-9)


def test_a_bool_has_no_mean_as_a_number():
    with pytest.raises(ValueError, match='gives no numbers'):
        expectations.mean_of('bernoulli', {'p': 0.5})


def test_with_sobol_sampling_the_weighted_mean_has_the_interval_of_its_blocks():
    """The gain is uniform from 1 to 3 people, drawn from 8 blocks of 4 scrambled Sobol' points.
    The mean of a sample over the outcomes is `g n p`: the estimate is the mean of the 8 block
    means of that, and its standard error is their standard deviation over the root of 8."""
    model = compiled(ticks(uncertain('gain', 'people', 0, 10, 'uniform(1 people, 3 people)')))
    settings = SamplingSettings(32, 5, 'sobol')
    gains = np.array(
        [p['shop.gain'] for p in evaluate_uncertainty(model, settings=settings).samples['a']['values']]
    )
    blocks = N * P * gains.reshape(8, 4).mean(axis=1)
    total = expectations.weighted(model, 'a', settings=settings)['outcomes']['total']
    assert total['mean'] == pytest.approx(blocks.mean(), rel=1e-12)
    assert total['se'] == pytest.approx(blocks.std(ddof=1) / 8**0.5, rel=1e-9)
    assert (total['n'], total['replicates']) == (32, 8)
    # Each block has the points of every stratum of 4: its mean is far nearer than that of 4 draws.
    assert total['se'] < 0.25 * N * P * (1 / 3) ** 0.5 / 32**0.5
