"""Builders: the short Python API with which tests, and the front end's lowering, make programs.

The tank of the spec, which delivers 3 L/h until it empties at 2 hours 40 minutes::

    from napkin.program.build import SINK, Builder, flow, q, value

    b = Builder({'L': {'volume': 1}, 'h': {'time': 1}})
    tank = b.entity('tank', value('water', 'L', 8, lower=0, upper=20, readonly=True))
    b.entity(
        'clinic',
        flow('delivery', tank.water, SINK, capacity=q(5, 'L/h'), request=q(3, 'L/h')),
    )
    program = b.finish()

An expression is written with handles (`X`): `this`, `local` (a bare name), `item`, `root`, `t`, a
member that `entity`, `member`, `named` or a table gives, `q(number, unit)`, `call` of a function
of the language (`call('abs', x)`), and the functions below. A handle on a path takes more steps by
attribute (`this.origin.level`), also a step named as an operation of a handle: `this.start` reads
the field `start`, and `this.start()` starts it (so too `draw`, `where`, `by`, `at` and `choose`).
Operators make nodes of `napkin/core/expr` (`&`, `|`, `~` are `and`, `or`, `not`). A node that no
operator makes, such as a chain of comparisons or an `and` of three values, is made with
`napkin/core/expr` and wrapped as `X(node, reads)` (see `X`). The part
constructors (`value`, `flow`, `event`, `after`, `solver`, ...) make the records of `parts.py`, and
`Builder` puts them into templates, members, the root and the setup.

`finish()` makes the program and checks it (`check.check`), raising `ProgramError` with each
refusal. On the way it gives each part its origin from its place (`grinder.refill.step[0].do[1]`),
each draw and choice its site (`<origin>.draw[0]`, in place of the temporary site that `draw` and
`choose` give), each name of a node the spelling of its read, each flow without a unit the unit of
its ends per hour (`1/h` for ends that are plain numbers, as the front end writes it), and the
program the table of the units that it spells. A unit is spelled with `*` and `/` over the units
that the builder is given (`L/h`, `person*year`, `1/h`, D12). A bare number where a declared unit is
expected (an initializer, a bound, a table cell) takes that unit, as in the language. The rows of a
table with ids are kept in the order of their ids (R-A4a-02); the other members in the order of
their declarations.
"""

from __future__ import annotations

import functools
import itertools
import re
from dataclasses import fields, is_dataclass, replace
from fractions import Fraction

from ..core import expr as nodes
from . import check as checking
from . import parts as p
from .parts import BOOL, PROPORTIONAL, TEXT
from .parts import SINK as SINK
from .parts import SOURCE as SOURCE
from .refs import (
    ITEM,
    ROOT,
    THIS,
    TIME,
    By,
    Choice,
    Delayed,
    Distribution,
    Draw,
    Elapsed,
    EnumValue,
    Expr,
    Formula,
    Instances,
    Literal,
    Local,
    Lookup,
    Named,
    Path,
    Reduce,
    Since,
    Where,
    spelled,
)

# A temporary site of a draw or a choice until `finish` gives it its place; each is distinct.
_TOKENS = itertools.count()


# ---- handles on expressions ---------------------------------------------------------------------


class _Operation:
    """An operation of a handle that is also a step of its path: `c.where` is the handle of the
    field `where` of what `c` names (a `_Step`), and `c.where(test)` calls the operation. So a field
    of any name can be read through a handle, a model's `start`, `draw` or `at` among them."""

    def __init__(self, function):
        self.function = function
        self.__doc__ = function.__doc__

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, handle, owner=None):
        if handle is None:
            return self
        if handle._path is None:
            # No path, no field: the call alone, which refuses what has no path.
            return functools.partial(self.function, handle)
        return _Step(handle, self.name, self.function)


