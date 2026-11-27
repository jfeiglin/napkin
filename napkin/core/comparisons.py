"""Change 29: numeric model predicates use the scales of their two operands."""

from __future__ import annotations

import math
import operator
import sys
from collections.abc import Callable
from dataclasses import dataclass
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal
from fractions import Fraction
from typing import NamedTuple

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
        return _magnitude(difference) <= band
    if op == 'ne':
        return _magnitude(difference) > band
    if op == 'lt':
        return difference < (band.copy_negate() if isinstance(band, Decimal) else -band)
    if op == 'le':
        return difference <= band
    if op == 'gt':
        return difference > band
    return difference >= (band.copy_negate() if isinstance(band, Decimal) else -band)


# Scale metadata may grow or shrink beyond a float while the authored value
# remains finite. Keep the exponent until the scale comes back into range.
_WIDE = Context(prec=40, Emax=MAX_EMAX, Emin=MIN_EMIN)
_DECIMAL_OPS = {
    operator.add: _WIDE.add,
    operator.sub: _WIDE.subtract,
    operator.mul: _WIDE.multiply,
    operator.truediv: _WIDE.divide,
    operator.pow: _WIDE.power,
}


def _wide_number(value):
    if isinstance(value, Fraction):
        return _WIDE.divide(Decimal(value.numerator), Decimal(value.denominator))
    return Decimal(value)


def _arithmetic(op, a, b):
    if op is operator.pow and a == 0 and b < 0:
        return 0.0  # an exactly cancelled contribution to a finite reciprocal
    if not isinstance(a, Decimal) and not isinstance(b, Decimal):
        try:
            result = op(a, b)
        except OverflowError:
            result = math.inf
        if sys.float_info.min <= abs(result) <= sys.float_info.max:
            return result
        if result == 0 and (op in (operator.add, operator.sub) or a == 0 or b == 0):
            return result
    result = _DECIMAL_OPS[op](_wide_number(a), _wide_number(b))
    rounded = float(result)
    if result.is_zero() or sys.float_info.min <= abs(rounded) <= sys.float_info.max:
        return rounded
    return result


def composed_floor(operation, sizes, exponent=None):
    """The comparison scale of an operation on its contributing quantity scales, in result units."""
    if operation == 'mul':
        return _arithmetic(operator.mul, *sizes)
    if operation == 'div':
        return _arithmetic(operator.truediv, *sizes) if sizes[1] else 0
    if operation == 'sqrt' and not isinstance(sizes[0], Decimal):
        return math.sqrt(sizes[0])
    if operation in ('pow', 'sqrt'):
        return _arithmetic(operator.pow, sizes[0], 0.5 if operation == 'sqrt' else exponent)
    return max(sizes, default=1)


def _same(a, b):
    """Whether two values that a floor's walk read are the same: of one type, equal, and of one sign
    (a zero included). An array is never the same, so its walk always runs."""
    if type(a) is not type(b):
        return False
    try:
        if not bool(a == b):
            return False
    except (TypeError, ValueError):
        return False
    return not isinstance(a, float) or math.copysign(1.0, a) == math.copysign(1.0, b)


def _magnitude(number):
    return number.copy_abs() if isinstance(number, Decimal) else abs(number)


def signed_gap(a, b, gap=None):
    """Preserve the sign and size of the gap between two finite model values."""
    gap = float(a) - float(b) if gap is None else gap
    if math.isinf(gap) and math.isfinite(a) and math.isfinite(b):
        return _arithmetic(operator.sub, float(a), float(b))
    return gap


def band_from_floor_width(factor, floor_width, a, b, maximum=max):
    """Combine a precomputed absolute band and the operands' relative band, also for vector rows."""
    return maximum(floor_width, factor * maximum(_magnitude(a), _magnitude(b)))


def band_width(factor, floor, a, b):
    """The closed equality band's width in the operands' unit."""
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        exact_factor = Fraction(str(factor))
        return band_from_floor_width(exact_factor, exact_factor * Fraction(str(floor)), a, b)
    if not isinstance(floor, Decimal) and not isinstance(a, Decimal) and not isinstance(b, Decimal):
        width = band_from_floor_width(factor, floor * factor, a, b)
        if math.isfinite(width) or not all(map(math.isfinite, (floor, a, b))):
            return width
    size = max(floor, _magnitude(a), _magnitude(b))
    return _arithmetic(operator.mul, size, factor)


def numeric_gap_band(factor, floor, a, b, gap=None):
    """Compare authored rational operands exactly; keep a located physical gap when supplied."""
    if gap is None and isinstance(a, Fraction) and isinstance(b, Fraction):
        return a - b, band_width(factor, floor, a, b)
    return signed_gap(a, b, gap), band_width(factor, floor, a, b)


