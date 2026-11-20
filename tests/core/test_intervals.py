"""The interval of an expression (`napkin/core/intervals.py`).

A proved interval is checked by sampling: at points of the ranges, the value of the expression (by the
interpreter of `tests/core/reference.py`) is inside the interval, and no part of it is outside its
domain. A prover that remembers the intervals of formulas gives what a new prover gives, and so does
a prover that is taken over other ranges and keeps its answers with the prover that it came from.
The cases of a guard are written with the interval that the guard gives by hand.
"""

import math
import random

import pytest

from napkin.core import expr, intervals, ops
from napkin.core.errors import ExpressionError
from tests.core.reference import ONE, UNITS, NotFinite, walked

NAMES = ('a', 'b', 'c', 'd')
BOUNDS = (
    (0.0, 1.0),
    (1.0, 2.0),
    (-1.0, 1.0),
    (0.5, 0.5),
    (0.0, 0.0),
    (-3.0, -1.0),
    (0.25, 40.0),
    (-2.0, 5.0),
)


def number(rng):
    return expr.const(rng.choice((0, 1, 2, 3, 0.5, -1, 10, 0.25, -2.5)))


def made(rng, depth, names=NAMES, guards=True):
    """A random numeric node over the names, with choices that guards decide unless `guards` is off."""
    if depth == 0 or rng.random() < 0.15:
        return expr.ref(rng.choice(names)) if rng.random() < 0.7 else number(rng)
    a, b, c = (made(rng, depth - 1, names, guards) for _ in range(3))
    k = rng.randrange(22 if guards else 13)
    if k < 6:
        return expr.binary(rng.choice(('add', 'sub', 'mul', 'div')), a, b)
    if k == 6:
        return expr.binary('pow', a, expr.const(rng.choice((2, 3, 0.5, -1, 0))))
    if k == 7:
        return expr.unary(rng.choice(('neg', 'pos')), a)
    if k < 10:
        # Each function of one argument that the walk of a node knows (`reference.ONE`).
        return expr.call(rng.choice(sorted(ONE)), [a])
    if k == 10:
        return expr.call(rng.choice(('min', 'max')), [a, b, c][: rng.randrange(1, 4)])
    if k == 11:
        return expr.call('clip', [a, number(rng), expr.binary('add', number(rng), expr.const(20))])
    if k == 12:
        return expr.call('q', [a, expr.const(rng.choice(('h', 'days')))])
    # A choice with a guard: a comparison of a name or of an expression with a number, or two of them.
    guard = expr.compare(
        [rng.choice(('gt', 'ge', 'lt', 'le', 'ne', 'eq'))], [rng.choice((a, c)), number(rng)]
    )
    if k < 15:
        guard = expr.boolean(rng.choice(('and', 'or')), [guard, expr.compare(['gt'], [c, expr.const(0)])])
    elif k == 15:
        guard = expr.unary('not', guard)
    return expr.if_else(guard, a, b)


def points(rng, ranges, count):
    for _ in range(count):
        env = {}
        for name, (low, high) in ranges.items():
            choices = [low, high, (low + high) / 2, rng.uniform(low, high)]
            choices += [x for x in (0.0, 1.0, -1.0, 1e-9) if low <= x <= high]
            env[name] = rng.choice(choices)
        yield env


def test_a_value_at_a_point_of_the_ranges_is_in_the_proved_interval():
    rng = random.Random(20261112)
    seen = {'proved': 0, 'rejected': 0, 'values': 0, 'not finite': 0}
    sampled = set()
    for _ in range(3000):
        ranges = {name: rng.choice(BOUNDS) for name in NAMES}
        node = made(rng, rng.randrange(1, 5))
        try:
            low, high = intervals.prover(ranges, UNITS)(node)
        except ExpressionError:
            seen['rejected'] += 1
            continue
        seen['proved'] += 1
        assert low <= high, expr.text(node)
        slack = 1e-9 * max(
            1.0, abs(low) if math.isfinite(low) else 1.0, abs(high) if math.isfinite(high) else 1.0
        )
        for env in points(rng, ranges, 25):
            try:
                value = walked(node, env)
            except (NotFinite, OverflowError):
                seen['not finite'] += 1  # a sum or a product can leave the floating-point range
                continue
            # Any other failure (a zero divisor, a logarithm or a root outside its domain, a power
            # that is not real) is a part that the proof said has a value.
            assert low - slack <= value <= high + slack, (expr.text(node), env, (low, high), value)
            seen['values'] += 1
            sampled |= {ops.operation_of(part) for part in expr.walk(node)}
    assert seen['proved'] > 800 and seen['rejected'] > 300 and seen['values'] > 15000, seen
    assert seen['not finite'] < seen['values'] / 20, seen
    # Each function of one argument was in a node that was proved and then sampled. So a handler that
    # gives a wrong interval for one of them fails here, and the test has a new function when the walk
    # of a node has it.
    assert sampled >= set(ONE), sorted(set(ONE) - sampled)