class X:
    """A handle on an expression while a program is built: a node of `napkin/core/expr` and the read
    of each of its names. A handle on a path (`_path`) takes more steps by attribute.

    `X(node, reads)` wraps any node, with `reads` as {name in the node: its read}: the way to write
    a node that no operator and no function of this module makes, such as a chain of comparisons
    or an `and` of more than two values. `0 <= this.share < 1`, which reads the share once::

        X(
            nodes.compare(['le', 'lt'], [nodes.written(0), nodes.ref('share'), nodes.written(1)]),
            {'share': Path(THIS, ('share',))},
        )

    Each read is a record of `refs.py` (a `Path`, `TIME`, a `Draw`, ...), and `finish` spells the
    names of the node after their reads."""

    __slots__ = ('_node', '_path', '_reads')

    def __init__(self, node, reads, path=None):
        object.__setattr__(self, '_node', node)
        object.__setattr__(self, '_reads', dict(reads))
        object.__setattr__(self, '_path', path)

    @classmethod
    def read(cls, read):
        """The handle that reads one read."""
        name = spelled(read)
        return cls(nodes.ref(name), {name: read}, read if isinstance(read, Path) else None)

    def __setattr__(self, name, value):
        raise AttributeError('a handle does not change')

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return X.read(self._own_path().then(name))

    def __bool__(self):
        raise TypeError('an expression has no truth value while a program is built: use & | ~')

    __hash__ = object.__hash__

    def __repr__(self):
        return f'X({nodes.text(self._node)})'

    def _own_path(self):
        if self._path is None:
            raise TypeError(f'{nodes.text(self._node)} is no path: only a path takes a step')
        return self._path

    # The operations of a collection, a distribution, an actor or an event that a path names. Each is
    # also a step: unless it is called, `this.start` reads the field `start`.

    @_Operation
    def where(self, test):
        """`c.where(test)`; the test reads the member through `item`."""
        return X.read(Path(Where(self._own_path(), expr_of(test))))

    @_Operation
    def by(self, key):
        """`c.by(key)`: the members keyed by their field `key`."""
        return X.read(Path(By(self._own_path(), key)))

    @_Operation
    def at(self, key):
        """`c.at(key)`: the member with the greatest key at or below `key`."""
        return X.read(Path(Lookup(self._own_path(), expr_of(key))))

    @_Operation
    def draw(self):
        """`d.draw()` of the distribution that this path names."""
        return draw(self)

    @_Operation
    def choose(self, source):
        """`actor.choose(d)`."""
        return choose(self, source)

    @_Operation
    def start(self, *args):
        """`event.start(args)` as a statement."""
        return start(self, *args)

    # Operators.

    def __add__(self, other):
        return _apply(lambda a, b: nodes.binary('add', a, b), self, other)

    def __radd__(self, other):
        return _apply(lambda a, b: nodes.binary('add', a, b), other, self)

    def __sub__(self, other):
        return _apply(lambda a, b: nodes.binary('sub', a, b), self, other)

    def __rsub__(self, other):
        return _apply(lambda a, b: nodes.binary('sub', a, b), other, self)

    def __mul__(self, other):
        return _apply(lambda a, b: nodes.binary('mul', a, b), self, other)

    def __rmul__(self, other):
        return _apply(lambda a, b: nodes.binary('mul', a, b), other, self)

    def __truediv__(self, other):
        return _apply(lambda a, b: nodes.binary('div', a, b), self, other)

    def __rtruediv__(self, other):
        return _apply(lambda a, b: nodes.binary('div', a, b), other, self)

    def __pow__(self, other):
        return _apply(lambda a, b: nodes.binary('pow', a, b), self, other)

    def __neg__(self):
        return _apply(lambda a: nodes.unary('neg', a), self)

    def __invert__(self):
        return _apply(lambda a: nodes.unary('not', a), self)

    def __and__(self, other):
        return _apply(lambda a, b: nodes.boolean('and', [a, b]), self, other)

    def __rand__(self, other):
        return _apply(lambda a, b: nodes.boolean('and', [a, b]), other, self)

    def __or__(self, other):
        return _apply(lambda a, b: nodes.boolean('or', [a, b]), self, other)

    def __ror__(self, other):
        return _apply(lambda a, b: nodes.boolean('or', [a, b]), other, self)

    def __eq__(self, other):
        return _compare('eq', self, other)

    def __ne__(self, other):
        return _compare('ne', self, other)

    def __lt__(self, other):
        return _compare('lt', self, other)

    def __le__(self, other):
        return _compare('le', self, other)

    def __gt__(self, other):
        return _compare('gt', self, other)

    def __ge__(self, other):
        return _compare('ge', self, other)


class _Step(X):
    """The handle of a step named as an operation (`this.start`): it reads that field, and called
    (`this.start()`) it is the operation on the path before the step."""

    __slots__ = ('_call',)

    def __init__(self, receiver, name, operation):
        path = receiver._path.then(name)
        spelling = spelled(path)
        super().__init__(nodes.ref(spelling), {spelling: path}, path)
        object.__setattr__(self, '_call', functools.partial(operation, receiver))

    def __call__(self, *args):
        return self._call(*args)


class _Names:
    """`local.amount` is the bare name `amount` of the scope; `root.total` a value of the root."""

    def __init__(self, start):
        self._start = start

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        if self._start is None:
            return X.read(Path(Local(name)))
        return X.read(Path(self._start, (name,)))


this = X.read(Path(THIS))
item = X.read(Path(ITEM))
t = X.read(TIME)
local = _Names(None)
root = _Names(ROOT)


def named(id):
    """The member with this id, also before it is declared."""
    return X.read(Path(Named(id)))


def literal(*members):
    """`<a, b>`: a collection of the members that the paths name."""
    return X.read(Path(Literal(tuple(_path(member) for member in members))))


def _number_node(number):
    if isinstance(number, Fraction):
        if number.denominator == 1:
            return nodes.written(number.numerator)
        return nodes.binary('div', nodes.written(number.numerator), nodes.const(number.denominator))
    return nodes.written(number)


def _x(value):
    """A handle of a handle, a number, a yes/no or a text."""
    if isinstance(value, X):
        return value
    if isinstance(value, (bool, str)):
        return X(nodes.const(value), {})
    if isinstance(value, (int, float, Fraction)):
        return X(_number_node(value), {})
    raise TypeError(f'no expression of {type(value).__name__}: {value!r}')


def _unit(spelling):
    """A unit as the program spells it: without spaces (`person * year` is `person*year`)."""
    return spelling.replace(' ', '')


def q(number, unit):
    """A number with a unit, the core's literal `q(number, unit)`."""
    return X(nodes.call('q', [_number_node(number), nodes.const(_unit(unit))]), {})


