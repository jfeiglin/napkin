"""The declared model: a parsed model text with its names resolved and its types and units checked.

It holds what a run needs and what the report and the drawings read beside the program: the scenario
line, the entities with their values and flows, the values of the top level, the records and the
notes, each with its texts and its evidence. Each declared part has a stable path, the path that the
program gives the part as its `origin` (`tank.water`, `clinic.delivery`, `close` at the top level),
so a report or a trace finds the label and the evidence of a part from the program.

- **Types and units.** A value's type is declared (`water: L`) or inferred from its initializer. A
  number's unit is checked by its dimension, from the units of the library and of the model: `+`,
  `-`, comparisons, `min`, `max`, `clip` and both sides of `if ... else` need one dimension, and `*`
  and `/` make the dimension of their result (D12). A bare number takes the declared unit where the
  spec says so: the whole initializer, a bare end of the declaration's range, its scale, the value
  arguments of a distribution that (or whose draw) is the whole initializer; and a bare zero beside
  a value of known unit.
- **Unit runs.** After a number, a name is a unit while the library has a unit of that name and the
  run has not stopped; the first name that is no unit stops the run, and it and the names after it
  are values (`(2 h) * hour` against `2 h * hour`). The arithmetic is the same either way.
- **Expressions** become a small typed form (`Const`, `Read`, `Apply`, `Retain`, `Distribution`,
  `Drawn`) that the lowering writes as a program.
- **What a later slice brings** is kept as a `Deferred` part, with the construct and the slice that
  brings it; the lowering refuses it by name. This slice resolves entities written once, values,
  inputs (a default may draw from a distribution), formulas, `readonly`, ranges with either side
  open, scales, stores and directed flows with `request` and `capacity`.
"""

from __future__ import annotations

import difflib
import math
from dataclasses import dataclass, field
from fractions import Fraction

from .language import nodes as n
from .language.problems import LanguageError, Problem

# ---- units ------------------------------------------------------------------------------------------


class Units:
    """The units of a model: a spelling and its dimension (base dimensions with their powers) or a
    pair of the dimension and its scale, as `napkin.program.build.Builder` takes them. A spelling with
    `*` and `/` is composed from the left (D12)."""

    def __init__(self, table):
        self.table = dict(table)
        self.base = {}
        for name, spec in self.table.items():
            dimension, scale = spec if isinstance(spec, tuple) else (spec, 1)
            self.base[name] = (tuple(sorted((k, v) for k, v in dimension.items() if v)), Fraction(scale))

    def has(self, name):
        return name in self.base

    def of(self, spelling):
        """(dimension, scale) of a spelling, or None when a name of it is no unit."""
        dimension, scale = {}, Fraction(1)
        for sign, name in factors(spelling):
            if name == '1':
                continue
            if name not in self.base:
                return None
            found, size = self.base[name]
            for key, power in found:
                dimension[key] = dimension.get(key, 0) + sign * power
            scale = scale * size if sign > 0 else scale / size
        return tuple(sorted((k, v) for k, v in dimension.items() if v)), scale


def factors(spelling):
    """The factors of a spelling, [(+1 or -1, name)] from the left: `L/h` is [(1, 'L'), (-1, 'h')]."""
    out, sign, name = [], 1, ''
    for char in spelling:
        if char in '*/':
            out.append((sign, name))
            sign, name = (1 if char == '*' else -1), ''
        else:
            name += char
    if name:
        out.append((sign, name))
    return out


def spelling_of(found):
    """The spelling of factors [(sign, name)]: the names over the line first, in their order, and the
    same name over and under the line cancels (`tunings/tuner/year * tuner` is `tunings/year`)."""
    powers = {}
    for sign, name in found:
        if name != '1':
            powers[name] = powers.get(name, 0) + sign
    above = [name for name, power in powers.items() for _ in range(max(power, 0))]
    below = [name for name, power in powers.items() for _ in range(max(-power, 0))]
    if not above and not below:
        return ''
    return '/'.join(['*'.join(above) or '1', *below])


def flat_unit(unit):
    """The factors of a unit of a type (`nodes.UnitOp` or a name), from the left with no brackets:
    `tunings / (tuner * year)` is tunings/tuner/year."""

    def walk(item, sign):
        if isinstance(item, str):
            return [(sign, item)]
        return walk(item.left, sign) + walk(item.right, sign if item.op == '*' else -sign)

    return walk(unit, 1)


# ---- types ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Num:
    """A number in a unit (its spelling, '' for a plain number) and the unit's dimension."""

    unit: str = ''
    dimension: tuple = ()

    def __str__(self):
        return self.unit or 'a plain number'


@dataclass(frozen=True)
class Word:
    """`bool` or `text`."""

    word: str

    def __str__(self):
        return self.word


BOOL, TEXT = Word('bool'), Word('text')
PLAIN = Num()


@dataclass(frozen=True)
class Dist:
    """A distribution of numbers in a unit."""

    of: Num

    def __str__(self):
        return f'distribution({self.of})'


def compatible(a, b):
    if isinstance(a, Num) and isinstance(b, Num):
        return a.dimension == b.dimension
    return a == b


# ---- the typed form of an expression -----------------------------------------------------------------


@dataclass(frozen=True)
class Const:
    """A number (in the unit of its type), a yes/no or a text."""

    value: object
    type: object


@dataclass(frozen=True)
class Read:
    """A read from a start: `('this',)`, `('named', entity)`, `('root',)` or `('time',)`, through its
    steps (a value, a flow and its rate)."""

    start: tuple
    steps: tuple
    type: object


