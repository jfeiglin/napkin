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
- **Endpoints.** A stored number that supplies a flow has `outflow`, one that receives has `inflow`
  (`End`): a request (zero when left out), a capacity (none when left out), the actual rate (the sum
  of its flows' actual rates, a formula) and `flows`, the collection of its flows keyed by their
  creation numbers. A `priority(...)` allocation is kept as its items (`rankings`): a flow, or a
  projection of a keyed collection of flows, whose keys the run reads at its start.
- **Connected sets.** A flow joins its two ends, and a request or a capacity, of a flow or of an
  endpoint at its ends, that reads a store, through formulas, reductions or directly, joins that
  store to the flow's set: what a rate reads that moves is in its own set. Each set has its way
  (`Connected.way`): a set of one flow with no endpoint settings whose rates read nothing that moves
  runs on arrays with every other such set (`family.py`); any other set whose rates read nothing that
  moves runs on lines (`lines.py`), at any size; a set whose rates move runs as one component of the
  continuous engine (`component.py`) when each store meets one flow, it has no endpoint settings and
  at most `LIMIT` stores, and on the sparse integrator otherwise (`sparse.py`). A stored value that no
  flow touches does not move in this slice, since no stage writes it. A flow with no store at either
  end moves nothing, and its actual rate is the formula `min(request, capacity)`.
- **Assertions** over inputs are checked once, at the start of the run.

What a later slice runs is refused by name (`Outside`), with the slice that brings it: events,
triggers, the starts of the setup and assertions over state (S4); a key of `.at(...)` that moves or
is a function of the time other than `t`, and a keyed read of a value that moves (S4); a request or a capacity that reads an actual rate, which needs the rates of other flows settled
first (S4); reversible routes and flows with legs (S3); solvers (S5). Enums and texts are refused
too: a value of this slice is a number or a yes/no.
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
    Distribution,
    Draw,
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
    This,
    Time,
    Where,
    spelled,
)
from .collections import Entries, Keyed, Reduction
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
STARTS = (INPUT, STATE, CAPTURE, LINK)  # the kinds that the start of a run evaluates once
FIXED = (INPUT, LINK)  # what an assertion over inputs may read
SIDES = ('outflow', 'inflow')  # the endpoints of a stored number
# The ways of a connected set (`Connected.way`).
FAMILY, LINES, COMPONENT, SPARSE = 'family', 'lines', 'component', 'sparse'
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
class Flow:
    """A directed flow: its engine id, the engine names of its ends (None for SOURCE or SINK), of its
    request and of its capacity (None when it has none), and its unit."""

    name: str
    source: str | None
    sink: str | None
    request: str
    capacity: str | None
    unit: str

    @property
    def rate(self):
        """The rate that the flow asks of the continuous engine: its request, within its capacity."""
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
    `LINES`, `COMPONENT` or `SPARSE` (see the module)."""

    stores: tuple[str, ...]
    flows: tuple[str, ...]
    formulas: tuple[str, ...]
    stepped: tuple[str, ...] = ()
    way: str = COMPONENT


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
    if isinstance(item, (This, Item)):
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
    return False


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
        self._flow_parts = {}  # the engine id of each flow -> (its member's id, the flow)
        self.asserts = []  # (origin, the member that it belongs to, its node)
        self.failures = []  # the errors of the setup that the plan finds: the run fails with them
        self._derived = {}  # (owner, read) -> the engine name of a reduction or a keyed read
        self._expanded = {}
        self._places = {}  # the place of each value in `values`, for `ordered`
        self._given = {(item.member, item.name): item for item in configuration.inputs}
        self._refuse_parts()
        # The values of each scope, then the flows, whose ends are values, then the expressions of
        # each: an expression may read a part that comes later.
        self._declared = []
        members = [
            (template, row, member)
            for template in program.templates
            for row, member in enumerate(template.members)
        ]
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
        self._connect()
        self._refuse_reads()

    @classmethod
    def of(cls, program, configuration):
        """The plan of a run of a program under a configuration."""
        return cls(program, configuration)

    # ---- what this slice refuses ----------------------------------------------------------------

    def _refuse_parts(self):
        program = self.program
        if program.setup:
            raise Outside('the statements of the setup, which start events (S4)')
        for template in program.templates:
            for what, found, slice_ in (
                ('an event', template.events, 'S4'),
                ('a solver', template.solvers, 'S5'),
            ):
                if found:
                    raise Outside(f'{found[0].origin}: {what} ({slice_})')
            if template.status is not None:
                raise Outside(f'{template.status.origin or template.name}: a status display (C)')

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

    def _declare(self, value, scope):
        """A value of the root (`scope` None) or of one member: (template, row, member)."""
        member = scope[2] if scope is not None else None
        key = Key(member.id if member is not None else '', (value.name,))
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
        own = member.value(value.name) if member is not None else None
        init = own if own is not None else value.init
        if isinstance(value.type, p.DistributionType):
            self._declare_distribution(value, member, name, init)
            return
        if not isinstance(value.type, (p.Number, p.Bool)):
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
                node = self._given_node(given, name, unit, boolean)
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

    def _given_node(self, given, name, unit, boolean):
        """The node of the value that a configuration gives an input, in canonical units (D2). Its
        unit is a spelling of the program's table, or a unit of the library given whole."""
        found = given.value
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
        """A flow of one member: its ends, its request and capacity, and its actual rate."""
        member = scope[2]
        if flow.kind != p.DIRECTED:
            raise Outside(
                f'{flow.origin}: a {"reversible route" if flow.kind == p.REVERSIBLE else "flow with legs"} (S3)'
            )
        name = name_of(Key(member.id, (flow.name,)))
        self._flow_parts[name] = (member.id, flow)
        ends = [self._end(end, scope, flow.origin) for end in (flow.source, flow.sink)]
        properties = {}
        for which in ('request', 'capacity'):
            setting = getattr(flow, which)
            key = Key(member.id, (flow.name, which))
            if setting is None and which == 'capacity':
                continue
            properties[which] = name_of(key)
            kind = FORMULA if isinstance(setting, Formula) else CAPTURE
            self._add(Value(name_of(key), key, kind, None, flow.unit))

            def make(setting=setting, key=key, kind=kind):
                shape, binding = None, ()
                if setting is None:
                    node = nodes.const(0)  # a request left out is zero
                else:
                    expression = setting.expr if isinstance(setting, Formula) else setting
                    node, binding = self._bound(expression, scope, flow.origin)
                    shape = expression.node if binding is not None else None
                self.values[name_of(key)] = Value(
                    name_of(key), key, kind, node, flow.unit, shape=shape, binding=binding or ()
                )

            self._declared.append(make)
        made = Flow(name, *ends, properties['request'], properties.get('capacity'), flow.unit)
        rate = Key(member.id, (flow.name, 'actual_rate'))
        if made.source is None and made.sink is None:
            # Nothing to move: the actual rate is what the flow asks.
            self._add(Value(name_of(rate), rate, FORMULA, made.rate, flow.unit))
        else:
            self._add(Value(name_of(rate), rate, RATE, None, flow.unit))
            self.flows[name] = made

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
        """The endpoints of each stored number that meets a flow or has settings (see the module)."""
        incident = {}
        for flow in self.flows.values():
            for side, end in zip(SIDES, (flow.source, flow.sink)):
                if end is not None:
                    incident.setdefault((end, side), []).append(flow.name)
        scopes = [(value, None) for value in self.program.root]
        scopes += [(value, scope) for scope in members for value in scope[0].values]
        for value, scope in scopes:
            store = name_of(Key(scope[2].id if scope is not None else '', (value.name,)))
            for side in SIDES:
                setting, flows = getattr(value, side), incident.get((store, side), [])
                if setting is None and not flows:
                    continue
                found = self.values.get(store)
                if found is None or found.kind != STATE or found.boolean:
                    raise Outside(f'{value.origin}: {side} of a value that is no stored number')
                self._declare_end(store, value, scope, side, setting or p.Endpoint(), tuple(flows))

    def _declare_end(self, store, value, scope, side, setting, flows):
        owner = scope[2].id if scope is not None else ''
        unit = self.flows[flows[0]].unit if flows else ''
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
        total = None
        for flow in flows:
            part = nodes.ref(f'{flow}.actual_rate')
            total = part if total is None else nodes.binary('add', total, part)
        self._add(Value(name_of(rate), rate, FORMULA, total if total is not None else nodes.const(0.0), unit))
        self.ends[(store, side)] = End(store, side, names['request'], names.get('capacity'), name_of(rate), flows)
        if isinstance(setting.allocation, p.Priority):
            self._declared.append(lambda: self._ranking(store, side, setting.allocation, scope, origin))

    def _ranking(self, store, side, allocation, scope, origin):
        """The items of a `priority(...)`: ('one', flow) or ('keyed', ((key, flow), ...)), where a
        key is the engine name of a value or a creation number."""
        items = []
        for path in allocation.items:
            point = self._resolve(path, scope, origin)
            if point[0] == 'flow':
                items.append(('one', f'{point[1]}.{point[2].name}'))
            elif point[0] == 'many' and all(each[0] == 'flow' for each in point[1].points):
                entries = point[1]
                flows = tuple(f'{each[1]}.{each[2].name}' for each in entries.points)
                items.append(('keyed', tuple(zip(entries.keys, flows))))
            else:
                raise Outside(f'{origin}: priority({spelled(path)}), which names no flow (a type error)')
        mine = set(self.ends[(store, side)].flows)
        for item in items:
            named = [item[1]] if item[0] == 'one' else [flow for _, flow in item[1]]
            for flow in named:
                if flow not in mine:
                    self.failures.append(
                        f'{origin}: priority(...) at {store}.{side} names {flow}, which is not a flow of '
                        'that endpoint'
                    )
        self.rankings[(store, side)] = tuple(items)

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
                elif point[0] == 'member':
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
            else:
                raise Outside(f'{origin}: the read {spelled(read)} (S4)')
        node = _renamed(expression.node, names)
        return node, (None if binding is None else tuple(sorted(binding.items())))

    # ---- paths ------------------------------------------------------------------------------------

    def _resolve(self, path, scope, origin, item=None):
        """What a path names, for a member's (`scope` = (template, row, member)) or the root's
        expression: `('value', engine name)`, `('member', id)`, `('flow', id, flow)` or
        `('many', Entries)`."""
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
            raise Outside(f'{origin}: the bare name {start.name}, of an event or a solver (S4, S5)')
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
                if part.kind != p.DIRECTED:
                    raise Outside(f'{origin}: the flow {point[1]}.{name} (S3)')
                return ('flow', point[1], part)
            raise Outside(f'{origin}: {point[1]}.{name} names an event or a solver (S4, S5)')
        if kind == 'flow':
            _, owner, flow = point
            if name not in ('actual_rate', 'request', 'capacity'):
                raise Outside(f'{origin}: the {name} of a flow (S2)')
            if name == 'capacity' and flow.capacity is None:
                raise Outside(f'{origin}: {owner}.{flow.name}.capacity, a capacity left out, has no value')
            return ('value', f'{owner}.{flow.name}.{name}')
        if kind == 'many':
            entries = point[1]
            points = tuple(self._step(each, name, origin) for each in entries.points)
            if any(each[0] == 'many' for each in points):
                raise Outside(f'{origin}: a collection of collections (a later slice)')
            return ('many', replace(entries, points=points, whole=False))
        if kind == 'value' and name in SIDES:
            if (point[1], name) not in self.ends:
                raise Outside(f'{origin}: {point[1]}.{name}, which no flow meets (a type error)')
            return ('end', point[1], name)
        if kind == 'end':
            end = self.ends[(point[1], point[2])]
            if name == 'flows':
                points = tuple(('flow', *self._flow_parts[flow]) for flow in end.flows)
                keys = tuple(list(self.flows).index(flow) for flow in end.flows)
                return ('many', Entries(None, points, (None,) * len(points), keys))
            found = {'request': end.request, 'capacity': end.capacity, 'actual_rate': end.actual_rate}
            if name not in found:
                raise Outside(f'{origin}: the {name} of {point[1]}.{point[2]}, which is no value (a type error)')
            if found[name] is None:
                raise Outside(f'{origin}: {point[1]}.{point[2]}.capacity, a capacity left out, has no value')
            return ('value', found[name])
        raise Outside(f'{origin}: the step {name} of a value, which names nothing of it (a type error)')

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
        entries = self._many(read.source, scope, origin, item)
        names = entries.names
        if names is None and (read.op != 'count' or any(point[0] not in ('member', 'flow') for point in entries.points)):
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
        entries = self._many(lookup.source, scope, origin, item)
        x = self.node(lookup.key, scope, origin, item)
        by_time = isinstance(lookup.key.node, nodes.Ref) and isinstance(
            lookup.key.read(lookup.key.node.name), Time
        )
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

    def formula_reads(self, node):
        """The names other than formulas and reductions that a node reads, through them (the keyed
        reads by the time among them), and the formulas and reductions on the way."""
        found = self.expansion(node)
        return set(found.leaves | found.stepped), set(found.formulas)

    # ---- the connected sets ---------------------------------------------------------------------

    def settings_of(self, flow):
        """The engine names of what a flow's rate reads: its request and capacity, and the request and
        capacity of the endpoints at its two ends."""
        names = [flow.request] + ([flow.capacity] if flow.capacity is not None else [])
        for side, store in zip(SIDES, (flow.source, flow.sink)):
            end = self.ends.get((store, side)) if store is not None else None
            if end is not None:
                names += [end.request] + ([end.capacity] if end.capacity is not None else [])
        return names

    def _settled(self, end):
        """Whether an endpoint has a capacity or a request that is not left out."""
        request = self.values[end.request]
        return end.capacity is not None or not (
            isinstance(request.node, nodes.Const) and request.node.value == 0
        )

    def _connect(self):
        """The connected sets of stores and flows, and the way of each (see the module)."""
        parent = {}

        def root(item):
            parent.setdefault(item, item)
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def join(a, b):
            parent[root(a)] = root(b)

        moving = {end for flow in self.flows.values() for end in (flow.source, flow.sink) if end}
        self.moving = frozenset(moving)
        reads = {}
        for flow in self.flows.values():
            root(flow.name)
            for end in (flow.source, flow.sink):
                if end is not None:
                    join(('store', end), flow.name)
            found = reads[flow.name] = Expanded.union(self.expanded(name) for name in self.settings_of(flow))
            for name in found.leaves:
                if self._is_rate(name):
                    raise Outside(
                        f'{flow.name}: a request or a capacity that reads an actual rate, which needs the '
                        'rates of other flows settled first (S4)'
                    )
                if name in moving:
                    join(('store', name), flow.name)
        sets = {}
        for flow in self.flows.values():
            sets.setdefault(root(flow.name), ([], []))[1].append(flow.name)
        for name in self.values:
            if name in moving:
                sets[root(('store', name))][0].append(name)
        meets = {}
        for flow in self.flows.values():
            for end in (flow.source, flow.sink):
                if end is not None:
                    meets[end] = meets.get(end, 0) + 1
        made = []
        for stores, flows in sets.values():
            found = Expanded.union(reads[flow] for flow in flows)
            moves = found.time or bool(found.leaves & moving)
            settled = any(
                self._settled(self.ends[(store, side)])
                for store in stores
                for side in SIDES
                if (store, side) in self.ends
            )
            if not moves:
                way = FAMILY if len(flows) == 1 and not settled else LINES
            elif not settled and len(stores) <= LIMIT and all(meets[store] == 1 for store in stores):
                way = COMPONENT
            else:
                way = SPARSE
            made.append(
                Connected(
                    tuple(stores),
                    tuple(flows),
                    tuple(self.ordered(found.formulas)),
                    tuple(sorted(found.stepped)),
                    way,
                )
            )
        self.sets = tuple(made)

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
            if len(self._places) != len(self.values):
                self._places = {name: place for place, name in enumerate(self.values)}
            for name in sorted(formulas, key=self._places.__getitem__):
                visit(name, frozenset())
        return order


_VISITING = Expanded(frozenset({'<visiting>'}))
