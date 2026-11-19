"""The values of an expression for many instances at once (`napkin/core/arrays.py`).

The oracle is the tests' own walk of a node for one instance (`reference.walked`): the values of an
array are, instance by instance, what that walk gives, and the call fails when the walk fails for one
instance. The walk reads only the branch that an instance takes, so the tests cover the branches that
would fail for the instances that do not take them.

The claim is for expressions with a number where a number goes, a yes/no where a condition goes, and
a text compared with a text: the kinds that the rules for units accept. Python gives a text times a
yes/no a value, and takes a yes/no as a number; no model has such an expression, and the arrays make
no claim for one. So the test makes its nodes by kind.
"""

import math
import random

import numpy as np
import pytest

from napkin.core import arrays, expr, ops
from napkin.core.errors import ExpressionError
from tests.core.reference import UNITS, outcome, walked
from tests.core.test_evaluation import NAMES, NUMBERS

COUNT = 6
NUMERIC = [name for name in NAMES if name not in ('flag', 'm.mode')]
ONE = ('abs', 'sqrt', 'exp', 'expm1', 'ln', 'log1p', 'erf')
ORDER = ('lt', 'le', 'gt', 'ge', 'eq', 'ne')


def number(rng, depth):
    """A node that gives a number, made of parts of the right kinds."""
    if depth == 0 or rng.random() < 0.2:
        return expr.ref(rng.choice(NUMERIC)) if rng.random() < 0.6 else expr.const(rng.choice(NUMBERS))
    a, b, c = (number(rng, depth - 1) for _ in range(3))
    k = rng.randrange(12)
    if k < 4:
        return expr.binary(('add', 'sub', 'mul', 'div')[k], a, b)
    if k == 4:
        return expr.binary('pow', a, rng.choice((expr.const(2), expr.const(0.5), expr.const(-1), b)))
    if k == 5:
        return expr.unary(rng.choice(('neg', 'pos')), a)
    if k == 6:
        return expr.call(rng.choice(ONE), [a])
    if k == 7:
        return expr.call(rng.choice(('min', 'max', 'sum')), [a, b, c][: rng.randrange(1, 4)])
    if k == 8:
        return expr.call('clip', [a, b, c])
    if k == 9:
        return expr.call('q', [a, expr.const(rng.choice(('h', 'days')))])
    return expr.if_else(condition(rng, depth - 1), a, b)


def condition(rng, depth):
    """A node that gives a yes/no."""
    if depth == 0 or rng.random() < 0.15:
        if rng.random() < 0.5:
            return expr.ref('flag')
        return expr.compare(
            [rng.choice(('eq', 'ne'))], [expr.ref('m.mode'), expr.const(rng.choice(('open', 'shut')))]
        )
    a, b, c = (condition(rng, depth - 1) for _ in range(3))
    k = rng.randrange(10)
    if k < 3 or k == 9:
        x, y, z = (number(rng, depth - 1) for _ in range(3))
        if k == 9:
            return expr.call('within', [x, y, z])
        if k == 2:
            return expr.compare([rng.choice(ORDER), rng.choice(ORDER)], [x, y, z])
        return expr.compare([rng.choice(ORDER)], [x, y])
    if k == 3:
        return expr.unary('not', a)
    if k < 6:
        return expr.boolean(rng.choice(('and', 'or')), [a, b, c][: rng.randrange(2, 4)])
    if k == 6:
        return expr.call(rng.choice(('any', 'all')), [a, b, c][: rng.randrange(1, 4)])
    return expr.if_else(a, b, c)


def environments(rng):
    """An environment for `COUNT` instances: each name has one value for all, or a value for each.
    (the environment with its arrays, the environment of each instance)."""
    shared, each = {}, [{} for _ in range(COUNT)]
    for name in NAMES:
        if name == 'm.mode':
            pick = lambda: rng.choice(('open', 'shut'))  # noqa: E731
        elif name == 'flag':
            pick = lambda: rng.choice((True, False))  # noqa: E731
        else:
            pick = lambda: rng.choice(NUMBERS)  # noqa: E731
        if rng.random() < 0.6:
            column = [pick() for _ in range(COUNT)]
            shared[name] = np.array(column)
            for env, value in zip(each, column):
                env[name] = value
        else:
            value = pick()
            shared[name] = value
            for env in each:
                env[name] = value
    return shared, each


