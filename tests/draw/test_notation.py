"""The notation of the Equations panel (napkin/draw/notation.py): each node is the model's expression,
node for node, and its LaTeX says the same.

- Build: each construct of the typed form of the declared model gives the node that the module's text
  names, worked out by hand; the reads of a member give the keys of the picture (`notation.Keys`).
- Value: an evaluator of the typed form and an evaluator of the notation's nodes, both written here
  (neither is the engine's), give the same value at seeded random points: a random value for each
  name, a random positive scale for each unit, a random time since each event and count of it. This
  holds for every expression of a model that writes every construct of the language, and of random
  expressions.
- LaTeX: `latex_subset.py` reads the LaTeX back into a node, which has the shape of the node and the
  value of the expression at the same points. Counterexamples show the parentheses that a naive
  writer leaves out.
- A membership test (`x in [lo, hi]`, the program's `within`) is `In` wherever the model writes it,
  its LaTeX is the model's form, and its value is the spec's: true or false, and a failure by name
  where its interval is reversed (`MEMBERSHIP`, with values worked by hand). `napkin draw` writes it so.
"""

from __future__ import annotations

import ast
import cmath
import json
import math
import operator
import random
import re
import string
import xml.etree.ElementTree as ET
from dataclasses import fields, is_dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.draw import notation
from napkin.draw.notation import (
    Assign,
    Call,
    Cases,
    Cmp,
    Count,
    Deriv,
    Elapsed,
    In,
    Keys,
    Logic,
    Neg,
    Not,
    Num,
    Op,
    Pos,
    Since,
    Sum,
    Sym,
    Text,
    Time,
)
from napkin.draw.things import Things
from napkin.model import semantic as s
from tests.commands.call import UNITS as COMMAND_UNITS
from tests.commands.call import napkin, package
from tests.draw.latex_subset import LatexError, read, read_line
from tests.draw.models import compiled

# ---- the typed form of a Python text --------------------------------------------------------------

NUMBER = s.Num()
HOURS = s.Num('h', (('time', 1),))
BINARY = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.Div: 'div', ast.Pow: 'pow'}
COMPARE = {ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=', ast.Eq: '==', ast.NotEq: '!='}
CALLS = ('min', 'max', 'clip', 'abs', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf')
REDUCTIONS = ('sum', 'count', 'any', 'all')
# The names of a text that are yes/no values, and those that are events.
BOOLS = frozenset('pqr')
EVENTS = frozenset({'go', 'stop'})


def read_of(name):
    """The read of the value `name` of the member `s`."""
    kind = s.BOOL if name in BOOLS else s.EventOf(f's.{name}') if name in EVENTS else NUMBER
    return s.Read(('this',), (name,), kind)


def node_of(text):
    """The typed form of a Python text, as the declared model gives it: each name a value of the
    member `s` (`read_of`; `p`, `q` and `r` are yes/no, `go` and `stop` events), `t` the time,
    `q(x, 'unit')` a number with a unit, `since(e)` and `elapsed(x)` history, `sum`, `count`, `any`,
    `all`, and `min` and `max` of one list `[a, b]` reductions of a literal collection, the other
    functions calls, and `x in [lo, hi]` the program's membership `within`."""

    def of(node):
        if isinstance(node, ast.Name):
            if node.id == 't':
                return s.Read(('time',), (), HOURS)
            if node.id in ('true', 'false'):
                return s.Const(node.id == 'true', s.BOOL)
            return read_of(node.id)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return s.Const(node.value, s.BOOL)
            if isinstance(node.value, str):
                return s.Const(node.value, s.TEXT)
            return s.Const(node.value, NUMBER)
        if isinstance(node, ast.BinOp):
            return s.Apply(BINARY[type(node.op)], (of(node.left), of(node.right)), NUMBER)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.UAdd):
                return of(node.operand)
            return s.Apply('not' if isinstance(node.op, ast.Not) else 'neg', (of(node.operand),), NUMBER)
        if isinstance(node, ast.BoolOp):
            return s.Apply(
                'and' if isinstance(node.op, ast.And) else 'or', tuple(map(of, node.values)), s.BOOL
            )
        if isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.In):
            (interval,) = node.comparators
            low, high = interval.elts
            return s.Apply('call', (of(node.left), of(low), of(high)), s.BOOL, 'within')
        if isinstance(node, ast.Compare):
            items = (of(node.left), *map(of, node.comparators))
            return s.Apply('compare', items, s.BOOL, tuple(COMPARE[type(op)] for op in node.ops))
        if isinstance(node, ast.IfExp):
            return s.Apply('if', (of(node.test), of(node.body), of(node.orelse)), NUMBER)
        if isinstance(node, ast.Call):
            name, args = node.func.id, node.args
            if name == 'q':
                unit = args[1].value
                return s.Const(args[0].value, s.Num(unit, ((unit, 1),)))
            if name in ('since', 'elapsed'):
                return s.History(name, of(args[0]), HOURS)
            if name in REDUCTIONS or (name in ('min', 'max') and isinstance(args[0], ast.List)):
                items = tuple(s.Read(('named', f'm{k}'), (), s.Ent('M')) for k in range(len(args[0].elts)))
                field = args[0].elts[0].id if args[0].elts else 'x'
                source = s.Read(('literal', items), (field,), s.Many(NUMBER))
                return s.Reduced(name, source, NUMBER)
            return s.Apply('call', tuple(map(of, args)), NUMBER, name)
        raise AssertionError(ast.dump(node))

    return of(ast.parse(text, mode='eval').body)


class TestKeys:
    """The keys of a test's reads: `s.<name>` for a value of `s`, `m<k>.<field>` for a member of a
    literal collection."""

    def __call__(self, read):
        if read.start == ('time',):
            return Time()
        return Sym(f's.{read.steps[-1]}')

    def reduced(self, node):
        if node.op == 'count' and isinstance(node.source.type.of, s.Occ):
            return Count(f's.{node.source.steps[0]}')
        field = node.source.steps[-1]
        return Sum(node.op, tuple(Sym(f'{item.start[1]}.{field}') for item in node.source.start[1]))


