"""The scenario's pools of capabilities: identities and properties of the specification.

A capability is a flaw that the defenders do not know, with the tools that use it. Each step of an
operation has a pool. A capability is never used, used by surveillance, held by an attack underway, kept
from an earlier attack that was not exposed, or burned; the held and kept ones are split by whether
surveillance also uses them. Each zero-day that a step needs comes from a capability already in use or a
never-used one, and each step moves in one part for each source, together with that source's stock. A step
moves whole attacks: each attack carries its targets, and it needs one capability for each kind of system of
its targets. The researchers refill each pool to its need, and a pool whose never-used stock runs short
holds back only the parts that need a never-used capability. These tests check the flows of each stock at
admissible states away from rest, and the properties that follow from the specification, without a value
computed from an authored default."""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin.core import expr
from napkin.dynamics import vector_field
from tests.helpers import catalogue_model

YEAR_H = 8760.0
POOLS = ('access_pool', 'movement_pool', 'effect_pool', 'collection_pool')
STOCKS = ('fresh', 'spy_used', 'held_shared', 'held_attack', 'kept_shared', 'kept_attack')


def field_of(run, values=None):
    return vector_field(catalogue_model('cyber_learning_loop'), run, values)


def inputs(run, values=None):
    return catalogue_model('cyber_learning_loop').resolve(run, values).parameter_values


def values_at(field, names, t_years, y):
    program = field.field.values_program([expr.ref(name) for name in names])
    return dict(zip(names, program(t_years * YEAR_H, y)))


def flows_at(field, t_years, y):
    """The rates of every quantity and the delivered rate of every flow at a state, per hour."""
    rates = field.rates_of(y, t_years * YEAR_H)
    return rates, dict(zip(field.system.flow_ids, field.field.delivered))


def flow_name(fid):
    """The name of a flow without the number of one of its moves."""
    head, _, tail = fid.rpartition('.')
    return head if tail.isdigit() else fid


def draws_from(system, pool):
    """The moves that take never-used capabilities of a pool for the steps of the missions."""
    return [
        fid
        for fid in system.flow_ids
        if system.flows[fid].source == f'{pool}.fresh' and not fid.endswith('.found_fresh')
    ]


def kinds(diversity, size):
    """The expected kinds of target system of an attack on `size` targets: its first target is one kind, and
    each further target is a new kind with the chance `diversity`."""
    return 1 + diversity * max(size - 1, 0)


# Stocks that no flow ever fills: no surveillance uses the effect's capabilities, and no attack holds or keeps
# collection's. They stay at zero in every run, so the states of these tests keep them there.
EMPTY = (
    'effect_pool.spy_used',
    'effect_pool.held_shared',
    'effect_pool.kept_shared',
    'collection_pool.held_shared',
    'collection_pool.held_attack',
    'collection_pool.kept_shared',
    'collection_pool.kept_attack',
)
# The steps of the attack chain: the stock of the targets in each step, and the stock of their attacks.
CARRIED = (
    ('effects_program.in_access', 'effects_program.in_access_attacks'),
    ('effects_program.accesses', 'effects_program.access_attacks'),
    ('effects_program.positioned', 'effects_program.positioned_attacks'),
)
# The attacks held ready and under assessment: the stock of the attacks, of their targets, of the spread of
# their outcomes (none for assessment) and of their independent outcomes.
WAITING = (
    ('held_ready', 'held_targets', 'held_spread', 'held_outcomes'),
    ('assessing', 'assessing_targets', None, 'assessing_outcomes'),
)


def random_states(field, count, seed):
    """Seeded admissible whole states: the active stocks within three sizes of the start and the bounds. The
    never-used capabilities of each pool stay at half of today's or more, so that each pool serves all that
    it is asked, and the stocks that no flow fills stay empty. Each attack has between one and 40 targets,
    and the targets of each attack held ready or under assessment have outcomes that correlate by a share
    between zero and one: m targets with the correlation rho spread the outcomes of the attack by
    m (1 + (m - 1) rho) and give m / (1 + (m - 1) rho) independent outcomes."""
    s = field.system
    rng = np.random.default_rng(seed)
    low = np.maximum(field.lower, field.start - 3 * field.scales)
    high = np.minimum(field.upper, field.start + 3 * field.scales)
    fresh = np.array([name.endswith('.fresh') for name in field.names])
    low = np.where(fresh, np.maximum(low, field.start / 2), low)
    empty = np.array([name in EMPTY for name in field.names])
    high = np.where(empty, 0, high)
    low = np.where(empty, 0, low)
    for _ in range(count):
        y = field.full(low + (high - low) * rng.random(len(field.start)))
        for targets, attacks in CARRIED:
            y[s.index[attacks]] = y[s.index[targets]] / rng.uniform(1, 40)
        for attacks, targets, spread, outcomes in WAITING:
            size, rho = rng.uniform(1, 40), rng.uniform(0, 1)
            n = y[s.index[f'effects_program.{attacks}']]
            y[s.index[f'effects_program.{targets}']] = n * size
            if spread:
                y[s.index[f'effects_program.{spread}']] = n * size * (1 + (size - 1) * rho)
            y[s.index[f'effects_program.{outcomes}']] = n * size / (1 + (size - 1) * rho)
        yield y


