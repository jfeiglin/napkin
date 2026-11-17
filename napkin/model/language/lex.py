"""The lines and the tokens of a model file (docs/language.md).

A file is a list of logical lines. A logical line is one line of the file, or more while a bracket
or a text is open. Each level of nesting is four spaces, and a tab is an error. A comment is a whole
line that starts with `#`, outside a text and outside brackets. The formatter keeps the comments and
the empty lines, so `lines` gives them too; `tree` gives the logical lines with the lines under each.

The tokens of a line are names, numbers, units, texts, `@` and the operators:
- a unit is the whole word after its number: it follows the number after one space, and it ends at
  the next space, comma, bracket, colon or bar. A reserved word is never a unit;
- a text is in double quotes, with no escapes. Its next lines are indented deeper than the line
  where it opens, except empty lines, which belong to the text. A line break inside it reads as a
  space, and an empty line is one line break.

Each token records whether a space comes before it on its line (`space`), so that the parser can
read the words that have no space inside them, such as an ID (`A-DEMO-RESPONSE`) or a unit of a type
(`L/h`), as one word.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

INDENT = 4
# The words that name nothing else (docs/language.md, §2.1).
RESERVED = frozenset(
    {
        # Names of the language: time, the clocks, copies and the ends of a move.
        't',
        'since',
        'count',
        'copy',
        'outside',
        'move',
        'from',
        'to',
        # The mark of an actor's choice under an event, and the window of an event.
        'choice',
        'each',
        # Words of an expression.
        'is',
        'not',
        'and',
        'or',
        'if',
        'else',
        'true',
        'false',
        'in',
    }
)
# The words that can follow a number on a line: none of them reads as its unit.
NOT_UNITS = RESERVED | {'size', 'when', 'while', 'within', 'order', 'limit', 'at', 'after', 'versus', 'each'}
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
NUMBER = re.compile(r'[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?')
# A unit is the whole word after its number, up to the next space, comma, bracket, colon or bar.
UNIT_WORD = re.compile(r'[^\s,()\[\]:|]+')
UNIT_START = re.compile(r'[A-Za-z_{]')
OPERATORS = ('**', '->', '<=', '>=', '==', '!=', '+=', '-=', '(', ')', '[', ']', ',', ':', '=', '+', '-', '*')
# `^` writes the power of a unit in a type (`m^2`); an expression has no `^` (`model/language/expressions`).
OPERATORS += ('/', '<', '>', '.', '{', '}', '|', '^')
# The operators that join two values: a line that ends with one, or a row that starts with one, means
# an expression that goes on outside brackets, which the language does not read.
JOINING = frozenset({'**', '<=', '>=', '==', '!=', '+', '-', '*', '/', '<', '>'})
JOINING_WORDS = frozenset({'and', 'or', 'if', 'else'})
CONTINUE = 'an expression goes on to the next row only inside brackets: ( … )'


def joins(token):
    return (token.kind == 'op' and token.value in JOINING) or (
        token.kind == 'name' and token.value in JOINING_WORDS
    )


OPENS = {'(': ')', '[': ']'}
CLOSES = {')': '(', ']': '['}


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


class Lexer:
    def __init__(self, text):
        if '\t' in text:
            number = text[: text.index('\t')].count('\n') + 1
            raise SyntaxProblem('a tab is not allowed: each level of nesting is four spaces', number)
        self.rows = text.split('\n')

    def indent(self, row, number):
        spaces = len(row) - len(row.lstrip(' '))
        return spaces

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
            tokens, i = self.logical(i, spaces)
            # No line of the language starts with an operator that joins two values, a sign included.
            if tokens and joins(tokens[0]):
                first = tokens[0]
                raise SyntaxProblem(
                    f'the line starts with {first.value}: {CONTINUE}', first.line, first.column
                )
            out.append(Line('line', depth, number, i, tokens))
        # Trailing empty lines of the file are not lines of it.
        while out and out[-1].kind == 'blank':
            out.pop()
        return out

    def logical(self, i, spaces):
        """The tokens of the logical line that starts at row `i`, and the row after it."""
        tokens = []
        stack = []  # the open brackets: (bracket, line, column)
        row = self.rows[i].rstrip()
        position = spaces
        space = True
        while True:
            if position >= len(row):
                if not stack:
                    if tokens and joins(tokens[-1]):
                        last = tokens[-1]
                        raise SyntaxProblem(
                            f'the line ends with {last.value}: {CONTINUE}', last.line, last.column
                        )
                    return tokens, i + 1
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
                if row[indent] == '#':
                    raise SyntaxProblem('a comment is a whole line outside brackets', i + 1, indent + 1)
                position, space = indent, True
                continue
            char = row[position]
            if char == ' ':
                position += 1
                space = True
                continue
            number, column = i + 1, position + 1
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
                # A unit is the whole word after the number, after one space.
                if row[position : position + 1] == ' ' and UNIT_START.match(row, position + 1):
                    word = UNIT_WORD.match(row, position + 1).group()
                    if word not in NOT_UNITS:
                        tokens.append(Token('unit', word, number, position + 2, True, word))
                        position += 1 + len(word)
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

    def text(self, i, row, position, space):
        """A text that opens at `position` of row `i`: its token, and the row and the position after
        its closing quote."""
        number, column = i + 1, position + 1
        opening = self.indent(row, number)
        close = row.find('"', position + 1)
        if close >= 0:
            value = row[position + 1 : close]
            return Token('text', value, number, column, space, row[position : close + 1]), i, row, close + 1
        pieces = [row[position + 1 :].rstrip()]
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
            close = row.find('"', indent)
            if close < 0:
                pieces.append(row[indent:])
                source.append(row)
                continue
            pieces.append(row[indent:close])
            source.append(row[: close + 1])
            # Empty lines just before the closing line still belong to the text.
            token = Token('text', fold(pieces), number, column, space, '\n'.join(source), len(source))
            return token, i, row, close + 1


def lines(text):
    """The lines of a file, in order: logical lines, comments and empty lines."""
    return Lexer(text).lines()


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
