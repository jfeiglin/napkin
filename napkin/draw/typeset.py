"""napkin's own typesetter for the Equations panel (D-53): it draws a math node of `notation.py` as SVG
`<text>` and `<tspan>`s, with paths for the bars, the radicals, the braces and the tall parentheses.
An equation then shows the same in a browser, an `<img>`, Inkscape and a PDF converter: it needs no
script and no font of its own. The same node gives the same bytes.

`typeset(node, symbol, …)` measures and places a node: an `Equation`, with its lines, and in each line
its atoms (`Atom`: a run of text in one style and size) and its rules (`Rule`: a path), in reading
order. `svg_parts(equation, x, y)` writes it, and `STYLE` holds the CSS rules of its classes for the
`<style>` of the picture.

`symbol(key)` gives the parts of the symbol of a key: (base, prime, subscript). The base is a letter,
the name of a Greek letter (`alpha`, `Omega`: drawn as α and Ω) or any text; the prime is a text of
primes (`'`), a yes/no or a number of primes; the subscript is a text or None. The keys are those of
`notation.latex`: a value, a flow or an event (`entity.member`), or an outcome (`entity.event.outcome`).

The look:
- A symbol is italic. A subscript of one letter is italic; any other subscript (a word, a number) is
  upright. The prime follows the base, and the subscript follows the prime.
- A number, a unit, a function's name, a named value and the words "if" and "otherwise" are upright. A
  unit follows its number after a thin space; a power of a unit (`m^2`) is a superscript. A number with
  an exponent is `1.5 × 10` with the exponent as a superscript.
- `*` is `·`, `-` is the minus sign `−`, `<=` is `≤`, `>=` is `≥`, `==` is `=`, `!=` is `≠`, `and`, `or`
  and `not` are `∧`, `∨` and `¬`, and a line of an event is `S ← v`. The time is an italic `t`. A
  membership test is `x ∈ [lo, hi]`, as the model writes it (`x in [lo, hi]`): `∈` is a relation, and
  the ends are in brackets, as the LaTeX writes them.
- `Since(e)` and `Elapsed(s)` are τ, and `Count(e)` is N, with the symbol of what they read as the
  subscript (`clocks` changes the letters). A subscript of that symbol is a subscript too, at the
  smallest size (`MIN_SIZE`).
- Sub- and superscripts are `SCRIPT` × the size, `SUB_DROP` em below and `SUP_RISE` em above the
  baseline (higher above a tall base). Each atom has its own absolute x and y: no `baseline-shift`,
  which Firefox ignores.
- A `/` that `notation.precedence` makes an atom (not in an exponent) is a stacked fraction with a
  bar, its numerator and denominator centred at `FRACTION` × the size. A `/` inside a stacked fraction
  or in an exponent is `a/b` on the line, with the parentheses that E1's LaTeX gives a `/` in an
  exponent. That is the one place where the parentheses differ from the LaTeX, which stacks every
  fraction outside an exponent.
- `Deriv(S)` is always a stacked fraction of `d S` over `d t`, as the LaTeX writes it.
- `sqrt(x)` is a radical sign with a bar over x, as `\\sqrt{x}` draws it, so it has no parentheses;
  `abs(x)` is `|x|`. A sum of a list is a larger Σ (`SIGMA` × the size) before the list, as the
  LaTeX writes `\\sum(…)`.
- `Cases` is a left brace and one row for each case: the value, then "if" and the condition, and the
  last row the value and "otherwise". The values and the words are in two columns.
- The parentheses are those of `notation.latex` (its `precedence` and its rules for a sign, a base and
  `not`). A parenthesis, a bar of `abs`, a bracket of an interval and a brace around content taller
  than a line are paths.

The width of a run is the estimate of `layout.text_width` (`EM` for each character), with other widths
for the characters that need them: an upper-case letter (a Greek capital too) is `CAPITAL` em, and
`WIDTHS` gives the narrow characters, the operators and the wide letters. Each character's width is at
least its advance in the common sans-serif fonts, DejaVu Sans (whose operators are 0.84 em) and
Liberation Sans (Arial's metrics) included. Then `MARGIN` (10%) is added. Each run is placed at that
width, so the runs of a line do not meet when a real font is up to 10% wider still. The glyphs of a run
sit at the start, the middle or the end of its width (`ANCHORS`, written as `text-anchor`): an
operator in the middle, a function's name against its parenthesis, a base against its subscript or
its exponent. Each line has `EDGE` px at each end (2 px a line), and the equation `EDGE` px at the top
and the bottom.

The lines (with `width` and `lines`):
- An equation is `left = node` (`left` and `relation` given), a line of an event (`Assign`), a single
  comparison (`Cmp`), or a node alone. Its body is the part after the relation, or the whole node.
- A body that is a sum or a difference breaks before a top-level `+` or `−`: the greedy way, as many
  terms on a line as fit in `width`. The next lines start where the body starts on the first line
  (after "="), or `INDENT` em in when nothing is before the body, or when that is too far in. The
  first term goes to the next line when it fits there and not after the relation.
- A body that is a `Cases` gives one line for each row, with the brace over all of them.
- At most `lines` lines. When the equation needs more, the last line ends with `MARKER`; the terms
  that do not fit with the marker go too. A line with a single term wider than `width` is cut at the
  width: the atoms and the rules past `width` less the marker go (a bar is shortened, and the
  numerator and the denominator of its fraction move to its left end first), the marker follows, and
  that line is the last. So each line fits in `width` (when `width` holds the marker and what is
  before the body), and nothing is cut without the marker. `Equation.cut` says whether something was
  cut.

Every position is on the grid of 0.5 px (`layout.half`, `layout.up`), and so is every size.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from .layout import EM, TEXT_SIZE, Box, half, text_width, up
from .notation import (
    Assign,
    Call,
    Cases,
    Cmp,
    Count,
    Deriv,
    Elapsed,
    In,
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
    precedence,
)

# The sizes, as parts of the size of the text around them, and the smallest size of a script.
SCRIPT = 0.7
FRACTION = 0.85
SIGMA = 1.4
MIN_SIZE = 6.0
# The places of the scripts and of the bar of a fraction, in em of the size of their base.
SUB_DROP = 0.3
SUP_RISE = 0.45
AXIS = 0.3  # the bar of a fraction and the middle of a brace, above the baseline
# The top and the bottom of a run, in em above and below its baseline.
ASCENT = 0.8
DESCENT = 0.25
# Content taller than this (em above or below the baseline) gets drawn parentheses.
TALL_ASCENT = 1.1
TALL_DESCENT = 0.7
# The widths in em: each character (`layout.EM`), an upper-case letter, and the characters whose width
# is another, each at least its advance in the common sans-serif fonts (Arial and Liberation Sans,
# Helvetica, Roboto, Segoe UI, Noto Sans, DejaVu Sans and Verdana); then the margin of each run.
CAPITAL = 0.72
NARROW = 0.45
OPERATOR = 0.8
WIDTHS = {
    **dict.fromkeys("()[]|,.:;!/·′' ijlIftr", NARROW),
    **dict.fromkeys('+−=<>≤≥≠×¬±∧∨#&^~∈', OPERATOR),
    **{'m': 0.9, 'w': 0.8, 'M': 0.9, 'W': 1.0, 'Μ': 0.9, '%': 0.9, '@': 1.0, '…': 1.0, '—': 1.0, '←': 1.0},
    '⇔': 1.0,
    **dict.fromkeys('ωψφϕπΦΨ', 0.8),
}
MARGIN = 0.1
EDGE = 1.0
# The spaces, in em: around a binary operator, a relation, `∧` and `∨`; after a comma; before a unit;
# before "if"; after "if"; between two lines; a continued line. A run is wider than its glyphs in most
# fonts, and the glyphs sit inside it (`ANCHORS`), so the spaces are small.
BINARY = 0.1
RELATION = 0.15
LOGIC_SPACE = 0.12
COMMA = 0.12
THIN = 0.12
QUAD = 1.0
WORD_SPACE = 0.3
LINE_GAP = 0.35
INDENT = 1.0
# Where the glyphs of a run sit in its box, by kind: at its start, in its middle or at its end. A
# symbol's base with a prime or a subscript sits at the end, against them; so does a function's name,
# against its parenthesis.
ANCHORS = {
    'symbol': 'middle',
    'prime': 'start',
    'index': 'start',
    'number': 'middle',
    'unit': 'start',
    'text': 'middle',
    'function': 'end',
    'operator': 'middle',
    'relation': 'middle',
    'delimiter': 'middle',
    'word': 'start',
    'marker': 'start',
}
_DELIMITER_ANCHORS = {'(': 'end', ')': 'start', '[': 'end', ']': 'start', ',': 'start', ':': 'start'}

MARKER = '… (continues in the LaTeX)'
CLOCKS = {'since': 'τ', 'count': 'N', 'elapsed': 'τ'}
RELATIONS = {'=': '=', '==': '=', '⇔': '⇔', '<-': '←', '<': '<', '<=': '≤', '>': '>', '>=': '≥', '!=': '≠'}
_CMP = {'<': '<', '<=': '≤', '>': '>', '>=': '≥', '==': '=', '!=': '≠'}
_SIGNS = {'+': '+', '-': '−', '*': '·', '/': '/'}
_LOGIC_SIGNS = {'and': '∧', 'or': '∨'}
_LIST_NAMES = {'sum': 'Σ'}
_POWER = re.compile(r'\^(-?[0-9]+)')
_GREEK_SMALL = {
    'alpha': 'α',
    'beta': 'β',
    'gamma': 'γ',
    'delta': 'δ',
    'epsilon': 'ϵ',
    'varepsilon': 'ε',
    'zeta': 'ζ',
    'eta': 'η',
    'theta': 'θ',
    'vartheta': 'ϑ',
    'iota': 'ι',
    'kappa': 'κ',
    'lambda': 'λ',
    'mu': 'μ',
    'nu': 'ν',
    'xi': 'ξ',
    'omicron': 'ο',
    'pi': 'π',
    'rho': 'ρ',
    'sigma': 'σ',
    'tau': 'τ',
    'upsilon': 'υ',
    'phi': 'ϕ',
    'varphi': 'φ',
    'chi': 'χ',
    'psi': 'ψ',
    'omega': 'ω',
}
GREEK = _GREEK_SMALL | {
    name.capitalize(): letter.upper() for name, letter in _GREEK_SMALL.items() if not name.startswith('var')
}
# The kinds of atoms that are muted, and the kinds of rules that a cut shortens.
MUTED = ('word', 'marker')
SHORTENED = ('bar', 'overline')
# The CSS rules of the classes of `svg_parts`, for the `<style>` of the picture.
STYLE = (
    '.napkin-draw .math{fill:var(--ink)}',
    '.napkin-draw .math-symbol{font-style:italic}',
    '.napkin-draw .math-muted{fill:var(--muted)}',
    '.napkin-draw .math-rule{stroke:var(--ink)}',
)


# ---- the result -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Atom:
    """A run of text: its text, the x of its left and the y of its baseline (from the top left corner
    of the equation), its size, whether it is italic, its kind, its estimated width, and where its
    glyphs sit in that width (`anchor`). The kinds: `symbol` (italic), `prime`, `index` (an upright
    subscript of a symbol), `number`, `unit`, `text` (a named value, a yes/no, the name of a keyword),
    `function`, `operator`, `relation`, `delimiter`, `word` ("if", "otherwise") and `marker`."""

    text: str
    x: float
    y: float
    size: float
    italic: bool
    kind: str
    width: float
    anchor: str = 'start'

    @property
    def at(self):
        """The x of its anchor (`text-anchor`): its left, its middle or its right."""
        if self.anchor == 'middle':
            return self.x + half(self.width / 2)
        return self.x + self.width if self.anchor == 'end' else self.x

    @property
    def box(self):
        """The box that the run takes, by the estimate."""
        top, bottom = _top(self.size), _bottom(self.size)
        return Box(self.x, self.y - top, self.width, top + bottom)


@dataclass(frozen=True)
class Rule:
    """A path: its kind (`bar` of a fraction, `overline` and `radical` of a root, `brace`, `paren`,
    `bars` of `abs`, and `bracket` of an interval), its commands ((letter, (x, y, …)), …) in the
    coordinates of the equation, the width of its stroke, the text that it stands for in the reading
    order ('/', '', '√', '{', '(', ')', '|', '[' or ']'), and its box (the box of its points)."""

    kind: str
    path: tuple
    stroke: float
    text: str
    box: Box


@dataclass(frozen=True)
class Line:
    """A line: its atoms and rules in reading order, the y of its baseline, and its box (from x 0, with
    `EDGE` at each end)."""

    items: tuple
    baseline: float
    box: Box

    @property
    def width(self):
        return self.box.width

    def reading(self):
        """The texts of the items, in reading order."""
        return ''.join(item.text for item in self.items)


@dataclass(frozen=True)
class Equation:
    """A typeset node: its lines, its width and height, its ascent (from the top to the first
    baseline) and descent (from the last baseline to the bottom), whether something was cut, and its
    size."""

    lines: tuple
    width: float
    height: float
    ascent: float
    descent: float
    cut: bool
    size: float

    @property
    def box(self):
        return Box(0.0, 0.0, self.width, self.height)

    def atoms(self):
        return [item for line in self.lines for item in line.items if isinstance(item, Atom)]

    def rules(self):
        return [item for line in self.lines for item in line.items if isinstance(item, Rule)]

    def reading(self):
        """The texts of the items of every line, in reading order."""
        return ''.join(line.reading() for line in self.lines)


# ---- widths and sizes -----------------------------------------------------------------------------


def char_width(char):
    """The width of a character, in em: `WIDTHS`, else `CAPITAL` for an upper-case letter (a Greek
    capital too), else `layout.EM`."""
    if char in WIDTHS:
        return WIDTHS[char]
    return CAPITAL if char.isupper() else EM


def run_width(text, size):
    """The width of a run in px: `layout.text_width` with the width of each character (`char_width`),
    plus `MARGIN`; rounded up to 0.5."""
    other = sum(char_width(char) - EM for char in text)
    return up((1 + MARGIN) * (text_width(text, size) + other * size))


def scaled(size, factor):
    """A size times `factor`, on the grid of 0.5 and not below `MIN_SIZE`."""
    return max(MIN_SIZE, half(size * factor))


def _space(em, size):
    return max(0.5, half(em * size))


def _top(size):
    return up(ASCENT * size)


def _bottom(size):
    return up(DESCENT * size)


def _stroke(size):
    return max(0.6, round(0.075 * size, 1))


# ---- the pieces while they are set ----------------------------------------------------------------


class _Run:
    """An atom while it is set: x from the left of its piece, y from the piece's baseline."""

    __slots__ = ('anchor', 'italic', 'kind', 'size', 'text', 'width', 'x', 'y')

    def __init__(self, text, size, kind, italic, anchor=None):
        self.text, self.size, self.kind, self.italic = text, size, kind, italic
        if anchor is None:
            anchor = _DELIMITER_ANCHORS.get(text, ANCHORS[kind]) if kind == 'delimiter' else ANCHORS[kind]
        self.anchor = anchor
        self.width = run_width(text, size)
        self.x = self.y = 0.0

    def move(self, dx, dy):
        self.x += dx
        self.y += dy

    def left(self):
        return self.x

    def right(self):
        return self.x + self.width

    def frozen(self, dx, dy):
        return Atom(
            self.text, self.x + dx, self.y + dy, self.size, self.italic, self.kind, self.width, self.anchor
        )


