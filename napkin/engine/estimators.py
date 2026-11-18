"""The estimators of a study, each with the interval that belongs to it (docs/engine.md, "Estimators").

A study gives numbers that vary with its samples. Each function here gives one estimate with one
interval, and says in its text under which assumption the interval holds. The functions take plain
numbers and know nothing of a model: a study gives them its samples (`engine/uncertainty.py`).

- `mean_interval`: the mean of independent samples, with Student's interval.
- `replicate_interval`: the mean of the means of independent replicates (the blocks of scrambled
  Sobol' points): the points of one block are not independent, the blocks are.
- `quantile_interval`: an interval for a quantile from two order statistics, which holds for any
  continuous distribution and has at least the confidence that it says.
- `spent` and `until_narrow`: a stopping rule that looks at a growing study several times and
  keeps the confidence of the interval that it stops with.
- `control_variate`: the mean with a control whose own mean is known, without bias.
- `every_path` and `weighted`: the expectation over the outcomes of chance events from every
  path of those outcomes with its weight.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats


def mean_interval(values, confidence=0.95):
    """{mean, se, low, high, n} of independent samples of one distribution. The interval is
    Student's: it has the confidence that it says when the mean of n samples is close to normal."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < 2:
        raise ValueError('an interval of a mean needs two samples or more')
    mean, se = float(x.mean()), float(x.std(ddof=1) / math.sqrt(n))
    half = float(stats.t.ppf(0.5 + confidence / 2, n - 1)) * se
    return {'mean': mean, 'se': se, 'low': mean - half, 'high': mean + half, 'n': n}


def replicate_interval(blocks, confidence=0.95):
    """{mean, se, low, high, n} from independent replicates of one estimator: `blocks` has the
    values of each replicate. The estimate is the mean of the means of the blocks, and its
    standard error comes from how those means differ; so the values inside one block need not be
    independent (the points of one scrambled Sobol' block are not). Each block has one size."""
    sizes = {len(block) for block in blocks}
    if len(blocks) < 2 or len(sizes) != 1 or 0 in sizes:
        raise ValueError('the replicates are two blocks or more of one size')
    found = mean_interval([float(np.mean(block)) for block in blocks], confidence)
    return {**found, 'n': len(blocks) * sizes.pop(), 'replicates': len(blocks)}


def quantile_interval(values, p, confidence=0.95):
    """{low, high, ranks, coverage} for the quantile `p` (0 < p < 1) of the distribution of
    independent samples: two of the sorted values, of the ranks (l, u) from 1, such that the
    quantile is between them with at least `confidence`. It holds for every continuous
    distribution: the number of samples below the quantile is binomial (n, p), and the quantile is
    between the two values when that number is from l to u - 1. The ranks go out from n p by one
    rank at a time, on the side that adds more, until the coverage is enough. None when even the
    least and the greatest value do not give the confidence: the study has too few samples."""
    if not 0 < p < 1:
        raise ValueError('a quantile is between 0 and 1')
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    # The chance that at most k samples are below the quantile, for each k from 0 to n.
    at_most = stats.binom.cdf(np.arange(n + 1), n, p)

    def coverage(low, high):
        return float(at_most[high - 1] - at_most[low - 1])

    if n < 2 or coverage(1, n) < confidence:
        return None
    low = min(max(math.floor(n * p), 1), n - 1)
    high = low + 1
    while coverage(low, high) < confidence:
        down = coverage(low - 1, high) if low > 1 else -1.0
        up = coverage(low, high + 1) if high < n else -1.0
        if down >= up:
            low -= 1
        else:
            high += 1
    return {
        'low': float(x[low - 1]),
        'high': float(x[high - 1]),
        'ranks': (low, high),
        'coverage': coverage(low, high),
    }


def spent(alpha, look):
    """The part of the error `alpha` that look number `look` (from 0) of a stopping rule can
    spend: half of what is left after the looks before it, `alpha / 2^(look + 1)`. All looks
    together spend less than `alpha`, however many there are."""
    return alpha / 2 ** (look + 1)


