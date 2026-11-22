"""An independent oracle of the scenario's rest point today and of the balances that hold at any rest point. It
imports no engine code.

The specification (the approved plan of the rebuild, the section "Specification" of
scenarios/cyber_learning_loop/README.md, with the fixes of the review of 2026-11) builds today's state as a rest
point from today's inputs, in this order:
- today's work of each stage of an attack sets today's attacks: the experts on attacks over the work of one
  attack, and today's work of each kind of expert sets the size of its group (researchers, operators,
  collection specialists, analysts). No operator is retrained today;
- an attack keeps the targets, the kinds of target system and the correlation of its targets that it was
  built with. Its targets pass initial access, movement inside the network and the effect, and the chain
  holds the attacks next to their targets. So each stock of the chain holds what passes in a year times its
  time (Little's law): the targets, the attacks, and for the attacks held ready and assessed, their targets,
  the targets weighted by their correlation (the spread) and the independent outcomes;
- each pool of capabilities is at rest: each of its six stocks gains in a year what it loses. A flaw that no
  one uses, or that only attacks keep, is lost by discovery, patching and irrelevance; a flaw in use, by
  surveillance or by an attack underway, is lost faster, because the defenders can see it at work. The oracle
  solves the six balances numerically, from the flows of the specification, not from a closed form;
- surveillance's new accesses replace the accesses that it loses; they pass initial access, then movement and
  deployment, and the implants collect while they live; the take waits in a queue for the collection
  specialists. The defenders also find accesses through the shared capabilities that exposed attacks burn,
  so the stocks of accesses follow in order: new accesses, accesses held, deployments, implants;
- today's returns of an operator on attacks and on surveillance are equal, which sets the value of one effect.

`balances` gives, for any state, the residuals of the specification's balance equations of the attack chain,
of the pools, of surveillance, of the lessons, of the defenders' attention and of the splits, with the rates
that the oracle computes from the state; at a rest point of the engine they vanish.

Its values are in years, people, operations, targets, accesses, capabilities and SEV: the units of the
specification, not the engine's execution units. It covers the funding rule that follows current results
(no foresight), peace and no surge, and every rule of the analysts' staffing and of the workforce.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
from scipy.optimize import fsolve

YEAR_H = 8760.0


def sigmoid(z):
    return 1 / (1 + math.exp(-max(-40.0, min(40.0, z))))


@dataclass(frozen=True)
class Inputs:
    """The inputs of the oracle, by the names of the oracle-inputs map."""

    v: dict

    def __getitem__(self, key):
        return self.v[key]


STAGES = ('planning_stage', 'access_stage', 'payload_stage', 'execution_stage', 'assessment_stage')
OPERATOR_STAGES = ('access_stage', 'payload_stage', 'execution_stage')
ANALYST_STAGES = ('planning_stage', 'assessment_stage')
CHANNELS = ('tools_channel', 'infrastructure_channel', 'operators_channel', 'targeting_channel')
POOLS = ('access_pool', 'movement_pool', 'effect_pool', 'collection_pool')
STOCKS = ('fresh', 'spy_used', 'held_shared', 'held_attack', 'kept_shared', 'kept_attack')
# The stocks of the attack chain: targets and attacks in each step, and what the attacks held ready and the
# attacks in assessment carry.
CHAIN = (
    'in_access',
    'accesses',
    'positioned',
    'held_ready',
    'assessing',
    'in_access_attacks',
    'access_attacks',
    'positioned_attacks',
    'held_targets',
    'held_spread',
    'held_outcomes',
    'assessing_targets',
    'assessing_outcomes',
)
SURVEILLANCE = ('accesses_underway', 'accesses_held', 'implants', 'collected')


def progress(x, t_years, time_key='progress_time'):
    """AI progress at time t (years) on one path: access (`progress_time`) or payloads (`payload_time`)."""
    g = 1 - math.exp(-t_years / x[time_key])
    back = 1 - math.exp(-max(t_years - x['reversal_start'], 0.0) / x['reversal_time'])
    return min(max(x['pace'] * (g - x['reversal_depth'] * back), 0.0), 1.0)


def stage(x, name, key):
    return x[f'{name}.{key}']


def stage_time(x, name, g, g2):
    """The time of one stage's work, on its AI path."""
    h = g2 if stage(x, name, 'payload_path') else g
    return stage(x, name, 'time_now') * (stage(x, name, 'time_end') / stage(x, name, 'time_now')) ** h


def lead(x, g, g2):
    """The time to build an attack: the sum of the times of the stages that build it."""
    return sum(stage_time(x, name, g, g2) for name in STAGES if stage(x, name, 'builds'))


def channels(x, g):
    """The attacks that one expert supervises at once, and the compute for each expert-year of AI work."""
    parallel = x['parallel_now'] * (x['parallel_end'] / x['parallel_now']) ** g
    compute = x['compute_now'] * (x['compute_end'] / x['compute_now']) ** g
    return parallel, compute


def ai_unit(x, share, g):
    """The cost of a unit of work as a share of its cost by hand, when AI does `share` of it."""
    parallel, compute = channels(x, g)
    return 1 - share + share * (x['supervision'] / parallel + compute / x['expert_cost'])


def unit_cost(x, name, g, g2):
    """The cost of a stage's work for the attack, as a share of its cost by hand."""
    h = g2 if stage(x, name, 'payload_path') else g
    a = stage(x, name, 'ai_now') + (stage(x, name, 'ai_end') - stage(x, name, 'ai_now')) * h
    return ai_unit(x, a, g)


