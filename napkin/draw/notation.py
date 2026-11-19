"""The mathematics of a model's expressions: a small tree of math nodes, and its LaTeX (docs/draw.md,
the Equations panel).

The nodes come from the expressions of the declared model, in its typed form
(`napkin/model/semantic.py`), so an equation always says what the model says. `build(expression,
keys)` makes the node of an expression, with the node of each read from `keys` (`Keys`: the reads of
one member, by the keys of the picture). `assignment` makes the node of an assignment of a stage. The
picture reads the nodes; nothing in the model or the engine reads them.

The nodes, each a frozen dataclass:
- `Sym`: a value, a flow, an event or a part of one, by its key `member.name` (the member's id, then
  the name; `site.restore.labor` for a leg, `grinder.refill.amount` for a parameter of an event). The
  key of a value of the top level is its name alone. `Time` is the time `t`. `Num` is a number with
  its unit (the unit's spelling, or None). `Text` is an enum member or a text (a string), or a yes/no
  (True or False); it is also the words of a read that no symbol stands for (a member of a keyed
  collection that only a run knows).
- `Op` (`+ - * / **`), `Neg` and `Pos` (a sign), `Cmp`, `Logic` (`and`, `or`), `Not` and `Cases`. A
  comparison is one `Cmp` with its operators and its operands: the chain `a < b < c` is one `Cmp` with
  two operators and three operands. `Cases` is `a if C else b`; each `else … if` of a chain is one
  more case, in order.
- `Call`: a function of the language (`min`, `max`, `clip`, `abs`, `sqrt`, `exp`, `ln`, …); a
  distribution (`uniform`, `pert`, `categorical` with a keyword argument for each outcome); `draw`
  and `choose` of a distribution; and the reads of a flow or a store that are no value of their own:
  `request(f)`, `capacity(f)`, `outflow(S)`, `inflow(S)`, `mean(d)` and `std(d)`. `Sum`: `sum`,
  `any`, `all`, `count`, `min` or `max` of a collection whose members the model fixes, with the value
  of each member (`terms`).
- `Since` and `Count`: the time since an event last started, and how many times it started. `Elapsed`
  is the time since a value last changed (`elapsed(x)`).
- `Deriv` (d/dt of a stock) and `Assign` (an assignment of a stage: `=`, `+=` or `-=`) are for the
  balances and the jumps of the Equations panel. The language writes no derivative, so `Deriv` has no
  expression of its own.

A node keeps how the file writes each name (`written`), which takes no part in the equality of two
nodes. `as_dict` and `from_dict` give a node as JSON data, and `to_json` as JSON text.

`walk(found)` gives each expression of a model with its place (`Place`).

`latex(node, symbol)` writes a node in LaTeX (amsmath). `symbol(key)` gives the LaTeX of the symbol
of a key; `latex` writes what it gives as it is. `clocks` gives the forms of `Since`, `Count` and
`Elapsed`, with `%s` for the symbol of what they read: `CLOCKS` by default. The LaTeX of each node is
one form only, so the LaTeX reads back to the node (a list in `min` or `max` writes its members in
place, the same function of the same values):
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
- An enum member and a text are `\\text{…}`, and a yes/no word `\\mathrm{true}` or `\\mathrm{false}`.
  Every text is escaped (`escape`).
- `Deriv` is `\\frac{\\mathrm{d}S}{\\mathrm{d}t}`. `Assign` is `S \\leftarrow v`; for `+=` and `-=`, v is
  `S + v` and `S - v`.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, fields

from ..model import semantic as s

OPERATORS = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'div', '**': 'pow'}
COMPARISONS = {'<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge', '==': 'eq', '!=': 'ne'}
LOGIC = {'and': 'and', 'or': 'or'}
ASSIGNMENTS = {'=': None, '+=': 'add', '-=': 'sub'}
# The functions of a list (`Sum`).
LISTS = ('sum', 'any', 'all', 'count', 'min', 'max')
# The calls of the reads of a flow, a store and a distribution that are no value of their own.
STEPS = ('request', 'capacity', 'outflow', 'inflow', 'mean', 'std')


class Node:
    """A node of the notation."""

    __slots__ = ()

    def as_dict(self):
        return as_dict(self)


def _tuple(node, name):
    object.__setattr__(node, name, tuple(getattr(node, name)))


@dataclass(frozen=True)
class Sym(Node):
    """A value, a flow or an event: `member.name`, or the name of a value of the top level."""

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
    """An enum member or a text, or a yes/no word (True or False)."""

    word: str | bool


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
    """`fn` of the members of a collection: `fn` is one of `LISTS`, and `terms` are the members'
    values (`Sym`). `written` is the collection in words."""

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
    """The time since the event `event` (`member.event`) last started."""

    event: str
    written: str | None = field(default=None, compare=False)

    @property
    def target(self):
        """The key of what it reads: the event."""
        return self.event


@dataclass(frozen=True)
class Count(Node):
    """How many times the event `event` (`member.event`) started."""

    event: str
    written: str | None = field(default=None, compare=False)

    @property
    def target(self):
        """The key of what it reads: the event."""
        return self.event


@dataclass(frozen=True)
class Elapsed(Node):
    """The time since the value `key` last changed."""

    key: str
    written: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Deriv(Node):
    """The rate of change of the stock or tally `key`, d/dt."""

    key: str


@dataclass(frozen=True)
class Assign(Node):
    """An assignment of a stage: `target op value`, with op `=`, `+=` or `-=`."""

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
    """The key of the part `member` of `entity` (a member, or a part of one); of a value of the top
    level (entity None), its name."""
    return member if entity is None else f'{entity}.{member}'


def split(key):
    """(entity, name) of a key at its last dot: the entity is None for a value of the top level. An
    entity can hold dots (the row `places.a`, the event `grinder.refill`); a name cannot."""
    entity, _, member = key.rpartition('.')
    return entity or None, member


# ---- from the typed form of the declared model -------------------------------------------------------

_BINARY = {name: op for op, name in OPERATORS.items()}


def build(expression, keys):
    """The node of an expression of the typed form (`semantic.Const`, `Read`, `Apply`, `Reduced`,
    `Retain`, `History`, `Distribution`, `Drawn`, `Chosen`); `keys(read)` gives the node of each read,
    and `keys.reduced(node)` that of a reduction (`Keys`). Raises ValueError for a part that is not in
    the notation."""
    if isinstance(expression, s.Const):
        return constant(expression.value, expression.type)
    if isinstance(expression, s.Read):
        return keys(expression)
    if isinstance(expression, s.Retain):
        return build(expression.body, keys)
    if isinstance(expression, s.Reduced):
        return keys.reduced(expression)
    if isinstance(expression, s.History):
        found = keys(expression.source)
        if expression.op == 'since':
            return Since(found.key) if isinstance(found, Sym) else Call('since', (found,))
        return Elapsed(found.key) if isinstance(found, Sym) else Call('elapsed', (found,))
    if isinstance(expression, s.Distribution):
        return distribution(expression)
    if isinstance(expression, s.Drawn):
        return Call('draw', (build(expression.source, keys),))
    if isinstance(expression, s.Chosen):
        return Call('choose', (build(expression.source, keys),))
    if isinstance(expression, s.Apply):
        return _apply(expression, keys)
    raise ValueError(f'{type(expression).__name__} is not a part of the notation')


def constant(value, kind=None):
    """The node of a constant: a number with the unit of its type, a yes/no, an enum member or a
    text."""
    if isinstance(value, bool):
        return Text(value)
    if isinstance(value, str):
        return Text(value)
    if type(value) in (int, float) and math.isfinite(value):
        unit = getattr(kind, 'unit', '') or None
        return Neg(Num(-value, unit)) if math.copysign(1, value) < 0 else Num(value, unit)
    raise ValueError(f'the constant {value!r} is not in the notation')


def distribution(expression):
    """The node of a distribution: its family with its parameters in its unit, or a categorical with a
    keyword argument for the weight of each outcome."""
    if expression.family == 'categorical':
        weights = tuple(
            (outcome, constant(weight)) for outcome, weight in zip(expression.outcomes, expression.params)
        )
        return Call('categorical', (), weights)
    kind = expression.type.of
    return Call(expression.family, tuple(constant(value, kind) for value in expression.params))


def _apply(node, keys):
    op, args = node.op, node.args
    if op in _BINARY:
        return Op(_BINARY[op], build(args[0], keys), build(args[1], keys))
    if op == 'neg':
        return Neg(build(args[0], keys))
    if op == 'not':
        return Not(build(args[0], keys))
    if op in LOGIC:
        return Logic(op, tuple(build(arg, keys) for arg in args))
    if op == 'compare':
        return Cmp(tuple(node.detail), tuple(build(arg, keys) for arg in args))
    if op == 'if':
        pairs = []
        while isinstance(node, s.Apply) and node.op == 'if':
            test, body, node = node.args
            pairs.append((build(test, keys), build(body, keys)))
        return Cases(tuple(pairs), build(node, keys))
    if op == 'call':
        return Call(node.detail, tuple(build(arg, keys) for arg in args))
    raise ValueError(f'{op} is not a part of the notation')


def assignment(statement, keys):
    """The node of an assignment of a stage (`semantic.DeclaredAssign`): `x = v`, `x += v` or
    `x -= v`, whose target is a symbol. Raises ValueError for an assignment of a value that no symbol
    stands for (a setting of a flow or of an endpoint)."""
    target = keys(statement.target)
    if not isinstance(target, Sym) or not isinstance(
        statement.value, (s.Const, s.Read, s.Apply, s.Reduced, s.History, s.Drawn, s.Chosen, s.Retain)
    ):
        raise ValueError('the target of the assignment is no value of the notation')
    return Assign(target.key, statement.op, build(statement.value, keys))


class Keys:
    """The nodes of the reads of one member (`member`, a member of a card of `found`, a
    `things.Things`; None at the top level), by the keys of the picture:
    - a value is `member.name` (`places.a.need`), and a value of the top level its name;
    - a parameter or a local of an event is `member.event.name`;
    - a flow is `member.flow`, the symbol of its rate (`actual_rate`); a leg `member.flow.leg`; the
      served fraction of a flow with legs is the flow's own symbol; a result of a solver is
      `member.solver.name`;
    - `request`, `capacity`, `outflow`, `inflow`, `mean` and `std` are calls of what they read
      (`STEPS`);
    - an event is `member.event`, for `Since` and `Count`.
    A read that reaches several members (a member of a keyed collection, which only a run knows) is
    its words (`Text`), as a trigger line writes them (`triggers.namer`)."""

    def __init__(self, found, member=None):
        self.found, self.member = found, member

    @property
    def members(self):
        return () if self.member is None else (self.member,)

    def words(self, read):
        from .triggers import namer

        card = self.found.card_of.get(self.member)
        return Text(namer(self.found, card, (read,))(read))

    def __call__(self, read):
        if read.start == ('time',):
            return Time()
        if read.start == ('root',):
            return Sym(read.steps[0]) if len(read.steps) == 1 else self.words(read)
        found = self.found.reached(read, self.members)
        if found is None or found.what == 'member' or len(set(found.members)) != 1:
            return self.words(read)
        if found.what == 'local':
            template = self.found.template_of[found.members[0]]
            return Sym(f'{found.members[0]}{read.part[len(template) :]}')
        key = f'{found.members[0]}.{found.name}'
        rest = list(found.steps)
        if found.what == 'solver':
            if not rest:
                return self.words(read)
            key, rest = f'{key}.{rest[0]}', rest[1:]
        elif found.what == 'flow':
            part = self.found.part(self.found.template_of[found.members[0]], found.name)
            legs = {leg.name for leg in getattr(part, 'legs', ())}
            if isinstance(part, s.DeclaredRoute):
                legs = {'forward', 'backward'}
            if rest and rest[0] in legs:
                key, rest = f'{key}.{rest[0]}', rest[1:]
        node = Sym(key)
        for step in rest:
            if step in ('actual_rate', 'served_fraction', 'occurrences'):
                continue
            if step not in STEPS:
                return self.words(read)
            node = Call(step, (node,))
        return node

    def reduced(self, node):
        """The node of a reduction: the count of the occurrences of an event, or the reduction of the
        values of a collection whose members the model fixes (`Sum`); else its words."""
        source = node.source
        of = source.type.of if isinstance(source.type, s.Many) else None
        found = self.found.reached(source, self.members)
        if isinstance(of, s.Occ) and found is not None and found.what == 'event' and len(found.members) == 1:
            return Count(f'{found.members[0]}.{found.name}')
        if _fixed_members(source) and found is not None and found.what == 'value' and not found.steps:
            return Sum(node.op, tuple(Sym(f'{member}.{found.name}') for member in found.members))
        from .triggers import condition_words, namer

        card = self.found.card_of.get(self.member)
        return Text(condition_words(node, namer(self.found, card, (source,))))


def _fixed_members(read):
    """Whether a read of a collection names members that the model fixes: `T.instances`, a literal,
    and steps through links and collection values of them; not a `where`, a `by` or a lookup, whose
    members a run's values choose."""
    start = read.start[0]
    if start in ('where', 'by', 'lookup'):
        return False
    if start == 'literal':
        return all(_fixed_members(item) for item in read.start[1])
    return True


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
    """Where an expression is: the declared path of the part that holds it (a value, a flow, an
    endpoint, an event or a part of one, a solver's input, an assertion), what it is (`part`) and its
    line."""

    path: str
    part: str
    line: int