class _Path:
    """A rule while it is set: its points move with its piece. The bar of a fraction keeps the items of
    its numerator and its denominator (`parts`) and the space at its ends (`pad`), for a cut."""

    __slots__ = ('commands', 'kind', 'pad', 'parts', 'stroke', 'text')

    def __init__(self, kind, commands, stroke, text):
        self.kind, self.stroke, self.text = kind, stroke, text
        self.commands = [(letter, list(points)) for letter, points in commands]
        self.parts, self.pad = (), 0.0

    def left(self):
        return self.bounds()[0]

    def move(self, dx, dy):
        for _, points in self.commands:
            for k in range(0, len(points), 2):
                points[k] += dx
                points[k + 1] += dy

    def bounds(self):
        xs = [x for _, points in self.commands for x in points[0::2]]
        ys = [y for _, points in self.commands for y in points[1::2]]
        return min(xs), min(ys), max(xs), max(ys)

    def right(self):
        return self.bounds()[2]

    def shorten(self, limit):
        """Ends a straight rule at x `limit`."""
        for _, points in self.commands:
            for k in range(0, len(points), 2):
                points[k] = min(points[k], limit)

    def frozen(self, dx, dy):
        commands = tuple(
            (letter, tuple(value + (dx if k % 2 == 0 else dy) for k, value in enumerate(points)))
            for letter, points in self.commands
        )
        x0, y0, x1, y1 = self.bounds()
        return Rule(self.kind, commands, self.stroke, self.text, Box(x0 + dx, y0 + dy, x1 - x0, y1 - y0))


