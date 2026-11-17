"""Independent mathematical oracles for the numerical runtime."""

import copy
import json
import math
import pickle

import numpy as np
import pytest

import napkin.engine.continuous.integrate as integrate
import napkin.engine.runtime as runtime
from napkin.core import expr as nodes
from napkin.engine.continuous.bounds import correct_boundary_roundoff
from napkin.engine.continuous.fields import Field
from napkin.engine.continuous.kernels import MatrixExponential
from napkin.engine.continuous.system import Run, System, initial_store
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import SimulationError
from napkin.expressions import ExpressionError, UnitSystem, evaluate
from napkin.model import ModelError
from tests.build import (
    UNITS,
    check,
    compiled,
    edit,
    event,
    flow,
    formula,
    library,
    member,
    move,
    named,
    once_at,
    output,
    parameter,
    places,
    rejected,
    replace,
    resolved,
    run,
    share,
    stock,
    system,
)


def switch(name, state, source, target, time):
    """An event `name` that moves named state `state` from `source` to `target` at a fixed time."""
    return event(name, f't >= {time}', once=False, transition=f'{state} "{source}" -> "{target}"')


def with_timescales(text, *timescales):
    """A text whose solver keeps its steps shorter than each of `timescales`."""
    return edit(text, member('scenario:', f'timescales {", ".join(timescales)}'))


# A cohort beside the other values that leaves at cohort e^{-t / 1 h} an hour: a rate that reads the
# time keeps a segment on the numerical solver, where the exact kernels would take a linear system.
TIMED_COHORT = (
    stock('cohort', 1, kind='state'),
    flow('cohort_decay', move('cohort', None), 'cohort / 1 h * exp(-t / 1 h)'),
)


def decay(name, initial):
    """`name` decays at its own value an hour: a' = -a / 1 h."""
    return stock(name, initial, kind='state'), flow(f'{name}_decay', move(name, None), f'{name} / 1 h')


def held(name, initial, **lines):
    """A stock that nothing moves: a flow of nothing takes from it, so it has the bounds of a stock."""
    return stock(name, initial, **lines), flow(f'{name}_out', move(name, None), 0)


@pytest.mark.parametrize('hazard', [0, 1e-14, 1e-9, 0.1, 2, 1000])
def test_hazard_conserves_survivors_and_matches_expm1(hazard):
    source = system(
        parameter('hazard', hazard, 'per_h'),
        stock('alive', 1_000_000, size=1_000_000),
        stock('dead', size=1_000_000, kind='tally'),
        flow('death', move('alive', 'dead'), 'hazard * alive'),
        horizon=10,
    )
    _, tr = run(source)
    expected = 1_000_000 * -math.expm1(-hazard * 10)
    assert tr.env_at(10)['s.dead'] == pytest.approx(expected, rel=1e-8, abs=1e-7)
    for t in [0, 0.1, 1, 3.25, 10]:
        env = tr.env_at(t)
        assert env['s.alive'] >= 0 and env['s.dead'] >= 0
        assert env['s.alive'] + env['s.dead'] == pytest.approx(1_000_000, abs=1e-6)


def test_reporting_is_pure_and_does_not_move_events():
    source = system(
        stock('stock', 10),
        stock('used'),
        flow('use', move('stock', 'used'), '2 people/h'),
        event('empty', 'stock <= 0 people'),
    )
    _, tr = run(source)
    trace_before = copy.deepcopy(tr.trace)
    evaluations = tr.evaluations
    for t in [10, 0, 5, 5.00001, 3.7, *[i / 100 for i in range(1001)]]:
        env = tr.env_at(t)
        assert env['s.stock'] == pytest.approx(max(0, 10 - 2 * t))
        assert env['s.stock'] + env['s.used'] == pytest.approx(10)
    assert tr.trace == trace_before
    assert tr.evaluations == evaluations
    assert tr.trace[0]['t'] == pytest.approx(5)


def test_supply_through_exhausted_stock_and_replenishment():
    source = system(
        named('supply', 'low', 'high'),
        stock('stock', 10),
        stock('used'),
        flow('inflow', move(None, 'stock'), '1 people/h if supply is "low" else 4 people/h'),
        flow('use', move('stock', 'used'), '3 people/h'),
        switch('restore', 'supply', 'low', 'high', '10 h'),
        horizon=20,
    )
    _, tr = run(source)
    assert tr.env_at(5)['s.stock'] == pytest.approx(0)
    assert tr.env_at(10)['s.stock'] == pytest.approx(0)
    assert tr.env_at(20)['s.stock'] == pytest.approx(10)
    assert tr.env_at(20)['s.used'] == pytest.approx(50)


def test_simultaneous_threshold_prerequisite_precedes_schedule():
    source = system(
        stock('capacity', kind='tally', rate='2 people/h'),
        stock('settled'),
        event('deadline', 't >= 5 h and count(ready) > 0', 'settled = capacity'),
        event('ready', 'capacity >= 10 people'),
    )
    _, tr = run(source)
    assert [e['event'] for e in tr.trace] == ['s.ready.done', 's.deadline.done']
    assert tr.env_at(5)['s.settled'] == 10
    assert tr.env_at(5, side='left')['s.settled'] == 0


def test_a_lookup_takes_the_snapshot_or_the_segment_that_holds_the_time():
    # Each moment keeps a snapshot before its steps and one after each step, all at its time; the
    # first is the left side of the moment and the last its right side. Between moments, the one
    # segment that holds the time gives the state. A scan of both lists in time order is the rule.
    source = system(
        named('supply', 'low', 'high'),
        stock('stock', 10),
        stock('used'),
        flow('inflow', move(None, 'stock'), '1 people/h if supply is "low" else 4 people/h'),
        flow('use', move('stock', 'used'), '3 people/h'),
        switch('restore', 'supply', 'low', 'high', '10 h'),
        event('deadline', 't >= 5 h', 'used = used'),
        event('ready', 't >= 5 h and count(deadline) > 0'),
        horizon=20,
    )
    _, tr = run(source)
    assert any(a[0] == b[0] for a, b in zip(tr._snapshots, tr._snapshots[1:]))
    middles = [(segment.start + segment.end) / 2 for segment in tr._segments]
    for t in sorted({snap[0] for snap in tr._snapshots} | set(middles)):
        same = [snap for snap in tr._snapshots if snap[0] == t]
        for side in ('left', 'right'):
            if same:
                snap = same[0] if side == 'left' else same[-1]
                state, store = snap[1], snap[2]
            else:
                segment = next(seg for seg in tr._segments if seg.start <= t <= seg.end)
                state, store = segment.solution(t), segment.store
            expected = tr._environment(t, tr._project(state), store)
            assert tr.env_at(t, side) == expected, (t, side)


