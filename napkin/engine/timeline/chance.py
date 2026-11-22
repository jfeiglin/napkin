"""Chance in a run: the value of each executed draw.

- **A draw** (`plan.Drawn`) is executed where its expression is evaluated: at the start of the run
  for a value of a member or of the root, at the entry of an occurrence, in a stage or the setup,
  when a step captures its delay, and at a firing of a trigger. Only an executed draw draws: a stage
  reads the names of an expression as its evaluation asks for them (`run.Run.truth`), so a draw in
  a branch of `a if c else b` that is not taken draws nothing, and neither does a statement that a
  branch or a guard skips. In a median run a numeric draw is the median of its distribution, and a
  categorical one the most likely of its eligible outcomes, the first declared of them on a tie. In
  a sampled run it is the quantile of a uniform number keyed by the seed, the draw's site and its
  owner: the member, the occurrence, or the firing of a trigger that executes it (`owner`; the n-th
  firing of `tank.refill.when[0]`, from 1, is `tank.refill.when[0]!n`), never its place in a stream
  (R-A2-17). So an unexecuted branch, an extra read, a report or the step size of an integrator moves
  no draw. The number is the first 64 bits of the SHA-256 of `seed|site|owner` (`uniform`), as the
  oracle draws it. Each executed draw is an entry of the trace, with its value.
- **A distribution that a stage replaced** gives the draws after the replacement, the stage's own
  included: a stage sees its own writes, so a draw, a `switch` on a draw, and a mean or a standard
  deviation read in it take the new distribution at once (`distribution`).
- **Eligibility** (D1): a `switch` whose selector is a draw reads its case guards first
  (`moment.Moment.select`); an outcome that a false guard bars is not eligible, and the draw is made
  among the others, their weights scaled to sum to one. With none eligible, the `else` body runs and
  nothing is drawn. Elsewhere every outcome is eligible. Eligible outcomes whose weights are all zero
  have no draw, and the run fails.
- **A stage that runs again** from its start after a breakpoint stopped it (`checkpoints.py`) makes
  its draws again with the same keys, so they are the same; those that it made before the stop are
  in the trace (`kept`), and are not traced twice.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from ...distributions import FAMILIES, PERT_WEIGHT, quantile
from ...program.config import MEDIAN
from ..errors import SimulationError


def uniform(seed, key):
    """The uniform number of a draw, in (0, 1): (2k + 1) / 2^65 for k the first 64 bits of the SHA-256
    of `seed|key`. Python divides two whole numbers to the nearest float."""
    digest = hashlib.sha256(f'{seed}|{key}'.encode()).digest()
    return (int.from_bytes(digest[:8], 'big') * 2 + 1) / 2**65


def numeric(distribution, units, u):
    """The u-quantile of a numeric distribution (`refs.Distribution`), in canonical units."""
    family = FAMILIES[distribution.family]
    scale = units.scale(distribution.unit) if distribution.unit else 1.0
    args = {
        name: float(value) * (1.0 if name in family.dimensionless else scale)
        for name, value in zip(family.parameters, distribution.params)
    }
    if 'min' in family.parameters and 'min' not in args:
        # The unbounded forms of `normal` and `lognormal`.
        args.update(min=0.0 if family.name == 'lognormal' else -math.inf, max=math.inf)
    with np.errstate(divide='ignore'):
        return float(quantile(family.name, args, u))


# Gauss-Legendre points and weights on [-1, 1], for the moments of a normal truncated to an
# interval (`_tail`).
_POINTS, _WEIGHTS = np.polynomial.legendre.leggauss(64)
# How far into a tail its density counts: past the point where it has fallen by e^-50 from where the
# interval starts, what is left changes no moment by a part in 1e20.
_DEPTH = 50.0
_HALF_LOG_TAU = 0.5 * math.log(2.0 * math.pi)


def _tail(alpha, width):
    """The density of a standard normal on [alpha, alpha + width], alpha >= 0, as quadrature: points
    y from alpha, and the weights of the density at alpha + y relative to its value at alpha,
    e^(-alpha y - y^2/2). The points end where that has fallen by e^-50 (`_DEPTH`), or at the end of
    the interval, so the density falls by the same factor over them however far out the tail lies:
    nothing underflows, and no mass is a difference of two masses near 1."""
    reach = 2.0 * _DEPTH / (alpha + math.sqrt(alpha * alpha + 2.0 * _DEPTH))
    end = min(width, reach)
    y = 0.5 * end * (_POINTS + 1.0)
    return y, 0.5 * end * _WEIGHTS * np.exp(-alpha * y - 0.5 * y * y)


def _points(alpha, beta, width):
    """A standard normal truncated to [alpha, beta] (of width `width`) as quadrature, from the tail
    that holds it (`_tail`): (base, offsets, weights) of points base + offsets, the weights relative to
    the density at the base. An interval below zero is the mirror of one above it, and one around
    zero is a tail on each side of it."""
    if beta <= 0:
        base, offsets, weights = _points(-beta, -alpha, width)
        return -base, -offsets, weights
    if alpha >= 0:
        return (alpha, *_tail(alpha, width))
    (right, upper), (left, lower) = _tail(0.0, beta), _tail(0.0, -alpha)
    return 0.0, np.concatenate([right, -left]), np.concatenate([upper, lower])


def truncated(alpha, beta, width=None):
    """The mean and the standard deviation of a standard normal truncated to [alpha, beta] (alpha <
    beta, either may be infinite; `width`, beta - alpha, when it is known more precisely than their
    difference), from its points (`_points`). The spread is taken about the mean of the offsets, so
    it has no cancellation."""
    base, offsets, weights = _points(alpha, beta, beta - alpha if width is None else width)
    total = float(weights.sum())
    shift = float(weights @ offsets) / total
    return base + shift, math.sqrt(float(weights @ (offsets - shift) ** 2) / total)


def log_mass(alpha, beta, width=None):
    """The logarithm of the probability that a standard normal lies in [alpha, beta] (`_points`),
    with `width` as `truncated` takes it."""
    base, _, weights = _points(alpha, beta, beta - alpha if width is None else width)
    return -0.5 * base * base - _HALF_LOG_TAU + math.log(float(weights.sum()))


def _lognormal(mu, sigma, low, high):
    """The mean and the standard deviation of e^(mu + sigma N) for N a standard normal truncated to
    the logarithms of [low, high] (either may be 0 or infinite). Where sigma times the span of the
    points of N is at most 1, both come from the points, the spread about their mean with `expm1`, so
    a narrow range keeps its precision. Elsewhere, from E[X^k] = e^(k mu + k^2 sigma^2 / 2) P(N in
    [alpha - k sigma, beta - k sigma]) / P(N in [alpha, beta]) (the normal of the logarithm tilted by
    k sigma is a normal shifted by it), whose ratio of the second to the square of the first is then
    far enough from 1 for its logarithm to give the spread (`expm1`)."""
    alpha = (math.log(low) - mu) / sigma if low > 0 else -math.inf
    beta = (math.log(high) - mu) / sigma if math.isfinite(high) else math.inf
    # The width in the logarithm, from the ratio of the bounds: one width for every interval below,
    # so that its roundoff cancels from the spread.
    width = math.log1p((high - low) / low) / sigma if low > 0 else math.inf
    base, offsets, weights = _points(alpha, beta, width)
    if sigma * float(offsets.max() - offsets.min()) <= 1.0:
        total = float(weights.sum())
        tilt = np.expm1(sigma * offsets)
        shift = float(weights @ tilt) / total
        level = math.exp(mu + sigma * base)
        return level * (1.0 + shift), level * math.sqrt(float(weights @ (tilt - shift) ** 2) / total)
    whole = log_mass(alpha, beta, width)
    first = log_mass(alpha - sigma, beta - sigma, width) - whole
    second = log_mass(alpha - 2 * sigma, beta - 2 * sigma, width) - whole
    mean = math.exp(mu + 0.5 * sigma * sigma + first)
    return mean, mean * math.sqrt(max(math.expm1(sigma * sigma + second - 2 * first), 0.0))


def _excess(h):
    """h cosh h - sinh h, from its series below 1 (h^3/3 + h^5/30 + ...), whose terms would cancel."""
    if abs(h) >= 1.0:
        return h * math.cosh(h) - math.sinh(h)
    term, total, k = h, 0.0, 1
    while True:
        term *= h * h / ((2 * k) * (2 * k + 1))  # h^(2k+1) / (2k+1)!
        part = 2 * k * term
        total += part
        if abs(part) <= 1e-17 * abs(total):
            return total
        k += 1


def described(distribution, units, which):
    """The mean or the standard deviation (`which`) of a numeric distribution, in canonical units,
    in a form that keeps its precision across the tails and for narrow ranges: no difference of two
    nearly equal numbers. A normal or a lognormal with bounds is truncated to them, as its draws are
    (`distributions.quantile`): a normal from the tail that holds it (`truncated`), a lognormal from
    the masses of its interval shifted by one and two of its sigmas (`log_mass`), its spread from
    their logarithms (`expm1`). A spread of the others is a sum of squares of differences or of
    products of positive numbers. Reading it draws nothing."""
    family = FAMILIES[distribution.family]
    scale = units.scale(distribution.unit) if distribution.unit else 1.0
    a = [
        float(value) * (1.0 if name in family.dimensionless else scale)
        for name, value in zip(family.parameters, distribution.params)
    ]
    name = distribution.family
    if name == 'uniform':
        low, high = a
        mean, std = 0.5 * (low + high), (high - low) / math.sqrt(12.0)
    elif name == 'triangular':
        low, mode, high = a
        mean = (low + mode + high) / 3
        std = math.sqrt(((high - low) ** 2 + (mode - low) ** 2 + (high - mode) ** 2) / 36)
    elif name == 'pert':
        low, mode, high = a
        alpha = 1 + PERT_WEIGHT * (mode - low) / (high - low)
        beta = 1 + PERT_WEIGHT * (high - mode) / (high - low)
        mean = low + (high - low) * alpha / (alpha + beta)
        std = (high - low) * math.sqrt(alpha * beta / ((alpha + beta) + 1)) / (alpha + beta)
    elif name == 'loguniform':
        low, high = a
        span = math.log1p((high - low) / low)  # log(high / low), exact for a narrow range
        mean = (high - low) / span
        # high^2 - low^2 over 2 span, less the mean squared: low^2 expm1(s) / s^2 2 e^(s/2) (h cosh h
        # - sinh h) for h = s/2, with no cancellation.
        half = 0.5 * span
        std = low * math.sqrt(math.expm1(span) / (span * span) * 2.0 * math.exp(half) * _excess(half))
    elif name == 'beta':
        p, q = a
        mean, std = p / (p + q), math.sqrt(p * q / (p + q + 1)) / (p + q)
    elif name == 'normal':
        mu, sd = a[:2]
        mean, std = mu, sd
        if len(a) == 4:
            low, high = a[2:]
            if not low < high:
                mean, std = low, 0.0
            else:
                middle, spread = truncated((low - mu) / sd, (high - mu) / sd, (high - low) / sd)
                mean, std = mu + sd * middle, sd * spread
    elif name == 'lognormal':
        mu, sigma = math.log(a[0]), math.log(a[1])
        if len(a) == 4 and not a[2] < a[3]:
            mean, std = a[2], 0.0
        elif len(a) == 4 and (a[2] > 0 or math.isfinite(a[3])):
            mean, std = _lognormal(mu, sigma, a[2], a[3])
        else:
            mean = math.exp(mu + 0.5 * sigma * sigma)
            std = mean * math.sqrt(math.expm1(sigma * sigma))
    else:
        raise SimulationError(f'a {name} distribution has no mean or standard deviation to read')
    return mean if which == 'mean' else std


def outcome(distribution, eligible, u, site=''):
    """The outcome of a categorical distribution among the eligible ones (None: all): with no uniform
    number (a median run) the most likely, the first declared of them on a tie; else the one whose
    share of (0, 1), in the declared order, holds u."""
    weights = [
        (member, float(weight))
        for member, weight in zip(distribution.outcomes, distribution.params)
        if eligible is None or member in eligible
    ]
    total = sum(weight for _, weight in weights)
    if not total > 0:
        names = ', '.join(member for member, _ in weights) or 'none'
        raise SimulationError(f'{site}: no eligible outcome has a weight to draw (eligible: {names})')
    if u is None:
        return max(weights, key=lambda pair: pair[1])[0]  # `max` keeps the first of equal weights
    if math.isinf(total):
        # Rescale by one binary exponent so the largest eligible weight is below one.
        exponent = math.frexp(max(weight for _, weight in weights))[1]
        weights = [(member, math.ldexp(weight, -exponent)) for member, weight in weights]
        total = sum(weight for _, weight in weights)
    reached = 0.0
    for member, weight in weights:
        reached += weight / total
        if u < reached:
            return member
    return next(member for member, weight in reversed(weights) if weight > 0)


def paused(record):
    """The `pause` entry that ends the record so far of a run that a breakpoint stopped, or None."""
    if record.trace and record.trace[-1].kind == 'pause':
        return record.trace[-1]
    return None


class Chance:
    """The draws of one run (see the module)."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan
        configuration = self.plan.configuration
        self.mode, self.seed = configuration.mode, configuration.seed
        self.firing = {}  # trigger key -> the number of its firing that runs now, from 1
        self.kept = set()  # (site, owner) of the draws of a stopped stage, which the trace holds
        self.made = []  # (site, owner, value) of the draws of the stage that runs

    def owner(self, owner):
        """Who executes a draw of an owner of the plan: a trigger's present firing."""
        n = self.firing.get(owner)
        return owner if n is None else f'{owner}!{n}'

    def distribution(self, source, tx=None):
        """The distribution of a draw: written in place, or the present distribution of a
        distribution-valued value, which a stage may have replaced: the stage that runs (`tx`) sees
        its own replacement, as it sees its other writes."""
        if not isinstance(source, str):
            return source
        if tx is not None and source in tx.writes:
            return tx.writes[source]
        found = self.run.env.get(source)
        return found if found is not None else self.plan.distributions[source]

    def described(self, name, tx=None):
        """The mean or the standard deviation of the present distribution of a distribution-valued
        value (`plan.Plan.described`), through the writes of the stage that runs (`tx`)."""
        source, which = self.plan.described[name]
        return described(self.distribution(source, tx), self.plan.units, which)

    def outcomes(self, name, tx=None):
        """The outcomes of the categorical distribution of a draw, in declared order."""
        found = self.plan.draws[name]
        distribution = self.distribution(found.source, tx)
        if distribution.family != 'categorical':
            raise SimulationError(f'{found.site}: a switch draws from a categorical distribution')
        return distribution.outcomes

    def value(self, distribution, key, eligible=None, site=''):
        """One value of a distribution under the run's mode, keyed by `site|owner`."""
        u = None if self.mode == MEDIAN else uniform(self.seed, key)
        if distribution.family == 'categorical':
            return outcome(distribution, eligible, u, site)
        if eligible is not None:
            raise SimulationError(f'{site}: a switch draws from a categorical distribution')
        return numeric(distribution, self.plan.units, 0.5 if u is None else u)

    def draw(self, name, eligible=None, tx=None):
        """An executed draw (see the module), with its entry of the trace; in a stage (`tx`), from the
        distribution that the stage may have given the value that it draws from."""
        drawn = self.plan.draws[name]
        owner = self.owner(drawn.owner)
        source = self.distribution(drawn.source, tx)
        found = self.value(source, f'{drawn.site}|{owner}', eligible, drawn.site)
        if (drawn.site, owner) not in self.kept:
            self.run.recorder.entry(self.run.now, 'draw', drawn.site, owner, value=found)
        self.made.append((drawn.site, owner, found))
        return found
