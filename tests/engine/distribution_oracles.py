"""Independent mathematics of the distribution families, in mpmath: the cdf and survival function of
each family from its definition, the closed-form quantiles where they exist, the mean and variance
from closed forms, and the probability bounds that keep a seeded statistical test from failing by
chance. Nothing here imports the production code (CONTRIBUTING.md, "Testing")."""

from __future__ import annotations

import math

import mpmath as mp

DIGITS = 40
# The weight of the mode in beta-PERT, as the literature defines it (Vose, Risk Analysis, 2008).
PERT_WEIGHT = 4


def _mpf(args):
    return {name: mp.mpf(value) for name, value in args.items()}


def _pert_shape(low, mode, high):
    width = high - low
    return 1 + PERT_WEIGHT * (mode - low) / width, 1 + PERT_WEIGHT * (high - mode) / width


def _log_bounds(a):
    mu, sigma = mp.log(a['median']), mp.log(a['gsd'])
    return mu, sigma, (mp.log(a['min']) - mu) / sigma, (mp.log(a['max']) - mu) / sigma


def tails(family, args, x):
    """(F(x), 1 - F(x)) of one family at x, each computed directly, so that both tails keep their
    precision."""
    with mp.workdps(DIGITS):
        x = mp.mpf(x)
        a = _mpf(args)
        if family == 'uniform':
            f = (x - a['min']) / (a['max'] - a['min'])
            return f, 1 - f
        if family == 'triangular':
            low, c, high = a['min'], a['mode'], a['max']
            if x <= c:
                f = (x - low) ** 2 / ((high - low) * (c - low)) if c > low else mp.mpf(0)
                return f, 1 - f
            s = (high - x) ** 2 / ((high - low) * (high - c))
            return 1 - s, s
        if family in ('pert', 'beta'):
            if family == 'pert':
                alpha, beta = _pert_shape(a['min'], a['mode'], a['max'])
                z = (x - a['min']) / (a['max'] - a['min'])
            else:
                alpha, beta, z = a['a'], a['b'], x
            f = mp.betainc(alpha, beta, 0, z, regularized=True)
            s = mp.betainc(alpha, beta, z, 1, regularized=True)
            return f, s
        if family == 'loguniform':
            f = mp.log(x / a['min']) / mp.log(a['max'] / a['min'])
            return f, mp.log(a['max'] / x) / mp.log(a['max'] / a['min'])
        if family in ('normal', 'lognormal'):
            if family == 'normal':
                z = (x - a['mean']) / a['sd']
                alpha, beta = (a['min'] - a['mean']) / a['sd'], (a['max'] - a['mean']) / a['sd']
            else:
                mu, sigma, alpha, beta = _log_bounds(a)
                z = (mp.log(x) - mu) / sigma
            mass = mp.ncdf(beta) - mp.ncdf(alpha)
            return (mp.ncdf(z) - mp.ncdf(alpha)) / mass, (mp.ncdf(beta) - mp.ncdf(z)) / mass
    raise ValueError(family)


def quantile(family, args, u):
    """The closed-form u-quantile of the families that have one."""
    with mp.workdps(DIGITS):
        u = mp.mpf(u)
        a = _mpf(args)
        if family == 'uniform':
            return a['min'] + u * (a['max'] - a['min'])
        if family == 'loguniform':
            return a['min'] * (a['max'] / a['min']) ** u
        if family == 'triangular':
            low, c, high = a['min'], a['mode'], a['max']
            if u < (c - low) / (high - low):
                return low + mp.sqrt(u * (high - low) * (c - low))
            return high - mp.sqrt((1 - u) * (high - low) * (high - c))
    raise ValueError(f'{family} has no closed-form quantile here')


def moments(family, args):
    """(mean, variance) of one family, from its closed forms."""
    with mp.workdps(DIGITS):
        a = _mpf(args)
        if family == 'uniform':
            return (a['min'] + a['max']) / 2, (a['max'] - a['min']) ** 2 / 12
        if family == 'triangular':
            low, c, high = a['min'], a['mode'], a['max']
            return (low + c + high) / 3, (low**2 + c**2 + high**2 - low * c - low * high - c * high) / 18
        if family in ('pert', 'beta'):
            if family == 'pert':
                low, high = a['min'], a['max']
                alpha, beta = _pert_shape(low, a['mode'], high)
            else:
                low, high, alpha, beta = mp.mpf(0), mp.mpf(1), a['a'], a['b']
            s = alpha + beta
            return low + (high - low) * alpha / s, (high - low) ** 2 * alpha * beta / (s**2 * (s + 1))
        if family == 'loguniform':
            low, high = a['min'], a['max']
            span = mp.log(high / low)
            mean = (high - low) / span
            return mean, (high**2 - low**2) / (2 * span) - mean**2
        if family == 'normal':
            alpha, beta = (a['min'] - a['mean']) / a['sd'], (a['max'] - a['mean']) / a['sd']
            z = mp.ncdf(beta) - mp.ncdf(alpha)
            shift = (mp.npdf(alpha) - mp.npdf(beta)) / z
            spread = 1 + (alpha * mp.npdf(alpha) - beta * mp.npdf(beta)) / z - shift**2
            return a['mean'] + a['sd'] * shift, a['sd'] ** 2 * spread
        if family == 'lognormal':
            mu, sigma, alpha, beta = _log_bounds(a)
            z = mp.ncdf(beta) - mp.ncdf(alpha)

            def raw(k):
                part = mp.ncdf(beta - k * sigma) - mp.ncdf(alpha - k * sigma)
                return mp.exp(k * mu + k**2 * sigma**2 / 2) * part / z

            return raw(1), raw(2) - raw(1) ** 2
    raise ValueError(family)


def dkw_epsilon(n, failure=1e-9):
    """The Dvoretzky-Kiefer-Wolfowitz bound with Massart's constant: the empirical cdf of n draws
    is farther than eps from the true cdf, anywhere, with probability at most 2 exp(-2 n eps^2)."""
    return math.sqrt(math.log(2 / failure) / (2 * n))


def hoeffding_epsilon(n, failure=1e-9):
    """Hoeffding's bound: the mean of n independent draws in [0, 1] is farther than eps from its
    expectation with probability at most 2 exp(-2 n eps^2)."""
    return math.sqrt(math.log(2 / failure) / (2 * n))
