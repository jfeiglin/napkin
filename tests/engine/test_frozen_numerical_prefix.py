"""Frozen gross transfers on a genuine numerical leg and competing failure boundaries."""

import math
from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.declared import DeclaredWay, MovingDeclared
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from tests.engine.resume_parity import assert_resume_parity
from tests.reference.from_program import run_of

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
ALLOWANCE = Fraction(1, 10)


def reciprocal(method, held, mean, pause=False):
    # x = (t - 1 h) / (1 h). The antiderivative of the physical rate
    # 2m/(1+x)^2 is 2mx/(1+x), exactly m at x=1. No polynomial rate
    # shortcut applies. All sources stay interior and the sink has unlimited room.
    source = """scenario "A numerical gross leg at retirement"
    horizon 2 h
plant:
    water: L = 10 L in [0,]
    flow supply: SOURCE -> this.water
        request = 0.2 L/h
    retire = event():
        batch: L = 0 L in [0,] scale 1000000000 L
        after 1 h
    watch = event():
        job = this.retire.occurrences.at(t)
        flow curved: this.water -> job.batch
            request = 0 L/h
"""
    if held:
        source += """        flow steady: this.water -> job.batch
            request = 0 L/h
"""
    source += f"""        after 1 h:
            curved.request = formula(2 * {mean} L/h / ((1 + (t - 1 h) / (1 h)) ** 2))
"""
    if held:
        source += '            steady.request = 0.075 L/h\n'
    source += '        after 3 h\n'
    if pause:
        source += '    cut = event():\n        after 1.25 h\n'
    if method is MovingDeclared:
        source += """provider:
    share = solver:
        inputs:
            supply = plant.supply
        solve_for:
            supply.actual_rate
"""
    source += 'plant.retire.start()\nplant.watch.start()\n'
    if pause:
        source += 'plant.cut.start()\n'
    return compile_text(source, UNITS)


def run(model, stops=()):
    engine = Run(Plan.of(model.program, model.configuration), stops)
    return engine, engine.run()


def assert_amount(record, mean, held):
    exact = Fraction('0.075') if held else 0
    residual = ALLOWANCE - exact
    if Fraction(mean) <= residual:
        assert record.failure is None and record.end == 2
    else:
        assert record.failure is not None
        assert record.end == pytest.approx(2, abs=2e-10, rel=0)
        message = record.failure.detail('message')
        assert 'into plant.retire#0.batch' in message
        legs = ['curved', 'steady'] if held else ['curved']
        assert record.failure.detail('violations') == tuple(
            ('plant.retire#0.batch', 'inflow', f'plant.watch#0.{leg}') for leg in legs
        )


@pytest.mark.parametrize(
    'edge,method,held',
    [
        pytest.param(
            edge,
            method,
            held,
            id=f'{label}-{method.__name__}-{held}',
            # Retain both a successful single-leg and a failed mixed-leg
            # MovingDeclared run in regular. Sparse covers every mixed-leg edge.
            marks=pytest.mark.deep
            if method is MovingDeclared and (edge, held) not in {(0, False), (1, True)}
            else (),
        )
        for edge, label in [(-1, 'below'), (0, 'equal'), (1, 'above')]
        for method, held in [
            (ComponentWay, False),
            (Sparse, False),
            (MovingDeclared, False),
            (Sparse, True),
            (MovingDeclared, True),
        ]
    ],
)
def test_numerical_leg_respects_the_exact_residual_allowance(method, held, edge, monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    limit = 0.025 if held else 0.1
    mean = repr(math.nextafter(limit, 0 if edge < 0 else math.inf) if edge else limit)
    model = reciprocal(method, held, mean)
    engine, record = run(model)
    assert type(engine.ways.instance_of('plant.watch#0.curved')) is method
    assert_amount(record, mean, held)


@pytest.mark.parametrize('mean', ['0.1', repr(math.nextafter(0.1, 1))])
def test_an_interior_checkpoint_preserves_the_numerical_residual_decision(mean, monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0)
    uninterrupted = reciprocal(Sparse, False, mean)
    _, whole = run(uninterrupted)
    assert_amount(whole, mean, False)
    model = reciprocal(Sparse, False, mean, pause=True)
    machine, stop = run(model, (Breakpoint('plant.cut.step[0]'),))
    assert isinstance(stop, Checkpoint) and stop.stop.t == 1.25
    restored = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(stop)))
    continued = restored.resume()
    assert_resume_parity(model.program, model.configuration, machine.resume(), continued)
    assert_amount(continued, mean, False)


