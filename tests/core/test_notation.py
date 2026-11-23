"""An expression in a message is written as the model writes it (the review of `2cd1751`, R11;
`scratch/rewrite/briefs/audit3b.md` at af5428b, agent V).

The rule (spec, "Limits on a runaway run": the diagnostic quotes the gate as the model writes it,
"waits at `until this.cleared`"; "Execution errors fail the run with the expression, invocation and
simulation time"; a quantity is a number and its unit, `2 L`): a message that quotes an expression
writes it in the model's notation (`expr.notation`): a quantity as its number and its unit, a yes/no
as `true` or `false`, a membership test as `x in [lo, hi]`, a member of an enum by its name and a
text in double quotes. The model's parser reads that text back as the same expression. A failure of
arithmetic is named in the language's words: a division by zero, a number outside the domain of its
function, a number too large to hold.

The rule test: random expressions of every kind of node, written and read back by the model's own
parser (`napkin/model/language/parse.py`); then each message of a run, a reader and a proof that
quotes an expression with a quantity in it: the `max_active` limit, a division by zero in a stage, a
formula that cannot be evaluated, a crossing that cannot be certified, a lag that a proof refuses, a
denominator that an interval does not keep from zero. No message holds the program's own call
`q(2, 'L')`, Python's `True`, `False` and `within(...)`, or Python's words for an arithmetic error.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from napkin.core import expr, intervals
from napkin.core.errors import ExpressionError
from napkin.engine.report import Lag, report
from napkin.engine.timeline import read, run
from napkin.model.compile import compile_text
from napkin.model.language import nodes as tree
from napkin.model.language.parse import parse_expression
from napkin.program.config import Limits
from napkin.program.record import Unavailable
from tests.core.reference import UNITS as CORE_UNITS

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
NAMES = ('x', 'crews', 'this.water', 'tank.level', 'plant.drain.actual_rate')
QUANTITIES = ('L', 'h', 'L/h', 'L*h')
NUMBERS = (0, 1, 2, 7, 0.5, 2.5, 1e-05, 1000000.0)
# What no message of the language holds: the program's call of a quantity, Python's constants and
# membership test, and Python's words for an arithmetic error.
PYTHON = ('q(', 'True', 'False', 'within(', 'float division', 'math domain', 'math range', 'ZeroDivision')
SYMBOLS = {'-': 'sub', '+': 'add', '*': 'mul', '/': 'div', '**': 'pow'}
SIGNS = {'-': 'neg', '+': 'pos', 'not': 'not'}
COMPARISONS = {'==': 'eq', '!=': 'ne', '<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge'}


def made(rng, depth):
    """A random node of the language: names, numbers, quantities, yes/no values, enum members and
    texts, signs, arithmetic, chains of comparisons, `and` and `or`, choices, calls and membership."""
    if depth == 0 or rng.random() < 0.2:
        kind = rng.choice(['name', 'number', 'quantity', 'quantity', 'bool', 'member', 'text'])
        if kind == 'name':
            return expr.ref(rng.choice(NAMES))
        if kind == 'number':
            return expr.const(rng.choice(NUMBERS))
        if kind == 'quantity':
            number = rng.choice(NUMBERS) * rng.choice([1, 1, -1])
            return expr.call('q', [expr.const(number), expr.const(rng.choice(QUANTITIES))])
        if kind == 'bool':
            return expr.const(rng.random() < 0.5)
        if kind == 'member':
            return expr.const(rng.choice(['FIXED', 'WAITING', 'DONE']))
        return expr.const(rng.choice(['A text', 'case[0]', 'done!']))
    kind = rng.choice(['unary', 'binary', 'binary', 'binary', 'compare', 'bool', 'if', 'call', 'within'])
    part = lambda: made(rng, depth - 1)  # noqa: E731
    if kind == 'unary':
        return expr.unary(rng.choice(['neg', 'pos', 'not']), part())
    if kind == 'binary':
        op = rng.choice(['add', 'sub', 'mul', 'div', 'pow'])
        right = expr.const(rng.choice([2, 3, 0.5])) if op == 'pow' else part()
        return expr.binary(op, part(), right)
    if kind == 'compare':
        # A chain of comparisons points one way, as in lo <= x < hi (the language's rule).
        if rng.random() < 0.7:
            return expr.compare([rng.choice(list(COMPARISONS.values()))], [part(), part()])
        way = rng.choice([('lt', 'le'), ('gt', 'ge')])
        return expr.compare([rng.choice(way), rng.choice(way)], [part(), part(), part()])
    if kind == 'bool':
        return expr.boolean(rng.choice(['and', 'or']), [part() for _ in range(rng.choice([2, 3]))])
    if kind == 'if':
        return expr.if_else(part(), part(), part())
    if kind == 'call':
        function = rng.choice(['min', 'max', 'abs', 'exp', 'ln', 'sqrt', 'clip'])
        count = {'abs': 1, 'exp': 1, 'ln': 1, 'sqrt': 1, 'clip': 3}.get(function, rng.choice([2, 3]))
        return expr.call(function, [part() for _ in range(count)])
    return expr.call('within', [part(), part(), part()])


def shape(node):
    """A node of the core as a comparable shape: a quantity as (number, unit), a sign of a number or
    of a quantity folded into it, the members of one `and` or `or` flattened."""
    if isinstance(node, expr.Ref):
        return ('name', node.name)
    if isinstance(node, expr.Const):
        value = node.value
        if isinstance(value, bool):
            return ('bool', value)
        if isinstance(value, str):
            return ('name', value) if value.isidentifier() and value[0].isupper() else ('text', value)
        return ('number', float(value))
    if isinstance(node, expr.Call) and node.function == 'q':
        return ('quantity', float(node.args[0].value), node.args[1].value)
    if isinstance(node, expr.Call) and node.function == 'within':
        return ('within', *map(shape, node.args))
    if isinstance(node, expr.Unary):
        inner = shape(node.operand)
        if node.op == 'neg' and inner[0] in ('number', 'quantity'):
            return (inner[0], -inner[1], *inner[2:])
        return ('unary', node.op, inner)
    if isinstance(node, expr.Binary):
        return ('binary', node.op, shape(node.left), shape(node.right))
    if isinstance(node, expr.Compare):
        return ('compare', tuple(node.ops), tuple(map(shape, node.operands)))
    if isinstance(node, expr.BoolOp):
        return ('bool', node.op, _flat(node.op, [shape(value) for value in node.values]))
    if isinstance(node, expr.IfElse):
        return ('if', shape(node.test), shape(node.body), shape(node.orelse))
    return ('call', node.function, tuple(map(shape, node.args)))


def read_shape(found):
    """A tree of the model's parser as the same comparable shape."""
    if isinstance(found, tree.Name):
        return ('name', found.name)
    if isinstance(found, tree.Member):
        return ('name', f'{read_shape(found.base)[1]}.{found.name}')
    if isinstance(found, tree.Bool):
        return ('bool', found.value)
    if isinstance(found, tree.Text):
        return ('text', found.value)
    if isinstance(found, tree.Number):
        return ('number', float(found.value))
    if isinstance(found, tree.Quantity):
        return ('quantity', float(found.value), ''.join(op + name for op, name in found.unit))
    if isinstance(found, tree.Within):
        return ('within', read_shape(found.value), read_shape(found.low), read_shape(found.high))
    if isinstance(found, tree.Unary):
        inner = read_shape(found.operand)
        if found.op == '-' and inner[0] in ('number', 'quantity'):
            return (inner[0], -inner[1], *inner[2:])
        return ('unary', SIGNS[found.op], inner)
    if isinstance(found, tree.Binary):
        return ('binary', SYMBOLS[found.op], read_shape(found.left), read_shape(found.right))
    if isinstance(found, tree.Compare):
        return ('compare', tuple(COMPARISONS[op] for op in found.ops), tuple(map(read_shape, found.operands)))
    if isinstance(found, tree.BoolOp):
        return ('bool', found.op, _flat(found.op, [read_shape(value) for value in found.values]))
    if isinstance(found, tree.IfElse):
        return ('if', read_shape(found.test), read_shape(found.body), read_shape(found.orelse))
    assert isinstance(found, tree.Call), found
    return ('call', found.function, tuple(map(read_shape, found.args)))


