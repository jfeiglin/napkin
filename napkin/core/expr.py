"""Typed expressions: immutable nodes, each made once.

An expression is a tree of nodes: a constant (`Const`), a reference to a named value (`Ref`), an
operation on one value (`Unary`: `neg`, `pos`, `not`) or on two (`Binary`: `add`, `sub`, `mul`, `div`,
`pow`), a chain of comparisons (`Compare`: `eq`, `ne`, `lt`, `le`, `gt`, `ge`), `and` / `or` of values
(`BoolOp`), a choice (`IfElse`) and a call of a function of the language (`Call`).

Three things are kept apart.

- **The identity of a computation.** Two nodes with the same kind, the same operation and the same
  parts are one object, so `a is b` says that two expressions compute the same thing, and a node is a
  key of a dictionary by itself. A constant is tagged by its type: `1`, `1.0` and `True` are three
  constants, and so are `0.0` and `-0.0`. A node holds no place in a file and no unit.
- **What holds of a computation in a context** (its unit, whether it moves in a segment) is no field
  of a node: an analysis keeps it, by the node and the context.
- **The places where a computation is written** are records of their own (the part, the role of the
  expression in it), each with its place in the file. One node can be written in many places.

A node lives while something holds it: a part of a model, a larger node, or a memory of this module
or of a consumer (each has a limit). So a long study, which reads new numbers for each sample, does
not fill the memory with nodes that nothing reads again. Two nodes that are both alive and have the
same key are still one object.

A membership `x in [lo, hi]` is the call `within(x, lo, hi)`, one operation that reads x once and
fails where its interval is reversed; `membership` gives the chain of comparisons that it tests, for
a consumer that reads the comparisons of a condition.

`read` gives the node of an expression text of today's structures, once for each text. A part of a
text that is outside the language (an operator or a form that the language does not have) is a
`Foreign` node, which keeps Python's own tree of that part: such a text fails when its value is asked,
as it does today, and not when it is read. `text` writes a node as `ast.unparse` writes its tree, for
each node that has no `Foreign` part. `names` gives the names that a node reads.

The contract of each operation (its arity, its rule for units, where it is defined) is not here: it is
in `ops`, and what a consumer does with an operation is with that consumer.
"""

from __future__ import annotations

import ast
import math
import sys
import weakref
from collections import deque
from functools import lru_cache
from threading import RLock

from .errors import ExpressionError

# The longest text and the largest tree of one expression.
LONGEST = 10000
LARGEST = 1000
# The deepest tree of one expression: the operations one inside the other.
# The readers of an expression go down its tree with calls, at most four for each level, and Python
# has 1,000 calls one inside the other.
DEEPEST = 150