def opposing(inward, outward, close=None):
    source = f"""scenario "Competing directions at nearby times"
    horizon 3 h
plant:
    water: L = 10 L in [0,]
    retire = event():
        batch: L = 0.001 L in [0,] scale 1000000000 L
        after 1 h
    watch = event():
        job = this.retire.occurrences.at(t)
        flow inward: this.water -> job.batch
            request = 0 L/h
        flow outward: job.batch -> this.water
            request = 0 L/h
        after 1 h:
            inward.request = {inward} L/h
            outward.request = {outward} L/h
        after 3 h
"""
    if close:
        source += f"""    close = event():
        after {close} h:
            this.watch.occurrences.at(t).inward.request = 0 L/h
            this.watch.occurrences.at(t).outward.request = 0 L/h
"""
    source += 'plant.retire.start()\nplant.watch.start()\n'
    if close:
        source += 'plant.close.start()\n'
    return compile_text(source, UNITS)


@pytest.mark.parametrize(
    'inward,outward,close,names',
    [
        ('0.100000000001', '0.1', None, ('outward', 'inward')),
        ('0.1', '0.100000000001', None, ('outward', 'inward')),
        ('0.100001', '0.1', None, ('inward',)),
        ('0.100000000001', '0.1', '2', ('inward',)),
    ],
)
def test_nearby_directions_share_one_report_only_if_they_exceed_before_the_stage(
    inward, outward, close, names
):
    model = opposing(inward, outward, close)
    _, record = run(model)
    reference, error = run_of(model.program, model.configuration)
    early = Fraction(1) + ALLOWANCE / max(Fraction(inward), Fraction(outward))
    assert error is not None and reference.view.t == early
    assert record.failure is not None
    assert record.end == pytest.approx(float(early), abs=1e-14, rel=0)
    additions = tuple(
        ('plant.retire#0.batch', 'inflow' if n == 'inward' else 'outflow', f'plant.watch#0.{n}')
        for n in names
    )
    assert error.violations == additions
    assert record.failure.detail('violations') == additions


@pytest.mark.parametrize('close', ['1.99999999999', '2', '2.00000000001'])
def test_an_exact_limit_at_a_stage_commits_only_if_the_incoming_interval_fits(close):
    _, record = run(opposing('0.1', '0.099', close))
    closed = any(entry.kind == 'commit' and entry.part == 'plant.close.step[0]' for entry in record.trace)
    if Fraction(close) <= 2:
        assert record.failure is None and closed
    else:
        assert record.failure is not None and record.end == 2 and not closed
        assert 'the flow plant.watch#0.inward carries' in record.failure.detail('message')


def test_the_offender_can_start_at_zero_while_another_leg_stays_idle():
    program = compile_text(
        """scenario "First positive amount after exhausting a frozen allowance"
    horizon 3 h
plant:
    bulk: L = 10 L in [0,]
    retire = event():
        batch: L = 0 L in [0,] scale 1000000000 L
        after 1 h
    watch = event():
        job = this.retire.occurrences.at(t)
        flow idle: this.bulk -> job.batch
            request = 0 L/h
        flow prime: this.bulk -> job.batch
            request = 0 L/h
        flow ramp: this.bulk -> job.batch
            request = 0 L/h
        after 1 h:
            prime.request = 0.1 L/h
        after 1 h:
            prime.request = 0 L/h
            ramp.request = formula(0.2 L/h * (t - 2 h) / (1 h))
        after 2 h
plant.retire.start()
plant.watch.start()
""",
        UNITS,
    )
    _, record = run(program)
    assert record.failure is not None and record.end == 2
    assert [(e.kind, e.part) for e in record.trace if e.t == 2] == [
        ('commit', 'plant.watch.step[1]'),
        ('failure', ''),
    ]
    reference, error = run_of(program.program, program.configuration)
    expected = (('plant.retire#0.batch', 'inflow', 'plant.watch#0.ramp'),)
    assert reference.view.t == 2 and error.violations == expected
    assert record.failure.detail('violations') == expected


