"""A reader of exactly the LaTeX that `napkin.draw.notation.latex` writes, for the tests: it reads the
LaTeX back into the nodes of the notation, so that a test can compare the node and its value with
those of the expression. It shares no code with the writer. Its grammar is Python's: the precedences
and the associativity of Python's operators, with the forms of the writer's text (the module text of
`napkin.draw.notation`).

The symbols of a test are `x_{i}` for a value and `e_{i}` for an event: `values` maps each `x_{i}` to
its key, and `events` each `e_{i}` to the key of its event. Anything that the writer does
not write is an error (`LatexError`), so a text that the reader reads is a text of the subset: an
unescaped special character in a text, a stray brace, a token after the end, a membership
`x \\in \\left[lo, hi\\right]` in a chain of comparisons (Python reads `a < b in [c, d]` as a chain;
the writer puts a membership inside a comparison in parentheses).
"""

from __future__ import annotations

from napkin.draw.notation import (
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
)

# How a text writes the characters that LaTeX reads: each escape and the character that it stands for.
UNESCAPES = (
    (r'\textbackslash{}', '\\'),
    (r'\textasciitilde{}', '~'),
    (r'\textasciicircum{}', '^'),
    (r'\textless{}', '<'),
    (r'\textgreater{}', '>'),
    (r'\textbar{}', '|'),
    (r'\&', '&'),
    (r'\%', '%'),
    (r'\$', '$'),
    (r'\#', '#'),
    (r'\_', '_'),
    (r'\{', '{'),
    (r'\}', '}'),
)
# The characters that a text never writes as they are.
SPECIAL = set('\\&%$#_{}~^<>|')
COMPARE = {'<': '<', r'\le': '<=', '>': '>', r'\ge': '>=', '=': '==', r'\ne': '!='}
FUNCTIONS = {r'\min': 'min', r'\max': 'max', r'\exp': 'exp', r'\ln': 'ln'}
LIST_NAMES = ('any', 'all', 'count')


class LatexError(ValueError):
    pass