@pytest.mark.parametrize(('run', 't_years'), [('no_ai', 0), ('ai_fast', 3), ('ai_slow', 12), ('wartime', 2)])
def test_capabilities_enter_a_pool_only_by_research_and_leave_it_only_by_burns_and_finds(run, t_years):
    # The moves between the states of a pool (draws, reuse, the keeping of an unexposed attack's capabilities)
    # only shift capabilities inside it: only the researchers' finds come in, and only the burns and what
    # others find go out. So the capabilities of a pool that are not burned change by the researchers' finds
    # for it, less the burns, less what others find of every stock.
    field = field_of(run)
    s = field.system
    for pool in POOLS:
        stocks = {f'{pool}.{stock}' for stock in STOCKS}
        for fid in s.flow_ids:
            source, target = s.flows[fid].source, s.flows[fid].target
            if target in stocks and source not in stocks:
                assert fid == f'{pool}.research'
            if source in stocks and target not in stocks:
                assert target == f'{pool}.burned' or (target is None and fid.startswith(f'{pool}.found_'))
    for y in random_states(field, 10, seed=51):
        rates, delivered = flows_at(field, t_years, y)
        for pool in POOLS:
            change = sum(rates[s.index[f'{pool}.{stock}']] for stock in STOCKS)
            held = sum(y[s.index[f'{pool}.{stock}']] for stock in STOCKS)
            burned = rates[s.index[f'{pool}.burned']]
            found = sum(delivered[fid] for fid in s.flow_ids if fid.startswith(f'{pool}.found_'))
            assert burned >= 0 and found >= 0
            expected = delivered[f'{pool}.research'] - burned - found
            assert change == pytest.approx(expected, rel=1e-9, abs=1e-12 * max(held, 1)), pool


# Explicit rates of the three routes, inside their ranges, to show that one factor of AI multiplies every rate.
ROUTES = {
    'defenders.discovery_now': 0.1,
    'defenders.use_discovery_now': 0.4,
    'defenders.patch_now': 0.07,
    'defenders.irrelevance_now': 0.02,
}


def losses(run, values, t_years):
    """The inputs of a run and the yearly rates at which a stockpiled flaw and a flaw in use are lost, today
    and at time t, with AI progress at time t."""
    field = field_of(run, values)
    names = ['defenders.rediscovery', 'defenders.use_rediscovery', 'ai_tools.progress']
    rates = {}
    for t in (0, t_years):
        v = values_at(field, names, t, field.base)
        rates[t] = (v['defenders.rediscovery'] * YEAR_H, v['defenders.use_rediscovery'] * YEAR_H)
    return field.rs.parameter_values, rates, v['ai_tools.progress']


def closing(x, stockpiled):
    """The factor by which discovery and patching of a stockpiled flaw have grown since today."""
    return (stockpiled - x['defenders.irrelevance_now']) / (
        x['defenders.discovery_now'] + x['defenders.patch_now']
    )


@pytest.mark.parametrize(
    ('run', 't_years'), [('no_ai', 12), ('ai_fast', 3), ('ai_slow', 12), ('ai_fast', 60)]
)
def test_a_flaw_is_lost_by_three_routes_and_ai_speeds_only_discovery_and_patching(run, t_years):
    # A flaw is lost when others find it, when a patch made for another reason closes it, or when its systems
    # leave service or stop mattering. The routes compete, so a flaw is lost at the sum of their rates. A flaw
    # in use can also be found at work, so its discovery has a rate of its own. AI multiplies discovery and
    # patching by one factor: one today and without AI progress, one plus the input gain at the end of AI
    # progress. It leaves irrelevance as it is.
    factors = []
    for values in (None, ROUTES):
        x, rates, progress = losses(run, values, t_years)
        found, patched, gone = (
            x[f'defenders.{name}'] for name in ('discovery_now', 'patch_now', 'irrelevance_now')
        )
        found_in_use = x['defenders.use_discovery_now']
        assert rates[0] == pytest.approx((found + patched + gone, found_in_use + patched + gone), rel=1e-12)
        stockpiled, in_use = rates[t_years]
        factor = closing(x, stockpiled)
        assert (in_use - gone) / (found_in_use + patched) == pytest.approx(factor, rel=1e-12)
        factors.append(factor)
    # The factor does not depend on the rates that it multiplies.
    assert factors[1] == pytest.approx(factors[0], rel=1e-12)
    gain = x['defenders.close_gain']
    if x['ai_tools.pace'] == 0:
        assert factors[0] == pytest.approx(1, rel=1e-12)
    else:
        assert 1 < factors[0] <= 1 + gain
    if progress > 1 - 1e-6:
        assert factors[0] == pytest.approx(1 + gain, rel=1e-6)
    # The input gain alone sets the factor's growth: half the gain halves it, and no gain leaves today's rates.
    for scale in (0, 0.5):
        x, rates, _ = losses(run, {'defenders.close_gain': scale * gain}, t_years)
        assert closing(x, rates[t_years][0]) - 1 == pytest.approx(
            scale * (factors[0] - 1), rel=1e-9, abs=1e-12
        )
    # Without discovery and patching, a stockpiled flaw is lost only as its systems leave service, whatever AI does.
    x, rates, _ = losses(run, {'defenders.discovery_now': 0, 'defenders.patch_now': 0}, t_years)
    assert rates[t_years][0] == pytest.approx(x['defenders.irrelevance_now'], rel=1e-12)