def until_narrow(sample, p, width, confidence=0.95, start=64, limit=1 << 20):
    """A study that grows until the interval of a quantile is narrow enough.

    `sample(n)` gives the first n samples of the study, and the first n of a larger study are the
    same samples. The rule looks at n = `start`, 2 `start`, 4 `start`, …: at look j the interval
    of the quantile `p` is made with the confidence `1 - spent(1 - confidence, j)`, and the rule
    stops when it is no wider than `width`, or when the next look would pass `limit`. It gives
    {n, look, narrow, interval}.

    The interval that the rule stops with has at least `confidence`, although the rule chose
    when to stop: the chance that the interval of any look misses the quantile is no more than
    the sum of what the looks spend, which is below `1 - confidence`."""
    alpha, look, n, last = 1 - confidence, 0, start, None
    while True:
        found = quantile_interval(sample(n), p, 1 - spent(alpha, look))
        if found is not None:
            last = {'n': n, 'look': look, 'interval': found, 'narrow': found['high'] - found['low'] <= width}
            if last['narrow']:
                return last
        if 2 * n > limit:
            return last
        look, n = look + 1, 2 * n


def control_variate(values, controls, expected, confidence=0.95, replicates=None):
    """{mean, se, low, high, n, plain} of the mean of `values` with a control: `controls` has, for
    each sample, the value of a function of the same draws whose true mean `expected` is known.
    The estimate is the mean of `value - (control - expected)`. It has no bias, whatever the
    control is; its standard error is that of the differences, so it is small where the control
    follows the value (a linear form of the inputs near the central run), and it can be larger
    than that of the plain mean where it does not. `plain` is the plain mean with its interval.
    With `replicates` the samples are that many independent blocks one after another, and each
    interval is that of the means of the blocks (`replicate_interval`)."""
    y, c = np.asarray(values, dtype=float), np.asarray(controls, dtype=float)
    if y.shape != c.shape:
        raise ValueError('each sample has one value and one control')

    def interval(x):
        if replicates is None:
            return mean_interval(x, confidence)
        return replicate_interval(np.split(x, replicates), confidence)

    return {**interval(y - (c - float(expected))), 'plain': interval(y)}


class TooManyPaths(ValueError):
    """The outcomes of the chance events of a run have more paths than the limit."""


def every_path(run, limit=4096):
    """Every path of the outcomes of the chance events of a run: [(weight, firings, result)].

    `run(places)` makes one run in which the first firings that go by chance take the outcomes at
    `places`, and each later one takes an outcome that the run chooses. It gives (firings, result):
    `firings` has, for each such firing in the order of the run, (the chance of each outcome, the
    place of the outcome that the firing took). A run is a function of its places alone.

    The paths make a tree: a run with the places `p` has one child for each later firing and each
    other outcome of that firing with a chance, the places of the run up to that firing and then
    that outcome. Each path of the tree is run once. The weight of a path is the product of the
    chances of the outcomes that it took, and the weights add up to 1.

    More than `limit` paths: `TooManyPaths`, before the run that would pass the limit."""
    found, pending = [], [()]
    while pending:
        if len(found) + len(pending) > limit:
            raise TooManyPaths(f'the outcomes of the events have more than {limit} paths')
        places = pending.pop()
        firings, result = run(places)
        taken = tuple(place for _, place in firings)
        if taken[: len(places)] != places:
            raise ValueError(f'the run with the places {places} took the places {taken}')
        weight = 1.0
        for chances, place in firings:
            weight *= chances[place]
        found.append((weight, firings, result))
        for at in range(len(places), len(firings)):
            chances, place = firings[at]
            pending += [
                (*taken[:at], other) for other, chance in enumerate(chances) if other != place and chance > 0
            ]
    return found


def weighted(paths, tolerance=1e-9):
    """{mean, variance, paths, weight} of a value over the outcomes of chance events: `paths` has
    (weight, value) of every path, a weight being the product of the chances of the outcomes that
    the path took. The mean has no sampling error: every path is there. The weights add up to 1,
    else a path is missing or is there twice, and that is an error."""
    weights = np.array([weight for weight, _ in paths], dtype=float)
    values = np.array([value for _, value in paths], dtype=float)
    total = float(weights.sum())
    if not len(paths) or abs(total - 1.0) > tolerance or np.any(weights < 0):
        raise ValueError(f'the weights of the paths add up to {total:g}, not 1')
    mean = float(weights @ values)
    return {
        'mean': mean,
        'variance': float(weights @ (values - mean) ** 2),
        'paths': len(paths),
        'weight': total,
    }
