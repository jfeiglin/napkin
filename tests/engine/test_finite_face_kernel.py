"""Fresh-context analytic witnesses for finite faces and repayment certificates."""

import math

import pytest

from napkin.engine.runtime import SimulationError, simulate
from napkin.model import ModelError
from tests.build import (
    compiled,
    drop,
    edit,
    event,
    flow,
    formula,
    library,
    member,
    move,
    named,
    named_event,
    once_at,
    replace,
    resolved,
    run,
    scenario,
    share,
    stock,
    system,
    with_horizon,
)

REJECTED_WHEN = 'service/{}/when:'
# The check of the supplied empty stock fixture: the 20 people of the warehouse are conserved.
CONSERVED = 'abs(warehouse + stock + served - 20 people) <= 1e-8 people'


def variable(name, initial, unit, **lines):
    """A number state: it rises and falls freely."""
    return stock(name, initial, unit, minimum=None, size=1, kind='state', **lines)


def rejected_paths(caught):
    return {(diagnostic['code'], diagnostic['path']) for diagnostic in caught.value.diagnostics}


def with_timescale(text, timescale):
    """A text whose solver keeps its steps shorter than `timescale`."""
    return edit(text, member('scenario:', f'timescales {timescale}'))


def supplied_empty_stock_fixture(*, delayed=False, delivery='1 people/h if stock > 0 else 0'):
    """The analytic transfer for 12 h, with an empty stock that a warehouse of 20 people supplies at
    2 people an hour, from the start or, when `delayed`, from 4 h. The service delivers at `delivery`
    and never stops, and the milestone `empty` happens when its stock is empty."""
    supply = '2 people/h if state is "on" else 0' if delayed else '2 people/h'
    starts = event(
        'supply_starts', 't >= 4 h', once=False, transition='state "off" -> "on"', doc='Supply starts'
    )
    return edit(
        with_horizon(scenario(), 12),
        replace('var stock: people = n', 'var stock: people = 0'),
        replace('rate if state is "on" else 0 people/h', delivery),
        *((replace('var state: "on" | "off" = "on"', 'var state: "on" | "off" = "off"'),) if delayed else ()),
        drop('service/stop'),
        replace('assert stock + served is n', f'assert {CONSERVED}'),
        member(
            'service',
            stock('warehouse', '20 people', size=20),
            flow('supply', 'warehouse -> stock', supply),
            event('empty', 'stock <= 0', doc='Empty'),
            *((starts,) if delayed else ()),
        ),
    )


@pytest.mark.parametrize('delayed', [False, True])
def test_zero_face_departure_switches_to_the_positive_stock_field(delayed):
    _, trajectory = run(supplied_empty_stock_fixture(delayed=delayed))
    offset = 4 if delayed else 0
    # While warehouse has supply: W'=−2, S'=2−1, C'=1.
    # After W reaches zero at exposure10: S'=−1, C'=1.
    for t in (offset, offset + 0.5, offset + 2, offset + 5, 12):
        exposure = max(0, t - offset)
        env = trajectory.env_at(t)
        expected_warehouse = max(0, 20 - 2 * exposure)
        expected_served = exposure
        expected_stock = 20 - expected_warehouse - expected_served
        assert env['service.warehouse'] == pytest.approx(expected_warehouse, abs=2e-7)
        assert env['service.stock'] == pytest.approx(expected_stock, abs=2e-7)
        assert env['service.served'] == pytest.approx(expected_served, abs=2e-7)
        assert env['service.warehouse'] + env['service.stock'] + env['service.served'] == pytest.approx(
            20, abs=1e-10
        )


def test_zero_face_chattering_field_fails_explicitly():
    rs = resolved(supplied_empty_stock_fixture(delivery='3 people/h if stock > 0 else 0'))
    # At zero, S'=2; immediately above zero, S'=2−3<0.
    # This discontinuous field has no forward classical trajectory.
    with pytest.raises(SimulationError, match='chattering'):
        simulate(rs, library())


