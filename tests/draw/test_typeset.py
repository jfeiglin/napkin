"""The typesetter of the Equations panel (napkin/draw/typeset.py), by its properties:

- Geometry: every atom and rule lies inside the box of the equation, and each atom inside the box of
  its line; no two atoms meet, and no atom meets a rule (by the width estimate); every position is on
  the grid of 0.5; each line fits in `width`; at most `lines` lines; the marker ends a cut equation,
  and only a cut one.
- Reading: the texts of the items in reading order are the reading that a writer in this file gives
  the node (`Reader`), so nothing is lost, added or put in another order. A cut equation reads as a
  part of the whole: its start when it is cut at a line, else what is left after the cut.
- Parentheses: the same parentheses as `notation.latex` in the same places (`skeleton`), with the one
  difference that the module states: a `/` inside a stacked fraction is on the line, with the
  parentheses that the LaTeX gives a `/` in an exponent.
- Scripts and fractions: a subscript is smaller and lower than its base, a superscript smaller and
  higher; a numerator is above its bar and a denominator below.
- Lines: a body breaks only before a top-level `+` or `−`; a `Cases` gives a line for each row.
- Widths: each character's estimate holds its advance in DejaVu Sans and Liberation Sans (frozen
  measurements, `ADVANCES`).
- SVG: it parses, it has no script and no reference out of the file, its colours are those of the
  picture, and the same node gives the same bytes, in other processes too.

These hold on every expression and every assignment of a stage of the model of the notation's tests
that writes every construct, of the water works, and of random nodes.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.draw import notation, svg
from napkin.draw.notation import (
    Assign,
    Call,
    Cases,
    Cmp,
    Count,
    Deriv,
    Elapsed,
    Logic,
    Neg,
    Not,
    Num,
    Op,
    Pos,
    Since,
    Sum,
    Sym,
    Text,
    Time,
)
from napkin.draw.things import Things, event_statements
from napkin.draw.typeset import MARGIN, MARKER, STYLE, Atom, Rule, char_width, run_width, svg_parts, typeset
from napkin.model import semantic
from tests.draw.models import WORKS, compiled
from tests.draw.test_notation import EVERY_CONSTRUCT, NODES, UNITS, built

ROOT = Path(__file__).resolve().parents[2]
NS = '{http://www.w3.org/2000/svg}'

# ---- the symbols of a test ------------------------------------------------------------------------


class Symbols:
    """The symbols of a test: `ζ` and a number for each key, in the order that they are asked for.
    Every third has a prime, and some have a subscript: a letter, a word or a digit. `latex(key)` is
    the same token, for E1's LaTeX."""

    SUBS = (None, None, 'k', 'max', '2')

    def __init__(self):
        self.index = {}

    def number(self, key):
        return self.index.setdefault(key, len(self.index))

    def parts(self, key):
        n = self.number(key)
        return f'ζ{n}', "'" if n % 3 == 1 else '', self.SUBS[n % 5]

    def latex(self, key):
        return f'ζ{self.number(key)}'

    def read(self, key):
        base, prime, sub = self.parts(key)
        return base + prime.replace("'", '′') + (sub or '')


# ---- the reading of a node, written here ----------------------------------------------------------

SIGNS = {'+': '+', '-': '−', '*': '·', '/': '/'}
COMPARE = {'<': '<', '<=': '≤', '>': '>', '>=': '≥', '==': '=', '!=': '≠'}
# Python's precedences; an atom is 9. A `/` is a stacked fraction, an atom, except on the line.
LEVELS = {'or': 1, 'and': 2, '+': 5, '-': 5, '*': 6, '/': 6, '**': 8}


def level(node, inline):
    if isinstance(node, Cases):
        return 0
    if isinstance(node, Logic):
        return LEVELS[node.op]
    if isinstance(node, Not):
        return 3
    if isinstance(node, Cmp):
        return 4
    if isinstance(node, Op):
        return 9 if node.op == '/' and not inline else LEVELS[node.op]
    if isinstance(node, (Neg, Pos)):
        return 7
    return 9


def number_reading(value):
    """A number as Python writes it, with `×10` and its exponent (a minus sign `−`)."""
    if type(value) is int:
        return str(value)
    mantissa, e, power = repr(value).partition('e')
    return mantissa + '×10' + str(int(power)).replace('-', '−') if e else mantissa


def unit_reading(text):
    """A unit: each `^n` after text that is not itself a power is the superscript n; any other `^n`
    is text."""
    out, piece, at = '', '', 0
    for found in re.finditer(r'\^(-?[0-9]+)', text):
        piece += text[at : found.start()]
        at = found.end()
        if piece:
            out += piece + found.group(1).replace('-', '−')
            piece = ''
        else:
            piece = found.group()
    return out + piece + text[at:]