def test_a_trajectory_pickles_without_its_programs_and_gives_the_same_environments():
    # A trajectory keeps the program of its environments and the index of its lookups for its own
    # use. A generated program cannot be pickled, and the run store pickles each trajectory.
    source = system(
        named('supply', 'low', 'high'),
        stock('stock', 10),
        stock('used'),
        formula('pressure', 'stock / 10 h', 'people/h'),
        flow('inflow', move(None, 'stock'), '1 people/h if supply is "low" else 4 people/h'),
        flow('use', move('stock', 'used'), 'pressure'),
        switch('restore', 'supply', 'low', 'high', '5 h'),
        horizon=10,
    )
    _, tr = run(source)
    times = [0, 2.5, 5, 7.5, 10]
    before = [tr.env_at(t) for t in times]
    assert {'_lookup', '_program'} <= tr.__dict__.keys()
    restored = pickle.loads(pickle.dumps(tr))
    assert not {'_lookup', '_program'} & restored.__dict__.keys()
    assert [restored.env_at(t) for t in times] == before


def test_a_formula_that_fails_in_the_program_of_the_environments_is_named_by_its_evaluation():
    tr = runtime.Trajectory(
        1.0,
        [],
        [],
        {},
        ('s.x',),
        {'s.a': 2.0},
        {'s.c': {'expr': nodes.read('s.a / s.x')}},
        UnitSystem(UNITS),
        None,
    )
    assert tr._environment(0.0, [4.0], {})['s.c'] == 0.5  # the first environment finds the order
    assert tr._environment(0.0, [8.0], {})['s.c'] == 0.25  # the next ones run the program
    with pytest.raises(ExpressionError) as caught:
        tr._environment(0.0, [0.0], {})
    assert repr('s.a / s.x') in str(caught.value)


def test_the_programs_of_a_run_give_what_each_expression_gives_in_each_state_and_mode():
    # The inputs are literals in the programs, which read the time, the store and the state.
    source = system(
        named('response', 'inactive', 'active'),
        parameter('base', 2, 'people/h'),
        stock('stock', 10),
        stock('used'),
        # A tally never falls: its rate is base, or half of it.
        stock('level', 0, minimum=None, kind='state', rate='base if response is "active" else base / 2'),
        formula('capacity', 'base * 3 if response is "active" else base + stock / 1 h', 'people/h'),
        flow('inflow', move(None, 'stock'), 'base'),
        flow('use', move('stock', 'used'), 'capacity * (1 + t / 10 h)'),
        flow('spill', move('stock', 'used'), 'stock / 4 h'),
        share('stock', 'capacity'),
        horizon=4,
    )
    rs = resolved(source)
    s = System(rs, library(), runtime.NumericalSettings.parse(None))
    tr = runtime.Trajectory(
        s.horizon, [], [], s.settings, s.state_ids, s.values, s.computed, s.units, s.bounds
    )
    store = initial_store(rs)
    field = Field(s, Run(0.0, s.initial_state(store), store), tr)
    (mode,) = rs.modes
    for value in ('inactive', 'active'):
        store[mode] = value  # the run's store changes in place, as the scheduler changes it
        for at, level in [(0.0, 0.0), (1.5, 3.25), (3.0, 1e-9), (4.0, 12.0)]:
            state = s.initial_state(store)
            state[s.index['s.stock']] = level
            rates, requested, capacities = field.compiled(at, state)
            reference = {**s.values, **dict(zip(s.state_ids, state.tolist())), **store, 't': at}
            for name, expr in tr._order:
                reference[name] = evaluate(expr, reference, s.units)
            assert tr._environment(at, state, store) == reference

            def each(sources, env=reference):
                return np.array([evaluate(source, env, s.units) for source in sources], dtype=float).tobytes()

            assert rates.tobytes() == each(rs.rates[name].expr for name in s.derivative_ids)
            assert requested.tobytes() == each(f.rate for f in s.flows.values())
            assert capacities.tobytes() == each(g.capacity for g in s.groups.values())


def test_atomic_layer_cannot_hide_resource_overdraft():
    # Each move fits the source of 10 on its own. At one moment they go one at a time: the second
    # finds 2 people left, and its move does not fit.
    source = system(
        stock('source', 10),
        stock('a'),
        stock('b'),
        once_at('give_a', '0 h', 'move 8 people from source to a'),
        once_at('give_b', '0 h', 'move 8 people from source to b'),
        horizon=1,
    )
    with pytest.raises(SimulationError, match='does not fit'):
        run(source)


@pytest.mark.parametrize(
    'change',
    ['level += 1 people', 'move 1 people from source to level'],
    ids=['set', 'move'],
)
def test_an_order_holds_while_a_set_or_a_move_can_make_the_first_rule_due(change):
    """At 1 h `add` puts one person into `level`, `watch` fires once `level >= 1`, and the line of
    `watch` comes before that of `close`, which is also due at 1 h. After each step every condition is
    read again: once `add` fires, `watch` is due, and it goes before `close`. A move into the stock
    makes `watch` due as a set does, so the order holds in the same steps."""
    source = system(
        stock('source', 5),
        stock('level'),
        named('seen', 'no', 'yes'),
        named('closed', 'no', 'yes'),
        once_at('add', '1 h', change),
        event('watch', 'level >= 1 people', 'seen = "yes"'),
        once_at('close', '1 h', 'closed = "yes"'),
        horizon=2,
    )
    _, tr = run(source)
    first = tr.trace[0]['step']
    steps = [(e['t'], e['step'], e['rule']) for e in tr.trace]
    assert steps == [(1, first, 's.add'), (1, first + 1, 's.watch'), (1, first + 2, 's.close')]