def test_positive_face_departure_propagates_through_an_empty_downstream_stock():
    sc = edit(
        with_horizon(supplied_empty_stock_fixture(delivery='1.99999999 people/h if stock > 0 else 0'), 1),
        replace('flow serve: stock -> served', 'flow serve: stock -> second'),
        replace(CONSERVED, 'abs(warehouse + stock + second + served - 20 people) <= 1e-8 people'),
        member(
            'service',
            stock('second', size=10),
            flow('finish', 'second -> served', '0.5 people/h if second > 0 else 0'),
        ),
    )
    _, trajectory = run(sc)
    # The positive-side field gives S'=1e−8, Q'=1.49999999, C'=.5.
    for t in (0.25, 0.5, 1):
        env = trajectory.env_at(t)
        assert env['service.stock'] == pytest.approx(1e-8 * t, abs=2e-9)
        assert env['service.second'] == pytest.approx(1.49999999 * t, abs=2e-7)
        assert env['service.served'] == pytest.approx(0.5 * t, abs=2e-7)
        assert sum(
            env[f'service.{name}'] for name in ('warehouse', 'stock', 'second', 'served')
        ) == pytest.approx(20, abs=1e-10)


def test_a_tiny_positive_stock_cannot_skip_depletion_at_a_large_timestamp():
    supply = '83333.33333333333 people/h if state is "on" else 0'
    sc = edit(
        with_horizon(
            supplied_empty_stock_fixture(
                delayed=True, delivery=f'300000 people/h if stock > 0 else {supply}'
            ),
            4321,
        ),
        replace('var warehouse: people = 20 people', 'var warehouse: people = 1000000 people'),
        replace('size 20 people', 'size 1000000 people'),
        replace('at 2 people/h if state is "on" else 0', f'at {supply}'),
        replace('t >= 4 h:', 't >= 4320 h:'),
        member('service/supply_starts', 'move 1e-18 people from warehouse to stock'),
        replace(CONSERVED, 'abs(warehouse + stock + served - 1000000 people) <= 1e-7 people'),
    )
    _, trajectory = run(sc)
    # The physical depletion delay is1e−18/(300000−83333.3333)h,
    # below the spacing of timestamps near4320h. Flow then passes through0.
    for at in (4320, 4320.5, 4321):
        env = trajectory.env_at(at)
        served = (at - 4320) * (250000 / 3)
        assert env['service.stock'] == pytest.approx(0, abs=1e-9)
        assert env['service.served'] == pytest.approx(served, abs=1e-7)
        assert env['service.warehouse'] == pytest.approx(1000000 - served, abs=1e-7)
        assert env['service.warehouse'] + env['service.stock'] + env['service.served'] == pytest.approx(
            1000000, abs=1e-7
        )
    assert all(segment.start < segment.end for segment in trajectory._segments)


def test_a_fast_affine_threshold_is_located_inside_the_event_time_tolerance():
    sc = edit(
        with_horizon(scenario(), 1),
        replace('var stock: people = n', 'var stock: people = 0'),
        drop('service/stop', 'service/serve', 'service/assert:/0'),
        member(
            'service',
            flow('supply', move(None, 'stock'), '1e10 people/h if state is "on" else 0'),
            event(
                'enough',
                'stock >= 1 people',
                once=False,
                transition='state "on" -> "off"',
                doc='Enough supply',
            ),
        ),
    )
    _, trajectory = run(sc)
    # S(t)=1e10*t reaches1 at1e−10h; the stop then fixes S=1.
    assert trajectory.trace[0]['t'] == pytest.approx(1e-10, abs=1e-20)
    assert trajectory.env_at(1)['service.stock'] == pytest.approx(1, abs=1e-10)
    assert not trajectory.settings['integration_segments']


def test_active_threshold_gate_settles_before_an_ordered_follower():
    sc = edit(
        scenario(),
        replace('var stock: people = n', 'var stock: people = 0'),
        replace('= rate if state is "on" else 0 people/h', '= 0'),
        drop('service/stop', 'service/assert:/0'),
        # At one moment the events go in the order of their lines: `notice` before `follower`.
        member(
            'service',
            variable('flag', 0, 'fraction'),
            once_at('open_gate', '0 h', 'flag = 1', doc='Open gate'),
            event('notice', 'stock <= 0 and flag is 1', doc='Notice'),
            once_at('follower', '0 h', doc='Follower'),
        ),
    )
    _, trajectory = run(sc)
    assert [event['rule'] for event in trajectory.trace] == [
        'service.open_gate',
        'service.notice',
        'service.follower',
    ]
    assert all(event['t'] == 0 for event in trajectory.trace)