class Reader:
    """The reading of a node: the texts of its parts, in reading order, as the module's text says
    they look. The bar of a fraction reads `/`, a radical `√` and a brace `{`."""

    def __init__(self, symbols):
        self.symbols = symbols

    def operand(self, node, minimum, inline):
        text = self.read(node, inline)
        return f'({text})' if level(node, inline) < minimum else text

    def right(self, node, minimum, inline):
        if isinstance(node, (Neg, Pos)):
            return f'({self.read(node, inline)})'
        return self.operand(node, minimum, inline)

    def equation(self, node, left=None):
        if left is None:
            return self.read(node, False)
        return self.read(left, False) + '=' + self.read(node, False)

    def read(self, node, inline):
        symbol = self.symbols.read
        if isinstance(node, Sym):
            return symbol(node.key)
        if isinstance(node, Num):
            return number_reading(node.value) + ('' if node.unit is None else unit_reading(node.unit))
        if isinstance(node, Text):
            if isinstance(node.word, bool):
                return 'true' if node.word else 'false'
            return node.word
        if isinstance(node, Time):
            return 't'
        if isinstance(node, Op):
            if node.op == '**':
                plain = isinstance(node.left, (Sym, Time, Text, Call, Sum, Since, Count, Elapsed))
                plain = plain or (
                    isinstance(node.left, Num) and node.left.unit is None and 'e' not in repr(node.left.value)
                )
                base = self.read(node.left, inline)
                return (base if plain else f'({base})') + self.read(node.right, True)
            if node.op == '/' and not inline:
                return self.read(node.left, True) + '/' + self.read(node.right, True)
            n = LEVELS[node.op]
            return self.operand(node.left, n, inline) + SIGNS[node.op] + self.right(node.right, n + 1, inline)
        if isinstance(node, (Neg, Pos)):
            sign = '−' if isinstance(node, Neg) else '+'
            if isinstance(node.x, (Neg, Pos)):
                return f'{sign}({self.read(node.x, inline)})'
            return sign + self.operand(node.x, 7, inline)
        if isinstance(node, Cmp):
            text = self.operand(node.items[0], 5, inline)
            for op, item in zip(node.ops, node.items[1:]):
                text += COMPARE[op] + self.operand(item, 5, inline)
            return text
        if isinstance(node, Logic):
            word = '∧' if node.op == 'and' else '∨'
            return word.join(self.operand(item, 3, inline) for item in node.items)
        if isinstance(node, Not):
            return '¬' + self.operand(node.x, 7, inline)
        if isinstance(node, Cases):
            rows = [self.read(value, inline) + 'if' + self.read(test, inline) for test, value in node.pairs]
            return '{' + ''.join(rows) + self.read(node.otherwise, inline) + 'otherwise'
        if isinstance(node, Call):
            if node.name == 'sqrt':
                return '√' + self.read(node.args[0], inline)
            if node.name == 'abs':
                return '|' + self.read(node.args[0], inline) + '|'
            items = []
            for arg in node.args:
                if isinstance(arg, Sum) and arg.fn == node.name:
                    items += [self.read(term, inline) for term in arg.terms]
                else:
                    items.append(self.read(arg, inline))
            items += [name + ':' + self.read(value, inline) for name, value in node.keywords]
            return node.name + '(' + ','.join(items) + ')'
        if isinstance(node, Sum):
            name = 'Σ' if node.fn == 'sum' else node.fn
            return name + '(' + ','.join(self.read(term, inline) for term in node.terms) + ')'
        if isinstance(node, Since):
            return 'τ' + symbol(node.target)
        if isinstance(node, Count):
            return 'N' + symbol(node.target)
        if isinstance(node, Elapsed):
            return 'τ' + symbol(node.key)
        if isinstance(node, Deriv):
            return 'd' + symbol(node.key) + '/dt'
        if isinstance(node, Assign):
            value = node.value if node.op == '=' else Op(node.op[0], Sym(node.target), node.value)
            return symbol(node.target) + '←' + self.read(value, inline)
        raise AssertionError(node)


# ---- the parentheses of E1's LaTeX ----------------------------------------------------------------

TOKENS = re.compile(r'\\left\(|\\right\)|ζ\d+|ψ\d+')
BASE = '__base__'


def mapped(node, change):
    """The node with `change` applied to each node directly under it."""

    def value(item):
        if isinstance(item, notation.Node):
            return change(item)
        if isinstance(item, tuple):
            return tuple(value(part) for part in item)
        return item

    return type(node)(**{f.name: value(getattr(node, f.name)) for f in fields(node)})


def latex_skeleton(text, expand):
    """The parentheses and the symbols of a LaTeX text, in order; a placeholder `ψk` is `expand[ψk]`."""
    out = []
    for found in TOKENS.finditer(text):
        token = found.group()
        if token.startswith('ψ'):
            out += expand[token]
        else:
            out.append({r'\left(': '(', r'\right)': ')'}.get(token, token))
    return out


def expected_skeleton(node, symbols):
    """The parentheses and symbols of E1's LaTeX of `node`, where each stacked fraction has its
    numerator and its denominator as E1 writes them in an exponent: on the line. A placeholder
    `Deriv` stands for each stacked fraction in the LaTeX of the rest: like the fraction, it is an
    atom with no parentheses of its own, and a base that needs them."""
    stacked = []

    def strip(part, inline):
        if isinstance(part, Op) and part.op == '/' and not inline:
            stacked.append((part.left, part.right))
            return Deriv(f'#{len(stacked) - 1}')
        if isinstance(part, Op) and part.op == '**':
            return Op('**', strip(part.left, inline), strip(part.right, True))
        return mapped(part, lambda child: strip(child, inline))

    def symbol(key):
        return f'ψ{key[1:]}' if key.startswith('#') else symbols.latex(key)

    def on_the_line(part):
        found = latex_skeleton(notation.latex(Op('**', Sym(BASE), part), symbol), {})
        assert found[0] == symbols.latex(BASE)
        return found[1:]

    outer = strip(node, False)
    expand = {f'ψ{k}': on_the_line(top) + on_the_line(bottom) for k, (top, bottom) in enumerate(stacked)}
    return latex_skeleton(notation.latex(outer, symbol), expand)


