"""Intervals: the range of an expression over the ranges of its names, with the proof that it has a
value everywhere in them.

`prover(ranges, registry, aliases)` gives a function of one node: its closed interval, or an
`ExpressionError` when a part cannot be shown to have a value (a divisor that can be zero, a logarithm
of a number that can be zero or less, a root of a number that can be negative, an exponential that can
leave the floating-point range). The proof is conservative: what it cannot show, it rejects. It does
not sample.

- `ranges` gives the closed interval of a name, in execution units. A name with no range and no
  formula can be any number.
- `aliases` gives the node of the formula of a name. The interval of such a name is the interval of
  its formula.
- A condition narrows the branch that it guards: in `x / y if y > 0 else 0` the divisor is above zero.
  A comparison of a name, or of any expression, with a value that is fixed in the branch narrows that
  name or that expression; `!= 0` is kept as a fact of its own.

The interval of a formula is kept for the facts of the branch that its names read, directly or through
other formulas, so a formula that many others read is proved once for each such set of facts, and not
once for each path to it. A formula on a circle of formulas is proved again each time, because its
interval depends on the path.

What this module does with each operation is in `TABLE`, checked against the contracts (`ops.handlers`)
when the module is read.
"""

from __future__ import annotations

import ast
import copy
import itertools
import math
from collections import ChainMap

from . import evaluation, expr, ops
from .errors import ExpressionError

# Marks in a context: some narrowed interval has no value; a condition narrows an expression that is
# no name; the names and the expressions that are known not to be zero.
EMPTY = '__empty__'
GUARDED = '__guarded__'
NONZERO = '__nonzero__'
# A comparison with its sides swapped (`0 < x` is `x > 0`), and the comparison that holds when one fails.
MIRRORED = {'lt': 'gt', 'le': 'ge', 'gt': 'lt', 'ge': 'le', 'eq': 'eq', 'ne': 'ne'}
OPPOSITE = {'gt': 'le', 'ge': 'lt', 'lt': 'ge', 'le': 'gt', 'eq': 'ne', 'ne': 'eq'}
WHOLE = (-math.inf, math.inf)
LARGEST = float.fromhex('0x1.fffffffffffffp+1023')


def _key(node):
    """What a context holds a narrowed interval by: the name of a reference, else the node."""
    return node.name if isinstance(node, expr.Ref) else node


def _written(key):
    return key if isinstance(key, str) else expr.text(key)


# How many answers the provers of the same formulas keep together, and how many marks.
KEPT = 200_000


class _Kept:
    """What the provers of the same formulas keep together, whatever their ranges.

    `found` holds what a prover gave: of a formula, by its mark and the facts of the branch; of an
    expression that it was asked, by its mark. A mark is a number that stands for everything that
    the answer depends on apart from the facts of a branch: the formula or the expression itself,
    whether the ranges are empty, and the mark of each name that it reads. The mark of a name with
    a range is the number of that range (its ends with their types and the signs of their zeros);
    the mark of a formula is made in the same way, from the names that it reads. So two provers
    that give one mark to a formula have the same range for every name that it reads through the
    formulas, and what one of them found is what the other finds.

    A number is given once and never again. When the marks or the answers are too many, all of them
    go: a prover that holds a mark that is gone finds nothing under it and proves again."""

    __slots__ = ('found', 'marks', 'numbers')

    def __init__(self):
        self.found, self.marks, self.numbers = {}, {}, itertools.count()

    def mark(self, key):
        found = self.marks.get(key)
        if found is None:
            if len(self.marks) >= KEPT:
                self.marks.clear()
                self.found.clear()
            found = self.marks[key] = next(self.numbers)
        return found

    def keep(self, key, answer):
        if len(self.found) >= KEPT:
            self.found.clear()
        self.found[key] = answer


def _single(condition):
    """(left, operation, right) of a comparison of two values, else None. The operation is None for a
    comparison that the language does not have: it narrows nothing."""
    if isinstance(condition, expr.Compare) and len(condition.ops) == 1:
        return condition.operands[0], condition.ops[0], condition.operands[1]
    if isinstance(condition, expr.Foreign):
        tree = condition.tree
        if isinstance(tree, ast.Compare) and len(tree.ops) == 1:
            return expr.of_tree(tree.left), None, expr.of_tree(tree.comparators[0])
    return None


