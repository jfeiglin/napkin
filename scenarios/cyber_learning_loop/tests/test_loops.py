"""The scenario's steps of work and its chains of targets, attacks and accesses: identities and properties of the
specification.

An attack's work is the sum of its stages' work. Each stage has work by hand for the attack and for each
target; AI does a share of it, and a unit of AI work costs an expert's supervision, shared by the attacks
that one expert runs at once, and compute. An attack's targets then move through initial access, movement
inside the network and the effect, which turns the targets of one attack into an attack; it waits ready or
is made at once, and its damage is assessed. Each attack keeps the targets that it started with, and the
spread and the independent outcomes that their correlation gives it, until its assessment ends.
Surveillance's accesses move through initial access and deployment to implants, whose take waits in a queue
for processing. Each step runs at the lower of its stock over its time and the pace that its hours allow,
each group of people serves the work farthest along first, and a step passes only the units that the pools
of capabilities can equip. On attacks, damage assessment takes at most its share of the analysts' work
waiting, and planning gets the rest; the analysts' split moves toward the target of the staffing rule, and
the operators' split toward a target set by the ratio of the two missions' returns. These tests check the
identities that tie the steps and the stocks to the totals, the book-keeping of the targets and the attacks
from their start to their assessment, the priority orders, the staffing rules, the workforce option, the
supply of capabilities and the properties of the AI channels and of the delays, without a value computed
from an authored default."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import cumulative_trapezoid

from napkin.core import expr
from napkin.dynamics import vector_field
from tests.helpers import catalogue_model

YEAR_H = 8760.0
STAGES = ('planning_stage', 'access_stage', 'payload_stage', 'execution_stage', 'assessment_stage')
EMPTY = (
    'effect_pool.spy_used',
    'effect_pool.held_shared',
    'effect_pool.kept_shared',
    'collection_pool.held_shared',
    'collection_pool.held_attack',
    'collection_pool.kept_shared',
    'collection_pool.kept_attack',
)
# The stocks of the attack chain, in order: the targets in each, and the attacks that carry them.
CARRIED = (
    ('effects_program.in_access', 'effects_program.in_access_attacks'),
    ('effects_program.accesses', 'effects_program.access_attacks'),
    ('effects_program.positioned', 'effects_program.positioned_attacks'),
    ('effects_program.held_targets', 'effects_program.held_ready'),
    ('effects_program.assessing_targets', 'effects_program.assessing'),
)
CHAIN = tuple(targets for targets, _ in CARRIED[:3])
POOLS = ('access_pool', 'movement_pool', 'effect_pool', 'collection_pool')


def field_of(run, values=None):
    return vector_field(catalogue_model('cyber_learning_loop'), run, values)


def inputs(run, values=None):
    return catalogue_model('cyber_learning_loop').resolve(run, values).parameter_values


def values_at(run, names, t_years=0.0, values=None):
    field = field_of(run, values)
    program = field.field.values_program([expr.ref(name) for name in names])
    return dict(zip(names, program(t_years * YEAR_H, field.base)))


def evaluate(field, names, t_years, y):
    """Quantities at the state `y`, in execution units (hours); inputs included."""
    program = field.field.values_program([expr.ref(name) for name in names])
    return dict(zip(names, program(t_years * YEAR_H, y)))


def random_states(field, count, seed):
    """Seeded admissible whole states: the active stocks within three sizes of the start and the bounds. The
    never-used capabilities of each pool stay at half of today's or more, so that no step waits for them, and
    the stocks that no flow fills stay empty."""
    rng = np.random.default_rng(seed)
    low = np.maximum(field.lower, field.start - 3 * field.scales)
    high = np.minimum(field.upper, field.start + 3 * field.scales)
    fresh = np.array([name.endswith('.fresh') for name in field.names])
    low = np.where(fresh, np.maximum(low, field.start / 2), low)
    empty = np.array([name in EMPTY for name in field.names])
    low, high = np.where(empty, 0, low), np.where(empty, 0, high)
    for _ in range(count):
        yield field.full(low + (high - low) * rng.random(len(field.start)))


def state_with(field, changes=None, **named):
    """The start state with some quantities set (a value) or scaled (a one-item tuple), named in a mapping or
    as keywords with `__` for the dot."""
    y = field.base.copy()
    named = {name.replace('__', '.'): change for name, change in named.items()}
    for name, change in {**(changes or {}), **named}.items():
        i = field.system.index[name]
        y[i] = y[i] * change[0] if isinstance(change, tuple) else change
    return y


def with_carried_sizes(field, y, rng, largest=40.0):
    """`y` with the attacks of each stock of the attack chain between a third and three times today's, each
    stock's attacks with between one and `largest` targets on average, and the spread and the independent
    outcomes of the attacks held ready and under assessment anywhere between those of independent targets and
    of fully correlated ones."""
    y = y.copy()
    index = field.system.index
    for targets, attacks in CARRIED:
        y[index[attacks]] = field.base[index[attacks]] * rng.uniform(1 / 3, 3)
        y[index[targets]] = y[index[attacks]] * rng.uniform(1, largest)
    held = y[index['effects_program.held_targets']]
    held_size = held / y[index['effects_program.held_ready']]
    y[index['effects_program.held_spread']] = held * (1 + (held_size - 1) * rng.random())
    y[index['effects_program.held_outcomes']] = held / (1 + (held_size - 1) * rng.random())
    assessed = y[index['effects_program.assessing_targets']]
    assessed_size = assessed / y[index['effects_program.assessing']]
    y[index['effects_program.assessing_outcomes']] = assessed / (1 + (assessed_size - 1) * rng.random())
    return y


def series(trajectory, names, times):
    """{name: its values at `times`} along a simulated trajectory."""
    envs = [trajectory.env_at(t) for t in times]
    return {name: np.array([env[name] for env in envs]) for name in names}


@pytest.mark.parametrize(
    ('run', 't_years'), [('no_ai', 0), ('ai_fast', 2), ('ai_slow', 10), ('ai_reversal', 20)]
)
def test_the_work_and_the_time_of_an_attack_are_the_sums_of_its_stages(run, t_years):
    x = inputs(run)
    names = [f'{s}.{m}' for s in STAGES for m in ('cost', 'time')]
    v = values_at(run, [*names, 'effects_program.base_cost', 'effects_program.lead_time'], t_years)
    assert v['effects_program.base_cost'] == pytest.approx(sum(v[f'{s}.cost'] for s in STAGES), rel=1e-12)
    building = [s for s in STAGES if x[f'{s}.builds']]
    assert building
    assert v['effects_program.lead_time'] == pytest.approx(sum(v[f'{s}.time'] for s in building), rel=1e-12)


@pytest.mark.parametrize(('run', 't_years'), [('no_ai', 0), ('ai_fast', 3), ('ai_fast', 25)])
def test_initial_access_and_movement_split_the_time_and_the_work_of_access(run, t_years):
    # Initial access and movement inside the network take today's time and work of access between them, by
    # one share; per target, they add up to the work of access of an attack over its targets.
    x = inputs(run)
    share = x['effects_program.initial_share']
    names = [
        'access_stage.time',
        'access_stage.learned_cost',
        'effects_program.initial_time',
        'effects_program.movement_time',
        'effects_program.initial_work',
        'effects_program.movement_work',
        'effects_program.attack_targets',
    ]
    v = values_at(run, names, t_years)
    assert v['effects_program.initial_time'] == pytest.approx(share * v['access_stage.time'], rel=1e-12)
    assert v['effects_program.movement_time'] == pytest.approx(
        (1 - share) * v['access_stage.time'], rel=1e-12
    )
    per_target = v['access_stage.learned_cost'] / v['effects_program.attack_targets']
    assert v['effects_program.initial_work'] == pytest.approx(share * per_target, rel=1e-12)
    assert v['effects_program.movement_work'] == pytest.approx((1 - share) * per_target, rel=1e-12)


@pytest.mark.parametrize('t_years', [0, 3, 25])
def test_the_waiting_cost_is_the_upkeep_and_the_decay_of_held_work_until_its_use(t_years):
    # A stage whose product waits ready costs its work times 1 + q (decay + upkeep) / use rate, where q is
    # the share of attacks that need their access built in advance: a Hill curve of the build time over the
    # warning time.
    x = inputs('ai_fast')
    v = values_at(
        'ai_fast',
        [
            'access_stage.cost',
            'access_stage.hand_work',
            'access_stage.unit_cost',
            'effects_program.lead_time',
        ],
        t_years,
    )
    # Inputs resolve in their own units (years, per year); the model's values are in hours.
    years = v['effects_program.lead_time'] / YEAR_H
    ratio = (years / x['effects_program.warning_time']) ** x['effects_program.waiting_sharpness']
    ahead = ratio / (1 + ratio)
    decay, upkeep = x['effects_program.access_decay'], x['effects_program.upkeep']
    waiting = 1 + ahead * (decay + upkeep) / x['effects_program.use_rate']
    assert x['access_stage.held']
    assert v['access_stage.cost'] == pytest.approx(
        v['access_stage.hand_work'] * v['access_stage.unit_cost'] * waiting, rel=1e-9
    )


NO_AI_WORK = {f'{s}.{m}': 0 for s in STAGES for m in ('ai_now', 'ai_end', 'target_ai_now', 'target_ai_end')}


@pytest.mark.parametrize('t_years', [1, 6, 25])
def test_running_attacks_in_parallel_saves_only_the_work_that_ai_does(t_years):
    # With no AI work in any stage, neither more attacks per supervisor nor cheaper compute changes the
    # work of an attack. With AI work, more attacks per supervisor lower it.
    def cost(values):
        return values_at('ai_fast', ['effects_program.base_cost'], t_years, values)[
            'effects_program.base_cost'
        ]

    manual = cost(NO_AI_WORK)
    assert cost({**NO_AI_WORK, 'effects_program.parallel_end': 50}) == pytest.approx(manual, rel=1e-12)
    assert cost({**NO_AI_WORK, 'effects_program.compute_end': 0.004}) == pytest.approx(manual, rel=1e-12)
    assert cost({'effects_program.parallel_end': 50}) < cost({'effects_program.parallel_end': 1})


def test_work_for_each_target_grows_with_the_targets_that_it_serves_and_work_for_the_attack_does_not():
    # At the end of AI progress, an attack's stages grow with its targets only through their work for each
    # target. Damage assessment counts the targets that the attacks under assessment carry, and the other
    # stages the targets of an attack now. The operators' work on the effect counts the targets of the
    # attacks whose effect the force builds: the stage's own work for an attack of that size.
    x = inputs('ai_fast')
    few, many = {'effects_program.targets_end': 3}, {'effects_program.targets_end': 100}
    names = [
        *(f'{s}.hand_work' for s in STAGES),
        'payload_stage.learned_cost',
        'effects_program.attack_targets',
    ]
    a, b = values_at('ai_fast', names, 25, few), values_at('ai_fast', names, 25, many)
    grown = b['effects_program.attack_targets'] - a['effects_program.attack_targets']
    assert grown > 0
    for s in STAGES:
        slope = (b[f'{s}.hand_work'] - a[f'{s}.hand_work']) / grown / YEAR_H
        expected = 0 if s == 'assessment_stage' else x[f'{s}.target_work']
        assert slope == pytest.approx(expected, rel=1e-9, abs=1e-12), s
    field = field_of('ai_fast', many)
    index = field.system.index

    def carrying(size):
        y = field.base.copy()
        for targets, attacks in (CARRIED[2], CARRIED[4]):
            y[index[targets]] = size * y[index[attacks]]
        names = ['assessment_stage.hand_work', 'effects_program.effect_work', 'payload_stage.learned_cost']
        return evaluate(field, names, 25, y)

    small, large = carrying(2.0), carrying(7.0)
    slope = (large['assessment_stage.hand_work'] - small['assessment_stage.hand_work']) / 5 / YEAR_H
    assert slope == pytest.approx(x['assessment_stage.target_work'], rel=1e-9)
    # The effect's work for an attack moves with the attack's own targets as the stage's work moves with the
    # targets of an attack, and it is the stage's work for an attack of the targets of an attack now.
    stage_slope = (b['payload_stage.learned_cost'] - a['payload_stage.learned_cost']) / grown
    effect_slope = (large['effects_program.effect_work'] - small['effects_program.effect_work']) / 5
    assert effect_slope == pytest.approx(stage_slope, rel=1e-9)
    now = carrying(b['effects_program.attack_targets'])
    assert now['effects_program.effect_work'] == pytest.approx(now['payload_stage.learned_cost'], rel=1e-12)


# The quantities that the book-keeping of the attack chain reads at a state.
CARRIAGE_NAMES = [
    'effects_program.starts',
    'effects_program.attack_targets',
    'effects_program.assessed_rate',
    'effects_program.moment_rate',
    'effects_program.execution_served',
    'effects_program.within_correlation',
    'effects_program.attacks',
    'effects_program.made_targets',
]


@pytest.mark.parametrize(
    ('run', 't_years'), [('ai_fast', 3), ('ai_slow', 12), ('ai_reversal', 20), ('wartime', 1)]
)
def test_each_step_of_the_chain_passes_on_the_targets_that_its_attacks_carry(run, t_years):
    # Away from rest, with attacks of every size in each stock: the attacks started bring the targets of an
    # attack now. The attacks that leave a stock carry its mean targets, and its mean spread and independent
    # outcomes; the attacks that the effect finishes take the targets of the attacks whose effect it builds, with
    # the spread and the outcomes that the correlation of their targets now gives. So the targets in the chain
    # change by the targets of the attacks started less those of the attacks assessed, and the attacks by the
    # attacks started less those assessed. The attacks made are those built on demand and those whose moment
    # comes, each with its own targets.
    field = field_of(run)
    s = field.system
    rng = np.random.default_rng(45)
    for drawn in random_states(field, 10, seed=45):
        y = with_carried_sizes(field, drawn, rng)
        rates = field.rates_of(y, t_years * YEAR_H)
        v = evaluate(field, CARRIAGE_NAMES, t_years, y)

        def stock(name):
            return y[s.index[f'effects_program.{name}']]

        def rate(name):
            return rates[s.index[f'effects_program.{name}']]

        starts, m = v['effects_program.starts'], v['effects_program.attack_targets']
        assessed = v['effects_program.assessed_rate']
        scale = starts * m + sum(abs(rates[s.index[name]]) for pair in CARRIED for name in pair)
        tolerance = {'rel': 1e-9, 'abs': 1e-12 * scale}
        # Each step of the pipeline: the targets that leave it are the attacks that leave it times its mean size.
        moving, carried = starts, starts * m
        for targets, attacks in CARRIED[:3]:
            moving -= rates[s.index[attacks]]
            carried -= rates[s.index[targets]]
            assert moving >= 0
            assert carried == pytest.approx(moving * y[s.index[targets]] / y[s.index[attacks]], **tolerance)
        size = stock('positioned') / stock('positioned_attacks')
        held_size = stock('held_targets') / stock('held_ready')
        assessed_size = stock('assessing_targets') / stock('assessing')
        grows = 1 + (size - 1) * v['effects_program.within_correlation']
        # The moments of the attacks held ready come at their rate, for the attacks whose execution is served.
        used = v['effects_program.moment_rate'] * stock('held_ready') * v['effects_program.execution_served']
        held = rate('held_ready') + used
        now = moving - held
        assert held >= -tolerance['abs'] and now >= -tolerance['abs']
        assert rate('assessing') == pytest.approx(now + used - assessed, **tolerance)
        assert rate('held_targets') == pytest.approx(held * size - used * held_size, **tolerance)
        assert rate('assessing_targets') == pytest.approx(
            now * size + used * held_size - assessed * assessed_size, **tolerance
        )
        held_spread = stock('held_spread') / stock('held_ready')
        held_outcomes = stock('held_outcomes') / stock('held_ready')
        assert rate('held_spread') == pytest.approx(held * size * grows - used * held_spread, **tolerance)
        assert rate('held_outcomes') == pytest.approx(held * size / grows - used * held_outcomes, **tolerance)
        assert rate('assessing_outcomes') == pytest.approx(
            now * size / grows
            + used * held_outcomes
            - assessed * stock('assessing_outcomes') / stock('assessing'),
            **tolerance,
        )
        # The whole chain, and the attacks made with their targets.
        assert sum(rates[s.index[attacks]] for _, attacks in CARRIED) == pytest.approx(
            starts - assessed, **tolerance
        )
        assert sum(rates[s.index[targets]] for targets, _ in CARRIED) == pytest.approx(
            starts * m - assessed * assessed_size, **tolerance
        )
        assert v['effects_program.attacks'] == pytest.approx(now + used, **tolerance)
        assert v['effects_program.made_targets'] == pytest.approx(now * size + used * held_size, **tolerance)


@pytest.mark.parametrize('run', ['ai_fast', 'ai_reversal'])
def test_the_chain_keeps_every_target_and_attack_that_it_starts_until_its_assessment(run, trajectory_of):
    # Book-keeping along a run from its start: the targets that enter are each attack started times the
    # targets of an attack at its start, and at every time they are in a stock of the chain or have been
    # assessed with the targets that their attacks carry. The attacks likewise. AI moves the targets of an
    # attack up (ai_fast), and up and then down (ai_reversal), while attacks wait ready and in assessment: so
    # targets counted at the attacks there times the targets of an attack now would not balance.
    trajectory = trajectory_of(run)
    times = np.linspace(0.0, trajectory.horizon, 4001)
    targets = tuple(targets for targets, _ in CARRIED)
    attacks = tuple(attacks for _, attacks in CARRIED)
    flows = ('effects_program.starts', 'effects_program.attack_targets', 'effects_program.assessed_rate')
    v = series(trajectory, [*targets, *attacks, *flows], times)
    m = v['effects_program.attack_targets']
    starts, assessed = v['effects_program.starts'], v['effects_program.assessed_rate']
    assessed_size = v['effects_program.assessing_targets'] / v['effects_program.assessing']
    entered = cumulative_trapezoid(starts * m, times, initial=0.0)
    in_stocks = sum(v[name] for name in targets)
    balance = in_stocks - in_stocks[0] + cumulative_trapezoid(assessed * assessed_size, times, initial=0.0)
    assert np.max(np.abs(entered - balance)) <= 1e-5 * entered[-1]
    started = cumulative_trapezoid(starts, times, initial=0.0)
    in_stocks = sum(v[name] for name in attacks)
    balance = in_stocks - in_stocks[0] + cumulative_trapezoid(assessed, times, initial=0.0)
    assert np.max(np.abs(started - balance)) <= 1e-5 * started[-1]
    # The run moves the targets of an attack, and they fall at its end in the reversal.
    assert m.max() > 5 * m[0]
    if run == 'ai_reversal':
        assert m[-1] < 0.9 * m.max()
    waiting = v['effects_program.held_ready'] + v['effects_program.assessing']
    current = sum(v[name] for name in CHAIN) + waiting * m
    counted = current - current[0] + cumulative_trapezoid(assessed * m, times, initial=0.0)
    assert np.max(np.abs(entered - counted)) > 0.05 * entered[-1]


def stage_work(v, stage, size, held=False):
    """The expert work of a stage, after lessons, for one attack with `size` targets: its work for the attack
    and its work for each target, each at its cost as a share of the work by hand; a stage whose product waits
    ready also bears the cost of the wait."""
    work = v[f'{stage}.work'] * v[f'{stage}.unit_cost']
    work += v[f'{stage}.target_work'] * size * v[f'{stage}.target_cost']
    return work * v[f'{stage}.learning'] * (v['effects_program.waiting'] if held else 1)


def attack_allocation(v):
    """The operators' hours on attacks served by the specification's priority: execution, the effect,
    movement inside the network, initial access, each at the lower of its stock over its time and its
    hours left over its work. Execution and the effect work on attacks, each with the targets that it was
    built with: the attacks that wait for execution are those held ready whose moment comes and those built on
    demand. Every value is in execution units."""
    hours = v['leadership.attack_experts']
    moment, ahead = v['effects_program.moment_rate'], v['effects_program.built_ahead']
    effect_time = v['payload_stage.time']
    effect_pace = v['effects_program.positioned_attacks'] / effect_time
    asked = moment * v['effects_program.held_ready'] + (1 - ahead) * effect_pace
    waiting = (
        moment * v['effects_program.held_targets']
        + (1 - ahead) * v['effects_program.positioned'] / effect_time
    )
    executed = waiting / asked
    execution_work = stage_work(v, 'execution_stage', executed)
    served = min(1.0, hours / (asked * execution_work))
    left = max(hours - served * asked * execution_work, 0.0)
    positioned = v['effects_program.positioned'] / v['effects_program.positioned_attacks']
    effect_work = stage_work(v, 'payload_stage', positioned, held=True)
    ready = min(effect_pace, left / effect_work)
    left = max(left - (ahead + (1 - ahead) * served) * ready * effect_work, 0.0)
    movement = min(
        v['effects_program.accesses'] / v['effects_program.movement_time'],
        left / v['effects_program.movement_work'],
    )
    left = max(left - movement * v['effects_program.movement_work'], 0.0)
    access = min(
        v['effects_program.in_access'] / v['effects_program.initial_time'],
        left / v['effects_program.initial_work'],
    )
    return {
        'executed': executed,
        'execution_work': execution_work,
        'effect_work': effect_work,
        'served': served,
        'ready': ready,
        'movement': movement,
        'access': access,
    }


ATTACK_NAMES = [
    'leadership.attack_experts',
    'effects_program.attack_targets',
    'effects_program.built_ahead',
    'effects_program.moment_rate',
    'effects_program.waiting',
    'effects_program.held_ready',
    'effects_program.held_targets',
    'effects_program.positioned',
    'effects_program.positioned_attacks',
    'effects_program.accesses',
    'effects_program.in_access',
    'effects_program.movement_time',
    'effects_program.initial_time',
    'effects_program.movement_work',
    'effects_program.initial_work',
    'effects_program.executed_size',
    'effects_program.execution_work',
    'effects_program.effect_work',
    'payload_stage.time',
    *(
        f'{stage}.{part}'
        for stage in ('execution_stage', 'payload_stage')
        for part in ('work', 'unit_cost', 'target_work', 'target_cost', 'learning', 'learned_cost')
    ),
    'effects_program.execution_served',
    'effects_program.ready_rate',
    'effects_program.movement_rate',
    'effects_program.access_rate',
]


@pytest.mark.parametrize(
    ('share', 'scale', 'size', 'held'),
    [
        (None, 1, 1, None),
        (0.3, 1, 1, None),
        (0.05, 1, 1, None),
        (0.003, 1, 1, None),
        (0.003, 1, 1, 12),
        (0.95, 5, 1, None),
        (0.3, 1, 6, 12),
    ],
)
def test_the_operators_serve_the_attacks_farthest_along_first(share, scale, size, held):
    # With plenty of operators each step runs at its pace by time; as their hours fall, initial access is
    # cut first, then movement, then the effect, and execution last. Every step's rate is the lower of its
    # stock over its time and its hours left over its work, in that order. Execution and the effect work on
    # attacks, each with the targets that it was built with: the stage's own work for an attack of that size.
    # Here the attacks that wait carry fewer targets than an attack now (today's, or `size` in the pipeline)
    # or more (`held` targets for each attack held ready).
    field = field_of('ai_fast')
    changes = {}
    for targets, attacks in CARRIED[:3]:
        changes[targets], changes[attacks] = (scale * size,), (scale,)
    if held is not None:
        changes['effects_program.held_targets'] = (held,)
        changes['effects_program.held_spread'] = (held * held,)
    if share is not None:
        changes['leadership.attack_share'] = share
    v = evaluate(field, ATTACK_NAMES, 2, state_with(field, changes))
    expected = attack_allocation(v)
    m = v['effects_program.attack_targets']
    # The stage's work at the targets of an attack now is the stage's own cost: what a charge at them would be.
    for stage, held_stage in (('execution_stage', False), ('payload_stage', True)):
        assert stage_work(v, stage, m, held_stage) == pytest.approx(v[f'{stage}.learned_cost'], rel=1e-12)
    assert abs(expected['execution_work'] / v['execution_stage.learned_cost'] - 1) > 0.1
    assert v['effects_program.executed_size'] == pytest.approx(expected['executed'], rel=1e-12)
    assert v['effects_program.execution_work'] == pytest.approx(expected['execution_work'], rel=1e-12)
    assert v['effects_program.effect_work'] == pytest.approx(expected['effect_work'], rel=1e-12)
    assert v['effects_program.execution_served'] == pytest.approx(expected['served'], rel=1e-12)
    assert v['effects_program.ready_rate'] == pytest.approx(expected['ready'], rel=1e-9, abs=1e-15)
    assert v['effects_program.movement_rate'] == pytest.approx(expected['movement'], rel=1e-9, abs=1e-15)
    assert v['effects_program.access_rate'] == pytest.approx(expected['access'], rel=1e-9, abs=1e-15)
    if share == 0.003:
        # Too few hours even for execution: nothing else gets more than the rounding of the hours.
        hours = v['leadership.attack_experts']
        assert v['effects_program.execution_served'] < 1
        assert v['effects_program.ready_rate'] * expected['effect_work'] <= 1e-12 * hours
        assert v['effects_program.movement_rate'] * v['effects_program.movement_work'] <= 1e-12 * hours
        assert v['effects_program.access_rate'] * v['effects_program.initial_work'] <= 1e-12 * hours
    if share == 0.05:
        # Execution is served in full and the step behind it is cut by its hours.
        assert v['effects_program.execution_served'] == 1
        assert v['effects_program.access_rate'] == 0


def test_the_operators_on_surveillance_deploy_before_they_gain_new_access():
    # The operators on surveillance deploy implants on the accesses held first; initial access gets the hours
    # left. With most operators on attacks, deployment takes all of surveillance's hours.
    field = field_of('ai_fast')
    names = [
        'surveillance_program.spying_experts',
        'surveillance_program.accesses_held',
        'surveillance_program.accesses_underway',
        'effects_program.movement_time',
        'effects_program.initial_time',
        'surveillance_program.deploy_work',
        'surveillance_program.initial_work',
        'surveillance_program.deploy_rate',
        'surveillance_program.access_rate',
    ]
    for share in (None, 0.7, 0.95):
        y = state_with(field, **({} if share is None else {'leadership__attack_share': share}))
        v = evaluate(field, names, 2, y)
        hours = v['surveillance_program.spying_experts']
        deploy = min(
            v['surveillance_program.accesses_held'] / v['effects_program.movement_time'],
            hours / v['surveillance_program.deploy_work'],
        )
        left = max(hours - deploy * v['surveillance_program.deploy_work'], 0.0)
        access = min(
            v['surveillance_program.accesses_underway'] / v['effects_program.initial_time'],
            left / v['surveillance_program.initial_work'],
        )
        assert v['surveillance_program.deploy_rate'] == pytest.approx(deploy, rel=1e-12)
        assert v['surveillance_program.access_rate'] == pytest.approx(access, rel=1e-9, abs=1e-15)
        if share == 0.95:
            assert v['surveillance_program.access_rate'] == 0 < v['surveillance_program.deploy_rate']


def test_the_collection_specialists_process_the_take_before_they_run_collection():
    # The collection specialists process what waits in the queue first and run implants with the hours left;
    # a running implant gives one access-year of take a year, and the implants run are the implants and the
    # specialists' reach in series. With a large queue, processing takes every hour and no implant runs.
    field = field_of('ai_fast')
    names = [
        'collection_specialists.people',
        'surveillance_program.collected',
        'surveillance_program.process_time',
        'surveillance_program.process_work',
        'surveillance_program.run_work',
        'surveillance_program.implants',
        'surveillance_program.processed',
        'surveillance_program.used',
    ]
    for scale in (1, 3, 30):
        y = state_with(field, surveillance_program__collected=(scale,))
        v = evaluate(field, names, 2, y)
        people = v['collection_specialists.people']
        processed = min(
            v['surveillance_program.collected'] / v['surveillance_program.process_time'],
            people / v['surveillance_program.process_work'],
        )
        reach = (
            max(people - processed * v['surveillance_program.process_work'], 0.0)
            / v['surveillance_program.run_work']
        )
        implants = v['surveillance_program.implants']
        assert v['surveillance_program.processed'] == pytest.approx(processed, rel=1e-12)
        assert v['surveillance_program.used'] == pytest.approx(
            implants * reach / (implants + reach),
            rel=1e-9,
            abs=1e-12 * people / v['surveillance_program.run_work'],
        )
        if scale == 30:
            # Every hour processes: what is left to run collection is the rounding of the hours.
            assert processed == people / v['surveillance_program.process_work']
            assert v['surveillance_program.used'] <= 1e-12 * implants


def test_collecting_does_not_drain_implants_and_the_queue_gains_the_take_less_what_is_processed():
    # Collection reads the implants but takes none of them: the implants change only by deployments, losses
    # and burns. The queue gains the take of the implants run and loses what is processed.
    field = field_of('ai_fast')
    s = field.system
    names = [
        'surveillance_program.deploy_rate',
        'surveillance_program.loss_rate',
        'access_pool.burn_loss',
        'movement_pool.burn_loss',
        'surveillance_program.used',
        'surveillance_program.processed',
    ]
    for y in random_states(field, 10, seed=58):
        rates = field.rates_of(y, 4 * YEAR_H)
        v = evaluate(field, names, 4, y)
        implants = y[s.index['surveillance_program.implants']]
        out = v['surveillance_program.loss_rate'] + v['access_pool.burn_loss'] + v['movement_pool.burn_loss']
        assert rates[s.index['surveillance_program.implants']] == pytest.approx(
            v['surveillance_program.deploy_rate'] - out * implants, rel=1e-9, abs=1e-12
        )
        assert rates[s.index['surveillance_program.collected']] == pytest.approx(
            v['surveillance_program.used'] - v['surveillance_program.processed'], rel=1e-9, abs=1e-12
        )


@pytest.mark.parametrize(('run', 't_years'), [('ai_fast', 3), ('ai_slow', 12), ('ai_reversal', 20)])
def test_accesses_leave_surveillance_only_when_lost_or_burned(run, t_years):
    # Away from rest, surveillance's accesses along its chain change by the new accesses that the analysts
    # plan less the accesses held and implants lost and those that the defenders find through burned
    # capabilities.
    field = field_of(run)
    s = field.system
    names = [
        'surveillance_program.new_accesses',
        'surveillance_program.loss_rate',
        'surveillance_program.burned_accesses',
    ]
    chain = (
        'surveillance_program.accesses_underway',
        'surveillance_program.accesses_held',
        'surveillance_program.implants',
    )
    for y in random_states(field, 15, seed=46):
        rates = field.rates_of(y, t_years * YEAR_H)
        v = evaluate(field, names, t_years, y)
        held = y[s.index['surveillance_program.accesses_held']] + y[s.index['surveillance_program.implants']]
        change = sum(rates[s.index[name]] for name in chain)
        expected = (
            v['surveillance_program.new_accesses']
            - v['surveillance_program.loss_rate'] * held
            - v['surveillance_program.burned_accesses']
        )
        assert change == pytest.approx(expected, rel=1e-9, abs=1e-9)


ANALYST_NAMES = [
    'analysts.attack_capacity',
    'effects_program.assessing',
    'assessment_stage.time',
    'assessment_stage.learned_cost',
    'planning_stage.learned_cost',
    'effects_program.wanted_starts',
    'effects_program.supply',
    'effects_program.assessed_rate',
    'effects_program.starts',
]


@pytest.mark.parametrize(('backlog', 'share'), [(1, None), (3, None), (30, None), (1, 0.2), (30, 0.05)])
def test_damage_assessment_takes_at_most_its_share_of_the_work_waiting_and_planning_the_rest(backlog, share):
    # The analysts on attacks assess the attacks made and plan new ones. Assessment takes at most its share of
    # the work waiting: the assessments that its queue asks and the planning of the attacks that the
    # operators can start. Planning gets the hours left, and the force starts no more attacks than they plan
    # and the pools can equip. So with any backlog of assessments the analysts go on planning, and with hours
    # for all of the work both get all of it.
    field = field_of('ai_fast')
    changes = {
        name: (backlog,)
        for name in (
            'effects_program.assessing',
            'effects_program.assessing_targets',
            'effects_program.assessing_outcomes',
        )
    }
    if share is not None:
        changes['analysts.attack_share'] = share
    v = evaluate(field, ANALYST_NAMES, 3, state_with(field, changes))
    capacity = v['analysts.attack_capacity']
    queue = v['effects_program.assessing'] / v['assessment_stage.time']
    assess_cost, plan_cost = v['assessment_stage.learned_cost'], v['planning_stage.learned_cost']
    wanted = v['effects_program.wanted_starts']
    part = queue * assess_cost / (queue * assess_cost + wanted * plan_cost)
    assessed = min(queue, capacity * part / assess_cost)
    left = capacity - assessed * assess_cost
    starts = min(wanted, left / plan_cost) * v['effects_program.supply']
    assert v['effects_program.assessed_rate'] == pytest.approx(assessed, rel=1e-12)
    assert v['effects_program.starts'] == pytest.approx(starts, rel=1e-9)
    assert left >= (1 - part) * capacity * (1 - 1e-12)
    assert v['effects_program.starts'] > 0
    if capacity >= queue * assess_cost + wanted * plan_cost:
        assert v['effects_program.assessed_rate'] == pytest.approx(queue, rel=1e-12)
        assert v['effects_program.starts'] == pytest.approx(wanted * v['effects_program.supply'], rel=1e-12)
    else:
        assert v['effects_program.assessed_rate'] * assess_cost <= part * capacity * (1 + 1e-12)
    if backlog == 30:
        # The queue alone asks for more than the analysts' hours: to assess first would plan no attack.
        assert queue * assess_cost > capacity


# What the analysts' staffing rules read, in execution units.
STAFFING_NAMES = [
    'analysts.people',
    'analysts.share_now',
    'analysts.adjust_time',
    'analysts.priority_steepness',
    'analysts.target_share',
    'effects_program.assessing',
    'assessment_stage.time',
    'assessment_stage.learned_cost',
    'planning_stage.learned_cost',
    'effects_program.wanted_starts',
    'surveillance_program.builds',
    'surveillance_program.plan_work',
    'effects_program.risk_value',
    'effects_program.attacks',
    'effects_program.hits',
    'effects_program.saturation',
    'effects_program.sanctions',
    'effects_program.burned',
    'surveillance_program.spying_value',
    'surveillance_program.returns_scale',
    'surveillance_program.reach',
    'surveillance_program.implants',
    'surveillance_program.new_accesses',
]


def analysis_needs(v):
    """The analysis work that attacks need in a year (the planning of the attacks that the operators can
    start, and the assessment of those or of the queue, if it is larger) and the planning that surveillance
    asks for the accesses that its operators can start."""
    queue = v['effects_program.assessing'] / v['assessment_stage.time']
    wanted = v['effects_program.wanted_starts']
    attacks = (
        max(queue, wanted) * v['assessment_stage.learned_cost'] + wanted * v['planning_stage.learned_cost']
    )
    return attacks, v['surveillance_program.builds'] * v['surveillance_program.plan_work']


def marginal_values(v):
    """The value of one more analyst-year on each mission where the analysts limit it: on attacks, the value
    that one more attack adds with the value's saturation, less the costs of an attack, over the analysts'
    work of an attack; on surveillance, the value that one more implant adds to the implants that the
    specialists run in series with their reach, to the power of the returns, over the analysts' work of the
    new accesses."""
    added = (
        v['effects_program.risk_value']
        / v['effects_program.attacks']
        / (1 + v['effects_program.hits'] / v['effects_program.saturation'])
    )
    margin = max(added - v['effects_program.sanctions'] - v['effects_program.burned'], 0.0)
    attacks = margin / (v['planning_stage.learned_cost'] + v['assessment_stage.learned_cost'])
    implants, reach = v['surveillance_program.implants'], v['surveillance_program.reach']
    spying = (
        v['surveillance_program.spying_value']
        * v['surveillance_program.returns_scale']
        * reach
        / (implants + reach)
    ) / (v['surveillance_program.new_accesses'] * v['surveillance_program.plan_work'])
    return attacks, spying


def split_rate(field, y, t_years):
    return field.rates_of(y, t_years * YEAR_H)[field.system.index['analysts.attack_share']]


@pytest.mark.parametrize(('run', 't_years'), [('ai_fast', 3), ('ai_slow', 12), ('wartime', 1)])
@pytest.mark.parametrize('steepness', [None, 0, 10])
def test_the_analysts_go_first_to_the_mission_where_one_more_analyst_year_is_worth_more(
    run, t_years, steepness
):
    # By default the staffing rule weighs two splits: attacks first, with the work that their attacks need,
    # and surveillance first, with all of its planning, each over the analysts with today's slack. The weight
    # of attacks is the ratio of the values of one more analyst-year on each, to the power of the steepness,
    # over one more than that power: above one half exactly where attacks are worth more, a half at zero
    # steepness. The split moves toward the target, about two thirds of the way in the adjustment time.
    field = field_of(run, None if steepness is None else {'analysts.priority_steepness': steepness})
    s = field.system
    for y in random_states(field, 10, seed=59):
        v = evaluate(field, STAFFING_NAMES, t_years, y)
        attacks, spying = analysis_needs(v)
        people = v['analysts.people']
        first_attacks, first_spying = min(attacks / people, 1.0), max(1 - spying / people, 0.0)
        attack_value, spy_value = marginal_values(v)
        steep = v['analysts.priority_steepness']
        if steep == 0:
            weight = 0.5
        elif attack_value == 0 or spy_value == 0:
            # One more analyst-year adds nothing to one mission (no margin of attacks, or no specialists' hours
            # to run one more implant): the other mission gets the priority.
            weight = 0.5 if attack_value == spy_value else float(attack_value > spy_value)
        else:
            power = (attack_value / spy_value) ** steep
            weight = power / (1 + power)
        target = weight * first_attacks + (1 - weight) * first_spying
        assert v['analysts.target_share'] == pytest.approx(target, rel=1e-9, abs=1e-9)
        if (
            steep > 0
            and first_attacks != first_spying
            and not math.isclose(attack_value, spy_value, rel_tol=1e-6)
        ):
            toward_attacks = abs(target - first_attacks) < abs(target - first_spying)
            assert toward_attacks == (attack_value > spy_value)
        share = y[s.index['analysts.attack_share']]
        assert split_rate(field, y, t_years) == pytest.approx(
            (target - share) / v['analysts.adjust_time'], rel=1e-9, abs=1e-15
        )


@pytest.mark.parametrize(('run', 't_years'), [('ai_fast', 3), ('ai_slow', 12), ('wartime', 1)])
def test_the_work_waiting_rule_follows_the_work_that_attacks_need_and_not_the_attacks_made(run, t_years):
    # With the option "Work waiting", the split moves toward attacks' share of the analysis work that the two
    # missions need. Attacks need the planning of the attacks that the operators can start and the assessment
    # of those, or of the queue if it is larger. So where the analysts let the force make fewer attacks than its
    # operators can start, a shorter queue of assessments leaves the target where it is: the rule does not feed
    # on the attacks that it rations. A longer queue than that raises it.
    field = field_of(run, {'analysts.by_value': False})
    s = field.system
    queue_names = (
        'effects_program.assessing',
        'effects_program.assessing_targets',
        'effects_program.assessing_outcomes',
    )
    for y in random_states(field, 10, seed=60):
        v = evaluate(field, STAFFING_NAMES, t_years, y)
        attacks, spying = analysis_needs(v)
        target = attacks / (attacks + spying)
        assert v['analysts.target_share'] == pytest.approx(target, rel=1e-9)
        share = y[s.index['analysts.attack_share']]
        assert split_rate(field, y, t_years) == pytest.approx(
            (target - share) / v['analysts.adjust_time'], rel=1e-9, abs=1e-15
        )
        queue = v['effects_program.assessing'] / v['assessment_stage.time']
        wanted = v['effects_program.wanted_starts']
        targets = []
        for queued in (wanted / 4, wanted / 2, 3 * wanted):
            z = y.copy()
            for name in queue_names:
                z[s.index[name]] *= queued / queue
            targets.append(evaluate(field, ['analysts.target_share'], t_years, z)['analysts.target_share'])
        shorter, short, longer = targets
        assert shorter == pytest.approx(short, rel=1e-12)
        assert longer > short


@pytest.mark.parametrize(('run', 't_years'), [('ai_fast', 3), ('wartime', 1)])
def test_with_a_fixed_split_the_analysts_stay_at_todays_split(run, t_years):
    # With the option "Fixed split", the split moves back toward today's from any state, and from today's split
    # it never moves, whatever the work waiting.
    field = field_of(run, {'analysts.fixed_split': True})
    s = field.system
    for y in random_states(field, 10, seed=62):
        v = evaluate(field, ['analysts.share_now', 'analysts.adjust_time'], t_years, y)
        share = y[s.index['analysts.attack_share']]
        assert split_rate(field, y, t_years) == pytest.approx(
            (v['analysts.share_now'] - share) / v['analysts.adjust_time'], rel=1e-9, abs=1e-15
        )
        y[s.index['analysts.attack_share']] = v['analysts.share_now']
        assert split_rate(field, y, t_years) == pytest.approx(0, abs=1e-15)


@pytest.mark.parametrize('rule', [None, {'analysts.by_value': False}, {'analysts.fixed_split': True}])
def test_every_staffing_rule_gives_todays_split_at_rest(rule):
    # Today the attacks need the analysts on attacks and surveillance asks for the rest, with the same slack:
    # attacks first and surveillance first give the same split, and so does each mission's share of the work.
    field = field_of('no_ai', rule)
    v = evaluate(field, STAFFING_NAMES, 0, field.base)
    attacks, spying = analysis_needs(v)
    people = v['analysts.people']
    assert attacks / people == pytest.approx(v['analysts.share_now'], rel=1e-12)
    assert 1 - spying / people == pytest.approx(v['analysts.share_now'], rel=1e-12)
    assert v['analysts.target_share'] == pytest.approx(v['analysts.share_now'], rel=1e-12)
    assert split_rate(field, field.base, 0) == pytest.approx(0, abs=1e-15)


@pytest.mark.parametrize(
    ('run', 'values'),
    [
        ('no_ai', None),
        ('ai_fast', None),
        ('ai_slow', None),
        ('ai_reversal', None),
        ('dispersed', None),
        ('dispersed_no_ai', None),
        ('ai_fast', {'effects_program.targets_now': 2.5}),
        ('ai_fast', {'operators.retrains': True}),
    ],
    ids=['no_ai', 'ai_fast', 'ai_slow', 'ai_reversal', 'dispersed', 'dispersed_no_ai', 'targets', 'retrain'],
)
def test_every_run_without_a_surge_starts_at_rest(run, values):
    # AI progress starts at zero, so each stock starts with what passes in a year today times its mean time,
    # and nothing moves at the start (Little's law); the share of the attacks made that come from those held
    # ready is the share built in advance. Every attack carries today's targets, with the spread and the
    # independent outcomes that today's correlation of its targets gives.
    field = field_of(run, values)
    assert np.max(np.abs(field(field.start, 0.0)) * field.horizon / field.scales) <= 1e-12
    names = [
        *(name for pair in CARRIED for name in pair),
        'effects_program.held_spread',
        'effects_program.held_outcomes',
        'effects_program.assessing_outcomes',
        'effects_program.starts',
        'effects_program.attacks',
        'effects_program.attack_targets',
        'effects_program.targets_now',
        'effects_program.initial_time_now',
        'effects_program.movement_time_now',
        'payload_stage.time_now',
        'assessment_stage.time_now',
        'effects_program.built_ahead_now',
        'effects_program.use_rate',
        'defenders.within_now',
        'surveillance_program.accesses_underway',
        'surveillance_program.new_accesses',
        'surveillance_program.collected',
        'surveillance_program.processed',
        'surveillance_program.process_time',
    ]
    v = evaluate(field, names, 0, field.base)
    starts, m = v['effects_program.starts'], v['effects_program.attack_targets']
    assert m == pytest.approx(v['effects_program.targets_now'], rel=1e-12)
    times = (
        'effects_program.initial_time_now',
        'effects_program.movement_time_now',
        'payload_stage.time_now',
    )
    for (targets, attacks), time in zip(CARRIED, times):
        assert v[targets] / (starts * m) == pytest.approx(v[time], rel=1e-12)
        assert v[attacks] / starts == pytest.approx(v[time], rel=1e-12)
    for targets, attacks in CARRIED[3:]:
        assert v[targets] / v[attacks] == pytest.approx(m, rel=1e-12)
    assert v['effects_program.assessing'] / v['effects_program.attacks'] == pytest.approx(
        v['assessment_stage.time_now'], rel=1e-12
    )
    from_shelf = v['effects_program.use_rate'] * v['effects_program.held_ready']
    assert from_shelf / v['effects_program.attacks'] == pytest.approx(
        v['effects_program.built_ahead_now'], rel=1e-12
    )
    grows = 1 + (m - 1) * v['defenders.within_now']
    assert v['effects_program.held_spread'] == pytest.approx(
        v['effects_program.held_targets'] * grows, rel=1e-12
    )
    assert v['effects_program.held_outcomes'] * grows == pytest.approx(
        v['effects_program.held_targets'], rel=1e-12
    )
    assert v['effects_program.assessing_outcomes'] * grows == pytest.approx(
        v['effects_program.assessing_targets'], rel=1e-12
    )
    assert v['surveillance_program.accesses_underway'] / v[
        'surveillance_program.new_accesses'
    ] == pytest.approx(v['effects_program.initial_time_now'], rel=1e-12)
    assert v['surveillance_program.collected'] / v['surveillance_program.processed'] == pytest.approx(
        v['surveillance_program.process_time'], rel=1e-12
    )


def test_a_surge_costs_before_it_pays(trajectory_of):
    # The force pays for an attack when it starts it, and makes it only after its steps and, if it was built
    # in advance, its wait. So just after a surge of money starts, the force makes fewer attacks than it
    # starts, and the attacks that it has paid for and not yet made grow; just after the surge ends, it makes
    # more than it starts, and they fall.
    x = inputs('surge_today')
    trajectory = trajectory_of('surge_today')
    begin, length = x['leadership.surge_start'], x['leadership.surge_years']
    early = trajectory.env_at((begin + 0.05) * YEAR_H)
    late = trajectory.env_at((begin + length + 0.05) * YEAR_H)
    assert early['effects_program.attacks'] < early['effects_program.starts']
    assert late['effects_program.attacks'] > late['effects_program.starts']

    def underway(years):
        env = trajectory.env_at(years * YEAR_H)
        return sum(env[attacks] for _, attacks in CARRIED[:4])

    assert underway(begin) < underway(begin + length) > underway(begin + length + 1)


def test_a_war_uses_up_the_attacks_held_ready_and_brings_quarterly_reviews(trajectory_of):
    # The war starts from today's peacetime posture. The moments to use the attacks held ready come at once,
    # so the force makes many times the attacks that it starts, and the stock held ready soon falls to a
    # fraction of its start. The queue of assessments grows, but assessment takes at most its share of the
    # analysts' work waiting, so the analysts go on planning new attacks. From the start of the war, the
    # planners review every quarter.
    x = inputs('wartime')
    trajectory = trajectory_of('wartime')
    start = trajectory.env_at(0.0)
    early = trajectory.env_at(0.02 * YEAR_H)
    assert early['effects_program.attacks'] > 3 * early['effects_program.starts']
    assert (
        trajectory.env_at(0.5 * YEAR_H)['effects_program.held_ready']
        < start['effects_program.held_ready'] / 5
    )
    queue = []
    for t in np.linspace(0, 1, 53) * YEAR_H:
        v = trajectory.env_at(t)
        capacity = v['analysts.attack_capacity']
        assess_cost, plan_cost = v['assessment_stage.learned_cost'], v['planning_stage.learned_cost']
        wanted = v['effects_program.wanted_starts']
        asked = v['effects_program.assessing'] / v['assessment_stage.time'] * assess_cost
        part = asked / (asked + wanted * plan_cost)
        assert v['effects_program.assessed_rate'] * assess_cost <= part * capacity * (1 + 1e-9)
        planned = min(wanted, (1 - part) * capacity / plan_cost) * v['effects_program.supply']
        assert v['effects_program.starts'] >= planned * (1 - 1e-9) > 0
        queue.append(v['effects_program.assessing'])
    assert max(queue) > 3 * start['effects_program.assessing']
    reviews = [
        entry['t']
        for entry in trajectory.trace
        if entry['event'].startswith('military_planners.review.') and len(entry['event'].split('.')) == 3
    ]
    quarter = x['military_planners.war_review_interval'] * YEAR_H
    begins = x['military_planners.war_start'] * YEAR_H
    gaps = np.diff([begins, *reviews[:8]])
    assert gaps == pytest.approx(np.full(len(gaps), quarter), rel=1e-6)


@pytest.mark.parametrize(
    ('run', 't_years'), [('no_ai', 0), ('ai_fast', 4), ('ai_fast', 25), ('ai_reversal', 20)]
)
def test_the_gain_of_surveillance_is_bounded_by_its_implants_its_specialists_and_its_queue(run, t_years):
    # The specialists run the implants and their own reach in series, so the implants run lie between half
    # the smaller of the two and the smaller. What they process is at most the queue over its time and at
    # most what their number allows, and the value of surveillance, without the loss from alert defenders,
    # is the processed take over today's, to the power of the returns: so idle implants and busy specialists
    # bound what AI can add.
    field = field_of(run)
    names = [
        'surveillance_program.spying_value',
        'surveillance_program.value_now',
        'surveillance_program.reach',
        'surveillance_program.used',
        'surveillance_program.processed',
        'surveillance_program.processed_now',
        'surveillance_program.collected',
        'surveillance_program.process_time',
        'surveillance_program.process_work',
        'collection_specialists.people',
        'defenders.alertness',
        'defenders.hardening',
        'surveillance_program.implants',
    ]
    x = inputs(run)
    for y in random_states(field, 15, seed=47):
        v = evaluate(field, names, t_years, y)
        smaller = min(v['surveillance_program.implants'], v['surveillance_program.reach'])
        assert smaller / 2 - 1 <= v['surveillance_program.used'] <= smaller * (1 + 1e-12)
        assert v['surveillance_program.processed'] <= v['surveillance_program.collected'] / v[
            'surveillance_program.process_time'
        ] * (1 + 1e-12)
        assert v['surveillance_program.processed'] <= v['collection_specialists.people'] / v[
            'surveillance_program.process_work'
        ] * (1 + 1e-12)
        alert = x['surveillance_program.alert_sensitivity'] * (
            v['defenders.alertness'] - x['defenders.alert_now'] + v['defenders.hardening']
        )
        gain = v['surveillance_program.spying_value'] / v['surveillance_program.value_now'] * np.exp(alert)
        ratio = v['surveillance_program.processed'] / v['surveillance_program.processed_now']
        assert gain == pytest.approx(ratio ** x['surveillance_program.returns_scale'], rel=1e-9)


def test_attention_stays_under_its_cap_and_far_below_the_linear_rule():
    # The defenders answer the whole threat flow, counted in targets, of which the force's attacks are a
    # share. So the attention that k times today's attacks held ready, with their targets, draw is today's at
    # k = 1, never reaches the cap, grows less than the threat flow, and stays far below the k times today's
    # attention of a rule linear in the force's attacks.
    field = field_of('no_ai')
    s = field.system
    program = field.field.values_program(
        [
            expr.ref(name)
            for name in ('defenders.attention_target', 'defenders.threat', 'effects_program.attacks')
        ]
    )
    x = inputs('no_ai')
    today, cap = x['defenders.alert_now'], x['defenders.attention_cap']
    base_attacks = program(0.0, field.base)[2]
    held = ('held_ready', 'held_targets', 'held_spread', 'held_outcomes')
    for k in (1, 3, 10, 100):
        y = field.base.copy()
        for name in held:
            y[s.index[f'effects_program.{name}']] *= k
        target, threat, attacks = program(0.0, y)
        ratio = attacks / base_attacks
        if k == 1:
            assert ratio == pytest.approx(1, rel=1e-12) and target == pytest.approx(today, rel=1e-12)
        else:
            assert ratio > 1 and target < cap * today
            assert today < target <= today * threat < today * ratio


@pytest.mark.parametrize(
    ('pool', 'time', 't_years'),
    [
        ('access_pool', 'effects_program.initial_time', 0),
        ('movement_pool', 'effects_program.movement_time', 0),
        ('movement_pool', 'effects_program.movement_time', 10),
        ('effect_pool', 'payload_stage.time', 0),
        ('effect_pool', 'payload_stage.time', 25),
    ],
)
def test_a_known_flaw_serves_a_need_where_it_exists_and_the_target_has_not_fixed_it(pool, time, t_years):
    # For each need of a step, draw whether a known flaw exists, whether the target never fixes it, and the
    # time until it fixes it, exponential at the defenders' rate times the pace of the step; the force uses
    # the flaw after the time of the step. The share of needs that a known flaw serves must be the model's
    # chance of a one-day.
    v = values_at('ai_fast', [f'{pool}.one_day', time], t_years)
    x = inputs('ai_fast')
    rng = np.random.default_rng(48)
    draws = 400000
    exists = rng.random(draws) < x[f'{pool}.known']
    never = rng.random(draws) < x['defenders.residual']
    rate = x['defenders.fix_rate'] * x[f'{pool}.patch_pace']
    open_ = never | (rng.exponential(1 / rate, draws) > v[time] / YEAR_H)
    assert (exists & open_).mean() == pytest.approx(v[f'{pool}.one_day'], abs=0.005)


@pytest.mark.parametrize('short', [0.5, 0.0])
@pytest.mark.parametrize('t_years', [0, 0.5])
def test_a_pool_short_of_never_used_capabilities_holds_back_the_starts_and_its_steps(t_years, short):
    # A pool serves every ask for a never-used capability while its never-used stock holds at least the asks
    # of the supply time, and below that a share of them in proportion to the stock. The units of a step that
    # need a never-used capability pass with that share; the units that a known flaw or a capability in use
    # serves pass in full. The missions start only the operations that the pools can equip: the starts of
    # attacks and the new accesses of surveillance are what the operators can start and the analysts plan,
    # times the product of the shares of their steps' units that pass, and initial access passes its share of
    # the targets that it reaches. (At these times every step of both missions draws on its pool. Fewer
    # attacks made burn fewer capabilities, so surveillance's operators can start a little more.)
    field = field_of('ai_fast')
    s = field.system
    parts = (
        'fresh_draws',
        'available',
        'attack_served',
        'spy_served',
        'one_day',
        'attack_from_fresh',
        'spy_from_fresh',
    )
    names = [
        *(f'{pool}.{part}' for pool in POOLS for part in parts),
        'researchers.supply_time',
        'effects_program.starts',
        'effects_program.wanted_starts',
        'effects_program.planning_left',
        'planning_stage.learned_cost',
        'effects_program.attack_targets',
        'effects_program.access_rate',
        'surveillance_program.new_accesses',
        'surveillance_program.builds',
        'surveillance_program.plan_work',
        'analysts.spy_capacity',
    ]
    full = evaluate(field, names, t_years, field.base)
    y = field.base.copy()
    for pool in POOLS:
        assert full[f'{pool}.fresh_draws'] > 0
        assert full[f'{pool}.available'] == 1
        assert full[f'{pool}.attack_served'] == full[f'{pool}.spy_served'] == 1
        y[s.index[f'{pool}.fresh']] = short * full[f'{pool}.fresh_draws'] * full['researchers.supply_time']
    v = evaluate(field, names, t_years, y)
    for pool in POOLS:
        assert v[f'{pool}.available'] == pytest.approx(short, abs=1e-12)
        for mission in ('attack', 'spy'):
            waits = (1 - v[f'{pool}.one_day']) * v[f'{pool}.{mission}_from_fresh']
            assert v[f'{pool}.{mission}_served'] == pytest.approx(1 - waits * (1 - short), rel=1e-12)
            assert v[f'{pool}.{mission}_served'] > 0
    attack_pass = math.prod(
        v[f'{pool}.attack_served'] for pool in ('access_pool', 'movement_pool', 'effect_pool')
    )
    spy_pass = math.prod(
        v[f'{pool}.spy_served'] for pool in ('access_pool', 'movement_pool', 'collection_pool')
    )
    assert attack_pass < 1 and spy_pass < 1
    for w in (full, v):
        attacks = min(
            w['effects_program.wanted_starts'],
            w['effects_program.planning_left'] / w['planning_stage.learned_cost'],
        )
        accesses = min(
            w['surveillance_program.builds'], w['analysts.spy_capacity'] / w['surveillance_program.plan_work']
        )
        passes = (1, 1) if w is full else (attack_pass, spy_pass)
        assert w['effects_program.starts'] == pytest.approx(attacks * passes[0], rel=1e-12)
        assert w['surveillance_program.new_accesses'] == pytest.approx(accesses * passes[1], rel=1e-12)
    assert v['effects_program.starts'] == pytest.approx(
        full['effects_program.starts'] * attack_pass, rel=1e-12
    )
    rates = field.rates_of(y, t_years * YEAR_H)
    passed = (
        v['effects_program.starts'] * v['effects_program.attack_targets']
        - rates[s.index['effects_program.in_access']]
    )
    assert passed == pytest.approx(
        v['effects_program.access_rate'] * v['access_pool.attack_served'], rel=1e-9
    )


WORKFORCE_NAMES = [
    'operators.people',
    'operators.idle',
    'operators.retrain_time',
    'leadership.attack_experts',
    'effects_program.starts',
    'effects_program.operator_cost',
    'surveillance_program.spying_experts',
    'surveillance_program.new_accesses',
    'surveillance_program.initial_work',
    'surveillance_program.deploy_work',
    'surveillance_program.deploy_survival',
]


@pytest.mark.parametrize(('run', 't_years'), [('ai_fast', 10), ('analysts_one_share', 15), ('wartime', 1)])
def test_only_operators_who_wait_for_the_analysts_retrain(run, t_years):
    # With the option "Idle operators retrain", the share of the operators who do analysis work grows at the
    # idle operators over all of the operators and the time to retrain. An idle operator is an hour that the
    # operations started do not use: the operators' hours on each mission less the work of the attacks or the
    # accesses that it starts. So the share does not grow where the analysts plan all that the operators can
    # start, and without the option it never grows.
    on, off = field_of(run, {'operators.retrains': True}), field_of(run)
    i = on.system.index['operators.retrained_share']

    def idle_of(y):
        v = evaluate(on, WORKFORCE_NAMES, t_years, y)
        attack_idle = (
            v['leadership.attack_experts'] - v['effects_program.starts'] * v['effects_program.operator_cost']
        )
        access_work = (
            v['surveillance_program.initial_work']
            + v['surveillance_program.deploy_work'] * v['surveillance_program.deploy_survival']
        )
        spy_idle = (
            v['surveillance_program.spying_experts'] - v['surveillance_program.new_accesses'] * access_work
        )
        return v, max(attack_idle, 0.0) + max(spy_idle, 0.0)

    idle_seen = False
    for y in random_states(on, 12, seed=61):
        v, idle = idle_of(y)
        people = v['operators.people']
        assert v['operators.idle'] == pytest.approx(idle, rel=1e-9, abs=1e-9 * people)
        growth = on.rates_of(y, t_years * YEAR_H)[i]
        assert growth == pytest.approx(idle / people / v['operators.retrain_time'], rel=1e-9, abs=1e-18)
        assert off.rates_of(y, t_years * YEAR_H)[i] == 0
        idle_seen |= idle > 1e-3 * people
    assert idle_seen
    # With most operators retrained, the analysts plan all that the few operators left can start: none waits,
    # and the share stays where it is.
    y = state_with(on, {'operators.retrained_share': 0.9})
    v, idle = idle_of(y)
    assert idle == pytest.approx(0, abs=1e-12 * v['operators.people'])
    assert v['operators.idle'] == 0 == on.rates_of(y, t_years * YEAR_H)[i]


def test_retrained_operators_leave_the_operations_for_analysis_and_none_retrain_today():
    # Today no operator waits for the analysts, so with the option on, today stays at rest. A retrained share
    # takes that share of the operators from the operations of both missions and adds that share of the
    # operators, at the efficiency of a retrained operator, to the analysts' capacity.
    field = field_of('ai_fast', {'operators.retrains': True})
    assert np.max(np.abs(field(field.start, 0.0)) * field.horizon / field.scales) <= 1e-12
    today = evaluate(field, ['operators.idle', 'operators.people'], 0, field.base)
    assert today['operators.idle'] == pytest.approx(0, abs=1e-12 * today['operators.people'])
    names = [
        'leadership.attack_experts',
        'surveillance_program.spying_experts',
        'operators.people',
        'operators.retrain_efficiency',
        'analysts.capacity',
        'analysts.load_now',
    ]
    fixed = evaluate(field, names, 5, state_with(field, {'operators.retrained_share': 0.0}))
    moved = evaluate(field, names, 5, state_with(field, {'operators.retrained_share': 0.3}))
    working = ('leadership.attack_experts', 'surveillance_program.spying_experts')
    assert sum(moved[name] for name in working) == pytest.approx(
        0.7 * sum(fixed[name] for name in working), rel=1e-12
    )
    added = (
        moved['operators.retrain_efficiency'] * 0.3 * moved['operators.people'] / moved['analysts.load_now']
    )
    assert moved['analysts.capacity'] - fixed['analysts.capacity'] == pytest.approx(added, rel=1e-9)


RETURN_NAMES = [
    'leadership.assessed_return',
    'leadership.attack_experts',
    'leadership.return_gap',
    'leadership.target_share',
    'leadership.share_floor',
    'leadership.share_ceiling',
    'leadership.proportional_rate',
    'surveillance_program.spying_return',
    'surveillance_program.spying_return_now',
    'effects_program.risk_value',
    'effects_program.attack_cost',
    'effects_program.assessment_bias',
]


def at_return_ratio(run, t_years, changes, ratio, values=None):
    """The field of `run`, the start state with `changes` and with the assessment error that makes the assessed
    return of an operator on attacks `ratio` times the current return of one on surveillance, and the values
    there. Only the leaders' assessment sets the error, so the field holds it in its base state."""
    field = field_of(run, values)
    v = evaluate(field, RETURN_NAMES, t_years, state_with(field, changes))
    value = (
        ratio * v['surveillance_program.spying_return'] * v['leadership.attack_experts']
        + v['effects_program.attack_cost']
    )
    error = math.log(value / v['effects_program.risk_value']) - v['effects_program.assessment_bias']
    assert -4 < error < 4
    field = vector_field(
        catalogue_model('cyber_learning_loop'), run, values, state={'leadership.assessment_error': error}
    )
    y = state_with(field, changes)
    return field, y, evaluate(field, RETURN_NAMES, t_years, y)