def skeleton(equation):
    """The parentheses and the symbols of a typeset node, in reading order."""
    out = []
    for item in items_of(equation):
        if isinstance(item, Rule):
            shown = item.kind == 'paren'
        else:
            shown = item.kind == 'delimiter' and item.text in ('(', ')')
            shown = shown or (item.kind == 'symbol' and TOKENS.fullmatch(item.text) is not None)
        if shown:
            out.append(item.text)
    return out


# ---- the checks -----------------------------------------------------------------------------------


def items_of(equation):
    return [item for line in equation.lines for item in line.items]


def texts(equation):
    return [item.text for item in items_of(equation)]


def on_grid(value):
    return float(value * 2).is_integer()


def check_geometry(equation, width=None, lines=None):
    """Every property of the boxes of an equation (see the module's text)."""
    box = equation.box
    atoms, rules = equation.atoms(), equation.rules()
    assert equation.height == equation.lines[-1].baseline + equation.descent
    assert equation.ascent == equation.lines[0].baseline
    assert equation.width == max(line.box.width for line in equation.lines)
    for line in equation.lines:
        assert box.contains(line.box)
        for item in line.items:
            assert box.contains(item.box), item
            if isinstance(item, Atom):
                assert line.box.contains(item.box), item
        # A margin of 1 px at each end of a line, 2 px a line.
        assert min(item.box.x for item in line.items) >= 1
        assert max(item.box.right for item in line.items) + 1 <= line.box.right
        if width is not None:
            assert line.box.width <= width, line.reading()
    for upper, lower in zip(equation.lines, equation.lines[1:]):
        assert upper.box.bottom <= lower.box.y
    ordered = sorted(atoms, key=lambda atom: atom.x)
    for k, atom in enumerate(ordered):
        for other in ordered[k + 1 :]:
            if other.x >= atom.box.right:
                break
            assert not atom.box.overlaps(other.box), (atom, other)
    for rule in rules:
        for atom in atoms:
            assert not rule.box.overlaps(atom.box), (rule, atom)
    for atom in atoms:
        assert all(on_grid(v) for v in (atom.x, atom.y, atom.width, atom.size, atom.at)), atom
        assert atom.italic == (atom.kind == 'symbol'), atom
        assert atom.anchor in ('start', 'middle', 'end')
        assert atom.width >= (1 + MARGIN) * sum(char_width(c) for c in atom.text) * atom.size - 1e-9
    for rule in rules:
        assert all(on_grid(v) for _, points in rule.path for v in points), rule
    if lines is not None:
        assert len(equation.lines) <= lines
    markers = [atom for atom in atoms if atom.kind == 'marker']
    if equation.cut:
        assert markers == [equation.lines[-1].items[-1]] and markers[0].text == MARKER
    else:
        assert not markers


def is_subsequence(part, whole):
    found = iter(whole)
    return all(any(item == other for other in found) for item in part)


def check_node(node, width=480, lines=3):
    """Every property of a node, typeset alone and as the value of `y = …` in a width."""
    symbols = Symbols()
    equation = typeset(node, symbols.parts)
    check_geometry(equation)
    assert not equation.cut
    assert equation.reading() == Reader(symbols).equation(node)
    assert skeleton(equation) == expected_skeleton(node, symbols)
    left = Sym('zz.y') if not isinstance(node, Assign) else None
    whole = typeset(node, symbols.parts, left=left)
    limited = typeset(node, symbols.parts, left=left, width=width, lines=lines)
    check_geometry(limited, width, lines)
    if not limited.cut:
        assert limited.reading() == Reader(symbols).equation(node, left)
        return equation
    shown = texts(limited)[:-1]
    if typeset(node, symbols.parts, left=left, width=width).cut:
        assert is_subsequence(shown, texts(whole))
    else:
        assert shown == texts(whole)[: len(shown)]
    return equation


def nodes_of(found):
    """The node of each expression and of each assignment of a stage of a model (`Things`), with the
    keys of its first member."""
    out = [
        notation.build(expression, notation.keys_of(found, place))
        for place, expression in notation.walk(found)
    ]
    for card in found.cards:
        keys = notation.Keys(found, found.cards[card].members[0])
        for event in found.events(card):
            for statement in event_statements(event):
                if isinstance(statement, semantic.DeclaredAssign):
                    out.append(notation.assignment(statement, keys))
    return out


# ---- every model ----------------------------------------------------------------------------------


@pytest.fixture(scope='module')
def synthetic():
    """The models of the tests: the notation's, which writes each construct of the expressions, and
    the water works."""
    return {'every construct': Things(compiled(EVERY_CONSTRUCT)), 'works': Things(compiled(WORKS))}


def test_every_expression_and_assignment_of_a_model_holds_every_property(synthetic):
    found = set()
    for model in synthetic.values():
        for node in nodes_of(model):
            check_node(node)
            check_node(node, width=320, lines=1)
            found |= {type(part) for part in notation.nodes(node)}
    # Every node but those that only the panel makes: a derivative and a sign.
    assert found >= set(notation.NODES.values()) - {Deriv, Pos}


@settings(max_examples=250, derandomize=True, deadline=None)
@given(NODES, st.sampled_from([320, 480, 720]), st.integers(1, 4))
def test_every_property_holds_on_random_nodes(node, width, lines):
    check_node(node, width, lines)
    check_svg(typeset(node, Symbols().parts, width=width, lines=lines))


