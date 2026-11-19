"""The plan of a run: what the engine runs of a program, under one configuration (`Plan.of`).

A plan reads a program (`napkin/program`) and gives each value that a run holds a name of the engine
and an expression over those names: a node of `napkin/core/expr`, whose names are engine names. The
continuous engine and the record read these names; nothing reads the spelling of a path.

- **Names.** A value is named by its key in the record (`record.Key`): `tank.water`,
  `sites.clinic.level`; the actual rate, the request and the capacity of a flow
  `clinic.delivery.actual_rate`, `clinic.delivery.request`, `clinic.delivery.capacity`; a value of
  the root by its own name. The continuous engine knows a flow by `clinic.delivery`. A draw is named
  by the member that executes it and its site. A reduction and a keyed read are named by their
  spelling, after the member that they depend on (`|sum(Place.instances.stock)` for one that reads
  no `this`), and have no key in the record.
- **Paths.** A path is resolved once for each member that reads it, through the pools of the
  program (`pools.py`): a link step goes to the member that the link names, a collection is a list
  of entries (`collections.Entries`) and a step from a collection projects each entry. An entity
  that an expression reads (`this`, `item.destination`) is the text of its member's id: entities
  compare by identity. A `where` test is resolved for each entry; its constant parts are folded
  here, and `T.instances.where(link == this)` takes its entries from the reverse index of the link.
- **Kinds.** An input is fixed for the run: the configuration's value, or its default. A stored value
  starts from its initializer. Each of these, a link (the id of the member that it names), a draw,
  and a request or a capacity that is captured once, is evaluated at the start of the run, in the
  order of what it reads. A formula, a reduction, a keyed read, and a request or a capacity written
  as a formula, is evaluated at each read. A request left out is zero; a capacity left out sets no
  limit and has no value.
- **Draws.** A draw in an initializer is executed once at the start, keyed by its site and by the
  member that executes it. A draw of a path reads the distribution of a distribution-valued value of
  that member: the configuration's, or its default. An input that the configuration sets skips the
  draws of its default (D2).
- **Keyed reads.** `.at(x)` with an x that reads only fixed values is fixed for the run; with x the
  time `t`, it changes only at the keys of its collection, its key times, which go on the timeline
  of the run (`stepped`).
- **Flows** (`Flow`) are of three kinds, and meet the stores by their connections (`Connection`):
  a directed flow is its one connection, with its actual rate; a reversible route
  (`west.water <-> east.water`) has one signed actual rate, positive from its first end to its
  second, within its capacity on the magnitude, and a signed request, and its legs `forward` and
  `backward` are its two connections, whose actual rates and requests are the formulas
  `max(x, 0)` and `max(-x, 0)` of the route's; a flow with legs has one `served_fraction` and its
  legs are its connections, each with its own request, capacity and unit, and the actual rate
  `served_fraction * request`, a formula. `.source` and `.sink` of a directed flow, a leg of a
  route or a leg of a flow with legs name the store at that end (at SOURCE or SINK they hold no
  value: a type error). A route ends at stores only; a store is a tally only by its use, when no
  flow takes from it, and the route takes from both of its ends, so no end of a route is one.
- **Endpoints.** A stored number that supplies a connection has `outflow`, one that receives has
  `inflow` (`End`): a request (zero when left out), a capacity (none when left out), the actual rate
  (the sum of its connections' actual rates, a formula) and `flows`, the collection of its
  connections keyed by their creation numbers (from one: a flow, then each of its legs, as the
  oracle numbers them). A `priority(...)` allocation is kept as its items (`rankings`): a connection
  (a directed flow or a leg), or a projection of a keyed collection of flows, whose keys the run
  reads at its start; a route or a flow with legs named whole is an error of the setup.
- **Connected sets.** A flow joins the ends of its connections, and a request or a capacity, of a
  connection or of an endpoint at its ends, that reads a store, through formulas, reductions or
  directly, joins that store to the flow's set: what a rate reads that moves is in its own set.
  Each set has its way (`Connected.way`): a set of one directed flow with no endpoint settings whose
  rates read nothing that moves runs on arrays with every other such set (`family.py`); any other
  set whose rates read nothing that moves runs on lines (`lines.py`), at any size; a set whose rates
  move runs as one component of the continuous engine (`component.py`) when its flows are directed,
  each store meets at most one flow on each side, it has no endpoint settings and at most `LIMIT`
  stores, and on the sparse integrator otherwise (`sparse.py`). A stored value that no flow touches
  does not move in this slice, since no stage writes it. A directed flow with no store at either end
  moves nothing, and its actual rate is the formula `min(request, capacity)`.
- **Assertions** over inputs are checked once, at the start of the run.

What a later slice runs is refused by name (`Outside`), with the slice that brings it: events,
triggers, the starts of the setup and assertions over state (S4); a key of `.at(...)` that moves or
is a function of the time other than `t`, and a keyed read of a value that moves (S4); a request or
a capacity that reads an actual rate or a served fraction, which needs the rates of other flows
settled first (S4); solvers (S5). Enums and texts are refused too: a value of this slice is a
number or a yes/no.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, replace

from ...core import expr as nodes
from ...expressions import UnitSystem, evaluate
from ...program import parts as p
from ...program.config import ConfigurationError, Quantity
from ...program.record import Key
from ...program.refs import (
    By,
    Choice,
    Delayed,
    Distribution,
    Draw,
    Elapsed,
    EnumValue,
    Expr,
    Formula,
    Instances,
    Item,
    Literal,
    Local,
    Lookup,
    Named,
    Path,
    Reduce,
    Root,
    Since,
    This,
    Time,
    Where,
    spelled,
)
from .collections import Dynamic, Entries, Keyed, Reduction
from .pools import pools_of

# The kinds of the values of a plan.
INPUT = 'input'  # fixed for the run
STATE = 'state'  # stored: from its initializer; a store of a connected set moves
CAPTURE = 'capture'  # a request or a capacity captured once, at the start
FORMULA = 'formula'  # evaluated at each read
RATE = 'rate'  # the actual rate of a flow, which the continuous engine gives
LINK = 'link'  # fixed: the id of the member that a link names, a text
REDUCE = 'reduce'  # a reduction of a collection (`Plan.reductions`), evaluated at each read
LOOKUP = 'lookup'  # a keyed read `.at(x)` (`Plan.keyed`)
DYNAMIC = 'dynamic'  # a read of a collection whose members change in a run (`Plan.dynamic`)
STARTS = (INPUT, STATE, CAPTURE, LINK)  # the kinds that the start of a run evaluates once
FIXED = (INPUT, LINK)  # what an assertion over inputs may read
BUILTINS = ('started', 'done', 'active')  # the fields of every occurrence
SIDES = ('outflow', 'inflow')  # the endpoints of a stored number
# The ways of a connected set (`Connected.way`).
FAMILY, LINES, COMPONENT, SPARSE = 'family', 'lines', 'component', 'sparse'
# The kinds of a flow (`Flow.kind`), and the roles of a connection (`Connection.role`).
DIRECTED, ROUTE, LEGS = 'directed', 'route', 'legs'
DIRECT, FORWARD, BACKWARD, LEG = 'direct', 'forward', 'backward', 'leg'
LIMIT = 150  # the most stores of a component of the continuous engine (R-A4a-04)


class Outside(Exception):
    """A part of a program that this engine does not run yet. The message names the part and the
    slice of the rewrite that brings it."""


def name_of(key):
    """The engine name of a record key: its owner and its steps, joined by dots (the root has no
    owner)."""
    return '.'.join((key.owner, *key.steps) if key.owner else key.steps)


@dataclass(frozen=True)
class Value:
    """A value that a run holds. `node` is its expression over engine names: evaluated once at the
    start for an input, a stored value or a captured request or capacity, and at each read for a
    formula; a rate, a reduction and a keyed read have none. `unit` is the spelling of its declared
    unit (`''` for a plain number or a yes/no). `shape` and `binding` are the expression as its
    template writes it and the engine name of each of its names, so that the members of a family
    are evaluated together over arrays (`family.py`); a value whose expression reads an entity has
    no shape."""

    name: str
    key: Key | None
    kind: str
    node: nodes.Node | None
    unit: str = ''
    boolean: bool = False
    lower: nodes.Node | None = None  # an input's admitted range, or a stored value's bounds
    upper: nodes.Node | None = None
    scale: nodes.Node | None = None  # a stored value's numerical scale (D8)
    given: bool = False  # an input that the configuration sets
    shape: nodes.Node | None = None
    binding: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Drawn:
    """A draw that the start of a run executes: its distribution, its site and the member that
    executes it (`''` for the root)."""

    name: str
    distribution: Distribution
    site: str
    member: str


@dataclass(frozen=True)
class Connection:
    """What meets the stores of a flow (`network.py`): a directed flow itself, a leg of a route
    (`forward` from its first end to its second, `backward` the other way) or a leg of a flow with
    legs. Its engine name, the engine names of its ends (None for SOURCE or SINK), of its request and
    of its capacity (None when it has none; a leg of a route reads the route's signed request and its
    capacity on the magnitude), its unit and its role."""

    name: str
    source: str | None
    sink: str | None
    request: str
    capacity: str | None
    unit: str
    role: str = DIRECT


@dataclass(frozen=True)
class Flow:
    """A flow: its engine id, its kind (`DIRECTED`, `ROUTE` or `LEGS`) and its connections. A
    directed flow and a route have the engine names of their ends (a route's first and second, None
    for SOURCE or SINK), of their request (a route's is signed) and of their capacity (None when it
    has none), and their unit; a flow with legs has its legs, each a connection."""

    name: str
    source: str | None
    sink: str | None
    request: str | None
    capacity: str | None
    unit: str
    kind: str = DIRECTED
    legs: tuple[Connection, ...] = ()

    @property
    def connections(self):
        """Its connections, in their order of creation: one for a directed flow, `forward` and
        `backward` for a route, and the legs of a flow with legs."""
        if self.kind == DIRECTED:
            return (Connection(self.name, self.source, self.sink, self.request, self.capacity, self.unit),)
        if self.kind == ROUTE:
            ends = ((FORWARD, self.source, self.sink), (BACKWARD, self.sink, self.source))
            return tuple(
                Connection(f'{self.name}.{role}', a, b, self.request, self.capacity, self.unit, role)
                for role, a, b in ends
            )
        return self.legs

    @property
    def rate(self):
        """The rate that a directed flow asks of the continuous engine: its request, within its
        capacity."""
        request = nodes.ref(self.request)
        if self.capacity is None:
            return request
        return nodes.call('min', [request, nodes.ref(self.capacity)])


@dataclass(frozen=True)
class End:
    """An endpoint of a stored number, `store.outflow` or `store.inflow`: the engine names of its
    request, its capacity (None when it has none) and its actual rate, and its flows in their order
    of creation."""

    store: str
    side: str
    request: str
    capacity: str | None
    actual_rate: str
    flows: tuple[str, ...]


@dataclass(frozen=True)
class Connected:
    """A connected set of stores and flows, the formulas and reductions that its rates read, each
    after those that it reads, the keyed reads by the time that they read, and its way: `FAMILY`,
    `LINES`, `COMPONENT` or `SPARSE` (see the module). `rates` are the actual rates and served
    fractions of other sets that its settings read, so it settles after them; `reads` is every
    engine name that its settings read, through formulas, reductions and dynamic reads, so that a
    moment knows which writes touch it."""

    stores: tuple[str, ...]
    flows: tuple[str, ...]
    formulas: tuple[str, ...]
    stepped: tuple[str, ...] = ()
    way: str = COMPONENT
    rates: frozenset = frozenset()
    reads: frozenset = frozenset()


@dataclass(frozen=True)
class Expanded:
    """What a value or a node reads through formulas and reductions: the values that it reads that
    are none of these (`leaves`), the formulas and reductions on the way (`formulas`), the keyed
    reads by the time (`stepped`), and whether it reads the time otherwise (`time`)."""

    leaves: frozenset = frozenset()
    formulas: frozenset = frozenset()
    stepped: frozenset = frozenset()
    time: bool = False

    @staticmethod
    def union(parts):
        """What all of several expansions read (one pass: no set is copied for each part)."""
        leaves, formulas, stepped, time = set(), set(), set(), False
        for part in parts:
            leaves |= part.leaves
            formulas |= part.formulas
            stepped |= part.stepped
            time = time or part.time
        return Expanded(frozenset(leaves), frozenset(formulas), frozenset(stepped), time)


def _renamed(node, names):
    """A node with each of its names replaced by the node that `names` gives it."""
    if isinstance(node, nodes.Ref):
        return names[node.name]
    if isinstance(node, nodes.Const):
        return node
    if isinstance(node, nodes.Unary):
        return nodes.unary(node.op, _renamed(node.operand, names))
    if isinstance(node, nodes.Binary):
        return nodes.binary(node.op, _renamed(node.left, names), _renamed(node.right, names))
    if isinstance(node, nodes.Compare):
        return nodes.compare(node.ops, [_renamed(part, names) for part in node.operands])
    if isinstance(node, nodes.BoolOp):
        return nodes.boolean(node.op, [_renamed(part, names) for part in node.values])
    if isinstance(node, nodes.IfElse):
        return nodes.if_else(*(_renamed(part, names) for part in (node.test, node.body, node.orelse)))
    if isinstance(node, nodes.Call):
        return nodes.call(node.function, [_renamed(part, names) for part in node.args])
    raise Outside(f'an expression node of kind {type(node).__name__}')


@functools.cache
def _uses(item, start):
    """Whether a read, a path or a start reads the start of kind `start` (This or Item)."""
    if isinstance(item, Path):
        return _uses(item.start, start)
    if isinstance(item, (This, Item, Local)):
        return isinstance(item, start)
    if isinstance(item, Literal):
        return any(_uses(path, start) for path in item.items)
    if isinstance(item, Where):
        return _uses(item.source, start) or any(_uses(read, start) for _, read in item.test.reads)
    if isinstance(item, By):
        return _uses(item.source, start)
    if isinstance(item, Lookup):
        return _uses(item.source, start) or any(_uses(read, start) for _, read in item.key.reads)
    if isinstance(item, Reduce):
        return _uses(item.source, start)
    if isinstance(item, Since):
        return _uses(item.event, start)
    return False


@dataclass(frozen=True)
class Frame:
    """The bare names of an occurrence or of a trigger: its id (`tank.receive#0`,
    `grinder.refill.when[0]`) and the point that each name stands for (`('value', engine name)`,
    `('flow', engine name)` or `('member', id)` of an entity parameter)."""

    owner: str
    names: dict


@dataclass(frozen=True)
class Trigger:
    """A trigger of one receiver: its key (`grinder.refill.when[0]`), its origin, its receiver and
    the event that it starts; its condition, its captures (engine name and node, in written order)
    and its reset (`('when', node)` or `('after', node)`, or None) as nodes over engine names; its
    body, which a firing executes in `scope` (the captures are its frame)."""

    key: str
    origin: str
    member: str
    event: str
    test: nodes.Node
    captures: tuple
    reset: tuple | None
    body: tuple
    scope: tuple


@dataclass(frozen=True)
class Occurrence:
    """An occurrence of an event as a plan holds it: its id, its receiver, its event and its scope;
    the engine names of its values in the order in which its entry gives them a value (D14: its
    parameters, its built-in fields, then its locals and the plain settings of its flows in written
    order); its stored numbers, its flows and its formulas, which freeze at its finish."""

    id: str
    member: str
    event: p.Event
    scope: tuple
    initial: tuple
    stores: tuple
    flows: tuple
    formulas: tuple


class Plan:
    """See the module. `values` are in the order of the program: the root's, then each template's
    members in their order; `draws`, `flows` and `sets` likewise."""

    def __init__(self, program, configuration):
        self.program, self.configuration = program, configuration
        self.horizon = float(configuration.request.horizon)
        self.numerics = configuration.numerics
        self.units = UnitSystem(
            {
                unit.name: {'dimensions': dict(unit.dimension), 'scale': float(unit.scale)}
                for unit in program.units
            }
        )
        self.pools = pools_of(program)
        self.values, self.draws, self.flows, self.distributions = {}, {}, {}, {}
        self.reductions, self.keyed = {}, {}
        self.ends, self.rankings = {}, {}  # (store, side) -> End; -> the items of a priority(...)
        self.connections = {}  # the engine name of each connection -> its `Connection`
        # The engine name of each flow and of each connection -> (what it is, its Flow or
        # Connection): `directed`, `route` and `legs` name a flow, `forward`, `backward` and `leg` a
        # connection of a route or of a flow with legs.
        self._parts = {}
        self._numbers = {}  # the creation number of each flow and connection, from 1 (its key)
        self.asserts = []  # (origin, the member that it belongs to, its node)
        self.failures = []  # the errors of the setup that the plan finds: the run fails with them
        self._derived = {}  # (owner, read) -> the engine name of a reduction or a keyed read
        self._expanded = {}
        self._places = {}  # the place of each value in `values`, for `ordered`
        self._given = {(item.member, item.name): item for item in configuration.inputs}
        self._refuse_parts()
        self.dynamic = {}  # engine name -> `Dynamic`: a read of a collection that changes in a run
        self.events = {}  # (member id, event name) -> (template, row, member, Event)
        self.occurrences = {}  # (member id, event name) -> the ids of its occurrences, in order
        self.frames = {}  # occurrence id -> its scope (template, row, member, Frame)
        self.end_flows = {}  # (store, side) -> the connections present at a dynamic endpoint
        # With flows of events, every endpoint's collection of flows changes in a run.
        self.dynamic_ends = any(
            isinstance(part, p.Flow)
            for template in program.templates
            for event in template.events
            for part in event.locals
        )
        # The values of each scope, then the flows, whose ends are values, then the expressions of
        # each: an expression may read a part that comes later.
        self._declared = []
        members = [
            (template, row, member)
            for template in program.templates
            for row, member in enumerate(template.members)
        ]
        for template, row, member in members:
            for event in template.events:
                self.events[(member.id, event.name)] = (template, row, member, event)
                self.occurrences[(member.id, event.name)] = []
        for value in program.root:
            self._declare(value, None)
        for scope in members:
            for value in scope[0].values:
                self._declare(value, scope)
        for scope in members:
            for flow in scope[0].flows:
                self._declare_flow(flow, scope)
        self._declare_ends(members)
        unused = sorted(f'{member}.{name}'.lstrip('.') for member, name in self._given)
        if unused:
            raise ConfigurationError(f'no input of the program has these names: {", ".join(unused)}')
        for make in self._declared:
            make()
        for check in program.asserts:
            self.asserts.append((check.origin, '', self.node(check.test, None, check.origin)))
        for scope in members:
            for check in scope[0].asserts:
                self.asserts.append((check.origin, scope[2].id, self.node(check.test, scope, check.origin)))
        self.triggers = [
            self._trigger(scope, event, index)
            for scope in members
            for event in scope[0].events
            for index in range(len(event.triggers))
        ]
        self._connect()
        self._refuse_reads()

    @classmethod
    def of(cls, program, configuration):
        """The plan of a run of a program under a configuration."""
        return cls(program, configuration)

    # ---- what this slice refuses ----------------------------------------------------------------

    def _refuse_parts(self):
        """Solvers (S5), status displays (C), and what the second part of S4 brings: a draw in an
        event, an actor's choice, `elapsed` and `delayed`, an assignment of a formula, a
        distribution, a collection or an allocation, and controllers of actors."""
        program = self.program
        for template in program.templates:
            if template.solvers:
                raise Outside(f'{template.solvers[0].origin}: a solver (S5)')
            if template.status is not None:
                raise Outside(f'{template.status.origin or template.name}: a status display (C)')
        if self.configuration.controllers or self.configuration.picks:
            raise Outside('the controllers and picks of actors (S4)')
        for origin, expression, in_event in _program_expressions(program):
            for _, read in expression.reads:
                if isinstance(read, (Choice, Elapsed, Delayed)) or (isinstance(read, Draw) and in_event):
                    raise Outside(f'{origin}: {spelled(read)}, which the second part of S4 runs (S4)')
        for origin, statement in _program_statements(program):
            if isinstance(statement, p.Assign) and not isinstance(statement.value, Expr):
                raise Outside(
                    f'{origin}: an assignment of a {type(statement.value).__name__.lower()} in a stage (S4)'
                )

    def _refuse_reads(self):
        """A keyed read of what moves, and an assertion over state, are refused (S4)."""
        moving = self.moving
        for keyed in self.keyed.values():
            found = Expanded.union(self.expanded(read) for read in keyed.reads())
            if (
                found.time
                or found.stepped
                or any(leaf in moving or self._is_rate(leaf) for leaf in found.leaves)
            ):
                raise Outside(
                    f'{keyed.spelled}: `.at(...)` of a value or with a key that changes between moments (S4)'
                )
        for origin, _, node in self.asserts:
            if not self._fixed(self.expansion(node)):
                raise Outside(f'{origin}: an assertion over state, which is checked at each moment (S4)')

    def _fixed(self, found):
        """Whether what an expansion reads is fixed by the inputs: inputs, links, and keyed reads
        with a fixed key of what is fixed."""
        if found.time or found.stepped:
            return False
        for leaf in found.leaves:
            value = self.values.get(leaf)
            if value is None or value.kind in FIXED:
                continue  # a draw, which only an input's initializer executes
            if value.kind != LOOKUP:
                return False
            inner = Expanded.union(self.expanded(read) for read in self.keyed[leaf].reads())
            if not self._fixed(inner):
                return False
        return True

    def _is_rate(self, name):
        value = self.values.get(name)
        return value is not None and value.kind == RATE

    # ---- the values and the flows ---------------------------------------------------------------

    def _add(self, value):
        if value.name in self.values or value.name in self.flows:
            raise Outside(f'{value.name}: two values that the engine names alike')
        self.values[value.name] = value

    @staticmethod
    def _owner(scope):
        """The owner of the values of a scope: an occurrence's id, a member's id, or the root's."""
        if scope is None:
            return ''
        return scope[3].owner if len(scope) > 3 else scope[2].id

    def _declare(self, value, scope):
        """A value of the root (`scope` None), of one member ((template, row, member)) or of an
        occurrence ((template, row, member, frame))."""
        member = scope[2] if scope is not None else None
        local = scope is not None and len(scope) > 3
        key = Key(self._owner(scope), (value.name,))
        name = name_of(key)
        if value.kind == p.COLLECTION:
            return  # a collection has no value of its own: a path that steps into it reads its init
        if value.kind == p.LINK:
            if member is None:
                raise Outside(f'{value.origin}: a link of the root (a later slice)')
            target = self.program.template(value.type.template)
            linked = target.members[member.link(value.name)].id
            self._add(Value(name, key, LINK, nodes.const(linked)))
            return
        own = member.value(value.name) if member is not None and not local else None
        init = own if own is not None else value.init
        if isinstance(value.type, p.DistributionType):
            self._declare_distribution(value, member, name, init)
            return
        if not isinstance(value.type, (p.Number, p.Bool, p.EnumType, p.Text)):
            raise Outside(f'{value.origin}: a value of type {type(value.type).__name__} (a later slice)')
        unit = value.type.unit if isinstance(value.type, p.Number) else ''
        boolean = isinstance(value.type, p.Bool)
        given = self._given.pop((key.owner, value.name), None)
        if given is not None and value.kind != p.INPUT:
            raise ConfigurationError(f'{name} is no input: a configuration sets only inputs')
        kind = {p.INPUT: INPUT, p.STATE: STATE, p.FORMULA: FORMULA}[value.kind]

        def make():
            shape, binding = None, ()
            if given is not None:
                node = self._given_node(given, name, unit, boolean, value.type)
            else:
                expression = init.expr if kind == FORMULA else init
                node, binding = self._bound(expression, scope, value.origin)
                shape = expression.node if binding is not None else None
            bounds = [
                self.node(bound, scope, value.origin) if bound is not None else None
                for bound in (value.lower, value.upper)
            ]
            scale = self.node(value.scale, scope, value.origin) if value.scale is not None else None
            self.values[name] = Value(
                name, key, kind, node, unit, boolean, *bounds, scale, given is not None, shape, binding or ()
            )

        self._add(Value(name, key, kind, None, unit, boolean))
        self._declared.append(make)

    def _declare_distribution(self, value, member, name, init):
        """A distribution-valued value: the configuration's distribution, or its default."""
        owner = member.id if member is not None else ''
        given = self._given.pop((owner, value.name), None)
        if given is not None:
            if value.kind != p.INPUT:
                raise ConfigurationError(f'{name} is no input: a configuration sets only inputs')
            if not isinstance(given.value, Distribution):
                raise ConfigurationError(f'{name} is distribution-valued: it takes a distribution')
            init = given.value
        if not isinstance(init, Distribution):
            raise Outside(f'{value.origin}: a distribution-valued value that is no distribution (S4)')
        self.distributions[name] = init

    def _given_node(self, given, name, unit, boolean, value_type=None):
        """The node of the value that a configuration gives an input, in canonical units (D2). Its
        unit is a spelling of the program's table, or a unit of the library given whole. An enum
        input takes a member of its enum, and a text input a text."""
        found = given.value
        if isinstance(value_type, p.EnumType):
            members = self.program.enum(value_type.enum).members
            if not isinstance(found, EnumValue) or found.member not in members:
                raise ConfigurationError(f'{name} takes a member of {value_type.enum}, not {found!r}')
            return nodes.const(found.member)
        if isinstance(value_type, p.Text):
            if not isinstance(found, str):
                raise ConfigurationError(f'{name} is a text: it takes a text, not {found!r}')
            return nodes.const(found)
        if boolean:
            if not isinstance(found, bool):
                raise ConfigurationError(f'{name} is a yes/no: it takes true or false, not {found!r}')
            return nodes.const(found)
        if not isinstance(found, Quantity) or isinstance(found.number, bool):
            raise ConfigurationError(f'{name} is a number in {unit or "no unit"}: it takes a quantity')
        try:
            declared = self.program.unit(unit)
            written = found.unit if isinstance(found.unit, p.Unit) else self.program.unit(found.unit)
        except KeyError:
            raise ConfigurationError(
                f'{name}: the unit {found.unit!r} is not in the program; '
                'give a unit of the library with its dimension and scale'
            ) from None
        if not declared.compatible(written):
            raise ConfigurationError(
                f'{name} is in {unit or "no unit"}: {written.name or "no unit"} does not convert'
            )
        return nodes.const(float(found.number) * float(written.scale))

    def _declare_flow(self, flow, scope):
        """A flow of one member: its ends, its requests and capacities, and what the run gives of it:
        the actual rate of a directed flow and the signed actual rate of a route, which the network
        gives, and the served fraction of a flow with legs. The rates of the legs are formulas of
        these: `max(rate, 0)` forward and `max(-rate, 0)` backward on a route (and so are their
        requests, of the route's signed request), and the fraction times the leg's request on a flow
        with legs."""
        owner = self._owner(scope)
        name = name_of(Key(owner, (flow.name,)))
        self._numbers[name] = len(self._numbers) + 1
        if flow.kind == p.LEGS:
            fraction = name_of(Key(owner, (flow.name, 'served_fraction')))
            self._add(Value(fraction, Key(owner, (flow.name, 'served_fraction')), RATE, None, ''))
            legs = []
            for leg in flow.legs:
                steps, origin = (flow.name, leg.name), leg.origin or flow.origin
                ends = [self._end(end, scope, origin) for end in (leg.source, leg.sink)]
                request, capacity = self._settings(leg, steps, scope, origin)
                made = Connection(name_of(Key(owner, steps)), *ends, request, capacity, leg.unit, LEG)
                rate = Key(owner, (*steps, 'actual_rate'))
                node = nodes.binary('mul', nodes.ref(fraction), nodes.ref(request))
                self._add(Value(name_of(rate), rate, FORMULA, node, leg.unit))
                self._parts[made.name] = (LEG, made)
                self._numbers[made.name] = len(self._numbers) + 1
                legs.append(made)
            made = Flow(name, None, None, None, None, '', LEGS, tuple(legs))
            self._parts[name] = (LEGS, made)
            self.flows[name] = made
            return
        ends = [self._end(end, scope, flow.origin) for end in (flow.source, flow.sink)]
        request, capacity = self._settings(flow, (flow.name,), scope, flow.origin)
        rate = Key(owner, (flow.name, 'actual_rate'))
        if flow.kind == p.REVERSIBLE:
            if None in ends:
                raise Outside(f'{flow.origin}: a reversible route that ends at SOURCE or SINK (a type error)')
            made = Flow(name, *ends, request, capacity, flow.unit, ROUTE)
            self._add(Value(name_of(rate), rate, RATE, None, flow.unit))
            for leg in made.connections:
                for which, signed in (('actual_rate', name_of(rate)), ('request', request)):
                    part = nodes.ref(signed) if leg.role == FORWARD else nodes.unary('neg', nodes.ref(signed))
                    key = Key(owner, (flow.name, leg.role, which))
                    node = nodes.call('max', [part, nodes.const(0.0)])
                    self._add(Value(name_of(key), key, FORMULA, node, flow.unit))
                self._parts[leg.name] = (leg.role, leg)
                self._numbers[leg.name] = len(self._numbers) + 1
            self._parts[name] = (ROUTE, made)
            self.flows[name] = made
            return
        made = Flow(name, *ends, request, capacity, flow.unit)
        self._parts[name] = (DIRECTED, made)
        if made.source is None and made.sink is None:
            # Nothing to move: the actual rate is what the flow asks.
            self._add(Value(name_of(rate), rate, FORMULA, made.rate, flow.unit))
        else:
            self._add(Value(name_of(rate), rate, RATE, None, flow.unit))
            self.flows[name] = made

    def _settings(self, flow, steps, scope, origin):
        """The engine names of the request (zero when left out) and of the capacity (None when left
        out) of a flow or a leg, declared as values under the key steps `steps`."""
        owner = self._owner(scope)
        names = {}
        for which in ('request', 'capacity'):
            setting = getattr(flow, which)
            if setting is None and which == 'capacity':
                continue
            key = Key(owner, (*steps, which))
            names[which] = name_of(key)
            kind = FORMULA if isinstance(setting, Formula) else CAPTURE
            self._add(Value(name_of(key), key, kind, None, flow.unit))

            def make(setting=setting, key=key, kind=kind):
                shape, binding = None, ()
                if setting is None:
                    node = nodes.const(0)  # a request left out is zero
                else:
                    expression = setting.expr if isinstance(setting, Formula) else setting
                    node, binding = self._bound(expression, scope, origin)
                    shape = expression.node if binding is not None else None
                self.values[name_of(key)] = Value(
                    name_of(key), key, kind, node, flow.unit, shape=shape, binding=binding or ()
                )

            self._declared.append(make)
        return names['request'], names.get('capacity')

    def _end(self, end, scope, origin):
        """The engine name of a stored number at an end of a flow, or None for SOURCE and SINK."""
        if isinstance(end, p.Outside):
            return None
        point = self._resolve(end, scope, origin)
        found = self.values.get(point[1]) if point[0] == 'value' else None
        if found is None or found.kind != STATE or found.boolean:
            raise Outside(f'{origin}: an end of a flow that is no stored number of this slice')
        return point[1]

    def _declare_ends(self, members):
        """The endpoints that the program sets; an endpoint that it only reads is declared when a path
        reads it (`end_of`)."""
        self._incident, self._stores = {}, {}
        for flow in self.flows.values():
            for connection in flow.connections:
                self.connections[connection.name] = connection
                for side, end in zip(SIDES, (connection.source, connection.sink)):
                    if end is not None:
                        self._incident.setdefault((end, side), []).append(connection.name)
        if self.dynamic_ends:
            self.end_flows = {pair: list(flows) for pair, flows in self._incident.items()}
        scopes = [(value, None) for value in self.program.root]
        scopes += [(value, scope) for scope in members for value in scope[0].values]
        for value, scope in scopes:
            store = name_of(Key(scope[2].id if scope is not None else '', (value.name,)))
            self._stores[store] = (value, scope)
            for side in SIDES:
                if getattr(value, side) is not None:
                    self.end_of(store, side, value.origin)

    def end_of(self, store, side, origin):
        """The endpoint `side` of a stored number, declared on its first use."""
        if (store, side) in self.ends:
            return self.ends[(store, side)]
        value, scope = self._stores[store]
        flows = tuple(self._incident.get((store, side), ()))
        setting = getattr(value, side)
        if setting is None and not flows and not self.dynamic_ends:
            raise Outside(f'{origin}: {store}.{side}, which no flow meets (a type error)')
        found = self.values.get(store)
        if found is None or found.kind != STATE or found.boolean:
            raise Outside(f'{value.origin}: {side} of a value that is no stored number (a type error)')
        self._declare_end(store, value, scope, side, setting or p.Endpoint(), flows)
        return self.ends[(store, side)]

    def _declare_end(self, store, value, scope, side, setting, flows):
        owner = self._owner(scope)
        # With no flow yet, the unit of the store per hour.
        unit = self.connections[flows[0]].unit if flows else f'{getattr(value.type, "unit", "") or "1"}/h'
        origin = setting.origin or value.origin
        names = {}
        for which in ('request', 'capacity'):
            expression = getattr(setting, which)
            if expression is None and which == 'capacity':
                continue
            key = Key(owner, (value.name, side, which))
            kind = FORMULA if isinstance(expression, Formula) else CAPTURE
            names[which] = name_of(key)
            self._add(Value(name_of(key), key, kind, None, unit))

            def make(expression=expression, key=key, kind=kind):
                shape, binding = None, ()
                if expression is None:
                    node = nodes.const(0)  # a request left out is zero
                else:
                    written = expression.expr if isinstance(expression, Formula) else expression
                    node, binding = self._bound(written, scope, origin)
                    shape = written.node if binding is not None else None
                self.values[name_of(key)] = Value(
                    name_of(key), key, kind, node, unit, shape=shape, binding=binding or ()
                )

            self._declared.append(make)
        rate = Key(owner, (value.name, side, 'actual_rate'))
        if self.dynamic_ends:
            # The flows present at the endpoint change in a run: its actual rate is their sum then.
            spelling = f'{store}.{side}.actual_rate'
            self.dynamic[name_of(rate)] = Dynamic(
                name_of(rate), 'sum', ('flows', store, side), ('actual_rate',), spelling
            )
            self._add(Value(name_of(rate), rate, DYNAMIC, None, unit))
        else:
            total = None
            for flow in flows:
                part = nodes.ref(f'{flow}.actual_rate')
                total = part if total is None else nodes.binary('add', total, part)
            total = total if total is not None else nodes.const(0.0)
            self._add(Value(name_of(rate), rate, FORMULA, total, unit))
        self.ends[(store, side)] = End(
            store, side, names['request'], names.get('capacity'), name_of(rate), flows
        )
        if isinstance(setting.allocation, p.Priority):
            self._declared.append(lambda: self._ranking(store, side, setting.allocation, scope, origin))

    def _ranking(self, store, side, allocation, scope, origin):
        """The items of a `priority(...)`, which name connections: ('one', connection) or ('keyed',
        ((key, connection), ...)), where a key is the engine name of a value or a creation number."""
        items = []
        for path in allocation.items:
            point = self._resolve(path, scope, origin)
            if point[0] == 'flow':
                items.append(('one', point[1]))
            elif point[0] == 'many' and all(each[0] == 'flow' for each in point[1].points):
                entries = point[1]
                items.append(('keyed', tuple(zip(entries.keys, (each[1] for each in entries.points)))))
            else:
                raise Outside(f'{origin}: priority({spelled(path)}), which names no flow (a type error)')
        mine = set(self.ends[(store, side)].flows)
        for item in items:
            named = [item[1]] if item[0] == 'one' else [flow for _, flow in item[1]]
            for flow in named:
                if flow not in mine:
                    whole = self._parts[flow][0] in (ROUTE, LEGS)
                    self.failures.append(
                        f'{origin}: priority(...) at {store}.{side} names {flow}, which is not a flow of '
                        f'that endpoint{"; name its leg of that direction" if whole else ""}'
                    )
        self.rankings[(store, side)] = tuple(items)

    # ---- events -------------------------------------------------------------------------------

    def _trigger(self, scope, event, index):
        """A trigger of an event of one receiver (`Trigger`). Its captures are named under the
        trigger's key; each firing sets them."""
        template, row, member = scope
        trigger = event.triggers[index]
        key = f'{member.id}.{event.name}.when[{index}]'
        frame = Frame(key, {})
        inner = (template, row, member, frame)
        captures = []
        for capture in trigger.captures:
            # A capture is held by the run, which sets it at each firing: it is no value of the plan.
            name = f'{key}.{capture.name}'
            frame.names[capture.name] = ('value', name)
            captures.append((name, self.node(capture.init, inner, capture.origin or trigger.origin)))
        reset = None
        if trigger.reset is not None:
            reset = (trigger.reset.kind, self.node(trigger.reset.expr, inner, trigger.origin))
        test = self.node(trigger.test, inner, trigger.origin)
        return Trigger(
            key, trigger.origin, member.id, event.name, test, tuple(captures), reset, trigger.body, inner
        )

    def occurrence(self, member, event_name, index, args, started):
        """The values and flows of a new occurrence of an event on a member (`Occurrence`), the
        `index`-th start of that event on it: its parameters take the arguments (an entity's id for
        an entity parameter), `started` the time of its start, `done` false and `active` true."""
        template, row, receiver, event = self.events[(member, event_name)]
        occ = f'{member}.{event_name}#{index}'
        frame = Frame(occ, {})
        scope = (template, row, receiver, frame)
        initial = []
        for param, arg in zip(event.params, args):
            key = Key(occ, (param.name,))
            if isinstance(param.type, p.EntityType):
                self._add(Value(name_of(key), key, LINK, nodes.const(arg)))
                frame.names[param.name] = ('member', arg)
            else:
                bounds = [
                    self.node(bound, scope, param.origin) if bound is not None else None
                    for bound in (param.lower, param.upper)
                ]
                self._add(Value(name_of(key), key, STATE, nodes.const(arg), *_type_of(param.type), *bounds))
                frame.names[param.name] = ('value', name_of(key))
            initial.append(name_of(key))
        for field, kind, value in (
            ('started', INPUT, started),
            ('done', STATE, False),
            ('active', STATE, True),
        ):
            key = Key(occ, (field,))
            self._add(Value(name_of(key), key, kind, nodes.const(value), '', field != 'started'))
            initial.append(name_of(key))
        for part in event.locals:
            kind = 'flow' if isinstance(part, p.Flow) else 'value'
            frame.names[part.name] = (kind, name_of(Key(occ, (part.name,))))
        first = len(self._declared)
        for part in event.locals:
            if isinstance(part, p.Value):
                self._declare(part, scope)
        flows = []
        for part in event.locals:
            if isinstance(part, p.Flow):
                self._declare_flow(part, scope)
                flows.append(name_of(Key(occ, (part.name,))))
        makers, self._declared = self._declared[first:], self._declared[:first]
        for make in makers:
            make()
        stores, formulas = [], []
        for part in event.locals:
            name = name_of(Key(occ, (part.name,)))
            if isinstance(part, p.Value):
                initial.append(name)
                value = self.values.get(name)
                if value is None:
                    continue  # a distribution or a collection
                if value.kind == STATE and isinstance(part.type, p.Number):
                    stores.append(name)
                    self._stores[name] = (part, scope)
                elif value.kind == FORMULA:
                    formulas.append(name)
                continue
            for setting in self._flow_settings(name):
                (formulas if self.values[setting].kind == FORMULA else initial).append(setting)
        for name in flows:
            if name in self.flows:
                for connection in self.flows[name].connections:
                    self.connections[connection.name] = connection
        self.frames[occ] = scope
        self.occurrences[(member, event_name)].append(occ)
        flows = tuple(name for name in flows if name in self.flows)
        return Occurrence(occ, member, event, scope, tuple(initial), tuple(stores), flows, tuple(formulas))

    def _flow_settings(self, name):
        """The engine names of the requests and capacities of a flow (or of its legs), in order."""
        found = []
        for which in ('request', 'capacity'):
            for each in (f'{name}.{which}', *(f'{leg}.{which}' for leg in self._legs_of(name))):
                if each in self.values and each not in found:
                    found.append(each)
        return found

    def _legs_of(self, name):
        flow = self.flows.get(name)
        if flow is None or flow.kind != LEGS:
            return ()
        return tuple(leg.name for leg in flow.legs)

    # ---- expressions ----------------------------------------------------------------------------

    def node(self, expression, scope, origin, item=None):
        """The node of an expression of a scope, with engine names; `item` is the member that the
        test of a `where` is about."""
        return self._bound(expression, scope, origin, item)[0]

    def _bound(self, expression, scope, origin, item=None):
        """The node of an expression with engine names, and the engine name of each of its names
        (None when it reads an entity, whose name becomes a text)."""
        if not isinstance(expression, Expr):
            raise Outside(f'{origin}: an initializer of kind {type(expression).__name__} (a later slice)')
        names, binding = {}, {}
        for name, read in expression.reads:
            if isinstance(read, Time):
                names[name], binding[name] = nodes.ref('t'), 't'
            elif isinstance(read, Path):
                point = self._resolve(read, scope, origin, item)
                if point[0] == 'value':
                    names[name], binding[name] = nodes.ref(point[1]), point[1]
                elif point[0] in ('member', 'occurrence'):
                    names[name], binding = nodes.const(point[1]), None
                else:
                    raise Outside(f'{origin}: {spelled(read)} where a value is expected (a later slice)')
            elif isinstance(read, Reduce):
                found = self._reduction(read, scope, origin, item)
                names[name] = nodes.ref(found)
                if binding is not None:
                    binding[name] = found
            elif isinstance(read, Draw):
                found = self._draw(read, scope, origin)
                names[name] = nodes.ref(found)
                if binding is not None:
                    binding[name] = found
            elif isinstance(read, EnumValue):
                names[name] = nodes.const(read.member)
            elif isinstance(read, Since):
                point = self._resolve(read.event, scope, origin, item)
                if point[0] != 'event':
                    raise Outside(f'{origin}: {spelled(read)} of what is no event (a type error)')
                found = self._dynamic(read, 'since', ('occurrences', point[1], point[2]), (), scope, item)
                names[name], binding = nodes.ref(found), None
            else:
                raise Outside(f'{origin}: the read {spelled(read)} (S4)')
        node = _renamed(expression.node, names)
        return node, (None if binding is None else tuple(sorted(binding.items())))

    # ---- paths ------------------------------------------------------------------------------------

    def _resolve(self, path, scope, origin, item=None):
        """What a path names, for a member's (`scope` = (template, row, member)) or the root's
        expression: `('value', engine name)`, `('member', id)`, `('flow', engine name)` of a flow or
        a connection, or `('many', Entries)`."""
        if isinstance(path.start, Lookup):
            return ('value', self._keyed(path, scope, origin, item))
        point = self._start(path.start, scope, origin, item)
        for step in path.steps:
            point = self._step(point, step, origin)
        return point

    def _start(self, start, scope, origin, item):
        if isinstance(start, This):
            if scope is None:
                raise Outside(f'{origin}: `this` at the root')
            return ('member', scope[2].id)
        if isinstance(start, Root):
            return ('root',)
        if isinstance(start, Named):
            self.program.member(start.id)
            return ('member', start.id)
        if isinstance(start, Item):
            if item is None:
                raise Outside(f'{origin}: a member of a where, read outside its where')
            return ('member', item)
        if isinstance(start, Instances):
            template = self.program.template(start.template)
            ids = [member.id for member in template.members]
            points = tuple(('member', id) for id in ids)
            return ('many', Entries(template.name, points, (None,) * len(ids), tuple(range(len(ids))), True))
        if isinstance(start, Literal):
            return ('many', self._literal(start, scope, origin, item))
        if isinstance(start, Where):
            return (
                'many',
                self._where(self._many(start.source, scope, origin, item), start.test, scope, origin),
            )
        if isinstance(start, By):
            entries = self._many(start.source, scope, origin, item)
            keys = []
            for point in entries.points:
                found = self._step(point, start.key, origin)
                if found[0] != 'value':
                    raise Outside(f'{origin}: `by({start.key})`, which names no value')
                keys.append(found[1])
            return ('many', replace(entries, keys=tuple(keys), whole=False))
        if isinstance(start, Local):
            frame = scope[3] if scope is not None and len(scope) > 3 else None
            if frame is None or start.name not in frame.names:
                raise Outside(f'{origin}: the bare name {start.name}, of a solver (S5)')
            return frame.names[start.name]
        raise Outside(f'{origin}: the start of a path {type(start).__name__} (a later slice)')

    def _step(self, point, name, origin):
        """The point that a step from a point names."""
        kind = point[0]
        if kind == 'root':
            if self.program.root_value(name) is None:
                raise Outside(f'{origin}: no value {name} of the root')
            return ('value', name)
        if kind == 'member':
            template, row = self.program.member(point[1])
            part = template.part(name)
            if isinstance(part, p.Value):
                if part.kind == p.LINK:
                    target = self.program.template(part.type.template)
                    return ('member', target.members[template.members[row].link(name)].id)
                if part.kind == p.COLLECTION:
                    member = template.members[row]
                    return self._resolve(member.value(name) or part.init, (template, row, member), origin)
                return ('value', f'{point[1]}.{name}')
            if isinstance(part, p.Flow):
                return ('flow', f'{point[1]}.{name}')
            if isinstance(part, p.Event):
                return ('event', point[1], name)
            raise Outside(f'{origin}: {point[1]}.{name} names a solver (S5)')
        if kind == 'event':
            if name != 'occurrences':
                raise Outside(f'{origin}: the {name} of the event {point[1]}.{point[2]} (a type error)')
            return ('dynamic', ('occurrences', point[1], point[2]), ())
        if kind == 'dynamic':
            return ('dynamic', point[1], point[2] + (name,))
        if kind == 'occurrence':
            names = self.frames[point[1]][3].names
            if name in names:
                return names[name]
            if name in BUILTINS:
                return ('value', f'{point[1]}.{name}')
            raise Outside(f'{origin}: {point[1]} has no {name} (a type error)')
        if kind == 'flow':
            return self._flow_step(point[1], name, origin)
        if kind == 'many':
            entries = point[1]
            points = tuple(self._step(each, name, origin) for each in entries.points)
            if any(each[0] == 'many' for each in points):
                raise Outside(f'{origin}: a collection of collections (a later slice)')
            return ('many', replace(entries, points=points, whole=False))
        if kind == 'value' and name in SIDES and point[1] in self._stores:
            self.end_of(point[1], name, origin)
            return ('end', point[1], name)
        if kind == 'end':
            end = self.ends[(point[1], point[2])]
            if name == 'flows' and self.dynamic_ends:
                return ('dynamic', ('flows', point[1], point[2]), ())
            if name == 'flows':
                points = tuple(('flow', flow) for flow in end.flows)
                keys = tuple(self._numbers[flow] for flow in end.flows)
                return ('many', Entries(None, points, (None,) * len(points), keys))
            found = {'request': end.request, 'capacity': end.capacity, 'actual_rate': end.actual_rate}
            if name not in found:
                raise Outside(
                    f'{origin}: the {name} of {point[1]}.{point[2]}, which is no value (a type error)'
                )
            if found[name] is None:
                raise Outside(f'{origin}: {point[1]}.{point[2]}.capacity, a capacity left out, has no value')
            return ('value', found[name])
        raise Outside(f'{origin}: the step {name} of a value, which names nothing of it (a type error)')

    def _flow_step(self, name, step, origin):
        """The point that a step from a flow or a connection names: a leg of a route or of a flow with
        legs, a value of it, or the store at one of its ends (`.source`, `.sink`)."""
        what, found = self._parts[name]
        if what == ROUTE and step in (FORWARD, BACKWARD):
            return ('flow', f'{name}.{step}')
        if what == LEGS:
            if step == 'served_fraction':
                return ('value', f'{name}.served_fraction')
            if f'{name}.{step}' in self._parts:
                return ('flow', f'{name}.{step}')
            raise Outside(
                f'{origin}: {name} is a flow with legs, which has no {step}: read a leg (a type error)'
            )
        steps = {
            DIRECTED: ('actual_rate', 'request', 'capacity', 'source', 'sink'),
            LEG: ('actual_rate', 'request', 'capacity', 'source', 'sink'),
            ROUTE: ('actual_rate', 'request', 'capacity'),
            FORWARD: ('actual_rate', 'request', 'source', 'sink'),
            BACKWARD: ('actual_rate', 'request', 'source', 'sink'),
        }[what]
        if step not in steps:
            raise Outside(f'{origin}: the {step} of {name}, which it does not have (a type error)')
        if step in ('source', 'sink'):
            end = found.source if step == 'source' else found.sink
            if end is None:
                outside = 'SOURCE' if step == 'source' else 'SINK'
                raise Outside(f'{origin}: {name}.{step} is {outside}, which holds no value (a type error)')
            return ('value', end)
        if step == 'capacity':
            if found.capacity is None:
                raise Outside(f'{origin}: {name}.capacity, a capacity left out, has no value')
            return ('value', found.capacity)
        return ('value', f'{name}.{step}')

    def _many(self, path, scope, origin, item):
        point = self._resolve(path, scope, origin, item)
        if point[0] != 'many':
            raise Outside(f'{origin}: {spelled(path)} is no collection')
        return point[1]

    def _literal(self, literal, scope, origin, item):
        """`<a, b>`: the members that the paths name, in their order of creation, each once."""
        found, template = {}, None
        for path in literal.items:
            point = self._resolve(path, scope, origin, item)
            if point[0] != 'member':
                raise Outside(f'{origin}: {spelled(path)} in a literal is no member')
            owner, row = self.program.member(point[1])
            template = owner.name
            if point[1] in found:
                self.failures.append(f'{origin}: the literal {spelled(Path(literal))} names {point[1]} twice')
            found[point[1]] = row
        ids = sorted(found, key=found.get)
        return Entries(
            template, tuple(('member', id) for id in ids), (None,) * len(ids), tuple(found[id] for id in ids)
        )

    def _where(self, entries, test, scope, origin):
        """The entries that a where test keeps: its constant parts folded, the rest per entry."""
        reverse = self._reverse(entries, test, scope)
        if reverse is not None:
            return reverse
        points, tests, keys = [], [], []
        for point, before, key in zip(entries.points, entries.tests, entries.keys):
            if point[0] != 'member':
                raise Outside(f'{origin}: a where over values, not members (a later slice)')
            node = self.node(test, scope, origin, item=point[1])
            if not nodes.names(node):
                if not evaluate(node, {}, self.units):
                    continue
                node = None
            if before is not None:
                node = before if node is None else nodes.boolean('and', [before, node])
            points.append(point)
            tests.append(node)
            keys.append(key)
        return Entries(entries.template, tuple(points), tuple(tests), tuple(keys))

    def _reverse(self, entries, test, scope):
        """The entries of `T.instances.where(link == this)` from the reverse index of the link, or
        None for any other test."""
        node = test.node
        if scope is None or not isinstance(node, nodes.Compare) or list(node.ops) != ['eq']:
            return None
        if not all(isinstance(part, nodes.Ref) for part in node.operands):
            return None
        reads = [test.read(part.name) for part in node.operands]
        this = [read for read in reads if read == Path(This())]
        linked = [read for read in reads if isinstance(read, Path) and isinstance(read.start, Item)]
        if len(this) != 1 or len(linked) != 1 or len(linked[0].steps) != 1:
            return None
        if not entries.whole:
            return None
        pool, field = self.pools[entries.template], linked[0].steps[0]
        if field not in pool.links or pool.links[field][0] != scope[0].name:
            return None
        rows = pool.back(field).of(scope[1]).tolist()
        return Entries(
            entries.template,
            tuple(entries.points[row] for row in rows),
            (None,) * len(rows),
            tuple(entries.keys[row] for row in rows),
        )

    def _derived_name(self, read, scope, item):
        """The engine name of a reduction or a keyed read: its spelling, after the member that it
        reads through `this` and the member of a where that it reads through `item`."""
        owner = scope[2].id if scope is not None and _uses(read, This) else ''
        if scope is not None and len(scope) > 3 and _uses(read, Local):
            owner = scope[3].owner
        if item is not None and _uses(read, Item):
            owner = f'{owner}@{item}'
        key = (owner, read)
        if key in self._derived:
            return key, self._derived[key]
        name = f'{owner}|{spelled(read)}'
        while name in self.values:
            name += "'"
        return key, name

    def _reduction(self, read, scope, origin, item):
        """The engine name of a reduction, which the plan holds in `reductions`."""
        key, name = self._derived_name(read, scope, item)
        if key in self._derived:
            return name
        point = self._resolve(read.source, scope, origin, item)
        if point[0] == 'dynamic':
            return self._dynamic(read, read.op, point[1], point[2], scope, item)
        entries = self._many(read.source, scope, origin, item)
        names = entries.names
        if names is None and (
            read.op != 'count' or any(point[0] not in ('member', 'flow') for point in entries.points)
        ):
            raise Outside(f'{origin}: {spelled(read)} of members or flows (a type error)')
        if names is not None and not entries.points and read.op == 'count':
            names = None
        self._derived[key] = name
        self.reductions[name] = Reduction(name, read.op, entries.tests, names, spelled(read))
        unit = self._unit_of(names[0]) if names and read.op in ('sum', 'min', 'max') else ''
        self._add(Value(name, None, REDUCE, None, unit, read.op in ('any', 'all')))
        return name

    def _keyed(self, path, scope, origin, item):
        """The engine name of a keyed read `.at(x)` and the steps after it, which the plan holds in
        `keyed`."""
        key, name = self._derived_name(path, scope, item)
        if key in self._derived:
            return name
        lookup = path.start
        by_time = isinstance(lookup.key.node, nodes.Ref) and isinstance(
            lookup.key.read(lookup.key.node.name), Time
        )
        source = self._resolve(lookup.source, scope, origin, item)
        if source[0] == 'dynamic':
            if source[1][0] != 'occurrences' or source[2] or not by_time:
                raise Outside(f'{origin}: {spelled(path)}: occurrences are read at the time t only')
            return self._dynamic(path, 'at', source[1], path.steps, scope, item)
        entries = self._many(lookup.source, scope, origin, item)
        x = self.node(lookup.key, scope, origin, item)
        if 't' in nodes.names(x) and not by_time:
            raise Outside(f'{origin}: a key of `.at(...)` that is a function of the time other than t (S4)')
        points = entries.points
        for step in path.steps:
            points = tuple(self._step(point, step, origin) for point in points)
        if any(point[0] != 'value' for point in points):
            raise Outside(
                f'{origin}: {spelled(path)}, a member or a flow read through `.at(...)` (a later slice)'
            )
        names = tuple(point[1] for point in points)
        self._derived[key] = name
        self.keyed[name] = Keyed(name, entries.tests, entries.keys, names, x, by_time, spelled(path))
        unit = self._unit_of(names[0]) if names else ''
        boolean = bool(names) and self.values[names[0]].boolean
        self._add(Value(name, None, LOOKUP, None, unit, boolean))
        return name

    def _dynamic(self, read, op, source, steps, scope, item):
        """The engine name of a read of a collection whose members change in a run, which the plan
        holds in `dynamic`."""
        key, name = self._derived_name(read, scope, item)
        if key in self._derived:
            return name
        self._derived[key] = name
        self.dynamic[name] = Dynamic(name, op, source, tuple(steps), spelled(read))
        boolean = op in ('any', 'all') or (op == 'at' and self._projects_boolean(source, steps))
        self._add(Value(name, None, DYNAMIC, None, '', boolean))
        return name

    def _projects_boolean(self, source, steps):
        """Whether the steps from an occurrence of an event name a yes/no."""
        if source[0] != 'occurrences' or len(steps) != 1:
            return False
        if steps[0] in ('done', 'active'):
            return True
        event = self.events[(source[1], source[2])][3]
        part = next((part for part in (*event.params, *event.locals) if part.name == steps[0]), None)
        return isinstance(part, p.Value) and isinstance(part.type, p.Bool)

    def project(self, point, steps, origin=''):
        """The engine name that the steps from a member of a dynamic collection name."""
        for step in steps:
            point = self._step(point, step, origin)
        if point[0] != 'value':
            raise Outside(f'{origin}: a member of a collection read whole, not one of its values')
        return point[1]

    def _unit_of(self, name):
        value = self.values.get(name)
        return value.unit if value is not None else ''

    def _draw(self, read, scope, origin):
        """The engine name of a draw that an initializer executes, with its distribution."""
        member = scope[2].id if scope is not None else ''
        if isinstance(read.source, Distribution):
            distribution = read.source
        else:
            point = self._resolve(read.source, scope, origin)
            if point[0] != 'value' or point[1] not in self.distributions:
                raise Outside(
                    f'{origin}: a draw of {spelled(read.source)}, which is no distribution of this slice'
                )
            distribution = self.distributions[point[1]]
        if distribution.family == 'categorical':
            raise Outside(f'{origin}: a draw of a categorical distribution (S4)')
        name = f'{member}|{read.site}'
        self.draws.setdefault(name, Drawn(name, distribution, read.site, member))
        return name

    # ---- what a value reads --------------------------------------------------------------------------

    def reads(self, name):
        """The names that the value `name` reads, directly (a reduction and a keyed read: what their
        entries read)."""
        if name in self.reductions:
            return self.reductions[name].reads()
        if name in self.keyed:
            return self.keyed[name].reads()
        node = self.values[name].node
        return set() if node is None else set(nodes.names(node)) - {'t'}

    def expanded(self, name):
        """What a value reads through formulas and reductions (`Expanded`): a formula, a reduction
        and a keyed read by the time are followed, any other value is a leaf."""
        found = self._expanded.get(name)
        if found is not None:
            if found is _VISITING:
                raise Outside(f'{name}: a formula that reads itself')
            return found
        value = self.values.get(name)
        if name == 't':
            return Expanded(time=True)
        followed = value is not None and (
            value.kind in (FORMULA, REDUCE) or (value.kind == LOOKUP and self.keyed[name].by_time)
        )
        if not followed:
            return Expanded(leaves=frozenset({name}))
        self._expanded[name] = _VISITING
        if value.kind == FORMULA:
            found = self.expansion(value.node)
        else:
            found = Expanded.union(self.expanded(read) for read in self.reads(name))
        if value.kind == LOOKUP:
            found = Expanded(found.leaves, found.formulas, found.stepped | {name}, found.time)
        else:
            found = Expanded(found.leaves, found.formulas | {name}, found.stepped, found.time)
        self._expanded[name] = found
        return found

    def expansion(self, node):
        """What a node reads through formulas and reductions (`Expanded`)."""
        names = nodes.names(node)
        parts = [self.expanded(name) for name in sorted(set(names) - {'t'})]
        return Expanded.union([Expanded(time='t' in names), *parts])

    def expansion_of(self, names):
        """What several values read through formulas and reductions (`Expanded`)."""
        return Expanded.union(self.expanded(name) for name in names)

    def rigid(self, flow):
        """Whether a flow provably never carries more than its request: its capacity is the same
        expression as its request, or a number at most its request's number."""
        if flow.capacity is None:
            return False
        request, capacity = self.values[flow.request].node, self.values[flow.capacity].node
        if request == capacity:
            return True
        return (
            isinstance(request, nodes.Const)
            and isinstance(capacity, nodes.Const)
            and float(capacity.value) <= float(request.value)
        )

    def formula_reads(self, node):
        """The names other than formulas and reductions that a node reads, through them (the keyed
        reads by the time among them), and the formulas and reductions on the way."""
        found = self.expansion(node)
        return set(found.leaves | found.stepped), set(found.formulas)

    # ---- the connected sets ---------------------------------------------------------------------

    def settings_of(self, flow):
        """The engine names of what a flow's value reads: the request and capacity of each of its
        connections, and the request and capacity of the endpoints at their ends."""
        names = []
        for connection in flow.connections:
            names += [connection.request] + ([connection.capacity] if connection.capacity is not None else [])
            for side, store in zip(SIDES, (connection.source, connection.sink)):
                end = self.ends.get((store, side)) if store is not None else None
                if end is not None:
                    names += [end.request] + ([end.capacity] if end.capacity is not None else [])
        return list(dict.fromkeys(names))

    def settled(self, end):
        """Whether an endpoint has a capacity or a request that is not left out."""
        request = self.values[end.request]
        return end.capacity is not None or not (
            isinstance(request.node, nodes.Const) and request.node.value == 0
        )

    def _connect(self):
        """The connected sets of the flows of the program, and the way of each (see the module)."""
        self.moving = {
            end
            for flow in self.flows.values()
            for connection in flow.connections
            for end in (connection.source, connection.sink)
            if end
        }
        self.sets = tuple(self.connect(list(self.flows), self.moving))

    def members(self, source):
        """The points of the members of a dynamic collection now: every occurrence of an event that
        has started, or the connections present at an endpoint."""
        if source[0] == 'occurrences':
            return [('occurrence', occ) for occ in self.occurrences[(source[1], source[2])]]
        return [('flow', connection) for connection in self.end_flows.get((source[1], source[2]), ())]

    def settings_reads(self, flow):
        """What the settings of a flow read (`Expanded`), with the projections of the members that
        its dynamic reads have now, and the names of those dynamic reads among the leaves."""
        found = self.expansion_of(self.settings_of(flow))
        seen, pending = set(), [leaf for leaf in found.leaves if leaf in self.dynamic]
        parts = [found]
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            dynamic = self.dynamic[name]
            if dynamic.op == 'since' or not dynamic.steps:
                continue
            for point in self.members(dynamic.source):
                inner = self.expanded(self.project(point, dynamic.steps))
                parts.append(inner)
                pending += [leaf for leaf in inner.leaves if leaf in self.dynamic]
        return Expanded.union(parts)

    def connect(self, flows, moving):
        """The connected sets of some flows (`Connected`): a flow joins the stores at its ends and
        the stores of `moving` that its settings read (through formulas, reductions and the members
        of dynamic reads). A setting that reads an actual rate or a served fraction of another set
        makes the set settle after that one; of its own set, it has no answer of local sharing."""
        parent = {}

        def root(item):
            parent.setdefault(item, item)
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def join(a, b):
            parent[root(a)] = root(b)

        reads = {}
        for name in flows:
            flow = self.flows[name]
            root(name)
            for connection in flow.connections:
                for end in (connection.source, connection.sink):
                    if end is not None:
                        join(('store', end), name)
            found = reads[name] = self.settings_reads(flow)
            for leaf in found.leaves:
                if leaf in moving:
                    join(('store', leaf), name)
        sets, stores_of = {}, {}
        for name in flows:
            sets.setdefault(root(name), ([], []))[1].append(name)
            for connection in self.flows[name].connections:
                for end in (connection.source, connection.sink):
                    if end is not None:
                        stores_of.setdefault(root(name), set()).add(end)
            for leaf in reads[name].leaves:
                if leaf in moving:
                    stores_of.setdefault(root(name), set()).add(leaf)
        place = self._place_of()
        for key, (stores, _) in sets.items():
            stores.extend(sorted(stores_of.get(key, ()), key=place))
        meets = {}
        for name in flows:
            for connection in self.flows[name].connections:
                for side, end in zip(SIDES, (connection.source, connection.sink)):
                    if end is not None:
                        meets[end, side] = meets.get((end, side), 0) + 1
        made = []
        for stores, members in sets.values():
            found = Expanded.union(reads[flow] for flow in members)
            own = {f'{flow}.actual_rate' for flow in members} | {
                f'{flow}.served_fraction' for flow in members
            }
            for flow in members:
                own |= {f'{c.name}.actual_rate' for c in self.flows[flow].connections}
            rates = {leaf for leaf in found.leaves if self._is_rate(leaf)}
            rates |= {
                leaf
                for leaf in found.leaves
                if leaf in self.dynamic
                and self.dynamic[leaf].steps[-1:] in (('actual_rate',), ('served_fraction',))
            }
            if rates & own or any(self._rate_of_store(leaf, stores) for leaf in rates):
                raise Outside(
                    f'{members[0]}: a request or a capacity that reads an actual rate of its own connected '
                    'set, which local sharing settles at once (S5: a solver)'
                )
            moves = found.time or bool(found.leaves & moving)
            settled = any(
                self.settled(self.ends[(store, side)])
                for store in stores
                for side in SIDES
                if (store, side) in self.ends
            )
            # A route and a flow with legs are unknowns of the network: lines or the sparse integrator.
            directed = all(self.flows[flow].kind == DIRECTED for flow in members)
            if not moves:
                way = FAMILY if len(members) == 1 and not settled and directed else LINES
            elif (
                directed
                and not settled
                and len(stores) <= LIMIT
                and all(count == 1 for (store, _), count in meets.items() if store in stores)
            ):
                way = COMPONENT
            else:
                way = SPARSE
            made.append(
                Connected(
                    tuple(stores),
                    tuple(members),
                    tuple(self.ordered(found.formulas)),
                    tuple(sorted(found.stepped)),
                    way,
                    frozenset(rates),
                    frozenset(found.leaves | found.formulas | found.stepped),
                )
            )
        return made

    def rates_of_flow(self, flow):
        """The engine names of what the network gives of a flow, which other sets may read: its
        actual rate or its served fraction, and the actual rates of the endpoints at its ends."""
        found = self.flows[flow]
        names = [f'{flow}.served_fraction' if found.kind == LEGS else f'{flow}.actual_rate']
        for connection in found.connections:
            for side, store in zip(SIDES, (connection.source, connection.sink)):
                end = self.ends.get((store, side)) if store is not None else None
                if end is not None:
                    names.append(end.actual_rate)
        return names

    def _rate_of_store(self, name, stores):
        """Whether a dynamic read is the actual rate of an endpoint of one of `stores`."""
        dynamic = self.dynamic.get(name)
        return dynamic is not None and dynamic.source[0] == 'flows' and dynamic.source[1] in stores

    def _place_of(self):
        """The place of each value in `values`, as a key of a sort."""
        if len(self._places) != len(self.values):
            self._places = {name: place for place, name in enumerate(self.values)}
        return self._places.__getitem__

    def ordered(self, formulas):
        """Formulas and reductions in an order in which each comes after those that it reads."""
        done, order = set(), []
        formulas = set(formulas)

        def visit(name, path):
            if name in done:
                return
            if name in path:
                raise Outside(f'{name}: a formula that reads itself')
            for read in sorted(self.reads(name)):
                if read in formulas:
                    visit(read, path | {name})
            done.add(name)
            order.append(name)

        if formulas:
            for name in sorted(formulas, key=self._place_of()):
                visit(name, frozenset())
        return order