# Two rules act on the stock `pool` at 0 h. The names of their events put the first rule before or
# after the second in the order of the rule IDs; the order of their lines decides, and the result is
# the same for both names.
ID_ORDERS = pytest.mark.parametrize('names', [('a_first', 'b_second'), ('b_first', 'a_second')])


def two_rules(names, first, second):
    """A system whose events `names` make the changes `first` and `second` at 0 h."""
    return system(
        stock('pool', 10),
        stock('supply', 5),
        stock('out'),
        once_at(names[0], '0 h', first),
        once_at(names[1], '0 h', second),
        horizon=1,
    )


def codes(caught):
    return [d.get('code') for d in caught.value.diagnostics]


@ID_ORDERS
def test_two_rules_that_move_one_stock_never_conflict_also_when_one_reads_it(names):
    """The first rule reads the pool and moves half of it out; the second moves 3 into it from the
    supply. Each is a step of its own, in the order of their lines, and the moves add up."""
    source = two_rules(names, 'move pool / 2 from pool to out', 'move 3 people from supply to pool')
    _, tr = run(source)
    assert [e['rule'] for e in tr.trace] == [f's.{name}' for name in names]
    assert tr.trace[1]['step'] == tr.trace[0]['step'] + 1
    end = tr.env_at(1)
    assert (end['s.pool'], end['s.out'], end['s.supply']) == (10 - 10 / 2 + 3, 10 / 2, 5 - 3)


@ID_ORDERS
def test_moves_that_together_overdraw_a_stock_stop_the_run(names):
    """The first rule reads the pool and moves all of it out; the second moves 4 more out of it. Each
    move fits on its own, and together they would leave the pool at -4: the second finds the pool
    empty, and its move does not fit."""
    source = two_rules(names, 'move pool from pool to out', 'move 4 people from pool to supply')
    with pytest.raises(SimulationError, match='does not fit') as caught:
        run(source)
    assert codes(caught)[0] == 'transaction_failed'


def test_relative_events_preserve_nonzero_time_impulses():
    source = system(
        stock('a'),
        once_at('impulse', '3 h', 'a = 10 people'),
        event('settle', 'since(impulse) >= 4 h', 'a = 20 people'),
        horizon=12,
    )
    _, tr = run(source)
    assert tr.env_at(3, 'left')['s.a'] == 0
    assert tr.env_at(3)['s.a'] == 10
    assert tr.env_at(7)['s.a'] == 20
    assert [e['t'] for e in tr.trace] == [3, 7]


def test_uniform_pending_cohort_transfer_keeps_living_people_until_death():
    source = system(
        named('period', 'waiting', 'active', 'done'),
        stock('pending', 20),
        stock('dead'),
        flow('death', move('pending', 'dead'), '1 people/h if period is "active" else 0 people/h'),
        switch('begin', 'period', 'waiting', 'active', '10 h'),
        switch('close', 'period', 'active', 'done', '30 h'),
        horizon=50,
    )
    _, tr = run(source)
    for t in [0, 10, 20, 30, 50]:
        env = tr.env_at(t)
        assert env['s.dead'] == max(0, min(20, t - 10))
        assert env['s.pending'] + env['s.dead'] == 20


def test_proportional_and_priority_share_scarce_capacity():
    source = system(
        stock('stock'),
        stock('a'),
        stock('b'),
        flow('supply', move(None, 'stock'), '6 people/h'),
        flow('to_a', move('stock', 'a'), '8 people/h'),
        flow('to_b', move('stock', 'b'), '4 people/h'),
        share('stock', '12 people/h'),
        horizon=1,
    )
    _, tr = run(source)
    assert tr.env_at(1)['s.a'] == pytest.approx(4)
    assert tr.env_at(1)['s.b'] == pytest.approx(2)
    source = edit(
        source, replace('share stock limit 12 people/h', 'share stock limit 12 people/h order to_a, to_b')
    )
    _, tr = run(source)
    assert tr.env_at(1)['s.a'] == pytest.approx(6)
    assert tr.env_at(1)['s.b'] == pytest.approx(0)


def test_priority_pass_keeps_every_other_boundary_flow_maximal():
    # Both buffers start empty. Supply 1+1 people/hour reaches mid; the 3/hour drain can
    # carry only those 2, and end passes on its 1/hour burn. By hand: mid stays 0, end
    # gains 1/hour and out gains 1/hour. A priority group must not zero the other flows.
    source = system(
        stock('source', 100),
        stock('mid'),
        stock('end'),
        stock('out'),
        flow('p1', move('source', 'mid'), '1 people/h'),
        flow('p2', move('source', 'mid'), '1 people/h'),
        flow('drain', move('mid', 'end'), '3 people/h'),
        flow('burn', move('end', 'out'), '1 people/h'),
        share('source', '2 people/h', ['p1', 'p2']),
        horizon=4,
    )
    _, tr = run(source)
    env = tr.env_at(4)
    assert env['s.source'] == pytest.approx(92)
    assert env['s.mid'] == pytest.approx(0, abs=1e-9)
    assert env['s.end'] == pytest.approx(4)
    assert env['s.out'] == pytest.approx(4)


@pytest.mark.parametrize('serve', [['to_full', 'to_empty'], ['to_empty', 'to_full'], 'proportional'])
def test_a_flow_that_a_bound_holds_back_leaves_its_share_of_the_limit_to_the_others(serve):
    # Two flows of 10 people an hour draw on a store of 100 under one limit of 10 people an hour.
    # One flows into a stock that is full, so it moves nothing. In any order, and in proportion,
    # the other flow takes the whole limit: 10 people in the first hour.
    source = system(
        stock('store', 100),
        stock('full', 5, maximum=5),
        stock('empty'),
        flow('to_full', move('store', 'full'), '10 people/h'),
        flow('to_empty', move('store', 'empty'), '10 people/h'),
        share('store', '10 people/h', serve),
        horizon=1,
    )
    env = run(source)[1].env_at(1)
    assert env['s.empty'] == pytest.approx(10)
    assert env['s.full'] == pytest.approx(5)
    assert env['s.store'] == pytest.approx(90)


