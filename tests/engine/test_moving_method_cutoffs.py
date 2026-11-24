"""Moving methods expose accepted physical amounts and switches inside the timeline's cutoff."""

import math
from dataclasses import replace

import pytest

from napkin.core import expr
from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.declared import MovingDeclared
from napkin.engine.timeline.sparse import Sparse
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from tests.engine.resume_parity import assert_resume_parity
from tests.engine.test_threshold_transfer_placement import use_method

METHODS = {'component': ComponentWay, 'sparse': Sparse, 'moving_declared': MovingDeclared}


@pytest.mark.parametrize('method', METHODS)
def test_accepted_amount_and_saved_arrival_exclude_the_unaccepted_tail(method, monkeypatch):
    source = """scenario "Reading an accepted prefix"
    horizon 1 h
yard:
    stock: L = 10 L
    received: L = 0 L
    flow fill: this.stock -> this.received
        request = formula(1 L/h / (1 + t / (16 h)))
    observed: L = 0 L
    pause = event():
        after 0.5 h:
            this.observed = this.received
        after 0 h
yard.pause.start()
"""
    model = use_method(source, method, monkeypatch, 'fill')
    plan = Plan.of(model.program, model.configuration)
    live = Run(plan, (Breakpoint('yard.pause.step[0]'),))
    checkpoint = live.run()
    assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 0.5
    restored = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(checkpoint)))
    pipe = 'yard.fill'
    way = live.ways.instance_of(pipe)
    saved = restored.ways.instance_of(pipe)
    assert type(way) is type(saved) is METHODS[method]
    accepted = way.amounts.through
    assert accepted < 0.5
    inside = (accepted + 0.5) / 2

    def integral(t):
        return pytest.approx(16 * math.log1p(t / 16), abs=5e-10, rel=0)

    assert way.transferred(pipe, inside) == integral(inside)
    for installed in (way, saved):
        assert installed.transferred(pipe, accepted) == integral(accepted)
        assert installed.transferred(pipe, 0.5) == integral(0.5)
        # The adjacent float is inside the clock tolerance but is still in the proposed tail.
        for outside in (math.nextafter(accepted, -math.inf), math.nextafter(0.5, math.inf), 1):
            with pytest.raises(ValueError, match='outside the accepted interval'):
                installed.transferred(pipe, outside)
        assert installed.transferred(pipe, 0.5) == way.transferred(pipe, 0.5)

    whole = live.resume()
    assert whole.failure is None, whole.failure
    assert_resume_parity(model.program, model.configuration, whole, restored.resume())
    assert [(e.t, e.round, e.part) for e in whole.entries('commit')] == [
        (0.5, 1, 'yard.pause.step[0]'),
        (0.5, 2, 'yard.pause.step[1]'),
    ]
    observed, received = read(whole, model.program, ['yard.observed', 'yard.received'], [1])
    assert observed.values[0] == integral(0.5)
    assert received.values[0] == integral(1)
    assert live.ways.instance_of(pipe).transferred(pipe, 1) == integral(1)


@pytest.mark.parametrize('method', METHODS)
def test_detected_switch_uses_both_the_closed_clock_window_and_the_accepted_cutoff(method, monkeypatch):
    source = """scenario "A switch beside a stage"
    horizon 1.1 h
yard:
    stock: L = 0 L
    flow fill: SOURCE -> this.stock
        request = formula(1 L/h if this.stock < 1 L else 2 L/h)
    before: L/h = 0 L/h
    after_rate: L/h = 0 L/h
    pause = event():
        after 1.0000000001 h:
            this.before = this.fill.actual_rate
        after 0 h:
            this.after_rate = this.fill.actual_rate
yard.pause.start()
"""
    model = use_method(source, method, monkeypatch, 'fill')
    # A binary-exact window lets the test put a located root exactly at its upper time edge.
    window = 2**-20
    config = replace(model.configuration, numerics=replace(model.configuration.numerics, crossing=window))
    run = Run(Plan.of(model.program, config), (Breakpoint('yard.pause.step[0]'),))
    stop = run.run()
    assert isinstance(stop, Checkpoint) and run.now == 1.0000000001
    way = run.ways.instance_of('yard.fill')
    assert type(way) is METHODS[method]
    ((located, operands),) = way.crossed_operands(run.now, run.now)
    assert located == pytest.approx(1, abs=1e-13, rel=0)
    assert {expr.text(side) for side in operands} == {'yard.stock', "q(1, 'L')"}
    assert (located - window) + window == located
    for moment in (located - window, located, located + window / 2):
        assert list(way.crossed_operands(moment, located)) == [(located, operands)]
        assert list(way.crossed_operands(moment, math.nextafter(located, -math.inf))) == []
    for moment in (located - 2 * window, located + 2 * window):
        assert list(way.crossed_operands(moment, located + 3 * window)) == []

    record = run.resume()
    assert record.failure is None, record.failure
    at = 1.0000000001
    assert [(e.t, e.round, e.kind, e.part) for e in record.trace if e.kind in ('contact', 'commit')] == [
        (at, 1, 'contact', 'yard.fill'),
        (at, 1, 'commit', 'yard.pause.step[0]'),
        (at, 2, 'commit', 'yard.pause.step[1]'),
    ]
    before, after, stock = read(
        record, model.program, ['yard.before', 'yard.after_rate', 'yard.stock'], [at, 1.1]
    )
    assert before.values == (1, 1)
    assert after.values == (2, 2)
    assert stock.values == pytest.approx((1, 1 + 2 * (1.1 - at)), rel=0, abs=1e-12)
