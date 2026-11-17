"""The equations of a card (docs/draw.md, D-53): the block of lines that the Equations panel shows for a
thing, as math trees (`notation.py`). Each tree comes from the model's own expressions, so a block
always says what the model says. The panel, the symbols and the typesetting are the callers' (E5, E2,
E4); this module makes no symbol and no SVG.

`Equations(model, run=None)` reads a model once. `block(entity)` gives the block of one entity: an
entity, an instance of a template, or one copy of a set. Its keys are those of the notation:
`entity.member`, with the entity as the semantic model names it (`waves.1`). With `run`, the parts
that the structure of the run leaves out are absent; without it, a part is in the block when it can
act in one run or more (as `model_map.picture`).

The lines of a block, in this order of kinds (`KINDS`), each in the order of the file:

- `balance`: for each stock and tally, `dS/dt = Σ in − Σ out`. A term is the symbol of the rate of a
  pair of a flow that ends on S (`Term`): the symbols of the pairs into S, then of the pairs out of S.
  A pair with a rate of its own has the key `entity.flow[k]` (`pair_key`, k from 0 as the structure
  numbers the pairs); every other pair moves at the flow's rate, `entity.flow`. A stock that no flow
  moves has `dS/dt = 0`: between moments it stays constant (docs/engine.md, "Values that only rules
  set").
- `rate`: for each flow, `f = rate`, with its `while` as `Cases` (the rate while C holds, else 0, as
  the builder writes it); and for each pair with a rate of its own, `f[k] = rate`. A rate that is
  one bare name of a formula of the same entity, without `while`, takes the formula's symbol and its
  line: the line is `D = <the formula>`, and `flows` lists each flow and pair that moves at D. The
  rate of a flow is what the flow asks: a share and a bound can give it less (below).
- `formula`: each formula of the entity that the rates reach within `depth` hops of names, defined
  once, in the order of a breadth-first search (`hop` is its number of hops). The search goes
  through the formulas of the entity only. A formula of another entity is a name in the line and
  the line of that entity's block; inputs, states and the formulas deeper than `depth` are names
  too (the Symbols table lists them).
- `bound`: for each stock and tally, and each number state with a bound in the file:
  `lo ≤ S ≤ hi`, with the stock's and the tally's `0` when the file gives no minimum. Where a flow
  moves S, the words say that the engine limits the flows at a bound (docs/engine.md, "At a bound":
  "Material that cannot move is limited, never lost: a flow out of an empty stock gets only what
  flows in, and a flow into a full stock is cut."). Elsewhere a value past a bound stops the run
  ("Checks": "A quantity below `min` or above `max` by more than its tolerance stops the run").
  The `size` is not a bound: it scales the solver's tolerance only ("Sizes").
- `share`: each `share` of the entity: the flows that take from its stock add up to at most its
  limit, `f1 + f2 ≤ L` ("the most that the group gives out per hour"), in the listed order or in
  proportion to what they ask (docs/engine.md, "Allocation").
- `together`: each flow of several pairs: the symbols of its pairs, which move by one fraction
  ("Coupling": "when one flow is cut, every flow of the group is cut by the same fraction").
- `jump`: each line of an event, of any entity, that sets, adds to or takes from a value of the
  entity: `S ← v` (`notation.assignment`); and each `move A from S to D` with an end on the entity:
  `S ← S − A` and `D ← D + A`, for its ends on the entity. `event` is the event's key, and `outcome`
  the outcome's name when the event has more than one.
- `check`: with `checks`, each `assert` of the entity: its condition, or for a sum
  `|a + b − T| ≤ d` with `within d` and `a + b = T` without it.

Each line has its trees: `lhs` and `rhs` for a balance, a rate and a formula (`lhs = rhs`), else
`math`, a tuple (most lines have one tree; a move with both ends on the entity has two, and
`together` lists its symbols). It has its few words where the math alone cannot say it (`words`),
the key of the part whose form it shows (`part`), the records of that part (`records`, for the
reference marks: of a rate line that a formula takes, the formula's records and then those of each
flow that moves at it), and the keys that it names (`keys`, for the Symbols table).

Templates. `same(a, b)` says whether two blocks are the same up to their entity: the blocks are
equal once each one's own keys name one placeholder. A list (`Sum`) keeps its members: it is the same
list for every instance. `generic(block, name)` writes a block with `name` for its entity, so
`Zone.level` for `north.level`. `together(entities, name)` groups the blocks of `entities` that are
the same (`Group`): each group's block is written once with the keys of `name` (a template), and its
`members` are the entities that it stands for. `template(name)` does this for every instance of a
template, in the order of the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace

from ..model import resolved
from ..model.semantic import Assign as AssignLine
from ..model.semantic import Move, Problem, Ref, flat_entity
from . import notation
from .notation import (
    Assign,
    Call,
    Cases,
    Cmp,
    Count,
    Deriv,
    Elapsed,
    Neg,
    Node,
    Num,
    Op,
    Since,
    Sum,
    Sym,
    key_of,
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
    'together': 'the pairs move by one fraction',
}
# The kinds of value that have a balance: the stocks and the tallies.
BALANCED = ('stock', 'tally')
# The placeholder of the entity that `same` gives two blocks.
PLACEHOLDER = '*'


def pair_key(flow, k):
    """The key of pair k (from 0) of the flow `flow` (`entity.flow`), whose rate is its own."""
    return f'{flow}[{k}]'


@dataclass(frozen=True)
class Term:
    """A term of a balance: the sign (+1 into the stock, -1 out of it), the flow (`entity.flow`), the
    number of its pair (from 0), and the symbol of the pair's rate."""

    sign: int
    flow: str
    pair: int
    node: Sym


