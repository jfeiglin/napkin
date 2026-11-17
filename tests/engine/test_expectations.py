"""Other estimators of the expectation of an outcome (`napkin/engine/expectations.py`,
docs/engine.md, "Estimators"): the outcomes of chance events weighted, a control from the linear
form at the central run, and the derivative of an expectation with its label.

The oracles are closed forms of small models, and exact sums that each test makes again by itself:

- a clock that ticks n times, each tick a hit with the chance p that adds g to a total: the
  total is g times a binomial number, with the mean `g n p` and the variance `g^2 n p (1 - p)`;
- the same with a chance that follows the last outcome (a chain of two states), whose mean and
  variance the test adds up over every sequence of outcomes with exact fractions;
- a tally at an uncertain rate until an uncertain time, `rate * end`, whose mean is the product
  of the two means;
- the threshold example: a uniform number U and the outcome `1 if U < x else 0`, whose mean is x.
"""

from fractions import Fraction
from itertools import product

import mpmath
import numpy as np
import pytest
from scipy import special

from napkin.engine import SamplingSettings, evaluate_uncertainty, expectations
from napkin.engine import uncertainty as study_module
from napkin.engine.uncertainty import uncertainty_report
from tests.build import (
    block,
    compiled,
    document,
    entity,
    flow,
    formula,
    move,
    once_at,
    output,
    parameter,
    stock,
    system,
    template,
    timer,
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


# ---- the control --------------------------------------------------------------------------------------


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


def tally(rate, *members, at='rate'):
    """A tally that rises at `at` for 24 hours: served = 24 * at."""
    return system(
        uncertain('rate', 'people/h', 0.5, 4, rate),
        *members,
        stock('served', 0, kind='tally', size=100, rate=at),
        horizon=24,
        outputs=(output('served', 's.served', 'people'),),
    )


def test_an_outcome_that_is_linear_in_its_inputs_has_its_exact_mean_and_no_error():
    """served = 24 * rate, with a triangular rate from 1 to 4 and the mode 2: the mean is
    24 * 7/3 = 56. The control is the outcome but for a constant, so each sample gives 56. The
    plain mean of the same samples has the error of 32 draws."""
    model = compiled(tally('triangular(1 people/h, 2 people/h, 4 people/h)'))
    found = expectations.controlled(evaluate_uncertainty(model, settings=SamplingSettings(32, 4)), 'a')
    served = found['outcomes']['served']
    assert served['coefficients'] == pytest.approx({'s.rate': 24.0}, rel=1e-9)
    assert served['mean'] == pytest.approx(56.0, rel=1e-9)
    assert served['se'] < 1e-9 < 0.5 < served['plain']['se']
    assert (found['samples'], found['left_out']) == (32, {})


def test_the_control_of_a_product_has_no_bias_and_a_smaller_error_than_the_plain_mean():
    """served = rate * end, the rate uniform from 1 to 3 and the end a PERT (2, 6, 20) h: the mean
    is 2 * 46/6. The estimate is the mean of `y - g (x - E[x])`, which the test makes again from
    the draws, the outcomes and the two derivatives at the central run (the median end, and the
    median rate 2). It is within four of its standard errors of the true mean, and its error is
    less than a third of that of the plain mean."""
    model = compiled(timer())
    result = evaluate_uncertainty(model, settings=SamplingSettings(128, 3))
    found = expectations.controlled(result, 'a')
    served = found['outcomes']['served']
    points = result.samples['a']['values']
    rate, end = (np.array([point[name] for point in points]) for name in ('s.rate', 's.end'))
    median = float(special.betaincinv(1 + 4 * 4 / 18, 1 + 4 * 14 / 18, 0.5)) * 18 + 2
    assert served['coefficients'] == pytest.approx({'s.rate': median, 's.end': 2.0}, rel=1e-6)
    each = rate * end - median * (rate - 2.0) - 2.0 * (end - 46 / 6)
    assert served['mean'] == pytest.approx(each.mean(), rel=1e-6)
    assert served['se'] == pytest.approx(each.std(ddof=1) / 128**0.5, rel=1e-6)
    assert served['plain']['mean'] == pytest.approx((rate * end).mean(), rel=1e-9)
    assert abs(served['mean'] - 2 * 46 / 6) < 4 * served['se']
    assert served['se'] < served['plain']['se'] / 3


def test_given_coefficients_take_the_place_of_the_derivatives_and_keep_the_estimate_without_bias():
    """Any numbers that do not come from the samples make a control with no bias: here 5 and -1,
    which are far from the derivatives. The estimate is the mean of `y - 5 (rate - 2) + (end -
    46/6)` over the draws, and the true mean is within four of its standard errors."""
    result = evaluate_uncertainty(compiled(timer()), settings=SamplingSettings(128, 3))
    given = {'served': {'s.rate': 5.0, 's.end': -1.0}}
    served = expectations.controlled(result, 'a', coefficients=given)['outcomes']['served']
    points = result.samples['a']['values']
    rate, end = (np.array([point[name] for point in points]) for name in ('s.rate', 's.end'))
    each = rate * end - 5.0 * (rate - 2.0) + (end - 46 / 6)
    assert served['coefficients'] == given['served']
    assert served['mean'] == pytest.approx(each.mean(), rel=1e-9)
    assert abs(served['mean'] - 2 * 46 / 6) < 4 * served['se']


def test_an_input_that_is_no_number_or_whose_distribution_reads_another_has_no_part_in_the_control():
    """The rate of the tally is `rate + more` when `open` is true. `more` is uniform from 0 to
    the rate: its mean is not that of one distribution. The control has the rate alone, with the
    derivative 24 at the central run (`open` is more likely true, so it is true there)."""
    source = tally(
        'uniform(1 people/h, 3 people/h)',
        uncertain('more', 'people/h', 0, 4, 'uniform(0 people/h, rate)'),
        uncertain('open', 'bool', None, None, 'bernoulli(0.8)'),
        at='rate + (more if open else 0 people/h)',
    )
    result = evaluate_uncertainty(compiled(source), settings=SamplingSettings(64, 2))
    found = expectations.controlled(result, 'a')
    assert found['left_out'] == {
        's.more': 'its distribution reads other values',
        's.open': 'its values are no numbers',
    }
    served = found['outcomes']['served']
    assert served['coefficients'] == pytest.approx({'s.rate': 24.0}, rel=1e-9)
    points = result.samples['a']['values']
    rate, more, opened = (
        np.array([point[name] for point in points]) for name in ('s.rate', 's.more', 's.open')
    )
    each = 24 * (rate + np.where(opened, more, 0.0)) - 24 * (rate - 2.0)
    assert served['mean'] == pytest.approx(each.mean(), rel=1e-9)
    # The true mean: 24 * (2 + 0.8 * 1).
    assert abs(served['mean'] - 24 * 2.8) < 4 * served['se']


def test_with_sobol_sampling_the_interval_of_a_control_is_that_of_its_blocks():
    """Eight blocks of 16 points: the estimate is the mean of the eight means of `y - (c - E[c])`,
    and its standard error is their standard deviation over the root of 8."""
    result = evaluate_uncertainty(compiled(timer()), settings=SamplingSettings(128, 3, 'sobol'))
    served = expectations.controlled(result, 'a')['outcomes']['served']
    points = result.samples['a']['values']
    rate, end = (np.array([point[name] for point in points]) for name in ('s.rate', 's.end'))
    slope = served['coefficients']
    each = rate * end - slope['s.rate'] * (rate - 2.0) - slope['s.end'] * (end - 46 / 6)
    blocks = each.reshape(8, 16).mean(axis=1)
    assert (served['n'], served['replicates']) == (128, 8)
    assert served['mean'] == pytest.approx(blocks.mean(), rel=1e-9)
    assert served['se'] == pytest.approx(blocks.std(ddof=1) / 8**0.5, rel=1e-9)
    assert abs(served['mean'] - 2 * 46 / 6) < 4 * served['se']


def test_a_rejected_study_has_no_control():
    source = system(
        uncertain('amount', 'people', 0, 20, 'uniform(5 people, 15 people)'),
        stock('source', 10),
        stock('out'),
        once_at('takes', '1 h', 'move amount from source to out'),
        horizon=3,
    )
    # A sample that moves more than the stock holds stops its run: the study keeps no sample.
    result = evaluate_uncertainty(compiled(source), settings=SamplingSettings(8, 6))
    assert not result.admissible
    with pytest.raises(ValueError, match='rejected'):
        expectations.controlled(result, 'a')


# ---- the derivative of an expectation -------------------------------------------------------------------


def one(found, output, name):
    return found['derivatives'][output][name]


def threshold(outcome='1 if gate.u < gate.x else 0', u='uniform(0, 1)'):
    return document(
        'Threshold',
        entity('gate', uncertain('u', 'fraction', 0, 1, u), parameter('x', 0.3, 'fraction', 0, 1)),
        output('hit', outcome, 'fraction'),
        horizon=6,
    )


def test_the_threshold_example_has_no_sample_mean():
    """U is uniform from 0 to 1 and the outcome is 1 where U < x: its mean is x, so the
    derivative of the mean by x is 1. Each sample has the derivative 0 (no sample has U = x). The
    pair is unsupported, with the comparison as the reason, and has no value: above all not 0."""
    found = expectations.derivatives(compiled(threshold()), 'a', ['gate.x'], settings=SamplingSettings(32, 1))
    pair = one(found, 'hit', 'gate.x')
    assert pair['label'] == 'unsupported'
    assert pair['why'] == ['a comparison that the input can change, in hit']
    assert (pair['value'], pair['se'], pair['low'], pair['high']) == (None, None, None, None)


def test_the_same_chance_as_an_outcome_of_an_event_has_the_derivative_of_its_weight():
    """An event sets the outcome to 1 with the chance x: the mean is x again. Here the two paths
    are run with their weights x and 1 - x, whose derivatives are 1 and -1: the derivative of the
    mean is 1 * 1 + (-1) * 0 = 1, with no sampling error."""
    source = document(
        'Chance',
        entity(
            'gate',
            parameter('x', 0.3, 'fraction', 0, 1),
            stock('hit', 0, 'fraction', size=1),
            block(
                'event attempt once when t >= 1 h:  @fixture',
                '"One trial."',
                block('yes x:', 'hit = 1'),
                'no else:',
            ),
        ),
        output('hit', 'gate.hit', 'fraction'),
        horizon=6,
    )
    found = expectations.derivatives(compiled(source), 'a', ['gate.x'])
    pair = one(found, 'hit', 'gate.x')
    assert (pair['label'], pair['value'], pair['se']) == ('branch weighting', 1.0, None)
    assert found['outcomes']['hit']['mean'] == pytest.approx(0.3, rel=1e-12)
    assert (found['samples'], found['paths']) == (1, 2)


def test_the_two_labels_of_a_binomial_total_and_their_exact_derivatives():
    """The mean of the total is `g n p`. By the gain g a path is continuous (a hit adds g) and
    no chance reads it: the sample mean, `n p`. By the odds p the weights of the paths change:
    branch weighting, `g n`. The time of the horizon does not reach the total through an input
    that the test names, and an input that reaches nothing is zero by the structure."""
    source = ticks(parameter('gain', G, 'people', 0, 10), parameter('spare', 1, 'people', 0, 10))
    found = expectations.derivatives(compiled(source), 'a')
    assert found['inputs'] == ['shop.odds', 'shop.gain', 'shop.spare']
    gain, odds, spare = (one(found, 'total', name) for name in ('shop.gain', 'shop.odds', 'shop.spare'))
    assert (gain['label'], odds['label'], spare['label']) == (
        'sample mean',
        'branch weighting',
        'zero by the structure',
    )
    assert gain['value'] == pytest.approx(N * P, rel=1e-12)
    assert odds['value'] == pytest.approx(G * N, rel=1e-12)
    assert (spare['value'], spare['why']) == (0.0, [])
    assert gain['unit'] == 'people per people' and odds['unit'] == 'people per fraction'
    assert found['outcomes']['total']['mean'] == pytest.approx(G * N * P, rel=1e-12)


def test_with_an_uncertain_gain_the_derivative_by_the_odds_is_the_mean_over_the_samples():
    """The gain is uniform from 1 to 3 people: the derivative of the mean by the odds is
    `n E[g]`, and that of a sample is `n g` exactly, so the estimate is n times the mean of the
    gains that the study draws, with n times their standard error. The gain is uncertain itself:
    the derivative by it has no meaning as that of one value, and is unsupported."""
    model = compiled(ticks(uncertain('gain', 'people', 0, 10, 'uniform(1 people, 3 people)')))
    settings = SamplingSettings(32, 5)
    gains = np.array(
        [p['shop.gain'] for p in evaluate_uncertainty(model, settings=settings).samples['a']['values']]
    )
    found = expectations.derivatives(model, 'a', ['shop.odds', 'shop.gain'], settings=settings)
    odds, gain = one(found, 'total', 'shop.odds'), one(found, 'total', 'shop.gain')
    assert odds['label'] == 'branch weighting'
    assert odds['value'] == pytest.approx(N * gains.mean(), rel=1e-12)
    assert odds['se'] == pytest.approx(N * gains.std(ddof=1) / 32**0.5, rel=1e-12)
    assert odds['low'] < 2 * N < odds['high']
    assert (gain['label'], gain['value']) == ('unsupported', None)
    assert gain['why'] == ['the input is uncertain: a study draws its values']
    # By default the inputs are those with one value.
    assert expectations.derivatives(model, 'a', settings=settings)['inputs'] == ['shop.odds']


def test_a_bend_keeps_the_sample_mean_and_the_estimate_is_the_part_of_the_samples_on_one_side():
    """The outcome is `max(U, x)`, U uniform from 0 to 1 and x = 0.3: it has a bend at U = x and
    no jump. Its mean is `(1 + x^2) / 2`, with the derivative x. The derivative of a sample is 1
    where U < x and 0 else: the estimate is the part of the draws below x."""
    model = compiled(threshold('max(gate.u, gate.x)'))
    settings = SamplingSettings(256, 7)
    draws = np.array(
        [p['gate.u'] for p in evaluate_uncertainty(model, settings=settings).samples['a']['values']]
    )
    pair = one(expectations.derivatives(model, 'a', ['gate.x'], settings=settings), 'hit', 'gate.x')
    assert pair['label'] == 'sample mean'
    assert pair['value'] == pytest.approx((draws < 0.3).mean(), abs=1e-12)
    assert abs(pair['value'] - 0.3) < 4 * pair['se']
    assert pair['se'] == pytest.approx((0.3 * 0.7 / 256) ** 0.5, rel=0.2)


def test_an_event_that_the_input_moves_into_the_horizon_has_no_sample_mean():
    """An event at the time `x + U` sets the outcome to 1, and the horizon is 6 h: the mean is the
    chance that `x + U <= 6`, which changes with x, and each sample has the derivative 0."""
    source = document(
        'Late',
        entity(
            'gate',
            uncertain('u', 'h', 0, 10, 'uniform(0 h, 10 h)'),
            parameter('x', 1, 'h', 0, 10),
            stock('hit', 0, 'fraction', size=1),
            block('event late once when t >= x + u:  @fixture', '"It comes."', 'hit = 1'),
        ),
        output('hit', 'gate.hit', 'fraction'),
        horizon=6,
    )
    pair = one(
        expectations.derivatives(compiled(source), 'a', ['gate.x'], settings=SamplingSettings(8, 1)),
        'hit',
        'gate.x',
    )
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['an event that the input can move or stop: gate.late']


def test_a_distribution_that_reads_the_input_has_no_estimate():
    """U is uniform from 0 to x and the outcome is U: the mean is x / 2. A sample holds its draw
    of U, so its derivative by x is 0."""
    source = threshold('gate.u', 'uniform(0, x)')
    pair = one(
        expectations.derivatives(compiled(source), 'a', ['gate.x'], settings=SamplingSettings(8, 1)),
        'hit',
        'gate.x',
    )
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['the draw of gate.u follows the input']


def test_a_draw_that_follows_the_input_through_another_draw_has_no_estimate():
    """U is uniform from 0 to x, V is uniform from U to U + 1, and the outcome is V: its mean is
    `x / 2 + 1 / 2`. No read of a run leads from x to V, and the distribution of V does not name
    x: the draw of V follows x through the draw of U."""
    source = document(
        'Chain',
        entity(
            'gate',
            parameter('x', 0.3, 'fraction', 0, 1),
            uncertain('u', 'fraction', 0, 1, 'uniform(0, x)'),
            uncertain('v', 'fraction', 0, 2, 'uniform(u, u + 1)'),
        ),
        output('hit', 'gate.v', 'fraction'),
        horizon=6,
    )
    pair = one(
        expectations.derivatives(compiled(source), 'a', ['gate.x'], settings=SamplingSettings(8, 1)),
        'hit',
        'gate.x',
    )
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['the draw of gate.v follows the input']


def test_a_chance_with_a_comparison_that_the_input_can_change_has_no_estimate():
    source = ticks(
        parameter('gain', G, 'people', 0, 10),
        parameter('mark', 3, 'people', 0, 10),
        odds='(0.9 if total > mark else 0.1)',
    )
    found = expectations.derivatives(compiled(source), 'a', ['shop.mark', 'shop.gain'])
    mark = one(found, 'total', 'shop.mark')
    assert (mark['label'], mark['value']) == ('unsupported', None)
    assert mark['why'] == ['a chance with a comparison that the input can change: shop.tick']
    # The gain moves the total, which the comparison of the chance reads: the same.
    assert one(found, 'total', 'shop.gain')['label'] == 'unsupported'


def test_a_chance_at_the_end_of_its_range_has_no_estimate():
    """With the odds 0 no sample has a hit, and the one path that is run has the weight 1. A
    change of the odds opens the paths with a hit, which are not run."""
    source = ticks().replace('input odds: fraction = 0.3', 'input odds: fraction = 0')
    pair = one(expectations.derivatives(compiled(source), 'a', ['shop.odds']), 'total', 'shop.odds')
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['a chance that the input changes is at the end of its range']


def test_an_input_that_is_no_input_of_the_model_is_an_error():
    with pytest.raises(KeyError, match='no input'):
        expectations.derivatives(compiled(ticks()), 'a', ['shop.none'])


def test_too_many_paths_refuse_the_derivatives():
    found = expectations.derivatives(compiled(ticks()), 'a', limit=10)
    assert not found['admissible'] and [item['code'] for item in found['diagnostics']] == ['paths']


def jump(u='normal(5, 1, 0, 10)'):
    """The outcome is `U + d B`: U a normal number of the mean 5 (cut five standard deviations
    out), d = 0.5, and B is 1 with the chance x, by an event."""
    return document(
        'Jump',
        entity(
            'gate',
            uncertain('u', 'fraction', 0, 10, u),
            parameter('x', 0.3, 'fraction', 0, 1),
            stock('more', 0, 'fraction', size=1),
            block(
                'event attempt once when t >= 1 h:  @fixture',
                '"One trial."',
                block('yes x:', 'more = 0.5'),
                'no else:',
            ),
        ),
        output('hit', 'gate.u + gate.more', 'fraction'),
        horizon=6,
    )


def test_the_tails_of_a_jump_by_chance_have_the_derivatives_of_the_mixture():
    """The distribution of the outcome is `(1 - x) Phi(y) + x Phi(y - d)`. By x:

    (y is the outcome less the mean 5 of U.)

    - the chance to be above c has the derivative `Phi(c) - Phi(c - d)`. No value moves with x, so
      the estimate is a mean, `1(U + d > c) - 1(U > c)` over the draws, with no bias;
    - the quantile q of p has the derivative `(Phi(q) - Phi(q - d)) / f(q)`, f the density. The
      density is estimated with a kernel: the estimate is slower, and it is compared here with
      the same ratio for the density that a normal kernel of the given width makes of the
      mixture (a normal density of the variance `1 + h^2`), at four standard errors."""
    model = compiled(jump())
    settings = SamplingSettings(1500, 11)
    draws = np.array(
        [p['gate.u'] for p in evaluate_uncertainty(model, settings=settings).samples['a']['values']]
    )
    c, d, x, p, mid = 5.8, 0.5, 0.3, 0.5, 5.0
    found = expectations.derivatives(
        model, 'a', ['gate.x'], settings=settings, exceed={'hit': c}, quantiles={'hit': p}
    )
    pair = one(found, 'hit', 'gate.x')
    assert pair['label'] == 'branch weighting' and pair['value'] == pytest.approx(d, rel=1e-9)
    above = pair['exceedance']
    assert above['value'] == pytest.approx(((draws + d > c).astype(float) - (draws > c)).mean(), abs=1e-12)
    assert abs(above['value'] - (special.ndtr(c - mid) - special.ndtr(c - mid - d))) < 4 * above['se']
    assert (above['slower'], above['bandwidth'], above['at']) == (False, None, c)
    quantile = pair['quantile']
    from scipy.optimize import brentq

    q = brentq(lambda y: (1 - x) * special.ndtr(y) + x * special.ndtr(y - d) - p, -5, 5)  # less the mean
    assert quantile['at'] == pytest.approx(mid + q, abs=0.1)
    wide = (1 + quantile['bandwidth'] ** 2) ** 0.5
    smoothed = ((1 - x) * np.exp(-0.5 * (q / wide) ** 2) + x * np.exp(-0.5 * ((q - d) / wide) ** 2)) / (
        wide * (2 * np.pi) ** 0.5
    )
    assert quantile['slower'] and quantile['density'] == pytest.approx(smoothed, rel=0.1)
    assert abs(quantile['value'] - (special.ndtr(q) - special.ndtr(q - d)) / smoothed) < 4 * quantile['se']
    assert quantile['se'] < 0.1 * quantile['value']


def test_the_tails_need_independent_samples():
    found = expectations.derivatives(
        compiled(jump()), 'a', ['gate.x'], settings=SamplingSettings(64, 1, 'sobol'), exceed={'hit': 5.8}
    )
    pair = one(found, 'hit', 'gate.x')
    assert pair['exceedance'] is None
    # The mean has the interval of the blocks: the derivative of each sample is 0.5 exactly.
    assert pair['value'] == pytest.approx(0.5, rel=1e-9) and pair['se'] == pytest.approx(0.0, abs=1e-12)


# ---- more of the structure behind a label --------------------------------------------------------------


def test_a_comparison_in_the_value_that_a_step_sets_has_no_sample_mean():
    """The threshold example again, with the comparison in the value that an event sets at 1 h:
    the mean is x and each sample has the derivative 0. The event does not move with x; the value
    that it writes jumps."""
    source = document(
        'Set',
        entity(
            'gate',
            uncertain('u', 'fraction', 0, 1, 'uniform(0, 1)'),
            parameter('x', 0.3, 'fraction', 0, 1),
            stock('hit', 0, 'fraction', size=1),
            block('event look once when t >= 1 h:  @fixture', '"It looks."', 'hit = (1 if u < x else 0)'),
        ),
        output('hit', 'gate.hit', 'fraction'),
        horizon=6,
    )
    pair = one(
        expectations.derivatives(compiled(source), 'a', ['gate.x'], settings=SamplingSettings(8, 1)),
        'hit',
        'gate.x',
    )
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['a comparison that the input can change, in gate.hit']


def test_a_comparison_in_a_member_of_a_list_has_no_sample_mean():
    """Two copies of a cell, each with the threshold example as a formula, and the outcome is
    their sum: the comparison is in the members of the list that the outcome reads."""
    source = document(
        'List',
        entity('gate', parameter('x', 0.3, 'fraction', 0, 1)),
        template(
            'Cell',
            uncertain('u', 'fraction', 0, 1, 'uniform(0, 1)'),
            formula('hit', '1 if u < gate.x else 0', 'fraction'),
        ),
        entity('cells', template='Cell', copies=2),
        output('hits', 'sum(Cell.hit)', 'fraction'),
        horizon=6,
    )
    pair = one(
        expectations.derivatives(compiled(source), 'a', ['gate.x'], settings=SamplingSettings(8, 1)),
        'hits',
        'gate.x',
    )
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['a comparison that the input can change, in hits']


def test_a_comparison_that_the_input_cannot_change_keeps_the_sample_mean():
    """The outcome is `x (2 if U < 0.5 else 1)`: the comparison reads U alone, so the outcome of
    a sample is a line in x. The derivative of the mean is 1.5, and the estimate is the mean of
    2 or 1 over the draws."""
    model = compiled(threshold('gate.x * (2 if gate.u < 0.5 else 1)'))
    settings = SamplingSettings(64, 3)
    draws = np.array(
        [p['gate.u'] for p in evaluate_uncertainty(model, settings=settings).samples['a']['values']]
    )
    pair = one(expectations.derivatives(model, 'a', ['gate.x'], settings=settings), 'hit', 'gate.x')
    assert pair['label'] == 'sample mean'
    assert pair['value'] == pytest.approx(np.where(draws < 0.5, 2.0, 1.0).mean(), rel=1e-12)
    assert abs(pair['value'] - 1.5) < 4 * pair['se']


def test_a_store_that_can_rest_on_its_bound_has_no_sample_mean():
    """A pool of 5 people drains at the rate x until it is empty: what has left at 10 h is
    `min(5, 10 x)`. The pool can rest on its bound, and the label is the safe one."""
    source = system(
        parameter('x', 1, 'people/h', 0, 4),
        stock('pool', 5),
        stock('gone', 0, kind='tally', size=100),
        flow('drain', move('pool', 'gone'), 'x'),
        horizon=10,
        outputs=(output('gone', 's.gone', 'people'),),
    )
    pair = one(expectations.derivatives(compiled(source), 'a', ['s.x']), 'gone', 's.x')
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['a store that can rest on its bound: s.pool']


def test_an_event_that_the_input_moves_stops_only_the_outcomes_that_it_reaches():
    """The gain moves an event (it comes when the gain is above 1 person) that sets a flag. The
    flag has no sample mean by the gain. The total does not read the flag: by the gain it keeps
    its sample mean, `n p`."""
    source = ticks(
        extra=(
            stock('flag', 0, 'fraction', size=1),
            block('event lift once when gain > 1 people:  @fixture', '"The flag goes up."', 'flag = 1'),
        )
    ).replace('\noutput total', '\n' + output('flag', 'shop.flag', 'fraction') + '\n\noutput total')
    found = expectations.derivatives(compiled(source), 'a', ['shop.gain'])
    flag, total = one(found, 'flag', 'shop.gain'), one(found, 'total', 'shop.gain')
    assert (flag['label'], flag['value']) == ('unsupported', None)
    assert flag['why'] == ['an event that the input can move or stop: shop.lift']
    assert (total['label'], total['value']) == ('sample mean', pytest.approx(N * P, rel=1e-12))


def test_a_run_that_sets_a_value_on_its_bound_has_no_estimate():
    """The total holds 12 people at most, and a hit adds a little more than 2 people (by one
    part in 10^13). Six hits pass the bound by less than the engine can resolve: the step of the
    sixth hit sets the total on its bound, where the total does not move with the gain. The
    structure shows a sample mean; the run with six hits is no smooth path, and the pair has no
    estimate. With a gain of 1 person no path comes near the bound."""
    bounded = ticks().replace(
        'var total: people = 0 size 1000 people', 'var total: people = 0 in 0 to 12 people'
    )
    near = bounded.replace('input gain: people = 2.0 people', 'input gain: people = 2.0000000000002 people')
    assert bounded != ticks() and near != bounded
    pair = one(expectations.derivatives(compiled(near), 'a', ['shop.gain']), 'total', 'shop.gain')
    assert (pair['label'], pair['value']) == ('unsupported', None)
    assert pair['why'] == ['a run met: shop.total is set on its bound (t = 6 h)']
    far = bounded.replace('input gain: people = 2.0 people', 'input gain: people = 1.0 people')
    pair = one(expectations.derivatives(compiled(far), 'a', ['shop.gain']), 'total', 'shop.gain')
    assert (pair['label'], pair['value']) == ('sample mean', pytest.approx(N * P, rel=1e-12))


def test_a_sample_on_a_bend_has_the_derivative_of_one_side_and_says_so():
    """The outcome is `max(x, y)` with x = y: no value is uncertain, and the one sample sits on
    the bend. The derivative by each input is that of one side: 1 for the piece that gives the
    value and 0 for the other, so the two add up to 1. Away from the bend nothing is one-sided."""
    source = document(
        'Bend',
        entity('gate', parameter('x', 0.3, 'fraction', 0, 1), parameter('y', 0.3, 'fraction', 0, 1)),
        output('top', 'max(gate.x, gate.y)', 'fraction'),
        horizon=6,
    )
    found = expectations.derivatives(compiled(source), 'a')
    x, y = one(found, 'top', 'gate.x'), one(found, 'top', 'gate.y')
    assert (x['label'], y['label']) == ('sample mean', 'sample mean')
    assert x['one_sided'] and y['one_sided']
    assert sorted([x['value'], y['value']]) == [0.0, 1.0]
    apart = expectations.derivatives(compiled(source.replace('y: fraction = 0.3', 'y: fraction = 0.2')), 'a')
    assert [one(apart, 'top', name)['one_sided'] for name in ('gate.x', 'gate.y')] == [False, False]
    assert [one(apart, 'top', name)['value'] for name in ('gate.x', 'gate.y')] == [1.0, 0.0]


def test_a_derivative_is_in_the_unit_of_the_outcome_as_the_file_writes_it():
    """A hit adds 12 h to a time that the outcome gives in days: the mean is `n p / 2` days, the
    derivative by the odds `n / 2` days, and that by the gain `n p / 24` days for an hour."""
    source = (
        ticks(parameter('gain', 12, 'h', 0, 100))
        .replace('var total: people = 0 size 1000 people', 'var total: h = 0 size 1000 h')
        .replace('output total: people', 'output total: days')
    )
    found = expectations.derivatives(compiled(source), 'a')
    odds, gain = one(found, 'total', 'shop.odds'), one(found, 'total', 'shop.gain')
    assert found['outcomes']['total']['mean'] == pytest.approx(N * P / 2, rel=1e-12)
    assert (odds['value'], odds['unit']) == (pytest.approx(N / 2, rel=1e-12), 'days per fraction')
    assert (gain['value'], gain['unit']) == (pytest.approx(N * P / 24, rel=1e-12), 'days per h')


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
