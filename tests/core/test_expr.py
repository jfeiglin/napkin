"""The typed nodes of an expression (`napkin/core/expr.py`).

A node read from a text writes the text that `ast.unparse` writes for Python's tree of it, and reads the
names that the present walker reads. Two texts give one node when, and only when, Python's trees of them
are the same: that is the identity that about twenty places of the code take from a text or from
`ast.dump` today. A constant is tagged by its type. A node cannot change, and it is the same object
after a pickle. A text that is outside the language is read, and keeps Python's tree of the part that
the language does not have.
"""

import ast
import gc
import pickle
import random
import threading

import pytest

from napkin import expressions
from napkin.core import expr
from napkin.core.errors import ExpressionError

NAMES = ('a', 'b', 'tank.level', 'tank.gate', 't', 'pool.cells_1.water__time')
TEXTS = ("'open'", "'it''s'".replace("''", "\\'"), '"say \\"no\\""', "'a\\\\b'", "'tab\\there'", "'né'")
NUMBERS = ('0', '1', '2', '0.5', '1.0', '1e-07', '2.5e+20', '1000000', 'True', 'False')
ONE = ('exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf', 'abs')


def written(choose, depth):
    """One random expression of the language, as text, with brackets and spaces as an author writes."""
    if depth == 0 or choose.random() < 0.15:
        return choose.choice((*NAMES, *NAMES, *NUMBERS, *TEXTS))
    kind = choose.choice(('unary', 'binary', 'binary', 'compare', 'bool', 'if', 'call', 'q', 'brackets'))

    def part():
        return written(choose, depth - 1)

    if kind == 'unary':
        return choose.choice(('-', '+', 'not ')) + part()
    if kind == 'binary':
        return f'{part()} {choose.choice(("+", "-", "*", "/", "**"))} {part()}'
    if kind == 'compare':
        ops = ('==', '!=', '<', '<=', '>', '>=')
        out = part()
        for _ in range(choose.choice((1, 1, 1, 2))):
            out += f' {choose.choice(ops)} {part()}'
        return out
    if kind == 'bool':
        joiner = choose.choice((' and ', ' or '))
        return joiner.join(part() for _ in range(choose.choice((2, 2, 3))))
    if kind == 'if':
        return f'{part()} if {part()} else {part()}'
    if kind == 'call':
        name = choose.choice((*ONE, 'min', 'max', 'clip'))
        count = 1 if name in ONE else 3 if name == 'clip' else choose.choice((1, 2, 3))
        return f'{name}({", ".join(part() for _ in range(count))})'
    if kind == 'q':
        return f'q({choose.choice(("2", "0.5", "-1", part()))}, {choose.choice(("'h'", "'people/day'"))})'
    return f'({part()})'


def corpus(count=600, seed=7):
    choose = random.Random(seed)
    found = []
    while len(found) < count:
        source = written(choose, choose.choice((1, 2, 3, 4)))
        try:
            ast.parse(source, mode='eval')
        except SyntaxError:
            continue  # two operators in a row that Python does not read
        found.append(source)
    return found


SOURCES = corpus()


def tree(source):
    return ast.parse(source, mode='eval').body


def test_the_corpus_has_each_kind_of_node_and_texts_that_are_not_canonical():
    kinds = {type(node) for source in SOURCES for node in expr.walk(expr.read(source))}
    assert kinds == {
        expr.Const,
        expr.Ref,
        expr.Unary,
        expr.Binary,
        expr.Compare,
        expr.BoolOp,
        expr.IfElse,
        expr.Call,
    }
    assert sum(ast.unparse(tree(source)) != source for source in SOURCES) > 50


def test_a_node_writes_the_text_that_python_writes_for_its_tree_and_reads_back_to_itself():
    for source in SOURCES:
        node = expr.read(source)
        assert expr.text(node) == ast.unparse(tree(source))
        assert expr.read(expr.text(node)) is node
        # Each part of the tree too.
        for part in ast.walk(tree(source)):
            if isinstance(part, ast.expr):
                inner = ast.unparse(part)
                assert expr.text(expr.read(inner)) == inner