class _Piece:
    """A piece of an equation while it is set: its width, its ascent and descent (from its baseline),
    and its items in reading order. A piece is used once: putting it in another moves its items."""

    __slots__ = ('ascent', 'descent', 'items', 'width')

    def __init__(self, width=0.0, ascent=0.0, descent=0.0, items=None):
        self.width, self.ascent, self.descent = width, ascent, descent
        self.items = [] if items is None else items

    def move(self, dx, dy):
        for item in self.items:
            item.move(dx, dy)


def _run(text, size, kind, italic=False, anchor=None):
    run = _Run(text, size, kind, italic, anchor)
    return _Piece(run.width, _top(size), _bottom(size), [run])


def _row(*parts):
    """The parts side by side on one baseline: each part is a piece, or a number (a space in px)."""
    x, ascent, descent, items = 0.0, 0.0, 0.0, []
    for part in parts:
        if isinstance(part, (int, float)):
            x += part
            continue
        part.move(x, 0.0)
        items.extend(part.items)
        ascent, descent = max(ascent, part.ascent), max(descent, part.descent)
        x += part.width
    return _Piece(x, ascent, descent, items)


def _shift(piece, dy):
    """The piece with its baseline `dy` lower (higher for a negative `dy`)."""
    piece.move(0.0, dy)
    piece.ascent, piece.descent = piece.ascent - dy, piece.descent + dy
    return piece


