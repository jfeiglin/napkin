"""The unit of an expression of typed nodes (`napkin/core/units.py`).

The dimensions of a product, a quotient, a power and a root are checked against a walk of the node that
this file writes: it adds and scales the powers of the dimensions. The other rules are checked on
cases whose unit follows from the rule itself, and each rule is shown to reject what it must reject.
"""

import json
import random
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.core import expr, ops, units
from napkin.core.errors import ExpressionError
from tests.units import library

REGISTRY = units.UnitSystem(library()['units'])
UNIT = REGISTRY.parse_unit
SYMBOLS = {
    't': UNIT('h'),
    'n': UNIT('people'),
    'r': UNIT('people/h'),
    'x': units.NUMBER,
    'ok': units.BOOLEAN,
    'mode': units.STRING,
}
PLAIN, TIME, PEOPLE, RATE = {}, {'time': 1}, {'people': 1}, {'people': 1, 'time': -1}


def found(source, symbols=SYMBOLS):
    return units.unit_of(expr.read(source), symbols, REGISTRY)


def powers(node):
    """The powers of the dimensions of a product, a quotient, a power or a root of the symbols."""
    if isinstance(node, expr.Ref):
        return dict(SYMBOLS[node.name].dimensions)
    if isinstance(node, expr.Const):
        return {}
    if isinstance(node, expr.Call):
        (inner,) = node.args
        return {name: power / 2 for name, power in powers(inner).items()}
    left, right = powers(node.left), powers(node.right)
    if node.op == 'pow':
        return {name: power * node.right.value for name, power in left.items() if power * node.right.value}
    sign = 1 if node.op == 'mul' else -1
    total = {name: left.get(name, 0) + sign * right.get(name, 0) for name in {*left, *right}}
    return {name: power for name, power in total.items() if power}


def made(rng, depth):
    if depth == 0 or rng.random() < 0.25:
        return expr.ref(rng.choice(('t', 'n', 'r', 'x')))
    kind = rng.randrange(6)
    if kind < 2:
        return expr.binary('mul', made(rng, depth - 1), made(rng, depth - 1))
    if kind < 4:
        return expr.binary('div', made(rng, depth - 1), made(rng, depth - 1))
    if kind == 4:
        return expr.binary('pow', made(rng, depth - 1), expr.const(rng.choice((2, 3, -1, 0.5, -2))))
    return expr.call('sqrt', [made(rng, depth - 1)])


def test_the_dimensions_of_products_quotients_powers_and_roots_are_the_sums_of_the_powers():
    rng, seen = random.Random(20261112), set()
    for _ in range(1500):
        node = made(rng, rng.randrange(1, 6))
        unit, names = units.unit_of(node, SYMBOLS, REGISTRY)
        want = powers(node)
        assert dict(unit.dimensions) == pytest.approx(want) and unit.dimensions == tuple(
            sorted(unit.dimensions)
        )
        assert (unit.kind, unit.scale) == ('number', 1.0) and names == expr.names(node)
        seen.add(tuple(sorted(want)))
    assert len(seen) >= 4  # plain numbers, times, people and mixed units all came up


@pytest.mark.parametrize(
    'source, kind, dimensions',
    [
        # number: the unit of the argument.
        ('-t', 'number', TIME),
        ('+r', 'number', RATE),
        ('abs(n - n)', 'number', PEOPLE),
        # condition and compared: a yes/no.
        ('not ok', 'boolean', PLAIN),
        ('ok and t > t or not ok', 'boolean', PLAIN),
        ('t < t <= t', 'boolean', PLAIN),
        ("mode == 'open'", 'boolean', PLAIN),
        ('ok != ok', 'boolean', PLAIN),
        ('t > 0', 'boolean', PLAIN),
        # choice and same: the one unit of the branches or of the arguments; a plain zero has every unit.
        ('t if ok else 0', 'number', TIME),
        ('0 if ok else n', 'number', PEOPLE),
        ('n + n - 0', 'number', PEOPLE),
        ('min(t, 0, t)', 'number', TIME),
        ('max(r)', 'number', RATE),
        ('clip(t, 0, t)', 'number', TIME),
        # membership: a value and the ends of its interval in one unit, and a yes/no.
        ('within(t, 0, t)', 'boolean', PLAIN),
        ('0 + 0', 'zero', PLAIN),
        # plain: a plain number in, a plain number out.
        ('exp(x) + ln(x) + expm1(x) + log1p(x) + erf(x)', 'number', PLAIN),
        ('exp(t / t)', 'number', PLAIN),
        # literal: the unit that is written, in execution units.
        ("q(2, 'days')", 'number', TIME),
        ("q(x, 'people/h') * t", 'number', PEOPLE),
        # power: a written exponent keeps the unit to that power; another exponent needs a plain base.
        ('t ** -2', 'number', {'time': -2}),
        ('x ** x', 'number', PLAIN),
        ('(t / t) ** x', 'number', PLAIN),
    ],
)
def test_the_unit_of_each_rule(source, kind, dimensions):
    unit, _ = found(source)
    assert (unit.kind, dict(unit.dimensions), unit.scale) == (kind, dimensions, 1.0)


