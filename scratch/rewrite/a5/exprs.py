"""Expressions for the migration scripts: one small tree, a printer in the language of now, and the
rewrite of an expression of the old language into it.

The tree is made of tuples:

    ('num', text, unit or None)        a number as written, with its unit: `12 h`, `0.3`
    ('name', 'a.b.c')                  a path: `this.water`, `Utility.instances.unserved`, `t`, `OPEN`
    ('text', 'words')                  a quoted text
    ('call', 'f', [args])              `f(a, b)`
    ('method', obj, 'm', [args])       `obj.m(a)`: `.draw()`, `.at(t)`, `.where(...)`, `.by(...)`
    ('attr', obj, 'x')                 `obj.x` where obj is not a plain path: `c.at(t).factor`
    ('un', op, x)                      op is `-`, `+` or `not`
    ('bin', op, a, b)                  op is `+ - * / **`
    ('cmp', op, a, b)                  op is `== != < <= > >=`
    ('bool', op, [values])             op is `and` or `or`
    ('if', test, then, otherwise)      `then if test else otherwise`
    ('in', x, low, high)               `x in [low, high]`
    ('coll', [items])                  `<a, b>`
    ('pair', key, value)               `KEY: value` inside a call: `categorical(OPEN: 1, WAIT: 0)`

`rewrite_old` reads an expression of the old language with the old compiler's own reader
(`napkin.model.language.expressions`) and gives it in this tree, with each name as the new language
writes it; `with_new_units` then spells each unit as the language of now does (D12). The tree keeps
the old spelling of a unit until then, because `numbers_of` gives the old file's numbers to the
check (`oldmodel.facts`), which reads the old spellings with the old registry of units.
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal, InvalidOperation

# ---- the printer ------------------------------------------------------------------------------------------

PRECEDENCE = {'if': 1, 'or': 2, 'and': 3, 'not': 4, 'cmp': 5, '+': 6, '-': 6, '*': 7, '/': 7, 'neg': 8, '**': 9}
ATOM = 10


def level(node):
    kind = node[0]
    if kind == 'if':
        return PRECEDENCE['if']
    if kind == 'bool':
        return PRECEDENCE[node[1]]
    if kind == 'un':
        return PRECEDENCE['not'] if node[1] == 'not' else PRECEDENCE['neg']
    if kind in ('cmp', 'in'):
        return PRECEDENCE['cmp']
    if kind == 'bin':
        return PRECEDENCE[node[1]]
    if kind == 'num' and node[1].startswith('-'):
        return PRECEDENCE['neg']
    return ATOM


def show(node, parent=0, right=False):
    """The text of a tree in the proposed notation, with the brackets that it needs."""
    kind = node[0]
    mine = level(node)
    if kind == 'num':
        text = node[1] if node[2] is None else f'{node[1]} {node[2]}'
        # A number with its unit is one value: `(2 h)` after a division keeps it together, and so
        # does a unit that is a product, wherever it stands in an operation (`(3 person * days)`).
        if node[2] is not None and parent > 0 and ((parent >= PRECEDENCE['*'] and right) or ' * ' in node[2]):
            return f'({text})'
    elif kind == 'name':
        text = node[1]
    elif kind == 'text':
        text = '"' + node[1].replace('\\', '\\\\').replace('"', '\\"') + '"'
    elif kind == 'call':
        text = f'{node[1]}({", ".join(show(arg) for arg in node[2])})'
    elif kind == 'method':
        text = f'{show(node[1], ATOM)}.{node[2]}({", ".join(show(arg) for arg in node[3])})'
    elif kind == 'attr':
        text = f'{show(node[1], ATOM)}.{node[2]}'
    elif kind == 'un':
        if node[1] == 'not':
            text = f'not {show(node[2], mine)}'
        else:
            text = f'{node[1]}{show(node[2], mine)}'
    elif kind == 'bin':
        op = node[1]
        if op == '**':
            text = f'{show(node[2], mine + 1)} ** {show(node[3], mine)}'
        else:
            text = f'{show(node[2], mine)} {op} {show(node[3], mine, right=True)}'
            # `a - (b - c)` and `a / (b * c)` keep their brackets: the right side binds one level tighter.
            if level(node[3]) == mine:
                text = f'{show(node[2], mine)} {op} ({show(node[3])})'
    elif kind == 'cmp':
        text = f'{show(node[2], mine + 1)} {node[1]} {show(node[3], mine + 1)}'
    elif kind == 'in':
        text = f'{show(node[1], mine + 1)} in [{show(node[2])}, {show(node[3])}]'
    elif kind == 'bool':
        text = f' {node[1]} '.join(show(value, mine + 1) for value in node[2])
    elif kind == 'if':
        text = f'{show(node[2], mine + 1)} if {show(node[1], mine + 1)} else {show(node[3], mine)}'
    elif kind == 'coll':
        text = '<' + ', '.join(show(item) for item in node[1]) + '>'
    elif kind == 'pair':
        text = f'{show(node[1])}: {show(node[2])}'
    else:
        raise ValueError(f'no text for {node!r}')
    return f'({text})' if mine < parent else text


def number_value(text):
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def canonical(node):
    """A tree with each number as its value, so that `100000.0` and `100000` are one number, and with
    a sign joined to its number."""
    kind = node[0]
    if kind == 'num':
        value = number_value(node[1])
        return ('num', str(value.normalize()) if value is not None else node[1], node[2])
    if kind == 'un' and node[1] == '-' and node[2][0] == 'num':
        inner = canonical(node[2])
        value = number_value(inner[1])
        return ('num', str((-value).normalize()) if value is not None else '-' + inner[1], inner[2])
    if kind in ('name', 'text', 'old'):
        return node
    if kind == 'call':
        return ('call', node[1], [canonical(arg) for arg in node[2]])
    if kind == 'method':
        return ('method', canonical(node[1]), node[2], [canonical(arg) for arg in node[3]])
    if kind == 'attr':
        return ('attr', canonical(node[1]), node[2])
    if kind == 'un':
        return ('un', node[1], canonical(node[2]))
    if kind in ('bin', 'cmp'):
        return (kind, node[1], canonical(node[2]), canonical(node[3]))
    if kind == 'bool':
        flat = []
        for value in node[2]:
            value = canonical(value)
            if value[0] == 'bool' and value[1] == node[1]:
                flat += value[2]
            else:
                flat.append(value)
        return ('bool', node[1], flat)
    if kind == 'if':
        return ('if', canonical(node[1]), canonical(node[2]), canonical(node[3]))
    if kind == 'in':
        return ('in', canonical(node[1]), canonical(node[2]), canonical(node[3]))
    if kind == 'coll':
        return ('coll', [canonical(item) for item in node[1]])
    if kind == 'pair':
        return ('pair', canonical(node[1]), canonical(node[2]))
    raise ValueError(f'no canonical form for {node!r}')


def walk(node):
    """Each node of a tree, the node itself first."""
    yield node
    kind = node[0]
    if kind == 'call':
        children = node[2]
    elif kind == 'method':
        children = [node[1], *node[3]]
    elif kind == 'attr':
        children = [node[1]]
    elif kind == 'un':
        children = [node[2]]
    elif kind in ('bin', 'cmp'):
        children = [node[2], node[3]]
    elif kind == 'bool':
        children = node[2]
    elif kind == 'if':
        children = [node[1], node[2], node[3]]
    elif kind == 'in':
        children = [node[1], node[2], node[3]]
    elif kind == 'coll':
        children = node[1]
    elif kind == 'pair':
        children = [node[1], node[2]]
    else:
        children = []
    for child in children:
        yield from walk(child)


def numbers_of(node, unit=None):
    """[(value, unit)] of the numbers of a tree. A number with no unit that is the whole tree, an
    argument of a distribution that is the whole tree, or an end of a range takes `unit`: a declared
    unit supplies the unit of a direct numeric literal."""
    node = canonical(node)
    out = []

    def direct(n):
        """Whether `n` is a literal that the declaration's unit reaches: the value itself, or an
        argument of the one distribution that is the value (also behind `.draw()`)."""
        if n[0] == 'num':
            return [n]
        if n[0] == 'method' and n[2] == 'draw' and not n[3]:
            return direct(n[1])
        if n[0] == 'call' and n[1] in DISTRIBUTIONS:
            return [arg for arg in n[2] if arg[0] == 'num']
        return []

    reached = {id(n) for n in direct(node)}
    for n in walk(node):
        if n[0] == 'num':
            value = number_value(n[1])
            given = n[2] if n[2] is not None else (unit if id(n) in reached else None)
            out.append((value if value is not None else n[1], given))
    return out


def names_of(node):
    """The paths that a tree reads."""
    return [n[1] for n in walk(node) if n[0] == 'name']


def calls_of(node):
    return [n[1] for n in walk(node) if n[0] == 'call'] + [n[2] for n in walk(node) if n[0] == 'method']


DISTRIBUTIONS = frozenset(
    {'uniform', 'triangular', 'pert', 'loguniform', 'normal', 'lognormal', 'beta', 'bernoulli', 'categorical'}
)
# The families that the language of now has; the old `beta` and `bernoulli` have no form now.
NEW_DISTRIBUTIONS = frozenset({'uniform', 'triangular', 'pert', 'loguniform', 'normal', 'lognormal'})
FUNCTIONS = frozenset(
    {'min', 'max', 'clip', 'abs', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf', 'sum', 'count', 'any', 'all'}
    | {'since', 'elapsed'}
)

# ---- the rewrite of an old expression -------------------------------------------------------------------


class Hand(Exception):
    """An expression that no mechanical rule translates: the reason, for the `# TODO(hand)` line."""


IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def member_of(value):
    """The enum member that a named value of the old language becomes: `"boil_water"` is
    `BOIL_WATER`."""
    if not IDENTIFIER.match(value):
        raise Hand(f'the named value "{value}" is no name: choose a member name by hand')
    return value.upper()


def old_tree(expr):
    """(the tree of an expression of the old language, before its names are resolved; the text that
    the old reader made of it). Names are ('old', 'a.b')."""
    from napkin.model.language import expressions

    text, names, _ = expressions.python(expr.tokens)
    try:
        tree = ast.parse(text, mode='eval').body
    except SyntaxError as exc:
        raise Hand(f'the old reader does not read this expression: {exc.msg}') from None

    def segment(node):
        return ast.get_source_segment(text, node)

    def visit(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return ('text', node.value)
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise Hand(f'a constant {node.value!r}')
            return ('num', segment(node), None)
        if isinstance(node, ast.Name):
            if node.id in names:
                return ('old', names[node.id])
            return ('name', node.id)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise Hand('a call of something that is no name')
            name = node.func.id
            if name in names:
                raise Hand(f'{names[name]} is not a function of the language')
            if name == 'q':
                return ('num', segment(node.args[0]), node.args[1].value)
            if node.keywords:
                args = [visit(arg) for arg in node.args]
                args += [('pair', ('name', k.arg), visit(k.value)) for k in node.keywords]
                return ('call', name, args)
            return ('call', name, [visit(arg) for arg in node.args])
        if isinstance(node, ast.BinOp):
            ops = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.Pow: '**'}
            if type(node.op) not in ops:
                raise Hand(f'the operator {type(node.op).__name__}')
            return ('bin', ops[type(node.op)], visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp):
            ops = {ast.USub: '-', ast.UAdd: '+', ast.Not: 'not'}
            if type(node.op) not in ops:
                raise Hand(f'the operator {type(node.op).__name__}')
            return ('un', ops[type(node.op)], visit(node.operand))
        if isinstance(node, ast.BoolOp):
            return ('bool', 'and' if isinstance(node.op, ast.And) else 'or', [visit(v) for v in node.values])
        if isinstance(node, ast.Compare):
            ops = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}
            sides = [node.left, *node.comparators]
            parts = []
            for op, left, right in zip(node.ops, sides, sides[1:], strict=False):
                if type(op) not in ops:
                    raise Hand(f'the comparison {type(op).__name__}')
                parts.append(('cmp', ops[type(op)], visit(left), visit(right)))
            return parts[0] if len(parts) == 1 else ('bool', 'and', parts)
        if isinstance(node, ast.IfExp):
            return ('if', visit(node.test), visit(node.body), visit(node.orelse))
        raise Hand(f'a {type(node).__name__} is no part of the new notation')

    return visit(tree)


class Scope:
    """Where an old expression stands: the names of its model (`oldmodel.Symbols`), the thing that it
    is read in (None: the top level), and the names of the outputs of the scenario, which a top-level
    expression can read. `renames` gives a member a new name: {(declaring thing, member): name}."""

    def __init__(self, symbols, thing, outputs=(), own='this.', renames=None):
        self.symbols = symbols
        self.thing = thing
        self.outputs = set(outputs)
        # What stands before a member of the thing itself: `this.` in the thing, and the thing's own
        # name where the expression stands outside it (a line of an option).
        self.own = own
        self.renames = renames or {}

    def path(self, name):
        """The new path of an old dotted name, and what it reads (`Symbols.read`)."""
        written, found = self._path(name)
        if found[0] == 'value' and (self.symbols.declarer(found[2]), found[3]) in self.renames:
            head, _, _ = written.rpartition('.')
            new = self.renames[(self.symbols.declarer(found[2]), found[3])]
            written = f'{head}.{new}' if head else new
        return written, found

    def _path(self, name):
        found = self.symbols.read(name, self.thing)
        parts = name.split('.')
        head = parts[0]
        if found is None:
            if self.thing is None and len(parts) == 1 and name in self.outputs:
                return name, ('output', name)
            raise Hand(f'the name {name} reads nothing that this script resolves')
        info = self.symbols.things.get(self.thing) if self.thing is not None else None
        if info is not None and (
            head in info.values or head in info.events or head in info.flows or head in info.links
        ):
            # A member of the thing itself, or a path through one of its links.
            return self.own + name, found
        if head in self.symbols.templates:
            if len(parts) == 1:
                return f'{head}.instances', found
            return f'{head}.instances.' + '.'.join(parts[1:]), found
        return name, found


def rewrite_old(expr, scope, draws=True):
    """The tree of an old expression in the new language. Raises `Hand` for a part that needs a
    decision. With `draws`, a distribution is drawn where it stands: `pert(a, m, b).draw()`."""
    return _new(old_tree(expr), scope, draws)


def _new(node, scope, draws):
    kind = node[0]
    if kind == 'old':
        if node[1] == 'copy':
            raise Hand('`copy` has no form in the first version')
        path, found = scope.path(node[1])
        if found[0] == 'event':
            raise Hand(f'the event {node[1]} is read as a value')
        return ('name', path)
    if kind == 'text':
        return ('name', member_of(node[1]))
    if kind in ('num', 'name'):
        return node
    if kind == 'call':
        return _call(node, scope, draws)
    if kind == 'un':
        return ('un', node[1], _new(node[2], scope, draws))
    if kind == 'bin':
        return ('bin', node[1], _new(node[2], scope, draws), _new(node[3], scope, draws))
    if kind == 'cmp':
        sides = [node[2], node[3]]
        since = [k for k, side in enumerate(sides) if side[0] == 'call' and side[1] == 'since']
        if since:
            # The old compiler reads `since(e) OP x` as `count(e) > 0 and t - e_time OP x`
            # (napkin/model/lower/expressions.py, `since_form`). The new language fails a run that
            # reads `since(e)` before the first occurrence, so the guard is written out.
            if len(since) != 1:
                raise Hand('since() on both sides of a comparison')
            event = _event(sides[since[0]], scope)
            other = _new(sides[1 - since[0]], scope, draws)
            if event[0] == 'state':
                clock = ('call', 'elapsed', [('name', event[1])])
                ordered = (clock, other) if since[0] == 0 else (other, clock)
                return ('cmp', node[1], *ordered)
            clock = ('call', 'since', [('name', event[1])])
            ordered = (clock, other) if since[0] == 0 else (other, clock)
            happened = ('cmp', '>', ('call', 'count', [('name', event[1] + '.occurrences')]), ('num', '0', None))
            return ('bool', 'and', [happened, ('cmp', node[1], *ordered)])
        return ('cmp', node[1], _new(node[2], scope, draws), _new(node[3], scope, draws))
    if kind == 'bool':
        values = []
        for value in node[2]:
            value = _new(value, scope, draws)
            # `a and (b and c)` is `a and b and c`: the guard of a `since` joins the condition it is in.
            values += value[2] if value[0] == 'bool' and value[1] == node[1] else [value]
        return ('bool', node[1], values)
    if kind == 'if':
        return ('if', _new(node[1], scope, draws), _new(node[2], scope, draws), _new(node[3], scope, draws))
    if kind == 'pair':
        return ('pair', node[1], _new(node[2], scope, draws))
    raise Hand(f'no rule for {node!r}')


def _event(call, scope):
    """('event', path) of the event that `since(e)` or `count(e)` reads, or ('state', path) for
    `since(state)`, which the old compiler reads as `elapsed(state)`."""
    args = call[2]
    if len(args) != 1 or args[0][0] != 'old':
        raise Hand(f'{call[1]}() of something that is no name')
    path, found = scope.path(args[0][1])
    if found[0] == 'event':
        if found[3] is not None:
            raise Hand(
                f'{call[1]}({args[0][1]}) reads one outcome of an event: the new language keeps no history of '
                'an outcome. Start an event of its own on that branch, and read that event'
            )
        return ('event', path)
    if found[0] == 'value' and found[1] == 'var.named' and call[1] == 'since':
        return ('state', path)
    raise Hand(f'{call[1]}({args[0][1]}) reads no event')


def _call(node, scope, draws):
    name, args = node[1], node[2]
    if name == 'since':
        raise Hand('since() outside a comparison')
    if name == 'count':
        if len(args) == 1 and args[0][0] == 'old':
            path, found = scope.path(args[0][1])
            if found[0] == 'value' and found[4]:
                return ('call', 'count', [('name', path)])
        event = _event(node, scope)
        return ('call', 'count', [('name', event[1] + '.occurrences')])
    if name == 'elapsed':
        if len(args) != 1 or args[0][0] != 'old':
            raise Hand('elapsed() of something that is no name')
        path, _ = scope.path(args[0][1])
        return ('call', 'elapsed', [('name', path)])
    if name in ('sum', 'any', 'all'):
        if len(args) != 1 or args[0][0] != 'old':
            raise Hand(f'{name}() of something that is no list')
        path, found = scope.path(args[0][1])
        if not (found[0] == 'value' and found[4]):
            raise Hand(f'{name}({args[0][1]}) reads no list')
        return ('call', name, [('name', path)])
    if name in ('min', 'max'):
        lists, others = [], []
        for arg in args:
            if arg[0] == 'old':
                path, found = scope.path(arg[1])
                if found[0] == 'value' and found[4]:
                    lists.append(('call', name, [('name', path)]))
                    continue
            others.append(_new(arg, scope, draws))
        if not lists:
            return ('call', name, others)
        # `max(list.x, v)`: the largest of the members' values and the other arguments.
        return ('call', name, [*lists, *others]) if others or len(lists) > 1 else lists[0]
    if name in NEW_DISTRIBUTIONS:
        made = ('call', name, [_new(arg, scope, draws) for arg in args])
        return ('method', made, 'draw', []) if draws else made
    if name in DISTRIBUTIONS:
        raise Hand(f'the language of now has no {name}(): write the draw with a family that it has')
    if name == 'delayed':
        # Change 12 after G0: a delayed observation is an event that waits and then writes.
        raise Hand('delayed() left the language: an event that waits (`after D:`) and then writes')
    if name in FUNCTIONS:
        return ('call', name, [_new(arg, scope, draws) for arg in args])
    raise Hand(f'the function {name}')


# ---- units, as the language of now spells them ---------------------------------------------------------


def new_unit(spelling):
    """A unit of the old notation as the language of now spells it (D12): the factors of a product,
    which the old notation joins with a hyphen, are joined by `*`, a power is its factor written again,
    and each factor below the line divides from the left. `tunings/tuner-year` is
    `tunings/tuner/year`, `person-hours` is `person * hours` and `L/h^2` is `L/h/h`. A unit that the
    old library declares under a composed name (`USD2024_bn/yr`) is spelled by its parts, each of which
    must then be a unit of the new library."""
    if spelling is None:
        return None

    def factors(piece):
        out = []
        for term in piece.split('-'):
            base, _, power = term.partition('^')
            out += [base] * (int(power) if power else 1)
        return out

    pieces = spelling.split('/')
    above = factors(pieces[0])
    below = [factor for piece in pieces[1:] for factor in factors(piece)]
    return ' * '.join(above) + ''.join('/' + factor for factor in below)


def with_new_units(node):
    """A tree with the unit of each number spelled as the language of now does (`new_unit`)."""
    kind = node[0]
    if kind == 'num':
        return ('num', node[1], new_unit(node[2]))
    if kind == 'call':
        return ('call', node[1], [with_new_units(arg) for arg in node[2]])
    if kind == 'method':
        return ('method', with_new_units(node[1]), node[2], [with_new_units(arg) for arg in node[3]])
    if kind == 'attr':
        return ('attr', with_new_units(node[1]), node[2])
    if kind == 'un':
        return ('un', node[1], with_new_units(node[2]))
    if kind in ('bin', 'cmp'):
        return (kind, node[1], with_new_units(node[2]), with_new_units(node[3]))
    if kind == 'bool':
        return ('bool', node[1], [with_new_units(value) for value in node[2]])
    if kind in ('if', 'in'):
        return (kind, *(with_new_units(part) for part in node[1:]))
    if kind == 'coll':
        return ('coll', [with_new_units(item) for item in node[1]])
    if kind == 'pair':
        return ('pair', node[1], with_new_units(node[2]))
    return node
