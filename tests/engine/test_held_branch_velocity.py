"""A physical net on a held face cannot select the outgoing branch of a moving field."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import UNITS, use_method
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize('cut', [False, True], ids=['direct', 'empty-event'])
@pytest.mark.parametrize('leaves', [False, True], ids=['held', 'released'])
def test_branch_obeys_the_release_decision_while_the_stock_books_both_legs(method, cut, leaves, monkeypatch):
    inlet, outlet = ('0.501', '0.499') if leaves else ('0.5000000000005', '0.4999999999995')
    text = f"""scenario "A counter follows a stock"
    horizon 1 h
yard:
    stock: L = 0 L in [0, 1 L]
    measured: L = 0 L
    flow feed: SOURCE -> this.stock
        request = {inlet} L/h
        capacity = {inlet} L/h
    flow drain: this.stock -> SINK
        request = {outlet} L/h
        capacity = {outlet} L/h
    flow meter: SOURCE -> this.measured
        request = formula(2 L/h if this.stock > 0 L else 1 L/h)
        capacity = formula(2 L/h if this.stock > 0 L else 1 L/h)
"""
    if cut:
        text += """    inspect = event():
        after 0.25 h
yard.inspect.start()
"""
    model = use_method(text, method, monkeypatch, 'feed')
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None and record.end == 1
    way = machine.ways.instance_of('yard.meter')
    assert (
        type(way).__name__
        == {
            'component': 'ComponentWay',
            'sparse': 'Sparse',
            'moving_declared': 'MovingDeclared',
        }[method]
    )
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and oracle.view.t == 1
    rate = 2 if leaves else 1
    net = Fraction(inlet) - Fraction(outlet)
    times = (0, 0.25, 0.5, 1)
    stock, measured, actual = read(
        record, model.program, ['yard.stock', 'yard.measured', 'yard.meter.actual_rate'], times
    )
    assert actual.values == pytest.approx([rate] * len(times))
    assert measured.values == pytest.approx([rate * t for t in times], abs=2e-13)
    if cut:
        paused = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.inspect.step[0]'),))
        checkpoint = paused.run()
        assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 0.25
        resumed = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(checkpoint))).resume()
        assert resumed.end == record.end and resumed.failure is None
        books, counts, rates = read(
            resumed, model.program, ['yard.stock', 'yard.measured', 'yard.meter.actual_rate'], times
        )
        assert books.values == pytest.approx(stock.values, rel=0, abs=2e-15)
        assert counts.values == pytest.approx(measured.values, rel=0, abs=2e-13)
        assert rates.values == pytest.approx(actual.values)
    physical = machine.ways.instance_of('yard.stock')
    received = physical.transferred('yard.feed', 1) - physical.transferred('yard.drain', 1)
    assert float(received) == pytest.approx(stock.values[-1], rel=0, abs=2e-15)
    for t, level in zip(times[1:], stock.values[1:]):
        assert 0 < level < float(net * t) + 2e-15
        assert value_at(oracle, model.program, Key('yard', ('stock',)), Fraction(t)) == net * Fraction(t)
        assert value_at(oracle, model.program, Key('yard', ('measured',)), Fraction(t)) == rate * Fraction(t)


@pytest.mark.parametrize('method', ['sparse', 'moving_declared'])
@pytest.mark.parametrize('leaves', [False, True], ids=['held', 'released'])
def test_a_held_member_key_keeps_its_rank_at_an_empty_event(method, leaves, monkeypatch):
    inlet, outlet = ('0.501', '0.499') if leaves else ('0.5000000000005', '0.4999999999995')
    text = f"""scenario "Two eligible counter keys"
    horizon 1 h
Bin:
    input into = 0 L/h
    input out = 0 L/h
    input price = 1 L/h
    level: L = 0 L in [0, 1 L]
    flow feed: SOURCE -> this.level
        request = this.into
        capacity = this.into
    flow drain: this.level -> SINK
        request = this.out
        capacity = this.out
changing: Bin
    into = {inlet} L/h
    out = {outlet} L/h
    price = 2 L/h
