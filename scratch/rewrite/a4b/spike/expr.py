"""The expressions of the spike: small nodes, evaluated for many rows at once.

The engine does not use these. It has `napkin/core/expr.py` and `core/arrays.py`. The spike needs
only three readings of an expression, and they are here:

- `ev(x, env)`: the value, for every row of an environment at once (numpy arrays or scalars);
- `names(x)`: what it reads, which gives the reader graph;
- `iv(x, ranges)`: an interval that holds its value, which gives the proofs.

A name is a text: `t`; `this.water` (a field or a store of the receiver); `this.depot.supply` (through
a link); `amount` (a parameter, a local or a local store of the occurrence); `pipe.request` (a
property of a flow of the occurrence). A reduction over a collection is a node of its own, as a
named part is in the program of the plan: `count_occ(event)`, `count_done(event)`,
`any_active(event)`, `newest(event, field)`, `since(event)`, `n_flows(store, side)`,
`sum_request(store, side)`, `actual(store, side)`.
"""

from __future__ import annotations

import math

import numpy as np


class X:
    __slots__ = ('args', 'op')

    def __init__(self, op, *args):
        self.op, self.args = op, args

    def __add__(self, other):
        return X('add', self, lift(other))

    def __radd__(self, other):
        return X('add', lift(other), self)

    def __sub__(self, other):
        return X('sub', self, lift(other))

    def __rsub__(self, other):
        return X('sub', lift(other), self)

    def __mul__(self, other):
        return X('mul', self, lift(other))

    def __rmul__(self, other):
        return X('mul', lift(other), self)

    def __truediv__(self, other):
        return X('div', self, lift(other))

    def __neg__(self):
        return X('neg', self)

    def __ge__(self, other):
        return X('ge', self, lift(other))

    def __le__(self, other):
        return X('le', self, lift(other))

    def __gt__(self, other):
        return X('gt', self, lift(other))

    def __lt__(self, other):
        return X('lt', self, lift(other))

    def __and__(self, other):
        return X('and', self, lift(other))

    def __or__(self, other):
        return X('or', self, lift(other))

    def __invert__(self):
        return X('not', self)

    def __repr__(self):
        return text(self)


def lift(value):
    return value if isinstance(value, X) else X('const', value)


def ref(name):
    return X('ref', name)


T = ref('t')


def least(a, b):
    return X('min', lift(a), lift(b))


def greatest(a, b):
    return X('max', lift(a), lift(b))


def choose(test, a, b):
    return X('if', lift(test), lift(a), lift(b))


def same(a, b):
    return X('eq', lift(a), lift(b))


# The reductions. `event` and `store` are paths from the reader: `this.deliver`, `this.depot.supply`.
def count_occ(event):
    return X('count_occ', event)


def count_done(event):
    return X('count_done', event)


def any_active(event):
    return X('any_active', event)


def newest(event, field):
    """`event.occurrences.at(t).field`: the field of the newest start."""
    return X('newest', event, field)


def since(event):
    return X('since', event)


def n_flows(store, side='out'):
    return X('n_flows', store, side)


def sum_request(store, side='out'):
    return X('sum_request', store, side)


def actual(store, side='out'):
    return X('actual', store, side)


def lookup(table, index):
    """`table[index]`: a column of numbers that the driver of a case gives."""
    return X('lookup', table, lift(index))


REDUCTIONS = ('count_occ', 'count_done', 'any_active', 'newest', 'since', 'n_flows', 'sum_request', 'actual')
BINARY = {
    'add': np.add,
    'sub': np.subtract,
    'mul': np.multiply,
    'div': np.divide,
    'min': np.minimum,
    'max': np.maximum,
    'ge': np.greater_equal,
    'le': np.less_equal,
    'gt': np.greater,
    'lt': np.less,
    'eq': np.equal,
    'and': np.logical_and,
    'or': np.logical_or,
}
PLAIN = {
    'add': lambda a, b: a + b,
    'sub': lambda a, b: a - b,
    'mul': lambda a, b: a * b,
    'div': lambda a, b: a / b,
    'min': min,
    'max': max,
    'ge': lambda a, b: a >= b,
    'le': lambda a, b: a <= b,
    'gt': lambda a, b: a > b,
    'lt': lambda a, b: a < b,
    'eq': lambda a, b: a == b,
    'and': lambda a, b: bool(a) and bool(b),
    'or': lambda a, b: bool(a) or bool(b),
}
SYMBOL = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'ge': '>=', 'le': '<=', 'gt': '>', 'lt': '<'}
SYMBOL |= {'eq': '==', 'and': 'and', 'or': 'or'}


