"""The contract of each operation (`napkin/core/ops.py`).

Each operation that a node can have has a contract, and no other name has one. The partial
derivatives are checked against central differences of the operation's own value, at random points
away from its kinks. Each claim that a value never falls, or never rises, with an argument is checked
on random pairs, and a claim of neither has a pair each way. The number of arguments is the one that
the present evaluator takes. A consumer's table of handlers is whole, or the check says what it lacks.
"""

import math
import random

import pytest

from napkin import expressions
from napkin.core import evaluation, expr, ops
from napkin.core.errors import ExpressionError
from tests import build as b

UNITS = expressions.UnitSystem(b.library()['units'])
NAMES = ('x', 'y', 'z')
ONE = ('exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf', 'abs')


def value(node, env):
    """The value of a node at a point, by the present evaluator of its text read again."""
    return expressions.evaluate(expr.read(expr.text(node)), env, UNITS)


def applied(name, args):
    """The node of one operation on some nodes."""
    if name in expr.UNARY.values():
        return expr.unary(name, *args)
    if name in expr.BINARY.values():
        return expr.binary(name, *args)
    if name in expr.COMPARE.values():
        return expr.compare([name], args)
    if name in ('and', 'or'):
        return expr.boolean(name, args)
    if name == 'if':
        return expr.if_else(*args)
    return expr.call(name, args)


def test_each_operation_that_a_node_can_have_has_a_contract_and_no_other_name_has_one():
    of_nodes = {*expr.UNARY.values(), *expr.BINARY.values(), *expr.COMPARE.values(), 'and', 'or', 'if'}
    assert set(ops.OPERATIONS) == of_nodes | expr.FUNCTIONS
    for name, operation in ops.OPERATIONS.items():
        assert operation.name == name and operation.units in ops.UNIT_RULES
        assert operation.domain and operation.kinks
        count = operation.arity or 1
        assert len(operation.monotone) == count and set(operation.monotone) <= {'+', '-', 'sign', 'none'}
    # The operation of a node, and none for a node that is no operation.
    for source, name in (('-x', 'neg'), ('x ** y', 'pow'), ('x < y <= z', 'lt'), ('x or y', 'or')):
        assert ops.operation_of(expr.read(source)) == name
    assert (
        ops.operation_of(expr.read('x if y else z')) == 'if'
        and ops.operation_of(expr.read('min(x)')) == 'min'
    )
    for source in ('x', '2.5', 'x is y'):
        assert ops.operation_of(expr.read(source)) is None


def test_the_number_of_arguments_is_the_one_that_the_evaluator_takes():
    env = {'x': 0.5, 'y': 0.25, 'z': 0.75}
    for name in sorted(expr.FUNCTIONS):
        operation = ops.OPERATIONS[name]
        for count in range(0, 5):
            args = ['x', 'y', 'z', 'x', 'y'][:count]
            if name == 'q' and count >= 2:
                args[1] = "'h'"
            if name == 'clip' and count == 3:
                args = ['x', 'y', 'z']  # the bounds in their order
            source = f'{name}({", ".join(args)})'
            if ops.arity_holds(operation, count):
                assert math.isfinite(expressions.evaluate(expr.read(source), env, UNITS))
            else:
                with pytest.raises(ExpressionError, match='Invalid argument count'):
                    expressions.evaluate(expr.read(source), env, UNITS)
    assert ops.arity_holds(ops.OPERATIONS['and'], 3) and not ops.arity_holds(ops.OPERATIONS['add'], 3)


def points(name, choose):
    """Arguments of an operation, as numbers, in its domain and away from its kinks."""
    if name in ('ln', 'sqrt', 'pow'):
        first = choose.uniform(0.3, 3.0)
    elif name == 'log1p':
        first = choose.uniform(-0.7, 3.0)
    else:
        first = choose.choice((-1, 1)) * choose.uniform(0.3, 2.5)
    if name in ('neg', 'pos', *ONE):
        return [first]
    if name == 'div':
        return [first, choose.choice((-1, 1)) * choose.uniform(0.4, 2.5)]
    if name == 'pow':
        return [first, choose.uniform(-2.0, 2.0)]
    if name in ('min', 'max'):
        spread = choose.sample(range(-6, 7), choose.choice((1, 2, 3)))  # distinct, at least 0.5 apart
        return [0.5 * k + choose.uniform(-0.1, 0.1) for k in spread]
    if name == 'clip':
        low = choose.uniform(-2, 0)
        high = low + choose.uniform(1, 2)
        inside = choose.uniform(low + 0.2, high - 0.2)
        return [choose.choice((low - 0.5, inside, high + 0.5)), low, high]
    return [first, choose.choice((-1, 1)) * choose.uniform(0.3, 2.5)]


