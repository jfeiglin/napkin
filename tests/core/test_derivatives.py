"""The derivative of an expression by a name (`napkin/core/derivatives.py`).

The oracles are independent of the chain rule of the module:

- closed forms that calculus gives for whole expressions;
- for expressions that a generator composes at random from the smooth operations, the slope of the
  expression's own value, by a difference of the fourth order;
- a choice, a bound and a condition, at points away from where they change.
"""

import math
import random

import pytest

from napkin import expressions
from napkin.core import expr
from napkin.core.derivatives import derivative
from napkin.core.errors import ExpressionError
from tests import build as b

UNITS = expressions.UnitSystem(b.library()['units'])


def value(node, env):
    return expressions.evaluate(expr.read(expr.text(node)), env, UNITS)


def slope(node, env, by):
    """The slope of the value of a node along one name: a central difference of the fourth order."""
    h = 1e-3 * max(1.0, abs(env[by]))

    def at(shift):
        return float(value(node, {**env, by: env[by] + shift}))

    return (-at(2 * h) + 8 * at(h) - 8 * at(-h) + at(-2 * h)) / (12 * h)


CLOSED = [
    ('x ** 3 + 2 * x * y', lambda x, y: 3 * x * x + 2 * y),
    ('exp(-y * x)', lambda x, y: -y * math.exp(-y * x)),
    ('ln(1 + x * x)', lambda x, y: 2 * x / (1 + x * x)),
    ('sqrt(x * y) / y', lambda x, y: 0.5 * math.sqrt(y / x) / y),
    ('x / (x + y)', lambda x, y: y / (x + y) ** 2),
    ('expm1(x) - log1p(x)', lambda x, y: math.exp(x) - 1 / (1 + x)),
    ('erf(x / y)', lambda x, y: 2 / math.sqrt(math.pi) * math.exp(-((x / y) ** 2)) / y),
    ('y ** x', lambda x, y: math.log(y) * y**x),
    ('sum(x, x * y, y)', lambda x, y: 1 + y),
    ('-x * abs(y - 5)', lambda x, y: -abs(y - 5)),
]


@pytest.mark.parametrize(('text', 'exact'), CLOSED)
def test_the_derivative_of_a_whole_expression_is_the_closed_form_of_calculus(text, exact):
    node = derivative(expr.read(text), 'x')
    choose = random.Random(text)
    for _ in range(25):
        x, y = choose.uniform(0.2, 2.0), choose.uniform(0.3, 1.8)
        assert value(node, {'x': x, 'y': y}) == pytest.approx(exact(x, y), rel=1e-12, abs=1e-13)


def composed(choose, depth):
    """An expression of x, y and z from the smooth operations, with values that stay in their domains."""
    if depth == 0 or choose.random() < 0.2:
        return choose.choice(['x', 'y', 'z', '0.7', '2', '1.5'])
    left, right = composed(choose, depth - 1), composed(choose, depth - 1)
    form = choose.choice(['add', 'sub', 'mul', 'div', 'exp', 'ln', 'sqrt', 'pow', 'if', 'min', 'max', 'clip'])
    if form == 'add':
        return f'({left} + {right})'
    if form == 'sub':
        return f'({left} - {right})'
    if form == 'mul':
        return f'({left} * {right})'
    if form == 'div':
        return f'({left} / (1 + ({right}) ** 2))'
    if form == 'exp':
        return f'exp(-(({left}) ** 2) / 8)'
    if form == 'ln':
        return f'ln(1 + ({left}) ** 2)'
    if form == 'sqrt':
        return f'sqrt(1 + ({left}) ** 2)'
    if form == 'pow':
        return f'(1 + ({left}) ** 2) ** 0.5'
    if form == 'if':
        return f'(({left}) if x > y else ({right}))'
    if form == 'clip':
        return f'clip({left}, -40, 40)'
    return f'{form}({left}, {right})'


@pytest.mark.parametrize('seed', range(60))
def test_the_derivative_of_a_composed_expression_is_the_slope_of_its_value(seed):
    choose = random.Random(seed)
    text = composed(choose, 4)
    node = expr.read(text)
    for by in ('x', 'y', 'z'):
        found = derivative(node, by)
        for _ in range(4):
            env = {name: choose.uniform(0.3, 1.7) for name in ('x', 'y', 'z')}
            # Away from the places where a choice, min, max or clip changes its piece: there the
            # difference reads two pieces, and the derivative is of one of them.
            near = [
                {**env, by: env[by] + shift * max(1.0, abs(env[by]))} for shift in (-4e-3, -2e-3, 2e-3, 4e-3)
            ]
            pieces = {repr(pieces_of(node, point)) for point in [env, *near]}
            if len(pieces) > 1:
                continue
            expected = slope(node, env, by)
            assert float(value(found, env)) == pytest.approx(expected, rel=2e-6, abs=2e-7), (text, by, env)


def pieces_of(node, env):
    """The answers of every test of an expression at a point: which piece of each choice, min, max
    and clip gives the value."""
    found = []
    for part in expr.walk(node):
        if isinstance(part, expr.IfElse):
            found.append(bool(value(part.test, env)))
        elif isinstance(part, expr.Call) and part.function in ('min', 'max'):
            values = [float(value(arg, env)) for arg in part.args]
            found.append(values.index(min(values) if part.function == 'min' else max(values)))
        elif isinstance(part, expr.Call) and part.function == 'clip':
            x, low, high = (float(value(arg, env)) for arg in part.args)
            found.append((x <= low, x >= high))
    return found


def test_a_name_that_the_expression_does_not_read_has_the_derivative_zero():
    node = expr.read('x * exp(y) + 3')
    assert derivative(node, 'w') is expr.const(0)
    assert derivative(expr.read('4.5'), 'x') is expr.const(0)
    assert derivative(expr.read('x'), 'x') is expr.const(1)


def test_a_condition_is_flat_and_a_choice_has_the_derivative_of_its_branch():
    assert derivative(expr.read('x > y and not (x == 2)'), 'x') is expr.const(0)
    node = derivative(expr.read('x * x if x > y else 3 * x'), 'x')
    assert value(node, {'x': 2.0, 'y': 1.0}) == 4.0
    assert value(node, {'x': 0.5, 'y': 1.0}) == 3.0
    # The test is read, never differentiated: a test that reads the name gives no term of its own.
    assert value(derivative(expr.read('y if x > 1 else 2 * y'), 'x'), {'x': 3.0, 'y': 1.0}) == 0


def test_a_quantity_has_the_scale_of_its_unit_as_its_slope():
    node = derivative(expr.read("q(3 * x, 'days')"), 'x')
    assert value(node, {'x': 1.0}) == pytest.approx(3 * UNITS.parse_unit('days').scale)


def test_the_sum_over_a_list_keeps_its_form():
    node = derivative(expr.read('sum(x * y, y, x)'), 'x')
    assert isinstance(node, expr.Call) and node.function == 'sum' and len(node.args) == 3
    assert derivative(expr.read('sum(y, 2 * y)'), 'x') is expr.const(0)


def test_the_same_node_and_name_give_the_same_node_again():
    node = expr.read('exp(x * y) / (1 + x)')
    assert derivative(node, 'x') is derivative(node, 'x')
    assert derivative(node, 'x') is not derivative(node, 'y')


def test_an_expression_outside_the_language_has_no_derivative():
    with pytest.raises(ExpressionError):
        derivative(expr.read('x[0] + 1'), 'x')
