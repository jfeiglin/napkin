"""An empty stage cannot select which part of a moving capacity history limits a grouped transfer."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CUT = 0.99999
TARGET = Fraction('1.0000000001')
CAP = '(2 - t / (1 h)) * (1 L/h)'
CEILINGS = {
    'saturated': (CAP, CUT),
    'limited': ('(2.001 - t / (1 h)) * (1 L/h)', 0.99999995),
    'open': ('(3 - t / (1 h)) * (1 L/h)', CUT),
}
CASES = [
    ('component', 'pipe'),
    ('sparse', 'pipe'),
    ('moving_declared', 'pipe'),
    ('sparse', 'inflow'),
    ('moving_declared', 'inflow'),
    ('sparse', 'outflow'),
    ('moving_declared', 'outflow'),
    ('moving_declared', 'equation'),
]


def force_method(monkeypatch, method):
    connect = Plan.connect

    def groups(plan, *args, **kwargs):
        found = connect(plan, *args, **kwargs)
        if method in ('declared', 'moving_declared'):
            return [
                replace(group, moves=method == 'moving_declared') if group.way == 'declared' else group
                for group in found
            ]
        return [replace(group, way=method) for group in found]

    monkeypatch.setattr(Plan, 'connect', groups)


def model(method, kind, mode, cap, cut, *, written, literal):
    limit = cap if literal else f'formula({cap})'
    if written:
        limit = '1 L/h'
    tank = f'\n        inflow.capacity = {limit}' if kind == 'inflow' else ''
    donor = f'\n        outflow.capacity = {limit}' if kind == 'outflow' else ''
    pipe = f'\n        capacity = {limit}' if kind == 'pipe' else ''
    source = f"""scenario "A grouped transfer near the end of a moving capacity"
    horizon 1 h
yard:
    tank: L = 0 L{tank}
    donor: L = 2 L{donor}
    flow fill: this.donor -> this.tank
        request = 1 L/h{pipe}
    watch = event():
        when this.tank >= 1.0000000001 L:
            this.watch.start()
        after 0 h
    clock = event():
        after 1 h
"""
    if mode != 'direct':
        body = f':\n            this.fill.capacity = formula({cap})' if written else ''
        source += f'    cut = event():\n        after {cut} h{body}\nyard.cut.start()\n'
    source += 'yard.clock.start()\n'
    if method in ('declared', 'moving_declared'):
        source += """owner:
    share = solver:
        inputs:
            pipe = yard.fill
        solve_for:
            pipe.actual_rate
