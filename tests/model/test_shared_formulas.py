"""Formulas that many formulas read: an analysis reads each one once, and gives the answer of the
definition, which follows every way to a formula.

Two analyses follow the formulas that an expression reads: the resolver, which says whether an `assert`
reads inputs only (`Resolver.of_inputs`), and the proof that an expression is constant on the zero
faces of the stocks (`expressions.stock_face_dependencies`). Each keeps what it found for a formula. The
tests here state the definition with no memory, on small graphs of formulas, and compare; and they
compile and prove chains in which each formula reads the one before it twice, which have 2^40 ways and
more to their first formula.
"""

import random

import pytest

from napkin import expressions
from napkin.core.expr import read
from tests import build as b

DEPTH = 40  # a chain of this depth has 2^40 ways from its last formula to its first


def chain(depth, first):
    """The formulas `f0` to `f<depth>`: `f0` is `first`, and each other one reads the one before it twice."""
    formulas = [b.formula('f0', first, 'people')]
    formulas += [b.formula(f'f{k}', f'(f{k - 1} + f{k - 1}) / 2', 'people') for k in range(1, depth + 1)]
    return formulas


def checks_of(text):
    """(the asserts that are checked before the run, the asserts that are checked at each step)."""
    (structure,) = b.compiled(text).structures.values()
    return structure.input_checks, structure.state_checks


def test_an_assert_on_a_deep_chain_of_shared_formulas_is_a_check_of_the_inputs():
    members = [b.parameter('p', 0.5, 'people'), b.stock('w', 5, 'people'), *chain(DEPTH, 'p')]
    before, at_each_step = checks_of(b.system(*members, checks=[b.check(f's.f{DEPTH} >= 0 people')]))
    assert len(before) == 1 and not at_each_step
    # The same chain on a stock: no formula of it reads inputs only, whichever formula the assert reads.
    members = [b.parameter('p', 0.5, 'people'), b.stock('w', 5, 'people'), *chain(DEPTH, 'w')]
    asserts = [b.check(f's.f{DEPTH} >= 0 people'), b.check('s.f1 >= 0 people'), b.check('s.p >= 0 people')]
    before, at_each_step = checks_of(b.system(*members, checks=asserts))
    assert [item.path for item in before.values()] == ['assert:/2']
    assert [item.path for item in at_each_step.values()] == ['assert:/0', 'assert:/1']


def test_one_formula_on_a_stock_makes_each_assert_that_reaches_it_a_check_at_each_step():
    """A diamond: `top` reads `left` and `right`, and both read `shared`. The answer for `top` is the
    same when another assert has read `left`, `right` or `shared` before it."""

    def members(shared):
        return [
            b.parameter('p', 2, 'people'),
            b.stock('w', 5, 'people'),
            b.formula('shared', shared, 'people'),
            b.formula('left', 'shared + p', 'people'),
            b.formula('right', 'shared + shared', 'people'),
            b.formula('top', 'left + right', 'people'),
            b.formula('apart', 'p + p', 'people'),
        ]

    names = ['shared', 'left', 'right', 'top', 'apart']
    for order in (names, names[::-1], ['top', 'apart', 'shared', 'right', 'left']):
        asserts = [b.check(f's.{name} >= 0 people') for name in order]
        before, at_each_step = checks_of(b.system(*members('p'), checks=asserts))
        assert len(before) == len(order) and not at_each_step
        before, at_each_step = checks_of(b.system(*members('w'), checks=asserts))
        # Only `apart` does not reach the stock.
        assert [item.path for item in before.values()] == [f'assert:/{order.index("apart")}']
        assert len(at_each_step) == len(order) - 1


# ---- the proof on the zero faces ----------------------------------------------------------------------

STATIC, MOVING, ZERO = ('p', 'q'), ('m',), ('w', 'v')


@pytest.fixture(scope='module')
def units():
    return expressions.UnitSystem(b.library()['units'])


def text_of(items):
    """The expression of a formula of the graphs here: the sum of what it reads. A read of a stock is
    a comparison of the stock with zero, which is constant on the stock's zero face."""
    return ' + '.join(f'(1 if {target} > 0 else 0)' if kind == 'zero' else target for kind, target in items)


