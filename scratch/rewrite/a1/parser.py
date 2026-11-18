#!/usr/bin/env python
"""A prototype parser of the notation of the rewrite (brief A1, scratch/rewrite/spec.md).

    python parser.py corpus/                  one summary line for each file of the corpus
    python parser.py corpus/ --tree           the tree of each file too
    python parser.py FILE.scn --context members --tree
    python parser.py --expr 'this.water / (2 h)'

It reads a model text into a tree. It resolves no name and checks no unit. It has three parts:

1. A tokenizer (`Lexer`). It starts from the rules of `napkin/model/language/lex.py` at the base
   commit. `Token`, `Line`, `fold` and `tree` are copied unchanged. Each rule that had to change is
   marked `CHANGED` below, and FINDINGS.md lists them.
2. A precedence parser of expressions (`Expressions`). It gives nodes of `napkin.core.expr` where a
   kind exists (`Const`, `Ref`, `Unary`, `Binary`, `Compare`, `BoolOp`, `IfElse`, `Call`), and node
   kinds of its own where none does (`Quantity`, `Collection`, `Member`, `Method`, `Formula`,
   `Within`, `Case`, `Absent`). The kinds of its own are made with `expr.made`, so two equal
   expressions are still one object.
3. A parser of lines and blocks (`Parser`), one method for each place where a line can stand.

`napkin` is imported from the stable copy of the base commit (`/home/user/napkin-base`, or the folder
that `NAPKIN_BASE` names): the package of the checkout changes while the prototypes are written.
"""

from __future__ import annotations

import math
import os
import re
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

BASE = os.environ.get('NAPKIN_BASE', '/home/user/napkin-base')
if 'napkin' not in sys.modules and os.path.isdir(BASE) and BASE not in sys.path:
    sys.path.insert(0, BASE)

from napkin.core import expr  # noqa: E402

# ---- the words of the language ------------------------------------------------------------------------

