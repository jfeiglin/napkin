"""The values of an expression for many instances at once.

`values(node, environment, registry, count)` gives the value of a node for each of `count` instances
in one pass. A name of the environment has one value for all instances (a number, a yes/no, a text) or
an array with one value for each. The result is an array of `count` values, or one value when the
node reads no array.

The meaning is that of `evaluation.value` for each instance by itself:

- a part that gives a number is checked: each number is finite and real;
- a choice computes, for each instance, only the branch that its test takes; `and` and `or` stop,
  for each instance, at the term that decides; a chain of comparisons stops at the first link that
  fails. So a branch that would fail for an instance that does not take it is no failure;
- when the computation of one instance fails, the whole call fails with an ExpressionError, as a loop
  over the instances fails at the first of them.

What differs from the value of one instance: a number of an array is a float, also where one instance
by itself gives a whole number; and `exp`, `expm1`, `ln`, `log1p`, `sqrt`, `erf` and a power are those
of numpy and SciPy, which can differ from Python's by a rounding of the last place. Sums, differences,
products and quotients are the same bit for bit.

What this module does with each operation is in `TABLE`, which `ops.handlers` checks when the module
is read.
"""

from __future__ import annotations

import numpy as np
from scipy import special

from . import expr, ops
from .errors import ExpressionError

NOT_FINITE = 'Expression produced a nonfinite or non-real value'


def _checked(value):
    """A number, or an array of numbers, that passes the check of a value: finite and real."""
    if isinstance(value, np.ndarray):
        if value.dtype.kind == 'f':
            if not np.isfinite(value).all():
                raise ExpressionError(NOT_FINITE)
        elif value.dtype.kind == 'c':
            raise ExpressionError(NOT_FINITE)
        return value
    if isinstance(value, complex) or (
        isinstance(value, (float, int)) and not isinstance(value, bool) and not np.isfinite(value)
    ):
        raise ExpressionError(NOT_FINITE)
    return value


def _number(value):
    """A value that arithmetic takes: a number, or an array of numbers or of yes/no."""
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in 'fiub':
            raise ExpressionError('Arithmetic needs numbers')
        return value
    if isinstance(value, str) or value is None:
        raise ExpressionError('Arithmetic needs numbers')
    return value


class _Pass:
    """One pass over a node for the instances `chosen` (None: all of them; else their places)."""

    def __init__(self, environment, registry, count):
        self.environment, self.registry, self.count = environment, registry, count
        # The value of each part for all instances, by the part. An expression can hold one part in
        # many places (a formula that is written in the place of its name, in each expression that
        # reads it): the part is computed once in a pass, so the cost of a pass grows with the
        # number of different parts, not with the number of places. No part changes a value that it
        # is given, so the kept value is the value.
        self.kept = {}

    def size(self, chosen):
        return self.count if chosen is None else len(chosen)

    def places(self, chosen):
        return np.arange(self.count) if chosen is None else chosen

    def narrowed(self, chosen, places):
        """The instances at `places` (in their order, each once) of the chosen ones: the chosen ones
        themselves when `places` are all of them, so that a part read for all instances is known as
        that."""
        if len(places) == self.size(chosen):
            return chosen
        return self.places(chosen)[places]

    def value(self, node, chosen):
        if isinstance(node, expr.Const):
            return _checked(node.value)
        if isinstance(node, expr.Ref):
            if node.name not in self.environment:
                raise ExpressionError(f'Missing value for {node.name!r}')
            found = self.environment[node.name]
            if isinstance(found, np.ndarray):
                found = found if chosen is None else found[chosen]
            return _checked(found)
        if isinstance(node, expr.Foreign):
            raise ExpressionError('Unsupported expression')
        if chosen is None:
            kept = self.kept.get(id(node))
            if kept is not None:
                return kept[1]
        name = ops.operation_of(node)
        if isinstance(node, expr.Call):
            if name not in TABLE:
                raise ExpressionError('Unsupported function or keyword arguments')
            if not ops.arity_holds(ops.OPERATIONS[name], len(node.args)):
                raise ExpressionError(f'Invalid argument count for {name}')
        found = TABLE[name](self, node, chosen)
        if chosen is None:
            # The node is kept with its value: its place in memory names it while the pass lives.
            self.kept[id(node)] = (node, found)
        return found

    def spread(self, value, chosen):
        """A value as an array over the chosen instances."""
        if isinstance(value, np.ndarray):
            return value
        return np.full(self.size(chosen), value)

    def truth(self, node, chosen):
        """The yes/no of a node for each chosen instance, as an array."""
        found = self.value(node, chosen)
        if isinstance(found, np.ndarray):
            return found.astype(bool)
        return np.full(self.size(chosen), bool(found))


