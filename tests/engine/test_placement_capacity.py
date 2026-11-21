"""A grouped stock target cannot change a directed amount past an authored capacity."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import use_method
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize(
    ('setting', 'method'),
    [
        (setting, method)
        for setting in ('pipe', 'inflow', 'outflow')
        for method in ('lines', 'sparse', 'declared', 'moving_declared')
    ]
    + [('pipe', 'component')],
)
@pytest.mark.parametrize(
    'gap', [Fraction('0.0000000001'), Fraction('0.000000005')], ids=['within', 'outside']
)
def test_a_placement_respects_the_integrated_pipe_or_endpoint_capacity(setting, method, gap, monkeypatch):
    rising = setting != 'outflow'
    ends = (
        ('this.first -> this.tank', 'this.second -> this.tank')
        if rising
        else (
            'this.tank -> this.first',
            'this.tank -> this.second',
        )
    )
    stock_setting = '' if setting == 'pipe' else f'\n        {setting}.capacity = 1 L/h'
    small_cap = '\n        capacity = 0.25 L/h' if setting == 'pipe' else ''
    large_cap = '\n        capacity = 0.75 L/h' if setting == 'pipe' else ''
    comparison, sign = ('>=', 1) if rising else ('<=', -1)
    target = 1 + sign * gap
    text = f"""scenario "Preserve the accepted capacity at a grouped threshold"
    horizon 1 h
yard:
    tank: L = {0 if rising else 2} L{stock_setting}
    first: L = 10 L
    second: L = 10 L
    flow small: {ends[0]}
        request = 0.25 L/h{small_cap}
    flow large: {ends[1]}
        request = 0.75 L/h{large_cap}
    watch = event():
        when this.tank {comparison} {float(target)} L:
            this.watch.start()
        after 0 h
    clock = event():
        after 1 h
yard.clock.start()
"""
    model = use_method(text, method, monkeypatch, 'large')
    oracle, error = run_of(model.program, model.configuration)
    run = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.clock.step[0]'),))
    stop = run.run()
    totals = {'yard.small': Fraction(1, 4), 'yard.large': Fraction(3, 4)}
    accepted = {name: run.ways.instance_of(name).transferred(name, 1) for name in totals}
    for name, target_amount in totals.items():
        assert float(accepted[name]) == pytest.approx(float(target_amount), rel=0, abs=5e-16)
    # Both ends of each leg read precisely the same accepted amount, even when an
    # integration carries a sub-ulp difference from the analytical quarter litre.
    balances = {
        'tank': (0 if rising else 2) + sign * sum(accepted.values()),
        'first': 10 - sign * accepted['yard.small'],
        'second': 10 - sign * accepted['yard.large'],
    }
    for name, actual in balances.items():
        assert run.stock_balance('yard.' + name, 1) == actual
    outside = gap > Fraction('0.000000001')
    if outside:
        record = stop
        assert record.failure is not None and error is not None
        assert tuple(error.placements) == (('yard.tank', 1, target),)
        assert tuple(record.failure.detail('placements')) == (
            ('yard.tank', float(balances['tank']), float(target)),
        )
    else:
        assert isinstance(stop, Checkpoint)
        record = run.resume()
        assert record.failure is None and error is None
    assert record.end == oracle.view.t == 1
    assert [entry.t for entry in record.entries('fire')] == ([] if outside else [1])
    assert [entry.t for entry in oracle.trace if entry.kind == 'fire'] == ([] if outside else [1])
    for name, expected in [('tank', 1), ('first', 10 - sign / 4), ('second', 10 - 3 * sign / 4)]:
        key = Key('yard', (name,))
        assert value_at(oracle, model.program, key, 1) == expected
        assert record.history(key).at(1) == float(balances[name])
    assert {row[3]: row[6] for row in oracle.ledger if row[0] == 'flow' and row[2] == 1} == totals


@pytest.mark.parametrize('method', ['family', 'lines', 'component', 'sparse', 'declared', 'moving_declared'])
def test_all_simultaneous_refused_targets_are_reported_in_stock_order(method, monkeypatch):
    text = """scenario "Two independent hard caps and one cutoff"
    horizon 1 h
yard:
    z: L = 0 L
    a: L = 0 L
    flow z_pipe: SOURCE -> this.z
        request = 1 L/h
        capacity = 1 L/h
    flow a_pipe: SOURCE -> this.a
        request = 1 L/h
        capacity = 1 L/h
    watch_z = event():
        when this.z >= 1.000000005 L:
            this.watch_z.start()
        after 0 h
    watch_a = event():
        when this.a >= 1.000000005 L:
            this.watch_a.start()
        after 0 h
    clock = event():
        after 1 h
yard.clock.start()
"""
    model = use_method(text, method, monkeypatch, 'z_pipe')
    oracle, error = run_of(model.program, model.configuration)
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.end == oracle.view.t == 1
    assert record.failure is not None and error is not None
    names = ('yard.a', 'yard.z')
    target = Fraction('1.000000005')
    expected = []
    for stock in names:
        leg = stock + '_pipe'
        total = run.ways.instance_of(leg).transferred(leg, 1)
        assert run.stock_balance(stock, 1) == total
        assert float(total) == pytest.approx(1, abs=2e-15, rel=0)
        expected.append((stock, float(total), float(target)))
    assert tuple(error.placements) == tuple((name, 1, target) for name in names)
    assert tuple(record.failure.detail('placements')) == tuple(expected)
    assert not record.entries('fire')
    assert not [e for e in oracle.trace if e.kind == 'fire']
