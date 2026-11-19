"""Chance and choice in a run: the value of each executed draw, an actor's choice, and the pause.

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
- **Eligibility** (D1): a `switch` whose selector is a draw or a choice reads its case guards first
  (`moment.Moment.select`); an outcome that a false guard bars is not eligible, and the draw is made
  among the others, their weights scaled to sum to one. With none eligible, the `else` body runs and
  nothing is drawn. Elsewhere every outcome is eligible. Eligible outcomes whose weights are all zero
  have no draw, and the run fails.
- **A choice** (`plan.Chosen`, `actor.choose(d)`) asks the actor's controller
  (`Configuration.controllers`): with none, or `forecast`, it is a draw of the forecast `d` under the
  mode, keyed as a draw is; a `player` answers with the pick of the choice's site and its owner
  (`Configuration.picks`), any eligible outcome whatever its weight. Eligibility and probability are
  independent. A pick of an outcome that is not eligible fails the run. A choice in a stage is an
  entry of the trace when the stage commits; it says who decided (`by`), the eligible outcomes and,
  for a player, what the actor sees (`sees`: its template's observations, read on the committed
  state, each in its declared unit). `sees` permits nothing.
- **The pause** (spec, "A prompt pauses one atomic stage"): a player's choice that no pick answers
  stops the run inside its stage, before the stage commits (`Paused`). Nothing of the stage is
  visible: its writes, its moves and the starts that it queued are discarded, and the stages after
  it in its round do not run. The record holds the run to that time, and its trace ends with a
  `pause` entry (`paused`): its part is the statement that asks, its owner the occurrence, and its
  details the choice's site, the actor, the eligible outcomes and their forecast weights, what the
  actor sees, the draws that the stage made before the prompt (`kept`, which the trace holds once)
  and the starts that it queued (`starts`). A run of the configuration with the pick replays the
  stage and commits it once: its draws are keyed, so they are the same, and nothing of the stage
  happens twice. `run.Run.resume` goes on in place and gives the same record. A player's choice is
  made in a stage or in the setup: at an entry, a delay or a firing, which belong to a commit, it
  fails the run.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
from scipy import special

from ...distributions import FAMILIES, PERT_WEIGHT, quantile
from ...program.config import MEDIAN, PLAYER
from ...program.refs import spelled
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


class Paused(Exception):
    """A player's choice that no pick answers: the run pauses before the stage that asks commits.
    `details` are those of the `pause` entry of the trace."""

    def __init__(self, part, owner, details):
        super().__init__(f'{owner} waits for a pick at {dict(details)["site"]}')
        self.part, self.owner, self.details = part, owner, details


def paused(record):
    """The `pause` entry that ends the trace of a paused run, or None."""
    if record.trace and record.trace[-1].kind == 'pause':
        return record.trace[-1]
    return None


class Chance:
    """The draws and the choices of one run (see the module)."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan
        configuration = self.plan.configuration
        self.mode, self.seed = configuration.mode, configuration.seed
        self.players = {item.actor for item in configuration.controllers if item.by == PLAYER}
        self.picks = {(item.site, item.occurrence): item.value for item in configuration.picks}
        self.firing = {}  # trigger key -> the number of its firing that runs now, from 1
        self.kept = set()  # (site, owner) of the draws of a paused stage, which the trace holds
        self.made = []  # (site, owner, value) of the draws of the stage that runs

    def owner(self, owner):
        """Who executes a draw or a choice of an owner of the plan: a trigger's present firing."""
        n = self.firing.get(owner)
        return owner if n is None else f'{owner}!{n}'

    def distribution(self, source):
        """The distribution of a draw or a choice: written in place, or the present distribution of a
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
        """The outcomes of the categorical distribution of a draw or a choice, in declared order."""
        found = self.plan.draws.get(name) or self.plan.choices[name]
        distribution = self.distribution(found.source)
        if distribution.family != 'categorical':
            raise SimulationError(f'{found.site}: a switch draws or chooses from a categorical distribution')
        return distribution.outcomes

    def value(self, distribution, key, eligible=None, site=''):
        """One value of a distribution under the run's mode, keyed by `site|owner`."""
        u = None if self.mode == MEDIAN else uniform(self.seed, key)
        if distribution.family == 'categorical':
            return outcome(distribution, eligible, u, site)
        if eligible is not None:
            raise SimulationError(f'{site}: a switch draws from a categorical distribution')
        return numeric(distribution, self.plan.units, 0.5 if u is None else u)

    def produce(self, name, eligible=None, tx=None):
        """Execute the draw or the choice `name` among the eligible outcomes (None: all)."""
        if name in self.plan.draws:
            return self.draw(name, eligible)
        return self.choose(name, eligible, tx)

    def draw(self, name, eligible=None):
        """An executed draw (see the module), with its entry of the trace."""
        drawn = self.plan.draws[name]
        owner = self.owner(drawn.owner)
        found = self.value(self.distribution(drawn.source), f'{drawn.site}|{owner}', eligible, drawn.site)
        if (drawn.site, owner) not in self.kept:
            self.run.recorder.entry(self.run.now, 'draw', drawn.site, owner, value=found)
        self.made.append((drawn.site, owner, found))
        return found

    def choose(self, name, eligible, tx):
        """An actor's choice (see the module): the forecast's draw, or the player's pick. A choice
        in a stage is traced when the stage commits (`tx.choices`), any other at once."""
        chosen = self.plan.choices[name]
        owner, site = self.owner(chosen.owner), chosen.site
        forecast = self.distribution(chosen.source)
        if forecast.family != 'categorical':
            raise SimulationError(f'{site}: an actor chooses from a categorical forecast')
        options = tuple(member for member in forecast.outcomes if eligible is None or member in eligible)
        details = {'actor': chosen.actor, 'options': options}
        if chosen.actor not in self.players:
            found = self.value(forecast, f'{site}|{owner}', eligible, site)
            details['by'] = 'forecast'
        else:
            if tx is None or not tx.stage:
                raise SimulationError(
                    f'{site}: {chosen.actor} is played, and a player chooses in a stage: a prompt pauses '
                    'one stage, and an entry, a delay or a firing belongs to a commit'
                )
            details['sees'] = self.seen(chosen.actor)
            found = self.picks.get((site, owner))
            if found is None:
                weights = tuple(zip(forecast.outcomes, (float(w) for w in forecast.params)))
                kept = tuple((place, value) for place, by, value in self.made if by == owner)
                starts = tuple(f'{member}.{event}' for member, event, _ in tx.starts)
                raise Paused(
                    tx.origin,
                    owner,
                    (
                        ('site', site),
                        *details.items(),
                        ('weights', weights),
                        ('kept', kept),
                        ('starts', starts),
                    ),
                )
            if found not in options:
                raise SimulationError(
                    f'{site}: the pick {found} of {owner} is not available (available: '
                    f'{", ".join(options) or "none"})'
                )
            details['by'] = PLAYER
        details = {'value': found, **details}
        if tx is not None:
            tx.choices.append((site, owner, details))
        else:
            self.run.recorder.entry(self.run.now, 'choice', site, owner, **details)
        return found

    def seen(self, actor):
        """What a player of an actor is shown: each observation of its template (`sees`), read on the
        committed state, as (its spelling, its value in its declared unit)."""
        run, plan = self.run, self.plan
        template, row = plan.program.member(actor)
        scope = (template, row, template.members[row])
        found = []
        for path in template.sees:
            names = plan.observed(path, scope)
            values = []
            for name in names:
                value = run.value(name)
                unit = plan.values[name].unit if name in plan.values else ''
                if unit and not isinstance(value, bool | str):
                    value = float(value) / plan.units.scale(unit)
                values.append(value)
            found.append((spelled(path), values[0] if len(names) == 1 else tuple(values)))
        return tuple(found)