@dataclass(frozen=True)
class Line:
    """A line of a block (see the module's text). A balance, a rate and a formula are equations,
    `lhs = rhs`, and have no `math`; every other line has its trees in `math` and no `lhs` or `rhs`.
    (A definition is no comparison: `Cmp` would put a right side of lower precedence, such as
    `Cases`, in parentheses.) `flows`: of a rate line, what moves at its rate: a flow
    (`entity.flow`, each of its pairs without a rate of its own) or a pair with its own rate
    (`entity.flow[k]`); of a share, the pairs that take from its stock, in the order of the share;
    of `together`, the pairs of the flow. A pair of a share or of `together` is `entity.flow` for a
    flow of one pair, else `entity.flow[k]`. `hop`: of a formula, its hops from the rates. `terms`:
    of a balance, its terms, in the order of `rhs`. `relation`: of an equation, `=`, or `⇔` for a
    formula whose value is a yes/no: the formula holds exactly when its right side holds."""

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
        """The keys of the values, flows, events and outcomes that the line names, in order, each
        once: the keys of its trees. (A jump names its event in words, so its event is no key.)"""
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
    """The block of an entity: its lines, in the order of `KINDS`."""

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
    """Entities whose blocks are the same up to the entity: the name whose keys the block writes (a
    template), the entities that it stands for (`members`, in the order given), the block written
    once with the keys of `name`, and each member's own block (`blocks`, in the order of
    `members`)."""

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
class _Pair:
    """A pair of a flow, with what a block needs of it."""

    entity: str
    flow: object  # semantic.Flow
    k: int
    pair: object  # semantic.Pair
    ends: dict  # {'from' or 'to': the key of the value}
    symbol: Sym  # the symbol of its rate
    taken: str | None  # the key of the formula whose symbol and line its rate takes, or None
    fid: str  # its name in the structure

    @property
    def key(self):
        """The key of the flow, or of the pair when its rate is its own."""
        flow = key_of(self.entity, self.flow.name)
        return flow if self.pair.rate is None else pair_key(flow, self.k)

    @property
    def member(self):
        """The name of the pair itself: the flow's key for a flow of one pair, else `entity.flow[k]`."""
        flow = key_of(self.entity, self.flow.name)
        return flow if len(self.flow.pairs) == 1 else pair_key(flow, self.k)


