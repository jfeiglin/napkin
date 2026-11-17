"""The estimators of a study and their intervals (`napkin/engine/estimators.py`).

Each oracle is mathematics that the functions do not use: the binomial sum written with whole
numbers for the coverage of a quantile interval, the closed moments of small distributions, the
geometric series, and counts over many made-up studies with fixed seeds, each with the margin that
the binomial spread of such a count gives.
"""

import math
import statistics
from fractions import Fraction

import numpy as np
import pytest

from napkin.engine import estimators


def binomial_between(n, p, low, high):
    """P(low <= B <= high) for B binomial (n, p), with whole-number arithmetic."""
    p = Fraction(p).limit_denominator(10**6)
    return float(sum(math.comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(low, high + 1)))


def test_the_mean_of_independent_samples_has_students_interval():
    values = [2.0, 4.0, 4.0, 5.0, 10.0]
    found = estimators.mean_interval(values, 0.95)
    se = statistics.stdev(values) / math.sqrt(5)
    assert found['mean'] == pytest.approx(5.0) and found['se'] == pytest.approx(se) and found['n'] == 5
    # Student's t for 4 degrees of freedom at 97.5%: 2.776445.
    assert found['high'] - found['mean'] == pytest.approx(2.776445 * se, rel=1e-6)
    assert found['mean'] - found['low'] == pytest.approx(found['high'] - found['mean'])
    with pytest.raises(ValueError):
        estimators.mean_interval([1.0])


def test_the_interval_of_replicates_comes_from_the_means_of_the_blocks():
    """Three blocks whose means are 1, 2 and 6: the estimate is 3, and its standard error is that
    of those three numbers, whatever the spread inside a block is."""
    blocks = [[1.0, 1.0, 1.0, 1.0], [0.0, 4.0, 0.0, 4.0], [6.0, 6.0, 5.0, 7.0]]
    found = estimators.replicate_interval(blocks)
    assert found['mean'] == pytest.approx(3.0) and found['n'] == 12 and found['replicates'] == 3
    assert found['se'] == pytest.approx(statistics.stdev([1.0, 2.0, 6.0]) / math.sqrt(3))
    with pytest.raises(ValueError):
        estimators.replicate_interval([[1.0, 2.0]])
    with pytest.raises(ValueError):
        estimators.replicate_interval([[1.0, 2.0], [1.0]])


@pytest.mark.parametrize(
    ('n', 'p', 'confidence'),
    [(20, 0.5, 0.9), (100, 0.5, 0.95), (100, 0.95, 0.95), (500, 0.05, 0.99), (59, 0.95, 0.9)],
)
def test_the_interval_of_a_quantile_has_the_coverage_that_the_binomial_sum_gives(n, p, confidence):
    """The quantile is between the values of the ranks l and u when the number of samples below it
    is from l to u - 1: the coverage is that binomial sum, which is at least the confidence. The
    interval is no wider than needed: with one rank less on either side the sum is too small."""
    values = np.random.default_rng(5).normal(size=n)
    found = estimators.quantile_interval(values, p, confidence)
    low, high = found['ranks']
    ordered = np.sort(values)
    assert found['low'] == ordered[low - 1] and found['high'] == ordered[high - 1] and 1 <= low < high <= n
    exact = binomial_between(n, p, low, high - 1)
    assert found['coverage'] == pytest.approx(exact, abs=1e-9) and exact >= confidence
    if high - low > 1:
        assert binomial_between(n, p, low + 1, high - 1) < confidence
        assert binomial_between(n, p, low, high - 2) < confidence


def test_a_study_with_too_few_samples_has_no_interval_of_a_quantile():
    """Between the least and the greatest of n samples the 95th percentile lies with the chance
    1 - 0.95^n - 0.05^n: 0.9 needs 45 samples."""
    values = np.random.default_rng(1).normal(size=44)
    assert 1 - 0.95**44 - 0.05**44 < 0.9 < 1 - 0.95**45 - 0.05**45
    assert estimators.quantile_interval(values, 0.95, 0.9) is None
    assert estimators.quantile_interval(np.append(values, 0.0), 0.95, 0.9) is not None
    with pytest.raises(ValueError):
        estimators.quantile_interval(values, 1.0)


