"""Expressions of the language as the Python trees that the compiler reads (docs/language.md, §2.1).

`tree(tokens)` writes the tokens of an expression as Python text, then parses it with `ast`:
- each name, or dotted name (`plant.dosing`, `find.done`), becomes a placeholder `_0`, `_1` …,
  which `names` maps back to the name as written. So any name of the file, even a word that Python
  keeps for itself, reads as a name;
- `is` becomes `==`, and `is not` becomes `!=`; `==` and `!=` are errors;
- a number with its unit, `2 h`, becomes `q(2, 'h')`, with the number as written;
- a text becomes a Python string.
The functions of the language, and `t`, `true` and `false`, stay names.
"""

from __future__ import annotations

import ast

from .lex import Lexer, SyntaxProblem

FUNCTIONS = frozenset(
    {'min', 'max', 'clip', 'abs', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf', 'sum', 'since'}
)
FUNCTIONS |= {'count', 'elapsed', 'q', 'any', 'all', 'delayed'}
# A distribution written in an event is drawn each time the event fires (docs/language.md, §2.6).
FUNCTIONS |= {'uniform', 'triangular', 'pert', 'loguniform', 'normal', 'lognormal', 'beta'}
# The names that stay names: the time, and yes and no.
KEPT = frozenset({'t', 'true', 'false'})
WORDS = {'not', 'and', 'or', 'if', 'else'}
OPERATORS = {'**', '*', '/', '+', '-', '<', '<=', '>', '>=', '(', ')', ','}


def placeholder(i):
    return f'_{i}'


def python(tokens):
    """(the Python text of an expression's tokens, {placeholder: name as written}, [(offset, token)]:
    where each token starts in the text)."""
    pieces, names, starts = [], {}, []
    length = 0

    def add(piece, token):
        nonlocal length
        starts.append((length, token))
        pieces.append(piece)
        length += len(piece) + 1

    i = 0
    while i < len(tokens):
        token = tokens[i]
        following = tokens[i + 1] if i + 1 < len(tokens) else None
        if token.kind == 'name':
            if token.value in FUNCTIONS and following is not None and following.is_op('('):
                add(token.value, token)
                i += 1
                continue
            if token.value == 'is':
                if following is not None and following.is_name('not'):
                    add('!=', token)
                    i += 2
                else:
                    add('==', token)
                    i += 1
                continue
            if token.value in WORDS or token.value in KEPT:
                add(token.value, token)
                i += 1
                continue
            if token.value in ('move', 'from', 'to', 'outside'):
                raise SyntaxProblem(
                    f'{token.value} is not a value: move A from S to D is a line of a change',
                    token.line,
                    token.column,
                )
            parts, j = [token.value], i + 1
            while (
                j + 1 < len(tokens)
                and tokens[j].is_op('.')
                and (
                    tokens[j + 1].kind == 'name'
                    # A copy's number after the name of its set: `waves.2.waiting`.
                    or (len(parts) == 1 and tokens[j + 1].kind == 'number' and tokens[j + 1].value.isdigit())
                )
            ):
                parts.append(tokens[j + 1].value)
                j += 2
            if j < len(tokens) and tokens[j].is_op('.'):
                raise SyntaxProblem('a dotted name ends with a name', tokens[j].line, tokens[j].column)
            key = placeholder(len(names))
            names[key] = '.'.join(parts)
            add(key, token)
            i = j
            continue
        if token.kind == 'number':
            if following is not None and following.kind == 'unit':
                add(f'q({token.value}, {following.value!r})', token)
                i += 2
            else:
                add(token.value, token)
                i += 1
            continue
        if token.kind == 'text':
            add(repr(token.value), token)
            i += 1
            continue
        if token.kind == 'op':
            if token.value in ('==', '!='):
                right = 'is' if token.value == '==' else 'is not'
                raise SyntaxProblem(
                    f'equality is `is`: write {right}, not {token.value}', token.line, token.column
                )
            if token.value in OPERATORS:
                add(token.value, token)
                i += 1
                continue
            if token.value == '^':
                raise SyntaxProblem(
                    'a power in an expression is a ** b; ^ writes the power of a unit, such as 5 m^2',
                    token.line,
                    token.column,
                )
            raise SyntaxProblem(f'{token.value} is not a part of an expression', token.line, token.column)
        if token.kind == 'at':
            raise SyntaxProblem(
                'evidence comes after the expression, at the end of the line', token.line, token.column
            )
        raise SyntaxProblem(
            f'{token.source or token.value} is not a part of an expression', token.line, token.column
        )
    return ' '.join(pieces), names, starts


def tree(tokens):
    """(the Python tree of an expression's tokens, {placeholder: name as written}). Raises
    `SyntaxProblem` at the token where the expression stops being one."""
    if not tokens:
        raise SyntaxProblem('an expression is missing', 0)
    text, names, starts = python(tokens)
    try:
        node = ast.parse(text, mode='eval').body
    except SyntaxError as exc:
        offset = (exc.offset or 1) - 1
        at = tokens[-1]
        for start, token in starts:
            if start <= offset:
                at = token
        raise SyntaxProblem(f'invalid expression: {exc.msg}', at.line, at.column) from None
    return node, names


def tokens_of(text, line=1):
    """The tokens of an expression written on its own (a text of one logical line)."""
    found = Lexer(text).lines()
    rows = [row for row in found if row.kind == 'line']
    if len(rows) != 1:
        raise SyntaxProblem('an expression is one line', line)
    return rows[0].tokens