def _rule_piece(path, width):
    _, y0, _, y1 = path.bounds()
    return _Piece(width, max(0.0, -y0), max(0.0, y1), [path])


# ---- the symbols ----------------------------------------------------------------------------------


def letters(base):
    """The text of a base: a Greek name as its letter, any other text as it is."""
    return GREEK.get(base, str(base))


def primes(prime):
    """The text of the prime of a symbol: a text with `'` as `′`, a yes/no or a number of primes."""
    if isinstance(prime, bool):
        return '′' if prime else ''
    if isinstance(prime, int):
        return '′' * prime
    return str(prime or '').replace("'", '′')


def _number_text(value):
    """(the digits, the exponent or None) of a number, as `notation.number` writes it."""
    if type(value) is int:
        return str(value), None
    text = repr(value)
    mantissa, e, power = text.partition('e')
    return (mantissa, str(int(power))) if e else (text, None)


def unit_parts(text):
    """The parts of a unit, as `notation.unit` reads them: (text, power or None). A power after nothing,
    or after a power, is text."""
    parts, piece, at = [], '', 0
    for found in _POWER.finditer(text):
        piece += text[at : found.start()]
        at = found.end()
        if piece:
            parts.append((piece, found.group(1)))
            piece = ''
        else:
            piece = found.group()
    piece += text[at:]
    if piece:
        parts.append((piece, None))
    return parts


def _minus(text):
    return text.replace('-', '−')


# ---- the setter -----------------------------------------------------------------------------------


def _plain_base(node):
    """Whether the base of a power needs no parentheses: the rule of `notation.latex`."""
    if isinstance(node, (Sym, Time, Text, Call, Sum, Since, Count, Elapsed)):
        return True
    return isinstance(node, Num) and node.unit is None and 'e' not in repr(node.value)


