"""The derivative of an expression by one of the names that it reads.

`derivative(node, name)` gives a node of `expr`: the partial derivative of the value of `node` by the
value of the reference `name`, where that derivative has a meaning. It is the chain rule over the
partials of each operation (`ops.Operation.partials`), and this module adds no rule of its own for an
operation: a new operation gets its derivative from its contract.

What the result means:

- Where every operation of the expression is smooth at the values that it meets, the result is the
  derivative.
- A choice has the derivative of the branch that its test takes; `min`, `max`, `clip` and `abs` have
  the derivative of the piece that gives the value (`ops` says which one at a tie). At a point where
  the pieces meet with different slopes, that is a one-sided derivative. This module does not find
  such points: the reader that needs to know (the sensitivities of the engine) reads the margins of
  the tests.
- A condition (a comparison, `and`, `or`, `not`) is flat where it does not step, so its derivative
  is 0. The step itself is not a derivative, and no node stands for it.
- The second argument of `q` is the written name of a unit, which has no derivative.

The result is made small as it is built: a product with 0 is 0, a product with 1 is the other factor,
and a sum with 0 is the other term. Nothing else is rewritten, so the result computes what the chain
rule says, in the order of the arguments.
"""

from __future__ import annotations

from . import expr, ops
from .errors import ExpressionError

ZERO, ONE = expr.const(0), expr.const(1)


def _is(node, value):
    return isinstance(node, expr.Const) and type(node.value) in (int, float) and node.value == value


def _times(left, right):
    if _is(left, 0) or _is(right, 0):
        return ZERO
    if _is(left, 1):
        return right
    if _is(right, 1):
        return left
    return expr.binary('mul', left, right)


def _plus(left, right):
    if _is(left, 0):
        return right
    if _is(right, 0):
        return left
    return expr.binary('add', left, right)


def _chain(name, args, by, memo):
    """The chain rule for one operation: the sum, over its arguments, of its partial by the argument
    times the derivative of the argument."""
    operation = ops.OPERATIONS[name]
    if operation.partials is None:
        return ZERO
    inner = [_derivative(arg, by, memo) for arg in args]
    if all(_is(item, 0) for item in inner):
        return ZERO
    total = ZERO
    for partial, item in zip(operation.partials(*args), inner, strict=True):
        if partial is not None:
            total = _plus(total, _times(partial, item))
    return total


def _derivative(node, by, memo):
    found = memo.get(node)
    if found is None:
        found = memo[node] = _made(node, by, memo)
    return found


def _made(node, by, memo):
    if isinstance(node, expr.Const):
        return ZERO
    if isinstance(node, expr.Ref):
        return ONE if node.name == by else ZERO
    if isinstance(node, expr.Unary):
        return _chain(node.op, [node.operand], by, memo)
    if isinstance(node, expr.Binary):
        return _chain(node.op, [node.left, node.right], by, memo)
    if isinstance(node, (expr.Compare, expr.BoolOp)):
        return ZERO
    if isinstance(node, expr.IfElse):
        body, orelse = _derivative(node.body, by, memo), _derivative(node.orelse, by, memo)
        if body is orelse:
            return body
        return expr.if_else(node.test, body, orelse)
    if isinstance(node, expr.Call):
        if node.function == 'sum':
            # The derivative of a sum over a list is the sum of the derivatives, as one node: the
            # reader of a list (a reduction over the instances of a family) reads it as it reads the sum.
            inner = [_derivative(arg, by, memo) for arg in node.args]
            return ZERO if all(_is(item, 0) for item in inner) else expr.call('sum', inner)
        return _chain(node.function, list(node.args), by, memo)
    raise ExpressionError('An expression outside the language has no derivative')


_MEMOS: dict = {}


def derivative(node, name, *, memo=None):
    """The partial derivative of `node` by the reference `name`, as a node. A node that does not read
    `name` gives the constant 0."""
    if memo is None:
        memo = _MEMOS.setdefault(name, {})
    return _derivative(node, name, memo)