def test_the_interval_of_a_quantile_holds_the_quantile_as_often_as_it_says():
    """4,000 studies of 200 exponential samples: the interval of the 90th percentile at 0.9 holds
    the true one, ln 10, in at least 90% of them, less three times the binomial spread of that
    count; and not in all of them, or the interval would say too little."""
    rng, hits, studies = np.random.default_rng(11), 0, 4000
    for _ in range(studies):
        found = estimators.quantile_interval(rng.exponential(size=200), 0.9, 0.9)
        hits += found['low'] <= math.log(10) <= found['high']
    spread = math.sqrt(0.9 * 0.1 / studies)
    assert 0.9 - 3 * spread <= hits / studies <= 0.97


def test_the_looks_of_a_stopping_rule_spend_less_than_the_error_together():
    """Look j spends `alpha / 2^(j + 1)`: a half, a quarter, an eighth of the error, and so on.
    The sum of any number of these parts is below the whole (a geometric series), as whole-number
    arithmetic shows for 200 looks."""
    assert [estimators.spent(0.05, look) for look in range(3)] == [0.025, 0.0125, 0.00625]
    parts = [Fraction(estimators.spent(1.0, look)) for look in range(200)]
    assert parts == [Fraction(1, 2 ** (look + 1)) for look in range(200)]
    assert sum(parts) == 1 - Fraction(1, 2**200) < 1


def test_a_study_grows_until_its_interval_is_narrow_and_keeps_its_confidence():
    """2,000 studies of uniform numbers, each grown until the interval of the median is no wider
    than 0.12. Each stops at a look (64 times a power of two) with a narrow interval, the larger
    part of them after more than one look, and the interval that it stops with holds the true
    median 0.5 in at least 95% of the studies, less three times the binomial spread. The interval
    of a later look is wider than the 95% interval of its samples: it has the confidence that is
    left for that look."""
    rng, hits, sizes, studies = np.random.default_rng(3), 0, [], 2000
    for _ in range(studies):
        numbers = rng.uniform(size=4096)
        found = estimators.until_narrow(lambda n, numbers=numbers: numbers[:n], 0.5, 0.12, 0.95)
        assert found['narrow'] and found['n'] == 64 * 2 ** found['look']
        interval = found['interval']
        assert interval['high'] - interval['low'] <= 0.12
        # Look j has the confidence 1 - 0.05 / 2^(j + 1): the binomial sum of its ranks says so.
        low, high = interval['ranks']
        assert binomial_between(found['n'], 0.5, low, high - 1) >= 1 - 0.05 / 2 ** (found['look'] + 1)
        hits += interval['low'] <= 0.5 <= interval['high']
        sizes.append(found['n'])
    assert sum(size > 64 for size in sizes) > studies / 2 and max(sizes) <= 4096
    assert hits / studies >= 0.95 - 3 * math.sqrt(0.95 * 0.05 / studies)


def test_a_study_that_cannot_get_narrow_stops_at_its_limit_and_says_so():
    numbers = np.random.default_rng(2).uniform(size=256)
    found = estimators.until_narrow(lambda n: numbers[:n], 0.5, 1e-6, 0.95, start=64, limit=256)
    assert found['n'] == 256 and found['look'] == 2 and not found['narrow']


def test_a_control_with_a_known_mean_takes_out_what_it_follows_and_adds_no_bias():
    """x is uniform on (0, 1) and the value is x². The control is the line through the value at
    the middle, `x - 1/2`, whose mean is 0. The mean of `x² - (x - 1/2)` is 1/3, the mean of x²,
    so the estimate has no bias; and the variance of the differences is 1/180 where that of x² is
    4/45: the standard error is a quarter. A value that is its control exactly has no error."""
    x = np.random.default_rng(7).uniform(size=20000)
    found = estimators.control_variate(x * x, x - 0.5, 0.0)
    assert found['se'] == pytest.approx(math.sqrt(1 / 180 / len(x)), rel=0.03)
    assert found['plain']['se'] == pytest.approx(math.sqrt(4 / 45 / len(x)), rel=0.03)
    assert abs(found['mean'] - 1 / 3) <= 4 * found['se']
    assert abs(found['plain']['mean'] - 1 / 3) <= 4 * found['plain']['se']
    line = estimators.control_variate(3 * x + 2, 3 * (x - 0.5), 0.0)
    assert line['mean'] == pytest.approx(3.5, rel=1e-12) and line['se'] == pytest.approx(0.0, abs=1e-12)
    # A wrong mean of the control moves the estimate by that much: the mean must be the true one.
    assert estimators.control_variate(x * x, x - 0.5, 0.1)['mean'] == pytest.approx(found['mean'] + 0.1)
    with pytest.raises(ValueError):
        estimators.control_variate([1.0, 2.0], [1.0], 0.0)


