"""The equations of a card (docs/draw.md, D-53): the block of lines that the Equations panel shows for a
thing, as math trees (`notation.py`). Each tree comes from the model's own expressions, so a block
always says what the model says. The panel, the symbols and the typesetting are the callers' (E5, E2,
E4); this module makes no symbol and no SVG.

`Equations(found, run=None)` reads a model (`things.Things`) once. `block(member)` gives the block of
one member: an entity written once, a member written by hand, or one row of a table. Its keys are
those of the notation (`notation.Keys`): `member.name`. With `run`, the events that the run cannot
start are absent; without it, an event is in the block when it can start in one run or more (as
`model_map.picture`).

The lines of a block, in this order of kinds (`KINDS`), each in written order:

- `balance`: for each stock and tally, `dS/dt = Σ in − Σ out`. A term is the symbol of the rate of a
  flow that ends at S (`Term`): the flows into S, then the flows out of S, of any thing, a leg of a
  flow with legs and a flow of an event too (that one while its occurrence lasts). A route takes from
  its first end and gives to its second at its signed rate. A stock that no flow moves has
  `dS/dt = 0`: between moments it stays constant.
- `rate`: for each flow of the member, its request, `request(f) = r`: what the flow asks. Its
  capacity, its ends and the allocations of its endpoints can give it less (below). A flow with no
  request asks for nothing of its own (spec: "request … defaults to zero").
- `formula`: each formula of the member that the requests and capacities reach within `depth` hops
  of names, defined once, in the order of a breadth-first search (`hop` is its number of hops), with
  the member's own formula where it gives one. The search goes through the formulas of the member
  only; anything else is a name in the line (the Symbols table lists it).
- `bound`: for each capacity of a flow, `f ≤ c` (`|f| ≤ c` for a route); for each stock, tally and
  number state with a range, `lo ≤ S ≤ hi`. Where a flow moves S, the words say that the engine limits
  the flows at a bound (spec: "At its lower bound, total withdrawals can use simultaneous inflow");
  elsewhere a value past a bound stops the run.
- `share`: the settings of each endpoint of a store of the member: `outflow(S) ≤ c` for its capacity,
  `request(outflow(S)) = r` for its request, and `priority(f1, f2)` for an allocation by priority,
  with the words of the allocation (`priority` "shared in this order", `proportional` "shared in
  proportion to what the flows ask", the default).
- `together`: each flow with legs: the symbols of its legs, which move at one served fraction.
- `jump`: each assignment of a stage of an event, of any thing, that sets, adds to or takes from a
  value of the member: `S ← v` (`notation.assignment`); and each `move A from S to D` with an end on
  the member: `S ← S − A` and `D ← D + A`, for its ends on the member. `event` is the event's key,
  and `outcome` the case of a switch that the assignment is in, or None.
- `check`: with `checks`, each `assert` of the member's template.

Each line has its trees: `lhs` and `rhs` for a balance, a rate and a formula (`lhs = rhs`), else
`math`, a tuple. It has its few words where the math alone cannot say it (`words`), the key of the
part whose form it shows (`part`), the evidence of that part (`records`, for the reference marks),
and the keys that it names (`keys`, for the Symbols table).

Templates. `same(a, b)` says whether two blocks are the same up to their member: the blocks are
equal once each one's own keys name one placeholder. A list (`Sum`) keeps its members: it is the same
list for every member. `generic(block, name)` writes a block with `name` for its member, so
`Zone.level` for `north.level`. `together(members, name)` groups the blocks of `members` that are the
same (`Group`): each group's block is written once with the keys of `name` (a template), and its
`members` are the members that it stands for. `template(name)` does this for every member of a
template, in creation order.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace

from ..model import semantic as s
from . import notation
from .notation import (
    Assign,
    Call,
    Cmp,
    Count,
    Deriv,
    Elapsed,
    Keys,
    Neg,
    Node,
    Num,
    Op,
    Since,
    Sum,
    Sym,
    split,
)

# The kinds of line, in the order of a block, and the kinds that are equations, `lhs = rhs`.
KINDS = ('balance', 'rate', 'formula', 'bound', 'share', 'together', 'jump', 'check')
EQUATIONS = ('balance', 'rate', 'formula')
# The relations of an equation: `=`, and `⇔` for a yes/no formula.
RELATIONS = ('=', '⇔')
# The words of a line where the math alone cannot say it.
WORDS = {
    'bound_flows': 'at a bound, the flows are limited',
    'bound_stops': 'past a bound, the run stops',
    'priority': 'shared in this order',
    'proportional': 'shared in proportion to what the flows ask',
    'together': 'the legs move at one served fraction',
}
# The kinds of value that have a balance: the stocks and the tallies.
BALANCED = ('stock', 'tally')
# The placeholder of the member that `same` gives two blocks.
PLACEHOLDER = '*'


@dataclass(frozen=True)
class Term:
    """A term of a balance: the sign (+1 into the stock, -1 out of it), the flow's key, and the
    symbol of its rate."""

    sign: int
    flow: str
    node: Sym


@dataclass(frozen=True)
class Line:
    """A line of a block (see the module's text). A balance, a rate and a formula are equations,
    `lhs = rhs`, and have no `math`; every other line has its trees in `math` and no `lhs` or `rhs`.
    `flows`: of a rate and a capacity, its flow; of a share, the flows of the endpoint, in the order of
    its priority; of `together`, the legs. `hop`: of a formula, its hops from the rates. `terms`: of a
    balance, its terms, in the order of `rhs`. `relation`: of an equation, `=`, or `⇔` for a formula
    whose value is a yes/no: the formula holds exactly when its right side holds."""

    kind: str
    lhs: Node | None
    rhs: Node | None
    math: tuple
    words: str | None
    part: str | None
    records: tuple
    flows: tuple = ()
    event: str | None = None
    outcome: str | None = None
    terms: tuple = ()
    hop: int = 0
    relation: str = '='

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f'{self.kind} is not a kind of line')
        object.__setattr__(self, 'math', tuple(self.math))
        equation = self.kind in EQUATIONS
        if equation != (self.lhs is not None and self.rhs is not None) or (equation and self.math):
            raise ValueError(f'a line of kind {self.kind} has {"lhs and rhs" if equation else "math"} only')
        if not equation and not self.math:
            raise ValueError(f'a line of kind {self.kind} has its trees')
        if self.relation not in RELATIONS or (self.relation != '=' and self.kind != 'formula'):
            raise ValueError(f'a line of kind {self.kind} cannot have the relation {self.relation}')

    @property
    def trees(self):
        """Every tree of the line, in order: `lhs` and `rhs`, or `math`."""
        return (self.lhs, self.rhs) if self.kind in EQUATIONS else self.math

    @property
    def keys(self):
        """The keys of the values, flows and events that the line names, in order, each once: the
        keys of its trees. (A jump names its event in words, so its event is no key.)"""
        found = []
        for node in self.trees:
            for part in notation.nodes(node):
                key = _key_of(part)
                if key is not None and key not in found:
                    found.append(key)
        return tuple(found)


def _key_of(node):
    if isinstance(node, (Sym, Elapsed, Deriv)):
        return node.key
    if isinstance(node, (Since, Count)):
        return node.target
    if isinstance(node, Assign):
        return node.target
    return None


@dataclass(frozen=True)
class Block:
    """The block of a member: its lines, in the order of `KINDS`."""

    entity: str
    lines: tuple

    def of(self, kind):
        """The lines of one kind."""
        return tuple(line for line in self.lines if line.kind == kind)

    @property
    def keys(self):
        """The keys that the lines name, in order, each once."""
        return tuple(dict.fromkeys(key for line in self.lines for key in line.keys))


@dataclass(frozen=True)
class Group:
    """Members whose blocks are the same up to the member: the name whose keys the block writes (a
    template), the members that it stands for (`members`, in the order given), the block written once
    with the keys of `name`, and each member's own block (`blocks`, in the order of `members`)."""

    name: str
    members: tuple
    block: Block
    blocks: tuple = field(repr=False)


# ---- records ----------------------------------------------------------------------------------------


def records_of(*parts):
    """The records of the `.records` of parts, one after another, each once: None gives none, a list
    gives its records, and one record is itself."""
    found = []
    for records in parts:
        items = () if records is None else records if isinstance(records, (list, tuple)) else (records,)
        for item in items:
            if not any(item is other or item == other for other in found):
                found.append(item)
    return tuple(found)


# ---- the model ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Flow:
    """A flow of one member, with what a block needs of it: its key (`member.flow`, `member.flow.leg`
    for a leg, `member.event.flow` for a flow of an event), its member, its declared flow (a directed
    flow, a route or a leg), the flow with legs of a leg, the path of the event of a flow of an event,
    and the (member, name) of the store at each end, or None at `SOURCE` and `SINK`."""

    key: str
    member: str
    part: object
    parent: object
    event: str | None
    source: tuple | None
    sink: tuple | None


class Equations:
    """The blocks of one model (`things.Things`), for one run (`run`) or for every run joined."""

    def __init__(self, found, run=None):
        if run is not None and run not in found.runs:
            names = ', '.join(name for name in found.runs if name is not None) or 'none'
            raise ValueError(f'{run} is not a run of the model; its runs are {names}')
        self.found = found
        self.run = run
        startable = [found.startable(name) for name in ((run,) if run is not None else found.runs)]
        self.held = {
            event.path
            for card in found.cards
            for event in found.events(card)
            if any(item.get(event.path, True) for item in startable)
        }
        self.flows = [flow for card in found.cards for flow in self._flows(card)]

    def keys(self, member):
        """The `notation.Keys` of one member."""
        return Keys(self.found, member)

    def _flows(self, card):
        found = self.found
        parts = []
        for part in found.parts(card):
            if isinstance(part, (s.DeclaredFlow, s.DeclaredLegs)):
                parts.append((part.name, part, None))
            elif isinstance(part, s.DeclaredEvent) and part.path in self.held:
                for local in part.locals:
                    if isinstance(local, (s.DeclaredFlow, s.DeclaredLegs)):
                        parts.append((f'{part.name}.{local.name}', local, part.path))
        for member in found.cards[card].members:
            for name, part, event in parts:
                legs = part.legs if isinstance(part, s.DeclaredLegs) else (part,)
                for leg in legs:
                    key = f'{member}.{name}' + (f'.{leg.name}' if leg is not part else '')
                    ends = [self._end(end, member) for end in (leg.source, leg.sink)]
                    yield _Flow(key, member, leg, part if leg is not part else None, event, *ends)

    def _end(self, end, member):
        if not isinstance(end, s.Read):
            return None
        reached = self.found.reached(end, (member,))
        if reached is None or reached.what != 'value' or len(reached.members) != 1:
            return None
        return reached.members[0], reached.name

    def value(self, member, name):
        """The declared value `name` of a member's template, or None."""
        return self.found.part(self.found.template_of[member], name)

    def init(self, member, value):
        """The initializer of a value for a member: the member's own (its formula, its value), else
        its template's."""
        declared = self.found.declared.part(member)
        own = next((given for given in getattr(declared, 'values', ()) if given.name == value.name), None)
        return value.init if own is None else own.init

    # ---- a block

    def block(self, member, *, depth=1, checks=False):
        """The block of the member `member` (its id): see the module's text. `depth` is the number of
        hops of formulas from the rates (0 or more), and `checks` adds the `assert` lines of its
        template."""
        if member not in self.found.template_of:
            raise ValueError(f'{member} is not a member of the model')
        if type(depth) is not int or depth < 0:
            raise ValueError(f'depth is a whole number, 0 or more: {depth!r}')
        keys = self.keys(member)
        lines = [*self._balances(member)]
        rates, capacities = self._rates(member, keys)
        lines += rates
        lines += self._formulas(
            member, keys, [line.rhs for line in rates] + [line.math[0] for line in capacities], depth
        )
        lines += capacities + self._bounds(member)
        lines += self._shares(member, keys)
        lines += self._together(member)
        lines += self._jumps(member)
        if checks:
            lines += self._checks(member, keys)
        return Block(member, tuple(lines))

    def _balances(self, member):
        found, out = self.found, []
        for value in found.values(found.card_of[member]):
            if found.kind(value) not in BALANCED:
                continue
            key, end = f'{member}.{value.name}', (member, value.name)
            ins = [Term(1, flow.key, Sym(flow.key)) for flow in self.flows if flow.sink == end]
            outs = [Term(-1, flow.key, Sym(flow.key)) for flow in self.flows if flow.source == end]
            total = None
            for term in ins:
                total = term.node if total is None else Op('+', total, term.node)
            for term in outs:
                total = Neg(term.node) if total is None else Op('-', total, term.node)
            rhs = Num(0) if total is None else total
            out.append(Line('balance', Deriv(key), rhs, (), None, key, value.evidence, terms=(*ins, *outs)))
        return out

    def _rates(self, member, keys):
        """The request lines and the capacity lines of a member's flows, in written order."""
        rates, capacities = [], []
        for flow in self.flows:
            if flow.member != member:
                continue
            part, symbol = flow.part, Sym(flow.key)
            if part.request is not None:
                rhs = notation.build(part.request, keys)
                rates.append(
                    Line(
                        'rate',
                        Call('request', (symbol,)),
                        rhs,
                        (),
                        None,
                        flow.key,
                        part.evidence,
                        flows=(flow.key,),
                    )
                )
            if part.capacity is not None:
                size = Call('abs', (symbol,)) if isinstance(part, s.DeclaredRoute) else symbol
                math = Cmp(('<=',), (size, notation.build(part.capacity, keys)))
                capacities.append(
                    Line('bound', None, None, (math,), None, flow.key, part.evidence, flows=(flow.key,))
                )
        return rates, capacities

    def _formulas(self, member, keys, trees, depth):
        """The formulas of the member within `depth` hops of the trees of its rates, in the order of
        the search."""
        defined, out, frontier = set(), [], trees
        for hop in range(1, depth + 1):
            reached = []
            for node in frontier:
                for key in _names(node):
                    owner, name = split(key)
                    value = self.value(member, name) if owner == member else None
                    if not isinstance(value, s.DeclaredValue) or value.kind != s.FORMULA or key in defined:
                        continue
                    defined.add(key)
                    tree = notation.build(self.init(member, value), keys)
                    relation = '⇔' if value.type == s.BOOL else '='
                    out.append(
                        Line(
                            'formula',
                            Sym(key),
                            tree,
                            (),
                            None,
                            key,
                            value.evidence,
                            hop=hop,
                            relation=relation,
                        )
                    )
                    reached.append(tree)
            frontier = reached
        return out

    def _bounds(self, member):
        found, out = self.found, []
        keys = self.keys(member)
        for value in found.values(found.card_of[member]):
            kind = found.kind(value)
            if kind not in (*BALANCED, 'state') or not isinstance(value.type, s.Num):
                continue
            if value.lower is None and value.upper is None:
                continue
            key = f'{member}.{value.name}'
            symbol = Sym(key)
            low = None if value.lower is None else notation.build(value.lower, keys)
            high = None if value.upper is None else notation.build(value.upper, keys)
            if low is not None and high is not None:
                math = Cmp(('<=', '<='), (low, symbol, high))
            elif low is not None:
                math = Cmp(('>=',), (symbol, low))
            else:
                math = Cmp(('<=',), (symbol, high))
            words = WORDS['bound_flows'] if kind in BALANCED else WORDS['bound_stops']
            out.append(Line('bound', None, None, (math,), words, key, value.evidence))
        return out

    def _shares(self, member, keys):
        found, out = self.found, []
        for value in found.values(found.card_of[member]):
            store = (member, value.name)
            for side, end in ((value.outflow, 'source'), (value.inflow, 'sink')):
                if side is None:
                    continue
                total = Call('outflow' if end == 'source' else 'inflow', (Sym(f'{member}.{value.name}'),))
                math = []
                if side.capacity is not None:
                    math.append(Cmp(('<=',), (total, notation.build(side.capacity, keys))))
                if side.request is not None:
                    math.append(Cmp(('==',), (Call('request', (total,)), notation.build(side.request, keys))))
                incident = [flow.key for flow in self.flows if getattr(flow, end) == store]
                if side.allocation[0] == 'priority':
                    ranked = tuple(keys(item) for item in side.allocation[1])
                    math.append(Call('priority', ranked))
                    flows = tuple(node.key for node in ranked if isinstance(node, Sym))
                    words = WORDS['priority']
                else:
                    flows, words = tuple(incident), WORDS['proportional'] if math else None
                if math:
                    out.append(
                        Line(
                            'share',
                            None,
                            None,
                            tuple(math),
                            words,
                            side.path.replace(value.path, f'{member}.{value.name}', 1),
                            (),
                            flows=flows,
                        )
                    )
        return out

    def _together(self, member):
        out = []
        for part in self.found.parts(self.found.card_of[member]):
            if not isinstance(part, s.DeclaredLegs):
                continue
            legs = tuple(Sym(f'{member}.{part.name}.{leg.name}') for leg in part.legs)
            key = f'{member}.{part.name}'
            out.append(
                Line(
                    'together',
                    None,
                    None,
                    legs,
                    WORDS['together'],
                    key,
                    part.evidence,
                    flows=tuple(leg.key for leg in legs),
                )
            )
        return out

    def _jumps(self, member):
        """The assignments and moves of the stages of every event that can act, of any thing, that
        change a value of `member`."""
        found, out = self.found, []
        for card in found.cards:
            for event in found.events(card):
                if event.path not in self.held:
                    continue
                for owner in found.cards[card].members:
                    keys = self.keys(owner)
                    for step in event.steps:
                        if not isinstance(step, s.DeclaredStage):
                            continue
                        for statement, case in _cases(step.body, None):
                            nodes = _changed(statement, keys, member)
                            if nodes:
                                key = f'{owner}.{event.name}'
                                records = step.evidence or event.evidence
                                out.append(
                                    Line(
                                        'jump', None, None, nodes, None, key, records, event=key, outcome=case
                                    )
                                )
        return out

    def _checks(self, member, keys):
        out = []
        for part in self.found.parts(self.found.card_of[member]):
            if isinstance(part, s.DeclaredAssert):
                out.append(
                    Line('check', None, None, (notation.build(part.test, keys),), None, None, part.evidence)
                )
        return out

    # ---- templates

    def together(self, members, name, *, depth=1, checks=False):
        """The groups of `members` whose blocks are the same up to the member (`same`), in the order
        of their first members: each group's block is written with the keys of `name`."""
        groups = []
        for member in members:
            own = self.block(member, depth=depth, checks=checks)
            for k, (items, blocks, plain) in enumerate(groups):
                if plain == generic(own, PLACEHOLDER):
                    groups[k] = ((*items, member), (*blocks, own), plain)
                    break
            else:
                groups.append(((member,), (own,), generic(own, PLACEHOLDER)))
        return tuple(Group(name, items, generic(blocks[0], name), blocks) for items, blocks, _ in groups)

    def template(self, name, *, depth=1, checks=False):
        """The groups of the members of the template `name`, in creation order (`together`)."""
        if not isinstance(self.found.entities.get(name), s.DeclaredTemplate):
            raise ValueError(f'{name} is not a template of the model')
        return self.together(self.found.members_of(name), name, depth=depth, checks=checks)


def _cases(body, case):
    """(statement, the member of the innermost case of a switch that holds it, or None) of each
    statement of a body, outermost first."""
    for statement in body:
        yield statement, case
        if isinstance(statement, s.DeclaredIf):
            yield from _cases((*statement.then, *statement.orelse), case)
        elif isinstance(statement, s.DeclaredSwitch):
            for item in statement.cases:
                yield from _cases(item.body, item.member)
            yield from _cases(statement.orelse, case)


def _mine(key, member):
    return key == member or key.startswith(f'{member}.')


def _changed(statement, keys, member):
    """The trees of a statement that changes a value of `member`: an assignment's `S ← v`, and a
    move's `S ← S − A` and `D ← D + A` for its ends on the member."""
    if isinstance(statement, s.DeclaredAssign):
        try:
            node = notation.assignment(statement, keys)
        except ValueError:
            return ()
        owner, _ = split(node.target)
        return (node,) if owner == member else ()
    if isinstance(statement, s.DeclaredMove):
        amount = notation.build(statement.amount, keys)
        out = []
        for end, op in ((statement.source, '-='), (statement.destination, '+=')):
            node = keys(end)
            if isinstance(node, Sym) and split(node.key)[0] == member:
                out.append(Assign(node.key, op, amount))
        return tuple(out)
    return ()


def _names(node):
    """The keys of the values that a tree names, in order: its symbols and the members of its
    lists."""
    for part in notation.nodes(node):
        if isinstance(part, Sym):
            yield part.key


# ---- the same up to the entity -----------------------------------------------------------------------


def _renamed(key, entity, name):
    """A key of `entity` (the member itself, or a part of it) written with `name`."""
    if key == entity:
        return name
    return f'{name}{key[len(entity) :]}' if key.startswith(f'{entity}.') else key


def _rename(node, entity, name):
    """A tree with the keys of `entity` written with `name`; a list keeps its members."""
    if isinstance(node, Sum):
        return node
    if isinstance(node, (Sym, Elapsed, Deriv)):
        return replace(node, key=_renamed(node.key, entity, name))
    if isinstance(node, (Since, Count)):
        return replace(node, event=_renamed(node.event, entity, name))
    changed = {}
    for item in fields(node):
        value = getattr(node, item.name)
        if isinstance(value, (Node, tuple)):
            changed[item.name] = _rename_in(value, entity, name)
    if isinstance(node, Assign):
        changed['target'] = _renamed(node.target, entity, name)
    return replace(node, **changed) if changed else node


def _rename_in(value, entity, name):
    if isinstance(value, Node):
        return _rename(value, entity, name)
    if isinstance(value, tuple):
        return tuple(_rename_in(item, entity, name) for item in value)
    return value


def rename(node, entity, name):
    """A tree with the keys of `entity` written with `name` (`Zone.level` for `north.level`); a list
    keeps its members."""
    return _rename(node, entity, name)


def generic(found, name):
    """A block with the keys of its entity written with `name`: `Zone.level` for `north.level`. A list
    (`Sum`) keeps its members."""
    entity = found.entity

    def key(text):
        return None if text is None else _renamed(text, entity, name)

    lines = []
    for line in found.lines:
        lines.append(
            replace(
                line,
                lhs=_rename_in(line.lhs, entity, name),
                rhs=_rename_in(line.rhs, entity, name),
                math=_rename_in(line.math, entity, name),
                part=key(line.part),
                flows=tuple(key(item) for item in line.flows),
                event=key(line.event),
                terms=tuple(
                    replace(term, flow=key(term.flow), node=_rename(term.node, entity, name))
                    for term in line.terms
                ),
            )
        )
    return Block(name, tuple(lines))


def same(a, b):
    """Whether two blocks are the same up to their entities: equal once each one's own keys name one
    placeholder, with the same records and words."""
    return generic(a, PLACEHOLDER) == generic(b, PLACEHOLDER)


# ---- the functions of one block --------------------------------------------------------------------


def block(found, member, *, depth=1, checks=False, run=None):
    """The block of one member of a model (`Equations.block`)."""
    return Equations(found, run).block(member, depth=depth, checks=checks)


def template(found, name, *, depth=1, checks=False, run=None):
    """The groups of the members of a template (`Equations.template`)."""
    return Equations(found, run).template(name, depth=depth, checks=checks)


__all__ = [
    'BALANCED',
    'KINDS',
    'WORDS',
    'Block',
    'Equations',
    'Group',
    'Line',
    'Term',
    'block',
    'generic',
    'records_of',
    'rename',
    'same',
    'template',
]