def test_a_prover_that_remembers_gives_what_a_new_prover_gives():
    rng = random.Random(20261113)
    asked = 0
    for _ in range(300):
        ranges = {name: rng.choice(BOUNDS) for name in NAMES}
        formulas = {}
        for k in range(rng.randrange(1, 6)):
            # A formula reads the names and the formulas, the later ones and itself included: circles.
            # It has no guard: a formula on a circle whose own guard reads it has no proof that ends.
            reads = (*NAMES, *(f'f{j}' for j in range(k + 2)))
            formulas[f'f{k}'] = made(rng, rng.randrange(1, 4), reads, guards=False)
        shared = intervals.prover(ranges, UNITS, formulas)
        for _ in range(6):
            node = made(rng, rng.randrange(1, 4), (*NAMES, *formulas))
            answers = []
            for prove in (shared, intervals.prover(ranges, UNITS, formulas), shared):
                try:
                    answers.append(prove(node))
                except ExpressionError as exc:
                    answers.append(str(exc))
            assert answers[0] == answers[1] == answers[2], (expr.text(node), ranges)
            asked += 1
    assert asked == 1800


def lines_of_provers(rng, count, circles):
    """`count` lines of provers, each taken over other ranges five times, with each answer checked
    against a new prover over the same ranges, which keeps nothing. Returns how many answers were
    checked, how many changes made the ranges empty, how many names lost their range and how many
    times a line came back to ranges that it had before."""
    asked = emptied = dropped = back = 0
    for _ in range(count):
        ranges = {name: rng.choice(BOUNDS) for name in NAMES}
        formulas = {}
        for k in range(rng.randrange(2, 7)):
            reads = (*NAMES, *(f'f{j}' for j in range(k + 2 if circles else k)))
            formulas[f'f{k}'] = made(rng, rng.randrange(1, 4), reads, guards=not circles)
        asks = [made(rng, rng.randrange(1, 4), (*NAMES, *formulas)) for _ in range(5)]
        lineage = intervals.prover(ranges, UNITS, formulas)
        before = [ranges]
        for step in range(6):
            for node in asks:
                answers = []
                for prove in (lineage, intervals.prover(ranges, UNITS, formulas)):
                    try:
                        answers.append(prove(node))
                    except (ExpressionError, ArithmeticError, ValueError, TypeError) as exc:
                        # Over ranges that are empty, the arithmetic of the ends of an interval can
                        # fail (a divisor from 1 to 0, the root of an end below 0, a power that is
                        # no real number). The two provers fail in the same way.
                        answers.append((type(exc).__name__, str(exc)))
                # The text of an interval tells a zero from a zero of the other sign.
                assert repr(answers[0]) == repr(answers[1]), (expr.text(node), ranges, step)
                asked += 1
            if rng.random() < 0.25:
                ranges = rng.choice(before)  # ranges that the line of provers had before
                back += 1
            else:
                ranges = dict(ranges)
                for name in rng.sample((*NAMES, *formulas), rng.randrange(0, 3)):
                    pair = rng.choice(BOUNDS)
                    if rng.random() < 0.1:
                        pair = (pair[1] + 1.0, pair[0])
                        emptied += 1
                    ranges[name] = pair
                if rng.random() < 0.3:
                    gone = rng.choice(sorted(ranges))
                    del ranges[gone]
                    dropped += 1
                for name, (low, high) in list(ranges.items()):
                    if low == 0 and rng.random() < 0.2:
                        ranges[name] = (-low, high)
                before.append(ranges)
            lineage = lineage.over(ranges)
    return asked, emptied, dropped, back


