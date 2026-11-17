"""Distributions of uncertain values: the families, the checks of their arguments, and the quantile
function that turns a uniform number into a value (docs/language.md, §2.3).

The arguments of a family are numbers in the unit of the value, except the dimensionless ones: the
geometric standard deviation `gsd`, the shape numbers `a` and `b` of a beta, and probabilities. Every
distribution has a bounded support, so a normal and a lognormal need `min` and `max`. A draw is the
family's quantile of a uniform number in the open interval (0, 1): the same uniform number gives the
same draw, and a larger one never gives a smaller draw.

Every function takes numbers or NumPy arrays, which broadcast: the arguments of a distribution that
reads other values differ from one sample to the next.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import special


@dataclass(frozen=True)
class Family:
    """A family of distributions: its parameters in their positional order, those that are plain
    numbers, those that can be left out, and the type of the values that it gives."""

    name: str
    parameters: tuple
    dimensionless: frozenset = frozenset()
    kind: str = 'number'  # 'number', 'bool' (bernoulli) or 'names' (categorical)


FAMILIES = {
    'uniform': Family('uniform', ('min', 'max')),
    'triangular': Family('triangular', ('min', 'mode', 'max')),
    'pert': Family('pert', ('min', 'mode', 'max')),
    'loguniform': Family('loguniform', ('min', 'max')),
    'normal': Family('normal', ('mean', 'sd', 'min', 'max')),
    'lognormal': Family('lognormal', ('median', 'gsd', 'min', 'max'), frozenset({'gsd'})),
    'beta': Family('beta', ('a', 'b'), frozenset({'a', 'b'})),
    'bernoulli': Family('bernoulli', ('p',), frozenset({'p'}), 'bool'),
    # The parameters of a categorical are the names of its values, each with its probability.
    'categorical': Family('categorical', (), frozenset(), 'names'),
}
# The weight of the mode of a PERT distribution (beta-PERT).
PERT_WEIGHT = 4
# The probabilities of a categorical add up to 1 within this.
TOTAL_TOLERANCE = 1e-9


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def problems(family, args):
    """The problems of the arguments of one distribution, as texts: empty when they are valid.
    `args` are numbers, by parameter name (for a categorical, by value name)."""
    if family == 'categorical':
        if not args:
            return ['a categorical names one or more values, each with its probability']
        found = [
            f'the probability of {name} is a number from 0 to 1'
            for name, p in args.items()
            if not _finite(p) or not 0 <= p <= 1
        ]
        if not found and abs(sum(args.values()) - 1) > TOTAL_TOLERANCE:
            found.append(f'the probabilities add up to {sum(args.values())!r}, not 1')
        return found
    bad = [name for name, value in args.items() if not _finite(value)]
    if bad:
        return [f'{name} is a finite number' for name in bad]
    a = args
    if family == 'uniform':
        return [] if a['min'] < a['max'] else ['min is below max']
    if family in ('triangular', 'pert'):
        return (
            []
            if a['min'] <= a['mode'] <= a['max'] and a['min'] < a['max']
            else ['min <= mode <= max, and min is below max']
        )
    if family == 'loguniform':
        return [] if 0 < a['min'] < a['max'] else ['0 < min < max']
    if family == 'normal':
        found = [] if a['sd'] > 0 else ['sd is above 0']
        found += [] if a['min'] < a['max'] else ['min is below max']
        if not found and _mass((a['min'] - a['mean']) / a['sd'], (a['max'] - a['mean']) / a['sd']) <= 0:
            found.append('the bounds hold no probability')
        return found
    if family == 'lognormal':
        found = [] if a['median'] > 0 else ['median is above 0']
        found += [] if a['gsd'] > 1 else ['gsd is above 1']
        found += [] if 0 < a['min'] < a['max'] else ['0 < min < max']
        if not found:
            alpha, beta = _log_bounds(a)
            if _mass(alpha, beta) <= 0:
                found.append('the bounds hold no probability')
        return found
    if family == 'beta':
        return [] if a['a'] > 0 and a['b'] > 0 else ['a and b are above 0']
    if family == 'bernoulli':
        return [] if 0 <= a['p'] <= 1 else ['p is a number from 0 to 1']
    raise ValueError(f'unknown family {family!r}')


def support(family, args):
    """(lowest, highest) value of a distribution of numbers."""
    if family == 'beta':
        return 0.0, 1.0
    return args['min'], args['max']


def _mass(alpha, beta):
    """The probability of a standard normal between alpha and beta, from the tail that is smaller."""
    return np.where(
        alpha > 0, special.ndtr(-alpha) - special.ndtr(-beta), special.ndtr(beta) - special.ndtr(alpha)
    )


def _log_bounds(a):
    scale = np.log(a['gsd'])
    centre = np.log(a['median'])
    return (np.log(a['min']) - centre) / scale, (np.log(a['max']) - centre) / scale


def _standard_normal(alpha, beta, u):
    """The u-quantile of a standard normal truncated to [alpha, beta]. Each quantile comes from the
    tail that holds less probability, so that a bound far in the upper tail keeps its precision."""
    lower_alpha, lower_beta = special.ndtr(alpha), special.ndtr(beta)
    upper_alpha, upper_beta = special.ndtr(-alpha), special.ndtr(-beta)
    # 1 - u is exact for u from 1/2 to 1, so the upper form has no cancellation near u = 1.
    lower = lower_alpha + u * (lower_beta - lower_alpha)
    upper = upper_beta + (1 - u) * (upper_alpha - upper_beta)
    with np.errstate(invalid='ignore', divide='ignore'):
        z = np.where(lower < 0.5, special.ndtri(lower), -special.ndtri(upper))
    return np.clip(z, alpha, beta)


def quantile(family, args, u):
    """The u-quantile of a distribution, for u in (0, 1): a number (a float array), a bool (bernoulli)
    or the index of a value in the order of `args` (categorical)."""
    u = np.asarray(u, dtype=float)
    a = {name: np.asarray(value, dtype=float) for name, value in args.items()}
    if family == 'uniform':
        return np.clip(a['min'] + u * (a['max'] - a['min']), a['min'], a['max'])
    if family == 'triangular':
        low, mode, high = a['min'], a['mode'], a['max']
        width = high - low
        split = (mode - low) / width
        left = low + np.sqrt(u * width * (mode - low))
        right = high - np.sqrt((1 - u) * width * (high - mode))
        return np.clip(np.where(u < split, left, right), low, high)
    if family == 'pert':
        low, mode, high = a['min'], a['mode'], a['max']
        width = high - low
        alpha = 1 + PERT_WEIGHT * (mode - low) / width
        beta = 1 + PERT_WEIGHT * (high - mode) / width
        return np.clip(low + width * special.betaincinv(alpha, beta, u), low, high)
    if family == 'loguniform':
        low, high = np.log(a['min']), np.log(a['max'])
        return np.clip(np.exp(low + u * (high - low)), a['min'], a['max'])
    if family == 'normal':
        alpha, beta = (a['min'] - a['mean']) / a['sd'], (a['max'] - a['mean']) / a['sd']
        return np.clip(a['mean'] + a['sd'] * _standard_normal(alpha, beta, u), a['min'], a['max'])
    if family == 'lognormal':
        alpha, beta = _log_bounds(a)
        z = _standard_normal(alpha, beta, u)
        return np.clip(np.exp(np.log(a['median']) + np.log(a['gsd']) * z), a['min'], a['max'])
    if family == 'beta':
        return special.betaincinv(a['a'], a['b'], u)
    if family == 'bernoulli':
        # F(false) = 1 - p, so the quantile is true where u is above 1 - p.
        return u > 1 - a['p']
    if family == 'categorical':
        names = list(a)
        cumulative = np.cumsum([a[name] for name in names], axis=0)
        cumulative = cumulative / cumulative[-1]
        index = np.zeros(np.broadcast(u, cumulative[0]).shape, dtype=int)
        for edge in cumulative[:-1]:
            index = index + (u > edge)
        return index
    raise ValueError(f'unknown family {family!r}')


def central(family, args):
    """The value of a distribution in the central run: the median of a distribution of numbers, and
    the most likely value of a bool or a name (on a tie, false, or the first name)."""
    if family == 'bernoulli':
        return bool(args['p'] > 0.5)
    if family == 'categorical':
        names = list(args)
        return max(range(len(names)), key=lambda i: (args[names[i]], -i))
    return float(quantile(family, args, 0.5))
