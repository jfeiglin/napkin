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

The parts of a node are reached with a list and not with calls (re-audit 15), so a node of any height
has its values, as `evaluation` gives one instance its value (it writes the code of a deep node in
parts): the handler of each operation is a computation, a generator that yields each part that it
needs, with the instances that need it, is sent the part's value, and returns its own (`_Pass.value`).

What this module does with each operation is in `TABLE`, which `ops.handlers` checks when the module
is read.
"""

from __future__ import annotations

from copy import copy

import numpy as np
from scipy import special

from . import expr, ops
from .comparisons import Comparisons, UnresolvedScale, against
from .errors import ExpressionError
from .evaluation import value as scalar_value

NOT_FINITE = 'Expression produced a nonfinite or non-real value'
# What `_Pass.ready` gives for a part that needs a computation of its own.
_OPEN = object()


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

    def __init__(self, environment, registry, count, bindings, read_bound):
        self.read_bound = read_bound
        self.bindings = bindings
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

    def ready(self, node, chosen):
        """The value of a part that needs no computation of its own (a constant, a name, a part
        already computed for all the instances), else `_OPEN`."""
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
        return _OPEN

    def computation(self, node, chosen):
        """The computation of an operation for the chosen instances (see the module)."""
        name = ops.operation_of(node)
        if isinstance(node, expr.Call):
            if name not in TABLE:
                raise ExpressionError('Unsupported function or keyword arguments')
            if not ops.arity_holds(ops.OPERATIONS[name], len(node.args)):
                raise ExpressionError(f'Invalid argument count for {name}')
        return TABLE[name](self, node, chosen)

    def value(self, node, chosen):
        """The value of a node for the chosen instances. The computations that wait for a part are on
        an explicit stack, each with its node and its instances. No computation catches the failure
        of a part, so a failure ends the whole pass, at the part where a walk by calls would fail."""
        found = self.ready(node, chosen)
        if found is not _OPEN:
            return found
        stack = [(node, chosen, self.computation(node, chosen))]
        sent = None
        while True:
            part, instances, computation = stack[-1]
            try:
                asked, wanted = computation.send(sent)
            except StopIteration as done:
                stack.pop()
                sent = done.value
                if instances is None:
                    # The part is kept with its value: its place in memory names it while the pass lives.
                    self.kept[id(part)] = (part, sent)
                if not stack:
                    return sent
                continue
            sent = self.ready(asked, wanted)
            if sent is _OPEN:
                stack.append((asked, wanted, self.computation(asked, wanted)))
                sent = None

    def band(self, left, right, a, b, places):
        policy = self.registry.comparisons
        if self.bindings and policy.named is not None:
            key = (left, right, self.bound_names((left, right)))
            floors = policy.floors.get(key)
            if floors is None and places is None:
                try:
                    floors = np.array([self.row_policy(i).band_floor(left, right) for i in range(self.count)])
                except UnresolvedScale:
                    floors = _OPEN
                policy.floors[key] = floors
            if floors is None or floors is _OPEN:
                floor = [self.row_floor(left, right, i) for i in self.places(places)]
            else:
                floor = floors if places is None else floors[places]
        else:
            try:
                floor = policy.band_floor(left, right)
            except UnresolvedScale:
                floor = [self.row_floor(left, right, i) for i in self.places(places)]
        return np.maximum(floor, policy.factor * np.maximum(np.abs(a), np.abs(b)))

    def bound_names(self, nodes):
        if not self.bindings or self.registry.comparisons.named is None:
            return ()
        names = sorted(frozenset().union(*(expr.names(node) for node in nodes)))
        return tuple((name, self.bindings[name]) for name in names if name in self.bindings)

    def literal_rows(self, nodes, bound, places, evaluate):
        """Exact values or gaps of a template expression on rows that take this branch."""
        policy = self.registry.comparisons
        key = 'literal rows', nodes, policy.factor, bound
        if key not in policy.floors:
            policy.floors[key] = set(), {}
        checked, values = policy.floors[key]
        if checked is not None:
            for i in range(self.count) if places is None else places:
                if i not in checked:
                    found = evaluate(self.row_policy(i), *nodes)
                    if found is not None:
                        values[i] = found
                    checked.add(i)
            if len(checked) == self.count:
                policy.floors[key] = None, values
        return values

    def literal_sum(self, node, rounded, places):
        policy = self.registry.comparisons
        bound = self.bound_names((node,))
        if not bound:
            if isinstance(rounded, np.ndarray) and policy.named is not None:
                replacement = policy.rounded_literal(node)
                if replacement is not None:
                    return np.full(rounded.shape, replacement)
                return rounded
            return policy.literal_sum(node, rounded)
        values = self.literal_rows((node,), bound, places, Comparisons.literal_value)
        if not values:
            return rounded
        indices = self.places(places)
        result = np.broadcast_to(rounded, len(indices)).astype(float, copy=True)
        for j, i in enumerate(indices):
            if i in values:
                result[j] = float(values[i])
        return result

    def ordered(self, op, left, right, a, b, places):
        policy = self.registry.comparisons
        bound = self.bound_names((left, right))
        exact = policy.literal_gap(left, right, bindings=bool(bound))
        if exact is not None:
            return against(op, *exact)
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        with np.errstate(over='ignore'):
            gap = a - b
        band = self.band(left, right, a, b, places)
        result = against(op, gap, band)
        wide = np.isinf(gap) & np.isinf(band)
        if np.any(wide):
            # Only the rows whose gap and band both overflow need the scalar extended range.
            indices = self.places(places)
            av, bv, mask = (np.broadcast_to(v, len(indices)) for v in (a, b, wide))
            result = np.broadcast_to(result, len(indices)).copy()
            for j in np.flatnonzero(mask):
                policy, read = self.row_reader(indices[j])
                result[j] = policy.ordered(op, left, right, float(av[j]), float(bv[j]), read)
        if bound:
            # Template expressions share syntax; different rows may name different
            # exact formulas. Keep their rational gaps across evaluations.
            pairs = self.literal_rows((left, right), bound, places, Comparisons.literal_gap)
            if pairs:
                indices = self.places(places)
                result = np.broadcast_to(result, len(indices)).copy()
                for j, i in enumerate(indices):
                    if i in pairs:
                        result[j] = against(op, *pairs[i])
        return result

    def row_policy(self, i):
        policy = self.registry.comparisons
        if not self.bindings or policy.named is None:
            return policy

        def concrete(name):
            return self.bindings[name][i] if name in self.bindings else name

        return policy.for_row(self.registry, concrete)

    def row_reader(self, i):
        """The comparison policy and scalar reader bound to this row."""
        policy = self.row_policy(i)
        units = copy(self.registry)
        units.comparisons = policy
        row = _Row(self.environment, self.read_bound, i)
        return policy, lambda node: scalar_value(node, row, units)

    def row_floor(self, left, right, i):
        policy, read = self.row_reader(i)
        return policy.band_floor(left, right, read)

    def spread(self, value, chosen):
        """A value as an array over the chosen instances."""
        if isinstance(value, np.ndarray):
            return value
        return np.full(self.size(chosen), value)

    def truth(self, found, chosen):
        """A value of a yes/no for each chosen instance, as an array."""
        if isinstance(found, np.ndarray):
            return found.astype(bool)
        return np.full(self.size(chosen), bool(found))


class _Row:
    """One instance's values for a scale that depends on its chosen branch."""

    def __init__(self, environment, read_bound, index):
        self.environment, self.read_bound, self.index = environment, read_bound, index

    def __contains__(self, name):
        return name in self.environment or self.read_bound is not None

    def __getitem__(self, name):
        if name not in self.environment:
            return self.read_bound(name)
        values = self.environment[name]
        if isinstance(values, np.ndarray):
            entry = values[self.index]
            return entry.item() if isinstance(entry, np.generic) else entry
        return values


