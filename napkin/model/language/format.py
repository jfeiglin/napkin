"""The formatter (docs/language.md, §2.1): each line of a file with the language's
spacing, within 110 columns where it can be.

The formatter writes each logical line again from its tokens, at four spaces for each level. It
never moves a line, never changes a text, never puts a space inside a unit and keeps the comments and
the empty lines where they are. A long line breaks:
- inside a text, at a single space: a line break inside a text reads as a space;
- inside a bracket, before a part that a space separates, on a line indented one level deeper than
  the line's first line.
A long line whose first bracket opens its expression, right after its `:`, its `=`, `move`, `when`,
`at`, `while` or `assert`, hangs
as the language page shows (§2.1): the bracket opens at the end of the first row, its inside fills
the rows one level deeper, and it closes at the start of the last row, with the rest of the line. A
line that has neither a text nor a bracket stays as it is. Formatting a formatted file changes
nothing, because the formatter reads only the tokens and never the layout.
"""

from __future__ import annotations

import re

from .lex import INDENT, OPENS
from .parse import Parser

WIDTH = 110
# The words before which a bracket keeps its space: `not (…)`, `if (…)`.
KEYWORDS = frozenset(
    {
        'if',
        'else',
        'and',
        'or',
        'not',
        'is',
        'from',
        'to',
        'move',
        'in',
        'when',
        'after',
        'at',
        'while',
        'assert',
    }
    | {'size', 'limit', 'order', 'within', 'versus'}
)
# The words after which a long line's first bracket hangs, as after its `:` or `=`.
HANG_AFTER = frozenset({'move', 'when', 'at', 'while', 'assert'})
# What comes before a sign: `-` after these is a sign, not a subtraction.
SIGN_AFTER_OPS = frozenset(
    {'(', '[', ',', '=', ':', '**', '*', '/', '+', '-', '<', '<=', '>', '>=', '->', '+=', '-='}
)
SINGLE_SPACE = re.compile(r'(?<! ) (?! )')
# A row never breaks right after these, so that a row that continues an expression starts with its
# operator: `+ standby_demand`.
OPERATORS = frozenset({'+', '-', '*', '/', '**', '<', '<=', '>', '>=', '=', '+=', '-=', '->'})
WORD_OPERATORS = frozenset({'and', 'or', 'not', 'is', 'if', 'else'})


def format_text(text):
    """The formatted text of a model file. Raises `SyntaxProblem` for a file that does not parse,
    and ValueError for a text that the language cannot write on several lines."""
    parser = Parser(text)
    parser.parse()
    return layout(parser.flat)


def layout(found):
    """The text of the lines of a file (`lex.lines`), each written again with the language's spacing
    and breaks. A stylesheet, which has the lines of a model file but not its declarations, is laid
    out so too."""
    out = []
    for line in found:
        if line.kind == 'blank':
            out.append('')
        elif line.kind == 'comment':
            out.append(' ' * (INDENT * line.depth) + line.comment)
        else:
            out.extend(render(line.tokens, INDENT * line.depth))
    return '\n'.join(out) + '\n'


def separator(before, previous, token, depth=0):
    """The space before `token`, which follows `previous` (and `before` it), `depth` brackets deep. A
    keyword argument inside a bracket has no spaces: `min=2 h`."""
    if previous is None or token.joined or previous.kind == 'at':
        return ''
    if depth > 0 and (token.is_op('=') or previous.is_op('=')):
        return ''
    if token.kind == 'at':
        return ' ' if before is not None and before.kind == 'at' else '  '
    if token.kind == 'unit':
        return ' '
    if token.is_op(':', ',', ')', ']', '.') or previous.is_op('(', '[', '.'):
        return ''
    if token.is_op('('):
        return '' if previous.kind == 'name' and previous.value not in KEYWORDS else ' '
    if previous.is_op('-') and sign(before):
        return ''
    return ' '


def sign(before):
    """Whether a `-` after `before` is a sign."""
    return (
        before is None
        or (before.kind == 'op' and before.value in SIGN_AFTER_OPS)
        or (before.kind == 'name' and before.value in KEYWORDS)
        or before.kind == 'at'
    )