def test_two_texts_give_one_node_when_and_only_when_their_trees_are_the_same():
    """Each part of each expression of the corpus, by the dump of Python's tree of it: one node for
    each tree, and one tree for each node."""
    parts = {}
    for source in SOURCES:
        for part in ast.walk(tree(source)):
            if isinstance(part, ast.expr):
                parts.setdefault(ast.dump(part), ast.unparse(part))
    nodes = {dump: expr.read(inner) for dump, inner in parts.items()}
    assert len({id(node) for node in nodes.values()}) == len(nodes) > 1000
    for dump, inner in parts.items():
        assert ast.dump(tree(inner)) == dump
    # Brackets and spaces are no part of the identity; the order and the grouping are.
    assert expr.read('(a)+( b )') is expr.read('a + b') is expr.read('a+b')
    assert expr.read('a + b') is not expr.read('b + a')
    assert expr.read('a - (b - c)') is not expr.read('a - b - c')
    assert expr.read('a < b < c') is not expr.read('a < b and b < c')


def test_a_constant_is_tagged_by_its_type():
    one, real, yes = expr.read('1'), expr.read('1.0'), expr.read('True')
    assert len({id(one), id(real), id(yes)}) == 3
    assert (one.value, real.value, yes.value) == (1, 1.0, True)
    assert [type(node.value) for node in (one, real, yes)] == [int, float, bool]
    assert expr.const(0.0) is not expr.const(-0.0) and expr.const(0.0) is expr.const(0.0)
    assert expr.const('1') is not expr.const(1)
    # A number that is given as a number is read as its text, as the present programs read it.
    assert expr.read(2.5) is expr.read('2.5') and expr.read(True) is yes
    assert expr.read(-1) is expr.read('-1') is expr.unary('neg', expr.const(1))


def tree_names(part):
    """The names that Python's tree of an expression reads, by a walk of that tree: a dotted name is
    one name, and the name of a function that is called is none."""
    if isinstance(part, ast.Name):
        return {part.id}
    if isinstance(part, ast.Attribute):
        inner = tree_names(part.value)
        if (
            isinstance(part.value, (ast.Name, ast.Attribute))
            and len(inner) == 1
            and not part.attr.startswith('_')
        ):
            return {f'{next(iter(inner))}.{part.attr}'}
        return inner
    children = part.args if isinstance(part, ast.Call) else ast.iter_child_nodes(part)
    return set().union(*map(tree_names, children))


def test_the_names_of_a_node_are_those_of_a_walk_of_pythons_tree():
    for source in SOURCES:
        assert (
            expr.names(expr.read(source))
            == tree_names(tree(source))
            == expressions.names_in(expr.read(source))
        )
    assert expr.names(expr.read('min(a, max(b, 2)) + exp(tank.level)')) == {'a', 'b', 'tank.level'}
    assert expr.names(expr.read('3 * 2')) == frozenset()


def test_a_node_cannot_change_and_is_the_same_object_after_a_pickle():
    for source in SOURCES[:100]:
        node = expr.read(source)
        assert pickle.loads(pickle.dumps(node)) is node
    node = expr.read('a + b * 2')
    for name in ('op', 'left', 'key', 'other'):
        with pytest.raises(AttributeError, match='cannot change'):
            setattr(node, name, None)
    assert isinstance(node.right.children, tuple) and node.children == (node.left, node.right)
    assert [type(part).__name__ for part in expr.walk(node)] == ['Binary', 'Ref', 'Binary', 'Ref', 'Const']


OUTSIDE = (
    'a is b',
    'a in (b, c)',
    'a // b',
    'a % 2',
    '~a',
    'a[0]',
    'f(a)',
    'min(a, key=b)',
    'lambda: a',
    '[a for a in b]',
    'a._hidden + 1',
    'a if b is c else min(d, e % 2)',
)