def target_unit_cost(x, name, g, g2):
    """The cost of a stage's work for each target, as a share of its cost by hand: its own AI share and path
    where the stage splits them, else the share of the work for the attack."""
    if not stage(x, name, 'split_ai'):
        return unit_cost(x, name, g, g2)
    h = g2 if stage(x, name, 'target_payload_path') else g
    a = (
        stage(x, name, 'target_ai_now')
        + (stage(x, name, 'target_ai_end') - stage(x, name, 'target_ai_now')) * h
    )
    return ai_unit(x, a, g)


def correlation(x, g):
    """The correlation of the targets of one attack: a share of today's log-chance of success lies in the
    steps that the targets share, and AI tailors a share of those steps to each target."""
    p0 = x['success_now']
    q0 = p0 / (p0 + x['within_now'] * (1 - p0))
    q = math.exp((1 - x['tailoring_end'] * g) * math.log(q0))
    return p0 * (1 - q) / (q * (1 - p0))


def attribution(x, g):
    miss = 1.0
    for name in CHANNELS:
        now, end = x[f'{name}.chance_now'], x[f'{name}.chance_end']
        miss *= 1 - (now + (end - now) * g)
    return 1 - miss


def ahead(x, lead_time, warning=None):
    """Share of attacks that need access built in advance: a Hill curve of the lead time."""
    return 1 - 1 / (1 + (lead_time / (warning or x['warning_time'])) ** x['waiting_sharpness'])


def waiting(x, lead_time, moment=None, warning=None):
    """The work of an attack with the cost of waiting, as a multiple of its build: the attacks built in advance
    keep their access and lose some of it until their moment."""
    return 1 + ahead(x, lead_time, warning) * (x['access_decay'] + x['upkeep']) / (moment or x['use_rate'])


def targets(x, g):
    return x['targets_now'] * math.exp(g * math.log(x['targets_end'] / x['targets_now']))


def stage_cost(x, name, g, g2, m, moment=None, warning=None):
    """Expert work of one stage for one attack with m targets, before lessons: its work by hand times the human
    share plus the supervised and computed AI share, and times the cost of waiting when its product is held
    ready."""
    work = stage(x, name, 'work') * unit_cost(x, name, g, g2)
    work += stage(x, name, 'target_work') * m * target_unit_cost(x, name, g, g2)
    return work * (waiting(x, lead(x, g, g2), moment, warning) if stage(x, name, 'held') else 1)


def stage_costs(x, g, g2, m, moment=None, warning=None):
    """Expert work of each stage of one attack with m targets, before lessons."""
    return {name: stage_cost(x, name, g, g2, m, moment, warning) for name in STAGES}


def learning(x, name, access_factor_value, effects_gain):
    """The share of a stage's work that is left after lessons: the stage that surveillance also does learns
    from the lessons of access, and the others from the lessons of attacks."""
    return access_factor_value if stage(x, name, 'shared_work') else 1 - x['cost_learning'] * effects_gain


def learned_costs(x, costs, access_factor_value, effects_gain):
    """The work of each stage after lessons."""
    return {name: c * learning(x, name, access_factor_value, effects_gain) for name, c in costs.items()}


def access_factor(x, lessons, lessons0):
    """Wright's law: each doubling of the lessons of access saves the share `access_learning` of its work."""
    return (lessons / lessons0) ** math.log2(1 - x['access_learning'])


def spread(m, rho):
    """The growth of the spread of the outcomes of an attack with m targets whose correlation is rho."""
    return 1 + (m - 1) * rho


def run_cost(x, g):
    """The work to run one implant, as a share of the work by hand."""
    return ai_unit(x, x['run_ai_now'] + (x['run_ai_end'] - x['run_ai_now']) * g, g)


def analysis_unit(x, g, g2):
    """The collection specialists' processing work, as a share of its work by hand, on the slower AI path."""
    share = x['analysis_ai_now'] + (x['analysis_ai_end'] - x['analysis_ai_now']) * g2
    return ai_unit(x, share, g)


def kinds(x, m):
    """Kinds of target system in one attack with m targets: each further target is a new kind with a chance."""
    return 1 + x['diversity'] * max(m - 1, 0.0)


def loss_rates(x, g):
    """The rates (per year) at which the force loses a flaw that it holds: (no one uses it or only attacks keep
    it, in use). Others find it on their own, a patch made for another reason closes it, or its systems stop
    mattering; a flaw in use on targets is also found at work, at its own rate. AI multiplies discovery and
    patching, not irrelevance, by 1 + close_gain at the end of AI progress."""
    closing = 1 + x['close_gain'] * g
    unused = (x['discovery_now'] + x['patch_now']) * closing + x['irrelevance_now']
    in_use = (x['use_discovery_now'] + x['patch_now']) * closing + x['irrelevance_now']
    return unused, in_use


def access_times(x, g, g2):
    """Initial access and movement inside the network split the time of access by one share."""
    total = stage_time(x, 'access_stage', g, g2)
    return x['initial_share'] * total, (1 - x['initial_share']) * total


def one_day(x, pool, g, g2):
    """The chance that a known flaw serves a need of the pool's step: the flaw exists, and the target has not
    fixed it by the time of use. Initial access, movement and the effect each have their own time;
    collection's flaws never get fixed (its pace is zero), so its time does not matter."""
    initial, movement = access_times(x, g, g2)
    years = {
        'access_pool': initial,
        'movement_pool': movement,
        'effect_pool': stage_time(x, 'payload_stage', g, g2),
        'collection_pool': stage_time(x, 'access_stage', g, g2),
    }[pool]
    known, pace = x[f'{pool}.known'], x[f'{pool}.patch_pace']
    return known * (x['residual'] + (1 - x['residual']) * math.exp(-x['fix_rate'] * pace * years))