# ---- the parentheses ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'parentheses'),
    [
        ('a - (b - c)', 1),
        ('(a - b) - c', 0),
        ('a + (b + c)', 1),
        ('(a * b) * c', 0),
        ('-(a ** 2)', 0),
        ('(-a) ** 2', 1),
        ('(a + b) ** 2', 1),
        ('a ** b ** c', 0),
        ('(a ** b) ** c', 1),
        ('a / (b * c)', 0),
        ('(a + b) / (c - d)', 0),
        ('(a + b) * (c - d)', 2),
        ('-a * b', 0),
        ('a * -b', 1),
        ('a - -b', 1),
        ('-(-a)', 1),
        ('not p and (q or r)', 1),
        ('not (a < b)', 1),
        ('not not p', 1),
        ('p or q and r', 1),
        ('(a if p else b) + c', 1),
        ('a == (b if p else c)', 1),
        ('min(a, b) ** 2', 1),
        ('q(2, "m") ** 2', 1),
        ('2.5e-07 ** a', 1),
        ('2.5 ** a', 0),
        ('sqrt(a + b) * abs(a - b)', 0),
    ],
)
def test_the_parentheses_are_those_of_the_latex_in_number_and_place(text, parentheses):
    node = built(text)
    symbols = Symbols()
    equation = typeset(node, symbols.parts)
    found = skeleton(equation)
    assert found.count('(') == found.count(')') == parentheses, equation.reading()
    assert found == expected_skeleton(node, symbols)
    assert found == latex_skeleton(notation.latex(node, symbols.latex), {})


@pytest.mark.parametrize(
    ('text', 'parentheses'),
    [
        ('x / (a / (b * c))', 1),
        ('(a / b) / c', 0),
        ('x / (a * (b / c))', 1),
        ('(1 - a) / a / b', 1),
        ('2 ** (a / (b * c))', 1),
    ],
)
def test_a_division_inside_a_fraction_is_on_the_line_with_the_parentheses_of_an_exponent(text, parentheses):
    node = built(text)
    symbols = Symbols()
    equation = typeset(node, symbols.parts)
    found = skeleton(equation)
    assert found.count('(') == parentheses
    assert found == expected_skeleton(node, symbols)
    assert len([rule for rule in equation.rules() if rule.kind == 'bar']) == (
        0 if text.startswith('2') else 1
    )


# ---- the look -------------------------------------------------------------------------------------


def atoms_of(node, symbol=None, **options):
    return typeset(node, symbol or Symbols().parts, **options).atoms()


def by_text(atoms, text):
    found = [atom for atom in atoms if atom.text == text]
    assert len(found) == 1, (text, [atom.text for atom in atoms])
    return found[0]


@pytest.mark.parametrize(
    ('text', 'signs'),
    [
        ('a * b - c', ['·', '−']),
        ('a <= b', ['≤']),
        ('a >= b', ['≥']),
        ('a != b', ['≠']),
        ('a == b', ['=']),
        ('p and q or not r', ['∧', '∨', '¬']),
        ('-a', ['−']),
    ],
)
def test_each_operator_has_its_mathematical_sign(text, signs):
    atoms = atoms_of(built(text))
    found = [atom.text for atom in atoms if atom.kind in ('operator', 'relation')]
    assert found == signs
    assert not any(atom.italic for atom in atoms if atom.kind in ('operator', 'relation'))


def test_symbols_and_the_time_are_italic_and_the_rest_upright():
    node = built('max(a, 3) * exp(t) + q(2, "m^2/s") + clip(b, 0, 1)')
    atoms = atoms_of(node, lambda key: ('W', '', None))
    for atom in atoms:
        assert atom.italic == (atom.text in ('W', 't'))
    assert {atom.text for atom in atoms if atom.kind == 'function'} == {'max', 'exp', 'clip'}
    assert [atom.text for atom in atoms if atom.kind == 'unit'] == ['m', '2', '/s']


def test_a_unit_follows_its_number_after_a_space_and_its_power_is_a_superscript():
    atoms = atoms_of(Num(12, 'm^2'))
    digits, unit, power = by_text(atoms, '12'), by_text(atoms, 'm'), by_text(atoms, '2')
    assert unit.x > digits.box.right and not unit.italic
    assert power.size < unit.size and power.y < unit.y and power.x >= unit.box.right


@pytest.mark.parametrize('unit', UNITS)
def test_a_unit_reads_as_its_text_with_each_power_after_text_a_superscript(unit):
    atoms = atoms_of(Num(12, unit))
    assert ''.join(atom.text for atom in atoms) == '12' + unit_reading(unit)
    pieces = [atom for atom in atoms if atom.kind == 'unit']
    assert all(not atom.italic for atom in pieces)
    for atom in pieces:
        power = atom.size < atoms[0].size
        assert power == (atom.y < atoms[0].y)
        assert not power or re.fullmatch('−?[0-9]+', atom.text)


def test_a_number_with_an_exponent_is_times_ten_with_a_superscript():
    atoms = atoms_of(Num(1.5e-07))
    assert [atom.text for atom in atoms] == ['1.5', '×', '10', '−7']
    ten, power = by_text(atoms, '10'), by_text(atoms, '−7')
    assert power.size < ten.size and power.y < ten.y