KEYS = TestKeys()


def built(text):
    """The node of a Python text (`node_of`)."""
    return notation.build(node_of(text), KEYS)


def shape(value):
    """The meaning of a node, to compare: its class and fields, without how the file writes its names
    (`written`), and with the type of each number."""
    if is_dataclass(value):
        kept = [f for f in fields(value) if f.name != 'written']
        return (type(value).__name__, *(shape(getattr(value, f.name)) for f in kept))
    if isinstance(value, tuple):
        return tuple(shape(item) for item in value)
    if isinstance(value, float):
        return ('float', value)
    return value


def canonical(node):
    """A node with the lists of `min` and `max` written as their members, as LaTeX writes them, and an
    assignment `x += v` as `x = x + v`."""
    if isinstance(node, Sum) and node.fn in ('min', 'max'):
        return Call(node.fn, node.terms)
    if isinstance(node, Call) and node.name in ('min', 'max'):
        args = []
        for arg in node.args:
            args += arg.terms if isinstance(arg, Sum) and arg.fn == node.name else [canonical(arg)]
        return Call(node.name, tuple(args), tuple((k, canonical(v)) for k, v in node.keywords))
    if isinstance(node, Assign) and node.op != '=':
        return Assign(node.target, '=', Op(node.op[0], Sym(node.target), canonical(node.value)))
    if not is_dataclass(node):
        return node
    return type(node)(**{f.name: _canonical(getattr(node, f.name)) for f in fields(node)})


def _canonical(value):
    if isinstance(value, notation.Node):
        return canonical(value)
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    return value


# ---- the two evaluators ---------------------------------------------------------------------------

# The failure of a membership test whose interval is reversed (spec: "reversed bounds are an error"),
# by the name that the program gives it.
REVERSED = 'the interval of a membership test is reversed'


def within(x, low, high):
    """`x in [low, high]`: whether x is in the closed interval; a reversed interval is an error."""
    if low > high:
        raise ValueError(REVERSED)
    return low <= x <= high