stationary: Bin
yard:
    measured: L = 0 L
    flow meter: SOURCE -> this.measured
        request = formula(Bin.instances.by(level).at(1 L).price)
    inspect = event():
        after 0.25 h
yard.inspect.start()
"""
    model = use_method(text, method, monkeypatch, 'meter')
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None and record.end == 1
    assert type(machine.ways.instance_of('yard.meter')).__name__ == (
        'Sparse' if method == 'sparse' else 'MovingDeclared'
    )
    oracle, error = run_of(model.program, model.configuration)
    assert error is None
    times = [0, 0.25, 0.5, 1]
    (amount,) = read(record, model.program, ['yard.measured'], times)
    rate = 2 if leaves else 1
    assert amount.values == pytest.approx([rate * t for t in times], abs=1e-12)
    key = Key('yard', ('measured',))
    assert [value_at(oracle, model.program, key, Fraction(t)) for t in times] == [rate * t for t in times]


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize('cut', [False, True], ids=['direct', 'restored'])
def test_a_retained_net_eventually_exits_the_comparison_band(method, cut, monkeypatch):
    # The two physical leg amounts differ by 1e-12 L/h on a 1 L comparison
    # scale. At 1,000 h the retained stock reaches the 1e-9 L band edge.
    text = """scenario "A counter following an accumulating balance"
    horizon 2000 h
yard:
    stock: L = 0 in [0, 1 L]
    count: L = 0
    flow feed: SOURCE -> this.stock
        request = 1 L/h
        capacity = 1 L/h
    flow drain: this.stock -> SINK
        request = 0.999999999999 L/h
        capacity = 0.999999999999 L/h
    flow meter: SOURCE -> this.count
        request = formula(2 L/h if this.stock > 0 L else 1 L/h)
        capacity = 3 L/h
"""
    if method == 'moving_declared':
        text += """    hard = solver:
        inputs:
            a = yard.feed
            b = yard.drain
        solve_for:
            a.actual_rate
            b.actual_rate
        constraints:
            a.actual_rate == 1 L/h
            b.actual_rate == 0.999999999999 L/h
"""
    if cut:
        text += """    inspect = event():
        after 377.25 h
yard.inspect.start()
"""
    if method == 'moving_declared':
        connect = Plan.connect

        def force(plan, *args, **kwargs):
            return [
                replace(g, moves=True) if g.way == 'declared' else g for g in connect(plan, *args, **kwargs)
            ]

        monkeypatch.setattr(Plan, 'connect', force)
        model = compile_text(text, UNITS)
    else:
        model = use_method(text, method, monkeypatch, 'feed')
    oracle, error = run_of(model.program, model.configuration)
    assert error is None
    times = (999, 1000, 1001, 2000)
    expected = [999, 1000, 1002, 3000]
    assert [value_at(oracle, model.program, Key('yard', ('count',)), t) for t in times] == expected
    plan = Plan.of(model.program, model.configuration)
    if cut:
        stop = Run(plan, (Breakpoint('yard.inspect.step[0]'),)).run()
        assert isinstance(stop, Checkpoint) and stop.stop.t == 377.25
        machine = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(stop)))
        record = machine.resume()
    else:
        machine = Run(plan)
        record = machine.run()
    assert record.failure is None and record.end == 2000
    level, counted, rates = read(
        record, model.program, ['yard.stock', 'yard.count', 'yard.meter.actual_rate'], times
    )
    assert (rates.values[0], *rates.values[2:]) == pytest.approx((1, 2, 2))
    # The clock float can be on either side of the numerically located edge;
    # a fit across both sides must not invent a third allocated rate.
    assert rates.values[1] in (1, 2)
    assert counted.values == pytest.approx(expected, rel=2e-9)
    giver = machine.ways.instance_of('yard.feed')
    incoming, outgoing = (giver.transferred('yard.' + name, 2000) for name in ('feed', 'drain'))
    assert incoming - outgoing == machine.stock_balance('yard.stock', 2000)
    assert level.values[-1] == float(incoming - outgoing)
    assert float(incoming) == pytest.approx(2000, rel=0, abs=1e-10)
    assert float(outgoing) == pytest.approx(2000 - 2e-9, rel=0, abs=1e-10)
