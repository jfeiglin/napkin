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