class _Setter:
    def __init__(self, symbol, clocks):
        self.symbol_of = symbol
        self.clocks = CLOCKS if clocks is None else clocks

    # ---- the small parts

    def symbol(self, key, size):
        base, prime, sub = self.symbol_of(key)
        prime, sub = primes(prime), '' if sub is None else str(sub)
        parts = [_run(letters(base), size, 'symbol', True, 'end' if prime or sub else None)]
        if prime:
            parts += [_space(0.05, size), _run(prime, size, 'prime')]
        if sub:
            one = len(sub) == 1 and sub.isalpha()
            index = _run(sub, scaled(size, SCRIPT), 'symbol' if one else 'index', one, 'start')
            parts.append(_shift(index, half(SUB_DROP * size)))
        return _row(*parts)

    def superscript(self, base, exponent, size):
        rise = max(half(SUP_RISE * size), half(base.ascent - 0.4 * size))
        last = base.items[-1] if base.items else None
        if isinstance(last, _Run) and last.y == 0:
            last.anchor = 'end'  # against the exponent, when it is on the baseline
        return _row(base, _space(0.05, size), _shift(exponent, -rise))

    def number(self, node, size):
        digits, power = _number_text(node.value)
        parts = [_run(digits, size, 'number')]
        if power is not None:
            gap = _space(BINARY, size)
            ten = _row(_run('×', size, 'operator'), gap, _run('10', size, 'number'))
            parts += [gap, self.superscript(ten, _run(_minus(power), scaled(size, SCRIPT), 'number'), size)]
        if node.unit is not None:
            parts += [_space(THIN, size), self.unit(node.unit, size)]
        return _row(*parts)

    def unit(self, text, size):
        parts = []
        for piece, power in unit_parts(text):
            run = _run(piece, size, 'unit')
            if power is not None:
                run = self.superscript(run, _run(_minus(power), scaled(size, SCRIPT), 'unit'), size)
            parts.append(run)
        return _row(*parts)

    def clock(self, letter, key, size):
        sub = _shift(self.symbol(key, scaled(size, SCRIPT)), half(SUB_DROP * size))
        return _row(_run(letter, size, 'symbol', True, 'end'), sub)

    def commas(self, items, size):
        parts = []
        for k, item in enumerate(items):
            if k:
                parts += [_run(',', size, 'delimiter'), _space(COMMA, size)]
            parts.append(item)
        return _row(*parts)

    # ---- delimiters

    def tall(self, piece, size):
        return piece.ascent > TALL_ASCENT * size or piece.descent > TALL_DESCENT * size

    def parens(self, piece, size):
        if not self.tall(piece, size):
            return _row(_run('(', size, 'delimiter'), piece, _run(')', size, 'delimiter'))
        pad = _space(0.1, size)
        top, bottom = -piece.ascent - pad, piece.descent + pad
        w = half(0.35 * size)
        upper, lower = half(top + 0.3 * (bottom - top)), half(bottom - 0.3 * (bottom - top))
        stroke = _stroke(size)
        left = _Path('paren', (('M', (w, top)), ('C', (0.0, upper, 0.0, lower, w, bottom))), stroke, '(')
        gap = _space(0.05, size)
        right = _Path('paren', (('M', (0.0, top)), ('C', (w, upper, w, lower, 0.0, bottom))), stroke, ')')
        return _row(_rule_piece(left, w), gap, piece, gap, _rule_piece(right, w))

    def brackets(self, piece, size):
        """The interval of a membership, `[piece]`, with drawn brackets around content taller than a
        line, as `parens` draws its parentheses."""
        if not self.tall(piece, size):
            return _row(_run('[', size, 'delimiter'), piece, _run(']', size, 'delimiter'))
        pad = _space(0.1, size)
        top, bottom = -piece.ascent - pad, piece.descent + pad
        w = half(0.3 * size)
        stroke = _stroke(size)
        left, right = _bracket('[', w, 0.0, top, bottom, stroke), _bracket(']', 0.0, w, top, bottom, stroke)
        gap = _space(0.05, size)
        return _row(_rule_piece(left, w), gap, piece, gap, _rule_piece(right, w))

    def bars(self, piece, size):
        if not self.tall(piece, size):
            return _row(_run('|', size, 'delimiter'), piece, _run('|', size, 'delimiter'))
        pad = _space(0.1, size)
        top, bottom = -piece.ascent - pad, piece.descent + pad
        w = half(0.25 * size)
        mid = half(w / 2)
        stroke = _stroke(size)
        bar = (('M', (mid, top)), ('L', (mid, bottom)))
        left, right = _Path('bars', bar, stroke, '|'), _Path('bars', bar, stroke, '|')
        gap = _space(0.05, size)
        return _row(_rule_piece(left, w), gap, piece, gap, _rule_piece(right, w))

    def radical(self, piece, size):
        gap = _space(0.15, size)
        top = -piece.ascent - gap
        bottom = max(piece.descent, _bottom(size))
        height = bottom - top
        tick, foot, rise = half(0.2 * size), half(0.45 * size), half(0.75 * size)
        stroke = _stroke(size)
        sign = _Path(
            'radical',
            (
                ('M', (0.0, half(top + 0.62 * height))),
                ('L', (tick, half(top + 0.52 * height))),
                ('L', (foot, bottom)),
                ('L', (rise, top)),
            ),
            stroke,
            '√',
        )
        end = rise + gap + piece.width + gap
        over = _Path('overline', (('M', (rise, top)), ('L', (end, top))), stroke, '')
        piece.move(rise + gap, 0.0)
        return _Piece(end, -top, bottom, [sign, over, *piece.items])

    def fraction(self, numerator, denominator, size):
        pad, gap = _space(0.12, size), _space(0.12, size)
        width = max(numerator.width, denominator.width) + 2 * pad
        axis = half(AXIS * size)
        numerator.move(half((width - numerator.width) / 2), -axis - gap - numerator.descent)
        denominator.move(half((width - denominator.width) / 2), -axis + gap + denominator.ascent)
        bar = _Path('bar', (('M', (0.0, -axis)), ('L', (width, -axis))), _stroke(size), '/')
        bar.parts, bar.pad = (numerator.items, denominator.items), pad
        ascent = axis + gap + numerator.descent + numerator.ascent
        descent = -axis + gap + denominator.ascent + denominator.descent
        return _Piece(width, ascent, descent, [*numerator.items, bar, *denominator.items])

    # ---- cases

    def case_rows(self, node, size, inline):
        """(value, word, condition or None) of each row of a `Cases`."""
        rows = [
            (self.write(value, size, inline), 'if', self.write(condition, size, inline))
            for condition, value in node.pairs
        ]
        rows.append((self.write(node.otherwise, size, inline), 'otherwise', None))
        return rows

    def columns(self, rows, size):
        """Each row as one piece: the values in one column, the words in the next."""
        at = max(value.width for value, _, _ in rows) + _space(QUAD, size)
        out = []
        for value, word, condition in rows:
            parts = [value, at - value.width, _run(word, size, 'word')]
            if condition is not None:
                parts += [_space(WORD_SPACE, size), condition]
            out.append(_row(*parts))
        return out

    def cases(self, node, size, inline):
        rows = self.columns(self.case_rows(node, size, inline), size)
        gap = _space(LINE_GAP, size)
        baseline, baselines = 0.0, []
        for k, row in enumerate(rows):
            if k:
                baseline += rows[k - 1].descent + gap + row.ascent
            baselines.append(baseline)
        top, bottom = -rows[0].ascent, baselines[-1] + rows[-1].descent
        dy = half(-half(AXIS * size) - (top + bottom) / 2)
        brace, w = _brace(top + dy, bottom + dy, size)
        after = _space(0.2, size)
        items = [brace]
        for row, y in zip(rows, baselines):
            row.move(w + after, y + dy)
            items.extend(row.items)
        width = w + after + max(row.width for row in rows)
        return _Piece(width, -(top + dy), bottom + dy, items)

    # ---- the nodes

    def operand(self, node, minimum, size, inline):
        """A node where its parent needs at least the precedence `minimum`."""
        piece = self.write(node, size, inline)
        return self.parens(piece, size) if precedence(node, inline) < minimum else piece

    def right(self, node, minimum, size, inline):
        """The right operand of a binary operator: a sign there is in parentheses."""
        if isinstance(node, (Neg, Pos)):
            return self.parens(self.write(node, size, inline), size)
        return self.operand(node, minimum, size, inline)

    def write(self, node, size, inline):
        """The piece of a node. `inline`: in an exponent or in a stacked fraction, where a `/` is on the
        line."""
        if isinstance(node, Sym):
            return self.symbol(node.key, size)
        if isinstance(node, Num):
            return self.number(node, size)
        if isinstance(node, Text):
            word = node.word
            if isinstance(word, bool):
                word = 'true' if word else 'false'
            return _run(word, size, 'text')
        if isinstance(node, Time):
            return _run('t', size, 'symbol', True)
        if isinstance(node, Op):
            return self.op(node, size, inline)
        if isinstance(node, (Neg, Pos)):
            sign = _run('−' if isinstance(node, Neg) else '+', size, 'operator', anchor='end')
            x = node.x
            if isinstance(x, (Neg, Pos)):
                return _row(sign, self.parens(self.write(x, size, inline), size))
            return _row(sign, self.operand(x, 7, size, inline))
        if isinstance(node, Cmp):
            gap = _space(RELATION, size)
            parts = [self.operand(node.items[0], 5, size, inline)]
            for op, item in zip(node.ops, node.items[1:]):
                parts += [gap, _run(_CMP[op], size, 'relation'), gap, self.operand(item, 5, size, inline)]
            return _row(*parts)
        if isinstance(node, In):
            gap = _space(RELATION, size)
            ends = [self.write(node.low, size, inline), self.write(node.high, size, inline)]
            return _row(
                self.operand(node.x, 5, size, inline),
                gap,
                _run('∈', size, 'relation'),
                gap,
                self.brackets(self.commas(ends, size), size),
            )
        if isinstance(node, Logic):
            gap = _space(LOGIC_SPACE, size)
            parts = []
            for k, item in enumerate(node.items):
                if k:
                    parts += [gap, _run(_LOGIC_SIGNS[node.op], size, 'operator'), gap]
                parts.append(self.operand(item, 3, size, inline))
            return _row(*parts)
        if isinstance(node, Not):
            return _row(
                _run('¬', size, 'operator', anchor='end'),
                _space(0.1, size),
                self.operand(node.x, 7, size, inline),
            )
        if isinstance(node, Cases):
            return self.cases(node, size, inline)
        if isinstance(node, Call):
            return self.call(node, size, inline)
        if isinstance(node, Sum):
            terms = self.parens(self.commas([self.write(t, size, inline) for t in node.terms], size), size)
            if node.fn in _LIST_NAMES:
                big = scaled(size, SIGMA)
                sigma = _shift(_run(_LIST_NAMES[node.fn], big, 'operator'), half(0.36 * big - AXIS * size))
                return _row(sigma, _space(0.1, size), terms)
            return _row(_run(node.fn, size, 'function'), terms)
        if isinstance(node, Since):
            return self.clock(self.clocks['since'], node.target, size)
        if isinstance(node, Count):
            return self.clock(self.clocks['count'], node.target, size)
        if isinstance(node, Elapsed):
            return self.clock(self.clocks['elapsed'], node.key, size)
        if isinstance(node, Deriv):
            small = scaled(size, FRACTION)
            d = _space(0.05, small)
            top = _row(_run('d', small, 'operator', anchor='end'), d, self.symbol(node.key, small))
            bottom = _row(
                _run('d', small, 'operator', anchor='end'), d, _run('t', small, 'symbol', True, 'start')
            )
            return self.fraction(top, bottom, size)
        if isinstance(node, Assign):
            gap = _space(RELATION, size)
            arrow = _row(gap, _run('←', size, 'relation'), gap)
            return _row(self.symbol(node.target, size), arrow, self.write(_value(node), size, inline))
        raise ValueError(f'{node!r} is not a node of the notation')

    def op(self, node, size, inline):
        if node.op == '**':
            base = self.write(node.left, size, inline)
            if not _plain_base(node.left):
                base = self.parens(base, size)
            return self.superscript(base, self.write(node.right, scaled(size, SCRIPT), True), size)
        if node.op == '/' and not inline:
            small = scaled(size, FRACTION)
            return self.fraction(
                self.write(node.left, small, True), self.write(node.right, small, True), size
            )
        level = precedence(node, True)
        gap = 0.0 if node.op == '/' else _space(BINARY, size)
        left = self.operand(node.left, level, size, inline)
        right = self.right(node.right, level + 1, size, inline)
        return _row(left, gap, _run(_SIGNS[node.op], size, 'operator'), gap, right)

    def call(self, node, size, inline):
        if node.name == 'sqrt':
            return self.radical(self.write(node.args[0], size, inline), size)
        if node.name == 'abs':
            return self.bars(self.write(node.args[0], size, inline), size)
        items = []
        for arg in node.args:
            if isinstance(arg, Sum) and arg.fn == node.name:
                items += [self.write(term, size, inline) for term in arg.terms]
            else:
                items.append(self.write(arg, size, inline))
        for name, value in node.keywords:
            colon = _row(_run(name, size, 'text'), _run(':', size, 'delimiter'), _space(COMMA, size))
            items.append(_row(colon, self.write(value, size, inline)))
        return _row(_run(node.name, size, 'function'), self.parens(self.commas(items, size), size))

    # ---- the top of an equation

    def head(self, node, left, relation, size):
        """(the piece before the body or None, the body, whether the body is in parentheses)."""
        gap = _space(RELATION, size)
        if left is not None:
            sign = _run(RELATIONS[relation], size, 'relation')
            return _row(self.write(left, size, False), gap, sign, gap), node, False
        if isinstance(node, Assign):
            sign = _run('←', size, 'relation')
            return _row(self.symbol(node.target, size), gap, sign, gap), _value(node), False
        if isinstance(node, Cmp) and len(node.ops) == 1:
            sign = _run(_CMP[node.ops[0]], size, 'relation')
            head = _row(self.operand(node.items[0], 5, size, False), gap, sign, gap)
            return head, node.items[1], precedence(node.items[1]) < 5
        return None, node, False

    def terms(self, node, size):
        """The terms of a sum or a difference: (operator or None, piece), the operator before each
        term but the first."""
        if isinstance(node, Op) and node.op in ('+', '-'):
            if isinstance(node.left, Op) and node.left.op in ('+', '-'):
                out = self.terms(node.left, size)
            else:
                out = [(None, self.operand(node.left, 5, size, False))]
            out.append((node.op, self.right(node.right, 6, size, False)))
            return out
        return [(None, self.write(node, size, False))]


