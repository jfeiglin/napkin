"""The value of an expression (`napkin/core/evaluation.py`).

The function of a node is checked against an interpreter that this file writes: it walks the node and
computes each part with Python's own operations, by the rules of the module (each value that a part
gives is finite and real; a choice, `and` and `or` compute only what they need; a name with no value
fails when it is reached). The two must give the same value of the same type, bit for bit, or both
fail. A program with known values must give what the function gives with those values in the
environment. A consumer's table is whole.
"""

import math
import random

import pytest

from napkin import expressions
from napkin.core import evaluation, expr, ops
from napkin.core.errors import ExpressionError
from tests.core.reference import FAILURES, ONE, ORDER, SCALES, UNITS, outcome, walked

NAMES = ('p.a', 'p.b', 'x.s', 'x.t', 'flag', 'm.mode', 'nowhere')
NUMBERS = (0, 1, 2, 3, 0.5, -1, 10, 1e-300, 1e300, 1e308, 7.25, 1000, 0.0, -0.0, 4.5, -2.5)


def leaf(rng):
    r = rng.random()
    if r < 0.45:
        return expr.ref(rng.choice(NAMES))
    if r < 0.5:
        return expr.const(rng.choice(('open', 'shut', True, False)))
    return expr.const(rng.choice(NUMBERS))


def made(rng, depth):
    """A random node of the language, made by the functions of `expr` and not from a text."""
    if depth == 0 or rng.random() < 0.15:
        return leaf(rng)
    a, b, c = (made(rng, depth - 1) for _ in range(3))
    k = rng.randrange(20)
    if k < 5:
        return expr.binary(rng.choice(('add', 'sub', 'mul', 'div', 'pow')), a, b)
    if k == 5:
        return expr.binary('pow', a, expr.const(rng.choice((2, 0.5, -1, 3, 2000))))
    if k == 6:
        return expr.unary(rng.choice(('neg', 'pos', 'not')), a)
    if k == 7:
        return expr.call(rng.choice(sorted(ONE)), [a])
    if k == 8:
        return expr.call(rng.choice(('min', 'max', 'sum')), [a, b, c][: rng.randrange(1, 4)])
    if k == 9:
        return expr.call('clip', [a, b, c])
    if k == 10:
        return expr.call('q', [a, expr.const(rng.choice(('h', 'days')))])
    if k < 13:
        return expr.compare([rng.choice(sorted(ORDER))], [a, b])
    if k == 13:
        return expr.compare([rng.choice(sorted(ORDER)), rng.choice(sorted(ORDER))], [a, b, c])
    if k == 14:
        return expr.boolean(rng.choice(('and', 'or')), [a, b, c][: rng.randrange(2, 4)])
    if k == 15:
        return expr.call(rng.choice(('any', 'all')), [a, b, c][: rng.randrange(1, 4)])
    return expr.if_else(a, b, c)


def environment(rng):
    env = {name: rng.choice((*NUMBERS, math.inf, math.nan)) for name in ('p.a', 'p.b', 'x.s', 'x.t')}
    env['flag'] = rng.choice((True, False, 0, 1))
    env['m.mode'] = rng.choice(('open', 'shut'))
    return env


def test_the_scales_of_the_units_of_this_file_are_those_of_the_registry():
    assert SCALES == {'h': 1.0, 'days': 24.0}
    for name, scale in SCALES.items():
        assert UNITS.parse_unit(name).scale == scale and type(UNITS.parse_unit(name).scale) is float


def test_the_function_of_a_node_gives_what_a_walk_of_the_node_gives():
    rng = random.Random(20261112)
    seen = {'fails': 0, 'values': 0}
    kinds = set()
    for _ in range(4000):
        node, env = made(rng, rng.randrange(1, 5)), environment(rng)
        want = outcome(lambda: walked(node, env))
        assert outcome(lambda: evaluation.value(node, env, UNITS)) == want, (expr.text(node), env)
        seen['fails' if want == ('fails',) else 'values'] += 1
        kinds |= {ops.operation_of(part) for part in expr.walk(node)}
        # A failure of the function is an error of an expression or one of Python's arithmetic.
    assert min(seen.values()) > 800, seen
    # Each operation of the language was in some node.
    assert kinds - {None} == set(ops.OPERATIONS)