def test_a_symbol_has_its_greek_letter_its_prime_and_its_subscript():
    atoms = atoms_of(Sym('s.a'), lambda key: ('alpha', "'", 'max'))
    base, prime, sub = atoms
    assert (base.text, prime.text, sub.text) == ('α', '′', 'max')
    assert base.italic and not prime.italic and not sub.italic
    assert sub.size < base.size and sub.y > base.y and sub.x >= prime.box.right >= base.box.right
    letter = atoms_of(Sym('s.a'), lambda key: ('W', '', 's'))
    assert letter[1].italic and letter[1].kind == 'symbol'


@settings(derandomize=True, deadline=None)
@given(st.sampled_from(['', "'", "''"]), st.sampled_from(['s', 'max', '12', 'tank']))
def test_a_subscript_is_smaller_and_lower_than_its_base(prime, sub):
    base, *rest = atoms_of(Sym('s.a'), lambda key: ('Q', prime, sub))
    index = rest[-1]
    assert index.text == sub and index.size < base.size and index.y > base.y


@settings(max_examples=120, derandomize=True, deadline=None)
@given(NODES)
def test_a_superscript_is_smaller_than_its_base_and_above_it(base):
    symbols = Symbols()
    node = Op('**', base, Sym('zz.power'))
    equation = typeset(node, symbols.parts)
    token = symbols.latex('zz.power')
    power = by_text(equation.atoms(), token)
    line = equation.lines[0]
    assert power.size < equation.size and power.y < line.baseline
    below = [atom for atom in equation.atoms() if atom.box.right <= power.x]
    assert below and all(atom.y > power.y for atom in below if atom.size == equation.size)


@settings(max_examples=120, derandomize=True, deadline=None)
@given(NODES, NODES)
def test_a_numerator_is_above_its_bar_and_a_denominator_below(top, bottom):
    symbols = Symbols()
    top_keys = keys_of(top)
    renamed = mapped_keys(bottom, lambda key: 'd.' + key)
    equation = typeset(Op('/', top, renamed), symbols.parts)
    (bar,) = [rule for rule in equation.rules() if rule.kind == 'bar']
    tokens = {symbols.latex(key): key for key in symbols.index}
    for atom in equation.atoms():
        key = tokens.get(atom.text)
        if key is None:
            continue
        assert atom.size < equation.size
        assert bar.box.x <= atom.box.x and atom.box.right <= bar.box.right
        if key in top_keys:
            assert atom.box.bottom <= bar.box.y
        else:
            assert key.startswith('d.') and atom.box.y >= bar.box.bottom


def keys_of(node):
    """The keys whose symbols a node shows."""
    out = set()
    for part in notation.nodes(node):
        if isinstance(part, (Sym, Elapsed, Deriv)):
            out.add(part.key)
        elif isinstance(part, (Since, Count)):
            out.add(part.target)
    return out


def mapped_keys(node, change):
    """The node with each key that it shows changed."""
    if isinstance(node, Sym):
        return Sym(change(node.key))
    if isinstance(node, Elapsed):
        return Elapsed(change(node.key))
    if isinstance(node, (Since, Count)):
        return type(node)(change(node.event))
    return mapped(node, lambda child: mapped_keys(child, change))


def test_a_division_in_an_exponent_or_a_fraction_is_on_the_line_and_elsewhere_stacked():
    equation = typeset(built('a / b + 2 ** (a / b) + c / (d / e)'), Symbols().parts)
    assert len([rule for rule in equation.rules() if rule.kind == 'bar']) == 2
    assert [atom.text for atom in equation.atoms() if atom.text == '/'] == ['/', '/']


def test_a_sum_of_a_list_is_a_larger_sigma_and_the_other_lists_are_named():
    atoms = atoms_of(Op('+', Sum('sum', (Sym('s.a'), Sym('s.b'))), Sum('any', (Sym('s.c'),))))
    sigma = by_text(atoms, 'Σ')
    assert sigma.size > 1.3 * atoms[-1].size and not sigma.italic
    assert by_text(atoms, 'any').kind == 'function'


def test_a_root_has_a_radical_and_a_bar_over_its_argument_and_no_parentheses():
    equation = typeset(built('sqrt(a + b / c)'), Symbols().parts)
    kinds = [rule.kind for rule in equation.rules()]
    assert kinds.count('radical') == 1 and kinds.count('overline') == 1
    over = next(rule for rule in equation.rules() if rule.kind == 'overline')
    inside = [atom for atom in equation.atoms()]
    assert all(over.box.x <= atom.box.x and atom.box.right <= over.box.right for atom in inside)
    assert all(atom.box.y >= over.box.y for atom in inside)
    assert not [atom for atom in inside if atom.kind == 'delimiter']


def test_the_clocks_are_tau_and_n_with_the_symbol_as_a_subscript():
    for node, letter in ((Since('s.go', 'done'), 'τ'), (Count('s.go'), 'N'), (Elapsed('s.mode'), 'τ')):
        clock, base, *rest = atoms_of(node, lambda key: ('E', '', 'x'))
        assert clock.text == letter and clock.italic
        assert base.text == 'E' and base.size < clock.size and base.y > clock.y
        assert rest[0].size <= base.size and rest[0].y >= base.y


def test_a_derivative_is_d_s_over_d_t():
    equation = typeset(
        Cmp(('==',), (Deriv('s.level'), Sym('s.inflow'))), lambda key: (key[2].upper(), '', None)
    )
    (bar,) = [rule for rule in equation.rules() if rule.kind == 'bar']
    above = [atom.text for atom in equation.atoms() if atom.box.bottom <= bar.box.y]
    below = [atom.text for atom in equation.atoms() if atom.box.y >= bar.box.bottom]
    assert above == ['d', 'L'] and below == ['d', 't']
    assert equation.reading() == 'dL/dt=I'