def test_discrete_gate_activation_observes_a_previously_crossed_threshold():
    sc = edit(
        scenario(),
        drop('service/stop'),
        member(
            'service',
            variable('flag', 0, 'fraction'),
            once_at('open_gate', '12 h', 'flag = 1', doc='Open gate'),
            event('notice', 'stock <= 0 and flag is 1', doc='Notice'),
        ),
    )
    _, trajectory = run(sc)
    assert [(event['rule'], event['t']) for event in trajectory.trace] == [
        ('service.open_gate', 12),
        ('service.notice', 12),
    ]
    assert trajectory.env_at(10)['service.stock'] == 0
    assert trajectory.env_at(24)['service.served'] == pytest.approx(10)


def timed_crossing(when, paused=False):
    """The analytic transfer of `scenario()`: 10 people move at 24 people a day, 1 an hour, so the
    served tally is S(t) = t people until the stock empties at 10 h. `paused` stops the delivery
    from 1 h to 2 h, so S(t) = t - 1 after 2 h. A milestone `watch` happens on `when`: its trigger and
    the times when it happens."""
    watch = event('watch', when, doc='Watch')
    if paused:
        # The stop and the pause fire one event, which switches the service off.
        steps = (
            member('service/stop', 'switch_off'),
            member(
                'service',
                event('pause', 't >= 1 h', 'switch_off', transition='state "on" -> "off"', doc='Pause'),
                event('resume', 't >= 2 h', transition='state "off" -> "on"', doc='Resume'),
                watch,
                named_event('switch_off', 'state = "off"', records=None),
            ),
        )
    else:
        steps = (member('service', watch),)
    sc = edit(scenario(), *steps)
    (structure,) = compiled(sc).structures.values()
    _, trajectory = run(sc)
    return structure.rules['service.watch'].trigger, [
        entry['t'] for entry in trajectory.trace if entry['rule'] == 'service.watch'
    ]


@pytest.mark.parametrize(('threshold', 'expected'), [(3, 5.0), (7, 7.0)])
def test_a_crossing_with_a_clock_happens_at_the_clock_or_at_the_first_crossing_after_it(threshold, expected):
    """The clock holds from T = 5 h, and S(5) = 5: a threshold of 3 already holds at T, so the event
    is at T; a threshold of 7 is crossed after T, where S(t) = 7."""
    trigger, times = timed_crossing(f'served >= {threshold} people and t >= 5 h')
    assert trigger.kind == 'crossing' and trigger.times
    assert times == pytest.approx([expected], abs=1e-8)


def test_a_clock_whose_anchor_moves_before_it_is_due_moves_the_moment():
    """The state changes at 1 h and again at 2 h, so `elapsed(state) >= 2 h` holds from 4 h, not from
    3 h, though S(3) = 2 already holds the threshold of 2."""
    trigger, times = timed_crossing('elapsed(state) >= 2 h and served >= 2 people', True)
    assert trigger.kind == 'crossing'
    assert times == pytest.approx([4.0], abs=1e-8)


@pytest.mark.parametrize('gate', ['served > 1 people', 'served >= 1 people'])
def test_continuous_active_threshold_gates_fail_compilation(gate):
    sc = edit(supplied_empty_stock_fixture(), replace('when stock <= 0:', f'when stock <= 0 and {gate}:'))
    with pytest.raises(ModelError) as caught:
        compiled(sc)
    assert ('unsupported_condition', REJECTED_WHEN.format('empty')) in rejected_paths(caught), (
        caught.value.diagnostics
    )


@pytest.mark.parametrize(
    'predicate',
    ['stock > 0', 'stock is not 0', 'not (stock <= 0)', 'stock > 0 or state is "off"'],
)
def test_a_strict_stock_presence_event_requires_an_attained_first_timestamp(predicate):
    sc = edit(
        supplied_empty_stock_fixture(delivery='1.99999999 people/h if stock > 0 else 0'),
        member('service', event('stock_present', predicate, doc='Stock present')),
    )
    # Positive-side S(t)=1e−8*t: S>0 holds for every t>0 and has no
    # attained first time. The compiler requires closed zero-face truth.
    with pytest.raises(ModelError) as caught:
        compiled(sc)
    assert ('unsupported_condition', REJECTED_WHEN.format('stock_present')) in rejected_paths(caught), (
        caught.value.diagnostics
    )