@pytest.mark.parametrize('first', ['upstream', 'downstream'])
def test_priority_is_served_upstream_first_whatever_the_order_of_the_limits(first):
    # One person an hour reaches the empty stock a. Under a's limit, `high` comes before `feed`, a
    # transaction that carries people from a to the empty stock b together with material from a
    # reserve. Under b's limit, `out` and `other` share what reaches b. a's order decides first: high
    # takes the one person an hour, so feed and everything after it carry nothing. The order in which
    # the file lists the two limits changes nothing.
    limits = {
        'upstream': share('a', '100 people/h', ['high', 'feed']),
        'downstream': share('b', '100 people/h', ['out', 'other']),
    }
    flows = (
        flow('supply', move(None, 'a'), '1 people/h'),
        flow('high', move('a', 'h'), '1 people/h'),
        flow('feed', ['a -> b', 'reserve -> used'], '1 people/h'),
        flow('out', move('b', 'o'), '1 people/h'),
        flow('other', move('b', 'p'), '1 people/h'),
    )
    order = [first, 'downstream' if first == 'upstream' else 'upstream']
    names = ('a', 'b', 'h', 'o', 'p', 'used')
    source = system(
        *(stock(name) for name in names),
        stock('reserve', 100),
        *flows,
        *(limits[name] for name in order),
        horizon=1,
    )
    env = run(source)[1].env_at(1)
    assert env['s.h'] == pytest.approx(1)
    assert env['s.o'] == pytest.approx(0, abs=1e-9)
    assert env['s.p'] == pytest.approx(0, abs=1e-9)


def test_a_transaction_that_runs_short_leaves_its_share_of_the_limit_to_the_others():
    # The first flow under the limit moves people from the store together with items from an empty
    # stock, so it moves nothing. The second flow takes the whole limit.
    source = system(
        stock('store', 100),
        stock('x'),
        stock('items'),
        stock('y'),
        stock('out'),
        flow('both', ['store -> x', 'items -> y'], '10 people/h'),
        flow('other', move('store', 'out'), '10 people/h'),
        share('store', '10 people/h', ['both', 'other']),
        horizon=1,
    )
    env = run(source)[1].env_at(1)
    assert env['s.out'] == pytest.approx(10)
    assert env['s.x'] == pytest.approx(0, abs=1e-9)
    assert env['s.store'] == pytest.approx(90)


def ledger_library():
    lib = library()
    lib['units']['person_hour'] = {'dimensions': {'people': 1, 'time': 1}, 'scale': 1}
    return lib


def ledger(name, rate):
    """A running total in person-hours, with the given rate of change."""
    return stock(name, 0, 'person_hour', kind='tally', rate=rate)


def test_running_total_of_a_coupled_constant_drain_is_exact_and_stops_at_empty():
    # By hand: stock = 100 - 10t empties at t = 10; its running total is
    # 100t - 5t^2 = 500 there and stays 500. The coupled spare use stops with it.
    source = system(
        stock('stock', 100),
        stock('shipped'),
        stock('spares', 1000),
        stock('used'),
        ledger('exposure', 'stock'),
        flow('shipment', ['stock -> shipped', 'spares -> used'], '10 people/h'),
        horizon=20,
    )
    _, tr = run(source, lib=ledger_library())
    assert tr.env_at(5)['s.exposure'] == pytest.approx(375, rel=1e-12)
    for t in (10, 20):
        env = tr.env_at(t)
        assert env['s.exposure'] == pytest.approx(500, rel=1e-12)
        assert env['s.stock'] == pytest.approx(0, abs=1e-9)
        assert env['s.spares'] == pytest.approx(900, rel=1e-12)
        assert env['s.used'] == pytest.approx(100, rel=1e-12)
    assert tr.evaluations < 50


def test_clipped_boundary_allocation_feeds_an_exact_quadratic_total():
    # By hand: mid stays empty, so the 8/hour capacity passes on only the 5/hour inflow;
    # end = 5t and its running total is 2.5t^2.
    source = system(
        stock('mid'),
        stock('end'),
        ledger('exposure', 'end'),
        flow('supply', move(None, 'mid'), '5 people/h'),
        flow('pass_on', move('mid', 'end'), '8 people/h'),
        horizon=10,
    )
    _, tr = run(source, lib=ledger_library())
    env = tr.env_at(10)
    assert env['s.mid'] == pytest.approx(0, abs=1e-9)
    assert env['s.end'] == pytest.approx(50, rel=1e-12)
    assert env['s.exposure'] == pytest.approx(250, rel=1e-12)
    assert tr.evaluations < 50


def test_unsourced_inflow_linear_in_a_decaying_stock_matches_closed_form():
    # By hand: pending = 100 e^{-0.2t}; value' = 3 pending gives 1500 (1 - e^{-0.2t}).
    source = system(
        stock('pending', 100),
        stock('gone', kind='tally'),
        stock('value', size=1000, kind='tally'),
        flow('decay', move('pending', 'gone'), '0.2 per_h * pending'),
        flow('accrue', move(None, 'value'), '3 per_h * pending'),
        horizon=10,
    )
    _, tr = run(source)
    assert tr.env_at(10)['s.value'] == pytest.approx(1500 * -math.expm1(-2), rel=1e-10)
    assert tr.evaluations < 50


