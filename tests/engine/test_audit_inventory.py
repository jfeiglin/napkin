"""Hand-worked inventory and solver ownership findings from the readiness audit of 6f297e5."""

from __future__ import annotations

import math
import textwrap
from fractions import Fraction

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, resume, selection
from napkin.model.compile import compile_text
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    constraint,
    endpoint,
    event,
    flow,
    formula,
    given,
    input_,
    local,
    move,
    param,
    q,
    route,
    solve_for,
    solver,
    start,
    t,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.config import Configuration, InputValue, Quantity, Request
from napkin.program.record import Key
from tests.program.examples import UNITS
from tests.reference.from_program import run_of, value_at


def retired(*, leak='0', move=None, against=False, split=False, scale=None):
    """A physical stock with one litre as its own scale, retired empty at 0.5 h."""
    sources = ['flow leak: this.water -> job.batch', '    request = 0 L/h']
    actions = [f'leak.request = {leak} L/h']
    if against:
        sources.extend(('flow returned: job.batch -> this.water', '    request = 0 L/h'))
        actions.append(f'returned.request = {leak} L/h')
    if move is not None:
        actions.extend([f'move {move} L from this.water to job.batch'] * 100)
    watch = ['job = this.retire.occurrences.at(t)', *sources, 'after 0.5 h:']
    watch.extend(f'    {line}' for line in actions)
    if split:
        watch.extend(['after 0.25 h'] * 12)
    watch.append('after 1000 h')
    text = textwrap.dedent("""\
        scenario "Retired stock"
            horizon 1001 h
        plant:
            water: L = 100 L in [0,]
            retire = event():
                batch: L = 0 L in [0, 1000000000 L]
                after 0.5 h
            watch = event():
        """)
    if scale is not None:
        text = text.replace('1000000000 L]', f'1000000000 L] scale {scale} L')
    return compile_text(
        text
        + textwrap.indent('\n'.join(watch), '        ')
        + '\nplant.retire.start()\nplant.watch.start()\n',
        UNITS,
    )


def test_finished_stock_rejects_an_authored_nonzero_move():
    """100 moves would put 2 L in a finished batch. The first one fails without moving anything."""
    compiled = retired(move='0.02')
    record = run(compiled.program, compiled.configuration)
    assert record.failure is not None and record.failure.t == 0.5
    assert 'plant.retire#0.batch belongs to the finished occurrence' in record.failure.detail('message')
    assert record.entries('move') == ()
    oracle, error = run_of(compiled.program, compiled.configuration)
    assert oracle.view.t == Fraction(1, 2)
    assert 'plant.retire#0.batch belongs to the finished occurrence' in str(error)


@pytest.mark.parametrize(
    'rate,split,against',
    [
        ('0.02', False, False),
        ('0.0000000001', True, False),
        ('0.0000000001', True, True),
        ('0.00000000000000001', False, False),
    ],
)
def test_finished_stock_limits_cumulative_computed_transfer(rate, split, against):
    """The allowance is 1e-10 L. 0.02 L/h would add 20 L; even balanced pipes transfer material."""
    compiled = retired(leak=rate, split=split, against=against)
    record = run(compiled.program, compiled.configuration)
    oracle, error = run_of(compiled.program, compiled.configuration)
    if Fraction(rate) * 1000 < Fraction(1, 10**10):
        assert record.failure is None and error is None
        return
    expected = 0.5 + float(Fraction(1, 10**10) / Fraction(rate))
    assert record.failure is not None, record.end
    assert record.failure.t == pytest.approx(expected, abs=1e-8, rel=0)
    assert 'plant.retire#0.batch belongs to the finished occurrence' in record.failure.detail('message')
    assert error is not None and float(oracle.view.t) == pytest.approx(expected, abs=1e-8, rel=0)
    if split:
        live = Run(Plan.of(compiled.program, compiled.configuration), (Breakpoint('plant.watch.step[1]'),))
        stopped = live.run()
        assert isinstance(stopped, Checkpoint)
        assert live.resume() == resume(compiled.program, stopped) == record