def test_the_paths_of_chance_events_with_their_weights_give_the_expectation_with_no_error():
    """Two events with two outcomes each: four paths. The mean is the sum of weight times value,
    and the variance the weighted spread around it. Weights that do not add up to 1 are an error."""
    p, q = 0.3, 0.6
    paths = [(p * q, 10.0), (p * (1 - q), 4.0), ((1 - p) * q, 1.0), ((1 - p) * (1 - q), 0.0)]
    found = estimators.weighted(paths)
    mean = 0.18 * 10 + 0.12 * 4 + 0.42 * 1
    assert (
        found['mean'] == pytest.approx(mean) and found['paths'] == 4 and found['weight'] == pytest.approx(1.0)
    )
    assert found['variance'] == pytest.approx(0.18 * 100 + 0.12 * 16 + 0.42 * 1 - mean**2)
    with pytest.raises(ValueError):
        estimators.weighted(paths[:3])
    with pytest.raises(ValueError):
        estimators.weighted([])


# ---- every path of the outcomes ----------------------------------------------------------------------


def made_up_tree(depth=5):
    """A tree of firings that the test makes up: after the places `taken`, the next firing has
    two or three outcomes whose chances follow from those places, and a path ends at `depth`
    firings or, for some places, sooner. `chances(taken)` gives the chances of the next firing,
    or None at the end of a path."""

    def chances(taken):
        if len(taken) >= depth or (len(taken) >= 2 and sum(taken) % 4 == 3):
            return None
        seed = 7 * len(taken) + sum((k + 1) * place for k, place in enumerate(taken))
        parts = [1 + seed % 3, 2 + seed % 5, (seed % 2) * (1 + seed % 4)]
        return tuple(Fraction(part, sum(parts)) for part in parts)

    return chances


def run_of(chances, calls=None):
    """`run(places)` of `every_path` for a made-up tree: the run takes the given places, and after
    them the likeliest outcome of each firing (the first on a tie)."""

    def run(places):
        if calls is not None:
            calls.append(places)
        taken, firings = (), []
        while (found := chances(taken)) is not None:
            place = (
                places[len(taken)]
                if len(taken) < len(places)
                else max(range(3), key=lambda k: (found[k], -k))
            )
            firings.append((tuple(float(chance) for chance in found), place))
            taken = (*taken, place)
        return firings, taken

    return run


def leaves(chances, taken=(), weight=Fraction(1)):
    """Every path of a made-up tree with its exact weight, by going down each branch."""
    found = chances(taken)
    if found is None:
        return {taken: weight}
    out = {}
    for place, chance in enumerate(found):
        if chance > 0:
            out |= leaves(chances, (*taken, place), weight * chance)
    return out


def test_every_path_of_a_tree_is_run_once_with_the_product_of_its_chances():
    """The paths of `every_path` are those that the test finds by going down each branch, each
    once, and the weight of each is the product of its chances; the weights add up to 1."""
    chances = made_up_tree()
    exact = leaves(chances)
    calls = []
    found = estimators.every_path(run_of(chances, calls))
    assert len(calls) == len(found) == len(exact) > 40
    assert sorted(result for _, _, result in found) == sorted(exact)
    for weight, firings, result in found:
        assert weight == pytest.approx(float(exact[result]), rel=1e-12)
        assert tuple(place for _, place in firings) == result
    assert sum(exact.values()) == 1
    assert sum(weight for weight, _, _ in found) == pytest.approx(1.0, abs=1e-12)


def test_more_paths_than_the_limit_stop_before_the_limit_is_passed():
    chances, calls = made_up_tree(), []
    count = len(leaves(chances))
    with pytest.raises(estimators.TooManyPaths, match=f'more than {count - 1} paths'):
        estimators.every_path(run_of(chances, calls), limit=count - 1)
    assert len(calls) < count
    assert len(estimators.every_path(run_of(chances), limit=count)) == count


def test_a_run_that_does_not_take_its_given_places_is_an_error():
    def run(places):
        return [((0.5, 0.5), 0), ((0.5, 0.5), 0)], None

    with pytest.raises(ValueError, match='took the places'):
        estimators.every_path(run)