FUNCTIONS = {
    'min': min,
    'max': max,
    'clip': lambda x, low, high: min(max(x, low), high),
    'abs': abs,
    'exp': math.exp,
    'expm1': math.expm1,
    'ln': math.log,
    'log1p': math.log1p,
    'sqrt': math.sqrt,
    'erf': math.erf,
    'within': within,
}
ARITHMETIC_OPS = {'add': operator.add, 'sub': operator.sub, 'mul': operator.mul, 'div': operator.truediv}
ARITHMETIC_OPS['pow'] = operator.pow
ORDER = {'<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge, '==': operator.eq}
ORDER['!='] = operator.ne


def stand_in(name, args, keywords):
    """The value that the tests give a distribution, a draw and the reads of a flow or a
    store that are calls (`notation.STEPS`): it reads each argument by its place, so an argument in the
    wrong place or under the wrong name changes it."""
    given = [*args, *(value for _, value in keywords)]
    names = ''.join(key for key, _ in keywords)
    return len(name) + len(names) + sum((i + 1) * value for i, value in enumerate(given))


class Point:
    """A seeded random point: a value for each key (yes/no for `BOOLS`), a positive scale for each
    unit, the time, and for each event the time since it and its count. Each value depends on the seed
    and the name only, so the order of the reads does not matter."""

    def __init__(self, seed, kinds=None):
        self.seed, self.kinds = seed, kinds or {}
        self.time = self.rng('t').uniform(0, 10)

    def rng(self, *name):
        return random.Random(':'.join(map(str, (self.seed, *name))))

    def value(self, key):
        rng = self.rng('value', key)
        kind = self.kinds.get(key, 'bool' if key.rpartition('.')[2] in BOOLS else 'number')
        if kind == 'bool':
            return rng.random() < 0.5
        if isinstance(kind, tuple):
            return rng.choice(kind)
        if kind == 'text':
            return rng.choice(('a', 'b'))
        return rng.uniform(0.25, 4.0)

    def scale(self, unit):
        return self.rng('unit', unit).uniform(0.5, 2.0)

    def since(self, key):
        return self.rng('since', key).uniform(0, 5)

    def count(self, key):
        return self.rng('count', key).randint(0, 3)

    def elapsed(self, key):
        return self.rng('elapsed', key).uniform(0, 5)


def value_of_typed(expression, point, keys):
    """The value of an expression of the typed form, by Python's rules; `keys(read)` gives the key of
    each read, and `keys.reduced` the members of a reduction."""

    def of(node):
        if isinstance(node, s.Const):
            value = node.value
            unit = getattr(node.type, 'unit', '')
            return value * point.scale(unit) if unit and not isinstance(value, (bool, str)) else value
        if isinstance(node, s.Read):
            found = keys(node)
            return point.time if isinstance(found, Time) else value_of_node(found, point)
        if isinstance(node, s.Retain):
            return of(node.body)
        if isinstance(node, s.Reduced):
            members = keys.reduced(node)
            if isinstance(members, Count):
                return point.count(members.event)
            values = [point.value(term.key) for term in members.terms]
            if node.op == 'count':
                return sum(1 for value in values if value)
            return {'sum': sum, 'any': any, 'all': all, 'min': min, 'max': max}[node.op](values)
        if isinstance(node, s.History):
            key = keys(node.source).key
            return point.since(key) if node.op == 'since' else point.elapsed(key)
        if isinstance(node, s.Distribution):
            if node.family == 'categorical':
                return stand_in('categorical', [], list(zip(node.outcomes, node.params)))
            unit = getattr(node.type.of, 'unit', '')
            scale = point.scale(unit) if unit else 1
            return stand_in(node.family, [value * scale for value in node.params], [])
        if isinstance(node, s.Drawn):
            return stand_in('draw', [of(node.source)], [])
        assert isinstance(node, s.Apply), node
        op, args = node.op, node.args
        if op in ARITHMETIC_OPS:
            return ARITHMETIC_OPS[op](of(args[0]), of(args[1]))
        if op == 'neg':
            return -of(args[0])
        if op == 'not':
            return not of(args[0])
        if op in ('and', 'or'):
            result = None
            for arg in args:
                result = of(arg)
                if (op == 'and') != bool(result):
                    return result
            return result
        if op == 'compare':
            values = [of(args[0])]
            for written, arg in zip(node.detail, args[1:]):
                values.append(of(arg))
                if not ORDER[written](values[-2], values[-1]):
                    return False
            return True
        if op == 'if':
            return of(args[1]) if of(args[0]) else of(args[2])
        return FUNCTIONS[node.detail](*map(of, args))

    return of(expression)


def value_of_node(node, point):
    """The value of a node of the notation."""

    def of(node):
        if isinstance(node, Sym):
            return point.value(node.key)
        if isinstance(node, Num):
            return node.value if node.unit is None else node.value * point.scale(node.unit)
        if isinstance(node, Text):
            return node.word
        if isinstance(node, Time):
            return point.time
        if isinstance(node, Op):
            ops = {'+': operator.add, '-': operator.sub, '*': operator.mul, '/': operator.truediv}
            return (ops.get(node.op) or operator.pow)(of(node.left), of(node.right))
        if isinstance(node, Neg):
            return -of(node.x)
        if isinstance(node, Pos):
            return +of(node.x)
        if isinstance(node, Not):
            return not of(node.x)
        if isinstance(node, Logic):
            result = None
            for item in node.items:
                result = of(item)
                if (node.op == 'and') != bool(result):
                    return result
            return result
        if isinstance(node, Cmp):
            values = [of(node.items[0])]
            for op, item in zip(node.ops, node.items[1:]):
                values.append(of(item))
                if not ORDER[op](values[-2], values[-1]):
                    return False
            return True
        if isinstance(node, In):
            return within(of(node.x), of(node.low), of(node.high))
        if isinstance(node, Cases):
            for condition, value in node.pairs:
                if of(condition):
                    return of(value)
            return of(node.otherwise)
        if isinstance(node, Sum):
            members = [of(term) for term in node.terms]
            fn = {'sum': sum, 'any': any, 'all': all, 'min': min, 'max': max}
            return fn[node.fn](members) if node.fn != 'count' else sum(1 for x in members if x)
        if isinstance(node, Call):
            args = []
            for arg in node.args:
                list_of = isinstance(arg, Sum) and arg.fn == node.name
                args += [of(term) for term in arg.terms] if list_of else [of(arg)]
            if node.name in FUNCTIONS:
                return FUNCTIONS[node.name](*args)
            return stand_in(node.name, args, [(k, of(v)) for k, v in node.keywords])
        if isinstance(node, Since):
            return point.since(node.event)
        if isinstance(node, Count):
            return point.count(node.event)
        if isinstance(node, Elapsed):
            return point.elapsed(node.key)
        if isinstance(node, Assign):
            value = of(node.value)
            if node.op == '=':
                return value
            return point.value(node.target) + (value if node.op == '+=' else -value)
        raise AssertionError(node)

    return of(node)


def outcome(evaluate, *args):
    """('value', v) or ('error', the class of the error)."""
    try:
        return 'value', evaluate(*args)
    except (ArithmeticError, ValueError, TypeError) as exc:
        return 'error', type(exc).__name__


def same(a, b):
    if a[0] != b[0] or a[0] == 'error':
        return a == b
    x, y = a[1], b[1]
    if isinstance(x, complex) or isinstance(y, complex):
        return cmath.isclose(x, y, rel_tol=1e-12)
    if isinstance(x, float) or isinstance(y, float):
        return (math.isnan(x) and math.isnan(y)) or math.isclose(x, y, rel_tol=1e-12, abs_tol=0)
    return type(x) is type(y) and x == y


# ---- symbols for the LaTeX ------------------------------------------------------------------------


def symbols(node):
    """(symbol, the values by symbol, the events by symbol) of a node: `x_{i}` for each value it
    names and `e_{i}` for each event."""
    values, events = {}, {}
    for part in notation.nodes(node):
        if isinstance(part, (Sym, Elapsed, Deriv)):
            values.setdefault(part.key, f'x_{{{len(values) + 1}}}')
        elif isinstance(part, Assign):
            values.setdefault(part.target, f'x_{{{len(values) + 1}}}')
        elif isinstance(part, (Since, Count)):
            events.setdefault(part.event, f'e_{{{len(events) + 1}}}')
    return (
        {**values, **events}.__getitem__,
        {written: name for name, written in values.items()},
        {written: name for name, written in events.items()},
    )


def latex_back(node):
    """The node that the subset reader reads from the LaTeX of `node`, with the symbols of `node`."""
    symbol, values, events = symbols(node)
    text = notation.latex(node, symbol)
    found = read_line(text, values, events) if isinstance(node, Assign) else read(text, values, events)
    return text, found


# ---- each construct -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'node'),
    [
        ('a - (b - c)', Op('-', Sym('s.a'), Op('-', Sym('s.b'), Sym('s.c')))),
        ('-a ** 2', Neg(Op('**', Sym('s.a'), Num(2)))),
        ('+a', Sym('s.a')),
        ('q(2, "h") * a', Op('*', Num(2, 'h'), Sym('s.a'))),
        ('-2.5', Neg(Num(2.5))),
        ('a < b <= c', Cmp(('<', '<='), (Sym('s.a'), Sym('s.b'), Sym('s.c')))),
        ('p and q and r', Logic('and', (Sym('s.p'), Sym('s.q'), Sym('s.r')))),
        ('not p or q', Logic('or', (Not(Sym('s.p')), Sym('s.q')))),
        (
            'a if p else (b if q else c)',
            Cases(((Sym('s.p'), Sym('s.a')), (Sym('s.q'), Sym('s.b'))), Sym('s.c')),
        ),
        (
            '(a if p else b) if q else c',
            Cases(((Sym('s.q'), Cases(((Sym('s.p'), Sym('s.a')),), Sym('s.b'))),), Sym('s.c')),
        ),
        ('clip(a, 0, 1)', Call('clip', (Sym('s.a'), Num(0), Num(1)))),
        ('max(a, b)', Call('max', (Sym('s.a'), Sym('s.b')))),
        ('sum([w, w])', Sum('sum', (Sym('m0.w'), Sym('m1.w')))),
        ('any([p])', Sum('any', (Sym('m0.p'),))),
        ('since(go) >= q(3, "h")', Cmp(('>=',), (Since('s.go'), Num(3, 'h')))),
        ('elapsed(a)', Elapsed('s.a')),
        ('t >= 2', Cmp(('>=',), (Time(), Num(2)))),
        ('a in [b, q(3, "h")]', In(Sym('s.a'), Sym('s.b'), Num(3, 'h'))),
        ('true', Text(True)),
        ('"a text"', Text('a text')),
    ],
)
def test_each_construct_of_the_typed_form_is_its_node(text, node):
    found = built(text)
    assert shape(found) == shape(node), found