def _free(name, taken):
    index = 1
    while f'{name}#{index}' in taken:
        index += 1
    return f'{name}#{index}'


def _renamed(node, names):
    """A node with some of its names replaced."""
    if isinstance(node, nodes.Ref):
        return nodes.ref(names.get(node.name, node.name))
    if isinstance(node, nodes.Const):
        return node

    def each(items):
        return [_renamed(part, names) for part in items]

    if isinstance(node, nodes.Unary):
        return nodes.unary(node.op, _renamed(node.operand, names))
    if isinstance(node, nodes.Binary):
        return nodes.binary(node.op, _renamed(node.left, names), _renamed(node.right, names))
    if isinstance(node, nodes.Compare):
        return nodes.compare(node.ops, each(node.operands))
    if isinstance(node, nodes.BoolOp):
        return nodes.boolean(node.op, each(node.values))
    if isinstance(node, nodes.IfElse):
        return nodes.if_else(*each((node.test, node.body, node.orelse)))
    if isinstance(node, nodes.Call):
        return nodes.call(node.function, each(node.args))
    raise TypeError(f'no node of a program: {type(node).__name__}')


def _apply(make, *items):
    """The handle of an operation on handles or plain values: the union of their reads, a name that
    two different reads share renamed in the later one."""
    reads, parts = {}, []
    for value in items:
        handle = _x(value)
        renames = {}
        for name, read in handle._reads.items():
            if name in reads and reads[name] != read:
                renames[name] = _free(name, reads.keys() | handle._reads.keys())
                reads[renames[name]] = read
            else:
                reads[name] = read
        parts.append(_renamed(handle._node, renames) if renames else handle._node)
    return X(make(*parts), reads)


def _compare(op, left, right):
    return _apply(lambda a, b: nodes.compare([op], [a, b]), left, right)


def expr_of(value):
    """The `Expr` of a handle or a plain value."""
    handle = _x(value)
    return Expr(handle._node, tuple(sorted(handle._reads.items())))


def _path(value):
    if not isinstance(value, X) or value._path is None:
        raise TypeError(f'a path is expected, not {value!r}')
    return value._path


def _read(read):
    return X.read(read)


# ---- functions of expressions ---------------------------------------------------------------------


def ifelse(test, body, orelse):
    """`body if test else orelse`."""
    return _apply(nodes.if_else, test, body, orelse)


def in_range(value, lower, upper):
    """`value in [lower, upper]`: one chain of comparisons, so the value is read once."""
    return _apply(lambda lo, x, hi: nodes.compare(['le', 'le'], [lo, x, hi]), lower, value, upper)


def call(function, *args):
    """`function(args...)`: a call of a function of the language's closed list
    (`napkin/core/expr.FUNCTIONS`): `abs`, `exp`, `expm1`, `ln`, `log1p`, `sqrt`, `erf`, `min`, `max`,
    `clip`, and `sum`, `any` and `all` of their arguments (of a collection they are `fsum`, `fany`
    and `fall`). A number with a unit is `q`. Any other name is a ValueError."""
    if function not in nodes.FUNCTIONS or function == 'q':
        names = ', '.join(sorted(nodes.FUNCTIONS - {'q'}))
        raise ValueError(f'{function!r} is no function of the language: one of {names}')
    return _apply(lambda *parts: nodes.call(function, parts), *args)


def fmin(*args):
    """`min(a, b, ...)`; of one collection or projection, its reduction."""
    return _read(Reduce('min', _path(args[0]))) if len(args) == 1 else call('min', *args)


def fmax(*args):
    """`max(a, b, ...)`; of one collection or projection, its reduction."""
    return _read(Reduce('max', _path(args[0]))) if len(args) == 1 else call('max', *args)


def fsum(collection):
    """`sum(c.f)`: zero in the projected unit when the collection is empty."""
    return _read(Reduce('sum', _path(collection)))


def count(collection):
    """`count(c)` counts members; `count(c.done)` counts true values."""
    return _read(Reduce('count', _path(collection)))


def fany(collection):
    """`any(c.f)`."""
    return _read(Reduce('any', _path(collection)))


def fall(collection):
    """`all(c.f)`."""
    return _read(Reduce('all', _path(collection)))


def clip(value, lower, upper):
    """`clip(value, lower, upper)`."""
    return call('clip', value, lower, upper)


def sqrt(value):
    """`sqrt(value)`."""
    return call('sqrt', value)


def since(event):
    """`since(e)`: the time since the latest start of an event."""
    return _read(Since(_path(event)))


def elapsed(value):
    """`elapsed(x)`: the time since `x` last changed at a commit."""
    return _read(Elapsed(_path(value)))


def delayed(value, delay):
    """`delayed(x, d)`: the committed value of `x` at `d` before now."""
    return _read(Delayed(_path(value), expr_of(delay)))


def draw(source):
    """`d.draw()` of a distribution, or of the distribution that a path names."""
    origin = source if isinstance(source, Distribution) else _path(source)
    return _read(Draw(origin, f'?{next(_TOKENS)}'))


def choose(actor, source):
    """`actor.choose(d)`: the controller's pick, or a draw of the forecast `d`."""
    origin = source if isinstance(source, Distribution) else _path(source)
    return _read(Choice(_path(actor), origin, f'?{next(_TOKENS)}'))