def test_a_control_over_replicates_has_the_interval_of_the_means_of_its_blocks():
    """Four blocks of three samples. The values less the control (whose mean is 1) have the block
    means 2, 4, 6 and 8: the estimate is 5, with the standard error of those four numbers."""
    values = [3.0, 2.0, 4.0, 5.0, 5.0, 5.0, 8.0, 6.0, 7.0, 9.0, 9.0, 9.0]
    controls = [2.0, 1.0, 3.0, 2.0, 2.0, 2.0, 3.0, 1.0, 2.0, 2.0, 2.0, 2.0]
    found = estimators.control_variate(values, controls, 1.0, replicates=4)
    assert found['mean'] == pytest.approx(5.0)
    assert found['se'] == pytest.approx(statistics.stdev([2.0, 4.0, 6.0, 8.0]) / 2)
    assert (found['n'], found['replicates']) == (12, 4)
    assert found['plain']['mean'] == pytest.approx(statistics.fmean(values))


# ---- the derivatives of the tails ----------------------------------------------------------------------


def normal_density(x, mean=0.0, sd=1.0):
    return math.exp(-0.5 * ((x - mean) / sd) ** 2) / (sd * math.sqrt(2 * math.pi))


def normal_below(x, mean=0.0, sd=1.0):
    return 0.5 * (1 + math.erf((x - mean) / (sd * math.sqrt(2))))


def moved_samples(n, x, seed):
    """n samples of one path each: the value `x U`, U normal (2, 0.5), which moves with x at the
    rate U; the weight 1 does not change."""
    draws = np.random.default_rng(seed).normal(2.0, 0.5, n)
    return [([1.0], [x * u], [u], [0.0]) for u in draws]


def test_the_chance_to_pass_a_value_that_moves_has_the_rate_of_the_density_there():
    """The value is `x U` with U normal (2, 0.5), so it is normal (2 x, 0.5 x). The chance to be
    above c is `1 - Phi((c / x - 2) / 0.5)`, whose derivative by x is
    `phi((c / x - 2) / 0.5) c / (0.5 x^2)`. The estimate uses a kernel of the width h: its mean is
    not that derivative but `E[k_h(c - x U) U]`, which is a closed form for a normal kernel: with
    `s^2 = (0.5 x)^2 + h^2`, the density of a normal (2 x, s) at c times the mean of U given
    that the smoothed value is c. The estimate is within four of its standard errors of that,
    and the kernel moves it from the true derivative by less than a tenth here."""
    x, c, n = 1.5, 3.6, 4000
    found = estimators.tail_slopes(moved_samples(n, x, 21), threshold=c)
    h = found['bandwidth']
    assert found['slower'] and h == pytest.approx(1.06 * 0.75 * n**-0.2, rel=0.05)
    spread = (0.5 * x) ** 2
    mean_of_value = (2 * x * h**2 + c * spread) / (spread + h**2)
    smoothed = normal_density(c, 2 * x, math.sqrt(spread + h**2)) * mean_of_value / x
    exact = normal_density((c / x - 2) / 0.5) * c / (0.5 * x**2)
    assert abs(found['value'] - smoothed) < 4 * found['se']
    assert abs(smoothed - exact) < 0.1 * exact
    assert found['se'] < 0.1 * exact and found['at'] == c and found['density'] is None


def test_the_quantile_of_a_value_that_moves_has_the_mean_rate_of_the_values_there():
    """The quantile p of `x U` is x times that of U: its derivative by x is the quantile of U,
    `2 + 0.5 z`. The estimate is the mean of U among the samples near the quantile (a ratio of
    two kernel sums): for the upper quartile, `2 + 0.5 * 0.6745`. The kernel pulls it toward the
    mean of U by the part `h^2 / (spread + h^2)` of the distance, which the test allows for, and
    the rest is within four standard errors."""
    x, p, n = 1.5, 0.75, 4000
    found = estimators.tail_slopes(moved_samples(n, x, 22), p=p)
    exact = 2 + 0.5 * 0.6744897501960817
    assert found['at'] == pytest.approx(x * exact, abs=0.05)
    h, spread = found['bandwidth'], (0.5 * x) ** 2
    pulled = (2 * x * h**2 + found['at'] * spread) / (spread + h**2) / x
    assert found['slower'] and abs(found['value'] - pulled) < 4 * found['se']
    assert abs(pulled - exact) < 0.03 * exact
    assert found['density'] == pytest.approx(
        normal_density(found['at'], 2 * x, math.sqrt(spread + h**2)), rel=0.1
    )
    assert found['low'] < found['value'] < found['high']
    assert found['high'] - found['low'] == pytest.approx(2 * 1.96 * found['se'], rel=0.01)