class Equations:
    """The blocks of one model, for one run (`run`) or for every run joined."""

    def __init__(self, model, run=None):
        if run is not None and run not in model.runs:
            raise ValueError(f'{run} is not a run of the model; its runs are {", ".join(model.runs)}')
        self.model = model
        self.scenario = model.scenario
        self.run = run
        starts = dict.fromkeys(model.runs[name]['starts'] for name in ([run] if run else model.runs))
        self.structures = [model.structures[key] for key in starts]
        self.entities = {entity.name: entity for entity in self.scenario.entities}
        self.values = {
            key_of(entity.name, value.name): (entity, value)
            for entity in self.scenario.entities
            for value in entity.values
        }
        self.pairs = [pair for entity in self.scenario.entities for pair in self._pairs(entity)]
        self.jumps = self._jumps()

    # ---- what the runs hold

    def holds(self, section, name):
        """Whether a structure of the runs holds `name` in `section`."""
        return any(name in structure.section(section) for structure in self.structures)

    def holds_pair(self, pair):
        """Whether a structure of the runs holds a pair: a flow, or the rate of a tally."""
        return any(
            pair.fid in structure.flows or any(pair.fid in rate.flows for rate in structure.rates.values())
            for structure in self.structures
        )

    def holds_value(self, entity, value):
        """Whether a structure of the runs holds a value: a stock, tally or number state, or a formula
        (the builder writes a bool formula into its readers, so it is held while its entity is)."""
        name = f'{flat_entity(entity.name)}.{value.name}'
        if value.kind == 'formula':
            return self.holds('computed', name) or self.holds('entities', flat_entity(entity.name))
        return self.holds('quantities', name)

    # ---- the parts of the model

    def formula(self, key):
        """The value of a key when it is a formula with its expression, else None."""
        found = self.values.get(key)
        if found is None:
            return None
        value = found[1]
        return value if value.kind == 'formula' and value.formula is not None else None

    def _taken(self, entity, flow, rate):
        """The key of the formula whose symbol a rate takes: one bare name of a formula of the flow's
        own entity, without `while`; else None."""
        node = getattr(rate, 'node', None)
        if flow.condition is not None or not isinstance(node, resolved.Ref) or node.entity != entity.name:
            return None
        key = key_of(node.entity, node.member)
        return key if self.formula(key) is not None else None

    def _pairs(self, entity):
        host = flat_entity(entity.name)
        for flow in entity.flows:
            several = len(flow.pairs) > 1
            for k, pair in enumerate(flow.pairs):
                ends = {end: key_of(ref.entity, ref.member) for end, ref in pair.ends if isinstance(ref, Ref)}
                taken = self._taken(entity, flow, pair.rate if pair.rate is not None else flow.rate)
                if taken is not None:
                    symbol = Sym(taken)
                elif pair.rate is not None:
                    symbol = Sym(pair_key(key_of(entity.name, flow.name), k))
                else:
                    symbol = Sym(key_of(entity.name, flow.name))
                fid = f'{host}.{flow.name}' + (f'.{k}' if several else '')
                yield _Pair(entity.name, flow, k, pair, ends, symbol, taken, fid)

    def _jumps(self):
        """{entity: [(event entity, event, outcome, the line's trees)]}: the lines of the events that
        change a value of each entity, in the order of the model."""
        found = {}
        for owner in self.scenario.entities:
            for event in owner.events:
                for outcome in event.outcomes:
                    for line in outcome.lines:
                        for target, node in _changes(line):
                            found.setdefault(target, []).append((owner, event, outcome, node))
        return found

    # ---- a block

    def block(self, entity, *, depth=1, checks=False):
        """The block of the entity `entity` (its name in the semantic model): see the module's text.
        `depth` is the number of hops of formulas from the rates (0 or more), and `checks` adds the
        entity's `assert` lines."""
        if entity not in self.entities:
            raise ValueError(f'{entity} is not an entity of the model')
        if type(depth) is not int or depth < 0:
            raise ValueError(f'depth is a whole number, 0 or more: {depth!r}')
        thing = self.entities[entity]
        lines = []
        lines += self._balances(thing)
        rates = self._rates(thing)
        lines += rates
        lines += self._formulas(thing, rates, depth)
        lines += self._bounds(thing)
        lines += self._shares(thing)
        lines += self._together(thing)
        lines += self._jump_lines(thing)
        if checks:
            lines += self._checks(thing)
        return Block(entity, tuple(lines))

    def _balances(self, thing):
        out = []
        for value in thing.values:
            if value.kind not in BALANCED or not self.holds_value(thing, value):
                continue
            key = key_of(thing.name, value.name)
            ins, outs = [], []
            for pair in self.pairs:
                if not self.holds_pair(pair):
                    continue
                if pair.ends.get('to') == key:
                    ins.append(Term(1, key_of(pair.entity, pair.flow.name), pair.k, pair.symbol))
                if pair.ends.get('from') == key:
                    outs.append(Term(-1, key_of(pair.entity, pair.flow.name), pair.k, pair.symbol))
            sum_ = None
            for term in ins:
                sum_ = term.node if sum_ is None else Op('+', sum_, term.node)
            for term in outs:
                sum_ = Neg(term.node) if sum_ is None else Op('-', sum_, term.node)
            rhs = Num(0) if sum_ is None else sum_
            records = records_of(value.records)
            out.append(Line('balance', Deriv(key), rhs, (), None, key, records, terms=(*ins, *outs)))
        return out

    def _rates(self, thing):
        """The rate lines of an entity's flows, in the order of the file; a formula that rates take is
        one line, where the first of them is."""
        out, taken = [], {}
        for pair in self.pairs:
            if pair.entity != thing.name or not self.holds_pair(pair):
                continue
            flow, own = pair.flow, pair.pair.rate is not None
            if not own and pair.k != min(k for k, item in enumerate(flow.pairs) if item.rate is None):
                continue  # the pairs that move at the flow's rate share the flow's line
            records = records_of(pair.pair.records if own else None) or records_of(flow.records)
            if pair.taken is not None:
                line = taken.get(pair.taken)
                if line is None:
                    _, formula = self.values[pair.taken]
                    rhs = notation.build(formula.formula)
                    line = taken[pair.taken] = len(out)
                    out.append(
                        Line('rate', Sym(pair.taken), rhs, (), None, pair.taken, records_of(formula.records))
                    )
                found = out[line]
                out[line] = replace(
                    found,
                    flows=(*found.flows, pair.key),
                    records=records_of(found.records, records),
                )
                continue
            rate = notation.build(pair.pair.rate if own else flow.rate)
            if flow.condition is not None:
                rate = Cases(((notation.build(flow.condition), rate),), Num(0))
            out.append(Line('rate', pair.symbol, rate, (), None, pair.key, records, flows=(pair.key,)))
        return out

    def _formulas(self, thing, rates, depth):
        """The formulas of the entity within `depth` hops of the rates, in the order of the search."""
        defined = {line.part for line in rates}
        out = []
        frontier = [line.rhs for line in rates]
        for hop in range(1, depth + 1):
            reached = []
            for node in frontier:
                for key in _names(node):
                    value = self.formula(key)
                    entity, _ = split(key)
                    if value is None or entity != thing.name or key in defined:
                        continue
                    if not self.holds_value(thing, value):
                        continue
                    defined.add(key)
                    tree = notation.build(value.formula)
                    records = records_of(value.records)
                    relation = '⇔' if value.type == 'bool' else '='
                    out.append(
                        Line('formula', Sym(key), tree, (), None, key, records, hop=hop, relation=relation)
                    )
                    reached.append(tree)
            frontier = reached
        return out

    def _bounds(self, thing):
        out = []
        for value in thing.values:
            numeric = value.kind in BALANCED or (
                value.kind == 'state' and value.type != 'bool' and not isinstance(value.type, tuple)
            )
            if not numeric or not self.holds_value(thing, value):
                continue
            key = key_of(thing.name, value.name)
            low = notation.build(value.minimum.expression) if value.minimum is not None else None
            if low is None and value.kind in BALANCED:
                low = Num(0)  # a stock and a tally never go below 0 (docs/language.md, §2.4)
            high = notation.build(value.maximum.expression) if value.maximum is not None else None
            if low is None and high is None:
                continue
            symbol = Sym(key)
            if low is not None and high is not None:
                math = Cmp(('<=', '<='), (low, symbol, high))
            elif low is not None:
                math = Cmp(('>=',), (symbol, low))
            else:
                math = Cmp(('<=',), (symbol, high))
            moved = any(
                key in pair.ends.values()
                and any(pair.fid in structure.flows for structure in self.structures)
                for pair in self.pairs
            )
            written = value.minimum is not None or value.maximum is not None
            records = records_of(value.records) if written else ()
            words = WORDS['bound_flows'] if moved else WORDS['bound_stops']
            out.append(Line('bound', None, None, (math,), words, key, records))
        return out

    def _shares(self, thing):
        out = []
        host = flat_entity(thing.name)
        for allocation in thing.allocations:
            stock = allocation.stock
            if not isinstance(stock, Ref) or not self.holds('allocation', f'{host}.{allocation.name}'):
                continue
            source = key_of(stock.entity, stock.member)
            members = [
                pair for pair in self.pairs if pair.ends.get('from') == source and self.holds_pair(pair)
            ]
            if allocation.serve is not None:
                order = []
                for _, owner, name, _ in allocation.serve:
                    order += [pair for pair in members if (pair.entity, pair.flow.name) == (owner, name)]
                members = order
            if not members:
                continue
            total = None
            for pair in members:
                total = pair.symbol if total is None else Op('+', total, pair.symbol)
            math = Cmp(('<=',), (total, notation.build(allocation.limit)))
            words = WORDS['proportional' if allocation.serve is None else 'priority']
            out.append(
                Line(
                    'share',
                    None,
                    None,
                    (math,),
                    words,
                    key_of(thing.name, allocation.name),
                    records_of(allocation.records),
                    flows=tuple(pair.member for pair in members),
                )
            )
        return out

    def _together(self, thing):
        out = []
        host = flat_entity(thing.name)
        for flow in thing.flows:
            if len(flow.pairs) < 2 or not self.holds('coupling', f'{host}.{flow.name}'):
                continue
            pairs = [
                pair
                for pair in self.pairs
                if (pair.entity, pair.flow.name) == (thing.name, flow.name) and self.holds_pair(pair)
            ]
            symbols = tuple(dict.fromkeys(pair.symbol for pair in pairs))
            records = records_of(flow.together.value if flow.together is not None else None)
            out.append(
                Line(
                    'together',
                    None,
                    None,
                    symbols,
                    WORDS['together'],
                    key_of(thing.name, flow.name),
                    records,
                    flows=tuple(pair.member for pair in pairs),
                )
            )
        return out

    def _jump_lines(self, thing):
        out = []
        for owner, event, outcome, nodes in self.jumps.get(thing.name, ()):
            if not self.holds('rules', f'{flat_entity(owner.name)}.{event.name}'):
                continue
            records = records_of(outcome.records if outcome.records is not None else event.records)
            out.append(
                Line(
                    'jump',
                    None,
                    None,
                    nodes,
                    None,
                    key_of(owner.name, event.name),
                    records,
                    event=key_of(owner.name, event.name),
                    outcome=outcome.name if len(event.outcomes) > 1 else None,
                )
            )
        return out

    def _checks(self, thing):
        if not self.holds('entities', flat_entity(thing.name)):
            return []
        out = []
        for check in thing.checks:
            if check.kind == 'sum':
                total = None
                for ref in check.parts:
                    term = Sym(key_of(ref.entity, ref.member), ref.written)
                    total = term if total is None else Op('+', total, term)
                whole = notation.build(check.total)
                if check.within is None:
                    math = Cmp(('==',), (total, whole))
                else:
                    gap = Call('abs', (Op('-', total, whole),))
                    math = Cmp(('<=',), (gap, notation.build(check.within)))
            else:
                math = notation.build(check.condition)
            out.append(Line('check', None, None, (math,), None, None, records_of(check.records)))
        return out

    # ---- templates

    def together(self, entities, name, *, depth=1, checks=False):
        """The groups of `entities` whose blocks are the same up to the entity (`same`), in the order
        of their first members: each group's block is written with the keys of `name`."""
        groups = []
        for entity in entities:
            own = self.block(entity, depth=depth, checks=checks)
            for k, (members, blocks, plain) in enumerate(groups):
                if plain == generic(own, PLACEHOLDER):
                    groups[k] = ((*members, entity), (*blocks, own), plain)
                    break
            else:
                groups.append(((entity,), (own,), generic(own, PLACEHOLDER)))
        return tuple(Group(name, members, generic(blocks[0], name), blocks) for members, blocks, _ in groups)

    def template(self, name, *, depth=1, checks=False):
        """The groups of the instances of the template `name`, copies included, in the order of the
        model (`together`)."""
        if name not in self.scenario.templates:
            raise ValueError(f'{name} is not a template of the model')
        members = [entity.name for entity in self.scenario.entities if entity.template == name]
        return self.together(members, name, depth=depth, checks=checks)


