"""Whole-balance precision through adjustments, checkpoint edits and recorded cutoffs."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read, resume
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.record import Key
from tests.engine.resume_parity import assert_resume_parity

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
    assert_resume_parity(model.program, model.configuration, record, resume(model.program, loads(saved)))
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


def test_two_external_edits_keep_their_small_net_transfer_after_a_restore():
    model = compile_text(
        """scenario "Two external transfers"
    horizon 1 h
yard:
    tank: L = 0 L
    got: L = 0 L
    mark = event():
        after 0.25 h
        after 0.5 h:
            move 1 L from this.tank to this.got
yard.mark.start()
""",
        UNITS,
    )
    stops = tuple(Breakpoint(f'yard.mark.step[{k}]') for k in range(2))
    machine = Run(Plan.of(model.program, model.configuration), stops)
    machine.run()
    machine.edit('yard.tank', Fraction(10**16 + 1))
    machine.resume()
    saved = machine.edit('yard.tank', 1)
    for record in (machine.resume(), resume(model.program, loads(dumps(saved)))):
        assert record.failure is None
        ledger = read(record, model.program, ['yard.tank.external'], [0, 0.5, 1])[0]
        assert ledger.values == (0, 1e16, 1)


def test_restore_of_an_unposted_legacy_stock_keeps_its_opening_and_incoming_incidence():
    model = compile_text(
        """scenario "Old posting cursors"
    horizon 1 h
yard:
    tank: L = 3 L
    reserve: L = 4000000.0000000001 L
    got: L = 0 L
    flow fill: SOURCE -> this.tank
        request = 2 L/h
    mark = event():
        after 0.5 h:
            move 4000000 L from this.reserve to this.got
yard.mark.start()
""",
        UNITS,
    )
    machine = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.mark.step[0]'),))
    checkpoint = machine.run()
    parts = dict(checkpoint.saved)
    state = dict(parts['run'])
    state.pop('stock_ranges')
    state['stocks'] = tuple(
        (name, entry) for name, entry in state['stocks'] if name not in ('yard.tank', 'yard.reserve')
    )
    parts['run'] = tuple(state.items())
    legacy = loads(dumps(replace(checkpoint, saved=tuple(parts.items()))))
    restored = Run.restored(Plan.of(model.program, model.configuration), legacy)
    record = restored.resume()
    assert record.failure is None
    assert restored.stock_balance('yard.tank', 1) == 5
    assert restored.stock_balance('yard.reserve', 1) == Fraction(1, 10**10)
