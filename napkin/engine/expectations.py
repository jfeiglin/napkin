"""The plain estimators of a Monte Carlo study: what the samples of one value at one time say of its
distribution, each with the interval that belongs to it (docs/engine.md, "Estimators").

Each sample is a run under a seed of its own (`sampling.py`), so the samples of one value are
independent draws of its distribution under the model's assumptions, and the plain estimators hold:

- `mean`: the mean, with Student's interval (`estimators.mean_interval`), which has its confidence
  when the mean of the samples is close to normal;
- `quantile`: the type-7 percentile (Hyndman and Fan, numpy's `linear`), with the interval between
  two of the sorted samples (`estimators.quantile_interval`), which holds for every continuous
  distribution with at least its confidence, or none when the samples are too few;
- `exceedance`: the share of the samples above a value, P(X > v) = count / n, with the
  Clopper-Pearson interval of a binomial share, which has at least its confidence;
- `summary`: what a study says of one value at one time (`Summary`);
- `spearman`: the rank correlation of two samples, with tied values at their mean rank.

No function here runs a model: `uncertainty.py` gives them the values of its samples. The spread of
the samples is the spread of the inputs that the scenario assumes, carried through the model; it is
not a measured interval.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import estimators

# The percentiles of a summary.
PERCENTILES = (5, 25, 50, 75, 95)


@dataclass(frozen=True)
class Estimate:
    """An estimate from n samples, with its interval (`low`, `high`) at its confidence; no interval
    (None, None) from one sample, or for a quantile from too few."""

    value: float
    low: float | None
    high: float | None
    confidence: float
    n: int


@dataclass(frozen=True)
class Summary:
    """What the samples say of one value at one time: the value of the central run, the mean with its
    interval, the standard deviation and the standard error of the mean (None from one sample), the
    least and the greatest value, and each percentile of `PERCENTILES` as (p, value). A value that is
    not a number in every sample has no summary (`estimated` false, every number None), and `reason`
    says why."""

    estimated: bool
    central: object = None
    mean: Estimate | None = None
    sd: float | None = None
    sem: float | None = None
    least: float | None = None
    greatest: float | None = None
    percentiles: tuple[tuple[int, float], ...] = ()
    reason: str | None = None


def _numbers(values):
    """The values as floats: a yes/no is 1 or 0."""
    return np.asarray([float(value) for value in values], dtype=float)


def mean(values, confidence=0.95):
    """The mean of the samples, with Student's interval (`Estimate`)."""
    x = _numbers(values)
    if len(x) == 1:
        return Estimate(float(x[0]), None, None, confidence, 1)
    found = estimators.mean_interval(x, confidence)
    return Estimate(found['mean'], found['low'], found['high'], confidence, len(x))


def quantile(values, p, confidence=0.95):
    """The quantile `p` (0 < p < 1) of the samples, type 7, with the interval of two order statistics
    (`Estimate`; no interval when the samples are too few for the confidence)."""
    x = _numbers(values)
    found = estimators.quantile_interval(x, p, confidence)
    value = float(np.percentile(x, 100 * p, method='linear'))
    if found is None:
        return Estimate(value, None, None, confidence, len(x))
    return Estimate(value, found['low'], found['high'], confidence, len(x))


def exceedance(values, threshold, confidence=0.95):
    """The share of the samples above `threshold`, with its Clopper-Pearson interval (`Estimate`): the
    bounds of the share p at which k of n samples above the value, or more (for the low bound) and k or
    fewer (for the high bound), would be as likely as the half of the error, 0 and 1 at the ends."""
    from scipy.stats import beta

    x = _numbers(values)
    n, k = len(x), int(np.count_nonzero(x > threshold))
    alpha = 1 - confidence
    low = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    high = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return Estimate(k / n, low, high, confidence, n)


def summary(values, central, confidence=0.95):
    """The summary of one value over the samples (`Summary`). A yes/no counts as 1 or 0, so its mean is
    the share of the samples in which it holds; a text, or a value that one sample could not give
    (`Unavailable`), leaves the value without a summary."""
    for value in (central, *values):
        if isinstance(value, str):
            return Summary(False, central, reason='a text has no mean')
        if not isinstance(value, (bool, int, float)):
            return Summary(False, central, reason=getattr(value, 'reason', f'{value!r} is no number'))
    x = _numbers(values)
    sd = float(x.std(ddof=1)) if len(x) > 1 else None
    return Summary(
        True,
        central,
        mean(x, confidence),
        sd,
        None if sd is None else sd / math.sqrt(len(x)),
        float(x.min()),
        float(x.max()),
        tuple(
            (p, float(value))
            for p, value in zip(PERCENTILES, np.percentile(x, PERCENTILES, method='linear'))
        ),
    )


def spearman(x, y):
    """The Spearman rank correlation of two samples of one length, with tied values at their mean rank;
    None when either has one value only."""
    from scipy.stats import rankdata

    x, y = rankdata(_numbers(x)), rankdata(_numbers(y))
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])