def _arithmetic(compute):
    def handler(run, node, chosen):
        left = _number(run.value(node.left, chosen))
        right = _number(run.value(node.right, chosen))
        if not isinstance(left, np.ndarray) and not isinstance(right, np.ndarray):
            try:
                return _checked(compute(left, right))
            except (ZeroDivisionError, OverflowError, ValueError, TypeError) as exc:
                raise ExpressionError(str(exc)) from exc
        with np.errstate(all='ignore'):
            return _checked(
                np.asarray(compute(np.asarray(left, dtype=float), np.asarray(right, dtype=float)))
            )

    return handler


def _power(run, node, chosen):
    left = _number(run.value(node.left, chosen))
    right = _number(run.value(node.right, chosen))
    if np.any(np.abs(right) > 1024):
        raise ExpressionError('Exponent exceeds supported magnitude 1024')
    if not isinstance(left, np.ndarray) and not isinstance(right, np.ndarray):
        try:
            return _checked(float(left) ** right)
        except (ZeroDivisionError, OverflowError, ValueError, TypeError) as exc:
            raise ExpressionError(str(exc)) from exc
    with np.errstate(all='ignore'):
        return _checked(np.power(np.asarray(left, dtype=float), right))


def _neg(run, node, chosen):
    found = _number(run.value(node.operand, chosen))
    return _checked(-found.astype(float) if isinstance(found, np.ndarray) else -found)


def _pos(run, node, chosen):
    return run.value(node.operand, chosen)


def _not(run, node, chosen):
    found = run.value(node.operand, chosen)
    return ~found.astype(bool) if isinstance(found, np.ndarray) else (not found)


def _lazy(conjunction):
    """`and` (`conjunction`) or `or` of the terms `node.values`, or of the arguments of `all` or `any`:
    for each instance, the terms are read until one decides."""

    def handler(run, node, chosen, terms=None):
        terms = node.values if terms is None else terms
        result = np.full(run.size(chosen), conjunction)
        open_places = np.arange(run.size(chosen))
        for term in terms:
            if not len(open_places):
                break
            found = run.truth(term, run.narrowed(chosen, open_places))
            decided = ~found if conjunction else found
            result[open_places[decided]] = not conjunction
            open_places = open_places[~decided]
        if _reads_array(run, terms):
            return result
        return bool(result[0]) if len(result) else conjunction

    return handler


def _reads_array(run, terms):
    return any(
        isinstance(run.environment.get(name), np.ndarray) for term in terms for name in expr.names(term)
    )


COMPARISONS = {
    'eq': lambda a, b: a == b,
    'ne': lambda a, b: a != b,
    'lt': lambda a, b: a < b,
    'le': lambda a, b: a <= b,
    'gt': lambda a, b: a > b,
    'ge': lambda a, b: a >= b,
}


def _ordered(op, left, right):
    """The comparison of two values for each instance, as Python compares them: two numbers, or two
    texts. A text and a number are never equal, and have no order."""
    texts = [
        value.dtype.kind in 'USO' if isinstance(value, np.ndarray) else isinstance(value, str)
        for value in (left, right)
    ]
    if texts[0] != texts[1]:
        if op not in ('eq', 'ne'):
            raise ExpressionError('A text and a number have no order')
        return np.asarray(op == 'ne')
    try:
        return np.asarray(COMPARISONS[op](left, right)).astype(bool)
    except TypeError as exc:
        raise ExpressionError(str(exc)) from exc


def _chain(run, node, chosen):
    """A chain of comparisons: for each instance, the links are read until one fails."""
    size = run.size(chosen)
    result = np.ones(size, dtype=bool)
    open_places = np.arange(size)
    left = run.spread(run.value(node.operands[0], chosen), chosen)
    for op, operand in zip(node.ops, node.operands[1:]):
        if not len(open_places):
            break
        still = run.narrowed(chosen, open_places)
        right = run.spread(run.value(operand, still), still)
        holds = np.broadcast_to(_ordered(op, left, right), (len(open_places),))
        result[open_places[~holds]] = False
        open_places = open_places[holds]
        left = right[holds]
    if _reads_array(run, node.operands):
        return result
    return bool(result[0]) if size else True


