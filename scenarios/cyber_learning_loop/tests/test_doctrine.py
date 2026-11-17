"""The scenario's doctrine test against independent mathematics.

A plan counts on the attacks that the force can mass on one objective in its time, and each attack carries
its targets. Each kind of target system in an attack needs its own shared capability, each fails on its own,
and each failure takes the attacks that depend on it. The model gives the chance that the plan meets its plan
by a normal approximation of the share of targets hit, mixed over the number of shared capabilities that
fail. The planned share is the mean share. These tests count the same chance exactly, simulate the spread of
the share from its causes, and check the properties of the review and of doctrine that follow from the
specification without a computed value."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.optimize import brentq
from scipy.special import expit, logit
from scipy.stats import binom, norm, poisson

from napkin.core import expr
from napkin.dynamics import vector_field
from tests.helpers import catalogue_model, catalogue_study

YEAR_H = 8760.0
DAYS_IN_YEAR = 365.0
PLANS = ('day_plan', 'week_plan', 'month_plan', 'quarter_plan')
# Nodes of the Gauss-Hermite quadrature over the plan's common factor.
NODES = 40


def values_at(run, names, t_years=0.0, values=None):
    """The model's values of `names` at the start state, at time t (execution units)."""
    field = vector_field(catalogue_model('cyber_learning_loop'), run, values)
    return field_values(field, names, t_years, field.base)


def field_values(field, names, t_years, y):
    program = field.field.values_program([expr.ref(name) for name in names])
    return dict(zip(names, program(t_years * YEAR_H, y)))


def inputs(run, values=None):
    return catalogue_model('cyber_learning_loop').resolve(run, values).parameter_values


def forecast_error(x, success, lessons):
    """The planners' forecast error: a floor and the sampling error of the chance from the lessons."""
    floor = x['military_planners.forecast_floor']
    return math.sqrt(floor**2 + (1 - success) / success / (lessons + 1))


def kinds(diversity, size):
    """The expected kinds of target system of an attack on `size` targets: its first target is one kind, and
    each further target is a new kind with the chance `diversity`."""
    return 1 + diversity * max(size - 1, 0)


def normal_factor(chance, spread):
    """The chance of a target at each node of the plan's common factor, and the weights of the nodes. The
    factor is normal on the chance, with the mean `chance` and the relative spread (1 - chance) * spread: a
    spread of the log-odds carried to the chance by its slope."""
    z, w = np.polynomial.hermite_e.hermegauss(NODES)
    chances = chance * (1 + (1 - chance) * spread * z)
    assert np.all((chances > 0) & (chances < 1))
    return chances, w / w.sum()


def failure_counts(failures, depth, attacks):
    """For each number k of failed shared capabilities, a Poisson number with the mean `failures`: k, the
    whole attacks that are left when each failure takes the share `depth` of the plan's attacks, and the
    chance of k. The last entry also holds every larger number, when no attack is left or when more failures
    have a negligible chance."""
    k, mass = 0, 0.0
    while True:
        left = round((1 - min(k * depth, 1)) * attacks)
        weight = poisson.pmf(k, failures)
        if left == 0 or 1 - mass - weight < 1e-15:
            yield k, left, 1 - mass
            return
        yield k, left, weight
        mass += weight
        k += 1


def exact_chance(attacks, chance, tolerance, failures, depth, error, factor):
    """The chance that a plan of single-target attacks meets its plan, by an exact count of hits.

    Each attack that a failure leaves hits its target with the chance of the common factor at each of its
    nodes. The planners plan for the share chance * (1 + error * z), z standard normal, and the plan is met
    when the hits reach (1 - tolerance) of the planned hits. So h hits meet the plan with the chance
    Phi((h / planned - 1) / error)."""
    chances, weights = factor
    planned = (1 - tolerance) * attacks * chance
    total = 0.0
    for _, left, weight in failure_counts(failures, depth, attacks):
        met = 0.0
        for c, w in zip(chances, weights):
            # The hits beyond 12 standard deviations of their mean have a negligible chance.
            sd = math.sqrt(left * c * (1 - c))
            hits = np.arange(
                max(0, math.floor(left * c - 12 * sd) - 1), min(left, math.ceil(left * c + 12 * sd) + 1) + 1
            )
            met += w * (binom.pmf(hits, left, c) @ norm.cdf((hits / planned - 1) / error))
        total += weight * met
    return total