# What others find of each stock, by the way in which the stock waits: unused, or in use on targets.
STOCKPILED = {'fresh': 'found_fresh', 'kept_attack': 'found_kept_attack'}
IN_USE = {
    'spy_used': 'found_spy',
    'held_shared': 'found_held_shared',
    'held_attack': 'found_held_attack',
    'kept_shared': 'found_kept_shared',
}


@pytest.mark.parametrize(('run', 't_years'), [('no_ai', 0), ('ai_fast', 3)])
def test_a_stockpiled_flaw_and_a_flaw_in_use_are_lost_at_their_own_rates(run, t_years):
    # The never-used capabilities and those that only attacks kept from earlier attacks wait unused, so others
    # find them only by the routes of a stockpiled flaw. Surveillance runs its capabilities on targets, also
    # those that it took from the attacks' kept capabilities, and the attacks underway hold theirs on their
    # targets, so the defenders can also find all of those at work.
    field = field_of(run)
    s = field.system
    v = values_at(field, ['defenders.rediscovery', 'defenders.use_rediscovery'], t_years, field.base)
    stockpiled, in_use = v['defenders.rediscovery'], v['defenders.use_rediscovery']
    for y in random_states(field, 4, seed=59):
        _, delivered = flows_at(field, t_years, y)
        for pool in POOLS:
            for rate, stocks in ((stockpiled, STOCKPILED), (in_use, IN_USE)):
                for stock, flow in stocks.items():
                    assert s.flows[f'{pool}.{flow}'].source == f'{pool}.{stock}'
                    assert delivered[f'{pool}.{flow}'] == pytest.approx(
                        rate * y[s.index[f'{pool}.{stock}']], rel=1e-9, abs=1e-18
                    )


# Inputs inside their ranges that move today's rest of the pools: a flaw in use lost far faster than a stockpiled
# one, attacks that expose half of what they use, much reuse, and a flaw in use lost as fast as a stockpiled one.
REST = [
    None,
    {
        'defenders.use_discovery_now': 2,
        'defenders.discovery_now': 0.01,
        'defenders.patch_now': 0.01,
        'defenders.irrelevance_now': 0.01,
    },
    {'effects_program.exposure': 0.5},
    {'effects_program.reuse_source': 0.15, 'surveillance_program.attack_source': 0.0005},
    {
        'effects_program.spy_source': 0.3,
        'surveillance_program.own_source': 0.5,
        'defenders.use_discovery_now': 0.057,
    },
]
TODAY = (
    'attack_need_now',
    'at_once_need_now',
    'spy_need_now',
    'attack_spy_now',
    'attack_kept_now',
    'spy_own_now',
    'spy_kept_now',
    'made_rate_now',
)


@pytest.mark.parametrize('values', REST)
def test_todays_pools_are_at_rest_by_the_balances_of_their_flows(values):
    # Today each stock of each pool gains in a year what it loses. Today's needs and source shares, the share of
    # the attacks that hold the pool's capabilities that the force makes in a year, the exposure and the two
    # rates of loss give the balance of each stock, which must vanish at today's stocks:
    # - surveillance's own capabilities gain its never-used draws, and lose the attacks' draws and what others find;
    # - the held stocks gain the attacks' draws from their sources, and lose what the force makes and what others
    #   find;
    # - the kept stocks gain what hidden attacks keep and lose what attacks reuse and what others find. The kept
    #   capabilities that only attacks used also lose surveillance's draws, which the shared ones gain;
    # - the never-used stock holds the draws of the reserve time.
    # Surveillance uses the shared kept capabilities, so they are lost at the rate of a flaw in use and the others
    # at the rate of a stockpiled flaw: the split of the kept stock comes from two balances.
    field = field_of('no_ai', values)
    s = field.system
    x = field.rs.parameter_values
    patched, gone = x['defenders.patch_now'], x['defenders.irrelevance_now']
    stockpiled = (x['defenders.discovery_now'] + patched + gone) / YEAR_H
    in_use = (x['defenders.use_discovery_now'] + patched + gone) / YEAR_H
    exposure, reserve = x['effects_program.exposure'], x['researchers.reserve_time'] * YEAR_H
    rates, _ = flows_at(field, 0, field.base)
    for pool in POOLS:
        v = values_at(field, [f'{pool}.{name}' for name in TODAY], 0, field.base)
        need, at_once, spy, from_spy, from_kept, own, spy_kept, made = (v[f'{pool}.{name}'] for name in TODAY)
        stock = {name: field.base[s.index[f'{pool}.{name}']] for name in STOCKS}
        assert all(value >= 0 for value in stock.values())
        kept = stock['kept_shared'] + stock['kept_attack']
        shared = stock['kept_shared'] / kept if kept > 0 else 0
        unused = 1 - from_spy - from_kept
        balance = {
            'spy_used': spy * (1 - own - spy_kept) - need * from_spy - in_use * stock['spy_used'],
            'held_shared': need * (from_spy + from_kept * shared) - (made + in_use) * stock['held_shared'],
            'held_attack': need * (1 - from_spy - from_kept * shared)
            - (made + in_use) * stock['held_attack'],
            'kept_shared': (1 - exposure) * made * stock['held_shared']
            + spy * spy_kept
            - need * from_kept * shared
            - in_use * stock['kept_shared'],
            'kept_attack': (1 - exposure) * (made * stock['held_attack'] + at_once * unused)
            - (need + exposure * at_once) * from_kept * (1 - shared)
            - spy * spy_kept
            - stockpiled * stock['kept_attack'],
            'fresh': (stock['fresh'] - reserve * ((need + at_once) * unused + spy * (1 - own - spy_kept)))
            / reserve,
        }
        scale = need + at_once + spy
        for name, residual in balance.items():
            assert residual == pytest.approx(0, abs=1e-12 * scale), (pool, name)
            # The engine's own flows agree: each stock of the pool stays as it is.
            assert rates[s.index[f'{pool}.{name}']] == pytest.approx(0, abs=1e-12 * scale), (pool, name)


