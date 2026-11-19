"""The plain estimators of a Monte Carlo study (`napkin/engine/expectations.py`): a mean with Student's
interval, a quantile with the interval of two order statistics, a share above a value with its
Clopper-Pearson interval, the summary of one value over the samples, and a rank correlation.

The expected values are worked by hand or from the definitions: Student's 97.5% point with 3 degrees
of freedom is 3.182446305284263 (a table's value); an interval of order statistics covers the quantile
with the exact binomial chance of its ranks, summed here with fractions; and a Clopper-Pearson bound is
where the binomial tail beyond the count is half the error, 1 - (alpha / 2)^(1/n) for no sample above
the value.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from napkin.engine import expectations
from napkin.program.record import Unavailable

T_975_3 = 3.182446305284263


def binomial(n, k, p):
    return math.comb(n, k) * p**k * (1 - p) ** (n - k)


def test_the_mean_of_independent_samples_has_students_interval():
    """1, 2, 3, 4: the mean is 2.5, the standard error sqrt(5/3) / 2."""
    found = expectations.mean([1, 2, 3, 4], 0.95)
    half = T_975_3 * math.sqrt(5 / 12)
    assert (found.value, found.n, found.confidence) == (2.5, 4, 0.95)
    assert (found.low, found.high) == pytest.approx((2.5 - half, 2.5 + half), rel=1e-12)
    one = expectations.mean([7.0])
    assert (one.value, one.low, one.high, one.n) == (7.0, None, None, 1)


def test_a_quantile_is_the_type_7_percentile_with_two_order_statistics_that_cover_it():
    """Of 1 to 10, the median is 5.5. Its interval is two of the values, whose ranks l < u cover the
    median with the chance that from l to u - 1 samples fall below it, at least 90%."""
    values = [float(v) for v in (7, 1, 10, 4, 2, 9, 3, 8, 6, 5)]
    found = expectations.quantile(values, 0.5, 0.9)
    assert found.value == 5.5 and found.n == 10
    low, high = int(found.low), int(found.high)
    assert found.low == low and found.high == high and 1 <= low < high <= 10
    coverage = sum(binomial(10, k, Fraction(1, 2)) for k in range(low, high))
    assert coverage >= Fraction(9, 10)
    # The 25th percentile of 1 to 10: rank 1 + 9 / 4 = 3.25, so 3.25.
    assert expectations.quantile(values, 0.25).value == pytest.approx(3.25)
    # Three samples cover a median with 1 - 2 / 8 = 75% at most: no interval at 99%.
    few = expectations.quantile([1.0, 2.0, 3.0], 0.5, 0.99)
    assert (few.value, few.low, few.high) == (2.0, None, None)


def test_a_share_above_a_value_has_its_clopper_pearson_interval():
    alpha = 0.05
    none = expectations.exceedance([1.0] * 10, 2.0, 0.95)
    assert (none.value, none.low) == (0.0, 0.0)
    assert none.high == pytest.approx(1 - (alpha / 2) ** (1 / 10), rel=1e-12)
    every = expectations.exceedance([3.0] * 10, 2.0, 0.95)
    assert (every.value, every.high) == (1.0, 1.0)
    assert every.low == pytest.approx((alpha / 2) ** (1 / 10), rel=1e-12)
    # Three of ten above 2: at the low bound, three or more above has half the error; at the high
    # bound, three or fewer.
    some = expectations.exceedance([1, 2, 3, 4, 5, 0, 0, 0, 0, 2], 2.0, 0.95)
    assert some.value == 0.3 and some.n == 10
    assert sum(binomial(10, k, some.low) for k in range(3, 11)) == pytest.approx(alpha / 2, rel=1e-9)
    assert sum(binomial(10, k, some.high) for k in range(4)) == pytest.approx(alpha / 2, rel=1e-9)


def test_a_summary_has_the_mean_the_spread_the_extremes_and_the_percentiles():
    found = expectations.summary([4.0, 1.0, 3.0, 2.0], central=2.5)
    assert found.estimated and found.central == 2.5 and found.reason is None
    assert found.mean.value == 2.5 and found.sd == pytest.approx(math.sqrt(5 / 3), rel=1e-12)
    assert found.sem == pytest.approx(math.sqrt(5 / 3) / 2, rel=1e-12)
    assert (found.least, found.greatest) == (1.0, 4.0)
    # Type 7 of 1, 2, 3, 4: rank 1 + 3 p / 100.
    assert [p for p, _ in found.percentiles] == [5, 25, 50, 75, 95]
    assert [value for _, value in found.percentiles] == pytest.approx([1.15, 1.75, 2.5, 3.25, 3.85])
    one = expectations.summary([3.0], central=3.0)
    assert one.estimated and (one.sd, one.sem, one.mean.low) == (None, None, None)


def test_a_yes_or_no_counts_as_one_or_zero_and_a_text_or_an_unavailable_value_has_no_summary():
    shares = expectations.summary([True, False, True, True], central=True)
    assert shares.estimated and shares.mean.value == 0.75 and (shares.least, shares.greatest) == (0, 1)
    text = expectations.summary(['HIGH', 'LOW'], central='LOW')
    assert not text.estimated and text.reason == 'a text has no mean' and text.mean is None
    missing = expectations.summary([1.0, Unavailable('the pump has not started')], central=1.0)
    assert not missing.estimated and missing.reason == 'the pump has not started'
    central = expectations.summary([1.0, 2.0], central=Unavailable('no reading at 0 h'))
    assert not central.estimated and central.reason == 'no reading at 0 h'


def test_a_rank_correlation_takes_tied_values_at_their_mean_rank():
    """x = 1, 2, 2, 3 has the ranks 1, 2.5, 2.5, 4: with the ranks of y = 1 to 4, the correlation is
    4.5 / sqrt(4.5 * 5)."""
    assert expectations.spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(
        4.5 / math.sqrt(22.5), rel=1e-12
    )
    assert expectations.spearman([1, 2, 3], [9, 5, 1]) == pytest.approx(-1)
    assert expectations.spearman([2, 2, 2], [1, 2, 3]) is None