def one_line(tokens):
    """The text of a line's tokens with the language's spacing, on one line."""
    out = ''
    before = previous = None
    level = 0
    for token in tokens:
        out += separator(before, previous, token, level) + written(token)
        before, previous = previous, token
        if token.kind == 'op' and token.value in OPENS:
            level += 1
        elif token.kind == 'op' and token.value in (')', ']'):
            level -= 1
    return out


def written(token):
    if token.kind == 'text':
        return f'"{token.value}"'
    return token.source or str(token.value)


def spacing(tokens):
    """[(the space before each token, the token)] of one logical line."""
    spaced = []
    before = previous = None
    level = 0
    for token in tokens:
        spaced.append((separator(before, previous, token, level), token))
        before, previous = previous, token
        if token.kind == 'op' and token.value in OPENS:
            level += 1
        elif token.kind == 'op' and token.value in (')', ']'):
            level -= 1
    return spaced


def render(tokens, indent):
    """The rows of one logical line."""
    spaced = spacing(tokens)
    hang = hanging(spaced, indent)
    if hang is None:
        return fill(spaced, indent)
    i, j = hang
    inside = [('', spaced[i + 1][1]), *spaced[i + 2 : j]]
    return [
        *fill(spaced[: i + 1], indent),
        *fill(inside, indent + INDENT, depth=1, continued=indent + INDENT),
        *fill([('', spaced[j][1]), *spaced[j + 1 :]], indent, depth=1),
    ]


def hanging(spaced, indent):
    """(the place of the opening bracket, of its closing bracket) of a line that hangs, or None: a
    line that does not fit, whose first bracket is a `(` right after its `:`, its `=` (or `+=`, `-=`)
    or a word of `HANG_AFTER`, with something inside."""
    tokens = [token for _, token in spaced]
    if any(token.kind == 'text' and '\n' in token.value for token in tokens):
        return None
    if indent + sum(len(space) + len(written(token)) for space, token in spaced) <= WIDTH:
        return None
    i = next((k for k, token in enumerate(tokens) if token.kind == 'op' and token.value in OPENS), None)
    if i is None or i == 0 or not tokens[i].is_op('('):
        return None
    before = tokens[i - 1]
    if not (before.is_op(':', '=', '+=', '-=') or (before.kind == 'name' and before.value in HANG_AFTER)):
        return None
    j = closing(tokens, i)
    return None if j == i + 1 else (i, j)


def closing(tokens, i):
    """The place of the bracket that closes the bracket at `i`."""
    depth = 0
    for j in range(i, len(tokens)):
        token = tokens[j]
        if token.kind == 'op' and token.value in OPENS:
            depth += 1
        elif token.kind == 'op' and token.value in (')', ']'):
            depth -= 1
            if depth == 0:
                return j
    raise ValueError('a bracket has no closing bracket')


