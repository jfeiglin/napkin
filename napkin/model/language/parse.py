"""The parser: the logical lines of a text (`lex.py`) as its tree (`nodes.py`), one tree for one text.

It reads the form of each line and resolves no name: what a name means, and whether a value has its
unit, is the declared model's (`napkin/model/semantic.py`). Each place where a line can stand has its
method, and a line that does not belong where it stands is refused with a message that names the
form it should have.

Expressions bind, from the loosest: `a if C else b`; `or`; `and`; `not`; a comparison or `x in [lo,
hi]`; `+ -`; `* /`; a sign; `**`; a dot (a member or an operation); a value. The place decides three
readings:

- **`in`**: after the `=` of a declaration an `in` outside brackets starts the range; after the `=`
  of an assignment it is refused, so one text has one meaning; elsewhere it tests membership.
- **Units (D12)**: a number with a name one space after it is a quantity, and its unit runs on
  through `*` and `/` while the next factor is a bare name (no dot, call or power after it). The run
  is kept as written (`Quantity.unit`); `48 h/2` stops before the 2 and `2 h * this.crews` before
  `this`. A hyphen or a `^` in a unit is refused: `person * year`, `L/h/h`.
- **Capitals**: a name with a capital first letter is a template or a member of an enum; the name of
  a value starts with a small letter.
- **The setup scope**: a top-level line that starts an event (`grinder.refill.start(50 g)`) is a
  statement of the setup, which commits as round zero; the top level has no other statement.
"""

from __future__ import annotations

from . import lex
from . import nodes as n
from .problems import SyntaxProblem