@pytest.mark.parametrize(
    'amount_unit,rate_unit,large_unit,factor', [('L', 'L/h', 'L/h', 1000000), ('Wh', 'W', 'MW', 1)]
)
def test_publishing_an_idle_route_preserves_its_stock(amount_unit, rate_unit, large_unit, factor):
    """The main request gets its capacity of 10 million. The last row then allows an idle
    flow of up to 1. Its target is zero and zero is feasible, so no inventory leaves the stock."""
    units = {**UNITS, 'MW': ({'energy': 1, 'time': -1}, 1000000)}
    b = Builder(units)
    stock = b.entity('stock', value('water', amount_unit, 10, lower=0))
    receiver = b.entity('receiver', value('water', amount_unit, 10, lower=0))
    pipes = b.entity(
        'pipes',
        flow(
            'supply',
            SOURCE,
            receiver.water,
            request=q(30 * factor, large_unit),
            capacity=q(10 * factor, large_unit),
        ),
        route('idle', stock.water, receiver.water),
    )
    b.entity(
        'provider',
        solver(
            'dispatch',
            given('supply', pipes.supply),
            given('idle', pipes.idle),
            solve_for(local.supply.actual_rate),
            solve_for(local.idle.actual_rate),
            constraint(
                10_000_000 * (local.supply.actual_rate - q(10 * factor, large_unit)) + local.idle.actual_rate
                <= q(1, rate_unit)
            ),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    idle, stock = read(record, program, ['pipes.idle.actual_rate', 'stock.water'], [0, 1])
    assert idle.values == (0, 0)
    assert stock.values == (10, 10)


def test_local_sharing_keeps_an_idle_rate_zero_beside_a_large_unserved_request():
    """For targets (30 million, 0), a cap of 10 million on the first fixes the nearest answer
    at (10 million, 0). The first delivery stays put, so 1 on the second worsens the distance."""
    rows = selection.Rows(2)
    lower, upper = np.zeros(2), np.array([10_000_000, np.inf])
    target = np.array([30_000_000, 0])
    answer = np.array([10_000_000, 0])
    candidate = np.array([10_000_000, 1])
    kept = selection._kept(rows, lower, upper, target, [], answer, (candidate,))
    assert kept.tolist() == [10_000_000, 0]


def test_declared_solver_shares_two_source_to_sink_flows():
    """Each pipe gets 8/2 L/h. A third, unowned boundary pipe gets its own 3 L/h."""
    b = Builder(UNITS)
    pipes = b.entity(
        'pipes',
        *(
            flow(name, SOURCE, SINK, request=q(wanted, 'L/h'), unit='L/h')
            for name, wanted in [('one', 6), ('two', 6), ('free', 3)]
        ),
    )
    b.entity(
        'provider',
        solver(
            'dispatch',
            given('one', pipes.one),
            given('two', pipes.two),
            solve_for(local.one.actual_rate),
            solve_for(local.two.actual_rate),
            constraint(local.one.actual_rate + local.two.actual_rate <= q(8, 'L/h')),
        ),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    assert [
        r.values
        for r in read(
            record, program, [f'pipes.{name}.actual_rate' for name in ('one', 'two', 'free')], [0, 1]
        )
    ] == [(4, 4), (4, 4), (3, 3)]
    oracle, error = run_of(program, Configuration(Request(1)))
    assert error is None
    for name, expected in [('one', 4), ('two', 4), ('free', 3)]:
        assert value_at(oracle, program, Key('pipes', (name, 'actual_rate')), 1) == expected


@pytest.mark.parametrize('upper', ['100 L', '1000000000 L'])
def test_a_live_move_keeps_its_amount_when_an_upper_bound_is_large(upper):
    """A 0.02 L move from 0.04 L leaves 0.02 L, whatever else the store could hold."""
    compiled = compile_text(
        textwrap.dedent(f"""\
            scenario "Stock move"
                horizon 1 h
            plant:
                source: L = 0.04 L in [0, {upper}]
                basin: L = 0 L in [0,]
                transfer = event():
                    after 1 h:
                        move 0.02 L from this.source to this.basin
            plant.transfer.start()
        """),
        UNITS,
    )
    record = run(compiled.program, compiled.configuration)
    assert [s.values for s in read(record, compiled.program, ['plant.source', 'plant.basin'], [1])] == [
        (0.02,),
        (0.02,),
    ]


@pytest.mark.parametrize('declared', [False, True], ids=['sparse', 'moving-declared'])
def test_a_small_inward_rate_releases_an_empty_store_with_a_large_upper_bound(declared):
    """For an empty tank with input p + V/(1 h), V(t) = p × (exp(t) − 1) in litres."""
    b = Builder(UNITS)
    initial_rate = 2e-8 if declared else 0.02
    tank = b.entity(
        'tank',
        value('water', 'L', 0, lower=0, upper=1_000_000_000, inflow=endpoint(capacity=q(1, 'L/h'))),
        flow('fill', SOURCE, this.water, request=formula(q(initial_rate, 'L/h') + this.water / q(1, 'h'))),
    )
    if declared:
        b.entity('provider', solver('dispatch', given('fill', tank.fill), solve_for(local.fill.actual_rate)))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    assert read(record, program, ['tank.water'], [0.5, 1])[0].values == pytest.approx(
        tuple(initial_rate * math.expm1(t) for t in (0.5, 1)), rel=5e-4, abs=0
    )


def test_authored_zero_move_into_a_finished_stock_transfers_nothing():
    """A source that has only 0.02 L in a billion-litre tank cannot turn a zero move into a transfer."""
    model = compile_text(
        textwrap.dedent("""\
        scenario "A move of zero"
            horizon 1 h
        plant:
            water: L = 0.02 L in [0, 1000000000 L]
            retire = event():
                batch: L = 0 L in [0, 1000000000 L]
                after 0.5 h
            transfer = event():
                job = this.retire.occurrences.at(t)
                after 1 h:
                    move 0 L from this.water to job.batch
        plant.retire.start()
        plant.transfer.start()
    """),
        UNITS,
    )
    record = run(model.program, model.configuration)
    assert record.failure is None
    assert record.entries('move')[0].detail('amount') == 0
    assert [s.values for s in read(record, model.program, ['plant.water', 'plant.retire#0.batch'], [1])] == [
        (0.02,),
        (0,),
    ]


@pytest.mark.deep
@pytest.mark.parametrize('rate_power', range(-3, 7))
@pytest.mark.parametrize('scale_power', [-3, 0, 3])
def test_frozen_inventory_uses_its_declared_amount_scale_over_time(rate_power, scale_power):
    """A constant leak reaches the store's own allowance at t₀ + 10⁻¹⁰ scale/rate hours."""
    scale = Fraction(10) ** scale_power
    rate = Fraction(10) ** rate_power
    compiled = retired(leak=str(float(rate)), scale=str(float(scale)), against=True)
    record = run(compiled.program, compiled.configuration)
    oracle, error = run_of(compiled.program, compiled.configuration)
    reached = Fraction(1, 2) + Fraction(1, 10**10) * scale / rate
    assert record.failure is not None and error is not None
    assert record.failure.t == pytest.approx(float(reached), abs=1e-12, rel=0)
    assert oracle.view.t == reached


def test_a_store_range_inverted_within_the_band_is_a_single_physical_point():
    """The authored ends fit the 1e-9 L band. Their midpoint is the feasible physical inventory."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('lo', 'L', 0.3000000006),
        value('hi', 'L', 0.3),
        value('water', 'L', 0.3, lower=this.lo, upper=this.hi),
        flow('fill', SOURCE, this.water, request=q(0, 'L/h')),
    )
    program = b.finish()
    config = Configuration(Request(1))
    record = run(program, config)
    oracle, error = run_of(program, config)
    assert record.failure is None and error is None
    expected = Fraction('0.3000000003')
    key = Key('plant', ('water',))
    assert read(record, program, [key], [0, 1])[0].values == pytest.approx(
        (float(expected),) * 2, abs=1e-15, rel=0
    )
    assert value_at(oracle, program, key, 1) == expected


@pytest.mark.parametrize('sharing', ['component', 'sparse', 'declared'])
def test_small_curved_delivery_keeps_its_shape_beside_a_large_store_bound(sharing):
    """A request of 0.001 t² L/h delivers 0.00025 L/h at half an hour and cumulatively t³/3000 L."""
    b = Builder(UNITS)
    hours = t / q(1, 'h')
    cap = endpoint(capacity=q(1, 'L/h')) if sharing == 'sparse' else None
    tank = b.entity(
        'tank',
        value('water', 'L', 0, lower=0, upper=1_000_000_000, inflow=cap),
        flow('fill', SOURCE, this.water, request=formula(q(0.001, 'L/h') * hours * hours)),
    )
    if sharing == 'declared':
        b.entity('provider', solver('dispatch', given('fill', tank.fill), solve_for(local.fill.actual_rate)))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    fill, stock = read(record, program, ['tank.fill.actual_rate', 'tank.water'], [0.5, 1])
    assert fill.values == pytest.approx((0.00025, 0.001), abs=1e-10, rel=0)
    assert stock.values == pytest.approx((1 / 24_000, 1 / 3_000), abs=1e-10, rel=0)


def test_fitted_formula_in_picolitres_keeps_its_declared_scale():
    """A record of t² pL gives a quarter picolitre halfway through a one-hour window."""
    b = Builder({**UNITS, 'pL': ({'volume': 1}, Fraction(1, 10**12))})
    hours = t / q(1, 'h')
    b.entity('lab', value('sample', 'pL', formula(q(1, 'pL') * hours * hours)))
    program = b.finish()
    key = Key('lab', ('sample',))
    config = Configuration(Request(1, False, (key,)))
    record = run(program, config)
    assert record.failure is None
    assert record.value(key, 0.5) == pytest.approx(0.25e-12, rel=1e-9, abs=0)


@pytest.mark.parametrize('entry', ['configured input', 'event argument'])
def test_numeric_entry_inside_its_range_comparison_band_is_admitted(entry):
    """0.3000000006 L is within 1e−9 L of 0.3 L, so the argument is admitted as given."""
    b = Builder(UNITS)
    entered = Fraction('0.3000000006')
    if entry == 'event argument':
        tank = b.entity('tank', event('take', param('limit', 'L', upper=q(0.3, 'L')), after(q(2, 'h'))))
        b.setup(start(tank.take, q(float(entered), 'L')))
        key = Key('tank.take#0', ('limit',))
        config = Configuration(Request(1))
    else:
        b.entity('tank', input_('limit', 'L', 0, upper=0.3))
        key = Key('tank', ('limit',))
        config = Configuration(
            Request(1), inputs=(InputValue('tank', 'limit', Quantity(float(entered), 'L')),)
        )
    program = b.finish()
    record = run(program, config)
    assert record.failure is None
    oracle, error = run_of(program, config)
    assert error is None
    assert read(record, program, [key], [1])[0].values == (float(entered),)
    assert value_at(oracle, program, key, 1) == entered


@pytest.mark.parametrize(
    'initial_src, floor, initial_dst, ceiling, amount, fits',
    [
        (1, 0, 1_000_000_000, 1_000_000_000, '0.02', False),
        (1_000_000_000, 1_000_000_000, 0, 1, '0.02', False),
        (1, 0, 999_999_999.99, 1_000_000_000, '0.02', False),
        (1_000_000_000.01, 1_000_000_000, 0, 1, '0.02', False),
        (1_000_000_000, 0, 0, 1_000_000_000, '1000000000', True),
        (1_000_000_000.02, 1_000_000_000, 999_999_999.98, 1_000_000_000, '0.02', True),
    ],
    ids=[
        'full destination',
        'empty source',
        'short room',
        'short supply',
        'full transfer',
        'subtraction roundoff',
    ],
)
def test_a_bounded_move_preserves_both_inventories(initial_src, floor, initial_dst, ceiling, amount, fits):
    """A move needs both stock and room. Where either is short the entire stage is discarded.
    Where subtraction loses digits near a billion, the authored transfer exactly fills the room."""
    b = Builder(UNITS)
    tank = b.entity(
        'yard',
        value('source', 'L', initial_src, lower=floor),
        value('destination', 'L', initial_dst, upper=ceiling),
        event('send', after(q(1, 'h'), move(q(float(amount), 'L'), this.source, this.destination))),
    )
    b.setup(start(tank.send))
    program, config = b.finish(), Configuration(Request(1))
    record = run(program, config)
    oracle, error = run_of(program, config)
    assert (record.failure is None) == (error is None) == fits
    if not fits:
        assert 'nothing is moved' in record.failure.detail('message')
        assert not record.entries('move')
    else:
        assert record.entries('move')[0].detail('amount') == float(amount)
    transferred = Fraction(amount) if fits else 0
    expected = [Fraction(str(initial_src)) - transferred, Fraction(str(initial_dst)) + transferred]
    for field, left in zip(('source', 'destination'), expected):
        key = Key('yard', (field,))
        assert value_at(oracle, program, key, 1) == left
        assert read(record, program, [key], [1])[0].values == (float(left),)


def test_seven_moves_empty_their_source_across_a_checkpoint():
    """Seven moves of 10/7 L transfer exactly 10 L. Subtracting the first six in floats
    leaves less than the last request; the accumulated arithmetic allows that final transfer."""
    b = Builder(UNITS)
    amount = q(10, 'L') / 7
    yard = b.entity(
        'yard',
        value('supply', 'L', 10, lower=0),
        value('sink', 'L', 0, lower=0),
        event('empty', *(after(q(1, 'h'), move(amount, this.supply, this.sink)) for _ in range(7))),
    )
    b.setup(start(yard.empty))
    program, config = b.finish(), Configuration(Request(7))
    record = run(program, config)
    assert record.failure is None
    assert read(record, program, ['yard.supply', 'yard.sink'], [7])[0].values == (0,)
    assert read(record, program, ['yard.sink'], [7])[0].values == pytest.approx(
        (10,), abs=7 * math.ulp(10), rel=0
    )
    live = Run(Plan.of(program, config), (Breakpoint('yard.empty.step[6]'),))
    stopped = live.run()
    assert isinstance(stopped, Checkpoint)
    assert live.resume() == resume(program, stopped) == record


def test_a_positive_shortage_in_the_first_move_is_not_cumulative_roundoff():
    """0.01000000000001 L exceeds the authored 0.01 L in an untouched store, by many ulps."""
    b = Builder(UNITS)
    yard = b.entity(
        'yard',
        value('supply', 'L', 0.01, lower=0, scale=1_000_000_000),
        value('sink', 'L', 0, lower=0),
        event('empty', after(q(1, 'h'), move(q(0.01000000000001, 'L'), this.supply, this.sink))),
    )
    b.setup(start(yard.empty))
    program, config = b.finish(), Configuration(Request(1))
    record = run(program, config)
    assert record.failure is not None and not record.entries('move')