@dataclass(frozen=True)
class Apply:
    """An operation: `add`, `sub`, `mul`, `div`, `pow`, `neg`, `not`, `and`, `or`, `if`, `compare`
    (its operators in `detail`) or `call` (the function in `detail`)."""

    op: str
    args: tuple
    type: object
    detail: object = None


@dataclass(frozen=True)
class Retain:
    """`formula(body)`."""

    body: object
    type: object


@dataclass(frozen=True)
class Distribution:
    """A distribution of a family, its parameters as numbers in one unit."""

    family: str
    params: tuple
    type: Dist


@dataclass(frozen=True)
class Drawn:
    """`d.draw()` of a distribution."""

    source: Distribution
    type: Num


# ---- the declared parts -------------------------------------------------------------------------------

INPUT, STATE, FORMULA, DISTRIBUTION = 'input', 'state', 'formula', 'distribution'


@dataclass(frozen=True)
class DeclaredValue:
    """A value of an entity or of the top level: its kind (`input`, `state`, `formula`,
    `distribution`), its type, its initializer, its range (either side None), its scale, its texts
    and its evidence (the records that it cites and those written under it)."""

    path: str
    name: str
    kind: str
    type: object
    init: object
    lower: object = None
    upper: object = None
    scale: object = None
    readonly: bool = False
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredFlow:
    """A directed flow: its ends (`'SOURCE'`, `'SINK'` or the `Read` of a store), the type of its
    rates, its request and its capacity (captured once, or a `Retain`)."""

    path: str
    name: str
    source: object
    sink: object
    rate: Num
    request: object = None
    capacity: object = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredEntity:
    """An entity written once: a template of one member, with its parts in written order."""

    path: str
    parts: tuple = ()
    text: str | None = None
    title: str | None = None
    role: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class Deferred:
    """A part that this slice parses and formats but does not lower: what it is and the slice that
    brings it."""

    path: str
    construct: str
    slice: str
    line: int = 0


@dataclass(frozen=True)
class Scenario:
    """The scenario line: its role (`main` or `variant`), its title and texts, and its times in hours."""

    role: str
    title: str
    summary: str | None = None
    scope: str | None = None
    library: str | None = None
    horizon: object = None
    resolution: object = None
    timescales: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredModel:
    """A declared model: its scenario line, its entities and top-level values in written order, its
    records and notes, the parts that a later slice brings, its units and its tree."""

    scenario: Scenario | None
    entities: tuple[DeclaredEntity, ...]
    root: tuple[DeclaredValue, ...]
    records: tuple = ()
    notes: tuple = ()
    deferred: tuple[Deferred, ...] = ()
    units: Units = None
    tree: n.File = field(default=None, repr=False)

    def part(self, path):
        """The declared part of a path (an entity, a value, a flow or a deferred part), or None."""
        for entity in self.entities:
            if entity.path == path:
                return entity
            for part in entity.parts:
                if part.path == path:
                    return part
        return next((part for part in (*self.root, *self.deferred) if part.path == path), None)


# ---- resolution ---------------------------------------------------------------------------------------


class Later(Exception):
    """A construct that a later slice brings, met while a part is resolved."""

    def __init__(self, construct, slice_):
        super().__init__(construct)
        self.construct, self.slice = construct, slice_