@pytest.mark.parametrize(('run', 't_years'), [('no_ai', 0), ('ai_fast', 4), ('wartime', 1)])
def test_each_pool_asks_the_researchers_for_its_draws_its_losses_and_its_reserve(run, t_years):
    # A pool asks for the never-used capabilities that the missions draw from it and that others find, and for
    # what brings its never-used stock to a reserve of the draws of the reserve time, within the reserve time.
    # It asks for nothing while its stock is far above the reserve. The researchers give each pool what it
    # asks while they can, and else share their output in proportion to the asks. So, while they can, the
    # never-used stock moves toward its reserve at the pace of the reserve time.
    field = field_of(run)
    s = field.system
    x = inputs(run)
    reserve = x['researchers.reserve_time'] * YEAR_H
    supply = x['researchers.supply_time'] * YEAR_H
    found = values_at(field, ['defenders.rediscovery'], t_years, field.base)['defenders.rediscovery']
    draws = {pool: draws_from(s, pool) for pool in POOLS}
    for y in random_states(field, 8, seed=52):
        rates, delivered = flows_at(field, t_years, y)
        output = values_at(field, ['researchers.output'], t_years, y)['researchers.output']
        stock = {pool: y[s.index[f'{pool}.fresh']] for pool in POOLS}
        drawn = {pool: sum(delivered[fid] for fid in draws[pool]) for pool in POOLS}
        asks = {}
        for pool in POOLS:
            # The stock serves every ask within the supply time, so the draws are the asks.
            assert drawn[pool] * supply < stock[pool]
            asks[pool] = max(
                drawn[pool] + found * stock[pool] + (reserve * drawn[pool] - stock[pool]) / reserve, 0
            )
        total = sum(asks.values())
        given = {pool: delivered[f'{pool}.research'] for pool in POOLS}
        assert sum(given.values()) == pytest.approx(min(total, output), rel=1e-9, abs=1e-15)
        for pool in POOLS:
            share = min(1, output / total) if total > 0 else 1
            assert given[pool] == pytest.approx(asks[pool] * share, rel=1e-9, abs=1e-15)
            if asks[pool] > 0 and total <= output:
                toward = (reserve * drawn[pool] - stock[pool]) / reserve
                assert rates[s.index[f'{pool}.fresh']] == pytest.approx(
                    toward, rel=1e-9, abs=1e-12 * stock[pool] / reserve
                )


def test_the_pools_share_a_shortfall_of_the_researchers_in_proportion_to_their_asks():
    # Today the researchers find what the pools need at rest. With every never-used stock at a tenth of today's,
    # each pool asks for its draws and for most of its reserve, more than the researchers find. They then share
    # their output in proportion to the asks, and every pool's never-used stock still grows.
    field = field_of('no_ai')
    s = field.system
    x = inputs('no_ai')
    reserve = x['researchers.reserve_time'] * YEAR_H
    found = values_at(field, ['defenders.rediscovery'], 0, field.base)['defenders.rediscovery']
    y = field.base.copy()
    for pool in POOLS:
        y[s.index[f'{pool}.fresh']] /= 10
    rates, delivered = flows_at(field, 0, y)
    output = values_at(field, ['researchers.output'], 0, y)['researchers.output']
    asks = {}
    for pool in POOLS:
        stock = y[s.index[f'{pool}.fresh']]
        drawn = sum(delivered[fid] for fid in draws_from(s, pool))
        asks[pool] = drawn + found * stock + (reserve * drawn - stock) / reserve
    total = sum(asks.values())
    assert total > output
    assert sum(delivered[f'{pool}.research'] for pool in POOLS) == pytest.approx(output, rel=1e-9)
    for pool in POOLS:
        assert delivered[f'{pool}.research'] == pytest.approx(output * asks[pool] / total, rel=1e-9)
        assert rates[s.index[f'{pool}.fresh']] > 0


STEPS = {
    # step: (pool, the stock of the targets in the step, the stock of their attacks)
    'effects_program.access': (
        'access_pool',
        'effects_program.in_access',
        'effects_program.in_access_attacks',
    ),
    'effects_program.move': ('movement_pool', 'effects_program.accesses', 'effects_program.access_attacks'),
}
PAIRS = {
    'spy': ('spy_used', 'held_shared'),
    'kept_shared': ('kept_shared', 'held_shared'),
    'kept_attack': ('kept_attack', 'held_attack'),
    'new': ('fresh', 'held_attack'),
}


