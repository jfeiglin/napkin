"""The compiled model as typed parts, and the queries that the engine, the reports, the pictures and the
tools ask of it.

A `Structure` is the model for one set of start-state options: each part of the model once, as an
immutable record, in the compiled order. A `Resolved` is a structure with the values of one run. They
take the place of the nested mappings that the builder makes (`lower/builder.py`): a consumer reads
`structure.flows[name].rate`, never a key of a mapping, so the way the model is kept can change under
it. Until the lowering makes these records itself, `Structure.of` and
`Resolved.of` read them from the builder's mappings. The build reads each mapping that the builder
derives into typed parts at once (`model.typed_of`) and keeps only the typed parts: no reader outside
the lowering gets a mapping of the builder.

The contract:

- **Nothing is lost.** `of` raises `StructureError` for a key that no field takes, and for a field
  that must be there and is not. `plain()` writes the mapping again, with the same keys in the same
  order: a record keeps the order of the keys that it was read from. A record that was not read from
  a mapping (a changed copy) writes its fields in their order, and leaves out an optional field that
  has no value.
- **The order is the compiled order.** Each kind of part is a read-only mapping from the name to the
  record, in the builder's order: quantities by the name of their thing, flows by name, rules by
  line, file and copy. `moment_order` gives the rules as one moment reads them.
- **A record is immutable**, and so is each mapping and each list in it. A step that today writes into
  a structure makes a new record (`dataclasses.replace`).
- **An expression is its typed node** (`Source`: a node of `napkin/core/expr`, or the number or the
  yes/no that it is). The lowering writes each node into its mapping, and a record holds that node.
  `plain()` writes the text of the node (`str(node)`), and `of` reads such a text into its node
  again: the same node. The chance of the outcome that takes what the other chances leave is the
  word `else`.
- **Evidence** (`basis`) and free notes (`metadata`) are plain immutable data, as the builder writes
  them: a mapping, or a list of mappings.

The names of the fields are the keys of the mappings, with four exceptions that are words of Python
or of its library: `from` is `source`, `to` is `target`, `min` is `minimum` and `max` is `maximum`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar

from ..core import expr as nodes
from ..expressions import names_in

# An expression of a part: its typed node (`napkin/core/expr`), or the number or the yes/no that it
# is. The builder writes the node into its mapping, and a record holds it (`Part.of`); the plain
# data of a record writes the text of the node (`plain`), which `Part.of` reads into the node again.
Source = nodes.Node | int | float | bool
# For each class of record, {field: how} of its fields that hold expressions: one expression
# ('one'), a list of them ('list') or a mapping to them ('map').
SOURCES = {}
# The words that a mapping writes in the place of an expression: the chance of the outcome that
# takes what the chances of the other outcomes leave.
WORDS = frozenset({'else'})

RENAMES = {'from': 'source', 'to': 'target', 'min': 'minimum', 'max': 'maximum'}
BACK = {new: old for old, new in RENAMES.items()}
EMPTY = MappingProxyType({})
# Each order of keys that a record was read from, once: the records of one kind share a few orders.
ORDERS = {}


class StructureError(ValueError):
    """A mapping of the builder that the typed parts cannot take whole, or a part that is not there."""


def frozen(value):
    """Plain data made immutable: each mapping read-only, each list a tuple."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: frozen(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(frozen(item) for item in value)
    return value


def sources(cls):
    """{field: how} of the fields of a class of record that hold expressions (`SOURCES`)."""
    found = SOURCES.get(cls)
    if found is None:
        found = SOURCES[cls] = {}
        for item in dataclasses.fields(cls):
            written = item.type if isinstance(item.type, str) else getattr(item.type, '__name__', '')
            if 'Source' in written:
                how = (
                    'list'
                    if written.startswith('tuple[')
                    else 'map'
                    if written.startswith('Mapping[')
                    else 'one'
                )
                found[item.name] = how
    return found


def node_of(value, where):
    """The node of an expression that a mapping writes as its text; a number, a yes/no and a node
    are what they are."""
    if type(value) is not str or value in WORDS:
        return value
    try:
        return nodes.read(value)
    except (nodes.ExpressionError, SyntaxError, RecursionError, ValueError) as exc:
        raise StructureError(f'{where}: {value!r} is no expression: {exc}') from None


def node(source):
    """The node of an expression of a part: a number or a yes/no is the node of its text."""
    return source if isinstance(source, nodes.Node) else nodes.read(source)


