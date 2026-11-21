"""Whole-balance precision through adjustments, checkpoint edits and recorded cutoffs."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read, resume
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.record import Key

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
STOCK = """scenario "Inventory edits"
    horizon 1 h
yard:
    tank: L = 10000000 L in [0 L,]
    cash: L = 0.0000000003 L in [0 L,]
    bulk: L = 0 L
    refund: L = 0 L
    flow inactive: SOURCE -> this.tank
        request = 0 L/h
    adjust = event():
        after 0.25 h:
            move this.cash from this.cash to this.tank
        after 0.75 h:
            BODY
yard.adjust.start()
"""


def test_a_stock_increment_then_decrement_keeps_the_carried_remainder():
    actions = [
        'this.tank += 1 L',
        'this.tank -= 1 L',
        'move 10000000 L from this.tank to this.bulk',
        'move this.tank from this.tank to this.refund',
    ]
    model = compile_text(STOCK.replace('BODY', '\n            '.join(actions)), UNITS)
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None, record.failure
    assert [row.values for row in read(record, model.program, ['yard.tank', 'yard.refund'], [1])] == [
        (0,),
        (3e-10,),
    ]


@pytest.mark.parametrize('replacement', [10_000_000, 10_000_001])
@pytest.mark.parametrize('stop', ['yard.adjust.step[1]', 'yard.adjust.step[1].do[0]'])
def test_checkpoint_edit_books_its_difference_from_the_physical_balance(replacement, stop):
    model = compile_text(STOCK.replace('BODY', 'this.bulk = 1 L'), UNITS)
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint(stop),))
    live.run()
    checkpoint = live.edit('yard.tank', replacement)
    saved = dumps(checkpoint)
    record = live.resume()
    assert resume(model.program, loads(saved)) == record
    assert record.failure is None, record.failure
    expected = float(replacement - 10_000_000 - Fraction(3, 10_000_000_000))
    tank, external = read(record, model.program, ['yard.tank', 'yard.tank.external'], [0.5, 1])
    assert tank.values == (10_000_000, replacement)
    assert external.values == (0, expected)


@pytest.mark.parametrize('sparse', [False, True])
def test_recorded_stock_at_horizon_is_the_same_rounded_balance_a_stage_can_spend(sparse, monkeypatch):
    from napkin.engine.timeline import plan

    monkeypatch.setattr(plan, 'LIMIT', 0 if sparse else 150)
    source = """scenario "Horizon"
    horizon 1 h
plant:
    pool: L = 10000000 L
    donor: L = 1 L
    flow leg: this.donor -> this.pool
        request = formula(0.1 L/h * (t / (1 h)))
    reported_pool = formula(this.pool)
"""
    model = compile_text(source, UNITS)
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None, record.failure
    delivered = Fraction(1, 20)
    for name, balance in (('plant.pool', 10_000_000 + delivered), ('plant.donor', 1 - delivered)):
        assert machine.stock_balance(name, 1) == balance
        assert read(record, model.program, [name], [1])[0].values == (float(balance),)
    assert record.history(Key('plant', ('reported_pool',))).at(1) == float(10_000_000 + delivered)