class _Prover:
    def __init__(self, ranges, registry, aliases, weights=None):
        self.registry, self.aliases = registry, aliases
        # The names that stand for more than one value in a list: `weights.get(name, 1)` is how many.
        self.weights = weights if weights is not None else {}
        # The names that each formula reads; None for a formula that cannot be read.
        self.names = {}
        for name in aliases:
            try:
                self.names[name] = expr.names(aliases[name])
            except (ExpressionError, SyntaxError, ValueError, RecursionError):
                self.names[name] = None
        self.remembered_names = self.names.keys() - self._cyclic()
        self.reads = {}
        # The names that each formula and each expression that was asked reads, in one order.
        self.ordered = {}
        self.kept = _Kept()
        self._over(ranges)

    def _over(self, ranges):
        root = ChainMap(dict(ranges))
        if any(isinstance(pair, tuple) and len(pair) == 2 and pair[0] > pair[1] for pair in ranges.values()):
            root[EMPTY] = True
        self.root, self.empty = root, bool(root.get(EMPTY))
        # The marks of this prover: of each name with a range, of each formula and of each expression
        # that was asked (`_Kept`). They are found when they are first read.
        self.range_marks, self.marks = {}, {}

    def over(self, ranges):
        """A prover of the same formulas over `ranges`: it gives what a new prover over them gives.
        The two keep their answers together (`_Kept`), so an answer of one that depends on no range
        that is another one for the other is not found again."""
        other = copy.copy(self)
        other._over(ranges)
        return other

    def range_mark(self, name):
        found = self.range_marks.get(name)
        if found is None:
            pair = self.root.maps[0][name]
            try:
                key = (name, pair, *map(type, pair), *(math.copysign(1.0, end) for end in pair))
                hash(key)
            except TypeError:
                key = (name, object())  # a range that is no pair of numbers is equal to no range
            found = self.range_marks[name] = self.kept.mark(key)
        return found

    def marks_of(self, key, names):
        """The marks of the names that a formula or an expression reads, in one order. A name with a
        range has the mark of its range (the range is read, not a formula of that name); a formula
        with no circle has its own mark; a formula that is not remembered has the mark of every
        range that it can reach; another name can be any number."""
        ordered = self.ordered.get(key)
        if ordered is None:
            ordered = self.ordered[key] = tuple(sorted(names))
        root, out = self.root.maps[0], []
        for name in ordered:
            if name in root:
                out.append(self.range_mark(name))
            elif name in self.remembered_names:
                out.append(self.mark(name))
            elif name in self.names:
                out.append(self.circle_mark(name))
            else:
                out.append(-1)
        return tuple(out)

    def mark(self, name):
        """The mark of a formula with no circle: its name and the marks of the names that it reads."""
        found = self.marks.get(name)
        if found is None:
            key = ('formula', self.empty, name, self.marks_of(name, self.names[name]))
            found = self.marks[name] = self.kept.mark(key)
        return found

    def circle_mark(self, name):
        """The mark of a formula that is not remembered (it is on a circle, it reads one, or it cannot
        be read): the mark of each range that it reaches through the formulas. What the prover finds
        of it depends on the chain that reached it, so it is no answer to keep; an expression that
        reads it has this mark in its own."""
        key = 'circle', name
        found = self.marks.get(key)
        if found is None:
            reach = self.ordered.get(key)
            if reach is None:
                seen, pending = set(), [name]
                while pending:
                    for read in self.names.get(pending.pop()) or ():
                        if read not in seen:
                            seen.add(read)
                            if read in self.names:
                                pending.append(read)
                reach = self.ordered[key] = tuple(sorted(seen))
            root = self.root.maps[0]
            marks = tuple(self.range_mark(read) if read in root else -1 for read in reach)
            found = self.marks[key] = self.kept.mark(('circle', self.empty, name, marks))
        return found

    def asked_of(self, node):
        """The interval of an expression over the ranges, or its failure."""
        mark = self.marks.get(node)
        if mark is None:
            key = ('asked', self.empty, node, self.marks_of(node, expr.names(node)))
            mark = self.marks[node] = self.kept.mark(key)
        found = self.kept.found.get(mark)
        if found is None:
            try:
                found = (self.bounded(node, self.root), None)
            except ExpressionError as exc:
                found = (None, exc)
            self.kept.keep(mark, found)
        if found[1] is not None:
            raise ExpressionError(*found[1].args) from found[1].__cause__
        return found[0]

    def _cyclic(self):
        """The formulas from which a chain of formulas can come back to a formula that it went through."""
        acyclic, changed = set(), True
        while changed:
            changed = False
            for name, found in self.names.items():
                if name not in acyclic and found is not None and found & self.names.keys() <= acyclic:
                    acyclic.add(name)
                    changed = True
        return self.names.keys() - acyclic

    def reads_all(self, name):
        """Every name that a formula that cannot come back to itself reads, through the formulas it reads."""
        if name not in self.reads:
            found = set()
            for read in self.names[name]:
                found.add(read)
                if read in self.remembered_names:
                    found |= self.reads_all(read)
            self.reads[name] = frozenset(found)
        return self.reads[name]

    def branch_facts(self, context, name):
        """The facts of a branch that the formula of `name` reads, as a value that cannot change: what
        the layers over the ranges narrow, what they know not to be zero, and the two marks. The facts
        of the ranges themselves are in the mark of the formula (`mark`) and are no part of it."""
        if context is self.root:
            return ()
        dependencies = self.reads_all(name)

        def relevant(key):
            if isinstance(key, str):
                return key in dependencies
            used = expr.names(key)
            return not used or not used.isdisjoint(dependencies)

        layered = set().union(*context.maps[:-1]) - {EMPTY, GUARDED, NONZERO}
        bounds = tuple((key, context[key]) for key in sorted(layered, key=_written) if relevant(key))
        nonzero = frozenset(key for key in context.get(NONZERO, ()) if relevant(key))
        flags = bool(context.get(EMPTY)), bool(context.get(GUARDED))
        return (bounds, nonzero, flags) if bounds or nonzero or any(flags) else ()

    def constant_value(self, node, context):
        """The value of a node whose names all have one value in the context, else None."""
        try:
            needed = expr.names(node)
            env = {}
            for name in needed:
                pair = context.get(name)
                if isinstance(pair, tuple) and pair[0] == pair[1]:
                    env[name] = pair[0]
            if needed <= env.keys():
                result = evaluation.value(node, env, self.registry)
                if isinstance(result, (int, float)) and not isinstance(result, bool):
                    return float(result)
        except (ExpressionError, ValueError, KeyError, OverflowError, ZeroDivisionError):
            pass
        return None

    def refine(self, context, condition, positive):
        """The context of the branch where `condition` holds (`positive`) or fails. Each refinement
        layers its few narrowed intervals over the context around it. A condition that narrows
        nothing gives that context itself, so the intervals that it keeps stay remembered. No state
        reaches a context that is empty: nothing narrows it more, and no part is read in it, because
        an interval of it can have its ends in the wrong order (a divisor from 5e-324 to 0)."""
        if context.get(EMPTY, False):
            return context
        if isinstance(condition, expr.Unary) and condition.op == 'not':
            return self.refine(context, condition.operand, not positive)
        if isinstance(condition, expr.BoolOp) and (condition.op == 'and') == positive:
            for child in condition.values:
                context = self.refine(context, child, positive)
            return context
        single = _single(condition)
        if single is None:
            return context
        left, op, other = single
        right = self.constant_value(other, context)
        if right is None:
            right = self.constant_value(left, context)
            if right is None or op not in MIRRORED:
                return context
            left, op = other, MIRRORED[op]
        updated = context.new_child()
        name = _key(left)
        if not isinstance(left, expr.Ref):
            # A guard on an expression narrows that expression wherever the branch reads it.
            updated[GUARDED] = True
        if name not in updated:
            # A computed value starts from the interval of its definition, an expression from its own.
            try:
                updated[name] = self.bounded(left, updated)
            except ExpressionError:
                return updated
        lower, upper = updated[name]
        if not positive:
            op = OPPOSITE.get(op)
        if op == 'gt':
            lower = max(lower, math.nextafter(right, math.inf))
        elif op == 'ge':
            lower = max(lower, right)
        elif op == 'lt':
            upper = min(upper, math.nextafter(right, -math.inf))
        elif op == 'le':
            upper = min(upper, right)
        elif op == 'eq':
            lower = max(lower, right)
            upper = min(upper, right)
            if right == 0 and name in updated.get(NONZERO, set()):
                updated[EMPTY] = True
        elif op == 'ne' and right == lower:
            lower = math.nextafter(lower, math.inf)
        elif op == 'ne' and right == upper:
            upper = math.nextafter(upper, -math.inf)
        if op == 'ne' and right == 0:
            updated[NONZERO] = set(updated.get(NONZERO, set())) | {name}
        updated[name] = (lower, upper)
        if lower > upper:
            updated[EMPTY] = True  # refinements only narrow intervals, so emptiness persists
        return updated

    def remembered(self, name, context):
        """The interval, or the failure, of a formula with no circle under the facts that it reads."""
        key = self.mark(name), self.branch_facts(context, name)
        kept = self.kept.found.get(key)
        if kept is None:
            try:
                kept = (self.bounded(self.aliases[name], context, frozenset((name,))), None)
            except ExpressionError as exc:
                kept = (None, exc)
            self.kept.keep(key, kept)
        found, problem = kept
        if problem is not None:
            raise ExpressionError(*problem.args) from problem.__cause__
        return found

    def bounded(self, node, context, seen=frozenset()):
        low, high = self.interval(node, context, seen)
        if math.isnan(low) or math.isnan(high):
            # An indeterminate bound, such as inf - inf, proves nothing.
            low, high = WHOLE
        if context.get(GUARDED) and not isinstance(node, expr.Ref):
            narrowed = context.get(node)
            if narrowed is not None:
                low, high = max(low, narrowed[0]), min(high, narrowed[1])
        return low, high

    def interval(self, node, context, seen):
        if isinstance(node, expr.Ref):
            name = node.name
            if name in context:
                return context[name]
            if name in self.aliases and name not in seen:
                # Without a circle, the facts that its formula reads decide its interval, whatever
                # chain reached it.
                if name in self.remembered_names:
                    return self.remembered(name, context)
                return self.bounded(self.aliases[name], context, seen | {name})
            return WHOLE
        if isinstance(node, expr.Const):
            value = node.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return (float(value), float(value))
            return WHOLE
        if isinstance(node, expr.Foreign):
            return _foreign(self, node, context, seen)
        handler = TABLE.get(ops.operation_of(node))
        if handler is None:
            return _unknown_call(self, node.args, context, seen)
        return handler(self, node, context, seen)


