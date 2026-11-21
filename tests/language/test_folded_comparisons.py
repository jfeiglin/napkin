"""A mixed-unit constant takes the same comparison band in the compiler as in the run."""

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.semantic import exact_value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.program.examples import UNITS
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize(
    ('operand', 'expected'),
    [
        ('0.00000001 h + 0 day', 1),
        ('0 day + 0.00000001 h', 1),
        ('max(0.00000001 h, 0 day)', 1),
        ('(0.00000001 h + 0 day) if true else (1 h / 0)', 1),
        ('0.00000003 h + 0 day', 10),
        ('(0.100000024 h + 0 day) - 0.1 h', 1),
        ('((0.100000024 h + 0 day) if true else this.unused) - 0.1 h', 1),
        ('(0.1000000240001 h + 0 day) - 0.1 h', 10),
        ('(0.100000024000000001 h + 0 day) - 0.1 h', 10),
    ],
)
def test_a_mixed_unit_initializer_keeps_its_value_in_a_singleton_range(operand, expected):
    # The literal sum has a floor of one day, 24 h. Its band is 0.000000024 h.
    units = {**UNITS, 'day': ({'time': 1}, 24)}
    text = f'w:\n    input unused: h = 2 h\n    delay: h = 10 h if ({operand}) > 0 h else 1 h'
    plain = compile_text(text + '\n', units)
    config = Configuration(Request(0))
    record = run(plain.program, config)
    assert record.failure is None, record.failure
    assert read(record, plain.program, ['w.delay'], [0])[0].values == (expected,)
    oracle, failure = run_of(plain.program, config)
    assert failure is None, failure
    assert value_at(oracle, plain.program, Key('w', ('delay',)), 0) == expected
    ranged = compile_text(text + f' in [{expected} h, {expected} h]\n', units)
    value = ranged.declared.part('w.delay')
    assert exact_value(value.init, ranged.declared.units) == Fraction(expected)


def test_literal_gap_uses_the_active_factor_for_scalar_and_array_reads():
    from napkin.core import arrays, expr
    from napkin.core.evaluation import checked_value
    from napkin.core.units import UnitSystem

    units = UnitSystem({'h': {'dimensions': {'time': 1}}, 'day': {'dimensions': {'time': 1}, 'scale': 24}})
    test = expr.read("q(0.100000024, 'h') + q(0, 'day') > q(0.1, 'h')")
    # The closed gap is 24e-9 h. Halving that band makes the same gap strictly greater.
    for factor, expected in [(1e-9, False), (5e-10, True), (1e-9, False)]:
        units.comparisons.factor = factor
        assert checked_value(test, {}, units) == expected
        assert arrays.values(test, {}, units, 2) == expected
