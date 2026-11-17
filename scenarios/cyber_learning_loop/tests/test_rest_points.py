"""The scenario's rest points and their properties, against independent mathematics.

The oracle `rest_point.py` builds today's rest point from the specification with no engine code: the four groups of
experts, the attack chain by Little's law (the attacks in each step next to their targets, and what the attacks
held ready and assessed carry), each pool of capabilities by solving its six balances numerically, and
surveillance's chain in the order that its losses give. The engine reads its start values from the model; they
must be the oracle's, stock by stock, for the default inputs and for edited inputs that move each part.

At any state and time the oracle computes the rate of change of each of the 47 stocks from its own rules: the
operators' and the analysts' priorities, the steps and the targets that each attack carries, the sources of each
zero-day and the share of the asks that a pool can serve, research to need, the collection specialists' queue,
the lessons, the defenders' attention, the two splits and the workforce. Along a run, and at states pushed into
the other branches of those rules, the engine's rates must be the oracle's. Newton's method finds a rest point of
the engine's field at frozen t; the oracle's rates must vanish there, and they must not vanish a little away
from it.

The other tests check properties that follow from the specification without a computed value: today's split is
a rest point under every form of the rules, today's split of the experts lies in the staff ratios of the
evidence, and the value of the lessons of an expert is the slope of the net value where the operators limit the
attacks, and a continuous blend of the two limits' slopes where the analysts limit them."""

from __future__ import annotations

import numpy as np
import pytest

from napkin.core import expr
from napkin.dynamics import vector_field
from napkin.dynamics.equilibria import newton
from scenarios.cyber_learning_loop.tests.rest_point import (
    CHAIN,
    POOLS,
    STOCKS,
    SURVEILLANCE,
    balances,
    rates_at,
    today,
)
from scenarios.tests.sources import oracle_inputs
from tests.helpers import catalogue_model

YEAR_H = 8760.0


def oracle(model, run, values=None):
    return oracle_inputs('cyber_learning_loop', model.resolve(run, values).parameter_values)


def spec_state(field, y):
    """The whole state `y` (execution units) in each quantity's own unit."""
    s = field.system
    return {name: float(y[i]) / s.units.scale(s.quantities[name].unit) for i, name in enumerate(s.state_ids)}


def engine_state(field, state):
    """The whole state in execution units from the values in each quantity's own unit."""
    s = field.system
    y = field.base.copy()
    for name, value in state.items():
        y[s.index[name]] = value * s.units.scale(s.quantities[name].unit)
    return y


def expected_today(x):
    """The oracle's rest point today, by the engine's names."""
    o = today(x)
    out = {f'effects_program.{name}': o['chain'][name] for name in CHAIN}
    out.update({f'surveillance_program.{name}': o['surveillance'][name] for name in SURVEILLANCE})
    out.update({f'{pool}.{name}': o['pools'][pool][name] for pool in POOLS for name in STOCKS})
    out.update(
        {
            'leadership.attack_share': o['share0'],
            'analysts.attack_share': o['analyst_share0'],
            'effects_program.know_how': o['lessons0'],
            'effects_program.access_know_how': o['access0'],
            'defenders.alertness': x['alert_now'],
            'operators.retrained_share': 0.0,
        }
    )
    return o, out