SMOOTH = [
    name for name, operation in ops.OPERATIONS.items() if operation.partials and name not in ('if', 'q')
]


@pytest.mark.parametrize('name', SMOOTH)
def test_each_partial_derivative_is_the_slope_of_the_operation(name):
    operation, choose = ops.OPERATIONS[name], random.Random(name)
    for _ in range(40):
        at = points(name, choose)
        refs = [expr.ref(n) for n in NAMES[: len(at)]]
        env = dict(zip(NAMES, at))
        whole = applied(name, refs)
        partials = operation.partials(*refs)
        assert len(partials) == len(at)
        for k, partial in enumerate(partials):
            step = 1e-6 * max(1.0, abs(at[k]))
            up, down = ({**env, NAMES[k]: at[k] + sign * step} for sign in (1, -1))
            slope = (value(whole, up) - value(whole, down)) / (2 * step)
            assert value(partial, env) == pytest.approx(slope, rel=1e-6, abs=1e-7), (name, k, at)


def test_the_partials_of_a_choice_and_of_a_quantity():
    test, body, orelse = (expr.ref(n) for n in ('c', 'x', 'y'))
    none, by_body, by_orelse = ops.OPERATIONS['if'].partials(test, body, orelse)
    assert none is None
    for taken in (True, False):
        env = {'c': taken, 'x': 1.5, 'y': -2.0}
        assert (value(by_body, env), value(by_orelse, env)) == ((1, 0) if taken else (0, 1))
    # A quantity is its number times the scale of its unit: the slope is the quantity of one.
    amount, unit = expr.ref('x'), expr.const('days')
    by_amount, none = ops.OPERATIONS['q'].partials(amount, unit)
    assert none is None
    whole = expr.call('q', [amount, unit])
    slope = (value(whole, {'x': 3.0 + 1e-3}) - value(whole, {'x': 3.0 - 1e-3})) / 2e-3
    scale = UNITS.parse_unit('days').scale
    assert value(by_amount, {}) == pytest.approx(slope, rel=1e-9) == pytest.approx(scale)
    assert scale != 1


def moves(name, k, at, claim, choose):
    """(the value before, the value after) when argument `k` rises and the others stay. For a claim
    that holds on one side of zero, the argument stays on its side."""
    refs = [expr.const(v) if isinstance(v, str) else expr.ref(n) for n, v in zip(NAMES, at)]  # a written unit
    whole = applied(name, refs)
    higher = list(at)
    if isinstance(at[k], bool):
        higher[k] = True
    elif name in ('eq', 'ne'):
        higher[k] = at[k] + 1
    elif claim == 'sign' and at[k] < 0:
        higher[k] = at[k] * choose.uniform(0.2, 0.95)
    else:
        higher[k] = at[k] + choose.uniform(0.01, 0.6)
    try:
        return value(whole, dict(zip(NAMES, at))), value(whole, dict(zip(NAMES, higher)))
    except ExpressionError:
        return None  # the higher point left the domain (a lower bound of clip above the upper one)


def conditions(count, choose):
    return [choose.choice((False, True)) for _ in range(count)]