def spread_function(attacks, chance, tolerance, error, factor, targets=1, correlation=0.0):
    """The spread of the share hit, as a share of the planned share, when failures take the share L of the
    plan: the luck of the targets of the attacks left, the common factor on them and the planners' error."""
    chances, weights = factor
    luck = (1 - chance) * (1 + (targets - 1) * correlation) / (chance * attacks * targets)
    common = weights @ (chances / chance - 1) ** 2
    planners = ((1 - tolerance) * error) ** 2
    return lambda loss: math.sqrt((1 - loss) * luck + (1 - loss) ** 2 * common + planners)


def tail_moments(failures):
    """The numbers of failures from four up, their chances given four or more, and their mean and variance."""
    top = int(failures + 40 * math.sqrt(failures) + 60)
    count = np.arange(4, top + 1)
    weights = poisson.pmf(count, failures)
    weights[-1] += poisson.sf(top, failures)
    weights = weights / weights.sum()
    mean = weights @ count
    return count, weights, mean, weights @ (count - mean) ** 2


def antiderivative(z):
    """The integral of the standard normal distribution function up to z."""
    return z * norm.cdf(z) + norm.pdf(z)


def wasserstein_to_normal(points, weights, mean, sd):
    """The Wasserstein distance between the distribution of `weights` on `points` and the normal of `mean` and
    `sd`: the integral of the gap of their distribution functions, by the antiderivative of the normal one."""
    if sd == 0:
        return float(weights @ np.abs(points - mean))
    order = np.argsort(points)
    z, below = (points[order] - mean) / sd, np.cumsum(weights[order])
    total = antiderivative(z[0]) + norm.pdf(z[-1]) - z[-1] * norm.sf(z[-1])
    for low, high, level in zip(z[:-1], z[1:], below[:-1]):
        if high > low:
            cut = min(max(norm.ppf(min(level, 1.0)), low), high)
            total += level * (cut - low) - (antiderivative(cut) - antiderivative(low))
            total += antiderivative(high) - antiderivative(cut) - level * (high - cut)
    return sd * total


def tail_bound(failures, depth, spread_at):
    """A bound on the gap between the chance of a plan in which four or more shared capabilities fail, counted
    one number of failures at a time, and the model's chance of that case: at the mean number of failures given
    four or more, with the variance of that number in the spread. Weighted by the chance of four or more:
    - the spread of the share hit at each loss and not at the mean loss: phi(1) times the gap of their squares,
      over twice the smaller square;
    - the loss itself: the model's chance is the mean of the normal chance at a loss of the normal of the tail's
      mean and variance. A normal chance moves with the loss by at most the largest density of its spread, so
      the gap is at most that density times the Wasserstein distance of the tail's loss from that normal."""
    tail = poisson.sf(3, failures)
    if tail == 0:
        return 0.0
    count, weights, mean, variance = tail_moments(failures)
    centre = min(max(mean * depth, min(4 * depth, 1)), 1)
    losses = np.minimum(count * depth, 1)
    spreads = np.array([spread_at(loss) for loss in losses])
    at_mean = spread_at(centre)
    spread = weights @ (
        norm.pdf(1) * np.abs(spreads**2 - at_mean**2) / (2 * np.minimum(spreads, at_mean) ** 2)
    )
    loss = wasserstein_to_normal(losses, weights, centre, depth * math.sqrt(variance)) / (
        at_mean * math.sqrt(2 * math.pi)
    )
    return tail * (spread + loss)


def count_bound(attacks, chance, tolerance, failures, depth, error, factor):
    """A bound on the gap between the exact count and the normal mixture of the same plan, by its parts:
    - the count of hits: its Wasserstein distance from its normal is at most (c^2 + (1 - c)^2) in hits
      (Goldstein 2010, constant 1), so at most that over the planned hits at the chance in the share. The
      planners' error smooths the plan's threshold, so the chance moves by at most that distance times the
      largest density of the error;
    - whole attacks: the attacks that a failure leaves differ from their share of the plan by at most half an
      attack, which moves the mean share;
    - the luck of each target at the chance of the factor's node and not at the mean chance: a change of the
      variance v moves a normal chance by at most phi(1) v over twice the variance of the error;
    - the model counts four or more failures at their mean number, with the spread of that number (`tail_bound`)."""
    chances, weights = factor
    spread = (1 - tolerance) * error
    density = 1 / (spread * math.sqrt(2 * math.pi))
    total = 0.0
    for k, left, weight in failure_counts(failures, depth, attacks):
        share = 1 - min(k * depth, 1)
        count = (chances**2 + (1 - chances) ** 2) / (attacks * chance) * density if left else 0 * chances
        whole = abs(left / attacks - share) * chances / chance * density
        luck = left * chances * (1 - chances) / (attacks * chance) ** 2 - share * (1 - chance) / (
            chance * attacks
        )
        total += weight * (weights @ (count + whole + norm.pdf(1) * np.abs(luck) / (2 * spread**2)))
    return total + tail_bound(failures, depth, spread_function(attacks, chance, tolerance, error, factor))