def test_a_distribution_and_a_draw_are_calls():
    uniform = s.Distribution('uniform', (1, 3), s.Dist(HOURS))
    assert notation.build(uniform, KEYS) == Call('uniform', (Num(1, 'h'), Num(3, 'h')))
    assert notation.build(s.Drawn(uniform, HOURS), KEYS) == Call(
        'draw', (Call('uniform', (Num(1, 'h'), Num(3, 'h'))),)
    )
    kinds = s.EnumOf(('FIXED', 'FAILED'))
    categorical = s.Distribution('categorical', (0.7, 0.3), s.Dist(kinds), ('FIXED', 'FAILED'))
    assert notation.build(categorical, KEYS) == Call(
        'categorical', (), (('FIXED', Num(0.7)), ('FAILED', Num(0.3)))
    )
    assert notation.build(s.Const('OPEN', s.EnumOf(('OPEN', 'SHUT'))), KEYS) == Text('OPEN')


def test_a_constant_is_its_number_or_its_word():
    assert notation.constant(3) == Num(3)
    assert shape(notation.constant(-2.5)) == shape(Neg(Num(2.5)))
    assert notation.constant(2, s.Num('L')) == Num(2, 'L')
    assert notation.constant(True) == Text(True)
    assert notation.constant('OPEN') == Text('OPEN')
    with pytest.raises(ValueError):
        notation.constant(None)
    with pytest.raises(ValueError):
        notation.constant(float('inf'))


def test_a_part_outside_the_notation_is_an_error_that_names_it():
    with pytest.raises(ValueError, match='object'):
        notation.build(object(), KEYS)
    with pytest.raises(ValueError, match='modulo'):
        notation.build(s.Apply('modulo', (s.Const(1, NUMBER), s.Const(2, NUMBER)), NUMBER), KEYS)


def test_an_assignment_is_its_target_its_operator_and_its_value():
    target = read_of('a')
    for op in ('=', '+=', '-='):
        line = s.DeclaredAssign('s.e.step[0].do[0]', target, op, node_of('b * 2'))
        assert notation.assignment(line, KEYS) == Assign('s.a', op, Op('*', Sym('s.b'), Num(2)))
    # The setting of a flow is no value of the notation.
    setting = s.DeclaredAssign('x', s.Read(('this',), ('pipe', 'request'), NUMBER), '=', node_of('b'))

    class FlowKeys(TestKeys):
        def __call__(self, read):
            return (
                Call('request', (Sym('s.pipe'),)) if read.steps[-1] == 'request' else super().__call__(read)
            )

    with pytest.raises(ValueError):
        notation.assignment(setting, FlowKeys())


# ---- the keys of a model -------------------------------------------------------------------------

# A model whose reads take every way of `notation.Keys`: a link, a route's leg, an endpoint, a flow's
# request, a parameter, the occurrences of an event, the time since it, a solver's result, a keyed
# collection and a reduction over a template's members.
KEYED = """\
Place:
    input need: L = 1 L in [0 L,]
    big = formula(this.need >= 2 L)

a: Place
    need = 1 L

b: Place
    need = 3 L

Pump:
    home: Place
    home_need = formula(this.home.need)

pump: Pump
    home = b

west:
    water: L = 10 L in [0 L, 20 L]
        outflow.capacity = 4 L/h

east:
    water: L = 10 L in [0 L, 20 L]

channel:
    flow link: west.water <-> east.water
        request = -3 L/h
    backward = formula(this.link.backward.actual_rate)
    wanted = formula(this.link.request)
    limit = formula(west.water.outflow.capacity)

grinder:
    beans: g = 8
    refill = event(amount: g):
        after 0.5 h:
            this.beans += amount
    last = formula(since(this.refill))
    refills = formula(count(this.refill.occurrences))

clinic:
    hours: h = 100 h
    staffing = solver:
        inputs:
            available = this.hours
        solve_for:
            care: h in [0 h, available]
        constraints:
            care <= available
        objective:
            maximize(care)
    care = formula(this.staffing.care)

total = sum(Place.instances.need)
largest = Place.instances.by(need).at(3 L).big

grinder.refill.start(50 g)
"""


@pytest.fixture(scope='module')
def keyed():
    return Things(compiled(KEYED))


@pytest.mark.parametrize(
    ('path', 'member', 'node'),
    [
        ('Pump.home_need', 'pump', Sym('b.need')),
        ('channel.backward', 'channel', Sym('channel.link.backward')),
        ('channel.wanted', 'channel', Call('request', (Sym('channel.link'),))),
        ('channel.limit', 'channel', Call('capacity', (Call('outflow', (Sym('west.water'),)),))),
        ('grinder.last', 'grinder', Since('grinder.refill')),
        ('grinder.refills', 'grinder', Count('grinder.refill')),
        ('clinic.care', 'clinic', Sym('clinic.staffing.care')),
        ('Place.big', 'a', Cmp(('>=',), (Sym('a.need'), Num(2, 'L')))),
        ('total', None, Sum('sum', (Sym('a.need'), Sym('b.need')))),
    ],
)
def test_the_reads_of_a_member_are_the_keys_of_the_picture(keyed, path, member, node):
    value = keyed.declared.part(path)
    assert notation.build(value.init, Keys(keyed, member)) == node