@pytest.mark.parametrize('ratio', [0.5, 2.0])
def test_the_leaders_compare_the_returns_of_the_missions_by_their_ratio_at_any_level(ratio):
    # The split responds to the assessed return of an operator on attacks as a share of the current return of
    # one on surveillance. So attacks that return twice what surveillance returns now push the split as hard
    # at the end of AI progress, with a larger queue of take and fewer operators on surveillance, as they do
    # today; and in the proportional form the split moves at its rate times its room times the same gap.
    _, _, today = at_return_ratio('no_ai', 0, {}, ratio)
    later_state = {'surveillance_program.collected': (3,), 'leadership.attack_share': 0.8}
    _, _, later = at_return_ratio('ai_fast', 25, later_state, ratio)
    assert later['surveillance_program.spying_return'] > 2 * later['surveillance_program.spying_return_now']
    for v in (today, later):
        assert v['leadership.assessed_return'] / v['surveillance_program.spying_return'] == pytest.approx(
            ratio, rel=1e-12
        )
        assert v['leadership.return_gap'] == pytest.approx(ratio - 1, rel=1e-9)
    assert later['leadership.target_share'] == pytest.approx(today['leadership.target_share'], rel=1e-9)
    field, y, v = at_return_ratio('ai_fast', 25, later_state, ratio, {'leadership.proportional': True})
    share = y[field.system.index['leadership.attack_share']]
    room = (share - v['leadership.share_floor']) * (v['leadership.share_ceiling'] - share)
    expected = v['leadership.proportional_rate'] * room * (ratio - 1)
    assert field.rates_of(y, 25 * YEAR_H)[field.system.index['leadership.attack_share']] == pytest.approx(
        expected, rel=1e-9
    )


