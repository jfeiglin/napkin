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
from scipy import special

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


def _phi(x):
    """The density of a standard normal, and x times it (0 at an infinite x)."""
    if not math.isfinite(x):
        return 0.0, 0.0
    density = math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
    return density, x * density


def described(distribution, units, which):
    """The mean or the standard deviation (`which`) of a numeric distribution, in canonical units:
    the closed form of its family. A normal or a lognormal with bounds is truncated to them, as its
    draws are (`distributions.quantile`). Reading it draws nothing."""
    family = FAMILIES[distribution.family]
    scale = units.scale(distribution.unit) if distribution.unit else 1.0
    a = [
        float(value) * (1.0 if name in family.dimensionless else scale)
        for name, value in zip(family.parameters, distribution.params)
    ]
    name = distribution.family
    if name == 'uniform':
        low, high = a
        mean, variance = (low + high) / 2, (high - low) ** 2 / 12
    elif name == 'triangular':
        low, mode, high = a
        mean = (low + mode + high) / 3
        variance = (low * low + mode * mode + high * high - low * mode - low * high - mode * high) / 18
    elif name == 'pert':
        low, mode, high = a
        alpha = 1 + PERT_WEIGHT * (mode - low) / (high - low)
        beta = 1 + PERT_WEIGHT * (high - mode) / (high - low)
        mean = low + (high - low) * alpha / (alpha + beta)
        variance = (high - low) ** 2 * alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1))
    elif name == 'loguniform':
        low, high = a
        span = math.log(high / low)
        mean = (high - low) / span
        variance = (high * high - low * low) / (2 * span) - mean * mean
    elif name == 'normal':
        mu, sd = a[:2]
        low, high = a[2:] if len(a) == 4 else (-math.inf, math.inf)
        alpha, beta = (low - mu) / sd, (high - mu) / sd
        mass = float(special.ndtr(beta) - special.ndtr(alpha))
        (pa, xa), (pb, xb) = _phi(alpha), _phi(beta)
        shift = (pa - pb) / mass
        mean, variance = mu + sd * shift, sd * sd * (1 + (xa - xb) / mass - shift * shift)
    else:  # lognormal: the k-th moment of a normal of the logarithm, truncated
        mu, sigma = math.log(a[0]), math.log(a[1])
        low, high = a[2:] if len(a) == 4 else (0.0, math.inf)
        alpha = (math.log(low) - mu) / sigma if low > 0 else -math.inf
        beta = (math.log(high) - mu) / sigma if math.isfinite(high) else math.inf
        mass = float(special.ndtr(beta) - special.ndtr(alpha))

        def moment(k):
            inside = special.ndtr(beta - k * sigma) - special.ndtr(alpha - k * sigma)
            return math.exp(k * mu + k * k * sigma * sigma / 2) * float(inside) / mass

        mean = moment(1)
        variance = moment(2) - mean * mean
    return mean if which == 'mean' else math.sqrt(max(variance, 0.0))


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

    def distribution(self, source):
        """The distribution of a draw: written in place, or the present distribution of a
        distribution-valued value, which a stage may have replaced."""
        if not isinstance(source, str):
            return source
        found = self.run.env.get(source)
        return found if found is not None else self.plan.distributions[source]

    def described(self, name):
        """The mean or the standard deviation of the present distribution of a distribution-valued
        value (`plan.Plan.described`)."""
        source, which = self.plan.described[name]
        return described(self.distribution(source), self.plan.units, which)

    def outcomes(self, name):
        """The outcomes of the categorical distribution of a draw, in declared order."""
        found = self.plan.draws[name]
        distribution = self.distribution(found.source)
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

    def draw(self, name, eligible=None):
        """An executed draw (see the module), with its entry of the trace."""
        drawn = self.plan.draws[name]
        owner = self.owner(drawn.owner)
        found = self.value(self.distribution(drawn.source), f'{drawn.site}|{owner}', eligible, drawn.site)
        if (drawn.site, owner) not in self.kept:
            self.run.recorder.entry(self.run.now, 'draw', drawn.site, owner, value=found)
        self.made.append((drawn.site, owner, found))
        return found