@pytest.mark.parametrize(('run', 't_years'), [('ai_fast', 2), ('ai_slow', 10), ('wartime', 1)])
def test_each_part_of_an_attack_step_moves_whole_attacks_with_their_targets_and_capabilities(run, t_years):
    # A step moves whole attacks: each part of it moves targets, their attacks in the same proportion, and
    # one capability of its own source for each kind of system of each attack, from that source to the held
    # stock. The size of an attack is that of the attacks in the step. The parts add up to the step, and
    # their shares are the one-day share and the shares of the other sources.
    field = field_of(run)
    s = field.system
    diversity = inputs(run)['effects_program.diversity']
    for y in random_states(field, 6, seed=53):
        _, delivered = flows_at(field, t_years, y)
        for step, (pool, targets, attacks) in STEPS.items():
            size = y[s.index[targets]] / y[s.index[attacks]]
            assert size >= 1
            v = values_at(
                field,
                [
                    f'{pool}.{name}'
                    for name in ('one_day', 'attack_from_spy', 'attack_from_kept', 'attack_from_fresh')
                ],
                t_years,
                y,
            )
            for key in ('known', *PAIRS):
                moved = delivered[f'{step}_{key}.0']
                assert delivered[f'{step}_{key}.1'] == pytest.approx(moved / size, rel=1e-9, abs=1e-15)
            for key, (source, target) in PAIRS.items():
                pair = s.flows[f'{step}_{key}.2']
                assert (pair.source, pair.target) == (f'{pool}.{source}', f'{pool}.{target}')
                assert delivered[f'{step}_{key}.2'] == pytest.approx(
                    delivered[f'{step}_{key}.1'] * kinds(diversity, size), rel=1e-9, abs=1e-15
                )
            # The source shares of the step's zero-days add up to one, and one-days take nothing from the pool.
            zero_day = (
                v[f'{pool}.attack_from_spy'] + v[f'{pool}.attack_from_kept'] + v[f'{pool}.attack_from_fresh']
            )
            assert zero_day == pytest.approx(1, rel=1e-12)
            total = delivered[f'{step}_known.0'] + sum(delivered[f'{step}_{key}.0'] for key in PAIRS)
            if total > 0:
                assert delivered[f'{step}_known.0'] / total == pytest.approx(v[f'{pool}.one_day'], rel=1e-9)
                kept = delivered[f'{step}_kept_shared.0'] + delivered[f'{step}_kept_attack.0']
                assert kept / total == pytest.approx(
                    (1 - v[f'{pool}.one_day']) * v[f'{pool}.attack_from_kept'], rel=1e-9, abs=1e-12
                )


EFFECT_MOVES = {
    # a capability move of a part of the effect: (its source, its target, the share of the capabilities)
    'prepare_kept.6': ('kept_attack', 'held_attack', 'all'),
    'prepare_new.6': ('fresh', 'held_attack', 'all'),
    'now_kept.5': ('kept_attack', 'burned', 'exposed'),
    'now_new.5': ('fresh', 'burned', 'exposed'),
    'now_new.6': ('fresh', 'kept_attack', 'hidden'),
}


def test_the_effect_turns_the_targets_of_an_attack_into_one_attack_with_one_capability_for_each_kind():
    # The effect takes the targets of one attack at a time: each part moves its attacks with the targets that
    # they carry, and takes one capability of the effect for each kind of system of each attack. An attack
    # built in advance waits with its targets, the spread of their outcomes and their independent outcomes.
    # An attack made at once goes to assessment with its targets and outcomes. It burns the exposure share of
    # its capabilities, and keeps the rest if they were never used. The moment of an attack held ready takes
    # it to assessment with its own targets and outcomes.
    field = field_of('ai_fast')
    s = field.system
    x = inputs('ai_fast')
    exposure, diversity = x['effects_program.exposure'], x['effects_program.diversity']
    share = {'all': 1, 'exposed': exposure, 'hidden': 1 - exposure}
    for move, (source, target, _) in EFFECT_MOVES.items():
        flow = s.flows[f'effects_program.{move}']
        assert (flow.source, flow.target) == (f'effect_pool.{source}', f'effect_pool.{target}')
    for y in random_states(field, 6, seed=54):
        _, d = flows_at(field, 3, y)
        rho = values_at(field, ['effects_program.within_correlation'], 3, y)[
            'effects_program.within_correlation'
        ]
        m = y[s.index['effects_program.positioned']] / y[s.index['effects_program.positioned_attacks']]
        spread, outcomes = m * (1 + (m - 1) * rho), m / (1 + (m - 1) * rho)
        for part in ('prepare_known', 'prepare_kept', 'prepare_new', 'now_known', 'now_kept', 'now_new'):
            attacks = d[f'effects_program.{part}.1']
            assert d[f'effects_program.{part}.0'] == pytest.approx(attacks * m, rel=1e-9, abs=1e-15)
            assert d[f'effects_program.{part}.2'] == pytest.approx(attacks, rel=1e-9, abs=1e-15)
            assert d[f'effects_program.{part}.3'] == pytest.approx(attacks * m, rel=1e-9, abs=1e-15)
            if part.startswith('prepare'):
                assert d[f'effects_program.{part}.4'] == pytest.approx(attacks * spread, rel=1e-9, abs=1e-15)
                assert d[f'effects_program.{part}.5'] == pytest.approx(
                    attacks * outcomes, rel=1e-9, abs=1e-15
                )
            else:
                assert d[f'effects_program.{part}.4'] == pytest.approx(
                    attacks * outcomes, rel=1e-9, abs=1e-15
                )
        for move, (_, _, part_share) in EFFECT_MOVES.items():
            attacks = d[f'effects_program.{move.split(".")[0]}.1']
            assert d[f'effects_program.{move}'] == pytest.approx(
                attacks * kinds(diversity, m) * share[part_share], rel=1e-9, abs=1e-15
            )
        made = d['effects_program.use_held.0'] / y[s.index['effects_program.held_ready']]
        for move, stock in (('1', 'held_targets'), ('2', 'held_spread'), ('3', 'held_outcomes')):
            assert d[f'effects_program.use_held.{move}'] == pytest.approx(
                made * y[s.index[f'effects_program.{stock}']], rel=1e-9, abs=1e-15
            )