@pytest.mark.parametrize('name', sorted(ops.OPERATIONS))
def test_a_value_moves_with_each_argument_as_the_contract_says(name):
    operation, choose = ops.OPERATIONS[name], random.Random(name)
    logic = name in ('not', 'and', 'or', 'any', 'all')
    seen = {}
    for _ in range(300):
        if name == 'q':
            at = [choose.uniform(-3, 3), 'days']
        elif name == 'if':
            at = [choose.choice((False, True)), choose.uniform(-3, 3), choose.uniform(-3, 3)]
        elif logic:
            at = conditions(operation.arity or choose.choice((1, 2, 3)), choose)
        elif name in ('eq', 'ne'):
            at = [choose.choice((-1, 0, 1)), choose.choice((-1, 0, 1))]  # whole, so that some are equal
        elif name in expr.COMPARE.values():
            at = [choose.uniform(-1, 1), choose.uniform(-1, 1)]
        else:
            at = points(name, choose)
        for k in range(len(at)):
            claim = operation.monotone[min(k, len(operation.monotone) - 1)]
            if isinstance(at[k], str) or (name == 'if' and k == 0):
                continue
            if logic and at[k]:
                continue  # a yes cannot rise
            found = moves(name, k, at, claim, choose)
            if found is None:
                continue
            before, after = found
            if claim == '+':
                assert after >= before, (name, k, at)
            elif claim == '-':
                assert after <= before, (name, k, at)
            direction = 'up' if after > before else 'down' if after < before else 'flat'
            # For `sign`, the direction is one for a given sign of what the argument is combined with.
            others = None
            if claim == 'sign':
                others = tuple(v > (1 if name == 'pow' and j == 0 else 0) for j, v in enumerate(at) if j != k)
            seen.setdefault((k, claim, others), set()).add(direction)
    # Each argument that can rise did rise at some point. A point that the operation does not take (a
    # wrong number of arguments from `points`) moves nothing, and then a wrong claim would pass.
    fixed = {0} if name == 'if' else {1} if name == 'q' else set()
    assert {k for k, _, _ in seen} >= set(range(operation.arity or 1)) - fixed, (name, sorted(seen, key=str))
    for (k, claim, _), directions in seen.items():
        if claim == 'sign':
            assert not {'up', 'down'} <= directions, (name, k, directions)
        if claim == 'none' and name in ('abs', 'eq', 'ne'):
            assert {'up', 'down'} <= directions, (name, k, directions)
    if any(claim == 'sign' for claim in operation.monotone):
        # Both directions are met, each under its own sign.
        assert {d for (_, claim, _), ds in seen.items() if claim == 'sign' for d in ds} >= {'up', 'down'}


def test_the_table_of_a_consumer_is_whole_or_the_check_says_what_it_lacks():
    whole = dict.fromkeys(ops.OPERATIONS, print)
    assert ops.handlers('a consumer', whole) == whole
    without = {name: handler for name, handler in whole.items() if name not in ('erf', 'clip')}
    with pytest.raises(LookupError, match='a consumer: no handler for clip, erf'):
        ops.handlers('a consumer', without)
    assert ops.handlers('a consumer', without, unsupported=('erf', 'clip')) == without
    with pytest.raises(LookupError, match='no such operation: sinh'):
        ops.handlers('a consumer', {**whole, 'sinh': print})
    with pytest.raises(LookupError, match='no such operation: sinh'):
        ops.handlers('a consumer', whole, unsupported=('sinh',))
    with pytest.raises(LookupError, match='a handler and no handler for erf'):
        ops.handlers('a consumer', whole, unsupported=('erf',))


# ---- the functions over the members of a list ---------------------------------------------------------


def chain(op, names):
    """The members joined two by two from the left, as the lowering writes a list in a flat structure."""
    total = expr.ref(names[0])
    for name in names[1:]:
        total = expr.binary(op, total, expr.ref(name))
    return total


def test_a_sum_over_members_is_the_chain_of_sums_from_the_left_bit_for_bit():
    """The oracle is Python's own addition, two values at a time from the left, on numbers that are no
    round binary fractions: another order of the additions gives other bits for most of them."""
    choose = random.Random('sum')
    other_order = 0
    for _ in range(300):
        # A chain of more than about 39 members is nested too deep for Python to read its code.
        count = choose.randint(1, 30)
        names = [f'v{k}' for k in range(count)]
        env = {name: choose.uniform(-1e3, 1e3) * 10 ** choose.randint(-6, 6) for name in names}
        total = env[names[0]]
        for name in names[1:]:
            total = total + env[name]
        found = value(expr.call('sum', [expr.ref(name) for name in names]), env)
        assert found.hex() == total.hex() == value(chain('add', names), env).hex()
        other_order += math.fsum(env.values()) != total
    # The test can tell an order from another: the exact sum differs from the sum from the left.
    assert other_order > 50


