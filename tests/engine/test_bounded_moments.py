"""The mean and the standard deviation of every bounded distribution keep their precision across the
tails and for narrow ranges (re-audit 13, `briefs/audit2.md` part B).

`normal(0, 1, 9, 10)` drew 9.07578 in a median run, but its mean and standard deviation divided by
zero: its mass was a difference of two masses that round to 1. The rule: for random distributions of
each bounded family, far into either tail and over ranges from a millionth of a sigma to the whole
line, `chance.described` agrees to 1e-10 with the textbook closed form of the family evaluated by
mpmath at 50 digits, where a cancellation costs nothing and a mass is taken from the tail that holds
it. The engine computes them otherwise (quadrature in the tail, sums of squares of differences), so
the two share no step.
"""

from __future__ import annotations

import math
import random
from types import SimpleNamespace

import mpmath
import pytest

from napkin.engine.timeline import read, run
from napkin.engine.timeline.chance import described
from napkin.program.build import Builder, after, assign, dist_of, event, normal, q, start, this, value
from napkin.program.config import Configuration, Request
from tests.engine.test_checkpoints import UNITS

TOLERANCE = 1e-10
DIGITS = 50


class _Units:
    """Every unit of a distribution here is canonical."""

    def scale(self, unit):
        return 1.0


def moments(family, *params):
    """(mean, standard deviation) as the engine reads them."""
    distribution = SimpleNamespace(family=family, unit='', params=params)
    return described(distribution, _Units(), 'mean'), described(distribution, _Units(), 'std')


def close(found, expected):
    mean, std = found
    want_mean, want_std = (float(x) for x in expected)
    assert mean == pytest.approx(want_mean, rel=TOLERANCE, abs=TOLERANCE * want_std)
    assert std == pytest.approx(want_std, rel=TOLERANCE)


def mass(alpha, beta):
    """P(alpha <= N <= beta) for a standard normal N, from the tail that holds the interval."""
    if alpha >= 0:
        return mpmath.ncdf(-alpha) - mpmath.ncdf(-beta)
    return mpmath.ncdf(beta) - mpmath.ncdf(alpha)


def normal_moments(alpha, beta):
    """The mean and the standard deviation of a standard normal truncated to [alpha, beta]:
    (phi(a) - phi(b)) / Z and 1 + (a phi(a) - b phi(b)) / Z - mean^2."""
    with mpmath.workdps(DIGITS):
        a, b = mpmath.mpf(alpha), mpmath.mpf(beta)
        z = mass(a, b)
        phi = [mpmath.npdf(x) if mpmath.isfinite(x) else 0 for x in (a, b)]
        moment = [x * p if mpmath.isfinite(x) else 0 for x, p in zip((a, b), phi)]
        mean = (phi[0] - phi[1]) / z
        return mean, mpmath.sqrt(1 + (moment[0] - moment[1]) / z - mean * mean)


def lognormal_moments(mu, sigma, low, high):
    """E[X] and its standard deviation for X = e^(mu + sigma N), N truncated to the logarithms of
    [low, high]: E[X^k] = e^(k mu + k^2 sigma^2 / 2) P(N in [alpha - k sigma, beta - k sigma]) / Z."""
    with mpmath.workdps(DIGITS):
        m, s = mpmath.mpf(mu), mpmath.mpf(sigma)
        alpha = (mpmath.log(low) - m) / s if low > 0 else -mpmath.inf
        beta = (mpmath.log(high) - m) / s if high < math.inf else mpmath.inf
        z = mass(alpha, beta)
        raw = [mpmath.exp(k * m + k * k * s * s / 2) * mass(alpha - k * s, beta - k * s) / z for k in (1, 2)]
        return raw[0], mpmath.sqrt(raw[1] - raw[0] ** 2)


def _interval(rng):
    """A random interval in standard units: far in a tail, around zero, narrow or wide, or with an
    infinite end."""
    start = rng.choice([rng.uniform(-60, 60), rng.uniform(-3, 3), rng.choice([-math.inf, math.inf])])
    if start == math.inf:
        return -math.inf, rng.uniform(-60, 60)
    if start == -math.inf:
        return rng.uniform(-60, 60), math.inf
    return start, start + 10 ** rng.uniform(-6, 2)