def _value(node):
    """The value of a line of an event, as `notation.latex` writes it: `S + v` for `S += v`."""
    if node.op == '=':
        return node.value
    return Op(node.op[0], Sym(node.target), node.value)


# ---- the lines ------------------------------------------------------------------------------------


def _items(pieces):
    return [item for piece in pieces for item in piece.items]


def _right_edge(items, start):
    return max([start, *(item.right() for item in items)])


def _flush(items, limit):
    """Each fraction whose bar goes past x `limit`, the longest first, with its numerator and its
    denominator moved to the left end of its bar, so that a cut keeps the start of both."""
    bars = [item for item in items if isinstance(item, _Path) and item.kind == 'bar' and item.right() > limit]
    for bar in sorted(bars, key=lambda bar: bar.left() - bar.right()):
        for part in bar.parts:
            if part:
                dx = bar.left() + bar.pad - min(item.left() for item in part)
                for item in part if dx < 0 else ():
                    item.move(dx, 0.0)


def _cut(items, limit):
    """The items of a line that end at x `limit` or before; a straight rule that starts before it
    ends at it (`_flush` first)."""
    _flush(items, limit)
    kept = []
    for item in items:
        if isinstance(item, _Path) and item.kind in SHORTENED:
            if item.bounds()[0] < limit:
                item.shorten(limit)
                kept.append(item)
        elif item.right() <= limit:
            kept.append(item)
    return kept


