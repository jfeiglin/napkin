"""The mathematics of a model's expressions: a small tree of math nodes, and its LaTeX (docs/draw.md,
the Equations panel).

The nodes come from the expressions of the semantic model (`napkin/model/semantic.py`), so an equation
always says what the model says. `build` makes the node of an expression from its typed nodes
(`Expression.node`, `napkin/model/resolved.py`), and `to_node` writes a node back as those typed
nodes: `to_node(build(e)) is e.node`, because two typed nodes with the same parts are one object. An
expression that is a bare number or yes/no with no tree of its own is that number or word (`literal`).
`assignment` makes the node of a line of an event. The picture reads the nodes; nothing in the model or
the engine reads them.

The nodes, each a frozen dataclass:
- `Sym`: a value, by its key `entity.member` (the entity as the semantic `Ref` names it). The key of
  an output of the scenario is its name alone. `Time` is the time `t`. `Num` is a number with its unit
  (the unit's text, or None). `Text` is a named value (`"on"`) or a yes/no word (True or False).
- `Op` (`+ - * / **`), `Neg` and `Pos` (a sign), `Cmp`, `Logic` (`and`, `or`, with the items of one
  Python `and` or `or`), `Not` and `Cases`. A comparison is one `Cmp` with its operators and its
  operands: the chain `a < b < c` is one `Cmp` with two operators and three operands. `Cases` is
  `a if C else b`; each `else … if` of a chain is one more case, in order.
- `Call`: a function of the language (docs/language.md §2.1), and `delayed` and the distributions of
  an event, with their keyword arguments. The typed node of a call with keyword arguments is a
  `resolved.Named`. `Sum`: `sum`, `any`, `all`, `count`, `min` or `max` of a list, with the value of
  each member (`terms`). An argument of `min` or `max` that is a list is a `Sum` of the same function,
  in its place among the arguments of the `Call`.
- `Since` and `Count`: the time since an event happened, and how many times it happened. `ending` is
  the outcome that the file names (`since(respond.shut)`), or None for the event itself. `Elapsed` is
  the time since a named state took its value: the file writes `since(state)`.
- `Deriv` (d/dt of a stock) and `Assign` (a line of an event: `=`, `+=` or `-=`) are for the balances
  and the jumps of the Equations panel. The language writes no derivative, so `Deriv` has no typed
  node.

A node keeps how the file writes each name (`written`), and a yes/no word keeps its note (`problem`),
so that `to_node` gives the same typed nodes again. Neither takes part in the equality of two nodes.
A node with a `written` of None writes its key in the typed nodes. `as_dict` and `from_dict` give a
node as JSON data, and `to_json` as JSON text.

`walk(model)` gives each expression of a model with its place (`Place`).

`latex(node, symbol)` writes a node in LaTeX (amsmath). `symbol(key)` gives the LaTeX of the symbol
of a key; `latex` writes what it gives as it is. A key is that of a value, a flow or an event
(`entity.member`: the members of a thing share one set of names), or of an outcome
(`entity.event.outcome`, the name of an outcome in the language, docs/language.md §2.6). `clocks`
gives the forms of `Since`, `Count` and `Elapsed`, with `%s` for the symbol of what they read:
`CLOCKS` by default. The LaTeX of each node is one form only, so the LaTeX reads back to the node (a
list in `min` or `max` writes its members in place, the same function of the same values):
- The parentheses are the fewest that keep the tree. An operand with a lower precedence than its
  operator has them. So does a right operand of `+ - * /` with the same precedence: `a - (b - c)`
  and `a + (b + c)` keep them, and `(a - b) - c` is `a - b - c`. The precedences are those of Python
  (`precedence`). Also, for the reader: a sign after an operator or after a sign has them
  (`a \\cdot (-b)`), and so do the operand of `\\lnot` that is not an atom and an `and` or an `or`
  inside another.
- `*` is `\\cdot`. `/` is `\\frac{a}{b}`, except in an exponent, where it is `a / b`. The base of a
  power is in braces, `{a}^{b}`, and in parentheses too unless it is an atom (a symbol, a number
  without a unit, a function, a clock).
- A number is as Python writes it, with `\\times 10^{k}` for an exponent. Its unit follows a thin
  space, upright: `12\\,\\mathrm{Mgal/day}`, `\\mathrm{m}^{2}`; a character other than a letter, a
  digit, `/` or `.` is text, so `-` is a hyphen (`\\mathrm{person\\text{-}hours}`).
- `min`, `max`, `exp` and `ln` are `\\min`, `\\max`, `\\exp` and `\\ln`; `sqrt` is `\\sqrt{x}` and `abs`
  is `\\left|x\\right|`; a sum of a list is `\\sum(…)`; every other function is `\\operatorname{…}`, with
  its name. A keyword argument is `\\text{name}\\colon value`.
- `Cmp` writes `<`, `\\le`, `>`, `\\ge`, `=` and `\\ne`; `Logic` and `Not` write `\\land`, `\\lor` and
  `\\lnot`. `Cases` is `\\begin{cases} a & \\text{if } C \\\\ b & \\text{otherwise} \\end{cases}`.
- A named value is `\\text{…}`, and a yes/no word `\\mathrm{true}` or `\\mathrm{false}`. Every text
  is escaped (`escape`).
- `Deriv` is `\\frac{\\mathrm{d}S}{\\mathrm{d}t}`. `Assign` is `S \\leftarrow v`; for `+=` and `-=`, v is
  `S + v` and `S - v`, as the semantic model of the line writes it.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, fields

from ..core import expr
from ..model import resolved, semantic
from ..model.ir import DRAWN
from ..model.semantic import Ref

# The operators of each node, as Python writes them, and the name that a typed node gives each
# operation (`napkin/core/expr.py`).
OPERATORS = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'div', '**': 'pow'}
COMPARISONS = {'<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge', '==': 'eq', '!=': 'ne'}
LOGIC = {'and': 'and', 'or': 'or'}
ASSIGNMENTS = {'=': None, '+=': 'add', '-=': 'sub'}
# The functions of a list (`Sum`), and the functions that take a list among their arguments.
LISTS = ('sum', 'any', 'all', 'count', 'min', 'max')
# The number of arguments of each function of a `Call` (None: one or more), except the distributions,
# which take their parameters (`DRAWN`) by position or by name.
ARITY = {
    'min': None,
    'max': None,
    'clip': 3,
    'abs': 1,
    'exp': 1,
    'expm1': 1,
    'ln': 1,
    'log1p': 1,
    'sqrt': 1,
    'erf': 1,
    'delayed': 2,
}


class Node:
    """A node of the notation."""

    __slots__ = ()

    def as_dict(self):
        return as_dict(self)


def _tuple(node, name):
    object.__setattr__(node, name, tuple(getattr(node, name)))


@dataclass(frozen=True)
class Sym(Node):
    """A value: `entity.member`, or the name of an output of the scenario."""

    key: str
    written: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Num(Node):
    """A number that is not below 0, with its unit (the unit's text) or None."""

    value: int | float
    unit: str | None = None

    def __post_init__(self):
        value = self.value
        if type(value) not in (int, float) or not math.isfinite(value) or math.copysign(1, value) < 0:
            raise ValueError(f'a number of the notation is finite and not below 0: {value!r}')


@dataclass(frozen=True)
class Text(Node):
    """A named value (a text), or a yes/no word (True or False) with its note."""

    word: str | bool
    problem: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Time(Node):
    """The time, `t`."""


@dataclass(frozen=True)
class Op(Node):
    """`left op right`, with op one of `+ - * / **`."""

    op: str
    left: Node
    right: Node

    def __post_init__(self):
        if self.op not in OPERATORS:
            raise ValueError(f'{self.op} is not an operator of the notation')


@dataclass(frozen=True)
class Neg(Node):
    """`-x`."""

    x: Node


@dataclass(frozen=True)
class Pos(Node):
    """`+x`."""

    x: Node


@dataclass(frozen=True)
class Call(Node):
    """A function, with its arguments and its keyword arguments ((name, node), in order)."""

    name: str
    args: tuple
    keywords: tuple = ()

    def __post_init__(self):
        _tuple(self, 'args')
        object.__setattr__(self, 'keywords', tuple(tuple(pair) for pair in self.keywords))


@dataclass(frozen=True)
class Sum(Node):
    """`fn` of the members of a list: `fn` is one of `LISTS`, and `terms` are the members' values
    (`Sym`). `written` is the name of the list and its member as the file writes them (`zones.flag`)."""

    fn: str
    terms: tuple
    written: str | None = field(default=None, compare=False)

    def __post_init__(self):
        _tuple(self, 'terms')
        if self.fn not in LISTS:
            raise ValueError(f'{self.fn} is not a function of a list')
        if not all(isinstance(term, Sym) for term in self.terms):
            raise ValueError('each member of a list is a value (Sym)')


@dataclass(frozen=True)
class Cases(Node):
    """The value of the first case whose condition holds, else `otherwise`: `pairs` are (condition,
    value)."""

    pairs: tuple
    otherwise: Node

    def __post_init__(self):
        object.__setattr__(self, 'pairs', tuple(tuple(pair) for pair in self.pairs))
        if not self.pairs or any(len(pair) != 2 for pair in self.pairs):
            raise ValueError('Cases has one (condition, value) pair or more')


@dataclass(frozen=True)
class Cmp(Node):
    """A comparison, or a chain of them: `items[0] ops[0] items[1] ops[1] items[2] …`."""

    ops: tuple
    items: tuple

    def __post_init__(self):
        _tuple(self, 'ops')
        _tuple(self, 'items')
        if not self.ops or len(self.items) != len(self.ops) + 1:
            raise ValueError('a comparison has one operand more than its operators')
        for op in self.ops:
            if op not in COMPARISONS:
                raise ValueError(f'{op} is not a comparison of the notation')


@dataclass(frozen=True)
class Logic(Node):
    """`and` or `or` of two items or more."""

    op: str
    items: tuple

    def __post_init__(self):
        _tuple(self, 'items')
        if self.op not in LOGIC or len(self.items) < 2:
            raise ValueError('Logic is an `and` or an `or` of two items or more')


@dataclass(frozen=True)
class Not(Node):
    """`not x`."""

    x: Node


@dataclass(frozen=True)
class Since(Node):
    """The time since the event `event` (`entity.event`) happened, or its outcome `ending`."""

    event: str
    ending: str | None = None
    written: str | None = field(default=None, compare=False)

    @property
    def target(self):
        """The name of what it reads: the event, or its outcome (`entity.event.outcome`)."""
        return self.event if self.ending is None else f'{self.event}.{self.ending}'


@dataclass(frozen=True)
class Count(Node):
    """How many times the event `event` (`entity.event`) happened, or its outcome `ending`."""

    event: str
    ending: str | None = None
    written: str | None = field(default=None, compare=False)

    @property
    def target(self):
        """The name of what it reads: the event, or its outcome (`entity.event.outcome`)."""
        return self.event if self.ending is None else f'{self.event}.{self.ending}'


@dataclass(frozen=True)
class Elapsed(Node):
    """The time since the named state `key` took its value."""

    key: str
    written: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Deriv(Node):
    """The rate of change of the stock or tally `key`, d/dt."""

    key: str


@dataclass(frozen=True)
class Assign(Node):
    """A line of an event: `target op value`, with op `=`, `+=` or `-=`."""

    target: str
    op: str
    value: Node
    written: str | None = field(default=None, compare=False)

    def __post_init__(self):
        if self.op not in ASSIGNMENTS:
            raise ValueError(f'{self.op} is not a line of an event')


# Each class of node by its name, as `as_dict` writes it.
_CLASSES = (Sym, Num, Text, Time, Op, Neg, Pos, Call, Sum, Cases, Cmp, Logic, Not, Since, Count, Elapsed)
NODES = {cls.__name__: cls for cls in (*_CLASSES, Deriv, Assign)}


# ---- keys -----------------------------------------------------------------------------------------


def key_of(entity, member):
    """The key of member `member` of entity `entity`; of an output of the scenario (entity None), its
    name."""
    return member if entity is None else f'{entity}.{member}'


def split(key):
    """(entity, member) of a key: the entity is None for an output of the scenario. An entity's name
    can hold dots (copy k of a set, `waves.1`); a member's name cannot."""
    entity, _, member = key.rpartition('.')
    return entity or None, member


# ---- from the typed nodes of the semantic model ---------------------------------------------------

# The operator of each node, by the name that a typed node gives its operation.
_BINARY = {name: op for op, name in OPERATORS.items()}
_COMPARE = {name: op for op, name in COMPARISONS.items()}


def build(expression):
    """The node of an expression: a semantic `Expression`, its typed nodes (`Expression.node`, the
    value of a line, the amount of a move), or a bare number or yes/no.

    An expression with no node is its written number or yes/no. So is a yes/no that the file writes
    where an expression goes, such as the start value of a bool state: the front end gives it a
    `Problem` ("an expression is text or a number"), and the builder reads the word that the file
    writes (`literal`). Raises ValueError for a part that is not in the notation, and for any other
    `Problem`."""
    if isinstance(expression, semantic.Expression):
        if literal(expression):
            return _literal(expression.written)
        return _node(expression.node)
    if isinstance(expression, (bool, int, float)):
        return _literal(expression)
    return _node(expression)


def literal(expression):
    """Whether the node of a semantic `Expression` is its written number or yes/no, and not its typed
    nodes: it has none, or it is a yes/no whose typed node is a `Problem`."""
    if expression.node is None:
        return True
    return isinstance(expression.node, resolved.Problem) and isinstance(expression.written, bool)


def _literal(value):
    if isinstance(value, bool):
        return Text(value)
    if type(value) in (int, float) and math.isfinite(value):
        return Neg(Num(-value)) if math.copysign(1, value) < 0 else Num(value)
    raise ValueError(f'{value!r} is not a number or a yes/no')


def _node(node):
    if isinstance(node, resolved.Problem):
        raise ValueError(f'the expression has a problem: {node.message}')
    if isinstance(node, resolved.Ref):
        return Sym(key_of(node.entity, node.member), node.written)
    if isinstance(node, resolved.Word):
        return Text(bool(node.value), node.problem)
    if isinstance(node, (resolved.EventRef, resolved.Terms)):
        raise ValueError(f'{type(node).__name__} is only the argument of a function')
    if isinstance(node, expr.Const):
        value = node.value
        if isinstance(value, str):
            return Text(value)
        if type(value) in (int, float) and math.isfinite(value) and math.copysign(1, value) > 0:
            return Num(value)
        raise ValueError(f'the constant {value!r} is not in the notation')
    if isinstance(node, expr.Ref):
        if node.name == 't':
            return Time()
        # The front end reads every other name: one that it leaves is a name of Python's tree.
        raise ValueError('Name is not a part of the notation')
    if isinstance(node, expr.Binary):
        return Op(_BINARY[node.op], _node(node.left), _node(node.right))
    if isinstance(node, expr.Unary):
        return {'neg': Neg, 'pos': Pos, 'not': Not}[node.op](_node(node.operand))
    if isinstance(node, expr.BoolOp):
        return Logic(node.op, tuple(_node(value) for value in node.values))
    if isinstance(node, expr.Compare):
        return Cmp(tuple(_COMPARE[op] for op in node.ops), tuple(_node(item) for item in node.operands))
    if isinstance(node, expr.IfElse):
        pairs = []
        while isinstance(node, expr.IfElse):
            pairs.append((_node(node.test), _node(node.body)))
            node = node.orelse
        return Cases(tuple(pairs), _node(node))
    if isinstance(node, expr.Call):
        return _call(node.function, node.args, ())
    if isinstance(node, resolved.Named):
        return _call(node.function, node.args, node.named)
    if isinstance(node, expr.Foreign):
        return _outside(node)
    raise ValueError(f'{type(node).__name__} is not a part of the notation')


def _outside(node):
    """A part that the language does not have (`expr.Foreign`) is an error that names its kind in
    Python's tree, which the typed node keeps."""
    kind = type(node.tree).__name__
    if kind == 'Call':
        raise ValueError('a function is called by its name')
    shown = type(getattr(node.tree, 'op', None)).__name__ if hasattr(node.tree, 'op') else None
    raise ValueError(f'{kind}{f" ({shown})" if shown else ""} is not a part of the notation')


def _terms(terms):
    if not all(isinstance(ref, resolved.Ref) for ref in terms.refs):
        raise ValueError('each member of a list is a value')
    return tuple(Sym(key_of(ref.entity, ref.member), ref.written) for ref in terms.refs)


def _call(name, args, keywords):
    """The node of a call of the function `name` with the typed nodes `args`. `keywords` are its
    keyword arguments, ((name, typed node), …)."""
    if keywords and name not in DRAWN:
        raise ValueError(f'{name}() takes no keyword arguments')
    one = args[0] if len(args) == 1 and not keywords else None
    if name == 'q':
        if len(args) == 2 and type(args[0]) is expr.Const and type(args[1]) is expr.Const:
            value, written = args[0].value, args[1].value
            if type(value) in (int, float) and isinstance(written, str):
                return Num(value, written)
        raise ValueError('q() takes a number and the text of its unit')
    if name in ('since', 'count') and isinstance(one, resolved.EventRef):
        if one.kind != 'trigger':
            raise ValueError(f'an event of kind {one.kind!r} is not in the notation')
        clock = Since if name == 'since' else Count
        return clock(one.key, one.ending, one.written)
    if name in ('sum', 'any', 'all', 'count'):
        if isinstance(one, resolved.Terms):
            return Sum(name, _terms(one), one.written)
        raise ValueError(f'{name}() takes {"an event or " if name == "count" else ""}a list')
    if name == 'since':
        raise ValueError('since() takes an event')
    if name == 'elapsed':
        if isinstance(one, resolved.Ref):
            return Elapsed(key_of(one.entity, one.member), one.written)
        raise ValueError('elapsed() takes a named state')
    if name in ('min', 'max') and isinstance(one, resolved.Terms):
        return Sum(name, _terms(one), one.written)
    if name in ('min', 'max'):
        items = tuple(
            Sum(name, _terms(arg), arg.written) if isinstance(arg, resolved.Terms) else _node(arg)
            for arg in args
        )
    else:
        items = tuple(_node(arg) for arg in args)
    if name in DRAWN:
        parameters = DRAWN[name]
        named = [key for key, _ in keywords]
        if (
            len(args) > len(parameters)
            or None in named
            or len(set(named)) != len(named)
            or not set(named) <= set(parameters[len(args) :])
        ):
            raise ValueError(f'{name}() takes {", ".join(parameters)}, each once')
        return Call(name, items, tuple((key, _node(value)) for key, value in keywords))
    if name not in ARITY:
        raise ValueError(f'{name}() is not a function of the notation')
    arity = ARITY[name]
    if (arity is None and not args) or (arity is not None and len(args) != arity):
        raise ValueError(f'{name}() takes {arity or "one or more"} arguments')
    return Call(name, items)


def assignment(line):
    """The node of a line of an event that sets a value (a semantic `Assign`): `x = v`, `x += v` or
    `x -= v`, whose value (v) is without the target. Raises ValueError for a line that has a
    problem."""
    target = line.target
    if not isinstance(target, Ref):
        raise ValueError('the target of the line has a problem')
    key = key_of(target.entity, target.member)
    value = line.value
    if not line.augmented:
        return Assign(key, '=', build(value), target.written)
    op = {'Add': '+=', 'Sub': '-='}.get(line.operator)
    if (
        op is None
        or not isinstance(value, expr.Binary)
        or value.op != ASSIGNMENTS[op]
        or not isinstance(value.left, resolved.Ref)
        or key_of(value.left.entity, value.left.member) != key
    ):
        raise ValueError('the value of the line is not its target and the change')
    return Assign(key, op, build(value.right), value.left.written)


# ---- back to the typed nodes -----------------------------------------------------------------------


def _ref(key, written):
    entity, member = split(key)
    return resolved.ref(entity, member, key if written is None else written)


def _list(node):
    return resolved.terms((_ref(term.key, term.written) for term in node.terms), node.written)


def to_node(node):
    """The typed nodes of a node (`napkin/model/resolved.py`): the nodes that `build` reads, so
    `to_node(build(e)) is e.node`. For an `Assign`, the nodes of the value of its line. A `Deriv` has
    no typed node."""
    if isinstance(node, Sym):
        return _ref(node.key, node.written)
    if isinstance(node, Num):
        if node.unit is None:
            return expr.const(node.value)
        return expr.call('q', [expr.const(node.value), expr.const(node.unit)])
    if isinstance(node, Text):
        if isinstance(node.word, bool):
            return resolved.word(node.word, node.problem)
        return expr.const(node.word)
    if isinstance(node, Time):
        return expr.ref('t')
    if isinstance(node, Op):
        return expr.binary(OPERATORS[node.op], to_node(node.left), to_node(node.right))
    if isinstance(node, (Neg, Pos, Not)):
        return expr.unary({Neg: 'neg', Pos: 'pos', Not: 'not'}[type(node)], to_node(node.x))
    if isinstance(node, Logic):
        return expr.boolean(LOGIC[node.op], [to_node(item) for item in node.items])
    if isinstance(node, Cmp):
        return expr.compare([COMPARISONS[op] for op in node.ops], [to_node(item) for item in node.items])
    if isinstance(node, Cases):
        made = to_node(node.otherwise)
        for condition, value in reversed(node.pairs):
            made = expr.if_else(to_node(condition), to_node(value), made)
        return made
    if isinstance(node, Call):
        args = [
            _list(arg) if isinstance(arg, Sum) and arg.fn == node.name else to_node(arg) for arg in node.args
        ]
        if node.keywords:
            return resolved.named(node.name, args, ((key, to_node(value)) for key, value in node.keywords))
        return expr.call(node.name, args)
    if isinstance(node, Sum):
        return expr.call(node.fn, [_list(node)])
    if isinstance(node, (Since, Count)):
        written = node.target if node.written is None else node.written
        event = resolved.event_ref('trigger', node.event, node.ending, written)
        return expr.call('since' if isinstance(node, Since) else 'count', [event])
    if isinstance(node, Elapsed):
        return expr.call('elapsed', [_ref(node.key, node.written)])
    if isinstance(node, Assign):
        value = to_node(node.value)
        if node.op == '=':
            return value
        return expr.binary(ASSIGNMENTS[node.op], _ref(node.target, node.written), value)
    if isinstance(node, Deriv):
        raise ValueError('the language writes no derivative: a Deriv has no typed node')
    raise ValueError(f'{node!r} is not a node of the notation')


# ---- the nodes as data ----------------------------------------------------------------------------


def children(node):
    """The nodes directly under a node, in order."""
    for item in fields(node):
        yield from _nodes_in(getattr(node, item.name))


def _nodes_in(value):
    if isinstance(value, Node):
        yield value
    elif isinstance(value, tuple):
        for item in value:
            yield from _nodes_in(item)


def nodes(node):
    """A node and every node under it, the node first, in order."""
    yield node
    for child in children(node):
        yield from nodes(child)


def as_dict(node):
    """A node as JSON data: `{"node": its class, each field: its value}`, a node as a dict and a
    tuple as a list."""
    out = {'node': type(node).__name__}
    for item in fields(node):
        out[item.name] = _plain(getattr(node, item.name))
    return out


def _plain(value):
    if isinstance(value, Node):
        return as_dict(value)
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def from_dict(data):
    """The node of `as_dict`."""
    cls = NODES[data['node']]
    return cls(**{item.name: _value(data[item.name]) for item in fields(cls) if item.name in data})


def _value(value):
    if isinstance(value, dict):
        return from_dict(value)
    if isinstance(value, list):
        return tuple(_value(item) for item in value)
    return value


def to_json(node):
    """A node as JSON text."""
    return json.dumps(as_dict(node), ensure_ascii=False, separators=(',', ':'))


# ---- the expressions of a model -------------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    """Where an expression is: its entity (None for the scenario's own parts), the member that holds
    it (a value, a flow, a share, an event or an output; None for a timescale), what it is (`part`)
    and its place in the file."""

    entity: str | None
    name: str | None
    part: str
    where: tuple


def walk(model) -> Iterator[tuple[Place, semantic.Expression]]:
    """Each expression of a model (or of its semantic `Scenario`), once, with its place, in the order
    of the semantic model. The parts:
    - of a value: `start`, `formula`, `rate`, `minimum`, `maximum`, `size`, `argument` (a parameter of
      its distribution), and `output` and `lag` of an output;
    - `option` (the start value that an option gives), `status` (a condition of a status line), and
      `check`, `total` and `within` of an `assert`;
    - of a flow: `flow` (its rate), `while` (its condition) and `pair` (the rate of a pair); of a
      share: `limit`;
    - of an event: `when`, `after`, `each`, `keep` (its `while`), and of its outcomes `chance`,
      `available` (the condition of an outcome), `set` (the value of a line `x = v`, `x += v` or
      `x -= v`, as its semantic tree writes it: `x + v` for `x += v`) and `move` (the amount of a
      move);
    - of the scenario: `timescale`, and its outputs and checks.
    The value of a line and the amount of a move are typed nodes: each is an `Expression` here, with
    no written text."""
    scenario = getattr(model, 'scenario', model)
    seen = set()
    found = []

    def add(entity, name, part, item, where=None):
        if item is None:
            return
        if not isinstance(item, semantic.Expression):
            item = semantic.Expression(None, item, tuple(where))
        if id(item) in seen:
            return
        seen.add(id(item))
        found.append((Place(entity, name, part, tuple(item.where)), item))

    def output(entity, name, item):
        add(entity, name, 'output', item.formula)
        for delay in item.lag.delays if item.lag is not None else ():
            add(entity, name, 'lag', delay)

    def check(entity, item):
        add(entity, None, 'check', item.condition)
        add(entity, None, 'total', item.total)
        add(entity, None, 'within', item.within)

    for entity in scenario.entities:
        e = entity.name
        for value in entity.values:
            n = value.name
            add(e, n, 'start', value.initial)
            add(e, n, 'formula', value.formula)
            if value.rate is not None:
                add(e, n, 'rate', value.rate.expression)
            for part in ('minimum', 'maximum', 'size'):
                bound = getattr(value, part)
                if bound is not None:
                    add(e, n, part, bound.expression)
            for _, _, arguments in value.arguments:
                for _, expression in arguments:
                    add(e, n, 'argument', expression)
            if value.output is not None:
                output(e, n, value.output)
        for setting in entity.settings:
            add(e, setting.target, 'option', setting.start)
        if entity.status is not None:
            for case in entity.status.cases:
                add(e, None, 'status', case.condition)
        for item in entity.checks:
            check(e, item)
        for flow in entity.flows:
            add(e, flow.name, 'flow', flow.rate)
            add(e, flow.name, 'while', flow.condition)
            for pair in flow.pairs:
                add(e, flow.name, 'pair', pair.rate)
        for allocation in entity.allocations:
            add(e, allocation.name, 'limit', allocation.limit)
        for event in entity.events:
            n = event.name
            add(e, n, 'when', event.when)
            add(e, n, 'after', event.after)
            for item in event.each:
                add(e, n, 'each', item)
            add(e, n, 'keep', event.keep)
            for outcome in event.outcomes:
                if isinstance(outcome.chance, semantic.Expression):
                    add(e, n, 'chance', outcome.chance)
                add(e, n, 'available', outcome.available)
                for line in outcome.lines:
                    if isinstance(line, semantic.Assign):
                        add(e, n, 'set', line.value, line.where)
                    elif isinstance(line, semantic.Move):
                        add(e, n, 'move', line.amount, line.where)
    for item in scenario.timescales or ():
        add(None, None, 'timescale', item)
    for item in scenario.outputs:
        output(None, item.name, item)
    for item in scenario.checks:
        check(None, item)
    yield from found


# ---- LaTeX ----------------------------------------------------------------------------------------

# The forms of the clocks: `%s` is the symbol of the event, the outcome or the named state.
CLOCKS = {'since': r'\tau_{%s}', 'count': r'N_{%s}', 'elapsed': r'\tau_{%s}'}
_CMP = {'<': '<', '<=': r'\le', '>': '>', '>=': r'\ge', '==': '=', '!=': r'\ne'}
_LOGIC_WORDS = {'and': r'\land', 'or': r'\lor'}
_FUNCTIONS = {'min': r'\min', 'max': r'\max', 'exp': r'\exp', 'ln': r'\ln'}
_LISTS = {'sum': r'\sum', 'min': r'\min', 'max': r'\max'}
# The characters that LaTeX reads in a text, and how a text writes them.
_ESCAPES = {
    '\\': r'\textbackslash{}',
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
    '<': r'\textless{}',
    '>': r'\textgreater{}',
    '|': r'\textbar{}',
}
_POWER = re.compile(r'\^(-?[0-9]+)')
_UNIT_TEXT = re.compile(r'[^A-Za-z0-9/.]+')

# The precedences, as Python's: a higher one binds tighter. An atom writes its own bounds.
ATOM = 9
_PRECEDENCE = {'or': 1, 'and': 2, '+': 5, '-': 5, '*': 6, '/': 6, '**': 8}


def escape(text):
    """A text as LaTeX text reads it: each special character escaped."""
    return ''.join(_ESCAPES.get(char, char) for char in text)


def precedence(node, exponent=False):
    """The precedence of a node's LaTeX: Python's (a `Cases` 0, `or` 1, `and` 2, `not` 3, a comparison
    4, `+ -` 5, `* /` 6, a sign 7, `**` 8), and `ATOM` for a node that writes its own bounds. A `/` is
    an atom, `\\frac{}{}`, except in an exponent."""
    if isinstance(node, Cases):
        return 0
    if isinstance(node, Logic):
        return _PRECEDENCE[node.op]
    if isinstance(node, Not):
        return 3
    if isinstance(node, Cmp):
        return 4
    if isinstance(node, Op):
        return ATOM if node.op == '/' and not exponent else _PRECEDENCE[node.op]
    if isinstance(node, (Neg, Pos)):
        return 7
    return ATOM


def number(value):
    """The LaTeX of a number: as Python writes it, with `\\times 10^{k}` for its exponent."""
    if type(value) is int:
        return str(value)
    text = repr(value)
    mantissa, e, power = text.partition('e')
    return rf'{mantissa} \times 10^{{{int(power)}}}' if e else text


def unit(text):
    """The LaTeX of a unit: upright, each power `^n` as a superscript, and each character other than a
    letter, a digit, `/` or `.` as text (`\\text{-}`)."""

    def upright(piece):
        return r'\mathrm{' + _UNIT_TEXT.sub(lambda m: r'\text{' + escape(m.group()) + '}', piece) + '}'

    parts, piece, at = [], '', 0
    for found in _POWER.finditer(text):
        piece += text[at : found.start()]
        at = found.end()
        if piece:
            parts.append(f'{upright(piece)}^{{{found.group(1)}}}')
            piece = ''
        else:
            piece = found.group()  # a power after nothing, or after a power, is text
    piece += text[at:]
    if piece:
        parts.append(upright(piece))
    return ''.join(parts)


def latex(node, symbol: Callable[[str], str], clocks=None):
    """The LaTeX of a node (see the module's text): `symbol(key)` is the LaTeX of the symbol of a key,
    and `clocks` the forms of the clocks (`CLOCKS`)."""
    return _Writer(symbol, CLOCKS if clocks is None else clocks).write(node, False)


def _round(text):
    return r'\left(' + text + r'\right)'


class _Writer:
    def __init__(self, symbol, clocks):
        self.symbol, self.clocks = symbol, clocks

    def operand(self, node, minimum, exponent):
        """A node where its parent needs at least the precedence `minimum`."""
        text = self.write(node, exponent)
        return _round(text) if precedence(node, exponent) < minimum else text

    def right(self, node, minimum, exponent):
        """The right operand of a binary operator: a sign there is in parentheses."""
        if isinstance(node, (Neg, Pos)):
            return _round(self.write(node, exponent))
        return self.operand(node, minimum, exponent)

    def base(self, node, exponent):
        """The base of a power: in parentheses unless it is an atom."""
        text = self.write(node, exponent)
        plain = isinstance(node, (Sym, Time, Text, Call, Sum, Since, Count, Elapsed))
        plain = plain or (isinstance(node, Num) and node.unit is None and 'e' not in repr(node.value))
        return '{' + (text if plain else _round(text)) + '}'

    def arguments(self, items, exponent):
        return _round(', '.join(self.write(item, exponent) for item in items))

    def write(self, node, exponent):
        if isinstance(node, Sym):
            return self.symbol(node.key)
        if isinstance(node, Num):
            text = number(node.value)
            return text if node.unit is None else text + r'\,' + unit(node.unit)
        if isinstance(node, Text):
            if isinstance(node.word, bool):
                return r'\mathrm{true}' if node.word else r'\mathrm{false}'
            return r'\text{' + escape(node.word) + '}'
        if isinstance(node, Time):
            return 't'
        if isinstance(node, Op):
            return self.op(node, exponent)
        if isinstance(node, (Neg, Pos)):
            sign = '-' if isinstance(node, Neg) else '+'
            x = node.x
            if isinstance(x, (Neg, Pos)):
                return sign + _round(self.write(x, exponent))
            return sign + self.operand(x, 7, exponent)
        if isinstance(node, Cmp):
            parts = [self.operand(node.items[0], 5, exponent)]
            for op, item in zip(node.ops, node.items[1:]):
                parts += [_CMP[op], self.operand(item, 5, exponent)]
            return ' '.join(parts)
        if isinstance(node, Logic):
            word = f' {_LOGIC_WORDS[node.op]} '
            return word.join(self.operand(item, 3, exponent) for item in node.items)
        if isinstance(node, Not):
            return r'\lnot ' + self.operand(node.x, 7, exponent)
        if isinstance(node, Cases):
            rows = [
                f'{self.write(value, exponent)} & \\text{{if }} {self.write(condition, exponent)}'
                for condition, value in node.pairs
            ]
            rows.append(f'{self.write(node.otherwise, exponent)} & \\text{{otherwise}}')
            return r'\begin{cases} ' + r' \\ '.join(rows) + r' \end{cases}'
        if isinstance(node, Call):
            return self.call(node, exponent)
        if isinstance(node, Sum):
            name = _LISTS.get(node.fn, rf'\operatorname{{{node.fn}}}')
            return name + self.arguments(node.terms, exponent)
        if isinstance(node, Since):
            return self.clocks['since'] % self.symbol(node.target)
        if isinstance(node, Count):
            return self.clocks['count'] % self.symbol(node.target)
        if isinstance(node, Elapsed):
            return self.clocks['elapsed'] % self.symbol(node.key)
        if isinstance(node, Deriv):
            return r'\frac{\mathrm{d}' + self.symbol(node.key) + r'}{\mathrm{d}t}'
        if isinstance(node, Assign):
            value = node.value
            if node.op != '=':
                value = Op(node.op[0], Sym(node.target), value)
            return self.symbol(node.target) + r' \leftarrow ' + self.write(value, exponent)
        raise ValueError(f'{node!r} is not a node of the notation')

    def op(self, node, exponent):
        if node.op == '**':
            return self.base(node.left, exponent) + '^{' + self.write(node.right, True) + '}'
        if node.op == '/' and not exponent:
            return r'\frac{' + self.write(node.left, False) + '}{' + self.write(node.right, False) + '}'
        level = _PRECEDENCE[node.op]
        sign = r'\cdot' if node.op == '*' else node.op
        left = self.operand(node.left, level, exponent)
        return f'{left} {sign} {self.right(node.right, level + 1, exponent)}'

    def call(self, node, exponent):
        if node.name == 'sqrt':
            return r'\sqrt{' + self.write(node.args[0], exponent) + '}'
        if node.name == 'abs':
            return r'\left|' + self.write(node.args[0], exponent) + r'\right|'
        items = []
        for arg in node.args:
            if isinstance(arg, Sum) and arg.fn == node.name:
                items += [self.write(term, exponent) for term in arg.terms]
            else:
                items.append(self.write(arg, exponent))
        items += [
            rf'\text{{{escape(name)}}}\colon {self.write(value, exponent)}' for name, value in node.keywords
        ]
        name = _FUNCTIONS.get(node.name, rf'\operatorname{{{node.name}}}')
        return name + _round(', '.join(items))
