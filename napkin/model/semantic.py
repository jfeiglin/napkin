"""The declared model: a parsed model text with its names resolved and its types and units checked.

It holds what a run needs and what the report and the drawings read beside the program: the scenario
line, the entities and templates with their values and flows, their members (instances written by
hand and the rows of tables), the values and assertions of the top level, the records and the notes,
each with its texts and its evidence. Each declared part has a stable path, the path that the program
gives the part as its `origin` (`tank.water`, `Place.level`, `close` at the top level, the member
`sites.clinic`), so a report or a trace finds the label and the evidence of a part from the program.

- **Types and units.** A value's type is declared (`water: L`) or inferred from its initializer. A
  number's unit is checked by its dimension, from the units of the library and of the model: `+`,
  `-`, comparisons, `min`, `max`, `clip` and both sides of `if ... else` need one dimension, and `*`
  and `/` make the dimension of their result (D12). A bare number takes the declared unit where the
  spec says so: the whole initializer, a bare end of the declaration's range, its scale, the value
  arguments of a distribution that (or whose draw) is the whole initializer, a member's own value and
  a table cell; and a bare zero beside a value of known unit.
- **Unit runs.** After a number, a name is a unit while the library has a unit of that name and the
  run has not stopped; the first name that is no unit stops the run, and it and the names after it
  are values (`(2 h) * hour` against `2 h * hour`). The arithmetic is the same either way.
- **Members and links.** A template (`Place:`) is the schema that its members share; an entity
  written once (`tank:`) is the template of its one member, under its own name. A member is written
  by hand (`north: Utility`, with its own values and links under it) or is a row of a table. A link
  (`origin: Place`) names one member, fixed for the run: the member sets it, or the link's
  initializer names it (`origin = sites.junction`), so the declared model knows each target.
- **Collections** (`<T>`) are typed with their template and their key: `Template.instances`, a
  literal, `where` (a bare name in its test that is a field of the member is the member's, and it
  must be fixed: an input or a link), `by(field)` (the key) and `.at(x)` (one member, `x` in the
  key's unit). A step from a collection is a projection, which only a reduction reads: `sum` and
  `min`/`max` of numbers, `count` of members or of yes/no values, `any` and `all` of yes/no values.
- **Flows and endpoints.** A directed flow ends at `SOURCE`, `SINK` or a stored number: of its own
  member, through links (`this.origin.power`), of a named member (`reservoir.water`) or of the top
  level. A stored number has an `outflow` and an `inflow` (`EndOf`): their `actual_rate` (the sum of
  the incident flows), `request`, `capacity` and `flows` (a collection of flows) are read, and their
  settings are written under the store (`outflow.capacity = 10 L/h`, `inflow.allocation =
  priority(this.main, this.backup)`; `DeclaredEndpoint`). A setting is resolved after its store, so
  it may read it. `priority(...)` ranks flows, or a projection of flows over a collection by its
  keys; that each is incident at the store is the program's rule (`check.priority_item`).
- **Routes and legs.** A reversible route (`flow link: west.water <-> east.water`, a
  `DeclaredRoute`) has one signed `actual_rate` and `request` and a `capacity` on the magnitude,
  and its legs `link.forward` and `link.backward` (`FlowOf.view`), which read the positive part of
  the rate and of the request in their direction, are members of the flows of its ends and are what
  a `priority(...)` names; a bare route is no claim there. Both ends of a route are stores. No mark
  makes a store receive-only: a tally is a store that nothing takes from, and a route takes from
  both of its ends, so a store at an end of a route is a stock, and only `SOURCE` and `SINK` (and
  what is no stored number) are refused there. A flow with legs (`DeclaredLegs`) reads its
  `served_fraction` and its legs, each a directed flow in its own unit at `owner.flow.leg`, named in
  the priority of its own endpoint; it has no rate and no request of its own.
- **The ends of a flow** (`f.source`, `f.sink`, also of a leg and of a leg of a route) read the
  store at that end, with its amount and the steps of a store. The ends are fixed for the run, so
  the read goes to the store's own path from the flow's member (`end`); an end at `SOURCE` or
  `SINK`, or of a member of an endpoint's `flows`, which may end anywhere, has no store to read.
- **Expressions** become a small typed form (`Const`, `Read`, `Apply`, `Retain`, `Distribution`,
  `Drawn`, `Reduced`) that the lowering writes as a program. A `Read` knows whether what it reads is
  fixed for the run (inputs, links and the members of fixed collections), which `where` and `assert`
  need, and whether it ends at a stored number, which a flow and an endpoint need.
- **What a later slice brings** is kept as a `Deferred` part, with the construct and the slice that
  brings it; the lowering refuses it by name. These slices resolve the entities, the templates and
  their members, the tables, values, inputs (a default may draw from a distribution), formulas,
  `readonly`, ranges with either side open, scales, links, collections and their reductions, stores,
  directed flows between any stores with `request` and `capacity`, reversible routes, flows with
  legs, the reads of the ends of a flow, the settings and the reads of endpoints, and assertions
  over inputs.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import cached_property

from .language import nodes as n
from .language import tables
from .language.parse import parse_expression
from .language.problems import LanguageError, Problem, SyntaxProblem

# ---- units ------------------------------------------------------------------------------------------


class Units:
    """The units of a model: a spelling and its dimension (base dimensions with their powers) or a
    pair of the dimension and its scale, as `napkin.program.build.Builder` takes them. A spelling with
    `*` and `/` is composed from the left (D12)."""

    def __init__(self, table):
        self.table = dict(table)
        self.base = {}
        for name, spec in self.table.items():
            dimension, scale = spec if isinstance(spec, tuple) else (spec, 1)
            self.base[name] = (tuple(sorted((k, v) for k, v in dimension.items() if v)), Fraction(scale))

    def has(self, name):
        return name in self.base

    def of(self, spelling):
        """(dimension, scale) of a spelling, or None when a name of it is no unit."""
        dimension, scale = {}, Fraction(1)
        for sign, name in factors(spelling):
            if name == '1':
                continue
            if name not in self.base:
                return None
            found, size = self.base[name]
            for key, power in found:
                dimension[key] = dimension.get(key, 0) + sign * power
            scale = scale * size if sign > 0 else scale / size
        return tuple(sorted((k, v) for k, v in dimension.items() if v)), scale


def factors(spelling):
    """The factors of a spelling, [(+1 or -1, name)] from the left: `L/h` is [(1, 'L'), (-1, 'h')]."""
    out, sign, name = [], 1, ''
    for char in spelling:
        if char in '*/':
            out.append((sign, name))
            sign, name = (1 if char == '*' else -1), ''
        else:
            name += char
    if name:
        out.append((sign, name))
    return out


def spelling_of(found):
    """The spelling of factors [(sign, name)]: the names over the line first, in their order, and the
    same name over and under the line cancels (`tunings/tuner/year * tuner` is `tunings/year`)."""
    powers = {}
    for sign, name in found:
        if name != '1':
            powers[name] = powers.get(name, 0) + sign
    above = [name for name, power in powers.items() for _ in range(max(power, 0))]
    below = [name for name, power in powers.items() for _ in range(max(-power, 0))]
    if not above and not below:
        return ''
    return '/'.join(['*'.join(above) or '1', *below])


def flat_unit(unit):
    """The factors of a unit of a type (`nodes.UnitOp` or a name), from the left with no brackets:
    `tunings / (tuner * year)` is tunings/tuner/year."""

    def walk(item, sign):
        if isinstance(item, str):
            return [(sign, item)]
        return walk(item.left, sign) + walk(item.right, sign if item.op == '*' else -sign)

    return walk(unit, 1)


# ---- types ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Num:
    """A number in a unit (its spelling, '' for a plain number) and the unit's dimension."""

    unit: str = ''
    dimension: tuple = ()

    def __str__(self):
        return self.unit or 'a plain number'


@dataclass(frozen=True)
class Word:
    """`bool` or `text`."""

    word: str

    def __str__(self):
        return self.word


BOOL, TEXT = Word('bool'), Word('text')
PLAIN = Num()


@dataclass(frozen=True)
class Dist:
    """A distribution of numbers in a unit."""

    of: Num

    def __str__(self):
        return f'distribution({self.of})'


@dataclass(frozen=True)
class Ent:
    """A member of a template: `this`, a link, a named member, a row or a keyed read. An entity
    written once is the template of its one member, under its own name."""

    template: str

    def __str__(self):
        return f'a member of {self.template}'


@dataclass(frozen=True)
class Many:
    """A collection of members (`of` is an `Ent`), or a projection of a field over one (`of` is the
    field's type), with the type of its keys: the creation number (a plain number) or the field that
    a `by` names."""

    of: object
    key: Num = PLAIN

    def __str__(self):
        if isinstance(self.of, Ent):
            return f'a collection of {self.of.template}'
        return f'a projection of {self.of}'


@dataclass(frozen=True)
class FlowOf:
    """A directed flow, which is no value: its rates are read (`actual_rate`, `request`, `capacity`)
    and its ends (`source`, `sink`). `flow` is the path of its declaration: a flow, a leg of a flow
    with legs (`site.restore.labor`) or a leg of a route (`channel.link.forward`, a `view`), or ''
    for a member of an endpoint's `flows`, which may be any of the flows incident there. A leg of a
    route reads the positive part of the route's rate and request in its direction, and has no
    capacity of its own."""

    rate: Num
    flow: str = field(default='', compare=False)
    view: bool = field(default=False, compare=False)

    def __str__(self):
        return f'a flow in {self.rate}'


@dataclass(frozen=True)
class RouteOf:
    """A reversible route, which is no value: its signed `actual_rate` and `request` (positive from
    its first end to its second), its `capacity` on the magnitude, and its two legs `forward` and
    `backward`, which are members of the collections of flows of its ends."""

    rate: Num
    flow: str = ''

    def __str__(self):
        return f'a reversible route in {self.rate}'


@dataclass(frozen=True)
class LegsOf:
    """A flow with several legs (`flow` is the path of its declaration), which is no value and has
    no rate of its own: its `served_fraction` (a plain number from 0 to 1) and each leg by its name
    (`restore.labor`, a directed flow in its own unit) are read."""

    flow: str

    def __str__(self):
        return 'a flow with legs'


@dataclass(frozen=True)
class EndOf:
    """The outflow or the inflow of a store, which is no value: its total rate (`actual_rate`), its
    settings (`request`, `capacity`) and its incident flows (`flows`) are read. `rate` is the store's
    unit per hour."""

    rate: Num

    def __str__(self):
        return f'an endpoint in {self.rate}'


def compatible(a, b):
    if isinstance(a, Num) and isinstance(b, Num):
        return a.dimension == b.dimension
    if isinstance(a, Many) and isinstance(b, Many):
        return a.of == b.of
    return a == b


# ---- the typed form of an expression -----------------------------------------------------------------


@dataclass(frozen=True)
class Const:
    """A number (in the unit of its type), a yes/no or a text."""

    value: object
    type: object


@dataclass(frozen=True)
class Read:
    """A read from a start through its steps (a value, a link, a flow and its rate). The starts are
    `('this',)`, `('named', id)` (an entity, an instance or a row), `('root',)`, `('time',)`,
    `('item',)` (the member of a `where`), `('instances', template)`, `('literal', reads)`, `('where',
    source, test)`, `('by', source, field)` and `('lookup', source, key)`. `fixed` says that what it
    reads is fixed for the run."""

    start: tuple
    steps: tuple
    type: object
    fixed: bool = False
    # The path of the formula that the read ends at, when the way to it is fixed: an assertion that
    # reads it is over inputs when the formula is.
    formula: str = field(default='', compare=False)
    # Whether the read ends at a stored number, which can be an end of a flow and has an outflow and
    # an inflow.
    stored: bool = field(default=False, compare=False)


@dataclass(frozen=True)
class Apply:
    """An operation: `add`, `sub`, `mul`, `div`, `pow`, `neg`, `not`, `and`, `or`, `if`, `compare`
    (its operators in `detail`) or `call` (the function in `detail`)."""

    op: str
    args: tuple
    type: object
    detail: object = None


@dataclass(frozen=True)
class Reduced:
    """`sum`, `count`, `any`, `all`, `min` or `max` of a collection or of a projection (`source`)."""

    op: str
    source: Read
    type: object


@dataclass(frozen=True)
class Retain:
    """`formula(body)`."""

    body: object
    type: object