def test_a_decay_chain_with_straight_lines_matches_its_closed_form():
    # A first-order chain a -> b -> c with an inflow into a (Bateman), a tally d that accrues on a
    # straight line s, and a straight line u that nothing reads. By hand, with k1 = 0.3/h, k2 = 0.05/h:
    # a = r/k1 + (a0 - r/k1) e^{-k1 t}; b solves b' + k2 b = k1 a; c = a0 + b0 + r t - a - b;
    # s = s0 + 4 t, d = 0.5 (s0 t + 2 t^2), u = 3 t.
    a0, b0, s0, r, k1, k2 = 100.0, 10.0, 2.0, 5.0, 0.3, 0.05
    source = system(
        stock('a', a0),
        stock('b', b0),
        stock('c', kind='tally'),
        stock('s', s0, kind='tally'),
        stock('d', kind='tally', size=10_000),
        stock('u', kind='tally'),
        flow('inflow', move(None, 'a'), f'{r} people/h'),
        flow('first', move('a', 'b'), f'{k1} per_h * a'),
        flow('second', move('b', 'c'), f'{k2} per_h * b'),
        flow('grow', move(None, 's'), '4 people/h'),
        flow('accrue', move(None, 'd'), '0.5 per_h * s'),
        flow('tick', move(None, 'u'), '3 people/h'),
        horizon=100,
    )
    _, tr = run(source)
    (segment,) = [segment for segment in tr._segments if isinstance(segment.solution, MatrixExponential)]
    ids = list(tr._states)
    # The exponential is of what moves and what it reads: a, b and c, and d with the s that it reads.
    assert sorted(ids[i] for i in segment.solution.columns) == ['s.a', 's.b', 's.c', 's.d', 's.s']
    for at in [0, 0.5, 3, 20, 100]:
        a = r / k1 + (a0 - r / k1) * math.exp(-k1 * at)
        first = (k1 * a0 - r) / (k2 - k1)
        b = r / k2 + first * math.exp(-k1 * at) + (b0 - r / k2 - first) * math.exp(-k2 * at)
        env = tr.env_at(at)
        assert env['s.a'] == pytest.approx(a, rel=1e-12)
        assert env['s.b'] == pytest.approx(b, rel=1e-12)
        assert env['s.c'] == pytest.approx(a0 + b0 + r * at - a - b, rel=1e-12, abs=1e-12)
        assert env['s.s'] == pytest.approx(s0 + 4 * at, rel=1e-15)
        assert env['s.d'] == pytest.approx(0.5 * (s0 * at + 2 * at * at), rel=1e-12, abs=1e-12)
        assert env['s.u'] == 3 * at


def test_the_exponential_of_what_moves_is_the_exponential_of_the_whole_system():
    # Random positive compartment systems y' = A y + c in which some quantities read none: the block of
    # the quantities that move and those that they read gives what the exponential of the whole
    # augmented matrix gives, to its roundoff; a quantity that reads none moves on its straight line.
    from scipy.linalg import expm

    rng = np.random.default_rng(14)
    for _ in range(200):
        n = int(rng.integers(1, 9))
        linear = rng.uniform(0, 1, (n, n)) * (rng.random((n, n)) < 0.3)
        np.fill_diagonal(linear, -rng.uniform(0, 2, n) * (rng.random(n) < 0.6))
        linear[rng.random(n) < 0.4] = 0  # quantities whose rates read no quantity
        matrix = np.zeros((n + 1, n + 1))
        matrix[:n, :n] = linear
        matrix[:n, n] = rng.uniform(0, 5, n) * (rng.random(n) < 0.7)
        state, start = rng.uniform(0, 100, n), float(rng.uniform(0, 50))
        solution = MatrixExponential.of(matrix, n, start, state)
        still = ~np.any(linear != 0, axis=1)
        for at in start + np.array([0.0, 1e-9, 0.7, 13.0]):
            got, elapsed = solution(at), at - start
            whole = (expm(matrix * elapsed) @ np.append(state, 1.0))[:n]
            scale = np.abs(whole).max() + 1
            assert np.max(np.abs(got - whole)) <= 1e-13 * scale
            assert got[still].tobytes() == (state + matrix[:n, n] * elapsed)[still].tobytes()


def test_linear_member_of_an_allocation_group_falls_back_to_integration_exactly():
    # A state-dependent allocation member cannot use the fixed-allocation kernel;
    # by hand each of the two equal hazards takes 50 (1 - e^{-0.2t}).
    source = system(
        stock('pending', 100),
        stock('a', kind='tally'),
        stock('b', kind='tally'),
        flow('to_a', move('pending', 'a'), '0.1 per_h * pending'),
        flow('to_b', move('pending', 'b'), '0.1 per_h * pending'),
        share('pending', '1000 people/h'),
        horizon=10,
    )
    _, tr = run(source)
    assert tr.env_at(10)['s.a'] == pytest.approx(50 * -math.expm1(-2), rel=1e-7)
    assert tr.env_at(10)['s.b'] == pytest.approx(50 * -math.expm1(-2), rel=1e-7)


def test_event_set_flag_gates_a_rate_exactly_under_the_implicit_integrator():
    # By hand: the flag is 0 until the 5 h event sets it to 1; the hazard 0.1/h then
    # acts on 100 people, so none die before 5 h and 100 (1 - e^{-0.5}) die by 10 h.
    source = system(
        stock('alive', 100),
        stock('dead', kind='tally'),
        stock('flag', kind='state'),
        formula('flag_on', '1 if flag > 0 people else 0', 'fraction'),
        flow('death', move('alive', 'dead'), 'flag_on * alive * 0.1 per_h * alive / 100 people'),
        once_at('onset', '5 h', 'flag = 1 people'),
        horizon=10,
    )
    _, tr = run(source)
    assert tr.env_at(5, 'left')['s.dead'] == 0
    # a' = -0.001 a^2 from 5 h: a(10) = 100 / (1 + 0.5)
    assert tr.env_at(10)['s.dead'] == pytest.approx(100 - 100 / 1.5, rel=1e-7)


def test_constant_tail_handles_five_year_horizon_without_step_loop():
    source = system(stock('cumulative', kind='tally', rate='0.1 people/h'), horizon=43_812)
    _, tr = run(source)
    assert tr.env_at(43_812)['s.cumulative'] == pytest.approx(4381.2)
    assert tr.evaluations < 20