def thawed(value, written=True):
    """Immutable data as plain data again: each mapping a dict, each tuple a list, and each
    expression its text, or its node when not `written`."""
    if isinstance(value, nodes.Node):
        return nodes.text(value) if written else value
    if isinstance(value, (Part, Structure)):
        return value.plain(written)
    if isinstance(value, Mapping):
        return {key: thawed(item, written) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thawed(item, written) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Part:
    """One record of the model. A subclass names its fields; `NESTED` names the fields that hold
    records, as `(how, class)` with `how` one of `one`, `list` and `map`; `OPTIONAL` names the fields
    that the builder leaves out when they have no value."""

    NESTED: ClassVar[Mapping[str, tuple[str, type]]] = EMPTY
    OPTIONAL: ClassVar[frozenset[str]] = frozenset()
    # The keys of the mapping that the record was read from, in their order. It is no argument: a
    # record that is made in another way has none.
    _order: tuple | None = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def of(cls, item, where=''):
        """The record of one mapping of the builder. `where` says which part it is, for an error."""
        if not isinstance(item, Mapping):
            raise StructureError(f'{where or cls.__name__}: a {cls.__name__} is a mapping, not {item!r}')
        names = {f.name for f in dataclasses.fields(cls) if f.init}
        expressions = sources(cls)
        found = {}
        for key, value in item.items():
            name = RENAMES.get(key, key)
            if name not in names:
                raise StructureError(f'{where or cls.__name__}: {cls.__name__} has no field for {key!r}')
            how, kind = cls.NESTED.get(name, (None, None))
            place = f'{where}/{key}'
            if value is None:
                found[name] = None
            elif name in expressions:
                kind = expressions[name]
                if kind == 'one':
                    found[name] = node_of(value, place)
                elif kind == 'list':
                    found[name] = tuple(node_of(entry, f'{place}[{k}]') for k, entry in enumerate(value))
                else:
                    found[name] = MappingProxyType(
                        {k: node_of(entry, f'{place}/{k}') for k, entry in value.items()}
                    )
            elif how is None:
                found[name] = frozen(value)
            elif how == 'one':
                found[name] = kind.of(value, place)
            elif how == 'list':
                found[name] = tuple(kind.of(entry, f'{place}[{k}]') for k, entry in enumerate(value))
            else:
                found[name] = MappingProxyType(
                    {k: kind.of(entry, f'{place}/{k}') for k, entry in value.items()}
                )
        missing = [
            BACK.get(f.name, f.name)
            for f in dataclasses.fields(cls)
            if f.init
            and f.name not in found
            and f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING
        ]
        if missing:
            raise StructureError(f'{where or cls.__name__}: {cls.__name__} lacks {", ".join(missing)}')
        record = cls(**found)
        object.__setattr__(record, '_order', ORDERS.setdefault(tuple(item), tuple(item)))
        return record

    def plain(self, written=True):
        """The mapping of the builder again: the keys that the record was read from, in their order.
        A record that was not read from a mapping writes its fields in their order, and leaves out an
        optional field that has no value. Each expression is its text, or its node when not
        `written`."""
        if self._order is not None:
            return {key: thawed(getattr(self, RENAMES.get(key, key)), written) for key in self._order}
        out = {}
        for f in dataclasses.fields(self):
            if f.name == '_order':
                continue
            value = getattr(self, f.name)
            if value is None and f.name in self.OPTIONAL:
                continue
            out[BACK.get(f.name, f.name)] = thawed(value, written)
        return out

    def changed(self, **fields):
        """A copy with some fields changed. It keeps the order of the keys that the record was read
        from, with each new key after them; use it in place of `dataclasses.replace`, which loses that
        order."""
        copy = dataclasses.replace(self, **fields)
        if self._order is not None:
            new = [BACK.get(name, name) for name, value in fields.items() if value is not None]
            kept = [
                key
                for key in self._order
                if RENAMES.get(key, key) not in fields or getattr(copy, RENAMES.get(key, key)) is not None
            ]
            order = (*kept, *(key for key in new if key not in kept))
            object.__setattr__(copy, '_order', ORDERS.setdefault(order, order))
        return copy


def parts(kind, items, where):
    """{name: record} of one kind of part, read-only, in the order of `items`."""
    return MappingProxyType({name: kind.of(item, f'{where}/{name}') for name, item in items.items()})


# ---- the parts ------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Sight(Part):
    """One thing that an actor sees when it decides: an event, or a value as an expression with how a
    decision shows it (`kind`): the value of a named state (`state`), of a named input (`choice`, with
    its `values`), a yes/no (`bool`), or a number in its unit (`number`; the unit can be none)."""

    name: str
    kind: str | None = None
    expr: Source | None = None
    unit: str | None = None
    event: str | None = None
    values: tuple[str, ...] | None = None
    OPTIONAL: ClassVar = frozenset({'kind', 'expr', 'unit', 'event', 'values'})

    def plain(self, written=True):
        out = Part.plain(self, written)
        if self._order is None and self.kind == 'number':
            out['unit'] = self.unit  # the builder writes the unit of a number, also when it has none
        return out


@dataclass(frozen=True, slots=True)
class Entity(Part):
    """A thing of the model: its label, its kind, the copy that it is of a template, its named states,
    and, for an actor, what it sees."""

    label: str
    kind: str
    metadata: Any
    basis: Any
    origin: str
    copy: int | None
    modes: tuple[str, ...]
    health: str | None
    sees: tuple[Sight, ...] | None
    NESTED: ClassVar = MappingProxyType({'sees': ('list', Sight)})


@dataclass(frozen=True, slots=True)
class Adjust(Part):
    """How an edit can change an input: its mode, its range when it has one, and the records that
    support the limits of the range, when the model gives any."""

    mode: str
    minimum: float | None = None
    maximum: float | None = None
    basis: Any = None
    OPTIONAL: ClassVar = frozenset({'minimum', 'maximum', 'basis'})


@dataclass(frozen=True, slots=True)
class Parameter(Part):
    """An input: its central value in its unit, and how an edit can change it."""

    entity: str
    label: str
    unit: str
    value: Any
    adjust: Adjust
    basis: Any
    path: str
    metadata: Any = None
    NESTED: ClassVar = MappingProxyType({'adjust': ('one', Adjust)})
    OPTIONAL: ClassVar = frozenset({'metadata'})


@dataclass(frozen=True, slots=True)
class Quantity(Part):
    """A number that the run changes: a stock, a tally (`cumulative`) or a number that only rules set
    (`variable`), with its start, its bounds and its size."""

    entity: str
    kind: str
    unit: str
    initial: Source
    basis: Any
    path: str
    label: str | None = None
    minimum: Source | None = None
    maximum: Source | None = None
    size: Source | None = None
    binary: bool | None = None
    OPTIONAL: ClassVar = frozenset({'label', 'minimum', 'maximum', 'size', 'binary'})


@dataclass(frozen=True, slots=True)
class Computed(Part):
    """A formula: a value that its expression gives at each time."""

    entity: str
    expr: Source
    unit: str
    basis: Any
    path: str
    label: str | None = None
    OPTIONAL: ClassVar = frozenset({'label'})


@dataclass(frozen=True, slots=True)
class LabelCase(Part):
    """One case of a status: the value and the words that it has while its condition holds."""

    when: Source
    value: str
    text: str
    path: str


@dataclass(frozen=True, slots=True)
class LabelDefault(Part):
    """The value and the words of a status when no case holds."""

    value: str
    text: str


@dataclass(frozen=True, slots=True)
class Label(Part):
    """A status: the first case that holds, or the default."""

    entity: str
    cases: tuple[LabelCase, ...]
    default: LabelDefault
    basis: Any
    path: str
    label: str | None
    NESTED: ClassVar = MappingProxyType({'cases': ('list', LabelCase), 'default': ('one', LabelDefault)})


@dataclass(frozen=True, slots=True)
class Mode(Part):
    """A named state: its values and the one that it starts in."""

    entity: str
    initial: str
    values: tuple[str, ...]
    path: str
    label: str | None = None
    basis: Any = None
    OPTIONAL: ClassVar = frozenset({'label', 'basis'})


@dataclass(frozen=True, slots=True)
class Link(Part):
    """A part of another thing that a thing names: what it reaches, and how."""

    kind: str
    target: Any
    basis: Any


@dataclass(frozen=True, slots=True)
class Flow(Part):
    """A flow: from one quantity to another, or from or to outside the model (no `source`, or no
    `target`), at its rate, in the share (`allocation`) of the stock that it drains, if that has one."""

    entity: str
    rate: Source
    basis: Any
    path: str
    source: str | None = None
    target: str | None = None
    label: str | None = None
    allocation: str | None = None
    OPTIONAL: ClassVar = frozenset({'source', 'target', 'label', 'allocation'})


@dataclass(frozen=True, slots=True)
class Rate(Part):
    """What fills a tally from outside the model: the sum of its flows, as one expression."""

    expr: Source
    flows: tuple[str, ...]
    basis: Any
    path: str


@dataclass(frozen=True, slots=True)
class Allocation(Part):
    """A share of a stock among the flows that drain it: its limit, and its order when it serves the
    flows in order (`policy` `priority`) and not in proportion."""

    policy: str
    capacity: Source
    basis: Any
    path: str
    order: tuple[str, ...] | None = None
    OPTIONAL: ClassVar = frozenset({'order'})


@dataclass(frozen=True, slots=True)
class Coupling(Part):
    """Flows that move together: each gets the same part of what it asks."""

    flows: tuple[str, ...]
    basis: Any


@dataclass(frozen=True, slots=True)
class Event(Part):
    """An event that a rule can read: the rules and outcomes that make it happen."""

    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Trigger(Part):
    """When a rule triggers. The builder writes the condition (`when`), and the place of the
    condition (`path`) when the file writes one: an event with no condition has none. The checks of
    the structure give the rest (`analysis.structure.classify`): the place, which is that of the rule
    for an event with no condition, and the class of the condition. `kind` is `discrete`, `timer`,
    `crossing` or `face`; `gate` is the part of the condition that is no time and no crossing; `times`
    are the times of a timer; `var`, `op` and `value` are the quantity, the comparison and the level
    of a crossing; `face` the condition of a stock on its zero face."""

    when: Source
    path: str | None = None
    kind: str | None = None
    gate: Source | None = None
    times: tuple[Source, ...] | None = None
    var: str | None = None
    op: str | None = None
    value: Source | None = None
    face: Source | None = None
    OPTIONAL: ClassVar = frozenset({'path', 'kind', 'gate', 'times', 'var', 'op', 'value', 'face'})


@dataclass(frozen=True, slots=True)
class Assignment(Part):
    """What a line of an outcome sets: a number by its expression, or a named state to one value."""

    expr: Source | None = None
    mode: str | None = None
    values: tuple[str, ...] | None = None
    path: str | None = None
    OPTIONAL: ClassVar = frozenset({'expr', 'mode', 'values', 'path'})


@dataclass(frozen=True, slots=True)
class Transfer(Part):
    """What a line of an outcome moves at once: an amount from one quantity to another."""

    amount: Source
    path: str
    source: str | None = None
    target: str | None = None
    OPTIONAL: ClassVar = frozenset({'source', 'target'})


@dataclass(frozen=True, slots=True)
class Effects(Part):
    """What an outcome does: what it sets, in the order of its lines, what it moves, and the events
    that it fires."""

    set: Mapping[str, Assignment]
    transfer: tuple[Transfer, ...]
    fire: tuple[str, ...]
    NESTED: ClassVar = MappingProxyType({'set': ('map', Assignment), 'transfer': ('list', Transfer)})

    def sources(self):
        """The expressions that the step reads, in the order of its lines: each number that it sets,
        then each amount that it moves."""
        found = [item.expr for item in self.set.values() if item.expr is not None]
        return (*found, *(move.amount for move in self.transfer))

    def targets(self):
        """What the step changes: each value that it sets, and the two ends of each move."""
        found = list(self.set)
        for move in self.transfer:
            found += [move.source, move.target]
        return tuple(found)


@dataclass(frozen=True, slots=True)
class EventOutcome(Part):
    """One outcome of an event: its chance, when it is available, and what it does."""

    name: str
    chance: Source | None
    available: Source | None
    label: str | None
    basis: Any
    path: str
    do: Effects
    emits: tuple[str, ...]
    role: str | None = None
    NESTED: ClassVar = MappingProxyType({'do': ('one', Effects)})
    OPTIONAL: ClassVar = frozenset({'role'})


@dataclass(frozen=True, slots=True)
class Extra(Part):
    """A value that a rule reads at one stage of a firing (`trigger` or `fire`): a value that it draws
    (`family` and `args`), or a value of the run's past (`kind` `delayed`: `expr` and `delay`)."""

    name: str
    kind: str
    stage: str
    expr: Source | None = None
    delay: Source | None = None
    family: str | None = None
    args: Mapping[str, Source] | None = None
    OPTIONAL: ClassVar = frozenset({'expr', 'delay', 'family', 'args'})


@dataclass(frozen=True, slots=True)
class Rule(Part):
    """A rule of an event: when it triggers, how long it waits, and its outcomes. `rank` orders the
    rules of one moment."""

    id: str
    entity: str
    label: str | None
    basis: Any
    metadata: Any
    path: str
    rank: tuple
    once: bool
    named: bool
    trigger: Trigger
    delay: Source | None
    outcomes: tuple[EventOutcome, ...]
    emits: tuple[str, ...]
    delay_path: str | None = None
    each: tuple[Source, ...] | None = None
    each_path: str | None = None
    keep: Source | None = None
    keep_path: str | None = None
    extras: tuple[Extra, ...] | None = None
    choice: bool | None = None
    role: str | None = None
    NESTED: ClassVar = MappingProxyType(
        {'trigger': ('one', Trigger), 'outcomes': ('list', EventOutcome), 'extras': ('list', Extra)}
    )
    OPTIONAL: ClassVar = frozenset(
        {'delay_path', 'each', 'each_path', 'keep', 'keep_path', 'extras', 'choice', 'role'}
    )

    def sources(self):
        """(role, expression) of each expression that the rule reads. The roles, in this order: `when`
        (the whole condition; the gate and the times of the trigger are parts of it), `delay`, `each`,
        `keep`, `extra` (the arguments of each value that the rule draws, then the expression and the
        delay of each value of the past), and then of each outcome its `chance` (an outcome that takes
        what is left, `else`, has none), its `available`, each `set` and each `amount`. A role that has
        no expression is left out."""
        found = [('when', self.trigger.when), ('delay', self.delay)]
        found += [('each', item) for item in self.each or ()]
        found.append(('keep', self.keep))
        for extra in self.extras or ():
            found += [('extra', source) for source in (extra.args or {}).values()]
            found += [('extra', extra.expr), ('extra', extra.delay)]
        for outcome in self.outcomes:
            if outcome.chance != 'else':
                found.append(('chance', outcome.chance))
            found.append(('available', outcome.available))
            found += [('set', item.expr) for item in outcome.do.set.values()]
            found += [('amount', move.amount) for move in outcome.do.transfer]
        return tuple((role, source) for role, source in found if source is not None)

    def events(self):
        """Each event that the rule can make happen: its own, when it triggers, and each outcome's."""
        return (*self.emits, *(event for outcome in self.outcomes for event in outcome.emits))

    def steps(self):
        """What each outcome does, in the order of the outcomes."""
        return tuple(outcome.do for outcome in self.outcomes)


@dataclass(frozen=True, slots=True)
class Check(Part):
    """An `assert`: before the run when it reads inputs only (it then has a `severity`), else at each
    step."""

    expr: Source
    message: str | None
    basis: Any
    path: str
    severity: str | None = None
    OPTIONAL: ClassVar = frozenset({'severity'})


@dataclass(frozen=True, slots=True)
class Partition(Part):
    """A sum that holds at each step: the parts add up to the total, within the tolerance if the
    model gives one."""

    label: str | None
    parts: tuple[str, ...]
    total: Source
    tolerance: Source | None
    basis: Any
    path: str


@dataclass(frozen=True, slots=True)
class LagComponent(Part):
    """One part of an output's lag: a share of the value, a delay later."""

    weight: Any
    delay: Source


@dataclass(frozen=True, slots=True)
class Lag(Part):
    """How an output reads its expression later than it happens."""

    type: str
    delay: Source | None = None
    minimum: Source | None = None
    maximum: Source | None = None
    components: tuple[LagComponent, ...] | None = None
    NESTED: ClassVar = MappingProxyType({'components': ('list', LagComponent)})
    OPTIONAL: ClassVar = frozenset({'delay', 'minimum', 'maximum', 'components'})


@dataclass(frozen=True, slots=True)
class Outcome(Part):
    """An output of the model: its expression when it is estimated, or the reason that it is not."""

    label: str
    kind: str
    unit: str
    status: str
    nonnegative: bool
    basis: Any
    scope: Any = None
    expr: Source | None = None
    reason: str | None = None
    description: str | None = None
    category: str | None = None
    additive: Any = None
    lag: Lag | None = None
    NESTED: ClassVar = MappingProxyType({'lag': ('one', Lag)})
    OPTIONAL: ClassVar = frozenset({'scope', 'expr', 'reason', 'description', 'category', 'additive', 'lag'})

    def distinct(self):
        """Whether the file says that the people that the output adds are different people (its line
        `distinct`). The builder writes the key `additive` for that line: with the records of the
        line, or with no value for a line with no record. So a record that was read from a mapping
        says it by that key, and any other record by its records."""
        return self.additive is not None or (self._order is not None and 'additive' in self._order)


# ---- the structure ---------------------------------------------------------------------------------------

# Each kind of part of a structure, in the builder's order: the name of its section, and the class of
# its records. `links` is apart: it has the links of each thing, by the part that they reach, and the
# builder writes it after the sections. `computed_order` is a list, which the checks add last.
SECTIONS = MappingProxyType(
    {
        'entities': Entity,
        'parameters': Parameter,
        'quantities': Quantity,
        'modes': Mode,
        'computed': Computed,
        'labels': Label,
        'rates': Rate,
        'flows': Flow,
        'allocation': Allocation,
        'coupling': Coupling,
        'rules': Rule,
        'events': Event,
        'input_checks': Check,
        'state_checks': Check,
        'partitions': Partition,
        'outcomes': Outcome,
    }
)


@dataclass(frozen=True)
class Structure:
    """The model for one set of start-state options: each part once, in the compiled order."""

    entities: Mapping[str, Entity]
    parameters: Mapping[str, Parameter]
    quantities: Mapping[str, Quantity]
    computed: Mapping[str, Computed]
    computed_order: tuple
    labels: Mapping[str, Label]
    modes: Mapping[str, Mode]
    links: Mapping[str, Mapping[str, Link]]
    flows: Mapping[str, Flow]
    rates: Mapping[str, Rate]
    allocation: Mapping[str, Allocation]
    coupling: Mapping[str, Coupling]
    events: Mapping[str, Event]
    rules: Mapping[str, Rule]
    input_checks: Mapping[str, Check]
    state_checks: Mapping[str, Check]
    partitions: Mapping[str, Partition]
    outcomes: Mapping[str, Outcome]
    # The parts that cannot act in a run with these start-state options, and why:
    # {section: {name: the reason}} (docs/python-api.md, "The parts that cannot act"). The structure
    # itself has only the parts that can act; the whole structure has every part.
    left_out: Mapping[str, Mapping[str, str]] = field(default=EMPTY, compare=False)
    # What each formula reads, once it is worked out (`expanded`). It is no argument: a changed copy
    # (`dataclasses.replace`) starts with none, so it never holds what was true of the structure that
    # it was copied from.
    _kept: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    # The keys of the builder's mapping that `of` reads beside the sections.
    OTHER: ClassVar = ('links', 'computed_order')

    @classmethod
    def fields_of(cls, item, where=''):
        """{field: value} of the sections of one mapping of the builder; each other key is left to
        the caller (`rest`)."""
        found = {}
        for section, kind in SECTIONS.items():
            if section not in item:
                raise StructureError(f'{where}: a structure has the section {section}')
            found[section] = parts(kind, item[section], f'{where}{section}')
        found['links'] = MappingProxyType(
            {
                owner: parts(Link, links, f'{where}links/{owner}')
                for owner, links in (item.get('links') or {}).items()
            }
        )
        found['computed_order'] = frozen(item.get('computed_order', ()))
        return found

    @classmethod
    def of(cls, item, where='', left_out=None):
        """The structure of one mapping of the builder, with the parts that it leaves out, if the
        caller has them."""
        unknown = [key for key in item if key not in SECTIONS and key not in cls.OTHER]
        if unknown:
            raise StructureError(f'{where}: a structure has no part for {", ".join(map(repr, unknown))}')
        return cls(**cls.fields_of(item, where), left_out=frozen(left_out or {}))

    def plain(self, written=True):
        """The mapping of the builder again, with its keys in the builder's order. Each expression is
        its text, or its node when not `written`, as the mappings of the builder hold it."""
        out = {section: thawed(getattr(self, section), written) for section in SECTIONS}
        out['links'] = thawed(self.links, written)
        out['computed_order'] = thawed(self.computed_order, written)
        return out

    # ---- the queries -------------------------------------------------------------------------------

    def section(self, name):
        """{name: record} of one kind of part, by the name of its section."""
        if name not in SECTIONS:
            raise StructureError(f'a structure has no section {name!r}')
        return getattr(self, name)

    def moment_order(self):
        """The rules in the order in which one moment reads them: by rank."""
        return tuple(sorted(self.rules.values(), key=lambda rule: rule.rank))

    def flows_from(self, quantity):
        """The flows that drain a quantity, in the order of the flows."""
        return tuple(name for name, flow in self.flows.items() if flow.source == quantity)

    def flows_into(self, quantity):
        """The flows that fill a quantity, in the order of the flows."""
        return tuple(name for name, flow in self.flows.items() if flow.target == quantity)

    def names(self, source):
        """The names that one expression reads itself: no name of a function, and nothing through a
        formula. A number, a yes/no and no expression (None) read nothing; a text is a TypeError
        (`expressions.names_in`)."""
        return names_in(source) if isinstance(source, (str, nodes.Node)) else frozenset()

    def reads(self, rule, roles=None):
        """The names that a rule reads itself, in the expressions of `Rule.sources`: all of them, or
        those of the `roles` that the caller names. Nothing through a formula (`expanded` does that),
        and no end of a move."""
        found = set()
        for role, source in rule.sources():
            if roles is None or role in roles:
                found |= self.names(source)
        return frozenset(found)

    def writes(self, rule):
        """What a rule can change: each value that an outcome sets and the two ends of each move
        (`Effects.targets`). It has no event: `Rule.events` gives those."""
        return frozenset(target for step in rule.steps() for target in step.targets())

    def expanded(self, source, *, labels=False, keep=False, seen=frozenset()):
        """The names that an expression reads, through the formulas: each formula that it reads gives
        the names that the formula's own expression reads, and so on. With `labels`, a status gives the
        names that the conditions of its cases read; without it, the name of a status is a name like any
        other. With `keep`, the names of the formulas (and of the statuses) on the way are in the result;
        without it they are not, but for a formula that reads itself on a circle of formulas, whose name
        stays. `seen` are formulas that the caller is already inside.

        The checks of a structure and of the values of a run use it, both through the statuses and
        without the names on the way (`labels=True`). The engine has a walker of its own,
        `System.expanded_names`, which gives the names on the way too; a test holds the two to one
        result (`labels=True, keep=True`)."""
        seen = frozenset(seen)
        kept = {} if seen else self._kept.setdefault((labels, keep), {})
        return frozenset(self._expanded(source, seen, labels, keep, kept)[0])

    def _expanded(self, source, seen, labels, keep, kept):
        """(the names, whether a formula on the way reached itself). What a formula gives is kept once
        it is worked out with no circle on the way, so each result is that of the plain recursion."""
        out, circle = set(), False
        for name in self.names(source):
            if name in self.computed:
                texts = (self.computed[name].expr,)
            elif labels and name in self.labels:
                texts = tuple(case.when for case in self.labels[name].cases)
            else:
                out.add(name)
                continue
            if keep:
                out.add(name)
            if name in seen:
                out.add(name)
                circle = True
                continue
            found = kept.get(name)
            if found is None:
                found, hit = set(), False
                for text in texts:
                    names, inner = self._expanded(text, seen | {name}, labels, keep, kept)
                    found |= names
                    hit = hit or inner
                if hit:
                    circle = True
                else:
                    kept[name] = found
            out |= found
        return out, circle

    def with_facts(self, facts):
        """The structure with what its checks found (`analysis.structure.structure_facts`): the order
        of the formulas (`computed_order`), and the classified trigger of each rule that has one
        (`triggers`: rule → `Trigger`). A structure cannot change, so this is a copy; it shares each
        part that takes no fact, and it keeps the parts that the structure leaves out (`left_out`)."""
        triggers = facts['triggers']
        rules = MappingProxyType(
            {
                name: rule.changed(trigger=triggers[name]) if name in triggers else rule
                for name, rule in self.rules.items()
            }
        )
        return dataclasses.replace(self, computed_order=tuple(facts['computed_order']), rules=rules)

    def with_part(self, section, name, record):
        """A copy of the structure with one part of one section in place of the part of that name (or
        after the others, for a new name)."""
        changed = MappingProxyType({**self.section(section), name: record})
        return dataclasses.replace(self, **{section: changed})

    def left(self, section):
        """{name: why} of the parts of one section that cannot act with these start-state options."""
        return self.left_out.get(section, EMPTY)

    def owner(self, name):
        """The thing that a part belongs to, or None for a part of no thing (an output of the scenario,
        a check of the file)."""
        for section in ('quantities', 'parameters', 'computed', 'labels', 'modes', 'flows', 'rules'):
            part = getattr(self, section).get(name)
            if part is not None:
                return part.entity
        return None


@dataclass(frozen=True)
class Time(Part):
    """The time of a run: its horizon in hours, and the time scales and the resolution that the model
    names for the solver, if it names any."""

    horizon: float
    timescales: tuple[Source, ...] | None = None
    resolution: float | None = None
    OPTIONAL: ClassVar = frozenset({'timescales', 'resolution'})


@dataclass(frozen=True)
class Resolved(Structure):
    """A structure with the values of one run: the value of each input, the run's time, its name, its
    options, and what the checks of its values proved."""

    values: Mapping[str, Any] = EMPTY
    parameter_values: Mapping[str, Any] = EMPTY
    time: Time | None = None
    run: str | None = None
    options: tuple = ()
    starts: tuple = ()
    model_hash: str | None = None
    initiation: Any = None
    distributions: Any = None
    luck: Any = None
    proven_zero_stock_faces: tuple = ()
    proven_monotone_crossings: tuple = ()
    proven_cumulative_outcomes: tuple = ()
    # The keys of the mapping that the run was read from, in their order. It is no argument: a run
    # that is made in another way (a changed copy) has none.
    _keys: tuple | None = field(default=None, init=False, repr=False, compare=False)

    # The keys of its own that every resolution writes, in its order, and the keys that only some
    # steps write: the model, when it resolves a run by its name; a study of a run with distributions;
    # a sample. What a played run asks (who picks, and the picks) is no part of a resolved run: it is
    # an argument of the run (`engine.runtime.simulate`, `play`).
    ALWAYS: ClassVar = (
        'values',
        'parameter_values',
        'time',
        'initiation',
        'proven_zero_stock_faces',
        'proven_monotone_crossings',
        'proven_cumulative_outcomes',
    )
    NAMED: ClassVar = ('run', 'options', 'starts', 'model_hash')
    SOMETIMES: ClassVar = ('distributions', 'luck')

    @classmethod
    def of(cls, item, where=''):
        """The resolved run of one mapping of the model's resolution (`Model.resolve`)."""
        found = cls.fields_of(item, where)
        own = {*cls.ALWAYS, *cls.NAMED, *cls.SOMETIMES}
        unknown = [key for key in item if key not in found and key not in own]
        if unknown:
            raise StructureError(f'{where}: a resolved run has no part for {", ".join(map(repr, unknown))}')
        for key in own & set(item):
            timed = key == 'time' and item[key] is not None
            found[key] = Time.of(item[key], f'{where}time') if timed else frozen(item[key])
        resolved = cls(**found)
        object.__setattr__(resolved, '_keys', tuple(key for key in item if key in own))
        return resolved

    @classmethod
    def over(cls, structure, own, bounds=None):
        """The resolved run of a structure: the parts of the structure themselves, with what the
        resolution has of its own (`own`: the keys that every resolution writes, as plain data) and
        the number of each bound of a quantity that is written as an expression (`bounds`: quantity
        → `min` / `max` → number). The parts cannot change, so every resolution of a structure
        shares them: a resolution makes no part again, but for the quantities with such a bound."""
        found = {section: getattr(structure, section) for section in SECTIONS}
        found['links'], found['computed_order'] = structure.links, structure.computed_order
        if bounds:
            quantities = dict(structure.quantities)
            for name, numbers in bounds.items():
                quantities[name] = quantities[name].changed(
                    **{RENAMES.get(key, key): number for key, number in numbers.items()}
                )
            found['quantities'] = MappingProxyType(quantities)
        unknown = [key for key in own if key not in cls.ALWAYS]
        if unknown:
            raise StructureError(f'a resolution has no part for {", ".join(map(repr, unknown))}')
        for key, value in own.items():
            found[key] = Time.of(value, 'time') if key == 'time' and value is not None else frozen(value)
        return cls(**found)

    def adding(self, **own):
        """The run with more of its own: the name, the options and the start states of a run that
        the model resolves by its name, the hash of the model, its distributions, the luck of a
        sample. The copy shares the parts of the run."""
        unknown = [key for key in own if key not in self.NAMED and key not in self.SOMETIMES]
        if unknown:
            raise StructureError(
                f'a resolved run takes no {", ".join(map(repr, unknown))} after its resolution'
            )
        return dataclasses.replace(self, **{key: frozen(value) for key, value in own.items()})

    def own(self):
        """What the run has of its own, as plain data: the keys of a resolution, in their order. A
        run that was read from a mapping has the keys of that mapping. Any other run has the keys
        that every resolution writes, the four of a run that the model resolved by its name when it
        has a name, and each other key that has a value: so two runs that differ never write the
        same mapping."""
        keys = self._keys
        if keys is None:
            keys = [*self.ALWAYS, *(self.NAMED if self.run is not None else ())]
            keys += [key for key in self.SOMETIMES if getattr(self, key) is not None]
        return {key: thawed(getattr(self, key)) for key in keys}

    def plain(self, written=True):
        """The mapping of the resolution again: the mapping of its structure, then what the run has
        of its own (`own`). Each expression of the structure is its text, or its node when not
        `written`."""
        return {**super().plain(written), **self.own()}