def test_a_program_with_known_values_gives_what_the_function_gives():
    rng = random.Random(20261113)
    seen = {'fails': 0, 'values': 0}
    for _ in range(2500):
        formula, node, env = made(rng, 2), made(rng, rng.randrange(1, 5)), environment(rng)
        first = outcome(lambda: walked(formula, env))
        if first == ('fails',):
            continue  # a caller reports a formula that fails before any program runs
        reference = {**env, 'c.one': walked(formula, env)}
        reads = expr.binary('add', node, expr.ref('c.one')) if rng.random() < 0.5 else node
        want = outcome(lambda: walked(reads, reference))
        seen['fails' if want == ('fails',) else 'values'] += 1
        known = {name: value for name, value in env.items() if rng.random() < 0.6}
        program = evaluation.program([('c.one', formula)], [reads], constants=known, units=UNITS)
        written = dict(env)
        assert outcome(lambda: program(written, UNITS)[0]) == want, (
            expr.text(formula),
            expr.text(reads),
            known,
        )
        assert outcome(lambda: written['c.one']) == first
        # With no registry a quantity is converted when the program runs: the value is the same.
        late = evaluation.program([('c.one', formula)], [reads], constants=known)
        assert outcome(lambda: late(dict(env), UNITS)[0]) == want
    assert min(seen.values()) > 400, seen


def test_only_the_part_that_is_reached_is_computed():
    read = expr.read
    env = {'ok': True, 'no': False, 'zero': 0, 'x': 2.5}
    for source, want in (
        ('x if ok else 1 / zero', 2.5),
        ('1 / zero if no else x', 2.5),
        ('no and 1 / zero > 0', False),
        ('ok or missing.name > 0', True),
        ('x if ok else missing.name', 2.5),
        ('x if ok else zero % 2', 2.5),  # a part outside the language, not reached
        ('x if ok else exp(x, x)', 2.5),  # a wrong number of arguments, not reached
        ('zero > 1 > 1 / zero', False),  # a chain stops at the first link that fails to hold
    ):
        assert evaluation.value(read(source), env, UNITS) == want
    for source, message in (
        ('x if no else 1 / zero', 'division by zero'),
        ('ok and missing.name > 0', "Missing value for 'missing.name'"),
        ('x if no else zero % 2', 'Unsupported operator'),
        ('x if no else exp(x, x)', 'Invalid argument count for exp'),
        ('x if no else sinh(x)', 'Unsupported function'),
        ('x if no else [x]', 'Unsupported expression'),
        ('x * 1e308 * 10', 'nonfinite'),
        ('(0 - x) ** 0.5', 'non-real'),
        ('x ** 2000', 'Exponent exceeds supported magnitude 1024'),
        ('clip(x, 2, 1)', 'clip lower bound exceeds upper bound'),
    ):
        with pytest.raises(FAILURES, match=message):
            evaluation.value(read(source), env, UNITS)


def test_a_known_part_that_fails_stays_code_and_a_known_test_leaves_a_branch_out():
    read = expr.read
    known = {'p.zero': 0, 'p.flag': True, 'p.big': 1e308}
    program = evaluation.program([], [read('x if p.flag else 1 / p.zero')], constants=known)
    assert program({'x': 2.5}, UNITS) == (2.5,)
    assert '_power' not in evaluation.program_text([], [read('2 ** 10 + x')], constants=known)
    assert evaluation.program([], [read('2 ** 10 + x')], constants=known)({'x': 1}, UNITS) == (1025.0,)
    for source in ('1 / p.zero', 'p.big * 10', 'ln(p.zero)', 'x if not p.flag else p.big * p.big'):
        failing = evaluation.program([], [read(source)], constants=known)  # making it does not fail
        with pytest.raises(FAILURES):
            failing({'x': 1.0}, UNITS)