class Refused(Exception):
    """A diagnostic that stops the resolution of one part."""

    def __init__(self, code, message, node=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.line = getattr(node, 'line', 0)
        self.column = getattr(node, 'column', 0)


@dataclass(frozen=True)
class EntityRef:
    """An entity named in an expression: only a step from it reads a value."""

    name: str
    start: tuple


@dataclass(frozen=True)
class FlowRef:
    """A flow named in an expression: only its rates are read."""

    path: str
    start: tuple
    steps: tuple
    rate: Num


FLOW_READS = ('actual_rate', 'request', 'capacity')
SHAPES = {'lognormal': {1}}  # the positions of the plain (shape) arguments of a family: the gsd
ARITY = {
    'uniform': (2,),
    'triangular': (3,),
    'pert': (3,),
    'loguniform': (2,),
    'normal': (2, 4),
    'lognormal': (2, 4),
}
PURE = ('exp', 'expm1', 'ln', 'log1p', 'erf')
LATER_CALLS = {
    **dict.fromkeys(('sum', 'count', 'any', 'all'), ('a reduction', 'S1')),
    **dict.fromkeys(('since', 'elapsed', 'delayed'), ('history (since, elapsed, delayed)', 'S4')),
    **dict.fromkeys(('priority', 'proportional'), ('an allocation (priority, proportional)', 'S2')),
}
LATER_METHODS = {
    'where': ('a where filter', 'S1'),
    'by': ('a key (by)', 'S1'),
    'at': ('a keyed read (at)', 'S1'),
    'draw': ('a draw outside the default of an input', 'S4'),
    'choose': ("an actor's choice", 'S4'),
}


def close(name, names):
    found = difflib.get_close_matches(name, sorted(set(names) - {name}), n=3)
    return f'; did you mean {" or ".join(found)}?' if found else ''


def literal(node):
    """The number of a literal (a number or a quantity, with its signs), or None."""
    sign = 1
    while isinstance(node, n.Unary) and node.op in ('-', '+'):
        sign = -sign if node.op == '-' else sign
        node = node.operand
    if isinstance(node, (n.Number, n.Quantity)):
        return sign * node.value, node
    return None


class Resolver:
    """Resolves the parts of one parsed text against a table of units."""

    def __init__(self, tree, units):
        self.tree, self.units = tree, units
        self.problems, self.deferred = [], []
        self.entities, self.root, self.records, self.templates, self.tables = {}, {}, {}, set(), set()
        self.syntax, self.done, self.active = {}, {}, set()
        for item in tree.items:
            if isinstance(item, n.Entity) and item.name[:1].islower():
                self.entities[item.name] = item
                for member in item.members:
                    name = getattr(member, 'name', None)
                    if isinstance(member, (n.Declaration, n.Flow, n.Event, n.Solver)) and name:
                        self.syntax[f'{item.name}.{name}'] = (item.name, member)
            elif isinstance(item, n.Entity):
                self.templates.add(item.name)
            elif isinstance(item, n.Table):
                self.tables.add(item.name)
            elif isinstance(item, n.Declaration):
                self.root[item.name] = item
                self.syntax[item.name] = ('', item)
            elif isinstance(item, n.Record):
                self.records[item.name] = item

    def fail(self, code, message, node=None):
        raise Refused(code, message, node)

    def report(self, code, message, line=0, column=0):
        self.problems.append(Problem(code, message, line, column))

    # ---- types and units ---------------------------------------------------------------------

    def num(self, spelling, node=None):
        found = self.units.of(spelling)
        if found is None:
            unknown = [name for _, name in factors(spelling) if name != '1' and not self.units.has(name)]
            self.fail(
                'unit',
                f'{unknown[0]} is no unit of the library or of the model'
                + close(unknown[0], self.units.base),
                node,
            )
        return Num(spelling, found[0])

    def declared_type(self, node):
        """The type that a declaration writes; `formula(T)` gives (T, True)."""
        if isinstance(node, n.FormulaType):
            inner, retained = self.declared_type(node.of)
            if retained:
                self.fail('type', 'a formula of a formula: reading a formula gives its value', node)
            return inner, True
        if isinstance(node, n.WordType):
            return (PLAIN if node.word == 'number' else Word(node.word)), False
        if isinstance(node, n.NamedType):
            if node.name in self.templates:
                raise Later('a link to a template', 'S1')
            if node.name[:1].isupper() and not self.units.has(node.name):
                self.fail(
                    'unknown_name',
                    f'{node.name} is no unit and no template' + close(node.name, self.templates),
                    node,
                )
            return self.num(node.name, node), False
        if isinstance(node, n.UnitType):
            return self.num(spelling_of(flat_unit(node.unit)), node), False
        if isinstance(node, n.DistributionType):
            inner, _ = self.declared_type(node.of)
            if not isinstance(inner, Num):
                raise Later('a distribution of an enum', 'S4')
            return Dist(inner), False
        if isinstance(node, n.EnumType):
            raise Later('an enum', 'S4')
        if isinstance(node, n.CollectionType):
            raise Later('a collection', 'S1')
        self.fail('type', 'no type', node)

    # ---- expressions -----------------------------------------------------------------------------

    def expression(self, node, scope, unit=None):
        """The typed form of an expression in a scope (`''` for the top level, or an entity's name).
        `unit` is the declared unit that a bare number takes (the whole initializer)."""
        found = literal(node)
        if found is not None:
            value, written = found
            if isinstance(written, n.Quantity):
                return self.quantity(value, written, scope)
            if unit is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
                return Const(value, unit)
            return Const(value, PLAIN)
        if isinstance(node, n.Bool):
            return Const(node.value, BOOL)
        if isinstance(node, n.Text):
            return Const(node.value, TEXT)
        if isinstance(node, (n.Name, n.Member)):
            found = self.path(node, scope)
            if isinstance(found, (EntityRef, FlowRef)):
                what = 'an entity' if isinstance(found, EntityRef) else 'a flow'
                self.fail(
                    'type',
                    f'{what} is no value: read one of its values, as tank.water or delivery.actual_rate',
                    node,
                )
            return found
        if isinstance(node, n.Method):
            if node.name == 'diff':
                self.fail('not_in_v1', 'formula differentiation (.diff) is not in the first version', node)
            if node.name == 'start':
                self.fail('start', '.start(...) starts an occurrence and gives no value', node)
            raise Later(*LATER_METHODS[node.name])
        if isinstance(node, n.Call):
            return self.call(node, scope)
        if isinstance(node, n.Formula):
            self.fail(
                'formula',
                'formula(...) keeps a calculation where a value stands: it is the whole initializer',
                node,
            )
        if isinstance(node, n.Collection):
            raise Later('a collection', 'S1')
        if isinstance(node, n.Unary):
            operand = self.expression(node.operand, scope)
            if node.op == 'not':
                self.want_bool(operand, node, 'not')
                return Apply('not', (operand,), BOOL)
            self.want_number(operand, node, node.op)
            return operand if node.op == '+' else Apply('neg', (operand,), operand.type)
        if isinstance(node, n.Binary):
            return self.binary(node, scope)
        if isinstance(node, n.Compare):
            operands = [self.expression(item, scope) for item in node.operands]
            for k, op in enumerate(node.ops):
                operands[k], operands[k + 1] = self.alike(operands[k], operands[k + 1], node, op)
            return Apply('compare', tuple(operands), BOOL, node.ops)
        if isinstance(node, n.BoolOp):
            values = tuple(self.expression(item, scope) for item in node.values)
            for value in values:
                self.want_bool(value, node, node.op)
            return Apply(node.op, values, BOOL)
        if isinstance(node, n.IfElse):
            test = self.expression(node.test, scope)
            self.want_bool(test, node, 'if')
            body, orelse = self.alike(
                self.expression(node.body, scope), self.expression(node.orelse, scope), node, 'if'
            )
            return Apply('if', (test, body, orelse), body.type if body.type != PLAIN else orelse.type)
        if isinstance(node, n.Within):
            value = self.expression(node.value, scope)
            self.want_number(value, node, 'in')
            tests = []
            if node.low is not None:
                low, value = self.alike(self.expression(node.low, scope), value, node, 'in')
                tests.append(Apply('compare', (low, value), BOOL, ('<=',)))
            if node.high is not None:
                value, high = self.alike(value, self.expression(node.high, scope), node, 'in')
                tests.append(Apply('compare', (value, high), BOOL, ('<=',)))
            if len(tests) == 2:
                return Apply('compare', (tests[0].args[0], value, tests[1].args[1]), BOOL, ('<=', '<='))
            return tests[0]
        self.fail('syntax', f'{type(node).__name__} is no value here', node)

    def quantity(self, value, node, scope):
        """A number and its unit run: the names that are units, then the names that are values."""
        first = node.unit[0][1]
        if not self.units.has(first):
            self.fail(
                'unit',
                f'{first} is no unit of the library or of the model' + close(first, self.units.base),
                node,
            )
        taken = [(1, first)]
        k = 1
        while k < len(node.unit) and self.units.has(node.unit[k][1]):
            taken.append((1 if node.unit[k][0] == '*' else -1, node.unit[k][1]))
            k += 1
        spelling = taken[0][1] + ''.join(('*' if sign > 0 else '/') + name for sign, name in taken[1:])
        result = Const(value, self.num(spelling, node))
        for op, name in node.unit[k:]:
            other = self.path(n.Name(name, line=node.line, column=node.column), scope)
            if isinstance(other, (EntityRef, FlowRef)):
                self.fail('type', f'{name} is no value', node)
            result = self.product('mul' if op == '*' else 'div', result, other, node)
        return result

    def binary(self, node, scope):
        left, right = self.expression(node.left, scope), self.expression(node.right, scope)
        if node.op in ('+', '-'):
            left, right = self.alike(left, right, node, node.op)
            self.want_number(left, node, node.op)
            kind = left.type if left.type != PLAIN or right.type == PLAIN else right.type
            return Apply('add' if node.op == '+' else 'sub', (left, right), kind)
        if node.op in ('*', '/'):
            return self.product('mul' if node.op == '*' else 'div', left, right, node)
        self.want_number(left, node, '**')
        self.want_number(right, node, '**')
        if right.type.dimension:
            self.fail('unit', 'an exponent has no unit', node)
        if not left.type.dimension:
            return Apply('pow', (left, right), PLAIN)
        if not (isinstance(right, Const) and isinstance(right.value, int) and right.value > 0):
            self.fail(
                'unit', f'a value in {left.type} is raised only to a whole number written in place', node
            )
        spelling = spelling_of(factors(left.type.unit) * right.value)
        return Apply('pow', (left, right), self.num(spelling, node))

    def product(self, op, left, right, node):
        self.want_number(left, node, '*' if op == 'mul' else '/')
        self.want_number(right, node, '*' if op == 'mul' else '/')
        found = factors(left.type.unit) if left.type.unit else []
        other = factors(right.type.unit) if right.type.unit else []
        if op == 'div':
            other = [(-sign, name) for sign, name in other]
        return Apply(
            op, (left, right), self.num(spelling_of(found + other), node) if found or other else PLAIN
        )

    def alike(self, left, right, node, op):
        """Two operands of one dimension; a bare zero takes the other's unit."""
        if isinstance(left.type, Num) and isinstance(right.type, Num):
            if left.type.dimension != right.type.dimension:
                if _zero(left) and not left.type.dimension:
                    return Const(left.value, right.type), right
                if _zero(right) and not right.type.dimension:
                    return left, Const(right.value, left.type)
                self.fail(
                    'unit', f'{op} needs one dimension on both sides: {left.type} and {right.type}', node
                )
            return left, right
        if left.type != right.type:
            self.fail('type', f'{op} needs one type on both sides: {left.type} and {right.type}', node)
        if op not in ('==', '!=', 'if'):
            self.fail('type', f'{left.type} has == and != only', node)
        return left, right

    def want_number(self, value, node, op):
        if not isinstance(value.type, Num):
            hint = ': write (1 if c else 0)' if value.type == BOOL else ''
            self.fail('type', f'{op} takes numbers, not {value.type}{hint}', node)

    def want_bool(self, value, node, op):
        if value.type != BOOL:
            self.fail('type', f'{op} takes a yes/no, not {value.type}', node)

    def call(self, node, scope):
        if node.function in LATER_CALLS or (node.function in ('min', 'max') and len(node.args) == 1):
            raise Later(*LATER_CALLS.get(node.function, ('a reduction', 'S1')))
        if node.function in ARITY or node.function == 'categorical':
            self.fail(
                'draw',
                f'{node.function}(...) is a distribution: it is the whole initializer of a value or an '
                'input, and a draw of it the default of an input',
                node,
            )
        args = [self.expression(arg, scope) for arg in node.args]
        for arg in args:
            self.want_number(arg, node, node.function)
        wanted = {'clip': 3, 'abs': 1, 'sqrt': 1}.get(node.function, 1 if node.function in PURE else None)
        if wanted is not None and len(args) != wanted:
            self.fail(
                'arguments', f'{node.function} takes {wanted} argument' + ('s' if wanted > 1 else ''), node
            )
        if node.function in ('min', 'max', 'clip'):
            if len(args) < 2:
                self.fail('arguments', f'{node.function} of values takes two at least', node)
            reference = next((arg for arg in args if arg.type != PLAIN), args[0])
            for k, arg in enumerate(args):
                _, args[k] = self.alike(reference, arg, node, node.function)
            return Apply('call', tuple(args), reference.type, node.function)
        if node.function == 'abs':
            return Apply('call', tuple(args), args[0].type, 'abs')
        if node.function == 'sqrt':
            powers = {}
            for sign, name in factors(args[0].type.unit) if args[0].type.unit else []:
                powers[name] = powers.get(name, 0) + sign
            if any(power % 2 for power in powers.values()):
                self.fail('unit', f'sqrt of {args[0].type}: each unit of it needs an even power', node)
            half = [
                (1 if power > 0 else -1, name)
                for name, power in powers.items()
                for _ in range(abs(power) // 2)
            ]
            return Apply('call', tuple(args), self.num(spelling_of(half), node) if half else PLAIN, 'sqrt')
        if args[0].type.dimension:
            self.fail('unit', f'{node.function} takes a plain number, not {args[0].type}', node)
        return Apply('call', tuple(args), PLAIN, node.function)

    # ---- paths -------------------------------------------------------------------------------------

    def path(self, node, scope):
        """What a name or a dotted path names: a value (`Read`), an entity, or a flow."""
        if isinstance(node, n.Name):
            return self.name(node, scope)
        base = self.path(node.base, scope)
        if isinstance(base, EntityRef):
            return self.entity_part(base, node.name, node)
        if isinstance(base, FlowRef):
            if node.name in FLOW_READS:
                return Read(base.start, (*base.steps, node.name), base.rate)
            if node.name in ('source', 'sink'):
                raise Later("a flow's ends as values", 'S2')
            self.fail(
                'unknown_name',
                f'a directed flow reads actual_rate, request and capacity, not {node.name}',
                node,
            )
        if node.name in ('outflow', 'inflow'):
            raise Later('the settings of an endpoint (outflow, inflow)', 'S2')
        if isinstance(base.type, Dist) and node.name in ('mean', 'std'):
            raise Later("a distribution's mean and std", 'S4')
        self.fail('unknown_name', f'{node.name} is no part of a {base.type} value', node)

    def name(self, node, scope):
        name = node.name
        if name == 'this':
            if not scope:
                self.fail('unknown_name', 'this is the entity of a member: the top level has none', node)
            return EntityRef(scope, ('this',))
        if name == 't':
            return Read(('time',), (), self.num('h', node))
        if name in self.root:
            value = self.value(name)
            return Read(('root',), (name,), value.type)
        if name in self.entities:
            return EntityRef(name, ('named', name))
        if name in self.templates:
            raise Later('a template and its instances', 'S1')
        if name in self.tables:
            raise Later('a table', 'S1')
        if name[:1].isupper():
            raise Later('a member of an enum', 'S4')
        known = [*self.root, *self.entities]
        self.fail('unknown_name', f'{name} names nothing here' + close(name, known), node)

    def entity_part(self, entity, name, node):
        path = f'{entity.name}.{name}'
        if path not in self.syntax:
            parts = [key.split('.', 1)[1] for key in self.syntax if key.startswith(f'{entity.name}.')]
            self.fail('unknown_name', f'{entity.name} has no {name}' + close(name, parts), node)
        _, syntax = self.syntax[path]
        if isinstance(syntax, n.Flow):
            return FlowRef(path, entity.start, (name,), self.rate(path))
        if isinstance(syntax, n.Declaration):
            return Read(entity.start, (name,), self.value(path).type)
        raise Later('an event', 'S4') if isinstance(syntax, n.Event) else Later('a solver', 'S5')

    # ---- values ------------------------------------------------------------------------------------

    def value(self, path):
        """The declared value of a path, resolved once; a later-slice value raises `Later` again."""
        if path in self.done:
            found = self.done[path]
            if isinstance(found, Deferred):
                raise Later(found.construct, found.slice)
            if found is None:
                raise Refused('depends', f'{path} has a problem of its own')
            return found
        owner, syntax = self.syntax[path]
        if path in self.active:
            self.fail(
                'cycle',
                f'{path} reads itself through its initializer: its starting value has no order',
                syntax,
            )
        self.active.add(path)
        try:
            found = self.declaration(path, owner, syntax)
        except Later as later:
            self.done[path] = Deferred(path, later.construct, later.slice, syntax.line)
            raise
        except Refused:
            self.done[path] = None
            raise
        finally:
            self.active.discard(path)
        self.done[path] = found
        return found

    def declaration(self, path, scope, node):
        if node.properties:
            raise Later('the settings of an endpoint (outflow, inflow)', 'S2')
        declared, retained = (None, False) if node.type is None else self.declared_type(node.type)
        if node.value is None:
            if (
                isinstance(node.type, n.NamedType)
                and node.type.name[:1].isupper()
                and not self.units.has(node.type.name)
            ):
                raise Later('an instance of a template', 'S1')
            self.fail(
                'no_value', f'{node.name} has no starting value: an annotation gives no value (D4)', node
            )
        unit = declared if isinstance(declared, Num) else None
        kind, init = self.initializer(node, scope, declared, retained, unit)
        value_type = init.type if declared is None else declared
        if declared is not None and not compatible(init.type, declared):
            code = 'unit' if isinstance(declared, Num) and isinstance(init.type, Num) else 'type'
            self.fail(code, f'{node.name} is declared {declared}, and its initializer is {init.type}', node)
        lower = upper = scale = None
        if node.range is not None:
            if not isinstance(value_type, Num):
                self.fail(
                    'range', f'a range belongs to a number, and {node.name} is {value_type}', node.range
                )
            lower, upper = (
                self.bound(end, scope, value_type, node) for end in (node.range.low, node.range.high)
            )
            if isinstance(lower, Const) and isinstance(upper, Const) and lower.value > upper.value:
                self.fail(
                    'range',
                    f'the range of {node.name} is reversed: [{lower.value}, {upper.value}]',
                    node.range,
                )
        if node.scale is not None:
            if not isinstance(value_type, Num):
                self.fail('range', f'a scale belongs to a number, and {node.name} is {value_type}', node)
            scale = self.bound(node.scale, scope, value_type, node)
        if kind == INPUT and isinstance(init, Drawn):
            lower, upper = self.support(init.source, lower, upper, node)
        evidence = self.evidence(node)
        return DeclaredValue(
            path,
            node.name,
            kind,
            value_type,
            init,
            lower,
            upper,
            scale,
            node.modifier == 'readonly',
            node.text,
            evidence,
            node.line,
        )

    def initializer(self, node, scope, declared, retained, unit):
        """(kind, typed initializer) of a declaration."""
        value = node.value
        if isinstance(value, n.Formula):
            if node.modifier == 'input':
                self.fail('formula', 'an input is fixed for the run: it cannot keep a calculation', node)
            if declared is not None and not retained:
                self.fail(
                    'formula',
                    f'{node.name} keeps a calculation: declare it {node.name}: formula({declared})',
                    node,
                )
            body = self.expression(value.body, scope)
            return FORMULA, Retain(body, body.type)
        if retained:
            self.fail('formula', f'{node.name} is declared a formula: its initializer is formula(...)', node)
        if isinstance(value, n.Call) and (value.function in ARITY or value.function == 'categorical'):
            source = self.distribution(value, unit.of if isinstance(unit, Dist) else unit)
            return (INPUT if node.modifier == 'input' else DISTRIBUTION), source
        if isinstance(value, n.Method) and value.name == 'draw' and not value.args:
            if node.modifier != 'input':
                raise Later(*LATER_METHODS['draw'])
            if not (isinstance(value.base, n.Call) and value.base.function in ARITY):
                raise Later('the draw of a distribution that a value holds', 'S4')
            source = self.distribution(value.base, unit)
            return INPUT, Drawn(source, source.type.of)
        init = self.expression(value, scope, unit)
        return (INPUT if node.modifier == 'input' else STATE), init

    def bound(self, node, scope, unit, owner):
        """An end of a range, or a scale: a bare number takes the value's unit."""
        if node is None:
            return None
        found = self.expression(node, scope, unit)
        if not compatible(found.type, unit):
            if _zero(found):
                return Const(found.value, unit)
            self.fail(
                'unit', f'the range and the scale of {owner.name} are in {unit}, not {found.type}', node
            )
        return found

    def distribution(self, node, unit):
        """A distribution of numbers: its value arguments take the declared unit, or they write one."""
        if node.function == 'categorical':
            raise Later('a categorical distribution', 'S4')
        if len(node.args) not in ARITY[node.function]:
            counts = ' or '.join(str(count) for count in ARITY[node.function])
            self.fail('arguments', f'{node.function} takes {counts} arguments', node)
        found = [literal(arg) for arg in node.args]
        if any(item is None for item in found):
            raise Later('a distribution whose arguments are values', 'S4')
        shapes = SHAPES.get(node.function, set())
        written = {
            item[1].unit
            for k, item in enumerate(found)
            if k not in shapes and isinstance(item[1], n.Quantity)
        }
        target = unit
        if target is None and written:
            first = next(
                item for k, item in enumerate(found) if k not in shapes and isinstance(item[1], n.Quantity)
            )
            target = self.quantity(1, first[1], '').type
        target = target or PLAIN
        params = []
        for k, (value, written_node) in enumerate(found):
            if k in shapes:
                if isinstance(written_node, n.Quantity):
                    self.fail('unit', f'the argument {k + 1} of {node.function} is a plain number', node)
                params.append(value)
                continue
            if isinstance(written_node, n.Quantity):
                own = self.quantity(1, written_node, '').type
                if own.dimension != target.dimension:
                    self.fail('unit', f'{node.function} takes its arguments in {target}, not {own}', node)
                params.append(
                    _converted(
                        value, self.units.of(own.unit)[1], self.units.of(target.unit)[1] if target.unit else 1
                    )
                )
            elif target.dimension and unit is None:
                self.fail(
                    'unit', f'{node.function} has an argument with no unit beside one in {target}', node
                )
            else:
                params.append(value)
        return Distribution(node.function, tuple(params), Dist(target))

    def support(self, source, lower, upper, node):
        """The range of an input whose default draws: the written range, which must hold the support
        of the distribution, or the support of a bounded distribution."""
        params, unit = source.params, source.type.of
        if len(params) == 4:
            ends = (params[2], params[3])
        elif source.family == 'normal':
            ends = (-math.inf, math.inf)
        elif source.family == 'lognormal':
            ends = (0, math.inf)  # above zero; the default range leaves both sides open
        else:
            ends = (params[0], params[-1])
        if lower is None and upper is None:
            if source.family in ('normal', 'lognormal') and len(params) == 2:
                return None, None
            return Const(ends[0], unit), Const(ends[1], unit)
        scale = self.scale(unit)
        for end, bound, sign in ((ends[0], lower, 1), (ends[1], upper, -1)):
            if not isinstance(bound, Const):
                continue
            if sign * (bound.value * self.scale(bound.type) - end * scale) > 0:
                self.fail(
                    'range',
                    f'the range of {node.name} must hold the support of its distribution, '
                    f'[{ends[0]}, {ends[1]}] {unit.unit}'.rstrip(),
                    node,
                )
        return lower, upper

    def scale(self, kind):
        """The size of one of a number's unit in the canonical unit of its dimension."""
        return self.units.of(kind.unit)[1] if kind.unit else 1

    def evidence(self, node):
        """The records that a line cites and those written under it; each cited name is a record."""
        found = (*node.cites, *node.evidence)
        for item in found:
            if isinstance(item, n.Cite) and item.name not in self.records:
                self.fail(
                    'unknown_record',
                    f'@{item.name} names no record of the model' + close(item.name, self.records),
                    item,
                )
        return found

    # ---- flows -------------------------------------------------------------------------------------

    def rate(self, path):
        """The type of a flow's rates, from its ends (a store's unit per hour), or for `SOURCE ->
        SINK` from a rate written with its unit."""
        owner, node = self.syntax[path]
        if not node.arrow:
            raise Later('a flow with legs', 'S3')
        if node.arrow == '<->':
            raise Later('a reversible route', 'S3')
        # As the program's builder does: a rate written with its unit first, then a store's unit per hour.
        for item in node.properties:
            found = literal(item.value.body if isinstance(item.value, n.Formula) else item.value)
            if (
                item.path[-1] in ('request', 'capacity')
                and found is not None
                and isinstance(found[1], n.Quantity)
            ):
                return self.quantity(1, found[1], owner).type
        for end in (node.source, node.sink):
            if end not in (('SOURCE',), ('SINK',)):
                store = self.store(end, owner, node)
                return self.num(f'{store.type.unit}/h' if store.type.unit else '1/h', node)
        self.fail('flow_units', f'flow {node.name}: SOURCE -> SINK needs a rate written with its unit', node)

    def store(self, end, owner, node):
        """The stored number that an end of a flow names: `this.water` or `tank.water`."""
        if len(end) != 2:
            raise Later('an end of a flow through a link or a local', 'S1' if len(end) > 2 else 'S4')
        head, name = end
        if head == 'this':
            entity = owner
        elif head in self.entities:
            entity = head
        else:
            self.fail('unknown_name', f'{head} names no entity' + close(head, self.entities), node)
        path = f'{entity}.{name}'
        if path not in self.syntax or not isinstance(self.syntax[path][1], n.Declaration):
            self.fail('flow_end', f'{".".join(end)} is no stored number of {entity}', node)
        value = self.value(path)
        if value.kind != STATE or not isinstance(value.type, Num):
            self.fail(
                'flow_end',
                f'{".".join(end)} is no stored number: a flow ends at a stored value, SOURCE or SINK',
                node,
            )
        return value

    def flow(self, path, owner, node):
        rate = self.rate(path)
        ends = []
        for end in (node.source, node.sink):
            if end in (('SOURCE',), ('SINK',)):
                ends.append(end[0])
                continue
            store = self.store(end, owner, node)
            per_hour = self.units.of(f'{store.type.unit}/h' if store.type.unit else '1/h')[0]
            if per_hour != rate.dimension:
                self.fail(
                    'flow_units',
                    f'flow {node.name}: its ends and its rates are of two dimensions '
                    f'({store.type} against {rate}; a rate is its stock per time)',
                    node,
                )
            start = ('this',) if end[0] == 'this' else ('named', end[0])
            ends.append(Read(start, (end[1],), store.type))
        settings = {}
        for item in node.properties:
            key = item.path[-1] if len(item.path) == 1 else '.'.join(item.path)
            if key not in ('request', 'capacity'):
                if len(item.path) > 1 and item.path[0] in ('outflow', 'inflow'):
                    raise Later('the settings of an endpoint (outflow, inflow)', 'S2')
                self.fail('property', f'a directed flow takes request and capacity, not {key}', item)
            if key in settings:
                self.fail('property', f'{key} is given twice', item)
            if isinstance(item.value, n.Formula):
                body = self.expression(item.value.body, owner)
                found = Retain(body, body.type)
            else:
                found = self.expression(item.value, owner)
            if not compatible(found.type, rate):
                if _zero(found):
                    found = Const(found.value, rate)
                else:
                    self.fail('unit', f'the {key} of {node.name} is a rate in {rate}, not {found.type}', item)
            settings[key] = found
        return DeclaredFlow(
            path,
            node.name,
            ends[0],
            ends[1],
            rate,
            settings.get('request'),
            settings.get('capacity'),
            node.text,
            self.evidence(node),
            node.line,
        )

    # ---- the model ---------------------------------------------------------------------------------

    def part(self, path, owner, node):
        """A declared part of an entity, a `Deferred` one, or None after a problem."""
        try:
            if isinstance(node, n.Declaration):
                return self.value(path)
            if isinstance(node, n.Flow):
                return self.flow(path, owner, node)
        except Later as later:
            return Deferred(path, later.construct, later.slice, node.line)
        except Refused as refused:
            if refused.code != 'depends':
                self.report(refused.code, refused.message, refused.line or node.line, refused.column)
            return None
        construct, slice_ = {
            n.Event: ('an event', 'S4'),
            n.Solver: ('a solver', 'S5'),
            n.Status: ('a status display', 'C'),
            n.Assert: ('an assertion', 'S1'),
            n.Sees: ('sees', 'S4'),
            n.Property: ('a property set by its path', 'S1'),
        }[type(node)]
        return Deferred(path, construct, slice_, node.line)

    def model(self):
        entities, root, notes, scenario = [], [], [], None
        top_later = {
            n.Entity: ('a template and its instances', 'S1'),
            n.Table: ('a table', 'S1'),
            n.Use: ('use', 'S6'),
            n.Change: ('change', 'S6'),
            n.Options: ('options', 'S6'),
            n.Runs: ('runs', 'S6'),
            n.Assert: ('an assertion', 'S1'),
            n.Property: ('a property set by its path', 'S1'),
        }
        for index, item in enumerate(self.tree.items):
            if isinstance(item, n.Scenario):
                scenario = self.scenario(item)
            elif isinstance(item, n.Entity) and item.name in self.entities:
                parts = []
                for k, member in enumerate(item.members):
                    name = getattr(member, 'name', None) or f'{type(member).__name__.lower()}[{k}]'
                    found = self.part(f'{item.name}.{name}', item.name, member)
                    if isinstance(found, Deferred):
                        self.deferred.append(found)
                    elif found is not None:
                        parts.append(found)
                try:
                    evidence = self.evidence(item)
                except Refused as refused:
                    self.report(refused.code, refused.message, refused.line, refused.column)
                    evidence = ()
                entities.append(
                    DeclaredEntity(
                        item.name, tuple(parts), item.text, item.title, item.role, evidence, item.line
                    )
                )
            elif isinstance(item, n.Declaration):
                found = self.part(item.name, '', item)
                if isinstance(found, Deferred):
                    self.deferred.append(found)
                elif found is not None:
                    root.append(found)
            elif isinstance(item, n.Notes):
                notes.extend(item.notes)
            elif isinstance(item, n.Record):
                continue
            else:
                construct, slice_ = top_later[type(item)]
                self.deferred.append(
                    Deferred(
                        getattr(item, 'name', '') or f'{type(item).__name__.lower()}[{index}]',
                        construct,
                        slice_,
                        item.line,
                    )
                )
        if scenario is not None and scenario.role == 'variant':
            self.deferred.append(Deferred('scenario', 'a variant', 'S6', scenario.line))
        self.check_names()
        if self.problems:
            raise LanguageError(sorted(self.problems, key=lambda item: (item.line, item.column)))
        return DeclaredModel(
            scenario,
            tuple(entities),
            tuple(root),
            tuple(self.records.values()),
            tuple(notes),
            tuple(self.deferred),
            self.units,
            self.tree,
        )

    def check_names(self):
        """Two declarations of one scope with one name are an error."""
        seen = {}
        for item in self.tree.items:
            name = getattr(item, 'name', None)
            if isinstance(item, (n.Entity, n.Table, n.Declaration)) and name:
                if name in seen:
                    self.report(
                        'duplicate_name',
                        f'{name} is declared twice; the first is on line {seen[name]}',
                        item.line,
                    )
                seen.setdefault(name, item.line)
            if isinstance(item, n.Entity):
                own = {}
                for member in item.members:
                    member_name = getattr(member, 'name', None)
                    if isinstance(member, (n.Declaration, n.Flow, n.Event, n.Solver)) and member_name:
                        if member_name in own:
                            self.report(
                                'duplicate_name',
                                f'{item.name}.{member_name} is declared twice; the first is '
                                f'on line {own[member_name]}',
                                member.line,
                            )
                        own.setdefault(member_name, member.line)

    def scenario(self, node):
        def hours(value, key):
            if value is None:
                return None
            try:
                found = self.expression(value, '')
            except (Refused, Later):
                self.report('scenario', f'{key} is a time, such as 30 days', node.line)
                return None
            if not isinstance(found, Const) or found.type.dimension != (('time', 1),):
                self.report('scenario', f'{key} is a time, such as 30 days', node.line)
                return None
            return _converted(found.value, self.units.of(found.type.unit)[1], 1)

        return Scenario(
            'main' if node.role == 'scenario' else 'variant',
            node.title,
            node.summary,
            node.scope,
            node.library,
            hours(node.horizon, 'horizon'),
            hours(node.resolution, 'resolution'),
            tuple(hours(item, 'timescales') for item in node.timescales),
            node.line,
        )


def _zero(value):
    return (
        isinstance(value, Const)
        and isinstance(value.value, (int, float))
        and value.value == 0
        and value.type == PLAIN
    )


def _converted(value, scale_from, scale_to):
    """A number in one unit written in another: exact for a whole number, a float otherwise."""
    if scale_from == scale_to:
        return value
    if isinstance(value, int):
        found = Fraction(value) * Fraction(scale_from) / Fraction(scale_to)
        return int(found) if found.denominator == 1 else found
    return float(value * scale_from / scale_to)


def declare(tree, units):
    """The declared model of a parsed text (`nodes.File`) with a table of units (`Units`, or a table
    as `Units` takes it). Raises `LanguageError` with every problem that it finds."""
    return Resolver(tree, units if isinstance(units, Units) else Units(units)).model()
