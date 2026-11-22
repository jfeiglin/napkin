"""Elapsed restarts when a stage changes the exact inventory of a stock."""

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.from_program import run_of, values_at


@pytest.mark.parametrize('posting', ['0.0000000001', '0'], ids=['sub-ulp', 'zero'])
@pytest.mark.parametrize('moving', [False, True], ids=['held', 'linear'])
def test_an_exact_stock_posting_sets_the_same_clock_in_the_stage_event_and_record(posting, moving):
    inlet = '    flow fill: SOURCE -> this.stock\n        request = 1 L/h\n' if moving else ''
    source = f"""scenario "A clock on the physical balance"
    horizon 1.5 h
yard:
    stock: L = 4000000 L
    cup: L = 0 L
    inside: h = 0 h
    later: h = 0 h
    age = formula(elapsed(this.stock))
{inlet}    inspect = event():
        after 1 h:
            move {posting} L from this.stock to this.cup
            this.inside = elapsed(this.stock)
        after 0.5 h:
            this.later = elapsed(this.stock)
yard.inspect.start()
"""
    model = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}})
    keys = [Key('yard', (field,)) for field in ('inside', 'later', 'age')]
    expected = (0, 0.5, 0.5) if posting != '0' else (1, 1.5, 1.5)
    oracle, failure = run_of(model.program, model.configuration)
    assert failure is None, failure
    reference = values_at(oracle, model.program, keys, [1.5])
    assert tuple(reference[key][0] for key in keys) == expected
    record = run(model.program, model.configuration)
    assert record.failure is None, record.failure
    observed = read(record, model.program, keys, [1.5])
    assert tuple(row.values[0] for row in observed) == expected