def failure_shares(failures, depth):
    """For each Poisson number of failed shared capabilities: the share of the plan's attacks that they leave,
    and its chance. The last entry also holds every larger number, when no attack is left or when more failures
    have a negligible chance."""
    k, mass = 0, 0.0
    while True:
        share = 1 - min(k * depth, 1)
        weight = poisson.pmf(k, failures)
        if share == 0 or 1 - mass - weight < 1e-15:
            yield share, 1 - mass
            return
        yield share, weight
        mass += weight
        k += 1


def normal_mixture(attacks, chance, tolerance, failures, depth, error, factor, targets, correlation):
    """The chance that a plan meets its plan when its attacks are so many that the hits of the attacks that the
    failures leave are normal: the mean, over the Poisson number of failures and the nodes of the common factor,
    of the normal chance that the hits reach (1 - tolerance) of the planned hits. At the chance c, the hits of
    one attack on m targets whose outcomes correlate by rho have the variance m c (1 - c) (1 + (m - 1) rho)."""
    chances, weights = factor
    planners = ((1 - tolerance) * error) ** 2
    spread = 1 + (targets - 1) * correlation
    total = 0.0
    for share, weight in failure_shares(failures, depth):
        variance = share * chances * (1 - chances) * spread / (attacks * targets * chance**2)
        met = norm.cdf((share * chances / chance - (1 - tolerance)) / np.sqrt(variance + planners))
        total += weight * (weights @ met)
    return total


def limit_bound(attacks, chance, tolerance, failures, depth, error, factor, targets, correlation):
    """A bound on the gap between that mixture and the model's: the luck of the targets at the chance of each
    node of the factor and not at the mean chance, and the model's count of four or more failures at their mean
    number (`tail_bound`)."""
    chances, weights = factor
    planners = ((1 - tolerance) * error) ** 2
    spread = 1 + (targets - 1) * correlation
    total = 0.0
    for share, weight in failure_shares(failures, depth):
        gap = (
            share
            * spread
            * np.abs(chances * (1 - chances) - chance * (1 - chance))
            / (attacks * targets * chance**2)
        )
        total += weight * (weights @ (norm.pdf(1) * gap / (2 * planners)))
    spread_at = spread_function(attacks, chance, tolerance, error, factor, targets, correlation)
    return total + tail_bound(failures, depth, spread_at)


def share_moments(attacks, chance, tolerance, failures, depth, error, factor):
    """The mean and the variance of the share of the planned hits that the plan's attacks hit, in the same
    count."""
    chances, weights = factor
    mean = second = 0.0
    for _, left, weight in failure_counts(failures, depth, attacks):
        hits = left * chances
        mean += weight * (weights @ hits) / (attacks * chance)
        second += weight * (weights @ (hits * (1 - chances) + hits**2)) / (attacks * chance) ** 2
    return mean, second - mean**2


# Single-target attacks, so every plan has today's kinds; the least common factor and forecast floor that the
# ranges admit; no failures while the plan runs; and a plan that counts on all of the force's attacks.
MIXTURE = {
    'effects_program.targets_end': 1,
    'defenders.common_spread': 0.1,
    'defenders.shared_failure': 0.1,
    'defenders.failure_rate': 0,
    'effects_program.concentration_now': 0.9,
    'military_planners.forecast_floor': 0.1,
    'military_planners.objective_share': 1,
}
# The plan's attacks held ready, as a multiple of today's, that makes the luck of the targets almost average
# out, so that the count tests the mixture over the failures sharply.
LARGE = 1000