def test_a_parameter_is_a_key_of_its_event_and_a_keyed_read_is_its_words(keyed):
    (stage,) = keyed.declared.part('grinder.refill').steps
    (line,) = stage.body
    assert notation.assignment(line, Keys(keyed, 'grinder')) == Assign(
        'grinder.beans', '+=', Sym('grinder.refill.amount')
    )
    # Which member `.at(3 L)` reads only a run knows: the words of the read.
    found = notation.build(keyed.declared.part('largest').init, Keys(keyed, None))
    assert isinstance(found, Text) and 'big' in found.word and 'need' in found.word


# ---- every construct of the language --------------------------------------------------------------

EVERY_CONSTRUCT = (
    KEYED
    + """\
lab:
    input rate: L/h = 2 L/h in [0 L/h, 10 L/h]
    input repair: h = uniform(1 h, 3 h).draw() in [0 h,]
    input spread = uniform(1 h, 5 h)
    on: bool = true
    mode: enum[CALM, BUSY] = CALM
    level: L = 0 L in [0 L, 100 L]
    flow fill: SOURCE -> this.level
        request = this.rate
    low = formula(this.level < 5 L and this.on or not this.on)
    chain = formula(1 L < this.level <= 50 L)
    inside = formula(this.level in [1 L, 2 * this.level])
    pick = formula(this.rate if this.on else (2 * this.rate if this.level > 1 L else this.rate / 2))
    shaped = formula(clip(this.level, 1 L, 6 L) + max(this.level - 5 L, 0 L) + abs(-this.level))
    grown = formula(exp(ln(2)) * sqrt(16) - (this.level / (1 L)) ** 2)
    calm = formula(elapsed(this.mode))
    every = formula(all(Place.instances.big) or any(Place.instances.big))
    many = formula(count(Place.instances.big) + min(Place.instances.need) / max(Place.instances.need))
    clock = formula(t >= 2 h)
    mean = this.spread.mean
    check = event():
        after 1 h:
            switch categorical(FIXED: 0.7, FAILED: 0.3).draw():
                FIXED:
                    this.mode = BUSY
                FAILED:
                    this.level -= 1 L
"""
)


@pytest.fixture(scope='module')
def every():
    return Things(compiled(EVERY_CONSTRUCT))


def kinds_of(found):
    """{key: 'bool', 'text', the members of an enum or 'number'} of each value of each member."""
    out = {}
    for member, template in found.template_of.items():
        for part in found.entities[template].parts:
            if isinstance(part, s.DeclaredValue):
                kind = part.type
                written = 'bool' if kind == s.BOOL else 'text' if kind == s.TEXT else 'number'
                out[f'{member}.{part.name}'] = tuple(kind.members) if isinstance(kind, s.EnumOf) else written
    return out


def test_every_expression_of_a_model_builds_and_the_model_writes_every_node(every):
    found, parts = set(), set()
    for place, expression in notation.walk(every):
        node = notation.build(expression, notation.keys_of(every, place))
        found |= {type(part) for part in notation.nodes(node)}
        parts.add(place.part)
    # The text writes an expression in each of these places.
    assert parts == {
        'init',
        'lower',
        'upper',
        'capacity',
        'request',
        'delay',
        'value',
        'selector',
        'input',
        'own',
        'argument',
    }
    # Every node but those that only the panel makes: a derivative, an assignment and a sign.
    assert found >= set(notation.NODES.values()) - {Deriv, Assign, Pos}


def test_each_expression_of_a_model_keeps_its_value_and_its_latex_too(every):
    kinds = kinds_of(every)
    points = [Point(seed, kinds) for seed in (1, 2, 3)]
    for place, expression in notation.walk(every):
        keys = notation.keys_of(every, place)
        node = notation.build(expression, keys)
        text, back = latex_back(node)
        assert shape(canonical(back)) == shape(canonical(node)), (place, text)
        for point in points:
            expected = outcome(value_of_typed, expression, point, keys)
            assert same(outcome(value_of_node, node, point), expected), (place, point.seed)
            assert same(outcome(value_of_node, back, point), expected), (place, text, point.seed)


# ---- a membership test ----------------------------------------------------------------------------

# A plant with a membership test in each place where a model writes one: a formula, a stage's guard,
# a trigger's condition and a stage's statement, with ends that the model fixes, ends that only a run
# knows, and both. The fill reads `inside`, so the Equations panel shows that formula; the statement
# is a jump of the panel.
MEMBERSHIP = """\
scenario "Interval"
    horizon 4 h

plant:
    lo: h = 1 h
    hi: h = 3 h
    x: h = 2.5 h
    y: h = 0.5 h
    on: bool = true
    seen: bool = false
    water: L = 1 L in [0 L,]
    inside = formula(this.x in [this.lo, this.hi])
    fixed = formula(this.x + this.y in [1 h, 3 h])
    picked = formula((this.x if this.on else this.y) in [this.lo, 2 * this.hi])
    flow fill: SOURCE -> this.water
        request = 2 L/h if this.inside else 1 L/h
    go = event():
        when this.on and not (this.x in [this.lo, 3 h]):
            this.go.start()
        after 1 h when this.x in [1 h, 2 h]:
            this.seen = (this.y in [this.lo, this.hi])
    check = event():
        when this.x in [this.lo, this.hi]:
            this.check.start()
        after 0 h when this.y in [this.lo, this.hi]:
            this.seen = false
"""


def plant(name):
    return Sym(f'plant.{name}')