def _close(pieces, start, size, available, keep):
    """The items of the last line of a cut equation, then the marker: the line's pieces, less its last
    pieces (never the first `keep`) while they do not fit with the marker after them, and of those, the
    items that end before the marker."""
    marker = _Run(MARKER, size, 'marker', False)
    gap = _space(QUAD / 2, size)
    limit = available - gap - marker.width
    pieces = list(pieces)
    while len(pieces) > keep and _right_edge(_items(pieces), start) > limit:
        pieces.pop()
    items = _cut(_items(pieces), limit)
    marker.move(_right_edge(items, start) + (gap if items else 0.0), 0.0)
    return [*items, marker]


def _finish(rows, starts, keeps, size, available, cut):
    """The lines of an equation: (items, ascent, descent) for each row of pieces, and whether something
    was cut. A row wider than the width is cut at the width and is the last; the last row of a cut
    equation ends with the marker."""
    out = []
    for k, row in enumerate(rows):
        last = k == len(rows) - 1
        if _right_edge(_items(row), starts[k]) > available:
            items, cut, last = _close(row, starts[k], size, available, len(row)), True, True
        elif last and cut:
            items = _close(row, starts[k], size, available, keeps[k])
        else:
            items = _items(row)
        ascent = max([_top(size), *(piece.ascent for piece in row)])
        descent = max([_bottom(size), *(piece.descent for piece in row)])
        out.append((items, ascent, descent))
        if last:
            break
    return out, cut


def typeset(
    node,
    symbol: Callable[[str], tuple],
    *,
    left=None,
    relation='=',
    size=TEXT_SIZE,
    width=None,
    lines=None,
    clocks=None,
):
    """The `Equation` of a node (see the module's text). `symbol(key)` gives (base, prime, subscript);
    `left`, a node, goes before the node with `relation` (a key of `RELATIONS`) between them; `size` is
    the size of the text in px (on the grid of 0.5); `width` (px) and `lines` limit the lines (None: no
    limit); `clocks` gives the letters of `since`, `count` and `elapsed` (`CLOCKS`)."""
    if lines is not None and lines < 1:
        raise ValueError('an equation has one line or more')
    if width is not None and not width > 0:
        raise ValueError('the width of an equation is above 0')
    if relation not in RELATIONS:
        raise ValueError(f'{relation!r} is not a relation of an equation')
    setter = _Setter(symbol, clocks)
    size = half(size)
    available = math.inf if width is None else width - 2 * EDGE
    head, body, wrapped = setter.head(node, left, relation, size)
    if isinstance(body, Cases) and not wrapped:
        return _cases_equation(setter, head, body, size, available, lines)
    if wrapped:
        pieces = [(None, setter.parens(setter.write(body, size, False), size))]
    else:
        pieces = setter.terms(body, size)
    start = 0.0 if head is None else head.width
    indent = start if 0 < start <= available / 2 else _space(INDENT, size)
    gap = _space(BINARY, size)
    rows, starts = [[] if head is None else [head]], [0.0]
    x = start
    for k, (op, term) in enumerate(pieces):
        piece = term if op is None else _row(_run(_SIGNS[op], size, 'operator'), gap, term)
        before = gap if k else 0.0
        over = x + before + piece.width > available
        # A line breaks before each term but the first; and after the head when the first term fits
        # on the next line only.
        if over and (k or (head is not None and indent + piece.width <= available)):
            rows.append([])
            starts.append(indent)
            x, before = indent, 0.0
        rows[-1].append(_row(x + before, piece))
        x += before + piece.width
    cut = lines is not None and len(rows) > lines
    rows, starts = rows[:lines], starts[:lines]
    keeps = [1 if k == 0 and head is not None else 0 for k in range(len(rows))]
    found, cut = _finish(rows, starts, keeps, size, available, cut)
    return _stack(found, None, size, cut)