def formula(value):
    """`formula(e)`: a retained calculation."""
    return Formula(expr_of(value))


# ---- distributions and types -------------------------------------------------------------------


def uniform(lower, upper, unit=''):
    return Distribution('uniform', (lower, upper), _unit(unit))


def triangular(lower, mode, upper, unit=''):
    return Distribution('triangular', (lower, mode, upper), _unit(unit))


def pert(lower, mode, upper, unit=''):
    return Distribution('pert', (lower, mode, upper), _unit(unit))


def loguniform(lower, upper, unit=''):
    return Distribution('loguniform', (lower, upper), _unit(unit))


def normal(mean, sd, unit='', lower=None, upper=None):
    bounds = () if lower is None else (lower, upper)
    return Distribution('normal', (mean, sd, *bounds), _unit(unit))


def lognormal(median, gsd, unit='', lower=None, upper=None):
    bounds = () if lower is None else (lower, upper)
    return Distribution('lognormal', (median, gsd, *bounds), _unit(unit))


def categorical(enum, **weights):
    """`categorical(FIXED: 0.7, FAILED: 0.3)` over the members of an enum (a `Builder.enum`)."""
    return Distribution('categorical', tuple(weights.values()), enum=enum.name, outcomes=tuple(weights))


def ref_to(template):
    """The type of a link or an entity parameter to a member of a template."""
    return p.EntityType(template)


def group_of(template):
    """The type `<Template>`."""
    return p.CollectionType(template)


def dist_of(of):
    """The type of a distribution of numbers in a unit, or of an enum's members."""
    return p.DistributionType(_type(of))


class EnumHandle:
    """An enum of a builder: `E.DONE` is the handle of a member, and `E` a type."""

    def __init__(self, name, members):
        self.name, self.members = name, tuple(members)

    def __getattr__(self, member):
        if member.startswith('_'):
            raise AttributeError(member)
        return _read(EnumValue(self.name, member))


def _type(spec):
    """A type from a unit's spelling, an enum, or a type record."""
    if isinstance(spec, str):
        return p.Number(_unit(spec))
    if isinstance(spec, EnumHandle):
        return p.EnumType(spec.name)
    return spec


def _inferred(init):
    """The type of an initializer that shows it, or None."""
    if isinstance(init, Formula):
        node = init.expr.node
        if isinstance(node, nodes.Ref):
            read = init.expr.read(node.name)
            return p.EnumType(read.enum) if isinstance(read, EnumValue) else None
        return _node_type(node)
    if isinstance(init, Distribution):
        return p.DistributionType(
            p.EnumType(init.enum) if init.family == 'categorical' else p.Number(init.unit)
        )
    if isinstance(init, bool):
        return BOOL
    if isinstance(init, str):
        return TEXT
    if isinstance(init, (int, float, Fraction)):
        return p.Number()
    if isinstance(init, X):
        if len(init._reads) == 1 and isinstance(init._node, nodes.Ref):
            read = next(iter(init._reads.values()))
            return p.EnumType(read.enum) if isinstance(read, EnumValue) else None
        return _node_type(init._node)
    return None


