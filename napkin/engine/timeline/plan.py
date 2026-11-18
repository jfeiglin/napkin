"""The plan of a run: what the engine runs of a program, under one configuration (`Plan.of`).

A plan reads a program (`napkin/program`) and gives each value that a run holds a name of the engine
and an expression over those names: a node of `napkin/core/expr`, whose names are engine names. The
continuous engine and the record read these names; nothing reads the spelling of a path.

- **Names.** A value is named by its key in the record (`record.Key`): `tank.water`; the actual rate,
  the request and the capacity of a flow `clinic.delivery.actual_rate`, `clinic.delivery.request`,
  `clinic.delivery.capacity`; a value of the root by its own name. The continuous engine knows a
  flow by `clinic.delivery`. A draw is named by the member that executes it and its site.
- **Kinds.** An input is fixed for the run: the configuration's value, or its default. A stored value
  starts from its initializer. Each of these, a draw, and a request or a capacity that is captured
  once, is evaluated at the start of the run, in the order of what it reads. A formula, and a request
  or a capacity written as a formula, is evaluated at each read. A request left out is zero; a
  capacity left out sets no limit and has no value.
- **Draws.** A draw in an initializer is executed once at the start, keyed by its site and by the
  member that executes it. A draw of a path reads the distribution of a distribution-valued value of
  that member: the configuration's, or its default. An input that the configuration sets skips the
  draws of its default (D2).
- **Connected sets.** A flow joins its two ends, and a request or a capacity that reads a store,
  through formulas or directly, joins that store to the flow's set: what a rate reads that moves is
  in its own set. Each set runs as one component of the continuous engine (`component.py`). A stored
  value that no flow touches does not move in this slice, since no stage writes it. A flow with no
  store at either end moves nothing, and its actual rate is the formula `min(request, capacity)`.

What a later slice runs is refused by name (`Outside`), with the slice that brings it: events,
triggers and the starts of the setup (S4); links, collections, reductions, keyed reads and assertions
(S1); the scopes of an endpoint (`outflow`, `inflow`), two flows out of one store or into one
store, which its endpoint shares at a bound, and a rate that reads an actual rate (S2); reversible
routes and flows with legs (S3); solvers (S5). Enums and texts are refused too: a value of
this slice is a number or a yes/no.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core import expr as nodes
from ...expressions import UnitSystem
from ...program import parts as p
from ...program.config import ConfigurationError, Quantity
from ...program.record import Key
from ...program.refs import Distribution, Draw, Expr, Formula, Named, Path, Root, This, Time, spelled

# The kinds of the values of a plan.
INPUT = 'input'  # fixed for the run
STATE = 'state'  # stored: from its initializer; a store of a connected set moves
CAPTURE = 'capture'  # a request or a capacity captured once, at the start
FORMULA = 'formula'  # evaluated at each read
RATE = 'rate'  # the actual rate of a flow, which the continuous engine gives
STARTS = (INPUT, STATE, CAPTURE)  # the kinds that the start of a run evaluates once


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
    formula; a rate has none. `unit` is the spelling of its declared unit (`''` for a plain number
    or a yes/no)."""

    name: str
    key: Key
    kind: str
    node: nodes.Node | None
    unit: str = ''
    boolean: bool = False
    lower: nodes.Node | None = None  # an input's admitted range, or a stored value's bounds
    upper: nodes.Node | None = None
    scale: nodes.Node | None = None  # a stored value's numerical scale (D8)
    given: bool = False  # an input that the configuration sets


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
class Connected:
    """A connected set of stores and flows, and the formulas that its rates read, each after those
    that it reads."""

    stores: tuple[str, ...]
    flows: tuple[str, ...]
    formulas: tuple[str, ...]