def _choice(run, node, chosen):
    """A choice: for each instance, only the branch that its test takes."""
    test = run.value(node.test, chosen)
    if not isinstance(test, np.ndarray):
        return _checked(run.value(node.body if test else node.orelse, chosen))
    test = test.astype(bool)
    yes, no = run.narrowed(chosen, np.flatnonzero(test)), run.narrowed(chosen, np.flatnonzero(~test))
    taken = run.spread(run.value(node.body, yes), yes) if test.any() else None
    other = run.spread(run.value(node.orelse, no), no) if (~test).any() else None
    kinds = [part.dtype for part in (taken, other) if part is not None]
    if any(kind.kind in 'USO' for kind in kinds) and not all(kind.kind in 'USO' for kind in kinds):
        result = np.empty(len(test), dtype=object)
    else:
        result = np.empty(len(test), dtype=np.result_type(*kinds))
    if taken is not None:
        result[test] = taken
    if other is not None:
        result[~test] = other
    return _checked(result)


def _extreme(reduce):
    def handler(run, node, chosen):
        args = [_number(run.value(arg, chosen)) for arg in node.args]
        if not any(isinstance(arg, np.ndarray) for arg in args):
            return _checked((min if reduce is np.minimum else max)(args))
        found = np.asarray(args[0], dtype=float)
        for arg in args[1:]:
            found = reduce(found, arg)
        return _checked(np.broadcast_to(found, (run.size(chosen),)).copy())

    return handler


def _clip(run, node, chosen):
    value, low, high = (_number(run.value(arg, chosen)) for arg in node.args)
    if np.any(np.asarray(low) > np.asarray(high)):
        raise ExpressionError('clip lower bound exceeds upper bound')
    if not any(isinstance(arg, np.ndarray) for arg in (value, low, high)):
        return _checked(min(max(value, low), high))
    return _checked(np.minimum(np.maximum(value, low), high))


def _of_one(compute):
    def handler(run, node, chosen):
        (value,) = (_number(run.value(arg, chosen)) for arg in node.args)
        with np.errstate(all='ignore'):
            found = compute(np.asarray(value, dtype=float))
        return _checked(found if isinstance(value, np.ndarray) else float(found))

    return handler


def _absolute(run, node, chosen):
    (value,) = (_number(run.value(arg, chosen)) for arg in node.args)
    return _checked(abs(value))


def _quantity(run, node, chosen):
    value, unit = (run.value(arg, chosen) for arg in node.args)
    if not isinstance(unit, str):
        raise ExpressionError('The unit of a quantity is a written name')
    if not isinstance(value, np.ndarray):
        return run.registry.normalize(value, unit)
    if value.dtype.kind not in 'fiu':
        # A yes/no is no quantity, as for one instance.
        raise ExpressionError(f'Expected a finite quantity in {unit}')
    scale = run.registry.parse_unit(unit).scale
    with np.errstate(all='ignore'):
        found = _checked(value.astype(float)) * scale
    if not np.isfinite(found).all():
        raise ExpressionError('Unit conversion overflow')
    return found


def _sum(run, node, chosen):
    """The members added from the left, each sum of two checked. One member is that member."""
    if len(node.args) == 1:
        return run.value(node.args[0], chosen)
    total = _number(run.value(node.args[0], chosen))
    for arg in node.args[1:]:
        with np.errstate(all='ignore'):
            total = _checked(total + _number(run.value(arg, chosen)))
    return total


def _listed(conjunction):
    lazy = _lazy(conjunction)

    def handler(run, node, chosen):
        if len(node.args) == 1:
            return run.value(node.args[0], chosen)
        return lazy(run, node, chosen, node.args)

    return handler


TABLE = ops.handlers(
    'the values of an expression for many instances',
    {
        'neg': _neg,
        'pos': _pos,
        'not': _not,
        'and': _lazy(True),
        'or': _lazy(False),
        **dict.fromkeys(COMPARISONS, _chain),
        'if': _choice,
        'add': _arithmetic(lambda a, b: a + b),
        'sub': _arithmetic(lambda a, b: a - b),
        'mul': _arithmetic(lambda a, b: a * b),
        'div': _arithmetic(lambda a, b: a / b),
        'pow': _power,
        'min': _extreme(np.minimum),
        'max': _extreme(np.maximum),
        'sum': _sum,
        'any': _listed(False),
        'all': _listed(True),
        'clip': _clip,
        'abs': _absolute,
        'sqrt': _of_one(np.sqrt),
        'exp': _of_one(np.exp),
        'expm1': _of_one(np.expm1),
        'ln': _of_one(np.log),
        'log1p': _of_one(np.log1p),
        'erf': _of_one(special.erf),
        'q': _quantity,
    },
)


def values(node, environment, registry, count):
    """The value of a node for each of `count` instances: an array of `count` values, or one value when
    the node reads no array of the environment. Each failure is an ExpressionError."""
    return _Pass(environment, registry, count).value(node, None)
