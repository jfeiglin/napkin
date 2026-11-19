"""Units: the unit of a value, the registry of the units of a model, and the unit of an expression.

A `Unit` is the dimensions of a value, its scale in execution units and its kind (a number, a yes/no,
a text, or the plain zero, which has every unit of a number). A `UnitRegistry` holds the units that a
model declares and composes the others from them.

A quantity converts to execution units once and exactly (`normalize`): its number is the decimal that
writes it (`rational`: `0.1` is 1/10, not the binary float nearest to it) and its scale the exact
rational of its unit, and only the product is rounded to a float. So equal quantities are one number
however they are spelled: `0.1 day`, `144 min` and `2.4 h` are each the float nearest to 12/5 hours.

`unit_of` gives the unit of an expression of typed nodes, by the rule for units that the contract of
each operation names (`ops.UNIT_RULES`): the function of each rule is in `RULES`, and the handler of an
operation is the function of its rule. So an operation with a rule that has no function here is an
error when this module is read.
"""

from __future__ import annotations

import ast
import difflib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from . import expr, ops
from .errors import ExpressionError


@dataclass(frozen=True)
class Unit:
    dimensions: tuple[tuple[str, float], ...] = ()
    scale: float = 1.0
    kind: str = 'number'

    @property
    def dims(self):
        return self.dimensions

    def compatible(self, other: Unit) -> bool:
        return self.kind == other.kind and self.dimensions == other.dimensions

    def canonical(self) -> Unit:
        return Unit(self.dimensions, 1.0, self.kind)

    def power(self, exponent: float) -> Unit:
        if self.kind != 'number':
            raise ExpressionError('Powers require numeric quantities')
        return Unit(
            tuple((key, value * exponent) for key, value in self.dimensions if value * exponent),
            self.scale**exponent,
        )

    def multiply(self, other: Unit, divide=False) -> Unit:
        if self.kind != 'number' or other.kind != 'number':
            raise ExpressionError('Arithmetic requires numeric quantities')
        dims = dict(self.dimensions)
        for key, value in other.dimensions:
            dims[key] = dims.get(key, 0) + (-value if divide else value)
        return Unit(
            tuple(sorted((key, value) for key, value in dims.items() if value)),
            self.scale / other.scale if divide else self.scale * other.scale,
        )


def rational(number):
    """The exact rational of a number as a text writes it: an int or a Fraction is itself, and a float
    is the shortest decimal that writes it (its `repr`, which a model's text, a JSON file and a
    program's canonical text hold: `0.1` is 1/10). A float made by arithmetic reads as the decimal of
    its own `repr`, within half a unit of its last place of the binary value."""
    if isinstance(number, Fraction):
        return number
    if isinstance(number, int):
        return Fraction(number)
    return Fraction(float.__repr__(float(number)))


NUMBER = Unit()
BOOLEAN = Unit(kind='boolean')
STRING = Unit(kind='string')
ZERO = Unit(kind='zero')


# A factor of a composed unit with its power, `m^2` or `s^-1`; and the `-` that joins two factors of a
# product, which is never the sign of a power.
_POWER = re.compile(r'(.+)\^(-?[0-9]+)')
_PRODUCT = re.compile(r'(?<!\^)-')
# A part of a composed unit, between its `/` and `-` (`tunings`, `/`, `tuner`, `-`, `year`).
_PARTS = re.compile(r'(/|(?<!\^)-)')