def test_the_functions_of_the_last_nodes_are_kept_and_no_more(monkeypatch):
    node = expr.read('kept.x + 1')
    assert evaluation.function(node) is evaluation.function(node)
    monkeypatch.setattr(evaluation, 'LIMIT', 8)
    nodes = [expr.binary('add', expr.ref('kept.x'), expr.const(k)) for k in range(40)]
    for k, each in enumerate(nodes):
        assert evaluation.value(each, {'kept.x': 1}, UNITS) == 1 + k
    assert len(evaluation._FUNCTIONS) <= 8
    # A node whose function was dropped gets a new one, with the same value.
    assert evaluation.value(nodes[0], {'kept.x': 1}, UNITS) == 1


def test_this_consumer_has_a_handler_for_each_operation():
    assert set(evaluation.TABLE) == set(ops.OPERATIONS)
    assert set(evaluation.COMPARISONS) == set(expr.COMPARE.values())
    # The names that the written code reads are there for each function of the language but `q`,
    # which the registry converts, `clip`, which has its own function, and the functions over the
    # members of a list: `sum` has its own function, and `any` and `all` are written as `or` and `and`.
    assert expr.FUNCTIONS - {'q', 'clip'} - expr.LISTED <= set(evaluation.RUNTIME)
    assert '_sum' in evaluation.RUNTIME


def test_the_text_entry_reads_a_number_as_the_constant_that_it_is():
    program = expressions.compile_program(
        [('c.n', -0.0), ('c.m', 3)], [expr.read('c.n'), expr.read('c.m * x'), 2.5, True]
    )
    env = {'x': 2}
    assert [outcome(lambda v=v: v) for v in program(env, UNITS)] == [
        (float, (-0.0).hex()),
        (int, 6),
        (float, (2.5).hex()),
        (bool, True),
    ]
    for bad in (math.inf, math.nan):
        with pytest.raises(ExpressionError, match='Nonfinite literal'):
            expressions.compile_program([], [bad])
    # A source that is no text and no number is an error of an expression, and so is its value.
    with pytest.raises(ExpressionError):
        expressions.evaluate(None, {}, UNITS)
    with pytest.raises(ExpressionError):
        expressions.evaluate(b'1 + 1', {}, UNITS)


# ---- a tree that is deeper than the code that Python reads ----------------------------------------------
#
# Python reads no code with more than 200 brackets one inside the other. The code of a deep node is
# written in parts (`_Writer.split`, `evaluation.SPLIT`). The oracle is the walk of the whole node.

MILD = (0.5, 1, 2, 3, 7.25, -2.5, 4.5, 0.1)


def tall(rng, height, mild=False):
    """A random node whose tree has at least `height` levels: a random node at the bottom, and at
    each level one more operation with it on one side and a small random node on the other. With
    `mild`, the numbers and the operations keep the value in range, so the node has a value."""

    def small():
        if not mild:
            return made(rng, 1)
        return (
            expr.ref(rng.choice(('p.a', 'p.b', 'x.s', 'x.t')))
            if rng.random() < 0.6
            else expr.const(rng.choice(MILD))
        )

    node = small() if mild else made(rng, 2)
    for _ in range(height):
        other, third = small(), small()
        k = rng.randrange(9)
        if k < 4:
            sides = (node, other) if rng.random() < 0.7 else (other, node)
            node = expr.binary(rng.choice(('add', 'sub') if mild else ('add', 'sub', 'mul', 'div')), *sides)
        elif k == 4:
            test = expr.compare(['lt'], [other, third]) if mild else other
            node = expr.if_else(test, node, third) if rng.random() < 0.5 else expr.if_else(test, third, node)
        elif k == 5:
            node = expr.call(rng.choice(('min', 'max')), [node, other])
        elif k == 6:
            node = expr.unary('neg', node)
        elif k == 7:
            node = expr.call('clip', [node, expr.const(-50), expr.const(60)])
        else:
            # A yes/no part in the middle of the tree: the level above it reads it as a number.
            node = expr.boolean(rng.choice(('and', 'or')), [expr.compare(['ge'], [other, third]), node])
            node = expr.if_else(node, other, third)
    return node