def by_the_definition(items, graph, visiting=frozenset()):
    """The stocks that an expression compares with zero, or None when it is not constant on the zero
    faces: it reads a name that moves, or a formula on a circle of formulas. It follows every way."""
    used = set()
    for kind, target in items:
        if kind == 'zero':
            used.add(target)
        elif target in graph:
            if target in visiting:
                return None
            found = by_the_definition(graph[target], graph, visiting | {target})
            if found is None:
                return None
            used |= found
        elif target not in STATIC:
            return None
    return frozenset(used)


def proved(items, graph, units):
    aliases = {name: read(text_of(found)) for name, found in graph.items()}
    return expressions.stock_face_dependencies(
        read(text_of(items)), set(STATIC), set(ZERO), aliases, {}, units
    )


def test_the_face_proof_of_formulas_that_share_formulas_is_that_of_the_definition(units):
    shared = {
        'base': [('read', 'p'), ('zero', 'w')],
        'left': [('read', 'base'), ('read', 'q')],
        'right': [('read', 'base'), ('zero', 'v')],
        'top': [('read', 'left'), ('read', 'right'), ('read', 'left')],
    }
    assert proved([('read', 'top')], shared, units) == frozenset({'w', 'v'})
    assert proved([('read', 'left')], shared, units) == frozenset({'w'})
    # One formula that moves, under a formula that two others read: every formula above it moves.
    moving = {**shared, 'base': [('read', 'p'), ('read', 'm')]}
    for name in moving:
        assert proved([('read', name)], moving, units) is None
    # A circle of formulas is constant from no entry, and neither is a formula that reaches it.
    circle = {
        'a': [('read', 'b'), ('read', 'p')],
        'b': [('read', 'c')],
        'c': [('read', 'a'), ('zero', 'w')],
        'reaches': [('read', 'p'), ('read', 'b')],
        'apart': [('read', 'q'), ('zero', 'v')],
    }
    for name in ('a', 'b', 'c', 'reaches'):
        assert proved([('read', name)], circle, units) is None
    assert proved([('read', 'apart')], circle, units) == frozenset({'v'})
    # After a way round the circle, a formula apart from it still has its own answer.
    assert proved([('read', 'apart'), ('read', 'apart')], circle, units) == frozenset({'v'})


def test_the_face_proof_agrees_with_the_definition_on_random_graphs_of_formulas(units):
    targets = (*STATIC, *MOVING)
    seen = {'constant': 0, 'not constant': 0, 'shared': 0}
    for seed in range(300):
        choose = random.Random(seed)
        names = [f'f{k}' for k in range(choose.randint(2, 6))]
        graph = {}
        for name in names:
            items = []
            for _ in range(choose.randint(1, 3)):
                kind = choose.choices(('formula', 'static', 'moving', 'zero'), (6, 3, 0.4, 2))[0]
                if kind == 'formula':
                    items.append(('read', choose.choice(names)))  # any formula: a circle can form
                elif kind == 'zero':
                    items.append(('zero', choose.choice(ZERO)))
                else:
                    items.append(('read', choose.choice(STATIC if kind == 'static' else MOVING)))
            graph[name] = items
        assert set(targets) >= {target for items in graph.values() for _, target in items} - set(names) - set(
            ZERO
        )
        for name in names:
            entry = [('read', name), ('read', choose.choice(names))]
            expected = by_the_definition(entry, graph)
            assert proved(entry, graph, units) == expected, (seed, name, graph)
            seen['constant' if expected is not None else 'not constant'] += 1
        read = [target for items in graph.values() for kind, target in items if target in graph]
        seen['shared'] += len(read) > len(set(read))
    # The graphs hold both answers, and formulas that more than one formula reads.
    assert min(seen.values()) > 50


def test_the_face_proof_of_a_deep_chain_of_shared_formulas_ends(units):
    graph = {'f0': [('read', 'p'), ('zero', 'w')]}
    graph |= {f'f{k}': [('read', f'f{k - 1}'), ('read', f'f{k - 1}')] for k in range(1, DEPTH + 1)}
    assert proved([('read', f'f{DEPTH}')], graph, units) == frozenset({'w'})
    graph['f0'] = [('read', 'm')]
    assert proved([('read', f'f{DEPTH}')], graph, units) is None
