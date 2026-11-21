"""Each stepper reports gross physical transfers only through the accepted instant."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
PAUSE = """    pause = event():
        after 0.5 h
plant.pause.start()
"""


@pytest.mark.parametrize('method', [ComponentWay, Sparse])
@pytest.mark.parametrize('cycle', [False, True], ids=['named-ramp', 'balanced-cycle'])
def test_event_cut_preserves_each_accepted_leg(method, cycle, monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    source = """plant:
    donor: L = 10 L
    pool: L = 4000000 L
    pace = formula(0.1 L/h * t / (1 h))
    flow delivery: this.donor -> this.pool
        request = formula(this.pace)
"""
    names = ['plant.delivery']
    if cycle:
        # Net change at either stock is zero. Each directed physical leg carries the ramp.
        source += """    flow returning: this.pool -> this.donor
        request = formula(this.pace)
"""
        names.append('plant.returning')
    program = compile_text(source + PAUSE, UNITS).program
    machine = Run(Plan.of(program, Configuration(Request(1))))
    finish = machine.finish_arrival
    observed = {}

    def observe():
        if machine.arriving and machine.now in (0.5, 1):
            way = machine.ways.instance_of(names[0])
            assert isinstance(way, method)
            time = machine.now
            end = way.pending[1] if method is Sparse else way.pending.end
            before = [way.transferred(name, time) for name in names]
            finish()
            after = [way.transferred(name, time) for name in names]
            assert before == after
            observed[time] = end, after
        else:
            finish()

    machine.finish_arrival = observe
    record = machine.run()
    assert record.failure is None
    assert observed[0.5][0] > 0.5
    for t, volume in ((0.5, Fraction(1, 80)), (1, Fraction(1, 20))):
        if cycle:
            assert observed[t][1] == pytest.approx([float(volume)] * 2, abs=1e-12, rel=0)
        else:
            assert observed[t][1] == [volume]


@pytest.mark.parametrize('method', [ComponentWay, Sparse])
@pytest.mark.parametrize('power', [True, False], ids=['polynomial', 'reciprocal'])
def test_hidden_circulation_survives_a_serialized_mid_stage_stop(method, power, monkeypatch):
    import math

    from napkin.program.checkpoint import Breakpoint, dumps, loads

    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    rate = '(t / (1 h)) ** 6' if power else '1 / (1 + t / (1 h))'
    source = f"""plant:
    a: L = 100 L
    b: L = 100 L
    pace = formula(1 L/h * ({rate}))
    flow there: this.a -> this.b
        request = formula(this.pace)
    flow back: this.b -> this.a
        request = formula(this.pace)
    pause = event():
        after 0.5 h:
            this.count = 1
    count = 0
plant.pause.start()
"""
    program = compile_text(source, UNITS).program
    config = Configuration(Request(1))
    straight = Run(Plan.of(program, config))
    assert straight.run().failure is None
    machine = Run(Plan.of(program, config), (Breakpoint('plant.pause.step[0]'),))
    checkpoint = machine.run()
    restored = Run.restored(Plan.of(program, config), loads(dumps(checkpoint)))
    names = ['plant.there', 'plant.back']
    for name in names:
        expected = 0.5**7 / 7 if power else math.log1p(0.5)
        assert restored.ways.instance_of(name).transferred(name, 0.5) == pytest.approx(expected, abs=2e-12)
    assert restored.resume().failure is None
    for name in names:
        whole = straight.ways.instance_of(name).transferred(name, 1)
        resumed = restored.ways.instance_of(name).transferred(name, 1)
        assert resumed == whole
        assert whole == pytest.approx(1 / 7 if power else math.log(2), abs=2e-12)


def test_a_signed_route_posts_both_physical_legs_when_it_reverses():
    from napkin.program.build import Builder, formula, q, route, t, value

    builder = Builder(UNITS)
    a = builder.entity('a', value('water', 'L', 10))
    b = builder.entity('b', value('water', 'L', 10))
    builder.entity('ferry', route('link', a.water, b.water, request=formula(q(3, 'L/h') - q(1, 'L/h/h') * t)))
    program = builder.finish()
    run = Run(Plan.of(program, Configuration(Request(6))))
    assert run.run().failure is None
    way = run.ways.instance_of('ferry.link')
    assert isinstance(way, Sparse)
    assert [
        float(way.transferred(f'ferry.link.{side}', 6)) for side in ('forward', 'backward')
    ] == pytest.approx([4.5, 4.5], abs=1e-9)


@pytest.mark.parametrize('family', [True, False], ids=['family', 'lines'])
def test_held_amounts_follow_rate_changes_through_a_checkpoint(family):
    from napkin.engine.timeline.family import Family
    from napkin.engine.timeline.lines import Lines
    from napkin.program.checkpoint import Breakpoint, dumps, loads

    if family:
        # A native Family row runs until it empties, then holds a zero rate.
        source = """tank:
    donor: L = 0.25 L in [0,]
    water: L = 0 L
    flow tap: this.donor -> this.water
        request = 0.5 L/h
