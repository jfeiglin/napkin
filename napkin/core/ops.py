"""The contract of each operation of an expression: what holds of it for every consumer.

An operation of `expr` (a unary or a binary operator, a comparison, `and`, `or`, a choice, a function
of the language) has one `Operation` here, with what no consumer may decide for itself:

- `arity`: the number of its arguments (None: one or more);
- `units`: its rule for units, one of `UNIT_RULES`;
- `domain`: where it has a value;
- `kinks`: where it is not smooth, so that its derivative there is one-sided or has no meaning;
- `partials`: its partial derivative by each argument where it is smooth, as nodes of `expr` made from
  the nodes of its arguments (None for an argument, or for the operation, that has no derivative of
  its own: a condition);
- `monotone`: how its value moves with each argument while the others stay: `+` it never falls when
  the argument rises, `-` it never rises, `none` it can do both. `sign`: it is one of the two while
  the argument stays on one side of zero, and which one follows from the other arguments (the sign
  of a factor, of a dividend, of a divisor and of an exponent; for `pow` by its exponent, whether
  the base is above 1). For `pow` this holds for a base above zero.
- `active`: for an operation with kinks, what it is on a part where each argument stays in an
  interval. It reads `ranges[i]`, the interval of argument `i` (of a yes/no argument, the interval of
  `1 if it holds else 0`). It gives `(i, s)` where the operation is `s` times argument `i`, `ITSELF`
  where the operation is smooth, and None where the intervals cannot show one of the two. None for an
  operation with no kinks, and for a yes/no.

What a consumer does with an operation (how it evaluates it, which code it writes for it, how it draws
it) is with that consumer, in a table from the name of the operation to its handler. `handlers` checks
such a table: a consumer has a handler for each operation, or says for which ones it has none. So a
new operation cannot be half supported in silence.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from . import expr

# The rules for units.
UNIT_RULES = {
    'number': 'The argument is a number in any unit, and the result has that unit.',
    'condition': 'Each argument is a yes/no, and so is the result.',
    'compared': 'The arguments have one unit, of any kind for `eq` and `ne` and numbers for an order; '
    'the result is a yes/no.',
    'choice': 'The test is a yes/no; the two branches have one unit, which the result has.',
    'same': 'The arguments are numbers of one unit, and the result has that unit. A plain zero has '
    'every unit.',
    'product': 'The arguments are numbers; the result has the product of their units.',
    'quotient': 'The arguments are numbers; the result has the quotient of their units.',
    'power': 'The exponent is a plain number. A base with a unit needs an exponent that is a written '
    'number of at most 1024 in size, and the result has the unit of the base to that power; '
    'else the result is a plain number.',
    'root': 'The argument is a number, and the result has its unit to the power one half.',
    'plain': 'The argument is a plain number, and so is the result.',
    'literal': 'The first argument is a plain number, and the second the written name of a unit of '
    'the registry; the result has that unit.',
    'membership': 'The tested value and the two ends of its interval are numbers of one unit; the result '
    'is a yes/no.',
}

# The failure of a membership whose interval is reversed (spec: reversed bounds are an error), in every
# evaluator of the program: the function of a node, a program, the values of many instances.
REVERSED = 'the interval of a membership test is reversed'


@dataclass(frozen=True)
class Operation:
    name: str
    arity: int | None
    units: str
    domain: str
    kinks: str
    partials: Callable | None
    monotone: tuple
    active: Callable | None = None


# What `Operation.active` gives where the operation is smooth as it is.
ITSELF = 'itself'


def _c(value):
    return expr.const(value)


def _neg(x):
    return expr.unary('neg', x)


def _op(name, x, y):
    return expr.binary(name, x, y)


def _when(test, yes, no):
    return expr.if_else(test, _c(yes), _c(no))


def _first_extreme(strict, loose):
    """The partials of `min` or `max`: 1 for the argument that gives the value (the first of equal
    ones, as Python's `min` and `max` give it), 0 for each other."""

    def partials(*args):
        found = []
        for i, x in enumerate(args):
            tests = [expr.compare([strict], [x, y]) for y in args[:i]]
            tests += [expr.compare([loose], [x, y]) for y in args[i + 1 :]]
            if not tests:
                found.append(_c(1))
            else:
                found.append(_when(tests[0] if len(tests) == 1 else expr.boolean('and', tests), 1, 0))
        return tuple(found)

    return partials


def _clip_partials(x, low, high):
    inside = expr.compare(['lt', 'lt'], [low, x, high])
    return (
        _when(inside, 1, 0),
        _when(expr.compare(['le'], [x, low]), 1, 0),
        _when(expr.compare(['ge'], [x, high]), 1, 0),
    )


def _active_extreme(least):
    """`Operation.active` of `min` (least) or `max`: the argument that is not above (not below) each
    other argument on the whole part."""

    def active(ranges):
        for i in range(len(ranges)):
            others = (ranges[j] for j in range(len(ranges)) if j != i)
            if all(ranges[i][1] <= other[0] if least else ranges[i][0] >= other[1] for other in others):
                return i, 1
        return None

    return active


def _active_clip(ranges):
    x, low, high = ranges
    if low[1] <= x[0] and x[1] <= high[0]:
        return 0, 1
    if low[1] <= high[0]:
        if x[1] <= low[0]:
            return 1, 1
        if x[0] >= high[1]:
            return 2, 1
    return None


def _active_power(ranges):
    # A power is smooth for a base above zero; a whole exponent that is not below zero makes a polynomial.
    exponent = ranges[1]
    whole = exponent[0] == exponent[1] and float(exponent[0]).is_integer() and exponent[0] >= 0
    return ITSELF if whole or ranges[0][0] > 0 else None


SMOOTH = 'It is smooth where it has a value.'
STEP = 'Its value is a yes/no: it steps where its arguments make it change, and is flat elsewhere.'
ALL = 'It has a value for all finite arguments whose result is finite.'

OPERATIONS = {
    op.name: op
    for op in (
        Operation('neg', 1, 'number', ALL, SMOOTH, lambda x: (_c(-1),), ('-',)),
        Operation('pos', 1, 'number', ALL, SMOOTH, lambda x: (_c(1),), ('+',)),
        Operation('not', 1, 'condition', 'It has a value for a yes/no.', STEP, None, ('-',)),
        Operation('and', None, 'condition', 'It has a value for yes/no arguments.', STEP, None, ('+',)),
        Operation('or', None, 'condition', 'It has a value for yes/no arguments.', STEP, None, ('+',)),
        Operation('eq', 2, 'compared', ALL, STEP, None, ('none', 'none')),
        Operation('ne', 2, 'compared', ALL, STEP, None, ('none', 'none')),
        Operation('lt', 2, 'compared', ALL, STEP, None, ('-', '+')),
        Operation('le', 2, 'compared', ALL, STEP, None, ('-', '+')),
        Operation('gt', 2, 'compared', ALL, STEP, None, ('+', '-')),
        Operation('ge', 2, 'compared', ALL, STEP, None, ('+', '-')),
        Operation(
            'if',
            3,
            'choice',
            'It has the value of the branch that the test takes; the other branch is not asked.',
            'It is not smooth where the test changes, unless the two branches meet there.',
            lambda test, body, orelse: (None, _when(test, 1, 0), _when(test, 0, 1)),
            ('none', '+', '+'),
            lambda ranges: (1, 1) if ranges[0][0] > 0 else (2, 1) if ranges[0][1] < 1 else None,
        ),
        Operation('add', 2, 'same', ALL, SMOOTH, lambda x, y: (_c(1), _c(1)), ('+', '+')),
        Operation('sub', 2, 'same', ALL, SMOOTH, lambda x, y: (_c(1), _c(-1)), ('+', '-')),
        Operation('mul', 2, 'product', ALL, SMOOTH, lambda x, y: (y, x), ('sign', 'sign')),
        Operation(
            'div',
            2,
            'quotient',
            'The divisor is not zero.',
            SMOOTH,
            lambda x, y: (_op('div', _c(1), y), _neg(_op('div', x, _op('mul', y, y)))),
            ('sign', 'sign'),
        ),
        Operation(
            'pow',
            2,
            'power',
            'The exponent is at most 1024 in size. A base below zero needs a whole exponent, and a '
            'base of zero an exponent that is not below zero.',
            'It is smooth for a base above zero. By the exponent it has a derivative only there.',
            lambda x, y: (
                _op('mul', y, _op('pow', x, _op('sub', y, _c(1)))),
                _op('mul', _op('pow', x, y), expr.call('ln', [x])),
            ),
            ('sign', 'sign'),
            _active_power,
        ),
        Operation(
            'min',
            None,
            'same',
            ALL,
            'It is not smooth where its two least arguments are equal.',
            _first_extreme('lt', 'le'),
            ('+',),
            _active_extreme(True),
        ),
        Operation(
            'max',
            None,
            'same',
            ALL,
            'It is not smooth where its two largest arguments are equal.',
            _first_extreme('gt', 'ge'),
            ('+',),
            _active_extreme(False),
        ),
        Operation('sum', None, 'same', ALL, SMOOTH, lambda *args: tuple(_c(1) for _ in args), ('+',)),
        Operation('any', None, 'condition', 'It has a value for yes/no arguments.', STEP, None, ('+',)),
        Operation('all', None, 'condition', 'It has a value for yes/no arguments.', STEP, None, ('+',)),
        Operation(
            'clip',
            3,
            'same',
            'The lower bound is not above the upper bound.',
            'It is not smooth where the value is at a bound.',
            _clip_partials,
            ('+', '+', '+'),
            _active_clip,
        ),
        # `x in [lo, hi]`: x is read once, and the ends are checked each time the membership is
        # evaluated, so an interval that only a run reverses fails where the run reads it.
        Operation(
            'within',
            3,
            'membership',
            'The lower end of the interval is not above its upper end.',
            STEP,
            None,
            ('none', '-', '+'),
        ),
        Operation(
            'abs',
            1,
            'number',
            ALL,
            'It is not smooth at zero.',
            lambda x: (_when(expr.compare(['gt'], [x, _c(0)]), 1, -1),),
            ('none',),
            lambda ranges: (0, 1) if ranges[0][0] >= 0 else (0, -1) if ranges[0][1] <= 0 else None,
        ),
        Operation(
            'sqrt',
            1,
            'root',
            'The argument is not below zero.',
            'It is smooth above zero; at zero its slope has no limit.',
            lambda x: (_op('div', _c(1), _op('mul', _c(2), expr.call('sqrt', [x]))),),
            ('+',),
            lambda ranges: ITSELF if ranges[0][0] > 0 else None,
        ),
        Operation('exp', 1, 'plain', ALL, SMOOTH, lambda x: (expr.call('exp', [x]),), ('+',)),
        Operation('expm1', 1, 'plain', ALL, SMOOTH, lambda x: (expr.call('exp', [x]),), ('+',)),
        Operation(
            'ln', 1, 'plain', 'The argument is above zero.', SMOOTH, lambda x: (_op('div', _c(1), x),), ('+',)
        ),
        Operation(
            'log1p',
            1,
            'plain',
            'The argument is above -1.',
            SMOOTH,
            lambda x: (_op('div', _c(1), _op('add', _c(1), x)),),
            ('+',),
        ),
        Operation(
            'erf',
            1,
            'plain',
            ALL,
            SMOOTH,
            lambda x: (_op('mul', _c(2 / math.sqrt(math.pi)), expr.call('exp', [_neg(_op('mul', x, x))])),),
            ('+',),
        ),
        Operation(
            'q',
            2,
            'literal',
            'The unit is in the registry, and the number in that unit is finite.',
            SMOOTH,
            lambda value, unit: (expr.call('q', [_c(1), unit]), None),
            ('+', 'none'),
        ),
    )
}


def operation_of(node):
    """The name of the operation of a node, or None for a constant, a reference and a part that is
    outside the language. A chain of comparisons has one operation for each link: this gives the
    first, and `node.ops` has them all."""
    if isinstance(node, (expr.Unary, expr.Binary, expr.BoolOp)):
        return node.op
    if isinstance(node, expr.Compare):
        return node.ops[0]
    if isinstance(node, expr.IfElse):
        return 'if'
    if isinstance(node, expr.Call):
        return node.function
    return None


def arity_holds(operation, count):
    """Whether an operation takes `count` arguments."""
    return count >= 1 if operation.arity is None else count == operation.arity


def handlers(consumer, table, unsupported=()):
    """The table of a consumer, checked: `table` has one handler for each operation, but for those
    that the consumer names in `unsupported`, and nothing else. A table that lacks an operation, or
    names one that the language does not have, raises LookupError with the names."""
    table, unsupported = dict(table), set(unsupported)
    missing = sorted(OPERATIONS.keys() - table.keys() - unsupported)
    unknown = sorted((table.keys() | unsupported) - OPERATIONS.keys())
    both = sorted(table.keys() & unsupported)
    problems = []
    if missing:
        problems.append(f'no handler for {", ".join(missing)}')
    if unknown:
        problems.append(f'no such operation: {", ".join(unknown)}')
    if both:
        problems.append(f'a handler and no handler for {", ".join(both)}')
    if problems:
        raise LookupError(f'{consumer}: ' + '; '.join(problems))
    return table