def test_cascade_and_numerical_budgets_fail_loudly():
    # Two events that move one named state back and forth never settle a moment.
    source = system(
        named('phase', 'x', 'y'),
        event('flip', 'true', once=False, transition='phase "x" -> "y"'),
        event('flop', 'true', once=False, transition='phase "y" -> "x"'),
        horizon=1,
    )
    with pytest.raises(SimulationError, match='does not settle within 5 steps'):
        run(source, settings={'max_steps': 5})
    source = system(*decay('a', 100), *TIMED_COHORT, horizon=10)
    with pytest.raises(SimulationError, match='evaluation budget'):
        run(source, settings={'max_evaluations': 5})
    # The budget is of the whole run, over the moments that start the solver again: a run that
    # takes n evaluations in all finishes with a budget of n and stops with a budget of n - 1.
    source = system(
        *decay('a', 100), *TIMED_COHORT, event('refill', 't >= 5 h', 'a = 100 people'), horizon=10
    )
    _, whole = run(source)
    assert [row['rule'] for row in whole.trace] == ['s.refill'] and whole.evaluations > 5
    assert run(source, settings={'max_evaluations': whole.evaluations})[1].evaluations == whole.evaluations
    with pytest.raises(SimulationError, match='evaluation budget'):
        run(source, settings={'max_evaluations': whole.evaluations - 1})


def test_radau_matches_independent_exponential_solution():
    source = system(*decay('a', 100), *TIMED_COHORT, horizon=2)
    _, tr = run(source)
    assert tr.settings['integration_segments']
    assert tr.env_at(2)['s.a'] == pytest.approx(100 * math.exp(-2), rel=1e-8)


def test_missing_scarce_resource_policy_fails_instead_of_choosing_tie():
    source = system(
        stock('stock'),
        stock('a'),
        stock('b'),
        flow('supply', move(None, 'stock'), '1 people/h'),
        flow('to_a', move('stock', 'a'), '1 people/h'),
        flow('to_b', move('stock', 'b'), '1 people/h'),
        horizon=1,
    )
    assert ('allocation', 's/stock') in rejected(source)


def test_initial_state_can_depend_on_a_signal():
    source = system(
        parameter('initial_population', 42, 'people'),
        formula('population', 'initial_population', 'people'),
        stock('alive', 'population'),
        horizon=1,
    )
    assert run(source)[1].env_at(1)['s.alive'] == 42


def production():
    """Two units of input a and one unit of input b make one product, two products an hour, as one
    flow of three pairs: the pairs always move by the same delivered fraction."""
    return flow(
        'factory', ['input_a -> at 4 people/h', 'input_b -> at 2 people/h', '-> product'], '2 people/h'
    )


def test_coupled_multi_input_production_stops_all_material_flows_together():
    # By hand: input b (3) runs out at 1.5 h, after 3 products; input a keeps 12 - 2 * 3 = 6.
    source = system(stock('input_a', 12), stock('input_b', 3), stock('product'), production(), horizon=10)
    _, tr = run(source)
    final = tr.env_at(10)
    assert final['s.product'] == pytest.approx(3)
    assert final['s.input_a'] == pytest.approx(6)
    assert final['s.input_b'] == pytest.approx(0)
    assert final['s.input_a'] + 2 * final['s.product'] == pytest.approx(12)
    assert final['s.input_b'] + final['s.product'] == pytest.approx(3)


def test_mode_specialized_stationary_tail_preserves_guarded_division():
    guarded = 'capacity * alive / alive if alive > 0 people else 0 people/h'
    source = system(
        named('response', 'inactive', 'active'),
        stock('alive', 10),
        stock('protected'),
        stock('functionality', 1, maximum=1, size=1, kind='state', rate='0'),
        stock('loss', kind='tally', rate='(1 people - functionality) / 1 h'),
        formula('capacity', '1 people/h if response is "active" else 0 people/h', 'people/h'),
        flow('protect', move('alive', 'protected'), guarded),
        horizon=43_800,
    )
    _, tr = run(source)
    assert tr.evaluations < 20
    assert tr.env_at(43_800)['s.alive'] == 10
    # An unguarded zero denominator is still a numerical error.
    source = edit(source, replace(guarded, 'capacity * alive / 0 people'))
    with pytest.raises(ModelError, match='zero'):
        run(source)


def test_nonlinear_large_hazard_has_a_bounded_trial_extension():
    source = system(
        stock('alive', 100),
        stock('dead'),
        flow('death', move('alive', 'dead'), 'alive * (1 + alive / 100 people) / 0.001 h'),
        horizon=0.1,
    )
    _, tr = run(source)
    # dN/dt = -1000 N (1 + N/100); solve by separation of variables.
    for t in [0, 0.001, 0.01, 0.1]:
        expected_alive = 100 * math.exp(-1000 * t) / (2 - math.exp(-1000 * t))
        env = tr.env_at(t)
        assert env['s.alive'] == pytest.approx(expected_alive, abs=2e-7)
        assert env['s.alive'] + env['s.dead'] == pytest.approx(100, abs=2e-7)


def test_public_json_signed_accounting_capped_recovery_and_duplicate_credit():
    source = system(
        stock('principal', 100, 'USD2025'),
        stock('recovered', 0, 'USD2025', kind='tally'),
        flow('recovery', move('principal', 'recovered'), '30 USD2025/h'),
        horizon=10,
        outputs=(
            output(
                'net_position',
                's.principal - 50 USD2025',
                'USD2025',
                'net',
                doc='Net position',
                under=('signed',),
            ),
        ),
    )
    lib = library()
    rs = compiled(source).resolve('a')
    tr = runtime.simulate(rs, lib)
    assert tr.env_at(1)['s.principal'] == 70
    assert tr.env_at(10)['s.principal'] == 0
    assert tr.env_at(10)['s.recovered'] == 100
    rows = evaluate_outputs({'resolved': rs, 'trajectory': tr}, lib, [0, 1, 10])
    assert rows[-1]['values']['net_position'] == -50
    assert rows[0]['values']['net_position'] == 50
    assert tr.env_at(10)['s.principal'] + tr.env_at(10)['s.recovered'] == 100
    # A second credit cannot withdraw principal that has already been recovered.
    source = edit(
        source, member('s', once_at('duplicate', '6 h', 'move 1 USD2025 from principal to recovered'))
    )
    with pytest.raises(SimulationError) as refused:
        runtime.simulate(compiled(source).resolve('a'), lib)
    assert any(
        d.get('code') == 'transaction_failed' and d.get('rule') == 's.duplicate'
        for d in refused.value.diagnostics
    )