def day_plan(run, t_years, values, held=1):
    """The inputs of the exact count of the day plan at the start state, with `held` times today's attacks held
    ready, its inputs and the model's chance. The attacks have one target each, so they have today's kinds:
    at least one shared capability fails with today's chance, and a failure takes today's share."""
    field = vector_field(catalogue_model('cyber_learning_loop'), run, values)
    s = field.system
    y = field.base.copy()
    for name in ('held_ready', 'held_targets', 'held_spread', 'held_outcomes'):
        y[s.index[f'effects_program.{name}']] *= held
    names = [
        'day_plan.chance',
        'day_plan.attacks',
        'day_plan.failures',
        'day_plan.depth',
        'effects_program.success',
        'effects_program.know_how',
    ]
    v = field_values(field, names, t_years, y)
    x = field.rs.parameter_values
    assert x['defenders.failure_rate'] == 0
    p = v['effects_program.success']
    plan = {
        'attacks': v['day_plan.attacks'],
        'chance': p,
        'tolerance': x['military_planners.tolerance'],
        'failures': -math.log(1 - x['defenders.shared_failure']),
        'depth': x['effects_program.concentration_now'],
        'error': forecast_error(x, p, v['effects_program.know_how']),
    }
    assert v['day_plan.failures'] == pytest.approx(plan['failures'], rel=1e-12)
    assert v['day_plan.depth'] == pytest.approx(plan['depth'], rel=1e-12)
    return x, plan, v['day_plan.chance']


def test_the_mixture_matches_an_exact_count_where_a_normal_formula_does_not():
    # One shared capability fails by the plan's start with a chance of 0.1. Nine tenths of the plan's effect
    # depends on it, so one failure takes 90% of the plan's attacks, and two take all of them. The model's
    # mixture must match an exact count of hits within the bound of its normal approximation. A normal formula
    # with the mean and the variance of the same count misses it by far more. In a plan of far more attacks,
    # the bound shrinks, and the model must still match the count within it. The count takes the common factor
    # normal on the chance; the test of the spread checks its shape in log-odds.
    x, plan, chance = day_plan('no_ai', 0, MIXTURE)
    factor = normal_factor(plan['chance'], x['defenders.common_spread'])
    exact = exact_chance(**plan, factor=factor)
    bound = count_bound(**plan, factor=factor)
    assert abs(chance - exact) <= bound
    mean, variance = share_moments(**plan, factor=factor)
    threshold = 1 - plan['tolerance']
    normal = norm.cdf((mean - threshold) / math.sqrt(variance + (threshold * plan['error']) ** 2))
    assert abs(normal - exact) > 3 * bound
    x, plan, chance = day_plan('no_ai', 0, MIXTURE, held=LARGE)
    factor = normal_factor(plan['chance'], x['defenders.common_spread'])
    assert abs(chance - exact_chance(**plan, factor=factor)) <= count_bound(**plan, factor=factor)


def test_a_small_shared_part_matches_an_exact_count_of_the_attacks_that_keep_their_own_path():
    # When a failed capability takes less than the tolerance of the plan, the plan can still meet its plan
    # after one failure, but hardly after two. The attacks that depend on a failed capability give nothing,
    # and every other attack keeps its own chance. The model's chance must match an exact count of hits in
    # that mixture, in today's plan and in a plan of far more attacks.
    edits = {**MIXTURE, 'effects_program.concentration_now': 0.2, 'defenders.shared_failure': 0.3}
    for held in (1, LARGE):
        x, plan, chance = day_plan('ai_fast', 25, edits, held)
        assert plan['depth'] < plan['tolerance'] < 2 * plan['depth']
        factor = normal_factor(plan['chance'], x['defenders.common_spread'])
        assert abs(chance - exact_chance(**plan, factor=factor)) <= count_bound(**plan, factor=factor)


# Every further target of an attack a kind of its own, 100 targets an attack, and the least common factor of the
# range.
MANY_KINDS = {
    'effects_program.diversity': 1,
    'effects_program.targets_end': 100,
    'defenders.common_spread': 0.1,
}


