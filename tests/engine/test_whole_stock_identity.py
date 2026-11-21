"""An atomic move of the stock itself can spend the part lost when its balance was rounded."""

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import use_method
from tests.reference.from_program import run_of, value_at

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


def specimen(spelling, floor=0, upper=None):
    room = f' in [0 L, {upper} L]' if upper else ' in [0 L,]'
    text = f"""plant:
    batch: L = 4000000 L in [{floor} L,]
    cash: L = 1 L in [0 L,]
    bulk: L = 0 L{room}
    principal: L = 0 L
    receipt: L = 0 L
    captured: L = 0 L
    alias = formula(this.cash)
    indirect = formula(this.alias)
    sweep = event():
        after 1 h:
            move (2 L / 3) from this.cash to this.batch
            this.captured = this.batch
            this.alias = formula(this.batch)
            move {spelling} from this.batch to this.bulk
        after 0 h:
            move 3999999 L from this.bulk to this.principal
            move this.bulk from this.bulk to this.receipt
plant.sweep.start()
"""
    program = compile_text(text, UNITS).program
    record = run(program, Configuration(Request(1)))
    actual = {
        row.path: row.values[0]
        for row in read(record, program, ['plant.batch', 'plant.cash', 'plant.bulk', 'plant.receipt'], [1])
    }
    return record, actual


@pytest.mark.parametrize('name', ['this.batch', 'this.alias', 'this.indirect'])
def test_direct_and_live_formula_chain_spend_the_full_balance_after_a_stage_write(name):
    record, final = specimen(name)
    assert record.failure is None, record.failure
    assert final['plant.batch'] == final['plant.bulk'] == 0
    assert final['plant.receipt'] == float(Fraction(5, 3))
    assert final['plant.cash'] == float(Fraction(1, 3))


@pytest.mark.parametrize('expression', ['this.batch + 0 L', 'this.captured', 'this.batch - 1 L'])
def test_an_ordinary_amount_uses_its_evaluated_number(expression):
    record, final = specimen(expression)
    assert record.failure is None, record.failure
    rounded = Fraction(str(float(4_000_000 + Fraction(2, 3))))
    requested = rounded - (1 if expression.endswith('- 1 L') else 0)
    assert final['plant.batch'] == float(4_000_000 + Fraction(2, 3) - requested)
    assert final['plant.receipt'] == float(requested - 3_999_999)


@pytest.mark.parametrize('floor, upper', [(1, None), (0, 4000000)])
def test_whole_balance_must_fit_both_ends_and_rollback_the_entire_stage(floor, upper):
    record, final = specimen('this.indirect', floor, upper)
    assert record.failure is not None and record.failure.t == 1
    assert 'outside its range' in record.failure.detail('message')
    assert record.entries('move') == ()
    assert final == {'plant.batch': 4000000, 'plant.cash': 1, 'plant.bulk': 0, 'plant.receipt': 0}


@pytest.mark.parametrize(
    'method, way_type',
    [
        ('family', 'Family'),
        ('lines', 'Lines'),
        ('component', 'ComponentWay'),
        ('sparse', 'Sparse'),
        ('declared', 'DeclaredWay'),
        ('moving_declared', 'MovingDeclared'),
    ],
)
def test_a_stage_can_move_the_residual_held_back_from_a_pipe(method, way_type, monkeypatch):
    text = """scenario "An allocated floor with a spendable residual"
    horizon 1 h
yard:
    stock: L = 0.0000000001 L in [0 L,]
    receipt: L = 0 L
    flow pipe: this.stock -> SINK
        request = 1 L/h
        capacity = 1 L/h
    collect = event():
        after 1 h:
            move this.stock from this.stock to this.receipt
yard.collect.start()
"""
    model = use_method(text, method, monkeypatch, 'pipe')
    oracle, error = run_of(model.program, model.configuration)
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert error is None and record.failure is None
    assert type(machine.ways.instance_of('yard.pipe')).__name__ == way_type
    assert value_at(oracle, model.program, Key('yard', ('receipt',)), 1) == Fraction(1, 10**10)
    rate, stock, receipt = read(
        record, model.program, ['yard.pipe.actual_rate', 'yard.stock', 'yard.receipt'], [0, 1]
    )
    assert list(rate.values) == [0, 0]
    assert list(stock.values) == [1e-10, 0]
    assert list(receipt.values) == [0, 1e-10]
    assert [entry.detail('amount') for entry in record.entries('move')] == [1e-10]
