"""A physical stock leaves a face only above the owner's traffic-relative threshold."""

import math
from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.declared import DeclaredWay
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import use_method
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('upper', [False, True], ids=['floor', 'ceiling'])
@pytest.mark.parametrize(
    'larger,smaller,leaves',
    [
        ('0.50000000000049', '0.49999999999951', False),
        ('0.50000000000050', '0.49999999999950', False),
        ('0.50000000000051', '0.49999999999949', True),
    ],
    ids=['below', 'at', 'above'],
)
def test_departure_depends_on_the_net_rate_relative_to_both_gross_rates(
    method, upper, larger, smaller, leaves, monkeypatch
):
    inflow, outflow = (smaller, larger) if upper else (larger, smaller)
    initial = 1 if upper else 0
    text = f"""scenario "A nearly balanced pass-through"
    horizon 1 h
yard:
    stock: L = {initial} L in [0, 1 L]
    flow feed: SOURCE -> this.stock
        request = {inflow} L/h
        capacity = {inflow} L/h
    flow drain: this.stock -> SINK
        request = {outflow} L/h
        capacity = {outflow} L/h
"""
    model = use_method(text, method, monkeypatch, 'feed')
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and oracle.conservation()['balanced']
    (component,) = oracle.components
    assert bool(component.released) == leaves
    declared_faces = []
    if method == 'declared':
        original = DeclaredWay._settled

        def capture_face(way, *args):
            answer, low, high = original(way, *args)
            declared_faces.append(bool((high if upper else low)[way.place['yard.stock']]))
            return answer, low, high

        monkeypatch.setattr(DeclaredWay, '_settled', capture_face)
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None and record.end == 1
    way = machine.ways.instance_of('yard.stock')
    if method == 'declared':
        assert declared_faces and all(retained == (not leaves) for retained in declared_faces)
    elif method == 'lines':
        mask = way.instant.upper if upper else way.instant.lower
        assert bool(mask[way.place['yard.stock']]) == (not leaves)
    else:
        low, high = way._clock_bounds()
        assert bool((high if upper else low)(way.place['yard.stock'])) == (not leaves)
    rate_in, rate_out = read(record, model.program, ['yard.feed.actual_rate', 'yard.drain.actual_rate'], [0])
    gross = Fraction(inflow) + Fraction(outflow)
    net = Fraction(inflow) - Fraction(outflow)
    assert gross == 1 and (abs(net) > gross / 10**12) == leaves
    assert rate_in.values[0] == pytest.approx(float(inflow), rel=0, abs=2e-15)
    assert rate_out.values[0] == pytest.approx(float(outflow), rel=0, abs=2e-15)
    # Holding either face cannot increase the lesser hard-capped flow to
    # force a flat physical history. Both accepted gross transfers still post.
    (stock,) = read(record, model.program, ['yard.stock'], [0.5, 1])
    expected = (initial + float(net) / 2, initial + float(net))
    assert stock.values == pytest.approx(expected, rel=0, abs=2e-15)
    assert value_at(oracle, model.program, Key('yard', ('stock',)), 1) == initial + net


