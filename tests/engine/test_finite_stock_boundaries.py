"""Independent conservation and finite-face crossing witnesses.

Cross-case peer counterexamples for physical stock-root correction.

Expected stocks and ledgers use literal constant-rate arithmetic. The clinical
cohort keeps these witnesses on the numerical solver path.
"""

import math

import pytest

from napkin import SCHEMA_VERSION
from napkin.engine.runtime import NumericalSettings, SimulationError, simulate
from napkin.model import ModelError
from napkin.model.runs import Runs
from tests.build import (
    append,
    compiled,
    drop,
    edit,
    entity,
    event,
    flow,
    formula,
    library,
    member,
    move,
    named,
    named_event,
    once_at,
    parameter,
    replace,
    resolved,
    run,
    scenario,
    stock,
    system,
    with_horizon,
)

REJECTED_WHEN = 'service/{}/when:'
# The check of the boundary fixture: the people of the service and of the warehouse are conserved.
CONSERVED = 'warehouse + stock + served is n + 20 people'
# The end of the line of `empty` in the boundary fixture: its crossing of the stock.
EMPTY = 'stock <= 0:'
# The events of the boundary fixture that its tests take out, with the event `switch_off` that the stop
# and `empty` fire.
STOPS = ('service/stop', 'service/empty', 'service/refill_1', 'service/refill_2', 'service/switch_off')


def transaction(model, edits):
    """{run: resolved structure} of every run of a model under one edit document: the runs check the
    edits as one transaction, and the model resolves each run with its values."""
    document = {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **edits}
    values = Runs.from_table(model.run_table).resolve(document, model_hash=model.model_hash)
    return {name: model.resolve(name, item.values) for name, item in values.items()}


def fired(trajectory, rule):
    return [entry['t'] for entry in trajectory.trace if entry['rule'] == rule]


def rejected_paths(caught):
    return {(d['code'], d['path']) for d in caught.value.diagnostics}


def with_timescale(text, timescale):
    """A text whose solver keeps its steps shorter than `timescale`."""
    return edit(text, member('scenario:', f'timescales {timescale}'))


def boundary_fixture():
    """The analytic transfer for 12 h, with 5 people waiting, delivered at 1 person an hour while any
    wait, beside a warehouse of 20 people that supplies nothing and refills the stock with 2 people at
    8 h and with 1 at 11 h. The service stops at 12 h, or when its stock is empty: the stop and `empty`
    fire one event, `switch_off`."""
    return edit(
        with_horizon(scenario(), 12),
        replace('input n: people = 10 people', 'input n: people = 5 people'),
        replace('rate if state is "on" else 0 people/h', '1 people/h if stock > 0 else 0'),
        replace('stock + served is n', CONSERVED),
        member('service/stop', 'switch_off'),
        member(
            'service',
            stock('warehouse', '20 people', size=20),
            flow('supply', 'warehouse -> stock', 0),
            event(
                'empty',
                'stock <= 0',
                'switch_off',
                once=False,
                transition='state "on" -> "off"',
                doc='Empty',
            ),
            *(
                once_at(f'refill_{number}', f'{at} h', f'move {amount} people from warehouse to stock')
                for number, at, amount in ((1, 8, 2), (2, 11, 1))
            ),
            named_event('switch_off', 'state = "off"', records=None),
        ),
    )


def test_exact_zero_face_then_two_refills_preserves_mass():
    _, trajectory = run(boundary_fixture())
    assert fired(trajectory, 'service.empty')[0] == 5
    for at, remaining, served in ((5, 0, 5), (8.5, 1.5, 5.5), (10, 0, 7), (11.5, 0.5, 7.5), (12, 0, 8)):
        env = trajectory.env_at(at)
        assert env['service.stock'] == pytest.approx(remaining, abs=1e-10)
        assert env['service.served'] == pytest.approx(served, abs=1e-10)
        assert env['service.warehouse'] + env['service.stock'] + env['service.served'] == pytest.approx(
            25, abs=1e-10
        )
    assert not trajectory.settings['integration_segments']