def _renamed(node, names):
    """A node with each of its names replaced by its engine name."""
    if isinstance(node, nodes.Ref):
        return nodes.ref(names[node.name])
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
        self.values, self.draws, self.flows, self.distributions = {}, {}, {}, {}
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
        unused = sorted(f'{member}.{name}'.lstrip('.') for member, name in self._given)
        if unused:
            raise ConfigurationError(f'no input of the program has these names: {", ".join(unused)}')
        for make in self._declared:
            make()
        self._connect()

    @classmethod
    def of(cls, program, configuration):
        """The plan of a run of a program under a configuration."""
        return cls(program, configuration)

    # ---- what this slice refuses ----------------------------------------------------------------

    def _refuse_parts(self):
        program = self.program
        if program.setup:
            raise Outside('the statements of the setup, which start events (S4)')
        if program.asserts:
            raise Outside('an assertion of the root (S1, S4)')
        for template in program.templates:
            for what, found, slice_ in (
                ('an event', template.events, 'S4'),
                ('a solver', template.solvers, 'S5'),
                ('an assertion', template.asserts, 'S1, S4'),
            ):
                if found:
                    raise Outside(f'{found[0].origin}: {what} ({slice_})')
            if template.status is not None:
                raise Outside(f'{template.status.origin or template.name}: a status display (C)')

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
        if value.kind in (p.LINK, p.COLLECTION):
            raise Outside(f'{value.origin}: a {value.kind} (S1)')
        if value.outflow is not None or value.inflow is not None:
            raise Outside(f'{value.origin}: the scopes of an endpoint, outflow and inflow (S2)')
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
            if given is not None:
                node = self._given_node(given, name, unit, boolean)
            elif kind == FORMULA:
                node = self.node(init.expr, scope, value.origin)
            else:
                node = self.node(init, scope, value.origin)
            bounds = [
                self.node(bound, scope, value.origin) if bound is not None else None
                for bound in (value.lower, value.upper)
            ]
            scale = self.node(value.scale, scope, value.origin) if value.scale is not None else None
            self.values[name] = Value(name, key, kind, node, unit, boolean, *bounds, scale, given is not None)

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
        """The node of the value that a configuration gives an input, in canonical units (D2)."""
        found = given.value
        if boolean:
            if not isinstance(found, bool):
                raise ConfigurationError(f'{name} is a yes/no: it takes true or false, not {found!r}')
            return nodes.const(found)
        if not isinstance(found, Quantity) or isinstance(found.number, bool):
            raise ConfigurationError(f'{name} is a number in {unit or "no unit"}: it takes a quantity')
        try:
            declared, written = self.program.unit(unit), self.program.unit(found.unit)
        except KeyError:
            raise ConfigurationError(f'{name}: the unit {found.unit!r} is not in the program') from None
        if not declared.compatible(written):
            raise ConfigurationError(
                f'{name} is in {unit or "no unit"}: {found.unit or "no unit"} does not convert'
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
                if setting is None:
                    node = nodes.const(0)  # a request left out is zero
                else:
                    expression = setting.expr if isinstance(setting, Formula) else setting
                    node = self.node(expression, scope, flow.origin)
                self.values[name_of(key)] = Value(name_of(key), key, kind, node, flow.unit)

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
        name, _ = self.path(end, scope, origin)
        found = self.values.get(name)
        if found is None or found.kind != STATE or found.boolean:
            raise Outside(f'{origin}: an end of a flow that is no stored number of this slice')
        return name

    # ---- expressions ----------------------------------------------------------------------------

    def node(self, expression, scope, origin):
        """The node of an expression of a scope, with engine names."""
        if not isinstance(expression, Expr):
            raise Outside(f'{origin}: an initializer of kind {type(expression).__name__} (a later slice)')
        names = {}
        for name, read in expression.reads:
            if isinstance(read, Time):
                names[name] = 't'
            elif isinstance(read, Path):
                names[name] = self.path(read, scope, origin)[0]
            elif isinstance(read, Draw):
                names[name] = self._draw(read, scope, origin)
            else:
                raise Outside(f'{origin}: the read {spelled(read)} (a later slice)')
        return _renamed(expression.node, names)

    def path(self, path, scope, origin):
        """(engine name, value) of what a path names, for a member's (`scope` = (template, row,
        member)) or the root's expression."""
        start, steps = path.start, path.steps
        if isinstance(start, This):
            if scope is None:
                raise Outside(f'{origin}: `this` at the root')
            template, member = scope[0], scope[2]
        elif isinstance(start, Named):
            template, row = self.program.member(start.id)
            member = template.members[row]
        elif isinstance(start, Root):
            template, member = None, None
        else:
            raise Outside(f'{origin}: the path {spelled(path)} (S1, S4)')
        if not steps:
            raise Outside(f'{origin}: an entity as a value (S1)')
        part = template.part(steps[0]) if template is not None else self.program.root_value(steps[0])
        owner = member.id if member is not None else ''
        if isinstance(part, p.Value):
            name = name_of(Key(owner, (steps[0],)))
            if len(steps) > 1:
                raise Outside(f'{origin}: the path {spelled(path)} (S1, S2)')
            if part.kind in (p.LINK, p.COLLECTION):
                raise Outside(f'{origin}: the path {spelled(path)} through a {part.kind} (S1)')
            return name, part
        if isinstance(part, p.Flow):
            if part.kind != p.DIRECTED:
                raise Outside(f'{origin}: the path {spelled(path)} (S3)')
            if len(steps) != 2 or steps[1] not in ('actual_rate', 'request', 'capacity'):
                raise Outside(f'{origin}: the path {spelled(path)} (S1, S2)')
            if steps[1] == 'capacity' and part.capacity is None:
                raise Outside(f'{origin}: {spelled(path)}, a capacity left out, has no value')
            return name_of(Key(owner, steps)), part
        raise Outside(f'{origin}: the path {spelled(path)} names an event or a solver (S4, S5)')

    def _draw(self, read, scope, origin):
        """The engine name of a draw that an initializer executes, with its distribution."""
        member = scope[2].id if scope is not None else ''
        if isinstance(read.source, Distribution):
            distribution = read.source
        else:
            name, _ = self.path(read.source, scope, origin)
            if name not in self.distributions:
                raise Outside(
                    f'{origin}: a draw of {spelled(read.source)}, which is no distribution of this slice'
                )
            distribution = self.distributions[name]
        if distribution.family == 'categorical':
            raise Outside(f'{origin}: a draw of a categorical distribution (S4)')
        name = f'{member}|{read.site}'
        self.draws.setdefault(name, Drawn(name, distribution, read.site, member))
        return name

    def reads(self, name):
        """The names that the value `name` reads, directly."""
        node = self.values[name].node
        return set() if node is None else set(nodes.names(node)) - {'t'}

    def formula_reads(self, node):
        """The names other than formulas that a node reads, through the formulas that it reads."""
        found, pending, seen = set(), [node], set()
        while pending:
            for name in set(nodes.names(pending.pop())) - {'t'}:
                value = self.values.get(name)
                if value is not None and value.kind == FORMULA:
                    if name not in seen:
                        seen.add(name)
                        pending.append(value.node)
                else:
                    found.add(name)
        return found, seen

    # ---- the connected sets ---------------------------------------------------------------------

    def _connect(self):
        """The connected sets of stores and flows (see the module)."""
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
        for side in ('source', 'sink'):
            ends = [getattr(flow, side) for flow in self.flows.values() if getattr(flow, side)]
            shared = sorted({end for end in ends if ends.count(end) > 1})
            if shared:
                # At a bound the endpoint shares its flows by its own rule.
                way = 'out of' if side == 'source' else 'into'
                raise Outside(f'{shared[0]}: two flows {way} one store, which its endpoint shares (S2)')
        for flow in self.flows.values():
            root(flow.name)
            for end in (flow.source, flow.sink):
                if end is not None:
                    join(('store', end), flow.name)
            leaves, _ = self.formula_reads(flow.rate)
            for name in leaves:
                read = self.values.get(name)
                if read is not None and read.kind == RATE:
                    raise Outside(f'{flow.name}: a request or a capacity that reads an actual rate (S2)')
                if name in moving:
                    join(('store', name), flow.name)
        sets = {}
        for flow in self.flows.values():
            sets.setdefault(root(flow.name), ([], []))[1].append(flow.name)
        for name in self.values:
            if name in moving:
                sets[root(('store', name))][0].append(name)
        made = []
        for stores, flows in sets.values():
            read = set()
            for flow in flows:
                read |= self.formula_reads(self.flows[flow].rate)[1]
            made.append(Connected(tuple(stores), tuple(flows), tuple(self.ordered(read))))
        self.sets = tuple(made)

    def ordered(self, formulas):
        """Formulas in an order in which each comes after the formulas that it reads."""
        done, order = set(), []

        def visit(name, path):
            if name in done:
                return
            if name in path:
                raise Outside(f'{name}: a formula that reads itself')
            for read in sorted(self.reads(name)):
                if read in formulas:
                    visit(read, (*path, name))
            done.add(name)
            order.append(name)

        for name in self.values:
            if name in formulas:
                visit(name, ())
        return order
