"""A physical net on a held face cannot select the outgoing branch of a moving field."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import use_method
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