@dataclass(frozen=True)
class Distribution:
    """A distribution of a family, its parameters as numbers in one unit."""

    family: str
    params: tuple
    type: Dist


@dataclass(frozen=True)
class Drawn:
    """`d.draw()` of a distribution."""

    source: Distribution
    type: Num


def reads_of(expression):
    """The reads of a typed expression, outside the starts of its keyed reads."""
    if isinstance(expression, Read):
        yield expression
    elif isinstance(expression, Reduced):
        yield expression.source
    elif isinstance(expression, Apply):
        for arg in expression.args:
            yield from reads_of(arg)
    elif isinstance(expression, Retain):
        yield from reads_of(expression.body)


def fixed(expression):
    """Whether a typed expression reads only what is fixed for the run."""
    if isinstance(expression, Const):
        return True
    if isinstance(expression, Read):
        return expression.fixed
    if isinstance(expression, Reduced):
        return expression.source.fixed
    if isinstance(expression, Apply):
        return all(fixed(arg) for arg in expression.args)
    return False


# ---- the declared parts -------------------------------------------------------------------------------

INPUT, STATE, FORMULA, DISTRIBUTION = 'input', 'state', 'formula', 'distribution'
LINK, COLLECTION = 'link', 'collection'


@dataclass(frozen=True)
class DeclaredEndpoint:
    """The settings of a store's `outflow` or `inflow`, written under the store
    (`outflow.capacity = 10 L/h`): a hard `capacity` and a soft `request` on the total rate in that
    direction (each captured once, or a `Retain`), and the `allocation` among the incident flows,
    `('proportional',)` (the default) or `('priority', items)` with the `Read` of each item, a flow
    or a projection of flows (`Customer.instances.by(rank).delivery`), first to last. Its path is
    the store's and the side (`reservoir.water.outflow`); its line is that of its first setting."""

    path: str
    capacity: object = None
    request: object = None
    allocation: tuple = ('proportional',)
    line: int = 0


@dataclass(frozen=True)
class DeclaredValue:
    """A value of an entity, a template or the top level: its kind (`input`, `state`, `formula`,
    `distribution`, `link`, `collection`), its type, its initializer (None for a value of a template
    that each member gives, or a link that each member sets), its range (either side None), its
    scale, its texts and its evidence (the records that it cites and those written under it). A
    stored number has the settings of its `outflow` and its `inflow` (`DeclaredEndpoint`), or None."""

    path: str
    name: str
    kind: str
    type: object
    init: object
    lower: object = None
    upper: object = None
    scale: object = None
    readonly: bool = False
    text: str | None = None
    evidence: tuple = ()
    line: int = 0
    outflow: DeclaredEndpoint | None = None
    inflow: DeclaredEndpoint | None = None


def fixed_kind(value):
    """Whether a declared value is fixed for the run: an input, a link, or a collection whose members
    are fixed."""
    if value.kind in (INPUT, LINK):
        return True
    return value.kind == COLLECTION and value.init is not None and value.init.fixed


def _stored(value):
    """Whether a declared value is a stored number: an end of a flow, with an outflow and an inflow."""
    return value.kind == STATE and isinstance(value.type, Num)


@dataclass(frozen=True)
class DeclaredFlow:
    """A directed flow, or a leg of a flow with legs: its ends (`'SOURCE'`, `'SINK'` or the `Read` of
    a store: of its own member, through a link, of a named member or of the top level), the type of
    its rates, its request and its capacity (captured once, or a `Retain`)."""

    path: str
    name: str
    source: object
    sink: object
    rate: Num
    request: object = None
    capacity: object = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredRoute(DeclaredFlow):
    """A reversible route (`flow link: west.water <-> east.water`): one signed rate, positive from
    `source` to `sink`, a signed request and a capacity on the magnitude. Both ends are stores, which
    supply and receive through it: `SOURCE` and `SINK` stand at the ends of a directed flow only."""


@dataclass(frozen=True)
class DeclaredLegs:
    """A flow with several legs, served at one fraction: each leg is a `DeclaredFlow` with its own
    ends, unit, request and capacity, at the path `owner.flow.leg` (`site.restore.labor`). The
    parent has no request and no rate of its own."""

    path: str
    name: str
    legs: tuple[DeclaredFlow, ...]
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredAssert:
    """An assertion over what is fixed for the run, checked once: its test, its message (`text`) and
    its evidence. Its path is `assert[k]` of its owner."""

    path: str
    test: object
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredEntity:
    """An entity written once: a template of one member, with its parts in written order."""

    path: str
    parts: tuple = ()
    text: str | None = None
    title: str | None = None
    role: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredTemplate(DeclaredEntity):
    """A template: the schema and the behaviour that its members share, with its parts in written
    order."""


@dataclass(frozen=True)
class Given:
    """A member's own initializer of a value of its template (a typed expression, a `Retain` in
    place of the template's formula, a `Distribution`), or for a link the id of the member that it
    names."""

    name: str
    init: object
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredMember:
    """A member of a template: written by hand (`north: Utility`), or a row of the table `table`. Its
    path is its id (`north`, `sites.clinic`, or `readings[0]` for a row of a table without ids). Its
    line is in `file`: the model's ('') or the table's."""

    path: str
    template: str
    values: tuple[Given, ...] = ()
    links: tuple[Given, ...] = ()
    table: str | None = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0
    file: str = ''


@dataclass(frozen=True)
class DeclaredTable:
    """A table: its name, its template, the file that the model names and the one read (`origin`),
    its columns (`tables.Column`, with their units and records) and the ids of its members in file
    order."""

    path: str
    template: str
    file: str
    origin: str
    columns: tuple = ()
    members: tuple[str, ...] = ()
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class Deferred:
    """A part that this slice parses and formats but does not lower: what it is and the slice that
    brings it."""

    path: str
    construct: str
    slice: str
    line: int = 0


@dataclass(frozen=True)
class Scenario:
    """The scenario line: its role (`main` or `variant`), its title and texts, and its times in hours."""

    role: str
    title: str
    summary: str | None = None
    scope: str | None = None
    library: str | None = None
    horizon: object = None
    resolution: object = None
    timescales: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredModel:
    """A declared model: its scenario line; its entities and templates, its top-level values, its
    members (instances by hand and table rows, in written order) and its top-level assertions; its
    tables, records and notes; the parts that a later slice brings; its units and its tree."""

    scenario: Scenario | None
    entities: tuple[DeclaredEntity, ...]
    root: tuple[DeclaredValue, ...]
    records: tuple = ()
    notes: tuple = ()
    deferred: tuple[Deferred, ...] = ()
    units: Units = None
    tree: n.File = field(default=None, repr=False)
    members: tuple[DeclaredMember, ...] = ()
    tables: tuple[DeclaredTable, ...] = ()
    asserts: tuple[DeclaredAssert, ...] = ()

    def part(self, path):
        """The declared part of a path (an entity, a template, a value, the settings of an
        endpoint, a flow, a leg, an assertion, a member, a table or a deferred part), or None."""
        return self._paths.get(path)

    @cached_property
    def _paths(self):
        """Each declared part by its path, made once, so that a large model places each of many
        diagnostics at once: the first of two parts of one path wins, entities before members."""
        found = {}
        for entity in self.entities:
            found.setdefault(entity.path, entity)
            for part in entity.parts:
                found.setdefault(part.path, part)
                for leg in part.legs if isinstance(part, DeclaredLegs) else ():
                    found.setdefault(leg.path, leg)
        for part in (*self.members, *self.tables, *self.root, *self.asserts, *self.deferred):
            found.setdefault(part.path, part)
        for value in [part for part in found.values() if isinstance(part, DeclaredValue)]:
            for side in (value.outflow, value.inflow):
                if side is not None:
                    found.setdefault(side.path, side)
        return found


# ---- resolution ---------------------------------------------------------------------------------------


class Later(Exception):
    """A construct that a later slice brings, met while a part is resolved."""

    def __init__(self, construct, slice_):
        super().__init__(construct)
        self.construct, self.slice = construct, slice_