def mild_environment(rng):
    return {name: rng.choice(MILD) for name in ('p.a', 'p.b', 'x.s', 'x.t')}


def test_a_node_that_is_deeper_than_the_code_that_python_reads_gives_what_a_walk_of_it_gives():
    """The value of the function of a deep node, of the same type, bit for bit, and whether it
    fails, are those of the walk of the whole node: also where a choice, `and` or `or` leaves a
    part out that would fail."""
    rng = random.Random(20261114)
    seen = {'fails': 0, 'values': 0}
    for case in range(400):
        mild = case % 2 == 0
        node = tall(rng, rng.randrange(30, 160), mild)
        env = mild_environment(rng) if mild else environment(rng)
        assert expr.height(node) > evaluation.SPLIT
        want = outcome(lambda: walked(node, env))
        assert outcome(lambda: evaluation.value(node, env, UNITS)) == want, (expr.text(node)[:200], env)
        seen['fails' if want == ('fails',) else 'values'] += 1
    # Both kinds are there in number: a walk that fails, and a walk with a value.
    assert min(seen.values()) > 100, seen


@pytest.mark.parametrize('lean', [False, True])
def test_a_program_with_deep_nodes_gives_what_a_walk_of_them_gives(lean):
    """A program assigns a deep formula, assigns one of the names that the formula reads again,
    and gives two deep outputs that read both. Each value is that of the walk in the same order,
    with the values that the names have at that place: a part of one node is not the part of a
    later node that reads other values. Some names are known when the program is made.

    With `lean` the program has fewer checks: it gives the same values, and it fails where the
    walk fails."""
    rng = random.Random(20261115)
    seen = {'fails': 0, 'values': 0}
    for case in range(300):
        mild = case % 3 != 0
        env = mild_environment(rng) if mild else environment(rng)
        formula, second, first_output = (tall(rng, rng.randrange(20, 90), mild) for _ in range(3))
        shared = tall(rng, rng.randrange(26, 60), mild)  # the same deep part before and after `p.a` changes
        formula = expr.binary('add', formula, shared)
        outputs = [
            expr.binary('sub', first_output, expr.ref('c.one')),
            expr.binary('add', shared, expr.ref('p.a')),
        ]
        assignments = [('c.one', formula), ('p.a', second)]

        def reference():
            now = dict(env)
            for name, node in assignments:
                now[name] = walked(node, now)
            return tuple(walked(node, now) for node in outputs), now

        def exact(values):
            return tuple(
                (type(value), value.hex() if isinstance(value, float) else value) for value in values
            )

        want = outcome(lambda: exact(reference()[0]))
        seen['fails' if want == ('fails',) else 'values'] += 1
        known = {name: value for name, value in env.items() if rng.random() < 0.5}
        for write in (True, False):
            program = evaluation.program(
                assignments, outputs, constants=known, units=UNITS, write=write, lean=lean
            )
            written = dict(env)
            assert outcome(lambda: exact(program(written, UNITS))) == want, (case, write, known)
            if want != ('fails',) and write:
                assert exact(written[name] for name in ('c.one', 'p.a')) == exact(
                    reference()[1][name] for name in ('c.one', 'p.a')
                )
    assert min(seen.values()) > 60, seen


def depth_of_the_code(node, cut, top):
    """The operations one inside the other in the code of `top`, when each node of `cut` has code
    of its own: the code of a part goes down to a name, a number or such a node."""
    if node in cut and node is not top:
        return 0
    return 1 + max((depth_of_the_code(child, cut, top) for child in node.children), default=0)


def chain(height, bottom):
    node = bottom
    for _ in range(height - expr.height(bottom)):
        node = expr.call('min', [node, expr.ref('p.b')])
    return node


