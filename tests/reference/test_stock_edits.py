"""A planned transfer owns a stock's opening and subsequent edits before it first moves."""

from fractions import Fraction

import pytest

from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
STOCK = Key('box', ('stock',))
RECEIPT = Key('box', ('receipt',))


def edits(run):
    return [(row[2].name, row[3]) for row in run.ledger if row[0] == 'edit']


def test_an_edit_before_the_first_move_is_a_transfer_from_outside():
    model = compile_text(
        """scenario "Edit before a planned move"
    horizon 1 h
box:
    stock: L = 0 L
    receipt: L = 0 L
    send = event():
        after 1 h:
            move 5 L from this.stock to this.receipt
box.send.start()
""",
        UNITS,
    )
    run, error = run_of(model.program, model.configuration, [('box.send.step[0]', None, [(STOCK, 5)])])
    assert error is None, error
    assert value_at(run, model.program, RECEIPT, 1) == 5
    assert edits(run) == [('stock', 5)]
    assert run.conservation()['opening'] == 0 and run.conservation()['balanced']


@pytest.mark.parametrize('withdraw', [5, 6])
def test_an_edit_after_a_staged_move_is_booked_with_its_stage(withdraw):
    model = compile_text(
        f"""scenario "Edit between statements"
    horizon 1 h
box:
    stock: L = 0 L in [0 L,]
    supply: L = 2 L
    receipt: L = 0 L
    send = event():
        after 1 h:
            move 2 L from this.supply to this.stock
            move {withdraw} L from this.stock to this.receipt
box.send.start()
""",
        UNITS,
    )
    run, error = run_of(
        model.program,
        model.configuration,
        [('box.send.step[0].do[1]', None, [(STOCK, Fraction(13, 4)), (STOCK, 5)])],
    )
    assert (error is None) == (withdraw == 5)
    assert edits(run) == ([('stock', Fraction(5, 4)), ('stock', Fraction(7, 4))] if withdraw == 5 else [])
    assert value_at(run, model.program, RECEIPT, 1) == (5 if withdraw == 5 else 0)
    assert run.conservation()['balanced']


def test_an_unstarted_event_with_an_entity_parameter_identifies_only_its_possible_stocks():
    model = compile_text(
        """scenario "Possible stock owners"
    horizon 1 h
Bin:
    stock: L = 2 L
a: Bin
b: Bin
box:
    stock: L = 99 L
    receipt: L = 0 L
    send = event(src: Bin):
        after 1 h:
            move 2 L from src.stock to this.receipt
""",
        UNITS,
    )
    run, error = run_of(model.program, model.configuration)
    assert error is None, error
    assert {(cell.owner.id, cell.name) for cell in run.stores} == {
        ('a', 'stock'),
        ('b', 'stock'),
        ('box', 'receipt'),
    }
    assert run.conservation()['opening'] == 4


def test_an_occurrence_owns_its_move_only_local_from_its_start():
    model = compile_text(
        """scenario "Edit a new occurrence"
    horizon 1 h
box:
    receipt: L = 0 L
    send = event():
        stock: L = 0 L
        after 1 h:
            move 5 L from stock to this.receipt
box.send.start()
""",
        UNITS,
    )
    slot = Key('box.send#0', ('stock',))
    run, error = run_of(model.program, model.configuration, [('box.send.step[0]', None, [(slot, 5)])])
    assert error is None, error
    assert edits(run) == [('stock', 5)]
    assert value_at(run, model.program, RECEIPT, 1) == 5 and run.conservation()['balanced']


def test_only_the_endpoints_of_declared_transfers_are_stocks_even_when_no_transfer_runs():
    model = compile_text(
        """scenario "Stock roles"
    horizon 1 h
box:
    stored: L = 4 L
    counter = 8
    share: ratio = 6 ratio
    source = 3
    receipt = 0
    configured: L = 7 L
        inflow.capacity = 1 L/h
    change = event():
        after 1 h:
            this.counter += 2
            this.share += 1 ratio
            this.stored += 5 L
    idle = event():
        after 1 h:
            move 1 from this.source to this.receipt
box.change.start()
""",
        {**UNITS, 'ratio': ({}, Fraction(1, 100))},
    )
    run, error = run_of(model.program, model.configuration)
    assert error is None, error
    assert {cell.name for cell in run.stores} == {'source', 'receipt'}
    assert run.conservation()['opening'] == 3
    assert run.conservation()['write'] == 0 and run.conservation()['balanced']