def test_coupled_production_replenishment_preserves_material_accounting():
    # By hand: both inputs run out together at 1 h after 2 products; the 3 h refill makes
    # 2 more by 4 h. Each product uses two units of a and one unit of b.
    source = system(
        stock('input_a', 4),
        stock('input_b', 2),
        stock('warehouse_a', 4),
        stock('warehouse_b', 2),
        stock('product'),
        once_at(
            'replenish',
            '3 h',
            'move 4 people from warehouse_a to input_a',
            'move 2 people from warehouse_b to input_b',
        ),
        production(),
        horizon=10,
    )
    tr = runtime.simulate(compiled(source).resolve('a'), library())
    for t in [0, 1, 2, 3, 4, 10]:
        env = tr.env_at(t)
        assert env['s.input_a'] + env['s.warehouse_a'] + 2 * env['s.product'] == pytest.approx(8)
        assert env['s.input_b'] + env['s.warehouse_b'] + env['s.product'] == pytest.approx(4)
    assert tr.env_at(2)['s.product'] == 2
    assert tr.env_at(10)['s.product'] == 4


def test_numerical_root_roundoff_correction_is_balanced_and_recorded():
    source = system(
        stock('alive', 100),
        stock('dead'),
        flow('death', move('alive', 'dead'), 'alive * (1 + alive / 100 people) / 0.001 h'),
        horizon=0.1,
    )
    tr = runtime.simulate(compiled(source).resolve('a'), library())
    assert tr.env_at(0.1)['s.alive'] >= 0
    assert tr.env_at(0.1)['s.alive'] + tr.env_at(0.1)['s.dead'] == pytest.approx(100, abs=1e-9)
    for correction in tr.diagnostics:
        if correction['code'] == 'boundary_roundoff':
            assert correction['delta'] + correction['balancing_delta'] == 0
            assert correction['balancing_state'] == 's.dead'


def test_scheduled_shutdown_at_numeric_upper_bound_does_not_create_false_infeasibility():
    source = system(
        named('repair', 'working', 'done'),
        stock('alive', 100),
        stock('dead'),
        stock(
            'restoration',
            0,
            'fraction',
            kind='tally',
            maximum=1,
            size=1,
            rate='1 / 216 h if repair is "working" else 0',
        ),
        flow('hazard', move('alive', 'dead'), 'alive * (1 + alive / 100 people) / 100 h'),
        switch('restored', 'repair', 'working', 'done', '216 h'),
        horizon=400,
    )
    _, tr = run(source)
    assert tr.env_at(216)['s.restoration'] == pytest.approx(1, abs=1e-12)
    assert tr.env_at(400)['s.restoration'] == pytest.approx(1, abs=1e-12)
    assert [e['event'] for e in tr.trace] == ['s.restored.done']


def test_stock_default_lower_bound_and_tally_transfer_invariants():
    # A stock with no `min` stops at zero.
    source = system(
        stock('stock', 1, minimum=None),
        stock('used'),
        flow('use', move('stock', 'used'), '1 people/h'),
        horizon=3,
    )
    assert 's/stock/min:' not in places(source)
    assert run(source)[1].env_at(3)['s.stock'] == 0


def test_a_set_that_misses_a_bound_by_roundoff_lands_on_the_bound():
    # In binary floating point 0.3 - 0.1 - 0.2 is a little below zero: the stock is empty, and a
    # move of nothing out of it into a tally moves nothing.
    assert -1e-15 < 0.3 - 0.1 - 0.2 < 0
    source = system(
        stock('x', 1),
        stock('used', 0, kind='tally'),
        once_at('at_one', '1 h', 'x = 0.3 people - 0.1 people - 0.2 people', 'move 0 people from x to used'),
        horizon=3,
    )
    end = run(source)[1].env_at(3)
    assert end['s.x'] == 0
    assert end['s.used'] == 0


def test_a_root_correction_does_not_lower_a_tally_while_another_leg_can_take_it():
    # A stock 1e-12 below empty, with a move into a tally listed before a move into another stock.
    source = system(
        stock('x', 1),
        stock('used', 0, kind='tally'),
        *held('other', 0),
        flow('a_use', move('x', 'used'), '1 people/h'),
        flow('b_pass', move('x', 'other'), '1 people/h'),
        share('x', '2 people/h'),
        horizon=1,
    )
    s = System(resolved(source), library(), runtime.NumericalSettings.parse(None))
    state = np.zeros(len(s.state_ids))
    state[s.index['s.x']], state[s.index['s.used']], state[s.index['s.other']] = -1e-12, 1.0, 1.0
    correct_boundary_roundoff(s, [], 1.0, state)
    assert state[s.index['s.x']] == 0
    assert state[s.index['s.used']] == 1.0
    assert state[s.index['s.other']] == 1.0 - 1e-12


def test_public_physical_timescales_cap_the_integrator_and_record_effective_settings(monkeypatch):
    source = with_timescales(
        system(
            parameter('physical_scale', 0.08, 'h', 0.001, 1),
            stock('alive', 100),
            stock('dead'),
            flow('death', move('alive', 'dead'), 'alive * (1 + alive / 100 people) / 1 h'),
            horizon=1,
        ),
        's.physical_scale',
        '0.4 h',
    )
    model = compiled(source)
    calls = []
    integrator = integrate.radau

    def capture(*args, **kwargs):
        calls.append(kwargs['max_step'])
        return integrator(*args, **kwargs)

    monkeypatch.setattr(integrate, 'radau', capture)
    tr = runtime.simulate(model.resolve('a'), library(), {'max_step': 2})
    assert tr.settings['requested_max_step'] == 2
    assert tr.settings['max_step'] == pytest.approx(0.01)
    assert tr.settings['physical_timescales_h'] == [0.08, 0.4]
    assert calls and all(step == pytest.approx(0.01) for step in calls)


