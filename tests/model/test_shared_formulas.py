"""Formulas that many formulas read: an analysis reads each one once, and gives the answer of the
definition, which follows every way to a formula.

Two analyses follow the formulas that an expression reads: the front end, which says whether an
assertion reads only what is fixed for the run (`semantic.DeclaredAssert.fixed`), and the proof that
an expression is constant on the zero faces of the stocks (`expressions.stock_face_dependencies`),
which the continuous engine reads. Each keeps what it found for a formula. The tests here state the
definition with no memory, on small graphs of formulas, and compare. The chain of 40 formulas, each
reading the one before it twice, is in `tests/language/test_collections.py` for the assertions.
"""

import random
import textwrap

import pytest

from napkin import expressions
from napkin.core.expr import read
from napkin.model.compile import compile_text
from tests.program.examples import UNITS
from tests.units import UNITS as LIBRARY_UNITS

DEPTH = 40  # a chain of this depth has 2^40 ways from its last formula to its first

DIAMOND = """
    s:
        input p: person = 2 person
        w: person = 5 person
        shared = formula({shared})
        left = formula(this.shared + this.p)
        right = formula(this.shared + this.shared)
        top = formula(this.left + this.right)
        apart = formula(this.p + this.p)
    """


def fixed(shared, order):
    """{formula: whether the assertion that reads it is fixed}, with the assertions in `order`."""
    text = textwrap.dedent(DIAMOND.format(shared=shared))
    text += ''.join(f'assert s.{name} >= 0 person\n' for name in order)
    return dict(zip(order, (item.fixed for item in compile_text(text, UNITS).declared.asserts)))


def test_one_formula_on_a_stock_makes_each_assertion_that_reaches_it_one_over_state():
    """A diamond: `top` reads `left` and `right`, and both read `shared`. The answer for `top` is the
    same when another assertion has read `left`, `right` or `shared` before it."""
    names = ['shared', 'left', 'right', 'top', 'apart']
    for order in (names, names[::-1], ['top', 'apart', 'shared', 'right', 'left']):
        assert fixed('this.p', order) == dict.fromkeys(order, True)
        # Only `apart` does not reach the stock.
        assert fixed('this.w', order) == {name: name == 'apart' for name in order}


# ---- the proof on the zero faces ----------------------------------------------------------------------

STATIC, MOVING, ZERO = ('p', 'q'), ('m',), ('w', 'v')


@pytest.fixture(scope='module')
def units():
    return expressions.UnitSystem(LIBRARY_UNITS)


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