def test_a_plan_of_many_kinds_of_target_system_counts_every_number_of_failures():
    # When every target of an attack is a kind of its own, an attack on 100 targets needs 100 shared
    # capabilities. One failure then takes a hundredth of today's share of the plan, but tens of capabilities
    # can fail in a long plan. The model counts zero to three failures one by one, and four or more at their
    # mean number with the spread of that number. In a plan of far more attacks, the luck of the targets
    # averages out, so after k failures the share hit is normal around what the attacks left can hit. The
    # plan's chance is then the mean of those normal chances over the Poisson number of failures, every number
    # counted, and the model must match it within the bound of its count of four or more failures.
    field = vector_field(catalogue_model('cyber_learning_loop'), 'ai_fast', MANY_KINDS)
    s = field.system
    x = field.rs.parameter_values
    rho = field_values(field, ['effects_program.within_correlation'], 25, field.base)
    size, correlation = x['effects_program.targets_end'], rho['effects_program.within_correlation']
    y = sized_state(field, size, size, correlation)
    for name in ('held_ready', 'held_targets', 'held_spread', 'held_outcomes'):
        y[s.index[f'effects_program.{name}']] *= LARGE
    names = [f'{plan}.{member}' for plan in PLANS for member in ('attacks', 'chance')]
    v = field_values(field, [*names, 'effects_program.success', 'effects_program.know_how'], 25, y)
    p = v['effects_program.success']
    diversity = x['effects_program.diversity']
    kinds_now = kinds(diversity, size) / kinds(diversity, x['effects_program.targets_now'])
    for plan in PLANS:
        one = 1 - (1 - x['defenders.shared_failure']) * math.exp(
            -x['defenders.failure_rate'] * x[f'{plan}.length'] / DAYS_IN_YEAR
        )
        case = {
            'attacks': v[f'{plan}.attacks'],
            'chance': p,
            'tolerance': x['military_planners.tolerance'],
            'failures': -kinds_now * math.log(1 - one),
            'depth': x['effects_program.concentration_now'] / kinds_now,
            'error': forecast_error(x, p, v['effects_program.know_how']),
            'factor': normal_factor(p, x['defenders.common_spread']),
            'targets': size,
            'correlation': correlation,
        }
        # Most of the plan's chance lies with four failures or more.
        assert poisson.sf(3, case['failures']) > 0.5
        assert abs(v[f'{plan}.chance'] - normal_mixture(**case)) <= limit_bound(**case)


def mean_preserving_shift(chance, spread):
    """The shift of the log-odds that keeps the mean chance at `chance` under a common factor in log-odds."""
    z, w = np.polynomial.hermite_e.hermegauss(NODES)
    w = w / w.sum()
    return brentq(lambda a: w @ expit(logit(chance) + a + spread * z) - chance, -1, 1, xtol=1e-15)


def test_the_spread_of_a_plan_is_the_spread_that_its_causes_give():
    # Each attack hits its targets with a chance drawn from a beta distribution whose intraclass correlation is
    # the correlation of that attack's targets. The attacks held ready keep the correlation that they were built
    # with, today's, and the attacks that the force finishes in the plan's time have the current one. All of the
    # plan's attacks share a common factor in log-odds that keeps the mean chance at the chance of success: the
    # planned share is the mean share. So the share hit, relative to the planned share, must have the mean one
    # and the model's attack spread as its spread.
    edits = {
        'effects_program.targets_now': 3,
        'effects_program.targets_end': 3,
        'defenders.common_spread': 0.1,
        'military_planners.objective_share': 0.6,
    }
    x = inputs('ai_fast', edits)
    names = [
        'quarter_plan.attacks',
        'quarter_plan.finished',
        'quarter_plan.attack_spread',
        'effects_program.held_ready',
        'effects_program.success',
        'effects_program.within_correlation',
    ]
    v = values_at('ai_fast', names, t_years=10, values=edits)
    share = x['military_planners.objective_share']
    held, finished = round(share * v['effects_program.held_ready']), round(share * v['quarter_plan.finished'])
    assert held + finished == pytest.approx(v['quarter_plan.attacks'], abs=1) and finished >= 40
    p, m, common = (
        v['effects_program.success'],
        round(x['effects_program.targets_now']),
        x['defenders.common_spread'],
    )
    correlation = {'held': x['defenders.within_now'], 'finished': v['effects_program.within_correlation']}
    assert correlation['finished'] < correlation['held']
    rng = np.random.default_rng(45)
    draws = 40000
    shift = mean_preserving_shift(p, common)
    chance = expit(logit(p) + shift + common * rng.standard_normal(draws))[:, None]

    def hits(attacks, rho):
        q = rng.beta(chance * (1 / rho - 1), (1 - chance) * (1 / rho - 1), size=(draws, attacks))
        return rng.binomial(m, q).sum(axis=1)

    hit = (hits(held, correlation['held']) + hits(finished, correlation['finished'])) / (
        (held + finished) * m * p
    )
    assert abs(np.mean(hit) - 1) < 4 * np.std(hit) / math.sqrt(draws)
    assert np.var(hit) == pytest.approx(v['quarter_plan.attack_spread'] ** 2, rel=0.05)


