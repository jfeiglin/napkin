"""A resolved expression as typed nodes.

The front end reads the names of an expression (`language/resolve.py`). What it finds is a tree of the
nodes of `napkin/core/expr.py` (a constant, an operation, a comparison, a choice, a call of a function
of the language) with five kinds of leaf of its own:

- `Ref`: a name of a value, resolved: member `member` of entity `entity`, or the output `member` of
  the scenario when `entity` is None. `written` is the name as the file writes it, for messages.
- `EventRef`: an event, resolved: the event (`key`, `entity.event`), the outcome that the name names
  (`ending`, or None for the event itself), and `kind`.
- `Terms`: what a sum over a list adds: one `Ref` for each entity of a list link, or for each copy
  of a set. `written` is the name of the list and its member as the file writes them (`zones.flag`),
  or None for terms that no file writes.
- `Word`: `true` or `false`. `problem` is why the word is no name, which a test of a named state
  needs.
- `Problem`: a part that the front end cannot read, and why.

A call keeps the name of its function as the file writes it (`sum`, `count`, `since`, `delayed`, the
name of a distribution, and the functions of the engine). A call with arguments by name, which is how
a distribution is written (`normal(a, b, min=c)`), is a kind of node of this module:

- `Named`: the name of the function (`function`), the nodes of its arguments by position (`args`)
  and its arguments by name (`named`: each a pair of the name and the node, in the order in which
  they are written). The name of a pair is None for an argument that is written `**x`: the grammar
  of a file reads that form, and no function of the language takes it.

A part that the language does not have is a `Foreign` node of `expr`, which keeps the tree that the
front end made of it. The grammar of a file lets three such forms through: values in round brackets
with a comma between them (`(a, b)`), a call of something that is no name (`max(a)(b)`), and an
argument with a star (`max(*a)`).

`of_tree` gives the nodes of the tree that the resolver makes today.
"""

from __future__ import annotations

import ast
from collections import deque

from ..core import expr as nodes
from . import semantic


class Ref(nodes.Node):
    __slots__ = ('entity', 'member', 'written')
    FIELDS = ('entity', 'member', 'written')

    def text(self):
        return self.written


class EventRef(nodes.Node):
    __slots__ = ('ending', 'key', 'kind', 'written')
    FIELDS = ('kind', 'key', 'ending', 'written')

    def text(self):
        return self.written


class Terms(nodes.Node):
    __slots__ = ('refs', 'written')
    FIELDS = ('refs', 'written')

    @property
    def children(self):
        return self.refs

    def text(self):
        return ', '.join(ref.written for ref in self.refs)


class Word(nodes.Node):
    __slots__ = ('problem', 'value')
    FIELDS = ('value', 'problem')

    def text(self):
        return 'true' if self.value else 'false'


class Problem(nodes.Node):
    __slots__ = ('message',)
    FIELDS = ('message',)

    def text(self):
        return f'<{self.message}>'


class Named(nodes.Node):
    __slots__ = ('args', 'function', 'named')
    FIELDS = ('function', 'args', 'named')

    @property
    def children(self):
        return (*self.args, *(value for _, value in self.named))

    def text(self):
        written = [nodes.text(arg) for arg in self.args]
        for name, value in self.named:
            # An argument with no name is the form with two stars.
            written.append(f'**{nodes.text(value)}' if name is None else f'{name}={nodes.text(value)}')
        return f'{self.function}({", ".join(written)})'


def ref(entity, member, written):
    return nodes.made(Ref, entity, member, written)


def event_ref(kind, key, ending, written):
    return nodes.made(EventRef, kind, key, ending, written)


def terms(refs, written=None):
    return nodes.made(Terms, tuple(refs), written)


def word(value, problem=None):
    return nodes.made(Word, value, problem)


def problem(message):
    return nodes.made(Problem, message)


def named(function, args, named):
    """The call of the function `function` with the nodes `args` by position and the pairs `named`
    (a name and a node) by name, each in its order."""
    return nodes.made(Named, function, tuple(args), tuple((name, value) for name, value in named))


class _Deeper:
    """The place of an argument with a name in the walk of `breadth_first`. Python's tree holds such
    an argument in a part of its own, so the argument is one level deeper than an argument by
    position. When the walk takes this place out, it puts the argument at the back."""

    __slots__ = ('node',)

    def __init__(self, node):
        self.node = node


def breadth_first(node):
    """Each node of a resolved expression, level by level: the node, then its parts, then their
    parts. An argument with a name is one level deeper than an argument by position, as it is in
    Python's tree of the call. A part outside the language gives the nodes of the expressions inside
    it too, each at the level that it has in Python's tree of the part. So the nodes come in the order
    in which Python's `ast.walk` gives the parts of the tree that the resolver made."""
    pending = deque([node])
    while pending:
        found = pending.popleft()
        if isinstance(found, _Deeper):
            pending.append(found.node)
            continue
        if isinstance(found, ast.expr):
            found = of_tree(found)
        if not isinstance(found, nodes.Node):
            # A part of Python's tree that is no expression: an argument with a name, an operator.
            pending.extend(ast.iter_child_nodes(found))
            continue
        yield found
        if isinstance(found, nodes.Foreign):
            pending.extend(ast.iter_child_nodes(found.tree))
        elif isinstance(found, Named):
            pending.extend(found.args)
            pending.extend(_Deeper(value) for _, value in found.named)
        else:
            pending.extend(found.children)


def of_tree(tree):
    """The typed nodes of a tree that the resolver made: Python's tree of an expression of a file, with
    the resolver's own nodes in the places of its names. A typed node is given back as it is."""
    if isinstance(tree, nodes.Node):
        return tree
    if isinstance(tree, semantic.Ref):
        return ref(tree.entity, tree.member, tree.written)
    if isinstance(tree, semantic.EventRef):
        return event_ref(tree.kind, tree.key, tree.ending, tree.written)
    if isinstance(tree, semantic.Terms):
        return terms((of_tree(item) for item in tree.refs), getattr(tree, 'written', None))
    if isinstance(tree, semantic.Word):
        return word(tree.value, tree.problem)
    if isinstance(tree, semantic.Problem):
        return problem(tree.message)
    if isinstance(tree, ast.Name):
        return nodes.ref(tree.id)
    if isinstance(tree, ast.Constant):
        return nodes.const(tree.value)
    if isinstance(tree, ast.IfExp):
        return nodes.if_else(of_tree(tree.test), of_tree(tree.body), of_tree(tree.orelse))
    if isinstance(tree, ast.BoolOp):
        return nodes.boolean('and' if isinstance(tree.op, ast.And) else 'or', map(of_tree, tree.values))
    if isinstance(tree, ast.UnaryOp) and type(tree.op) in nodes.UNARY:
        return nodes.unary(nodes.UNARY[type(tree.op)], of_tree(tree.operand))
    if isinstance(tree, ast.Compare) and all(type(op) in nodes.COMPARE for op in tree.ops):
        ops = [nodes.COMPARE[type(op)] for op in tree.ops]
        return nodes.compare(ops, map(of_tree, (tree.left, *tree.comparators)))
    if isinstance(tree, ast.BinOp) and type(tree.op) in nodes.BINARY:
        return nodes.binary(nodes.BINARY[type(tree.op)], of_tree(tree.left), of_tree(tree.right))
    if isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name):
        if not tree.keywords:
            return nodes.call(tree.func.id, map(of_tree, tree.args))
        pairs = ((keyword.arg, of_tree(keyword.value)) for keyword in tree.keywords)
        return named(tree.func.id, map(of_tree, tree.args), pairs)
    return nodes.foreign(tree)