@pytest.mark.parametrize('circles', [False, True])
def test_a_prover_taken_over_other_ranges_gives_what_a_new_prover_of_those_ranges_gives(circles):
    """`over(ranges)` gives a prover that keeps its answers together with the prover that it came
    from. The definition is a new prover over the new ranges, which keeps nothing. With no circle,
    the formulas can have guards, so their answers are kept under the facts of a branch too; with
    `circles`, a formula can read itself and the formulas after it (and has no guard: see the test
    above). A range can change and change back, a name can lose its range, and a formula can get a
    range (its range is then read, not its definition) and lose it again. A change can make the
    ranges empty (an end above its other end) and a later change can undo that. A zero can change
    its sign with nothing else."""
    asked, emptied, dropped, back = lines_of_provers(random.Random(20261114 + circles), 250, circles)
    assert asked == 7500 and emptied > 30 and dropped > 150 and back > 200, (asked, emptied, dropped, back)


@pytest.mark.parametrize('circles', [False, True])
def test_provers_that_can_keep_only_a_few_answers_give_the_same(monkeypatch, circles):
    """The answers that a line of provers keeps have a limit, and all of them go when it is reached.
    With a limit of a few, they go many times in each line: a prover that holds the mark of an
    answer that is gone proves again, and gives what a new prover gives."""
    monkeypatch.setattr(intervals, 'KEPT', 5)
    asked, _, _, back = lines_of_provers(random.Random(20261116 + circles), 80, circles)
    assert asked == 2400 and back > 60


def test_a_prover_proves_nothing_again_that_reads_the_ranges_of_a_proof_before(monkeypatch):
    """What `over` is for. The parts that a prover reads are counted: each formula is read once for
    the ranges that it reads, by whichever prover of the line comes to it first."""
    proved = []
    original = intervals._Prover.interval

    def counted(self, node, context, seen):
        proved.append(expr.text(node))
        return original(self, node, context, seen)

    monkeypatch.setattr(intervals._Prover, 'interval', counted)
    read = expr.read
    formulas = {'f': read('a + b'), 'g': read('f * c'), 'h': read('d + 1')}
    ranges = {'a': (0.0, 1.0), 'b': (1.0, 2.0), 'c': (2.0, 3.0), 'd': (0.0, 4.0)}
    nodes = [read('g + h'), read('h * 2')]
    first = intervals.prover(ranges, UNITS, formulas)
    answers = [first(node) for node in nodes]
    assert answers == [(3.0, 14.0), (2.0, 10.0)] and proved.count('a + b') == proved.count('d + 1') == 1
    # The same ranges: nothing is read.
    proved.clear()
    again = first.over(dict(ranges))
    assert [again(node) for node in nodes] == answers and proved == []
    # Another range of d: what reads d is proved again, and what reads only a, b and c is not.
    moved = first.over({**ranges, 'd': (5.0, 6.0)})
    assert [moved(node) for node in nodes] == [(8.0, 16.0), (12.0, 14.0)]
    assert 'd + 1' in proved and not {'a + b', 'f * c'} & set(proved)
    # The first ranges again, from the prover of the other ranges: nothing is read.
    proved.clear()
    back = moved.over(ranges)
    assert [back(node) for node in nodes] == answers and proved == []
    # A zero of the other sign is another range.
    low = intervals.prover({'x': (0.0, 1.0)}, UNITS)
    other = low.over({'x': (-0.0, 1.0)})
    assert [math.copysign(1, prove(read('x'))[0]) for prove in (low, other, low)] == [1, -1, 1]