def test_a_line_of_an_event_is_an_arrow():
    symbol = lambda key: ('H', '', None)  # noqa: E731
    assert typeset(Assign('s.h', '+=', Num(2)), symbol).reading() == 'H←H+2'
    assert typeset(Assign('s.h', '-=', Op('-', Num(2), Num(1))), symbol).reading() == 'H←H−(2−1)'


def test_cases_have_a_brace_and_a_row_for_each_case():
    node = built('a if p else (b if q else c)')
    equation = typeset(node, Symbols().parts, left=Sym('s.y'))
    assert len(equation.lines) == 3
    (brace,) = [rule for rule in equation.rules() if rule.kind == 'brace']
    for line in equation.lines:
        assert brace.box.y <= line.box.y + 1 and line.box.bottom - 1 <= brace.box.bottom
    words = [atom for atom in equation.atoms() if atom.kind == 'word']
    assert [atom.text for atom in words] == ['if', 'if', 'otherwise'] and not any(a.italic for a in words)
    assert len({atom.x for atom in words}) == 1
    nested = typeset(Op('+', node, Sym('s.c')), Symbols().parts)
    assert len(nested.lines) == 1 and [rule.kind for rule in nested.rules()].count('paren') == 2


def test_the_text_of_a_keyword_and_a_named_value_is_upright():
    node = Cmp(('==',), (Sym('s.mode'), Text('busy')))
    atoms = atoms_of(Op('+', Call('normal', (Num(1),), (('max', Num(3)),)), Num(0)))
    assert by_text(atoms, 'max').kind == 'text' and by_text(atoms, ':').kind == 'delimiter'
    assert not by_text(atoms_of(node), 'busy').italic


# ---- the lines ------------------------------------------------------------------------------------


def long_sum(count):
    """`a0 * b0 + (c1 - d1) - e2 / f2 + …`: terms of three kinds, whose insides hold `+` and `−` too."""
    terms = []
    for k in range(count):
        kind = k % 3
        if kind == 0:
            terms.append(Op('*', Sym(f's.a{k}'), Sym(f's.b{k}')))
        elif kind == 1:
            terms.append(Op('-', Sym(f's.c{k}'), Sym(f's.d{k}')))
        else:
            terms.append(Op('/', Op('+', Sym(f's.e{k}'), Num(1)), Sym(f's.f{k}')))
    node = terms[0]
    for k, term in enumerate(terms[1:], 1):
        node = Op('+' if k % 2 else '-', node, term)
    return node, terms


def term_prefixes(node, terms, symbols, left):
    """The reading of `left = ` and the first n terms, for each n."""
    reader = Reader(symbols)
    out, text = set(), reader.read(left, False) + '='
    prefix = None
    for k, term in enumerate(terms):
        prefix = term if k == 0 else Op('+' if k % 2 else '-', prefix, term)
        out.add(text + reader.read(prefix, False))
    return out


@pytest.mark.parametrize('width', [320, 480, 720])
def test_a_long_sum_breaks_only_before_a_top_level_plus_or_minus(width):
    node, terms = long_sum(24)
    symbols = Symbols()
    left = Sym('s.y')
    equation = typeset(node, symbols.parts, left=left, width=width)
    check_geometry(equation, width)
    assert len(equation.lines) > 1 and not equation.cut
    prefixes = term_prefixes(node, terms, symbols, left)
    so_far = ''
    for line in equation.lines:
        so_far += line.reading()
        assert so_far in prefixes
    assert so_far == Reader(symbols).equation(node, left)
    # The next lines start with their operator, where the body starts on the first line: after "=".
    first = equation.lines[0].items
    relation = next(k for k, item in enumerate(first) if isinstance(item, Atom) and item.kind == 'relation')
    for line in equation.lines[1:]:
        assert line.items[0].text in ('+', '−') and line.items[0].kind == 'operator'
        assert line.items[0].x == first[relation + 1].x > first[relation].box.right


@pytest.mark.parametrize('lines', [1, 2, 3])
def test_at_most_lines_lines_and_a_cut_ends_with_the_marker(lines):
    node, terms = long_sum(40)
    symbols = Symbols()
    left = Sym('s.y')
    whole = typeset(node, symbols.parts, left=left, width=480)
    assert len(whole.lines) > lines and not whole.cut
    equation = typeset(node, symbols.parts, left=left, width=480, lines=lines)
    check_geometry(equation, 480, lines)
    assert equation.cut and len(equation.lines) == lines
    assert equation.lines[-1].items[-1].text == MARKER
    shown = equation.reading().removesuffix(MARKER)
    assert shown in term_prefixes(node, terms, symbols, left)
    assert texts(equation)[:-1] == texts(whole)[: len(texts(equation)) - 1]


def test_one_line_of_a_long_sum_is_its_start_and_the_marker():
    node, _ = long_sum(40)
    equation = typeset(node, Symbols().parts, width=720, lines=1)
    check_geometry(equation, 720, 1)
    assert equation.cut and len(equation.lines) == 1 and equation.atoms()[-1].kind == 'marker'