@pytest.mark.parametrize(
    'values',
    [
        None,
        {'effects_program.initial_share': 0.3},
        {'surveillance_program.own_source': 0.8, 'surveillance_program.attack_source': 0.0},
        {'effects_program.spy_source': 0.3, 'effects_program.reuse_source': 0.1},
        {'effects_program.exposure': 0.6, 'surveillance_program.find_share': 0.2},
        {'surveillance_program.loss_rate': 1.0, 'surveillance_program.used_now': 0.3},
        {'surveillance_program.process_time': 0.5, 'analysts.load_now': 0.6},
        # The routes of loss of a flaw, unused and in use, the reserve, and several targets per attack today
        # with another correlation: the stocks that the attacks carry differ from their targets.
        {
            'researchers.reserve_time': 3,
            'defenders.discovery_now': 0.12,
            'defenders.use_discovery_now': 0.4,
            'defenders.patch_now': 0.09,
            'defenders.irrelevance_now': 0.01,
            'effects_program.targets_now': 2,
            'defenders.within_now': 0.6,
        },
        # The price of compute and of supervision moves today's cost of an attack, so today's attacks.
        {'effects_program.compute_now': 0.5, 'effects_program.parallel_now': 2},
        # The staffing rules and the workforce leave today's state as it is, and at rest.
        {
            'analysts.by_value': False,
            'operators.retrains': True,
            'surveillance_program.plan_target_weight': 0.3,
        },
        {'analysts.fixed_split': True},
    ],
)
def test_todays_state_is_the_rest_point_of_the_specification(values):
    model = catalogue_model('cyber_learning_loop')
    x = oracle(model, 'no_ai', values)
    field = vector_field(model, 'no_ai', values)
    start = spec_state(field, field.base)
    o, expected = expected_today(x)
    # The oracle sets every stock that the engine follows.
    assert set(expected) == set(field.names)
    for name, value in expected.items():
        assert start[name] == pytest.approx(value, rel=1e-9, abs=1e-9), name
    # The groups of experts and the attacks of a year today, as the model computes them.
    names = [
        'operators.people',
        'operators.attack_now',
        'collection_specialists.people',
        'analysts.people',
        'analysts.capacity',
        'researchers.people',
        'effects_program.attacks_now',
        'researchers.need_now',
    ]
    got = dict(zip(names, field.field.values_program([expr.ref(name) for name in names])(0.0, field.base)))
    assert got['operators.people'] == pytest.approx(o['operators'], rel=1e-12)
    assert got['operators.attack_now'] == pytest.approx(o['attack_ops'], rel=1e-12)
    assert got['collection_specialists.people'] == pytest.approx(o['specialists'], rel=1e-12)
    assert got['analysts.people'] == pytest.approx(o['analysts'], rel=1e-12)
    assert got['analysts.capacity'] == pytest.approx(o['capacity'], rel=1e-12)
    assert got['researchers.people'] == pytest.approx(o['researchers'], rel=1e-12)
    assert got['effects_program.attacks_now'] * YEAR_H == pytest.approx(o['n0'], rel=1e-12)
    assert got['researchers.need_now'] * YEAR_H == pytest.approx(o['research'], rel=1e-9)
    # The four groups are all of the experts.
    assert o['researchers'] + o['operators'] + o['specialists'] + o['analysts'] == pytest.approx(x['experts'])
    # The oracle's own rates vanish there too.
    rates, _ = balances(x, start, 0.0)
    assert max(abs(r) for r in rates.values()) <= 1e-9


# States of a run pushed into the other branches of the rules: retrained operators, too few operators on
# attacks to execute every attack that waits, two pools short of never-used capabilities, and few analysts on
# attacks, so that the analysts limit the attacks.
PUSHED = {
    'as run': {},
    'retrained operators': {'operators.retrained_share': 0.1},
    'few operators on attacks': {'leadership.attack_share': 0.01},
    'pools short of new capabilities': {'effect_pool.fresh': 0.3, 'access_pool.fresh': 0.5},
    'few analysts on attacks': {'analysts.attack_share': 0.1},
}