@pytest.mark.parametrize(
    'rate',
    [
        '1 people/h * sqrt(stock / 1 people)',
        '1 people/h * (stock / 1 people) ** 2',
        '1 people/h * (1 + t / 1 h) if stock > 0 else 0',
        '1 people/h if stock > 1 people else 0',
    ],
)
def test_finite_face_proof_rejects_tangent_forced_and_interior_switches(rate):
    sc = edit(
        supplied_empty_stock_fixture(delivery=rate),
        replace('var stock: people = 0', 'var stock: people = 5 people'),
        replace(CONSERVED, 'warehouse + stock + served is 25 people'),
    )
    with pytest.raises(ModelError) as caught:
        compiled(sc)
    assert ('unsupported_condition', REJECTED_WHEN.format('empty')) in rejected_paths(caught), (
        caught.value.diagnostics
    )


def test_a_proved_face_network_preserves_an_independent_clock_forced_pulse():
    sc = edit(
        with_timescale(with_horizon(supplied_empty_stock_fixture(), 1), '0.01 h'),
        replace('var stock: people = 0', 'var stock: people = 5 people'),
        replace(CONSERVED, 'abs(warehouse + stock + served - 25 people) <= 1e-8 people'),
        member(
            'service',
            variable('clock', 0, 'h', rate='1'),
            stock('pulse_supply', '100 people', size=100),
            stock('pulse_received', minimum=None, size=100, kind='tally'),
            flow(
                'pulse',
                'pulse_supply -> pulse_received',
                '1 people/h * (1 + 1000 * exp(-((clock - 0.45 h) / 0.01 h) ** 2))',
            ),
        ),
    )
    _, trajectory = run(sc)
    # clock(t)=t; substitute u=(t−.45)/.01 into the Gaussian integral.
    expected = 1 + 5 * math.sqrt(math.pi) * (math.erf(55) - math.erf(-45))
    env = trajectory.env_at(1)
    assert env['service.pulse_received'] == pytest.approx(expected, abs=1e-7)
    assert env['service.pulse_supply'] + env['service.pulse_received'] == pytest.approx(100, abs=1e-10)
    assert trajectory.settings['integration_segments']
    assert all(segment['max_step_h'] == 0.00125 for segment in trajectory.settings['integration_segments'])


def repayment_fixture(cash, *, income=0, expenses=0):
    """Cash repays debt at min(debt / 2 h, (cash - 5) / 1 h): one flow of two pairs, cash to paid and
    debt to retired, which move together. With expenses, a second flow draws on cash, and an
    share serves the repayment first."""
    members = [
        stock('cash', cash),
        stock('debt', 10),
        stock('paid', kind='tally'),
        stock('retired', kind='tally'),
        formula('repay', 'min(debt / 2 h, max(0, cash - 5 people) / 1 h)', 'people/h'),
        flow('repayment', ['cash -> paid', 'debt -> retired'], 'repay'),
    ]
    if income:
        members.append(flow('income', move(None, 'cash'), f'{income} people/h'))
    if expenses:
        members += [
            stock('spent', kind='tally'),
            # Competing withdrawals from cash share one explicit share. Its limit is the sum of both
            # requests, so the share never curtails either flow.
            flow('expense', 'cash -> spent', f'{expenses} people/h'),
            share('cash', f'repay + {expenses} people/h', ['repayment', 'expense']),
        ]
    return with_timescale(system(*members, horizon=12), '1 h')


def _assert_repayment_reference_boundary_and_resolution(trajectory):
    # Cash-limited branch: C=7−e^(−t), D=11−2t−e^(−t).
    # R switches when 2t=7+e^(−t), then D follows exponential decay.
    lo, hi = 3, 4
    for _ in range(70):
        midpoint = (lo + hi) / 2
        if 2 * midpoint < 7 + math.exp(-midpoint):
            lo = midpoint
        else:
            hi = midpoint
    switch = (lo + hi) / 2
    debt_at_switch = 11 - 2 * switch - math.exp(-switch)
    for t in (0.5, 2, switch, 4.5, 6, 12):
        debt = 11 - 2 * t - math.exp(-t) if t <= switch else debt_at_switch * math.exp(-(t - switch) / 2)
        cash = debt - 4 + 2 * t
        env = trajectory.env_at(t)
        assert env['s.cash'] == pytest.approx(cash, abs=2e-8)
        assert env['s.debt'] == pytest.approx(debt, abs=2e-8)
        assert env['s.cash'] - env['s.debt'] == pytest.approx(-4 + 2 * t, abs=1e-10)
        assert env['s.cash'] + env['s.paid'] == pytest.approx(6 + 2 * t, abs=1e-10)
        assert env['s.debt'] + env['s.retired'] == pytest.approx(10, abs=1e-10)
    # The independent budget clock C−D=−4+2t reaches its reserve at 4.5h.
    segments = trajectory.settings['integration_segments']
    assert any(segment['end_h'] == pytest.approx(4.5, abs=1e-8) for segment in segments)
    assert segments[-1]['end_h'] in (pytest.approx(4.5, abs=1e-8), pytest.approx(12, abs=1e-8))
    assert all(segment['max_step_h'] == 0.125 for segment in segments)