def test_a_term_wider_than_the_width_is_cut_at_the_width_with_the_marker():
    product = Sym('s.p0')
    for k in range(1, 60):
        product = Op('*', product, Sym(f's.p{k}'))
    fraction = Op('/', Num(1), Op('+', Num(1), product))
    for node in (product, fraction, Op('+', Sym('s.a'), fraction)):
        symbols = Symbols()
        equation = typeset(node, symbols.parts, left=Sym('s.y'), width=400, lines=3)
        check_geometry(equation, 400, 3)
        assert equation.cut and equation.lines[-1].items[-1].text == MARKER
        whole = typeset(node, symbols.parts, left=Sym('s.y'))
        assert is_subsequence(texts(equation)[:-1], texts(whole))
    # A cut fraction keeps the start of its numerator (here all of it) and of its denominator.
    shown = texts(equation)
    assert shown[shown.index('/') - 1 : shown.index('/') + 2] == ['1', '/', '1']


def test_a_cases_gives_a_line_for_each_row_up_to_lines():
    node = built('a if p else (b if q else (c if r else d))')
    symbols = Symbols()
    full = typeset(node, symbols.parts, left=Sym('s.y'), width=480)
    assert len(full.lines) == 4 and not full.cut
    cut = typeset(node, symbols.parts, left=Sym('s.y'), width=480, lines=2)
    check_geometry(cut, 480, 2)
    assert len(cut.lines) == 2 and cut.cut and cut.lines[-1].items[-1].text == MARKER
    (brace,) = [rule for rule in cut.rules() if rule.kind == 'brace']
    assert brace.box.bottom <= cut.lines[1].box.bottom


def test_with_no_width_a_sum_is_one_line():
    node, _ = long_sum(40)
    equation = typeset(node, Symbols().parts)
    assert len(equation.lines) == 1 and not equation.cut


def test_the_limits_are_checked():
    with pytest.raises(ValueError):
        typeset(Num(1), Symbols().parts, lines=0)
    with pytest.raises(ValueError):
        typeset(Num(1), Symbols().parts, width=0)
    with pytest.raises(ValueError):
        typeset(Num(1), Symbols().parts, left=Sym('s.y'), relation='≈')


# ---- the widths -----------------------------------------------------------------------------------

# The largest advance width (em) of each character in DejaVu Sans and Liberation Sans (the metrics of
# Arial), regular and oblique: the fonts of a Linux `sans-serif` and of Windows, measured from the
# font files on 2026-11-11. A glyph that a font lacks is left out of that font.
ADVANCES = {
    '0': 0.636, '1': 0.636, '2': 0.636, '3': 0.636, '4': 0.636, '5': 0.636, '6': 0.636, '7': 0.636,
    '8': 0.636, '9': 0.636, 'a': 0.613, 'b': 0.635, 'c': 0.55, 'd': 0.635, 'e': 0.615, 'f': 0.352,
    'g': 0.635, 'h': 0.634, 'i': 0.278, 'j': 0.278, 'k': 0.579, 'l': 0.278, 'm': 0.974, 'n': 0.634,
    'o': 0.612, 'p': 0.635, 'q': 0.635, 'r': 0.411, 's': 0.521, 't': 0.392, 'u': 0.634, 'v': 0.592,
    'w': 0.818, 'x': 0.592, 'y': 0.592, 'z': 0.525, 'A': 0.684, 'B': 0.686, 'C': 0.722, 'D': 0.77,
    'E': 0.667, 'F': 0.611, 'G': 0.778, 'H': 0.752, 'I': 0.295, 'J': 0.5, 'K': 0.667, 'L': 0.557,
    'M': 0.863, 'N': 0.748, 'O': 0.787, 'P': 0.667, 'Q': 0.787, 'R': 0.722, 'S': 0.667, 'T': 0.611,
    'U': 0.732, 'V': 0.684, 'W': 0.989, 'X': 0.685, 'Y': 0.667, 'Z': 0.685, '!': 0.401, '"': 0.46,
    '#': 0.838, '$': 0.636, '%': 0.95, '&': 0.78, "'": 0.275, '(': 0.39, ')': 0.39, '*': 0.5,
    '+': 0.838, ',': 0.318, '-': 0.361, '.': 0.318, '/': 0.337, ':': 0.337, ';': 0.337, '<': 0.838,
    '=': 0.838, '>': 0.838, '?': 0.556, '@': 1.015, '[': 0.39, '\\': 0.337, ']': 0.39, '^': 0.838,
    '_': 0.556, '`': 0.5, '{': 0.636, '|': 0.337, '}': 0.636, '~': 0.838, ' ': 0.318, '−': 0.838,
    '·': 0.333, '×': 0.838, '≤': 0.838, '≥': 0.838, '≠': 0.838, '←': 1.0, '∧': 0.75, '∨': 0.75,
    '¬': 0.838, '±': 0.838, 'τ': 0.602, 'Σ': 0.632, '…': 1.0, '′': 0.227, 'α': 0.659, 'β': 0.638,
    'γ': 0.592, 'δ': 0.612, 'ϵ': 0.615, 'ε': 0.541, 'ζ': 0.544, 'η': 0.634, 'θ': 0.612, 'ϑ': 0.619,
    'ι': 0.338, 'κ': 0.589, 'λ': 0.592, 'μ': 0.636, 'ν': 0.559, 'ξ': 0.558, 'ο': 0.612, 'π': 0.69,
    'ρ': 0.635, 'σ': 0.634, 'υ': 0.579, 'ϕ': 0.66, 'φ': 0.66, 'χ': 0.578, 'ψ': 0.728, 'ω': 0.837,
    'Α': 0.684, 'Β': 0.686, 'Γ': 0.57, 'Δ': 0.684, 'Ε': 0.667, 'Ζ': 0.685, 'Η': 0.752, 'Θ': 0.787,
    'Ι': 0.295, 'Κ': 0.667, 'Λ': 0.684, 'Μ': 0.863, 'Ν': 0.748, 'Ξ': 0.65, 'Ο': 0.787, 'Π': 0.752,
    'Ρ': 0.667, 'Τ': 0.611, 'Υ': 0.667, 'Φ': 0.837, 'Χ': 0.685, 'Ψ': 0.835, 'Ω': 0.764,
}  # fmt: skip


