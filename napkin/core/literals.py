"""Exact numbers and comparisons of expressions made solely of literals.

The compiler and the evaluator have different expression trees. Each supplies the operation,
its operands, and the declared unit of a numeric literal. The arithmetic and choice of branch
are shared, including on the closed edge of a comparison band.
"""

from __future__ import annotations

import math
from fractions import Fraction

from . import expr
from .comparisons import against


class Literals:
    def __init__(self, parts, scale, factor):
        self.parts, self.scale, self.factor = parts, scale, factor

    def value(self, node, known=None):
        """Evaluate selected operands once, reusing completed subtrees for these bindings.
        An active ancestor denotes a read cycle that the engine diagnoses."""
        known = {} if known is None else known
        stack = [(node, self._value(node))]
        active = {id(node)}
        value = None
        while stack:
            current, compute = stack[-1]
            try:
                child = compute.send(value)
            except StopIteration as done:
                value = done.value
                known[id(current)] = current, value
                active.remove(id(current))
                stack.pop()
                continue
            key = id(child)
            if key in known:
                value = known[key][1]
            elif key in active:
                value = None
            else:
                active.add(key)
                stack.append((child, self._value(child)))
                value = None
        return value

    def _value(self, node):
        op, args, data = self.parts(node)
        if op == 'unknown':
            return None
        if op == 'number':
            number, unit = data
            exact = Fraction(str(number)) if isinstance(number, float) else Fraction(number)
            return exact * (self.scale(unit) if unit else 1)
        if op == 'literal':
            return data
        if op == 'if':
            test = yield args[0]
            return (yield (args[1] if test else args[2])) if isinstance(test, bool) else None
        if op in ('and', 'or'):
            decides = op == 'or'
            for arg in args:
                value = yield arg
                if not isinstance(value, bool):
                    return None
                if value == decides:
                    return decides
            return not decides
        if op == 'compare':
            left = yield args[0]
            for symbol, second in zip(data, args[1:]):
                right = yield second
                if left is None or right is None:
                    return None
                if isinstance(left, Fraction) and isinstance(right, Fraction):
                    holds = self.ordered(symbol, left, right)
                elif symbol in ('eq', 'ne'):
                    holds = (left == right) == (symbol == 'eq')
                else:
                    return None
                if not holds:
                    return False
                left = right
            return True
        values = []
        for arg in args:
            value = yield arg
            if value is None:
                return None
            values.append(value)
        if op == 'pos':
            return values[0]
        if op == 'not':
            return not values[0] if isinstance(values[0], bool) else None
        if not all(isinstance(value, Fraction) for value in values):
            return None
        if op == 'q':
            return values[0] * self.scale(data)
        if op == 'within':
            value, low, high = values
            if self.ordered('gt', low, high):
                return None
            return self.ordered('le', low, value) and self.ordered('le', value, high)
        return _EXACT[op](*values) if op in _EXACT else None

    def gap_band(self, a, b, floor=0):
        """An authored literal adds no comparison floor, in any unit. A range can
        supply the declared scale of the quantity to which it belongs."""
        return a - b, Fraction(str(self.factor)) * max(floor or 0, abs(a), abs(b))

    def ordered(self, op, a, b, floor=0):
        return against(op, *self.gap_band(a, b, floor))


def node_parts(node):
    """The operations of a program expression, including its explicit quantity conversions."""
    if isinstance(node, expr.Const):
        value = node.value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return 'number', (), (value, '')
        return 'literal', (), value
    if isinstance(node, expr.IfElse):
        return 'if', node.children, None
    if isinstance(node, expr.Compare):
        return 'compare', node.children, node.ops
    if isinstance(node, (expr.Binary, expr.Unary, expr.BoolOp)):
        return node.op, node.children, None
    if isinstance(node, expr.Call):
        if node.function == 'q':
            return 'q', node.args[:1], node.args[1].value
        return node.function, node.args, None
    return 'unknown', (), None


def _power(base, exponent):
    """`base ** exponent` exactly: for a whole exponent (and a base that is not zero below zero), and
    for an exponent of one half of a whole number, from an exact square root; None otherwise."""
    if abs(exponent) > 1024 or (base == 0 and exponent < 0):
        return None
    if exponent.denominator == 1:
        return base ** int(exponent)
    if exponent.denominator == 2:
        root = _root(base)
        return None if root is None else _power(root, Fraction(exponent.numerator))
    return None


def _root(number):
    """The square root of a rational number exactly, when it is the square of a rational; else None."""
    if number < 0:
        return None
    top, bottom = math.isqrt(number.numerator), math.isqrt(number.denominator)
    if top * top != number.numerator or bottom * bottom != number.denominator:
        return None
    return Fraction(top, bottom)


def _clip(value, low, high):
    """`clip` exactly; None for bounds in the wrong order, which fail where a run reads them."""
    return None if low > high else min(max(value, low), high)


# The operations of numbers whose result `folded` computes exactly from exact arguments: None where
# the result is no rational number, or is no value.
_EXACT = {
    'neg': lambda value: -value,
    'add': lambda a, b: a + b,
    'sub': lambda a, b: a - b,
    'mul': lambda a, b: a * b,
    'div': lambda a, b: None if b == 0 else a / b,
    'pow': _power,
    'sum': lambda *values: sum(values, Fraction(0)),
    'min': lambda *values: min(values),
    'max': lambda *values: max(values),
    'abs': abs,
    'clip': _clip,
    'sqrt': _root,
    'exp': lambda value: Fraction(1) if value == 0 else None,
    'expm1': lambda value: Fraction(0) if value == 0 else None,
    'ln': lambda value: Fraction(0) if value == 1 else None,
    'log1p': lambda value: Fraction(0) if value == 0 else None,
    'erf': lambda value: Fraction(0) if value == 0 else None,
}