@pytest.mark.parametrize('source', OUTSIDE)
def test_a_text_outside_the_language_is_read_and_keeps_the_tree_of_what_the_language_lacks(source):
    node = expr.read(source)
    outside = [part for part in expr.walk(node) if isinstance(part, expr.Foreign)]
    # Each part keeps its tree: that tree, written and read again, is the same part.
    assert outside and all(
        expr.foreign(ast.parse(ast.unparse(part.tree), mode='eval').body) is part for part in outside
    )
    # The names are those of the present walker, and the node is one object for one tree.
    assert expr.names(node) == tree_names(tree(source))
    assert expr.read(ast.unparse(tree(source))) is node and pickle.loads(pickle.dumps(node)) is node
    assert isinstance(expr.text(node), str)


def test_a_text_over_the_limits_is_not_read():
    assert (expr.LONGEST, expr.LARGEST) == (10000, 1000)
    long = ' + '.join(['a'] * 5000)
    assert len(long) > expr.LONGEST
    with pytest.raises(ExpressionError, match='exceeds 10000 characters'):
        expr.read(long)
    deep = ' + '.join(['a'] * 600)
    assert len(deep) < expr.LONGEST and sum(1 for _ in ast.walk(tree(deep))) > expr.LARGEST
    with pytest.raises(ExpressionError, match='complexity budget'):
        expr.read(deep)
    # The limit counts each part of Python's tree: a call with 498 names has 999 parts, and one with
    # 499 has 1,001. A reader of the form alone reads a text over the limit.
    most, over = (f'min({", ".join(["a"] * count)})' for count in (498, 499))
    assert [sum(1 for _ in ast.walk(tree(text))) for text in (most, over)] == [999, 1001]
    assert expr.read(most) is expr.parse(most)
    with pytest.raises(ExpressionError, match='complexity budget'):
        expr.read(over)
    assert expr.names(expr.parse(over)) == {'a'}
    with pytest.raises(SyntaxError):
        expr.read('a +')


def chains(levels):
    """Texts with `levels` operations one inside the other, each under the limit of parts for the
    numbers of levels of the test below."""
    yield ' + '.join(['a'] * levels)  # the sum of `levels` names: its tree leans to the left
    yield 'a + (' * (levels - 1) + 'a' + ')' * (levels - 1)
    yield 'not ' * (levels - 1) + 'a'
    yield '-' * (levels - 1) + 'a'


def test_a_text_that_is_deeper_than_the_readers_go_is_not_read():
    """The readers of an expression go down its tree with calls, so there is a deepest tree. A text
    with that many operations one inside the other is read, and its height is that number. One
    level more is over the limit for each reader, also for the reader of the form alone: nothing
    can go down the node that it would give. Brackets alone make no level."""
    for text in chains(expr.DEEPEST):
        assert sum(1 for _ in ast.walk(tree(text))) < expr.LARGEST
        assert expr.height(expr.read(text)) == expr.DEEPEST
        assert expr.parse(text) is expr.read(text)
    for levels in (expr.DEEPEST + 1, expr.DEEPEST + 40):
        for text in chains(levels):
            assert sum(1 for _ in ast.walk(tree(text))) < expr.LARGEST and len(text) < expr.LONGEST
            for reader in (expr.read, expr.parse):
                with pytest.raises(ExpressionError, match='complexity budget'):
                    reader(text)
    # A chain that Python's own reader, or the reader of its tree, cannot go down at all.
    for text in (' + '.join(['a'] * 6000), 'not ' * 3000 + 'a'):
        with pytest.raises(ExpressionError, match='complexity budget'):
            expr.parse(text)
    wrapped = '(' * 150 + 'a + a' + ')' * 150
    assert expr.height(expr.read(wrapped)) == 2