def test_each_character_is_at_least_as_wide_as_in_the_common_fonts():
    for char, advance in ADVANCES.items():
        assert char_width(char) * (1 + MARGIN) >= advance, char


@settings(derandomize=True, deadline=None)
@given(st.text(alphabet=''.join(ADVANCES), max_size=30), st.sampled_from([6.0, 7.5, 9.0, 10.5, 14.5]))
def test_a_run_is_as_wide_as_its_glyphs_in_the_common_fonts(text, size):
    width = run_width(text, size)
    assert width >= sum(ADVANCES[char] for char in text) * size and on_grid(width)


# ---- the SVG --------------------------------------------------------------------------------------


def check_svg(equation, x=10.0, y=20.5):
    """The SVG of an equation: it parses, it stands alone, each tspan is an atom at its anchor, each
    path a rule, and every position is on the grid of 0.5."""
    text = svg_parts(equation, x, y)
    root = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{text}</svg>')
    tags = [element.tag.removeprefix(NS) for element in root.iter()]
    assert set(tags) <= {'svg', 'text', 'tspan', 'path'}
    assert 'url(' not in text and '@import' not in text
    for element in root.iter():
        for key in element.attrib:
            assert not key.startswith('on') and not key.endswith('href')
    spans = list(root.iter(f'{NS}tspan'))
    atoms = equation.atoms()
    assert [span.text or '' for span in spans] == [atom.text for atom in atoms]
    for span, atom in zip(spans, atoms):
        assert float(span.get('x')) == x + atom.at and float(span.get('y')) == y + atom.y
        assert span.get('text-anchor', 'start') == atom.anchor
        assert (span.get('font-style') == 'italic') == atom.italic
    paths = list(root.iter(f'{NS}path'))
    assert len(paths) == len(equation.rules())
    for element in root.iter():
        for key in ('x', 'y'):
            if key in element.attrib:
                assert on_grid(float(element.get(key)))
    for path in paths:
        assert all(on_grid(float(value)) for value in re.findall(r'-?[0-9.]+', path.get('d')))
    check_colours(root)
    return text


def check_colours(root):
    """A light colour of the picture on each text and path, with a class whose rule in `STYLE` gives
    the colour of each theme."""
    light = {pair[0] for pair in svg.COLOURS.values()}
    styled = set(re.findall(r'\.([a-z][a-z0-9-]*)\{', ''.join(STYLE)))
    used = set(re.findall(r'var\(--([a-z-]+)\)', ''.join(STYLE)))
    assert used <= set(svg.COLOURS)
    for element in root.iter():
        tag = element.tag.removeprefix(NS)
        if tag in ('text', 'path'):
            assert element.get('fill') or element.get('stroke')
        for key in ('fill', 'stroke'):
            value = element.get(key, '')
            if value.startswith('#'):
                assert value in light
                assert set(element.get('class', '').split()) & styled


def test_the_svg_of_every_construct_parses_and_stands_alone(synthetic):
    for model in synthetic.values():
        for node in nodes_of(model):
            check_svg(typeset(node, Symbols().parts, left=Sym('zz.y'), width=480, lines=2))


def test_every_text_is_escaped():
    words = ['a<b', 'R&D', '"x"', "it's", '</text>', ']]>', '&amp;']
    node = Logic('or', tuple(Cmp(('==',), (Sym('s.mode'), Text(word))) for word in words))
    equation = typeset(node, Symbols().parts)
    check_svg(equation)
    text = svg_parts(equation, 0, 0)
    assert '<b' not in text and '</text></text>' not in text


SAME = '(a + b) / (c - d) * sqrt(a ** 2 + b) - max(a, b, 2.5e-07) if a < b else -(c / d)'


def letter(key):
    """A symbol of a test: the first letter of the member, and its other letters as the subscript."""
    member = key.rpartition('.')[2]
    return member[:1].upper(), '', member[1:] or None


def test_the_same_node_gives_the_same_bytes_in_other_processes():
    node = built(SAME)
    here = svg_parts(typeset(node, letter, width=480, lines=3), 3.5, 7)
    assert here == svg_parts(typeset(built(SAME), letter, width=480, lines=3), 3.5, 7)
    code = (
        'import hashlib, json, sys\n'
        'from napkin.draw import notation\n'
        'from napkin.draw.typeset import svg_parts, typeset\n'
        f'node = notation.from_dict(json.loads({notation.to_json(node)!r}))\n'
        'def letter(key):\n'
        "    member = key.rpartition('.')[2]\n"
        "    return member[:1].upper(), '', member[1:] or None\n"
        'text = svg_parts(typeset(node, letter, width=480, lines=3), 3.5, 7)\n'
        'sys.stdout.write(hashlib.sha256(text.encode()).hexdigest())\n'
    )
    digests = set()
    for seed in ('0', '4242'):
        env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONHASHSEED': seed}
        done = subprocess.run(
            [sys.executable, '-B', '-c', code],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        digests.add(done.stdout)
    assert digests == {hashlib.sha256(here.encode()).hexdigest()}
