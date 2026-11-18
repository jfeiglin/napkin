"""The lines and the tokens of a model file (spec, "Units, comparisons and layout").

A file is a list of logical lines. A logical line is one row of the file, or more while a bracket `(`
or `[` or a text is open: an expression goes on to the next row only inside brackets. Each level of
nesting is four spaces, and a tab is an error. A `#` outside a text starts a comment that runs to the
end of its row; a whole row that is a comment is a line of its own, and the comment that ends a row
stays with its logical line, so the formatter keeps both. `lines` gives the comments and the empty
rows too; `tree` gives the logical lines, each with the lines under it.

The tokens of a line are names, numbers, texts, `@` and the operators. A text is in double quotes;
`\\"` and `\\\\` are its only escapes. Its next rows are indented deeper than the row where it opens;
a row break inside it reads as a space and an empty row as one line break. Each token records whether
a space comes before it (`space`), so the parser can read a word with no space inside it (an ID such
as `A-TIMING`, the unit of a type) as one word, and a unit as the name one space after its number.
The lexer reads no unit: units are the parser's (D12).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .problems import SyntaxProblem

INDENT = 4
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
NUMBER = re.compile(r'[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?')
# Longest first, so `<->` is one token and `<-` none (`a<-b` is `a < -b`).
OPERATORS = ('<->', '**', '->', '<=', '>=', '==', '!=', '+=', '-=')
OPERATORS += ('(', ')', '[', ']', ',', ':', '=', '+', '-', '*', '/', '<', '>', '.')
# Characters of the old notation, each with its code and what to write now.
GONE = {
    '^': ('unit', 'a unit has no power: write L/h/h, or m * m; a value is raised with a ** b (D12)'),
    '|': ('retired', 'named states are an enum: enum[OPEN, CLOSED]'),
    '{': ('retired', 'a unit takes no text parameter: each field of a template has one dimension'),
    '}': ('retired', 'a unit takes no text parameter: each field of a template has one dimension'),
}
# The operators and words that join two values: no line starts or ends with one outside brackets.
JOINING = frozenset({'**', '<=', '>=', '==', '!=', '+', '-', '*', '/', '<', '>', '->', '<->'})
JOINING_WORDS = frozenset({'and', 'or', 'if', 'else'})
CONTINUE = 'an expression goes on to the next row only inside brackets: ( … )'
OPENS = {'(': ')', '[': ']'}
CLOSES = {')': '(', ']': '['}


@dataclass
class Token:
    """A token: its kind (`name`, `number`, `text`, `op` or `at`), its value (a text's with its
    escapes and row breaks read), where it starts (`line`, `column`, from 1), whether a space or the
    start of a row comes before it, its source as written, and the rows of the file that it takes."""

    kind: str
    value: object
    line: int
    column: int
    space: bool
    source: str = ''
    rows: int = 1

    def is_op(self, *values):
        return self.kind == 'op' and self.value in values

    def is_name(self, *values):
        return self.kind == 'name' and (not values or self.value in values)


@dataclass
class Line:
    """A logical line: its kind (`line`, `comment` or `blank`), its depth (one level is four
    spaces), the rows of the file where it starts and where it ends, its tokens, the text of a comment
    line, the comments that end its rows (`comments`), and the logical lines under it (`tree`)."""

    kind: str
    depth: int
    number: int
    end: int
    tokens: list = field(default_factory=list)
    comment: str = ''
    comments: list = field(default_factory=list)
    under: list = field(default_factory=list)

    @property
    def first(self):
        return self.tokens[0] if self.tokens else None


def fold(pieces):
    """The value of a text from its pieces, one for each row of the file (None for an empty row): a
    row break reads as a space, and an empty row is one line break."""
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


def joins(token, last=False):
    """Whether a token joins two values. A line can end with `>`, which closes `<Pump>` or `<>`."""
    if last and token.is_op('>'):
        return False
    return (token.kind == 'op' and token.value in JOINING) or (
        token.kind == 'name' and token.value in JOINING_WORDS
    )


class Lexer:
    """The rows of one text. `alone` reads one expression written on its own, which may start with a
    sign or with `<`."""

    def __init__(self, text, alone=False):
        self.alone = alone
        if '\t' in text:
            number = text[: text.index('\t')].count('\n') + 1
            raise SyntaxProblem(
                'a tab is not allowed: each level of nesting is four spaces', number, 0, 'tab'
            )
        self.rows = text.split('\n')

    @staticmethod
    def indent(row):
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
            spaces = self.indent(row)
            if spaces % INDENT:
                raise SyntaxProblem('each level of nesting is four spaces', number, spaces + 1, 'indent')
            depth = spaces // INDENT
            if row[spaces] == '#':
                out.append(Line('comment', depth, number, number, comment=row[spaces:]))
                i += 1
                continue
            tokens, i, comments = self.logical(i, spaces)
            first = tokens[0]
            # A line of a stage starts with `if` or `else:`; no other line starts with a word or an
            # operator that joins two values, a sign included.
            if (
                not self.alone
                and joins(first)
                and not first.is_name('if')
                and not (first.is_name('else') and len(tokens) > 1 and tokens[1].is_op(':'))
            ):
                raise SyntaxProblem(
                    f'the line starts with {first.value}: {CONTINUE}', first.line, first.column, 'continue'
                )
            out.append(Line('line', depth, number, i, tokens, comments=comments))
        # The empty rows at the end of the file are no lines of it.
        while out and out[-1].kind == 'blank':
            out.pop()
        return out

    def logical(self, i, spaces):
        """The tokens of the logical line that starts at row `i`, the row after it, and the comments
        that end its rows: [(row, text)]."""
        tokens, comments, stack = [], [], []  # stack: the open brackets (bracket, line, column)
        row = self.rows[i].rstrip()
        position, space = spaces, True
        while True:
            if position >= len(row):
                if not stack:
                    if tokens and joins(tokens[-1], last=True) and not self.alone:
                        last = tokens[-1]
                        raise SyntaxProblem(
                            f'the line ends with {last.value}: {CONTINUE}', last.line, last.column, 'continue'
                        )
                    return tokens, i + 1, comments
                # A bracket is open: the line goes on, on the next row that is not empty.
                i += 1
                while i < len(self.rows) and not self.rows[i].strip():
                    i += 1
                bracket, line, column = stack[-1]
                if i >= len(self.rows):
                    raise SyntaxProblem(
                        f'the bracket {bracket} has no closing {OPENS[bracket]}', line, column, 'bracket'
                    )
                row = self.rows[i].rstrip()
                indent = self.indent(row)
                if indent <= spaces and not (indent == spaces and row[indent] in CLOSES):
                    raise SyntaxProblem(
                        f'the bracket {bracket} has no closing {OPENS[bracket]}: the rows of a bracket are '
                        'indented deeper than its first row',
                        line,
                        column,
                        'bracket',
                    )
                position, space = indent, True
                continue
            char = row[position]
            if char == ' ':
                position += 1
                space = True
                continue
            number, column = i + 1, position + 1
            if char == '#':
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
            found = NUMBER.match(row, position) or NAME.match(row, position)
            if found:
                written = found.group()
                if written[0].isdigit():
                    if not math.isfinite(float(written)):
                        raise SyntaxProblem(f'{written} is not a finite number', number, column, 'number')
                    tokens.append(Token('number', written, number, column, space, written))
                else:
                    tokens.append(Token('name', written, number, column, space, written))
                position = found.end()
                space = False
                continue
            op = next((op for op in OPERATORS if row.startswith(op, position)), None)
            if op is None:
                if char in GONE:
                    code, message = GONE[char]
                    raise SyntaxProblem(
                        f'{char} is not a part of the language: {message}', number, column, code
                    )
                raise SyntaxProblem(
                    f'{char!r} is not a part of the language here', number, column, 'character'
                )
            if op in OPENS:
                stack.append((op, number, column))
            elif op in CLOSES:
                if not stack or stack[-1][0] != CLOSES[op]:
                    raise SyntaxProblem(f'{op} closes no bracket', number, column, 'bracket')
                stack.pop()
            tokens.append(Token('op', op, number, column, space, op))
            position += len(op)
            space = False

    @staticmethod
    def scan(row, start, number):
        """The characters of a text from `start` of a row, with its escapes read, and the index of its
        closing quote (None when the row ends first)."""
        out, k = [], start
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
                        'text',
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
        opening = self.indent(row)
        value, close = self.scan(row, position + 1, number)
        if close is not None:
            return Token('text', value, number, column, space, row[position : close + 1]), i, row, close + 1
        pieces, source = [value.rstrip()], [row[position:]]
        while True:
            i += 1
            if i >= len(self.rows):
                raise SyntaxProblem('the text has no closing quote', number, column, 'text')
            row = self.rows[i].rstrip()
            if not row.strip():
                pieces.append(None)
                source.append('')
                continue
            indent = self.indent(row)
            if indent <= opening:
                raise SyntaxProblem(
                    'the text has no closing quote: its next rows are indented deeper than the row where it '
                    'opens',
                    number,
                    column,
                    'text',
                )
            value, close = self.scan(row, indent, i + 1)
            pieces.append(value)
            if close is None:
                source.append(row)
                continue
            source.append(row[: close + 1])
            token = Token('text', fold(pieces), number, column, space, '\n'.join(source), len(source))
            return token, i, row, close + 1


def lines(text, alone=False):
    """The lines of a text, in order: logical lines, comment lines and empty rows."""
    return Lexer(text, alone).lines()


def tree(found):
    """The logical lines of `found` (`lines`) that are not comments or empty rows, each with the lines
    under it, and the lines at the top level. A line is one level deeper than the line that it is
    under, or at the level of one of the lines above it."""
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
                'a line is one level (four spaces) deeper than the line that it is under, or at the level '
                'of a line above it',
                line.number,
                line.depth * INDENT + 1,
                'indent',
            )
        (stack[-1].under if stack else top).append(line)
        stack.append(line)
    return top