UNARY = {ast.USub: 'neg', ast.UAdd: 'pos', ast.Not: 'not'}
BINARY = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.Div: 'div', ast.Pow: 'pow'}
COMPARE = {ast.Eq: 'eq', ast.NotEq: 'ne', ast.Lt: 'lt', ast.LtE: 'le', ast.Gt: 'gt', ast.GtE: 'ge'}
# The functions that an expression of a structure can call.
FUNCTIONS = frozenset(
    {
        *('min', 'max', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf', 'abs', 'q', 'clip'),
        *('sum', 'any', 'all', 'within'),
    }
)
# The functions over the members of a list, each one node whatever the number of members: `sum(a, b, c)`
# is `a + b + c` added from the left, and `any` and `all` are `or` and `and` of their members. One
# member is that member. An author writes them over a list (`sum(zones.x)`), and the lowering gives the
# members.
LISTED = frozenset({'sum', 'any', 'all'})
# How each operation is written.
SYMBOLS = {
    'neg': '-',
    'pos': '+',
    'not': 'not',
    'add': '+',
    'sub': '-',
    'mul': '*',
    'div': '/',
    'pow': '**',
    'eq': '==',
    'ne': '!=',
    'lt': '<',
    'le': '<=',
    'gt': '>',
    'ge': '>=',
}

# Each node that is alive, by its key. A node is made under the lock, so two threads that ask for one
# key get one object.
_NODES = weakref.WeakValueDictionary()
_LOCK = RLock()
# The number of texts whose nodes `read` keeps.
READ = 65536


class Node:
    """A node of an expression. `_key` is its kind, its operation and its parts; a node is made by its
    function below (`const`, `ref`, …), never by its class, and it cannot change."""

    __slots__ = ('__weakref__', '_height', '_key', '_names', '_outside', '_parts', '_text')
    FIELDS = ()

    def __setattr__(self, name, value):
        raise AttributeError(f'a node of an expression cannot change: {name}')

    def __reduce__(self):
        return _made, (type(self), *(getattr(self, name) for name in self.FIELDS))

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self  # a node cannot change, so a copy of it is the node

    def __repr__(self):
        return f'<{type(self).__name__} {text(self)}>'

    def __str__(self):
        # The text of the expression: it reads back to this node (`read`).
        return text(self)

    @property
    def children(self):
        """The nodes that this node is made of, in their order."""
        return ()


class Const(Node):
    """A constant: a number, a yes/no or a text."""

    __slots__ = ('value',)
    FIELDS = ('value',)


class Ref(Node):
    """A reference to a named value."""

    __slots__ = ('name',)
    FIELDS = ('name',)


class Unary(Node):
    __slots__ = ('op', 'operand')
    FIELDS = ('op', 'operand')

    @property
    def children(self):
        return (self.operand,)


class Binary(Node):
    __slots__ = ('left', 'op', 'right')
    FIELDS = ('op', 'left', 'right')

    @property
    def children(self):
        return (self.left, self.right)


class Compare(Node):
    """A chain of comparisons: `operands[0] ops[0] operands[1] ops[1] operands[2]` …"""

    __slots__ = ('operands', 'ops')
    FIELDS = ('ops', 'operands')

    @property
    def children(self):
        return self.operands


class BoolOp(Node):
    __slots__ = ('op', 'values')
    FIELDS = ('op', 'values')

    @property
    def children(self):
        return self.values


class IfElse(Node):
    __slots__ = ('body', 'orelse', 'test')
    FIELDS = ('test', 'body', 'orelse')

    @property
    def children(self):
        return (self.test, self.body, self.orelse)


class Call(Node):
    """A call of a function of the language. The number of arguments is not checked here: a call
    with a wrong number fails when its value is asked."""

    __slots__ = ('args', 'function')
    FIELDS = ('function', 'args')

    @property
    def children(self):
        return self.args


class Foreign(Node):
    """A part of an expression text that is outside the language, as Python's tree of it. Its identity
    is the dump of that tree."""

    __slots__ = ('dump', 'tree')
    FIELDS = ('tree',)

    def __reduce__(self):
        return _foreign_again, (ast.unparse(self.tree),)


def _made(kind, *fields):
    """The one node of a kind with these fields."""
    if kind is Const:
        (value,) = fields
        shown = value.hex() if type(value) is float else value
        key = (Const, type(value).__name__, shown)
    else:
        key = (kind, *fields)
    with _LOCK:
        found = _NODES.get(key)
        if found is None:
            found = kind.__new__(kind)
            for name, value in zip(kind.FIELDS, fields):
                object.__setattr__(found, name, value)
            object.__setattr__(found, '_key', key)
            _NODES[key] = found
    return found


def made(kind, *fields):
    """The one node of a kind that another module defines (a subclass of `Node` with its `FIELDS`),
    with these fields. Such a kind writes itself with its method `text()`."""
    return _made(kind, *fields)


def const(value):
    """The constant of one value, tagged by the type of the value."""
    return _made(Const, value)


def written(value):
    """The node of a constant as a text writes it: a number below zero is the negation of the number
    above it (`-1` is `-(1)`), so the node is the one that its own text reads back to."""
    if type(value) in (int, float) and (value < 0 or (value == 0 and math.copysign(1, value) < 0)):
        return unary('neg', const(-value))
    return const(value)


def ref(name):
    return _made(Ref, name)


def unary(op, operand):
    return _made(Unary, op, operand)


def binary(op, left, right):
    return _made(Binary, op, left, right)


def compare(ops, operands):
    return _made(Compare, tuple(ops), tuple(operands))


def boolean(op, values):
    return _made(BoolOp, op, tuple(values))


def if_else(test, body, orelse):
    return _made(IfElse, test, body, orelse)


def call(function, args):
    return _made(Call, function, tuple(args))


def membership(node):
    """For a membership `within(x, lo, hi)` (`x in [lo, hi]`): (the chain `lo <= x <= hi` that it
    tests once its interval is ordered, lo, hi); None for any other node. A consumer that reads the
    comparisons of a condition (where it changes between moments, a near-tie) reads a membership as
    that chain, once the membership itself is evaluated, which fails by name where its interval is
    reversed (`ops.REVERSED`)."""
    if not (isinstance(node, Call) and node.function == 'within' and len(node.args) == 3):
        return None
    value, low, high = node.args
    return compare(['le', 'le'], [low, value, high]), low, high


def foreign(tree):
    """The node of a part that is outside the language."""
    # From Python 3.13 a dump leaves out an empty list by default, and for that it asks a kind of
    # node for the types of its fields, which a kind of another module (the resolver's) does not
    # have. With the empty parts shown, the dump is the one of the Pythons before.
    dump = ast.dump(tree, show_empty=True) if sys.version_info >= (3, 13) else ast.dump(tree)
    key = (Foreign, dump)
    with _LOCK:
        found = _NODES.get(key)
        if found is None:
            found = Foreign.__new__(Foreign)
            object.__setattr__(found, 'tree', tree)
            object.__setattr__(found, 'dump', dump)
            object.__setattr__(found, '_key', key)
            _NODES[key] = found
    return found


def _foreign_again(written):
    return foreign(ast.parse(written, mode='eval').body)


# ---- from an expression text ----------------------------------------------------------------------------


def symbol(tree):
    """The dotted name that a part of Python's tree writes (`a`, `a.b.c`), or None. A part of a name
    that starts with `_` is no name of a model."""
    if isinstance(tree, ast.Name):
        return tree.id
    if isinstance(tree, ast.Attribute):
        prefix = symbol(tree.value)
        if prefix and not tree.attr.startswith('_'):
            return f'{prefix}.{tree.attr}'
    return None


def of_tree(tree, functions=FUNCTIONS):
    """The node of one part of Python's tree of an expression. A call of a name of `functions` is a
    call; a call of another name is a part outside the language."""
    name = symbol(tree)
    if name is not None:
        return ref(name)
    if isinstance(tree, ast.Constant):
        try:
            return written(tree.value)
        except TypeError:  # a constant that is no key of a dictionary cannot be in an expression
            return foreign(tree)

    def part(item):
        return of_tree(item, functions)

    if isinstance(tree, ast.IfExp):
        return if_else(part(tree.test), part(tree.body), part(tree.orelse))
    if isinstance(tree, ast.BoolOp):
        return boolean('and' if isinstance(tree.op, ast.And) else 'or', map(part, tree.values))
    if isinstance(tree, ast.UnaryOp) and type(tree.op) in UNARY:
        return unary(UNARY[type(tree.op)], part(tree.operand))
    if isinstance(tree, ast.Compare) and all(type(op) in COMPARE for op in tree.ops):
        ops = [COMPARE[type(op)] for op in tree.ops]
        return compare(ops, map(part, (tree.left, *tree.comparators)))
    if isinstance(tree, ast.BinOp) and type(tree.op) in BINARY:
        return binary(BINARY[type(tree.op)], part(tree.left), part(tree.right))
    if (
        isinstance(tree, ast.Call)
        and isinstance(tree.func, ast.Name)
        and tree.func.id in functions
        and not tree.keywords
    ):
        return call(tree.func.id, map(part, tree.args))
    return foreign(tree)


def read(source):
    """The node of an expression that is written as a text, or of the number or the yes/no that it is
    (which is read as its text, so `-1` is the negation of `1`, as in a text). A node comes back as it
    is: a part of a compiled model holds the node itself. The nodes of the last `READ` texts are kept,
    so a text in use is read once. A text that is longer than `LONGEST` characters, or whose tree has
    more than `LARGEST` parts or is deeper than `DEEPEST`, is an `ExpressionError`; a text that Python
    cannot read is a `SyntaxError`; a source of another type is a `TypeError`."""
    if type(source) is not str:
        if isinstance(source, Node):
            return source  # a part of a compiled model holds the node itself
        if not isinstance(source, (str, bool, int, float)):
            raise TypeError(f'an expression is a text or a number, not {type(source).__name__}')
        source = str(source)
    return _read(source)


def parse(written, functions=FUNCTIONS):
    """The node of an expression text, with no limit of the number of its parts and no memory of it:
    for a reader of the form of an expression whose size another check judges. A text that Python
    cannot read is a `SyntaxError`, and a text whose tree is deeper than `DEEPEST` is an
    `ExpressionError`. `functions` names the functions whose calls are calls (`of_tree`)."""
    return _of_text(written, functions, None)


def _of_text(written, functions, largest):
    """The node of a text. A tree with more than `largest` parts, and a tree that is deeper than
    `DEEPEST`, are over the limit of size."""
    try:
        tree = ast.parse(written, mode='eval').body
        if largest is not None and sum(1 for _ in ast.walk(tree)) > largest:
            raise ExpressionError('Expression exceeds complexity budget')
        return shallow(of_tree(tree, functions))
    except RecursionError:
        # A chain of many hundreds of operations: Python, or the reader of its tree, cannot go down it.
        raise ExpressionError('Expression exceeds complexity budget') from None


def shallow(node):
    """The node, when its tree is no deeper than `DEEPEST`: a deeper tree is an `ExpressionError`."""
    if height(node) > DEEPEST:
        raise ExpressionError('Expression exceeds complexity budget')
    return node


def parts(node):
    """The number of parts of Python's tree of the text of a node (`text`): the parts that `ast.walk`
    gives of the tree of that expression, without the tree of the whole text (`ast.Expression`).
    Each node keeps it. A text that Python cannot read is a `SyntaxError`, or a `RecursionError`."""
    try:
        return node._parts
    except AttributeError:
        pass
    found = sum(1 for _ in ast.walk(ast.parse(text(node), mode='eval').body))
    object.__setattr__(node, '_parts', found)
    return found


def limited(node):
    """The node, when the limits of size hold for it, as they hold for its text: the text has at most
    `LONGEST` characters, Python's tree of the text has at most `LARGEST` parts with the tree of the
    whole text (`ast.Expression`), and the node is no deeper than `DEEPEST`. They are checked in this
    order, each an `ExpressionError`; a text that Python cannot read is the `ExpressionError` of an
    invalid expression."""
    try:
        written = text(node)
    except RecursionError:
        # A node of many hundreds of operations one inside the other has no text.
        raise ExpressionError('Expression exceeds complexity budget') from None
    if len(written) > LONGEST:
        raise ExpressionError(f'Expression exceeds {LONGEST} characters')
    try:
        found = parts(node)
    except (SyntaxError, RecursionError) as exc:
        raise ExpressionError(f'Invalid expression: {exc}') from exc
    if 1 + found > LARGEST:
        raise ExpressionError('Expression exceeds complexity budget')
    return shallow(node)


@lru_cache(maxsize=READ)
def _read(written):
    if len(written) > LONGEST:
        raise ExpressionError(f'Expression exceeds {LONGEST} characters')
    return _of_text(written, FUNCTIONS, LARGEST)


# ---- what a node reads ----------------------------------------------------------------------------------


def _tree_names(tree):
    name = symbol(tree)
    if name is not None:
        return frozenset((name,))
    children = tree.args if isinstance(tree, ast.Call) else ast.iter_child_nodes(tree)
    return frozenset().union(*map(_tree_names, children))


def names(node):
    """The names that an expression reads: each reference in it. The name of a function is no name
    that it reads."""
    try:
        return node._names
    except AttributeError:
        pass
    if isinstance(node, Ref):
        found = frozenset((node.name,))
    elif isinstance(node, Foreign):
        found = _tree_names(node.tree)
    else:
        found = frozenset().union(*map(names, node.children))
    object.__setattr__(node, '_names', found)
    return found


def outside(node):
    """Whether an expression has a part that is outside the language."""
    try:
        return node._outside
    except AttributeError:
        pass
    found = isinstance(node, Foreign) or any(map(outside, node.children))
    object.__setattr__(node, '_outside', found)
    return found


def height(node):
    """The height of the tree of a node: 1 for a node with no part. It is found with a list and not
    with calls, so a chain of thousands of operations has a height too. Each node keeps its
    height."""
    try:
        return node._height
    except AttributeError:
        pass
    pending = [node]
    while pending:
        part = pending[-1]
        waiting = [child for child in part.children if not hasattr(child, '_height')]
        if waiting:
            pending += waiting
            continue
        pending.pop()
        object.__setattr__(part, '_height', 1 + max((child._height for child in part.children), default=0))
    return node._height


def walk(node):
    """Each node of an expression, the node itself first, then the nodes of each part in order."""
    yield node
    for child in node.children:
        yield from walk(child)


def breadth_first(node):
    """Each node of an expression, level by level: the node, then its parts, then their parts. This
    is the order in which `ast.walk` gives the parts of Python's tree of the expression."""
    pending = deque([node])
    while pending:
        found = pending.popleft()
        yield found
        pending.extend(found.children)


# ---- as text --------------------------------------------------------------------------------------------

# The levels of binding of Python's grammar, as `ast.unparse` uses them.
TEST, OR, AND, NOT, CMP, EXPR, BOR, BXOR, BAND, SHIFT, ARITH, TERM, FACTOR, POWER, AWAIT, ATOM = range(1, 17)
LEVELS = {'add': ARITH, 'sub': ARITH, 'mul': TERM, 'div': TERM, 'pow': POWER, 'neg': FACTOR, 'pos': FACTOR}
LEVELS['not'] = NOT


# The level of a part outside the language, by its kind in Python's tree. A kind that is not here is
# written in brackets inside another node.
_OUTSIDE = {
    ast.Mod: TERM,
    ast.FloorDiv: TERM,
    ast.MatMult: TERM,
    ast.LShift: SHIFT,
    ast.RShift: SHIFT,
    ast.BitOr: BOR,
    ast.BitXor: BXOR,
    ast.BitAnd: BAND,
}
_ATOMS = (ast.Call, ast.Subscript, ast.Attribute, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp)
_ATOMS += (ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Constant, ast.Name, ast.JoinedStr)


def _foreign_level(tree):
    if isinstance(tree, _ATOMS):
        return ATOM
    if isinstance(tree, ast.BinOp):
        return _OUTSIDE.get(type(tree.op), TEST)
    if isinstance(tree, ast.UnaryOp):
        return FACTOR
    if isinstance(tree, ast.Compare):
        return CMP
    return TEST


def _float_text(value):
    # `ast.unparse` writes an infinity as a number that overflows.
    written = repr(value)
    return written.replace('inf', '1e309') if math.isinf(value) else written


def _string_text(value):
    """A text constant as `ast.unparse` writes it: single quotes, unless the text holds one."""
    if value.isprintable():
        escaped = value.replace('\\', '\\\\')
    else:
        escaped = value.encode('unicode_escape').decode('ascii')
    for quote in ("'", '"'):
        if quote not in escaped:
            return f'{quote}{escaped}{quote}'
    return repr(value)


def _written(node, level):
    if isinstance(node, Ref):
        return node.name
    if isinstance(node, Const):
        value = node.value
        if type(value) is float:
            return _float_text(value)
        return _string_text(value) if type(value) is str else repr(value)
    if isinstance(node, Unary):
        own = LEVELS[node.op]
        gap = ' ' if node.op == 'not' else ''
        written = SYMBOLS[node.op] + gap + _written(node.operand, own)
        return f'({written})' if level > own else written
    if isinstance(node, Binary):
        own = LEVELS[node.op]
        if node.op == 'pow':  # a power binds to the right
            written = f'{_written(node.left, own + 1)} ** {_written(node.right, own)}'
        else:
            written = f'{_written(node.left, own)} {SYMBOLS[node.op]} {_written(node.right, own + 1)}'
        return f'({written})' if level > own else written
    if isinstance(node, Compare):
        written = _written(node.operands[0], CMP + 1)
        for op, operand in zip(node.ops, node.operands[1:]):
            written += f' {SYMBOLS[op]} {_written(operand, CMP + 1)}'
        return f'({written})' if level > CMP else written
    if isinstance(node, BoolOp):
        own = OR if node.op == 'or' else AND
        # `ast.unparse` raises the level for each next value of one operator.
        parts, at = [], own
        for value in node.values:
            at += 1
            parts.append(_written(value, at))
        written = f' {node.op} '.join(parts)
        return f'({written})' if level > own else written
    if isinstance(node, IfElse):
        written = f'{_written(node.body, TEST + 1)} if {_written(node.test, TEST + 1)} else '
        written += _written(node.orelse, TEST)
        return f'({written})' if level > TEST else written
    if isinstance(node, Call):
        return f'{node.function}({", ".join(_written(arg, TEST) for arg in node.args)})'
    if not isinstance(node, Foreign):
        return node.text()  # a kind that another module defines
    # A part outside the language: Python's own text of it, in brackets where its own level asks for them.
    written = ast.unparse(node.tree)
    return f'({written})' if level > _foreign_level(node.tree) else written


def text(node):
    """An expression as text. For a node with no part outside the language, it is the text that
    `ast.unparse` writes for Python's tree of the expression, so it reads back to the same node."""
    try:
        return node._text
    except AttributeError:
        pass
    written = _written(node, TEST)
    object.__setattr__(node, '_text', written)
    return written