# ---- the handlers: the interval of each operation -------------------------------------------------------


def _both(prover, node, context, seen):
    return prover.bounded(node.left, context, seen), prover.bounded(node.right, context, seen)


def _arguments(prover, node, context, seen):
    return [prover.bounded(arg, context, seen) for arg in node.args]


def _condition(prover, node, context, seen):
    """A yes/no of parts that are each read in the context around them: `not`, a chain of comparisons."""
    for part in node.children:
        prover.bounded(part, context, seen)
    return (0, 1)


def _lazy(prover, node, context, seen):
    # Each term is read in the branch where the terms before it let it run.
    refined = context
    for child in node.values:
        if refined.get(EMPTY, False):
            break
        prover.bounded(child, refined, seen)
        refined = prover.refine(refined, child, node.op == 'and')
    return (0, 1)


def _choice(prover, node, context, seen):
    prover.bounded(node.test, context, seen)
    found = []
    for branch, positive in ((node.body, True), (node.orelse, False)):
        refined = prover.refine(context, node.test, positive)
        if not refined.get(EMPTY, False):
            found.append(prover.bounded(branch, refined, seen))
    return (min(x[0] for x in found), max(x[1] for x in found)) if found else (0, 0)


def _neg(prover, node, context, seen):
    low, high = prover.bounded(node.operand, context, seen)
    return (-high, -low)