def _changes(line):
    """[(the entity, the trees)] of a line of an event: the entity whose value an assignment changes,
    and the entities of the ends of a move with the trees of their ends (`S ← S − A`, `D ← D + A`)."""
    if isinstance(line, AssignLine):
        if isinstance(line.target, Ref):
            return [(line.target.entity, (notation.assignment(line),))]
        return []
    if not isinstance(line, Move):
        return []
    amount = notation.build(line.amount)
    found = {}
    for (_, end), op in zip(line.ends, ('-=', '+=')):
        if isinstance(end, Ref) and not isinstance(end, Problem):
            node = Assign(key_of(end.entity, end.member), op, amount, end.written)
            found.setdefault(end.entity, []).append(node)
    return [(entity, tuple(nodes)) for entity, nodes in found.items()]


def _names(node):
    """The keys of the values that a tree names, in order: its symbols and the members of its
    lists."""
    for part in notation.nodes(node):
        if isinstance(part, Sym):
            yield part.key


# ---- the same up to the entity -----------------------------------------------------------------------


def _renamed(key, entity, name):
    owner, member = split(key)
    return key_of(name, member) if owner == entity else key


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


def block(model, entity, *, depth=1, checks=False, run=None):
    """The block of one entity of `model` (`Equations.block`)."""
    return Equations(model, run).block(entity, depth=depth, checks=checks)


def template(model, name, *, depth=1, checks=False, run=None):
    """The groups of the instances of a template (`Equations.template`)."""
    return Equations(model, run).template(name, depth=depth, checks=checks)


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
    'pair_key',
    'records_of',
    'same',
    'template',
]