def _flat(op, values):
    """The members of an `and` or an `or`, with those of one of the same operator inside it."""
    found = []
    for value in values:
        found += list(value[2]) if value[:2] == ('bool', op) else [value]
    return tuple(found)


def python_in(message):
    """The parts of a message that are Python's own, which no message of the language holds."""
    return [part for part in PYTHON if part in message]


@pytest.mark.parametrize('seed', range(40))
def test_an_expression_is_written_as_the_model_writes_it_and_the_models_parser_reads_it_back(seed):
    rng = random.Random(seed)
    for _ in range(25):
        node = made(rng, 4)
        written = expr.notation(node)
        assert not python_in(written), written
        assert read_shape(parse_expression(written)) == shape(node), written


def test_a_quantity_is_its_number_and_its_unit_in_brackets_only_where_a_unit_would_run_on():
    """A unit runs on through `*` and `/` while the next factor is a bare name (D12): a quantity
    stands bare as a term, a comparand or an argument, and in brackets as a factor or a power."""
    two = expr.call('q', [expr.const(2), expr.const('L')])
    rate = expr.call('q', [expr.const(2), expr.const('L/h')])
    water, crews = expr.ref('this.water'), expr.ref('crews')
    assert expr.notation(expr.compare(['ge'], [water, two])) == 'this.water >= 2 L'
    assert (
        expr.notation(expr.binary('div', water, expr.binary('sub', water, two)))
        == 'this.water / (this.water - 2 L)'
    )
    assert expr.notation(expr.binary('mul', two, crews)) == '(2 L) * crews'
    assert expr.notation(expr.call('max', [rate, water])) == 'max(2 L/h, this.water)'
    assert expr.notation(expr.call('within', [water, two, rate])) == 'this.water in [2 L, 2 L/h]'
    assert (
        expr.notation(expr.boolean('and', [expr.const(True), expr.unary('not', expr.const(False))]))
        == 'true and not false'
    )
    assert (
        expr.notation(expr.compare(['eq'], [expr.ref('this.state'), expr.const('DONE')]))
        == 'this.state == DONE'
    )