def same(found, wanted):
    """A value of an array against the value of the walk: a yes/no and a text as they are, a number
    to a rounding of the last places (numpy's functions are not Python's)."""
    kind, value = wanted
    if kind is bool or kind is str:
        return found == value
    # The walk gives a float as its hexadecimal text.
    value = float.fromhex(value) if isinstance(value, str) else float(value)
    return math.isclose(float(found), value, rel_tol=1e-12, abs_tol=1e-300)


def test_the_values_for_many_instances_are_the_value_of_each_instance():
    rng = random.Random(20261112)
    seen = {'fails': 0, 'values': 0, 'arrays': 0}
    kinds = set()
    for _ in range(6000):
        depth = rng.randrange(1, 5)
        node = number(rng, depth) if rng.random() < 0.6 else condition(rng, depth)
        shared, each = environments(rng)
        wanted = [outcome(lambda env=env: walked(node, env)) for env in each]
        kinds |= {ops.operation_of(part) for part in expr.walk(node)}
        if ('fails',) in wanted:
            seen['fails'] += 1
            with pytest.raises(ExpressionError):
                arrays.values(node, shared, UNITS, COUNT)
            continue
        found = arrays.values(node, shared, UNITS, COUNT)
        seen['values'] += 1
        if isinstance(found, np.ndarray):
            seen['arrays'] += 1
            assert found.shape == (COUNT,)
            assert all(same(found[i], wanted[i]) for i in range(COUNT)), (
                expr.text(node),
                shared,
                found,
                wanted,
            )
        else:
            assert all(same(found, wanted[i]) for i in range(COUNT)), (expr.text(node), shared, found, wanted)
    # The test met failures, values, and arrays of values; and each operation of the language.
    assert min(seen.values()) > 500, seen
    assert kinds - {None} == set(ops.OPERATIONS)


def test_a_branch_that_would_fail_is_no_failure_for_an_instance_that_does_not_take_it():
    env = {'x': np.array([4.0, 0.0, 2.0]), 'y': np.array([8.0, 5.0, 3.0])}
    guarded = expr.read('y / x if x > 0 else 0')
    assert arrays.values(guarded, env, UNITS, 3).tolist() == [2.0, 0.0, 1.5]
    assert arrays.values(expr.read('x > 0 and y / x > 1'), env, UNITS, 3).tolist() == [True, False, True]
    assert arrays.values(expr.read('x == 0 or y / x > 1'), env, UNITS, 3).tolist() == [True, True, True]
    assert arrays.values(expr.read('0 < x < y / x'), env, UNITS, 3).tolist() == [False, False, False]
    with pytest.raises(ExpressionError):
        arrays.values(expr.read('y / x'), env, UNITS, 3)


def test_sums_products_and_quotients_of_arrays_are_those_of_each_instance_bit_for_bit():
    rng = random.Random('bits')
    x = np.array([rng.uniform(-1e3, 1e3) for _ in range(500)])
    y = np.array([rng.uniform(0.1, 9.0) for _ in range(500)])
    node = expr.read('(x + y) * y / (x - 2 * y) - x')
    found = arrays.values(node, {'x': x, 'y': y}, UNITS, 500)
    for i in range(500):
        a, b = float(x[i]), float(y[i])
        assert found[i].hex() == ((a + b) * b / (a - 2 * b) - a).hex()


def test_a_sum_over_members_that_are_arrays_is_the_sum_from_the_left_for_each_instance():
    rng = random.Random('members')
    members = {f'm{k}': np.array([rng.uniform(-1, 1) for _ in range(40)]) for k in range(9)}
    node = expr.call('sum', [expr.ref(name) for name in members])
    found = arrays.values(node, members, UNITS, 40)
    for i in range(40):
        total = float(members['m0'][i])
        for k in range(1, 9):
            total = total + float(members[f'm{k}'][i])
        assert found[i].hex() == total.hex()


def test_a_node_that_reads_no_array_has_one_value():
    assert arrays.values(expr.read('2 * x + 1'), {'x': 3}, UNITS, 5) == 7
    assert arrays.values(expr.read('x > 1'), {'x': 3}, UNITS, 5) is True


def test_this_consumer_has_a_handler_for_each_operation():
    assert set(arrays.TABLE) == set(ops.OPERATIONS)