@pytest.mark.parametrize(
    ('run', 't_years'), [('no_ai', 0), ('ai_fast', 4), ('ai_fast', 25), ('dispersed', 10)]
)
def test_the_two_sided_test_never_passes_a_plan_that_the_shortfall_test_fails(run, t_years):
    names = [f'{plan}.chance' for plan in PLANS]
    shortfall = values_at(run, names, t_years)
    two_sided = values_at(run, names, t_years, {'military_planners.two_sided': True})
    for name in names:
        assert 0 < two_sided[name] <= shortfall[name]


def test_a_higher_rate_of_shared_failures_makes_a_shorter_plan_win():
    # A longer plan masses more attacks, so its share of targets hit varies less, but it gives the
    # defenders more time to stop a capability that its attacks share. Every target of an attack runs one
    # kind of system, so half of the plan's effect depends on that capability. With no such failure over
    # time the longest plan wins; with frequent failures the shortest does.
    lengths = []
    for rate in (0, 0.6, 3):
        edits = {
            'military_planners.objective_share': 0.05,
            'defenders.failure_rate': rate,
            'effects_program.diversity': 0,
        }
        lengths.append(
            values_at('ai_fast', ['military_planners.best_length'], 25, edits)[
                'military_planners.best_length'
            ]
        )
    assert lengths == sorted(lengths, reverse=True)
    assert lengths[0] == pytest.approx(91 * 24) and lengths[-1] == pytest.approx(24)


def sized_state(field, held_size, new_size, rho):
    """Today's state with every attack held ready on `held_size` targets whose outcomes correlate by rho, and
    every attack in the chain on `new_size` targets."""
    s = field.system
    y = field.base.copy()
    for targets, attacks in (
        ('in_access', 'in_access_attacks'),
        ('accesses', 'access_attacks'),
        ('positioned', 'positioned_attacks'),
    ):
        y[s.index[f'effects_program.{targets}']] = new_size * y[s.index[f'effects_program.{attacks}']]
    held = y[s.index['effects_program.held_ready']]
    y[s.index['effects_program.held_targets']] = held * held_size
    y[s.index['effects_program.held_spread']] = held * held_size * (1 + (held_size - 1) * rho)
    y[s.index['effects_program.held_outcomes']] = held * held_size / (1 + (held_size - 1) * rho)
    return y


def expected_loss(failures, depth):
    """The mean share of a plan that a Poisson number of failures takes, each the share `depth`, all at most."""
    whole = math.ceil(1 / depth)
    k = np.arange(whole)
    return float(poisson.pmf(k, failures) @ (k * depth) + poisson.sf(whole - 1, failures))


SIZES = ((1, 1), (4, 4), (30, 30), (30, 10))
COUNTED = ('size', 'finished', 'depth', 'failure', 'failures', 'none_fail')
TAIL = ('two_or_more', 'three_or_more', 'four_or_more', 'tail_count', 'tail_spread', 'loss_4')