ACTIVE = """\
scenario "Active"
    horizon 10 h

plant:
    water: L = 0 L
    inspect = event():
        when t >= 1 h:
            this.inspect.start()
            reset after 1 h
        until this.water >= 2 L
"""
DIVIDE = """\
scenario "Divide"
    horizon 2 h

plant:
    water: L = 2 L
    x = 0
    look = event():
        after 0.5 h:
            this.x = this.water / (this.water - 2 L)

plant.look.start()
"""
RATE = """\
scenario "Rate"
    horizon 4 h

tank:
    water: L = 8 L in [0,]
    flow drain: this.water -> SINK
        request = formula(this.water / (2 h))
    alarm = event():
        when this.drain.actual_rate <= 2 L/h:
            this.alarm.start()
            reset when false
"""
FORMULAS = """\
scenario "Formulas"
    horizon 2 h

tank:
    water: L = 2 L
    served: L = 0 L in [0 L,]
    flow fill: SOURCE -> this.served
        request = 1 L/h

ratio = formula(tank.water / (tank.water - 2 L))
logged = formula(ln(tank.water / (1 L) - 3))
grown = formula(exp(tank.water / (1 L) * 1000))
gap = formula(abs(tank.served - 5 L))
"""


def test_each_message_that_quotes_an_expression_writes_it_as_the_model_does():
    """The `max_active` limit, a division by zero in a stage, a crossing that cannot be certified,
    a formula that cannot be evaluated (its reason as the reader gives it), a lag that the proof
    refuses: each in the model's notation, each failure of arithmetic in the language's words."""
    c = compile_text(ACTIVE, UNITS)
    found = run(c.program, replace(c.configuration, limits=Limits(max_active=3))).failure.detail('message')
    assert 'waits at `until this.water >= 2 L` (step 1)' in found and not python_in(found), found
    c = compile_text(DIVIDE, UNITS)
    found = run(c.program, c.configuration).failure.detail('message')
    assert '`plant.water / (plant.water - 2 L)`: a division by zero' in found and not python_in(found), found
    c = compile_text(RATE, UNITS)
    found = run(c.program, c.configuration).failure.detail('message')
    assert 'the first contact of tank.drain.actual_rate <= 2 L/h cannot be certified' in found, found
    assert not python_in(found), found
    c = compile_text(FORMULAS, UNITS)
    record = run(c.program, c.configuration)
    ratio, logged, grown = (
        reading.values[0] for reading in read(record, c.program, ['ratio', 'logged', 'grown'], [1])
    )
    for value, words in (
        (ratio, '`tank.water / (tank.water - 2 L)`: a division by zero'),
        (logged, '`ln(tank.water / (1 L) - 3)`: a number outside the domain of its function'),
        (grown, '`exp(tank.water / (1 L) * 1000)`: a number too large to hold'),
    ):
        assert isinstance(value, Unavailable) and words in value.reason and not python_in(value.reason), value
    (gap,) = report(record, c.program, c.configuration, ['gap'], [1.5], {'gap': Lag(0.5, 1)}).values
    assert gap.lag is None and 'abs(tank.served - 5 L) can fall' in gap.note and not python_in(gap.note), (
        gap.note
    )


def test_a_denominator_that_an_interval_does_not_keep_from_zero_is_quoted_as_the_model_writes_it():
    node = expr.read("x / (y - q(2, 'h'))")
    with pytest.raises(ExpressionError) as error:
        intervals.prover({'x': (0.0, 1.0), 'y': (0.0, 4.0)}, CORE_UNITS)(node)
    assert 'Cannot prove nonzero denominator in `x / (y - 2 h)`' in str(error.value), error.value
    assert not python_in(str(error.value))