def test_default_implicit_integrator_caps_physical_resolution_and_matches_closed_form(monkeypatch):
    # The nonlinear decay has a declared 0.02 h timescale and an independent
    # rational closed form. Numerical integration resolves that timescale.
    source = with_timescales(
        system(
            stock('alive', 100),
            stock('dead', kind='tally'),
            flow('death', move('alive', 'dead'), 'alive * alive / 100 people / 0.02 h'),
            horizon=2,
        ),
        '0.02 h',
    )
    calls = []
    integrator = integrate.radau

    def capture(*args, **kwargs):
        calls.append(kwargs['max_step'])
        return integrator(*args, **kwargs)

    monkeypatch.setattr(integrate, 'radau', capture)
    _, tr = run(source)
    assert tr.settings['max_step'] == pytest.approx(0.0025)
    assert calls and all(step == pytest.approx(0.0025) for step in calls)
    # logistic-type decay a' = -a^2/(100*0.02): a(t) = 100 / (1 + 50 t)
    assert tr.env_at(2)['s.alive'] == pytest.approx(100 / 101, rel=1e-7)
    assert tr.env_at(2)['s.dead'] == pytest.approx(100 - 100 / 101, rel=1e-7)


@pytest.mark.parametrize('timescale', ['0 h', '-1 h', '1 people', 'unknown_scale', 't'])
def test_public_invalid_physical_timescales_are_rejected(timescale):
    source = with_timescales(system(horizon=1), timescale)
    with pytest.raises(ModelError):
        compiled(source)


def numerical_model():
    # A quadratic drain is outside the exact affine and compartment kernels, so Radau integrates it.
    # The stock is the first coordinate of the solver state.
    return system(
        stock('stock', 50),
        stock('used', kind='tally'),
        flow('use', move('stock', 'used'), '0.01 per_h * stock * stock / 1 people'),
        horizon=8,
    )


def misbehaving_solver(monkeypatch, failure):
    """Every solver call hides a negative dense value around 3 h, or fails event location."""
    real = integrate.radau

    def solve(*args, **kwargs):
        if failure == 'event_location':
            raise ValueError('f(a) and f(b) must have different signs')
        solution = real(*args, **kwargs)
        dense = solution.sol

        def hidden(t):
            values = dense(t)
            at = np.atleast_1d(t)
            inside = np.abs(at - 3) <= 0.25
            values = values.copy()
            if values.ndim == 1:
                values[0] = -5 if inside.any() else values[0]
            else:
                values[0, inside] = -5
            return values

        solution.sol = hidden
        return solution

    monkeypatch.setattr(integrate, 'radau', solve)


def test_a_hidden_excursion_rejects_the_run(monkeypatch):
    misbehaving_solver(monkeypatch, 'excursion')
    with pytest.raises(SimulationError, match='hidden excursion'):
        run(numerical_model())


def test_failed_event_location_rejects_the_run(monkeypatch):
    misbehaving_solver(monkeypatch, 'event_location')
    with pytest.raises(SimulationError, match='event location failed'):
        run(numerical_model())


def test_a_state_outside_its_bounds_names_each_quantity_outside_them_in_their_order():
    source = system(*held('a', 1), *held('b', 1, maximum=10), *held('c', 1), *held('d', 1), horizon=1)
    rs = compiled(source).resolve('a')
    for name, initial in (('s.a', -5), ('s.b', 12), ('s.d', -1)):
        rs = rs.with_part('quantities', name, rs.quantities[name].changed(initial=initial))
    with pytest.raises(SimulationError) as caught:
        runtime.simulate(rs, library())
    assert str(caught.value).endswith(str(['s.a', 's.b', 's.d']))


def test_a_check_that_cannot_be_evaluated_is_named_by_its_evaluation():
    # The domain of this check ends at 5 h. It is set after compilation, so no domain proof stops it.
    # The failure names the expression by its text. A part holds the node of its expression: a text
    # that a caller writes into a part is a TypeError.
    source = system(stock('a', 1), checks=(check('s.a >= 0 people'),), horizon=10)
    rs = compiled(source).resolve('a')
    (name,) = rs.state_checks
    failing = "ln((q(5, 'h') - t) / q(1, 'h')) < 100"
    held = rs.with_part('state_checks', name, rs.state_checks[name].changed(expr=nodes.read(failing)))
    with pytest.raises(ExpressionError) as caught:
        runtime.simulate(held, library())
    assert repr(failing) in str(caught.value)
    text = rs.with_part('state_checks', name, rs.state_checks[name].changed(expr=failing))
    with pytest.raises(TypeError, match='an expression is a node or a number'):
        runtime.simulate(text, library())


def test_a_step_of_the_trace_names_the_record_of_its_event():
    """Each event of the fixture rests on the record `fixture`, an identity. One fires as it
    triggers, and one waits half an hour: the trace has the step of the first, and for the second
    the step where it triggers (no outcome yet) and the step where it fires. Each has the identity
    of the record, its name and its kind (docs/engine.md, "The trace"), as plain data that a report
    can write."""
    source = system(
        named('x', 'a', 'b'),
        named('z', 'a', 'b'),
        event('go', 't >= 1 h', 'x = "b"', doc='Go'),
        event('later', 't >= 1 h', 'z = "b"', after='0.5 h', doc='Later'),
        stock('y', 0),
        outputs=(output('y', 's.y', 'people', 'level', doc='y'),),
        horizon=2,
    )
    _, trajectory = run(source)
    steps = [(item['t'], item['event'], item['outcome']) for item in trajectory.trace]
    assert steps == [(1.0, 's.go.done', 'done'), (1.0, 's.later', None), (1.5, 's.later.done', 'done')]
    for item in trajectory.trace:
        assert item['basis'] == {'name': 'fixture', 'kind': 'identity'}
        assert json.loads(json.dumps(item['basis'])) == item['basis']


def test_a_rate_that_fails_inside_the_solver_rejects_the_run_at_once():
    # The domain of this rate ends at 5 h. It is set after compilation, so no domain proof stops it. The
    # rate of a tally never falls below zero inside its domain.
    source = system(stock('level', 0, minimum=None, kind='state', rate='1 people/h'), horizon=10)
    rs = compiled(source).resolve('a')
    failing = "q(1, 'people/h') * sqrt((q(5, 'h') - t) / q(1, 'h'))"
    rs = rs.with_part('rates', 's.level', rs.rates['s.level'].changed(expr=nodes.read(failing)))
    with pytest.raises(SimulationError, match='Rate evaluation failed') as caught:
        runtime.simulate(rs, library())
    assert not any(item.get('code') == 'numerical_refinement' for item in caught.value.diagnostics)
