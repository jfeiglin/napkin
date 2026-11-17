"""The typed nodes of a resolved expression (`napkin/model/resolved.py`).

The oracle is Python's own walk of the tree that the nodes are made from: `ast.walk` gives the parts
of a tree level by level, and the walk of the nodes must give the leaves that the resolver made in
that order.

A call with arguments by name is one node (`Named`). The oracle of its parts is the node that the
functions of the nodes make for each part, and the oracle of its text is Python's own writer of the
tree of the call.
"""

import ast
import copy
import pickle
import random

import pytest

from napkin.core import expr as typed
from napkin.model import resolved, semantic


def name(text):
    return ast.Name(id=text, ctx=ast.Load())


def leaf(rng):
    kind = rng.randrange(7)
    if kind == 0:
        return semantic.Ref(entity=rng.choice(['A', 'B', None]), member=rng.choice('xyz'), written='w')
    if kind == 1:
        return semantic.EventRef(kind='trigger', key=rng.choice(['A.e', 'B.f']), ending=None, written='e')
    if kind == 2:
        return semantic.Problem(message=rng.choice(['no such name', 'cannot read']))
    if kind == 3:
        return semantic.Word(value=rng.random() < 0.5, problem='unknown name')
    if kind == 4:
        return name(rng.choice(['t', 'u']))
    if kind == 5:
        members = [semantic.Ref(entity='C', member=str(i), written='c') for i in range(rng.randrange(3))]
        return ast.Call(func=name('sum'), args=[semantic.Terms(refs=members)], keywords=[])
    return ast.Constant(value=rng.choice([1, 2.5, True]))


def tree(rng, depth):
    """A tree as the resolver makes one: parts of the language, a call with an argument by name, and
    parts outside the language (a list in brackets, a test of membership, an index), with the
    resolver's leaves."""
    if depth == 0 or rng.random() < 0.2:
        return leaf(rng)
    part = lambda: tree(rng, depth - 1)  # noqa: E731
    kind = rng.randrange(10)
    if kind == 0:
        return ast.BinOp(left=part(), op=rng.choice([ast.Add, ast.Mult, ast.Div])(), right=part())
    if kind == 1:
        return ast.UnaryOp(op=rng.choice([ast.USub, ast.Not])(), operand=part())
    if kind == 2:
        return ast.BoolOp(op=rng.choice([ast.And, ast.Or])(), values=[part(), part(), part()])
    if kind == 3:
        return ast.Compare(left=part(), ops=[ast.Lt(), ast.GtE()], comparators=[part(), part()])
    if kind == 4:
        return ast.IfExp(test=part(), body=part(), orelse=part())
    if kind == 5:
        return ast.Call(func=name('max'), args=[part(), part()], keywords=[])
    if kind == 6:
        # An argument with a name is one level deeper in Python's tree.
        return ast.Call(func=name('normal'), args=[part()], keywords=[ast.keyword(arg='max', value=part())])
    if kind == 7:
        return ast.List(elts=[part(), part()], ctx=ast.Load())
    if kind == 8:
        return ast.Compare(left=part(), ops=[ast.In()], comparators=[part()])
    return ast.Subscript(value=part(), slice=part(), ctx=ast.Load())


def seen_in_tree(made):
    found = []
    for part in ast.walk(made):
        if isinstance(part, semantic.Ref):
            found.append(('value', part.entity, part.member))
        elif isinstance(part, semantic.EventRef):
            found.append(('event', part.key))
        elif isinstance(part, semantic.Problem):
            found.append(('problem', part.message))
        elif isinstance(part, semantic.Word):
            found.append(('word', part.value))
        elif isinstance(part, ast.Name) and part.id in ('t', 'u'):
            found.append(('name', part.id))
    return found


def seen_in_nodes(node):
    found = []
    for part in resolved.breadth_first(node):
        if isinstance(part, resolved.Ref):
            found.append(('value', part.entity, part.member))
        elif isinstance(part, resolved.EventRef):
            found.append(('event', part.key))
        elif isinstance(part, resolved.Problem):
            found.append(('problem', part.message))
        elif isinstance(part, resolved.Word):
            found.append(('word', part.value))
        elif isinstance(part, typed.Ref) and part.name in ('t', 'u'):
            found.append(('name', part.name))
    return found