def _pos(prover, node, context, seen):
    return prover.bounded(node.operand, context, seen)


def _add(prover, node, context, seen):
    left, right = _both(prover, node, context, seen)
    return (left[0] + right[0], left[1] + right[1])


def _sub(prover, node, context, seen):
    left, right = _both(prover, node, context, seen)
    return (left[0] - right[1], left[1] - right[0])


def _products(left, right):
    products = [0.0 if a == 0 or b == 0 else a * b for a in left for b in right]
    return (min(products), max(products))


def _mul(prover, node, context, seen):
    return _products(*_both(prover, node, context, seen))


def _div(prover, node, context, seen):
    left, right = _both(prover, node, context, seen)
    if right[0] <= 0 <= right[1]:
        if _key(node.right) in context.get(NONZERO, set()):
            return WHOLE
        raise ExpressionError(
            f'Cannot prove nonzero denominator in `{expr.notation(node)}`; declare bounds or guard the branch'
        )
    return _products(left, (1 / right[1], 1 / right[0]))


def _pow(prover, node, context, seen):
    left, _ = _both(prover, node, context, seen)
    exponent = prover.constant_value(node.right, context)
    if (exponent is None or not exponent.is_integer()) and left[0] < 0:
        raise ExpressionError('Cannot prove nonnegative base for fractional/variable power')
    if (exponent is None or exponent < 0) and left[0] <= 0 <= left[1]:
        raise ExpressionError('Cannot prove nonzero base for negative/variable power')
    if exponent is None:
        return WHOLE
    if exponent == 0:
        return (1, 1)
    try:
        ends = [x**exponent for x in left]
        if left[0] <= 0 <= left[1] and exponent > 0:
            ends.append(0)
        return (min(ends), max(ends))
    except (ValueError, OverflowError) as exc:
        raise ExpressionError('Power can overflow within the declared expression domain') from exc