@pytest.mark.parametrize('method', ['family', 'lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('upper', [False, True], ids=['floor', 'ceiling'])
def test_one_way_traffic_can_leave_a_bound_even_at_a_tiny_rate(method, upper, monkeypatch):
    opening = '0.0000000001' if upper else '0'
    ends = 'this.stock -> SINK' if upper else 'SOURCE -> this.stock'
    text = f"""scenario "One-way flow leaving a bound"
    horizon 1 h
yard:
    stock: L = {opening} L in [0, 0.0000000001 L] scale 0.0000000001 L
    flow tap: {ends}
        request = 0.000000000000001 L/h
        capacity = 0.000000000000001 L/h
"""
    model = use_method(text, method, monkeypatch, 'tap')
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and oracle.conservation()['balanced']
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None and record.end == 1
    level, rate = read(record, model.program, ['yard.stock', 'yard.tap.actual_rate'], [0, 1])
    change = Fraction(1, 10**15) * (-1 if upper else 1)
    expected = Fraction(opening) + change
    assert level.values == pytest.approx((float(opening), float(expected)), rel=0, abs=1e-25)
    assert float(machine.stock_balance('yard.stock', 1)) == pytest.approx(float(expected), rel=0, abs=1e-25)
    assert rate.values == pytest.approx((1e-15, 1e-15), rel=0, abs=1e-25)


@pytest.mark.parametrize('moving', [False, True], ids=['declared', 'moving-declared'])
def test_a_held_allocation_face_keeps_both_hard_transfers_on_its_books(moving, monkeypatch):
    text = """scenario "Fixed hard rates at an empty stock"
    horizon 2 h
yard:
    stock: L = 0 L in [0, 1 L]
    flow feed: SOURCE -> this.stock
        request = 1 L/h
    flow drain: this.stock -> SINK
        request = 0.999999999999 L/h
    hard = solver:
        inputs:
            a = yard.feed
            b = yard.drain
        solve_for:
            a.actual_rate
            b.actual_rate
        constraints:
            a.actual_rate == 1 L/h
            b.actual_rate == 0.999999999999 L/h
    inspect = event():
        after 1 h
yard.inspect.start()
"""
    model = compile_text(text, {'L': {'volume': 1}, 'h': {'time': 1}})
    connect = Plan.connect

    def force(plan, *args, **kwargs):
        return [
            replace(g, moves=moving) if g.way == 'declared' else g for g in connect(plan, *args, **kwargs)
        ]

    monkeypatch.setattr(Plan, 'connect', force)
    program, config = model.program, model.configuration
    oracle, error = run_of(program, config)
    assert error is None and oracle.conservation()['balanced']
    input_rate, output_rate, unit = Fraction(1), Fraction('0.999999999999'), Fraction('0.000000000001')
    assert value_at(oracle, program, Key('yard', ('stock',)), 2) == 2 * unit
    assert not oracle.components[0].released
    machine = Run(Plan.of(program, config), (Breakpoint('yard.inspect.step[0]'),))
    stop = machine.run()
    assert isinstance(stop, Checkpoint) and stop.stop.t == 1
    restored = Run.restored(Plan.of(program, config), loads(dumps(stop)))
    for run in (machine, restored):
        method = run.ways.instance_of('yard.stock')
        assert type(method).__name__ == ('MovingDeclared' if moving else 'DeclaredWay')
        assert run.stock_balance('yard.stock', 1) == unit
        record = run.resume()
        assert record.end == 2 and record.failure is None
        incoming = method.transferred('yard.feed', 2)
        outgoing = method.transferred('yard.drain', 2)
        assert incoming == 2 * input_rate
        assert outgoing == 2 * output_rate
        assert run.stock_balance('yard.stock', 2) == incoming - outgoing == 2 * unit
        stock, feed, drain = read(
            record, program, ['yard.stock', 'yard.feed.actual_rate', 'yard.drain.actual_rate'], [0, 1, 2]
        )
        assert stock.values == (0, float(unit), float(2 * unit))
        assert feed.values == (1, 1, 1)
        assert drain.values == (float(output_rate),) * 3


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'declared', 'moving_declared'])
def test_a_held_faces_intermediate_history_tracks_its_posted_legs(method, monkeypatch):
    text = """scenario "A capped inlet at a full tank"
    horizon 40 h
yard:
    tank: L = 0.01 L in [0, 0.01 L]
    flow fill: SOURCE -> this.tank
        request = 0.7999999999999999 L/h
        capacity = 0.7999999999999999 L/h
    flow first: this.tank -> SINK
        request = 0.1 L/h
    flow second: this.tank -> SINK
        request = 0.7 L/h
"""
    model = use_method(text, method, monkeypatch, 'fill')
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None
    at = [1, 13, 40]
    (history,) = read(record, model.program, ['yard.tank'], at)
    way = machine.ways.instance_of('yard.tank')
    inflow, first, second = [way.transferred('yard.' + name, 40) for name in ('fill', 'first', 'second')]
    start = Fraction(1, 100)
    total = inflow - first - second
    assert start + total == machine.stock_balance('yard.tank', 40)
    # Each actual rate is constant throughout. The balance at each reading is
    # its fraction of the very same accepted incidence the run posts at the horizon.
    for time, observed in zip(at, history.values, strict=True):
        expected = float(start + total * time / 40)
        assert observed == pytest.approx(expected, abs=math.ulp(expected), rel=0)


def test_a_released_store_never_reuses_an_answer_solved_while_it_was_held(monkeypatch):
    from napkin.engine.timeline.declared import MovingDeclared

    # The stock is held empty until the inflow passes the outflow, at 0.5 h. Its release is found on
    # the trajectory with the store still held; the next segment then starts with it free.
    text = """scenario "A stock released from its floor"
    horizon 1 h
yard:
    stock: L = 0 L in [0,]
    flow fill: SOURCE -> this.stock
        request = formula(t * 2 L/h/h)
    flow tap: this.stock -> SINK
        request = 1 L/h
"""
    model = use_method(text, 'moving_declared', monkeypatch, 'tap')
    solve, at = MovingDeclared.answer, MovingDeclared._at
    flags, made, stale, hits = [], {}, [], []

    def answer(self, t, low, high):
        if flags and flags[-1] is None:
            flags[-1] = (low.tobytes(), high.tobytes())
        return solve(self, t, low, high)

    def checked(self, t, y):
        flags.append(None)
        try:
            found = at(self, t, y)
        finally:
            used = flags.pop()
        now = (self.low.tobytes(), self.high.tobytes())
        if used is not None:
            made[id(found)] = used
        else:
            hits.append(float(t))
            if made.get(id(found), now) != now:
                stale.append(float(t))
        return found

    monkeypatch.setattr(MovingDeclared, 'answer', answer)
    monkeypatch.setattr(MovingDeclared, '_at', checked)
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None and record.end == 1
    assert hits and not stale
