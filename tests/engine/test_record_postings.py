"""Committed stock changes remain observable between two time boundaries."""

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

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