def collapsed_interval(factor, floor, low, high):
    """For reversed finite endpoints in the closed band, return their common point and that band."""
    difference, band = numeric_gap_band(factor, floor, low, high)
    if not against('eq', difference, band):
        return None
    if isinstance(difference, Decimal):  # subtracting these two finite floats overflowed
        return low / 2 + high / 2, band
    return high + difference / 2, band


def outside_authored_range(amount, low, high, floor):
    """Which exact endpoint excludes a fixed datum, allowing the shared narrow reversed interval."""
    if low is not None and high is not None and low > high:
        if floor is None:
            return None
        collapsed = collapsed_interval(DEFAULT_FACTOR, abs(floor), low, high)
        if collapsed is not None:
            midpoint, band = collapsed
            if against('eq', amount - midpoint, band):
                return None
    if low is not None and amount < low:
        return 'below'
    if high is not None and amount > high:
        return 'above'
    return None


def recorded_number(value):
    """A numeric trace value outside float range is recorded in canonical decimal units."""
    if isinstance(value, Fraction):
        try:
            return float(value)
        except OverflowError:
            return str(_WIDE.divide(Decimal(value.numerator), Decimal(value.denominator)))
    return str(value) if isinstance(value, Decimal) else value


@dataclass
class _Scale:
    unit: float | Decimal
    floor: float | Decimal
    # Signed contributions in the result's units. None identifies a literal expression.
    terms: dict | None = None

    def scaled(self, unit, factor):
        terms = (
            None
            if self.terms is None
            else {key: _arithmetic(operator.mul, amount, factor) for key, amount in self.terms.items()}
        )
        return _Scale(unit, _arithmetic(operator.mul, self.floor, _magnitude(factor)), terms)


def _sum_scales(unit, args, subtract):
    terms = {}
    for i, part in enumerate(args):
        for key, amount in (part.terms or {}).items():
            terms[key] = _arithmetic(
                operator.sub if i and subtract else operator.add, terms.get(key, 0.0), amount
            )
    return _Scale(unit, max(map(_magnitude, terms.values()), default=0.0), terms)


@dataclass
class SelectedScale:
    """An operand whose selected members supply its comparison-scale expression."""

    choose: Callable
    keys: set[str]
    members: tuple[str, ...]


class UnresolvedScale(LookupError):
    """A choice or exponent in a scale needs a value at the point of comparison."""


class Binding(NamedTuple):
    """A unit's size, the source of a comparison floor, and the live formula for exact reads."""

    unit: float
    floor: float | Decimal | str | expr.Node | SelectedScale
    definition: expr.Node | None = None


def _operand_walk(roots, walks):
    """Compile the scale operations on immutable nodes. Visit right operands first, as before.

    A reference or a choice has a live dependency. Its own instruction selects that
    dependency during evaluation. A policy and its row views share these walks.
    """
    cached = walks.get(roots)
    if cached is not None:
        return cached
    steps, seen = [], set()
    pending = [(node, None) for node in roots]
    while pending:
        node, parts = pending.pop()
        if node in seen:
            continue
        if parts is None and not isinstance(node, (expr.Ref, expr.IfElse)):
            parts = _scale_operands(node)
            if parts:
                pending.append((node, parts))
                pending.extend((child, None) for child in parts)
                continue
        seen.add(node)
        steps.append((node, parts))
    compiled = walks[roots] = tuple(steps)
    return compiled


