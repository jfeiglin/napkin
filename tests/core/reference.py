"""An interpreter of typed nodes for the tests of `napkin/core/`: a walk of a node that computes each
part with Python's own operations, by the rules of the language (each value that a part gives is
finite and real; a choice, `and` and `or` compute only what they need; a name with no value fails when
it is reached). It shares no code with the code that the package writes for a node."""

import math
import operator
from decimal import MAX_EMAX, MIN_EMIN, Decimal, localcontext
from fractions import Fraction

from napkin import expressions
from napkin.core import expr
from tests.units import library

DEFINITIONS = library()['units']
UNITS = expressions.UnitSystem(DEFINITIONS)
# The scale of a unit, exactly: a quantity is the decimal that writes its number times this, rounded
# once to a float (`0.1 days` is the float nearest to 12/5 h), whatever its number is.
SCALES = {name: Fraction(str(DEFINITIONS[name]['scale'])) for name in ('h', 'days')}
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


def _scale(node, env):
    """The walk's floor and signed contributions. Every independent name has scale one."""
    if isinstance(node, expr.Ref):
        return Decimal(1), {node: Decimal(1)}
    if isinstance(node, expr.IfElse):
        return _scale(node.body if walked(node.test, env) else node.orelse, env)
    if isinstance(node, expr.Binary) and node.op == 'pow':
        base, terms = _scale(node.left, env)
        if not terms:
            return Decimal(0), {}
        exponent = Decimal(walked(node.right, env))
        size = Decimal(0) if not base and exponent < 0 else Decimal(1) if exponent == 0 else base**exponent
        return size, terms if exponent == 1 else {node: size} if terms else {}
    if isinstance(node, expr.Binary):
        (a, left), (b, right) = (_scale(child, env) for child in node.children)
        if node.op in ('mul', 'div'):
            if left and not right:
                k = Decimal(walked(node.right, env))
                factor = k if node.op == 'mul' else 1 / k
                return a * abs(factor), {n: c * factor for n, c in left.items()}
            if right and not left:
                k = Decimal(walked(node.left, env))
                if node.op == 'mul':
                    return abs(k) * b, {n: k * c for n, c in right.items()}
                a = abs(k)
            size = a * b if node.op == 'mul' else a / b if b else Decimal(0)
            return size, {node: size} if left or right else {}
        parts = [(a, left), (b, right)]
    elif isinstance(node, expr.Call):
        if node.function == 'q':
            size, terms = _scale(node.args[0], env)
            unit = Decimal(float(SCALES[node.args[1].value]))
            return size * unit, {n: v * unit for n, v in terms.items()}
        parts = [_scale(arg, env) for arg in node.args]
        if node.function == 'sqrt':
            size = Decimal(parts[0][0]).sqrt()
            return size, {node: size} if parts[0][1] else {}
    elif isinstance(node, expr.Unary):
        size, terms = _scale(node.operand, env)
        return size, {n: -c for n, c in terms.items()} if node.op == 'neg' else terms
    else:
        return Decimal(0), {}
    contributors = [part for part in parts if part[1]]
    if not contributors:
        return Decimal(0), {}
    if isinstance(node, expr.Binary) or node.function == 'sum':
        terms = {}
        for i, (_, signed) in enumerate(parts):
            subtract = i and isinstance(node, expr.Binary) and node.op == 'sub'
            for name, size in signed.items():
                terms[name] = terms.get(name, 0) + (-size if subtract else size)
        return max(map(abs, terms.values())), terms
    size = max(size for size, _ in contributors)
    return size, {node: size}


def _ordered(op, a, b, x, y, env):
    if isinstance(x, (str, bool)) or isinstance(y, (str, bool)):
        return ORDER[op](x, y)
    # The independent walk computes the band at an extended exponent range.
    with localcontext(prec=50, Emax=MAX_EMAX, Emin=MIN_EMIN):
        sizes = [_scale(node, env) for node in (a, b)]
        named = any(is_named for _, is_named in sizes)
        floor = max(size for size, is_named in sizes if is_named or not named)
        a, b = Decimal(x), Decimal(y)
        if abs(a - b) <= Decimal('1e-9') * max(floor, abs(a), abs(b)):
            return op in ('eq', 'le', 'ge')
    return ORDER[op](x, y)


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
        for op, before, operand in zip(node.ops, node.operands, node.operands[1:]):
            right = walked(operand, env)
            result = _ordered(op, before, operand, left, right, env)
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
        if number == 0:
            return float(number)  # its sign stays, as in a product with a positive scale
        return real(float(Fraction(repr(float(number))) * SCALES[unit]))
    if name == 'clip':
        value, low, high = args
        if low > high:
            raise ValueError('bounds')
        return real(min(max(value, low), high))
    if name == 'within':
        # The closed interval [low, high], read once; a reversed one is an error.
        value, low, high = args
        x, lo, hi = node.args
        if _ordered('gt', lo, hi, low, high, env):
            raise ValueError('reversed')
        return _ordered('le', lo, x, low, value, env) and _ordered('le', x, hi, value, high, env)
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