@pytest.mark.parametrize('seed', range(60))
def test_a_truncated_normal_has_the_moments_of_its_closed_form(seed):
    rng = random.Random(seed)
    low, high = _interval(rng)
    mu, sd = rng.uniform(-100, 100), 10 ** rng.uniform(-2, 2)
    mean, std = normal_moments(low, high)
    close(moments('normal', mu, sd, mu + sd * low, mu + sd * high), (mu + sd * mean, sd * std))


@pytest.mark.parametrize('seed', range(60))
def test_a_truncated_lognormal_has_the_moments_of_its_closed_form(seed):
    rng = random.Random(1000 + seed)
    low, high = _interval(rng)
    low, high = max(low, -40), min(high, 40)  # the logarithm's interval, in its sigmas
    median, gsd = 10 ** rng.uniform(-2, 2), math.exp(10 ** rng.uniform(-2, 0.3))
    mu, sigma = math.log(median), math.log(gsd)
    a = math.exp(mu + sigma * low) if low > -40 else 0.0
    b = math.exp(mu + sigma * high) if high < 40 else math.inf
    close(moments('lognormal', median, gsd, a, b), lognormal_moments(mu, sigma, a, b))


@pytest.mark.parametrize('seed', range(30))
def test_the_closed_forms_keep_their_precision_for_a_narrow_range_far_from_zero(seed):
    """uniform, triangular, pert and loguniform over a range of width 1e-9 to 1e3 of its distance from
    zero, at up to 1e6 from it; beta over its parameters."""
    rng = random.Random(2000 + seed)
    low = 10 ** rng.uniform(-3, 6)
    high = low + low * 10 ** rng.uniform(-9, 1)
    mode = low + (high - low) * rng.random()
    p, r = 10 ** rng.uniform(-1, 2), 10 ** rng.uniform(-1, 2)
    with mpmath.workdps(DIGITS):
        lo, mo, hi = (mpmath.mpf(x) for x in (low, mode, high))
        close(moments('uniform', low, high), ((lo + hi) / 2, (hi - lo) / mpmath.sqrt(12)))
        spread = (lo * lo + mo * mo + hi * hi - lo * mo - lo * hi - mo * hi) / 18
        close(moments('triangular', low, mode, high), ((lo + mo + hi) / 3, mpmath.sqrt(spread)))
        a, b = 1 + 4 * (mo - lo) / (hi - lo), 1 + 4 * (hi - mo) / (hi - lo)
        spread = (hi - lo) ** 2 * a * b / ((a + b) ** 2 * (a + b + 1))
        close(moments('pert', low, mode, high), (lo + (hi - lo) * a / (a + b), mpmath.sqrt(spread)))
        span = mpmath.log(hi / lo)
        mean = (hi - lo) / span
        close(
            moments('loguniform', low, high), (mean, mpmath.sqrt((hi * hi - lo * lo) / (2 * span) - mean**2))
        )
        a, b = mpmath.mpf(p), mpmath.mpf(r)
        close(moments('beta', p, r), (a / (a + b), mpmath.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))))


def test_the_mean_and_spread_of_a_normal_far_in_its_tail_are_read_in_a_run():
    """Re-audit 13: normal(0, 1, 9, 10) draws its median in a median run, and a stage reads its mean
    and its standard deviation, 9.108456288012409 and 0.10699909262062107 by the closed form."""
    b = Builder(UNITS)
    crew = b.entity(
        'crew',
        value('time_of', dist_of('h'), normal(0, 1, 'h', 9, 10)),
        value('mean', 'h', 0),
        value('spread', 'h', 0),
        event(
            'look',
            after(q(1, 'h'), assign(this.mean, this.time_of.mean), assign(this.spread, this.time_of.std)),
        ),
    )
    b.setup(start(crew.look))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    found = read(record, program, ['crew.mean', 'crew.spread'], [2])
    close([reading.values[0] for reading in found], normal_moments(9, 10))
