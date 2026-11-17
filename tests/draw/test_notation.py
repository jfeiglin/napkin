"""The notation of the Equations panel (napkin/draw/notation.py): each node is the model's expression,
node for node, and its LaTeX says the same.

- Round trip: `to_node(build(e))` is the typed node of each expression (the same object: two typed
  nodes with the same parts are one), for every expression of every catalogue model and of synthetic
  models that write every construct of the language.
- Value: an evaluator of the typed nodes of the semantic model and an evaluator of the notation's
  nodes, both written here (neither is the engine's), give the same value at seeded random points: a
  random value for each name, a random positive scale for each unit, a random time since each event.
- LaTeX: `latex_subset.py` reads the LaTeX back into a node, which has the shape of the node and the
  value of the expression at the same points. Counterexamples show the parentheses that a naive
  writer leaves out.
"""

from __future__ import annotations

import ast
import cmath
import json
import math
import operator
import random
import string
from collections.abc import Mapping
from dataclasses import fields, is_dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.core import expr as typed
from napkin.draw import notation
from napkin.draw.notation import (
    Assign,
    Call,
    Cases,
    Cmp,
    Count,
    Deriv,
    Elapsed,
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
from napkin.model import resolved, semantic
from napkin.model.ir import DRAWN, thaw
from napkin.model.language.expressions import FUNCTIONS
from napkin.model.semantic import EventRef, Problem, Ref, Terms
from tests.acceptance.helpers import LIBRARY, fixture
from tests.build import (
    BASIS,
    check,
    compiled,
    document,
    entity,
    event,
    flow,
    formula,
    named,
    option,
    options,
    output,
    parameter,
    runs,
    status,
    stock,
    template,
)
from tests.draw.latex_subset import LatexError, read, read_line
from tests.helpers import SCENARIO_IDS, catalogue_model

# ---- typed nodes ----------------------------------------------------------------------------------


def key(ref):
    return ref.member if ref.entity is None else f'{ref.entity}.{ref.member}'


def node_of(text, entity='s'):
    """The typed nodes of a Python text, as the front end gives them: each name a `Ref` of `entity`,
    `true` and `false` `Word`s, and the function names and `t` as they are."""

    def named(node):
        if isinstance(node, typed.Ref):
            if node.name == 't':
                return node
            if node.name in ('true', 'false'):
                return resolved.word(node.name == 'true', None)
            return resolved.ref(entity, node.name, node.name)
        if isinstance(node, typed.Unary):
            return typed.unary(node.op, named(node.operand))
        if isinstance(node, typed.Binary):
            return typed.binary(node.op, named(node.left), named(node.right))
        if isinstance(node, typed.Compare):
            return typed.compare(node.ops, map(named, node.operands))
        if isinstance(node, typed.BoolOp):
            return typed.boolean(node.op, map(named, node.values))
        if isinstance(node, typed.IfElse):
            return typed.if_else(named(node.test), named(node.body), named(node.orelse))
        if isinstance(node, typed.Call):
            return typed.call(node.function, map(named, node.args))
        assert isinstance(node, typed.Const), node
        return node

    return named(typed.parse(text, functions=FUNCTIONS))


def shape(value):
    """The meaning of a node, to compare: its class and fields, without how the file writes its names
    (`written`, `problem`), and with the type of each number."""
    if is_dataclass(value):
        kept = [f for f in fields(value) if f.name not in ('written', 'problem')]
        return (type(value).__name__, *(shape(getattr(value, f.name)) for f in kept))
    if isinstance(value, tuple):
        return tuple(shape(item) for item in value)
    if isinstance(value, float):
        return ('float', value)
    return value


def canonical(node):
    """A node with the lists of `min` and `max` written as their members, as LaTeX writes them, and a
    line `x += v` as `x = x + v`, its semantic tree."""
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
    changed = {}
    for f in fields(node):
        value = getattr(node, f.name)
        changed[f.name] = _canonical(value)
    return type(node)(**changed)


def _canonical(value):
    if isinstance(value, notation.Node):
        return canonical(value)
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    return value


# ---- the two evaluators ---------------------------------------------------------------------------


def stand_in(name, args, keywords):
    """The value that the tests give a distribution or `delayed`: it reads each parameter by its
    place, so a parameter in the wrong place or under the wrong name changes it."""
    if name == 'delayed':
        return 0.5 * args[0] + args[1]
    given = dict(zip(DRAWN[name], args)) | dict(keywords)
    return len(name) + sum((i + 1) * given[p] for i, p in enumerate(DRAWN[name]) if p in given)


FUNCTIONS_OF_TESTS = {
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
}
BINARY = {
    'add': operator.add,
    'sub': operator.sub,
    'mul': operator.mul,
    'div': operator.truediv,
    'pow': operator.pow,
}
ORDER = {
    'lt': operator.lt,
    'le': operator.le,
    'gt': operator.gt,
    'ge': operator.ge,
    'eq': operator.eq,
    'ne': operator.ne,
}


class Point:
    """A seeded random point: a value for each name (of the type that `kinds` gives it), a positive
    scale for each unit, the time, and for each event or outcome the time since it and its count.
    Each value depends on the seed and the name only, so the order of the reads does not matter."""

    def __init__(self, seed, kinds=None):
        self.seed, self.kinds = seed, kinds or {}
        self.time = self.rng('t').uniform(0, 10)

    def rng(self, *name):
        return random.Random(':'.join(map(str, (self.seed, *name))))

    def value(self, name):
        rng = self.rng('value', name)
        kind = self.kinds.get(name, 'copy' if name.endswith('.copy') else 'number')
        if kind == 'bool':
            return rng.random() < 0.5
        if isinstance(kind, tuple):
            return rng.choice(kind)
        if kind == 'text':
            return rng.choice(('a', 'b'))
        if kind == 'copy':
            return rng.randint(1, 5)
        return rng.uniform(0.25, 4.0)

    def scale(self, unit):
        return self.rng('unit', unit).uniform(0.5, 2.0)

    def since(self, target):
        return self.rng('since', target).uniform(0, 5)

    def count(self, target):
        return self.rng('count', target).randint(0, 3)

    def elapsed(self, name):
        return self.rng('elapsed', name).uniform(0, 5)


def value_of_resolved(node, point):
    """The value of the typed nodes of an expression of the semantic model, by Python's rules."""

    def of(node):
        if isinstance(node, resolved.Ref):
            return point.value(key(node))
        if isinstance(node, resolved.Word):
            return node.value
        if isinstance(node, resolved.Terms):
            raise AssertionError('a list is the argument of a function')
        if isinstance(node, typed.Const):
            return node.value
        if isinstance(node, typed.Ref):
            assert node.name == 't'
            return point.time
        if isinstance(node, typed.Binary):
            return BINARY[node.op](of(node.left), of(node.right))
        if isinstance(node, typed.Unary):
            x = of(node.operand)
            return {'neg': operator.neg, 'pos': operator.pos, 'not': operator.not_}[node.op](x)
        if isinstance(node, typed.BoolOp):
            result = None
            for item in node.values:
                result = of(item)
                if (node.op == 'and') != bool(result):
                    return result
            return result
        if isinstance(node, typed.Compare):
            left = of(node.operands[0])
            for op, item in zip(node.ops, node.operands[1:]):
                right = of(item)
                if not ORDER[op](left, right):
                    return False
                left = right
            return True
        if isinstance(node, typed.IfElse):
            return of(node.body) if of(node.test) else of(node.orelse)
        if isinstance(node, resolved.Named):
            name, given, named = node.function, node.args, node.named
        else:
            assert isinstance(node, typed.Call), node
            name, given, named = node.function, node.args, ()
        if name == 'q':
            return given[0].value * point.scale(given[1].value)
        if name in ('since', 'count') and isinstance(given[0], resolved.EventRef):
            ref = given[0]
            target = ref.key if ref.ending is None else f'{ref.key}.{ref.ending}'
            return point.since(target) if name == 'since' else point.count(target)
        if name == 'elapsed':
            return point.elapsed(key(given[0]))
        args = []
        for arg in given:
            listed = isinstance(arg, resolved.Terms)
            args += [point.value(key(ref)) for ref in arg.refs] if listed else [of(arg)]
        if name in ('sum', 'any', 'all', 'count'):
            return {'sum': sum, 'any': any, 'all': all, 'count': lambda xs: sum(1 for x in xs if x)}[name](
                args
            )
        if name in DRAWN or name == 'delayed':
            return stand_in(name, args, [(k, of(v)) for k, v in named])
        return FUNCTIONS_OF_TESTS[name](*args)

    return of(node)


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
            tests = {'<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}
            tests |= {'==': operator.eq, '!=': operator.ne}
            values = [of(node.items[0])]
            for op, item in zip(node.ops, node.items[1:]):
                values.append(of(item))
                if not tests[op](values[-2], values[-1]):
                    return False
            return True
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
            if node.name in DRAWN or node.name == 'delayed':
                return stand_in(node.name, args, [(k, of(v)) for k, v in node.keywords])
            return FUNCTIONS_OF_TESTS[node.name](*args)
        if isinstance(node, Since):
            return point.since(node.event if node.ending is None else f'{node.event}.{node.ending}')
        if isinstance(node, Count):
            return point.count(node.event if node.ending is None else f'{node.event}.{node.ending}')
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
    names and `e_{i}` for each event or outcome."""
    values, events = {}, {}
    for part in notation.nodes(node):
        if isinstance(part, (Sym, Elapsed, Deriv)):
            values.setdefault(part.key, f'x_{{{len(values) + 1}}}')
        elif isinstance(part, Assign):
            values.setdefault(part.target, f'x_{{{len(values) + 1}}}')
        elif isinstance(part, (Since, Count)):
            events.setdefault((part.event, part.ending), f'e_{{{len(events) + 1}}}')
    by_key = dict(values)
    for (name, ending), written in events.items():
        by_key[name if ending is None else f'{name}.{ending}'] = written
    return (
        by_key.__getitem__,
        {written: name for name, written in values.items()},
        {written: pair for pair, written in events.items()},
    )


def latex_back(node):
    """The node that the subset reader reads from the LaTeX of `node`, with the symbols of `node`."""
    symbol, values, events = symbols(node)
    text = notation.latex(node, symbol)
    found = read_line(text, values, events) if isinstance(node, Assign) else read(text, values, events)
    return text, found


# ---- what a model's checks share ------------------------------------------------------------------


def value_kinds(scenario):
    """{key: 'bool', 'text', the named values (a tuple) or 'number'} of each value of a model."""
    kinds = {}
    for item in scenario.entities:
        for value in item.values:
            written = thaw(value.type)
            if written in ('bool', 'text'):
                kind = written
            elif isinstance(written, list):
                kind = tuple(written)
            else:
                kind = 'number'
            kinds[f'{item.name}.{value.name}'] = kind
    return kinds


def lines_of(scenario):
    """Each line of an event that sets a value (a semantic `Assign`)."""
    for item in scenario.entities:
        for found in item.events:
            for result in found.outcomes:
                for line in result.lines:
                    if isinstance(line, semantic.Assign):
                        yield line


def reachable(value, seen=None):
    """Every `Expression`, `Assign` and `Move` that the dataclasses of a semantic model hold, by a
    search of all their fields: what `walk` must give."""
    seen = set() if seen is None else seen
    if id(value) in seen or isinstance(value, (str, int, float)) or value is None:
        return
    seen.add(id(value))
    if isinstance(value, (semantic.Expression, semantic.Assign, semantic.Move)):
        yield value
        if isinstance(value, semantic.Expression):
            return
    if is_dataclass(value):
        for f in fields(value):
            yield from reachable(getattr(value, f.name), seen)
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from reachable(item, seen)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from reachable(item, seen)


def check_round_trip(model):
    """Each expression and each line of a model: its node gives its typed node back. `walk` gives every
    expression and every line once. The number of expressions."""
    found = list(notation.walk(model))
    given = {id(e) for _, e in found}
    assert len(given) == len(found)
    nodes = {e.node for _, e in found}
    for part in reachable(model.scenario):
        if isinstance(part, semantic.Expression):
            assert id(part) in given, part.where
        else:
            assert (part.value if isinstance(part, semantic.Assign) else part.amount) in nodes, part.where
    for place, expression in found:
        node = notation.build(expression)
        if notation.literal(expression):
            # A bare yes/no or number with no tree of its own: the word or the number as written.
            written = thaw(expression.written)
            assert isinstance(written, (bool, int, float)), place
            assert same(outcome(value_of_node, node, Point(0)), ('value', written)), place
            continue
        assert not isinstance(expression.node, resolved.Problem), place
        assert notation.to_node(node) is expression.node, place
        again = notation.build(notation.to_node(node))
        assert again == node and shape(again) == shape(node), place
    for line in lines_of(model.scenario):
        node = notation.assignment(line)
        assert notation.to_node(node) is line.value, line.where
    return len(found)


def check_values(model, seeds=(1, 2, 3)):
    """At each point, each expression and each line has the value of its typed nodes as a node and as the
    LaTeX of the node, which also reads back to the node's shape."""
    kinds = value_kinds(model.scenario)
    points = [Point(seed, kinds) for seed in seeds]
    items = [(place, notation.build(e), e) for place, e in notation.walk(model)]
    items += [(line.where, notation.assignment(line), line.value) for line in lines_of(model.scenario)]
    for place, node, item in items:
        text, back = latex_back(node)
        assert shape(canonical(back)) == shape(canonical(node)), (place, text)
        for point in points:
            if isinstance(item, semantic.Expression) and notation.literal(item):
                expected = ('value', thaw(item.written))
            else:
                given = item.node if isinstance(item, semantic.Expression) else item
                expected = outcome(value_of_resolved, given, point)
            assert same(outcome(value_of_node, node, point), expected), (place, point.seed)
            assert same(outcome(value_of_node, back, point), expected), (place, text, point.seed)


# ---- synthetic models -----------------------------------------------------------------------------


def line(text):
    return f'{text}  {BASIS}'


# One model that writes each construct of the expressions: every function, the lists, the clocks,
# a chain of comparisons and of cases, the signs, the units, yes/no words and named values.
EVERY_CONSTRUCT = document(
    'Notation fixture',
    template(
        'Zone',
        stock('level', 10, 'people', maximum=100, size=None),
        parameter('flag', True, 'bool', True, True),
        formula('weight', '0.5 * level / (1 people)', 'fraction'),
    ),
    template('Wave', formula('order', 'copy / 10', 'fraction')),
    template('Spare', stock('stock', 1, 'people', maximum=10, size=None)),
    entity('north', template='Zone'),
    entity('south', template='Zone'),
    entity('waves', template='Wave', copies=2),
    entity(
        's',
        parameter('x', 2, 'h', 1, 9),
        parameter('k', 0.3, 'fraction', 0, 1),
        parameter('y', 'uniform(1 h, x)', 'h', 1, 9),
        parameter('on', True, 'bool', True, True),
        named('mode', 'idle', 'busy', 'done'),
        stock('held', 5, 'people', maximum=1000, size=None),
        line('let zones = [north, south]'),
        formula('f1', 'min(k, 0.5) + max(k, 0.1) + clip(k, 0.2, 0.8) + abs(k - 0.5)', 'fraction'),
        formula('f2', 'exp(k) + expm1(k) + ln(1 + k) + log1p(k) + sqrt(k) + erf(k / sqrt(2))', 'fraction'),
        formula(
            'f3',
            'sum(zones.level) + max(zones.level) + min(zones.level, 3 people) + max(Zone.level, held)'
            ' + sum(Spare.stock)',
            'people',
        ),
        formula('f4', 'count(zones.flag) / 2 if any(zones.flag) and not all(zones.flag) else 0', 'fraction'),
        formula('f5', '1 if 0 h < x <= 5 h else (0.5 if x >= 5 h or not on else 0)', 'fraction'),
        formula('f6', '1 if mode is "busy" and on is true or mode is not "done" else 0', 'fraction'),
        formula(
            'f7', '(k + 1) ** 2 - -k ** 2 + (-k) ** 2 + k ** k ** 2 + k - (k - 1) + k / (k * 2)', 'fraction'
        ),
        formula('f8', 'x * 2 / 3 + 1.5e-3 h - +x + 2.5e-7 h * (1e20 / 1e20)', 'h'),
        formula('f9', 'sum(waves.order) + waves.1.order + (k if on is false else 1 - k)', 'fraction'),
        flow('drain', 'held ->', 'k * 1 people/h', condition='mode is "busy"'),
        flow('shift', ['north.level -> south.level', 'south.level -> at 0.5 people/h * k'], 'k * 1 people/h'),
        event('go', 't >= 1 h', 'mode = "busy"', 'held += 2 people'),
        event(
            'later',
            'since(go) >= x and count(go) > 0 and since(mode) >= 1 h',
            'held -= uniform(1 people, 2 people)',
        ),
        event('echo', 'count(later) > 0', 'held = delayed(held, 1 h)'),
        line('event pick once when t >= 2 h:') + '\n    yes k:\n        mode = "done"\n    no else:',
        event('after_pick', 'count(pick.yes) > 0 and since(pick.no) >= 0 h', 'held = 0 people'),
        status(('failed', 'held <= 0 people', 'Empty'), ('ok', None, 'Fine')),
        check('0 <= k <= 1', 'A share from 0 to 1'),
    ),
    output('total', 'max(s.held, north.level)', 'people', 'level'),
    output('double', 'total * 2', 'people', 'level'),
    option_groups=(
        options(
            'Response',
            option('Default', 'The defaults.'),
            option('More', 'More people.', line('s.held = 2 * 4 people')),
        ),
    ),
    run_lines=runs(a=['Default'], b=['More']),
)


@pytest.fixture(scope='module')
def synthetic():
    """The synthetic models: the one above, and F5 of the acceptance tests, which writes each
    construct of the language once."""
    return {'every construct': compiled(EVERY_CONSTRUCT), 'F5': compiled(fixture('F5'), LIBRARY)}


def test_the_synthetic_models_write_every_node_and_function(synthetic):
    built = [notation.build(e) for model in synthetic.values() for _, e in notation.walk(model)]
    parts = [part for node in built for part in notation.nodes(node)]
    kinds = {type(part) for part in parts}
    assert kinds == set(notation.NODES.values()) - {Deriv, Assign}
    called = {part.name for part in parts if isinstance(part, Call)}
    assert called >= set(notation.ARITY) | {'uniform'}
    assert {part.fn for part in parts if isinstance(part, Sum)} == set(notation.LISTS)
    assert any(isinstance(part, Cmp) and len(part.ops) > 1 for part in parts)
    assert any(isinstance(part, Cases) and len(part.pairs) > 1 for part in parts)
    assert any(isinstance(part, (Since, Count)) and part.ending is not None for part in parts)
    assert {part.word for part in parts if isinstance(part, Text)} >= {True, False}
    assert any(isinstance(part, Num) and part.unit is not None for part in parts)
    assert any(isinstance(part, Num) and 'e' in repr(part.value) for part in parts)
    assert any(isinstance(part, Sym) and part.key.endswith('.copy') for part in parts)
    assert any(isinstance(part, Sym) and '.' not in part.key for part in parts)
    assert any(isinstance(part, Sum) and not part.terms for part in parts)
    assert any(isinstance(part, Call) and any(isinstance(arg, Sum) for arg in part.args) for part in parts)
    # Each kind of place that `walk` gives, except the own rate of a value, which the front end never
    # sets (`Value.rate` is None: a flow gives the rate).
    places = {place.part for model in synthetic.values() for place, _ in notation.walk(model)}
    assert places >= {'start', 'formula', 'minimum', 'maximum', 'size', 'argument', 'output', 'lag'}
    assert places >= {'option', 'status', 'check', 'total', 'within', 'flow', 'while', 'pair', 'limit'}
    assert places >= {'when', 'after', 'each', 'keep', 'chance', 'available', 'set', 'move', 'timescale'}
    assert any(notation.literal(e) for model in synthetic.values() for _, e in notation.walk(model))


def test_each_expression_of_a_synthetic_model_is_its_node(synthetic):
    for model in synthetic.values():
        assert check_round_trip(model) > 0


def test_each_expression_of_a_synthetic_model_keeps_its_value_and_its_latex_too(synthetic):
    for model in synthetic.values():
        check_values(model, seeds=range(1, 9))


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_each_expression_of_a_catalogue_model_is_its_node(scenario_id):
    assert check_round_trip(catalogue_model(scenario_id)) > 0


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_each_expression_of_a_catalogue_model_keeps_its_value_and_its_latex_too(scenario_id):
    check_values(catalogue_model(scenario_id), seeds=(1, 2))


def test_the_notation_knows_each_function_of_the_language():
    # The clocks, the lists and `q` have their own nodes; each other function is a `Call`.
    own = {'q', 'since', 'count', 'elapsed', 'sum', 'any', 'all'}
    assert set(FUNCTIONS) == set(notation.ARITY) | set(DRAWN) | own


# ---- the LaTeX of the precedences -----------------------------------------------------------------

NUMBERS = {name: 'number' for name in 'abcd'} | {name: 'bool' for name in 'pqr'}
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
    nodes = [notation.build(node_of(text)) for text in (first, second)]
    texts = []
    for text, node in zip((first, second), nodes):
        written, back = latex_back(node)
        texts.append(written)
        assert shape(back) == shape(node), (text, written)
        for seed in range(6):
            point = Point(seed, {f's.{n}': kind for n, kind in NUMBERS.items()})
            expected = outcome(value_of_resolved, node_of(text), point)
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
    ],
)
def test_the_latex_has_the_fewest_parentheses(text, parentheses):
    # A fraction and the braces of a power need no parentheses; each other grouping keeps one pair.
    written, _ = latex_back(notation.build(node_of(text)))
    assert written.count(r'\left(') == parentheses, written