def test_more_kinds_of_target_system_split_a_failure_but_let_more_capabilities_fail():
    # Each kind of target system in an attack needs its own shared capability, and each fails on its own with
    # today's chance for one capability. So with u kinds, where today's attacks have u0, one failure takes
    # u0 / u of today's share of the plan, but the plan's capabilities fail as u / u0 sets of today's: the chance
    # that none fails is today's to the power u / u0. The mean number of failures grows as the share of each
    # falls, so the mean share that the failures take does not fall with the kinds. At today's kinds, the
    # chance that at least one fails is today's. The plan counts four or more failures at their mean number
    # given four or more, with the variance of that number: both are those of the Poisson count.
    x = inputs('ai_fast')
    shared, rate, concentration = (
        x['defenders.shared_failure'],
        x['defenders.failure_rate'],
        x['effects_program.concentration_now'],
    )
    found = {}
    for diversity in (0, 0.1, 1):
        field = vector_field(
            catalogue_model('cyber_learning_loop'), 'ai_fast', {'effects_program.diversity': diversity}
        )
        rho = field_values(field, ['effects_program.within_correlation'], 25, field.base)
        today = kinds(diversity, x['effects_program.targets_now'])
        names = [f'{plan}.{member}' for plan in PLANS for member in (*COUNTED, *TAIL)]
        for held_size, new_size in SIZES:
            y = sized_state(field, held_size, new_size, rho['effects_program.within_correlation'])
            held = y[field.system.index['effects_program.held_ready']]
            v = field_values(field, names, 25, y)
            for plan in PLANS:
                finished = v[f'{plan}.finished']
                size = (held * held_size + finished * new_size) / (held + finished)
                assert v[f'{plan}.size'] == pytest.approx(size, rel=1e-12)
                u = kinds(diversity, size)
                one = 1 - (1 - shared) * math.exp(-rate * x[f'{plan}.length'] / DAYS_IN_YEAR)
                assert v[f'{plan}.failure'] == pytest.approx(one, rel=1e-12)
                assert v[f'{plan}.depth'] == pytest.approx(concentration * today / u, rel=1e-12)
                assert v[f'{plan}.none_fail'] == pytest.approx(math.exp(-v[f'{plan}.failures']), rel=1e-12)
                assert v[f'{plan}.none_fail'] == pytest.approx((1 - one) ** (u / today), rel=1e-12)
                assert v[f'{plan}.failures'] * v[f'{plan}.depth'] == pytest.approx(
                    -concentration * math.log(1 - one), rel=1e-12
                )
                if size == 1:
                    assert 1 - v[f'{plan}.none_fail'] == pytest.approx(one, rel=1e-12)
                # The model's chances of two, three and four or more failures, and the mean and the variance of
                # the number given four or more, subtract nearly equal sums when few failures are expected; the
                # tolerances are those of that rounding.
                failures, depth = v[f'{plan}.failures'], v[f'{plan}.depth']
                for least, member in ((2, 'two_or_more'), (3, 'three_or_more'), (4, 'four_or_more')):
                    assert v[f'{plan}.{member}'] == pytest.approx(poisson.sf(least - 1, failures), rel=1e-8)
                assert poisson.sf(3, failures) > 1e-12
                _, _, mean, variance = tail_moments(failures)
                assert v[f'{plan}.tail_count'] == pytest.approx(mean, rel=1e-8)
                assert v[f'{plan}.tail_spread'] == pytest.approx(variance, rel=1e-5)
                assert v[f'{plan}.loss_4'] == pytest.approx(
                    min(max(mean * depth, min(4 * depth, 1)), 1), rel=1e-8
                )
                found[(plan, held_size, new_size, diversity)] = (
                    v[f'{plan}.depth'],
                    v[f'{plan}.failures'],
                    expected_loss(v[f'{plan}.failures'], v[f'{plan}.depth']),
                )
    for plan in PLANS:
        for held_size, new_size in SIZES:
            depth, failures, lost = zip(*(found[(plan, held_size, new_size, d)] for d in (0, 0.1, 1)))
            if held_size == new_size == 1:
                assert depth == pytest.approx([depth[0]] * 3) and failures == pytest.approx([failures[0]] * 3)
            else:
                assert depth[0] > depth[1] > depth[2] and failures[0] < failures[1] < failures[2]
            assert lost[0] <= lost[1] + 1e-12 and lost[1] <= lost[2] + 1e-12
            assert all(share <= f * d * (1 + 1e-12) for share, f, d in zip(lost, failures, depth))


@pytest.mark.parametrize(
    ('run', 't_years'), [('no_ai', 0), ('ai_fast', 6), ('ai_slow', 25), ('dispersed', 10)]
)
def test_shared_causes_cap_the_chance_however_many_attacks_a_plan_has(run, t_years):
    # Without a shared failure, the share of targets hit varies at least by the common factor and the
    # planners' error, which more attacks do not remove. So a plan's chance is at most
    # P(none fails) Phi(tolerance / that spread) + P(at least one fails).
    edits = {'military_planners.objective_share': 1}
    x = inputs(run, edits)
    names = [f'{plan}.{member}' for plan in PLANS for member in ('chance', 'none_fail')]
    v = values_at(run, [*names, 'effects_program.success', 'effects_program.know_how'], t_years, edits)
    p = v['effects_program.success']
    tolerance = x['military_planners.tolerance']
    floor = math.hypot(
        (1 - p) * x['defenders.common_spread'],
        (1 - tolerance) * forecast_error(x, p, v['effects_program.know_how']),
    )
    for plan in PLANS:
        none_fail = v[f'{plan}.none_fail']
        assert v[f'{plan}.chance'] <= none_fail * norm.cdf(tolerance / floor) + 1 - none_fail + 1e-12