_VISITING = Expanded(frozenset({'<visiting>'}))


def _type_of(value_type):
    """(unit, boolean) of a type of a value: a number's unit, or '' for a yes/no, an enum or a text."""
    return (value_type.unit if isinstance(value_type, p.Number) else '', isinstance(value_type, p.Bool))


# ---- what a program holds, for the refusals ---------------------------------------------------------


def _statements(statements):
    """Each statement of a body, and of the bodies inside it."""
    for statement in statements:
        yield statement
        if isinstance(statement, p.If):
            yield from _statements(statement.then)
            yield from _statements(statement.orelse)
        elif isinstance(statement, p.Switch):
            for case in statement.cases:
                yield from _statements(case.body)
            yield from _statements(statement.orelse)


def _program_statements(program):
    """(origin, statement) of each statement of the setup, of the stages and of the triggers."""
    bodies = [program.setup]
    for template in program.templates:
        for event in template.events:
            bodies += [step.body for step in event.steps if isinstance(step, p.After)]
            bodies += [trigger.body for trigger in event.triggers]
    for body in bodies:
        for statement in _statements(body):
            yield statement.origin, statement


def _statement_expressions(statement):
    """The expressions of one statement, without those of the bodies inside it."""
    if isinstance(statement, p.Assign):
        value = statement.value
        if isinstance(value, Formula):
            return [value.expr]
        return [value] if isinstance(value, Expr) else []
    if isinstance(statement, p.Move):
        return [statement.amount]
    if isinstance(statement, p.Start):
        return list(statement.args)
    if isinstance(statement, p.If):
        return [statement.test]
    if isinstance(statement, p.Switch):
        return [statement.selector, *(case.guard for case in statement.cases if case.guard is not None)]
    return []


