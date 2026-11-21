"""Local events materialize their own held inventories; future and repeated reads make no new postings."""

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.family import Family
from napkin.engine.timeline.lines import Lines
from napkin.program.build import SOURCE, Builder, after, event, flow, move, named, q, start, this, value
from napkin.program.config import Configuration, Request

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

    def traced(machine, store, t):
        advanced = original(machine, store, t)
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