# Each membership of the plant by its place: its node; its LaTeX with the symbols of the test
# (`symbols`: x_{i} in the order of the node's reads), whose only parentheses are those of an operand
# of a lower precedence than a comparison's (a conditional, and the membership under `not`); and its
# value at points given by hand, in hours: true, false, and the failure of a reversed interval, which
# ends that the model fixes cannot be (the compiler refuses them).
MEMBERSHIPS = {
    ('plant.inside', 'init'): (
        In(plant('x'), plant('lo'), plant('hi')),
        r'x_{1} \in \left[x_{2}, x_{3}\right]',
        (({'x': 2.5, 'lo': 1, 'hi': 3}, True), ({'x': 3.5, 'lo': 1, 'hi': 3}, False)),
        ({'x': 2.5, 'lo': 3, 'hi': 2},),
    ),
    ('plant.fixed', 'init'): (
        In(Op('+', plant('x'), plant('y')), Num(1, 'h'), Num(3, 'h')),
        r'x_{1} + x_{2} \in \left[1\,\mathrm{h}, 3\,\mathrm{h}\right]',
        (({'x': 2.5, 'y': 0.5}, True), ({'x': 2.75, 'y': 0.5}, False)),
        (),
    ),
    ('plant.picked', 'init'): (
        In(Cases(((plant('on'), plant('x')),), plant('y')), plant('lo'), Op('*', Num(2), plant('hi'))),
        r'\left(\begin{cases} x_{2} & \text{if } x_{1} \\ x_{3} & \text{otherwise} \end{cases}\right) '
        r'\in \left[x_{4}, 2 \cdot x_{5}\right]',
        (
            ({'on': True, 'x': 2.5, 'y': 0.5, 'lo': 1, 'hi': 3}, True),
            ({'on': False, 'x': 2.5, 'y': 0.5, 'lo': 1, 'hi': 3}, False),
        ),
        ({'on': True, 'x': 2.5, 'y': 0.5, 'lo': 7, 'hi': 3},),
    ),
    ('plant.go.when[0]', 'when'): (
        Logic('and', (plant('on'), Not(In(plant('x'), plant('lo'), Num(3, 'h'))))),
        r'x_{1} \land \lnot \left(x_{2} \in \left[x_{3}, 3\,\mathrm{h}\right]\right)',
        (({'on': True, 'x': 3.5, 'lo': 1}, True), ({'on': True, 'x': 3, 'lo': 1}, False)),
        ({'on': True, 'x': 2.5, 'lo': 4},),
    ),
    ('plant.go.step[0]', 'guard'): (
        In(plant('x'), Num(1, 'h'), Num(2, 'h')),
        r'x_{1} \in \left[1\,\mathrm{h}, 2\,\mathrm{h}\right]',
        (({'x': 1}, True), ({'x': 2.5}, False)),
        (),
    ),
    ('plant.go.step[0].do[0]', 'value'): (
        In(plant('y'), plant('lo'), plant('hi')),
        r'x_{1} \in \left[x_{2}, x_{3}\right]',
        (({'y': 2, 'lo': 2, 'hi': 2}, True), ({'y': 0.5, 'lo': 1, 'hi': 3}, False)),
        ({'y': 2, 'lo': 2.5, 'hi': 2},),
    ),
    ('plant.check.when[0]', 'when'): (
        In(plant('x'), plant('lo'), plant('hi')),
        r'x_{1} \in \left[x_{2}, x_{3}\right]',
        (({'x': 3, 'lo': 1, 'hi': 3}, True), ({'x': 0.5, 'lo': 1, 'hi': 3}, False)),
        ({'x': 2.5, 'lo': 3, 'hi': 1},),
    ),
    ('plant.check.step[0]', 'guard'): (
        In(plant('y'), plant('lo'), plant('hi')),
        r'x_{1} \in \left[x_{2}, x_{3}\right]',
        (({'y': 1, 'lo': 1, 'hi': 3}, True), ({'y': 3.5, 'lo': 1, 'hi': 3}, False)),
        ({'y': 1, 'lo': 3.5, 'hi': 3},),
    ),
}


class Given(Point):
    """A point whose values are given by hand, by name, with each unit at the scale 1."""

    def __init__(self, values):
        super().__init__(0)
        self.given = values

    def value(self, key):
        return self.given[key.rpartition('.')[2]]

    def scale(self, unit):
        return 1


def verdict(evaluate, *args):
    """The value of an evaluation, or the text of its failure."""
    try:
        return evaluate(*args)
    except ValueError as failure:
        return str(failure)


@pytest.fixture(scope='module')
def membership():
    return Things(compiled(MEMBERSHIP))


def test_a_membership_is_its_node_its_latex_and_its_value_wherever_the_model_writes_it(membership):
    found = {
        (place.path, place.part): (expression, notation.keys_of(membership, place))
        for place, expression in notation.walk(membership)
    }
    assert set(MEMBERSHIPS) <= set(found)
    for where, (node, written, values, reversed_values) in MEMBERSHIPS.items():
        expression, keys = found[where]
        made = notation.build(expression, keys)
        assert shape(made) == shape(node), (where, made)
        text, back = latex_back(made)
        assert text == written, where
        assert shape(back) == shape(node), (where, text)
        cases = [*values, *((at, REVERSED) for at in reversed_values)]
        for at, expected in cases:
            point = Given(at)
            for value in (
                verdict(value_of_typed, expression, point, keys),
                verdict(value_of_node, made, point),
                verdict(value_of_node, back, point),
            ):
                assert value == expected and type(value) is type(expected), (where, at, value)


SVG = '{http://www.w3.org/2000/svg}'