def test_a_sum_is_one_node_however_many_members_it_has():
    """A chain is nested once for each member, which stops Python at about 39 members; the sum over a
    list is one call."""
    choose = random.Random('many')
    names = [f'v{k}' for k in range(5000)]
    env = {name: choose.uniform(-1, 1) for name in names}
    total = env[names[0]]
    for name in names[1:]:
        total = total + env[name]
    node = expr.call('sum', [expr.ref(name) for name in names])
    assert evaluation.value(node, env, UNITS).hex() == total.hex()


def test_a_sum_fails_where_a_sum_of_two_of_its_chain_fails():
    env = {'a': 1e308, 'b': 1e308, 'c': -1e308}
    for node in (expr.call('sum', [expr.ref('a'), expr.ref('b'), expr.ref('c')]), chain('add', 'abc')):
        with pytest.raises(ExpressionError, match='nonfinite'):
            value(node, env)
    # The same members in an order whose sums of two are all finite have a value.
    assert value(expr.call('sum', [expr.ref('a'), expr.ref('c'), expr.ref('b')]), env) == 1e308


@pytest.mark.parametrize(('name', 'op'), [('any', 'or'), ('all', 'and')])
def test_any_and_all_of_members_are_the_or_and_the_and_of_them(name, op):
    choose = random.Random(name)
    for _ in range(200):
        count = choose.randint(1, 6)
        names = [f'c{k}' for k in range(count)]
        env = {member: choose.choice((False, True)) for member in names}
        listed = expr.call(name, [expr.ref(member) for member in names])
        joined = expr.ref(names[0]) if count == 1 else expr.boolean(op, [expr.ref(m) for m in names])
        assert value(listed, env) is value(joined, env) is (any if name == 'any' else all)(env.values())
    # A member that decides the value stops the reading, as `or` and `and` do: the next one would fail.
    decided = expr.read(f'{name}(c, 1 / zero > 0)')
    assert value(decided, {'c': name == 'any', 'zero': 0}) is (name == 'any')
    with pytest.raises(ExpressionError):
        value(decided, {'c': name != 'any', 'zero': 0})


def test_one_member_of_a_list_is_that_member():
    env = {'x': 2.5, 'flag': True}
    assert value(expr.read('sum(x)'), env) == 2.5
    assert value(expr.read('any(flag)'), env) is True and value(expr.read('all(flag)'), env) is True


def test_the_unit_and_the_interval_of_a_sum_are_those_of_its_chain():
    symbols = {name: UNITS.parse_unit('people') for name in 'abc'}
    listed, joined = expr.read('sum(a, b, c)'), chain('add', 'abc')
    assert expressions.compile_expression(expr.read(expr.text(listed)), symbols, UNITS).unit == (
        expressions.compile_expression(expr.read(expr.text(joined)), symbols, UNITS).unit
    )
    with pytest.raises(ExpressionError):
        expressions.compile_expression(
            expr.read('sum(a, b, t)'), {**symbols, 't': UNITS.parse_unit('h')}, UNITS
        )
    choose = random.Random('interval')
    for _ in range(100):
        ranges = {}
        for name in 'abc':
            low = choose.uniform(-50, 50)
            ranges[name] = (low, low + choose.uniform(0, 30))
        prove = expressions.domain_prover(ranges, UNITS)
        low, high = prove(expr.read(expr.text(listed)))
        assert (low, high) == prove(expr.read(expr.text(joined)))
        assert low == ranges['a'][0] + ranges['b'][0] + ranges['c'][0]
        assert high == ranges['a'][1] + ranges['b'][1] + ranges['c'][1]


def test_a_text_of_a_function_over_a_list_is_read_as_its_one_node():
    for source in ('sum(a, b, c)', 'any(a > 1, b > 1)', 'all(a > 1)'):
        node = expr.read(source)
        assert isinstance(node, expr.Call) and node.function in expr.LISTED
        assert expr.read(expr.text(node)) is node
