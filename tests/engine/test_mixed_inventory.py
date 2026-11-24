"""A single transfer debits and credits one amount, even across large changes of inventory."""

import math
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, resume
from napkin.model.compile import compile_text
from napkin.program.build import (
    SOURCE,
    Builder,
    after,
    assign,
    event,
    flow,
    ifelse,
    move,
    q,
    start,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Numerics, Request
from tests.engine.resume_parity import assert_resume_parity
from tests.engine.test_round_rate_reads import SETTING, check, model
from tests.program.examples import UNITS
from tests.reference.from_program import run_of


def cycle(bulk, deposit, count, excess=0):
    total = float(Fraction(str(deposit)) * count)
    b = Builder(UNITS)
    steps = [
        after(q(1, 'h'), *(move(q(deposit, 'L'), this.cash, this.tank) for _ in range(count))),
        after(q(1, 'h'), move(q(bulk, 'L'), this.tank, this.bulk)),
        after(q(1, 'h'), move(q(total, 'L'), this.tank, this.refund)),
    ]
    if excess:
        steps.append(after(q(1, 'h'), move(q(excess, 'L'), this.tank, this.refund)))
    yard = b.entity(
        'yard',
        value('cash', 'L', total, lower=0),
        value('tank', 'L', bulk, lower=0),
        value('bulk', 'L', 0),
        value('refund', 'L', 0),
        event('cycle', *steps),
    )
    b.setup(start(yard.cycle))
    return b.finish(), Configuration(Request(len(steps)))


def test_fifty_millilitres_can_be_refunded_after_a_four_million_litre_withdrawal():
    program, config = cycle(4_000_000, 0.05, 1)
    record = run(program, config)
    assert record.failure is None, record.failure
    tank, refund = read(record, program, ['yard.tank', 'yard.refund'], [2, 3])
    assert tank.values == pytest.approx((0.05, 0), abs=3e-10, rel=0)
    assert refund.values == pytest.approx((0, 0.05), abs=3e-10, rel=0)
    assert refund.values[-1] == record.entries('move')[-1].detail('amount')
    stopped = Run(Plan.of(program, config), (Breakpoint('yard.cycle.step[1]'),))
    checkpoint = stopped.run()
    assert isinstance(checkpoint, Checkpoint)
    assert_resume_parity(program, config, record, stopped.resume())
    assert_resume_parity(program, config, record, resume(program, loads(dumps(checkpoint))))


@pytest.mark.parametrize('deposit,count', [(0.001, 1000), (0.05, 100)])
def test_repeated_small_deposits_pay_the_refund_and_leave_no_extra_inventory(deposit, count):
    """1,000 mL make exactly 1 L. One hundred 50 mL deposits make exactly 5 L."""
    program, config = cycle(4_000_000, deposit, count, excess=1e-7)
    record = run(program, config)
    assert record.failure is not None and record.failure.t == 4, record.failure
    assert 'nothing is moved' in record.failure.detail('message')
    tank, refund = read(record, program, ['yard.tank', 'yard.refund'], [3])
    assert tank.values == (0,)
    assert refund.values == pytest.approx((deposit * count,), abs=1e-14, rel=0)


def test_ten_authored_tenths_pay_a_whole_lot_using_the_stages_selected_branch():
    """A 0.14 L lot split into ten 0.014 L transfers leaves exactly zero.
    At the requested precision the two flags compare equal, so no transfer reads 1/0."""
    b = Builder(UNITS)
    share = ifelse(this.flag > 1, this.lot / 0, this.lot * 0.1)
    yard = b.entity(
        'yard',
        value('lot', 'L', 0.14),
        value('cash', 'L', 0.14, lower=0),
        value('paid', 'L', 0),
        value('flag', '', 1.00000001),
        event('pay', after(q(1, 'h'), *(move(share, this.cash, this.paid) for _ in range(10)))),
    )
    b.setup(start(yard.pay))
    program = b.finish()
    record = run(program, Configuration(Request(1), numerics=Numerics(rtol=1e-6)))
    assert record.failure is None, record.failure
    assert [row.values for row in read(record, program, ['yard.cash', 'yard.paid'], [1])] == [(0,), (0.14,)]
    assert [entry.detail('amount') for entry in record.entries('move')] == [0.014] * 10


def frozen_flow(request, scale, split):
    pause = f'        after {split} h\n' if split else ''
    model = compile_text(
        'scenario "Cumulative transfer"\n    horizon 6 h\n'
        'plant:\n    water: L = 10 L in [0,]\n'
        f'    retire = event():\n        batch: L = 0 L in [0,] scale {scale} L\n        after 1 h\n'
        '    watch = event():\n        job = this.retire.occurrences.at(t)\n'
        '        flow leak: this.water -> job.batch\n            request = 0 L/h\n'
        f'        after 1 h:\n            leak.request = {request}\n'
        + pause
        + '        after 6 h\nplant.retire.start()\nplant.watch.start()\n',
        UNITS,
    )
    record = run(model.program, model.configuration)
    if split:
        paused = Run(Plan.of(model.program, model.configuration), (Breakpoint('plant.watch.step[1]'),))
        checkpoint = paused.run()
        assert isinstance(checkpoint, Checkpoint)
        assert_resume_parity(model.program, model.configuration, record, paused.resume())
        assert_resume_parity(
            model.program, model.configuration, record, resume(model.program, loads(dumps(checkpoint)))
        )
    return model, record


@pytest.mark.parametrize('split', [None, '0.3', '0.6'])
@pytest.mark.parametrize('moving', [False, True], ids=['constant', 'rising'])
@pytest.mark.parametrize(
    'rate,scale',
    [
        ('0.019999', '1000000000'),
        ('0.02', '1000000000'),
        ('0.020001', '1000000000'),
        ('0.02000000000000022', '1000000000'),
        ('0.00000000000142', '0.071'),
    ],
)
def test_exactly_the_retired_stocks_allowance_can_pass_at_the_horizon(rate, scale, moving, split):
    """A stock retires at 1 h, then receives five hours of flow. Its cumulative allowance is scale × 1e-10."""
    request = f'{rate} L/h'
    if moving:
        # A linear ramp from zero to twice the mean transfers the same five-hour total.
        request = f'formula({request} * (t - 1 h) / (2.5 h))'
    model, record = frozen_flow(request, scale, split)
    oracle, error = run_of(model.program, model.configuration)
    allowance = Fraction(scale) / 10**10
    if Fraction(rate) * 5 <= allowance:
        assert error is None
        assert record.failure is None, record.failure
    else:
        elapsed = allowance / Fraction(rate)
        at = 1 + ((5 * elapsed) ** 0.5 if moving else elapsed)
        assert error is not None and float(oracle.view.t) == pytest.approx(float(at), abs=1e-9)
        assert record.failure is not None and record.failure.t == pytest.approx(float(at), abs=1e-9)


@pytest.mark.parametrize('split', [None, '1', '1.2', '4.6', '4.7'])
@pytest.mark.parametrize(
    'mean', [repr(math.nextafter(0.02, 0)), '0.02', repr(math.nextafter(0.02, 1)), '0.02000000000000022']
)
def test_a_curved_retired_flow_compares_its_total_once(mean, split):
    # Integrating 3*r*(elapsed/5)^2 over five hours gives 5*r.
    request = f'formula(3 * {mean} L/h * ((t - 1 h) / (5 h)) ** 2)'
    _, record = frozen_flow(request, '1000000000', split)
    amount = 5 * Fraction(mean)
    if amount <= Fraction(1, 10):
        assert record.failure is None, record.failure
    else:
        at = 1 + float(Fraction(25, 10) / Fraction(mean)) ** (1 / 3)
        assert record.failure is not None and record.failure.t == pytest.approx(at, abs=1e-9)


@pytest.mark.parametrize(
    'seed', [*range(8), *[pytest.param(k, marks=pytest.mark.deep) for k in range(8, 64)]]
)
def test_mixed_magnitudes_conserve_inventory_in_the_generated_round(seed):
    program, answers, initial = model('move', seed, mixed_amounts=True)
    check(program, 3, answers)
    check(program, 3, answers, (SETTING, initial + 1))


@pytest.mark.parametrize('replace_balance', [False, True], ids=['resume', 'explicit-edit'])
def test_a_hidden_fraction_of_a_deposit_survives_resume_until_the_balance_is_replaced(replace_balance):
    """The large reported balance rounds away 1e-10 L. An explicit replacement owns its new value."""
    program, config = cycle(10_000_000, 0.0010000001, 1)
    live = Run(Plan.of(program, config), (Breakpoint('yard.cycle.step[1]'),))
    checkpoint = live.run()
    assert isinstance(checkpoint, Checkpoint)
    if replace_balance:
        checkpoint = live.edit('yard.tank', 10_000_000.001)
    record = live.resume()
    assert_resume_parity(program, config, record, resume(program, loads(dumps(checkpoint))))
    if replace_balance:
        assert record.failure is not None and record.failure.t == 3
        assert record.entries('move')[-1].detail('amount') == 10_000_000
    else:
        assert record.failure is None
        assert record.entries('move')[-1].detail('amount') == 0.0010000001


@pytest.mark.parametrize('bounded', [False, True], ids=['moving', 'reaches-upper-bound'])
def test_a_small_deposit_survives_continuous_flow_until_the_stock_reaches_a_bound(bounded):
    """A deposit's last digits are smaller than one ulp of this tank. One litre of continuous
    supply leaves the deposit after the bulk is withdrawn. An upper bound instead stops the supply
    when the tank is exactly full, so withdrawing its capacity must leave exactly zero."""
    deposit = Fraction('0.0010000003')
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10_000_000, lower=0, upper=10_000_001 if bounded else None),
        value('cash', 'L', q(deposit, 'L'), lower=0),
        value('bulk', 'L', 0),
        value('refund', 'L', 0),
        flow('fill', SOURCE, this.water, request=q(0, 'L/h')),
        event(
            'cycle',
            after(
                q(1, 'h'),
                move(q(deposit, 'L'), this.cash, this.water),
                assign(this.fill.request, q(1, 'L/h')),
            ),
            after(
                q(1, 'h'),
                assign(this.fill.request, q(0, 'L/h')),
                move(q(10_000_001, 'L'), this.water, this.bulk),
            ),
            after(
                q(1, 'h'),
                move(q(Fraction('0.0000000003') if bounded else deposit, 'L'), this.water, this.refund),
            ),
        ),
    )
    b.setup(start(tank.cycle))
    program, config = b.finish(), Configuration(Request(3))
    record = run(program, config)
    _, error = run_of(program, config)
    if bounded:
        assert error is not None
        assert record.failure is not None and record.failure.t == 3
        assert 'nothing is moved' in record.failure.detail('message')
        assert read(record, program, ['tank.water'], [2])[0].values == (0,)
    else:
        assert error is None
        assert record.failure is None, record.failure
        assert read(record, program, ['tank.water'], [2, 3])[0].values == (float(deposit), 0)
        assert record.entries('move')[-1].detail('amount') == float(deposit)


def test_a_failed_stage_discards_its_mixed_magnitude_transfers():
    """The second debit is 1 mL short. The earlier deposit in the same stage is discarded."""
    b = Builder(UNITS)
    yard = b.entity(
        'yard',
        value('cash', 'L', 1, lower=0),
        value('tank', 'L', 10_000_000, lower=0),
        event(
            'cycle',
            after(
                q(1, 'h'),
                move(q(0.0010000001, 'L'), this.cash, this.tank),
                move(q(1, 'L'), this.cash, this.tank),
            ),
        ),
    )
    b.setup(start(yard.cycle))
    program, config = b.finish(), Configuration(Request(1))
    record = run(program, config)
    assert record.failure is not None
    assert record.entries('move') == ()
    cash, tank = read(record, program, ['yard.cash', 'yard.tank'], [1])
    assert (cash.values, tank.values) == ((1,), (10_000_000,))