@pytest.mark.parametrize(
    'values',
    [
        None,
        {'analysts.by_value': False},
        {'analysts.fixed_split': True},
        {'operators.retrains': True, 'surveillance_program.plan_target_weight': 0.3},
        {
            'planning_stage.split_ai': False,
            'assessment_stage.split_ai': False,
            'effects_program.risk_aversion': 2,
        },
    ],
)
def test_along_a_run_each_stock_moves_at_the_rate_of_the_specification(values, trajectory_of):
    # Early in fast AI progress the attacks held ready and in the steps carry fewer targets than the attacks
    # that start now, so a rule that reads the targets of an attack must read its own targets.
    model = catalogue_model('cyber_learning_loop')
    x = oracle(model, 'ai_fast', values)
    field = vector_field(model, 'ai_fast', values)
    s = field.system
    trajectory = trajectory_of('ai_fast')
    found = {}
    for years in (1.0, 3.0, 6.0):
        env = trajectory.env_at(years * YEAR_H)
        run = spec_state(field, field.full(np.array([env[name] for name in field.names])))
        for label, move in PUSHED.items():
            state = {**run, **move}
            engine = field.rates_of(engine_state(field, state), years * YEAR_H)
            expected, found[years, label] = rates_at(x, state, years)
            for name in field.names:
                got = engine[s.index[name]] * YEAR_H / s.units.scale(s.quantities[name].unit)
                assert got == pytest.approx(
                    expected[name], rel=1e-8, abs=1e-9 * max(abs(state[name]), 1.0)
                ), (
                    years,
                    label,
                    name,
                )
            if not move:
                found[years, 'held size'] = (
                    state['effects_program.held_targets'] / state['effects_program.held_ready']
                )
    # The states reach each branch: attacks that carry fewer targets than the attacks that start now, execution
    # that waits for the operators, pools that serve only a part of their asks, and starts that the analysts
    # limit.
    assert found[3.0, 'held size'] < 0.8 * found[3.0, 'as run']['targets']
    assert found[3.0, 'few operators on attacks']['served'] < 1
    assert min(found[3.0, 'pools short of new capabilities']['available'].values()) < 1
    few = found[3.0, 'few analysts on attacks']
    assert few['starts'] < few['wanted']


@pytest.mark.parametrize(
    ('run', 't_years'),
    [
        ('ai_slow', 25.0),
        pytest.param('ai_fast', 6.0, marks=pytest.mark.deep),
        pytest.param('defenders_ai', 10.0, marks=pytest.mark.deep),
    ],
)
def test_the_engine_rest_points_are_rest_points_of_the_specification(run, t_years, trajectory_of):
    model = catalogue_model('cyber_learning_loop')
    x = oracle(model, run)
    field = vector_field(model, run)
    env = trajectory_of(run).env_at(t_years * YEAR_H)
    start = np.array([env[name] for name in field.names])
    z, converged = newton(field, start, t=t_years * YEAR_H)
    assert converged
    state = spec_state(field, field.full(z))
    rates, found = balances(x, state, t_years)
    assert max(abs(r) for r in rates.values()) <= 1e-9, max(rates.items(), key=lambda kv: abs(kv[1]))
    # A rest point away from today's: the stocks moved, so the test is not today's rest point again.
    assert abs(state['leadership.attack_share'] - today(x)['share0']) > 1e-3
    # A small move of the split, of the analysts' split, of a pool's stock or of the targets that the attacks
    # held ready carry leaves the rest.
    for name, step in (
        ('leadership.attack_share', 0.01),
        ('analysts.attack_share', 0.01),
        ('access_pool.spy_used', 0.05 * state['access_pool.spy_used']),
        ('effects_program.held_targets', 0.05 * state['effects_program.held_targets']),
    ):
        moved = {**state, name: state[name] + step}
        assert max(abs(r) for r in balances(x, moved, t_years)[0].values()) > 1e-6, name
    # At rest what enters the chain leaves it: the attacks started are made and assessed, and so are their
    # targets. So every attack carries the targets of the attacks that start now, with their correlation.
    m, rho = found['targets'], found['correlation']
    assert found['attacks'] == pytest.approx(found['starts'], rel=1e-9)
    assert found['assessed'] == pytest.approx(found['starts'], rel=1e-9)
    assert found['made_targets'] == pytest.approx(found['starts'] * m, rel=1e-9)
    for targets, attacks in (
        ('in_access', 'in_access_attacks'),
        ('accesses', 'access_attacks'),
        ('positioned', 'positioned_attacks'),
        ('held_targets', 'held_ready'),
        ('assessing_targets', 'assessing'),
    ):
        assert state[f'effects_program.{targets}'] / state[f'effects_program.{attacks}'] == pytest.approx(
            m, rel=1e-9
        ), targets
    spread = 1 + (m - 1) * rho
    held = state['effects_program.held_targets']
    assert state['effects_program.held_spread'] / held == pytest.approx(spread, rel=1e-9)
    assert state['effects_program.held_outcomes'] / held == pytest.approx(1 / spread, rel=1e-9)
    assert state['effects_program.assessing_outcomes'] / state['effects_program.assessing_targets'] == (
        pytest.approx(1 / spread, rel=1e-9)
    )