@pytest.mark.parametrize(
    ('run', 't_years', 'values'),
    [('ai_fast', 3, None), ('wartime', 1, None), ('ai_fast', 3, {'effects_program.exposure': 0.6})],
)
def test_an_exposed_attack_burns_the_capabilities_that_it_holds_and_a_hidden_one_keeps_them(
    run, t_years, values
):
    # The attacks that hold a pool's capabilities are the attacks past its step: in the chain and held ready.
    # The attacks made in a year are a share of them, and the same share of the held capabilities leaves the
    # held stocks: the exposure share of it burned, the rest kept for reuse. Only the attacks held ready hold
    # the effect's capabilities, and only their use takes those.
    field = field_of(run, values)
    s = field.system
    exposure = inputs(run, values)['effects_program.exposure']
    for y in random_states(field, 6, seed=55):
        _, d = flows_at(field, t_years, y)

        def stock(name):
            return y[s.index[f'effects_program.{name}']]

        made_held = d['effects_program.use_held.0']
        made = made_held + sum(
            d[f'effects_program.{part}.2'] for part in ('now_known', 'now_kept', 'now_new')
        )
        share = {
            'access_pool': made
            / (stock('access_attacks') + stock('positioned_attacks') + stock('held_ready')),
            'movement_pool': made / (stock('positioned_attacks') + stock('held_ready')),
            'effect_pool': made_held / stock('held_ready'),
        }
        for pool, rate in share.items():
            for kind in ('shared', 'attack'):
                held = y[s.index[f'{pool}.held_{kind}']]
                assert d[f'{pool}.burn_{kind}'] == pytest.approx(exposure * rate * held, rel=1e-9, abs=1e-15)
                assert d[f'{pool}.keep_{kind}'] == pytest.approx(
                    (1 - exposure) * rate * held, rel=1e-9, abs=1e-15
                )


def test_shared_burns_cost_surveillance_the_found_share_of_the_accesses_that_run_on_them():
    # Where an exposed attack burns a capability that surveillance also uses, the defenders find a share of
    # the accesses that run on it: surveillance's accesses on zero-days of the step, over the capabilities it
    # uses there. The accesses held depend on access, the implants on access and on movement.
    for find in (0.0, 0.02, 0.2):
        edits = {'surveillance_program.find_share': find}
        field = field_of('ai_fast', edits)
        s = field.system
        for y in random_states(field, 3, seed=56):
            _, d = flows_at(field, 3, y)
            loss = {}
            for pool in ('access_pool', 'movement_pool'):
                v = values_at(field, [f'{pool}.one_day'], 3, y)
                in_use = sum(
                    y[s.index[f'{pool}.{stock}']] for stock in ('spy_used', 'held_shared', 'kept_shared')
                )
                loss[pool] = find * d[f'{pool}.burn_shared'] * (1 - v[f'{pool}.one_day']) / in_use
            held = y[s.index['surveillance_program.accesses_held']]
            implants = y[s.index['surveillance_program.implants']]
            assert d['surveillance_program.access_burned'] == pytest.approx(
                loss['access_pool'] * held, rel=1e-9, abs=1e-18
            )
            assert d['surveillance_program.implant_burned'] == pytest.approx(
                (loss['access_pool'] + loss['movement_pool']) * implants, rel=1e-9, abs=1e-18
            )
            if find == 0:
                assert d['surveillance_program.access_burned'] == 0


def test_a_capability_in_use_serves_a_need_as_one_independent_try():
    # If each capability in use fits a need with a small chance, the chance that none of n fits is
    # (1 - chance)^n, so k times today's capabilities in use leave a need unserved with today's chance to the
    # power k. With reuse off, an attack's need at access meets surveillance's capabilities alone.
    edits = {'effects_program.reuse_source': 0}
    field = field_of('no_ai', edits)
    s = field.system
    x = inputs('no_ai', edits)
    today = 1 - x['effects_program.spy_source']
    names = ['access_pool.attack_from_spy', 'access_pool.attack_from_kept', 'access_pool.attack_from_fresh']
    base = values_at(field, names, 0, field.base)
    assert base['access_pool.attack_from_spy'] == pytest.approx(x['effects_program.spy_source'], rel=1e-12)
    served = []
    for k in (0, 0.25, 0.5, 1, 2, 4, 50):
        y = field.base.copy()
        y[s.index['access_pool.spy_used']] *= k
        v = values_at(field, names, 0, y)
        assert v['access_pool.attack_from_fresh'] == pytest.approx(today**k, rel=1e-9)
        assert v['access_pool.attack_from_kept'] == 0
        assert sum(v.values()) == pytest.approx(1, rel=1e-12)
        served.append(v['access_pool.attack_from_spy'])
    assert served[0] == 0 and served == sorted(served) and served[-1] < 1