class Counted(dict):
    """An environment that counts the readings of its names."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read = 0

    def __getitem__(self, name):
        self.read += 1
        return super().__getitem__(name)


@pytest.mark.parametrize('depth', [3, 20, 200])
def test_a_part_in_many_places_of_an_expression_is_computed_once(depth):
    """Each level is half the sum of the level below with itself, so the node of depth d has the
    level 0 in 2^d places and the value of that level exactly. A formula written in the place of its
    name makes such nodes. The value is right, and the name is read twice, by the two sides of the
    first sum, whatever the depth: the cost of a pass grows with the number of different parts (a
    walk of 2^200 places would not end)."""
    half = expr.const(0.5)
    one, many = expr.ref('a'), expr.ref('c')
    for _ in range(depth):
        one = expr.binary('mul', expr.binary('add', one, one), half)
        many = expr.binary('mul', expr.binary('add', many, many), half)
    scalar = Counted(a=0.3)
    found = arrays.values(one, scalar, UNITS, COUNT)
    assert found == 0.3
    assert scalar.read == 2
    column = np.array([0.1, -2.5, 3.0, 0.0, 7.25, 1e-9])
    spread = Counted(c=column)
    found = arrays.values(many, spread, UNITS, COUNT)
    assert np.array_equal(found, column)
    assert spread.read == 2


def test_a_part_in_a_branch_that_all_instances_take_is_the_part_for_all_instances():
    """A choice that every instance takes on one side, a chain of comparisons and an `and` read
    their parts for all instances: the part that they share with the rest of the expression is still
    computed once (its name is read twice, as above). A choice that splits the instances reads each
    side for its own instances, as before: an instance that does not take a branch does not fail in
    it."""
    deep = expr.ref('c')
    for _ in range(60):
        deep = expr.binary('mul', expr.binary('add', deep, deep), expr.const(0.5))
    column = np.array([1.0, 2.0, 4.0, 0.5, 3.0, 8.0])
    always = expr.if_else(expr.compare(['gt'], [deep, expr.const(0)]), deep, expr.const(-1))
    both = expr.boolean(
        'and',
        [expr.compare(['lt', 'le'], [expr.const(0), deep, deep]), expr.compare(['ge'], [deep, deep])],
    )
    env = Counted(c=column)
    found = arrays.values(always, env, UNITS, COUNT)
    assert np.array_equal(found, column)
    assert env.read == 2
    env = Counted(c=column)
    found = arrays.values(both, env, UNITS, COUNT)
    assert found.all()
    assert env.read == 2
    split = expr.if_else(
        expr.compare(['gt'], [expr.ref('c'), expr.const(2)]),
        expr.call('ln', [expr.binary('sub', expr.ref('c'), expr.const(2))]),
        expr.const(0),
    )
    expected = [math.log(value - 2) if value > 2 else 0.0 for value in column]
    found = arrays.values(split, {'c': column}, UNITS, COUNT).tolist()
    assert found == pytest.approx(expected, rel=1e-15)


def test_a_membership_over_many_instances_is_that_of_each_instance_and_fails_by_name_with_one():
    """`within(x, lo, hi)` over arrays: each instance's closed interval, as the function of one
    instance gives it; and when the interval of one instance is reversed, the whole call fails with
    the error that names it, as a loop over the instances fails at that one (the audit's row 12)."""
    rng = random.Random('membership')
    node = expr.call('within', [expr.ref('x'), expr.ref('lo'), expr.ref('hi')])
    for _ in range(200):
        size = rng.randrange(1, 8)
        columns = {name: np.array([rng.choice((-1.0, 0.0, 0.5, 2.0, 3.0)) for _ in range(size)]) for name in ('x', 'lo', 'hi')}
        if rng.random() < 0.5:
            columns['lo'] = np.minimum(columns['lo'], columns['hi'])
        env = {name: column if rng.random() < 0.8 else float(column[0]) for name, column in columns.items()}
        each = [{name: float(value[i]) if isinstance(value, np.ndarray) else value for name, value in env.items()} for i in range(size)]
        if any(one['lo'] > one['hi'] for one in each):
            with pytest.raises(ExpressionError, match='the interval of a membership test is reversed'):
                arrays.values(node, env, UNITS, size)
            continue
        found = arrays.values(node, env, UNITS, size)
        wanted = [one['lo'] <= one['x'] <= one['hi'] for one in each]
        if isinstance(found, np.ndarray):
            assert found.tolist() == wanted
        else:
            assert all(found is want for want in wanted)