class Reader:
    def __init__(self, text, values, events):
        self.text, self.at = text, 0
        self.values, self.events = values, events

    # ---- characters and tokens -------------------------------------------------------------------

    def fail(self, message):
        raise LatexError(f'{message} at {self.at}: {self.text[self.at : self.at + 40]!r}')

    def space(self):
        while self.at < len(self.text) and self.text[self.at] == ' ':
            self.at += 1

    def token(self):
        """The next token, without reading it: a command (`\\name`, `\\left(`, `\\,`), a number, a
        letter or one character; '' at the end."""
        self.space()
        text, at = self.text, self.at
        if at >= len(text):
            return ''
        char = text[at]
        if char == '\\':
            end = at + 1
            while end < len(text) and text[end].isalpha():
                end += 1
            if end == at + 1:
                return text[at : at + 2]
            word = text[at:end]
            if word in (r'\left', r'\right'):
                return text[at : end + 1]
            return word
        if char.isdigit():
            end = at
            while end < len(text) and text[end].isdigit():
                end += 1
            if text[end : end + 1] == '.' and text[end + 1 : end + 2].isdigit():
                end += 1
                while end < len(text) and text[end].isdigit():
                    end += 1
            return text[at:end]
        return char

    def take(self, expected=None):
        found = self.token()
        if expected is not None and found != expected:
            self.fail(f'expected {expected!r}, found {found!r}')
        if not found:
            self.fail('the text ends')
        self.at += len(found)
        return found

    def taken(self, expected):
        if self.token() == expected:
            self.take()
            return True
        return False

    def raw(self, expected):
        """Characters that follow at once, with no space before them."""
        if not self.text.startswith(expected, self.at):
            self.fail(f'expected {expected!r}')
        self.at += len(expected)

    def braced_text(self):
        """The text in `{…}` after `\\text`, with its escapes read; a special character as it is is
        an error."""
        self.raw('{')
        out = []
        while True:
            if self.at >= len(self.text):
                self.fail('a text does not end')
            char = self.text[self.at]
            if char == '}':
                self.at += 1
                return ''.join(out)
            if char == '\\':
                for written, meant in UNESCAPES:
                    if self.text.startswith(written, self.at):
                        out.append(meant)
                        self.at += len(written)
                        break
                else:
                    self.fail('an unknown escape in a text')
                continue
            if char in SPECIAL:
                self.fail(f'{char!r} is not escaped in a text')
            out.append(char)
            self.at += 1

    def upright(self):
        """The text in `{…}` after `\\mathrm`: letters, digits, `/`, `.` and `\\text{…}`."""
        self.raw('{')
        out = []
        while True:
            if self.at >= len(self.text):
                self.fail('an upright text does not end')
            char = self.text[self.at]
            if char == '}':
                self.at += 1
                return ''.join(out)
            if self.text.startswith(r'\text{', self.at):
                self.at += len(r'\text')
                out.append(self.braced_text())
                continue
            if not (char.isascii() and (char.isalnum() or char in '/.')):
                self.fail(f'{char!r} in an upright text')
            out.append(char)
            self.at += 1

    def integer(self):
        """`{n}` or `{-n}`."""
        self.take('{')
        sign = '-' if self.taken('-') else ''
        digits = self.take()
        if not digits.isdigit():
            self.fail('expected a whole number')
        self.take('}')
        return sign + digits

    def symbol(self):
        """A symbol of a test, `x_{i}` or `e_{i}`, as written."""
        letter = self.take()
        if letter not in ('x', 'e'):
            self.fail(f'{letter!r} is not a symbol')
        self.raw('_{')
        digits = self.take()
        if not digits.isdigit():
            self.fail('a symbol has a number')
        self.take('}')
        return f'{letter}_{{{digits}}}'

    def value_key(self, written):
        if written not in self.values:
            self.fail(f'{written} is not the symbol of a value')
        return self.values[written]

    # ---- the grammar ---------------------------------------------------------------------------

    def expression(self):
        items = [self.conjunction()]
        while self.taken(r'\lor'):
            items.append(self.conjunction())
        return items[0] if len(items) == 1 else Logic('or', tuple(items))

    def conjunction(self):
        items = [self.negation()]
        while self.taken(r'\land'):
            items.append(self.negation())
        return items[0] if len(items) == 1 else Logic('and', tuple(items))

    def negation(self):
        if self.taken(r'\lnot'):
            return Not(self.negation())
        return self.comparison()

    def comparison(self):
        items, ops = [self.sum()], []
        while self.token() in COMPARE:
            ops.append(COMPARE[self.take()])
            items.append(self.sum())
        if not ops and self.taken(r'\in'):
            return self.membership(items[0])
        return items[0] if not ops else Cmp(tuple(ops), tuple(items))

    def membership(self, value):
        """The interval after `\\in`, `\\left[lo, hi\\right]`: the membership of `value`. A comparison
        after it is a token that no rule reads, so the text is refused."""
        self.take(r'\left[')
        low = self.expression()
        self.take(',')
        high = self.expression()
        self.take(r'\right]')
        return In(value, low, high)

    def sum(self):
        node = self.product()
        while self.token() in ('+', '-'):
            op = self.take()
            node = Op(op, node, self.product())
        return node

    def product(self):
        node = self.unary()
        while self.token() in (r'\cdot', '/'):
            op = '*' if self.take() == r'\cdot' else '/'
            node = Op(op, node, self.unary())
        return node

    def unary(self):
        if self.taken('-'):
            return Neg(self.unary())
        if self.taken('+'):
            return Pos(self.unary())
        return self.power()

    def power(self):
        if not self.taken('{'):
            return self.primary()
        base = self.expression()
        self.take('}')
        self.take('^')
        self.take('{')
        exponent = self.expression()
        self.take('}')
        return Op('**', base, exponent)

    def primary(self):
        found = self.token()
        if found[:1].isdigit():
            return self.number()
        if found == r'\left(':
            self.take()
            node = self.expression()
            self.take(r'\right)')
            return node
        if found == r'\left|':
            self.take()
            node = self.expression()
            self.take(r'\right|')
            return Call('abs', (node,))
        if found == r'\frac':
            return self.fraction()
        if found == r'\sqrt':
            self.take()
            self.take('{')
            node = self.expression()
            self.take('}')
            return Call('sqrt', (node,))
        if found in FUNCTIONS:
            self.take()
            args, keywords = self.arguments()
            return Call(FUNCTIONS[found], args, keywords)
        if found == r'\sum':
            self.take()
            return Sum('sum', self.members())
        if found == r'\operatorname':
            self.take()
            name = self.upright_name()
            if name in LIST_NAMES:
                return Sum(name, self.members())
            args, keywords = self.arguments()
            return Call(name, args, keywords)
        if found in (r'\tau', 'N'):
            return self.clock()
        if found == r'\begin':
            return self.cases()
        if found == r'\text':
            self.take()
            return Text(self.braced_text())
        if found == r'\mathrm':
            self.take()
            word = self.upright()
            if word not in ('true', 'false'):
                self.fail(f'{word!r} is not a yes/no word')
            return Text(word == 'true')
        if found == 't':
            self.take()
            return Time()
        if found == 'x':
            return Sym(self.value_key(self.symbol()))
        self.fail(f'{found!r} does not start a value')

    def number(self):
        mantissa = self.take()
        exponent = None
        if self.taken(r'\times'):
            self.take('10')
            self.take('^')
            exponent = self.integer()
        if exponent is not None:
            value = float(f'{mantissa}e{exponent}')
        else:
            value = float(mantissa) if '.' in mantissa else int(mantissa)
        if not self.text.startswith(r'\,', self.at):
            return Num(value)
        self.raw(r'\,')
        pieces = []
        while self.text.startswith(r'\mathrm', self.at):
            self.raw(r'\mathrm')
            pieces.append(self.upright())
            if self.text.startswith('^{', self.at):
                self.raw('^')
                pieces.append('^' + self.integer())
        if not pieces:
            self.fail('a thin space without a unit')
        return Num(value, ''.join(pieces))

    def upright_name(self):
        self.raw('{')
        end = self.text.index('}', self.at)
        name = self.text[self.at : end]
        if not name.isidentifier():
            self.fail(f'{name!r} is not the name of a function')
        self.at = end + 1
        return name

    def fraction(self):
        self.take(r'\frac')
        self.take('{')
        if self.text.startswith(r'\mathrm{d}', self.at):
            self.raw(r'\mathrm{d}')
            key = self.value_key(self.symbol())
            self.take('}')
            self.take('{')
            self.raw(r'\mathrm{d}t')
            self.take('}')
            return Deriv(key)
        top = self.expression()
        self.take('}')
        self.take('{')
        bottom = self.expression()
        self.take('}')
        return Op('/', top, bottom)

    def arguments(self):
        """`\\left( … \\right)`: the arguments, then the keyword arguments (`\\text{name}\\colon v`)."""
        self.take(r'\left(')
        args, keywords = [], []
        if self.taken(r'\right)'):
            return (), ()
        while True:
            start = self.at
            if self.token() == r'\text':
                self.take()
                name = self.braced_text()
                if self.taken(r'\colon'):
                    keywords.append((name, self.expression()))
                else:
                    self.at = start
                    name = None
            else:
                name = None
            if name is None:
                if keywords:
                    self.fail('an argument after a keyword argument')
                args.append(self.expression())
            if self.taken(r'\right)'):
                return tuple(args), tuple(keywords)
            self.take(',')

    def members(self):
        args, keywords = self.arguments()
        if keywords or not all(isinstance(arg, Sym) for arg in args):
            self.fail('the members of a list are symbols')
        return args

    def clock(self):
        form = self.take()
        self.raw('_{')
        written = self.symbol()
        self.take('}')
        if form == 'N':
            event = self.events.get(written)
            if event is None:
                self.fail(f'{written} is not the symbol of an event')
            return Count(event)
        if written in self.events:
            return Since(self.events[written])
        return Elapsed(self.value_key(written))

    def cases(self):
        self.take(r'\begin')
        self.raw('{cases}')
        pairs = []
        while True:
            value = self.expression()
            self.take('&')
            self.take(r'\text')
            word = self.braced_text()
            if word == 'otherwise':
                self.take(r'\end')
                self.raw('{cases}')
                return Cases(tuple(pairs), value)
            if word != 'if ':
                self.fail(f'{word!r} in a case')
            pairs.append((self.expression(), value))
            self.take('\\\\')

    def end(self, node):
        if self.token():
            self.fail('a token after the end')
        return node


def read(text, values, events=None):
    """The node of a LaTeX text of the subset."""
    reader = Reader(text, values, events or {})
    return reader.end(reader.expression())


def read_line(text, values, events=None):
    """The node of the LaTeX of a line of an event, `S \\leftarrow v`: an `Assign` with `=`."""
    reader = Reader(text, values, events or {})
    target = reader.value_key(reader.symbol())
    reader.take(r'\leftarrow')
    return reader.end(Assign(target, '=', reader.expression()))
