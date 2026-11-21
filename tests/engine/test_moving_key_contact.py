"""When a collection member's key crosses the query, its new row supplies the outgoing rate."""

from fractions import Fraction

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at


def moving_key_model(filtered, declared=False, ranked=False):
    rows = 'Band.instances.by(level)'
    if filtered:
        rows += '.where(rate >= 0 L/h)'
    text = f"""scenario "Selection across a moving member's key"
    horizon 2 h
Band:
    input pace: L/h = 0 L/h
    input rate: L/h = 1 L/h
    level: L = 0 L
    flow drain: this.level -> SINK
        request = this.pace
        capacity = 1 L/h
low: Band
    level = {2 if ranked else 0} L
high: Band
    level = 3 L
    pace = 1 L/h
    rate = 2 L/h
yard:
    water: L = 0 L
    before: L/h = -1 L/h
    afterward: L/h = -1 L/h
    again: L/h = -1 L/h
    flow inlet: SOURCE -> this.water
        request = formula({rows}.at({10 if ranked else 2} L).rate)
    clock = event():
        after 0.99999999975 h:
            this.before = this.inlet.actual_rate
        after 0 h:
            this.afterward = this.inlet.actual_rate
        after 0.0000000001 h:
            this.again = this.inlet.actual_rate
yard.clock.start()
"""
    if declared:
        text += """owner:
    share = solver:
        inputs:
            inlet = yard.inlet
            drain = high.drain
        solve_for:
            inlet.actual_rate
            drain.actual_rate
"""
    return compile_text(text, {'L': {'volume': 1}, 'h': {'time': 1}})


@pytest.mark.parametrize('filtered', [False, True], ids=['direct', 'filtered'])
def test_reference_uses_the_member_whose_key_crosses_the_query(filtered):
    model = moving_key_model(filtered)
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and oracle.view.t == 2
    at = Fraction('0.99999999975')
    stock = 3 - at
    ties = [entry for entry in oracle.trace if entry.kind == 'near-tie']
    assert [(entry.t, entry.placements) for entry in ties] == [(at, (('high.level', stock, 2),))]
    assert value_at(oracle, model.program, Key('high', ('level',)), at) == stock
    expected = {'before': 1, 'afterward': 2, 'again': 2, 'water': at + 2 * (2 - at)}
    for name, amount in expected.items():
        assert value_at(oracle, model.program, Key('yard', (name,)), 2) == amount


@pytest.mark.parametrize('filtered', [False, True], ids=['direct', 'filtered'])
@pytest.mark.parametrize('declared', [False, True], ids=['sparse', 'moving_declared'])
def test_a_moving_member_key_selects_its_outgoing_row_at_the_grouped_stage(filtered, declared):
    model = moving_key_model(filtered, declared)
    worker = Run(Plan.of(model.program, model.configuration))
    record = worker.run()
    assert record.failure is None and record.end == 2
    assert type(worker.ways.instance_of('yard.inlet')).__name__ == (
        'MovingDeclared' if declared else 'Sparse'
    )
    at = 0.99999999975
    water, before, afterward, again, level = read(
        record,
        model.program,
        ['yard.water', 'yard.before', 'yard.afterward', 'yard.again', 'high.level'],
        [at, 2],
    )
    assert (before.values[1], afterward.values[1], again.values[1]) == (1, 2, 2)
    assert water.values == pytest.approx([at, at + 2 * (2 - at)], abs=1e-13, rel=0)
    assert level.values[0] == pytest.approx(3 - at, abs=2e-14, rel=0)
    ties = [e for e in record.entries('settle') if e.part == 'stock placement']
    assert len(ties) == 1 and ties[0].t == at
    assert ties[0].detail('placements') == (('high.level', level.values[0], 2.0),)


@pytest.mark.parametrize('filtered', [False, True], ids=['direct', 'filtered'])
@pytest.mark.parametrize('declared', [False, True], ids=['sparse', 'moving_declared'])
def test_two_eligible_member_keys_exchange_rank_through_the_grouped_stage(filtered, declared):
    model = moving_key_model(filtered, declared, ranked=True)
    oracle, error = run_of(model.program, model.configuration)
    assert error is None
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None
    at = Fraction('0.99999999975')
    names = ['yard.water', 'yard.before', 'yard.afterward', 'yard.again', 'high.level', 'low.level']
    expected = [2 * at + (2 - at), 2, 1, 1, 1, 2]
    for name, actual, amount in zip(names, read(record, model.program, names, [2]), expected, strict=True):
        owner, member = name.split('.')
        assert value_at(oracle, model.program, Key(owner, (member,)), 2) == amount
        assert actual.values[0] == pytest.approx(float(amount), abs=2e-13, rel=0)
    assert value_at(oracle, model.program, Key('high', ('level',)), at) == 3 - at
    high, low = read(record, model.program, ['high.level', 'low.level'], [float(at)])
    assert high.values[0] == pytest.approx(float(3 - at), abs=2e-14, rel=0)
    assert low.values[0] == 2
