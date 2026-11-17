"""An interpreter of typed nodes for the tests of `napkin/core/`: a walk of a node that computes each
part with Python's own operations, by the rules of the language (each value that a part gives is
finite and real; a choice, `and` and `or` compute only what they need; a name with no value fails when
it is reached). It shares no code with the code that the package writes for a node."""

import math
import operator

from napkin import expressions
from napkin.core import expr
from tests import build as b

DEFINITIONS = b.library()['units']
UNITS = expressions.UnitSystem(DEFINITIONS)
# The scale of a unit is a float, so a quantity is a float whatever its number is.
SCALES = {name: float(DEFINITIONS[name]['scale']) for name in ('h', 'days')}
FAILURES = (ArithmeticError, ValueError, TypeError, KeyError)
ARITHMETIC = {'add': operator.add, 'sub': operator.sub, 'mul': operator.mul, 'div': operator.truediv}
ORDER = {
    'eq': operator.eq,
    'ne': operator.ne,
    'lt': operator.lt,
    'le': operator.le,
    'gt': operator.gt,
    'ge': operator.ge,
}
ONE = {
    'abs': abs,
    'sqrt': math.sqrt,
    'exp': math.exp,
    'expm1': math.expm1,
    'ln': math.log,
    'log1p': math.log1p,
    'erf': math.erf,
}


class NotFinite(ValueError):
    """A part gave a number that is not finite."""


def real(value):
    """A value that a part gives: a number is finite and real."""
    if isinstance(value, complex):
        raise ValueError('not real')
    if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
        raise NotFinite('not finite')
    return value


def walked(node, env):
    """The value of a node, by a walk of the node."""
    if isinstance(node, expr.Ref):
        return real(env[node.name])
    if isinstance(node, expr.Const):
        return real(node.value)
    if isinstance(node, expr.Unary):
        value = walked(node.operand, env)
        return (not value) if node.op == 'not' else real(-value) if node.op == 'neg' else value
    if isinstance(node, expr.Binary):
        left, right = walked(node.left, env), walked(node.right, env)
        if node.op == 'pow':
            if abs(right) > 1024:
                raise ValueError('exponent')
            return real(float(left) ** right)
        return real(ARITHMETIC[node.op](left, right))
    if isinstance(node, expr.Compare):
        left = walked(node.operands[0], env)
        for op, operand in zip(node.ops, node.operands[1:]):
            right = walked(operand, env)
            result = ORDER[op](left, right)
            if not result:
                return result
            left = right
        return result
    if isinstance(node, expr.BoolOp):
        stops = node.op == 'or'
        for term in node.values:
            if bool(walked(term, env)) == stops:
                return stops
        return not stops
    if isinstance(node, expr.IfElse):
        return real(walked(node.body if walked(node.test, env) else node.orelse, env))
    assert isinstance(node, expr.Call)
    name = node.function
    if name in ('any', 'all'):
        # One member of a list is that member. More are read one by one until one decides.
        if len(node.args) == 1:
            return walked(node.args[0], env)
        stops = name == 'any'
        for term in node.args:
            if bool(walked(term, env)) == stops:
                return stops
        return not stops
    args = [walked(arg, env) for arg in node.args]
    if name == 'sum':
        # The members added two by two from the left; each sum of two is a real, finite number.
        total = args[0]
        for value in args[1:]:
            total = real(total + value)
        return total
    if name == 'q':
        number, unit = args
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError('no number')
        return real(number * SCALES[unit])
    if name == 'clip':
        value, low, high = args
        if low > high:
            raise ValueError('bounds')
        return real(min(max(value, low), high))
    if name in ('min', 'max'):
        return real((min if name == 'min' else max)(args))
    (value,) = args
    return real(ONE[name](value))


def outcome(compute):
    """('fails',) when `compute` fails as an evaluation fails, else the type and the exact value."""
    try:
        value = compute()
    except FAILURES:
        return ('fails',)
    return type(value), value.hex() if isinstance(value, float) else value