@pytest.mark.parametrize(
    ('text', 'parentheses'),
    [('a * -b', 1), ('a - -b', 1), ('-(-a)', 1), ('not not p', 1), ('not -a < b', 1), ('p or q and r', 1)],
)
def test_the_latex_has_parentheses_that_python_does_not_need(text, parentheses):
    # For the reader: a sign after an operator or a sign, the operand of `not` that is not an atom, and
    # an `and` inside an `or`.
    written, _ = latex_back(notation.build(node_of(text)))
    assert written.count(r'\left(') == parentheses, written


def test_a_division_in_an_exponent_is_a_slash_and_elsewhere_a_fraction():
    written, _ = latex_back(notation.build(node_of('a / b + 2 ** (a / b)')))
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
KEYS = st.sampled_from(['s.a', 's.b', 'waves.1.c', 'total', 'Zone_1.d'])
EVENTS = st.tuples(st.sampled_from(['s.go', 'waves.2.find']), st.sampled_from([None, 'done', 'shut']))
LEAVES = st.one_of(
    KEYS.map(Sym),
    st.builds(Num, NUMBERS_OF_NODES, st.one_of(st.none(), st.sampled_from(UNITS))),
    WORDS.map(Text),
    st.booleans().map(Text),
    st.just(Time()),
    EVENTS.map(lambda pair: Since(*pair)),
    EVENTS.map(lambda pair: Count(*pair)),
    KEYS.map(Elapsed),
    st.builds(Sum, st.sampled_from(notation.LISTS), st.lists(KEYS.map(Sym), max_size=3).map(tuple)),
)