@pytest.mark.parametrize('pool', ['access_pool', 'movement_pool'])
def test_todays_shares_of_the_sources_are_todays_inputs_and_split_by_the_tries_of_each_source(pool):
    # At today's stocks the shares of an attack's and of surveillance's zero-days are today's inputs. More
    # capabilities in one source raise its share and lower the never-used share; the shares never pass one.
    field = field_of('no_ai')
    s = field.system
    x = inputs('no_ai')
    names = [
        f'{pool}.{m}'
        for m in (
            'attack_from_spy',
            'attack_from_kept',
            'attack_from_fresh',
            'spy_from_kept',
            'spy_from_fresh',
        )
    ]
    v = values_at(field, names, 0, field.base)
    assert v[f'{pool}.attack_from_spy'] == pytest.approx(x['effects_program.spy_source'], rel=1e-12)
    assert v[f'{pool}.attack_from_kept'] == pytest.approx(x['effects_program.reuse_source'], rel=1e-12)
    assert v[f'{pool}.spy_from_kept'] == pytest.approx(x['surveillance_program.attack_source'], rel=1e-9)
    own = 1 - v[f'{pool}.spy_from_kept'] - v[f'{pool}.spy_from_fresh']
    assert own == pytest.approx(x['surveillance_program.own_source'], rel=1e-12)
    for stock, share in (('spy_used', 'attack_from_spy'), ('kept_attack', 'attack_from_kept')):
        y = field.base.copy()
        y[s.index[f'{pool}.{stock}']] *= 10
        w = values_at(field, names, 0, y)
        assert w[f'{pool}.{share}'] > v[f'{pool}.{share}']
        assert w[f'{pool}.attack_from_fresh'] < v[f'{pool}.attack_from_fresh']
        assert w[f'{pool}.attack_from_spy'] + w[f'{pool}.attack_from_kept'] < 1


def test_the_effect_and_collection_pools_have_only_their_own_missions_sources():
    # No surveillance uses the effect's capabilities and no attack uses collection's, so an attack's effect
    # never takes surveillance's capabilities, and surveillance's collection never takes an attack's.
    field = field_of('ai_fast')
    for y in random_states(field, 5, seed=57):
        v = values_at(field, ['effect_pool.attack_from_spy', 'collection_pool.spy_from_kept'], 5, y)
        assert v['effect_pool.attack_from_spy'] == 0 and v['collection_pool.spy_from_kept'] == 0


ATTACK_SOURCES = ('known', 'spy', 'kept_shared', 'kept_attack', 'new')
DEPLOYS = (
    'surveillance_program.deploy_free_free',
    'surveillance_program.deploy_free_new.0',
    'surveillance_program.deploy_kept_free.0',
    'surveillance_program.deploy_kept_new.0',
    'surveillance_program.deploy_new_free.0',
    'surveillance_program.deploy_new_new.0',
)
# The steps that take a pool's capabilities: for the operations that each mission starts, the moves of the
# units of every part of each such step.
STEP_PARTS = {
    'access_pool': {
        'effects_program.starts': [[f'effects_program.access_{key}.1' for key in ATTACK_SOURCES]],
        'surveillance_program.new_accesses': [
            [
                'surveillance_program.access_free',
                'surveillance_program.access_kept.0',
                'surveillance_program.access_new.0',
            ]
        ],
    },
    'movement_pool': {
        'effects_program.starts': [[f'effects_program.move_{key}.1' for key in ATTACK_SOURCES]],
        'surveillance_program.new_accesses': [list(DEPLOYS)],
    },
    'effect_pool': {
        'effects_program.starts': [
            [f'effects_program.prepare_{key}.1' for key in ('known', 'kept', 'new')],
            [f'effects_program.now_{key}.1' for key in ('known', 'kept', 'new')],
        ],
    },
    'collection_pool': {'surveillance_program.new_accesses': [list(DEPLOYS)]},
}
MADE_AT_ONCE = ('now_known', 'now_kept', 'now_new')
RESULTS = [
    'effects_program.starts',
    'surveillance_program.new_accesses',
    'effects_program.attacks',
    'effects_program.made_targets',
    'day_plan.finished',
]