def test_the_height_of_a_node_is_one_more_than_that_of_its_highest_part():
    a, b = expr.ref('a'), expr.ref('b')
    assert expr.height(a) == expr.height(expr.const(2.5)) == 1
    low = expr.binary('add', a, b)
    high = expr.unary('neg', expr.call('min', [low, a]))
    assert [expr.height(node) for node in (low, high)] == [2, 4]
    assert expr.height(expr.if_else(a, high, low)) == 5
    assert expr.height(expr.if_else(high, a, low)) == 5
    assert expr.height(expr.if_else(a, low, high)) == 5
    assert expr.height(expr.compare(['lt', 'le'], [a, low, high])) == 5
    assert expr.height(expr.boolean('or', [low, high, a])) == 5
    assert expr.height(expr.call('clip', [a, b, high])) == 5


def test_a_source_that_is_no_text_and_no_number_is_not_read():
    for source in (None, b'a + b', ['a'], ('a', 'b'), {'a': 1}, 2 + 1j):
        with pytest.raises(TypeError, match='an expression is a text or a number'):
            expr.read(source)


def test_a_node_that_nothing_holds_is_released_and_two_live_nodes_of_one_key_are_one_object():
    def alive():
        gc.collect()
        return len(expr._NODES)

    before = alive()
    held = [expr.binary('add', expr.ref(f'released.{k}'), expr.const(k + 0.0123)) for k in range(500)]
    assert alive() == before + 1500  # each sum, its reference and its constant
    # A node that is held is the node of its key, whichever way it is asked for.
    assert all(
        expr.binary('add', expr.ref(f'released.{k}'), expr.const(k + 0.0123)) is held[k] for k in range(500)
    )
    assert pickle.loads(pickle.dumps(held[7])) is held[7]
    # A part lives while the node that it is a part of lives.
    part = held[3].left
    del held
    assert alive() == before + 1 and part is expr.ref('released.3')
    del part
    assert alive() == before


def test_the_nodes_of_the_last_texts_are_kept_and_no_more():
    assert expr._read.cache_info().maxsize == expr.READ
    node = expr.read('kept.a * kept.b')
    hits = expr._read.cache_info().hits
    assert expr.read('kept.a * kept.b') is node and expr._read.cache_info().hits == hits + 1
    # A text that cannot be read is not kept: it is an error each time.
    for _ in range(2):
        with pytest.raises(SyntaxError):
            expr.read('kept.a *')


