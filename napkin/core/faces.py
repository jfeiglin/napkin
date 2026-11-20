"""The proof that an expression is constant on the zero faces of some stocks.

A stock is on its zero face while it is at zero and stays there. An expression is constant on such
faces when it reads the stocks only in comparisons with zero: on the face each such comparison has one
value. `constant_on_faces` gives the stocks that an expression reads in that way, or None when it reads
anything that moves in another way (a stock outside a comparison with zero, the time, a name that is
not fixed). This admits the finite switches of a conservative flow, and it excludes a smooth
dependence on a stock, a forcing by the time and a tangency at the bound.
"""

from __future__ import annotations

import ast

from . import evaluation, expr
from .errors import ExpressionError


def constant_on_faces(node, static_names, zero_stocks, aliases, parameters, registry):
    """The stocks of `zero_stocks` that `node` compares with zero, when it reads nothing else that
    moves; else None.

    - `static_names`: the names that are fixed.
    - `aliases`: the node of the formula of a name; a formula is constant when what it reads is.
    - A comparison of a stock with an expression of `parameters` (name → value) alone whose value is
      exactly zero is constant on the face of that stock. `registry` converts its quantities.

    The walk follows parts and formulas with a list and not with calls (re-audit 15), so a chain of
    thousands of formulas, or a node thousands deep, has its proof: the walk of each part is a
    computation that yields each part that it needs walked (a node of `expr`, or a part of Python's
    tree) and is sent whether that part is constant.
    """
    used = set()
    # What the walk found for each formula. A formula that many others read is walked once: its answer
    # does not depend on the way to it, because a formula on a circle of formulas is never constant,
    # from whichever formula the walk comes, and the stocks that it adds to `used` are added once.
    walked = {}
    visiting = set()  # the formulas on the way to the part that is walked, whose walks wait for it

    def comparison(operands):
        if len(operands) == 2:
            left, right = operands
            stock = left.name if isinstance(left, expr.Ref) else None
            if stock not in zero_stocks:
                stock = right.name if isinstance(right, expr.Ref) else None
                left, right = right, left
            if (
                stock in zero_stocks
                and expr.names(right) <= parameters.keys()
                and evaluation.checked_value(right, parameters, registry) == 0
            ):
                used.add(stock)
                return True
        return (yield from every(operands))

    def every(parts):
        """Whether each part is constant, the parts walked in order until one is not."""
        for part in parts:
            if not (yield part):
                return False
        return True

    def walk_tree(tree):
        """A part of Python's tree that is no expression of its own (an operator, a keyword)."""
        if isinstance(tree, ast.expr):
            return (yield expr.of_tree(tree))
        return (yield from every(list(ast.iter_child_nodes(tree))))

    def walk(node):
        if isinstance(node, expr.Ref):
            name = node.name
            if name not in aliases:
                return name in static_names
            if name in visiting:
                return False
            if name not in walked:
                visiting.add(name)
                walked[name] = yield aliases[name]
                visiting.discard(name)
            return walked[name]
        if isinstance(node, expr.Const):
            return True
        if isinstance(node, expr.Compare):
            return (yield from comparison(node.operands))
        if isinstance(node, expr.Foreign):
            tree = node.tree
            if isinstance(tree, ast.Compare):
                return (
                    yield from comparison([expr.of_tree(item) for item in (tree.left, *tree.comparators)])
                )
            if isinstance(tree, ast.Call):
                return (yield from every([expr.of_tree(arg) for arg in tree.args]))
            return (yield from every(list(ast.iter_child_nodes(tree))))
        return (yield from every(node.children))

    def walked_from(node):
        stack, sent = [walk(node)], None
        while True:
            try:
                part = stack[-1].send(sent)
            except StopIteration as done:
                stack.pop()
                if not stack:
                    return done.value
                sent = done.value
                continue
            stack.append(walk_tree(part) if isinstance(part, ast.AST) else walk(part))
            sent = None

    try:
        return frozenset(used) if walked_from(node) else None
    except (ExpressionError, SyntaxError, TypeError, ValueError, RecursionError):
        return None
