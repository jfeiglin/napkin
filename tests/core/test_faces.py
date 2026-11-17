"""The proof that an expression is constant on the zero faces of stocks (`napkin/core/faces.py`).

The meaning of the proof is checked by values: an expression that the proof admits has one value for
all states in which the same stocks are at zero, whatever the other stocks hold. An expression that
reads a stock in another way, or a name that is not fixed, is not admitted.
"""

import random

from napkin.core import expr, faces
from tests.core.reference import UNITS, walked

STOCKS = ('s.a', 's.b', 's.c')
FIXED = {'p.x': 2.0, 'p.y': -1.5, 'p.on': True}
PARAMETERS = {'p.zero': 0, 'p.none': 0.0, 'p.one': 1}
ZEROS = ('0', '0.0', 'p.zero', 'p.none', 'p.zero * p.one', 'p.one - 1')


def switch(rng):
    """A comparison of a stock with an expression of parameters whose value is zero, on either side."""
    stock, zero, op = rng.choice(STOCKS), rng.choice(ZEROS), rng.choice(('>', '<=', '==', '!=', '>=', '<'))
    return f'{stock} {op} {zero}' if rng.random() < 0.6 else f'{zero} {op} {stock}'


def made(rng, depth):
    """The text of a random expression that reads the stocks only in such comparisons."""
    if depth == 0 or rng.random() < 0.2:
        return rng.choice(('p.x', 'p.y', '1', '0.5', '3', 'p.zero'))
    a, b = made(rng, depth - 1), made(rng, depth - 1)
    k = rng.randrange(8)
    if k < 3:
        return f'({a} {rng.choice("+-*")} {b})'
    if k == 3:
        return f'{rng.choice(("min", "max"))}({a}, {b})'
    if k == 4:
        return f'({a} if {switch(rng)} and p.on else {b})'
    if k == 5:
        return f'({a} if {switch(rng)} or not {switch(rng)} else {b})'
    if k == 6:
        return f'({a} if p.x > p.y else abs({b}))'
    return f'({a} if {switch(rng)} else {b})'


def test_an_admitted_expression_has_one_value_for_one_set_of_stocks_at_zero():
    rng = random.Random(20261112)
    used_some, compared = 0, 0
    for _ in range(1500):
        node = expr.read(made(rng, rng.randrange(1, 5)))
        found = faces.constant_on_faces(
            node, FIXED.keys() | PARAMETERS.keys(), set(STOCKS), {}, PARAMETERS, UNITS
        )
        assert found is not None and found <= set(STOCKS) and found <= expr.names(node)
        used_some += bool(found)
        for _ in range(4):
            at_zero = {stock for stock in STOCKS if rng.random() < 0.5}
            states = [
                {stock: 0.0 if stock in at_zero else rng.uniform(0.01, 50.0) for stock in STOCKS}
                for _ in range(3)
            ]
            values = [walked(node, {**FIXED, **PARAMETERS, **state}) for state in states]
            assert values[0] == values[1] == values[2], (expr.text(node), states)
            compared += 1
    assert used_some > 800 and compared == 6000


def proof(source, formulas=None):
    nodes = {name: expr.read(text) for name, text in (formulas or {}).items()}
    fixed = FIXED.keys() | PARAMETERS.keys()
    return faces.constant_on_faces(expr.read(source), fixed, set(STOCKS), nodes, PARAMETERS, UNITS)


def test_what_moves_in_another_way_is_not_admitted():
    assert proof('p.x if s.a > 0 else 0') == {'s.a'}
    # A stock outside a comparison, or compared with what is not zero or not a parameter alone.
    for source in (
        's.a',
        'p.x * s.a',
        'p.x if s.a > 1 else 0',
        'p.x if s.a > p.one else 0',
        'p.x if s.a > s.b else 0',
    ):
        assert proof(source) is None, source
    assert proof('p.x if s.a > p.x * 0 else 0') is None  # zero, but not of the parameters alone
    # The time, and a name that is not fixed.
    assert proof('p.x * t') is None and proof('p.x + other.name') is None
    # A chain of two comparisons reads its stock as a value.
    assert proof('p.x if 0 < s.a < 1 else 0') is None
    # A zero that cannot be computed proves nothing.
    assert proof('p.x if s.a > 1 / p.zero else 0') is None


def test_a_formula_is_constant_when_what_it_reads_is():
    formulas = {
        'c.open': 's.a > 0',
        'c.rate': 'p.x if c.open and s.b > p.zero else 0',
        'c.loop': 'c.loop + 1',
    }
    assert proof('c.rate * 2', formulas) == {'s.a', 's.b'}
    assert proof('c.rate + c.rate', formulas) == {'s.a', 's.b'}
    assert proof('c.rate + c.loop', formulas) is None  # a formula on a circle is never constant
    assert proof('c.rate + s.c', formulas) is None
    # A formula that many read is walked once: the answer of a wide chain comes at once.
    chain = {'f0': 'p.x if s.a > 0 else 0', **{f'f{k}': f'f{k - 1} + f{k - 1}' for k in range(1, 60)}}
    assert proof('f59', chain) == {'s.a'}