@pytest.mark.parametrize(
    'values',
    [
        {'leadership.foresight': 1},
        {'leadership.foresight': 1, 'effects_program.exponential_curve': True},
        {'leadership.foresight': 1, 'effects_program.risk_aversion': 2},
        {'leadership.foresight': 0.5, 'leadership.proportional': True, 'effects_program.burn_share': 0.5},
        {'leadership.foresight': 1, 'analysts.by_value': False},
        {'analysts.fixed_split': True, 'operators.retrains': True},
        {'surveillance_program.plan_target_weight': 0.3, 'researchers.supply_time': 0.25},
    ],
)
def test_todays_split_is_at_rest_under_every_form_of_the_rules(values):
    # With foresight, the assessed return adds the value of lessons. The calibration must solve that whole
    # return for the value of one effect, or the split moves at once without AI. Every staffing rule of the
    # analysts gives today's split, no operator waits today, and today's never-used stocks serve every ask.
    model = catalogue_model('cyber_learning_loop')
    field = vector_field(model, 'no_ai', values)
    for years in (0, 10):
        assert np.max(np.abs(field(field.start, years * YEAR_H)) * field.horizon / field.scales) <= 1e-12


def test_todays_split_of_the_experts_lies_in_the_staff_ratios_of_the_evidence():
    # The workbook's staff ratios of surveillance to attack-oriented staff run from 6.3:1 to 12.7:1 (NSA
    # against the whole Cyber Mission Force, and GCHQ against its offensive staff). Today's experts on
    # surveillance (its operators, its planners and the collection specialists) over the experts on attacks
    # (operators and analysts) follow from today's work of each kind of expert, and must lie in that range.
    model = catalogue_model('cyber_learning_loop')
    field = vector_field(model, 'no_ai')
    names = [
        'operators.spy_now',
        'surveillance_program.planners_now',
        'collection_specialists.people',
        'operators.attack_now',
        'effects_program.analyst_work_now',
    ]
    v = dict(zip(names, field.field.values_program([expr.ref(name) for name in names])(0.0, field.base)))
    surveillance = (
        v['operators.spy_now'] + v['surveillance_program.planners_now'] + v['collection_specialists.people']
    )
    attacks = v['operators.attack_now'] + v['effects_program.analyst_work_now']
    assert 6.3 <= surveillance / attacks <= 12.7


# The value of lessons: the funding rule with foresight credits an operator on attacks with the change of the
# yearly net value for one more lesson, at rest. The stocks of the attack chain and the analysts' split are at
# rest for the lessons, with the operators' split, the attention, the pools and surveillance held. The burned
# surveillance is set to none: the model counts it per attack, which holds where the pools' stocks follow the
# attacks.
LESSONS_RUN = 'ai_fast_lessons'
LESSONS_YEARS = 6.0
LESSON_VALUES = [
    'effects_program.attack_value',
    'effects_program.attack_cost',
    'effects_program.value_slope',
    'effects_program.cost_slope',
    'effects_program.gain_slope',
    'effects_program.attack_slope',
    'effects_program.crowding',
    'effects_program.lesson_value',
    'effects_program.starts',
    'effects_program.wanted_starts',
    'effects_program.gain',
    'effects_program.operator_cost',
    'effects_program.effects_base',
]


