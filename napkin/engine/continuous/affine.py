"""Affine operations shared by the compartment kernel and moving-comparison departure."""

import math

from ...core import expr as nodes
from .walk import walked


def scale(form, factor):
    constant, terms = form
    return factor * constant, {name: factor * value for name, value in terms.items()}


def binary(op, left, right):
    """The exact affine operation, or None for a product or quotient that can curve."""
    a, x = left
    b, y = right
    if op in ('add', 'sub'):
        sign = -1 if op == 'sub' else 1
        return a + sign * b, {k: x.get(k, 0) + sign * y.get(k, 0) for k in x.keys() | y.keys()}
    if op == 'mul' and (not x or not y):
        return scale(left, b) if x else scale(right, a)
    if op == 'div' and not y and b != 0:
        return a / b, {k: v / b for k, v in x.items()}
    return None


def operands(pair, read, place, moving, definition, selected):
    """Find the coefficients of the two selected pieces in stocks and time. An unresolved
    choice, live rate, or curved expression delegates the departure to the trajectory probe."""
    forms = {}

    def form(node):
        if node in forms:
            return forms[node]
        forms[node] = None
        if isinstance(node, nodes.Ref) and (node.name in place or node.name == 't'):
            result = 0, {node.name: 1}
        elif not moving(node):
            result = float(read(node)), {}
        elif isinstance(node, nodes.Ref):
            formula = definition(node.name)
            if formula is None:
                return None
            result = yield form(selected(formula))
        elif isinstance(node, nodes.Unary) and node.op in ('pos', 'neg'):
            arg = yield form(node.operand)
            result = None if arg is None else scale(arg, -1 if node.op == 'neg' else 1)
        elif isinstance(node, nodes.Binary):
            left = yield form(node.left)
            right = yield form(node.right)
            result = None if left is None or right is None else binary(node.op, left, right)
        else:
            return None
        forms[node] = result
        return result

    left, right = (walked(form(selected(node))) for node in pair)
    return None if left is None or right is None else (left[1], right[1])


def velocity(forms, drift, place):
    """Relative rate on an affine pair and the error scale of its potentially cancelling terms."""
    terms = [
        sign * coefficient * (1 if name == 't' else drift[place[name]])
        for sign, form in zip((1, -1), forms, strict=True)
        for name, coefficient in form.items()
    ]
    return math.fsum(terms), math.fsum(map(abs, terms))