def test_repayment_preserves_reference_and_resolution_at_proved_boundary():
    _, trajectory = run(repayment_fixture(6, income=2))
    _assert_repayment_reference_boundary_and_resolution(trajectory)


def test_repayment_endpoint_roundoff_preserves_reference_boundary_and_resolution(monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    rs = resolved(repayment_fixture(6, income=2))
    original = integrate.radau
    injected = []
    indices = {name: i for i, name in enumerate(rs.quantities)}

    def rounded_endpoint(*args, **kwargs):
        solution = original(*args, **kwargs)
        if not injected and abs(float(solution.t[-1]) - 4.5) < 1e-8:
            ci, di, pi = indices['s.cash'], indices['s.debt'], indices['s.paid']
            before = float(solution.y[ci, -1])
            # Place the endpoint two ULPs below the lesser of the solver value
            # and the reserve surface, preserving the independently proved ledger.
            surface = float(solution.y[di, -1]) + 5
            start = min(before, surface)
            after = math.nextafter(math.nextafter(start, -math.inf), -math.inf)
            solution.y[ci, -1] = after
            solution.y[pi, -1] += before - after
            injected.append(
                {'delta': before - after, 'residual': math.fsum((after, -float(solution.y[di, -1]), -5))}
            )
        return solution

    monkeypatch.setattr(integrate, 'radau', rounded_endpoint)
    trajectory = simulate(rs, library())
    assert len(injected) == 1 and injected[0]['delta'] > 0
    assert injected[0]['residual'] < 0
    _assert_repayment_reference_boundary_and_resolution(trajectory)
    for t in (4.5, 6, 12):
        env = trajectory.env_at(t)
        assert env['s.paid'] == pytest.approx(env['s.retired'], abs=1e-10)


def test_competing_cash_withdrawal_keeps_the_physical_resolution_cap():
    sc = with_horizon(repayment_fixture(20, expenses=3), 2)
    _, trajectory = run(sc)
    # Cash−debt=10−3t, so the extra withdrawal defeats the tail invariant.
    for t in (0.25, 1, 2):
        expected_debt = 10 * math.exp(-t / 2)
        env = trajectory.env_at(t)
        assert env['s.debt'] == pytest.approx(expected_debt, abs=2e-8)
        assert env['s.cash'] == pytest.approx(expected_debt + 10 - 3 * t, abs=2e-8)
        assert env['s.cash'] + env['s.paid'] + env['s.spent'] == pytest.approx(20, abs=1e-10)
        assert env['s.debt'] + env['s.retired'] == pytest.approx(10, abs=1e-10)
    assert trajectory.settings['integration_segments']
    assert all(segment['max_step_h'] == 0.125 for segment in trajectory.settings['integration_segments'])


def test_a_blocked_resource_transaction_has_an_exact_catchup_boundary(monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    sc = system(
        *(stock(name) for name in ('source', 'resource', 'queue', 'committed', 'completed', 'recaptured')),
        stock('deferred', 100),
        named('economy', 'waiting', 'catching_up'),
        # Provisioning uses the resource: one flow moves both together.
        flow('production', ['source -> queue', 'resource -> committed'], '2 people/h'),
        flow('commission', 'queue -> completed', '3 people/h'),
        flow('defer', move(None, 'deferred'), '1.7 people/h + queue / 1 h'),
        flow('catchup', 'deferred -> recaptured', '5 people/h if economy is "catching_up" else 0'),
        event('catchup_starts', 't >= 4 h', once=False, transition='economy "waiting" -> "catching_up"'),
        horizon=100,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError('a proved blocked transaction entered the numerical solver')

    monkeypatch.setattr(integrate, 'radau', forbidden)
    _, trajectory = run(sc)
    # Empty source/resource block provisioning; queue and commissioning stay0.
    # D=100+1.7t−5(t−4) for4<=t<=t_empty; then recapture follows inflow.
    empty = 4 + (100 + 1.7 * 4) / (5 - 1.7)
    for t in (0, 4, 10, empty, 50, 100):
        env = trajectory.env_at(t)
        recaptured = min(5 * max(0, t - 4), 100 + 1.7 * t)
        assert env['s.deferred'] == pytest.approx(100 + 1.7 * t - recaptured, abs=1e-10)
        assert env['s.recaptured'] == pytest.approx(recaptured, abs=1e-10)
        assert env['s.deferred'] + env['s.recaptured'] == pytest.approx(100 + 1.7 * t, abs=1e-10)
        assert all(
            env[f's.{name}'] == 0 for name in ('source', 'resource', 'queue', 'committed', 'completed')
        )
    assert not trajectory.settings['integration_segments']


def test_coupled_admissions_share_capacity_across_a_discrete_access_change():
    """Two people ledgers each spend a leg of one common place inventory."""
    sc = system(
        *(
            stock(name, initial)
            for name, initial in [
                ('town', 90),
                ('worker', 20),
                ('town_admitted', 0),
                ('worker_admitted', 0),
                ('places', 100),
                ('occupied', 0),
            ]
        ),
        stock('share', 1, 'fraction', maximum=1, size=1, kind='state'),
        named('access', 'closed', 'open'),
        formula('intake', '2 people/h + 1 people/h * exp(-t / 1 h)', 'people/h'),
        # Each admission moves a person and takes a place, together.
        flow('admit_town', ['town -> town_admitted', 'places -> occupied'], 'intake * share'),
        flow(
            'admit_worker',
            ['worker -> worker_admitted', 'places -> occupied'],
            'intake * (1 - share) if access is "open" else 0',
        ),
        share('places', 'intake'),
        event(
            'access_opens', 't >= 4 h', 'share = 9 / 11', once=False, transition='access "closed" -> "open"'
        ),
        horizon=8,
    )
    _, trajectory = run(sc)

    def integral(a, b):
        return 2 * (b - a) + math.exp(-a) - math.exp(-b)

    for t in (0, 2, 4, 4.1, 6, 8):
        env = trajectory.env_at(t)
        early = integral(0, min(t, 4))
        late = integral(4, t) if t > 4 else 0
        assert env['s.town_admitted'] == pytest.approx(early + 9 / 11 * late, abs=1e-7)
        assert env['s.worker_admitted'] == pytest.approx(2 / 11 * late, abs=1e-7)
        assert env['s.town'] + env['s.town_admitted'] == pytest.approx(90, abs=1e-8)
        assert env['s.worker'] + env['s.worker_admitted'] == pytest.approx(20, abs=1e-8)
        assert env['s.places'] + env['s.occupied'] == pytest.approx(100, abs=1e-8)
        assert env['s.occupied'] == pytest.approx(env['s.town_admitted'] + env['s.worker_admitted'], abs=1e-8)


def test_nonlinear_inlet_dependencies_reach_an_empty_buffer_outlet():
    sc = system(
        stock('source', 1),
        stock('buffer'),
        stock('sink'),
        flow('inlet', 'source -> buffer', 'source ** 2 / 1 people / 1 h'),
        flow('outlet', 'buffer -> sink', '100 people/h'),
        horizon=2,
    )
    _, trajectory = run(sc)
    # S'=-S², S(0)=1. The empty pass-through queue delivers 1-S(t).
    for t in (0, 0.01, 0.1, 1, 2):
        env = trajectory.env_at(t)
        assert env['s.source'] == pytest.approx(1 / (1 + t), abs=1e-8)
        assert env['s.buffer'] == pytest.approx(0, abs=1e-10)
        assert env['s.sink'] == pytest.approx(t / (1 + t), abs=1e-8)
        assert sum(env[f's.{n}'] for n in ('source', 'buffer', 'sink')) == pytest.approx(1, abs=1e-8)