def fill(spaced, indent, depth=0, continued=None):
    """The rows of tokens that start on a row at `indent`, `depth` brackets deep, on rows at
    `continued` after the first (one level deeper by default). Each row is filled; a row that is too
    long breaks at its best place (`breaks`): in the second half of the row, the last of the places
    with the fewest brackets open, so `a * (1 - b) + c` breaks before `+`, not inside the bracket. A
    text with spaces breaks inside itself (`text_rows`)."""
    rows = []
    row = ' ' * indent
    deeper = ' ' * (indent + INDENT if continued is None else continued)
    start = depth
    marks = []  # (where the space is in the row, the brackets open there): where the row can break
    for k, (space, token) in enumerate(spaced):
        tail = trailing(spaced, k, start)
        here = breaks(spaced, k, depth)
        if token.kind == 'text' and SINGLE_SPACE.search(token.value):
            fits = len(row) + len(space) + len(written(token)) + tail <= WIDTH
            gap = space
            if not fits and here and row.strip():
                rows.append(row)
                row, gap = deeper, ''
            opening = len(row) - len(row.lstrip(' '))
            done, row = text_rows(row + gap, token.value, ' ' * (opening + INDENT), tail)
            rows += done
            marks = []
            continue
        piece = space + written(token)
        while len(row) + len(piece) + tail > WIDTH and row.strip():
            options = marks + ([(len(row), depth)] if here else [])
            if not options:
                break
            # The places in the second half of the row, unless it has none: a break earlier would
            # leave a short row.
            lead = len(row) - len(row.lstrip(' '))
            options = [o for o in options if o[0] - lead >= (WIDTH - lead) // 2] or options
            fewest = min(level for _, level in options)
            cut = max(offset for offset, level in options if level == fewest)
            rows.append(row[:cut])
            if cut == len(row):
                row, piece, here, marks = deeper, written(token), False, []
            else:
                shift = len(deeper) - (cut + 1)
                row = deeper + row[cut + 1 :]
                marks = [(offset + shift, level) for offset, level in marks if offset > cut]
        if here:
            marks.append((len(row), depth))
        row += piece
        if token.kind == 'op' and token.value in OPENS:
            depth += 1
        elif token.kind == 'op' and token.value in (')', ']'):
            depth -= 1
    rows.append(row)
    return [r.rstrip() for r in rows]


def trailing(spaced, k, start=0):
    """The length of what must stay on the row of token `k`: the tokens after it up to the next place
    where the row can break (`breaks`), or to the end of the line. The tokens start `start` brackets
    deep."""
    length = 0
    depth = start
    for _, token in spaced[: k + 1]:
        if token.kind == 'op' and token.value in OPENS:
            depth += 1
        elif token.kind == 'op' and token.value in (')', ']'):
            depth -= 1
    for m in range(k + 1, len(spaced)):
        space, token = spaced[m]
        if breaks(spaced, m, depth):
            break
        if token.kind == 'text' and SINGLE_SPACE.search(token.value):
            # A text can break inside itself; its first word stays on the row.
            length += len(space) + 1 + len(SINGLE_SPACE.split(token.value, 1)[0])
            break
        length += len(space) + len(written(token))
        if token.kind == 'op' and token.value in OPENS:
            depth += 1
        elif token.kind == 'op' and token.value in (')', ']'):
            depth -= 1
    return length


def breaks(spaced, k, depth):
    """Whether a row can break before token `k`, `depth` brackets deep: at a space inside a bracket,
    but not inside a number with its unit, and not right after an operator."""
    space, token = spaced[k]
    if depth <= 0 or space != ' ' or token.kind == 'unit' or k == 0:
        return False
    previous = spaced[k - 1][1]
    if previous.kind == 'op' and previous.value in OPERATORS:
        return False
    return not (previous.kind == 'name' and previous.value in WORD_OPERATORS)


def text_rows(row, value, deeper, tail):
    """The rows of a text that starts on `row`: its words at single spaces, filling each row; each
    line break of the text an empty row. Returns (the finished rows, the row where the text ends).
    `tail` is the length of what follows the text on its last row."""
    paragraphs = value.split('\n')
    for i, paragraph in enumerate(paragraphs):
        if i and paragraph.startswith(' '):
            raise ValueError(f'a text cannot start a line with a space after a line break: {value!r}')
        if i < len(paragraphs) - 1 and paragraph.endswith(' '):
            raise ValueError(f'a text cannot end a line with a space before a line break: {value!r}')
    rows = []
    current = row + '"'
    for i, paragraph in enumerate(paragraphs):
        if i:
            # Each line break is one empty row, so an empty paragraph between two breaks has no row.
            if current != deeper:
                rows.append(current)
            rows.append('')
            current = deeper
        words = SINGLE_SPACE.split(paragraph) if paragraph else ['']
        started = False  # whether a word of this paragraph is on the row
        for j, word in enumerate(words):
            last = i == len(paragraphs) - 1 and j == len(words) - 1
            end = 1 + tail if last else 0
            joined = word if not started else ' ' + word
            if started and word and len(current) + len(joined) + end > WIDTH:
                rows.append(current)
                current = deeper + word
            else:
                current += joined
            started = True
    return rows, current + '"'