def _cases_equation(setter, head, body, size, available, lines):
    """The equation of a body that is a `Cases`: one line for each row, after the head and the brace."""
    found = setter.case_rows(body, size, False)
    cut = lines is not None and len(found) > lines
    pieces = setter.columns(found[:lines], size)
    start = 0.0 if head is None else head.width
    at = start + half(0.5 * size) + _space(0.2, size)
    rows, starts, keeps = [], [], []
    for k, piece in enumerate(pieces):
        piece.move(at, 0.0)
        rows.append([head, piece] if k == 0 and head is not None else [piece])
        starts.append(at)
        keeps.append(len(rows[-1]) - 1)
    lines_found, cut = _finish(rows, starts, keeps, size, available, cut)
    # The brace spans the rows that the equation shows, and goes after the head in reading order.
    extents = [(piece.ascent, piece.descent) for piece in pieces[: len(lines_found)]]
    first = lines_found[0][0]
    index = sum(1 for item in first if item.right() <= start)
    return _stack(lines_found, (start, extents, index), size, cut)


def _brace(top, bottom, size):
    """A left brace from y `top` to y `bottom`, with its point at x 0, and its width."""
    w = half(0.5 * size)
    stem, mid = half(w / 2), half((top + bottom) / 2)
    r = min(half(0.25 * size), half((bottom - top) / 4))
    commands = (
        ('M', (w, top)),
        ('Q', (stem, top, stem, top + r)),
        ('L', (stem, mid - r)),
        ('Q', (stem, mid, 0.0, mid)),
        ('Q', (stem, mid, stem, mid + r)),
        ('L', (stem, bottom - r)),
        ('Q', (stem, bottom, w, bottom)),
    )
    return _Path('brace', commands, _stroke(size), '{'), w


def _bracket(text, tip, stem, top, bottom, stroke):
    """A square bracket (`text`) from y `top` to y `bottom`: its stem at x `stem`, its arms to x `tip`."""
    corners = ((tip, top), (stem, top), (stem, bottom), (tip, bottom))
    return _Path('bracket', (('M', corners[0]), *(('L', corner) for corner in corners[1:])), stroke, text)


def _stack(rows, brace, size, cut):
    """The equation of its lines, one under another: `rows` are (items, ascent, descent), and `brace`
    is None or (its x, the ascent and descent of each row that it spans, its place in the items of the
    first line)."""
    gap = _space(LINE_GAP, size)
    baselines, baseline = [], EDGE
    for k, (_, ascent, _) in enumerate(rows):
        baseline += ascent if k == 0 else rows[k - 1][2] + gap + ascent
        baselines.append(baseline)
    out = []
    for k, ((items, ascent, descent), y) in enumerate(zip(rows, baselines)):
        frozen = [item.frozen(EDGE, y) for item in items]
        if k == 0 and brace is not None:
            x, extents, index = brace
            top = baselines[0] - extents[0][0]
            bottom = baselines[len(extents) - 1] + extents[-1][1]
            path, _ = _brace(top, bottom, size)
            path.move(x, 0.0)
            frozen.insert(index, path.frozen(EDGE, 0.0))
        right = max([EDGE, *(item.box.right for item in frozen)])
        out.append(Line(tuple(frozen), y, Box(0.0, y - ascent, right + EDGE, ascent + descent)))
    height = baselines[-1] + rows[-1][2] + EDGE
    width = max(line.box.width for line in out)
    return Equation(tuple(out), width, height, baselines[0], height - baselines[-1], cut, size)


# ---- the SVG --------------------------------------------------------------------------------------


def _xml_char(char):
    """Whether XML 1.0 can hold a character."""
    code = ord(char)
    return code in (0x9, 0xA, 0xD) or 0x20 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or code > 0xFFFF


def _xml(text):
    """`text` without the characters that XML cannot hold: each becomes U+FFFD."""
    return ''.join(char if _xml_char(char) else chr(0xFFFD) for char in text)


def svg_parts(equation, x, y):
    """The SVG of an equation whose top left corner is at (x, y): one `<text class="math">` for each
    line with a `<tspan>` for each atom at the x of its anchor (`Atom.at`, with its `text-anchor`) and
    the y of its baseline, then a `<path class="math-rule">` for each rule of the line. Each element
    has its light colour as an attribute too (`svg.COLOURS`); `STYLE` gives the colours of each theme.
    (The import of `svg` is here, so that `svg.py` can import this module.)"""
    from . import svg

    ink, muted = svg.COLOURS['ink'][0], svg.COLOURS['muted'][0]
    number = svg.number
    out = []
    for line in equation.lines:
        atoms = [item for item in line.items if isinstance(item, Atom)]
        if atoms:
            spans = []
            for atom in atoms:
                attributes = [f'x="{number(x + atom.at)}"', f'y="{number(y + atom.y)}"']
                if atom.anchor != 'start':
                    attributes.append(f'text-anchor="{atom.anchor}"')
                if atom.size != equation.size:
                    attributes.append(f'font-size="{number(atom.size)}"')
                if atom.italic:
                    attributes += ['class="math-symbol"', 'font-style="italic"']
                elif atom.kind in MUTED:
                    attributes += ['class="math-muted"', f'fill="{muted}"']
                spans.append(f'<tspan {" ".join(attributes)}>{svg.escape(_xml(atom.text))}</tspan>')
            out.append(
                f'<text class="math" x="{number(x + atoms[0].x)}" y="{number(y + line.baseline)}" '
                f'font-size="{number(equation.size)}" fill="{ink}">{"".join(spans)}</text>'
            )
        for rule in line.items:
            if isinstance(rule, Rule):
                d = ''.join(
                    letter + ' '.join(number((x, y)[k % 2] + value) for k, value in enumerate(points))
                    for letter, points in rule.path
                )
                out.append(
                    f'<path class="math-rule" d="{d}" fill="none" stroke="{ink}" '
                    f'stroke-width="{number(rule.stroke)}" stroke-linecap="round" stroke-linejoin="round"/>'
                )
    return ''.join(out)


__all__ = [
    'MARKER',
    'STYLE',
    'Atom',
    'Equation',
    'Line',
    'Rule',
    'run_width',
    'svg_parts',
    'typeset',
]