def test_napkin_draw_writes_a_membership_as_the_model_writes_it(tmp_path, capsys):
    # The panel shows two memberships: the formula `inside`, which the fill reads, and the jump of
    # `go`. Each reads as the model writes it, a symbol, `∈`, and the interval of two symbols; the
    # LaTeX writes `\in` and the interval. The card shows the guards and the triggers' conditions in
    # the words of `triggers.py`. Nothing names the program's `within`.
    folder = package(tmp_path / 'interval', MEMBERSHIP, COMMAND_UNITS)
    style = '[equations]\nthings = ["plant"]\n\n[triggers]\nrules = ["plant"]\n'
    (folder / 'style.toml').write_text(style, encoding='utf-8')
    picture, latex = tmp_path / 'interval.svg', tmp_path / 'interval.tex'
    done = napkin(capsys, 'draw', folder, '-o', picture, '--latex', latex)
    assert done.code == 0, done.err
    root = ET.parse(picture).getroot()
    lines = [
        ''.join(span.text or '' for span in text.iter(f'{SVG}tspan'))
        for text in root.iter(f'{SVG}text')
        if text.get('class') == 'math'
    ]
    memberships = [line for line in lines if '∈' in line]
    symbol = r'[^⇔←∈\[\],]+'
    assert len(memberships) == 2, lines
    assert all(re.fullmatch(rf'{symbol}[⇔←]{symbol}∈\[{symbol},{symbol}\]', line) for line in memberships)
    words = '\n'.join(root.itertext())
    assert 'go — when on and not (x is in [lo, 3 h]); after 1 h when x is in [1 h, 2 h]: sets seen' in words
    assert 'check — when x is in [lo, hi]; after 0 h when y is in [lo, hi]: sets seen' in words
    text = latex.read_text(encoding='utf-8')
    assert text.count(r' \in \left[') == 2 and text.count(r'\right]') == 2
    assert 'within' not in picture.read_text(encoding='utf-8') + text


# ---- the LaTeX of the precedences -----------------------------------------------------------------

# Pairs of texts with the same operands and operators in another grouping. A writer that leaves out the
# parentheses of the first writes the second.
GROUPINGS = [
    ('a - (b - c)', 'a - b - c'),
    ('a / (b * c)', 'a / b * c'),
    ('(a + b) ** 2', 'a + b ** 2'),
    ('-(a ** 2) + c', '(-a) ** 2 + c'),
    ('a ** b ** c', '(a ** b) ** c'),
    ('a * (b / c)', 'a * b / c'),
    ('a + (b + c)', 'a + b + c'),
    ('2 ** (a / (b * c))', '2 ** (a / b * c)'),
    ('2 ** (a / (b / c))', '2 ** (a / b / c)'),
    ('2 ** (a * (b / c))', '2 ** (a * b / c)'),
    ('a * -b', '-(a * b)'),
    ('(a if p else b) + c', 'a if p else b + c'),
    ('a if p else (b if q else c)', '(a if p else b) if q else c'),
    ('(p or q) and r', 'p or (q and r)'),
    ('not p and q', 'not (p and q)'),
    ('(p and q) and r', 'p and q and r'),
    ('a < b < c', '(a < b) < c'),
    ('min(a, b) ** 2', 'min(a, b ** 2)'),
]


@pytest.mark.parametrize(('first', 'second'), GROUPINGS)
def test_the_latex_keeps_the_grouping_that_the_tree_has(first, second):
    texts = []
    for text in (first, second):
        node = built(text)
        written, back = latex_back(node)
        texts.append(written)
        assert shape(back) == shape(node), (text, written)
        for seed in range(6):
            point = Point(seed)
            expected = outcome(value_of_typed, node_of(text), point, KEYS)
            assert same(outcome(value_of_node, back, point), expected), (text, written)
    assert texts[0] != texts[1]


@pytest.mark.parametrize(
    ('text', 'parentheses'),
    [
        ('a - (b - c)', 1),
        ('(a - b) - c', 0),
        ('a + (b + c)', 1),
        ('(a * b) * c', 0),
        ('-(a ** 2)', 0),
        ('(-a) ** 2', 1),
        ('a ** b ** c', 0),
        ('(a ** b) ** c', 1),
        ('a / (b * c)', 0),
        ('(a + b) / (c - d)', 0),
        ('(a + b) * (c - d)', 2),
        ('-a * b', 0),
        ('not p and (q or r)', 1),
        ('not (a < b)', 1),
        ('a + b in [c - d, c * d]', 0),
        ('(a if p else b) in [c, d]', 1),
        ('not (a in [b, c])', 1),
        ('p and a in [b, c]', 0),
        ('(a in [b, c]) == p', 1),
        ('(a in [b, c]) in [d, e]', 1),
        ('a in [b in [c, d], e]', 0),
    ],
)
def test_the_latex_has_the_fewest_parentheses(text, parentheses):
    # A fraction and the braces of a power need no parentheses; each other grouping keeps one pair.
    written, _ = latex_back(built(text))
    assert written.count(r'\left(') == parentheses, written


@pytest.mark.parametrize(
    ('text', 'parentheses'),
    [('a * -b', 1), ('a - -b', 1), ('-(-a)', 1), ('not not p', 1), ('not -a < b', 1), ('p or q and r', 1)],
)
def test_the_latex_has_parentheses_that_python_does_not_need(text, parentheses):
    # For the reader: a sign after an operator or a sign, the operand of `not` that is not an atom, and
    # an `and` inside an `or`.
    written, _ = latex_back(built(text))
    assert written.count(r'\left(') == parentheses, written


def test_a_division_in_an_exponent_is_a_slash_and_elsewhere_a_fraction():
    written, _ = latex_back(built('a / b + 2 ** (a / b)'))
    assert written.count(r'\frac') == 1
    assert written.count(' / ') == 1
    assert written.index(r'\frac') < written.index('^')


# ---- properties of random nodes -------------------------------------------------------------------