"""
        at_pause = at_end = Fraction('0.25')
    else:
        # Three donors empty in succession at .25, .5 and .75 h. Local sharing
        # changes the tap in place at each bound on the same Lines installation.
        source = """tank:
    a: L = 0.015625 L in [0,]
    b: L = 0.0625 L in [0,]
    c: L = 0.1875 L in [0,]
    junction: L = 0 L in [0,]
    water: L = 0 L
    flow one: this.a -> this.junction
        request = 0.0625 L/h
        capacity = 0.0625 L/h
    flow two: this.b -> this.junction
        request = 0.125 L/h
        capacity = 0.125 L/h
    flow three: this.c -> this.junction
        request = 0.25 L/h
        capacity = 0.25 L/h
    flow tap: this.junction -> this.water
        request = 1 L/h
"""
        at_pause, at_end = Fraction('0.234375'), Fraction('0.265625')
    source += '    pause = event():\n        after 0.625 h\ntank.pause.start()\n'
    program = compile_text(source, UNITS).program
    config = Configuration(Request(1))
    machine = Run(Plan.of(program, config), (Breakpoint('tank.pause.step[0]'),))
    checkpoint = machine.run()
    name = 'tank.tap'
    restored = Run.restored(Plan.of(program, config), loads(dumps(checkpoint)))
    for run in (machine, restored):
        way = run.ways.instance_of(name)
        assert isinstance(way, Family if family else Lines)
        before = tuple(way.amounts.rows)
        assert way.transferred(name, 0.625) == way.transferred(name, 0.625) == at_pause
        assert tuple(way.amounts.rows) == before
        assert run.resume().failure is None
        assert run.ways.instance_of(name).transferred(name, 1) == at_end


def test_held_rectangles_keep_finite_decimal_extremes_in_a_bounded_row():
    from napkin.core.units import rational
    from napkin.engine.continuous.transfers import HeldAmounts

    amounts = HeldAmounts(0, 3)
    spans = [(5e-324, 5e-324), (0.05, 0.07), (1e150, 1e175), (2e150, 1e-300)]
    start = expected = Fraction(0)
    for t, rate in spans:
        expected += (rational(t) - start) * rational(rate)
        start = rational(t)
        amounts.change(1, t, rate)
        assert amounts.amount(1, t, 0) == expected
        assert amounts.rows[0] is amounts.rows[2] is None
    restored = HeldAmounts(0, 3)
    for row, through, value in amounts.closed():
        restored.restore(row, through, value)
    assert restored.amount(1, spans[-1][0], 0) == expected


@pytest.mark.parametrize('family', [True, False], ids=['family', 'lines'])
def test_departed_held_connection_keeps_its_terminal_amount(family, monkeypatch):
    from napkin.engine.timeline.family import Family
    from napkin.engine.timeline.lines import Lines

    source = """tank:
    water: L = 0 L
    open = event():
        flow tap: SOURCE -> this.water
            request = 0.05 L/h
"""
    if not family:
        source += '        flow other: SOURCE -> this.water\n            request = 0.125 L/h\n'
    source += '        after 0.25 h\ntank.open.start()\n'
    program = compile_text(source, UNITS).program
    method = Family if family else Lines
    retired = []
    retire = method.retire

    def finish(way, key):
        retired.append(way)
        retire(way, key)

    monkeypatch.setattr(method, 'retire', finish)
    run = Run(Plan.of(program, Configuration(Request(1))))
    assert run.run().failure is None
    name = 'tank.open#0.tap'
    old = next(way for way in retired if name in way.flows)
    assert old.transferred(name, 0.25) == old.transferred(name, 1) == Fraction(1, 80)