class Refused(Exception):
    """A diagnostic that stops the resolution of one part."""

    def __init__(self, code, message, node=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.line = getattr(node, 'line', 0)
        self.column = getattr(node, 'column', 0)


@dataclass(frozen=True)
class Scope:
    """Where an expression stands: the template whose member `this` names ('' at the top level), and
    inside the test of a `where` the template of the member under test (`item`)."""

    owner: str = ''
    item: str | None = None


TOP = Scope()
FLOW_READS = ('actual_rate', 'request', 'capacity')
ENDS = ('source', 'sink')
SIDES = ('outflow', 'inflow')
SETTINGS = ('capacity', 'request', 'allocation')
ALLOCATIONS = ('priority', 'proportional')
KEYED = ('where', 'by', 'at')
SHAPES = {'lognormal': {1}}  # the positions of the plain (shape) arguments of a family: the gsd
ARITY = {
    'uniform': (2,),
    'triangular': (3,),
    'pert': (3,),
    'loguniform': (2,),
    'normal': (2, 4),
    'lognormal': (2, 4),
}
PURE = ('exp', 'expm1', 'ln', 'log1p', 'erf')
LATER_CALLS = dict.fromkeys(('since', 'elapsed', 'delayed'), ('history (since, elapsed, delayed)', 'S4'))
LATER_METHODS = {
    'draw': ('a draw outside the default of an input', 'S4'),
    'choose': ("an actor's choice", 'S4'),
}
ID = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def close(name, names):
    found = difflib.get_close_matches(name, sorted(set(names) - {name}), n=3)
    return f'; did you mean {" or ".join(found)}?' if found else ''


def literal(node):
    """The number of a literal (a number or a quantity, with its signs), or None."""
    sign = 1
    while isinstance(node, n.Unary) and node.op in ('-', '+'):
        sign = -sign if node.op == '-' else sign
        node = node.operand
    if isinstance(node, (n.Number, n.Quantity)):
        return sign * node.value, node
    return None


class Resolver:
    """Resolves the parts of one parsed text against a table of units, reading its tables with
    `read_table` (see `tables.in_folder`)."""

    def __init__(self, tree, units, read_table):
        self.tree, self.units, self.read_table = tree, units, read_table
        self.problems, self.deferred = [], []
        self.entities, self.templates, self.instances, self.tables = {}, {}, {}, {}
        self.root, self.records = {}, {}
        self.syntax, self.done, self.active = {}, {}, set()
        self.ids, self.data = {}, {}  # the ids of the rows of each table that was read, and its form
        self.owned = {}  # the paths of the values of each template, once a member asks for them
        self.inputs_only = {}  # whether each formula that an assertion reaches reads inputs only
        for item in tree.items:
            if isinstance(item, n.Entity):
                (self.entities if item.name[:1].islower() else self.templates)[item.name] = item
                for member in item.members:
                    name = getattr(member, 'name', None)
                    if isinstance(member, (n.Declaration, n.Flow, n.Event, n.Solver)) and name:
                        self.syntax[f'{item.name}.{name}'] = (item.name, member)
        for item in tree.items:
            if isinstance(item, n.Table):
                self.tables[item.name] = item
            elif isinstance(item, n.Declaration):
                if (
                    item.value is None
                    and isinstance(item.type, n.NamedType)
                    and item.type.name in self.templates
                ):
                    self.instances[item.name] = item
                else:
                    self.root[item.name] = item
                    self.syntax[item.name] = ('', item)
            elif isinstance(item, n.Record):
                self.records[item.name] = item

    def fail(self, code, message, node=None):
        raise Refused(code, message, node)

    def report(self, code, message, line=0, column=0, file=''):
        self.problems.append(Problem(code, message, line, column, file))

    # ---- types and units ---------------------------------------------------------------------

    def per_hour(self, kind):
        """The type of the rates of a store of a number type: its unit per hour (`1/h` for a plain
        number), the spelling that the program's builder gives a flow between such stores."""
        return self.num(f'{kind.unit}/h' if kind.unit else '1/h')

    def num(self, spelling, node=None):
        found = self.units.of(spelling)
        if found is None:
            unknown = [name for _, name in factors(spelling) if name != '1' and not self.units.has(name)]
            self.fail(
                'unit',
                f'{unknown[0]} is no unit of the library or of the model'
                + close(unknown[0], self.units.base),
                node,
            )
        return Num(spelling, found[0])

    def declared_type(self, node):
        """The type that a declaration writes; `formula(T)` gives (T, True)."""
        if isinstance(node, n.FormulaType):
            inner, retained = self.declared_type(node.of)
            if retained:
                self.fail('type', 'a formula of a formula: reading a formula gives its value', node)
            return inner, True
        if isinstance(node, n.WordType):
            return (PLAIN if node.word == 'number' else Word(node.word)), False
        if isinstance(node, n.NamedType):
            if node.name in self.templates:
                return Ent(node.name), False
            if node.name[:1].isupper() and not self.units.has(node.name):
                self.fail(
                    'unknown_name',
                    f'{node.name} is no unit and no template' + close(node.name, self.templates),
                    node,
                )
            return self.num(node.name, node), False
        if isinstance(node, n.UnitType):
            return self.num(spelling_of(flat_unit(node.unit)), node), False
        if isinstance(node, n.DistributionType):
            inner, _ = self.declared_type(node.of)
            if not isinstance(inner, Num):
                raise Later('a distribution of an enum', 'S4')
            return Dist(inner), False
        if isinstance(node, n.EnumType):
            raise Later('an enum', 'S4')
        if isinstance(node, n.CollectionType):
            inner, _ = self.declared_type(node.of)
            if not isinstance(inner, Ent):
                self.fail('type', 'a collection holds members of a template, as <Pump>', node)
            return Many(inner), False
        self.fail('type', 'no type', node)

    # ---- expressions -----------------------------------------------------------------------------

    def expression(self, node, scope, unit=None):
        """The typed form of an expression in a scope. `unit` is the declared unit that a bare number
        takes (the whole initializer)."""
        found = literal(node)
        if found is not None:
            value, written = found
            if isinstance(written, n.Quantity):
                return self.quantity(value, written, scope)
            if unit is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
                return Const(value, unit)
            return Const(value, PLAIN)
        if isinstance(node, n.Bool):
            return Const(node.value, BOOL)
        if isinstance(node, n.Text):
            return Const(node.value, TEXT)
        if isinstance(node, (n.Name, n.Member, n.Collection)) or (
            isinstance(node, n.Method) and node.name in KEYED
        ):
            found = self.path(node, scope)
            if isinstance(found.type, (FlowOf, RouteOf)):
                self.fail(
                    'type',
                    'a flow is no value: read its actual_rate, request or capacity, as delivery.actual_rate',
                    node,
                )
            if isinstance(found.type, LegsOf):
                self.fail(
                    'type',
                    'a flow with legs is no value: read its served_fraction, or the actual_rate of a leg, '
                    'as restore.labor.actual_rate',
                    node,
                )
            if isinstance(found.type, EndOf):
                self.fail(
                    'type',
                    'an outflow or an inflow is no value: read its actual_rate, request or capacity, or '
                    'its flows, as water.outflow.actual_rate',
                    node,
                )
            return found
        if isinstance(node, n.Method):
            if node.name == 'diff':
                self.fail('not_in_v1', 'formula differentiation (.diff) is not in the first version', node)
            if node.name == 'start':
                self.fail('start', '.start(...) starts an occurrence and gives no value', node)
            raise Later(*LATER_METHODS[node.name])
        if isinstance(node, n.Call):
            return self.call(node, scope)
        if isinstance(node, n.Formula):
            self.fail(
                'formula',
                'formula(...) keeps a calculation where a value stands: it is the whole initializer',
                node,
            )
        if isinstance(node, n.Unary):
            operand = self.expression(node.operand, scope)
            if node.op == 'not':
                self.want_bool(operand, node, 'not')
                return Apply('not', (operand,), BOOL)
            self.want_number(operand, node, node.op)
            return operand if node.op == '+' else Apply('neg', (operand,), operand.type)
        if isinstance(node, n.Binary):
            return self.binary(node, scope)
        if isinstance(node, n.Compare):
            operands = [self.expression(item, scope) for item in node.operands]
            for k, op in enumerate(node.ops):
                operands[k], operands[k + 1] = self.alike(operands[k], operands[k + 1], node, op)
            return Apply('compare', tuple(operands), BOOL, node.ops)
        if isinstance(node, n.BoolOp):
            values = tuple(self.expression(item, scope) for item in node.values)
            for value in values:
                self.want_bool(value, node, node.op)
            return Apply(node.op, values, BOOL)
        if isinstance(node, n.IfElse):
            test = self.expression(node.test, scope)
            self.want_bool(test, node, 'if')
            body, orelse = self.alike(
                self.expression(node.body, scope), self.expression(node.orelse, scope), node, 'if'
            )
            return Apply('if', (test, body, orelse), body.type if body.type != PLAIN else orelse.type)
        if isinstance(node, n.Within):
            value = self.expression(node.value, scope)
            self.want_number(value, node, 'in')
            tests = []
            if node.low is not None:
                low, value = self.alike(self.expression(node.low, scope), value, node, 'in')
                tests.append(Apply('compare', (low, value), BOOL, ('<=',)))
            if node.high is not None:
                value, high = self.alike(value, self.expression(node.high, scope), node, 'in')
                tests.append(Apply('compare', (value, high), BOOL, ('<=',)))
            if len(tests) == 2:
                return Apply('compare', (tests[0].args[0], value, tests[1].args[1]), BOOL, ('<=', '<='))
            return tests[0]
        self.fail('syntax', f'{type(node).__name__} is no value here', node)

    def quantity(self, value, node, scope):
        """A number and its unit run: the names that are units, then the names that are values."""
        first = node.unit[0][1]
        if not self.units.has(first):
            self.fail(
                'unit',
                f'{first} is no unit of the library or of the model' + close(first, self.units.base),
                node,
            )
        taken = [(1, first)]
        k = 1
        while k < len(node.unit) and self.units.has(node.unit[k][1]):
            taken.append((1 if node.unit[k][0] == '*' else -1, node.unit[k][1]))
            k += 1
        spelling = taken[0][1] + ''.join(('*' if sign > 0 else '/') + name for sign, name in taken[1:])
        result = Const(value, self.num(spelling, node))
        for op, name in node.unit[k:]:
            other = self.path(n.Name(name, line=node.line, column=node.column), scope)
            if isinstance(other.type, (Ent, Many, FlowOf)):
                self.fail('type', f'{name} is no number', node)
            result = self.product('mul' if op == '*' else 'div', result, other, node)
        return result

    def binary(self, node, scope):
        left, right = self.expression(node.left, scope), self.expression(node.right, scope)
        if node.op in ('+', '-'):
            left, right = self.alike(left, right, node, node.op)
            self.want_number(left, node, node.op)
            kind = left.type if left.type != PLAIN or right.type == PLAIN else right.type
            return Apply('add' if node.op == '+' else 'sub', (left, right), kind)
        if node.op in ('*', '/'):
            return self.product('mul' if node.op == '*' else 'div', left, right, node)
        self.want_number(left, node, '**')
        self.want_number(right, node, '**')
        if right.type.dimension:
            self.fail('unit', 'an exponent has no unit', node)
        if not left.type.dimension:
            return Apply('pow', (left, right), PLAIN)
        if not (isinstance(right, Const) and isinstance(right.value, int) and right.value > 0):
            self.fail(
                'unit', f'a value in {left.type} is raised only to a whole number written in place', node
            )
        spelling = spelling_of(factors(left.type.unit) * right.value)
        return Apply('pow', (left, right), self.num(spelling, node))

    def product(self, op, left, right, node):
        self.want_number(left, node, '*' if op == 'mul' else '/')
        self.want_number(right, node, '*' if op == 'mul' else '/')
        found = factors(left.type.unit) if left.type.unit else []
        other = factors(right.type.unit) if right.type.unit else []
        if op == 'div':
            other = [(-sign, name) for sign, name in other]
        return Apply(
            op, (left, right), self.num(spelling_of(found + other), node) if found or other else PLAIN
        )

    def alike(self, left, right, node, op):
        """Two operands of one dimension; a bare zero takes the other's unit."""
        if isinstance(left.type, Num) and isinstance(right.type, Num):
            if left.type.dimension != right.type.dimension:
                if _zero(left) and not left.type.dimension:
                    return Const(left.value, right.type), right
                if _zero(right) and not right.type.dimension:
                    return left, Const(right.value, left.type)
                self.fail(
                    'unit', f'{op} needs one dimension on both sides: {left.type} and {right.type}', node
                )
            return left, right
        if isinstance(left.type, Many) or isinstance(right.type, Many):
            self.fail('type', f'{op} takes values, not collections: reduce one, as sum(c.f)', node)
        if left.type != right.type:
            self.fail('type', f'{op} needs one type on both sides: {left.type} and {right.type}', node)
        if op not in ('==', '!=', 'if'):
            self.fail('type', f'{left.type} has == and != only', node)
        return left, right

    def want_number(self, value, node, op):
        if not isinstance(value.type, Num):
            hint = ': write (1 if c else 0)' if value.type == BOOL else ''
            if isinstance(value.type, Many):
                hint = ': reduce it, as sum(c.f)'
            self.fail('type', f'{op} takes numbers, not {value.type}{hint}', node)

    def want_bool(self, value, node, op):
        if value.type != BOOL:
            self.fail('type', f'{op} takes a yes/no, not {value.type}', node)

    def call(self, node, scope):
        if node.function in LATER_CALLS:
            raise Later(*LATER_CALLS[node.function])
        if node.function in ALLOCATIONS:
            self.fail(
                'allocation',
                f'{node.function}(...) is an allocation, no value: it is the value of '
                'outflow.allocation or inflow.allocation under a store',
                node,
            )
        if node.function in ('sum', 'count', 'any', 'all') or (
            node.function in ('min', 'max') and len(node.args) == 1
        ):
            return self.reduction(node, scope)
        if node.function in ARITY or node.function == 'categorical':
            self.fail(
                'draw',
                f'{node.function}(...) is a distribution: it is the whole initializer of a value or an '
                'input, and a draw of it the default of an input',
                node,
            )
        args = [self.expression(arg, scope) for arg in node.args]
        for arg in args:
            self.want_number(arg, node, node.function)
        wanted = {'clip': 3, 'abs': 1, 'sqrt': 1}.get(node.function, 1 if node.function in PURE else None)
        if wanted is not None and len(args) != wanted:
            self.fail(
                'arguments', f'{node.function} takes {wanted} argument' + ('s' if wanted > 1 else ''), node
            )
        if node.function in ('min', 'max', 'clip'):
            reference = next((arg for arg in args if arg.type != PLAIN), args[0])
            for k, arg in enumerate(args):
                _, args[k] = self.alike(reference, arg, node, node.function)
            return Apply('call', tuple(args), reference.type, node.function)
        if node.function == 'abs':
            return Apply('call', tuple(args), args[0].type, 'abs')
        if node.function == 'sqrt':
            powers = {}
            for sign, name in factors(args[0].type.unit) if args[0].type.unit else []:
                powers[name] = powers.get(name, 0) + sign
            if any(power % 2 for power in powers.values()):
                self.fail('unit', f'sqrt of {args[0].type}: each unit of it needs an even power', node)
            half = [
                (1 if power > 0 else -1, name)
                for name, power in powers.items()
                for _ in range(abs(power) // 2)
            ]
            return Apply('call', tuple(args), self.num(spelling_of(half), node) if half else PLAIN, 'sqrt')
        if args[0].type.dimension:
            self.fail('unit', f'{node.function} takes a plain number, not {args[0].type}', node)
        return Apply('call', tuple(args), PLAIN, node.function)

    def reduction(self, node, scope):
        """`sum`, `count`, `any`, `all`, `min` or `max` of one collection or projection (D4: an empty
        `sum` is zero in its unit, `count` zero, `any` false, `all` true)."""
        op = node.function
        if len(node.args) != 1:
            self.fail('arguments', f'{op} takes one collection or projection, as {op}(c.f)', node)
        source = self.expression(node.args[0], scope)
        if not (isinstance(source, Read) and isinstance(source.type, Many)):
            what = 'of values is min(a, b)' if op in ('min', 'max') else 'takes a collection'
            self.fail('collection', f'{op} {what}: {op}(c.f) reduces a projection', node)
        of = source.type.of
        if op == 'count':
            if isinstance(of, Num):
                self.fail(
                    'type',
                    'count counts members, or true values: sum(c.f) is the total of numbers, and '
                    'count(c) the number of members',
                    node,
                )
            if not (isinstance(of, (Ent, FlowOf)) or of == BOOL):
                self.fail('type', f'count counts members or yes/no values, not {of}', node)
            return Reduced(op, source, PLAIN)
        if op in ('any', 'all'):
            if of != BOOL:
                self.fail('type', f'{op} takes yes/no values, not {of}', node)
            return Reduced(op, source, BOOL)
        if not isinstance(of, Num):
            self.fail('type', f'{op} takes numbers, not {of}', node)
        return Reduced(op, source, of)

    # ---- paths -------------------------------------------------------------------------------------

    def item_field(self, scope, name):
        """Whether a bare name is a value of the member under test of a `where`."""
        found = self.syntax.get(f'{scope.item}.{name}') if scope.item is not None else None
        return found is not None and isinstance(found[1], n.Declaration)

    def path(self, node, scope):
        """What a name, a dotted path, a keyed operation or a literal names, as a `Read` with its
        type: a value, a member, a collection, a projection or a flow."""
        if isinstance(node, n.Name):
            return self.name(node, scope)
        if isinstance(node, n.Collection):
            return self.literal(node, scope)
        if isinstance(node, n.Method) and node.name in KEYED:
            return self.keyed(node, scope)
        if not isinstance(node, n.Member):
            self.fail('syntax', 'only a name, a member or a collection has parts', node)
        head = node.base.name if isinstance(node.base, n.Name) else None
        if head is not None and not self.item_field(scope, head):
            if head in self.tables:
                return self.row(head, node.name, node)
            if head in self.templates:
                if node.name == 'instances':
                    return Read(('instances', head), (), Many(Ent(head)), True)
                self.fail('unknown_name', f'{head} is a template: {head}.instances names its members', node)
            if node.name == 'instances' and head[:1].isupper():
                self.fail('unknown_name', f'{head} is no template' + close(head, self.templates), node)
        return self.step(self.path(node.base, scope), node.name, node)

    def name(self, node, scope):
        name = node.name
        if name == 'this':
            if not scope.owner:
                self.fail('unknown_name', 'this is the entity of a member: the top level has none', node)
            return Read(('this',), (), Ent(scope.owner), True)
        if name == 't':
            return Read(('time',), (), self.num('h', node))
        if self.item_field(scope, name):
            return self.step(Read(('item',), (), Ent(scope.item), True), name, node)
        if name in self.root:
            value = self.value(name)
            formula = name if value.kind == FORMULA else ''
            return Read(('root',), (name,), value.type, fixed_kind(value), formula, _stored(value))
        if name in self.entities:
            return Read(('named', name), (), Ent(name), True)
        if name in self.instances:
            return Read(('named', name), (), Ent(self.instances[name].type.name), True)
        if name in self.templates:
            self.fail('unknown_name', f'{name} is a template: {name}.instances names its members', node)
        if name in self.tables:
            template = self.tables[name].template
            self.fail(
                'unknown_name',
                f'{name} is a table: {name}.id names one of its rows, and {template}.instances every member',
                node,
            )
        if name[:1].isupper():
            raise Later('a member of an enum', 'S4')
        known = [*self.root, *self.entities, *self.instances]
        self.fail('unknown_name', f'{name} names nothing here' + close(name, known), node)

    def row(self, table, id, node):
        """`sites.clinic`: the row of a table by its id."""
        if table not in self.ids:
            raise Refused('depends', f'the table {table} has a problem of its own')
        ids = self.ids[table]
        if ids is None:
            self.fail('unknown_name', f'the rows of {table} have no ids: an id column names them', node)
        template = self.tables[table].template
        if id not in ids:
            if f'{template}.{id}' in self.syntax:
                self.fail(
                    'unknown_name',
                    f'{table} is a table, which names its rows by their ids: the {id} of every member is '
                    f'{template}.instances.{id}',
                    node,
                )
            self.fail('unknown_name', f'{table} has no row {id}' + close(id, ids), node)
        return Read(('named', f'{table}.{id}'), (), Ent(template), True)

    def step(self, base, name, node):
        """The read one step on from `base`: a part of a member (a projection from a collection), a
        rate or an end of a flow, a rate or a leg of a route, the fraction or a leg of a flow with
        legs, the outflow or the inflow of a stored number, or what an endpoint reads (its rates and
        its flows)."""
        kind = base.type
        many = isinstance(kind, Many)
        inner = kind.of if many else kind
        steps = (*base.steps, name)
        if isinstance(inner, Ent):
            template = inner.template
            path = f'{template}.{name}'
            if path not in self.syntax:
                parts = [key.split('.', 1)[1] for key in self.syntax if key.startswith(f'{template}.')]
                self.fail('unknown_name', f'{template} has no {name}' + close(name, parts), node)
            _, syntax = self.syntax[path]
            formula, stored = '', False
            if isinstance(syntax, n.Flow):
                found, steady = self.flow_type(path, template, syntax), False
            elif isinstance(syntax, n.Declaration):
                value = self.value(path)
                found, steady = value.type, base.fixed and fixed_kind(value)
                formula = path if base.fixed and value.kind == FORMULA else ''
                stored = _stored(value)
            else:
                raise Later('an event', 'S4') if isinstance(syntax, n.Event) else Later('a solver', 'S5')
            return Read(base.start, steps, self.projected(found, kind, name, node), steady, formula, stored)
        if isinstance(inner, FlowOf):
            if name in FLOW_READS and not (inner.view and name == 'capacity'):
                return Read(base.start, steps, Many(inner.rate, kind.key) if many else inner.rate)
            if name in ENDS:
                return self.end(base, inner, name, node)
            if inner.view:
                self.fail(
                    'unknown_name',
                    f'a leg of a route reads actual_rate, request, source and sink, not {name}: the '
                    "route's capacity limits both its legs",
                    node,
                )
            self.fail(
                'unknown_name',
                f'a directed flow reads actual_rate, request, capacity, source and sink, not {name}',
                node,
            )
        if isinstance(inner, RouteOf):
            if name in FLOW_READS:
                return Read(base.start, steps, Many(inner.rate, kind.key) if many else inner.rate)
            if name in ('forward', 'backward'):
                leg = FlowOf(inner.rate, f'{inner.flow}.{name}', view=True)
                return Read(base.start, steps, Many(leg, kind.key) if many else leg)
            hint = f': a route has its ends through its legs, as forward.{name}' if name in ENDS else ''
            self.fail(
                'unknown_name',
                f'a reversible route reads actual_rate, request, capacity, forward and backward, not '
                f'{name}{hint}',
                node,
            )
        if isinstance(inner, LegsOf):
            owner, parent = self.syntax[inner.flow]
            leg = next((each for each in parent.legs if each.name == name), None)
            if leg is not None:
                found = FlowOf(self.rate(owner, leg), f'{inner.flow}.{name}')
                return Read(base.start, steps, Many(found, kind.key) if many else found)
            if name == 'served_fraction':
                return Read(base.start, steps, Many(PLAIN, kind.key) if many else PLAIN)
            if name in FLOW_READS:
                self.fail(
                    'type',
                    f'a flow with legs has no {name} of its own: read a leg, as '
                    f'{parent.name}.{parent.legs[0].name}.{name}, or its served_fraction',
                    node,
                )
            legs = [each.name for each in parent.legs]
            self.fail(
                'unknown_name',
                f'{parent.name} reads served_fraction and its legs ({", ".join(legs)}), not {name}'
                + close(name, legs),
                node,
            )
        if isinstance(inner, EndOf):
            if name in FLOW_READS:
                return Read(base.start, steps, Many(inner.rate, kind.key) if many else inner.rate)
            if name == 'flows':
                return Read(base.start, steps, self.projected(Many(FlowOf(inner.rate)), kind, name, node))
            if name == 'allocation':
                self.fail(
                    'allocation',
                    'an allocation is no value: it is set under the store, as outflow.allocation = '
                    'priority(...)',
                    node,
                )
            self.fail(
                'unknown_name',
                f'an outflow or an inflow reads actual_rate, request, capacity and flows, not {name}',
                node,
            )
        if name in SIDES:
            if not base.stored:
                self.fail(
                    'flow_end',
                    f'{".".join(base.steps) or name} is no stored number: a store has an outflow and an '
                    'inflow',
                    node,
                )
            return Read(base.start, steps, self.projected(EndOf(self.per_hour(inner)), kind, name, node))
        if isinstance(inner, Dist) and name in ('mean', 'std'):
            raise Later("a distribution's mean and std", 'S4')
        self.fail('unknown_name', f'{name} is no part of a value of {kind}', node)

    def projected(self, found, kind, name, node):
        """The type of a step: of the one thing that it names, or from a collection the projection
        of it over each member, with the collection's keys. A projection of collections is none."""
        if not isinstance(kind, Many):
            return found
        if isinstance(found, Many):
            self.fail(
                'collection',
                f'{name} is a collection on each member, and a projection of collections is no '
                'collection: reduce it on the member, then reduce that value',
                node,
            )
        return Many(found, kind.key)

    def literal(self, node, scope):
        """`<a, b>`: members of one template, each named once."""
        if not node.items:
            self.fail('collection', 'an empty collection needs its type: name: <Template> = <>', node)
        items = tuple(self.path(item, scope) for item in node.items)
        for item in items:
            if not isinstance(item.type, Ent):
                self.fail('collection', f'a collection lists members, and one of these is {item.type}', node)
        templates = sorted({item.type.template for item in items})
        if len(templates) > 1:
            self.fail(
                'collection', f'a collection holds members of one template, not {", ".join(templates)}', node
            )
        if len(set(items)) < len(items):
            self.fail('duplicate_literal', 'a collection names each member once', node)
        return Read(('literal', items), (), Many(Ent(templates[0])), all(item.fixed for item in items))

    def keyed(self, node, scope):
        """`c.where(test)`, `c.by(field)` and `c.at(key)` of a collection of members."""
        source = self.path(node.base, scope)
        if not (isinstance(source.type, Many) and isinstance(source.type.of, Ent)):
            self.fail(
                'collection', f'.{node.name}(...) takes a collection of members, not {source.type}', node
            )
        of, key = source.type.of, source.type.key
        if len(node.args) != 1:
            self.fail('arguments', f'.{node.name}(...) takes one argument', node)
        (arg,) = node.args
        if node.name == 'where':
            test = self.expression(arg, Scope(scope.owner, of.template))
            self.want_bool(test, node, 'where')
            for read in reads_of(test):
                if read.start == ('item',) and not read.fixed:
                    self.fail(
                        'where_live',
                        f'where tests what is fixed for each member, and {".".join(read.steps)} is not: '
                        'for a live test, put a yes/no formula on the member and reduce it',
                        node,
                    )
            return Read(('where', source, test), (), source.type, source.fixed and fixed(test))
        if node.name == 'by':
            path = f'{of.template}.{getattr(arg, "name", "")}'
            if not isinstance(arg, n.Name) or not isinstance(self.syntax.get(path, (0, 0))[1], n.Declaration):
                parts = [k.split('.', 1)[1] for k in self.syntax if k.startswith(f'{of.template}.')]
                self.fail(
                    'unknown_name',
                    f'by names a value of {of.template}' + close(getattr(arg, 'name', ''), parts),
                    node,
                )
            value = self.value(path)
            if not isinstance(value.type, Num):
                self.fail('type', f'a key is a number, and {arg.name} is {value.type}', node)
            return Read(
                ('by', source, arg.name), (), Many(of, value.type), source.fixed and fixed_kind(value)
            )
        found = self.expression(arg, scope)
        self.want_number(found, node, '.at')
        if found.type.dimension != key.dimension:
            if not _zero(found):
                self.fail('unit', f'.at(...) reads a key in {key}, not {found.type}', node)
            found = Const(found.value, key)
        return Read(('lookup', source, found), (), of, source.fixed and fixed(found))

    def link_target(self, found, expected, node):
        """The id of the member that a link's initializer names: an entity, an instance or a row."""
        if not (
            isinstance(found, Read)
            and found.start[0] == 'named'
            and not found.steps
            and isinstance(found.type, Ent)
        ):
            self.fail(
                'link',
                'a link names a member: an entity, an instance or a row of a table (sites.junction)',
                node,
            )
        if expected is not None and found.type != expected:
            self.fail(
                'type',
                f'the link is to a member of {expected.template}, and {found.start[1]} is a member of '
                f'{found.type.template}',
                node,
            )
        return found.start[1]

    # ---- values ------------------------------------------------------------------------------------

    def value(self, path):
        """The declared value of a path, resolved once; a later-slice value raises `Later` again."""
        if path in self.done:
            found = self.done[path]
            if isinstance(found, Deferred):
                raise Later(found.construct, found.slice)
            if found is None:
                raise Refused('depends', f'{path} has a problem of its own')
            return found
        owner, syntax = self.syntax[path]
        if path in self.active:
            self.fail(
                'cycle',
                f'{path} reads itself through its initializer: its starting value has no order',
                syntax,
            )
        self.active.add(path)
        try:
            found = self.declaration(path, Scope(owner), syntax)
        except Later as later:
            self.done[path] = Deferred(path, later.construct, later.slice, syntax.line)
            raise
        except Refused:
            self.done[path] = None
            raise
        finally:
            self.active.discard(path)
        self.done[path] = found
        return found

    def declaration(self, path, scope, node):
        declared, retained = (None, False) if node.type is None else self.declared_type(node.type)
        template = scope.owner in self.templates
        if node.value is None:
            if isinstance(declared, Ent):
                if not template:
                    self.fail(
                        'link',
                        f'{node.name} names no member: a link of an entity names its member, as '
                        f'{node.name} = pump_a',
                        node,
                    )
                return self.finish(path, scope, node, LINK, declared, None)
            if template and declared is not None and not retained:
                kind = (
                    COLLECTION if isinstance(declared, Many) else INPUT if node.modifier == 'input' else STATE
                )
                return self.finish(path, scope, node, kind, declared, None)
            self.fail(
                'no_value', f'{node.name} has no starting value: an annotation gives no value (D4)', node
            )
        unit = declared if isinstance(declared, Num) else None
        kind, init = self.initializer(node, scope, declared, retained, unit)
        value_type = init.type if declared is None else declared
        if declared is not None and not compatible(init.type, declared):
            code = 'unit' if isinstance(declared, Num) and isinstance(init.type, Num) else 'type'
            self.fail(code, f'{node.name} is declared {declared}, and its initializer is {init.type}', node)
        if isinstance(init, Retain) and isinstance(init.type, (Ent, Many)):
            self.fail(
                'formula', 'a formula gives a number, a yes/no or a text, not a member or a collection', node
            )
        if isinstance(init.type, Ent):
            if not scope.owner:
                self.fail(
                    'link',
                    'a link belongs to an entity or a template; at the top level, name: Template is an instance',
                    node,
                )
            if node.modifier == 'input':
                self.fail('link', f'{node.name} is a link, fixed for the run: it is no input', node)
            self.link_target(init, None, node)
            kind = LINK
        elif isinstance(init.type, Many):
            if isinstance(init.type.of, FlowOf):
                self.fail(
                    'collection',
                    'a collection of flows is read where it stands, as count(c) or sum(c.actual_rate): '
                    'it is no value of its own',
                    node,
                )
            if not isinstance(init.type.of, Ent):
                self.fail(
                    'collection',
                    'a projection is no list of values: put the calculation on the member and reduce it, '
                    'as sum(c.f)',
                    node,
                )
            if init.steps or init.start[0] not in ('literal', 'instances', 'where', 'by'):
                self.fail(
                    'collection',
                    'a collection value is a literal, the instances of a template, or a where or a by of one',
                    node,
                )
            if node.modifier == 'input':
                self.fail('collection', f'{node.name} is a collection: it is no input', node)
            kind = COLLECTION
        return self.finish(path, scope, node, kind, value_type, init)

    def finish(self, path, scope, node, kind, value_type, init):
        """The declared value, with its range, its scale and its evidence."""
        lower = upper = scale = None
        if node.range is not None:
            if not isinstance(value_type, Num):
                self.fail(
                    'range', f'a range belongs to a number, and {node.name} is {value_type}', node.range
                )
            lower, upper = (
                self.bound(end, scope, value_type, node) for end in (node.range.low, node.range.high)
            )
            if isinstance(lower, Const) and isinstance(upper, Const) and lower.value > upper.value:
                self.fail(
                    'range',
                    f'the range of {node.name} is reversed: [{lower.value}, {upper.value}]',
                    node.range,
                )
        if node.scale is not None:
            if not isinstance(value_type, Num):
                self.fail('range', f'a scale belongs to a number, and {node.name} is {value_type}', node)
            scale = self.bound(node.scale, scope, value_type, node)
        if kind == INPUT and isinstance(init, Drawn):
            lower, upper = self.support(init.source, lower, upper, node)
        found = DeclaredValue(
            path,
            node.name,
            kind,
            value_type,
            init,
            lower,
            upper,
            scale,
            node.modifier == 'readonly',
            node.text,
            self.evidence(node),
            node.line,
        )
        self.within(init, found, node)
        return found

    def initializer(self, node, scope, declared, retained, unit):
        """(kind, typed initializer) of a declaration."""
        value = node.value
        if isinstance(value, n.Formula):
            if node.modifier == 'input':
                self.fail('formula', 'an input is fixed for the run: it cannot keep a calculation', node)
            if declared is not None and not retained:
                self.fail(
                    'formula',
                    f'{node.name} keeps a calculation: declare it {node.name}: formula({declared})',
                    node,
                )
            body = self.expression(value.body, scope)
            return FORMULA, Retain(body, body.type)
        if retained:
            self.fail('formula', f'{node.name} is declared a formula: its initializer is formula(...)', node)
        if isinstance(value, n.Collection) and not value.items:
            if not isinstance(declared, Many):
                self.fail(
                    'collection', f'an empty collection needs its type: {node.name}: <Template> = <>', node
                )
            return STATE, Read(('literal', ()), (), declared, True)
        if isinstance(value, n.Call) and (value.function in ARITY or value.function == 'categorical'):
            source = self.distribution(value, unit.of if isinstance(unit, Dist) else unit)
            return (INPUT if node.modifier == 'input' else DISTRIBUTION), source
        if isinstance(value, n.Method) and value.name == 'draw' and not value.args:
            if node.modifier != 'input':
                raise Later(*LATER_METHODS['draw'])
            if not (isinstance(value.base, n.Call) and value.base.function in ARITY):
                raise Later('the draw of a distribution that a value holds', 'S4')
            source = self.distribution(value.base, unit)
            return INPUT, Drawn(source, source.type.of)
        init = self.expression(value, scope, unit)
        return (INPUT if node.modifier == 'input' else STATE), init

    def bound(self, node, scope, unit, owner):
        """An end of a range, or a scale: a bare number takes the value's unit."""
        if node is None:
            return None
        found = self.expression(node, scope, unit)
        if not compatible(found.type, unit):
            if _zero(found):
                return Const(found.value, unit)
            self.fail(
                'unit', f'the range and the scale of {owner.name} are in {unit}, not {found.type}', node
            )
        return found

    def within(self, found, value, node):
        """A number written in place (a starting value, a member's value, a cell) lies in the value's
        range."""
        if not isinstance(found, Const) or not isinstance(found.type, Num):
            return
        at = Fraction(found.value) * self.scale(found.type)
        for bound, sign, side in ((value.lower, 1, 'below'), (value.upper, -1, 'above')):
            if isinstance(bound, Const) and sign * (at - Fraction(bound.value) * self.scale(bound.type)) < 0:
                written = f'{found.value} {found.type.unit}'.strip()
                self.fail('range', f'{written} is {side} the range of {value.name}', node)

    def distribution(self, node, unit):
        """A distribution of numbers: its value arguments take the declared unit, or they write one."""
        if node.function == 'categorical':
            raise Later('a categorical distribution', 'S4')
        if len(node.args) not in ARITY[node.function]:
            counts = ' or '.join(str(count) for count in ARITY[node.function])
            self.fail('arguments', f'{node.function} takes {counts} arguments', node)
        found = [literal(arg) for arg in node.args]
        if any(item is None for item in found):
            raise Later('a distribution whose arguments are values', 'S4')
        shapes = SHAPES.get(node.function, set())
        written = {
            item[1].unit
            for k, item in enumerate(found)
            if k not in shapes and isinstance(item[1], n.Quantity)
        }
        target = unit
        if target is None and written:
            first = next(
                item for k, item in enumerate(found) if k not in shapes and isinstance(item[1], n.Quantity)
            )
            target = self.quantity(1, first[1], TOP).type
        target = target or PLAIN
        params = []
        for k, (value, written_node) in enumerate(found):
            if k in shapes:
                if isinstance(written_node, n.Quantity):
                    self.fail('unit', f'the argument {k + 1} of {node.function} is a plain number', node)
                params.append(value)
                continue
            if isinstance(written_node, n.Quantity):
                own = self.quantity(1, written_node, TOP).type
                if own.dimension != target.dimension:
                    self.fail('unit', f'{node.function} takes its arguments in {target}, not {own}', node)
                params.append(
                    _converted(
                        value, self.units.of(own.unit)[1], self.units.of(target.unit)[1] if target.unit else 1
                    )
                )
            elif target.dimension and unit is None:
                self.fail(
                    'unit', f'{node.function} has an argument with no unit beside one in {target}', node
                )
            else:
                params.append(value)
        return Distribution(node.function, tuple(params), Dist(target))

    def support(self, source, lower, upper, node):
        """The range of an input whose default draws: the written range, which must hold the support
        of the distribution, or the support of a bounded distribution."""
        params, unit = source.params, source.type.of
        if len(params) == 4:
            ends = (params[2], params[3])
        elif source.family == 'normal':
            ends = (-math.inf, math.inf)
        elif source.family == 'lognormal':
            ends = (0, math.inf)  # above zero; the default range leaves both sides open
        else:
            ends = (params[0], params[-1])
        if lower is None and upper is None:
            if source.family in ('normal', 'lognormal') and len(params) == 2:
                return None, None
            return Const(ends[0], unit), Const(ends[1], unit)
        scale = self.scale(unit)
        for end, bound, sign in ((ends[0], lower, 1), (ends[1], upper, -1)):
            if not isinstance(bound, Const):
                continue
            if sign * (bound.value * self.scale(bound.type) - end * scale) > 0:
                self.fail(
                    'range',
                    f'the range of {node.name} must hold the support of its distribution, '
                    f'[{ends[0]}, {ends[1]}] {unit.unit}'.rstrip(),
                    node,
                )
        return lower, upper

    def scale(self, kind):
        """The size of one of a number's unit in the canonical unit of its dimension."""
        return self.units.of(kind.unit)[1] if kind.unit else 1

    def evidence(self, node):
        """The records that a line cites and those written under it; each cited name is a record."""
        found = (*node.cites, *node.evidence)
        for item in found:
            if isinstance(item, n.Cite) and item.name not in self.records:
                self.fail(
                    'unknown_record',
                    f'@{item.name} names no record of the model' + close(item.name, self.records),
                    item,
                )
        return found

    # ---- flows and endpoints ---------------------------------------------------------------------

    def flow_type(self, path, owner, node):
        """The type of a declared flow: a directed flow, a reversible route or a flow with legs."""
        if node.arrow == '->':
            return FlowOf(self.rate(owner, node), path)
        if node.arrow == '<->':
            return RouteOf(self.rate(owner, node), path)
        return LegsOf(path)

    def rate(self, owner, node):
        """The type of the rates of a directed flow, a leg or a route, from its ends (a store's unit
        per hour), or for `SOURCE -> SINK` from a rate written with its unit."""
        # As the program's builder does: a rate written with its unit first, then a store's unit per hour.
        for item in node.properties:
            found = literal(item.value.body if isinstance(item.value, n.Formula) else item.value)
            if (
                item.path[-1] in ('request', 'capacity')
                and found is not None
                and isinstance(found[1], n.Quantity)
            ):
                return self.quantity(1, found[1], Scope(owner)).type
        for end in (node.source, node.sink):
            if end not in (('SOURCE',), ('SINK',)):
                return self.per_hour(self.store(end, owner, node).type)
        self.fail('flow_units', f'flow {node.name}: SOURCE -> SINK needs a rate written with its unit', node)

    def store(self, end, owner, node):
        """The `Read` of the stored number that an end of a flow names, in the scope of the flow's
        owner: a store of its own member (`this.water`), through links (`this.origin.power`), of a
        named member (`reservoir.water`, `sites.junction.power`) or of the top level."""
        written = n.Name(end[0], line=node.line, column=node.column)
        for name in end[1:-1]:
            written = n.Member(written, name, line=node.line, column=node.column)
        spelled = '.'.join(end)
        found = self.path(written, Scope(owner))
        if len(end) > 1:
            kind = found.type.of if isinstance(found.type, Many) else found.type
            if isinstance(kind, Ent) and f'{kind.template}.{end[-1]}' not in self.syntax:
                self.fail('flow_end', f'{spelled} is no stored number of {kind.template}', node)
            found = self.step(found, end[-1], node)
        if isinstance(found.type, Many):
            self.fail('flow_end', f'{spelled} is a projection: an end of a flow is one stored number', node)
        if not found.stored:
            self.fail(
                'flow_end',
                f'{spelled} is no stored number: a flow ends at a stored value, SOURCE or SINK',
                node,
            )
        return found

    def flow(self, path, owner, node):
        """A declared flow: a directed flow (or a leg), a reversible route (`DeclaredRoute`), or a
        flow with legs (`DeclaredLegs`). Each end is `SOURCE`, `SINK` or a stored number of the
        dimension of the rates per time; the parser keeps `SOURCE` and `SINK` off a route."""
        if not node.arrow:
            return self.legs(path, owner, node)
        rate = self.rate(owner, node)
        ends = []
        for end in (node.source, node.sink):
            if end in (('SOURCE',), ('SINK',)):
                ends.append(end[0])
                continue
            store = self.store(end, owner, node)
            if self.per_hour(store.type).dimension != rate.dimension:
                self.fail(
                    'flow_units',
                    f'flow {node.name}: its ends and its rates are of two dimensions '
                    f'({store.type} against {rate}; a rate is its stock per time)',
                    node,
                )
            ends.append(store)
        route = node.arrow == '<->'
        settings = {}
        for item in node.properties:
            key = '.'.join(item.path)
            if key not in ('request', 'capacity'):
                what = 'a reversible route' if route else 'a directed flow'
                self.fail('property', f'{what} takes request and capacity, not {key}', item)
            if key in settings:
                self.fail('property', f'{key} is given twice', item)
            settings[key] = self.rate_setting(item, Scope(owner), rate, f'the {key} of {node.name}')
        return (DeclaredRoute if route else DeclaredFlow)(
            path,
            node.name,
            ends[0],
            ends[1],
            rate,
            settings.get('request'),
            settings.get('capacity'),
            node.text,
            self.evidence(node),
            node.line,
        )

    def legs(self, path, owner, node):
        """A flow with legs: each leg a directed flow of its own, at `path.leg`, named once, and by no
        name that the flow reads or refuses itself (`restore.served_fraction`, `restore.request`)."""
        legs, seen = [], {}
        for leg in node.legs:
            if leg.name in ('served_fraction', *FLOW_READS):
                self.fail(
                    'reserved',
                    f'a leg is not named {leg.name}: {node.name}.{leg.name} reads the flow with legs',
                    leg,
                )
            if leg.name in seen:
                self.fail(
                    'duplicate_name',
                    f'{node.name} has two legs named {leg.name}; the first is on line {seen[leg.name]}',
                    leg,
                )
            seen[leg.name] = leg.line
            legs.append(self.flow(f'{path}.{leg.name}', owner, leg))
        return DeclaredLegs(path, node.name, tuple(legs), node.text, self.evidence(node), node.line)

    def end(self, base, flow, name, node):
        """`f.source` or `f.sink` of one declared flow, leg or leg of a route (`base` reads the flow):
        the store at that end, read as that store, with its amount and the steps of a store. The ends
        of a flow are fixed for the run, so the read goes to the store's own path, from the member of
        the flow: `this.main.sink` of `flow main: SOURCE -> this.water` reads `this.water`, and
        `Site.instances.restore.labor.sink` reads `Site.instances.crew.used`. An end at SOURCE or SINK
        holds nothing to read, and a member of an endpoint's `flows` may end anywhere."""
        if not flow.flow:
            self.fail(
                'flow_end',
                f'a member of flows may end at any store, or at SOURCE or SINK: read the {name} of a '
                f'declared flow, as this.main.{name}',
                node,
            )
        owner, ends = self.ends_of(flow)
        end = ends[0] if name == 'source' else ends[1]
        if end in (('SOURCE',), ('SINK',)):
            self.fail('flow_end', f'the {name} of {flow.flow} is {end[0]}, which holds nothing to read', node)
        store = self.store(end, owner, node)
        many = isinstance(base.type, Many)
        if store.start != ('this',):
            if many:
                self.fail(
                    'collection',
                    f'the {name} of {flow.flow} is {".".join(end)} for every member: read it by its path',
                    node,
                )
            return store
        # The flow's own steps follow its member's: one for a flow, two for a leg (`restore.labor`).
        member = base.steps[: -flow.flow.count('.')]
        kind = Many(store.type, base.type.key) if many else store.type
        return Read(base.start, (*member, *store.steps), kind, stored=not many)

    def ends_of(self, flow):
        """The owner of a declared flow, leg or leg of a route, and its two ends as written: a leg of
        a route runs from its route's first end (`forward`) or from its second (`backward`)."""
        if flow.flow in self.syntax:
            owner, node = self.syntax[flow.flow]
            return owner, (node.source, node.sink)
        parent, _, name = flow.flow.rpartition('.')
        owner, node = self.syntax[parent]
        if flow.view:
            return owner, ((node.source, node.sink) if name == 'forward' else (node.sink, node.source))
        leg = next(each for each in node.legs if each.name == name)
        return owner, (leg.source, leg.sink)

    def rate_setting(self, item, scope, rate, what):
        """A request or a capacity (of a flow or of an endpoint): a rate of the dimension of `rate`,
        captured once, or a `Retain`; a bare zero takes the rate's unit."""
        if isinstance(item.value, n.Formula):
            body = self.expression(item.value.body, scope)
            found = Retain(body, body.type)
        else:
            found = self.expression(item.value, scope)
        if not compatible(found.type, rate):
            if not _zero(found):
                self.fail('unit', f'{what} is a rate in {rate}, not {found.type}', item)
            found = Const(found.value, rate)
        return found

    def endpoints(self, value, owner, node):
        """A value with the settings of its outflow and its inflow, written under it: only a stored
        number has them. Each setting is resolved after the value, so that it may read the store (a
        request that fills a tank to a level). A setting with a problem is reported, or deferred,
        and leaves the value as it is."""
        if not node.properties:
            return value
        if not _stored(value):
            self.report(
                'property',
                f'{value.name} is no stored number: only a store takes the settings of its outflow and '
                'its inflow (capacity, request, allocation)',
                node.properties[0].line,
            )
            return value
        scope, sides = Scope(owner), {}
        for item in node.properties:
            key = '.'.join(item.path)
            side = item.path[0]
            if len(item.path) != 2 or side not in SIDES or item.path[1] not in SETTINGS:
                self.report(
                    'property',
                    f'{key} is no setting of a store: a store takes outflow.capacity, outflow.request, '
                    'outflow.allocation and the same of inflow',
                    item.line,
                )
                continue
            settings = sides.setdefault(side, {'line': item.line})
            if item.path[1] in settings:
                self.report('property', f'{key} is given twice', item.line)
                continue
            try:
                if item.path[1] == 'allocation':
                    settings['allocation'] = self.allocation(item.value, scope)
                else:
                    rate = self.per_hour(value.type)
                    settings[item.path[1]] = self.rate_setting(item, scope, rate, f'{value.name}.{key}')
            except Later as later:
                self.deferred.append(Deferred(f'{value.path}.{key}', later.construct, later.slice, item.line))
            except Refused as refused:
                if refused.code != 'depends':
                    self.report(refused.code, refused.message, refused.line or item.line, refused.column)
        found = {
            side: DeclaredEndpoint(
                f'{value.path}.{side}',
                settings.get('capacity'),
                settings.get('request'),
                settings.get('allocation', ('proportional',)),
                settings['line'],
            )
            for side, settings in sides.items()
        }
        value = replace(value, outflow=found.get('outflow'), inflow=found.get('inflow'))
        self.done[value.path] = value
        return value

    def allocation(self, node, scope):
        """`proportional()`, or `priority(...)` over flows, first to last: each a directed flow
        (`hospital.delivery`, `this.main`), a leg of a flow with legs (`this.restore.labor`), a leg of
        a route (`this.link.forward`), or a projection of these over a collection
        (`Customer.instances.by(rank).delivery`, ranked by the collection's keys), each named once.
        A bare route or a flow with legs is no claim at one endpoint. That each flow is incident at
        the store, in its direction, is the program's rule (`check.priority_item`)."""
        if not (isinstance(node, n.Call) and node.function in ALLOCATIONS):
            self.fail('allocation', 'an allocation is priority(...) or proportional()', node)
        if node.function == 'proportional':
            if node.args:
                self.fail('arguments', 'proportional() takes no argument', node)
            return ('proportional',)
        if not node.args:
            self.fail('arguments', 'priority(...) names the flows that it serves first, in order', node)
        items = []
        for arg in node.args:
            if not isinstance(arg, (n.Name, n.Member, n.Method)):
                self.fail('priority_item', 'priority(...) names flows, as hospital.delivery', arg)
            found = self.path(arg, scope)
            kind = found.type.of if isinstance(found.type, Many) else found.type
            if isinstance(kind, RouteOf):
                self.fail(
                    'priority_item',
                    'a reversible route is no claim at one endpoint: name its leg in the direction of '
                    'this endpoint, as link.forward or link.backward',
                    arg,
                )
            if isinstance(kind, LegsOf):
                self.fail(
                    'priority_item',
                    'a flow with legs is no claim at one endpoint: name its leg at this endpoint, as '
                    'restore.labor',
                    arg,
                )
            if not isinstance(kind, FlowOf) or not kind.flow:
                what = "an endpoint's collection of flows" if isinstance(kind, FlowOf) else str(found.type)
                self.fail(
                    'priority_item',
                    f'priority(...) ranks flows, or a projection of flows (customers.by(rank).delivery), '
                    f'not {what}',
                    arg,
                )
            items.append(found)
        if len(set(items)) < len(items):
            self.fail('priority_item', 'priority(...) names each flow once', node)
        return ('priority', tuple(items))

    def assertion(self, path, scope, node):
        """An assertion over what is fixed for the run, checked once; one that reads state is a later
        slice's."""
        test = self.expression(node.test, scope)
        self.want_bool(test, node, 'assert')
        if not self.over_inputs(test):
            raise Later('an assertion over state', 'S4')
        return DeclaredAssert(path, test, node.text, self.evidence(node), node.line)

    def over_inputs(self, expression):
        """Whether an expression reads only what is fixed for the run, also through the formulas that
        it reads: each formula is looked at once, so a deep chain of shared formulas costs its length."""
        for read in reads_of(expression):
            if read.fixed:
                continue
            if not read.formula:
                return False
            if read.formula not in self.inputs_only:
                template, _, name = read.formula.rpartition('.')
                # A member written by hand may replace its template's formula with one of its own.
                replaced = any(
                    member.type.name == template and any(item.path == (name,) for item in member.properties)
                    for member in self.instances.values()
                )
                found = not replaced and self.over_inputs(self.value(read.formula).init.body)
                self.inputs_only[read.formula] = found
            if not self.inputs_only[read.formula]:
                return False
        return True

    # ---- members -----------------------------------------------------------------------------------

    def given(self, template, path, node, line_node, evidence):
        """A member's own value or link: (whether it is a link, the `Given`)."""
        if len(path) != 1:
            self.fail(
                'property',
                f'{".".join(path)} is a setting of a part of {template}: a member gives the values and '
                'the links of its template, and its template the settings of its parts',
                line_node,
            )
        (name,) = path
        found = self.syntax.get(f'{template}.{name}')
        if found is None:
            parts = [key.split('.', 1)[1] for key in self.syntax if key.startswith(f'{template}.')]
            self.fail('unknown_name', f'{template} has no {name}' + close(name, parts), line_node)
        if isinstance(found[1], n.Flow):
            self.fail(
                'property',
                f"{name} is a flow of {template}: the settings of a flow are its template's",
                line_node,
            )
        if not isinstance(found[1], n.Declaration):
            raise Later('an event', 'S4') if isinstance(found[1], n.Event) else Later('a solver', 'S5')
        value = self.value(f'{template}.{name}')
        scope, line = Scope(template), line_node.line
        if value.kind == LINK:
            target = self.link_target(self.expression(node, scope), value.type, node)
            return True, Given(name, target, evidence, line)
        if value.kind == FORMULA:
            if not isinstance(node, n.Formula):
                self.fail(
                    'formula',
                    f'{name} is a formula of {template}: a member replaces it with formula(...)',
                    node,
                )
            body = self.expression(node.body, scope)
            if not compatible(body.type, value.type):
                self.fail('unit', f'{name} of {template} is {value.type}, and this formula {body.type}', node)
            return False, Given(name, Retain(body, body.type), evidence, line)
        if isinstance(node, n.Formula):
            self.fail(
                'formula', f'{name} of {template} keeps no calculation: a member gives it a value', node
            )
        if isinstance(value.type, Dist):
            if not (isinstance(node, n.Call) and node.function in ARITY):
                self.fail(
                    'type', f'{name} holds a distribution: a member gives another, as uniform(1 h, 3 h)', node
                )
            found = self.distribution(node, value.type.of)
            return False, Given(name, found, evidence, line)
        unit = value.type if isinstance(value.type, Num) else None
        if isinstance(node, n.Collection) and not node.items and isinstance(value.type, Many):
            return False, Given(name, Read(('literal', ()), (), value.type, True), evidence, line)
        found = self.expression(node, scope, unit)
        if not compatible(found.type, value.type):
            if not (_zero(found) and isinstance(value.type, Num)):
                code = 'unit' if isinstance(found.type, Num) and isinstance(value.type, Num) else 'type'
                self.fail(code, f'{name} of {template} is {value.type}, and this value is {found.type}', node)
            found = Const(found.value, value.type)
        if value.kind == COLLECTION and (
            found.steps or found.start[0] not in ('literal', 'instances', 'where', 'by')
        ):
            self.fail(
                'collection',
                'a collection value is a literal, the instances of a template, or a where or a by of one',
                node,
            )
        self.within(found, value, node)
        return False, Given(name, found, evidence, line)

    def instance(self, node):
        """A member written by hand: `north: Utility` with its own values and links under it."""
        template = node.type.name
        if node.range is not None or node.scale is not None:
            self.fail(
                'range', f'{node.name} is a member: a range or a scale belongs to a value of {template}', node
            )
        values, links, seen = [], [], {}
        for item in node.properties:
            key = '.'.join(item.path)
            if key in seen:
                self.report('property', f'{key} is given twice; the first is on line {seen[key]}', item.line)
                continue
            seen[key] = item.line
            try:
                is_link, found = self.given(template, item.path, item.value, item, self.evidence(item))
            except Later as later:
                self.deferred.append(Deferred(f'{node.name}.{key}', later.construct, later.slice, item.line))
                continue
            except Refused as refused:
                if refused.code != 'depends':
                    self.report(refused.code, refused.message, refused.line or item.line, refused.column)
                continue
            (links if is_link else values).append(found)
        member = DeclaredMember(
            node.name, template, tuple(values), tuple(links), None, node.text, self.evidence(node), node.line
        )
        self.complete(member, {path[0] for path in (item.path for item in node.properties)})
        return member

    def complete(self, member, written=()):
        """Each link of a member names a member, and each value has a starting value (D4). A value that
        the member writes (`written`) has its own problem if it is not among its values."""
        given = {item.name for item in (*member.values, *member.links)} | set(written)
        if member.template not in self.owned:
            self.owned[member.template] = [
                key
                for key, (owner, syntax) in self.syntax.items()
                if owner == member.template and isinstance(syntax, n.Declaration)
            ]
        for key in self.owned[member.template]:
            if key.rpartition('.')[2] in given:
                continue
            try:
                value = self.value(key)
            except (Later, Refused):
                continue
            if value.init is not None:
                continue
            if value.kind == LINK:
                message = (
                    f'{member.path} sets no {value.name}: a link names a member, and there is no none value'
                )
                self.report('link_unset', message, member.line, 0, member.file)
            else:
                message = (
                    f'{member.path} gives no {value.name}, which {member.template} leaves without a value'
                )
                self.report('no_value', message, member.line, 0, member.file)

    # ---- tables ------------------------------------------------------------------------------------

    def load(self, node):
        """Read the form of a table and the ids of its rows, before any name is resolved."""
        if node.template not in self.templates:
            message = f'{node.template} is no template' + close(node.template, self.templates)
            self.report('unknown_name', message, node.line)
            return
        text, origin = self.read_table(node.file)
        if text is None:
            self.report('table', f'{node.file!r} {origin}', node.line)
            return
        try:
            data = tables.read(text, origin)
        except LanguageError as error:
            self.problems.extend(error.problems)
            return
        self.data[node.name] = data
        names = [column.name for column in data.columns]
        if 'id' not in names:
            self.ids[node.name] = None
            return
        where, ids = names.index('id'), {}
        for row in data.rows:
            cell = row.cells[where]
            if not cell:
                self.report(
                    'table',
                    f'a row of {node.name} has no id: each row of a table with ids has one',
                    row.line,
                    0,
                    origin,
                )
            elif not ID.match(cell):
                self.report(
                    'table',
                    f'the id {cell!r} is no name: an id is written as a name, as junction',
                    row.line,
                    0,
                    origin,
                )
            elif cell in ids:
                message = f'{node.name} names the row {cell} twice; the first is on line {ids[cell]}'
                self.report('duplicate_name', message, row.line, 0, origin)
            else:
                ids[cell] = row.line
        self.ids[node.name] = ids

    def table(self, node):
        """A table and its members, one for each row: each cell that is not empty is the row's value
        of its column."""
        data = self.data.get(node.name)
        if data is None:
            return None, []
        evidence = ()
        try:
            evidence = self.evidence(node)
        except Refused as refused:
            self.report(refused.code, refused.message, refused.line, refused.column)
        columns, names = [], [column.name for column in data.columns]
        for k, column in enumerate(data.columns):
            if column.name == 'id':
                continue
            try:
                columns.append((k, column, self.column(node.template, column)))
            except Refused as refused:
                if refused.code != 'depends':
                    self.report(refused.code, refused.message, 1, 0, data.origin)
            except Later as later:
                message = (
                    f'the column {column.name}: {later.construct} comes with a later slice ({later.slice})'
                )
                self.report('later_slice', message, 1, 0, data.origin)
        ids, members = self.ids[node.name], []
        for index, row in enumerate(data.rows):
            if ids is None:
                id = f'{node.name}[{index}]'
            else:
                cell = row.cells[names.index('id')]
                if ids.get(cell) != row.line:
                    continue  # a row without its own id has its problem already
                id = f'{node.name}.{cell}'
            values, links = [], []
            for k, column, value in columns:
                if not row.cells[k]:
                    continue
                try:
                    is_link, found = self.cell(value, column, row.cells[k], row.line)
                except Refused as refused:
                    if refused.code != 'depends':
                        self.report(refused.code, f'{id}: {refused.message}', row.line, 0, data.origin)
                    continue
                (links if is_link else values).append(found)
            member = DeclaredMember(
                id,
                node.template,
                tuple(values),
                tuple(links),
                node.name,
                None,
                evidence,
                row.line,
                data.origin,
            )
            self.complete(member, {name for name, cell in zip(names, row.cells) if cell})
            members.append(member)
        declared = DeclaredTable(
            node.name,
            node.template,
            node.file,
            data.origin,
            data.columns,
            tuple(member.path for member in members),
            node.text,
            evidence,
            node.line,
        )
        return declared, members

    def column(self, template, column):
        """The value or the link of the template that a column gives, with the unit of its header."""
        key = f'{template}.{column.name}'
        found = self.syntax.get(key)
        if found is None:
            parts = [name.split('.', 1)[1] for name in self.syntax if name.startswith(f'{template}.')]
            self.fail(
                'unknown_name',
                f'the column {column.name} names no value of {template}' + close(column.name, parts),
            )
        if not isinstance(found[1], n.Declaration):
            self.fail(
                'table',
                f'the column {column.name} names no value of {template}: a column gives a value or a link',
            )
        value = self.value(key)
        if value.kind not in (INPUT, STATE, LINK) or isinstance(value.type, Dist):
            self.fail(
                'table',
                f'the column {column.name} names a {value.kind} of {template} ({value.type}): a column '
                'gives a number, a yes/no or a text of an input or a stored value, or a link',
            )
        if column.unit is not None:
            if not isinstance(value.type, Num):
                self.fail('unit', f'{column.name} takes no number: its header names no unit')
            unit = self.num(column.unit)
            if unit.dimension != value.type.dimension:
                self.fail(
                    'unit',
                    f'the column {column.name} is in {unit}, and {template}.{column.name} in {value.type}',
                )
        for name in column.cites:
            if name not in self.records:
                self.fail(
                    'unknown_record', f'@{name} names no record of the model' + close(name, self.records)
                )
        return value

    def cell(self, value, column, text, line):
        """A cell as the row's value of its column: a number (in the unit of the header, its own, or
        the value's), true or false, a text, or for a link the name of a member."""
        cites = tuple(n.Cite(name, line=line) for name in column.cites)
        if value.kind == LINK:
            node = _cell_path(text) or _cell_expression(text)
            if not isinstance(node, (n.Name, n.Member)):
                self.fail('link', f'{text!r} names no member: a link cell names a row, as sites.junction')
            return True, Given(
                column.name, self.link_target(self.path(node, TOP), value.type, None), cites, line
            )
        if value.type == BOOL:
            if text not in ('true', 'false'):
                self.fail('table', f'{column.name} is a yes/no: true or false, not {text!r}')
            return False, Given(column.name, Const(text == 'true', BOOL), cites, line)
        if value.type == TEXT:
            return False, Given(column.name, Const(text, TEXT), cites, line)
        found = _cell_number(text) or literal(_cell_expression(text))
        if found is None or not isinstance(value.type, Num):
            self.fail(
                'table', f'{text!r} is not a number, true or false: a cell holds a value, not a calculation'
            )
        number, written = found
        if isinstance(written, n.Quantity):
            if column.unit is not None:
                self.fail(
                    'unit', f'the header of {column.name} gives its unit: a cell writes the number alone'
                )
            names = [name for _, name in written.unit]
            for name in names:
                if not self.units.has(name):
                    self.fail(
                        'unit',
                        f'{name} is no unit of the library or of the model' + close(name, self.units.base),
                    )
            unit = self.num(names[0] + ''.join(op + name for op, name in written.unit[1:]))
        else:
            unit = self.num(column.unit) if column.unit is not None else value.type
        if unit.dimension != value.type.dimension:
            self.fail('unit', f'{column.name} is in {value.type}, not {unit}')
        result = Const(number, unit)
        self.within(result, value, None)
        return False, Given(column.name, result, cites, line)

    # ---- the model ---------------------------------------------------------------------------------

    def part(self, path, owner, node):
        """A declared part of an entity, a template or the top level, a `Deferred` one, or None after
        a problem."""
        try:
            if isinstance(node, n.Declaration):
                return self.endpoints(self.value(path), owner, node)
            if isinstance(node, n.Flow):
                return self.flow(path, owner, node)
            if isinstance(node, n.Assert):
                return self.assertion(path, Scope(owner), node)
        except Later as later:
            return Deferred(path, later.construct, later.slice, node.line)
        except Refused as refused:
            if refused.code != 'depends':
                self.report(refused.code, refused.message, refused.line or node.line, refused.column)
            return None
        construct, slice_ = {
            n.Event: ('an event', 'S4'),
            n.Solver: ('a solver', 'S5'),
            n.Status: ('a status display', 'C'),
            n.Sees: ('sees', 'S4'),
            n.Property: ('a property set by its path', 'S6'),
        }[type(node)]
        return Deferred(path, construct, slice_, node.line)

    def entity(self, item):
        """An entity written once or a template, with its parts."""
        parts, asserts = [], 0
        for k, member in enumerate(item.members):
            if isinstance(member, n.Assert):
                name, asserts = f'assert[{asserts}]', asserts + 1
            else:
                name = getattr(member, 'name', None) or f'{type(member).__name__.lower()}[{k}]'
            found = self.part(f'{item.name}.{name}', item.name, member)
            if isinstance(found, Deferred):
                self.deferred.append(found)
            elif found is not None:
                parts.append(found)
        try:
            evidence = self.evidence(item)
        except Refused as refused:
            self.report(refused.code, refused.message, refused.line, refused.column)
            evidence = ()
        kind = DeclaredTemplate if item.name in self.templates else DeclaredEntity
        return kind(item.name, tuple(parts), item.text, item.title, item.role, evidence, item.line)

    def model(self):
        for item in self.tree.items:
            if isinstance(item, n.Table):
                self.load(item)
        entities = [self.entity(item) for item in self.tree.items if isinstance(item, n.Entity)]
        root, members, tables_, asserts, notes, scenario = [], [], [], [], [], None
        top_later = {
            n.Use: ('use', 'S6'),
            n.Change: ('change', 'S6'),
            n.Options: ('options', 'S6'),
            n.Runs: ('runs', 'S6'),
            n.Property: ('a property set by its path', 'S6'),
        }
        for index, item in enumerate(self.tree.items):
            if isinstance(item, n.Scenario):
                scenario = self.scenario(item)
            elif isinstance(item, (n.Entity, n.Record)):
                continue
            elif isinstance(item, n.Table):
                declared, rows = self.table(item)
                if declared is not None:
                    tables_.append(declared)
                    members.extend(rows)
            elif isinstance(item, n.Declaration) and item.name in self.instances:
                try:
                    members.append(self.instance(item))
                except Refused as refused:
                    self.report(refused.code, refused.message, refused.line or item.line, refused.column)
            elif isinstance(item, (n.Declaration, n.Assert)):
                path = item.name if isinstance(item, n.Declaration) else f'assert[{len(asserts)}]'
                found = self.part(path, '', item)
                if isinstance(found, Deferred):
                    self.deferred.append(found)
                elif isinstance(found, DeclaredAssert):
                    asserts.append(found)
                elif found is not None:
                    root.append(found)
            elif isinstance(item, n.Notes):
                notes.extend(item.notes)
            else:
                construct, slice_ = top_later[type(item)]
                self.deferred.append(
                    Deferred(
                        getattr(item, 'name', '') or f'{type(item).__name__.lower()}[{index}]',
                        construct,
                        slice_,
                        item.line,
                    )
                )
        if scenario is not None and scenario.role == 'variant':
            self.deferred.append(Deferred('scenario', 'a variant', 'S6', scenario.line))
        self.check_names()
        if not self.problems:
            self.problems.extend(Order(entities, members, root).cycles())
        if self.problems:
            raise LanguageError(sorted(self.problems, key=lambda item: (item.file, item.line, item.column)))
        return DeclaredModel(
            scenario,
            tuple(entities),
            tuple(root),
            tuple(self.records.values()),
            tuple(notes),
            tuple(self.deferred),
            self.units,
            self.tree,
            members=tuple(members),
            tables=tuple(tables_),
            asserts=tuple(asserts),
        )

    def check_names(self):
        """Two declarations of one scope with one name are an error."""
        seen = {}
        for item in self.tree.items:
            name = getattr(item, 'name', None)
            if isinstance(item, (n.Entity, n.Table, n.Declaration)) and name:
                if name in seen:
                    self.report(
                        'duplicate_name',
                        f'{name} is declared twice; the first is on line {seen[name]}',
                        item.line,
                    )
                seen.setdefault(name, item.line)
            if isinstance(item, n.Entity):
                own = {}
                for member in item.members:
                    member_name = getattr(member, 'name', None)
                    if isinstance(member, (n.Declaration, n.Flow, n.Event, n.Solver)) and member_name:
                        if member_name in own:
                            self.report(
                                'duplicate_name',
                                f'{item.name}.{member_name} is declared twice; the first is '
                                f'on line {own[member_name]}',
                                member.line,
                            )
                        own.setdefault(member_name, member.line)

    def scenario(self, node):
        def hours(value, key):
            if value is None:
                return None
            try:
                found = self.expression(value, TOP)
            except (Refused, Later):
                self.report('scenario', f'{key} is a time, such as 30 days', node.line)
                return None
            if not isinstance(found, Const) or found.type.dimension != (('time', 1),):
                self.report('scenario', f'{key} is a time, such as 30 days', node.line)
                return None
            return _converted(found.value, self.units.of(found.type.unit)[1], 1)

        return Scenario(
            'main' if node.role == 'scenario' else 'variant',
            node.title,
            node.summary,
            node.scope,
            node.library,
            hours(node.horizon, 'horizon'),
            hours(node.resolution, 'resolution'),
            tuple(hours(item, 'timescales') for item in node.timescales),
            node.line,
        )


class Order:
    """The starting values of a model's members follow their dependencies, across members and
    whatever the order of the file (spec, "Model-level initializers follow their value
    dependencies"): a value needs what its initializer reads, its own or its template's, and a
    formula what it reads. Links are fixed, so each read reaches known members. A cycle has no order
    and is an error, given at a value on it; mutual links are no cycle.

    A node is `(member, value)`, `('', value)` of the top level, or `('*', read)` for a read that is
    the same for every member (`sum(Place.instances.need)`), which is walked once, so a template's
    read of all its members costs the members once and not once for each of them."""

    def __init__(self, entities, members, root):
        self.parts = {
            entity.path: {part.name: part for part in entity.parts if isinstance(part, DeclaredValue)}
            for entity in entities
        }
        self.members = {entity.path: [] for entity in entities}
        self.own, self.template, self.files = {}, {}, {}
        for entity in entities:
            if not isinstance(entity, DeclaredTemplate):
                self.members[entity.path].append(entity.path)
                self.own[entity.path], self.template[entity.path] = {}, entity.path
                self.files[entity.path] = ''
        for member in members:
            self.members[member.template].append(member.path)
            self.own[member.path] = {given.name: given for given in (*member.values, *member.links)}
            self.template[member.path], self.files[member.path] = member.template, member.file
        self.root = {value.name: value for value in root}
        self.shared = {}

    def init(self, node):
        """The initializer of a node: the member's own, or its template's."""
        member, name = node
        if member == '':
            return self.root[name].init
        given = self.own[member].get(name)
        return given.init if given is not None else self.parts[self.template[member]][name].init

    def needs(self, expression, member, item=()):
        """The nodes that a typed expression reads for a member ('' at the top level), in the order
        in which it reads them (a dict used as an ordered set, so the search is the same each run)."""
        found = {}
        for read in reads_of(expression):
            if _own(read):
                self.walk(read, member, item, found)
            else:
                key = ('*', read)
                if key not in self.shared:
                    self.shared[key] = {}
                    self.walk(read, '', (), self.shared[key])
                found[key] = None
        return found

    def walk(self, read, member, item, found):
        """The members that a read reaches, adding to `found` each value that it reads on its way. A
        flow's rate is no starting value, so a read through a flow reaches nothing."""
        kind, steps = read.start[0], read.steps
        if kind == 'time':
            return {}
        if kind == 'root':
            value = self.root.get(steps[0])
            if value is None or value.kind != COLLECTION:
                if value is not None:
                    found[('', steps[0])] = None
                return {}
            current, steps = self.walk(value.init, '', (), found), steps[1:]
        else:
            current = self.starts(read.start, member, item, found)
        for step in steps:
            following = {}
            for each in current:
                part = self.parts[self.template[each]].get(step)
                if part is None:
                    continue
                if part.kind == LINK:
                    given = self.own[each].get(step)
                    target = given.init if given is not None else part.init and part.init.start[1]
                    if target:
                        following[target] = None
                elif part.kind == COLLECTION:
                    init = self.init((each, step))
                    if init is not None:
                        following.update(self.walk(init, each, (), found))
                else:
                    found[(each, step)] = None
            current = following
        return current

    def starts(self, start, member, item, found):
        kind = start[0]
        if kind == 'this':
            return {member: None}
        if kind == 'named':
            return {start[1]: None}
        if kind == 'item':
            return dict.fromkeys(item)
        if kind == 'instances':
            return dict.fromkeys(self.members.get(start[1], ()))
        if kind == 'literal':
            reached = {}
            for each in start[1]:
                reached.update(self.walk(each, member, item, found))
            return reached
        source = self.walk(start[1], member, item, found)
        if kind == 'where':
            found.update(self.needs(start[2], member, tuple(source)))
        elif kind == 'by':
            found.update(dict.fromkeys((each, start[2]) for each in source))
        else:
            found.update(self.needs(start[2], member, item))
        return source

    def cycles(self):
        """The problems of the cycles among the starting values: one for each cycle that the search
        meets, at the line of a value on it."""
        nodes = [('', name) for name in self.root]
        for member, template in self.template.items():
            nodes += [(member, name) for name, part in self.parts[template].items() if part.kind != LINK]
        state, problems, seen = {}, [], set()
        for first in nodes:
            if first in state:
                continue
            state[first] = 'open'
            stack = [(first, iter(self.edges(first)))]
            while stack:
                node, edges = stack[-1]
                following = next(edges, None)
                if following is None:
                    state[node] = 'done'
                    stack.pop()
                elif following not in state:
                    state[following] = 'open'
                    stack.append((following, iter(self.edges(following))))
                elif state[following] == 'open':
                    path = [each for each, _ in stack]
                    ring = [each for each in path[path.index(following) :] if each[0] != '*']
                    if frozenset(ring) not in seen:
                        seen.add(frozenset(ring))
                        problems.append(self.problem(ring))
        return problems

    def edges(self, node):
        """The nodes that a node needs; a constant needs none."""
        if node[0] == '*':
            return self.shared[node]
        init = self.init(node)
        if init is None or isinstance(init, Const):
            return ()
        return self.needs(init, node[0])

    def problem(self, ring):
        """The problem of a cycle, at the line of its first value: a member's own, in the file of the
        member, or its template's."""
        names = [f'{member}.{name}' if member else name for member, name in ring]
        member, name = ring[0]
        if member == '':
            line, file = self.root[name].line, ''
        elif name in self.own[member]:
            line, file = self.own[member][name].line, self.files[member]
        else:
            line, file = self.parts[self.template[member]][name].line, ''
        message = (
            f'the starting values of {" and ".join(names)} read each other: they have no order'
            if len(names) > 1
            else f'the starting value of {names[0]} reads itself: it has no order'
        )
        return Problem('cycle', message, line, 0, file)


def _own(read, bound=False):
    """Whether a read depends on the member that reads it: it starts at `this`, or at the member of an
    enclosing `where` (not `bound` by a `where` inside the read), or a collection or a key on the way
    does."""
    kind = read.start[0]
    if kind == 'this' or (kind == 'item' and not bound):
        return True
    if kind == 'literal':
        return any(_own(each, bound) for each in read.start[1])
    if kind == 'where':
        return _own(read.start[1], bound) or any(_own(each, True) for each in reads_of(read.start[2]))
    if kind == 'lookup':
        return _own(read.start[1], bound) or any(_own(each, bound) for each in reads_of(read.start[2]))
    if kind == 'by':
        return _own(read.start[1], bound)
    return False


# A cell that is a plain number, or a name with at most one dot: most cells of a large table, which
# are read without the parser (each as the parser reads it).
_CELL_NUMBER = re.compile(r'-?([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)\Z')
_CELL_PATH = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?\Z')


def _cell_number(text):
    """(number, its node) of a cell that is a plain number, as `literal` gives them, or None."""
    found = _CELL_NUMBER.match(text)
    if found is None:
        return None
    written = found[1]
    number = float(written) if any(char in written for char in '.eE') else int(written)
    return (-number if text.startswith('-') else number), n.Number(number, written=written)


def _cell_path(text):
    """The tree of a cell that is a name or `table.id`, or None."""
    found = _CELL_PATH.match(text)
    if found is None:
        return None
    head = n.Name(found[1], line=1, column=1)
    return head if found[2] is None else n.Member(head, found[2], line=1, column=1)


def _cell_expression(text):
    """The tree of a cell as an expression, or None when the cell is no expression."""
    try:
        return parse_expression(text)
    except SyntaxProblem:
        return None


def _zero(value):
    return (
        isinstance(value, Const)
        and isinstance(value.value, (int, float))
        and value.value == 0
        and value.type == PLAIN
    )


def _converted(value, scale_from, scale_to):
    """A number in one unit written in another: exact for a whole number, a float otherwise."""
    if scale_from == scale_to:
        return value
    if isinstance(value, int):
        found = Fraction(value) * Fraction(scale_from) / Fraction(scale_to)
        return int(found) if found.denominator == 1 else found
    return float(value * scale_from / scale_to)


def declare(tree, units, tables_reader=None):
    """The declared model of a parsed text (`nodes.File`) with a table of units (`Units`, or a table
    as `Units` takes it), reading its tables with `tables_reader` (`tables.in_folder`,
    `tables.in_memory`; a text with none has no table). Raises `LanguageError` with every problem
    that it finds."""
    reader = tables_reader or tables.no_tables
    return Resolver(tree, units if isinstance(units, Units) else Units(units), reader).model()
