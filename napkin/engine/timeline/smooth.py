"""Where an expression can stop being smooth: the pairs of its parts that meet at a tie.

The derivative of an expression (`core/derivatives`) is the derivative of the piece that gives its
value: the branch of a choice that its test takes, the argument of `min` or `max` that is the
least or the greatest, the side of `clip` or `abs`. Where two pieces meet, a small change of an
input can change which piece gives the value, and the derivative is that of one side only. Two
pieces meet where two parts of the expression have one value:

- the two sides of a comparison (in the test of a choice, or in a condition);
- two arguments of `min` or `max`;
- the value of `clip` and one of its limits;
- the argument of `abs` and zero.

`pairs(node)` gives each such pair of a node, from its form alone. A reader with a state (the
sensitivities of the engine, `timeline/run.py`) evaluates the two parts of each pair: where they
are equal, the pair is a **tie**, and the derivative of their difference by an input says whether
that input can break it. A pair in a branch that the state does not take can be found too: that
makes a derivative one-sided that is not, and never the reverse.
"""

from __future__ import annotations

from functools import lru_cache

from ...core import expr

ORDERS = frozenset({'lt', 'le', 'gt', 'ge', 'eq', 'ne'})
ZERO = expr.const(0)


def _children(node):
    if isinstance(node, expr.Unary):
        return (node.operand,)
    if isinstance(node, expr.Binary):
        return (node.left, node.right)
    if isinstance(node, expr.Compare):
        return tuple(node.operands)
    if isinstance(node, expr.BoolOp):
        return tuple(node.values)
    if isinstance(node, expr.IfElse):
        return (node.test, node.body, node.orelse)
    if isinstance(node, expr.Call):
        return tuple(node.args)
    return ()


def _number(node):
    """Whether a part can be a number: a written text (the name of a status value, a unit) cannot."""
    return not (isinstance(node, expr.Const) and isinstance(node.value, (str, bool)))


def walk(node):
    """A node and each part of it, however deep."""
    pending = [node]
    while pending:
        part = pending.pop()
        yield part
        pending += _children(part)


@lru_cache(maxsize=8192)
def pairs(node):
    """The pairs (a, b) of parts of a node at whose tie two pieces of the node meet (the module),
    each once, in the order of the node."""
    found = []
    if isinstance(node, expr.Compare):
        for op, left, right in zip(node.ops, node.operands, node.operands[1:]):
            if op in ORDERS and _number(left) and _number(right):
                found.append((left, right))
    elif isinstance(node, expr.Call) and node.function in ('min', 'max'):
        args = [arg for arg in node.args if _number(arg)]
        found += [(a, b) for i, a in enumerate(args) for b in args[i + 1 :]]
    elif isinstance(node, expr.Call) and node.function == 'clip' and len(node.args) == 3:
        value, low, high = node.args
        found += [(value, low), (value, high)]
    elif isinstance(node, expr.Call) and node.function == 'abs' and len(node.args) == 1:
        found.append((node.args[0], ZERO))
    for child in _children(node):
        found += pairs(child)
    return tuple(dict.fromkeys(found))


@lru_cache(maxsize=8192)
def jumps(node):
    """The pairs of `pairs` at whose tie the value of the node can jump: the two sides of each
    comparison. Where the two parts of a pair of `min`, `max`, `clip` or `abs` meet, the value is
    continuous and only its derivative changes."""
    found = []
    for part in walk(node):
        if isinstance(part, expr.Compare):
            for op, left, right in zip(part.ops, part.operands, part.operands[1:]):
                if op in ORDERS and _number(left) and _number(right):
                    found.append((left, right))
    return tuple(dict.fromkeys(found))


@lru_cache(maxsize=8192)
def difference(a, b):
    """The node `a - b` of a pair: its sign says which piece gives the value."""
    return a if b is ZERO or b == ZERO else expr.binary('sub', a, b)