@pytest.mark.parametrize('first', [evaluation.SPLIT - 1, evaluation.SPLIT, evaluation.SPLIT + 1])
@pytest.mark.parametrize('second', [evaluation.SPLIT - 2, evaluation.SPLIT - 1, evaluation.SPLIT + 3])
@pytest.mark.parametrize(
    'above', [evaluation.SPLIT - 2, evaluation.SPLIT - 1, evaluation.SPLIT, 3 * evaluation.SPLIT]
)
def test_no_code_is_deeper_than_the_limit_whatever_the_form_of_the_tree(first, second, above):
    """A tree with two deep branches under a chain. A rule that cuts at each height that is a
    multiple of the limit leaves code of almost two times the limit here: the chain down to the
    place where the branches meet, and then the branch that is one level short of a cut. The parts
    are cut so that the code of the node, and that of each part, has no more than the limit. `min`
    has the most brackets of the operations, with every check."""
    left = chain(first, expr.ref('p.a'))
    right = chain(second, expr.ref('x.s'))
    node = chain(above + max(first, second) + 1, expr.binary('add', left, right))
    cut = set(evaluation._parts(node))
    assert cut
    for top in (node, *cut):
        assert depth_of_the_code(top, cut, top) <= evaluation.SPLIT
    # The parts come each after the parts under it.
    ordered = evaluation._parts(node)
    for place, part in enumerate(ordered):
        assert not {inner for inner in expr.walk(part) if inner in cut and inner is not part} - set(
            ordered[:place]
        )
    env = {'p.a': 3.5, 'p.b': 2.25, 'x.s': -1.5}
    assert evaluation.value(node, env, UNITS) == min(3.5, 2.25) + min(-1.5, 2.25) == walked(node, env)
    for lean in (False, True):
        assert evaluation.program([], [node], lean=lean)(env, UNITS) == (0.75,)


def towers():
    """For each place of each operation where a part can be: (a name, the node with `under` at
    that place). A tower is the same operation with itself at that place, level on level."""
    y, z = expr.ref('p.b'), expr.ref('x.s')
    found = {}
    for op in ('add', 'sub', 'mul', 'div', 'pow'):
        found[op, 0] = lambda under, op=op: expr.binary(op, under, y)
        found[op, 1] = lambda under, op=op: expr.binary(op, y, under)
    for op in ('neg', 'pos', 'not'):
        found[op, 0] = lambda under, op=op: expr.unary(op, under)
    for op in sorted(ORDER):
        found[op, 0] = lambda under, op=op: expr.compare([op], [under, y])
        found[op, 1] = lambda under, op=op: expr.compare([op, 'le'], [y, under, z])
    for op in ('and', 'or'):
        found[op, 1] = lambda under, op=op: expr.boolean(op, [y, under])
    found['if', 0] = lambda under: expr.if_else(under, y, z)
    found['if', 1] = lambda under: expr.if_else(y, under, z)
    found['if', 2] = lambda under: expr.if_else(z, y, under)
    for name in sorted(ONE):
        found[name, 0] = lambda under, name=name: expr.call(name, [under])
    for name in ('min', 'max', 'sum', 'any', 'all', 'clip'):
        for place in range(3):
            found[name, place] = lambda under, name=name, place=place: expr.call(
                name, [under if k == place else (y, z, y)[k] for k in range(3)]
            )
    found['q', 0] = lambda under: expr.call('q', [under, expr.const('h')])
    return found


def test_the_towers_of_this_file_have_each_operation():
    kinds = {
        ops.operation_of(part) for build in towers().values() for part in expr.walk(build(expr.ref('p.a')))
    }
    assert kinds - {None} == set(ops.OPERATIONS)


@pytest.mark.parametrize('place', sorted(towers(), key=str), ids=lambda place: f'{place[0]}-{place[1]}')
def test_a_tower_of_each_operation_is_code_that_python_reads(place):
    """The same operation level on level, with the part at one place: the code of one part is
    then the limit times the brackets of that operation, with every check and with few. Python
    reads it, and the value, or the failure, is that of the walk. A new operation needs a tower
    here (the test above)."""
    build = towers()[place]
    split = evaluation.SPLIT
    for height in (split - 1, split, split + 1, 2 * split - 1, 2 * split, 2 * split + 1, 5 * split + 3):
        for start, env in (
            (expr.ref('p.a'), {'p.a': 0.5, 'p.b': 1.25, 'x.s': 2.0}),
            (expr.ref('p.a'), {'p.a': 1, 'p.b': 1, 'x.s': 1}),
            (expr.const(True), {'p.b': 0.75, 'x.s': 3}),
        ):
            node = start
            for _ in range(height):
                node = build(node)
            want = outcome(lambda: walked(node, env))
            assert outcome(lambda: evaluation.value(node, env, UNITS)) == want, height
            for lean in (False, True):
                found = outcome(
                    lambda: evaluation.program([], [node], units=UNITS, lean=lean)(dict(env), UNITS)[0]
                )
                assert found == want, (height, lean)