def today_shares(x, pool):
    """Today's shares of the sources of a zero-day at the pool's step, by mission: (attacks from
    surveillance, attacks reused, surveillance's own, surveillance from attacks). A pool that a mission does
    not use has none of its sources; collection has no attacks, the effect no surveillance."""
    if pool == 'effect_pool':
        return 0.0, x['reuse_source'], 0.0, 0.0
    if pool == 'collection_pool':
        return 0.0, 0.0, x['own_source'], 0.0
    return x['spy_source'], x['reuse_source'], x['own_source'], x['attack_source']


def pool_flows(y, need, shares, exposure, made_rate, loss, available=1.0, passed=1.0):
    """The rates of change of one pool's six stocks at state y, with research left out (it only feeds the
    never-used stock).

    `need` = (attack needs of attacks that wait, attack needs of attacks made at once, surveillance needs) of
    zero-days in a year; `shares` = (attacks from surveillance, attacks from kept, surveillance's own,
    surveillance from kept); `loss` = (rate of a flaw that no one uses or that only attacks keep, rate of a
    flaw in use: by surveillance, which also uses the kept flaws that it shares, or by an attack underway); `available`
    the share of the asks for a never-used capability that the stock serves now; `passed` the share of
    surveillance's units that the other step of its deployment lets pass, since a unit moves only when both
    steps can equip it."""
    fresh, spy, hs, ha, ks, ka = y
    a, a_now, s = need
    q2a, q3a, q2s, q3s = shares
    q4a, q4s = 1 - q2a - q3a, 1 - q2s - q3s
    kept = ks + ka
    part = ks / kept if kept > 0 else 0.0
    e, x, (r, u) = exposure, made_rate, loss
    new_a, new_s = q4a * available, q4s * available * passed
    return np.array(
        [
            -(a + a_now) * new_a - s * new_s - r * fresh,
            s * new_s - a * q2a - u * spy,
            a * q2a + a * q3a * part - (x + u) * hs,
            a * new_a + a * q3a * (1 - part) - (x + u) * ha,
            (1 - e) * x * hs + s * q3s * passed - a * q3a * part - u * ks,
            (1 - e) * x * ha
            + a_now * (1 - e) * new_a
            - s * q3s * passed
            - a * q3a * (1 - part)
            - a_now * e * q3a * (1 - part)
            - r * ka,
        ]
    )


def pool_rest(need, shares, exposure, made_rate, loss, reserve):
    """One pool's stocks at rest, solved numerically from its balances: the never-used stock holds `reserve`
    years of what the missions draw from it, and research replaces what leaves it."""
    a, a_now, s = need
    q2a, q3a, q2s, q3s = shares
    r, u = loss
    draws = (a + a_now) * (1 - q2a - q3a) + s * (1 - q2s - q3s)
    fresh = reserve * draws
    research = draws + r * fresh
    size = max(a + a_now + s, 1.0)
    scale = size / r

    def equations(z):
        y = np.concatenate([[fresh], z * scale])
        rates = pool_flows(y, need, shares, exposure, made_rate, loss)
        return rates[1:] / size

    # A start: each stock's inflow over its rate of loss, as if no kept capability were shared.
    q4a, q4s = 1 - q2a - q3a, 1 - q2s - q3s
    held = (a * q2a / (made_rate + u), a * (q4a + q3a) / (made_rate + u))
    start = (
        np.array(
            [
                max(s * q4s - a * q2a, 0.0) / u,
                *held,
                ((1 - exposure) * made_rate * held[0] + s * q3s) / u,
                max((1 - exposure) * made_rate * held[1] + a_now * (1 - exposure) * q4a - a * q3a, 0.0) / r,
            ]
        )
        / scale
    )
    with warnings.catch_warnings():
        # fsolve warns when it cannot improve a solution that is already at the precision of the floats; the
        # residual below is the test.
        warnings.simplefilter('ignore', RuntimeWarning)
        z = fsolve(equations, start, xtol=1e-13, maxfev=20000)
        z = fsolve(equations, z, xtol=1e-13, maxfev=20000)
    if np.max(np.abs(equations(z))) > 1e-12:
        raise ValueError('the balances of a pool have no rest')
    stocks = dict(zip(STOCKS, [fresh, *(z * scale)]))
    stocks['research'] = research
    return stocks


def burn_loss(x, pool_stocks, made_rate, one_day_chance):
    """The share of surveillance's accesses that the defenders find in a year through one pool: exposed attacks
    burn the share `exposure` of the shared capabilities that they hold, and the defenders find the share
    `find_share` of the accesses that run on each; the accesses that run on zero-days of the pool share the
    capabilities that surveillance uses."""
    in_use = pool_stocks['spy_used'] + pool_stocks['held_shared'] + pool_stocks['kept_shared']
    burned = x['exposure'] * made_rate * pool_stocks['held_shared']
    return x['find_share'] * burned * (1 - one_day_chance) / max(in_use, 0.001)