# The words that name nothing else (ruling R-A1-08). A reserved word is never a unit.
RESERVED = frozenset(
    {
        # Values and places that the language gives.
        'true',
        'false',
        'none',
        'this',
        't',
        'SOURCE',
        'SINK',
        # Words of an expression.
        'and',
        'or',
        'not',
        'if',
        'else',
        'in',
        'is',  # no longer a word of the language: kept, so that `a is b` gets its own message
        # Words that end an expression inside a line.
        'from',
        'to',
        'when',
        # Words that start a line.
        'after',
        'until',
        'reset',
        'switch',
        'move',
        'assert',
        'flow',
        'record',
        'readonly',
        'input',
        # Words that make a value or a type.
        'formula',
        'event',
        'solver',
        'enum',
        'bool',
    }
)
# Words with a meaning in one position only. Each stays a valid name: the next token decides.
CONTEXTUAL = frozenset(
    {
        'status',  # `status ok when C` against `status: enum[...] = ...`
        'ok',
        'degraded',
        'failed',
        'inactive',
        'inputs',
        'solve_for',
        'constraints',
        'objective',
        'minimize',
        'maximize',
        'claims',
        'source',
        'source_transfer',
        'assumption',
        'identity',
        'convention',
        'distribution',
    }
)
# The words that brief A5 gives a spelling: this prototype names them and reads none of them.
A5_WORDS = frozenset({'scenario', 'variant', 'use', 'change', 'options', 'runs', 'notes', 'sees', 'report'})
# Words of the present language that the rewrite does not have: each with what to write now.
RETIRED = {
    'let': 'a value is `name = value`, and a calculation that follows its inputs is `name = formula(...)`',
    'var': 'a value that changes is `name: type = value`',
    'output': 'any named value can be reported: name the calculation with an ordinary binding',
    'share': 'sharing belongs to the endpoint: `outflow.allocation = priority(a, b)` under the stock',
}
# The types that are words. `bool`, `enum` and `formula` are reserved. `text` and `number` name a type
# after a colon and can still name a value (a present model has a field `number`).
TYPE_WORDS = frozenset({'bool', 'text', 'number'})
# The functions: a name before `(` is a call of one of these, and nothing else is a call.
FUNCTIONS = frozenset(
    {
        *('min', 'max', 'clip', 'abs', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf'),
        *('sum', 'count', 'any', 'all'),
        *('since', 'elapsed', 'delayed'),
        *('priority', 'proportional'),
    }
)
DISTRIBUTIONS = frozenset(
    {'uniform', 'triangular', 'pert', 'loguniform', 'normal', 'lognormal', 'beta', 'bernoulli', 'categorical'}
)
OBJECTIVES = ('minimize', 'maximize')
# The operations after a dot that take arguments.
METHODS = frozenset({'where', 'by', 'at', 'draw', 'start', 'diff'})
# The members that the language gives a value of some type (types.md). The census checks which of
# them the present models declare as names of their own.
BUILTIN_MEMBERS = METHODS | frozenset(
    {
        *('instances', 'occurrences', 'flows'),
        *('capacity', 'request', 'actual_rate', 'source', 'sink', 'forward', 'backward', 'served_fraction'),
        *('outflow', 'inflow', 'allocation'),
        *('started', 'done', 'active'),
        *('mean', 'std', 'median', 'low', 'high'),
    }
)
# The words that Python keeps. Today no name of a model can be one (`resolve.py:236`).
PYTHON_KEYWORDS = frozenset(__import__('keyword').kwlist)
RATINGS = ('ok', 'degraded', 'failed', 'inactive')
RECORD_KINDS = ('source', 'source_transfer', 'assumption', 'identity', 'convention')
SECTIONS = ('inputs', 'solve_for', 'constraints', 'objective')

INDENT = 4
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
NUMBER = re.compile(r'[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?')
# CHANGED. Today a unit is "the whole word after its number, up to the next space, comma, bracket,
# colon or bar". Now a unit has a grammar of its own (ruling R-A1-01): factors joined by `/` (divide)
# and `-` (multiply, binding tighter), each a name with an optional whole power `^n`.
UNIT_FACTOR = r'[A-Za-z_][A-Za-z0-9_]*(?:\^-?[0-9]+)?'
UNIT_WORD = re.compile(rf'{UNIT_FACTOR}(?:[/-]{UNIT_FACTOR})*')
# What can stand directly after a unit. Anything else is refused: `48 h/2`, `3 h+2 h`.
UNIT_ENDS = ' ,)]:'
# CHANGED. `<->` is new. `{`, `}` and `|` are gone: a unit takes no text parameter (`{item}/h`), and
# named values are `enum[A, B]`.
OPERATORS = ('<->', '**', '->', '<=', '>=', '==', '!=', '+=', '-=')
OPERATORS += ('(', ')', '[', ']', ',', ':', '=', '+', '-', '*', '/', '<', '>', '.', '^')
GONE = {
    '|': 'named values are an enum now: enum[OPEN, CLOSED]',
    '{': 'a unit takes no text parameter: each field of a template has one dimension',
    '}': 'a unit takes no text parameter: each field of a template has one dimension',
}
JOINING = frozenset({'**', '<=', '>=', '==', '!=', '+', '-', '*', '/', '<', '>', '->', '<->'})
JOINING_WORDS = frozenset({'and', 'or', 'if', 'else'})
CONTINUE = 'an expression goes on to the next row only inside brackets: ( … )'
OPENS = {'(': ')', '[': ']'}
CLOSES = {')': '(', ']': '['}


# ---- copied unchanged from napkin/model/language/lex.py (base commit) ---------------------------------


class SyntaxProblem(Exception):
    """A line that is not written as the language writes it: the message and the line (1 is the
    first line of the file)."""

    def __init__(self, message, line, column=None):
        self.message, self.line, self.column = message, line, column
        super().__init__(f'line {line}: {message}')


@dataclass
class Token:
    """A token: its kind (`name`, `number`, `unit`, `text`, `op` or `at`; the parser makes `word`s),
    its value (a text's value has its line breaks read), where it starts (`line`, `column`, from 1),
    and whether a space comes before it on its line. `source` is the token as written, and `lines` the
    number of lines of the file that a text takes."""

    kind: str
    value: object
    line: int
    column: int
    space: bool
    source: str = ''
    lines: int = 1
    # The parser reads a word with no space inside it, such as an ID, as one word: each token of the
    # word after its first is `joined` to the token before it, and the formatter writes them so.
    joined: bool = False

    def is_op(self, *values):
        return self.kind == 'op' and self.value in values

    def is_name(self, *values):
        return self.kind == 'name' and (not values or self.value in values)


@dataclass
class Line:
    """A logical line: its depth (one level is four spaces), the line of the file where it starts and
    the one where it ends, and its tokens. A comment has its text, and an empty line no tokens. `under`
    holds the logical lines under it (`tree`)."""

    kind: str  # 'line', 'comment' or 'blank'
    depth: int
    number: int
    end: int
    tokens: list = field(default_factory=list)
    comment: str = ''
    under: list = field(default_factory=list)

    @property
    def first(self):
        return self.tokens[0] if self.tokens else None


def fold(pieces):
    """The value of a text from its pieces, one for each line of the file (None for an empty line): a
    line break reads as a space, and an empty line is one line break."""
    out = ''
    previous = 'start'
    for piece in pieces:
        if piece is None:
            out += '\n'
            previous = 'empty'
            continue
        if previous == 'piece':
            out += ' '
        out += piece
        previous = 'piece'
    return out


def tree(found):
    """The logical lines of a file (`lines`) that are not comments or empty, each with the lines under
    it, and the lines at the top level. A line is one level deeper than the line that it is under."""
    top, stack = [], []
    for line in found:
        if line.kind != 'line':
            continue
        line.under = []
        while stack and stack[-1].depth >= line.depth:
            stack.pop()
        expected = stack[-1].depth + 1 if stack else 0
        if line.depth != expected:
            raise SyntaxProblem(
                'a line is one level (four spaces) deeper than the line that it is under, or at the same level',
                line.number,
                line.depth * INDENT + 1,
            )
        (stack[-1].under if stack else top).append(line)
        stack.append(line)
    return top


# ---- the tokenizer: lex.py with the rules that had to change -------------------------------------------


def joins(token, last=False):
    """Whether a token joins two values, so that no line starts with it or ends with it.
    CHANGED: a line can end with `>`, which closes a collection (`pumps: <Pump> = <>`)."""
    if last and token.is_op('>'):
        return False
    return (token.kind == 'op' and token.value in JOINING) or (
        token.kind == 'name' and token.value in JOINING_WORDS
    )


class Lexer:
    def __init__(self, text, alone=False):
        # `alone`: the text is one expression on its own, which can start with a sign or with `<`.
        self.alone = alone
        if '\t' in text:
            number = text[: text.index('\t')].count('\n') + 1
            raise SyntaxProblem('a tab is not allowed: each level of nesting is four spaces', number)
        self.rows = text.split('\n')

    def indent(self, row, number):
        return len(row) - len(row.lstrip(' '))

    def lines(self):
        out = []
        i = 0
        while i < len(self.rows):
            row = self.rows[i].rstrip()
            number = i + 1
            if not row.strip():
                out.append(Line('blank', 0, number, number))
                i += 1
                continue
            spaces = self.indent(row, number)
            if spaces % INDENT:
                raise SyntaxProblem('each level of nesting is four spaces', number, spaces + 1)
            depth = spaces // INDENT
            if row[spaces] == '#':
                out.append(Line('comment', depth, number, number, comment=row[spaces:]))
                i += 1
                continue
            tokens, i, comments = self.logical(i, spaces)
            # No line of the language starts with an operator that joins two values, a sign included.
            # CHANGED: `else:` starts the last case of a `switch`.
            # CHANGED: a line that starts with `if` gets the message of the place where it stands.
            if (
                tokens
                and joins(tokens[0])
                and not self.alone
                and not tokens[0].is_name('if')
                and not (tokens[0].is_name('else') and len(tokens) > 1 and tokens[1].is_op(':'))
            ):
                first = tokens[0]
                raise SyntaxProblem(
                    f'the line starts with {first.value}: {CONTINUE}', first.line, first.column
                )
            line = Line('line', depth, number, i, tokens)
            # CHANGED: the comments that end the rows of the line, for the formatter: (row, text).
            line.trailing = comments
            out.append(line)
        # Trailing empty lines of the file are not lines of it.
        while out and out[-1].kind == 'blank':
            out.pop()
        return out

    def logical(self, i, spaces):
        """The tokens of the logical line that starts at row `i`, the row after it, and the comments
        that end its rows."""
        tokens = []
        comments = []
        stack = []  # the open brackets: (bracket, line, column)
        row = self.rows[i].rstrip()
        position = spaces
        space = True
        while True:
            if position >= len(row):
                if not stack:
                    if tokens and joins(tokens[-1], last=True):
                        last = tokens[-1]
                        raise SyntaxProblem(
                            f'the line ends with {last.value}: {CONTINUE}', last.line, last.column
                        )
                    return tokens, i + 1, comments
                # A bracket is open: the line goes on, on the next line that is not empty.
                i += 1
                while i < len(self.rows) and not self.rows[i].strip():
                    i += 1
                if i >= len(self.rows):
                    bracket, line, column = stack[-1]
                    raise SyntaxProblem(
                        f'the bracket {bracket} has no closing {OPENS[bracket]}', line, column
                    )
                row = self.rows[i].rstrip()
                indent = self.indent(row, i + 1)
                closes = row[indent] in CLOSES
                if indent <= spaces and not (indent == spaces and closes):
                    bracket, line, column = stack[-1]
                    raise SyntaxProblem(
                        f'the bracket {bracket} has no closing {OPENS[bracket]}: the lines of a bracket are '
                        f'indented deeper than its first line',
                        line,
                        column,
                    )
                # CHANGED: a comment can stand on a row of its own inside a bracket. Today it is an
                # error there. The `#` branch below reads it.
                position, space = indent, True
                continue
            char = row[position]
            if char == ' ':
                position += 1
                space = True
                continue
            number, column = i + 1, position + 1
            if char == '#':
                # CHANGED: a comment ends a row. Today a comment is a whole line. A `#` inside a text
                # never comes here: `text` reads the text to its closing quote.
                comments.append((number, row[position:]))
                position = len(row)
                continue
            if char == '"':
                token, i, row, position = self.text(i, row, position, space)
                tokens.append(token)
                space = False
                continue
            if char == '@':
                tokens.append(Token('at', '@', number, column, space, '@'))
                position += 1
                space = False
                continue
            found = NUMBER.match(row, position)
            if found:
                written = found.group()
                if not math.isfinite(float(written)):
                    raise SyntaxProblem(f'{written} is not a finite number', number, column)
                tokens.append(Token('number', written, number, column, space, written))
                position = found.end()
                space = False
                following = row[position : position + 1]
                # A unit follows the number after one space.
                if following == ' ' and NAME.match(row, position + 1):
                    first = NAME.match(row, position + 1).group()
                    if first not in RESERVED:
                        # CHANGED: the unit is read by its grammar, and what stands directly after
                        # it must end it. Today `48 h/2` reads the unit `h/2`, which no registry has.
                        word = UNIT_WORD.match(row, position + 1)
                        after = row[word.end() : word.end() + 1]
                        if after and after not in UNIT_ENDS:
                            raise SyntaxProblem(
                                f'the unit {word.group()} is followed by {after}: a unit ends at a space, a '
                                f'comma, a closing bracket or a colon. Write a space on each side of an '
                                f'operator that follows a unit: 48 h / 2',
                                number,
                                word.end() + 1,
                            )
                        tokens.append(Token('unit', word.group(), number, position + 2, True, word.group()))
                        position = word.end()
                # A number with a name directly after it (`48h`) stays two tokens, as today: an ID of
                # the evidence can hold one (`E-SITE-90MIN`). An expression refuses it (`primary`).
                continue
            found = NAME.match(row, position)
            if found:
                tokens.append(Token('name', found.group(), number, column, space, found.group()))
                position = found.end()
                space = False
                continue
            for op in OPERATORS:
                if row.startswith(op, position):
                    break
            else:
                if char in GONE:
                    raise SyntaxProblem(f'{char} is not a part of the language: {GONE[char]}', number, column)
                raise SyntaxProblem(f'{char!r} is not a part of the language here', number, column)
            if op in OPENS:
                stack.append((op, number, column))
            elif op in CLOSES:
                if not stack or stack[-1][0] != CLOSES[op]:
                    raise SyntaxProblem(f'{op} closes no bracket', number, column)
                stack.pop()
            tokens.append(Token('op', op, number, column, space, op))
            position += len(op)
            space = False

    def scan(self, row, start, number):
        """CHANGED: the characters of a text from `start` of a row, with its escapes read: (the
        characters, the index of the closing quote or None when the row ends first). The escapes are
        `\\"` (a quote) and `\\\\` (a backslash). Today a text has no escape."""
        out = []
        k = start
        while k < len(row):
            char = row[k]
            if char == '"':
                return ''.join(out), k
            if char == '\\':
                following = row[k + 1 : k + 2]
                if following not in ('"', '\\') or not following:
                    raise SyntaxProblem(
                        'in a text, a backslash writes a quote (\\") or a backslash (\\\\), and nothing else',
                        number,
                        k + 1,
                    )
                out.append(following)
                k += 2
                continue
            out.append(char)
            k += 1
        return ''.join(out), None

    def text(self, i, row, position, space):
        """A text that opens at `position` of row `i`: its token, and the row and the position after
        its closing quote."""
        number, column = i + 1, position + 1
        opening = self.indent(row, number)
        value, close = self.scan(row, position + 1, number)
        if close is not None:
            return Token('text', value, number, column, space, row[position : close + 1]), i, row, close + 1
        pieces = [value.rstrip()]
        source = [row[position:]]
        while True:
            i += 1
            if i >= len(self.rows):
                raise SyntaxProblem('the text has no closing quote', number, column)
            row = self.rows[i].rstrip()
            if not row.strip():
                pieces.append(None)
                source.append('')
                continue
            indent = self.indent(row, i + 1)
            if indent <= opening:
                raise SyntaxProblem(
                    'the text has no closing quote: its next lines are indented deeper than the line where '
                    'it opens',
                    number,
                    column,
                )
            value, close = self.scan(row, indent, i + 1)
            if close is None:
                pieces.append(value)
                source.append(row)
                continue
            pieces.append(value)
            source.append(row[: close + 1])
            # Empty lines just before the closing line still belong to the text.
            token = Token('text', fold(pieces), number, column, space, '\n'.join(source), len(source))
            return token, i, row, close + 1


def lines(text, alone=False):
    """The lines of a file, in order: logical lines, comments and empty lines."""
    return Lexer(text, alone).lines()


# ---- the kinds of expression node that `napkin.core.expr` does not have ------------------------------

# The levels of binding, loosest first. A node is written in brackets inside a tighter one.
TEST, OR, AND, NOT, CMP, ARITH, TERM, FACTOR, POWER, ATOM = range(1, 11)


class Own(expr.Node):
    """A node kind of this module. It is made with `expr.made`, never by its class."""

    __slots__ = ()

    def text(self):
        return write(self)


class Quantity(Own):
    """A number with its unit: `5 L/h`. `number` is the `Const` of the number, `unit` the unit as
    written."""

    __slots__ = ('number', 'unit')
    FIELDS = ('number', 'unit')

    def lowered(self):
        """The same quantity as today's front end writes it, `q(5, 'L/h')`, which the unit rules and
        the evaluator of `napkin.core` read."""
        return expr.call('q', [self.number, expr.const(self.unit)])


class Collection(Own):
    """A collection literal: `<this.primary, this.backup>`, or `<>`."""

    __slots__ = ('items',)
    FIELDS = ('items',)

    @property
    def children(self):
        return self.items


class Member(Own):
    """A member of a value that is not a plain dotted name: `c.at(x).price`, after a call."""

    __slots__ = ('base', 'name')
    FIELDS = ('base', 'name')

    @property
    def children(self):
        return (self.base,)


class Method(Own):
    """An operation after a dot, with its arguments: `.where(...)`, `.by(...)`, `.at(...)`,
    `.draw()`, `.start(...)`, `.diff(...)`. With `Member` it is the path with calls."""

    __slots__ = ('base', 'name', 'args')
    FIELDS = ('base', 'name', 'args')

    @property
    def children(self):
        return (self.base, *self.args)


class Formula(Own):
    """`formula(expression)`: a calculation that is kept, where a value stands."""

    __slots__ = ('body',)
    FIELDS = ('body',)

    @property
    def children(self):
        return (self.body,)


class Within(Own):
    """A membership test, `x in [lo, hi]`: both ends are included."""

    __slots__ = ('value', 'low', 'high')
    FIELDS = ('value', 'low', 'high')

    @property
    def children(self):
        return (self.value, self.low, self.high)


class Case(Own):
    """A bare member of an enum, `OPEN`: a word with a capital first letter and no dot after it. The
    expected type gives it its enum (ruling R-A1-04)."""

    __slots__ = ('name',)
    FIELDS = ('name',)


class Absent(Own):
    """`none`: no value."""

    __slots__ = ()
    FIELDS = ()


def quantity(number, unit):
    return expr.made(Quantity, expr.const(number), unit)


def collection(items):
    return expr.made(Collection, tuple(items))


def member(base, name):
    """`base.name`. A plain dotted name stays one `Ref`, as in today's expressions."""
    if isinstance(base, expr.Ref):
        return expr.ref(f'{base.name}.{name}')
    return expr.made(Member, base, name)


def method(base, name, args):
    return expr.made(Method, base, name, tuple(args))


def formula(body):
    return expr.made(Formula, body)


def within(value, low, high):
    return expr.made(Within, value, low, high)


def case(name):
    return expr.made(Case, name)


def absent():
    return expr.made(Absent)


# ---- an expression as text, and as a tree in brackets -----------------------------------------------------

LEVELS = {'add': ARITH, 'sub': ARITH, 'mul': TERM, 'div': TERM, 'pow': POWER, 'neg': FACTOR, 'pos': FACTOR}
LEVELS['not'] = NOT


def number_text(value):
    """A number as a model writes it: `repr` writes `1e-05` and `1e+16`, which `NUMBER` reads."""
    return repr(value)


def text_text(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def write(node, level=TEST):
    """An expression as the notation writes it, with the brackets that the levels of binding need and
    no others. `parse_expression(write(node))` is the node again (`check.py` tests it)."""
    own, written = _write(node)
    return f'({written})' if level > own else written


def _write(node):
    if isinstance(node, expr.Ref):
        return ATOM, node.name
    if isinstance(node, Case):
        return ATOM, node.name
    if isinstance(node, Absent):
        return ATOM, 'none'
    if isinstance(node, expr.Const):
        value = node.value
        if value is True or value is False:
            return ATOM, 'true' if value else 'false'
        return ATOM, text_text(value) if isinstance(value, str) else number_text(value)
    if isinstance(node, Quantity):
        return ATOM, f'{number_text(node.number.value)} {node.unit}'
    if isinstance(node, expr.Unary):
        own = LEVELS[node.op]
        if node.op == 'not':
            return own, f'not {write(node.operand, own)}'
        return own, expr.SYMBOLS[node.op] + write(node.operand, own)
    if isinstance(node, expr.Binary):
        own = LEVELS[node.op]
        if node.op == 'pow':  # the base is a value with no operator; the exponent can have a sign
            base = f'({write(node.left)})' if isinstance(node.left, Quantity) else write(node.left, ATOM)
            return own, f'{base} ** {write(node.right, FACTOR)}'
        right = write(node.right, own + 1)
        if node.op in ('mul', 'div') and isinstance(node.right, Quantity):
            # `x / 2 h` reads as `x / (2 h)`; the brackets say so to a reader, as the spec writes them.
            right = f'({right})'
        return own, f'{write(node.left, own)} {expr.SYMBOLS[node.op]} {right}'
    if isinstance(node, expr.Compare):
        written = write(node.operands[0], ARITH)
        for op, operand in zip(node.ops, node.operands[1:]):
            written += f' {expr.SYMBOLS[op]} {write(operand, ARITH)}'
        return CMP, written
    if isinstance(node, Within):
        return CMP, f'{write(node.value, ARITH)} in [{write(node.low)}, {write(node.high)}]'
    if isinstance(node, expr.BoolOp):
        own = OR if node.op == 'or' else AND
        return own, f' {node.op} '.join(write(value, own + 1) for value in node.values)
    if isinstance(node, expr.IfElse):
        return TEST, f'{write(node.body, OR)} if {write(node.test, OR)} else {write(node.orelse, TEST)}'
    if isinstance(node, expr.Call):
        return ATOM, f'{node.function}({", ".join(write(arg) for arg in node.args)})'
    if isinstance(node, Formula):
        return ATOM, f'formula({write(node.body)})'
    if isinstance(node, Collection):
        return ATOM, '<' + ', '.join(write(item, ATOM) for item in node.items) + '>'
    if isinstance(node, (Member, Method)):
        base = write(node.base, ATOM)
        if isinstance(node.base, (Quantity, expr.Const)):
            base = f'({base})'  # `2 h.x` and `2.x` do not read as a member of a number
        if isinstance(node, Member):
            return ATOM, f'{base}.{node.name}'
        return ATOM, f'{base}.{node.name}({", ".join(write(arg) for arg in node.args)})'
    raise TypeError(f'no text for {type(node).__name__}')


def sexpr(node):
    """An expression as a tree in brackets, which shows how it was read: `(div this.water (q 2 h))`."""
    if isinstance(node, expr.Ref):
        return node.name
    if isinstance(node, Case):
        return f'(case {node.name})'
    if isinstance(node, Absent):
        return 'none'
    if isinstance(node, expr.Const):
        return write(node)
    if isinstance(node, Quantity):
        return f'(q {number_text(node.number.value)} {node.unit})'
    if isinstance(node, expr.Unary):
        return f'({node.op} {sexpr(node.operand)})'
    if isinstance(node, expr.Binary):
        return f'({node.op} {sexpr(node.left)} {sexpr(node.right)})'
    if isinstance(node, expr.Compare):
        parts = [sexpr(node.operands[0])]
        for op, operand in zip(node.ops, node.operands[1:]):
            parts += [op, sexpr(operand)]
        return f'(compare {" ".join(parts)})'
    if isinstance(node, Within):
        return f'(within {sexpr(node.value)} {sexpr(node.low)} {sexpr(node.high)})'
    if isinstance(node, expr.BoolOp):
        return f'({node.op} {" ".join(map(sexpr, node.values))})'
    if isinstance(node, expr.IfElse):
        return f'(if {sexpr(node.test)} {sexpr(node.body)} {sexpr(node.orelse)})'
    if isinstance(node, expr.Call):
        return f'(call {" ".join([node.function, *map(sexpr, node.args)])})'
    if isinstance(node, Formula):
        return f'(formula {sexpr(node.body)})'
    if isinstance(node, Collection):
        return f'(collection{"".join(" " + sexpr(item) for item in node.items)})'
    if isinstance(node, Member):
        return f'(member {sexpr(node.base)} {node.name})'
    if isinstance(node, Method):
        return f'(method {" ".join([sexpr(node.base), node.name, *map(sexpr, node.args)])})'
    raise TypeError(f'no tree for {type(node).__name__}')


# ---- the tree of a file --------------------------------------------------------------------------------


@dataclass
class Cite:
    """`@name`: a named record."""

    name: str


@dataclass
class InPlace:
    """A record written in place under a line: `@kind [ID] "explanation"`."""

    kind: str
    id: str | None
    text: str


@dataclass
class UnitType:
    """A number with a unit that is composed: `L/h^2`."""

    unit: str


@dataclass
class NameType:
    """One name where a type stands: a unit (`g`) or a template (`Place`). The resolver decides."""

    name: str


@dataclass
class WordType:
    """`bool`, `text` or `number`."""

    word: str


@dataclass
class EnumType:
    cases: tuple


@dataclass
class FormulaType:
    of: object


@dataclass
class CollectionType:
    of: object


@dataclass
class DistributionType:
    of: object


@dataclass
class Range:
    """`in [low, high]` on a declaration: the closed range of the value."""

    low: object
    high: object


@dataclass
class Property:
    """`property = expression` under a value or a flow, or by its full path at the top level."""

    path: str
    value: object
    line: int = 0
    evidence: list = field(default_factory=list)


@dataclass
class Declare:
    """`[readonly | input] name[: type] [= value] [in [lo, hi]] [@record]`, with the lines under it."""

    name: str
    modifier: str | None = None
    type: object = None
    value: object = None
    range: Range | None = None
    evidence: list = field(default_factory=list)
    text: str | None = None
    properties: list = field(default_factory=list)
    line: int = 0


@dataclass
class Param:
    name: str
    type: object
    range: Range | None = None


@dataclass
class Assign:
    """`target = value`, `target += value` or `target -= value` in a stage."""

    target: str
    op: str
    value: object
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class Start:
    """A line that starts an event: `this.refill.start(50 g)`, or on each member of a collection."""

    call: object
    line: int = 0


@dataclass
class Move:
    """`move amount from source to destination`."""

    amount: object
    source: str
    destination: str
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class SwitchCase:
    label: str
    body: list = field(default_factory=list)
    line: int = 0


@dataclass
class Switch:
    selector: object
    cases: list = field(default_factory=list)
    orelse: list | None = None
    line: int = 0


@dataclass
class Capture:
    """`name = expression` in the body of a trigger: a value that the firing keeps."""

    name: str
    value: object
    line: int = 0


@dataclass
class Reset:
    """`reset when C` or `reset after D`: the last line of a trigger."""

    kind: str
    value: object
    line: int = 0


@dataclass
class Trigger:
    """`when C:` in the body of an event, with its firing body."""

    condition: object
    captures: list = field(default_factory=list)
    starts: list = field(default_factory=list)
    reset: Reset | None = None
    text: str | None = None
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class Stage:
    """`after D:` or `after D when C:` with its actions; `after D` alone waits and does nothing."""

    delay: object
    guard: object = None
    body: list = field(default_factory=list)
    text: str | None = None
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class Gate:
    """`until C`: the occurrence waits here until the condition holds."""

    condition: object
    line: int = 0


@dataclass
class FlowDecl:
    """`flow name: a -> b`, `flow name: a <-> b`, or `flow name:` with a leg on each line under it."""

    name: str
    kind: str  # 'directed', 'reversible' or 'legs'
    source: str | None = None
    sink: str | None = None
    properties: list = field(default_factory=list)
    legs: list = field(default_factory=list)
    text: str | None = None
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class EventDecl:
    """`[readonly] name = event(parameters):` with its body: locals and flows, triggers, steps."""

    name: str
    modifier: str | None = None
    params: list = field(default_factory=list)
    text: str | None = None
    evidence: list = field(default_factory=list)
    locals: list = field(default_factory=list)
    flows: list = field(default_factory=list)
    triggers: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    line: int = 0


@dataclass
class Unknown:
    """A new unknown of a solver: `care: h in [0 h, available]`."""

    name: str
    type: object
    value: object = None
    range: Range | None = None
    line: int = 0


@dataclass
class Objective:
    direction: str
    value: object
    line: int = 0


@dataclass
class SolverDecl:
    """`name = solver:` with its sections."""

    name: str
    modifier: str | None = None
    inputs: list = field(default_factory=list)  # Declare
    solve_for: list = field(default_factory=list)  # Unknown, or an expression (a path)
    constraints: list = field(default_factory=list)  # expressions
    objective: list = field(default_factory=list)  # Objective
    text: str | None = None
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class StatusCase:
    """`status rating [when C]` with its text."""

    rating: str
    condition: object = None
    text: str | None = None
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class Check:
    """`assert C` with its message."""

    condition: object
    text: str | None = None
    evidence: list = field(default_factory=list)
    line: int = 0


@dataclass
class RecordDecl:
    """`record name: kind [ID] "explanation"`, with the lines under it."""

    name: str
    kind: str
    id: str | None
    text: str
    relations: list = field(default_factory=list)  # (kind, ID)
    claims: list = field(default_factory=list)
    line: int = 0


@dataclass
class Entity:
    """`name:` (an entity), `Name:` (a template), `name: Template` (an instance) or
    `name: Template from "file.csv"` (one instance for each row of a table)."""

    name: str
    kind: str  # 'entity', 'template', 'instance' or 'table'
    template: str | None = None
    table: str | None = None
    text: str | None = None
    evidence: list = field(default_factory=list)
    members: list = field(default_factory=list)
    line: int = 0


@dataclass
class File:
    items: list = field(default_factory=list)
    context: str = 'file'


# ---- the tokens of one line, read in order ------------------------------------------------------------


class Cursor:
    def __init__(self, line, tokens=None, start=0):
        self.line = line
        self.tokens = line.tokens if tokens is None else tokens
        self.i = start

    def peek(self, k=0):
        i = self.i + k
        return self.tokens[i] if i < len(self.tokens) else None

    def take(self):
        token = self.peek()
        if token is None:
            self.fail('the line ends too soon')
        self.i += 1
        return token

    def done(self):
        return self.i >= len(self.tokens)

    def fail(self, message, token=None):
        token = token or self.peek()
        if token is None:
            last = self.tokens[-1] if self.tokens else None
            if last is None:
                raise SyntaxProblem(message, self.line.number)
            raise SyntaxProblem(message, last.line, last.column + len(last.source.split('\n')[-1]))
        raise SyntaxProblem(message, token.line, token.column)

    def at_op(self, *values):
        token = self.peek()
        return token is not None and token.is_op(*values)

    def at_name(self, *values):
        token = self.peek()
        return token is not None and token.kind == 'name' and token.value in values

    def op(self, value, message):
        token = self.peek()
        if token is None or not token.is_op(value):
            self.fail(message)
        self.i += 1
        return token

    def name(self, message):
        token = self.peek()
        if token is None or token.kind != 'name':
            self.fail(message)
        if token.value in RESERVED:
            self.fail(f'{token.value} is a word of the language and names nothing else', token)
        self.i += 1
        return token.value

    def end(self, message='nothing more belongs on this line'):
        if not self.done():
            token = self.peek()
            if token.is_op('='):
                self.fail('one = on a line: equality inside an expression is ==')
            if token.kind == 'text':
                self.fail('a text stands on a line of its own, under the line that it describes')
            self.fail(message)


def small(name):
    """Whether a name is the name of a value: it starts with a small letter or `_` (R-A1-04)."""
    return not name[:1].isupper()


VALUE_NAME = (
    'the name of a value starts with a small letter: a capital starts a template or a member of an enum'
)
COMPARISONS = {'<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge', '==': 'eq', '!=': 'ne'}
UP, DOWN = {'lt', 'le'}, {'gt', 'ge'}
MEMBERSHIP = 'to keep the result of a membership test, put the whole test in brackets: ok = (x in [lo, hi])'


class Expressions:
    """The precedence parser of expressions, over the tokens of a cursor. From the loosest binding:
    `a if C else b`; `or`; `and`; `not`; a comparison or `x in [lo, hi]`; `+ -`; `* /`; a sign; `**`;
    a dot (a member or an operation); a value.

    `bare_in` says that an `in` outside brackets does not belong to the expression: after the `=` of a
    declaration it starts the range, and after the `=` of an assignment it is refused. `statement` says
    that the expression is the head of a line of a stage, where `.start(...)` can stand."""

    def __init__(self, cursor, statement=False):
        self.c = cursor
        self.statement = statement
        self.started = None  # the `.start(...)` that the head of a statement holds

    # -- from the loosest binding to the tightest

    def expression(self, bare_in=True):
        body = self.disjunction(bare_in)
        if self.c.at_name('if'):
            self.c.i += 1
            test = self.disjunction(bare_in)
            if not self.c.at_name('else'):
                if self.c.at_name('in') and not bare_in:
                    self.c.fail(MEMBERSHIP)
                self.c.fail('a value that depends on a condition has both sides: a if C else b')
            self.c.i += 1
            return expr.if_else(test, body, self.expression(bare_in))
        return body

    def disjunction(self, bare_in):
        values = [self.conjunction(bare_in)]
        while self.c.at_name('or'):
            self.c.i += 1
            values.append(self.conjunction(bare_in))
        return values[0] if len(values) == 1 else expr.boolean('or', values)

    def conjunction(self, bare_in):
        values = [self.negation(bare_in)]
        while self.c.at_name('and'):
            self.c.i += 1
            values.append(self.negation(bare_in))
        return values[0] if len(values) == 1 else expr.boolean('and', values)

    def negation(self, bare_in):
        if self.c.at_name('not'):
            self.c.i += 1
            return expr.unary('not', self.negation(bare_in))
        return self.comparison(bare_in)

    def comparison(self, bare_in):
        operands, ops = [self.sum()], []
        while True:
            token = self.c.peek()
            if token is None:
                break
            if token.kind == 'op' and token.value in COMPARISONS:
                self.c.i += 1
                ops.append(COMPARISONS[token.value])
                self.chain(ops, token)
                operands.append(self.sum())
                continue
            if token.is_name('is'):
                self.c.fail('equality is == and inequality is !=: `is` is no longer a word of the language')
            if token.is_op('->', '<->'):
                self.c.fail(
                    f'{token.value} joins the two ends of a flow (`flow name: source {token.value} sink`): it is '
                    f'no part of an expression'
                )
            if token.is_op('='):
                self.c.fail('one = on a line: equality inside an expression is ==')
            if token.is_name('not') and self.c.peek(1) is not None and self.c.peek(1).is_name('in'):
                self.c.fail('there is no `not in`: write not (x in [lo, hi])')
            if token.is_name('in') and bare_in:
                if ops:
                    self.c.fail('a membership test is not chained with a comparison: put one of them in brackets')
                self.c.i += 1
                low, high = self.interval()
                found = within(operands[0], low, high)
                token = self.c.peek()
                if token is not None and (token.is_name('in') or (token.kind == 'op' and token.value in COMPARISONS)):
                    self.c.fail('a membership test is not chained with a comparison: put one of them in brackets')
                return found
            break
        return expr.compare(ops, operands) if ops else operands[0]

    def chain(self, ops, token):
        """A chain of comparisons points one way: `lo <= x < hi`. Any other chain is refused, so that
        `a < b > c` is never read beside the brackets of a collection."""
        if len(ops) < 2:
            return
        if not (set(ops) <= UP or set(ops) <= DOWN):
            self.c.fail(
                'a chain of comparisons points one way, as in lo <= x < hi: join the others with `and`', token
            )

    def interval(self):
        self.c.op('[', 'in is followed by a closed interval: x in [lo, hi]')
        low = self.expression()
        self.c.op(',', 'an interval has two ends: [lo, hi]')
        high = self.expression()
        self.c.op(']', 'an interval closes with ]: [lo, hi]')
        return low, high

    def sum(self):
        left = self.product()
        while self.c.at_op('+', '-'):
            op = 'add' if self.c.take().value == '+' else 'sub'
            left = expr.binary(op, left, self.product())
        return left

    def product(self):
        left = self.signed()
        while self.c.at_op('*', '/'):
            op = 'mul' if self.c.take().value == '*' else 'div'
            left = expr.binary(op, left, self.signed())
        return left

    def signed(self):
        if self.c.at_op('-', '+'):
            op = 'neg' if self.c.take().value == '-' else 'pos'
            return expr.unary(op, self.signed())
        return self.power()

    def power(self):
        base = self.postfix()
        if self.c.at_op('**'):
            self.c.i += 1
            return expr.binary('pow', base, self.signed())
        if self.c.at_op('^'):
            self.c.fail('a power of a value is a ** b; ^ writes the power of a unit, such as 5 m^2')
        return base

    def postfix(self):
        node = self.primary()
        if self.c.at_op('['):
            self.c.fail('a value has no index: a member of a collection is read by its key, c.at(key)')
        while self.c.at_op('.'):
            if self.started is not None:
                self.c.fail('nothing follows .start(...): it starts an occurrence and gives no value')
            self.c.i += 1
            token = self.c.peek()
            if token is None or token.kind != 'name':
                self.c.fail('a dot is followed by the name of a member: a row of a table is named by its id')
            if token.value in RESERVED:
                self.c.fail(f'{token.value} is a word of the language and names no member')
            self.c.i += 1
            name = token.value
            if not self.c.at_op('('):
                if isinstance(node, Case):
                    # `Route.instances` reads `Route` as a name; a member of an enum has no members.
                    node = expr.ref(node.name)
                node = member(node, name)
                continue
            if name not in METHODS:
                self.c.fail(
                    f'.{name}(...) is not an operation of the language: the operations are '
                    f'{", ".join("." + m for m in sorted(METHODS))}',
                    token,
                )
            if isinstance(node, Case):
                node = expr.ref(node.name)
            args = self.arguments()
            self.operation(name, args, token)
            node = method(node, name, args)
            if name == 'start':
                if not self.statement:
                    self.c.fail(
                        '.start(...) starts an occurrence and gives no value: write it on a line of its own '
                        'in a stage or in a trigger',
                        token,
                    )
                self.started = node
        return node

    def operation(self, name, args, token):
        """The form of the arguments of an operation, where the form decides how a name is read."""
        if name == 'where':
            if len(args) != 1 or not self.filter(args[0]):
                self.c.fail(
                    'inside where, a field of the member stands alone or on the left of a comparison, and '
                    'the right side is read in the enclosing scope: where(critical), where(destination == this)',
                    token,
                )
        elif name == 'by':
            if len(args) != 1 or not self.field(args[0]):
                self.c.fail('by takes one field of the member, which gives the key: by(rank)', token)
        elif name == 'at':
            if len(args) != 1:
                self.c.fail('at takes the one value to look up: at(t)', token)
        elif name == 'draw':
            if args:
                self.c.fail('draw takes no argument: the distribution has them', token)
        elif name == 'diff':
            if len(args) != 1 or not isinstance(args[0], expr.Ref):
                self.c.fail('diff takes the one named quantity to differentiate by: y.diff(z)', token)

    @staticmethod
    def field(node):
        return isinstance(node, expr.Ref) and '.' not in node.name and node.name not in ('this', 't')

    def filter(self, node):
        if self.field(node):
            return True
        if isinstance(node, expr.Unary) and node.op == 'not':
            return self.field(node.operand)
        if isinstance(node, expr.Compare) and len(node.ops) == 1:
            return self.field(node.operands[0])
        if isinstance(node, expr.BoolOp) and node.op == 'and':
            return all(self.filter(value) for value in node.values)
        return False

    def arguments(self):
        self.c.op('(', 'the arguments of a call are in brackets')
        args = []
        while not self.c.at_op(')'):
            if self.c.done():
                self.c.fail('the arguments of a call end with )')
            args.append(self.expression())
            if self.c.at_op(','):
                self.c.i += 1
                continue
            if not self.c.at_op(')'):
                self.c.fail('the arguments of a call are separated by commas and end with )')
        self.c.i += 1
        return args

    def primary(self):
        token = self.c.peek()
        if token is None:
            self.c.fail('a value is missing here')
        if token.kind == 'number':
            self.c.i += 1
            written = token.value
            value = float(written) if any(ch in written for ch in '.eE') else int(written)
            following = self.c.peek()
            if following is not None and following.kind == 'unit':
                self.c.i += 1
                return quantity(value, following.value)
            if following is not None and following.kind == 'name' and not following.space:
                self.c.fail(f'{written}{following.source}: a unit follows its number after one space, as in 48 h', token)
            if following is not None and following.kind in ('name', 'number') and following.value not in RESERVED:
                self.c.fail(
                    f'{written} {following.source}: a unit follows its number after exactly one space, and '
                    f'two values need an operator between them',
                    following,
                )
            return expr.const(value)
        if token.kind == 'text':
            self.c.i += 1
            return expr.const(token.value)
        if token.kind == 'unit':
            self.c.fail(f'the unit {token.value} follows no number')
        if token.kind == 'at':
            self.c.fail('a value is missing before the evidence')
        if token.kind == 'op':
            if token.value == '(':
                self.c.i += 1
                inner = self.expression()  # inside brackets, `in` is a membership test again
                self.c.op(')', 'a bracket ( closes with )')
                return inner
            if token.value == '<':
                return self.collection()
            if token.value == '[':
                self.c.fail('an interval stands after `in`: x in [lo, hi]. A collection is written <a, b>')
            if token.value in ('->', '<->'):
                self.c.fail(f'{token.value} joins the two ends of a flow: flow name: source {token.value} sink')
            if token.value == '=':
                self.c.fail('one = on a line: equality inside an expression is ==')
            self.c.fail(f'a value is missing before {token.value}')
        name = token.value
        following = self.c.peek(1)
        called = following is not None and following.is_op('(')
        if name in ('true', 'false'):
            self.c.i += 1
            return expr.const(name == 'true')
        if name == 'none':
            self.c.i += 1
            return absent()
        if name in ('this', 't'):
            self.c.i += 1
            return expr.ref(name)
        if name == 'formula':
            if not called:
                self.c.fail('formula keeps a calculation: formula(expression)')
            self.c.i += 2
            body = self.expression()
            self.c.op(')', 'formula(expression) closes with )')
            return formula(body)
        if name == 'event':
            self.c.fail('an event is declared on a line of its own: name = event(parameters):')
        if name == 'solver':
            self.c.fail('a solver is declared on a line of its own: name = solver:')
        if name in ('SOURCE', 'SINK'):
            self.c.fail(f'{name} is an end of a flow, not a value: flow name: SOURCE -> stock')
        if name in RESERVED:
            self.c.fail(f'{name} is a word of the language, not a value')
        if called:
            if name in FUNCTIONS or name in DISTRIBUTIONS:
                self.c.i += 1
                return expr.call(name, self.arguments())
            if name in OBJECTIVES:
                self.c.fail(f'{name}(...) ranks the answers of a solver: it stands in its objective section')
            self.c.fail(f'{name}(...) is not a function of the language')
        self.c.i += 1
        if not small(name):
            return case(name)
        return expr.ref(name)

    def collection(self):
        """`<a, b>`: each member is a path. An operator inside it needs brackets, so the first `>`
        always closes the literal."""
        opening = self.c.take()
        items = []
        if self.c.at_op('>'):
            self.c.i += 1
            return collection(items)
        while True:
            items.append(self.postfix())
            if self.c.at_op(','):
                self.c.i += 1
                if self.c.at_op('>'):
                    self.c.i += 1
                    break
                continue
            if self.c.at_op('>'):
                self.c.i += 1
                break
            self.c.fail(
                'a collection literal lists its members between < and >, as in <a, b>: a member with an '
                'operator needs brackets, and a comparison with < has a value on its left',
                self.c.peek() or opening,
            )
        return collection(items)


# ---- lines and blocks -----------------------------------------------------------------------------------

TOP = (
    'a line at the top level is an entity (`name:`), a template (`Name:`), an instance (`name: Template`), '
    'a table (`name: Template from "file.csv"`), a value (`name = value`), a property by its path '
    '(`a.b.request = value`), an assert or a record'
)
MEMBER = (
    'a line of an entity is its text, evidence, a value (`name: type = value`), a flow, an event '
    '(`name = event(...):`), a solver (`name = solver:`), an assert or a status case'
)
EVENT = (
    'a line of an event is its text, a local value or a flow (before the steps), a trigger (`when C:`), '
    'or a step (`after D:`, `after D when C:`, `until C`)'
)
ACTION = (
    'a line of a stage assigns (`x = v`, `x += v`, `x -= v`), starts an event (`e.start(...)`), moves '
    '(`move A from S to D`) or branches (`switch E:`)'
)
STEP_IN_STAGE = 'a timing step stands at the level of the event, outside the stages and their branches'


class Parser:
    """The lines of a text as a tree. `loose` lets a line that opens a block have no block under it,
    for the notation that the spec shows inline (`after 0 h:`)."""

    def __init__(self, text, loose=False):
        self.flat = lines(text)
        self.top = tree(self.flat)
        self.loose = loose

    # ---- small readers ---------------------------------------------------------------------------

    def cites(self, cursor):
        out = []
        while cursor.peek() is not None and cursor.peek().kind == 'at':
            at = cursor.take()
            token = cursor.peek()
            if token is None or token.kind != 'name':
                cursor.fail('@ names a record: @name', at)
            cursor.i += 1
            out.append(Cite(token.value))
        return out

    def word(self, cursor, message):
        """A word with no space inside it, such as an ID: `A-TIMING`."""
        token = cursor.peek()
        if token is None or token.kind in ('text', 'at'):
            cursor.fail(message)
        parts = [cursor.take()]
        while cursor.peek() is not None and not cursor.peek().space and cursor.peek().kind not in ('text', 'at'):
            parts.append(cursor.take())
        return ''.join(part.source for part in parts)

    @staticmethod
    def text_line(line):
        tokens = line.tokens
        if len(tokens) == 1 and tokens[0].kind == 'text':
            return tokens[0].value
        if tokens and tokens[0].kind == 'text':
            raise SyntaxProblem(
                'a text ends at its closing quote: write \\" for a quote inside it',
                tokens[1].line,
                tokens[1].column,
            )
        return None

    def evidence_line(self, line):
        """A line that starts with `@`: names (`@a @b`), or a record in place (`@kind [ID] "text"`)."""
        cursor = Cursor(line)
        second, third = cursor.peek(1), cursor.peek(2)
        if second is not None and second.is_name(*RECORD_KINDS) and third is not None and third.kind != 'at':
            cursor.i += 2
            identifier = None
            if cursor.peek().kind != 'text':
                identifier = self.word(cursor, 'a record names an ID, then its explanation in quotes')
            token = cursor.peek()
            if token is None or token.kind != 'text':
                cursor.fail('a record has its explanation in quotes: @kind "explanation"')
            cursor.i += 1
            cursor.end()
            return [InPlace(second.value, identifier, token.value)]
        found = self.cites(cursor)
        cursor.end('evidence on a line of its own names records: @a @b')
        if line.under:
            raise SyntaxProblem('nothing goes under a line of evidence', line.under[0].number)
        return found

    def described(self, line, node, also=None):
        """The lines under `line` that describe `node`: its text and its evidence. `also(child)` reads
        any other line, and returns False for a line that it does not read."""
        for child in line.under:
            if child.first.kind == 'at':
                node.evidence += self.evidence_line(child)
                continue
            value = self.text_line(child)
            if value is not None:
                if child.under:
                    raise SyntaxProblem('nothing goes under a text', child.under[0].number)
                if node.text is not None:
                    raise SyntaxProblem('a line has one text under it', child.number)
                node.text = value
                continue
            if also is None or also(child) is False:
                raise SyntaxProblem('this line does not belong here', child.number, child.first.column)

    def expression(self, cursor, bare_in=True):
        return Expressions(cursor).expression(bare_in)

    def path(self, cursor, message):
        """A dotted name with no call: `this.supply`, `batch`, `tank.water`."""
        token = cursor.peek()
        if token is None or token.kind != 'name' or (token.value in RESERVED and token.value != 'this'):
            cursor.fail(message)
        parts = [cursor.take().value]
        while cursor.at_op('.'):
            cursor.i += 1
            token = cursor.peek()
            if token is None or token.kind != 'name' or token.value in RESERVED:
                cursor.fail(message)
            parts.append(cursor.take().value)
        if cursor.at_op('('):
            cursor.fail(f'{message}: it holds no call')
        return '.'.join(parts)

    def range(self, cursor):
        cursor.take()  # in
        low, high = Expressions(cursor).interval()
        return Range(low, high)

    def body(self, line, what):
        """The lines under a line that opens a block. A block has one line at least."""
        if not line.under and not self.loose:
            raise SyntaxProblem(f'{what} has its lines under it, indented by four spaces', line.number)
        return line.under

    def no_body(self, line, what):
        if line.under:
            raise SyntaxProblem(f'nothing goes under {what}', line.under[0].number)

    # ---- types -----------------------------------------------------------------------------------

    def type(self, cursor):
        token = cursor.peek()
        if token is None:
            cursor.fail('a type is missing after the colon')
        if token.is_op('<'):
            cursor.i += 1
            inner = self.type(cursor)
            closing = cursor.peek()
            if closing is not None and closing.is_op('>='):
                # `<Pump>= <>`: the tokenizer read `>=`. Where a type closes it is `>` and then `=`.
                closing.value, closing.source, closing.column = '=', '=', closing.column + 1
            else:
                cursor.op('>', 'the type of a collection closes with >: <Pump>')
            return CollectionType(inner)
        if token.kind != 'name':
            cursor.fail(
                'a type is a unit, bool, text, number, enum[...], formula(T), <T> or the name of a template'
            )
        word = token.value
        following = cursor.peek(1)
        tight = following is not None and not following.space
        if word in TYPE_WORDS and not (tight and following.is_op('/', '-', '^')):
            cursor.i += 1
            return WordType(word)
        if word == 'enum':
            cursor.i += 1
            cursor.op('[', 'an enum lists its members: enum[OPEN, CLOSED]')
            cases = []
            while True:
                token = cursor.peek()
                if token is None or token.kind != 'name':
                    cursor.fail('an enum lists its members by name: enum[OPEN, CLOSED]')
                if small(token.value) or token.value in RESERVED:
                    cursor.fail(f'a member of an enum starts with a capital letter: {token.value.upper()}')
                if token.value in cases:
                    cursor.fail(f'an enum lists each member once: {token.value} is written twice')
                cases.append(cursor.take().value)
                if cursor.at_op(','):
                    cursor.i += 1
                    continue
                cursor.op(']', 'an enum closes with ]: enum[OPEN, CLOSED]')
                return EnumType(tuple(cases))
        if word == 'formula':
            cursor.i += 1
            cursor.op('(', 'the type of a formula names the type of its result: formula(bool)')
            inner = self.type(cursor)
            cursor.op(')', 'the type of a formula closes with ): formula(bool)')
            return FormulaType(inner)
        if word == 'distribution' and following is not None and following.is_op('('):
            cursor.i += 2
            inner = self.type(cursor)
            cursor.op(')', 'the type of a distribution closes with ): distribution(h)')
            return DistributionType(inner)
        if word in RESERVED:
            cursor.fail(f'{word} is a word of the language, not a type')
        # A unit, or the name of a template: the tokens with no space between them.
        parts = [cursor.take()]
        while True:
            token = cursor.peek()
            if token is None or token.space:
                break
            if token.kind in ('name', 'number') or token.is_op('/', '-', '^'):
                parts.append(cursor.take())
                continue
            break
        written = ''.join(part.source for part in parts)
        if not UNIT_WORD.fullmatch(written):
            cursor.fail(
                f'{written} is not a unit: a unit is names joined by / (divide) and - (multiply), each '
                f'with an optional whole power, as in L/h^2',
                parts[0],
            )
        return NameType(written) if len(parts) == 1 else UnitType(written)

    # ---- a file ------------------------------------------------------------------------------------

    def file(self, context='file'):
        out = File(context=context)
        if context == 'file':
            out.items = [self.top_item(line) for line in self.top]
        elif context == 'members':
            out.items = self.members(self.top, owner='entity')
        elif context == 'event':
            event = EventDecl('(fragment)')
            self.event_body(self.top, event)
            out.items = [event]
        elif context == 'stage':
            out.items = self.statements(self.top)
        else:
            raise ValueError(f'no context {context!r}')
        return out

    def top_item(self, line):
        cursor = Cursor(line)
        first, second = cursor.peek(), cursor.peek(1)
        if first.kind == 'text':
            cursor.fail('a text stands under the line that it describes')
        if first.kind == 'at':
            cursor.fail('evidence stands at the end of a line, or under it')
        if first.kind != 'name':
            cursor.fail(TOP)
        word = first.value
        if word == 'record':
            return self.record(line)
        if word == 'assert':
            return self.check(line)
        if word in ('readonly', 'input'):
            return self.declaration(line, 'top')
        if word in A5_WORDS and second is not None and (second.kind in ('name', 'text') or second.is_op(':')):
            if not (second.is_op(':') and (cursor.peek(2) is None or word not in ('runs', 'notes', 'report'))):
                cursor.fail(f'{word}: this prototype does not read the lines that brief A5 gives a spelling')
        if word in RETIRED and second is not None and second.kind == 'name':
            cursor.fail(f'{word} is no longer a word of the language: {RETIRED[word]}')
        if word == 'flow':
            cursor.fail('a flow belongs to an entity or to an event: write it under one')
        if word in ('after', 'until', 'when', 'reset', 'switch', 'move'):
            cursor.fail(f'{word} belongs to the body of an event')
        if word in RESERVED:
            cursor.fail(f'{word} is a word of the language and names nothing else')
        if second is None:
            cursor.fail(TOP)
        if second.is_op('.'):
            return self.property(line)
        if second.is_op('='):
            return self.declaration(line, 'top')
        if not second.is_op(':'):
            cursor.fail(TOP)
        third = cursor.peek(2)
        if third is None or third.kind == 'at':
            # `name:` or `Name:` with its members.
            cursor.i = 2
            kind = 'entity' if small(word) else 'template'
            entity = Entity(word, kind, evidence=self.cites(cursor), line=line.number)
            cursor.end()
            entity.members = self.entity_lines(line, entity)
            return entity
        # `name: Type ...`: an instance, a table, or a value with its type.
        cursor.i = 2
        declared = self.type(cursor)
        if cursor.at_op('=') or cursor.at_name('in'):
            return self.declaration(line, 'top')
        if not isinstance(declared, NameType) or small(declared.name):
            cursor.fail(
                'a value at the top level has its starting value (`name: type = value`); an instance names '
                'its template, which starts with a capital letter (`name: Template`)',
                third,
            )
        if not small(word):
            cursor.fail(f'the name of an instance starts with a small letter: {word[:1].lower()}{word[1:]}', first)
        entity = Entity(word, 'instance', template=declared.name, line=line.number)
        if cursor.at_name('from'):
            cursor.i += 1
            token = cursor.peek()
            if token is None or token.kind != 'text':
                cursor.fail(f'{word}: {declared.name} from "file.csv" names the file of its table, in quotes')
            cursor.i += 1
            entity.kind, entity.table = 'table', token.value
        entity.evidence = self.cites(cursor)
        cursor.end(f'{word}: {declared.name}, or {word}: {declared.name} from "file.csv"')
        entity.members = self.entity_lines(line, entity)
        return entity

    def entity_lines(self, line, entity):
        """The lines under an entity: its text and evidence, then its members."""
        rest = []
        for child in line.under:
            if child.first.kind == 'at':
                entity.evidence += self.evidence_line(child)
                continue
            value = self.text_line(child)
            if value is not None:
                if child.under:
                    raise SyntaxProblem('nothing goes under a text', child.under[0].number)
                if entity.text is not None:
                    raise SyntaxProblem('an entity has one text: its description', child.number)
                entity.text = value
                continue
            rest.append(child)
        return self.members(rest, owner=entity.kind)

    def members(self, found, owner):
        out = []
        fallback = None  # the status case with no condition
        for line in found:
            cursor = Cursor(line)
            first, second = cursor.peek(), cursor.peek(1)
            if first.kind == 'text':
                cursor.fail('a text stands under the line that it describes')
            if first.kind == 'at':
                cursor.fail('evidence stands at the end of a line, or under it')
            if first.kind != 'name':
                cursor.fail(MEMBER)
            word = first.value
            if word == 'flow':
                out.append(self.flow(line))
            elif word == 'assert':
                out.append(self.check(line))
            elif word == 'status' and second is not None and second.kind == 'name':
                if fallback is not None:
                    raise SyntaxProblem(
                        f'the status case with no condition is the last one: it is at line {fallback}',
                        line.number,
                        first.column,
                    )
                found_case = self.status(line)
                if found_case.condition is None:
                    fallback = line.number
                out.append(found_case)
            elif word in ('after', 'until', 'when', 'reset', 'switch', 'move'):
                cursor.fail(f'{word} belongs to the body of an event: name = event(...):')
            elif word == 'record':
                cursor.fail('a record is declared at the top level, and a line cites it with @name')
            elif word == 'event':
                cursor.fail('an event is a value now: name = event(parameters): with its steps under it')
            elif word in RETIRED and second is not None and second.kind == 'name':
                cursor.fail(f'{word} is no longer a word of the language: {RETIRED[word]}')
            elif word in ('readonly', 'input'):
                out.append(self.declaration(line, owner))
            elif word in RESERVED and word != 'this':
                cursor.fail(f'{word} is a word of the language and names nothing else')
            elif second is not None and second.is_op('.'):
                out.append(self.property(line))
            elif second is not None and second.is_op(':', '='):
                out.append(self.declaration(line, owner))
            elif second is not None and second.is_op('+=', '-='):
                cursor.fail('an entity declares its values: a change (+=, -=) belongs to a stage of an event', second)
            else:
                cursor.fail(MEMBER)
        return out

    # ---- values ------------------------------------------------------------------------------------

    def declaration(self, line, owner):
        """`[readonly | input] name[: type] [= value] [in [lo, hi]] [@record]`. After `=`, `event(...)`
        and `solver:` open the body of an event or of a solver."""
        cursor = Cursor(line)
        modifier = None
        if cursor.at_name('readonly', 'input'):
            modifier = cursor.take().value
            if cursor.at_name('readonly', 'input'):
                cursor.fail('a value is readonly or an input, not both: an input is fixed during a run')
        if modifier == 'input' and owner == 'event':
            cursor.fail('an event has no input: its parameters are in event(...), and an input belongs to an entity')
        token = cursor.peek()
        name = cursor.name('a value is declared as name = value, or name: type = value')
        if not small(name):
            cursor.fail(VALUE_NAME, token)
        node = Declare(name, modifier, line=line.number)
        if cursor.at_op(':'):
            cursor.i += 1
            node.type = self.type(cursor)
        if cursor.at_op('='):
            cursor.i += 1
            if cursor.at_name('event'):
                return self.event(line, cursor, node, owner)
            if cursor.at_name('solver'):
                return self.solver(line, cursor, node, owner)
            node.value = self.expression(cursor, bare_in=False)
        elif node.type is None:
            cursor.fail(f'{name} needs a type or a value: {name}: type, or {name} = value')
        if cursor.at_name('in'):
            node.range = self.range(cursor)
        node.evidence = self.cites(cursor)
        cursor.end()
        self.described(line, node, also=lambda child: self.under_value(child, node))
        return node

    def under_value(self, child, node):
        """A line under a value that is not its text or its evidence: the range on a line of its own,
        or a property of the value (`outflow.capacity = 10 L/h`)."""
        cursor = Cursor(child)
        if cursor.at_name('in'):
            if node.range is not None:
                cursor.fail('a value has one range')
            node.range = self.range(cursor)
            cursor.end()
            self.no_body(child, 'a range')
            return True
        first, second = cursor.peek(), cursor.peek(1)
        if first.kind == 'name' and second is not None and second.is_op('.', '='):
            node.properties.append(self.property(child))
            return True
        return False

    def property(self, line):
        """`path = expression`: a property of the value above, or of a value by its full path."""
        cursor = Cursor(line)
        path = self.path(cursor, 'a property is named by its path: outflow.capacity = 10 L/h')
        if cursor.at_op('+=', '-='):
            cursor.fail('a change (+=, -=) belongs to a stage of an event: here a property gets its starting value')
        cursor.op('=', f'{path} = value')
        value = self.expression(cursor, bare_in=False)
        if cursor.at_name('in'):
            cursor.fail(f'a range belongs to the declaration of a value. {MEMBERSHIP[0].upper()}{MEMBERSHIP[1:]}')
        node = Property(path, value, line.number, self.cites(cursor))
        cursor.end()
        self.no_body(line, 'a property')
        return node

    # ---- flows -------------------------------------------------------------------------------------

    def end_of_flow(self, cursor):
        token = cursor.peek()
        if token is not None and token.is_name('SOURCE', 'SINK'):
            cursor.i += 1
            return token.value
        return self.path(cursor, 'an end of a flow is the path of a stored quantity, SOURCE or SINK')

    def flow(self, line, leg=False):
        cursor = Cursor(line)
        cursor.take()
        token = cursor.peek()
        name = cursor.name('a flow is `flow name: source -> sink`')
        if not small(name):
            cursor.fail(VALUE_NAME, token)
        cursor.op(':', f'flow {name}: source -> sink')
        if cursor.done() or cursor.peek().kind == 'at':
            if leg:
                cursor.fail('a leg of a flow has its two ends: flow name: source -> sink')
            node = FlowDecl(name, 'legs', evidence=self.cites(cursor), line=line.number)
            cursor.end()

            def under(child):
                if child.first.is_name('flow'):
                    node.legs.append(self.flow(child, leg=True))
                    return True
                return False

            self.described(line, node, also=under)
            if not node.legs and not self.loose:
                raise SyntaxProblem(
                    f'flow {name}: has its two ends on its line, or one leg on each line under it', line.number
                )
            return node
        source = self.end_of_flow(cursor)
        arrow = cursor.peek()
        if arrow is None or not arrow.is_op('->', '<->'):
            cursor.fail('the two ends of a flow are joined by -> (one direction) or <-> (a reversible route)')
        cursor.i += 1
        sink = self.end_of_flow(cursor)
        if arrow.value == '<->':
            if leg:
                cursor.fail('a leg of a flow goes one way: source -> sink', arrow)
            if 'SOURCE' in (source, sink) or 'SINK' in (source, sink):
                cursor.fail('a reversible route joins two stocks: SOURCE and SINK stand at an end of a -> flow', arrow)
        else:
            if source == 'SINK' or sink == 'SOURCE':
                cursor.fail('SOURCE stands on the left of -> and SINK on the right', arrow)
        kind = 'reversible' if arrow.value == '<->' else 'directed'
        node = FlowDecl(name, kind, source, sink, evidence=self.cites(cursor), line=line.number)
        cursor.end(
            'the line of a flow holds its two ends: its rate and its limit are `request = ...` and '
            '`capacity = ...` on lines under it'
        )

        def under(child):
            if child.first.is_name('flow'):
                raise SyntaxProblem(
                    'a flow has its two ends, or legs under it, not both', child.number, child.first.column
                )
            second = child.tokens[1] if len(child.tokens) > 1 else None
            if child.first.kind == 'name' and second is not None and second.is_op('.', '='):
                node.properties.append(self.property(child))
                return True
            return False

        self.described(line, node, also=under)
        return node

    # ---- events ------------------------------------------------------------------------------------

    def event(self, line, cursor, declared, owner):
        if declared.type is not None:
            cursor.fail('an event writes the types of its parameters inside event(...), and takes no type itself')
        if declared.modifier == 'input':
            cursor.fail('an event is no input: it is read-only by default')
        if owner in ('top', 'event'):
            cursor.fail('an event belongs to an entity or to a template: declare it under one')
        cursor.take()
        cursor.op('(', 'an event lists its parameters, also when it has none: event():')
        node = EventDecl(declared.name, declared.modifier, line=line.number)
        while not cursor.at_op(')'):
            token = cursor.peek()
            name = cursor.name('a parameter is name: type')
            if not small(name):
                cursor.fail(VALUE_NAME, token)
            if name in [param.name for param in node.params]:
                cursor.fail(f'the parameter {name} is written twice', token)
            cursor.op(':', f'a parameter declares its type: {name}: type')
            param = Param(name, self.type(cursor))
            if cursor.at_name('in'):
                param.range = self.range(cursor)
            if cursor.at_op('='):
                cursor.fail('a parameter has no default value: each start gives every argument')
            node.params.append(param)
            if cursor.at_op(','):
                cursor.i += 1
                continue
            if not cursor.at_op(')'):
                cursor.fail('the parameters of an event are separated by commas and end with )')
        cursor.i += 1
        cursor.op(':', 'the line of an event ends with a colon, and its body is under it')
        node.evidence = self.cites(cursor)
        cursor.end()
        self.event_body(line.under, node)
        return node

    def event_body(self, found, node):
        for line in found:
            cursor = Cursor(line)
            first, second = cursor.peek(), cursor.peek(1)
            if first.kind == 'at':
                node.evidence += self.evidence_line(line)
                continue
            value = self.text_line(line)
            if value is not None:
                if node.text is not None:
                    raise SyntaxProblem('an event has one text: its card', line.number)
                node.text = value
                continue
            if first.kind != 'name':
                cursor.fail(EVENT)
            word = first.value
            if word == 'when':
                node.triggers.append(self.trigger(line, node))
            elif word == 'after':
                node.steps.append(self.stage(line))
            elif word == 'until':
                node.steps.append(self.gate(line))
            elif word == 'flow':
                self.early(node, cursor, 'a flow')
                node.flows.append(self.flow(line))
            elif word == 'status' and second is not None and second.kind == 'name':
                cursor.fail(
                    'a status display belongs to an entity. An event declares a field for its progress: '
                    'status: enum[WEIGHING, ADDED] = WEIGHING'
                )
            elif word in ('switch', 'move', 'reset', 'assert'):
                cursor.fail(f'{word} is an action: it belongs inside a stage (`after 0 h:`)' if word != 'reset' else 'reset is the last line of a trigger (`when C:`)')
            elif word == 'this' or (second is not None and second.is_op('.', '+=', '-=')):
                cursor.fail('an action belongs inside a stage of the event: after 0 h:')
            elif word == 'readonly' or (second is not None and second.is_op(':', '=')):
                self.early(node, cursor, 'a local value', second)
                node.locals.append(self.declaration(line, 'event'))
            elif word == 'input':
                cursor.fail('an event has no input: its parameters are in event(...), and an input belongs to an entity')
            elif word == 'at' and second is not None and second.kind in ('name', 'number'):
                cursor.fail('there is no `at T:` step in this version: a step waits a duration, `after D:`')
            else:
                cursor.fail(EVENT)

    @staticmethod
    def early(node, cursor, what, second=None):
        if node.steps:
            hint = ''
            if second is not None and second.is_op('='):
                hint = '. An assignment goes inside a stage: is this line indented too little?'
            cursor.fail(f'{what} of an event is declared at its start, before its timing steps{hint}')

    def trigger(self, line, event):
        cursor = Cursor(line)
        cursor.take()
        node = Trigger(self.expression(cursor), line=line.number)
        cursor.op(':', 'a trigger is `when C:` with its firing body under it')
        node.evidence = self.cites(cursor)
        cursor.end()
        for child in self.body(line, 'a trigger'):
            sub = Cursor(child)
            first, second = sub.peek(), sub.peek(1)
            if first.kind == 'at':
                node.evidence += self.evidence_line(child)
                continue
            value = self.text_line(child)
            if value is not None:
                node.text = value
                continue
            if node.reset is not None:
                sub.fail('reset is the last line of a trigger, and a trigger has one')
            if first.is_name('reset'):
                sub.i += 1
                if sub.at_name('when'):
                    sub.i += 1
                    node.reset = Reset('when', self.expression(sub), child.number)
                elif sub.at_name('after'):
                    sub.i += 1
                    node.reset = Reset('after', self.expression(sub), child.number)
                else:
                    sub.fail('a trigger is armed again by `reset when C` or `reset after D`')
                sub.end()
                self.no_body(child, 'a reset')
                continue
            if first.kind == 'name' and second is not None and second.is_op('='):
                if node.starts:
                    sub.fail('a trigger captures its values before it starts the event')
                name = sub.name('a capture is name = value')
                if not small(name):
                    sub.fail(VALUE_NAME, first)
                sub.i += 1
                node.captures.append(Capture(name, self.expression(sub, bare_in=False), child.number))
                if sub.at_name('in'):
                    sub.fail(MEMBERSHIP)
                sub.end()
                self.no_body(child, 'a capture')
                continue
            found = self.statement(child)
            if not isinstance(found, Start):
                raise SyntaxProblem(
                    'the body of a trigger captures values (`name = value`), starts its event '
                    '(`this.event.start(...)`) and ends with its reset; a change of state belongs to a '
                    'stage of the event',
                    child.number,
                    first.column,
                )
            target = found.call.base
            own = f'this.{event.name}'
            if event.name != '(fragment)' and not (isinstance(target, expr.Ref) and target.name == own):
                raise SyntaxProblem(
                    f'a trigger starts its own event: {own}.start(...)', child.number, first.column
                )
            node.starts.append(found)
        if not node.starts and not self.loose:
            raise SyntaxProblem('a trigger starts its event: this.event.start(...)', line.number)
        return node

    def stage(self, line):
        cursor = Cursor(line)
        cursor.take()
        node = Stage(self.expression(cursor), line=line.number)
        if cursor.at_name('when'):
            cursor.i += 1
            node.guard = self.expression(cursor)
        if cursor.done() and node.guard is None and not line.under:
            return node  # `after D`: a wait with no action
        cursor.op(':', 'a stage is `after D:` or `after D when C:` with its actions under it')
        node.evidence = self.cites(cursor)
        cursor.end()
        rest = []
        for child in self.body(line, 'a stage'):
            if child.first.kind == 'at':
                node.evidence += self.evidence_line(child)
                continue
            value = self.text_line(child)
            if value is not None and node.text is None and not rest:
                node.text = value
                continue
            rest.append(child)
        node.body = self.statements(rest)
        return node

    def gate(self, line):
        cursor = Cursor(line)
        cursor.take()
        node = Gate(self.expression(cursor), line.number)
        if cursor.at_op(':'):
            cursor.fail('until C is a gate with no body: the next step goes on when C holds')
        cursor.end()
        self.no_body(line, 'a gate (`until C`)')
        return node

    # ---- actions -----------------------------------------------------------------------------------

    def statements(self, found):
        return [self.statement(line) for line in found]

    def statement(self, line):
        cursor = Cursor(line)
        first, second = cursor.peek(), cursor.peek(1)
        if first.kind != 'name':
            cursor.fail(ACTION)
        word = first.value
        if word == 'switch':
            return self.switch(line)
        if word == 'move':
            return self.move(line)
        if word in ('after', 'until', 'when'):
            cursor.fail(STEP_IN_STAGE)
        if word == 'reset':
            cursor.fail('reset is the last line of a trigger (`when C:`)')
        if word == 'if':
            cursor.fail('a stage has no `if` line: guard the stage (`after D when C:`) or branch with `switch`')
        if word in ('flow', 'readonly', 'input', 'assert', 'record'):
            cursor.fail(f'{word} is a declaration: it stands at the start of the event or under an entity, not in a stage')
        if second is not None and second.is_op(':'):
            cursor.fail(
                'a stage declares no value: declare a local at the start of the event, before its timing '
                'steps, and assign to it here'
            )
        reader = Expressions(cursor, statement=True)
        head = reader.postfix()
        if cursor.at_op('=', '+=', '-='):
            op = cursor.take()
            if not isinstance(head, expr.Ref) or head.name in ('this', 't'):
                cursor.fail('the target of an assignment is a name or a dotted path: this.beans += amount', first)
            value = self.expression(cursor, bare_in=False)
            if cursor.at_name('in'):
                cursor.fail(MEMBERSHIP)
            node = Assign(head.name, op.value, value, self.cites(cursor), line.number)
            cursor.end()
            self.no_body(line, 'an assignment')
            return node
        if reader.started is head and head is not None:
            cursor.end('nothing follows .start(...): it starts an occurrence and gives no value')
            self.no_body(line, 'a start')
            return Start(head, line.number)
        cursor.fail(ACTION, first if cursor.done() else None)

    def switch(self, line):
        cursor = Cursor(line)
        cursor.take()
        node = Switch(self.expression(cursor), line=line.number)
        cursor.op(':', 'a switch is `switch E:` with one case on each line under it')
        cursor.end()
        for child in self.body(line, 'a switch'):
            sub = Cursor(child)
            first = sub.peek()
            if node.orelse is not None:
                sub.fail('else is the last case of a switch')
            if first.kind != 'name' or not sub.peek(1) or not sub.peek(1).is_op(':'):
                sub.fail('a case of a switch is a member of the enum and a colon (`REPAIR:`), or `else:`')
            sub.i += 2
            sub.end('a case has one label, and its actions under it')
            body = self.statements(self.body(child, 'a case'))
            if first.value == 'else':
                node.orelse = body
                continue
            if first.value not in ('true', 'false') and (small(first.value) or first.value in RESERVED):
                sub.fail('a case of a switch is a member of the enum (`REPAIR:`), `true:`, `false:` or `else:`', first)
            if first.value in [found.label for found in node.cases]:
                sub.fail(f'the case {first.value} is written twice', first)
            node.cases.append(SwitchCase(first.value, body, child.number))
        return node

    def move(self, line):
        cursor = Cursor(line)
        cursor.take()
        if cursor.at_op('('):
            # `move (a + b) from s to d` has its amount in brackets; `move(s, d, a)` is refused.
            depth = 0
            for token in cursor.tokens[cursor.i :]:
                if token.kind == 'op' and token.value in OPENS:
                    depth += 1
                elif token.kind == 'op' and token.value in CLOSES:
                    depth -= 1
                    if depth == 0:
                        break
                elif depth == 1 and token.is_op(','):
                    cursor.fail('a move has one form: move amount from source to destination', token)
        amount = self.expression(cursor)
        if not cursor.at_name('from'):
            cursor.fail('a move is `move amount from source to destination`')
        cursor.i += 1
        source = self.path(cursor, 'the source of a move is the path of a stored quantity')
        if not cursor.at_name('to'):
            cursor.fail('a move is `move amount from source to destination`')
        cursor.i += 1
        destination = self.path(cursor, 'the destination of a move is the path of a stored quantity')
        node = Move(amount, source, destination, self.cites(cursor), line.number)
        cursor.end()
        self.no_body(line, 'a move')
        return node

    # ---- solvers -----------------------------------------------------------------------------------

    def solver(self, line, cursor, declared, owner):
        if declared.type is not None:
            cursor.fail('a solver takes no type: its unknowns declare theirs under solve_for')
        if declared.modifier == 'input':
            cursor.fail('a solver is no input')
        if owner in ('top', 'event'):
            cursor.fail('a solver belongs to an entity or to a template: declare it under one')
        cursor.take()
        cursor.op(':', 'a solver is `name = solver:` with its sections under it')
        node = SolverDecl(declared.name, declared.modifier, evidence=self.cites(cursor), line=line.number)
        cursor.end()
        seen = {}

        def section(child):
            sub = Cursor(child)
            first, second = sub.peek(), sub.peek(1)
            if first.kind != 'name' or first.value not in SECTIONS or second is None or not second.is_op(':'):
                return False
            if first.value in seen:
                sub.fail(f'{first.value}: is written twice; the first is at line {seen[first.value]}')
            seen[first.value] = child.number
            sub.i += 2
            sub.end()
            for entry in self.body(child, f'{first.value}:'):
                getattr(self, f'solver_{first.value}')(entry, node)
            return True

        self.described(line, node, also=section)
        if 'solve_for' not in seen and not self.loose:
            raise SyntaxProblem(
                'a solver names what it determines under solve_for: (its sections are inputs:, solve_for:, '
                'constraints: and objective:)',
                line.number,
            )
        return node

    def solver_inputs(self, line, node):
        cursor = Cursor(line)
        token = cursor.peek()
        name = cursor.name('an input of a solver is name = value')
        if not small(name):
            cursor.fail(VALUE_NAME, token)
        cursor.op('=', f'an input of a solver binds a name: {name} = value')
        found = Declare(name, line=line.number)
        found.value = self.expression(cursor, bare_in=False)
        if cursor.at_name('in'):
            cursor.fail('an input of a solver keeps the range of its source: it declares none')
        found.evidence = self.cites(cursor)
        cursor.end()
        self.no_body(line, 'an input of a solver')
        node.inputs.append(found)

    def solver_solve_for(self, line, node):
        cursor = Cursor(line)
        first, second = cursor.peek(), cursor.peek(1)
        if first.kind == 'name' and second is not None and second.is_op(':'):
            name = cursor.name('a new unknown is name: type in [lo, hi]')
            if not small(name):
                cursor.fail(VALUE_NAME, first)
            cursor.i += 1
            found = Unknown(name, self.type(cursor), line=line.number)
            if cursor.at_op('='):
                cursor.i += 1
                found.value = self.expression(cursor, bare_in=False)
            if cursor.at_name('in'):
                found.range = self.range(cursor)
            cursor.end()
            self.no_body(line, 'an unknown')
            node.solve_for.append(found)
            return
        if first.kind == 'name' and second is not None and second.is_op('='):
            cursor.fail('a new unknown declares its type: name: type in [lo, hi]. An input goes under inputs:')
        found = Expressions(cursor).postfix()
        if not isinstance(found, (expr.Ref, Member)):
            cursor.fail('an entry of solve_for is the path of a field, or a new unknown (name: type)', first)
        cursor.end('an entry of solve_for is the path of a field, or a new unknown (name: type)')
        self.no_body(line, 'an entry of solve_for')
        node.solve_for.append(found)

    def solver_constraints(self, line, node):
        cursor = Cursor(line)
        node.constraints.append(self.expression(cursor))
        cursor.end()
        self.no_body(line, 'a constraint')

    def solver_objective(self, line, node):
        cursor = Cursor(line)
        first = cursor.peek()
        if first.kind != 'name' or first.value not in OBJECTIVES or not cursor.peek(1) or not cursor.peek(1).is_op('('):
            cursor.fail('a line of objective: is minimize(expression) or maximize(expression)')
        cursor.i += 2
        value = self.expression(cursor)
        cursor.op(')', f'{first.value}(expression) closes with )')
        cursor.end()
        self.no_body(line, 'an objective')
        node.objective.append(Objective(first.value, value, line.number))

    # ---- status, checks and records --------------------------------------------------------------

    def status(self, line):
        cursor = Cursor(line)
        cursor.take()
        rating = cursor.take()
        if rating.value not in RATINGS:
            cursor.fail(f'a status case rates {", ".join(RATINGS[:-1])} or {RATINGS[-1]}', rating)
        node = StatusCase(rating.value, line=line.number)
        if cursor.at_name('when'):
            cursor.i += 1
            node.condition = self.expression(cursor)
        node.evidence = self.cites(cursor)
        cursor.end('a status case is `status rating` or `status rating when C`, with its text under it')
        self.described(line, node)
        return node

    def check(self, line):
        cursor = Cursor(line)
        cursor.take()
        if cursor.at_name('initially'):
            following = cursor.peek(1)
            if following is not None and not following.is_op('.', '(') and following.kind != 'op':
                cursor.fail('there is no `assert initially` in this version: assert over the inputs that give the start')
        node = Check(self.expression(cursor), line=line.number)
        if cursor.at_name('within'):
            cursor.fail('there is no `within`: a tolerance is a closed interval, assert x in [lo, hi]')
        node.evidence = self.cites(cursor)
        cursor.end()
        self.described(line, node)
        return node

    def record(self, line):
        cursor = Cursor(line)
        cursor.take()
        name = cursor.name('a record is `record name: kind "explanation"`')
        cursor.op(':', f'record {name}: kind "explanation"')
        kind = cursor.peek()
        if kind is None or not kind.is_name(*RECORD_KINDS):
            cursor.fail(f'the kind of a record is {", ".join(RECORD_KINDS[:-1])} or {RECORD_KINDS[-1]}')
        cursor.i += 1
        identifier = None
        if cursor.peek() is not None and cursor.peek().kind != 'text':
            identifier = self.word(cursor, 'a record names an ID, then its explanation in quotes')
        token = cursor.peek()
        if token is None or token.kind != 'text':
            cursor.fail(f'a record has its explanation in quotes: record {name}: {kind.value} "explanation"')
        cursor.i += 1
        cursor.end()
        node = RecordDecl(name, kind.value, identifier, token.value, line=line.number)
        for child in line.under:
            sub = Cursor(child)
            first, second = sub.peek(), sub.peek(1)
            if first.is_name('claims') and second is not None and second.is_op(':'):
                sub.i += 2
                sub.end()
                for item in self.body(child, 'claims:'):
                    claim = Cursor(item)
                    node.claims.append(self.word(claim, 'a claim is listed by its ID'))
                    claim.end('a claim is listed by its ID')
                continue
            if first.is_name(*RECORD_KINDS) and second is not None:
                sub.i += 1
                node.relations.append((first.value, self.word(sub, 'a relation of a record names an ID')))
                sub.end()
                self.no_body(child, 'a relation of a record')
                continue
            sub.fail('under a record: `kind ID` for a record that it rests on, or claims: with one ID on each line')
        return node


# ---- entry points -----------------------------------------------------------------------------------------


def parse(text, context='file', loose=False):
    """The tree of a model text. `context` says where its lines stand: `file`, `members` (the body of
    an entity), `event` (the body of an event) or `stage` (the actions of a stage)."""
    return Parser(text, loose).file(context)


def one_line(text, what):
    found = [line for line in lines(text, alone=True) if line.kind == 'line']
    if len(found) != 1:
        raise SyntaxProblem(f'{what} is one line', 1)
    return found[0]


def parse_expression(text, bare_in=True):
    """The node of an expression that is written on its own."""
    cursor = Cursor(one_line(text, 'an expression'))
    found = Expressions(cursor).expression(bare_in)
    cursor.end('the expression ends here: what follows does not belong to it')
    return found


def parse_type(text):
    cursor = Cursor(one_line(text, 'a type'))
    found = Parser('', loose=True).type(cursor)
    cursor.end('the type ends here')
    return found


def parse_range(text):
    cursor = Cursor(one_line(f'in {text}', 'a range'))
    found = Parser('', loose=True).range(cursor)
    cursor.end('the range ends here')
    return found


# The kinds of `corpus/inline.txt`, and the place where each one stands.
KINDS = {
    'declaration': 'members',
    'statement': 'stage',
    'step': 'event',
    'setup': 'file',
}


def parse_inline(kind, text):
    """One piece of notation that the spec shows inline, by its kind (`corpus/inline.txt`)."""
    if kind == 'expression':
        return parse_expression(text)
    if kind == 'type':
        return parse_type(text)
    if kind == 'range':
        return parse_range(text)
    if kind == 'objective':
        reader = Parser(text, loose=True)
        node = SolverDecl('(fragment)')
        for line in reader.top:
            reader.solver_objective(line, node)
        return node.objective
    if kind == 'trigger':
        # A line of the body of a trigger: it is read under `when true:`.
        body = '\n'.join('    ' + row for row in text.split('\n'))
        event = parse(f'when true:\n{body}', 'event', loose=True).items[0]
        trigger = event.triggers[0]
        return [*trigger.captures, *trigger.starts, *([trigger.reset] if trigger.reset else [])]
    if kind not in KINDS:
        raise ValueError(f'no kind {kind!r}')
    found = parse(text, KINDS[kind], loose=True)
    if kind == 'step':
        event = found.items[0]
        return [*event.locals, *event.flows, *event.triggers, *event.steps]
    return found.items


# ---- a tree as text -------------------------------------------------------------------------------------


def type_text(found):
    if found is None:
        return ''
    if isinstance(found, UnitType):
        return found.unit
    if isinstance(found, NameType):
        return found.name
    if isinstance(found, WordType):
        return found.word
    if isinstance(found, EnumType):
        return f'enum[{", ".join(found.cases)}]'
    if isinstance(found, FormulaType):
        return f'formula({type_text(found.of)})'
    if isinstance(found, CollectionType):
        return f'<{type_text(found.of)}>'
    if isinstance(found, DistributionType):
        return f'distribution({type_text(found.of)})'
    raise TypeError(type(found).__name__)


def show(value):
    """One field of a node of the tree, on one line."""
    if isinstance(value, expr.Node):
        return write(value)
    if isinstance(value, (UnitType, NameType, WordType, EnumType, FormulaType, CollectionType, DistributionType)):
        return type_text(value)
    if isinstance(value, Range):
        return f'[{write(value.low)}, {write(value.high)}]'
    if isinstance(value, Cite):
        return f'@{value.name}'
    if isinstance(value, InPlace):
        return f'@{value.kind}{" " + value.id if value.id else ""} {text_text(value.text)}'
    if isinstance(value, Param):
        return f'{value.name}: {type_text(value.type)}' + (f' in {show(value.range)}' if value.range else '')
    if isinstance(value, str):
        return value
    return repr(value)


def dump(node, depth=0):
    """The tree as indented lines: each node with its fields, then the nodes under it."""
    pad = '  ' * depth
    if isinstance(node, list):
        return [row for item in node for row in dump(item, depth)]
    if isinstance(node, expr.Node):
        return [f'{pad}{write(node)}']
    if not is_dataclass(node) or isinstance(node, (Cite, InPlace, Range, Param)):
        return [f'{pad}{show(node)}']
    head, under = [type(node).__name__], []
    for item in fields(node):
        value = getattr(node, item.name)
        if item.name == 'line' or value is None or value == [] or value == ():
            continue
        if is_dataclass(value) and isinstance(value, (Reset,)):
            under.append((item.name, [value]))
        elif isinstance(value, list):
            if all(isinstance(entry, (Cite, InPlace, Param, str)) for entry in value):
                head.append(f'{item.name}=[{", ".join(show(entry) for entry in value)}]')
            elif all(isinstance(entry, tuple) for entry in value):
                head.append(f'{item.name}={value}')
            else:
                under.append((item.name, value))
        elif item.name == 'text':
            head.append(f'text={text_text(value)}')
        else:
            head.append(f'{item.name}={show(value)}')
    out = [pad + ' '.join(head)]
    for name, value in under:
        out.append(f'{pad}  {name}:')
        out += dump(value, depth + 2)
    return out


def census(node, counts=None):
    """The number of nodes of each kind in a tree."""
    counts = {} if counts is None else counts
    if isinstance(node, list):
        for item in node:
            census(item, counts)
    elif is_dataclass(node) and not isinstance(node, (Cite, InPlace, Range, Param)):
        key = type(node).__name__
        if isinstance(node, Entity):
            key = node.kind
        counts[key] = counts.get(key, 0) + 1
        for item in fields(node):
            value = getattr(node, item.name)
            if isinstance(value, list) or is_dataclass(value):
                census(value, counts)
    return counts


NAMES = {
    'entity': 'entities',
    'template': 'templates',
    'instance': 'instances',
    'table': 'tables',
    'Declare': 'values',
    'Property': 'properties',
    'EventDecl': 'events',
    'Trigger': 'triggers',
    'Stage': 'stages',
    'Gate': 'gates',
    'FlowDecl': 'flows',
    'SolverDecl': 'solvers',
    'Unknown': 'unknowns',
    'Objective': 'objectives',
    'Assign': 'assignments',
    'Start': 'starts',
    'Move': 'moves',
    'Switch': 'switches',
    'StatusCase': 'status cases',
    'Check': 'asserts',
    'RecordDecl': 'records',
    'Capture': 'captures',
    'Reset': 'resets',
}


def summary(found):
    counts = census(found.items)
    return ', '.join(f'{counts[key]} {name}' for key, name in NAMES.items() if key in counts) or 'nothing'


def contexts(folder):
    """{file name: context} from the manifest of a corpus folder."""
    manifest = Path(folder) / 'MANIFEST.tsv'
    out = {}
    if manifest.exists():
        for row in manifest.read_text(encoding='utf-8').split('\n')[1:]:
            if row:
                name, _, context = row.split('\t')
                out[name] = context
    return out


def run(path, context, show_tree=False):
    """One summary line for a file: (whether it parsed, the line)."""
    try:
        found = parse(Path(path).read_text(encoding='utf-8'), context)
    except SyntaxProblem as problem:
        where = f'line {problem.line}' + (f', column {problem.column}' if problem.column else '')
        return False, f'{path}: REFUSED ({context}) at {where}: {problem.message}', None
    rows = dump(found.items) if show_tree else None
    return True, f'{path}: parsed ({context}): {summary(found)}', rows


def main(argv):
    show_tree = '--tree' in argv
    argv = [arg for arg in argv if arg != '--tree']
    if argv[:1] == ['--expr']:
        try:
            node = parse_expression(argv[1])
        except SyntaxProblem as problem:
            print(f'REFUSED at column {problem.column}: {problem.message}')
            return 1
        print(write(node))
        print(sexpr(node))
        return 0
    context = None
    if '--context' in argv:
        at = argv.index('--context')
        context = argv[at + 1]
        del argv[at : at + 2]
    if not argv:
        print(__doc__)
        return 2
    failed = 0
    for target in argv:
        target = Path(target)
        if target.is_dir():
            known = contexts(target)
            paths = [(path, known.get(path.name, 'file')) for path in sorted(target.glob('*.scn'))]
        else:
            paths = [(target, context or contexts(target.parent).get(target.name, 'file'))]
        for path, where in paths:
            ok, line, rows = run(path, context or where, show_tree)
            failed += not ok
            print(line)
            for row in rows or ():
                print('    ' + row)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