@pytest.mark.parametrize(
    'source, message',
    [
        ('t + n', 'Incompatible quantities'),
        ('t + ok', 'Incompatible quantities'),
        ('ok + ok', 'Arithmetic requires numbers'),
        ('t * ok', 'Arithmetic requires numbers'),
        ('-ok', 'Numeric unary operator on nonnumeric value'),
        ('not t', 'Incompatible quantities'),
        ('t and ok', 'Incompatible quantities'),
        ('t < n', 'Incompatible quantities'),
        ('ok < ok', 'Ordered comparisons require numeric values'),
        ("mode > 'a'", 'Ordered comparisons require numeric values'),
        ('t if t else t', 'Incompatible quantities'),
        ('t if ok else n', 'Incompatible quantities'),
        ('min(t, n)', 'Incompatible quantities'),
        ('min(ok, ok)', 'min/max require numbers'),
        ('clip(t, 0)', 'clip requires exactly three arguments'),
        ('within(t, 0)', 'within requires exactly three arguments'),
        ('within(t, n, t)', 'Incompatible quantities'),
        ('within(ok, ok, ok)', 'A membership tests numbers'),
        ('abs(mode)', 'abs requires numbers'),
        ('exp(t)', 'Incompatible quantities'),
        ('exp(x, x)', 'exp requires exactly one argument'),
        ('sqrt(ok)', 'Powers require numeric quantities'),
        ('t ** x', 'Dimensional powers require a literal exponent'),
        ('x ** t', 'Incompatible quantities'),
        ('t ** 2000', 'Exponent exceeds supported magnitude 1024'),
        ("q(t, 'h')", 'Incompatible quantities'),
        ('q(x, mode)', 'q requires a number and literal registered unit'),
        ("q(x, 'furlongs')", 'Unregistered unit'),
        ('nowhere + 1', "Unknown symbol 'nowhere'"),
        ('t % t', 'Unsupported arithmetic operator'),
        ('t is t', 'Unsupported comparison'),
        ('sinh(x)', 'Unsupported function or keyword arguments'),
        ('[t]', 'Unsupported syntax List'),
        ('1e309', 'Only finite numbers, booleans, and strings are allowed'),
    ],
)
def test_each_rule_rejects_what_breaks_it(source, message):
    with pytest.raises(ExpressionError, match=message):
        found(source)


def test_the_first_error_of_a_reading_from_left_to_right_is_the_one_reported():
    # An error inside an argument comes before an error of the number of arguments.
    with pytest.raises(ExpressionError, match="Unknown symbol 'nowhere'"):
        found('exp(x, nowhere)')
    with pytest.raises(ExpressionError, match='exp requires exactly one argument'):
        found('exp(x, x) + nowhere')
    # A chain is read link by link.
    with pytest.raises(ExpressionError, match='Incompatible quantities'):
        found('t < n is ok')
    with pytest.raises(ExpressionError, match='Unsupported comparison'):
        found('t is n < ok')


def test_each_rule_of_the_contracts_has_its_function_and_each_operation_its_rule():
    assert units.RULES.keys() == ops.UNIT_RULES.keys()
    assert set(units.TABLE) == set(ops.OPERATIONS)
    for name, operation in ops.OPERATIONS.items():
        assert units.TABLE[name] is units.RULES[operation.units]
    # A node of an operation that the language does not have is an error, and no missing key.
    with pytest.raises(ExpressionError, match='Unsupported function'):
        units.unit_of(expr.call('sinh', [expr.ref('x')]), SYMBOLS, REGISTRY)


