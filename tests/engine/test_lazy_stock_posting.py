"""Local events materialize their own inventories; endpoints share the retired physical prefix."""

from collections import Counter

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.family import Family
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.stocks import Stocks
from napkin.engine.timeline.way import Way
from napkin.program.build import SOURCE, Builder, after, event, flow, move, named, q, start, this, value
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.config import Configuration, Request
from tests.engine.test_threshold_transfer_placement import use_method

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


@pytest.mark.parametrize('method', [Family, Lines])
def test_held_stock_materialization_is_local_to_the_stage(method, monkeypatch):
    builder = Builder(UNITS)
    for i in range(96):
        legs = [flow('fill', SOURCE, this.water, request=q(1, 'L/h'))]
        if method is Lines:
            legs.append(flow('top_up', SOURCE, this.water, request=q(0.25, 'L/h')))
        builder.entity(f'tank{i}', value('water', 'L', 1, lower=0), *legs)
    bank = builder.entity(
        'bank',
        value('received', 'L', 0),
        event('idle', after(q(0.25, 'h'))),
        event('collect', after(q(0.5, 'h'), move(named('tank0').water, named('tank0').water, this.received))),
    )
    builder.setup(start(bank.idle), start(bank.collect))
    program = builder.finish()
    calls = []
    original = Run.post_stock

    def traced(machine, store, t, *args):
        advanced = original(machine, store, t, *args)
        if advanced:
            calls.append((t, store))
        return advanced

    monkeypatch.setattr(Run, 'post_stock', traced)
    machine = Run(Plan.of(program, Configuration(Request(1))))
    record = machine.run()
    assert record.failure is None
    assert isinstance(machine.ways.instance_of('tank1.fill'), method)
    assert not any(t == 0.25 for t, _ in calls)
    assert {name for t, name in calls if t == 0.5} == {'tank0.water', 'bank.received'}
    posted = list(calls)
    for i in (95, 0, 95):
        assert machine.stock_balance(f'tank{i}.water', 1) > 0
    assert calls == posted
    received, own, untouched = read(record, program, ['bank.received', 'tank0.water', 'tank95.water'], [1])
    rate = 1 if method is Family else 1.25
    assert (received.values[0], own.values[0], untouched.values[0]) == (1 + rate / 2, rate / 2, 1 + rate)


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
def test_retirement_reads_shared_legs_once_for_both_ends_and_resumes(method, monkeypatch):
    model = use_method(
        """scenario "Shared prefixes at retirement"
    horizon 2 h
yard:
    a: L = 10 L
    b: L = 1 L
    c: L = 0 L
    rate = 1 L/h
    flow main: this.a -> this.b
        request = formula(this.rate)
    flow parallel: this.a -> this.b
        request = 0.5 L/h
    flow exit: this.b -> this.c
        request = 0.25 L/h
    flow idle: this.a -> this.c
        request = 0 L/h
    change = event():
        after 1 h:
            this.rate = 2 L/h
yard.change.start()
""",
        method,
        monkeypatch,
        'main',
    )
    machine = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.change.step[0]'),))
    stopped = machine.run()
    restored = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(stopped)))
    release = Stocks.release_stock
    transferred = Way.transferred
    calls = Counter()
    releasing = False

    def track_release(self, *args):
        nonlocal releasing
        releasing = True
        try:
            return release(self, *args)
        finally:
            releasing = False

    def track_amount(self, name, t):
        if releasing:
            calls[t, name] += 1
        return transferred(self, name, t)

    monkeypatch.setattr(Stocks, 'release_stock', track_release)
    monkeypatch.setattr(Way, 'transferred', track_amount)
    records = []
    for simulation in (machine, restored):
        calls.clear()
        record = simulation.resume()
        assert record.failure is None
        assert calls == {(1, f'yard.{name}'): 1 for name in ('main', 'parallel', 'exit', 'idle')}
        rows = read(record, model.program, ['yard.a', 'yard.b', 'yard.c'], [1, 2])
        for row, expected in zip(rows, [(8.5, 6), (2.25, 4.5), (0.25, 0.5)], strict=True):
            assert row.values == pytest.approx(expected, abs=1e-12, rel=0)
        records.append(record)
    assert records[0] == records[1]