def _quantity(prover, node, context, seen):
    low, high = prover.bounded(node.args[0], context, seen)
    scale = prover.registry.parse_unit(node.args[1].value).scale
    return (low * scale, high * scale)


def _min(prover, node, context, seen):
    args = _arguments(prover, node, context, seen)
    return (min(x[0] for x in args), min(x[1] for x in args))


def _max(prover, node, context, seen):
    args = _arguments(prover, node, context, seen)
    return (max(x[0] for x in args), max(x[1] for x in args))


def _sum(prover, node, context, seen):
    # The members added from the left, as the chain of sums of two is. A member that reads a name
    # with a weight stands for that many values, each in the interval of the member: it is counted
    # that many times.
    low = high = 0.0
    for place, member in enumerate(node.args):
        a, b = prover.bounded(member, context, seen)
        if prover.weights:
            count = max((prover.weights.get(name, 1) for name in expr.names(member)), default=1)
            if count != 1:
                a, b = count * a, count * b
        low, high = (a, b) if place == 0 else (low + a, high + b)
    return (low, high)


def _listed(op):
    """`any` or `all` of the members of a list: one member is that member, and more are the `or` or the
    `and` of them."""

    def handler(prover, node, context, seen):
        if len(node.args) == 1:
            return prover.bounded(node.args[0], context, seen)
        return _lazy(prover, expr.boolean(op, node.args), context, seen)

    return handler


def _clip(prover, node, context, seen):
    args = _arguments(prover, node, context, seen)
    if args[1][1] > args[2][0]:
        raise ExpressionError('Cannot prove clip bounds are ordered')
    return (
        min(max(args[0][0], args[1][0]), args[2][0]),
        min(max(args[0][1], args[1][1]), args[2][1]),
    )


def _within(prover, node, context, seen):
    # A membership has a value only where its interval is ordered (`ops.REVERSED`).
    args = _arguments(prover, node, context, seen)
    if args[1][1] > args[2][0]:
        raise ExpressionError('Cannot prove the ends of a membership test are ordered')
    return (0, 1)


def _logarithm(name, offset):
    def handler(prover, node, context, seen):
        low, high = _arguments(prover, node, context, seen)[0]
        if low + offset <= 0:
            raise ExpressionError(f'Cannot prove {name} argument is in its domain')
        return (math.log(low + offset), math.log(high + offset))

    return handler


def _exponential(name, offset):
    def handler(prover, node, context, seen):
        low, high = _arguments(prover, node, context, seen)[0]
        if high > math.log(LARGEST):
            raise ExpressionError(f'Cannot prove {name} stays within finite floating-point range')
        return (math.exp(low) - offset, math.exp(high) - offset)

    return handler


def _sqrt(prover, node, context, seen):
    low, high = _arguments(prover, node, context, seen)[0]
    if low < 0:
        raise ExpressionError('Cannot prove sqrt argument is nonnegative')
    return (math.sqrt(low), math.sqrt(high))