UNITS = [
    'h',
    'people/h',
    'm^2/s',
    's^-1',
    'person-hours',
    'USD2025_bn',
    'a%b',
    'x{y}',
    'q^2^3',
    '^2m',
    'k~&#$\\',
]
WORDS = st.text(
    alphabet=string.ascii_letters + string.digits + ' _&%$#{}~^\\<>|-.,:;!?\'"()[]=+*/@', max_size=8
)
NUMBERS_OF_NODES = st.one_of(
    st.integers(0, 10**20),
    st.floats(min_value=0, allow_nan=False, allow_infinity=False).map(abs),
    st.sampled_from([0.5, 1.0, 1e-05, 2.5e-300, 1e16, 1.5e20]),
)
KEYS_OF_NODES = st.sampled_from(['s.a', 's.b', 'places.a.c', 'total', 'grinder.refill.amount'])
EVENTS_OF_NODES = st.sampled_from(['s.go', 'places.b.find'])
LEAVES = st.one_of(
    KEYS_OF_NODES.map(Sym),
    st.builds(Num, NUMBERS_OF_NODES, st.one_of(st.none(), st.sampled_from(UNITS))),
    WORDS.map(Text),
    st.booleans().map(Text),
    st.just(Time()),
    EVENTS_OF_NODES.map(Since),
    EVENTS_OF_NODES.map(Count),
    KEYS_OF_NODES.map(Elapsed),
    st.builds(Sum, st.sampled_from(notation.LISTS), st.lists(KEYS_OF_NODES.map(Sym), max_size=3).map(tuple)),
)
# The functions of a `Call` with the number of their arguments.
ARITY = {
    'clip': 3,
    'abs': 1,
    'exp': 1,
    'expm1': 1,
    'ln': 1,
    'log1p': 1,
    'erf': 1,
    **dict.fromkeys(notation.STEPS, 1),
}


def _extend(children):
    pairs = st.tuples(children, children)
    otherwise = children.filter(lambda node: not isinstance(node, Cases))
    one = st.tuples(children)
    calls = st.one_of(
        *(
            st.builds(Call, st.just(name), st.lists(children, min_size=n, max_size=n).map(tuple))
            for name, n in ARITY.items()
        ),
        st.builds(
            Call,
            st.sampled_from(['min', 'max']),
            st.lists(
                st.one_of(children, LEAVES.filter(lambda node: isinstance(node, Sum))), min_size=2, max_size=3
            ).map(tuple),
        ),
        st.builds(
            lambda args, keywords: Call('normal', args, keywords),
            st.lists(children, max_size=2).map(tuple),
            st.just((('FIXED', Num(3)),)) | st.just(()),
        ),
    )
    return st.one_of(
        st.builds(Op, st.sampled_from(sorted(notation.OPERATORS)), children, children),
        children.map(Neg),
        children.map(Pos),
        children.map(Not),
        st.builds(
            lambda ops, items: Cmp(tuple(ops), tuple(items[: len(ops) + 1])),
            st.lists(st.sampled_from(sorted(notation.COMPARISONS)), min_size=1, max_size=2),
            st.lists(children, min_size=3, max_size=3),
        ),
        st.builds(In, children, children, children),
        st.builds(
            Logic, st.sampled_from(['and', 'or']), st.lists(children, min_size=2, max_size=3).map(tuple)
        ),
        st.builds(Cases, st.lists(pairs, min_size=1, max_size=3).map(tuple), otherwise),
        calls,
        one.map(lambda xs: Call('sqrt', xs)),
    )


NODES = st.recursive(LEAVES, _extend, max_leaves=12)


@settings(max_examples=300, derandomize=True, deadline=None)
@given(NODES)
def test_a_random_node_reads_back_from_its_latex_and_its_json(node):
    written, back = latex_back(node)
    assert shape(canonical(back)) == shape(canonical(node)), written
    data = json.loads(notation.to_json(node))
    assert shape(notation.from_dict(data)) == shape(node)
    assert notation.from_dict(data) == node


# Random expressions of the typed form: arithmetic, comparisons, memberships, groups and conditionals
# of the values of `s`, and calls.
TYPED_TEXTS = st.recursive(
    st.one_of(st.sampled_from(['a', 'b', 'c', 't', '2', '0.5', 'q(3, "h")', 'since(go)', 'elapsed(b)'])),
    lambda children: st.one_of(
        st.builds(
            lambda a, op, b: f'({a} {op} {b})',
            children,
            st.sampled_from(['+', '-', '*', '/', '**']),
            children,
        ),
        children.map(lambda a: f'(-{a})'),
        st.builds(lambda a, b: f'max({a}, {b})', children, children),
        st.builds(lambda a, b, c: f'({a} if {b} < {c} else {c})', children, children, children),
        st.builds(lambda a, b, c: f'({a} if {b} in [{c}, {a}] else {c})', children, children, children),
        children.map(lambda a: f'exp({a})'),
    ),
    max_leaves=10,
)


@settings(max_examples=300, derandomize=True, deadline=None)
@given(TYPED_TEXTS)
def test_a_random_expression_has_the_value_of_its_node_and_of_its_latex(text):
    expression = node_of(text)
    node = notation.build(expression, KEYS)
    _, back = latex_back(node)
    for seed in range(3):
        point = Point(seed)
        expected = outcome(value_of_typed, expression, point, KEYS)
        assert same(outcome(value_of_node, node, point), expected), text
        assert same(outcome(value_of_node, back, point), expected), text


def test_a_derivative_has_no_expression_and_its_latex_reads_back():
    node = Op('-', Deriv('s.held'), Sym('s.k'))
    written, back = latex_back(node)
    assert shape(back) == shape(node), written


# ---- texts and units ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    'word',
    [
        'a_b',
        'R&D',
        '50%',
        '#1',
        '{x}',
        'x}{y',
        r'back\slash',
        '~^',
        'a < b > c | d',
        '$5',
        'if ',
        'otherwise',
    ],
)
def test_a_text_with_special_characters_reads_back_the_same(word):
    written, back = latex_back(Cmp(('==',), (Sym('s.mode'), Text(word))))
    assert back.items[1] == Text(word), written


@pytest.mark.parametrize('unit', UNITS)
def test_a_unit_reads_back_the_same(unit):
    written, back = latex_back(Op('*', Num(12, unit), Num(0.5, unit)))
    assert back == Op('*', Num(12, unit), Num(0.5, unit)), written


def test_a_reader_refuses_a_special_character_that_is_not_escaped():
    # The reader is strict: the tests that read texts back prove the escapes.
    with pytest.raises(LatexError):
        read(r'\text{a_b}', {})
    with pytest.raises(LatexError):
        read(r'2\,\mathrm{a-b}', {})