def _numbers(args, chosen):
    """The values of the parts `args` for the chosen instances, each checked as a value that
    arithmetic takes when it comes, before the next part is computed: a computation, for `yield from`."""
    found = []
    for arg in args:
        found.append(_number((yield arg, chosen)))
    return found


def _arithmetic(compute):
    def handler(run, node, chosen):
        left = _number((yield node.left, chosen))
        right = _number((yield node.right, chosen))
        if not isinstance(left, np.ndarray) and not isinstance(right, np.ndarray):
            try:
                result = _checked(compute(left, right))
            except (ZeroDivisionError, OverflowError, ValueError, TypeError) as exc:
                raise ExpressionError(str(exc)) from exc
        else:
            with np.errstate(all='ignore'):
                result = _checked(
                    np.asarray(compute(np.asarray(left, dtype=float), np.asarray(right, dtype=float)))
                )
        return run.literal_sum(node, result, chosen) if node.op in ('add', 'sub') else result

    return handler


def _power(run, node, chosen):
    left = _number((yield node.left, chosen))
    right = _number((yield node.right, chosen))
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
    found = _number((yield node.operand, chosen))
    return _checked(-found.astype(float) if isinstance(found, np.ndarray) else -found)


def _pos(run, node, chosen):
    return (yield node.operand, chosen)