@pytest.mark.parametrize(
    'source, ranges, interval',
    [
        # The guard keeps the divisor above zero: 1 / y is in [1/2, 1/tiny] and x / y in [0, huge].
        ('x / y if y > 0 else 0', {'x': (0.0, 1.0), 'y': (0.0, 2.0)}, (0.0, 1.0 / math.nextafter(0.0, 1.0))),
        ('x / y if y >= 0.5 else 3', {'x': (1.0, 1.0), 'y': (0.0, 2.0)}, (0.5, 3.0)),
        # The other side of the comparison, and its negation.
        ('x / y if 0.5 <= y else 3', {'x': (1.0, 1.0), 'y': (0.0, 2.0)}, (0.5, 3.0)),
        ('3 if not y >= 0.5 else x / y', {'x': (1.0, 1.0), 'y': (0.0, 2.0)}, (0.5, 3.0)),
        # `and` narrows by each term; `or` narrows the branch where it fails.
        ('x / y if y >= 0.5 and y <= 1 else 0', {'x': (1.0, 1.0), 'y': (0.0, 2.0)}, (0.0, 2.0)),
        ('0 if y < 0.5 or y > 1 else x / y', {'x': (1.0, 1.0), 'y': (0.0, 2.0)}, (0.0, 2.0)),
        # A guard on an expression narrows that expression in the branch.
        ('1 / (x - y) if x - y >= 1 else 0', {'x': (0.0, 5.0), 'y': (0.0, 5.0)}, (0.0, 1.0)),
        # `!= 0` proves that the divisor is not zero, and says nothing more of the quotient.
        ('1 / y if y != 0 else 0', {'y': (-1.0, 1.0)}, (-math.inf, math.inf)),
        # A branch that the ranges leave empty gives nothing.
        ('1 / y if y > 5 else 7', {'y': (0.0, 2.0)}, (7.0, 7.0)),
        # No state reaches the branch where a value that is 0 is not 0. Nothing is read in it: there
        # the divisor would be an interval with its ends in the wrong order, from 5e-324 to 0.
        ('x if x == 0 or 1 / (x + y) > 0 else 10', {'x': (0.0, 0.0), 'y': (0.0, 0.0)}, (0.0, 0.0)),
        ('10 if x != 0 and 1 / (x + y) > 0 else x', {'x': (0.0, 0.0), 'y': (0.0, 0.0)}, (0.0, 0.0)),
        # A name that is fixed makes a power exact; an even power of a range over zero starts at zero.
        ('x ** n', {'x': (-2.0, 3.0), 'n': (2.0, 2.0)}, (0.0, 9.0)),
    ],
)
def test_a_guard_narrows_its_branch(source, ranges, interval):
    assert intervals.prover(ranges, UNITS)(expr.read(source)) == interval


@pytest.mark.parametrize(
    'source, ranges, message',
    [
        ('x / y', {'x': (0.0, 1.0), 'y': (0.0, 2.0)}, 'Cannot prove nonzero denominator'),
        ('x / y if y >= 0 else 0', {'x': (0.0, 1.0), 'y': (0.0, 2.0)}, 'Cannot prove nonzero denominator'),
        ('x / y if x > 0 else 0', {'x': (0.0, 1.0), 'y': (0.0, 2.0)}, 'Cannot prove nonzero denominator'),
        ('ln(x)', {'x': (0.0, 1.0)}, 'Cannot prove ln argument is in its domain'),
        ('log1p(x)', {'x': (-1.0, 1.0)}, 'Cannot prove log1p argument is in its domain'),
        ('sqrt(x)', {'x': (-1.0, 1.0)}, 'Cannot prove sqrt argument is nonnegative'),
        ('exp(x)', {'x': (0.0, 1000.0)}, 'Cannot prove exp stays within finite floating-point range'),
        ('x ** 0.5', {'x': (-1.0, 1.0)}, 'Cannot prove nonnegative base'),
        ('x ** -1', {'x': (0.0, 1.0)}, 'Cannot prove nonzero base'),
        ('x ** y', {'x': (0.0, 1.0), 'y': (0.0, 1.0)}, 'Cannot prove nonzero base'),
        ('clip(x, 2, y)', {'x': (0.0, 1.0), 'y': (0.0, 5.0)}, 'Cannot prove clip bounds are ordered'),
        (
            'within(x, 2, y)',
            {'x': (0.0, 1.0), 'y': (0.0, 5.0)},
            'Cannot prove the ends of a membership test are ordered',
        ),
        ('1 / nowhere', {}, 'Cannot prove nonzero denominator'),
    ],
)
def test_a_part_that_can_be_outside_its_domain_is_rejected(source, ranges, message):
    with pytest.raises(ExpressionError, match=message):
        intervals.prover(ranges, UNITS)(expr.read(source))