def lessons_field(values):
    model = catalogue_model('cyber_learning_loop')
    values = {'surveillance_program.find_share': 0, **values}
    field = vector_field(model, LESSONS_RUN, values)
    program = field.field.values_program([expr.ref(name) for name in LESSON_VALUES])
    cost_learning = model.resolve(LESSONS_RUN, values).parameter_values['effects_program.cost_learning']
    return field, program, cost_learning


def chain_rows(field, analysts=True):
    index = field.system.index
    rows = [index[f'effects_program.{name}'] for name in CHAIN]
    return np.array(rows + ([index['analysts.attack_share']] if analysts else []))


def at_rest(field, y, t, rows, tol=1e-13):
    """`y` with the quantities `rows` at rest of the field at frozen t, the others held: implicit Euler steps
    from a month that double, then Newton's method with least-norm steps, because the backlog of initial access
    is neutral where the operators' hours limit it. A step falls at most to a tenth of a stock, so that no
    stock of attacks empties while its targets stay."""
    size = field.system.sizes[rows].astype(float)

    def drift(z):
        w = y.copy()
        w[rows] = z * size
        return field.rates_of(w, t)[rows] / size * YEAR_H

    def jacobian(z):
        h = 1e-7 * np.maximum(np.abs(z), 1.0)
        columns = []
        for j in range(len(z)):
            up, down = z.copy(), z.copy()
            up[j] += h[j]
            down[j] -= h[j]
            columns.append((drift(up) - drift(down)) / (2 * h[j]))
        return np.array(columns).T

    z = y[rows] / size
    if np.max(np.abs(drift(z))) > 1e-6:
        dt = 1 / 12
        for _ in range(30):
            z = np.maximum(z + np.linalg.solve(np.eye(len(z)) / dt - jacobian(z), drift(z)), z / 10)
            dt *= 2
    rate = drift(z)
    for _ in range(60):
        if np.max(np.abs(rate)) <= tol:
            break
        step = np.linalg.lstsq(jacobian(z), -rate, rcond=1e-12)[0]
        damping = 1.0
        while damping > 1e-6:
            trial = np.maximum(z + damping * step, z / 10)
            found = drift(trial)
            if np.max(np.abs(found)) < np.max(np.abs(rate)):
                break
            damping /= 2
        z, rate = trial, found
    assert np.max(np.abs(rate)) <= tol, 'the stocks of attacks found no rest'
    w = y.copy()
    w[rows] = z * size
    return w


def slopes_at(field, program, y, t, rows, h):
    """The model's values at the rest for the lessons of `y`, and at the rests for h more and h fewer
    lessons."""
    k = field.system.index['effects_program.know_how']
    y = at_rest(field, y, t, rows)
    up, down = y.copy(), y.copy()
    up[k] += h
    down[k] -= h
    up, down = at_rest(field, up, t, rows), at_rest(field, down, t, rows)
    values = [dict(zip(LESSON_VALUES, program(t, state))) for state in (y, up, down)]
    return y, values


def test_the_value_of_lessons_is_the_slope_of_the_net_value():
    # Where the operators limit the attacks, a lesson cuts the operators' work and the force starts more
    # attacks: there the value of lessons is the slope of the net value, exactly. A central difference of the
    # model's own net value at rest must give it, and of the attacks at rest the slope of the attacks.
    field, program, _ = lessons_field({})
    t = LESSONS_YEARS * YEAR_H
    rows = chain_rows(field)
    k = field.system.index['effects_program.know_how']
    y = field.base.copy()
    for lessons in (800.0, 4000.0, 20000.0):
        y[k] = lessons
        h = 1e-4 * lessons
        y, (rest, up, down) = slopes_at(field, program, y, t, rows, h)
        assert rest['effects_program.starts'] == rest['effects_program.wanted_starts']
        assert rest['effects_program.crowding'] == 1
        net = [v['effects_program.attack_value'] - v['effects_program.attack_cost'] for v in (up, down)]
        slope = (rest['effects_program.value_slope'] - rest['effects_program.cost_slope']) * rest[
            'effects_program.gain_slope'
        ]
        assert slope == pytest.approx((net[0] - net[1]) / (2 * h), rel=1e-6)
        gain = up['effects_program.gain'] - down['effects_program.gain']
        attacks = (up['effects_program.starts'] - down['effects_program.starts']) / gain
        assert rest['effects_program.attack_slope'] == pytest.approx(attacks, rel=1e-6)