def test_doctrine_forms_after_enough_passes_and_lapses_after_enough_misses():
    # AI progress is taken back from 2034. With planners who accept a chance of 0.77, a plan passes on the way
    # up and every plan misses on the way down, so doctrine forms and then lapses. Each forming must follow the
    # reviews in a row that it needs, and each lapse the misses in a row.
    edits = {'ai_tools.reversal_depth': 1, 'ai_tools.reversal_start': 8, 'military_planners.acceptance': 0.77}
    x = inputs('ai_reversal', edits)
    study = catalogue_study('cyber_learning_loop', {'set': edits}, runs=['ai_reversal'])
    reviews, changes = planner_events(study.runs['ai_reversal']['trajectory'].trace)
    assert [kind for _, kind in changes] == ['forms', 'lapses']
    for t, kind in changes:
        before = [outcome for when, outcome in reviews if when <= t]
        needed = x[
            'military_planners.passes_needed' if kind == 'forms' else 'military_planners.misses_needed'
        ]
        wanted = 'met' if kind == 'forms' else 'missed'
        assert len(before) >= needed and set(before[-int(needed) :]) == {wanted}
        # Doctrine changes at a review, the first time that the count in a row reaches the number needed.
        assert t in {when for when, _ in reviews}
        assert len(before) == needed or before[-int(needed) - 1] != wanted


def planner_events(trace):
    """The planning reviews of a run, as (time, outcome), and the changes of doctrine, as (time, kind)."""
    reviews, changes = [], []
    for entry in trace:
        parts = entry['event'].split('.')
        if parts[:2] == ['military_planners', 'review'] and len(parts) == 3:
            reviews.append((entry['t'], parts[2]))
        elif (
            parts[:2] in (['military_planners', 'forms'], ['military_planners', 'lapses']) and len(parts) == 3
        ):
            changes.append((entry['t'], parts[1]))
    return reviews, changes


def test_dispersed_targets_form_doctrine_at_the_first_review_that_can_with_or_without_ai():
    # A plan on unconnected targets counts on all of the force's attacks, and its targets share little. So its
    # chance is above the planners' acceptance from the start, with AI and without it. Each review then passes,
    # and doctrine forms at the first review that the passes in a row allow, with AI as without it.
    runs = ('dispersed', 'dispersed_no_ai')
    study = catalogue_study('cyber_learning_loop', {'set': {}}, runs=list(runs))
    formed = {}
    for run in runs:
        x = inputs(run)
        start = values_at(run, ['military_planners.best_chance'])['military_planners.best_chance']
        assert start >= x['military_planners.acceptance']
        reviews, changes = planner_events(study.runs[run]['trajectory'].trace)
        needed = int(x['military_planners.passes_needed'])
        assert [outcome for _, outcome in reviews[:needed]] == ['met'] * needed
        assert changes[0] == (reviews[needed - 1][0], 'forms')
        formed[run] = changes[0][0]
    assert formed['dispersed'] == formed['dispersed_no_ai']


@pytest.mark.parametrize('t_years', [0, 3, 25])
def test_the_correlation_of_an_attack_comes_from_its_shared_and_own_steps(t_years):
    # Targets share steps that work with the chance q; given those, each target succeeds on its own with the
    # chance p / q. A simulation of that process must give the model's correlation of two targets.
    x = inputs('ai_fast')
    names = ['effects_program.shared_chance', 'effects_program.within_correlation']
    v = values_at('ai_fast', names, t_years)
    p, q = x['effects_program.success_now'], v['effects_program.shared_chance']
    assert p < q <= 1
    rng = np.random.default_rng(7)
    draws = 400000
    shared = rng.random(draws) < q
    first = shared & (rng.random(draws) < p / q)
    second = shared & (rng.random(draws) < p / q)
    simulated = np.corrcoef(first, second)[0, 1]
    assert simulated == pytest.approx(v['effects_program.within_correlation'], abs=0.01)
    if t_years == 0:
        assert v['effects_program.within_correlation'] == pytest.approx(x['defenders.within_now'], rel=1e-12)


def test_only_tailoring_moves_the_correlation_of_an_attack():
    untailored = values_at(
        'ai_fast', ['effects_program.within_correlation'], 25, {'effects_program.tailoring_end': 0}
    )
    x = inputs('ai_fast')
    assert untailored['effects_program.within_correlation'] == pytest.approx(
        x['defenders.within_now'], rel=1e-12
    )
    tailored = values_at(
        'ai_fast', ['effects_program.within_correlation'], 60, {'effects_program.tailoring_end': 1}
    )
    assert tailored['effects_program.within_correlation'] < 1e-3