class Comparisons:
    """The scale of a numeric operand in the canonical units of this evaluation.

    A binding gives the name's declared unit size and either its own floor or the
    formula from which it inherits a floor. A literal threshold adopts the scale
    of the quantity it is compared with.
    """

    def __init__(self, units, factor=DEFAULT_FACTOR, named=None):
        self.units, self.factor, self.named = units, factor, named
        self.floors = {}
        self.literal_gaps = {}
        self._operand_walks = {}
        self.concrete_definitions = False
        self._literal_reference = None

    def for_row(self, units, resolve):
        """Resolve template names on one row. A plan binds the names inside a retained definition
        before installing it, so its literal value is shared with all other reads of that concrete
        name in this epoch. A general binding may use template names inside the definition too."""
        row = Comparisons(units, self.factor, lambda name: self._binding(resolve(name)))
        row._operand_walks = self._operand_walks
        if self.concrete_definitions:
            row._literal_reference = lambda name: self.literal_value(expr.ref(resolve(name)))
        return row

    def _binding(self, name):
        found = self.named(name) if self.named is not None else (1.0, 1.0)
        if isinstance(found, Binding):
            return found
        unit, floor = found
        return Binding(unit, floor, floor if isinstance(floor, expr.Node) else None)

    def definition(self, name):
        """The live formula for a bound name, when the binding supplies one."""
        return self._binding(name).definition

    def control_names(self, roots):
        """Names a generated program can need to choose a floor, through its named formulas."""
        controls, seen, pending = set(), set(), list(roots)
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            if isinstance(node, expr.Ref):
                definition = self._binding(node.name).floor
                if isinstance(definition, expr.Node):
                    pending.append(definition)
                elif isinstance(definition, SelectedScale):
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
        """Read each operand's scale in the current binding and selected branch."""
        roots = tuple(roots)
        found = {}
        walks = self._operand_walks
        pending = [(iter(_operand_walk(roots, walks)), None)]
        while pending:
            steps, waiting = pending.pop()
            if waiting is not None:
                node, source, unit = waiting
                basis = found[source]
                found[node] = basis if unit is None else _Scale(unit, basis.floor, basis.terms)

            for node, parts in steps:
                if node in found:
                    continue
                if parts is not None:
                    found[node] = self._operation(node, [found[part] for part in parts], read)
                    continue
                if isinstance(node, expr.Ref):
                    binding = self._binding(node.name)
                    source = binding.floor
                    if isinstance(source, SelectedScale):
                        source = read(source)
                    if not isinstance(source, expr.Node):
                        own = Decimal(source) if isinstance(source, str) else source
                        found[node] = _Scale(binding.unit, own, {node: own})
                        continue
                    unit = binding.unit
                else:
                    source = node.body if read(node.test) else node.orelse
                    unit = None  # the selected arm supplies its own unit

                # Finish this reference or choice after its live dependency. The remaining
                # instructions keep their position, even through long definition chains.
                pending.append((steps, (node, source, unit)))
                if source not in found:
                    pending.append((iter(_operand_walk((source,), walks)), None))
                break
        return [found[node] for node in roots]

    def _operation(self, node, args, read):
        quantities = [item for item in args if item.terms is not None]
        contributors = quantities or args
        first = contributors[0] if contributors else _Scale(1.0, 0.0)
        unit = first.unit
        sizes = [arg.floor for arg in contributors]
        operation, exponent = None, None
        if isinstance(node, expr.Call) and node.function == 'q':
            conversion = self.units.parse_unit(node.args[1].value).scale
            return first.scaled(_arithmetic(operator.mul, unit, conversion), conversion)
        if isinstance(node, expr.Unary):
            return first.scaled(unit, -1) if node.op == 'neg' else first
        if isinstance(node, expr.Binary):
            a = args[0]
            operation = node.op
            if node.op == 'pow':
                exponent = read(node.right)
                unit = _arithmetic(operator.pow, unit, exponent)
                if exponent == 1:
                    return first
            else:
                b = args[1]
                if node.op in ('add', 'sub') and quantities:
                    return _sum_scales(unit, args, node.op == 'sub')
                if node.op == 'mul':
                    unit = _arithmetic(operator.mul, a.unit, b.unit)
                    if len(quantities) == 1:
                        literal = node.left if a.terms is None else node.right
                        return first.scaled(unit, read(literal))
                if node.op == 'div':
                    unit = _arithmetic(operator.truediv, a.unit, b.unit)
                    if a.terms is not None and b.terms is None:
                        return a.scaled(unit, _arithmetic(operator.truediv, 1.0, read(node.right)))
                    if b.terms is not None and a.terms is None:
                        sizes = [abs(read(node.left)), b.floor]
        elif isinstance(node, expr.Call):
            if node.function == 'sum' and quantities:
                return _sum_scales(unit, args, False)
            if node.function == 'sqrt':
                unit = _arithmetic(operator.pow, unit, 0.5) if isinstance(unit, Decimal) else math.sqrt(unit)
                operation = 'sqrt'
        own = composed_floor(operation, sizes, exponent) if quantities else 0.0
        return _Scale(unit, own, {node: own} if quantities else None)

    def floor(self, left, right, read=None):
        key = left, right
        cached = self.floors.get(key)
        if cached is not None:
            return cached
        dynamic = False
        reads = []

        def point(node):
            nonlocal dynamic
            from .evaluation import value

            if isinstance(node, SelectedScale):
                if read is None:
                    raise UnresolvedScale
                dynamic = True
                found = node.choose(lambda name: read(expr.ref(name)))
            elif not expr.names(node):
                return value(node, {}, self.units)
            else:
                if read is None:
                    raise UnresolvedScale(node)
                dynamic = True
                found = read(node)
            reads.append((node, found))
            return found

        # A floor that reads the state is a function of the values that its walk reads, in their
        # order: when each one is the same as at the last walk, the walk takes the same path to the
        # same floor. The memo lives in `floors`, so whatever clears the floors clears it too.
        memo = self.floors.get(('reads', left, right)) if read is not None else None
        if memo is not None:
            last, result = memo
            if all(_same(point(node), found) for node, found in last):
                return result
            dynamic, reads = False, []
        operands = self.operands(key, point)
        contributors = [item for item in operands if item.terms is not None] or operands
        result = max(item.floor for item in contributors)
        if not dynamic:
            self.floors[key] = result
        elif read is not None:
            self.floors['reads', left, right] = tuple(reads), result
        return result

    def frozen_floor(self, name, read):
        """The formula's floor when retired, in a form that the record can serialize."""
        size = self.floor(expr.ref(name), expr.const(0), read)
        return recorded_number(size)

    def band_floor(self, left, right, read=None):
        return float(band_width(self.factor, self.floor(left, right, read), 0, 0))

    def band(self, left, right, a, b, read=None):
        return float(band_width(self.factor, self.floor(left, right, read), a, b))

    def band_interval(self, left, right, x, y, read=None):
        """The narrowest and the widest band of a comparison whose operands lie in the closed intervals
        x and y, rounded outward: the band grows with the operands' magnitudes."""
        floor = self.floor(left, right, read)

        def closest(interval):
            return max(interval[0], -interval[1], 0)

        low = math.nextafter(float(band_width(self.factor, floor, closest(x), closest(y))), 0)
        high = band_width(self.factor, floor, max(map(abs, x)), max(map(abs, y)))
        return low, math.nextafter(float(high), math.inf)

    def literal_value(self, node):
        """An operand fixed entirely by authored literals. An explicit floor preserves
        the formula that supplied the value. A change of definitions clears the binding cache."""
        bound = bool(expr.names(node))
        cache = self.floors if bound else self.literal_gaps
        # Neighbouring outputs can traverse the same retained definition chain. Its
        # literal and nonliteral subtrees are valid until the bindings or factor change.
        known = cache.setdefault(('literal operands', self.factor), {})
        cached = known.get(id(node))
        if cached is not None:
            return cached[1]

        from .literals import Literals, node_parts

        def parts(n):
            if isinstance(n, expr.Ref) and self.named is not None:
                if self._literal_reference is not None:
                    return 'literal', (), self._literal_reference(n.name)
                definition = self.definition(n.name)
                if isinstance(definition, expr.Node):
                    return 'pos', (definition,), None
            return node_parts(n)

        literals = Literals(
            parts, self.units.exact_scale if self.units is not None else None, self.factor, self.literal_floor
        )
        try:
            return literals.value(node, known)
        except UnresolvedScale:
            return None

    def literal_floor(self, left, right):
        """Resolve a floor using only values fixed by the authored expressions."""

        def read(node):
            value = self.literal_value(node)
            if value is None:
                raise UnresolvedScale(node)
            return value

        return self.floor(left, right, read)

    def rounded_literal(self, node):
        """The once-rounded value when all selected operands are authored literals."""
        key = node, self.factor
        try:
            return self.floors[key]
        except KeyError:
            # A solver can evaluate this sum thousands of times against different
            # stock levels. Only a change of definition or policy can make it literal.
            exact = self.literal_value(node) if self.named is not None or not expr.names(node) else None
            replacement = float(exact) if isinstance(exact, Fraction) else None
            self.floors[key] = replacement
            return replacement

    def literal_sum(self, node, rounded):
        """A named formula must expose the same small residual that its inline guard compares."""
        if not isinstance(rounded, float) or not math.isfinite(rounded):
            return rounded
        replacement = self.rounded_literal(node)
        return rounded if replacement is None else replacement

    def literal_gap(self, left, right, *, bindings=False):
        """Exact gap and comparison band of two literal operands. A vectorized template
        with row-specific bindings resolves its actual operands on each row."""
        bound = bool(expr.names(left) or expr.names(right))
        if bound and (bindings or self.named is None):
            return None
        cache = self.floors if bound else self.literal_gaps
        key = left, right, self.factor
        if key not in cache:
            a = self.literal_value(left)
            b = self.literal_value(right) if isinstance(a, Fraction) else None
            result = None
            if isinstance(b, Fraction):
                try:
                    floor = self.literal_floor(left, right) if bound else 0
                    result = numeric_gap_band(self.factor, floor, a, b)
                except UnresolvedScale:
                    pass  # this floor needs the live evaluation
            cache[key] = result
        return cache[key]

    def gap_band(self, left, right, a, b, read=None, gap=None):
        """The signed gap and band in the operands' units, even beyond float range."""
        if gap is None:
            exact = self.literal_gap(left, right)
            if exact is not None:
                return exact
        return numeric_gap_band(self.factor, self.floor(left, right, read), a, b, gap)

    def ordered(self, op, left, right, a, b, read=None):
        if (
            isinstance(a, (str, bool))
            or isinstance(b, (str, bool))
            or not (math.isfinite(a) and math.isfinite(b))
        ):
            return ORDER[op](a, b)
        return against(op, *self.gap_band(left, right, a, b, read))


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