def operators_slope(values, cost_learning):
    """The slope of the attacks in the gain where the operators limit them: the attacks wanted grow as the
    operators' work of the stages that learn from attacks falls."""
    return (
        values['effects_program.wanted_starts']
        * cost_learning
        * values['effects_program.effects_base']
        / values['effects_program.operator_cost']
    )


def test_where_the_analysts_limit_the_attacks_the_slope_blends_the_slopes_of_the_two_limits():
    # Where the analysts limit the attacks, their work for each attack sets the attacks, and a lesson that cuts
    # it lets them plan more. With the analysts' split fixed, the attacks at rest are the analysts on attacks
    # over their work of one attack, so the slope of the attacks in the gain follows from the work alone: a
    # central difference at rest must give the part of the model's slope that is not the operators' slope.
    # The blend weighs the two slopes by the share of the attacks wanted that start, which is below 1 here.
    field, program, cost_learning = lessons_field({'analysts.fixed_split': True})
    t = LESSONS_YEARS * YEAR_H
    rows = chain_rows(field)
    k = field.system.index['effects_program.know_how']
    y = field.base.copy()
    for lessons in (800.0, 4000.0):
        y[k] = lessons
        y, (rest, up, down) = slopes_at(field, program, y, t, rows, 1e-4 * lessons)
        crowding = rest['effects_program.crowding']
        assert crowding == pytest.approx(
            rest['effects_program.starts'] / rest['effects_program.wanted_starts'], rel=1e-12
        )
        assert crowding < 0.95
        gain = up['effects_program.gain'] - down['effects_program.gain']
        attacks = (up['effects_program.starts'] - down['effects_program.starts']) / gain
        analysts_part = (
            rest['effects_program.attack_slope'] - crowding * operators_slope(rest, cost_learning)
        ) / (1 - crowding)
        assert analysts_part == pytest.approx(attacks, rel=1e-6)


def test_the_value_of_lessons_is_continuous_where_the_two_limits_meet():
    # At the rest of the default rules the operators limit the attacks. Fewer analysts on attacks, with the
    # stocks held, move the attacks across the point where the analysts' limit meets the operators'. There the
    # slope of the attacks is the operators' slope from both sides, and the value of lessons has no jump: its
    # change across the point falls with the width of the step, as a continuous value's does.
    field, program, cost_learning = lessons_field({})
    t = LESSONS_YEARS * YEAR_H
    index = field.system.index
    y = field.base.copy()
    y[index['effects_program.know_how']] = 800.0
    y = at_rest(field, y, t, chain_rows(field))
    share = index['analysts.attack_share']

    def values(analysts):
        w = y.copy()
        w[share] = analysts
        return dict(zip(LESSON_VALUES, program(t, w)))

    def limited(analysts):
        v = values(analysts)
        return v['effects_program.starts'] < v['effects_program.wanted_starts']

    low, high = 0.5 * y[share], y[share]
    assert limited(low) and not limited(high)
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (low, middle) if not limited(middle) else (middle, high)
    meet = values(high)
    jumps = []
    for width in (1e-3, 1e-6):
        below, above = values(high - width), values(high + width)
        assert below['effects_program.starts'] < below['effects_program.wanted_starts']
        assert above['effects_program.crowding'] == 1
        assert above['effects_program.attack_slope'] == pytest.approx(operators_slope(above, cost_learning))
        jumps.append(abs(above['effects_program.lesson_value'] - below['effects_program.lesson_value']))
    assert below['effects_program.attack_slope'] == pytest.approx(
        operators_slope(meet, cost_learning), rel=1e-4
    )
    assert jumps[1] <= 1e-2 * jumps[0] + 1e-9 * abs(meet['effects_program.lesson_value'])