def _not(run, node, chosen):
    found = yield node.operand, chosen
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
            still = run.narrowed(chosen, open_places)
            found = run.truth((yield term, still), still)
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
    left = run.spread((yield node.operands[0], chosen), chosen)
    for op, before, operand in zip(node.ops, node.operands, node.operands[1:]):
        if not len(open_places):
            break
        still = run.narrowed(chosen, open_places)
        right = run.spread((yield operand, still), still)
        if left.dtype.kind in 'iuf' and right.dtype.kind in 'iuf':
            holds = run.ordered(op, before, operand, left, right, still)
        else:
            holds = _ordered(op, left, right)
        holds = np.broadcast_to(holds, (len(open_places),))
        result[open_places[~holds]] = False
        open_places = open_places[holds]
        left = right[holds]
    if _reads_array(run, node.operands):
        return result
    return bool(result[0]) if size else True


def _choice(run, node, chosen):
    """A choice: for each instance, only the branch that its test takes."""
    test = yield node.test, chosen
    if not isinstance(test, np.ndarray):
        return _checked((yield (node.body if test else node.orelse), chosen))
    test = test.astype(bool)
    yes, no = run.narrowed(chosen, np.flatnonzero(test)), run.narrowed(chosen, np.flatnonzero(~test))
    taken = other = None
    if test.any():
        taken = run.spread((yield node.body, yes), yes)
    if (~test).any():
        other = run.spread((yield node.orelse, no), no)
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
        args = yield from _numbers(node.args, chosen)
        if not any(isinstance(arg, np.ndarray) for arg in args):
            return _checked((min if reduce is np.minimum else max)(args))
        found = np.asarray(args[0], dtype=float)
        for arg in args[1:]:
            found = reduce(found, arg)
        return _checked(np.broadcast_to(found, (run.size(chosen),)).copy())

    return handler


def _clip(run, node, chosen):
    value, low, high = yield from _numbers(node.args, chosen)
    if np.any(np.asarray(low) > np.asarray(high)):
        raise ExpressionError('clip lower bound exceeds upper bound')
    if not any(isinstance(arg, np.ndarray) for arg in (value, low, high)):
        return _checked(min(max(value, low), high))
    return _checked(np.minimum(np.maximum(value, low), high))


def _within(run, node, chosen):
    """`x in [lo, hi]` for each instance: its three values are read for every instance, as each
    instance by itself reads them, and a reversed interval of any instance fails the call."""
    value, low, high = yield from _numbers(node.args, chosen)
    x, lo, hi = node.args
    reversed_ = run.ordered('gt', lo, hi, low, high, chosen)
    if np.any(reversed_):
        k = int(np.flatnonzero(np.broadcast_to(reversed_, (run.size(chosen),)))[0])
        ends = [float(np.broadcast_to(end, (run.size(chosen),))[k]) for end in (low, high)]
        raise ExpressionError(f'{ops.REVERSED}: [{ends[0]!r}, {ends[1]!r}]')
    result = run.ordered('le', lo, x, low, value, chosen) & run.ordered('le', x, hi, value, high, chosen)
    return bool(result) if np.ndim(result) == 0 else result


def _of_one(compute):
    def handler(run, node, chosen):
        (value,) = yield from _numbers(node.args, chosen)
        with np.errstate(all='ignore'):
            found = compute(np.asarray(value, dtype=float))
        return _checked(found if isinstance(value, np.ndarray) else float(found))

    return handler


def _absolute(run, node, chosen):
    (value,) = yield from _numbers(node.args, chosen)
    return _checked(abs(value))


def _quantity(run, node, chosen):
    value = yield node.args[0], chosen
    unit = yield node.args[1], chosen
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
        return (yield node.args[0], chosen)
    total = _number((yield node.args[0], chosen))
    for arg in node.args[1:]:
        # The part is computed outside `errstate`, which no other computation may run under.
        part = _number((yield arg, chosen))
        with np.errstate(all='ignore'):
            total = _checked(total + part)
    return total


def _listed(conjunction):
    lazy = _lazy(conjunction)

    def handler(run, node, chosen):
        if len(node.args) == 1:
            return (yield node.args[0], chosen)
        return (yield from lazy(run, node, chosen, node.args))

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
        'within': _within,
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


def values(node, environment, registry, count, bindings=None, read_bound=None):
    """The value of a node for each of `count` instances: an array of `count` values, or one value when
    the node reads no array of the environment. Each failure is an ExpressionError."""
    return _Pass(environment, registry, count, bindings, read_bound).value(node, None)