def _value_expressions(value):
    init = value.init.expr if isinstance(value.init, Formula) else value.init
    found = [init] if isinstance(init, Expr) else []
    found += [bound for bound in (value.lower, value.upper, value.scale) if bound is not None]
    for end in (value.outflow, value.inflow):
        if end is not None:
            found += [s.expr if isinstance(s, Formula) else s for s in (end.capacity, end.request) if s]
    return found


def _flow_expressions(flow):
    found = []
    for each in (flow, *flow.legs):
        found += [s.expr if isinstance(s, Formula) else s for s in (each.request, each.capacity) if s]
    return found


def _program_expressions(program):
    """(origin, expression, whether an event or the setup holds it) of each expression that a run
    evaluates."""
    for value in program.root:
        for expression in _value_expressions(value):
            yield value.origin, expression, False
    for template in program.templates:
        for value in template.values:
            for expression in _value_expressions(value):
                yield value.origin, expression, False
        for member in template.members:
            for name, init in member.values:
                written = init.expr if isinstance(init, Formula) else init
                if isinstance(written, Expr):
                    yield f'{member.id}.{name}', written, False
        for flow in template.flows:
            for expression in _flow_expressions(flow):
                yield flow.origin, expression, False
        for event in template.events:
            for part in (*event.params, *event.locals):
                found = _flow_expressions(part) if isinstance(part, p.Flow) else _value_expressions(part)
                for expression in found:
                    yield part.origin, expression, True
            for step in event.steps:
                found = [step.test] if isinstance(step, p.Until) else [step.delay, step.guard]
                for expression in found:
                    if expression is not None:
                        yield step.origin, expression, True
            for trigger in event.triggers:
                found = [trigger.test, *(c.init for c in trigger.captures)]
                found += [trigger.reset.expr] if trigger.reset is not None else []
                for expression in found:
                    if isinstance(expression, Expr):
                        yield trigger.origin, expression, True
    for origin, statement in _program_statements(program):
        for expression in _statement_expressions(statement):
            yield origin, expression, True