@pytest.mark.parametrize('pool', POOLS)
def test_a_short_never_used_stock_slows_only_the_parts_that_need_it(pool):
    # A pool serves every ask for a never-used capability while it holds more than the asks of the supply
    # time. Below that, it gives out its stock over the supply time. So the parts of each step that need a
    # never-used capability slow in proportion, and the parts that one-days and capabilities in use serve go
    # on as asked. Each mission starts only the share of its operations that the pool lets pass. The attacks
    # made and their targets are those that the steps move, so the attacks made fall when the effect's pool
    # runs short, and a plan counts only the attacks that the pool can equip. The lessons of access count only
    # the accesses that are gained.
    field = field_of('no_ai')
    s = field.system
    x = inputs('no_ai')
    supply, overlap = x['researchers.supply_time'] * YEAR_H, x['effects_program.task_overlap']
    i = s.index[f'{pool}.fresh']
    draws = draws_from(s, pool)
    new = {flow_name(fid) for fid in draws}
    ample = field.base
    _, asked = flows_at(field, 0, ample)
    before = values_at(field, RESULTS, 0, ample)
    demand = sum(asked[fid] for fid in draws)
    assert 0 < demand * supply < ample[i]
    for share in (0.8, 0.3, 0.0):
        y = ample.copy()
        y[i] = share * demand * supply
        rates, got = flows_at(field, 0, y)
        after = values_at(field, RESULTS, 0, y)
        assert sum(got[fid] for fid in draws) == pytest.approx(share * demand, rel=1e-9, abs=1e-15)
        for fid in s.flow_ids:
            if flow_name(fid) in new:
                assert got[fid] == pytest.approx(share * asked[fid], rel=1e-9, abs=1e-15)
        for count, steps in STEP_PARTS[pool].items():
            for parts in steps:
                for part in parts:
                    if flow_name(part) not in new:
                        assert asked[part] > 0 and got[part] == pytest.approx(asked[part], rel=1e-12)
                served = sum(got[part] for part in parts) / sum(asked[part] for part in parts)
                assert 0 < served < 1
                assert after[count] == pytest.approx(before[count] * served, rel=1e-9)
        made = got['effects_program.use_held.0'] + sum(
            got[f'effects_program.{part}.2'] for part in MADE_AT_ONCE
        )
        hit = got['effects_program.use_held.1'] + sum(
            got[f'effects_program.{part}.3'] for part in MADE_AT_ONCE
        )
        assert after['effects_program.attacks'] == pytest.approx(made, rel=1e-12)
        assert after['effects_program.made_targets'] == pytest.approx(hit, rel=1e-12)
        if pool == 'effect_pool':
            lost = asked['effects_program.now_new.2'] - got['effects_program.now_new.2']
            assert lost > 0
            assert before['effects_program.attacks'] - after['effects_program.attacks'] == pytest.approx(
                lost, rel=1e-9
            )
            ready = sum(got[part] for part in STEP_PARTS[pool]['effects_program.starts'][0]) / sum(
                asked[part] for part in STEP_PARTS[pool]['effects_program.starts'][0]
            )
            assert after['day_plan.finished'] == pytest.approx(before['day_plan.finished'] * ready, rel=1e-9)
        else:
            assert after['effects_program.attacks'] == pytest.approx(
                before['effects_program.attacks'], rel=1e-12
            )
        # The lessons of access count the accesses that attacks and surveillance gain, as far as the tasks of
        # surveillance teach those of an attack: one access for each target that gains access.
        gained = sum(got[f'effects_program.access_{key}.0'] for key in ATTACK_SOURCES) + overlap * sum(
            got[part] for part in STEP_PARTS['access_pool']['surveillance_program.new_accesses'][0]
        )
        assert got['effects_program.learn_access'] == pytest.approx(gained, rel=1e-12)
    # An empty stock gives out nothing, and others find none of it: it gains the researchers' finds.
    assert rates[i] == pytest.approx(got[f'{pool}.research'], rel=1e-12)


def test_kinds_of_target_system_grow_slower_than_the_targets_of_an_attack():
    # Each further target of an attack is a new kind of system with a chance, so an attack's needs grow with
    # its kinds of system, not with its targets. Each step counts the kinds of the attacks in it, and the
    # attacks that the force starts have the kinds of their own targets.
    for diversity in (0.0, 0.1, 1.0):
        field = field_of('ai_fast', {'effects_program.diversity': diversity})
        s = field.system
        needs = []
        for size in (1, 2, 10, 30, 100):
            y = field.base.copy()
            for targets, attacks in CARRIED:
                y[s.index[targets]] = size * y[s.index[attacks]]
            v = values_at(
                field,
                [
                    'effects_program.access_target_need',
                    'effects_program.movement_target_need',
                    'effects_program.positioned_types',
                ],
                25,
                y,
            )
            u = kinds(diversity, size)
            assert u <= size
            assert v['effects_program.positioned_types'] == pytest.approx(u, rel=1e-12)
            for name in ('access_target_need', 'movement_target_need'):
                assert v[f'effects_program.{name}'] == pytest.approx(u / size, rel=1e-12)
            needs.append(v['effects_program.access_target_need'])
        assert all(math.isfinite(need) and 0 < need <= 1 for need in needs)
        if diversity < 1:
            assert needs == sorted(needs, reverse=True) and needs[-1] < needs[0]
        else:
            assert needs == pytest.approx([1] * len(needs), rel=1e-12)
        v = values_at(field, ['effects_program.types', 'effects_program.attack_targets'], 25, field.base)
        assert v['effects_program.types'] == pytest.approx(
            kinds(diversity, v['effects_program.attack_targets']), rel=1e-12
        )