def test_the_walk_of_the_nodes_gives_the_leaves_in_the_order_of_pythons_walk_of_the_tree():
    rng = random.Random(20261112)
    outside = with_names = 0
    for _ in range(400):
        made = tree(rng, 4)
        node = resolved.of_tree(made)
        parts = list(resolved.breadth_first(node))
        outside += any(isinstance(part, typed.Foreign) for part in parts)
        with_names += any(isinstance(part, resolved.Named) for part in parts)
        assert seen_in_nodes(node) == seen_in_tree(made)
    # The property is about the parts outside the language too: most of the trees hold one. It is
    # about the calls with an argument by name too: many of the trees hold one.
    assert outside > 200
    assert with_names > 150


def test_an_argument_with_a_name_is_one_level_deeper_than_an_argument_without():
    """Python's tree holds an argument with a name inside a part of its own, so its leaves come after
    the leaves of the level of the other arguments. A walk that put both at one level would give the
    two in the other order."""
    late = semantic.Ref(entity='A', member='late', written='A.late')
    early = semantic.Ref(entity='B', member='early', written='B.early')
    call = ast.Call(
        func=name('normal'),
        args=[ast.BinOp(left=early, op=ast.Add(), right=ast.Constant(value=1))],
        keywords=[ast.keyword(arg='max', value=late)],
    )
    assert seen_in_nodes(resolved.of_tree(call)) == [('value', 'B', 'early'), ('value', 'A', 'late')]
    flat = ast.Call(
        func=name('normal'), args=[ast.Constant(value=1)], keywords=[ast.keyword(arg='max', value=late)]
    )
    both = ast.Call(func=name('max'), args=[flat, early], keywords=[])
    assert seen_in_nodes(resolved.of_tree(both)) == [('value', 'B', 'early'), ('value', 'A', 'late')]


def test_a_part_outside_the_language_that_holds_a_sum_over_nothing_has_its_nodes():
    """A sum over nothing has no leaf, so the walk of the leaves does not show it. A part outside the
    language gives it, and so does a call with an argument by name."""

    def nothing():
        return ast.Call(func=name('sum'), args=[semantic.Terms(refs=[])], keywords=[])

    listed = resolved.of_tree(ast.List(elts=[nothing()], ctx=ast.Load()))
    called = resolved.of_tree(
        ast.Call(
            func=name('normal'),
            args=[nothing()],
            keywords=[ast.keyword(arg='max', value=ast.Constant(value=3))],
        )
    )
    assert isinstance(listed, typed.Foreign) and isinstance(called, resolved.Named)
    for node in (listed, called):
        inside = [part for part in resolved.breadth_first(node) if isinstance(part, resolved.Terms)]
        assert len(inside) == 1 and inside[0].refs == ()


# ---- a call with arguments by name ----------------------------------------------------------------


def by_name(function, args, named):
    """Python's tree of a call with arguments by position and by name, as the resolver makes it."""
    return ast.Call(
        func=name(function),
        args=list(args),
        keywords=[ast.keyword(arg=key, value=value) for key, value in named],
    )


def a_ref(member):
    return semantic.Ref(entity='A', member=member, written=f'A.{member}')


def test_a_call_with_arguments_by_name_is_one_node_with_its_parts():
    """The oracle of each part is the node that the functions of the nodes make, not `of_tree`."""
    mean = ast.BinOp(left=a_ref('x'), op=ast.Add(), right=ast.Constant(value=1))
    made = resolved.of_tree(
        by_name('normal', [mean, ast.Constant(value=2)], [('min', a_ref('low')), ('max', name('t'))])
    )
    x, low = resolved.ref('A', 'x', 'A.x'), resolved.ref('A', 'low', 'A.low')
    assert type(made) is resolved.Named and resolved.Named.FIELDS == ('function', 'args', 'named')
    assert made.function == 'normal'
    # Two nodes are equal only when they are one object.
    assert made.args == (typed.binary('add', x, typed.const(1)), typed.const(2))
    assert [key for key, _ in made.named] == ['min', 'max']
    assert made.named[0][1] is low and made.named[1][1] is typed.ref('t')
    # The parts of the node: the arguments by position first, then the arguments by name.
    assert made.children == (*made.args, low, typed.ref('t'))