def test_threads_that_ask_for_one_new_node_get_one_object():
    found, start = [], threading.Barrier(8)

    def ask(k):
        start.wait()
        nodes = [expr.binary('mul', expr.ref(f'thread.{n}'), expr.const(n)) for n in range(300)]
        found.append(nodes)

    threads = [threading.Thread(target=ask, args=(k,)) for k in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(found) == 8
    for nodes in found[1:]:
        assert all(a is b for a, b in zip(nodes, found[0]))


class Members(ast.expr):
    """A kind of node of another module, as the resolver has: Python knows no types of its fields."""

    _fields = ('refs',)


def held(refs):
    return ast.Tuple(elts=[Members(refs=refs), ast.Constant(value=1)], ctx=ast.Load())


def test_a_part_outside_the_language_that_holds_an_empty_list_of_another_kind_has_one_node():
    node = expr.foreign(held([]))
    assert node is expr.foreign(held([]))
    assert node is not expr.foreign(held([ast.Constant(value=2)]))
    assert node is not expr.foreign(ast.Tuple(elts=[ast.Constant(value=1)], ctx=ast.Load()))


# ---- the limits of size of the text of a node ------------------------------------------------------


def deepest(node):
    """The number of levels of a node: 1 for a node with no part. With a list and not with calls."""
    most, pending = 0, [(node, 1)]
    while pending:
        part, level = pending.pop()
        most = max(most, level)
        pending += [(child, level + 1) for child in part.children]
    return most


def refused_as_a_text(written):
    """Why the check of an expression refused an expression when it took its text, or None. This is
    the rule of that check, written again from the text: at most 10,000 characters; a text that Python
    reads; at most 1,000 parts of Python's tree of it, the tree of the whole text with them; and at
    most 150 operations one inside the other in the node that the text reads to."""
    if len(written) > 10000:
        return 'Expression exceeds 10000 characters'
    try:
        whole = ast.parse(written, mode='eval')
    except (SyntaxError, RecursionError) as exc:
        return f'Invalid expression: {exc}'
    if sum(1 for _ in ast.walk(whole)) > 1000:
        return 'Expression exceeds complexity budget'
    try:
        node = expr.of_tree(whole.body)
    except RecursionError:
        return 'Expression exceeds complexity budget'
    return 'Expression exceeds complexity budget' if deepest(node) > 150 else None


def refused_as_a_node(node):
    try:
        found = expr.limited(node)
    except ExpressionError as exc:
        return str(exc)
    assert found is node
    return None


def near_the_limits():
    """Nodes on each side of each limit: a sum of two long names, a call with many constants (two
    levels deep), and chains of operations one inside the other."""
    for size in range(4995, 5001):
        yield expr.binary('add', expr.ref('x' * size), expr.ref('y' * size))
        yield expr.const('w' * (2 * size))
    for count in range(990, 1001):
        yield expr.call('max', [expr.const(1)] * count)
        yield expr.call('min', [expr.ref('a')] * (count // 2))
    for levels in range(146, 156):
        neg, negated, called, powers, added = (expr.ref('a'),) * 5
        for _ in range(levels):
            neg = expr.unary('neg', neg)
            negated = expr.unary('not', negated)
            called = expr.call('abs', [called])
            powers = expr.binary('pow', expr.ref('b'), powers)
            added = expr.binary('add', added, expr.const(2.5))
        yield from (neg, negated, called, powers, added)
    # Deeper than any reader goes, and texts that Python cannot read.
    yield expr.unary('neg', expr.binary('mul', expr.ref('a'), expr.const(-1)))
    deep = expr.ref('a')
    for _ in range(400):
        deep = expr.unary('neg', deep)
    yield deep
    yield from (expr.ref('lambda'), expr.ref('a b'), expr.ref('1x'), expr.ref('True'))
    yield from (expr.const(-0.0), expr.const(float('nan')), expr.const(float('-inf')), expr.const(-3))


def test_the_limits_of_a_node_are_those_of_the_check_of_its_text():
    """`expr.limited` refuses a node exactly when the check of an expression refused the text of the
    node, with the same reason: for random nodes of the language, for the nodes of random texts, and
    for nodes on each side of each limit."""
    from tests.core.test_evaluation import made

    rng = random.Random(20261114)
    nodes = [made(rng, rng.randrange(1, 6)) for _ in range(2000)]
    nodes += [expr.read(source) for source in SOURCES]
    nodes += [expr.read(source) for source in OUTSIDE]
    nodes += list(near_the_limits())
    reasons = []
    for node in nodes:
        want = refused_as_a_text(expr.text(node))
        assert refused_as_a_node(node) == want, expr.text(node)[:200]
        reasons.append(want and want.split(':')[0])
    # Each limit refuses some of the nodes, and each takes some near it.
    found = set(reasons)
    assert {
        None,
        'Expression exceeds 10000 characters',
        'Expression exceeds complexity budget',
        'Invalid expression',
    } <= found
    assert reasons.count(None) > 2000


def test_a_node_counts_the_parts_of_its_text_once(monkeypatch):
    node = expr.read('min(a.b, 2) + -c * (d if e else 3)')
    assert expr.parts(node) == sum(1 for _ in ast.walk(tree(expr.text(node))))
    read = []
    parse = ast.parse
    monkeypatch.setattr(ast, 'parse', lambda *args, **kwargs: read.append(args) or parse(*args, **kwargs))
    for _ in range(3):
        expr.limited(node)
        expr.parts(node)
    assert read == []
    fresh = expr.binary('add', node, expr.const(11.125))
    expr.limited(fresh)
    expr.limited(fresh)
    assert len(read) == 1