def walk(found) -> Iterator[tuple[Place, object]]:
    """Each expression of a model (`things.Things`), once, with its place, in written order. The
    parts: of a value, `init`, `lower` and `upper`; of an endpoint, `capacity` and `request`; of a
    flow and a leg, `request` and `capacity`; of an event, `when` (a trigger's condition), `capture`,
    `reset`, `argument`, `delay`, `guard`, `until`, `value` (of an assignment), `amount` (of a move),
    `test` (of an `if`), `selector` and `case` (a guard of a switch); `input` of a solver; `assert`;
    and `own` of a member's own value."""
    out = []

    def add(path, part, expression, line):
        if expression is not None and not isinstance(expression, (str, tuple)):
            out.append((Place(path, part, line), expression))

    def value(item):
        add(item.path, 'init', item.init, item.line)
        add(item.path, 'lower', item.lower, item.line)
        add(item.path, 'upper', item.upper, item.line)
        for side in (item.outflow, item.inflow):
            if side is not None:
                add(side.path, 'capacity', side.capacity, side.line)
                add(side.path, 'request', side.request, side.line)

    def flow(item):
        for leg in item.legs if isinstance(item, s.DeclaredLegs) else (item,):
            add(leg.path, 'request', leg.request, leg.line)
            add(leg.path, 'capacity', leg.capacity, leg.line)

    def statement(item):
        if isinstance(item, s.DeclaredAssign):
            add(item.path, 'value', item.value, item.line)
        elif isinstance(item, s.DeclaredMove):
            add(item.path, 'amount', item.amount, item.line)
        elif isinstance(item, s.DeclaredStart):
            for arg in item.args:
                add(item.path, 'argument', arg, item.line)
        elif isinstance(item, s.DeclaredIf):
            add(item.path, 'test', item.test, item.line)
        elif isinstance(item, s.DeclaredSwitch):
            add(item.path, 'selector', item.selector, item.line)
        elif isinstance(item, s.DeclaredCase):
            add(item.path, 'case', item.guard, item.line)

    for entity in found.declared.entities:
        for part in entity.parts:
            if isinstance(part, s.DeclaredValue):
                value(part)
            elif isinstance(part, (s.DeclaredFlow, s.DeclaredLegs)):
                flow(part)
            elif isinstance(part, s.DeclaredEvent):
                for trigger in part.triggers:
                    add(trigger.path, 'when', trigger.test, trigger.line)
                    for capture in trigger.captures:
                        add(capture.path, 'capture', capture.init, capture.line)
                    if trigger.reset is not None:
                        add(trigger.path, 'reset', trigger.reset[1], trigger.line)
                for local in part.locals:
                    flow(local) if isinstance(local, (s.DeclaredFlow, s.DeclaredLegs)) else value(local)
                for step in part.steps:
                    if isinstance(step, s.DeclaredGate):
                        add(step.path, 'until', step.test, step.line)
                        continue
                    add(step.path, 'delay', step.delay, step.line)
                    add(step.path, 'guard', step.guard, step.line)
                    for item in s.statements_of(step.body):
                        statement(item)
            elif isinstance(part, s.DeclaredSolver):
                for binding in part.inputs:
                    add(binding.path, 'input', binding.read, binding.line)
            elif isinstance(part, s.DeclaredAssert):
                add(part.path, 'assert', part.test, part.line)
    for item in found.declared.root:
        value(item)
    for item in found.declared.asserts:
        add(item.path, 'assert', item.test, item.line)
    for member in found.declared.members:
        for given in member.values:
            add(f'{member.path}.{given.name}', 'own', given.init, given.line)
    yield from out


def keys_of(found, place):
    """The `Keys` of the member that an expression at `place` reads from: the first member of the
    template whose part it is, or the member whose own value it is; the top level's for a value of
    the top level."""
    path = place.path
    if place.part == 'own':
        return Keys(found, path.rpartition('.')[0])
    head = next(
        (
            template
            for template in sorted(found.entities, key=len, reverse=True)
            if path.startswith(f'{template}.')
        ),
        None,
    )
    members = found.members_of(head) if head is not None else ()
    return Keys(found, members[0] if members else None)


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
