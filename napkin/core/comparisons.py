"""Change 29: numeric model predicates use the scales of their two operands."""

from __future__ import annotations

import math
import operator

from . import expr

DEFAULT_FACTOR = 1e-9

ORDER = {
    'eq': operator.eq,
    'ne': operator.ne,
    'le': operator.le,
    'lt': operator.lt,
    'ge': operator.ge,
    'gt': operator.gt,
}


def against(op, difference, band):
    """A gap in the closed band counts as equality."""
    if op == 'eq':
        return abs(difference) <= band
    if op == 'ne':
        return abs(difference) > band
    if op == 'lt':
        return difference < -band
    if op == 'le':
        return difference <= band
    if op == 'gt':
        return difference > band
    return difference >= -band


class Comparisons:
    """The operand scales of one evaluation context, in its canonical units.

    A binding supplies (declared unit size, the quantity's own scale). An unnamed
    expression uses its result unit. A literal threshold adopts the other operand's
    scale, so writing that threshold in another unit changes no decision.
    """

    def __init__(self, units, factor=DEFAULT_FACTOR, named=None):
        self.units, self.factor, self.named = units, factor, named
        self.floors = {}

    def operand(self, node):
        """(result unit size, own floor) of an operand."""
        if isinstance(node, expr.Ref):
            return self.named(node.name) if self.named is not None else (1.0, 1.0)
        sizes = {}
        pending = [node]
        while pending:
            part = pending[-1]
            if part in sizes:
                pending.pop()
                continue
            if isinstance(part, expr.Ref):
                size = self.named(part.name)[0] if self.named is not None else 1.0
            elif isinstance(part, expr.Call) and part.function == 'q':
                size = self.units.parse_unit(part.args[1].value).scale
            else:
                operands = _unit_operands(part)
                missing = [child for child in operands if child not in sizes]
                if missing:
                    pending.extend(missing)
                    continue
                units = [sizes[child] for child in operands]
                size = units[0] if units else 1.0
                if isinstance(part, expr.Binary):
                    if part.op == 'mul':
                        size *= units[1]
                    elif part.op == 'div':
                        size /= units[1]
                    elif part.op == 'pow' and units:
                        size **= part.right.value
                elif isinstance(part, expr.Call) and part.function == 'sqrt':
                    size = math.sqrt(size)
            sizes[part] = size
            pending.pop()
        return sizes[node], sizes[node]

    def floor(self, left, right):
        key = (left, right)
        found = self.floors.get(key)
        if found is None:
            a, b = bool(expr.names(left)), bool(expr.names(right))
            found = max(
                self.operand(node)[1] for node, keep in ((left, a or not b), (right, b or not a)) if keep
            )
            self.floors[key] = found
        return found

    def band(self, left, right, a, b):
        return self.factor * max(self.floor(left, right), abs(a), abs(b))

    def ordered(self, op, left, right, a, b):
        if (
            isinstance(a, (str, bool))
            or isinstance(b, (str, bool))
            or not (math.isfinite(a) and math.isfinite(b))
        ):
            return ORDER[op](a, b)
        return against(op, a - b, self.band(left, right, a, b))


def _unit_operands(node):
    """Only the operands that contribute the unit of the result."""
    if isinstance(node, expr.IfElse):
        return (node.body,)
    if isinstance(node, expr.Unary):
        return (node.operand,)
    if isinstance(node, expr.Binary):
        a, b = node.left, node.right
        if node.op in ('add', 'sub'):
            return (a if expr.names(a) or not expr.names(b) else b,)
        if node.op in ('mul', 'div'):
            return a, b
        if node.op == 'pow' and isinstance(b, expr.Const) and isinstance(b.value, (float, int)):
            return (a,)
    if isinstance(node, expr.Call) and node.function in ('sum', 'min', 'max', 'abs', 'clip', 'sqrt'):
        return node.args[:1]
    return ()