def today(x):
    """Today's groups, the attack chain, the pools, surveillance's chain, the lessons and the value of one
    effect, at rest. Today's experts on attacks are operators and analysts as the stages say; the researchers
    are part of the agency's experts, whose others deploy implants, plan new accesses or are collection
    specialists, in shares."""
    experts = x['experts']
    m0 = x['targets_now']
    rho0 = correlation(x, 0.0)
    costs = stage_costs(x, 0.0, 0.0, m0)
    n0 = x['share_now'] * experts / sum(costs.values())
    attack_ops = n0 * sum(costs[name] for name in OPERATOR_STAGES)
    attack_analysts = n0 * sum(costs[name] for name in ANALYST_STAGES)
    researchers = x['research_share'] * experts
    agency = (1 - x['share_now']) * experts - researchers
    deployers = x['build_share'] * agency
    planners = x['plan_share'] * x['analysis_share'] * agency
    runners = (1 - x['analysis_share']) * agency - deployers
    processors = (1 - x['plan_share']) * x['analysis_share'] * agency
    analysts = attack_analysts + planners
    # The attack chain: today's attacks pass each stock in its time, each with today's targets, spread and
    # independent outcomes.
    initial, movement = access_times(x, 0.0, 0.0)
    payload = stage_time(x, 'payload_stage', 0.0, 0.0)
    assessment = stage_time(x, 'assessment_stage', 0.0, 0.0)
    pi0 = ahead(x, lead(x, 0.0, 0.0))
    held = pi0 * n0 / x['use_rate']
    chain = {
        'in_access': n0 * m0 * initial,
        'accesses': n0 * m0 * movement,
        'positioned': n0 * m0 * payload,
        'held_ready': held,
        'assessing': n0 * assessment,
        'in_access_attacks': n0 * initial,
        'access_attacks': n0 * movement,
        'positioned_attacks': n0 * payload,
        'held_targets': held * m0,
        'held_spread': held * m0 * spread(m0, rho0),
        'held_outcomes': held * m0 / spread(m0, rho0),
        'assessing_targets': n0 * assessment * m0,
        'assessing_outcomes': n0 * assessment * m0 / spread(m0, rho0),
    }
    # The rate at which each pool's held capabilities leave with the attacks made: the attacks made over the
    # attacks that hold the pool's capabilities. Initial access's capabilities are held from access to the
    # attack's moment; movement's from the end of movement; the effect's only while the attack waits ready.
    made = {
        'access_pool': 1 / (movement + payload + pi0 / x['use_rate']),
        'movement_pool': 1 / (payload + pi0 / x['use_rate']),
        'effect_pool': x['use_rate'],
        'collection_pool': 0.0,
    }
    k0 = kinds(x, m0)
    p1 = {pool: one_day(x, pool, 0.0, 0.0) for pool in POOLS}
    loss = loss_rates(x, 0.0)
    builds = x['accesses_now'] * x['loss_rate']
    pools = {}

    def solve(pool, attack_waits, attack_now, spy):
        need = (attack_waits, attack_now, spy)
        stocks = pool_rest(need, today_shares(x, pool), x['exposure'], made[pool], loss, x['reserve_time'])
        pools[pool] = {**stocks, 'need': need}
        return stocks

    attack = {pool: n0 * k0 * (1 - p1[pool]) for pool in ('access_pool', 'movement_pool', 'effect_pool')}
    # Surveillance's new accesses take their access capabilities at initial access; the defenders then find
    # accesses through the access pool, so the accesses held, and from them the deployments, follow.
    solve('access_pool', attack['access_pool'], 0.0, builds * (1 - p1['access_pool']))
    loss_access = burn_loss(x, pools['access_pool'], made['access_pool'], p1['access_pool'])
    held_accesses = builds / (1 / movement + x['loss_rate'] + loss_access)
    deployed = held_accesses / movement
    solve('movement_pool', attack['movement_pool'], 0.0, deployed * (1 - p1['movement_pool']))
    solve('effect_pool', pi0 * attack['effect_pool'], (1 - pi0) * attack['effect_pool'], 0.0)
    solve('collection_pool', 0.0, 0.0, deployed * (1 - p1['collection_pool']))
    loss_movement = burn_loss(x, pools['movement_pool'], made['movement_pool'], p1['movement_pool'])
    implants = deployed / (x['loss_rate'] + loss_access + loss_movement)
    processed = x['used_now'] * implants
    surveillance = {
        'builds': builds,
        'accesses_underway': builds * initial,
        'accesses_held': held_accesses,
        'deployed': deployed,
        'implants': implants,
        'processed': processed,
        'reach': implants * x['used_now'] / (1 - x['used_now']),
        'collected': processed * x['process_time'],
        'burned': loss_access * (held_accesses + implants) + loss_movement * implants,
        'loss_access': loss_access,
        'loss_movement': loss_movement,
        # Today the operators' hours gain the initial access of today's new accesses and deploy today's
        # implants, so the work of one access is their hours over that work.
        'build_work': deployers / (x['initial_share'] * builds + (1 - x['initial_share']) * deployed),
        'plan_work': planners / builds,
    }
    # Lessons, and the value of one effect from equal returns today.
    lessons0 = x['assessment_reliability'] * n0 * m0 / spread(m0, rho0) / x['forget_rate']
    access0 = (n0 * m0 + x['task_overlap'] * builds) / x['access_forget_rate']
    value_now = (
        agency  # one expert-year of surveillance for each expert of the agency who is not a researcher
    )
    life_value = value_now / (x['accesses_now'] * x['loss_rate'])
    a0 = attribution(x, 0.0)
    cost0 = (
        n0 * a0 * x['sanction_cost'] * (1 + x['escalation'] * n0 * a0) + surveillance['burned'] * life_value
    )
    hits0 = n0 * m0 * x['success_now']
    p0 = x['success_now']
    var0 = (
        (1 - p0) / p0 * spread(m0, rho0) / (n0 * m0 + 1)
        + (1 - p0) ** 2 * x['common_spread'] ** 2
        + (1 - p0) / p0 / (lessons0 + x['prior_strength'] + 1)
    )
    risk0 = 1 / (1 + x['risk_aversion'] / 2 * var0)
    spy_return0 = value_now / deployers
    value = (attack_ops * spy_return0 + cost0) * (1 + hits0 / x['saturation']) / hits0 / risk0
    research = sum(p['research'] for p in pools.values())
    return {
        'n0': n0,
        'm0': m0,
        'rho0': rho0,
        'costs': costs,
        'pi0': pi0,
        'researchers': researchers,
        'attack_ops': attack_ops,
        'deployers': deployers,
        'operators': attack_ops + deployers,
        'share0': attack_ops / (attack_ops + deployers),
        'runners': runners,
        'processors': processors,
        'specialists': runners + processors,
        'planners': planners,
        'analysts': analysts,
        'capacity': analysts / x['load_now'],
        'analyst_share0': attack_analysts / analysts,
        'chain': chain,
        'made': made,
        'one_day': p1,
        'pools': pools,
        'surveillance': surveillance,
        'lessons0': lessons0,
        'access0': access0,
        'value_now': value_now,
        'life_value': life_value,
        'spy_return0': spy_return0,
        'value': value,
        'research': research,
        'finds': research / researchers,
    }