"""
        if kind == 'equation':
            source += f'        constraints:\n            pipe.actual_rate <= {cap}\n'
    return compile_text(source, UNITS)


def observe(method, kind, mode, *, written=False, cap=CAP, cut=CUT, literal=False):
    case = model(method, kind, mode, cap, cut, written=written, literal=literal)

    def plan():
        return Plan.of(case.program, case.configuration)

    stops = [Breakpoint('yard.clock.step[0]')]
    if mode == 'restored':
        stops.insert(0, Breakpoint('yard.cut.step[0]'))
    run = Run(plan(), tuple(stops))
    stop = run.run()
    if mode == 'restored':
        assert isinstance(stop, Checkpoint) and stop.stop.t == cut
        payload = dumps(stop)
        fields = ['yard.tank', 'yard.fill.actual_rate', 'yard.donor']
        early = read(stop.record, case.program, fields, [0.5, cut])
        reverse = read(stop.record, case.program, fields[::-1], [cut, 0.5])
        assert [v.values for v in early] == [v.values[::-1] for v in reverse[::-1]]
        assert dumps(stop) == payload
        run = Run.restored(plan(), loads(payload))
        stop = run.resume()
    assert isinstance(stop, Checkpoint) and stop.stop.t == 1, stop
    way = run.ways.instance_of('yard.fill')
    assert (
        type(way).__name__
        == {
            'family': 'Family',
            'lines': 'Lines',
            'component': 'ComponentWay',
            'sparse': 'Sparse',
            'declared': 'DeclaredWay',
            'moving_declared': 'MovingDeclared',
        }[method]
    )
    tank = run.stock_balance('yard.tank', 1)
    assert tank + run.stock_balance('yard.donor', 1) == 2
    record = run.resume()
    assert record.end == 1 and record.failure is None
    reasons = tuple(
        entry.detail('reason') for entry in record.entries('settle') if entry.detail('placements')
    )
    fires = tuple((entry.part, entry.t) for entry in record.entries('fire'))
    return tank, reasons, fires, case, record


@pytest.mark.parametrize(
    'room,method,kind',
    [
        pytest.param(
            room,
            method,
            kind,
            id=f'{label}-{method}-{kind}',
            # The regular tier keeps the saturated pipe on all three methods and
            # each declared hard row with both limited and sufficient headroom.
            marks=pytest.mark.deep
            if (room, method) == ('saturated', 'moving_declared') and kind != 'pipe'
            else (),
        )
        for room, label in [
            ('saturated', 'saturated-at-contact'),
            ('limited', 'limited-room'),
            ('open', 'room-at-contact'),
        ]
        for method, kind in CASES
    ],
)
def test_a_grouped_transfer_respects_the_cap_at_contact_and_the_accepted_prefix(
    method, kind, room, monkeypatch
):
    force_method(monkeypatch, method)
    constraint = {
        'pipe': 'yard.fill.capacity',
        'inflow': 'yard.tank.inflow.capacity',
        'outflow': 'yard.donor.outflow.capacity',
        'equation': 'owner.share.constraint[0]',
    }[kind]
    cap, cut = CEILINGS[room]
    for mode in ('direct', 'empty', 'restored'):
        tank, reasons, fires, case, record = observe(method, kind, mode, cap=cap, cut=cut)
        assert fires == (('yard.watch.when[0]', 1),), mode
        tank_read, donor_read, rate = read(
            record, case.program, ['yard.tank', 'yard.donor', 'yard.fill.actual_rate'], [cut, 1]
        )
        assert tank_read.values[-1] == pytest.approx(float(tank), rel=0, abs=2e-13)
        assert donor_read.values[-1] == pytest.approx(float(2 - tank), rel=0, abs=2e-13)
        assert rate.values == pytest.approx([1, 1], rel=0, abs=2e-9)
        if room == 'open':
            # (3 - t/h) L/h still has 1 L/h of room at the stage. Its final
            # prefix can supply a 1e-10 L placement at both ends of the pipe.
            assert tank == TARGET, mode
            assert not reasons
        else:
            # At saturation (2 - t/h) leaves just 5e-11 L beyond the
            # requested transfer on the last 1e-5 h. In the limited case
            # there is still 0.001 L/h of room at hour 1, yet the 5e-8 h
            # suffix has only 5.000125e-11 L. Neither can supply the target.
            assert tank < TARGET and float(tank) == pytest.approx(1, rel=0, abs=2e-11), mode
            assert len(reasons) == 1 and constraint in reasons[0], (mode, reasons)
            if mode != 'direct':
                # The empty stage or checkpoint fixes both physical readings.
                dt = 1 - Fraction(str(cut))
                terminal_slack = Fraction('0.001') if room == 'limited' else 0
                max_suffix = dt + dt * terminal_slack + dt * dt / 2
                a, b = tank_read.values
                assert b - a <= float(max_suffix) + 2e-13


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize('mode', ['empty', 'restored'])
def test_a_new_moving_pipe_capacity_cannot_retroactively_increase_its_earlier_ceiling(
    method, mode, monkeypatch
):
    force_method(monkeypatch, method)
    tank, reasons, _, case, record = observe(method, 'pipe', mode, written=True)
    # The old 1 L/h applies through the cut. The area between the new cap and 1 L/h is
    # (1 - CUT)^2/2 = 5e-11 L; using the new definition back to zero would give 0.5 L.
    limit = Fraction(1) + Fraction(1, 20_000_000_000)
    assert tank < TARGET and float(tank) <= float(limit) + 1e-13
    assert reasons and 'yard.fill.capacity' in reasons[0]
    (capacity,) = read(record, case.program, ['yard.fill.capacity'], [0.5, CUT, 1])
    assert capacity.values == pytest.approx([1, 2 - CUT, 1], abs=1e-14, rel=0)


@pytest.mark.parametrize('method', ['sparse', 'moving_declared'])
def test_a_real_second_inflow_shares_the_same_moving_endpoint_ceiling(method, monkeypatch):
    force_method(monkeypatch, method)
    source = f"""scenario "A second pipe joins a full endpoint"
    horizon 1 h