def _extend(children):
    pairs = st.tuples(children, children)
    otherwise = children.filter(lambda node: not isinstance(node, Cases))
    one = st.tuples(children)
    calls = st.one_of(
        *(
            st.builds(Call, st.just(name), st.lists(children, min_size=n, max_size=n).map(tuple))
            for name, n in notation.ARITY.items()
            if n is not None
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
            st.just((('max', Num(3)),)) | st.just(()),
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
        st.builds(
            Logic, st.sampled_from(['and', 'or']), st.lists(children, min_size=2, max_size=3).map(tuple)
        ),
        st.builds(Cases, st.lists(pairs, min_size=1, max_size=3).map(tuple), otherwise),
        calls,
        one.map(lambda xs: Call('sqrt', xs)),
    )


NODES = st.recursive(LEAVES, _extend, max_leaves=12)


def _as_built(node):
    """Whether a node is the one that `build` makes of its tree: a `min` or `max` of one list alone is
    a `Sum`, and the last value of `Cases` is never a `Cases`."""
    for part in notation.nodes(node):
        if isinstance(part, Cases) and isinstance(part.otherwise, Cases):
            return False
        lone = isinstance(part, Call) and part.name in ('min', 'max') and len(part.args) == 1
        if lone and isinstance(part.args[0], Sum) and part.args[0].fn == part.name:
            return False
    return True


@settings(max_examples=300, derandomize=True, deadline=None)
@given(NODES)
def test_a_random_node_is_its_tree_and_its_latex(node):
    assert _as_built(node)
    made = notation.to_node(node)
    again = notation.build(made)
    assert shape(again) == shape(node)
    assert notation.to_node(again) is made
    written, back = latex_back(node)
    assert shape(canonical(back)) == shape(canonical(node)), written
    data = json.loads(notation.to_json(node))
    assert shape(notation.from_dict(data)) == shape(node)
    assert notation.from_dict(data) == node


ARITHMETIC = st.recursive(
    st.one_of(
        st.sampled_from(['s.a', 's.b', 's.c']).map(Sym),
        # Floats only: a power of floats that is too large fails at once, a power of whole numbers
        # does not.
        st.builds(Num, st.sampled_from([0.0, 1.0, 2.0, 0.5, 3.25, 1e-3]), st.one_of(st.none(), st.just('h'))),
    ),
    lambda children: st.one_of(
        st.builds(Op, st.sampled_from(sorted(notation.OPERATORS)), children, children),
        children.map(Neg),
        children.map(Pos),
        st.builds(lambda xs: Call('max', xs), st.lists(children, min_size=2, max_size=3).map(tuple)),
        st.builds(lambda x: Call('exp', (x,)), children),
    ),
    max_leaves=10,
)


@settings(max_examples=300, derandomize=True, deadline=None)
@given(ARITHMETIC)
def test_a_random_sum_or_product_has_the_value_of_its_tree_and_of_its_latex(node):
    made = notation.to_node(node)
    _, back = latex_back(node)
    for seed in range(3):
        point = Point(seed)
        expected = outcome(value_of_resolved, made, point)
        assert same(outcome(value_of_node, node, point), expected)
        assert same(outcome(value_of_node, back, point), expected)


# ---- nodes outside the notation -------------------------------------------------------------------

A = Ref(entity='s', member='a', written='a')


@pytest.mark.parametrize(
    ('tree', 'named'),
    [
        (ast.BinOp(left=A, op=ast.Mod(), right=ast.Constant(2)), 'Mod'),
        (ast.BinOp(left=A, op=ast.FloorDiv(), right=ast.Constant(2)), 'FloorDiv'),
        (ast.UnaryOp(op=ast.Invert(), operand=A), 'Invert'),
        (ast.Attribute(value=ast.Name(id='a', ctx=ast.Load()), attr='b', ctx=ast.Load()), 'Attribute'),
        (ast.Subscript(value=A, slice=ast.Constant(0), ctx=ast.Load()), 'Subscript'),
        (ast.Compare(left=A, ops=[ast.In()], comparators=[A]), 'Compare'),
        (ast.Name(id='x', ctx=ast.Load()), 'Name'),
        (ast.Constant(True), 'True'),
        (ast.Constant(None), 'None'),
        (ast.Constant(-1), '-1'),
        (ast.Call(func=ast.Name(id='tan', ctx=ast.Load()), args=[A], keywords=[]), 'tan'),
        (ast.Call(func=ast.Name(id='sqrt', ctx=ast.Load()), args=[A, A], keywords=[]), 'sqrt'),
        (ast.Call(func=ast.Name(id='clip', ctx=ast.Load()), args=[A], keywords=[]), 'clip'),
        (ast.Call(func=ast.Name(id='max', ctx=ast.Load()), args=[], keywords=[]), 'max'),
        (ast.Call(func=ast.Name(id='q', ctx=ast.Load()), args=[A, ast.Constant('h')], keywords=[]), 'q'),
        (
            ast.Call(
                func=ast.Name(id='min', ctx=ast.Load()), args=[A], keywords=[ast.keyword(arg='x', value=A)]
            ),
            'min',
        ),
        (
            ast.Call(
                func=ast.Name(id='uniform', ctx=ast.Load()),
                args=[A, A],
                keywords=[ast.keyword(arg='min', value=A)],
            ),
            'uniform',
        ),
        (ast.Call(func=ast.Name(id='since', ctx=ast.Load()), args=[A], keywords=[]), 'since'),
        (ast.Call(func=ast.Name(id='sum', ctx=ast.Load()), args=[A], keywords=[]), 'sum'),
        (Terms(refs=[A]), 'Terms'),
        (EventRef(kind='trigger', key='s.e', ending=None, written='e'), 'EventRef'),
        (
            ast.Call(
                func=ast.Name(id='count', ctx=ast.Load()),
                args=[EventRef(kind='other', key='s.e', ending=None, written='e')],
                keywords=[],
            ),
            'other',
        ),
        (Problem(message='no such name'), 'no such name'),
        (ast.BinOp(left=A, op=ast.Add(), right=Problem(message='inner')), 'inner'),
    ],
)
def test_a_part_outside_the_notation_is_an_error_that_names_it(tree, named):
    with pytest.raises(ValueError) as raised:
        notation.build(resolved.of_tree(tree))
    assert named in str(raised.value)


def test_an_expression_with_a_problem_is_an_error():
    with pytest.raises(ValueError):
        notation.build(semantic.Expression('x +', resolved.problem('invalid expression'), ('s', 'f')))


def test_a_bare_number_or_yes_no_is_a_node():
    assert notation.build(semantic.Expression(3, None, ())) == Num(3)
    assert shape(notation.build(semantic.Expression(-2.5, None, ()))) == shape(Neg(Num(2.5)))
    assert notation.build(semantic.Expression(True, None, ())) == Text(True)
    with pytest.raises(ValueError):
        notation.build(semantic.Expression('text', None, ()))


def test_a_derivative_has_no_tree_and_its_latex_reads_back():
    with pytest.raises(ValueError):
        notation.to_node(Deriv('s.held'))
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