def test_the_value_of_lessons_has_no_jump_where_the_analysts_start_to_limit_the_attacks():
    # With foresight, the leaders also fund attacks for the value of their lessons, which counts the attacks
    # that a lesson lets the force start: those that the operators can start, as far as the analysts plan
    # them. Where the analysts start to limit the attacks, that value has a kink but no jump, so the funding
    # rule cannot chatter there: across the surface, the change of the value and of the split's rate shrinks
    # with the distance from it, as a continuous field's does.
    field = field_of('ai_fast_lessons')
    s = field.system
    t_years = 5
    names = [
        'effects_program.starts',
        'effects_program.wanted_starts',
        'effects_program.crowding',
        'effects_program.lesson_value',
    ]

    def at(share):
        y = field.base.copy()
        y[s.index['analysts.attack_share']] = share
        v = evaluate(field, names, t_years, y)
        rate = field.rates_of(y, t_years * YEAR_H)[s.index['leadership.attack_share']]
        return v, np.array([v['effects_program.crowding'], v['effects_program.lesson_value'], rate])

    def limited(share):
        v, _ = at(share)
        return v['effects_program.starts'] < v['effects_program.wanted_starts']

    # The share of the analysts on attacks at which they plan exactly the attacks that the operators can start.
    low, high = 0.0, 1.0
    assert limited(low) and not limited(high)
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (middle, high) if limited(middle) else (low, middle)
    edge = (low + high) / 2
    jumps = []
    for step in (1e-4, 1e-6):
        below, above = at(edge - step)[1], at(edge + step)[1]
        assert below[0] < 1 == above[0]
        jumps.append(np.abs(above - below))
    assert np.all(jumps[0] > 0)
    assert np.all(jumps[1] <= 0.05 * jumps[0])