def test_a_formula_has_the_interval_of_its_definition_and_a_circle_ends():
    read = expr.read
    formulas = {
        'rate': read('x / total'),
        'total': read('y + 1'),
        'loop': read('loop + x'),
        'bad': read('1 / y'),
    }
    prove = intervals.prover({'x': (0.0, 4.0), 'y': (0.0, 1.0)}, UNITS, formulas)
    assert prove(read('rate')) == (0.0, 4.0) and prove(read('rate + total')) == (1.0, 6.0)
    # A formula that reads itself can be any number where the circle closes.
    assert prove(read('loop')) == (-math.inf, math.inf)
    # The failure of a formula is the failure of each expression that reads it, each time.
    for _ in range(2):
        with pytest.raises(ExpressionError, match='Cannot prove nonzero denominator in `1 / y`'):
            prove(read('bad + 1'))
    # A branch narrows what a formula reads: the formula is proved again under those facts.
    assert prove(read('bad if y >= 0.5 else 0')) == (0.0, 2.0)


def test_a_member_with_a_weight_is_that_many_values_in_a_sum():
    """A member of a list can stand for n values, each in the range of its name: the rows of one
    class of a table. A sum counts it n times. The definition is the list written out, with n names
    of that range in the place of the member: the two provers give one interval. A count of the
    members where a condition holds is from 0 to n. A least and a greatest need no count."""
    read = expr.read
    ranges = {'x': (1.0, 2.0), 'y': (-0.5, 0.25), 'z': (3.0, 3.0)}
    weights = {'x': 5, 'y': 3}
    prove = intervals.prover(ranges, UNITS, weights=weights)
    out = {f'{name}{k}': ranges[name] for name, count in weights.items() for k in range(count)}
    written = intervals.prover({**out, 'z': ranges['z']}, UNITS)
    flat = read('sum(' + ', '.join([*out, 'z']) + ')')
    assert prove(read('sum(x, y, z)')) == written(flat) == (6.5, 13.75)
    assert prove(read('sum(2 * x, z)')) == written(
        read('sum(' + ', '.join(f'2 * x{k}' for k in range(5)) + ', z)')
    )
    assert prove(read('sum(1 if x > 1.5 else 0)')) == (0.0, 5.0)
    assert prove(read('max(x, z)')) == (3.0, 3.0) and prove(read('min(x, z)')) == (1.0, 2.0)
    # With no weight a member is one value, as before.
    assert intervals.prover(ranges, UNITS)(read('sum(x, y, z)')) == (3.5, 5.25)
    # A value at a point of the ranges of the list written out is in the interval of the weights.
    rng = random.Random(7)
    low, high = prove(read('sum(x * x, y)'))
    for _ in range(200):
        xs = [rng.uniform(*ranges['x']) for _ in range(5)]
        ys = [rng.uniform(*ranges['y']) for _ in range(3)]
        assert low <= math.fsum(x * x for x in xs) + math.fsum(ys) <= high


@pytest.mark.parametrize('count, proved', [(1, True), (4, True), (5, False), (6, False)])
def test_a_proof_over_a_list_depends_on_how_many_values_its_member_stands_for(count, proved):
    """Each value is from 1 to 2, so the sum of n of them is from n to 2 n. The divisor `10 - sum`
    cannot be 0 while 2 n is under 10: with 1 and with 4 values. With 5 values the sum can be 10,
    and with 6 it is from 6 to 12: the division has no proof. A proof made with one value for the
    member is no proof for more of them."""
    prove = intervals.prover({'x': (1.0, 2.0)}, UNITS, weights={'x': count})
    node = expr.read('1 / (10 - sum(x))')
    if proved:
        assert prove(node) == (1 / (10 - count), 1 / (10 - 2 * count))
    else:
        with pytest.raises(ExpressionError):
            prove(node)


def test_this_consumer_has_a_handler_for_each_operation():
    assert set(intervals.TABLE) == set(ops.OPERATIONS)