class UnitRegistry:
    """Explicit units prevent accidental conflation of episodes, people or money years.

    A unit that no entry declares is composed of declared units (docs/language.md, §2.1): `a/b`
    divides, `a-b` is a product, which binds tighter than `/`, and `a^n` is a power with a whole
    exponent, so `tunings/tuner-year` is tunings per tuner per year. An entry always wins over a
    composition: of the whole name, of a product of its parts and of the first parts of a quotient."""

    def __init__(self, definitions: Mapping):
        self._units, self._exact = {}, {}
        for name, spec in definitions.items():
            dimensions = spec.get('dimensions', spec.get('dimension'))
            if not isinstance(dimensions, Mapping):
                raise ExpressionError(f'Unit {name!r} requires a dimensions mapping')
            # A scale is a number of a units file, or the exact Fraction of a program's unit.
            scale = spec.get('scale', 1)
            if (
                isinstance(scale, bool)
                or not isinstance(scale, (int, float, Fraction))
                or not math.isfinite(scale)
                or scale <= 0
            ):
                raise ExpressionError(f'Unit {name!r} requires a positive finite scale')
            for key, value in dimensions.items():
                if (
                    not isinstance(key, str)
                    or isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ExpressionError(f'Invalid dimension in unit {name!r}')
            self._units[name] = Unit(tuple(sorted((k, v) for k, v in dimensions.items() if v)), float(scale))
            self._exact[name] = rational(scale)
        self._units = MappingProxyType(self._units)

    @property
    def names(self):
        """The names of the registered units."""
        return self._units.keys()

    def factors(self, name):
        """[(declared name, power)] of a unit: a declared name is itself; a composed name is each declared
        unit that it multiplies, with its power (a divisor's is negative). The longest declared run of
        factors wins (`person-hours` in `USD2025/person-hours`), and so does the longest declared run
        of the first parts of a quotient (`L/h` in `L/h/people`). Raises ExpressionError for any other
        name."""
        if not isinstance(name, str):
            raise ExpressionError(f'Unregistered unit {name!r}')
        if name in self._units:
            return [(name, 1)]
        pieces = name.split('/')
        start = next((k for k in range(len(pieces) - 1, 0, -1) if '/'.join(pieces[:k]) in self._units), 0)
        out = [('/'.join(pieces[:start]), 1)] if start else []
        for index, piece in enumerate(pieces[start:], start):
            sign = 1 if index == 0 else -1
            terms, i = _PRODUCT.split(piece), 0
            while i < len(terms):
                for j in range(len(terms), i, -1):
                    if '-'.join(terms[i:j]) in self._units:
                        out.append(('-'.join(terms[i:j]), sign))
                        i = j
                        break
                else:
                    found = _POWER.fullmatch(terms[i])
                    if found is None or found.group(1) not in self._units:
                        raise ExpressionError(f'Unregistered unit {name!r}')
                    out.append((found.group(1), sign * int(found.group(2))))
                    i += 1
        return out

    def parse_unit(self, name: str) -> Unit:
        try:
            return self._units[name]
        except (KeyError, TypeError):
            pass
        # The factors with a positive power multiply, and those with a negative power divide them. A
        # composition is made each time that it is read: the registry keeps only its entries.
        above, below = NUMBER, NUMBER
        for part, power in self.factors(name):
            term = self._units[part].power(abs(power))
            if power > 0:
                above = above.multiply(term)
            else:
                below = below.multiply(term)
        return above.multiply(below, divide=True)

    def exact_scale(self, name):
        """The exact scale of a unit, a Fraction: a declared unit's own, and a composed unit's the
        product of its factors' scales to their powers. Raises ExpressionError for a name that is no
        unit."""
        found = self._exact.get(name) if isinstance(name, str) else None
        if found is not None:
            return found
        scale = Fraction(1)
        for part, power in self.factors(name):
            scale *= self._exact[part] ** power
        return scale

    def __contains__(self, name):
        """Whether `name` is a unit: declared, or composed of declared units."""
        try:
            self.parse_unit(name)
        except ExpressionError:
            return False
        return True

    def suggestions(self, name):
        """The units close to `name`, which is no unit, for a diagnostic: the declared names, and `name`
        with a part that names no unit replaced by a declared name close to it (`tunings/yr` gives
        `tunings/year`)."""
        declared = sorted(self._units)
        found = set(declared)
        parts = _PARTS.split(name) if isinstance(name, str) else []
        for index, part in enumerate(parts):
            base, caret, power = part.partition('^')
            if part in ('/', '-') or base in self._units:
                continue
            for close in difflib.get_close_matches(base, declared, n=3):
                candidate = ''.join([*parts[:index], close + caret + power, *parts[index + 1 :]])
                if candidate in self:
                    found.add(candidate)
        return found

    def __getitem__(self, name):
        return self.parse_unit(name)

    def normalize(self, value, name):
        """A number in the unit `name` in execution units: the decimal that writes it times the unit's
        exact scale, rounded once (see the module), so that `0.1 day` and `2.4 h` are one float."""
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ExpressionError(f'Expected a finite quantity in {name}')
        scale = self.exact_scale(name)
        if scale == 1 or value == 0:
            return float(value)  # a zero keeps its sign, as a product with a positive scale does
        try:
            result = float(rational(value) * scale)
        except OverflowError:
            raise ExpressionError('Unit conversion overflow') from None
        return result


class UnitSystem(UnitRegistry):
    def scale(self, name):
        return self.parse_unit(name).scale

    def dimension(self, name):
        return self.parse_unit(name).canonical()


# ---- the unit of an expression --------------------------------------------------------------------------


def same(left, right):
    """The one unit of two values that must have one unit. A plain zero has every unit of a number."""
    if left == ZERO and right.kind == 'number':
        return right
    if right == ZERO and left.kind == 'number':
        return left
    if left == ZERO and right == ZERO:
        return ZERO
    if not left.compatible(right):
        raise ExpressionError(f'Incompatible quantities: {left} and {right}')
    return left


def literal(node):
    """The number that a literal writes, with its sign (`2`, `-1`, `+0.5`); None for anything else."""
    if isinstance(node, expr.Unary) and node.op in ('neg', 'pos'):
        value = literal(node.operand)
        return None if value is None else -value if node.op == 'neg' else value
    if (
        isinstance(node, expr.Const)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


def _numbers(units, message):
    for unit in units:
        if unit.kind not in ('number', 'zero'):
            raise ExpressionError(message)


def _arguments(infer, node, count):
    """The units of the arguments of a function that takes `count` of them. The arguments are read
    first, so an error inside one of them comes before an error of their number."""
    units = [infer(arg) for arg in node.args]
    if len(units) != count:
        raise ExpressionError(f'{node.function} requires exactly one argument')
    return units


def _number(infer, node, registry):
    if isinstance(node, expr.Unary):
        unit = infer(node.operand)
        _numbers([unit], 'Numeric unary operator on nonnumeric value')
        return unit
    (unit,) = _arguments(infer, node, 1)
    _numbers([unit], f'{node.function} requires numbers')
    return unit


def _condition(infer, node, registry):
    for part in node.children:
        same(infer(part), BOOLEAN)
    return BOOLEAN


def _chain(infer, first, links):
    """The unit of a chain of comparisons: `links` gives each next operation and node. An operation
    that the language does not have (None) is an error where the reading meets it."""
    left = infer(first)
    for op, operand in links:
        if op is None:
            raise ExpressionError('Unsupported comparison')
        right = infer(operand)
        same(left, right)
        if left.kind in ('boolean', 'string') and op not in ('eq', 'ne'):
            raise ExpressionError('Ordered comparisons require numeric values')
        left = right
    return BOOLEAN


def _compared(infer, node, registry):
    return _chain(infer, node.operands[0], zip(node.ops, node.operands[1:]))


def _choice(infer, node, registry):
    same(infer(node.test), BOOLEAN)
    return same(infer(node.body), infer(node.orelse))


def _same_unit(infer, node, registry):
    if isinstance(node, expr.Binary):
        result = same(infer(node.left), infer(node.right))
        _numbers([result], 'Arithmetic requires numbers')
        return result
    units = [infer(arg) for arg in node.args]
    name = node.function
    if name == 'clip':
        if len(units) != 3:
            raise ExpressionError('clip requires exactly three arguments')
        result = same(same(units[0], units[1]), units[2])
        _numbers([result], 'clip requires numbers')
        return result
    if len(units) < 1:
        raise ExpressionError(f'{name} requires at least one argument')
    result = units[0]
    for other in units[1:]:
        result = same(result, other)
    _numbers([result], 'Arithmetic requires numbers' if name == 'sum' else 'min/max require numbers')
    return result


def _factors(infer, node):
    """The units of the two sides of a product, a quotient or a power; a plain zero is a plain number."""
    left, right = infer(node.left), infer(node.right)
    _numbers([left, right], 'Arithmetic requires numbers')
    return (NUMBER if left == ZERO else left), (NUMBER if right == ZERO else right)


def _product(infer, node, registry):
    left, right = _factors(infer, node)
    return left.multiply(right).canonical()


def _quotient(infer, node, registry):
    left, right = _factors(infer, node)
    return left.multiply(right, divide=True).canonical()


def _power(infer, node, registry):
    left, right = _factors(infer, node)
    same(right, NUMBER)
    exponent = literal(node.right)
    if exponent is not None:
        if abs(exponent) > 1024:
            raise ExpressionError('Exponent exceeds supported magnitude 1024')
        return left.power(exponent).canonical()
    if left.dimensions:
        raise ExpressionError('Dimensional powers require a literal exponent')
    return NUMBER


def _root(infer, node, registry):
    (unit,) = _arguments(infer, node, 1)
    return (NUMBER if unit == ZERO else unit).power(0.5).canonical()


def _plain(infer, node, registry):
    (unit,) = _arguments(infer, node, 1)
    same(unit, NUMBER)
    return NUMBER


def _literal_unit(infer, node, registry):
    args = node.args
    if len(args) != 2 or not isinstance(args[1], expr.Const) or not isinstance(args[1].value, str):
        raise ExpressionError('q requires a number and literal registered unit')
    same(infer(args[0]), NUMBER)
    return registry.parse_unit(args[1].value).canonical()


# The rule of `ops.UNIT_RULES` that each function here is.
RULES = {
    'number': _number,
    'condition': _condition,
    'compared': _compared,
    'choice': _choice,
    'same': _same_unit,
    'product': _product,
    'quotient': _quotient,
    'power': _power,
    'root': _root,
    'plain': _plain,
    'literal': _literal_unit,
}
if RULES.keys() != ops.UNIT_RULES.keys():
    raise LookupError(f'the rules for units: {sorted(RULES.keys() ^ ops.UNIT_RULES.keys())}')
# The handler of each operation is the rule that its contract names.
TABLE = ops.handlers(
    'the unit of an expression', {name: RULES[operation.units] for name, operation in ops.OPERATIONS.items()}
)


def _foreign(infer, node):
    """The error of a part that is outside the language."""
    tree = node.tree
    if isinstance(tree, ast.Compare):
        links = (
            (expr.COMPARE.get(type(op)), expr.of_tree(item)) for op, item in zip(tree.ops, tree.comparators)
        )
        return _chain(infer, expr.of_tree(tree.left), links)
    if isinstance(tree, ast.BinOp):
        _numbers(
            [infer(expr.of_tree(tree.left)), infer(expr.of_tree(tree.right))], 'Arithmetic requires numbers'
        )
        raise ExpressionError('Unsupported arithmetic operator')
    if isinstance(tree, ast.Call):
        raise ExpressionError('Unsupported function or keyword arguments')
    raise ExpressionError(f'Unsupported syntax {type(tree).__name__}')


def unit_of(node, symbol_units, registry):
    """(the unit of an expression, the names that it reads). `symbol_units` gives the unit of each
    name. An expression that breaks a rule for units is an ExpressionError: the first one that a
    reading of the expression from left to right meets."""
    dependencies = set()

    def infer(part):
        if isinstance(part, expr.Ref):
            if part.name not in symbol_units:
                raise ExpressionError(f'Unknown symbol {part.name!r}')
            dependencies.add(part.name)
            return symbol_units[part.name].canonical()
        if isinstance(part, expr.Const):
            value = part.value
            if isinstance(value, bool):
                return BOOLEAN
            if isinstance(value, str):
                return STRING
            if isinstance(value, (int, float)) and math.isfinite(value):
                return ZERO if value == 0 else NUMBER
            raise ExpressionError('Only finite numbers, booleans, and strings are allowed')
        if isinstance(part, expr.Foreign):
            return _foreign(infer, part)
        handler = TABLE.get(ops.operation_of(part))
        if handler is None:
            raise ExpressionError('Unsupported function or keyword arguments')
        return handler(infer, part, registry)

    return infer(node), frozenset(dependencies)