def test_lasting_defender_gains_lower_both_attacks_and_surveillance():
    names = ['effects_program.success', 'surveillance_program.spying_value', 'defenders.hardening']
    none = values_at('ai_fast', names, 10, {'defenders.ai_hardening': 0, 'defenders.hardening_rate': 0})
    some = values_at('ai_fast', names, 10, {'defenders.ai_hardening': 1, 'defenders.hardening_rate': 0.05})
    assert none['defenders.hardening'] == 0 < some['defenders.hardening']
    assert some['effects_program.success'] < none['effects_program.success']
    assert some['surveillance_program.spying_value'] < none['surveillance_program.spying_value']


@pytest.mark.parametrize('t_years', [0, 10])
def test_each_doubling_of_the_lessons_of_access_saves_its_share_of_the_work_of_access(t_years):
    # Wright's law for the stage that surveillance also does: doubling the lessons of access multiplies its
    # work by one less the learning share, and leaves the stages that only attacks do as they are. More
    # lessons of effects do the reverse.
    field = field_of('ai_fast')
    index = field.system.index
    names = [f'{s}.learned_cost' for s in STAGES]
    program = field.field.values_program([expr.ref(name) for name in names])
    t = t_years * YEAR_H
    base = dict(zip(names, program(t, field.base)))
    y = field.base.copy()
    y[index['effects_program.access_know_how']] *= 2
    doubled = dict(zip(names, program(t, y)))
    saved = 1 - inputs('ai_fast')['effects_program.access_learning']
    for s in STAGES:
        ratio = doubled[f'{s}.learned_cost'] / base[f'{s}.learned_cost']
        assert ratio == pytest.approx(saved if s == 'access_stage' else 1, rel=1e-12)
    y = field.base.copy()
    y[index['effects_program.know_how']] *= 4
    learned = dict(zip(names, program(t, y)))
    ratios = {s: learned[f'{s}.learned_cost'] / base[f'{s}.learned_cost'] for s in STAGES}
    assert ratios.pop('access_stage') == pytest.approx(1, rel=1e-12)
    first = next(iter(ratios.values()))
    assert first < 1 and all(r == pytest.approx(first, rel=1e-12) for r in ratios.values())