yard:
    tank: L = 0 L
        inflow.capacity = formula({CAP})
    donor: L = 3 L
    second: L = 3 L
    flow fill: this.donor -> this.tank
        request = 3 L/h
    join = event():
        flow extra: yard.second -> yard.tank
            request = 3 L/h
        after 1 h
    shift = event():
        after 0.5 h:
            this.join.start()
    watch = event():
        when this.tank >= 1.5000000001 L:
            this.watch.start()
        after 0 h
    clock = event():
        after 1 h
yard.shift.start()
yard.clock.start()
"""
    if method in ('declared', 'moving_declared'):
        source += """owner:
    share = solver:
        inputs:
            pipe = yard.fill
        solve_for:
            pipe.actual_rate
"""
    case = compile_text(source, UNITS)
    run = Run(Plan.of(case.program, case.configuration), (Breakpoint('yard.clock.step[0]'),))
    stop = run.run()
    assert isinstance(stop, Checkpoint), stop
    tank, donor, second = (run.stock_balance(f'yard.{key}', 1) for key in ('tank', 'donor', 'second'))
    assert 0 < 3 - second < tank
    assert tank + donor + second == 6
    assert float(tank) == pytest.approx(1.5, rel=0, abs=2e-12)
    record = run.resume()
    assert record.failure is None
    (levels,) = read(record, case.program, ['yard.tank'], [0.5, 1])
    # The first pipe used 7/8 L before the second joined. The common ceiling supplies 5/8 L after.
    assert levels.values == pytest.approx([0.875, 1.5], rel=0, abs=2e-12)
    assert any('yard.tank.inflow.capacity' in str(e.detail('reason')) for e in record.entries('settle'))


@pytest.mark.parametrize(
    'method,kind',
    [
        ('family', 'pipe'),
        ('lines', 'pipe'),
        ('component', 'pipe'),
        ('sparse', 'pipe'),
        ('sparse', 'inflow'),
        ('sparse', 'outflow'),
        ('declared', 'equation'),
        ('moving_declared', 'equation'),
    ],
)
@pytest.mark.parametrize('rate', ['1.001', '2'], ids=['insufficient-room', 'enough-room'])
def test_equal_constant_caps_have_one_physical_outcome_across_forms_and_methods(
    method, kind, rate, monkeypatch
):
    force_method(monkeypatch, method)
    cut = 0.99999995
    # The static declared row takes an expression directly. The other authored
    # capacities accept both a literal and an explicitly wrapped formula.
    literal = f'{rate} L/h'
    forms = [(literal, True)]
    if kind != 'equation':
        forms.append((literal, False))
    if method in ('component', 'sparse', 'moving_declared'):
        forms.append((f'({rate} + 0 * t / (1 h)) * (1 L/h)', False))
    for cap, as_literal in forms:
        for mode in ('direct', 'empty', 'restored'):
            tank, reasons, fires, case, record = observe(
                method, kind, mode, cap=cap, cut=cut, literal=as_literal
            )
            assert fires == (('yard.watch.when[0]', 1),), (cap, mode)
            assert bool(reasons) == (rate == '1.001'), (cap, mode, reasons)
            expected = Fraction(1) if rate == '1.001' else TARGET
            if expected == TARGET:
                assert tank == TARGET
            else:
                assert float(tank) == pytest.approx(1, rel=0, abs=2e-11)
            level, donor, actual = read(
                record, case.program, ['yard.tank', 'yard.donor', 'yard.fill.actual_rate'], [cut, 1]
            )
            assert (level.values[-1], donor.values[-1]) == pytest.approx(
                [float(expected), float(2 - expected)], rel=0, abs=2e-11
            )
            assert actual.values == pytest.approx([1, 1], rel=0, abs=2e-9)
            if mode != 'direct':
                assert (
                    level.values[1] - level.values[0]
                    <= float(Fraction(rate) * (1 - Fraction(str(cut)))) + 2e-13
                )


@pytest.mark.parametrize('kind', ['pipe', 'inflow', 'outflow', 'equation'])
@pytest.mark.parametrize('rate', ['1.001', '2'], ids=['insufficient-room', 'enough-room'])
def test_the_reference_keeps_constant_capacity_room_independent_of_its_spelling_or_an_empty_stage(kind, rate):
    from napkin.program.record import Key
    from tests.reference.from_program import run_of, value_at

    cut = Fraction('0.99999995')
    expected = Fraction(1) if rate == '1.001' else TARGET
    method = 'declared' if kind == 'equation' else 'component'
    for expr, as_literal in ((f'{rate} L/h', True), (f'({rate} + 0 * t / (1 h)) * (1 L/h)', False)):
        for mode in ('direct', 'empty'):
            case = model(method, kind, mode, expr, float(cut), written=False, literal=as_literal)
            run, failure = run_of(case.program, case.configuration)
            assert failure is None and run.conservation()['balanced'], (expr, mode, failure)
            level = Key('yard', ('tank',))
            assert value_at(run, case.program, level, 1) == expected, (expr, mode)
            assert value_at(run, case.program, Key('yard', ('donor',)), 1) == 2 - expected
            assert [(e.label, e.t) for e in run.trace if e.kind == 'fire'] == [('yard.watch.when[0]', 1)]
            if mode == 'empty':
                assert expected - value_at(run, case.program, level, cut) <= Fraction(rate) * (1 - cut)


@pytest.mark.parametrize('method', ['family', 'lines', 'component', 'sparse', 'declared', 'moving_declared'])
@pytest.mark.parametrize('rate', ['1.02', '2'], ids=['limited', 'open'])
def test_a_separate_horizon_preserves_the_last_reading_and_its_remaining_cap(rate, method, monkeypatch):
    # The earlier authored stage brings the later clock into the same round.
    # The stock remains outside its guard band there, and the inclusive horizon
    # still has a separate physical reading. A 1.02 L/h ceiling can supply at
    # most 2.04e-9 L between those readings; placement would require 2.1e-9 L.
    force_method(monkeypatch, method)
    cut = 0.999999998
    kind = 'equation' if method in ('declared', 'moving_declared') else 'pipe'
    for mode in ('direct', 'empty', 'restored'):
        case = model(method, kind, mode, f'{rate} L/h', cut, written=False, literal=True)

        def plan():
            return Plan.of(case.program, case.configuration)

        run = Run(plan(), (Breakpoint('yard.cut.step[0]'),) if mode == 'restored' else ())
        record = run.run()
        if mode == 'restored':
            assert isinstance(record, Checkpoint) and record.stop.t == cut
            payload = dumps(record)
            (early,) = read(record.record, case.program, ['yard.tank'], [cut])
            assert early.values == pytest.approx([cut], rel=0, abs=2e-13)
            assert dumps(record) == payload
            run = Run.restored(plan(), loads(payload))
            record = run.resume()
        assert record.failure is None and record.end == 1
        assert [(e.t, e.part) for e in record.entries('fire')] == [(1, 'yard.watch.when[0]')]
        expected = Fraction(1) if rate == '1.02' else TARGET
        tank, donor = read(record, case.program, ['yard.tank', 'yard.donor'], [cut, 1])
        assert tank.values[-1] == pytest.approx(float(expected), rel=0, abs=2e-12)
        assert donor.values[-1] == pytest.approx(float(2 - expected), rel=0, abs=2e-12)
        if mode != 'direct':
            for event in ('clock', 'cut'):
                assert [x.t for x in record.entries('commit', f'yard.{event}.step[0]')] == [cut]
            assert tank.values[0] == pytest.approx(cut, rel=0, abs=2e-13)
            assert tank.values[1] - tank.values[0] <= float(Fraction(rate) * Fraction(2, 10**9)) + 2e-13


@pytest.mark.parametrize('kind', ['pipe', 'equation'])
@pytest.mark.parametrize('rate', ['1.02', '2'], ids=['limited', 'open'])
def test_the_exact_horizon_respects_a_stock_read_just_before_it(kind, rate):
    from napkin.program.record import Key
    from tests.reference.from_program import run_of, value_at

    cut = Fraction('0.999999998')
    method = 'declared' if kind == 'equation' else 'component'
    for mode in ('direct', 'empty'):
        case = model(method, kind, mode, f'{rate} L/h', float(cut), written=False, literal=True)
        run, error = run_of(case.program, case.configuration)
        assert error is None
        expected = 1 if rate == '1.02' else TARGET
        level = Key('yard', ('tank',))
        assert value_at(run, case.program, level, 1) == expected
        assert value_at(run, case.program, Key('yard', ('donor',)), 1) == 2 - expected
        assert [(x.t, x.label) for x in run.trace if x.kind == 'fire'] == [(1, 'yard.watch.when[0]')]
        if mode == 'empty':
            assert value_at(run, case.program, level, cut) == cut
            assert expected - cut <= Fraction(rate) * (1 - cut)