@pytest.mark.parametrize('change', ['sqrt', 'time', 'derivative', 'set', 'transfer', 'positive_threshold'])
def test_boundary_proof_rejects_fields_outside_finite_face_class(change):
    delivery = '1 people/h if stock > 0 else 0'
    # `empty` empties the stock, or moves a person into it, beside the stop. Neither fires the event
    # that switches the service off any more, so the stop is its transition alone.
    emptying = {'set': 'stock = 0', 'transfer': 'move 1 people from warehouse to stock'}
    if change == 'sqrt':
        steps = [replace(delivery, '1 people/h * sqrt(stock / 1 people)')]
    elif change == 'time':
        steps = [replace(delivery, '1 people/h * (1 + t / 1 h) if stock > 0 else 0')]
    elif change == 'derivative':
        # The field keeps the delivery and gains a term outside the class.
        steps = [replace(delivery, f'({delivery}) + 1 people/h * sqrt(stock / 1 people)')]
    elif change in emptying:
        steps = [drop('service/stop/done/1', 'service/switch_off'), replace('switch_off', emptying[change])]
    else:
        steps = [replace(EMPTY, 'stock <= 1 people:')]
    sc = edit(boundary_fixture(), *steps)
    with pytest.raises(ModelError) as caught:
        compiled(sc)
    assert ('unsupported_condition', REJECTED_WHEN.format('empty')) in rejected_paths(caught), (
        caught.value.diagnostics
    )


def threshold_parameter_fixture(default=0):
    """The boundary fixture, whose `empty` waits for the stock to fall to the input `empty_at`, of
    `default` people."""
    return edit(
        boundary_fixture(),
        replace(EMPTY, 'stock <= empty_at:'),
        member('service', parameter('empty_at', default, 'people', 0, 2)),
    )


@pytest.mark.parametrize('default', [0, 1])
def test_finite_face_proof_reads_the_transactions_effective_threshold(default):
    # The proof admits only an exact zero face. Its verdict must follow the
    # transaction's effective threshold, whatever the authored default.
    if default:
        with pytest.raises(ModelError):
            compiled(threshold_parameter_fixture(default))
    model = compiled(threshold_parameter_fixture(0))
    zero = transaction(model, {'set': {'service.empty_at': 0}})
    trajectory = simulate(zero['a'], library())
    assert fired(trajectory, 'service.empty')[0] == 5
    with pytest.raises(ModelError) as caught:
        transaction(model, {'set': {'service.empty_at': 1}})
    assert ('unsupported_condition', REJECTED_WHEN.format('empty')) in rejected_paths(caught), (
        caught.value.diagnostics
    )


def repayment_fixture(cash, debt=10):
    """Cash repays debt at min(debt / 2 h, (cash - 5) / 1 h): one flow of two pairs, cash to paid and
    debt to retired, which move together."""
    return with_timescale(
        system(
            stock('cash', cash),
            stock('debt', debt),
            stock('paid', kind='tally'),
            stock('retired', kind='tally'),
            formula('repay', 'min(debt / 2 h, max(0, cash - 5 people) / 1 h)', 'people/h'),
            flow('repayment', ['cash -> paid', 'debt -> retired'], 'repay'),
            horizon=20,
        ),
        '1 h',
    )