# The words that name nothing else. `scale` ends a declaration, so it is never read as a unit.
RESERVED = frozenset(
    {
        *('true', 'false', 'this', 't', 'SOURCE', 'SINK', 'none'),
        *('and', 'or', 'not', 'if', 'else', 'in', 'is'),
        *('from', 'to', 'when', 'after', 'until', 'reset', 'switch', 'move', 'assert', 'flow', 'record'),
        *('readonly', 'input', 'formula', 'event', 'solver', 'enum', 'bool', 'scale'),
    }
)
NONE = 'there is no none (D4): leave the declaration out, and say in the documentation or the evidence why'
# Words of the old notation that start a line, each with what to write now.
RETIRED = {
    'output': 'any named value can be reported (D10): name the calculation with an ordinary binding',
    'let': 'a value is `name = value`; a calculation that follows its inputs is `name = formula(...)`',
    'var': 'a value that changes is `name: type = value`',
    'versus': 'a scenario that compares runs runs the engine twice and compares the records (D9)',
    'share': 'sharing belongs to the endpoint: `outflow.allocation = priority(a, b)` under the stock',
    'report': 'a model has no report block (D10): the caller selects the paths and the times to report',
}
FUNCTIONS = frozenset(
    {
        *('min', 'max', 'clip', 'abs', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf'),
        *('sum', 'count', 'any', 'all', 'since', 'elapsed', 'delayed', 'priority', 'proportional'),
    }
)
DISTRIBUTIONS = frozenset(
    {'uniform', 'triangular', 'pert', 'loguniform', 'normal', 'lognormal', 'categorical'}
)
METHODS = frozenset({'where', 'by', 'at', 'draw', 'start', 'choose', 'diff'})
TYPE_WORDS = frozenset({'bool', 'text', 'number'})
RATINGS = ('ok', 'degraded', 'failed', 'inactive')
RECORD_KINDS = ('source', 'source_transfer', 'assumption', 'identity', 'convention')
SECTIONS = ('inputs', 'solve_for', 'constraints', 'objective')
HEADER = ('summary', 'horizon', 'scope', 'library', 'timescales', 'resolution')
COMPARISONS = frozenset({'<', '<=', '>', '>=', '==', '!='})
UP, DOWN = frozenset({'<', '<='}), frozenset({'>', '>='})
MEMBERSHIP = 'to keep the result of a membership test, put the whole test in brackets: ok = (x in [lo, hi])'
VALUE_NAME = (
    'the name of a value starts with a small letter: a capital starts a template or a member of an enum'
)
TOP = (
    'a line at the top level is the scenario line, a use, an entity (`name:`), a template (`Name:`), an '
    'instance (`name: Template`), a table (`name: Template from "file.csv"`), a value (`name = value`), a '
    'property by its path (`a.b.request = value`), a start of an event (`tank.fill.start(5 L)`), an '
    'assert, a record, a change, options, runs or notes'
)
COPIES = (
    'copies of a template are no form of the language: write each instance (name: Template), or give '
    'the rows in a table (name: Template from "file.csv")'
)
MEMBER = (
    'a line of an entity is its text, evidence, title, role, sees, a value (`name: type = value`), a flow, '
    'an event (`name = event(...):`), a solver (`name = solver:`), an assert or a status case'
)
EVENT = (
    'a line of an event is its text, its evidence, a local value or a flow (before the steps), a trigger '
    '(`when C:`), or a step (`after D:`, `after D when C:`, `after D`, `until C`)'
)
ACTION = (
    'a line of a stage assigns (`x = v`, `x += v`, `x -= v`), starts an event (`e.start(...)`), moves '
    '(`move A from S to D`) or branches (`if C:`, `switch E:`)'
)


def small(name):
    """Whether a name is the name of a value: it starts with a small letter or `_`."""
    return not name[:1].isupper()


class Cursor:
    """The tokens of one line, read in order."""

    def __init__(self, line, tokens=None):
        self.line = line
        self.tokens = line.tokens if tokens is None else tokens
        self.i = 0

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

    def fail(self, message, token=None, code='syntax'):
        token = token or self.peek()
        if token is None:
            last = self.tokens[-1] if self.tokens else None
            if last is None:
                raise SyntaxProblem(message, self.line.number, 0, code)
            raise SyntaxProblem(message, last.line, last.column + len(last.source.split('\n')[-1]), code)
        raise SyntaxProblem(message, token.line, token.column, code)

    def at_op(self, *values):
        token = self.peek()
        return token is not None and token.is_op(*values)

    def at_name(self, *values):
        token = self.peek()
        return token is not None and token.kind == 'name' and token.value in values

    def op(self, value, message):
        if not self.at_op(value):
            self.fail(message)
        return self.take()

    def name(self, message):
        """A name that is no word of the language."""
        token = self.peek()
        if token is None or token.kind != 'name':
            self.fail(message)
        if token.value in RESERVED:
            self.fail(
                NONE
                if token.value == 'none'
                else f'{token.value} is a word of the language and names nothing else',
                token,
                'none' if token.value == 'none' else 'reserved',
            )
        self.i += 1
        return token.value

    def text(self, message):
        token = self.peek()
        if token is None or token.kind != 'text':
            self.fail(message)
        self.i += 1
        return token.value

    def word(self, message):
        """A word with no space inside it, such as an ID: `A-TIMING`, `E-REPAIR-STUDY`."""
        token = self.peek()
        if token is None or token.kind in ('text', 'at'):
            self.fail(message)
        parts = [self.take()]
        while self.peek() is not None and not self.peek().space and self.peek().kind not in ('text', 'at'):
            if self.peek().is_op(',', ':', ')', ']'):
                break
            parts.append(self.take())
        return ''.join(part.source for part in parts)

    def cites(self):
        out = []
        while self.peek() is not None and self.peek().kind == 'at':
            at = self.take()
            token = self.peek()
            if token is None or token.kind != 'name':
                self.fail('@ names a record: @name', at)
            self.i += 1
            out.append(n.Cite(token.value, line=at.line, column=at.column))
        return tuple(out)

    def end(self, message='nothing more belongs on this line'):
        if not self.done():
            token = self.peek()
            if token.is_op('='):
                self.fail('one = on a line: equality inside an expression is ==')
            if token.kind == 'text':
                self.fail('a text stands on a row of its own, under the line that it describes')
            if token.is_name('in'):
                self.fail(MEMBERSHIP, code='in')
            self.fail(message)


def _place(token):
    return {'line': token.line, 'column': token.column}


class Expressions:
    """The precedence parser of expressions over a cursor. `statement` says that the expression is the
    head of a line of a stage or a trigger, where `.start(...)` can stand."""

    def __init__(self, cursor, statement=False):
        self.c = cursor
        self.statement = statement
        self.started = None

    def expression(self, bare_in=True):
        token = self.c.peek()
        body = self.disjunction(bare_in)
        if self.c.at_name('if'):
            self.c.i += 1
            test = self.disjunction(bare_in)
            if not self.c.at_name('else'):
                if self.c.at_name('in') and not bare_in:
                    self.c.fail(MEMBERSHIP, code='in')
                self.c.fail('a value that depends on a condition has both sides: a if C else b')
            self.c.i += 1
            return n.IfElse(test, body, self.expression(bare_in), **_place(token))
        return body

    def disjunction(self, bare_in):
        token = self.c.peek()
        values = [self.conjunction(bare_in)]
        while self.c.at_name('or'):
            self.c.i += 1
            values.append(self.conjunction(bare_in))
        return values[0] if len(values) == 1 else n.BoolOp('or', tuple(values), **_place(token))

    def conjunction(self, bare_in):
        token = self.c.peek()
        values = [self.negation(bare_in)]
        while self.c.at_name('and'):
            self.c.i += 1
            values.append(self.negation(bare_in))
        return values[0] if len(values) == 1 else n.BoolOp('and', tuple(values), **_place(token))

    def negation(self, bare_in):
        if self.c.at_name('not'):
            token = self.c.take()
            return n.Unary('not', self.negation(bare_in), **_place(token))
        return self.comparison(bare_in)

    def comparison(self, bare_in):
        start = self.c.peek()
        operands, ops = [self.sum()], []
        while True:
            token = self.c.peek()
            if token is None:
                break
            if token.kind == 'op' and token.value in COMPARISONS:
                self.c.i += 1
                ops.append(token.value)
                if len(ops) > 1 and not (set(ops) <= UP or set(ops) <= DOWN):
                    self.c.fail(
                        'a chain of comparisons points one way, as in lo <= x < hi: join the others with `and`',
                        token,
                        'chain',
                    )
                operands.append(self.sum())
                continue
            if token.is_name('is'):
                self.c.fail(
                    'equality is == and inequality is !=: `is` is no word of the language', code='retired'
                )
            if token.is_op('->', '<->'):
                self.c.fail(f'{token.value} joins the two ends of a flow (`flow name: a {token.value} b`)')
            if token.is_op('='):
                self.c.fail('one = on a line: equality inside an expression is ==')
            if token.is_name('not') and self.c.peek(1) is not None and self.c.peek(1).is_name('in'):
                self.c.fail('there is no `not in`: write not (x in [lo, hi])')
            if token.is_name('in') and bare_in:
                if ops:
                    self.c.fail(
                        'a membership test is not chained with a comparison: put one in brackets',
                        code='chain',
                    )
                self.c.i += 1
                low, high = self.interval()
                found = n.Within(operands[0], low, high, **_place(start))
                following = self.c.peek()
                if following is not None and (
                    following.is_name('in') or (following.kind == 'op' and following.value in COMPARISONS)
                ):
                    self.c.fail(
                        'a membership test is not chained with a comparison: put one in brackets',
                        code='chain',
                    )
                return found
            break
        return n.Compare(tuple(ops), tuple(operands), **_place(start)) if ops else operands[0]

    def interval(self):
        """`[lo, hi]` with either side left empty (D8): `[0,]`, `[, 10 L]`."""
        opening = self.c.op('[', 'in is followed by a closed interval: x in [lo, hi], or [0,] with one side')
        low = None if self.c.at_op(',') else self.expression()
        self.c.op(',', 'an interval has two sides separated by a comma: [lo, hi], or [0,] with one side')
        high = None if self.c.at_op(']') else self.expression()
        self.c.op(']', 'an interval closes with ]: [lo, hi]')
        if low is None and high is None:
            self.c.fail('an interval has at least one end: [0,] or [, 10 L]', opening)
        return low, high

    def sum(self):
        left = self.product()
        while self.c.at_op('+', '-'):
            token = self.c.take()
            left = n.Binary(token.value, left, self.product(), **_place(token))
        return left

    def product(self):
        left = self.signed()
        while self.c.at_op('*', '/'):
            token = self.c.take()
            left = n.Binary(token.value, left, self.signed(), **_place(token))
        return left

    def signed(self):
        if self.c.at_op('-', '+'):
            token = self.c.take()
            return n.Unary(token.value, self.signed(), **_place(token))
        return self.power()

    def power(self):
        base = self.postfix()
        if self.c.at_op('**'):
            token = self.c.take()
            return n.Binary('**', base, self.signed(), **_place(token))
        return base

    def postfix(self):
        node = self.primary()
        if self.c.at_op('['):
            self.c.fail('a value has no index: a member of a collection is read by its key, c.at(key)')
        while self.c.at_op('.'):
            if self.started is not None:
                self.c.fail(
                    'nothing follows .start(...): it starts an occurrence and gives no value', code='start'
                )
            dot = self.c.take()
            token = self.c.peek()
            if token is None or token.kind != 'name':
                self.c.fail('a dot is followed by the name of a member: a row of a table is named by its id')
            if token.value in RESERVED:
                self.c.fail(f'{token.value} is a word of the language and names no member', code='reserved')
            self.c.i += 1
            if not self.c.at_op('('):
                node = n.Member(node, token.value, **_place(dot))
                continue
            if token.value not in METHODS:
                self.c.fail(
                    f'.{token.value}(...) is no operation of the language: the operations are '
                    + ', '.join(f'.{name}' for name in sorted(METHODS)),
                    token,
                )
            node = n.Method(node, token.value, self.arguments(), **_place(token))
            if token.value == 'start':
                if not self.statement:
                    self.c.fail(
                        '.start(...) starts an occurrence and gives no value: write it on a line of its own in a '
                        'stage or in a trigger',
                        token,
                        'start',
                    )
                self.started = node
        return node

    def arguments(self, named=False):
        """The arguments of a call in brackets; with `named`, the outcomes `A: p` of `categorical`."""
        self.c.op('(', 'the arguments of a call are in brackets')
        args, pairs = [], []
        while not self.c.at_op(')'):
            if self.c.done():
                self.c.fail('the arguments of a call end with )')
            if named:
                token = self.c.peek()
                if (
                    token is None
                    or token.kind != 'name'
                    or small(token.value)
                    or not self.c.peek(1).is_op(':')
                ):
                    self.c.fail(
                        'categorical names each outcome, a member of an enum, with its weight: A: 0.7'
                    )
                self.c.i += 2
                if token.value in [name for name, _ in pairs]:
                    self.c.fail(f'categorical names each outcome once: {token.value} is written twice', token)
                pairs.append((token.value, self.expression()))
            else:
                args.append(self.expression())
            if self.c.at_op(','):
                self.c.i += 1
                continue
            if not self.c.at_op(')'):
                self.c.fail('the arguments of a call are separated by commas and end with )')
        self.c.i += 1
        return tuple(pairs) if named else tuple(args)

    def bare(self, k, first=False):
        """Whether the token at `k` is a bare name that a unit run can take: a name that is no word of
        the language, with no dot, call or index after it. A power ends the run before a later name
        (`2 h * x ** 2` raises x), and raises the quantity after its first name (`2 h ** 2`)."""
        token, following = self.c.peek(k), self.c.peek(k + 1)
        if token is None or token.kind != 'name' or token.value in RESERVED:
            return False
        stops = ('.', '(', '[') if first else ('.', '(', '[', '**')
        return following is None or not following.is_op(*stops)

    def quantity(self, token, value):
        """A number and, one space after it, its unit run."""
        first = self.c.peek()
        # `within` of the old notation is no unit, so the assertion that holds it can say what to write.
        if not (first is not None and first.kind == 'name' and first.value not in RESERVED | {'within'}):
            return n.Number(value, written=token.source, **_place(token))
        if not first.space or first.line != token.line:
            if not first.space:
                self.c.fail(
                    f'{token.source}{first.source}: a unit follows its number after one space, as in 48 h',
                    token,
                    'unit',
                )
            return n.Number(value, written=token.source, **_place(token))
        if first.value == 'size':
            self.c.fail(
                'size is now scale (D8), a numerical hint and no bound: due: tunings = need scale 20000 tunings',
                first,
                'retired',
            )
        if not self.bare(0, first=True):
            self.c.fail(
                f'{token.source} {first.source}: two values need an operator between them', first, 'syntax'
            )
        self.c.i += 1
        unit = [('', first.value)]
        while self.c.at_op('*', '/') and self.bare(1):
            unit.append((self.c.take().value, self.c.take().value))
        following = self.c.peek()
        if following is not None and following.is_op('-') and not following.space:
            after = self.c.peek(1)
            if after is not None and after.kind == 'name' and not after.space:
                self.c.fail(
                    'units multiply with *, as in person * year: a hyphen joins no unit (D12)',
                    following,
                    'unit',
                )
        return n.Quantity(value, tuple(unit), written=token.source, **_place(token))

    def primary(self):
        token = self.c.peek()
        if token is None:
            self.c.fail('a value is missing here')
        if token.kind == 'number':
            self.c.i += 1
            written = token.value
            value = float(written) if any(ch in written for ch in '.eE') else int(written)
            found = self.quantity(token, value)
            following = self.c.peek()
            if following is not None and following.kind in ('number', 'text') and following.space:
                self.c.fail('two values need an operator between them', following)
            return found
        if token.kind == 'text':
            self.c.i += 1
            return n.Text(token.value, **_place(token))
        if token.kind == 'at':
            self.c.fail('a value is missing before the evidence')
        if token.kind == 'op':
            if token.value == '(':
                self.c.i += 1
                inner = self.expression()
                self.c.op(')', 'a bracket ( closes with )')
                return inner
            if token.value == '<':
                return self.collection()
            if token.value == '[':
                self.c.fail('an interval stands after `in`: x in [lo, hi]. A collection is written <a, b>')
            self.c.fail(f'a value is missing before {token.value}')
        name = token.value
        called = self.c.peek(1) is not None and self.c.peek(1).is_op('(')
        if name in ('true', 'false'):
            self.c.i += 1
            return n.Bool(name == 'true', **_place(token))
        if name == 'none':
            self.c.fail(NONE, code='none')
        if name in ('this', 't'):
            self.c.i += 1
            return n.Name(name, **_place(token))
        if name == 'formula':
            if not called:
                self.c.fail('formula keeps a calculation: formula(expression)')
            self.c.i += 2
            body = self.expression()
            self.c.op(')', 'formula(expression) closes with )')
            return n.Formula(body, **_place(token))
        if name in ('event', 'solver'):
            self.c.fail(f'{name} is declared on a line of its own: name = {name}...')
        if name in ('SOURCE', 'SINK'):
            self.c.fail(f'{name} is an end of a flow, not a value: flow name: SOURCE -> stock')
        if name in RESERVED:
            self.c.fail(f'{name} is a word of the language, not a value', code='reserved')
        self.c.i += 1
        if called:
            if name == 'chance':
                self.c.fail(
                    'a random outcome is a branch on a drawn value (D1): switch categorical(A: 0.7, B: 0.3).draw():',
                    token,
                    'retired',
                )
            if name in FUNCTIONS or name in DISTRIBUTIONS:
                if name == 'categorical':
                    return n.Call(name, (), self.arguments(named=True), **_place(token))
                return n.Call(name, self.arguments(), **_place(token))
            if name in ('minimize', 'maximize'):
                self.c.fail(
                    f'{name}(...) ranks the answers of a solver: it stands in its objective section', token
                )
            self.c.fail(f'{name}(...) is no function of the language', token)
        return n.Name(name, **_place(token))

    def collection(self):
        """`<a, b>`: each member is a path. An operator inside it needs brackets, so the first `>`
        always closes the literal."""
        opening = self.c.take()
        items = []
        if self.c.at_op('>'):
            self.c.i += 1
            return n.Collection((), **_place(opening))
        while True:
            items.append(self.postfix())
            if self.c.at_op(','):
                self.c.i += 1
                continue
            if self.c.at_op('>'):
                self.c.i += 1
                return n.Collection(tuple(items), **_place(opening))
            self.c.fail(
                'a collection lists its members between < and >, as in <a, b>: a member with an operator needs '
                'brackets',
                self.c.peek() or opening,
            )


class Parser:
    """The lines of one text as its tree."""

    def __init__(self, text):
        self.flat = lex.lines(text)
        self.top = lex.tree(self.flat)
        # The comment rows and the empty rows above each line; empty rows collapse into one, and the
        # empty rows at the start of the text are none of its layout.
        self.lead, self.tail = {}, {}
        pending, started = [], False
        for line in self.flat:
            if line.kind == 'line':
                self.lead[line.number] = tuple(pending)
                self.tail[line.number] = tuple(text for _, text in line.comments)
                pending, started = [], True
            elif line.kind == 'comment':
                pending.append((line.depth, line.comment))
                started = True
            elif started and pending[-1:] != [(0, '')]:
                pending.append((0, ''))
        self.trailing = tuple(pending)

    def at(self, line):
        """The place and the layout of a line, for its node."""
        first = line.first
        return {
            'line': line.number,
            'column': first.column if first else 0,
            'lead': self.lead.get(line.number, ()),
            'tail': self.tail.get(line.number, ()),
        }

    # ---- small readers -------------------------------------------------------------------------

    @staticmethod
    def expression(cursor, bare_in=True):
        return Expressions(cursor).expression(bare_in)

    @staticmethod
    def text_line(line):
        """The text of a line that is one text, or None."""
        tokens = line.tokens
        if tokens[0].kind != 'text':
            return None
        if len(tokens) > 1:
            raise SyntaxProblem(
                'a text ends at its closing quote: write \\" for a quote inside it',
                tokens[1].line,
                tokens[1].column,
            )
        if line.under:
            raise SyntaxProblem('nothing goes under a text', line.under[0].number, 0, 'layout')
        return tokens[0].value

    def evidence_row(self, line):
        """A row that starts with `@`: names (`@a @b`), or a record in place (`@kind "text"`) with the
        IDs and claims that it rests on under it."""
        cursor = Cursor(line)
        kind, following = cursor.peek(1), cursor.peek(2)
        if (
            kind is not None
            and kind.is_name(*RECORD_KINDS)
            and following is not None
            and following.kind == 'text'
        ):
            cursor.i += 2
            text = cursor.take().value
            cursor.end('a record in place is @kind "explanation"; its IDs and claims go under it')
            relations, claims = self.record_lines(line)
            return [n.Inline(kind.value, text, relations, claims, line=line.number, column=line.first.column)]
        found = cursor.cites()
        if (
            kind is not None
            and kind.is_name(*RECORD_KINDS)
            and following is not None
            and following.kind != 'at'
        ):
            cursor.fail('a record in place has its explanation in quotes: @kind "explanation"')
        cursor.end('evidence on a row of its own names records: @a @b')
        if line.under:
            raise SyntaxProblem(
                'the rows under evidence belong to a record in place', line.under[0].number, 0, 'layout'
            )
        return list(found)

    def record_lines(self, line):
        """The relations (`assumption A-TIMING`) and the claims (`claims:` with an ID on each row, and
        `datum: key` under a claim) under a record."""
        relations, claims = [], []
        for child in line.under:
            cursor = Cursor(child)
            first, second = cursor.peek(), cursor.peek(1)
            if first.is_name('claims') and second is not None and second.is_op(':'):
                cursor.i += 2
                cursor.end('claims: has one ID on each row under it')
                for item in self.body(child, 'claims:'):
                    claim = Cursor(item)
                    identifier = claim.word('a claim is named by its ID')
                    claim.end('a claim is named by its ID; the record says how it supports the line')
                    datum = ''
                    for sub in item.under:
                        found = Cursor(sub)
                        if not (
                            found.at_name('datum') and found.peek(1) is not None and found.peek(1).is_op(':')
                        ):
                            found.fail('under a claim: datum: key')
                        found.i += 2
                        if datum:
                            found.fail('a claim names one datum')
                        datum = found.word('datum: names a key of the claim data')
                        found.end()
                    claims.append(n.Claim(identifier, datum, line=item.number, column=item.first.column))
                continue
            if first.is_name(*RECORD_KINDS) and second is not None:
                cursor.i += 1
                relations.append(
                    (first.value, cursor.word('a record rests on a record by its ID: assumption A-ID'))
                )
                cursor.end()
                self.no_body(child, 'the ID of a record')
                continue
            cursor.fail(
                'under a record: `kind ID` for a record that it rests on, or claims: with one ID on each row'
            )
        return tuple(relations), tuple(claims)

    def described(self, line, also=None):
        """(text, evidence) of the rows under a line. `also(child)` reads any other row and returns
        False for a row that it does not read."""
        text, evidence = None, []
        for child in line.under:
            if child.first.kind == 'at':
                evidence += self.evidence_row(child)
                continue
            value = self.text_line(child)
            if value is not None:
                if text is not None:
                    raise SyntaxProblem('a line has one text under it', child.number, 0, 'layout')
                text = value
                continue
            if also is None or also(child) is False:
                raise SyntaxProblem(
                    'this line does not belong here', child.number, child.first.column, 'layout'
                )
        return text, tuple(evidence)

    @staticmethod
    def body(line, what):
        """The lines under a line that opens a block: one line at least."""
        if not line.under:
            raise SyntaxProblem(
                f'{what} has its lines under it, indented by four spaces', line.number, 0, 'layout'
            )
        return line.under

    @staticmethod
    def no_body(line, what):
        if line.under:
            raise SyntaxProblem(f'nothing goes under {what}', line.under[0].number, 0, 'layout')

    @staticmethod
    def path(cursor, message):
        """A dotted name with no call: `this.supply`, `batch`, `tank.water`; `SOURCE` and `SINK`."""
        token = cursor.peek()
        if (
            token is None
            or token.kind != 'name'
            or (token.value in RESERVED and token.value not in ('this', 'SOURCE', 'SINK'))
        ):
            cursor.fail(message)
        parts = [cursor.take().value]
        while cursor.at_op('.') and parts[0] not in ('SOURCE', 'SINK'):
            cursor.i += 1
            token = cursor.peek()
            if token is None or token.kind != 'name' or token.value in RESERVED:
                cursor.fail(message)
            parts.append(cursor.take().value)
        if cursor.at_op('('):
            cursor.fail(f'{message}: it holds no call')
        return tuple(parts)

    def range_of(self, cursor):
        token = cursor.take()  # in
        low, high = Expressions(cursor).interval()
        return n.Range(low, high, **_place(token))

    # ---- types ---------------------------------------------------------------------------------

    def type(self, cursor):
        token = cursor.peek()
        if token is None:
            cursor.fail('a type is missing after the colon')
        if token.is_op('<'):
            cursor.i += 1
            inner = self.type(cursor)
            closing = cursor.peek()
            if closing is not None and closing.is_op('>='):
                # `<Pump>= <>`: where a type closes, `>=` is `>` and then `=`.
                cursor.tokens[cursor.i : cursor.i + 1] = [
                    lex.Token('op', '>', closing.line, closing.column, closing.space, '>'),
                    lex.Token('op', '=', closing.line, closing.column + 1, False, '='),
                ]
            cursor.op('>', 'the type of a collection closes with >: <Pump>')
            return n.CollectionType(inner, **_place(token))
        if token.kind != 'name' and not (token.kind == 'number' and token.value == '1'):
            cursor.fail(
                'a type is a unit, bool, text, number, enum[...], formula(T), distribution(T), <T> or a template'
            )
        word, following = token.value, cursor.peek(1)
        if word in TYPE_WORDS and not (following is not None and following.is_op('*', '/')):
            cursor.i += 1
            return n.WordType(word, **_place(token))
        if word == 'enum':
            cursor.i += 1
            cursor.op('[', 'an enum lists its members: enum[OPEN, CLOSED]')
            members = []
            while True:
                found = cursor.peek()
                if found is None or found.kind != 'name':
                    cursor.fail('an enum lists its members by name: enum[OPEN, CLOSED]')
                if small(found.value) or found.value in RESERVED:
                    cursor.fail(
                        f'a member of an enum starts with a capital letter: {found.value.upper()}',
                        code='name',
                    )
                if found.value in members:
                    cursor.fail(f'an enum lists each member once: {found.value} is written twice')
                members.append(cursor.take().value)
                if cursor.at_op(','):
                    cursor.i += 1
                    continue
                cursor.op(']', 'an enum closes with ]: enum[OPEN, CLOSED]')
                return n.EnumType(tuple(members), **_place(token))
        if word in ('formula', 'distribution') and following is not None and following.is_op('('):
            cursor.i += 2
            inner = self.type(cursor)
            cursor.op(')', f'the type of a {word} closes with ): {word}(h)')
            kind = n.FormulaType if word == 'formula' else n.DistributionType
            return kind(inner, **_place(token))
        if word in RESERVED:
            cursor.fail(f'{word} is a word of the language, not a type', code='reserved')
        unit = self.unit_expression(cursor)
        if isinstance(unit, str):
            return n.NamedType(unit, **_place(token))
        return n.UnitType(unit, **_place(token))

    def unit_expression(self, cursor):
        """The unit of a type: names joined by `*` and `/` from the left, with brackets."""
        left = self.unit_term(cursor)
        while cursor.at_op('*', '/'):
            op = cursor.take().value
            left = n.UnitOp(op, left, self.unit_term(cursor))
        following = cursor.peek()
        if following is not None and following.is_op('-') and not following.space:
            cursor.fail(
                'units multiply with *, as in person * year: a hyphen joins no unit (D12)', following, 'unit'
            )
        return left

    def unit_term(self, cursor):
        token = cursor.peek()
        if token is not None and token.is_op('('):
            cursor.i += 1
            inner = self.unit_expression(cursor)
            cursor.op(')', 'a bracket in a unit closes with ): tunings / (tuner * year)')
            return inner
        if token is not None and token.kind == 'number' and token.value == '1':
            cursor.i += 1
            return '1'
        if token is None or token.kind != 'name' or token.value in RESERVED:
            cursor.fail(
                'a unit is the names of units joined by * and /, as in L/h or person * year', code='unit'
            )
        cursor.i += 1
        return token.value

    # ---- the file ------------------------------------------------------------------------------

    def file(self):
        items = []
        for k, line in enumerate(self.top):
            items.append(self.top_item(line, k))
        return n.File(tuple(items), self.trailing)

    def top_item(self, line, k):
        cursor = Cursor(line)
        first, second = cursor.peek(), cursor.peek(1)
        if first.kind == 'text':
            cursor.fail('a text stands under the line that it describes', code='layout')
        if first.kind == 'at':
            cursor.fail('evidence stands at the end of a line, or under it', code='layout')
        if first.kind != 'name':
            cursor.fail(TOP)
        word = first.value
        if word in ('scenario', 'variant') and second is not None and second.kind == 'text':
            if k:
                cursor.fail(
                    f'the {word} line is the first declaration of its file: a file that starts with another '
                    'declaration is a module'
                )
            return self.scenario(line)
        if word == 'use' and second is not None and second.kind == 'name':
            return self.use(line)
        if word == 'record' and second is not None and second.kind == 'name':
            return self.record(line)
        if word == 'assert':
            return self.assertion(line)
        if word in ('readonly', 'input'):
            return self.declaration(line, 'top')
        if (
            word in RETIRED
            and second is not None
            and (second.kind == 'name' or (word == 'report' and second.is_op(':')))
        ):
            cursor.fail(f'{word} is no longer a word of the language: {RETIRED[word]}', code='retired')
        if word == 'change' and second is not None and second.kind == 'name':
            return self.change(line)
        if word == 'options' and second is not None and second.kind == 'text':
            return self.options(line)
        if word == 'runs' and second is not None and second.is_op(':') and cursor.peek(2) is None:
            return self.runs(line)
        if word == 'notes' and second is not None and second.is_op(':') and cursor.peek(2) is None:
            return self.notes_block(line)
        if word == 'flow':
            cursor.fail('a flow belongs to an entity or to an event: write it under one')
        if word in ('after', 'until', 'when', 'reset', 'switch', 'move', 'if'):
            cursor.fail(f'{word} belongs to the body of an event')
        if word in RESERVED:
            cursor.fail(
                NONE if word == 'none' else f'{word} is a word of the language and names nothing else',
                code='none' if word == 'none' else 'reserved',
            )
        if second is None:
            cursor.fail(TOP)
        if second.is_op('.'):
            # A line with no assignment is a start of the setup scope (`grinder.refill.start(50 g)`).
            if not any(token.is_op('=', '+=', '-=') for token in line.tokens):
                return self.setup_start(line)
            return self.property(line)
        if second.is_op('='):
            return self.declaration(line, 'top')
        if not second.is_op(':'):
            cursor.fail(TOP)
        third = cursor.peek(2)
        if third is None or third.kind == 'at':
            return self.entity(line)
        # `couriers: Courier * 3` of the old notation; a unit's type never multiplies by a number.
        following, count = cursor.peek(3), cursor.peek(4)
        if (
            third.kind == 'name'
            and not small(third.value)
            and following is not None
            and following.is_op('*')
            and count is not None
            and count.kind == 'number'
        ):
            cursor.fail(COPIES, third, 'retired')
        cursor.i = 2
        declared = self.type(cursor)
        if cursor.at_name('from'):
            return self.table(line, cursor, declared)
        return self.declaration(line, 'top')

    def setup_start(self, line):
        """`grinder.refill.start(50 g)` at the top level: a start of the setup scope, which commits
        as round zero. The setup scope starts events and does nothing else."""
        found = self.statement(line)
        if not isinstance(found, n.Start):
            raise SyntaxProblem(
                'the top level starts an event, as grinder.refill.start(50 g); a change of state belongs '
                'to a stage of an event',
                line.number,
                0,
            )
        return found

    def scenario(self, line):
        """`scenario "Title"` or `variant "Title"`, with the scenario's lines under it (`HEADER`)."""
        cursor = Cursor(line)
        word = cursor.take().value
        title = cursor.text(f'{word} "Title"')
        cursor.end(f'{word} "Title"; its other lines go under it')
        found = {}
        for child in line.under:
            sub = Cursor(child)
            key = sub.name(f'the lines under the {word} line are {", ".join(HEADER)}')
            if key not in HEADER:
                sub.fail(f'the {word} line has no line {key}; its lines are {", ".join(HEADER)}', child.first)
            if key in found:
                sub.fail(f'{key} is written twice', child.first)
            if key in ('summary', 'scope', 'library'):
                found[key] = sub.text(f'{key} is a text in quotes')
            elif key == 'timescales':
                items = [self.expression(sub)]
                while sub.at_op(','):
                    sub.i += 1
                    items.append(self.expression(sub))
                found[key] = tuple(items)
            else:
                if sub.done():
                    sub.fail(f'{key} is a time: {key} 30 days')
                found[key] = self.expression(sub)
            sub.end()
            self.no_body(child, key)
        return n.Scenario(word, title, **found, **self.at(line))

    def use(self, line):
        cursor = Cursor(line)
        cursor.take()
        parts = [cursor.name('use names a module: use file, or use folder.file')]
        while cursor.at_op('.'):
            cursor.i += 1
            parts.append(cursor.name('use names a module by its folders and its file: use folder.file'))
        cursor.end('use names one module: use file, or use folder.file')
        self.no_body(line, 'a use')
        return n.Use('.'.join(parts), **self.at(line))

    def record(self, line):
        """`record name: kind "explanation"`, with its relations and its claims under it."""
        cursor = Cursor(line)
        cursor.take()
        name = cursor.name('a record is `record name: kind "explanation"`')
        cursor.op(':', f'record {name}: kind "explanation"')
        kind = cursor.peek()
        if kind is None or not kind.is_name(*RECORD_KINDS):
            cursor.fail(f'the kind of a record is {", ".join(RECORD_KINDS[:-1])} or {RECORD_KINDS[-1]}')
        cursor.i += 1
        if cursor.peek() is not None and cursor.peek().kind != 'text':
            cursor.fail('a record names what it rests on under it (`assumption A-ID`), not after its kind')
        text = cursor.text(
            f'a record has its explanation in quotes: record {name}: {kind.value} "explanation"'
        )
        cursor.end()
        relations, claims = self.record_lines(line)
        return n.Record(name, kind.value, text, relations, claims, **self.at(line))

    # ---- entities and their members --------------------------------------------------------------

    def entity(self, line):
        """`name:` (an entity) or `Name:` (a template), with its members."""
        cursor = Cursor(line)
        name = cursor.name('an entity is `name:` with its members under it')
        cursor.i += 1
        cites = cursor.cites()
        cursor.end()
        text, title, role, evidence, rest = None, None, None, [], []
        for child in line.under:
            first, second = child.first, child.tokens[1] if len(child.tokens) > 1 else None
            if first.kind == 'at':
                evidence += self.evidence_row(child)
            elif first.kind == 'text':
                if text is not None:
                    raise SyntaxProblem('an entity has one text: its description', child.number, 0, 'layout')
                text = self.text_line(child)
            elif first.is_name('title') and second is not None and second.kind == 'text':
                sub = Cursor(child)
                sub.i = 1
                title = sub.text('title is a text in quotes')
                sub.end()
                self.no_body(child, 'a title')
            elif (
                first.is_name('role')
                and second is not None
                and second.kind == 'name'
                and len(child.tokens) == 2
            ):
                role = second.value
                self.no_body(child, 'a role')
            else:
                rest.append(child)
        members = self.members(rest)
        return n.Entity(
            name, members, title, role, cites=cites, text=text, evidence=tuple(evidence), **self.at(line)
        )

    def members(self, found):
        out = []
        for line in found:
            cursor = Cursor(line)
            first, second = cursor.peek(), cursor.peek(1)
            if first.kind == 'text':
                cursor.fail('a text stands under the line that it describes', code='layout')
            if first.kind != 'name':
                cursor.fail(MEMBER)
            word = first.value
            if word == 'flow':
                out.append(self.flow(line))
            elif word == 'assert':
                out.append(self.assertion(line))
            elif word == 'status' and second is not None and second.kind == 'name':
                out.append(self.status(line))
            elif word == 'sees' and second is not None and second.kind == 'name':
                cursor.i = 1
                path = Expressions(cursor).postfix()
                cursor.end('sees names one value to show: sees depot.spares')
                self.no_body(line, 'sees')
                out.append(n.Sees(path, **self.at(line)))
            elif word in ('after', 'until', 'when', 'reset', 'switch', 'move', 'if'):
                cursor.fail(f'{word} belongs to the body of an event: name = event(...):')
            elif word == 'record':
                cursor.fail('a record is declared at the top level, and a line cites it with @name')
            elif word == 'event':
                cursor.fail('an event is a value: name = event(parameters): with its steps under it')
            elif word in RETIRED and second is not None and second.kind == 'name':
                cursor.fail(f'{word} is no longer a word of the language: {RETIRED[word]}', code='retired')
            elif word in ('readonly', 'input'):
                out.append(self.declaration(line, 'entity'))
            elif word in RESERVED and word != 'this':
                cursor.fail(f'{word} is a word of the language and names nothing else', code='reserved')
            elif second is not None and second.is_op('.'):
                out.append(self.property(line))
            elif second is not None and second.is_op(':', '='):
                out.append(self.declaration(line, 'entity'))
            elif second is not None and second.is_op('+=', '-='):
                cursor.fail(
                    'an entity declares its values: a change (+=, -=) belongs to a stage of an event', second
                )
            else:
                cursor.fail(MEMBER)
        return tuple(out)

    def table(self, line, cursor, declared):
        name = line.first.value
        if not isinstance(declared, n.NamedType) or small(declared.name):
            cursor.fail(
                'a table names its template, which starts with a capital letter: sites: Place from "places.csv"'
            )
        cursor.i += 1
        file = cursor.text(f'{name}: {declared.name} from "file.csv" names the file of its table, in quotes')
        cites = cursor.cites()
        cursor.end()
        text, evidence = self.described(line)
        return n.Table(name, declared.name, file, cites=cites, text=text, evidence=evidence, **self.at(line))

    # ---- values ----------------------------------------------------------------------------------

    def declaration(self, line, owner):
        """`[readonly | input] name[: type] [= value] [in [lo, hi]] [scale s] [@record]`. After `=`,
        `event(...)` and `solver:` open the body of an event or of a solver."""
        cursor = Cursor(line)
        modifier = ''
        if cursor.at_name('readonly', 'input'):
            modifier = cursor.take().value
            if cursor.at_name('readonly', 'input'):
                cursor.fail('a value is readonly or an input, not both: an input is fixed during a run')
        if modifier == 'input' and owner == 'event':
            cursor.fail(
                'an event has no input: its parameters are in event(...), and an input belongs to an entity'
            )
        token = cursor.peek()
        name = cursor.name('a value is declared as name = value, or name: type = value')
        if not small(name):
            cursor.fail(VALUE_NAME, token, 'name')
        declared = value = range_ = scale = None
        if cursor.at_op(':'):
            cursor.i += 1
            declared = self.type(cursor)
        if cursor.at_op('='):
            cursor.i += 1
            if cursor.at_name('event') and cursor.peek(1) is not None and cursor.peek(1).is_op('('):
                return self.event(line, cursor, modifier, name, declared, owner)
            if cursor.at_name('solver') and cursor.peek(1) is not None and cursor.peek(1).is_op(':'):
                return self.solver(line, cursor, modifier, name, declared, owner)
            value = self.expression(cursor, bare_in=False)
        elif declared is None:
            cursor.fail(f'{name} needs a type or a value: {name}: type, or {name} = value')
        if cursor.at_name('in'):
            range_ = self.range_of(cursor)
        if cursor.at_name('scale'):
            cursor.i += 1
            scale = self.expression(cursor, bare_in=False)
        cites = cursor.cites()
        cursor.end()
        found = {'range': range_, 'scale': scale, 'row': False}
        properties = []

        def under(child):
            sub = Cursor(child)
            if sub.at_name('in'):
                if found['range'] is not None:
                    sub.fail('a value has one range')
                found['range'], found['row'] = self.range_of(sub), True
                sub.end()
                self.no_body(child, 'a range')
                return True
            if sub.at_name('scale'):
                if found['scale'] is not None:
                    sub.fail('a value has one scale')
                sub.i += 1
                found['scale'] = self.expression(sub, bare_in=False)
                sub.end()
                self.no_body(child, 'a scale')
                return True
            first, second = sub.peek(), sub.peek(1)
            if first.kind == 'name' and second is not None and second.is_op('.', '='):
                properties.append(self.property(child))
                return True
            return False

        text, evidence = self.described(line, under)
        return n.Declaration(
            modifier,
            name,
            declared,
            value,
            found['range'],
            found['scale'],
            tuple(properties),
            range_row=found['row'],
            cites=cites,
            text=text,
            evidence=evidence,
            **self.at(line),
        )

    def property(self, line):
        """`path = expression`: a property of the line above it, or of a value by its full path."""
        cursor = Cursor(line)
        path = self.path(cursor, 'a property is named by its path: outflow.capacity = 10 L/h')
        if cursor.at_op('+=', '-='):
            cursor.fail(
                'a change (+=, -=) belongs to a stage of an event: here a property gets its starting value'
            )
        cursor.op('=', f'{".".join(path)} = value')
        value = self.expression(cursor, bare_in=False)
        if cursor.at_name('in'):
            cursor.fail(
                'a range belongs to the declaration of a value. ' + MEMBERSHIP[0].upper() + MEMBERSHIP[1:],
                code='in',
            )
        cites = cursor.cites()
        cursor.end()
        text, evidence = self.described(line)
        return n.Property(path, value, cites=cites, text=text, evidence=evidence, **self.at(line))

    # ---- flows -----------------------------------------------------------------------------------

    def flow(self, line, leg=False):
        cursor = Cursor(line)
        cursor.take()
        token = cursor.peek()
        name = cursor.name('a flow is `flow name: source -> sink`')
        if not small(name):
            cursor.fail(VALUE_NAME, token, 'name')
        cursor.op(':', f'flow {name}: source -> sink')
        if cursor.done() or cursor.peek().kind == 'at':
            if leg:
                cursor.fail('a leg of a flow has its two ends: flow name: source -> sink')
            cites = cursor.cites()
            cursor.end()
            legs = []

            def under(child):
                if child.first.is_name('flow'):
                    legs.append(self.flow(child, leg=True))
                    return True
                if len(child.tokens) > 1 and child.first.kind == 'name' and child.tokens[1].is_op('=', '.'):
                    raise SyntaxProblem(
                        'a flow with legs takes no property: give each leg its request and capacity',
                        child.number,
                        child.first.column,
                        'layout',
                    )
                return False

            text, evidence = self.described(line, under)
            if not legs:
                raise SyntaxProblem(
                    f'flow {name}: has its two ends on its line, or a leg on each line under it',
                    line.number,
                    0,
                    'layout',
                )
            return n.Flow(
                name, '', legs=tuple(legs), cites=cites, text=text, evidence=evidence, **self.at(line)
            )
        end_message = 'an end of a flow is the path of a stored quantity, SOURCE or SINK'
        source = self.path(cursor, end_message)
        arrow = cursor.peek()
        if arrow is None or not arrow.is_op('->', '<->'):
            cursor.fail('the two ends of a flow are joined by -> (one direction) or <-> (a reversible route)')
        cursor.i += 1
        sink = self.path(cursor, end_message)
        ends = (source, sink)
        if arrow.value == '<->':
            if leg:
                cursor.fail('a leg of a flow goes one way: source -> sink', arrow)
            if ('SOURCE',) in ends or ('SINK',) in ends:
                cursor.fail(
                    'a reversible route joins two stocks: SOURCE and SINK stand at an end of a -> flow',
                    arrow,
                    'route_end',
                )
        elif source == ('SINK',) or sink == ('SOURCE',):
            cursor.fail('SOURCE stands on the left of -> and SINK on the right', arrow)
        cites = cursor.cites()
        cursor.end('the line of a flow holds its two ends: its request and its capacity go on lines under it')
        properties = []

        def under(child):
            if child.first.is_name('flow'):
                raise SyntaxProblem(
                    'a flow has its two ends, or legs under it, not both',
                    child.number,
                    child.first.column,
                    'layout',
                )
            if len(child.tokens) > 1 and child.first.kind == 'name' and child.tokens[1].is_op('.', '='):
                properties.append(self.property(child))
                return True
            return False

        text, evidence = self.described(line, under)
        return n.Flow(
            name,
            arrow.value,
            source,
            sink,
            tuple(properties),
            cites=cites,
            text=text,
            evidence=evidence,
            **self.at(line),
        )

    # ---- events ----------------------------------------------------------------------------------

    def event(self, line, cursor, modifier, name, declared, owner):
        if declared is not None:
            cursor.fail(
                'an event writes the types of its parameters inside event(...), and takes no type itself'
            )
        if modifier == 'input':
            cursor.fail('an event is no input: it is read-only by default')
        if owner in ('top', 'event'):
            cursor.fail('an event belongs to an entity or to a template: declare it under one')
        cursor.take()
        cursor.op('(', 'an event lists its parameters, also when it has none: event():')
        params = []
        while not cursor.at_op(')'):
            token = cursor.peek()
            param = cursor.name('a parameter is name: type')
            if not small(param):
                cursor.fail(VALUE_NAME, token, 'name')
            if param in [found.name for found in params]:
                cursor.fail(f'the parameter {param} is written twice', token)
            cursor.op(':', f'a parameter declares its type: {param}: type')
            kind = self.type(cursor)
            range_ = self.range_of(cursor) if cursor.at_name('in') else None
            if cursor.at_op('='):
                cursor.fail('a parameter has no default value: each start gives every argument')
            params.append(n.Param(param, kind, range_, **_place(token)))
            if cursor.at_op(','):
                cursor.i += 1
                continue
            if not cursor.at_op(')'):
                cursor.fail('the parameters of an event are separated by commas and end with )')
        cursor.i += 1
        cursor.op(':', 'the line of an event ends with a colon, and its body is under it')
        cites = cursor.cites()
        cursor.end()
        text, evidence, locals_, triggers, steps = None, [], [], [], []
        for child in line.under:
            sub = Cursor(child)
            first, second = sub.peek(), sub.peek(1)
            if first.kind == 'at':
                evidence += self.evidence_row(child)
                continue
            if first.kind == 'text':
                if text is not None:
                    raise SyntaxProblem('an event has one text: its card', child.number, 0, 'layout')
                text = self.text_line(child)
                continue
            if first.kind != 'name':
                sub.fail(EVENT)
            word = first.value
            if word == 'when':
                triggers.append(self.trigger(child, name))
            elif word == 'after':
                steps.append(self.stage(child))
            elif word == 'until':
                steps.append(self.gate(child))
            elif word == 'flow':
                self.early(steps, sub, 'a flow')
                locals_.append(self.flow(child))
            elif word == 'status' and second is not None and second.kind == 'name':
                sub.fail(
                    'a status display belongs to an entity; an event declares a field for its progress: '
                    'status: enum[WEIGHING, ADDED] = WEIGHING'
                )
            elif word in ('switch', 'move', 'assert', 'if'):
                sub.fail(f'{word} is an action: it belongs inside a stage (`after 0 h:`)')
            elif word == 'reset':
                sub.fail('reset is the last line of a trigger (`when C:`)')
            elif word == 'at' and second is not None and second.kind in ('name', 'number'):
                sub.fail('there is no `at T:` step in this version: a trigger on t >= T says the same')
            elif word == 'this' or (second is not None and second.is_op('.', '+=', '-=')):
                sub.fail('an action belongs inside a stage of the event: after 0 h:')
            elif word == 'readonly' or (second is not None and second.is_op(':', '=')):
                self.early(steps, sub, 'a local value', second)
                locals_.append(self.declaration(child, 'event'))
            elif word == 'input':
                sub.fail(
                    'an event has no input: its parameters are in event(...), and an input belongs to an entity'
                )
            else:
                sub.fail(EVENT)
        return n.Event(
            modifier,
            name,
            tuple(params),
            tuple(locals_),
            tuple(triggers),
            tuple(steps),
            cites=cites,
            text=text,
            evidence=tuple(evidence),
            **self.at(line),
        )

    @staticmethod
    def early(steps, cursor, what, second=None):
        if steps:
            hint = ''
            if second is not None and second.is_op('='):
                hint = '. An assignment goes inside a stage: is this line indented too little?'
            cursor.fail(f'{what} of an event is declared at its start, before its timing steps{hint}')

    def trigger(self, line, event):
        cursor = Cursor(line)
        cursor.take()
        test = self.expression(cursor)
        cursor.op(':', 'a trigger is `when C:` with its firing body under it')
        cites = cursor.cites()
        cursor.end()
        text, evidence, captures, starts, reset = None, [], [], [], None
        for child in self.body(line, 'a trigger'):
            sub = Cursor(child)
            first, second = sub.peek(), sub.peek(1)
            if first.kind == 'at':
                evidence += self.evidence_row(child)
                continue
            if first.kind == 'text':
                text = self.text_line(child)
                continue
            if reset is not None:
                sub.fail('reset is the last line of a trigger, and a trigger has one')
            if first.is_name('reset'):
                sub.i += 1
                if not sub.at_name('when', 'after'):
                    sub.fail('a trigger is armed again by `reset when C` or `reset after D`')
                kind = sub.take().value
                reset = n.Reset(kind, self.expression(sub), **self.at(child))
                sub.end()
                self.no_body(child, 'a reset')
                continue
            if first.kind == 'name' and second is not None and second.is_op('='):
                if starts:
                    sub.fail('a trigger captures its values before it starts its event')
                capture = sub.name('a capture is name = value')
                if not small(capture):
                    sub.fail(VALUE_NAME, first, 'name')
                sub.i += 1
                value = self.expression(sub, bare_in=False)
                sub.end()
                self.no_body(child, 'a capture')
                captures.append(n.Capture(capture, value, **self.at(child)))
                continue
            found = self.statement(child)
            if not isinstance(found, n.Start):
                raise SyntaxProblem(
                    'the body of a trigger captures values (`name = value`), starts its event (`this.event.start(...)`) '
                    'and ends with its reset; a change of state belongs to a stage of the event',
                    child.number,
                    first.column,
                )
            target = found.call.base
            if not (isinstance(target, n.Member) and target.name == event and target.base == n.Name('this')):
                raise SyntaxProblem(
                    f'a trigger starts its own event: this.{event}.start(...)', child.number, first.column
                )
            starts.append(found)
        if not starts:
            raise SyntaxProblem(
                f'a trigger starts its event: this.{event}.start(...)', line.number, 0, 'layout'
            )
        return n.Trigger(
            test,
            tuple(captures),
            tuple(starts),
            reset,
            cites=cites,
            text=text,
            evidence=tuple(evidence),
            **self.at(line),
        )

    def stage(self, line):
        cursor = Cursor(line)
        cursor.take()
        delay = self.expression(cursor)
        guard = None
        if cursor.at_name('when'):
            cursor.i += 1
            guard = self.expression(cursor)
        if cursor.done() and guard is None and not line.under:
            return n.Stage(delay, wait=True, **self.at(line))
        cursor.op(
            ':', 'a stage is `after D:` or `after D when C:` with its actions under it; `after D` alone waits'
        )
        cites = cursor.cites()
        cursor.end()
        text, evidence, rest = None, [], []
        for child in self.body(line, 'a stage'):
            if child.first.kind == 'at' and not rest:
                evidence += self.evidence_row(child)
                continue
            if child.first.kind == 'text' and text is None and not rest:
                text = self.text_line(child)
                continue
            rest.append(child)
        if not rest:
            raise SyntaxProblem(
                'a stage has its actions under it; `after D` alone waits', line.number, 0, 'layout'
            )
        return n.Stage(
            delay,
            guard,
            self.statements(rest),
            cites=cites,
            text=text,
            evidence=tuple(evidence),
            **self.at(line),
        )

    def gate(self, line):
        cursor = Cursor(line)
        cursor.take()
        test = self.expression(cursor)
        if cursor.at_op(':'):
            cursor.fail('until C is a gate with no body: the next step goes on when C holds')
        cursor.end()
        self.no_body(line, 'a gate (`until C`)')
        return n.Gate(test, **self.at(line))

    # ---- actions ---------------------------------------------------------------------------------

    def statements(self, found):
        out = []
        for line in found:
            cursor = Cursor(line)
            if cursor.at_name('else') and cursor.peek(1) is not None and cursor.peek(1).is_op(':'):
                previous = out[-1] if out else None
                if not isinstance(previous, n.If) or previous.orelse is not None:
                    cursor.fail('else: follows the body of an if, at the level of the if')
                cursor.i += 2
                cursor.end('else: has its actions under it')
                out[-1] = n.If(
                    previous.test,
                    previous.then,
                    self.statements(self.body(line, 'else:')),
                    line=previous.line,
                    column=previous.column,
                    lead=previous.lead,
                    tail=previous.tail,
                )
                continue
            out.append(self.statement(line))
        return tuple(out)

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
        if word == 'if':
            cursor.i += 1
            test = self.expression(cursor)
            cursor.op(':', 'a branch is `if C:` with its actions under it, and `else:` with its own')
            cursor.end()
            return n.If(test, self.statements(self.body(line, 'an if')), **self.at(line))
        if word in ('elif', 'else'):
            cursor.fail('a branch has one condition: write `else:` with an `if` inside it')
        if word in ('after', 'until', 'when'):
            cursor.fail(
                'a timing step stands at the level of the event, outside the stages and their branches'
            )
        if word == 'reset':
            cursor.fail('reset is the last line of a trigger (`when C:`)')
        if word in ('flow', 'readonly', 'input', 'assert', 'record'):
            cursor.fail(
                f'{word} is a declaration: it stands at the start of the event or under an entity, not in a stage'
            )
        if second is not None and second.is_op(':'):
            cursor.fail(
                'a stage declares no value: declare a local at the start of the event, before its timing steps, '
                'and assign to it here'
            )
        reader = Expressions(cursor, statement=True)
        head = reader.postfix()
        if cursor.at_op('=', '+=', '-='):
            op = cursor.take()
            if not isinstance(head, (n.Name, n.Member)) or head in (n.Name('this'), n.Name('t')):
                cursor.fail('the target of an assignment is a name or a path: this.beans += amount', first)
            value = self.expression(cursor, bare_in=False)
            if cursor.at_name('in'):
                cursor.fail(MEMBERSHIP, code='in')
            cites = cursor.cites()
            cursor.end()
            self.no_body(line, 'an assignment')
            return n.Assign(head, op.value, value, cites, **self.at(line))
        if reader.started is head:
            cursor.end('nothing follows .start(...): it starts an occurrence and gives no value')
            self.no_body(line, 'a start')
            return n.Start(head, **self.at(line))
        cursor.fail(ACTION, first if cursor.done() else None)

    def switch(self, line):
        cursor = Cursor(line)
        cursor.take()
        selector = self.expression(cursor)
        cursor.op(':', 'a switch is `switch E:` with one case on each line under it')
        cursor.end()
        cases, orelse = [], None
        for child in self.body(line, 'a switch'):
            sub = Cursor(child)
            first = sub.peek()
            if orelse is not None:
                sub.fail('else is the last case of a switch')
            if first.is_name('else') and sub.peek(1) is not None and sub.peek(1).is_op(':'):
                sub.i += 2
                sub.end('else: has its actions under it')
                orelse = self.statements(self.body(child, 'else:'))
                continue
            if first.kind != 'name' or small(first.value) or first.value in RESERVED:
                sub.fail(
                    'a case of a switch is a member of the enum (`REPAIR:`, `SEND when C:`) or `else:`', first
                )
            if first.value in [case.member for case in cases]:
                sub.fail(f'the case {first.value} is written twice', first)
            sub.i += 1
            guard = None
            if sub.at_name('when'):
                sub.i += 1
                guard = self.expression(sub)
            sub.op(':', 'a case is a member of the enum and a colon, with its actions under it: REPAIR:')
            cites = sub.cites()
            sub.end('a case has one member, an optional guard, and its actions under it')
            text, evidence, rest = None, [], []
            for item in self.body(child, 'a case'):
                if item.first.kind == 'at' and not rest:
                    evidence += self.evidence_row(item)
                elif item.first.kind == 'text' and text is None and not rest:
                    text = self.text_line(item)
                else:
                    rest.append(item)
            if not rest:
                raise SyntaxProblem('a case has its actions under it', child.number, 0, 'layout')
            cases.append(
                n.Case(
                    first.value,
                    guard,
                    self.statements(rest),
                    cites=cites,
                    text=text,
                    evidence=tuple(evidence),
                    **self.at(child),
                )
            )
        if not cases:
            raise SyntaxProblem('a switch has a case for at least one member', line.number, 0, 'layout')
        return n.Switch(selector, tuple(cases), orelse, **self.at(line))

    def move(self, line):
        cursor = Cursor(line)
        cursor.take()
        if cursor.at_op('('):
            depth = 0
            for token in cursor.tokens[cursor.i :]:
                if token.kind == 'op' and token.value in lex.OPENS:
                    depth += 1
                elif token.kind == 'op' and token.value in lex.CLOSES:
                    depth -= 1
                    if depth == 0:
                        break
                elif depth == 1 and token.is_op(','):
                    cursor.fail('a move has one form: move amount from source to destination', token)
        amount = self.expression(cursor)
        if not cursor.at_name('from'):
            cursor.fail('a move is `move amount from source to destination`')
        cursor.i += 1
        source = Expressions(cursor).postfix()
        if not cursor.at_name('to'):
            cursor.fail('a move is `move amount from source to destination`')
        cursor.i += 1
        destination = Expressions(cursor).postfix()
        cites = cursor.cites()
        cursor.end()
        self.no_body(line, 'a move')
        return n.Move(amount, source, destination, cites, **self.at(line))

    # ---- solvers ---------------------------------------------------------------------------------

    def solver(self, line, cursor, modifier, name, declared, owner):
        if declared is not None:
            cursor.fail('a solver takes no type: its unknowns declare theirs under solve_for')
        if modifier == 'input':
            cursor.fail('a solver is no input')
        if owner in ('top', 'event'):
            cursor.fail('a solver belongs to an entity or to a template: declare it under one')
        cursor.i += 2
        cites = cursor.cites()
        cursor.end()
        sections = {}

        def section(child):
            sub = Cursor(child)
            first, second = sub.peek(), sub.peek(1)
            if not (
                first.kind == 'name' and first.value in SECTIONS and second is not None and second.is_op(':')
            ):
                return False
            if first.value in sections:
                sub.fail(f'{first.value}: is written twice')
            sub.i += 2
            sub.end()
            sections[first.value] = tuple(
                getattr(self, first.value)(entry) for entry in self.body(child, f'{first.value}:')
            )
            return True

        text, evidence = self.described(line, section)
        if 'solve_for' not in sections:
            raise SyntaxProblem(
                'a solver names what it determines under solve_for: (its sections are inputs:, solve_for:, '
                'constraints: and objective:)',
                line.number,
                0,
                'layout',
            )
        return n.Solver(
            modifier, name, **sections, cites=cites, text=text, evidence=evidence, **self.at(line)
        )

    def inputs(self, line):
        cursor = Cursor(line)
        token = cursor.peek()
        name = cursor.name('an input of a solver is name = value')
        if not small(name):
            cursor.fail(VALUE_NAME, token, 'name')
        cursor.op('=', f'an input of a solver binds a name: {name} = value')
        value = self.expression(cursor, bare_in=False)
        if cursor.at_name('in'):
            cursor.fail('an input of a solver keeps the range of its source: it declares none')
        cursor.end()
        self.no_body(line, 'an input of a solver')
        return n.Binding(name, value, **self.at(line))

    def solve_for(self, line):
        cursor = Cursor(line)
        first, second = cursor.peek(), cursor.peek(1)
        if first.kind == 'name' and second is not None and second.is_op(':'):
            name = cursor.name('a new unknown is name: type in [lo, hi]')
            if not small(name):
                cursor.fail(VALUE_NAME, first, 'name')
            cursor.i += 1
            kind = self.type(cursor)
            value = range_ = scale = None
            if cursor.at_op('='):
                cursor.i += 1
                value = self.expression(cursor, bare_in=False)
            if cursor.at_name('in'):
                range_ = self.range_of(cursor)
            if cursor.at_name('scale'):
                cursor.i += 1
                scale = self.expression(cursor, bare_in=False)
            cursor.end()
            self.no_body(line, 'an unknown')
            return n.Unknown(name, kind, value, range_, scale, **self.at(line))
        if first.kind == 'name' and second is not None and second.is_op('='):
            cursor.fail(
                'a new unknown declares its type: name: type in [lo, hi]. An input goes under inputs:'
            )
        found = Expressions(cursor).postfix()
        if not isinstance(found, (n.Name, n.Member)):
            cursor.fail('an entry of solve_for is the path of a field, or a new unknown (name: type)', first)
        cursor.end('an entry of solve_for is the path of a field, or a new unknown (name: type)')
        self.no_body(line, 'an entry of solve_for')
        return found

    def constraints(self, line):
        cursor = Cursor(line)
        found = self.expression(cursor)
        cursor.end()
        self.no_body(line, 'a constraint')
        return found

    def objective(self, line):
        cursor = Cursor(line)
        first = cursor.peek()
        if not (
            first.is_name('minimize', 'maximize') and cursor.peek(1) is not None and cursor.peek(1).is_op('(')
        ):
            cursor.fail('a line of objective: is minimize(expression) or maximize(expression)')
        cursor.i += 2
        value = self.expression(cursor)
        cursor.op(')', f'{first.value}(expression) closes with )')
        cursor.end()
        self.no_body(line, 'an objective')
        return n.Objective(first.value, value, **self.at(line))

    # ---- status, assertions, changes, options, runs and notes ----------------------------------

    def status(self, line):
        cursor = Cursor(line)
        cursor.take()
        rating = cursor.take()
        if rating.value not in RATINGS:
            cursor.fail(f'a status case rates {", ".join(RATINGS[:-1])} or {RATINGS[-1]}', rating)
        test = None
        if cursor.at_name('when'):
            cursor.i += 1
            test = self.expression(cursor)
        cites = cursor.cites()
        cursor.end('a status case is `status rating` or `status rating when C`, with its text under it')
        text, evidence = self.described(line)
        return n.Status(rating.value, test, cites=cites, text=text, evidence=evidence, **self.at(line))

    def assertion(self, line):
        cursor = Cursor(line)
        cursor.take()
        if cursor.at_name('initially'):
            following = cursor.peek(1)
            if following is not None and following.kind != 'op':
                cursor.fail(
                    'there is no `assert initially` in this version: assert over the inputs that give the start'
                )
        test = self.expression(cursor)
        if cursor.at_name('within'):
            cursor.fail(
                'there is no `within`: a tolerance is a closed interval, assert x in [lo, hi]', code='retired'
            )
        cites = cursor.cites()
        cursor.end()
        text, evidence = self.described(line)
        return n.Assert(test, cites=cites, text=text, evidence=evidence, **self.at(line))

    def change(self, line):
        cursor = Cursor(line)
        cursor.take()
        name = cursor.name('change names an entity of an earlier file: change name:')
        cursor.op(':', f'change {name}: with its lines under it')
        cites = cursor.cites()
        cursor.end()
        rest, text, evidence = [], None, []
        for child in self.body(line, 'a change'):
            if child.first.kind == 'at':
                evidence += self.evidence_row(child)
            elif child.first.kind == 'text':
                text = self.text_line(child)
            else:
                rest.append(child)
        return n.Change(
            name, self.members(rest), cites=cites, text=text, evidence=tuple(evidence), **self.at(line)
        )

    def options(self, line):
        cursor = Cursor(line)
        cursor.take()
        group = cursor.text('options "Group": with its options under it')
        cursor.op(':', 'options "Group": with its options under it')
        cursor.end()
        options = []
        for child in self.body(line, 'options'):
            sub = Cursor(child)
            name = sub.text('an option is "Name": with its settings under it')
            sub.op(':', 'an option is "Name": with its settings under it')
            sub.end()
            settings = tuple(self.property(item) for item in self.body(child, 'an option'))
            options.append(n.Option(name, settings, **self.at(child)))
        return n.Options(group, tuple(options), **self.at(line))

    def runs(self, line):
        runs = []
        for child in self.body(line, 'runs:'):
            sub = Cursor(child)
            name = sub.name('a run is name = "Option" + "Option"')
            sub.op('=', 'a run is name = "Option" + "Option"')
            options = [sub.text('a run names its options in quotes: "Option" + "Option"')]
            while sub.at_op('+'):
                sub.i += 1
                options.append(sub.text('a run names its options in quotes: "Option" + "Option"'))
            sub.end()
            self.no_body(child, 'a run')
            runs.append(n.RunLine(name, tuple(options), **self.at(child)))
        return n.Runs(tuple(runs), **self.at(line))

    def notes_block(self, line):
        return n.Notes(self.notes(self.body(line, 'notes:')), **self.at(line))

    def notes(self, found):
        out = []
        for child in found:
            cursor = Cursor(child)
            key = cursor.word('a note is `key: value`')
            cursor.op(':', 'a note is `key: value`')
            value = None
            if not cursor.done() and cursor.peek().kind != 'at':
                value = self.note_value(cursor)
            cites = cursor.cites()
            cursor.end()
            evidence = [
                item for row in child.under if row.first.kind == 'at' for item in self.evidence_row(row)
            ]
            under = self.notes([row for row in child.under if row.first.kind != 'at'])
            out.append(n.Note(key, value, cites, under, tuple(evidence), **self.at(child)))
        return tuple(out)

    def note_value(self, cursor):
        token = cursor.peek()
        if token.kind == 'text':
            return n.Text(cursor.take().value)
        if token.is_op('['):
            cursor.i += 1
            values = []
            while not cursor.at_op(']'):
                values.append(self.note_value(cursor))
                if cursor.at_op(','):
                    cursor.i += 1
            cursor.op(']', 'a list closes with ]')
            return tuple(values)
        if token.kind == 'number' and (
            cursor.peek(1) is None or cursor.peek(1).space or cursor.peek(1).is_op(',', ']')
        ):
            if cursor.peek(1) is not None and cursor.peek(1).kind == 'name' and cursor.peek(1).space:
                cursor.fail(
                    'a number of a note has no unit: the notes are no values of the model', cursor.peek(1)
                )
            written = cursor.take().value
            return n.Number(float(written) if any(ch in written for ch in '.eE') else int(written))
        return cursor.word('a note holds a text, a number, a word or a list')


def parse(text):
    """The tree of a model text (`nodes.File`). Raises `SyntaxProblem` at the first line that the
    language does not read."""
    return Parser(text).file()


def parse_expression(text, bare_in=True):
    """The tree of one expression written on its own."""
    found = [line for line in lex.lines(text, alone=True) if line.kind == 'line']
    if len(found) != 1:
        raise SyntaxProblem('an expression is one line', 1)
    cursor = Cursor(found[0])
    node = Expressions(cursor).expression(bare_in)
    cursor.end('the expression ends here: what follows does not belong to it')
    return node
