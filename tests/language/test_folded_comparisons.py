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
        ('0.00000001 h + 0 day', 10),
        ('0 day + 0.00000001 h', 10),
        ('max(0.00000001 h, 0 day)', 10),
        ('(0.00000001 h + 0 day) if true else (1 h / 0)', 10),
        ('0.00000003 h + 0 day', 10),
        ('(0.100000024 h + 0 day) - 0.1 h', 10),
        ('((0.100000024 h + 0 day) if true else this.unused) - 0.1 h', 10),
        ('(0.1000000240001 h + 0 day) - 0.1 h', 10),
        ('(0.100000024000000001 h + 0 day) - 0.1 h', 10),
    ],
)
def test_a_mixed_unit_initializer_keeps_its_value_in_a_singleton_range(operand, expected):
    # The exact offset introduces no floor. Each positive gap exceeds its relative band.
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
    for factor in (1e-9, 5e-10, 1e-9):
        units.comparisons.factor = factor
        assert checked_value(test, {}, units)
        assert arrays.values(test, {}, units, 2)
    # At 1 h the relative band is 1e-9 h. The gap is exactly on its closed edge.
    test = expr.read("q(1, 'h') + q(0, 'day') > q(0.999999999, 'h')")
    for factor, expected in [(1e-9, False), (5e-10, True), (1e-9, False)]:
        units.comparisons.factor = factor
        assert checked_value(test, {}, units) == expected
        assert arrays.values(test, {}, units, 2) == expected


@pytest.mark.parametrize(
    ('operand', 'amount'),
    [
        ('(0.100000024 h + 0 day) - 0.1 h', Fraction('0.000000024')),
        ('1000000000.00000005 h - 1000000000 h', Fraction('0.00000005')),
    ],
)
def test_a_named_literal_residual_and_its_guards_agree_with_the_oracle(operand, amount):
    units = {**UNITS, 'day': ({'time': 1}, 24)}
    model = compile_text(
        f'scenario "Exact residual"\n    horizon 1 h\n'
        f'gap = formula({operand})\nnamed_guard = formula(gap > 0 h)\n'
        f'inline_guard = formula(({operand}) > 0 h)\n',
        units,
    )
    record = run(model.program, model.configuration)
    oracle, failure = run_of(model.program, model.configuration)
    assert record.failure is None and failure is None
    for path, expected in [('gap', float(amount)), ('named_guard', True), ('inline_guard', True)]:
        assert read(record, model.program, [path], [1])[0].values == (expected,)
        assert float(value_at(oracle, model.program, Key('', (path,)), 1)) == expected


def test_array_and_scalar_guards_use_each_rows_exact_operand():
    import numpy as np

    from napkin.core import arrays, expr
    from napkin.core.evaluation import checked_value
    from napkin.core.units import UnitSystem
    from napkin.program.build import q

    units = UnitSystem({'h': {'dimensions': {'time': 1}}})
    operands = {
        'above': q(Fraction('1000000000.00000005'), 'h')._node,
        'equal': q(1000000000, 'h')._node,
    }
    units.comparisons.named = lambda name: (1, operands[name])
    threshold = "q(1000000000, 'h')"
    test = expr.read(f'(cell - {threshold}) > 0')
    for name, expected in [('above', True), ('equal', False)]:
        assert checked_value(expr.read(f'({name} - {threshold}) > 0'), {name: 1e9}, units) is expected
    found = arrays.values(test, {'cell': np.array([1e9, 1e9])}, units, 2, {'cell': ('above', 'equal')})
    assert found.tolist() == [True, False]


@pytest.mark.parametrize(
    ('threshold', 'greater'),
    [
        ('0.999999999 h', False),
        ('0.999999998999999999 h', True),
    ],
)
def test_a_literal_just_outside_the_closed_relative_band_retains_its_decimal(threshold, greater):
    model = compile_text(
        f'scenario "Closed relative band"\n    horizon 1 h\n'
        f'edge = formula({threshold})\nnamed_check = formula(1 h > edge)\n'
        f'inline_check = formula(1 h > {threshold})\n',
        UNITS,
    )
    record = run(model.program, model.configuration)
    assert record.failure is None
    assert [row.values for row in read(record, model.program, ['named_check', 'inline_check'], [0])] == [
        (greater,),
        (greater,),
    ]