def test_proved_repayment_tail_matches_closed_form_without_numerical_steps(monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    def forbidden(*args, **kwargs):
        raise AssertionError('exact repayment tail entered numerical solver')

    monkeypatch.setattr(integrate, 'radau', forbidden)
    sc = with_horizon(repayment_fixture(20), 1000)
    _, trajectory = run(sc)
    for t in (0, 0.5, 2, 20, 1000):
        env = trajectory.env_at(t)
        paid = -10 * math.expm1(-t / 2)
        assert env['s.debt'] == pytest.approx(10 * math.exp(-t / 2), abs=1e-10)
        assert env['s.cash'] == pytest.approx(20 - paid, abs=1e-10)
        assert env['s.paid'] == env['s.retired'] == pytest.approx(paid, abs=1e-10)
        assert env['s.cash'] + env['s.paid'] == pytest.approx(20, abs=1e-10)
        assert env['s.debt'] + env['s.retired'] == pytest.approx(10, abs=1e-10)
    assert not trajectory.settings['integration_segments']


def test_repayment_arm_switch_preserves_capped_prefix_and_closed_form():
    sc = with_horizon(repayment_fixture(6, debt=1.5), 5)
    _, trajectory = run(sc)
    crossing = 2 * math.log(1.5)
    for t in (0.5, 2, 5):
        env = trajectory.env_at(t)
        debt = 1.5 * math.exp(-t / 2) if t <= crossing else 0.5 + 0.5 * math.exp(-(t - crossing))
        paid = 1.5 - debt
        assert env['s.cash'] == pytest.approx(6 - paid, abs=1e-8)
        assert env['s.debt'] == pytest.approx(debt, abs=1e-8)
        assert env['s.paid'] == pytest.approx(paid, abs=1e-8)
        assert env['s.retired'] == pytest.approx(paid, abs=1e-8)
    assert trajectory.settings['integration_segments']
    assert all(segment['max_step_h'] == 0.125 for segment in trajectory.settings['integration_segments'])


def test_zero_threshold_waits_for_discrete_activation():
    sc = edit(
        boundary_fixture(),
        replace('input n: people = 5 people', 'input n: people = 1 people'),
        replace('var stock: people = n', 'var stock: people = 0'),
        replace('= 1 people/h if stock > 0 else 0', '= 0'),
        drop('service/assert:/0', *STOPS),
        member(
            'service',
            event('activate', 't >= 3 h', once=False, transition='state "on" -> "off"', doc='Activate'),
            event('empty', 'stock <= 0 and count(activate) > 0 and state is "off"', doc='Empty'),
        ),
    )
    _, tr = run(sc)
    assert [(e['rule'], e['t']) for e in tr.trace] == [('service.activate', 3), ('service.empty', 3)]


@pytest.mark.parametrize(
    'gate, code',
    [
        ('stock > 0', 'unsupported_condition'),
        ('t > 1 h', 'unsupported_condition'),
        ('1', 'expression'),
        ('1 people', 'expression'),
    ],
)
def test_threshold_gate_requires_a_discrete_boolean(gate, code):
    sc = edit(boundary_fixture(), replace(EMPTY, f'stock <= 0 and ({gate}):'))
    with pytest.raises(ModelError) as caught:
        compiled(sc)
    assert (code, REJECTED_WHEN.format('empty')) in rejected_paths(caught), caught.value.diagnostics


def test_capped_pass_through_queue_uses_exact_positive_field(monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    def forbidden(*args, **kwargs):
        raise AssertionError('proved decreasing service entered numerical solver')

    monkeypatch.setattr(integrate, 'radau', forbidden)
    sc = system(
        stock('upstream', 100),
        stock('queue'),
        stock('served', kind='tally'),
        flow('arrive', 'upstream -> queue', 'upstream / 10 h'),
        flow('serve', 'queue -> served', 'min(20 people/h, queue / 1 h + upstream / 10 h)'),
        horizon=1000,
    )
    _, tr = run(sc)
    for t in (0, 0.5, 10, 100, 1000):
        env = tr.env_at(t)
        assert env['s.upstream'] == pytest.approx(100 * math.exp(-t / 10), abs=1e-10)
        assert env['s.queue'] == pytest.approx(0, abs=1e-10)
        assert env['s.served'] == pytest.approx(-100 * math.expm1(-t / 10), abs=1e-10)
        assert env['s.upstream'] + env['s.queue'] + env['s.served'] == pytest.approx(100, abs=1e-10)


def test_declining_ancestor_queues_preserve_capped_affine_arm(monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    def forbidden(*args, **kwargs):
        raise AssertionError('proved declining ancestor block entered numerical solver')

    monkeypatch.setattr(integrate, 'radau', forbidden)
    sc = system(
        stock('upstream', 2),
        stock('queue', 4),
        stock('served', kind='tally'),
        flow('arrive', 'upstream -> queue', 'upstream / 2 h'),
        flow('serve', 'queue -> served', 'min(10 people/h, queue / 1 h)'),
        horizon=1000,
    )
    _, tr = run(sc)
    for t in (0.5, 2, 20, 1000):
        env = tr.env_at(t)
        assert env['s.upstream'] == pytest.approx(2 * math.exp(-t / 2), abs=1e-10)
        assert env['s.queue'] == pytest.approx(2 * math.exp(-t / 2) + 2 * math.exp(-t), abs=1e-10)
        assert env['s.served'] == pytest.approx(6 - 4 * math.exp(-t / 2) - 2 * math.exp(-t), abs=1e-10)


def test_rising_ancestor_queue_retains_numerical_capacity_resolution():
    sc = system(
        stock('upstream', 20),
        stock('queue'),
        stock('served', kind='tally'),
        flow('arrive', 'upstream -> queue', 'upstream / 2 h'),
        flow('serve', 'queue -> served', 'min(3 people/h, queue / 1 h)'),
        horizon=0.2,
    )
    _, tr = run(sc)
    assert tr.settings['integration_segments']
    env = tr.env_at(0.2)
    assert env['s.upstream'] == pytest.approx(20 * math.exp(-0.1), abs=1e-8)
    assert env['s.queue'] == pytest.approx(20 * (math.exp(-0.1) - math.exp(-0.2)), abs=1e-8)
    assert env['s.served'] == pytest.approx(20 - 40 * math.exp(-0.1) + 20 * math.exp(-0.2), abs=1e-8)


def clinical_cohort(initial, rate, *, maximum=None):
    """A separate decaying cohort that keeps the run on the numerical solver path: its stock, its
    tally and the flow between them."""
    return (
        stock('clinical_pending', f'{initial} people', maximum=maximum, size=initial),
        stock('clinical_recovered', kind='tally', size=initial),
        flow('clinical_recovery', 'clinical_pending -> clinical_recovered', rate),
    )


@pytest.mark.parametrize('supply_rate', [330000, 300000])
def test_positive_departure_retains_balanced_zero_faces_and_shortage_accounting(monkeypatch, supply_rate):
    import napkin.engine.continuous.integrate as integrate

    sc = edit(
        with_horizon(boundary_fixture(), 49),
        replace('var state: "on" | "off" = "on"', 'var state: "on" | "off" = "off"'),
        replace('var stock: people = n', 'var stock: people = 0'),
        replace(
            CONSERVED,
            'abs(warehouse + stock + retail + consumer + served - 10000000000 people) <= 0.0001 people',
        ),
        # The rates have names of their own: a value and a flow of one entity never share a name.
        drop('service/delivery', 'service/serve', 'service/supply', 'service/warehouse', *STOPS),
        member(
            'service',
            stock('warehouse', '10000000000 people', size=10000000000),
            *(stock(name, size=100000000) for name in ('retail', 'consumer')),
            stock(
                'unmet',
                kind='tally',
                size=100000000,
                rate='1600000 people/h - burn_rate if state is "on" else 0',
            ),
            formula('supply_rate', f'{supply_rate} people/h if state is "on" else 0', 'people/h'),
            formula(
                'dispatch_rate',
                '300000 people/h if stock > 0 else min(300000 people/h, supply_rate)',
                'people/h',
            ),
            formula(
                'purchase_rate',
                '500000 people/h if retail > 0 else min(500000 people/h, dispatch_rate)',
                'people/h',
            ),
            formula(
                'burn_rate',
                '1600000 people/h if consumer > 0 else min(1600000 people/h, purchase_rate)',
                'people/h',
            ),
            flow('supply', 'warehouse -> stock', 'supply_rate'),
            flow('dispatch', 'stock -> retail', 'dispatch_rate'),
            flow('purchase', 'retail -> consumer', 'purchase_rate'),
            flow('burn', 'consumer -> served', 'burn_rate'),
            # The cohort still moves at 48 h, so the segment that starts there is a numerical one.
            *clinical_cohort(1, 'clinical_pending / 100 h', maximum=1),
            event('empty', 'stock <= 0', 'state = "off"'),
            event('activate', 't >= 48 h', once=False, transition='state "off" -> "on"', doc='Activate'),
        ),
    )
    rs = resolved(sc)
    ids = list(rs.quantities)
    original = integrate.radau
    observed = []

    def inspect_zero_face_continuation(fun, interval, initial, *args, **kwargs):
        if interval[0] == 48:
            trial = initial.copy()
            for name in ('retail', 'consumer'):
                trial[ids.index(f'service.{name}')] = 1
            velocity = fun(48, trial)
            for name, expected in {
                'warehouse': -supply_rate,
                'stock': supply_rate - 300000,
                'retail': 0,
                'consumer': 0,
                'served': 300000,
                'unmet': 1300000,
            }.items():
                assert velocity[ids.index(f'service.{name}')] == pytest.approx(expected, abs=1e-8)
            observed.append(True)
        return original(fun, interval, initial, *args, **kwargs)

    monkeypatch.setattr(integrate, 'radau', inspect_zero_face_continuation)
    tr = simulate(rs, library(), NumericalSettings())
    assert observed
    for at in (48.25, 48.5, 49):
        duration = at - 48
        env = tr.env_at(at)
        assert env['service.warehouse'] == pytest.approx(10000000000 - supply_rate * duration, abs=0.0001)
        assert env['service.stock'] == pytest.approx((supply_rate - 300000) * duration, abs=1e-6)
        assert env['service.retail'] == env['service.consumer'] == 0
        assert env['service.served'] == pytest.approx(300000 * duration, abs=1e-6)
        assert env['service.unmet'] == pytest.approx(1300000 * duration, abs=1e-6)


def monitored_activation(text):
    """The service starts off with a sub-ulp stock and turns on at 48 h. Its first depletion while on
    turns a separate monitor off: a change of a named state only, which leaves the stock field
    unchanged."""
    monitor = entity(
        'monitor',
        named('state', 'on', 'off'),
        named_event('turn_off', 'state = "off"'),
        doc='A monitor that the service turns off.',
        role='operator',
    )
    return edit(
        with_horizon(text, 49),
        replace('var state: "on" | "off" = "on"', 'var state: "on" | "off" = "off"'),
        replace('var stock: people = n', 'var stock: people = 1e-28 people'),
        drop(*STOPS),
        member(
            'service',
            event('activate', 't >= 48 h', once=False, transition='state "off" -> "on"', doc='Activate'),
            event('empty', 'stock <= 0 and state is "on"', 'monitor.turn_off', doc='Empty'),
        ),
        append(monitor),
    )


@pytest.mark.parametrize('drain_rate', [4e-13, 1])
def test_numeric_segment_settles_stock_root_below_timestamp_resolution(drain_rate):
    sc = edit(
        monitored_activation(boundary_fixture()),
        replace(
            '1 people/h if stock > 0 else 0', f'{drain_rate} people/h if stock > 0 and state is "on" else 0'
        ),
        member('service', *clinical_cohort(1, 'clinical_pending / 1 h', maximum=1)),
        replace(CONSERVED, 'abs(warehouse + stock + served - 20 people) <= 1e-12 people'),
    )
    _, tr = run(sc)
    assert fired(tr, 'service.empty')[0] == 48
    assert tr.env_at(49)['service.stock'] == 0
    assert tr.env_at(49)['service.warehouse'] + tr.env_at(49)['service.served'] == pytest.approx(
        20, abs=1e-12
    )
    corrections = [
        d
        for d in tr.diagnostics
        if d.get('state') == 'service.stock' and d.get('code') == 'boundary_roundoff'
    ]
    assert corrections and corrections[0]['delta'] == -1e-28
    assert corrections[0]['balancing_state'] in {'service.warehouse', 'service.served'}
    assert tr.settings['integration_segments']


@pytest.mark.parametrize('initial', [0, 1000000])
def test_empty_backlog_retains_conservative_incoming_allocation(initial, monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    def forbidden(*args, **kwargs):
        raise AssertionError('constant allocated stock entered numerical solver')

    monkeypatch.setattr(integrate, 'radau', forbidden)
    incoming = 121499.99999999997
    capacity = 338527.4999999999
    sc = system(
        stock('backlog', initial, size=1000000),
        stock('completed', kind='tally', size=1000000),
        flow('arrive', move(None, 'backlog'), f'{incoming!r} people/h'),
        flow('complete', 'backlog -> completed', f'{capacity!r} people/h'),
        horizon=43800,
    )
    _, tr = run(sc)
    empty_at = initial / (capacity - incoming)
    for at in (0, empty_at, 100, 43800):
        env = tr.env_at(at)
        assert env['s.backlog'] == pytest.approx(max(0, initial + (incoming - capacity) * at), abs=1e-7)
        assert env['s.completed'] == pytest.approx(initial + incoming * at - env['s.backlog'], abs=1e-5)
        assert env['s.backlog'] + env['s.completed'] == pytest.approx(initial + incoming * at, abs=1e-5)
    assert not tr.settings['integration_segments']


@pytest.mark.parametrize('initial', [0, 1000000])
def test_empty_backlog_balances_explicit_external_source_and_sink(initial, monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    def forbidden(*args, **kwargs):
        raise AssertionError('constant external allocation entered numerical solver')

    monkeypatch.setattr(integrate, 'radau', forbidden)
    incoming = 121499.99999999997
    capacity = 338527.4999999999
    sc = system(
        stock('backlog', initial, size=1000000),
        flow('arrive', move(None, 'backlog'), f'{incoming!r} people/h'),
        flow('complete', move('backlog', None), f'{capacity!r} people/h'),
        horizon=43800,
    )
    _, tr = run(sc)
    empty_at = initial / (capacity - incoming)
    for at in (0, empty_at / 2, empty_at, 100, 43800):
        remaining = tr.env_at(at)['s.backlog']
        external_arrivals = incoming * at
        external_departures = min(capacity * at, initial + external_arrivals)
        assert remaining == pytest.approx(initial + external_arrivals - external_departures, abs=1e-7)
    assert tr.env_at(43800)['s.backlog'] == 0
    assert not tr.settings['integration_segments']
    assert all(segment.end > segment.start for segment in tr._segments)


def test_located_positive_root_roundoff_preserves_refills_and_unhit_inventory(monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    # A flow of nothing out of the untouched inventory makes it a stock.
    untouched = (stock('untouched', '1e-28 people', size=100000000), flow('keep', move('untouched', None), 0))
    rs = resolved(numerical_fixture(*untouched))
    ids = list(rs.quantities)
    stock_row, served_row = ids.index('service.stock'), ids.index('service.served')
    original = integrate.radau
    injected = []

    def positive_interpolation_residue(fun, interval, initial, **kwargs):
        solution = original(fun, interval, initial, **kwargs)
        if solution.success and initial[stock_row] > 0 and abs(solution.y[stock_row, -1]) < 1e-8:
            delta = 2e-10 - solution.y[stock_row, -1]
            solution.y[stock_row, -1] += delta
            solution.y[served_row, -1] -= delta
            injected.append(float(solution.t[-1]))
        return solution

    monkeypatch.setattr(integrate, 'radau', positive_interpolation_residue)
    trajectory = simulate(rs, library(), NumericalSettings())
    assert len(injected) >= 2
    for at, remaining, consumed in ((5, 0, 5), (8.5, 1.5, 5.5), (10, 0, 7), (11.5, 0.5, 7.5), (12, 0, 8)):
        env = trajectory.env_at(at)
        assert env['service.stock'] == pytest.approx(remaining, abs=1e-8)
        assert env['service.served'] == pytest.approx(consumed, abs=1e-8)
        assert env['service.warehouse'] + env['service.stock'] + env['service.served'] == pytest.approx(
            25, abs=1e-10
        )
        assert env['service.untouched'] == 1e-28
        expected = 20 * math.exp(-0.25 * (-math.expm1(-at)))
        assert env['service.clinical_pending'] == pytest.approx(expected, rel=1e-8)
        assert env['service.clinical_pending'] + env['service.clinical_recovered'] == pytest.approx(
            20, abs=1e-10
        )
    corrections = [
        d
        for d in trajectory.diagnostics
        if d.get('code') == 'boundary_roundoff'
        and d.get('state') == 'service.stock'
        and d.get('delta', 0) < 0
    ]
    assert len(corrections) >= 2
    assert all(d['balancing_state'] == 'service.served' for d in corrections)


def numerical_fixture(*members):
    """The boundary fixture without its supply, with `members` and a clinical cohort of 20 people that
    keeps the run on the numerical solver path."""
    return edit(
        boundary_fixture(),
        drop('service/supply'),
        member('service', *members, *clinical_cohort(20, 'clinical_pending / 4 h * exp(-t / 1 h)')),
        replace(CONSERVED, 'abs(warehouse + stock + served - n - 20 people) <= 1e-10 people'),
    )


@pytest.mark.parametrize('direction', ['stationary', 'draining', 'replenishing'])
def test_tiny_unhit_inventory_preserves_its_physical_rate(direction):
    # A flow out of the small inventory makes it a stock: a flow of nothing where it does not drain.
    unused = flow('small_use', move('small', None), 0)
    moving = {
        'stationary': (unused,),
        'draining': (flow('small_drain', 'small -> small_delivered', 'small_rate'),),
        'replenishing': (flow('small_supply', move(None, 'small'), '1e-30 people/h'), unused),
    }[direction]
    authored = edit(
        numerical_fixture(),
        member(
            'service',
            stock('small', '1e-28 people', size=100000000),
            stock('small_delivered', kind='tally', size=100000000),
            formula('small_rate', '1e-30 people/h if small > 0 else 0', 'people/h'),
            *moving,
            event('small_empty', 'small <= 0', 'state = "on"'),
        ),
    )
    model = compiled(authored)
    trajectory = simulate(model.resolve('a'), library())
    velocity = {'stationary': 0, 'draining': -1e-30, 'replenishing': 1e-30}[direction]
    for at in (0, 5, 8.5, 10, 11.5, 12):
        observed = trajectory.env_at(at)
        assert observed['service.small'] == pytest.approx(1e-28 + velocity * at, rel=1e-12, abs=1e-40)
        delivered = observed.get('service.small_delivered')
        if delivered is None:
            # A tally that starts at zero and that nothing changes or reads is left out of the run:
            # it reads zero.
            assert 'service.small_delivered' in model.left_out[()]['quantities']
            delivered = 0
        assert delivered == pytest.approx(1e-30 * at if direction == 'draining' else 0, rel=1e-12, abs=1e-40)
        assert observed['service.warehouse'] + observed['service.stock'] + observed[
            'service.served'
        ] == pytest.approx(25, abs=1e-10)
        expected_clinical = 20 * math.exp(-0.25 * (-math.expm1(-at)))
        assert observed['service.clinical_pending'] == pytest.approx(expected_clinical, rel=1e-8)
        assert observed['service.clinical_pending'] + observed['service.clinical_recovered'] == pytest.approx(
            20, abs=1e-10
        )
    assert trajectory.settings['integration_segments']
    assert all(
        item.get('state') != 'service.small'
        for item in trajectory.diagnostics
        if item.get('code') == 'boundary_roundoff'
    )


def test_positive_authored_threshold_retains_its_remaining_stock():
    authored = edit(
        numerical_fixture(),
        replace('1 people/h if stock > 0 else 0', '1 people/h if state is "on" else 0'),
        drop(*STOPS),
        member(
            'service',
            event(
                'stop',
                'stock <= 2 people',
                once=False,
                transition='state "on" -> "off"',
                doc='Retain two people',
            ),
        ),
    )
    _, trajectory = run(authored)
    assert fired(trajectory, 'service.stop')[0] == pytest.approx(3, abs=1e-8)
    for at in (1, 3, 6, 12):
        observed = trajectory.env_at(at)
        assert observed['service.stock'] == pytest.approx(max(2, 5 - at), abs=1e-8)
        assert observed['service.served'] == pytest.approx(min(3, at), abs=1e-8)
        assert observed['service.warehouse'] + observed['service.stock'] + observed[
            'service.served'
        ] == pytest.approx(25, abs=1e-10)
    assert all(
        item.get('state') != 'service.stock'
        for item in trajectory.diagnostics
        if item.get('code') == 'boundary_roundoff'
    )


def test_subtimestamp_authored_depletion_books_actual_delivered_quantity():
    authored = edit(
        monitored_activation(numerical_fixture()),
        replace('1 people/h if stock > 0 else 0', '1 people/h if stock > 0 and state is "on" else 0'),
        replace('- n - 20 people', '- 20 people'),
    )
    _, trajectory = run(authored)
    assert trajectory.env_at(24)['service.stock'] == 1e-28
    assert trajectory.env_at(24)['service.served'] == 0
    assert trajectory.env_at(49)['service.stock'] == 0
    assert trajectory.env_at(49)['service.served'] == 1e-28
    corrections = [
        entry
        for entry in trajectory.diagnostics
        if entry.get('code') == 'boundary_roundoff' and entry.get('state') == 'service.stock'
    ]
    assert len(corrections) == 1
    assert corrections[0]['t'] == 48
    assert corrections[0]['delta'] == -1e-28
    assert corrections[0]['balancing_state'] == 'service.served'
    assert corrections[0]['balancing_delta'] == 1e-28


@pytest.mark.parametrize('inventory', [1e-28, 5])
def test_empty_coupled_resource_preserves_positive_inventory(inventory):
    authored = edit(
        numerical_fixture(),
        replace('var stock: people = n', f'var stock: people = {inventory!r} people'),
        replace('- n - 20 people', f'- {20 + inventory!r} people'),
        # `empty` alone switches the service off: its transition is its change.
        drop('service/serve', *STOPS),
        member(
            'service',
            stock('required_resource', size=10),
            stock('resource_used', kind='tally', size=10),
            event('empty', 'stock <= 0', once=False, transition='state "on" -> "off"', doc='Empty'),
            # Delivery needs the resource: one flow moves people and the resource together.
            flow('complete_delivery', ['stock -> served', 'required_resource -> resource_used'], 'delivery'),
        ),
    )
    _, trajectory = run(authored)
    for at in (0, 5, 12):
        observed = trajectory.env_at(at)
        assert observed['service.stock'] == inventory
        assert (
            observed['service.served']
            == observed['service.required_resource']
            == observed['service.resource_used']
            == 0
        )
    assert all(
        entry.get('state') != 'service.stock'
        for entry in trajectory.diagnostics
        if entry.get('code') == 'boundary_roundoff'
    )


def test_large_positive_depletion_residue_produces_numerical_failure(monkeypatch):
    import napkin.engine.continuous.integrate as integrate

    rs = resolved(numerical_fixture())
    indices = {name: position for position, name in enumerate(rs.quantities)}
    stock_row, served_row = indices['service.stock'], indices['service.served']
    original = integrate.radau
    injected = []

    def corrupt_located_boundary(fun, interval, initial, **kwargs):
        solution = original(fun, interval, initial, **kwargs)
        # The fixture drains exactly one person/hour, so a completed smooth
        # segment of this duration ends at physical depletion, including a
        # certified depletion clock that reaches the root directly.
        if (
            solution.success
            and initial[stock_row] > 0
            and abs(solution.t[-1] - interval[0] - initial[stock_row]) <= 1e-8
            and abs(solution.y[stock_row, -1]) <= 1e-8
        ):
            delta = 1e-3 - solution.y[stock_row, -1]
            solution.y[stock_row, -1] += delta
            solution.y[served_row, -1] -= delta
            injected.append(float(solution.t[-1]))
        return solution

    monkeypatch.setattr(integrate, 'radau', corrupt_located_boundary)
    with pytest.raises(SimulationError, match=r'Material state-bound violation for service\.stock'):
        simulate(rs, library(), NumericalSettings())
    assert injected