def several_stocks(declared):
    text = """scenario "More than five frozen violations"
    horizon 3 h
plant:
    water: L = 10 L in [0,]
    flow supply: SOURCE -> this.water
        request = 0.2 L/h
    retire = event():
        zeta: L = 0.001 L in [0,] scale 1000000000 L
        alpha: L = 0.001 L in [0,] scale 1000000000 L
        after 1 h
    watch = event():
        job = this.retire.occurrences.at(t)
"""
    writes = []
    # Deliberately declare zeta first, inflows first, and a small z leg before a large a leg.
    # Only the final ordering within one stock and side follows the declaration order.
    for field in ('zeta', 'alpha'):
        for side in ('inflow', 'outflow'):
            ends = ['this.water', f'job.{field}']
            if side == 'outflow':
                ends.reverse()
            for suffix, amount in [('z', '0.025'), ('a', '0.075')]:
                name = f'{field}_{side}_{suffix}'
                text += f'        flow {name}: {ends[0]} -> {ends[1]}\n            request = 0 L/h\n'
                writes.append(f'            {name}.request = {amount} L/h\n')
    text += '        after 1 h:\n' + ''.join(writes) + '        after 3 h\n'
    if declared:
        text += """provider:
    share = solver:
        inputs:
            supply = plant.supply
        solve_for:
            supply.actual_rate
"""
    return compile_text(text + 'plant.retire.start()\nplant.watch.start()\n', UNITS)


@pytest.mark.parametrize('method', [None, Lines, DeclaredWay], ids=['reference', 'held', 'declared'])
def test_every_grouped_violation_is_ordered_and_the_text_truncates_at_five(method):
    model = several_stocks(declared=method is DeclaredWay)
    if method is None:
        reference, error = run_of(model.program, model.configuration)
        assert reference.view.t == 2
        violations, message = error.violations, str(error)
    else:
        engine, record = run(model)
        assert type(engine.ways.instance_of('plant.watch#0.alpha_outflow_z')) is method
        assert record.failure is not None and record.end == 2
        violations, message = record.failure.detail('violations'), record.failure.detail('message')
    expected = tuple(
        (f'plant.retire#0.{field}', side, f'plant.watch#0.{field}_{side}_{suffix}')
        for field in ('alpha', 'zeta')
        for side in ('outflow', 'inflow')
        for suffix in ('z', 'a')
    )
    assert violations == expected
    positions = [message.index(leg) for _, _, leg in expected[:5]]
    assert positions == sorted(positions)
    assert all(leg not in message for _, _, leg in expected[5:])
    assert '3 more' in message


@pytest.mark.parametrize(
    'rate,direction,side', [('0.125', 'forward', 'outflow'), ('-0.125', 'backward', 'inflow')]
)
def test_a_reversible_connection_reports_its_directed_leg(rate, direction, side):
    model = compile_text(
        f"""scenario "A frozen directed route leg"
    horizon 3 h
plant:
    water: L = 10 L in [0,]
    retire = event():
        batch: L = 0 L scale 1000000000 L
        after 1 h
    watch = event():
        job = this.retire.occurrences.at(t)
        flow link: job.batch <-> this.water
            request = 0 L/h
        after 1 h:
            link.request = {rate} L/h
        after 3 h
plant.retire.start()
plant.watch.start()
""",
        UNITS,
    )
    reference, error = run_of(model.program, model.configuration)
    expected = (('plant.retire#0.batch', side, f'plant.watch#0.link.{direction}'),)
    assert reference.view.t == Fraction(9, 5) and error.violations == expected
    _, record = run(model)
    assert record.failure is not None and record.end == 1.8
    assert record.failure.detail('violations') == expected


@pytest.mark.parametrize('window,both', [(0.199, False), (0.2, True)])
def test_crossing_window_includes_its_edge(window, both):
    model = opposing('0.125', '0.1')
    numerics = replace(model.configuration.numerics, crossing=window)
    model = replace(model, configuration=replace(model.configuration, numerics=numerics))
    reference, error = run_of(model.program, model.configuration)
    inward = ('plant.retire#0.batch', 'inflow', 'plant.watch#0.inward')
    outward = ('plant.retire#0.batch', 'outflow', 'plant.watch#0.outward')
    expected = (outward, inward) if both else (inward,)
    assert reference.view.t == Fraction(9, 5) and error.violations == expected
    _, record = run(model)
    assert record.failure is not None and record.end == 1.8
    assert record.failure.detail('violations') == expected
