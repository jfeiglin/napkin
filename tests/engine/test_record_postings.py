"""Committed stock changes remain observable between two time boundaries."""

from fractions import Fraction

import pytest

from napkin import store
from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


@pytest.mark.parametrize('selective', (False, True))
def test_a_small_posting_on_a_moving_line_survives_compaction(selective):
    compiled = compile_text(
        """scenario "Moving stock posting"
    horizon 2 h
yard:
    stock: L = 4000000 L
    spare: L = 0 L
    flow fill: SOURCE -> this.stock
        request = 1 L/h
    debit = event():
        after 1 h:
            move 0.0000000003 L from this.stock to this.spare
yard.debit.start()
""",
        UNITS,
    )
    key = Key('yard', ('stock',))
    config = Configuration(Request(2, everything=not selective, keys=(key,) if selective else ()))
    record = run(compiled.program, config)
    assert record.failure is None
    times = (0.5, 1, 1.5, 2)
    expected = tuple(float(4_000_000 + Fraction(t) - (Fraction(3, 10**10) if t >= 1 else 0)) for t in times)
    assert read(record, compiled.program, (key,), times)[0].values == expected


@pytest.mark.parametrize('selective', (False, True), ids=['full', 'selective'])
@pytest.mark.parametrize('posting', ('0.0000000003', '0'), ids=['sub-ulp', 'zero'])
def test_a_sub_ulp_posting_becomes_visible_on_a_drain_below_a_power_of_two(tmp_path, selective, posting):
    # At 1 h the posted and unposted stocks round to the same float. Once the stock falls below
    # 2**22 L the spacing halves, and the same withdrawal changes the reported stock by one ULP.
    compiled = compile_text(
        f"""scenario "A drain crosses a floating point spacing boundary"
    horizon 4 h
yard:
    stock: L = 4194306 L
    spare: L = 0 L
    flow drain: this.stock -> SINK
        request = 1 L/h
    debit = event():
        after 1 h:
            move {posting} L from this.stock to this.spare
yard.debit.start()
""",
        UNITS,
    )
    key = Key('yard', ('stock',))
    cfg = Configuration(Request(4, everything=not selective, keys=(key,) if selective else ()))
    times = (0, 1, 2, 2.5, 3, 4)
    amounts = tuple(4_194_306 - Fraction(t) - (Fraction(posting) if t >= 1 else 0) for t in times)
    oracle, failure = run_of(compiled.program, cfg)
    assert failure is None, failure
    assert tuple(values_at(oracle, compiled.program, [key], times)[key]) == amounts
    expected = tuple(map(float, amounts))
    with store.use(tmp_path / 'store'):
        cold = store.run(compiled.program, cfg)
        cached = store.run(compiled.program, cfg)
    answers = {}
    for source, result in (('fresh', cold), ('cached', cached)):
        assert result.failure is None, result.failure
        answers[source] = read(result, compiled.program, [key], times)[0].values
    assert answers == {'fresh': expected, 'cached': expected}
