"""Change 29: numeric model predicates use the scales of their two operands."""

from __future__ import annotations

import math
import operator
from collections.abc import Callable
from dataclasses import dataclass

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


@dataclass
class _Scale:
    unit: float
    floor: float
    # Signed contributions in the result's units. None identifies a literal expression.
    terms: dict | None = None

    def scaled(self, unit, factor):
        terms = None if self.terms is None else {key: amount * factor for key, amount in self.terms.items()}
        return _Scale(unit, self.floor * abs(factor), terms)


def _sum_scales(unit, args, subtract):
    terms = {}
    for i, part in enumerate(args):
        for key, amount in (part.terms or {}).items():
            terms[key] = terms.get(key, 0.0) + (-amount if i and subtract else amount)
    return _Scale(unit, max(map(abs, terms.values()), default=0.0), terms)


@dataclass
class IndexedScale:
    """An indexed operand. Its index selects the declaration supplying its floor."""

    choose: Callable
    keys: set[str]
    members: tuple[str, ...]


class UnresolvedScale(LookupError):
    """A choice or exponent in a scale needs a value at the point of comparison."""


class Comparisons:
    """The scale of a numeric operand in the canonical units of this evaluation.

    A binding gives the name's declared unit size and either its own floor or the
    formula from which it inherits a floor. A literal threshold adopts the scale
    of the quantity it is compared with.
    """

    def __init__(self, units, factor=DEFAULT_FACTOR, named=None):
        self.units, self.factor, self.named = units, factor, named
        self.floors = {}

    def _binding(self, name):
        return self.named(name) if self.named is not None else (1.0, 1.0)

    def control_names(self, roots):
        """Names a generated program can need to choose a floor, through its named formulas."""
        controls, seen, pending = set(), set(), list(roots)
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            if isinstance(node, expr.Ref):
                definition = self._binding(node.name)[1]
                if isinstance(definition, expr.Node):
                    pending.append(definition)
                elif isinstance(definition, IndexedScale):
                    controls.update(definition.keys)
                    pending.extend(map(expr.ref, definition.members))
            elif isinstance(node, expr.IfElse):
                controls.update(expr.names(node.test))
                pending.extend((node.body, node.orelse, node.test))
            elif isinstance(node, expr.Binary) and node.op == 'pow':
                controls.update(expr.names(node.right))
                pending.extend(node.children)
            else:
                # An expression with no quantity operands (e.g. a predicate) supplies its
                # current value when it is a coefficient in a product or quotient.
                if node.children and not _scale_operands(node):
                    controls.update(expr.names(node))
                pending.extend(node.children)
        return controls

    def operands(self, roots, read):
        """The unit and comparison scale for each operand.

        Use an explicit stack through inline and named expressions alike. A choice
        asks for its condition and visits only the arm that supplied the value.
        """
        found, definitions, choices = {}, {}, {}
        pending = list(roots)
        while pending:
            node = pending[-1]
            if node in found:
                pending.pop()
                continue
            if isinstance(node, expr.Ref):
                if node not in definitions:
                    definitions[node] = self._binding(node.name)
                unit, own = definitions[node]
                if isinstance(own, IndexedScale):
                    own = expr.ref(read(own))
                    definitions[node] = unit, own
                if isinstance(own, expr.Node):
                    if own not in found:
                        pending.append(own)
                        continue
                    basis = found[own]
                    result = _Scale(
                        unit, basis.floor, basis.terms if basis.terms is not None else {node: basis.floor}
                    )
                else:
                    result = _Scale(unit, own, {node: own})
            elif isinstance(node, expr.IfElse):
                if node not in choices:
                    choices[node] = node.body if read(node.test) else node.orelse
                selected = choices[node]
                if selected not in found:
                    pending.append(selected)
                    continue
                result = found[selected]
            else:
                parts = _scale_operands(node)
                missing = [part for part in parts if part not in found]
                if missing:
                    pending.extend(missing)
                    continue
                args = [found[part] for part in parts]
                result = self._operation(node, args, read)
            found[node] = result
            pending.pop()
        return [found[n] for n in roots]

    def _operation(self, node, args, read):
        quantities = [item for item in args if item.terms is not None]
        contributors = quantities or args
        first = contributors[0] if contributors else _Scale(1.0, 1.0)
        unit, own = first.unit, max((arg.floor for arg in contributors), default=1.0)
        if isinstance(node, expr.Call) and node.function == 'q':
            conversion = self.units.scale(node.args[1].value)
            return first.scaled(unit * conversion, conversion)
        if isinstance(node, expr.Unary):
            return first.scaled(unit, -1) if node.op == 'neg' else first
        if isinstance(node, expr.Binary):
            a = args[0]
            if node.op == 'pow':
                exponent = read(node.right)
                unit, own = unit**exponent, own**exponent
                if exponent == 1:
                    return first
            else:
                b = args[1]
                if node.op in ('add', 'sub') and quantities:
                    return _sum_scales(unit, args, node.op == 'sub')
                if node.op == 'mul':
                    unit = a.unit * b.unit
                    if len(quantities) == 1:
                        literal = node.left if a.terms is None else node.right
                        return first.scaled(unit, read(literal))
                    own = a.floor * b.floor
                if node.op == 'div':
                    unit = a.unit / b.unit
                    if a.terms is not None and b.terms is None:
                        return a.scaled(unit, 1 / read(node.right))
                    numerator = abs(read(node.left)) if b.terms is not None and a.terms is None else a.floor
                    own = numerator / b.floor if b.floor else 0.0
        elif isinstance(node, expr.Call):
            if node.function == 'sum' and quantities:
                return _sum_scales(unit, args, False)
            if node.function == 'sqrt':
                unit, own = math.sqrt(unit), math.sqrt(own)
        return _Scale(unit, own, {node: own} if quantities else None)

    def floor(self, left, right, read=None):
        key = left, right
        cached = self.floors.get(key)
        if cached is not None:
            return cached
        dynamic = False

        def point(node):
            nonlocal dynamic
            from .evaluation import value

            if isinstance(node, IndexedScale):
                if read is None:
                    raise UnresolvedScale
                dynamic = True
                return node.choose(lambda name: read(expr.ref(name)))
            if not expr.names(node):
                return value(node, {}, self.units)
            if read is None:
                raise UnresolvedScale(node)
            dynamic = True
            return read(node)

        operands = self.operands(key, point)
        contributors = [item for item in operands if item.terms is not None] or operands
        result = max(item.floor for item in contributors)
        if not dynamic:
            self.floors[key] = result
        return result

    def band(self, left, right, a, b, read=None):
        return self.factor * max(self.floor(left, right, read), abs(a), abs(b))

    def ordered(self, op, left, right, a, b, read=None):
        if (
            isinstance(a, (str, bool))
            or isinstance(b, (str, bool))
            or not (math.isfinite(a) and math.isfinite(b))
        ):
            return ORDER[op](a, b)
        return against(op, a - b, self.band(left, right, a, b, read))


def _scale_operands(node):
    if isinstance(node, expr.Call) and node.function == 'q':
        return node.args[:1]
    if isinstance(node, expr.Binary):
        return (node.left,) if node.op == 'pow' else node.children
    if isinstance(node, expr.Unary) and node.op in ('neg', 'pos'):
        return node.children
    if isinstance(node, expr.Call) and node.function in (
        'sum',
        'min',
        'max',
        'abs',
        'clip',
        'sqrt',
        'exp',
        'expm1',
        'ln',
        'log1p',
        'erf',
    ):
        return node.args
    return ()