def weight(x, tau):
    r = tau / x['prior_strength']
    if x['exponential_curve']:
        return 1 - 2 ** (-r)
    return 1 - 1 / (1 + r ** x['curve_shape'])


def gain(x, tau, lessons0):
    k, k0 = weight(x, tau), weight(x, lessons0)
    return (k - k0) / (1 - k0)


def attention(x, targets_made, targets_now):
    """The defenders' attention at rest: today's attention times the cap c, times the threat flow T over
    T + c - 1, with T = 1 - f + f M / M0 for the force's share f of today's threat, counted in the targets of
    the attacks made (M in a year, M0 today)."""
    threat = 1 - x['force_share'] + x['force_share'] * targets_made / targets_now
    cap = x['attention_cap']
    return x['alert_now'] * cap * threat / (threat + cap - 1)


def source_shares(today_shares_, today_stocks, stocks):
    """The sources' shares of a zero-day need at the stocks `stocks`: a capability in use serves a need as one
    independent try, so the need is served by those in use with chance 1 - exp(-y), where y grows in
    proportion to the capabilities in use; today's y gives today's shares. Returns (attacks from
    surveillance, attacks from kept, surveillance from kept, attacks' never-used, surveillance's never-used)."""
    q2a, q3a, q2s, q3s = today_shares_

    def tries(share_a, share_b, now_a, now_b, a, b):
        total = share_a + share_b
        if total <= 0:
            return 0.0, 0.0
        scale = -math.log(1 - total)
        ya = scale * share_a / total * (a / now_a if now_a > 0 else 0.0)
        yb = scale * share_b / total * (b / now_b if now_b > 0 else 0.0)
        return ya, yb

    kept, kept_now = (
        stocks['kept_shared'] + stocks['kept_attack'],
        today_stocks['kept_shared'] + today_stocks['kept_attack'],
    )
    ya, yb = tries(q2a, q3a, today_stocks['spy_used'], kept_now, stocks['spy_used'], kept)
    in_use = stocks['spy_used'] + stocks['held_shared'] + stocks['kept_shared']
    in_use_now = today_stocks['spy_used'] + today_stocks['held_shared'] + today_stocks['kept_shared']
    za, zb = tries(q2s, q3s, in_use_now, today_stocks['kept_attack'], in_use, stocks['kept_attack'])
    used_a, used_s = -math.expm1(-(ya + yb)), -math.expm1(-(za + zb))
    from_spy = used_a * ya / (ya + yb) if ya + yb > 0 else 0.0
    from_kept = used_a * yb / (ya + yb) if ya + yb > 0 else 0.0
    spy_from_kept = used_s * zb / (za + zb) if za + zb > 0 else 0.0
    return from_spy, from_kept, spy_from_kept, math.exp(-(ya + yb)), math.exp(-(za + zb))


def hardening(x, t_years, g):
    """The defenders' lasting gains, as a loss of log-odds: a yearly trend and their AI."""
    return x['hardening_rate'] * t_years + x['ai_hardening'] * g


def balances(x, state, t_years):
    """The rates of change of the 47 stocks of the specification at `state` (in the specification's units)
    at time t of a peacetime run, as the oracle computes them from its own rules, each over a size of its
    stock. At a rest point every one vanishes.

    The rules: each step runs at the lower of its stock over its time and the hours left to it after the
    steps farther along; the attacks in each step carry their own targets, and the attacks held ready and
    assessed also carry the spread and the independent outcomes of their targets; the analysts on attacks
    give damage assessment at most its share of the work waiting and plan with what is left; the collection
    specialists process first and run implants with what is left; each zero-day comes from a source with the
    chance that the capabilities in use give, and a step waits for the part of its units whose never-used
    capability the pool cannot give now; research goes to each pool as far as the pool needs it, with a reserve;
    the leaders' and the analysts' splits move toward their targets; idle operators retrain if the leaders
    retrain them."""
    out, found = rates_at(x, state, t_years)
    sizes = {name: max(abs(state[name]), 1.0) for name in out}
    for name in (
        'leadership.attack_share',
        'analysts.attack_share',
        'defenders.alertness',
        'operators.retrained_share',
    ):
        sizes[name] = 1.0
    return {name: rate / sizes[name] for name, rate in out.items()}, found