def ev(x, env):
    """The value of x in an environment: `env.get(name)` and `env.reduce(node)` give scalars for one
    row, or arrays with one value for each row."""
    op, args = x.op, x.args
    if op == 'const':
        return args[0]
    if op == 'ref':
        return env.get(args[0])
    if op in BINARY:
        a, b = ev(args[0], env), ev(args[1], env)
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            return BINARY[op](a, b)
        return PLAIN[op](a, b)
    if op == 'neg':
        return -ev(args[0], env)
    if op == 'not':
        value = ev(args[0], env)
        return np.logical_not(value) if isinstance(value, np.ndarray) else not value
    if op == 'if':
        test, a, b = (ev(arg, env) for arg in args)
        if isinstance(test, np.ndarray):
            return np.where(test, a, b)
        return a if test else b
    if op == 'lookup':
        index = ev(args[1], env)
        return args[0][np.asarray(index, dtype=np.int64)] if isinstance(index, np.ndarray) else args[0][int(index)]
    return env.reduce(x)


def names(x, found=None):
    """The names that x reads: each `ref`, and each reduction as (op, path, ...)."""
    found = set() if found is None else found
    if x.op == 'ref':
        found.add(x.args[0])
    elif x.op in REDUCTIONS:
        found.add((x.op, *x.args))
    elif x.op == 'lookup':
        names(x.args[1], found)
    elif x.op != 'const':
        for arg in x.args:
            names(arg, found)
    return found


def conjuncts(x):
    if x.op == 'and':
        return [part for arg in x.args for part in conjuncts(arg)]
    return [x]


def text(x):
    op, args = x.op, x.args
    if op == 'const':
        return f'{args[0]:g}' if isinstance(args[0], float) else str(args[0])
    if op == 'ref':
        return args[0]
    if op in SYMBOL:
        return f'({text(args[0])} {SYMBOL[op]} {text(args[1])})'
    if op in REDUCTIONS:
        return f'{op}({", ".join(str(arg) for arg in args)})'
    if op == 'lookup':
        return f'table[{text(args[1])}]'
    return f'{op}({", ".join(text(arg) for arg in args)})'


def iv(x, ranges):
    """(low, high) of x when each name is in its range. A name with no range is anywhere."""
    op, args = x.op, x.args
    inf = math.inf
    if op == 'const':
        value = float(args[0])
        return value, value
    if op == 'ref':
        return ranges.get(args[0], (-inf, inf))
    if op in REDUCTIONS:
        return ranges.get((op, *args), (0.0, inf) if op != 'newest' else (-inf, inf))
    if op == 'lookup':
        return float(np.min(args[0])), float(np.max(args[0]))
    if op == 'neg':
        low, high = iv(args[0], ranges)
        return -high, -low
    if op in ('ge', 'le', 'gt', 'lt', 'eq', 'and', 'or', 'not'):
        return 0.0, 1.0
    if op == 'if':
        a, b = iv(args[1], ranges), iv(args[2], ranges)
        return min(a[0], b[0]), max(a[1], b[1])
    (a, b), (c, d) = iv(args[0], ranges), iv(args[1], ranges)
    if op == 'add':
        return a + c, b + d
    if op == 'sub':
        return a - d, b - c
    if op == 'min':
        return min(a, c), min(b, d)
    if op == 'max':
        return max(a, c), max(b, d)
    if op == 'mul':
        products = [p * q if (p != 0 and q != 0) else 0.0 for p in (a, b) for q in (c, d)]
        return min(products), max(products)
    if op == 'div':
        if c <= 0 <= d:
            return -inf, inf
        quotients = [p / q for p in (a, b) for q in (c, d)]
        return min(quotients), max(quotients)
    raise ValueError(f'no interval for {op}')