def weighted_samples(n, x, d, seed):
    """n samples of two paths each: the value U with the weight 1 - x and U + d with the weight
    x, U a standard normal number. No value moves with x; the weights change at -1 and 1."""
    draws = np.random.default_rng(seed).normal(0.0, 1.0, n)
    return [([1 - x, x], [u, u + d], [0.0, 0.0], [-1.0, 1.0]) for u in draws], draws


def test_the_tails_of_paths_whose_weights_change_are_means_with_no_kernel():
    """The distribution is `(1 - x) Phi(y) + x Phi(y - d)`. The chance to be above c has the
    derivative `Phi(c) - Phi(c - d)` by x: the estimate is the mean of `1(U + d > c) - 1(U > c)`
    over the draws, with the standard error of that mean, and it needs no density."""
    x, d, c, n = 0.3, 0.5, 0.8, 2000
    samples, draws = weighted_samples(n, x, d, 23)
    found = estimators.tail_slopes(samples, threshold=c)
    each = (draws + d > c).astype(float) - (draws > c)
    assert found['value'] == pytest.approx(each.mean(), abs=1e-12)
    assert found['se'] == pytest.approx(each.std(ddof=1) / math.sqrt(n), rel=1e-9)
    assert abs(found['value'] - (normal_below(c) - normal_below(c - d))) < 4 * found['se']
    assert (found['slower'], found['bandwidth'], found['density'], found['n']) == (False, None, None, n)


def test_a_result_with_no_density_has_no_derivative_of_a_quantile():
    """Every value the same, or one sample: no density. The chance to pass a value still has its
    derivative where only the weights change (one sample: with no interval)."""
    flat = [([0.5, 0.5], [1.0, 1.0], [0.0, 0.0], [-1.0, 1.0])] * 8
    assert estimators.tail_slopes(flat, p=0.5) is None
    one = [([0.7, 0.3], [0.0, 1.0], [0.0, 0.0], [-1.0, 1.0])]
    assert estimators.tail_slopes(one, p=0.5) is None
    assert estimators.tail_slopes(one, threshold=0.5) == {
        'value': 1.0,
        'se': None,
        'low': None,
        'high': None,
        'n': 1,
        'at': 0.5,
        'density': None,
        'bandwidth': None,
        'slower': False,
    }
    moving = [([1.0], [1.0], [1.0], [0.0])] * 8
    assert estimators.tail_slopes(moving, threshold=1.0) is None


def test_the_tails_take_a_value_or_a_quantile_and_not_both():
    one = [([1.0], [1.0], [0.0], [0.0])] * 4
    for options in ({}, {'threshold': 1.0, 'p': 0.5}):
        with pytest.raises(ValueError, match='one of'):
            estimators.tail_slopes(one, **options)


def test_the_interval_of_the_derivative_of_a_quantile_has_the_spread_of_the_estimate():
    """Sixty made-up studies of 500 samples each. The standard deviation of their sixty
    estimates is what the standard error of one study says, to the margin of sixty studies (a
    standard deviation from sixty numbers is right to about a tenth). Three cases: the quantile
    of a value that moves (`x U`), the quantile of paths whose weights change, and the chance
    that a value that moves is above a mark. For a quantile the error has two parts, that of the
    ratio and that of the quantile of the samples at which the ratio is taken: an interval with
    the first part alone is a quarter of the spread for the value that moves."""
    cases = {
        'moved': lambda study: estimators.tail_slopes(moved_samples(500, 1.5, 100 + study), p=0.75),
        'weighted': lambda study: estimators.tail_slopes(
            weighted_samples(500, 0.3, 0.5, 300 + study)[0], p=0.5
        ),
        'above': lambda study: estimators.tail_slopes(moved_samples(500, 1.5, 500 + study), threshold=3.6),
    }
    for name, make in cases.items():
        found = [make(study) for study in range(60)]
        spread = statistics.stdev(item['value'] for item in found)
        said = statistics.fmean(item['se'] for item in found)
        assert 0.7 < spread / said < 1.4, name