def _node_type(node):
    if isinstance(node, (nodes.Compare, nodes.BoolOp)) or (
        isinstance(node, nodes.Unary) and node.op == 'not'
    ):
        return BOOL
    if isinstance(node, nodes.Call) and node.function == 'q':
        return p.Number(node.args[1].value)
    if (
        isinstance(node, nodes.Const)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return p.Number()
    return None


def _initial(value, value_type):
    """An initializer as a record: a bare number takes the declared unit."""
    if value is None or isinstance(value, (Formula, Distribution)):
        return value
    if (
        isinstance(value, X)
        and value._path is not None
        and isinstance(value._path.start, (Literal, Instances, Where, By))
    ):
        return value._path
    unit = value_type.unit if isinstance(value_type, p.Number) else ''
    if unit and isinstance(value, (int, float, Fraction)) and not isinstance(value, bool):
        return expr_of(q(value, unit))
    return expr_of(value)


def _setting(value):
    """A request or a capacity: captured once, or a live formula."""
    if value is None or isinstance(value, Formula):
        return value
    return expr_of(value)


# ---- values, flows and endpoints -------------------------------------------------------------------


def _value(name, kind, value_type, init, lower, upper, readonly, scale, outflow, inflow):
    if value_type is None:
        value_type = _inferred(init)
        if value_type is None:
            raise TypeError(f'{name}: give the type of its value')
    value_type = _type(value_type)
    if kind is None:
        kind = (
            p.COLLECTION
            if isinstance(value_type, p.CollectionType)
            else p.FORMULA
            if isinstance(init, Formula)
            else p.DISTRIBUTION
            if isinstance(init, Distribution)
            else p.STATE
        )
    return p.Value(
        name,
        kind,
        value_type,
        _initial(init, value_type),
        _initial(lower, value_type),
        _initial(upper, value_type),
        readonly,
        _initial(scale, value_type),
        outflow,
        inflow,
    )


def value(
    name,
    type=None,
    init=None,
    *,
    lower=None,
    upper=None,
    readonly=False,
    scale=None,
    outflow=None,
    inflow=None,
):
    """A value: stored (`STATE`), a formula, a distribution or a collection, by its initializer."""
    return _value(name, None, type, init, lower, upper, readonly, scale, outflow, inflow)


def input_(name, type=None, init=None, *, lower=None, upper=None, readonly=False, scale=None):
    """An `input`: fixed for the run, which a configuration can override."""
    return _value(name, p.INPUT, type, init, lower, upper, readonly, scale, None, None)


def link(name, template):
    """A link to a member of a template, which each member sets."""
    return p.Value(name, p.LINK, p.EntityType(template))


def endpoint(capacity=None, request=None, allocation=PROPORTIONAL):
    """The settings of `outflow` or `inflow`."""
    return p.Endpoint(_setting(capacity), _setting(request), allocation)


def priority(*items):
    """`priority(a, b, ...)` over incident flows, legs or a projection of a keyed collection."""
    return p.Priority(tuple(_path(each) for each in items))


def proportional():
    """`proportional()`, the default allocation."""
    return PROPORTIONAL


def _end(end):
    return end if isinstance(end, p.Outside) else _path(end)


def flow(name, source, sink, *, request=None, capacity=None, unit=''):
    """`flow name: source -> sink`."""
    return p.Flow(
        name, p.DIRECTED, _end(source), _end(sink), _unit(unit), _setting(request), _setting(capacity)
    )


def route(name, first, second, *, request=None, capacity=None, unit=''):
    """`flow name: first <-> second`: one signed rate, positive from `first` to `second`."""
    return p.Flow(
        name, p.REVERSIBLE, _end(first), _end(second), _unit(unit), _setting(request), _setting(capacity)
    )


def legs(name, *legs):
    """A flow with several legs, each a `flow`, served at one fraction."""
    return p.Flow(name, p.LEGS, legs=tuple(legs))


# ---- events -----------------------------------------------------------------------------------------


class _Param:
    def __init__(self, value):
        self.value = value


def param(name, type, *, lower=None, upper=None):
    """A parameter of an event: a value copy, or with `ref_to(T)` an entity (D13)."""
    value_type = _type(type)
    kind = p.LINK if isinstance(value_type, p.EntityType) else p.STATE
    return _Param(_value(name, kind, value_type, None, lower, upper, False, None, None, None))


def _body(statements):
    return tuple(statements)


def assign(target, value):
    """`target = value`."""
    return p.Assign(_path(target), '=', _assigned(value))


def add(target, value):
    """`target += value`."""
    return p.Assign(_path(target), '+=', _assigned(value))


def subtract(target, value):
    """`target -= value`."""
    return p.Assign(_path(target), '-=', _assigned(value))


def _assigned(value):
    if isinstance(value, (Formula, Distribution, p.Priority, p.Proportional)):
        return value
    return _initial(value, None)


def move(amount, source, destination):
    """`move amount from source to destination`."""
    return p.Move(expr_of(amount), _path(source), _path(destination))


def start(event, *args):
    """`event.start(args)`: on one event, or on each member of a collection."""
    return p.Start(_path(event), tuple(expr_of(arg) for arg in args))


def if_(test, then, orelse=()):
    """`if test: then else: orelse` in a stage."""
    return p.If(expr_of(test), _body(then), _body(orelse))


def case(member, *body, when=None):
    """A case of a switch: an enum member (`E.FIXED`, or its name), its guard and its body."""
    if isinstance(member, X):
        member = next(iter(member._reads.values())).member
    return p.Case(member, _body(body), None if when is None else expr_of(when))


def switch(selector, *cases, orelse=()):
    """`switch selector:` with its cases and an optional else."""
    return p.Switch(expr_of(selector), tuple(cases), _body(orelse))


def after(delay, *body, when=None):
    """`after delay [when guard]:` and its stage."""
    return p.After(expr_of(delay), _body(body), None if when is None else expr_of(when))


def until(test):
    """`until test`."""
    return p.Until(expr_of(test))


def reset_when(test):
    """`reset when test`."""
    return p.Reset('when', expr_of(test))


def reset_after(duration):
    """`reset after duration`."""
    return p.Reset('after', expr_of(duration))


def when(test, *body, captures=(), reset=None):
    """A trigger of an event: `when test:`, its captures (values), its body and its reset."""
    return p.Trigger(expr_of(test), _body(body), tuple(captures), reset)


def event(name, *parts):
    """An event: its parameters (`param`), its locals (values and flows, in written order), its
    steps (`after`, `until`) and its triggers (`when`)."""
    params, locals_, steps, triggers = [], [], [], []
    for part in parts:
        if isinstance(part, _Param):
            params.append(part.value)
        elif isinstance(part, (p.Value, p.Flow)):
            locals_.append(part)
        elif isinstance(part, (p.After, p.Until)):
            steps.append(part)
        elif isinstance(part, p.Trigger):
            triggers.append(part)
        else:
            raise TypeError(f'{name}: no part of an event: {part!r}')
    return p.Event(name, tuple(params), tuple(locals_), tuple(steps), tuple(triggers))


# ---- solvers, displays and assertions ------------------------------------------------------------


class _Determine:
    def __init__(self, path):
        self.path = path


def given(name, source):
    """An input of a solver: a name for a value, a flow or a collection."""
    return p.Binding(name, _path(source))


def solve_for(target):
    """A `solve_for` entry that names an existing field or a projection of one."""
    return _Determine(_path(target))


def unknown(name, type, *, lower=None, upper=None, init=None, scale=None):
    """A new unknown of a solver, with its domain, its preferred value and its scale."""
    return _value(name, p.STATE, type, init, lower, upper, False, scale, None, None)


def constraint(test):
    """A relation that a solver enforces."""
    return p.Constraint(expr_of(test))


def minimize(value):
    return p.Objective('minimize', expr_of(value))


def maximize(value):
    return p.Objective('maximize', expr_of(value))


def solver(name, *parts):
    """A solver: its inputs (`given`), `solve_for` entries, unknowns, constraints and objectives."""
    inputs, targets, unknowns, constraints, objective = [], [], [], [], []
    for part in parts:
        if isinstance(part, p.Binding):
            inputs.append(part)
        elif isinstance(part, _Determine):
            targets.append(part.path)
        elif isinstance(part, p.Value):
            unknowns.append(part)
        elif isinstance(part, p.Constraint):
            constraints.append(part)
        elif isinstance(part, p.Objective):
            objective.append(part)
        else:
            raise TypeError(f'{name}: no part of a solver: {part!r}')
    return p.Solver(
        name, tuple(inputs), tuple(targets), tuple(unknowns), tuple(constraints), tuple(objective)
    )


def rating(rating, when=None):
    """A case of a status display; the last has no condition."""
    return p.StatusCase(rating, None if when is None else expr_of(when))


def status(*cases):
    """A status display."""
    return p.Status(tuple(cases))


def assertion(test):
    """An assertion."""
    return p.Assert(expr_of(test))


class _Sees:
    def __init__(self, path):
        self.path = path


def sees(value):
    """What a human player of this actor is shown."""
    return _Sees(_path(value))


# ---- the builder -------------------------------------------------------------------------------------


class TemplateHandle:
    """A template of a builder: its name, and `instances` as a handle."""

    def __init__(self, name):
        self.name = name

    @property
    def instances(self):
        return _read(Path(Instances(self.name)))


class TableHandle:
    """A table of a builder: `sites.clinic` is the handle of the row with the id `clinic`."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, id):
        if id.startswith('_'):
            raise AttributeError(id)
        return named(f'{self._name}.{id}')


class Builder:
    """Makes one program. `units` are the declared units: a spelling with its dimension (base
    dimensions with their powers), or a pair of the dimension and the scale."""

    def __init__(self, units=None):
        self._base = {}
        for name, spec in (units or {}).items():
            dimension, scale = spec if isinstance(spec, tuple) else (spec, 1)
            self._base[name] = p.Unit(
                name, tuple(sorted((k, v) for k, v in dimension.items() if v)), Fraction(scale)
            )
        self._enums = {}
        self._templates = {}  # name -> [parts]
        self._members = {}  # name -> [(id, values)]
        self._root = []
        self._setup = []

    def enum(self, name, *members):
        """An enum with its members."""
        handle = EnumHandle(name, members)
        self._enums[name] = handle
        return handle

    def template(self, name, *parts):
        """A template with its parts: values, flows, events, solvers, a status display,
        assertions and `sees`."""
        if name in self._templates:
            raise ValueError(f'the template {name!r} is declared twice')
        self._templates[name] = list(parts)
        self._members[name] = []
        return TemplateHandle(name)

    def member(self, template, id, /, **values):
        """A member of a template, with its own values and links."""
        name = template.name if isinstance(template, TemplateHandle) else template
        self._members[name].append((id, values))
        return named(id)

    def entity(self, name, *parts, **values):
        """An entity written on its own: a template of one member with the same name."""
        self.template(name, *parts)
        return self.member(name, name, **values)

    def table(self, name, template, rows):
        """The rows of a table of a template. A row with an `id` is the member `name.id`, and the
        rows are kept in the order of their ids; rows without ids are `name[k]` in file order."""
        template = template.name if isinstance(template, TemplateHandle) else template
        rows = [dict(row) for row in rows]
        if all('id' in row for row in rows):
            for row in sorted(rows, key=lambda row: row['id']):
                self.member(template, f'{name}.{row.pop("id")}', **row)
        else:
            for index, row in enumerate(rows):
                self.member(template, f'{name}[{index}]', **row)
        return TableHandle(name)

    def root(self, *parts):
        """Values and assertions of the run's root."""
        self._root.extend(parts)

    def setup(self, *statements):
        """Statements of the setup scope, which commit as round zero."""
        self._setup.extend(statements)

    def program(self):
        """The program, unchecked: for a test of the checker."""
        templates = [self._template(name, parts) for name, parts in self._templates.items()]
        templates = self._members_of(templates)
        root_values = tuple(part for part in self._root if isinstance(part, p.Value))
        root_asserts = tuple(part for part in self._root if isinstance(part, p.Assert))
        draft = p.Program(
            templates=tuple(templates), root=root_values, setup=tuple(self._setup), asserts=root_asserts
        )
        draft = replace(draft, templates=tuple(_flow_units(draft, template) for template in draft.templates))
        placed = replace(
            draft,
            templates=tuple(_placed(template, template.name) for template in draft.templates),
            root=tuple(_placed(each, each.name) for each in draft.root),
            setup=tuple(_placed(each, f'setup[{index}]') for index, each in enumerate(draft.setup)),
            asserts=tuple(_placed(each, f'assert[{index}]') for index, each in enumerate(draft.asserts)),
        )
        enums = tuple(p.Enum(handle.name, handle.members) for handle in self._enums.values())
        return replace(placed, units=self._units(placed), enums=enums)

    def finish(self):
        """The program, checked: `ProgramError` with each refusal of `check.check`."""
        program = self.program()
        found = checking.check(program)
        if found:
            raise checking.ProgramError(found)
        return program

    def _template(self, name, parts):
        groups = {'values': [], 'flows': [], 'events': [], 'solvers': [], 'asserts': [], 'sees': []}
        status = None
        for part in parts:
            if isinstance(part, p.Value):
                groups['values'].append(part)
            elif isinstance(part, p.Flow):
                groups['flows'].append(part)
            elif isinstance(part, p.Event):
                groups['events'].append(part)
            elif isinstance(part, p.Solver):
                groups['solvers'].append(part)
            elif isinstance(part, p.Assert):
                groups['asserts'].append(part)
            elif isinstance(part, _Sees):
                groups['sees'].append(part.path)
            elif isinstance(part, p.Status):
                status = part
            else:
                raise TypeError(f'{name}: no part of a template: {part!r}')
        return p.Template(name, status=status, **{key: tuple(items) for key, items in groups.items()})

    def _members_of(self, templates):
        """The templates with their members: each value as a record, each link as a row."""
        rows = {}
        for name, members in self._members.items():
            for row, (id, _) in enumerate(members):
                rows[id] = (name, row)
        done = []
        for template in templates:
            members = []
            for id, given_values in self._members[template.name]:
                values, links = [], []
                for name, init in given_values.items():
                    part = template.part(name)
                    if isinstance(part, p.Value) and part.kind == p.LINK:
                        found = rows.get(_member_id(init))
                        if found is not None and found[0] == part.type.template:
                            links.append((name, found[1]))
                        continue
                    value_type = part.type if isinstance(part, p.Value) else None
                    values.append((name, _initial(init, value_type)))
                members.append(p.Member(id, tuple(values), tuple(links)))
            done.append(replace(template, members=tuple(members)))
        return done

    def _units(self, program):
        """The table of every unit that the program spells, composed of the declared units."""
        spellings = set()
        _spellings(program, spellings)
        table = {}
        for spelling in spellings - {''}:
            unit = _compose(spelling, self._base)
            if unit is not None:
                table[spelling] = unit
        return tuple(table[name] for name in sorted(table))


def _member_id(handle):
    """The id of a member that a handle or a text names, or None."""
    if isinstance(handle, str):
        return handle
    if isinstance(handle, X) and handle._path is not None and isinstance(handle._path.start, Named):
        return None if handle._path.steps else handle._path.start.id
    return None


def _compose(spelling, base):
    """The unit of a spelling with `*` and `/` from the left over declared units (D12), or None."""
    pieces = re.split(r'([*/])', spelling)
    dimension, scale, sign = {}, Fraction(1), 1
    for piece in pieces:
        if piece in ('*', '/'):
            sign = 1 if piece == '*' else -1
            continue
        if piece == '1':
            continue
        unit = base.get(piece)
        if unit is None:
            return None
        for key, power in unit.dimension:
            dimension[key] = dimension.get(key, 0) + sign * power
        scale = scale * unit.scale if sign > 0 else scale / unit.scale
    return p.Unit(spelling, tuple(sorted((k, v) for k, v in dimension.items() if v)), scale)


def _spellings(value, found):
    """Each unit spelling of a program: of number types, flows, distributions and literals."""
    if (
        isinstance(value, p.Number)
        or (isinstance(value, p.Flow) and value.kind != p.LEGS)
        or (isinstance(value, Distribution) and value.family != 'categorical')
    ):
        found.add(value.unit)
    elif isinstance(value, Expr):
        for node in nodes.walk(value.node):
            if (
                isinstance(node, nodes.Call)
                and node.function == 'q'
                and isinstance(node.args[-1], nodes.Const)
            ):
                found.add(node.args[-1].value)
    if isinstance(value, tuple):
        for each in value:
            _spellings(each, found)
    elif is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _spellings(getattr(value, item.name), found)


def _flow_units(program, template):
    """A template whose flows without a unit take the unit of a literal rate, or of an end per hour:
    `L/h`, and `1/h` for an end that is a plain number, the spelling that the front end writes and
    that composes from the unit of time (D12)."""
    resolver = checking.Resolver(program)

    def unit_of(flow, scope):
        if flow.kind == p.LEGS:
            return replace(flow, legs=tuple(unit_of(leg, scope) for leg in flow.legs))
        if flow.unit:
            return flow
        for setting in (flow.request, flow.capacity):
            found = _inferred(setting) if isinstance(setting, Formula) else None
            node = setting.node if isinstance(setting, Expr) else None
            found = found or (_node_type(node) if node is not None else None)
            if isinstance(found, p.Number) and found.unit:
                return replace(flow, unit=found.unit)
        for end in (flow.source, flow.sink):
            if isinstance(end, Path):
                store = resolver.resolve(end, scope, '')
                if store is not None and store.kind == 'value' and isinstance(store.part.type, p.Number):
                    return replace(flow, unit=f'{store.part.type.unit or "1"}/h')
        return flow

    scope = checking.Scope(template)
    flows = tuple(unit_of(each, scope) for each in template.flows)
    events = []
    for each in template.events:
        inner = checking.Scope(template, each)
        locals_ = tuple(unit_of(part, inner) if isinstance(part, p.Flow) else part for part in each.locals)
        events.append(replace(each, locals=locals_))
    return replace(template, flows=flows, events=tuple(events))


# ---- origins, sites and the names of reads -------------------------------------------------------

# The label of an unnamed part by the field that holds it: `step[0]`, `do[1]`, `when[0]`, ...
_LABELS = {
    'steps': 'step',
    'body': 'do',
    'then': 'then',
    'orelse': 'else',
    'triggers': 'when',
    'constraints': 'constraint',
    'objective': 'objective',
    'asserts': 'assert',
    'cases': 'case',
}


def _has_origin(record):
    return is_dataclass(record) and any(item.name == 'origin' for item in fields(record))


def _placed_items(items, field, origin):
    """The parts of a tuple, each with its origin: by its name, its member, or its place."""
    label = _LABELS.get(field, field)
    placed = []
    for index, each in enumerate(items):
        if isinstance(each, p.Case):
            placed.append(_placed(each, f'{origin}.{each.member}'))
        elif getattr(each, 'name', None):
            placed.append(_placed(each, f'{origin}.{each.name}'))
        else:
            placed.append(_placed(each, f'{origin}.{label}[{index}]'))
    return tuple(placed)


def _placed(record, origin):
    """A record with its origin and its parts', its expressions with their names spelled, and the
    sites of its draws and choices numbered in the order in which they are written."""
    counter = {'draw': 0, 'choice': 0}
    changes = {'origin': origin} if _has_origin(record) else {}
    for item in fields(record):
        if item.name == 'origin':
            continue
        value = getattr(record, item.name)
        if isinstance(value, tuple) and any(_has_origin(each) for each in value):
            changes[item.name] = _placed_items(value, item.name, origin)
        elif _has_origin(value):
            changes[item.name] = _placed(value, f'{origin}.{item.name}')
        else:
            changes[item.name] = _inner(value, origin, counter)
    return replace(record, **changes)


def _inner(value, origin, counter):
    """A value inside a part: its expressions and paths with their reads placed."""
    if isinstance(value, Expr):
        return _spelled_expr(value, origin, counter)
    if isinstance(value, Formula):
        return Formula(_spelled_expr(value.expr, origin, counter))
    if isinstance(value, Path):
        return _placed_path(value, origin, counter)
    if isinstance(value, p.Priority):
        return p.Priority(tuple(_placed_path(each, origin, counter) for each in value.items))
    if isinstance(value, p.Reset):
        return p.Reset(value.kind, _spelled_expr(value.expr, origin, counter))
    if isinstance(value, p.Member):
        values = tuple(
            (name, _inner(init, f'{value.id}.{name}', {'draw': 0, 'choice': 0}))
            for name, init in value.values
        )
        return replace(value, values=values)
    if isinstance(value, tuple):
        return tuple(_inner(each, origin, counter) for each in value)
    return value


def _placed_path(path, origin, counter):
    start = path.start
    if isinstance(start, Where):
        start = Where(_placed_path(start.source, origin, counter), _spelled_expr(start.test, origin, counter))
    elif isinstance(start, By):
        start = By(_placed_path(start.source, origin, counter), start.key)
    elif isinstance(start, Lookup):
        start = Lookup(_placed_path(start.source, origin, counter), _spelled_expr(start.key, origin, counter))
    elif isinstance(start, Literal):
        start = Literal(tuple(_placed_path(each, origin, counter) for each in start.items))
    return Path(start, path.steps)


def _placed_read(read, origin, counter):
    if isinstance(read, (Draw, Choice)):
        kind = 'draw' if isinstance(read, Draw) else 'choice'
        site = f'{origin}.{kind}[{counter[kind]}]'
        counter[kind] += 1
        source = (
            read.source
            if isinstance(read.source, Distribution)
            else _placed_path(read.source, origin, counter)
        )
        if isinstance(read, Draw):
            return Draw(source, site)
        return Choice(_placed_path(read.actor, origin, counter), source, site)
    if isinstance(read, Path):
        return _placed_path(read, origin, counter)
    if isinstance(read, Reduce):
        return Reduce(read.op, _placed_path(read.source, origin, counter))
    if isinstance(read, Since):
        return Since(_placed_path(read.event, origin, counter))
    if isinstance(read, Elapsed):
        return Elapsed(_placed_path(read.value, origin, counter))
    if isinstance(read, Delayed):
        return Delayed(_placed_path(read.value, origin, counter), _spelled_expr(read.delay, origin, counter))
    return read


def _spelled_expr(expression, origin, counter):
    """An expression whose names are the spellings of their reads, in the order of the node."""
    order = []
    for node in nodes.walk(expression.node):
        if isinstance(node, nodes.Ref) and node.name not in order:
            order.append(node.name)
    reads = dict(expression.reads)
    names, used = {}, {}
    for name in order:
        read = _placed_read(reads[name], origin, counter)
        final = spelled(read)
        if final in used and used[final] != read:
            final = _free(final, used.keys())
        used[final] = read
        names[name] = final
    return Expr(_renamed(expression.node, names), tuple(sorted(used.items())))