def rates_at(x, state, t_years):
    """(rates, flows): the rate of change of each stock at `state` (per year, in its own unit) at time t of a
    peacetime run, and the flows that set them."""
    base = today(x)
    g, g2 = progress(x, t_years), progress(x, t_years, 'payload_time')
    m = targets(x, g)
    rho = correlation(x, g)
    unused, in_use = loss_rates(x, g)
    initial, movement = access_times(x, g, g2)
    payload = stage_time(x, 'payload_stage', g, g2)
    assessment = stage_time(x, 'assessment_stage', g, g2)
    pi = ahead(x, lead(x, g, g2))
    moment = x['use_rate']
    tau, know = state['effects_program.know_how'], state['effects_program.access_know_how']
    effects_gain = gain(x, tau, base['lessons0'])
    factor = access_factor(x, know, base['access0'])
    chain = {name: state[f'effects_program.{name}'] for name in CHAIN}

    def size(targets_, attacks_):
        """Targets per attack of a stock: at least one."""
        return max(targets_ / attacks_, 1.0) if attacks_ > 0 else 1.0

    size_i = size(chain['in_access'], chain['in_access_attacks'])
    size_m = size(chain['accesses'], chain['access_attacks'])
    size_e = size(chain['positioned'], chain['positioned_attacks'])
    size_q = size(chain['assessing_targets'], chain['assessing'])
    queue_outcomes = chain['assessing_outcomes'] / chain['assessing'] if chain['assessing'] > 0 else 0.0

    def learned(name, n_targets):
        """The work of one stage for one attack with n_targets, after lessons."""
        return stage_cost(x, name, g, g2, n_targets) * learning(x, name, factor, effects_gain)

    # The work of the attacks that the force starts now has the current targets per attack; the work of each
    # step that an attack is in counts the targets that the attack carries: the effect's for the attacks whose
    # effect the force builds, execution's for the attacks that wait for execution, assessment's for the
    # attacks assessed.
    operator_work = sum(learned(name, m) for name in OPERATOR_STAGES)
    plan, assess = learned('planning_stage', m), learned('assessment_stage', size_q)
    w_effect = learned('payload_stage', size_e)
    asked = moment * chain['held_ready'] + (1 - pi) * chain['positioned_attacks'] / payload
    size_x = size(moment * chain['held_targets'] + (1 - pi) * chain['positioned'] / payload, asked)
    w_run_attack = learned('execution_stage', size_x)
    w_initial = x['initial_share'] * learned('access_stage', m) / m
    w_move = (1 - x['initial_share']) * learned('access_stage', m) / m
    # The groups: the retrained operators leave operations and do analysis at their share of an analyst's work.
    share, analyst_share = state['leadership.attack_share'], state['analysts.attack_share']
    retrained = state['operators.retrained_share'] * base['operators']
    active = base['operators'] - retrained
    hours = share * active
    deployers = (1 - share) * active
    capacity = (base['analysts'] + x['retrain_efficiency'] * retrained) / x['load_now']
    # Analysts on attacks: damage assessment takes at most its share of the work waiting, planning the rest.
    wanted = hours / operator_work
    assessment_asked = chain['assessing'] / assessment * assess
    assessment_part = assessment_asked / (assessment_asked + wanted * plan)
    assessed = min(chain['assessing'] / assessment, analyst_share * capacity * assessment_part / assess)
    planning_left = max(analyst_share * capacity - assessed * assess, 0.0)
    # Operators on attacks: execution, then the effect, then movement, then initial access. The attacks that
    # wait for execution are those held ready whose moment comes and those built on demand.
    served = min(1.0, hours / max(asked * w_run_attack, 1e-9))
    effect_hours = max(hours - served * asked * w_run_attack, 0.0)
    prepare = min(chain['positioned_attacks'] / payload, effect_hours / w_effect)
    move_hours = max(effect_hours - (pi + (1 - pi) * served) * prepare * w_effect, 0.0)
    move = min(chain['accesses'] / movement, move_hours / w_move)
    access_hours = max(move_hours - move * w_move, 0.0)
    access = min(chain['in_access'] / initial, access_hours / w_initial)
    hold, now = pi * prepare, (1 - pi) * prepare * served
    # Surveillance: deployment first, then initial access; the work of a new access charges the deployment
    # that it will need, for the accesses that live until it; the analysts plan the new accesses.
    build_work = (
        base['surveillance']['build_work']
        * unit_cost(x, 'access_stage', g, g2)
        / unit_cost(x, 'access_stage', 0.0, 0.0)
    )
    spy_initial, spy_deploy = x['initial_share'] * build_work, (1 - x['initial_share']) * build_work
    # Planning a new access is the analysis of one target: its work moves with the planning stage's share for
    # each target and its share for the attack, in log terms, by the weight θ of the share for each target.
    theta = x['plan_target_weight']
    plan_work = base['surveillance']['plan_work'] * math.exp(
        theta
        * math.log(target_unit_cost(x, 'planning_stage', g, g2) / target_unit_cost(x, 'planning_stage', 0, 0))
        + (1 - theta) * math.log(unit_cost(x, 'planning_stage', g, g2) / unit_cost(x, 'planning_stage', 0, 0))
    )
    held = state['surveillance_program.accesses_held']
    implants = state['surveillance_program.implants']
    deploy = min(held / movement, deployers / spy_deploy)
    spy_hours = max(deployers - deploy * spy_deploy, 0.0)
    spy_access = min(state['surveillance_program.accesses_underway'] / initial, spy_hours / spy_initial)
    # The pools: each step's needs of zero-days, the sources that serve them, and the share of the asks for a
    # never-used capability that the stock can give now.
    p1 = {pool: one_day(x, pool, g, g2) for pool in POOLS}
    stocks = {pool: {name: state[f'{pool}.{name}'] for name in STOCKS} for pool in POOLS}
    # A target needs one capability for each kind of system of its attack, so the kinds of one attack over its
    # targets; the effect needs one for each kind of the attack.
    zero = {pool: 1 - p1[pool] for pool in POOLS}
    needs = {
        'access_pool': (
            access * kinds(x, size_i) / size_i * zero['access_pool'],
            0.0,
            spy_access * zero['access_pool'],
        ),
        'movement_pool': (
            move * kinds(x, size_m) / size_m * zero['movement_pool'],
            0.0,
            deploy * zero['movement_pool'],
        ),
        'effect_pool': (
            hold * kinds(x, size_e) * zero['effect_pool'],
            now * kinds(x, size_e) * zero['effect_pool'],
            0.0,
        ),
        'collection_pool': (0.0, 0.0, deploy * zero['collection_pool']),
    }
    sources, draws, available, attack_served, spy_served = {}, {}, {}, {}, {}
    for pool in POOLS:
        sources[pool] = source_shares(today_shares(x, pool), base['pools'][pool], stocks[pool])
        _, _, _, fresh_a, fresh_s = sources[pool]
        a, a_now, s = needs[pool]
        draws[pool] = (a + a_now) * fresh_a + s * fresh_s
        if draws[pool] > 0:
            available[pool] = min(1.0, stocks[pool]['fresh'] / (draws[pool] * x['supply_time']))
        else:
            available[pool] = 1.0
        attack_served[pool] = 1 - (1 - p1[pool]) * fresh_a * (1 - available[pool])
        spy_served[pool] = 1 - (1 - p1[pool]) * fresh_s * (1 - available[pool])
    # The force starts only the attacks that the pools can equip, and surveillance only the accesses.
    supply = attack_served['access_pool'] * attack_served['movement_pool'] * attack_served['effect_pool']
    starts = min(wanted, planning_left / plan) * supply
    access_out = access * attack_served['access_pool']
    move_out = move * attack_served['movement_pool']
    effect_out = (hold + now) * attack_served['effect_pool']
    made_now = now * attack_served['effect_pool']
    made_held = moment * chain['held_ready'] * served
    attacks = made_now + made_held
    made_targets = made_now * size_e + moment * chain['held_targets'] * served
    made_spread = spread(size_e, rho)
    out = {
        'effects_program.in_access': starts * m - access_out,
        'effects_program.in_access_attacks': starts - access_out / size_i,
        'effects_program.accesses': access_out - move_out,
        'effects_program.access_attacks': access_out / size_i - move_out / size_m,
        'effects_program.positioned': move_out - effect_out * size_e,
        'effects_program.positioned_attacks': move_out / size_m - effect_out,
        'effects_program.held_ready': hold * attack_served['effect_pool'] - made_held,
        'effects_program.held_targets': (
            hold * attack_served['effect_pool'] * size_e - moment * chain['held_targets'] * served
        ),
        'effects_program.held_spread': (
            hold * attack_served['effect_pool'] * size_e * made_spread
            - moment * chain['held_spread'] * served
        ),
        'effects_program.held_outcomes': (
            hold * attack_served['effect_pool'] * size_e / made_spread
            - moment * chain['held_outcomes'] * served
        ),
        'effects_program.assessing': attacks - assessed,
        'effects_program.assessing_targets': made_targets - assessed * size_q,
        'effects_program.assessing_outcomes': (
            made_now * size_e / made_spread
            + moment * chain['held_outcomes'] * served
            - assessed * queue_outcomes
        ),
    }
    # The made attacks and the attacks that hold each pool's capabilities: initial access's capabilities from
    # access to the attack's moment, movement's from the end of movement, the effect's while the attack waits.
    holders = {
        'access_pool': chain['access_attacks'] + chain['positioned_attacks'] + chain['held_ready'],
        'movement_pool': chain['positioned_attacks'] + chain['held_ready'],
    }
    made_rate = {
        'access_pool': attacks / holders['access_pool'],
        'movement_pool': attacks / holders['movement_pool'],
        'effect_pool': moment * served,
        'collection_pool': 0.0,
    }
    # A unit of surveillance's deployment moves only when both of its steps can equip it.
    passed = {
        'access_pool': 1.0,
        'movement_pool': spy_served['collection_pool'],
        'effect_pool': 1.0,
        'collection_pool': spy_served['movement_pool'],
    }
    # Research: each pool asks for what the missions draw from its never-used stock, what the defenders find
    # there, and what restores its reserve of `reserve_time` years of draws; the researchers do no more than
    # the pools ask, while they can.
    reserve = x['reserve_time']
    asks = {
        pool: max(
            draws[pool]
            + unused * stocks[pool]['fresh']
            + (reserve * draws[pool] - stocks[pool]['fresh']) / reserve,
            0.0,
        )
        for pool in POOLS
    }
    output = base['researchers'] * base['finds'] * x['gain_end'] ** g
    total = sum(asks.values())
    for pool in POOLS:
        from_spy, from_kept, spy_kept, _, fresh_s = sources[pool]
        shares = (from_spy, from_kept, 1 - spy_kept - fresh_s, spy_kept)
        rates = pool_flows(
            [stocks[pool][name] for name in STOCKS],
            needs[pool],
            shares,
            x['exposure'],
            made_rate[pool],
            (unused, in_use),
            available[pool],
            passed[pool],
        )
        rates[0] += asks[pool] * min(1.0, output / total) if total > 0 else 0.0
        for name, rate in zip(STOCKS, rates):
            out[f'{pool}.{name}'] = rate
    loss_access = burn_loss(x, stocks['access_pool'], made_rate['access_pool'], p1['access_pool'])
    loss_movement = burn_loss(x, stocks['movement_pool'], made_rate['movement_pool'], p1['movement_pool'])
    # The accesses that surveillance's operators can start: each charges its initial access and the deployment
    # that it needs if it lives until then.
    survival = 1 / (1 + (x['loss_rate'] + loss_access) * movement)
    builds = deployers / (spy_initial + spy_deploy * survival)
    new = (
        min(builds, (1 - analyst_share) * capacity / plan_work)
        * spy_served['access_pool']
        * spy_served['movement_pool']
        * spy_served['collection_pool']
    )
    gained = spy_access * spy_served['access_pool']
    deployed = deploy * spy_served['movement_pool'] * spy_served['collection_pool']
    # The collection specialists process the take first and run implants with what is left.
    process_work = (
        base['processors']
        / base['surveillance']['processed']
        * (analysis_unit(x, g, g2) / analysis_unit(x, 0.0, 0.0))
    )
    run_work = base['runners'] / base['surveillance']['reach'] * run_cost(x, g) / run_cost(x, 0.0)
    processed = min(
        state['surveillance_program.collected'] / x['process_time'], base['specialists'] / process_work
    )
    reach = max(base['specialists'] - processed * process_work, 0.0) / run_work
    used = implants * reach / (implants + reach)
    out['surveillance_program.accesses_underway'] = new - gained
    out['surveillance_program.accesses_held'] = gained - deployed - (x['loss_rate'] + loss_access) * held
    out['surveillance_program.implants'] = (
        deployed - (x['loss_rate'] + loss_access + loss_movement) * implants
    )
    out['surveillance_program.collected'] = used - processed
    # Lessons of effects from the independent outcomes of the attacks assessed, and lessons of access from the
    # accesses that attacks and surveillance gain; the defenders' attention follows the targets attacked.
    forgetting = x['forget_rate'] * (1 - x['burn_share'] + x['burn_share'] * attacks / base['n0'])
    out['effects_program.know_how'] = (
        x['assessment_reliability'] * assessed * queue_outcomes - forgetting * tau
    )
    out['effects_program.access_know_how'] = (
        access_out + x['task_overlap'] * gained - x['access_forget_rate'] * know
    )
    alertness = state['defenders.alertness']
    out['defenders.alertness'] = x['calm_rate'] * (
        attention(x, made_targets, base['n0'] * base['m0']) - alertness
    )
    # The value of the attacks of a year and its costs, and surveillance's value.
    p = sigmoid(
        math.log(x['success_now'] / (1 - x['success_now']))
        + (
            math.log(x['success_best'] / (1 - x['success_best']))
            - math.log(x['success_now'] / (1 - x['success_now']))
        )
        * effects_gain
        - (alertness - x['alert_now'])
        - hardening(x, t_years, g)
    )
    hits = made_targets * p
    value = (
        x['value_scale']
        * base['value']
        * hits
        / (1 + hits / x['saturation'])
        * (1 + x['value_learning']) ** effects_gain
    )
    variance = (
        (1 - p) / p * spread(m, rho) / (made_targets + 1)
        + (1 - p) ** 2 * x['common_spread'] ** 2
        + p * (1 - p) / (tau + x['prior_strength'] + 1) / p**2
    )
    risk_value = value / (1 + x['risk_aversion'] / 2 * variance)
    counted = risk_value * math.exp(x['assessment_bias_change'] * g)
    a_t = attribution(x, g)
    sanctions = a_t * x['sanction_cost'] * (1 + x['escalation'] * attacks * a_t)
    burned = loss_access * (held + implants) + loss_movement * implants
    costs = attacks * sanctions + burned * base['life_value']
    spying = (
        base['value_now']
        * (processed / base['surveillance']['processed']) ** x['returns_scale']
        * math.exp(-x['alert_sensitivity'] * (alertness - x['alert_now'] + hardening(x, t_years, g)))
    )
    # The analysts' split moves toward the target of the staffing rule. Each mission's need: attacks' is the
    # analysis of the attacks that the operators can start, or of the queue if it is larger; surveillance's is
    # the planning of the accesses that its operators can start.
    attack_need = max(chain['assessing'] / assessment, wanted) * assess + wanted * plan
    spy_need = builds * plan_work
    if x['fixed_split']:
        analyst_target = base['analyst_share0']
    elif x['by_value']:
        # The value of one more analyst-year on each mission: on attacks, one more attack at rest, less its
        # costs, over the analysis work of an attack; on surveillance, the value of the take of one more
        # access, over its planning. The priority is a logistic curve of the log of their ratio; each mission
        # gets its work first in proportion to its priority, with today's slack.
        margin = (
            risk_value / attacks / (1 + hits / x['saturation'])
            - sanctions
            - burned * base['life_value'] / attacks
        )
        attack_value = max(margin, 0.0) / (plan + assess)
        spy_value = spying * x['returns_scale'] * reach / (implants + reach) / (new * plan_work)
        priority = sigmoid(
            x['priority_steepness'] * math.log(max(attack_value, 1e-300) / max(spy_value, 1e-300))
        )
        first_attacks = min(attack_need / base['analysts'], 1.0)
        first_spying = max(1 - spy_need / base['analysts'], 0.0)
        analyst_target = priority * first_attacks + (1 - priority) * first_spying
    else:
        analyst_target = attack_need / (attack_need + spy_need)
    out['analysts.attack_share'] = (analyst_target - analyst_share) / x['analyst_adjust_time']
    # The leaders' split moves toward the target that the return gap, relative to surveillance's current
    # return, gives.
    spy_return = spying / deployers
    gap = ((counted - costs) / hours - spy_return) / spy_return
    center = math.log((base['share0'] - x['share_floor']) / (x['share_ceiling'] - base['share0']))
    target = x['share_floor'] + (x['share_ceiling'] - x['share_floor']) * sigmoid(
        x['steepness'] * gap + center
    )
    out['leadership.attack_share'] = (target - share) / x['adjust_time']
    # Operators whose hours wait for the analysts to plan their operations retrain, if the leaders retrain them.
    idle = hours * max(1 - starts / wanted, 0.0) + deployers * max(1 - new / builds, 0.0)
    out['operators.retrained_share'] = idle / base['operators'] / x['retrain_time'] if x['retrains'] else 0.0
    return out, {
        'starts': starts,
        'wanted': wanted,
        'attacks': attacks,
        'made_targets': made_targets,
        'targets': m,
        'correlation': rho,
        'access': access,
        'move': move,
        'prepare': prepare,
        'served': served,
        'assessed': assessed,
        'supply': supply,
        'available': available,
        'new': new,
        'builds': builds,
        'deploy': deploy,
        'spy_access': spy_access,
        'processed': processed,
        'used': used,
        'idle': idle,
        'analyst_target': analyst_target,
        'target': target,
        'gap': gap,
    }