@pytest.mark.parametrize('terms', [45, 200, 900, 6000])
def test_a_long_chain_of_operations_is_the_fold_of_its_terms_from_the_left(terms):
    """A sum that a flat structure writes member by member is a chain: `((a + b) - c) * d ...`. The
    function of the chain gives what the same operations give one after the other, from the left,
    on the same numbers: bit for bit. 45 terms were past what one function could hold. A program
    gives the same."""
    rng = random.Random(terms)
    names = [f'v.{k}' for k in range(terms)]
    env = {name: rng.choice((1 / 3, 0.1, 7 / 10, 2.5, 1e-3, 3.0)) for name in names}
    apply = {'add': lambda a, b: a + b, 'sub': lambda a, b: a - b, 'mul': lambda a, b: a * b}
    node, value = expr.ref(names[0]), env[names[0]]
    for name in names[1:]:
        op = rng.choice(('add', 'add', 'sub', 'mul'))
        value = apply[op](value, env[name])
        node = expr.binary(op, node, expr.ref(name))
        if abs(value) > 1e6:
            # Keep the fold away from an overflow: the test is of the order, not of the range.
            node, value = expr.binary('mul', node, expr.const(1e-6)), value * 1e-6
    found = evaluation.value(node, env, UNITS)
    assert type(found) is float and found.hex() == value.hex()
    for lean in (False, True):
        (again,) = evaluation.program([], [node], lean=lean)(env, UNITS)
        assert type(again) is float and again.hex() == value.hex()


def test_a_part_that_a_choice_leaves_out_is_not_computed_however_deep_it_is():
    """The branch that the test of a choice does not take is a chain of 300 terms that ends in a
    division by zero. With the test true the value is that of the other branch; with it false the
    chain is computed and fails. The same holds for the second term of `and` and of `or`."""
    chain = expr.ref('x')
    for _ in range(300):
        chain = expr.binary('add', chain, expr.ref('x'))
    failing = expr.binary('div', chain, expr.ref('zero'))
    choice = expr.if_else(expr.ref('flag'), expr.const(2.5), failing)
    both = expr.boolean(
        'and', [expr.unary('not', expr.ref('flag')), expr.compare(['gt'], [failing, expr.const(0)])]
    )
    either = expr.boolean('or', [expr.ref('flag'), expr.compare(['gt'], [failing, expr.const(0)])])
    taken = {'flag': True, 'x': 1.0, 'zero': 0.0}
    for compute in (
        lambda node, env: evaluation.value(node, env, UNITS),
        lambda node, env: evaluation.program([], [node])(dict(env), UNITS)[0],
        lambda node, env: evaluation.program([], [node], lean=True)(dict(env), UNITS)[0],
    ):
        assert compute(choice, taken) == 2.5
        assert compute(both, taken) is False and compute(either, taken) is True
        for node in (choice, both, either):
            with pytest.raises(FAILURES):
                compute(node, {**taken, 'flag': False})
        assert compute(choice, {'flag': False, 'x': 1.0, 'zero': 2.0}) == 301 / 2


