"""A hard ceiling limits the integral over the accepted prefix at a grouped threshold."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


@pytest.mark.parametrize(
    'kind,method',
    [
        ('pipe', 'component'),
        ('pipe', 'sparse'),
        ('pipe', 'moving_declared'),
        ('inflow', 'sparse'),
        ('inflow', 'moving_declared'),
        ('outflow', 'sparse'),
        ('outflow', 'moving_declared'),
        ('equation', 'moving_declared'),
    ],
)
@pytest.mark.parametrize('rises', [True, False], ids=['exhausted', 'headroom'])
@pytest.mark.parametrize('cut', [False, True], ids=['continuous', 'resumed'])
def test_a_grouped_placement_uses_the_moving_capacity_over_its_accepted_prefix(
    kind, method, rises, cut, monkeypatch
):
    cap = 't / (1 h) * (1 L/h)' if rises else '(2 - t / (1 h)) * (1 L/h)'
    target = '0.5000000001' if rises else '1.0000000001'
    stock_cap = f'\n        inflow.capacity = formula({cap})' if kind == 'inflow' else ''
    donor_cap = f'\n        outflow.capacity = formula({cap})' if kind == 'outflow' else ''
    pipe_cap = f'\n        capacity = formula({cap})' if kind == 'pipe' else ''
    text = f"""scenario "Moving capacity of a grouped contact"
    horizon 1 h
yard:
    tank: L = 0 L{stock_cap}
    donor: L = 2 L{donor_cap}
    flow fill: this.donor -> this.tank
        request = {2 if rises else 1} L/h{pipe_cap}
    watch = event():
        when this.tank >= {target} L:
            this.watch.start()
        after 0 h
    clock = event():
        after 1 h
"""
    if cut:
        text += """    cut = event():
        after 0.5 h
yard.cut.start()
"""
    text += 'yard.clock.start()\n'
    if method == 'moving_declared':
        text += """owner:
    share = solver:
        inputs:
            pipe = yard.fill
        solve_for:
            pipe.actual_rate
"""
        if kind == 'equation':
            text += f'        constraints:\n            pipe.actual_rate <= {cap}\n'
    model = compile_text(text, UNITS)
    connect = Plan.connect

    def force(plan, *args, **kwargs):
        return [
            replace(group, moves=True) if method == 'moving_declared' else replace(group, way=method)
            for group in connect(plan, *args, **kwargs)
        ]

    monkeypatch.setattr(Plan, 'connect', force)
    stops = [Breakpoint('yard.clock.step[0]')]
    if cut:
        stops.insert(0, Breakpoint('yard.cut.step[0]'))

    def plan():
        return Plan.of(model.program, model.configuration)

    run = Run(plan(), tuple(stops))
    stop = run.run()
    if cut:
        assert isinstance(stop, Checkpoint) and stop.stop.t == 0.5
        run = Run.restored(plan(), loads(dumps(stop)))
        stop = run.resume()
    assert isinstance(stop, Checkpoint) and stop.stop.t == 1, stop
    way = run.ways.instance_of('yard.fill')
    amount = way.transferred('yard.fill', 1)
    assert run.stock_balance('yard.tank', 1) == amount
    assert run.stock_balance('yard.donor', 1) == 2 - amount
    entries = [entry for entry in run.recorder.trace if entry.detail('placements')]
    if rises:
        # A declared endpoint is itself a numerical solve; the accepted integral is
        # within 1e-12 L of the analytic ceiling. The requested placement adds 1e-10 L.
        assert float(amount) == pytest.approx(0.5, abs=1e-12, rel=0)
        assert len(entries) == 1 and entries[0].detail('reason')
    else:
        assert amount == Fraction(target)
        assert not entries
    record = run.resume()
    assert record.end == 1 and record.failure is None
    assert [entry.t for entry in record.entries('fire')] == [1]


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_a_capacity_that_opens_at_the_cut_does_not_cover_earlier_transfers(method, monkeypatch):
    from tests.engine.test_threshold_transfer_placement import use_method

    source = """scenario "A hard capacity opens at the cutoff"
    horizon 1 h
yard:
    tank: L = 0 L
    flow fill: SOURCE -> this.tank
        request = 1 L/h
        capacity = formula(1 L/h if t < 1 h else 1000000 L/h)
    watch = event():
        when this.tank >= 1.0000000001 L:
            this.watch.start()
        after 0 h
    clock = event():
        after 1 h
yard.clock.start()
"""
    model = use_method(source, method, monkeypatch, 'fill')
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None and record.end == 1
    assert float(run.stock_balance('yard.tank', 1)) == pytest.approx(1, abs=5e-15, rel=0)
    assert [entry.t for entry in record.entries('fire')] == [1]
    assert any('yard.fill.capacity' in str(entry.detail('reason')) for entry in record.entries('settle'))