def _abs(prover, node, context, seen):
    low, high = _arguments(prover, node, context, seen)[0]
    return (0 if low <= 0 <= high else min(abs(low), abs(high)), max(abs(low), abs(high)))


def _erf(prover, node, context, seen):
    # erf rises on the whole line, so the ends of its argument give the ends of its value.
    low, high = _arguments(prover, node, context, seen)[0]
    return (math.erf(low), math.erf(high))


def _unknown_call(prover, args, context, seen):
    """A call of a function that the language does not have: its arguments are read, and its value
    can be any number. A call with no argument is an IndexError, as it was."""
    if not [prover.bounded(arg, context, seen) for arg in args]:
        raise IndexError('list index out of range')
    return WHOLE


def _foreign(prover, node, context, seen):
    """A part that is outside the language: the parts inside it are read, and its value can be any
    number. A model with such a part is rejected before any proof, by the rules for units."""
    tree = node.tree
    if isinstance(tree, ast.Compare):
        for item in (tree.left, *tree.comparators):
            prover.bounded(expr.of_tree(item), context, seen)
        return (0, 1)
    if isinstance(tree, ast.UnaryOp):
        return prover.bounded(expr.of_tree(tree.operand), context, seen)
    if isinstance(tree, ast.BinOp):
        prover.bounded(expr.of_tree(tree.left), context, seen)
        prover.bounded(expr.of_tree(tree.right), context, seen)
        return WHOLE
    if isinstance(tree, ast.Call):
        name, args = tree.func.id, [expr.of_tree(arg) for arg in tree.args]
        if name in expr.FUNCTIONS:  # a function of the language with keywords, which are not read
            return TABLE[name](prover, expr.call(name, args), context, seen)
        return _unknown_call(prover, args, context, seen)
    return WHOLE


TABLE = ops.handlers(
    'the interval of an expression',
    {
        'neg': _neg,
        'pos': _pos,
        'not': _condition,
        'and': _lazy,
        'or': _lazy,
        **dict.fromkeys(expr.COMPARE.values(), _condition),
        'if': _choice,
        'add': _add,
        'sub': _sub,
        'mul': _mul,
        'div': _div,
        'pow': _pow,
        'min': _min,
        'max': _max,
        'sum': _sum,
        'any': _listed('or'),
        'all': _listed('and'),
        'clip': _clip,
        'within': _within,
        'abs': _abs,
        'sqrt': _sqrt,
        'exp': _exponential('exp', 0),
        'expm1': _exponential('expm1', 1),
        'ln': _logarithm('ln', 0),
        'log1p': _logarithm('log1p', 1),
        'erf': _erf,
        'q': _quantity,
    },
)


def prover(ranges, registry, aliases=None, weights=None):
    """`prove(node)`: the closed interval of a node over `ranges` (name → (low, high), in execution
    units), or its ExpressionError. `aliases` gives the node of the formula of a name; it is read when
    the prover is made and when a formula is proved, and it must not change. The ranges are copied.

    `weights` (name → n) is for a list in which one member stands for n values: the rows of one class
    of a table, each of which has the range of the name. `sum` counts such a member n times. `min`,
    `max`, `any` and `all` need no count: n values in one interval have their least and their
    greatest in that interval."""
    return _Prove(_Prover(ranges, registry, {} if aliases is None else aliases, weights))


class _Prove:
    """The function that `prover` gives. `over(ranges)` gives the function of the same formulas over
    other ranges. The two keep their answers together: what one found of a formula or of an
    expression is not found again by the other, when each name that it reads through the formulas
    has one range for both. So a caller that changes a few ranges, or that changes them back, does
    not pay for every proof again."""

    __slots__ = ('made',)

    def __init__(self, made):
        self.made = made

    def __call__(self, node):
        # As the entries of `napkin.expressions`: a node, or a number, which is the node of its text;
        # a text is a TypeError.
        if isinstance(node, (bool, int, float)):
            node = expr.written(node)
        elif not isinstance(node, expr.Node):
            raise TypeError(
                f'an expression to prove is a node or a number, not {type(node).__name__}: read a '
                'text with napkin.core.expr.read'
            )
        return self.made.asked_of(node)

    def over(self, ranges):
        return _Prove(self.made.over(ranges))