PLAIN_FUNCTIONS = sorted(name for name, operation in ops.OPERATIONS.items() if operation.units == 'plain')


@pytest.mark.parametrize('name', PLAIN_FUNCTIONS)
def test_a_function_whose_rule_is_plain_takes_a_plain_number_and_gives_one(name):
    """The functions come from the contracts, so this test has a new function with no change. A
    function with the rule `number` in its place takes hours and gives hours: the test refuses it."""
    unit, names = found(f'{name}(x)')
    assert (unit.kind, dict(unit.dimensions), unit.scale) == ('number', PLAIN, 1.0) and names == {'x'}
    # A quotient of two times is a plain number, and the result times a count is a count.
    unit, _ = found(f'{name}(t / t) * n')
    assert dict(unit.dimensions) == PEOPLE
    for argument in ('t', 'n', 'r', 'ok', 'mode'):
        with pytest.raises(ExpressionError, match='Incompatible quantities'):
            found(f'{name}({argument})')
    for arguments in ('x, x', ''):
        with pytest.raises(ExpressionError, match=f'{name} requires exactly one argument'):
            found(f'{name}({arguments})')


def test_a_written_number_with_its_sign_is_a_literal():
    assert [units.literal(expr.read(source)) for source in ('2', '-1', '+0.5', '--3')] == [2, -1, 0.5, 3]
    assert [units.literal(expr.read(source)) for source in ('x', 'True', '2 * 1', "'2'")] == [None] * 4


# ---- the exact scale of a unit as a units file holds it ---------------------------------------------


@settings(derandomize=True, max_examples=300, deadline=None)
@given(st.integers(1, 10**5), st.integers(1, 10**4))
def test_a_ratio_that_a_units_file_holds_as_a_float_is_read_as_the_ratio(numerator, denominator):
    """A units file holds a scale as a JSON number, so a ratio such as the 1/24 of a unit per day is
    the float that a program wrote out for it, 0.041666666666666664. Its exact scale is the ratio
    (`units.scale_of`), for every ratio of whole numbers up to 10^5 over up to 10^4: no other fraction
    that simple rounds to its float, and no decimal that rounds to it is as short as the ratio, since
    one would need 13 digits or more."""
    ratio = Fraction(numerator, denominator)
    filed = json.loads(json.dumps(float(ratio)))
    assert units.scale_of(filed) == ratio


@settings(derandomize=True, max_examples=300, deadline=None)
@given(st.integers(1, 10**12 - 1), st.integers(-25, 10))
def test_a_decimal_that_a_units_file_writes_is_that_decimal(digits, exponent):
    """A decimal of at most 12 significant digits, as a person writes a scale (0.001, 3785411.784),
    is the scale that it writes: it survives its float, the float writes it again, and no fraction
    that rounds to the float is written with fewer digits."""
    written = f'{digits}e{exponent}'
    assert (
        units.scale_of(json.loads(json.dumps(float(written)))) == Fraction(digits) * Fraction(10) ** exponent
    )


@settings(derandomize=True, max_examples=300, deadline=None)
@given(st.floats(min_value=5e-324, allow_nan=False, allow_infinity=False))
def test_every_scale_is_a_fraction_that_rounds_to_the_float_of_its_file(value):
    """Whatever a units file holds, its exact scale rounds to the float that it holds: reading a
    scale exactly never moves it, it only chooses which number the float stood for."""
    assert float(units.scale_of(value)) == value


def test_the_scales_of_the_catalogue_are_their_ratios_and_their_decimals():
    """The library's units per day and per year, a minute, a billion dollars a year and a million
    gallons a year are their ratios; an acre-foot in litres and a gallon are the decimals that define
    them."""
    cases = {
        0.041666666666666664: Fraction(1, 24),
        0.016666666666666666: Fraction(1, 60),
        0.00011415525114155251: Fraction(1, 8760),
        114155.25114155251: Fraction(25_000_000, 219),
        432.1246328767123: Fraction(3_785_411_784, 8_760_000),
        1233481.83754752: Fraction('1233481.83754752'),
        3785411.784: Fraction('3785411.784'),
    }
    for filed, scale in cases.items():
        assert units.scale_of(filed) == scale, filed