@pytest.mark.parametrize(
    'levels', [evaluation.SPLIT - 2, evaluation.SPLIT - 1, evaluation.SPLIT, 2 * evaluation.SPLIT - 1]
)
def test_a_program_with_few_checks_checks_the_value_of_a_deep_part_where_it_could_be_hidden(levels):
    """A chain of sums of 1e308 is not finite from its first sum: its value is no value. `min`,
    a comparison, the test of a choice and `and` over it could hide that: `min(inf, 1)` is 1. The
    program with few checks leaves the check of a sum to its reader, and the reader of the chain
    is in other code than the chain here. The program fails, as the walk does."""
    chain = expr.ref('big')
    for _ in range(levels):
        chain = expr.binary('add', chain, expr.ref('big'))
    env = {'big': 1e308, 'one': 1.0}
    one = expr.ref('one')
    for reader in (
        expr.call('min', [chain, one]),
        expr.compare(['gt'], [chain, one]),
        expr.if_else(chain, one, one),
        expr.boolean('and', [chain, one]),
        expr.call('clip', [one, one, chain]),
        expr.binary('div', one, chain),
    ):
        node = reader
        for extra in range(3):
            # The reader is the node of the program, or it has operations over it.
            for _ in range(extra * evaluation.SPLIT // 2):
                node = expr.if_else(one, node, one)
            assert outcome(lambda: walked(node, env)) == ('fails',)
            for lean in (True, False):
                program = evaluation.program([], [node], lean=lean)
                assert outcome(lambda: program(dict(env), UNITS)[0]) == ('fails',), (
                    expr.text(node)[-60:],
                    lean,
                )
            assert outcome(lambda: evaluation.value(node, env, UNITS)) == ('fails',)
    # With a number in range the same programs have the value of the walk.
    small = {'big': 0.25, 'one': 1.0}
    node = expr.call('min', [chain, one])
    assert evaluation.program([], [node], lean=True)(small, UNITS) == (walked(node, small),)


def test_a_deep_part_of_known_values_is_computed_when_the_program_is_made():
    """A part that reads only known values is computed once, when the program is made, however
    deep it is: the program is the one whose node has the value of the part in its place. The
    value of an assignment of known values is known to the nodes after it."""
    known = {'k.a': 0.5, 'k.b': 3}
    deep = expr.ref('k.a')
    for step in range(3 * evaluation.SPLIT + 5):
        deep = (
            expr.binary('add', deep, expr.ref('k.b'))
            if step % 2
            else expr.call('min', [deep, expr.ref('k.b')])
        )
    value = walked(deep, known)
    reader = expr.binary('mul', expr.ref('x'), deep)
    again = expr.binary('mul', expr.ref('x'), expr.const(value))
    for lean in (False, True):
        with_part = evaluation.program_text([], [reader], constants=known, lean=lean)
        assert with_part == evaluation.program_text([], [again], lean=lean)
        assigned = evaluation.program_text(
            [('c.deep', deep)],
            [expr.binary('mul', expr.ref('x'), expr.ref('c.deep'))],
            constants=known,
            write=False,
            lean=lean,
        )
        assert assigned == with_part
    assert evaluation.program([], [reader], constants=known)({'x': 2.0}, UNITS) == (2.0 * value,)


def test_the_height_of_a_chain_is_found_with_no_call_for_each_level():
    """A chain of 20,000 operations is far deeper than the calls of Python go."""
    node = expr.ref('x')
    for _ in range(20000):
        node = expr.binary('add', node, expr.const(1))
    assert expr.height(node) == 20001 and expr.height(expr.ref('x')) == 1
    assert expr.height(node.left) == 20000
    assert evaluation.value(node, {'x': 0.5}, UNITS) == 20000.5


def test_a_name_that_a_program_assigns_again_has_its_last_value():
    """`a` is assigned, then assigned again from itself, and then two more names are assigned.
    Each later reader has the value of the assignment before it: (x + 1) * 2 + (x + 10)."""
    read = expr.read
    assignments = [('a', read('x + 1')), ('a', read('a * 2')), ('b', read('x + 10')), ('c', read('a + b'))]
    for write in (True, False):
        program = evaluation.program(assignments, [read('c'), read('a'), read('b')], write=write)
        env = {'x': 1.5}
        assert program(env, UNITS) == (16.5, 5.0, 11.5)
        assert env == ({'x': 1.5, 'a': 5.0, 'b': 11.5, 'c': 16.5} if write else {'x': 1.5})