def test_two_calls_with_arguments_by_name_that_are_written_the_same_are_one_object():
    def tree():
        return by_name('uniform', [a_ref('x')], [('max', ast.Constant(value=3))])

    made = resolved.of_tree(tree())
    assert resolved.of_tree(tree()) is made
    assert resolved.named('uniform', [resolved.ref('A', 'x', 'A.x')], [('max', typed.const(3))]) is made
    # A node pickles to itself in one process, and a copy of a node is the node.
    assert pickle.loads(pickle.dumps(made)) is made
    assert copy.deepcopy(made) is made
    # Another function, another argument, another name or another place of an argument is another call.
    x, three = resolved.ref('A', 'x', 'A.x'), typed.const(3)
    others = [
        resolved.named('normal', [x], [('max', three)]),
        resolved.named('uniform', [three], [('max', three)]),
        resolved.named('uniform', [x], [('min', three)]),
        resolved.named('uniform', [x], [('max', x)]),
        resolved.named('uniform', [x, three], []),
        resolved.named('uniform', [], [('min', x), ('max', three)]),
        typed.call('uniform', [x, three]),
    ]
    assert all(other is not made for other in others)
    assert len({id(other) for other in others}) == len(others)


def test_the_order_of_the_arguments_by_name_is_kept_and_is_a_part_of_the_identity():
    low, high = ast.Constant(value=1), ast.Constant(value=9)
    first = resolved.of_tree(by_name('uniform', [], [('min', low), ('max', high)]))
    second = resolved.of_tree(by_name('uniform', [], [('max', high), ('min', low)]))
    assert [key for key, _ in first.named] == ['min', 'max']
    assert [key for key, _ in second.named] == ['max', 'min']
    assert first is not second
    assert dict(first.named) == dict(second.named)  # the same arguments, in another order


@pytest.mark.parametrize(
    'written',
    [
        'normal(t, 2, min=u, max=3)',
        'normal(min=t)',
        'uniform(t + 1, max=u * 2 if t else 3)',
        "lognormal(median=q(6, 'h'), gsd=1.5)",
        'max(normal(1, sd=-t), u)',
        'normal(t, max=(u, 1))',
        'normal(t, **u)',
    ],
)
def test_the_text_of_a_call_with_arguments_by_name_is_the_text_that_python_writes(written):
    """The oracle is Python's own writer of its tree of the call."""
    tree = ast.parse(written, mode='eval').body
    assert typed.text(resolved.of_tree(tree)) == ast.unparse(tree) == written


def test_a_call_of_something_that_is_no_name_and_a_form_that_the_language_lacks_stay_outside():
    inner = ast.Call(func=name('max'), args=[a_ref('x')], keywords=[])
    outside = [
        ast.Call(func=inner, args=[a_ref('y')], keywords=[]),
        ast.Call(func=inner, args=[], keywords=[ast.keyword(arg='max', value=a_ref('y'))]),
        ast.Call(
            func=ast.Attribute(value=name('t'), attr='normal', ctx=ast.Load()),
            args=[],
            keywords=[ast.keyword(arg='max', value=a_ref('y'))],
        ),
        ast.List(elts=[a_ref('x')], ctx=ast.Load()),
        ast.Subscript(value=a_ref('x'), slice=ast.Constant(value=0), ctx=ast.Load()),
    ]
    for tree in outside:
        assert type(resolved.of_tree(tree)) is typed.Foreign
    # A call of a name is a node of the language, with arguments by name or without.
    assert type(resolved.of_tree(inner)) is typed.Call
    assert type(resolved.of_tree(by_name('max', [], [('max', a_ref('y'))]))) is resolved.Named


def test_the_nodes_of_a_node_are_the_node():
    made = resolved.of_tree(
        ast.BinOp(left=semantic.Ref(entity='A', member='x', written='A.x'), op=ast.Add(), right=name('t'))
    )
    assert resolved.of_tree(made) is made
