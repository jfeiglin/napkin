"""Each stepper reports gross physical transfers only through the accepted instant."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from tests.engine.resume_parity import assert_resume_parity

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
def test_a_moment_books_each_group_before_its_stages_and_never_records_past_that(method, monkeypatch):
    """Before the stages of a moment, each group's transfers are booked through it, and its history is
    never recorded past them. A second booking or recording there, or at an earlier time, changes
    nothing."""
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    source = """plant:
    donor: L = 10 L
    pool: L = 4000000 L
    flow delivery: this.donor -> this.pool
        request = formula(0.1 L/h * t / (1 h))
"""
    machine = Run(Plan.of(compile_text(source + PAUSE, UNITS).program, Configuration(Request(1))))
    finish = machine.finish_arrival
    seen = []

    def state(way):
        pieces = {name: list(rows) for name, rows in machine.recorder.pieces.items()}
        return way.booked_through, way.recorded_through, way.transferred('plant.delivery', 0.5), pieces

    def observe():
        if machine.arriving and machine.now == 0.5:
            way = machine.ways.instance_of('plant.delivery')
            assert isinstance(way, method) and way.booked_through == 0.5
            way.advance(0.5)
            way.record_through(0.75)
            before = state(way)
            assert before[1] == 0.5
            for t in (0.5, 0.25):
                way.advance(t)
            assert state(way) == before
            seen.append(way)
        finish()

    machine.finish_arrival = observe
    assert machine.run().failure is None and seen


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
    tolerance = dict(abs=config.numerics.atol_factor, rel=config.numerics.rtol)
    if power:
        tolerance = dict(abs=2e-12, rel=0)
    for name in names:
        expected = 0.5**7 / 7 if power else math.log1p(0.5)
        assert restored.ways.instance_of(name).transferred(name, 0.5) == pytest.approx(expected, **tolerance)
    assert restored.resume().failure is None
    for name in names:
        whole = straight.ways.instance_of(name).transferred(name, 1)
        resumed = restored.ways.instance_of(name).transferred(name, 1)
        if power:
            assert whole == resumed
        else:
            assert resumed == pytest.approx(whole, **tolerance)
        expected = 1 / 7 if power else math.log(2)
        for amount in (whole, resumed):
            assert amount == pytest.approx(expected, **tolerance)


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


@pytest.mark.parametrize('method', [ComponentWay, Sparse])
@pytest.mark.parametrize('polynomial_neighbor', [False, True], ids=['reciprocal-neighbor', 'two-polynomials'])
def test_individual_clock_legs_preserve_exact_prefixes_in_mixed_groups(
    method, polynomial_neighbor, monkeypatch
):
    from napkin.program.checkpoint import Breakpoint, dumps, loads

    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    neighbor = '0.3 L/h * t / (1 h)' if polynomial_neighbor else '1 L/h / (1 + t / (1 h))'
    source = (
        f"""plant:
    buffer: L = 10 L in [0,]
    water: L = 0 L in [0,]
    flow supply: SOURCE -> this.buffer
        request = formula({neighbor})
    flow delivery: this.buffer -> this.water
        request = formula(0.2 L/h * t / (1 h))
"""
        + PAUSE
    )
    program = compile_text(source, UNITS).program
    config = Configuration(Request(1))
    names = ['plant.delivery'] + (['plant.supply'] if polynomial_neighbor else [])
    expected = {0.5: (Fraction('0.025'), Fraction('0.0375')), 1: (Fraction('0.1'), Fraction('0.15'))}
    finish = Run.finish_arrival
    seen = []

    def observe(run):
        if not run.arriving or run.now not in expected:
            return finish(run)
        way = run.ways.instance_of('plant.delivery')
        assert type(way) is method and run.ways.instance_of('plant.supply') is way
        time = run.now
        if time == 0.5 and way.pending is not None:
            proposed = way.pending[1] if method is Sparse else way.pending.end
            assert proposed > time
        before = tuple(way.transferred(name, time) for name in names)
        finish(run)
        current = run.ways.instance_of('plant.delivery')
        after = tuple(current.transferred(name, time) for name in names)
        assert before == after == expected[time][: len(names)]
        seen.append(time)

    monkeypatch.setattr(Run, 'finish_arrival', observe)
    straight = Run(Plan.of(program, config)).run()
    assert straight.failure is None and seen == [0.5, 1]
    seen.clear()
    stopped = Run(Plan.of(program, config), (Breakpoint('plant.pause.step[0]'),))
    checkpoint = stopped.run()
    restored = Run.restored(Plan.of(program, config), loads(dumps(checkpoint)))
    for run in (stopped, restored):
        way = run.ways.instance_of('plant.delivery')
        assert tuple(way.transferred(name, 0.5) for name in names) == expected[0.5][: len(names)]
        assert_resume_parity(program, config, straight, run.resume())


@pytest.mark.parametrize('method', [ComponentWay, Sparse])
@pytest.mark.parametrize('limit', ['source', 'sink', 'pipe'])
def test_clock_request_yields_to_its_actual_allocation(method, limit, monkeypatch):
    from napkin.program.checkpoint import Breakpoint, dumps, loads

    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    # A source that empties at 1/4 h thereafter passes through the supply's cap.
    # A full destination with no discharge holds its pipe at zero. The capped
    # pipe carries its own cap throughout.
    supply = '0.125 L/h' if limit != 'pipe' else 'formula(1 L/h / (1 + t / (1 h)))'
    supply_cap = '        capacity = 0.125 L/h\n' if limit != 'pipe' else ''
    own_cap = '        capacity = 0.125 L/h\n' if limit == 'pipe' else ''
    initial = '0.046875 L' if limit == 'source' else '10 L'
    high = '0.125 L' if limit == 'sink' else ''
    water = '0.125 L' if limit == 'sink' else '0 L'
    base = '0.125' if limit == 'sink' else '0.25'
    model = (
        f"""plant:
    buffer: L = {initial} in [0,]
    water: L = {water} in [0,{high}]
    flow supply: SOURCE -> this.buffer
        request = {supply}
{supply_cap}    flow delivery: this.buffer -> this.water
        request = formula({base} L/h + 0.5 L/h * t / (1 h))
{own_cap}"""
        + PAUSE
    )
    program = compile_text(model, UNITS).program
    config = Configuration(Request(1))
    stopped = Run(Plan.of(program, config), (Breakpoint('plant.pause.step[0]'),))
    checkpoint = stopped.run()
    restored = Run.restored(Plan.of(program, config), loads(dumps(checkpoint)))
    name = 'plant.delivery'
    for run in (stopped, restored):
        way = run.ways.instance_of(name)
        assert isinstance(way, method)
        half, full = {'source': (0.109375, 0.171875), 'sink': (0, 0), 'pipe': (0.0625, 0.125)}[limit]
        assert way.transferred(name, 0.5) == pytest.approx(half, abs=1e-9)
        assert run.resume().failure is None
        assert run.ways.instance_of(name).transferred(name, 1) == pytest.approx(full, abs=1e-9)
