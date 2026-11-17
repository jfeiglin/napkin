"""The plan of the timeline engine: what follows from the structure of a hybrid core alone.

A plan is made once for a structure (`Plan.of`) and serves every run of it: each sample of a study,
each edit of a number. It reads a hybrid core (`napkin/model/hybrid.py`) and holds:

- **the spaces**: the things that no table makes are one space of one instance, and each family is a
  space with one instance for each row. A name belongs to the space of its thing;
- **each expression as one node**, with each formula in the place of its name, and with each
  reduction over the instances of a family (`sum`, `any`, `all`, `min`, `max` over a list) as an
  `Aggregate` that the expression reads by a name;
- **what each quantity is between two moments**: a value that only a step changes; a *line*, whose
  rate reads nothing that moves, so that it is a straight line until a step writes what its rate
  reads; or a member of a *numeric block*, a set of quantities whose rates read one another, which a
  solver integrates;
- **the kind of each rule** (`analysis.structure.classify`, the one classifier of the compiler);
- **the readers of each name**: the rules, the lines, the blocks and the members of the aggregates
  that read it, and for which instances. The engine reads a part again only when a step wrote a name
  that the part reads (D-65).

How a part of one space reads a name of another: a part of a family reads a name of the things
outside the tables as one value for all its instances; a name of a family that a link of its rows
names as the value of the instance that its own row links to; a name of a family of one instance as
that one value. A part outside the families reads the instances of a family only through a list.

`Outside` says that the model has a part that this engine does not run yet. It names the part.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np

from ...core import expr
from ...core.derivatives import derivative
from ...expressions import UnitSystem
from ...model.analysis import structure as analysis
from ...model.ir import COUNT, ENTERED, TIME, thaw
from ...model.structure import thawed
from .component import NetCheck, NetCoupling, NetFlow, NetGroup, NetRate, NetSum, Network

SCALARS = 0
LISTS = ('sum', 'any', 'all', 'min', 'max')
SAME, ALL, LINK = 'same', 'all', 'link'


def _no_text(source, where):
    """Raise the TypeError of a text in the place of a node: the parts of a compiled model hold nodes."""
    if isinstance(source, str):
        raise TypeError(f'{where}: an expression is a node or a number, not a text')


class Outside(Exception):
    """A part of a model, or a state of a run, that the timeline engine does not run yet.

    The engine has two tiers for a space (the module of `run.py`). `space`: the space of a part that
    the fast tier does not run, where the general tier can: the plan is made again with that space
    in the general tier. `tier`: the general tier cannot take a space, where the fast tier may."""

    def __init__(self, message, space=None, tier=False):
        super().__init__(message)
        self.space, self.tier = space, tier


@dataclass(frozen=True)
class Space:
    """One set of instances: the things outside the tables (one instance), or a family."""

    index: int
    host: str | None
    count: int
    family: object = None
    # {index of another space: the place, in that space, of the instance that each row links to}
    links: dict = field(default_factory=dict)
    # {index of another space: {place in it: the places of this space that link to it}}
    linked_from: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Term:
    """One member of a list: an expression of the instances of one space."""

    space: int
    node: object


@dataclass(frozen=True)
class Aggregate:
    """A reduction over a list. `moving`: a member reads a value that moves between moments."""

    name: str
    function: str
    terms: tuple
    moving: bool


@dataclass(frozen=True)
class Outcome:
    name: str
    chance: object  # a node, None (the only outcome) or 'else'
    sets: tuple  # (target, node or None, mode value or None)
    moves: tuple  # (source, target, node)
    fires: tuple
    emits: tuple
    available: object = None  # a node: the outcome can happen only while it holds
    label: object = None
    path: object = None
    basis: object = None


@dataclass(frozen=True)
class Check:
    """An `assert` on the state, which holds at each step: `node` is its condition."""

    index: int
    name: str
    space: int
    node: object
    message: str | None
    path: str | None
    source: object = None  # the expression as the model writes it, for the message of a failure


@dataclass(frozen=True)
class Partition:
    """A sum that holds at each step: the parts add up to the total, within the tolerance."""

    index: int
    name: str
    space: int
    total: object
    parts: tuple
    tolerance: object
    path: str | None


@dataclass(frozen=True)
class Extra:
    """A value that a rule reads at one stage of a firing (`trigger` or `fire`): a value that it
    draws (`family`, and `args` as (name, node)), or a value of the past of the run (`delayed`: `expr`
    read `delay` before the firing)."""

    name: str
    kind: str
    stage: str
    expr: object = None
    delay: object = None
    family: str | None = None
    args: tuple = ()


@dataclass(frozen=True)
class Rule:
    index: int
    name: str
    space: int
    line: int
    once: bool
    named: bool
    kind: str  # 'timer', 'crossing' or 'discrete'
    gate: object
    times: tuple
    var: str | None
    rising: bool
    value: object
    when: object
    delay: object
    outcomes: tuple
    emits: tuple
    keep: object = None  # `while K`: a firing that waits is cancelled when K fails
    each: tuple = ()  # `each W`: the values of the window
    extras: tuple = ()  # the values that it draws, and the values of the past that it reads
    # What a trace entry and a decision say of the rule: its thing, its text, its place in the file
    # and its basis; and whether an actor decides its outcome (`choice`).
    entity: str = ''
    label: object = None
    path: object = None
    basis: object = None
    choice: bool = False
    delay_path: object = None


@dataclass(frozen=True)
class Fact:
    """One thing that an actor sees at a decision: the value of an expression, or how many times an
    event has happened."""

    name: str
    event: str | None
    node: object
    kind: str | None
    values: tuple
    unit: str | None


@dataclass(frozen=True)
class Quantity:
    name: str
    space: int
    kind: str  # the kind of the language: stock, cumulative, variable, ...
    form: str  # 'value', 'line' or 'numeric'
    start: object
    scale: float
    lower: float
    upper: float
    size: float | None
    monotone: bool
    block: int | None = None


@dataclass(frozen=True)
class Block:
    """A set of quantities whose rates read one another. `whole`: its instances read one another
    (through a list or a link), so they are one problem; else each instance is a problem of its own.
    `linear`: each rate is a sum of constants times the quantities of the block, plus a constant,
    where a constant is a value that only a step changes. Between two moments such a block has a
    closed form."""

    index: int
    names: tuple
    space: int
    whole: bool
    linear: bool = False
    # The block of a space whose flows need the allocation in full: its rates come from the
    # allocation of the network of the space, with the bounds that hold its quantities.
    net: bool = False


@dataclass(frozen=True)
class Group:
    """An allocation group: the flows that share one limit (`capacity`, a node). `flows` are their
    names in the order of the flows of the model. With the policy `proportional` they share the limit
    in proportion to what they ask; with `priority` the flows of `order` take theirs in that order."""

    name: str
    space: int
    capacity: object
    flows: tuple
    policy: str = 'proportional'
    order: tuple = ()


@dataclass(frozen=True)
class Floor:
    """A quantity on a line that can rest on its lower bound. While it rests, the flows out of it
    get no more than what comes in. `flag` names the value that says, for each instance, whether it
    rests; `inflows` and `outflows` are the flows into it and out of it, `base` the nodes of its rate
    that are no flow, and `group` the allocation group of its outflows, if they have one."""

    name: str
    flag: str
    inflows: tuple
    base: tuple
    outflows: tuple
    group: str | None


def _number(source):
    """A bound or a size of a quantity that the structure holds as a number."""
    return float(thawed(source))


def _children_changed(node, change):
    if isinstance(node, expr.Unary):
        return expr.unary(node.op, change(node.operand))
    if isinstance(node, expr.Binary):
        return expr.binary(node.op, change(node.left), change(node.right))
    if isinstance(node, expr.Compare):
        return expr.compare(node.ops, [change(item) for item in node.operands])
    if isinstance(node, expr.BoolOp):
        return expr.boolean(node.op, [change(item) for item in node.values])
    if isinstance(node, expr.IfElse):
        return expr.if_else(change(node.test), change(node.body), change(node.orelse))
    if isinstance(node, expr.Call):
        return expr.call(node.function, [change(arg) for arg in node.args])
    if isinstance(node, expr.Foreign):
        raise Outside('an expression outside the language')
    return node


class Plan:
    """See the module."""

    @classmethod
    def of(cls, core, run=None, values=None, scalars=None):
        """The plan of one run of a hybrid core. `run` names a run of the model (default: its first);
        `values` are values of inputs of the things outside the tables for the resolution of the
        model of the representatives.

        `scalars` says which tier runs the things outside the tables, the space of one instance:
        'general', 'fast', or None for the general tier where it can take them, else the fast tier.
        A family is in the fast tier, but for a family with a part that only the general tier runs."""
        model = core.model
        run = run or next(iter(model.runs))
        resolved = model.resolve(run, values)
        # The model of the representatives proves its facts for one row of each class: the engine
        # reads the ones that hold for every row (`Hybrid.proved`).
        proved = core.proved(run, resolved if values else None)
        if proved is not None:
            resolved = dataclasses.replace(
                resolved,
                **{name: tuple(found) for name, found in proved.items() if name.startswith('proven_')},
            )
        key = next((k for k in core.listed if tuple(k) == tuple(resolved.starts)), None)
        if key is None:
            if len(core.listed) != 1:
                raise Outside('a model with start-state options')
            key = next(iter(core.listed))
        if scalars not in (None, 'general', 'fast'):
            raise ValueError(f'scalars: {scalars!r} is not general or fast')
        parts = (core, core.listed[key], resolved, thaw(model.library))
        try:
            return cls.made(
                parts, frozenset() if scalars == 'fast' else frozenset({SCALARS}), scalars is None
            )
        except Outside as problem:
            if not (problem.tier and scalars is None):
                raise
        return cls.made(parts, frozenset(), False)

    @classmethod
    def flat(cls, resolved, library, scalars=None):
        """The plan of a resolved run of a model with no table, from its flat structure: what
        `engine/runtime.simulate` is given. The things of the model are one space of one instance."""
        # No table: the rank of each event has the place of its thing in the order of the file.
        core = SimpleNamespace(families=(), positions=dict)
        parts = (core, resolved, resolved, thaw(library))
        try:
            return cls.made(
                parts, frozenset() if scalars == 'fast' else frozenset({SCALARS}), scalars is None
            )
        except Outside as problem:
            if not (problem.tier and scalars is None):
                raise
        return cls.made(parts, frozenset(), False)

    @classmethod
    def made(cls, parts, general, optional):
        """The plan with the spaces `general` in the general tier, and with each space that has a
        part that the fast tier does not run."""
        general = set(general)
        why = {}  # the part of each space that only the general tier runs
        while True:
            try:
                plan = cls(*parts, general=frozenset(general))
            except Outside as problem:
                if problem.space is None or problem.space in general:
                    raise
                general.add(problem.space)
                why[problem.space] = str(problem)
                continue
            plan.source, plan.optional, plan.others = parts, optional and SCALARS in plan.general, {}
            plan.only_general = why
            return plan

    def wider(self, space):
        """This plan with one more space in the general tier, or None when the space is there."""
        if space is None or space in self.general:
            return None
        if space not in self.others:
            self.others[space] = Plan.made(self.source, self.forced | {space}, self.optional)
        return self.others[space]

    def fast(self):
        """This plan with the things outside the tables in the fast tier, when it has them in the
        general tier only because that is the tier of a space of one instance; else None."""
        if not self.optional:
            return None
        if 'fast' not in self.others:
            self.others['fast'] = Plan.made(self.source, self.forced - {SCALARS}, False)
        return self.others['fast']

    def __init__(self, core, structure, resolved, library, general=frozenset()):
        # `structure` is the typed parts of the structure (`model.structure.Structure`): the plan
        # and its readers read them as `s`.
        self.core, self.s, self.library = core, structure, library
        self.resolved = resolved
        self.forced = frozenset(general)
        self.units = UnitSystem(library['units'])
        self.horizon = float(resolved.time.horizon)
        s = structure
        self.space_by_name = {}
        self._spaces(core)
        self.position = core.positions()
        self.kind = {}  # name -> 'value', 'line', 'numeric', 'aggregate', 'formula'
        self.aggregates = {}
        self._formulas = {name: item.expr for name, item in s.computed.items()}
        # An output can read another output: each estimated output is an expression by its name.
        for name, item in s.outcomes.items():
            if item.expr is not None and name not in self._formulas:
                self._formulas[name] = item.expr
        # A status is the value of its first case that holds, else its default: one expression.
        for name, label in s.labels.items():
            node = expr.const(label.default.value)
            for case in reversed(label.cases):
                node = expr.if_else(case.when, expr.const(case.value), node)
            self._formulas[name] = node
        self._inlined = {}
        self._listed_formulas = {}
        self.moving_quantities = analysis.evolving_parts(s)
        self._names(resolved)
        self._quantities()
        self._rules()
        # An output with no expression is not estimated: it has no value, which is not the value 0.
        self.unestimated = tuple(name for name, item in s.outcomes.items() if item.expr is None)
        for name in self.unestimated:
            # Another output can read it: where it does, that output has no value either.
            self.kind.setdefault(name, 'unknown')
        self.outputs = {
            name: self.node(item.expr, SCALARS, f'the output {name}')
            for name, item in s.outcomes.items()
            if item.expr is not None
        }
        self._groups()
        self._couplings()
        self.checks = tuple(
            Check(
                index,
                name,
                self.check_space(name),
                self.node(item.expr, self.check_space(name), f'the check {name}'),
                item.message,
                item.path,
                thawed(item.expr),
            )
            for index, (name, item) in enumerate(s.state_checks.items())
        )
        # The checks of the inputs, which hold before a run (`input_failures`): each with what the
        # diagnostic of a failure says of it.
        self.input_checks = tuple(
            (
                Check(
                    index,
                    name,
                    self.check_space(name),
                    self.node(item.expr, self.check_space(name), f'the check {name}'),
                    item.message,
                    item.path,
                    thawed(item.expr),
                ),
                item.severity,
                thawed(item.basis),
            )
            for index, (name, item) in enumerate(s.input_checks.items())
        )
        partitions = []
        for name, item in s.partitions.items():
            space = self.check_space(name)
            for part in item.parts:
                if part not in s.quantities:
                    raise Outside(f'the partition {name}: a part that is no quantity')
                if self.space_of(part) != space and space != SCALARS:
                    raise Outside(f'the partition {name}: a part of another family')
            tolerance = item.tolerance
            partitions.append(
                Partition(
                    len(partitions),
                    name,
                    space,
                    self.node(item.total, space, f'the partition {name}'),
                    tuple(item.parts),
                    None if not tolerance else self.node(tolerance, space, f'the partition {name}'),
                    item.path,
                )
            )
        self.partitions = tuple(partitions)
        self._forms()
        self._readers()

    # ---- the spaces -----------------------------------------------------------------------------

    def _spaces(self, core):
        spaces = [Space(SCALARS, None, 1)]
        self.space_of_host = {}
        place = {}
        for family in core.families:
            index = len(spaces)
            self.space_of_host[family.host] = index
            for j, host in enumerate(family.hosts):
                place[host] = (index, j)
            spaces.append(Space(index, family.host, len(family), family))
        for space in spaces[1:]:
            for link, targets in space.family.links.items():
                found = [place.get(target) for target in targets]
                if all(item is None for item in found):
                    continue  # a link to a thing outside the tables: one name for the whole class
                others = {item[0] for item in found if item is not None}
                if None in found or len(others) != 1:
                    raise Outside(
                        f'the link {link} of {space.host}, whose rows link into more than one class'
                    )
                other = others.pop()
                to = np.array([item[1] for item in found], dtype=int)
                if other in space.links and not np.array_equal(space.links[other], to):
                    raise Outside(f'two links of {space.host} into one class')
                space.links[other] = to
                back = {}
                for j, k in enumerate(to.tolist()):
                    back.setdefault(k, []).append(j)
                space.linked_from[other] = {k: np.array(rows, dtype=int) for k, rows in back.items()}
        self.spaces = tuple(spaces)

    def space_of(self, name):
        found = self.space_by_name.get(name)
        if found is None:
            found = self.space_by_name[name] = self.space_of_host.get(name.split('.', 1)[0], SCALARS)
        return found

    def check_space(self, name):
        """The space of a check or a partition. The builder names one by the template of its thing and
        its number (`Tank.0`), and by the thing too when the template has more than one instance in
        the model that it lowers (`Tank.0.tanks_3`)."""
        template, _, rest = name.partition('.')
        _, _, host = rest.partition('.')
        if host:
            return self.space_of_host.get(host, SCALARS)
        found = [space for space in self.spaces[1:] if space.family.template == template]
        return found[0].index if len(found) == 1 else SCALARS

    def check_name(self, name, space, j):
        """The name of a check of the instance j of its space, as the flat structure names it."""
        family = self.spaces[space].family
        if family is None:
            return name
        template, _, rest = name.partition('.')
        number, _, host = rest.partition('.')
        return f'{template}.{number}.{family.hosts[j]}' if host or len(family) > 1 else name

    def how(self, reader, name, where):
        """How a part of the space `reader` reads `name`: SAME (the same instance), ALL (one value
        for every instance) or LINK (the instance that its row links to)."""
        other = self.space_of(name)
        if other == reader:
            return SAME
        if self.spaces[other].count == 1:
            return ALL
        if other in self.spaces[reader].links:
            return LINK
        raise Outside(f'{where} reads {name}, a value of a family, outside a list')

    # ---- the names ------------------------------------------------------------------------------

    def _names(self, resolved):
        s, units = self.s, self.units
        self.values = {}  # name -> start value(s): an array over the instances of its space
        for name, parameter in s.parameters.items():
            space = self.spaces[self.space_of(name)]
            member = name.split('.', 1)[1] if '.' in name else name
            if space.family is not None and member in space.family.values:
                column = np.array(space.family.values[member], dtype=float) * units.scale(parameter.unit)
            else:
                column = np.full(space.count, float(resolved.values[name]))
            self.values[name] = column
            self.kind[name] = 'value'
        self.parameter_scale = {name: units.scale(item.unit) for name, item in s.parameters.items()}
        self.modes = {}
        for name, mode in s.modes.items():
            space = self.spaces[self.space_of(name)]
            column = np.empty(space.count, dtype=object)
            column[:] = mode.initial
            self.values[name] = column
            self.values[name + ENTERED] = np.zeros(space.count)
            self.kind[name] = self.kind[name + ENTERED] = 'value'
            self.modes[name] = tuple(mode.values)
        for event in s.events:
            space = self.spaces[self.space_of(event)]
            self.values[event + COUNT] = np.zeros(space.count, dtype=np.int64)
            self.values[event + TIME] = np.zeros(space.count)
            self.kind[event + COUNT] = self.kind[event + TIME] = 'value'
        self.events = frozenset(s.events)
        for name in self._formulas:
            self.kind[name] = 'formula'
        for name in s.quantities:
            self.kind[name] = 'value'  # `_forms` says which ones move, and how

    # ---- the expressions ------------------------------------------------------------------------

    def node(self, source, space, where):
        """An expression of a part of `space` as one node: each list over the instances of a family
        as the name of an aggregate, and each formula in the place of its name. `source` is a node or a
        number; a text is a TypeError, as in the entries of `napkin.expressions`."""
        _no_text(source, where)
        if isinstance(source, (bool, int, float)):
            source = repr(source)
        made = self._inline(self._lists(expr.read(source), space, where))
        for name in expr.names(made):
            if name == 't':
                continue
            if name not in self.kind:
                raise Outside(f'{where} reads {name}')
            self.how(space, name, where)
        return made

    def plain(self, source, space, where):
        """An expression of a part of `space` as the continuous engine reads it: the source
        itself, which names each formula of the space; or, where the source has a list over a family
        or names a formula of another space, its node with the name of the aggregate in the place
        of the list and that formula in the place of its name."""
        if isinstance(source, (bool, int, float)):
            return source
        _no_text(source, where)
        node = expr.read(source)

        def change(part):
            if (
                isinstance(part, expr.Ref)
                and self.kind.get(part.name) == 'formula'
                and self.space_of(part.name) != space
            ):
                return self._formula(part.name)
            return _children_changed(part, change)

        made = change(self._lists(node, space, where))
        for name in expr.names(made):
            if name != 't' and name not in self.kind:
                raise Outside(f'{where} reads {name}')
        return made

    def _lists(self, node, space, where):
        """`node` with each list that names a family as the name of its aggregate."""

        def change(part):
            part = _children_changed(part, change)
            if not (isinstance(part, expr.Call) and part.function in LISTS):
                return part
            terms = []
            for arg in part.args:
                found = {self.space_of(name) for name in expr.names(arg)} - {SCALARS}
                if len(found) > 1:
                    raise Outside(f'{where}: a member of a list that names two families')
                terms.append(Term(found.pop() if found else SCALARS, arg))
            if all(term.space == SCALARS for term in terms):
                return part
            if space != SCALARS:
                raise Outside(f'{where}: a list in a part of a family')
            return expr.ref(self._aggregate(part.function, terms, where))

        return change(node)

    def _aggregate(self, function, terms, where):
        terms = tuple(Term(term.space, self._inline(term.node)) for term in terms)
        key = (function, terms)
        for name, found in self.aggregates.items():
            if (found.function, found.terms) == key:
                return name
        name = f'__list{len(self.aggregates)}'
        for term in terms:
            for read in expr.names(term.node):
                if read != 't' and read not in self.kind:
                    raise Outside(f'{where} reads {read}')
                if read != 't':
                    self.how(term.space, read, where)
        # Whether it moves is known when the forms of the quantities are (`_forms`).
        self.aggregates[name] = Aggregate(name, function, terms, False)
        self.kind[name] = 'aggregate'
        return name

    def _inline(self, node):
        """`node` with each formula in the place of its name."""
        found = self._inlined.get(node)
        if found is not None:
            return found

        def change(part):
            if isinstance(part, expr.Ref) and self.kind.get(part.name) == 'formula':
                return self._formula(part.name)
            return _children_changed(part, change)

        made = self._inlined[node] = change(node)
        return made

    def _formula(self, name):
        found = self._listed_formulas.get(name)
        if found is None:
            if name in self._formulas and self._formulas[name] is None:
                raise Outside(f'the formula {name} reads itself')
            source, self._formulas[name] = self._formulas[name], None
            listed = self._lists(expr.read(source), self.space_of(name), f'the formula {name}')
            found = self._listed_formulas[name] = self._inline(listed)
            self._formulas[name] = source
        return found

    # ---- the quantities -------------------------------------------------------------------------

    def _quantities(self):
        s, units = self.s, self.units
        # The parts of each rate: (sign, node, whether it is a flow), and the flow of each part.
        self.parts = {name: [] for name in s.quantities}
        self.part_flows = {name: [] for name in s.quantities}
        for name, item in s.rates.items():
            space = self.space_of(name)
            self.parts[name].append((1.0, self.node(item.expr, space, f'the rate of {name}'), False))
            self.part_flows[name].append(None)
        self.flows, self.flow_source = {}, {}
        for key, flow in s.flows.items():
            space = self.space_of(key)
            node = self.node(flow.rate, space, f'the flow {key}')
            self.flows[key] = node
            if flow.source is not None:
                self.flow_source[key] = flow.source
            for target, sign in ((flow.target, 1.0), (flow.source, -1.0)):
                if target is None:
                    continue
                if self.space_of(target) != space:
                    raise Outside(f'the flow {key}, which joins two spaces')
                self.parts[target].append((sign, node, True))
                self.part_flows[target].append(key)
        self.definitions = {}
        # The inputs that a bound reads (`_bound`): a run that gives one of them a value of its own
        # would have another bound than the plan.
        self.bound_reads = set()
        for name, item in s.quantities.items():
            space = self.space_of(name)
            scale = units.scale(item.unit)
            minimum, maximum = self._bound(name, 'minimum'), self._bound(name, 'maximum')
            lower = (minimum if minimum is not None else 0 if item.kind == 'stock' else -np.inf) * scale
            upper = maximum * scale if maximum is not None else np.inf
            member = name.split('.', 1)[1] if '.' in name else name
            family = self.spaces[space].family
            if family is not None and member in family.starts:
                # The start of each row. One node for all rows when they write the same text.
                texts = family.starts[member]
                start = tuple(self.node(text, space, f'the start of {name}') for text in texts)
                start = start[0] if all(item_ is start[0] for item_ in start) else start
            else:
                start = self.node(item.initial, space, f'the start of {name}')
            size = item.size
            self.definitions[name] = dict(
                name=name,
                space=space,
                kind=item.kind,
                start=start,
                scale=scale,
                lower=lower,
                upper=upper,
                size=None if size is None else _number(size) * scale,
                monotone=item.kind == 'cumulative',
            )

    def _bound(self, name, field):
        """A bound of a quantity (its `minimum` or its `maximum`) as a number in the unit of the
        file, or None. A resolved run has each bound as a number. A structure with each list as
        one node keeps the expression that the file writes (`in 0 to cap`): its number is that of
        the resolved run of the plan, whose checks found it from the values of the inputs; and the
        plan keeps the inputs that the expression reads (`bound_reads`). The rows of one class
        have one bound: a bound that reads a column of a table is refused before
        (`analysis/values.py`)."""
        source = getattr(self.s.quantities[name], field)
        if source is None or isinstance(source, (int, float)):
            return source
        found = getattr(self.resolved.quantities.get(name), field, None)
        if not isinstance(found, (int, float)):
            raise Outside(f'the bound of {name}, which is no number in the run of the plan')
        self.bound_reads |= set(expr.names(source))
        return float(found)

    def _groups(self):
        groups = {}
        self.flow_group = {}
        for key, flow in self.s.flows.items():
            if flow.allocation:
                groups.setdefault(flow.allocation, []).append(key)
                self.flow_group[key] = flow.allocation
        self.groups = {}
        for name, item in self.s.allocation.items():
            space = self.space_of(name)
            capacity = item.capacity
            if item.policy not in ('proportional', 'priority'):
                raise Outside(f'the allocation group {name}: the policy {item.policy}')
            self.groups[name] = Group(
                name,
                space,
                None if capacity is None else self.node(capacity, space, f'the limit of {name}'),
                tuple(groups.get(name, ())),
                item.policy,
                tuple(item.order or ()),
            )
            for key in self.groups[name].flows:
                if self.space_of(key) != space:
                    raise Outside(f'the allocation group {name}, whose flows are of two spaces')

    def _couplings(self):
        """{flow: the flows that move by one fraction with it, itself with them}."""
        self.coupled = {}
        # The spaces whose flows need the allocation in full (`engine/allocation.py`): the engine
        # asks it for each instance, where the other spaces have their rates for all instances at once.
        self.general = {
            space
            for space in self.forced
            if any(self.space_of(name) == space for name in self.moving_quantities)
        }
        for name, item in self.s.coupling.items():
            members = tuple(item.flows)
            if any(key in self.flow_group for key in members):
                # A flow of the set is of an allocation group: what the group leaves of a flow that
                # its set cuts goes to the other flows of the group, in passes, and at a bound the
                # answer is that of a linear program.
                self.general.add(self.space_of(name))
                continue
            for key in members:
                if key in self.coupled:
                    raise Outside(
                        f'the flow {key} is of two sets of flows that move by one fraction',
                        space=self.space_of(key),
                    )
                self.coupled[key] = members
        for key in list(self.coupled):
            if self.space_of(key) in self.general:
                del self.coupled[key]

    def rate_nodes(self, name, seen=frozenset()):
        """The nodes that the rate of a quantity reads: each of its parts, and, for a flow of a group
        with a limit, each flow of the group and the limit, which decide what the flow delivers."""
        space = self.space_of(name)
        if space in self.general:
            # The allocation in full gives the rates of all quantities of the space together: each
            # reads what any flow, limit or rate of the space reads.
            found = [node for key, node in self.flows.items() if self.space_of(key) == space]
            found += [
                group.capacity
                for group in self.groups.values()
                if group.space == space and group.capacity is not None
            ]
            found += [
                node
                for other, parts in self.parts.items()
                if self.space_of(other) == space
                for (_, node, _), key in zip(parts, self.part_flows[other])
                if key is None
            ]
            return list(dict.fromkeys(found))
        found = []
        floors = getattr(self, 'floors', {})
        for (_, node, _), key in zip(self.parts[name], self.part_flows[name]):
            found.append(node)
            group = self.groups.get(self.flow_group.get(key)) if key is not None else None
            if group is not None and group.capacity is not None:
                found += [self.flows[other] for other in group.flows] + [group.capacity]
            # The flows that move by one fraction with it: what cuts one of them cuts it.
            for member in self.coupled.get(key, (key,)):
                if member != key:
                    found.append(self.flows[member])
                floor = floors.get(self.flow_source.get(member))
                if floor is not None:
                    # What a flow delivers while its source rests on its bound: what comes into the
                    # source, shared among the flows out of it.
                    found.append(expr.ref(floor.flag))
                    found += [self.flows[other] for other in floor.outflows]
                    if floor.name != name and floor.name not in seen:
                        found += self.rate_nodes(floor.name, seen | {name})
        return list(dict.fromkeys(found))

    def _floors(self):
        """The quantities on a line that can rest on their lower bound: each has a flow out of it."""
        floors = {}
        for name, quantity in self.quantities.items():
            if quantity.form != 'line' or not np.isfinite(quantity.lower) or quantity.space in self.general:
                continue
            parts = list(zip(self.parts[name], self.part_flows[name]))
            outflows = tuple(key for (sign, _, _), key in parts if key is not None and sign < 0)
            if not outflows:
                continue
            groups = {self.flow_group.get(key) for key in outflows}
            if len(outflows) > 1 and (None in groups or len(groups) > 1):
                raise Outside(
                    f'the flows out of {name}, which do not share one allocation group', space=quantity.space
                )
            flag = f'{name}__rests'
            floors[name] = Floor(
                name,
                flag,
                tuple(key for (sign, _, _), key in parts if key is not None and sign > 0),
                tuple(node for (_, node, _), key in parts if key is None),
                outflows,
                groups.pop(),
            )
            self.values[flag] = np.zeros(self.spaces[quantity.space].count, dtype=bool)
            self.kind[flag] = 'value'
        # A stock that rests gets what comes in from the stocks before it: the order of a chain is
        # the order of the reading. A ring of such stocks has no such order.
        seen = {}

        def visit(name, path):
            if name in path:
                raise Outside(
                    f'a ring of flows between quantities that can rest on a bound ({name})',
                    space=self.space_of(name),
                )
            if name in seen:
                return
            seen[name] = True
            for key in floors[name].inflows:
                source = self.flow_source.get(key)
                if source in floors:
                    visit(source, (*path, name))

        for name in floors:
            visit(name, ())
        self.floors = floors
        self.floor_of_group = {floor.group: floor for floor in floors.values() if floor.group is not None}
        self._nets()

    def _nets(self):
        """The network of each space whose flows need the allocation in full: what the continuous
        engine reads of a system (`component.Network`)."""
        s = self.s
        proven = set(self.resolved.proven_zero_stock_faces or ())
        crossings = {
            self.rule_index[name]
            for name in self.resolved.proven_monotone_crossings or ()
            if name in self.rule_index
        }
        self.nets = {}
        for space in sorted(self.general):
            names = tuple(name for name, quantity in self.quantities.items() if quantity.space == space)
            own = set(names)
            flows = {}
            for key, flow in s.flows.items():
                if self.space_of(key) != space:
                    continue
                for end in (flow.source, flow.target):
                    if end is not None and end not in own:
                        raise Outside(f'the flow {key}, which joins two spaces', tier=True)
                flows[key] = NetFlow(
                    self.plain(flow.rate, space, f'the flow {key}'),
                    flow.source,
                    flow.target,
                    flow.allocation,
                )
            rates = {
                name: NetRate(self.plain(item.expr, space, f'the rate of {name}'))
                for name, item in s.rates.items()
                if name in own
            }
            groups = {
                name: NetGroup(
                    group.policy,
                    group.order,
                    self.plain(s.allocation[name].capacity, space, f'the limit of {name}'),
                )
                for name, group in self.groups.items()
                if group.space == space
            }
            couplings = {
                name: NetCoupling(tuple(item.flows))
                for name, item in s.coupling.items()
                if self.space_of(name) == space
            }
            # The formulas of the space that these expressions read, by any path, under their names.
            computed, pending = {}, [flow.rate for flow in flows.values()]
            pending += [rate.expr for rate in rates.values()] + [group.capacity for group in groups.values()]
            leaves = set()
            while pending:
                source = pending.pop()
                if isinstance(source, (bool, int, float)):
                    continue
                for name in expr.names(expr.read(source)):
                    if self.kind.get(name) != 'formula':
                        leaves.add(name)
                    elif name not in computed:
                        computed[name] = {
                            'expr': self.plain(self._formulas[name], space, f'the formula {name}')
                        }
                        pending.append(computed[name]['expr'])
            leaves -= own | {'t'}

            def moves(name):
                return self.kind[name] in ('line', 'numeric') or (
                    self.kind[name] == 'aggregate' and self.aggregates[name].moving
                )

            for name in sorted(leaves):
                if moves(name):
                    raise Outside(
                        f'{names[0]}: a thing that needs the allocation in full, whose rates read {name}, '
                        'which moves outside it',
                        tier=True,
                    )
            # The checks of the state and the partitions that a space of one instance reads itself:
            # each one of the space that reads nothing that moves outside it. The names are those
            # of the one instance, so a failure has the names of the model.
            checks, sums, local = {}, {}, set()
            if self.spaces[space].count == 1:

                def reads(sources, what):
                    """The texts of some expressions of a check as the network reads them, with
                    the formulas and the other names that they read; None when one of them reads
                    a value that moves outside the space or that the network cannot read."""
                    texts, formulas, others = [], {}, set()
                    try:
                        for source in sources:
                            texts.append(None if source is None else self.plain(source, space, what))
                        pending = [text for text in texts if text is not None]
                        while pending:
                            source = pending.pop()
                            if isinstance(source, (bool, int, float)):
                                continue
                            for name in expr.names(expr.read(source)):
                                if self.kind.get(name) != 'formula':
                                    others.add(name)
                                elif name not in computed and name not in formulas:
                                    text = self.plain(self._formulas[name], space, f'the formula {name}')
                                    formulas[name] = {'expr': text}
                                    pending.append(text)
                    except Outside:
                        return None
                    others -= own | {'t'}
                    if any(name not in self.kind or moves(name) for name in others):
                        return None
                    return texts, formulas, others

                for check in self.checks:
                    found = check.space == space and reads(
                        [s.state_checks[check.name].expr], f'the check {check.name}'
                    )
                    if found:
                        (text,), formulas, others = found
                        checks[check.name] = NetCheck(text, check.path, check.message)
                        computed.update(formulas)
                        leaves |= others
                        local.add(('check', check.index))
                for partition in self.partitions:
                    item = s.partitions[partition.name]
                    found = (
                        partition.space == space
                        and all(part in own for part in partition.parts)
                        and reads([item.total, item.tolerance or None], f'the partition {partition.name}')
                    )
                    if found:
                        (total, tolerance), formulas, others = found
                        sums[partition.name] = NetSum(total, partition.parts, tolerance, partition.path)
                        computed.update(formulas)
                        leaves |= others
                        local.add(('partition', partition.index))
            # In the order of the model.
            computed = {name: computed[name] for name in self._formulas if name in computed}
            block = {name for name in names if self.quantities[name].form == 'numeric'}
            parameters = tuple(name for name in sorted(leaves) if name in s.parameters)
            self.nets[space] = Network(
                space,
                names,
                {name: self.quantities[name].kind for name in names},
                [self.quantities[name].lower for name in names],
                [self.quantities[name].upper for name in names],
                flows,
                rates,
                groups,
                couplings,
                computed,
                block,
                parameters,
                leaves - set(parameters),
                proven,
                crossings,
                checks,
                sums,
                local,
            )

    # ---- the rules ------------------------------------------------------------------------------

    def _rules(self):
        s = self.s
        moving = self.moving_quantities | {'t'}
        # The checks of a structure give each trigger its class (`Rule.trigger`). A structure that
        # they have not read (one with each list as one node, or a run that a caller made by hand)
        # has none: the classifier of the compiler gives it, from the typed parts.
        discrete = None
        if any(rule.trigger.kind is None for rule in s.rules.values()):
            discrete = analysis.discrete_names(s)
        rules = []
        for name, rule in s.rules.items():
            where = f'the event {name}'
            space = self.space_of(name)
            # The names of the values that the rule draws or reads of the past: its other
            # expressions read them, and a firing gives them their values.
            for item in rule.extras or ():
                self.kind[item.name] = 'extra'
            trigger = rule.trigger
            if trigger.kind is None:
                try:
                    trigger = analysis.classify(rule, s, discrete, moving)
                except ValueError as problem:
                    raise Outside(f'{where}: {problem}') from problem

            def node(source, what='its condition', space=space, where=where):
                return self.node(source, space, f'{what} of {where}')

            outcomes = []
            for outcome in rule.outcomes:
                step = outcome.do
                sets = []
                for target, value in step.set.items():
                    if value.mode is not None:
                        sets.append((target, None, value.mode))
                    else:
                        sets.append((target, node(value.expr, 'a step'), None))
                chance = outcome.chance
                outcomes.append(
                    Outcome(
                        outcome.name,
                        chance if chance in (None, 'else') else node(chance, 'a chance'),
                        tuple(sets),
                        tuple((m.source, m.target, node(m.amount, 'a step')) for m in step.transfer),
                        tuple(step.fire),
                        tuple(outcome.emits),
                        None
                        if outcome.available is None
                        else node(outcome.available, 'the condition of an outcome'),
                        outcome.label,
                        outcome.path,
                        thawed(outcome.basis),
                    )
                )
            # The start has a rank of its own, shorter than that of an event: it goes before each rank
            # that begins as it does, as a shorter tuple does.
            rank = (*(rule.rank or ()), -1, -1, -1)[:3]
            rules.append(
                Rule(
                    index=len(rules),
                    name=name,
                    space=space,
                    line=rank[0],
                    once=bool(rule.once),
                    named=bool(rule.named),
                    kind=trigger.kind,
                    gate=node(True if trigger.gate is None else trigger.gate),
                    times=tuple(node(time) for time in trigger.times or ()),
                    var=trigger.var,
                    rising=trigger.op == '>=',
                    value=None if trigger.value is None else node(trigger.value),
                    when=node(trigger.when),
                    delay=None if rule.delay is None else node(rule.delay, 'the delay'),
                    outcomes=tuple(outcomes),
                    emits=tuple(rule.emits),
                    keep=None if rule.keep is None else node(rule.keep, 'the `while`'),
                    each=tuple(node(item, 'the window') for item in rule.each or ()),
                    extras=tuple(
                        Extra(
                            item.name,
                            item.kind,
                            item.stage,
                            None if item.expr is None else node(item.expr, 'a value of the past'),
                            None if item.delay is None else node(item.delay, 'a value of the past'),
                            item.family,
                            tuple((arg, node(source, 'a draw')) for arg, source in (item.args or {}).items()),
                        )
                        for item in rule.extras or ()
                    ),
                    entity=rule.entity or '',
                    label=rule.label,
                    path=rule.path,
                    basis=thawed(rule.basis),
                    choice=bool(rule.choice),
                    delay_path=rule.delay_path,
                )
            )
        self.rules = tuple(rules)
        # What the actor of each thing sees at a decision.
        self.sees = {}
        for entity, item in s.entities.items():
            facts = []
            for fact in item.sees or ():
                found = None
                if fact.event is None:
                    found = self.node(fact.expr, self.space_of(fact.name), f'what {entity} sees')
                facts.append(
                    Fact(
                        fact.name,
                        fact.event,
                        found,
                        fact.kind,
                        tuple(fact.values or ()),
                        fact.unit,
                    )
                )
            self.sees[entity] = tuple(facts)
        self.rule_index = {rule.name: rule.index for rule in rules}
        # The rules that watch a crossing of each quantity.
        self.crossings = {}
        for rule in rules:
            if rule.kind == 'crossing':
                self.crossings.setdefault(rule.var, []).append(rule.index)
        # A value of the past needs the record of the run.
        self.records = any(extra.kind == 'delayed' for rule in rules for extra in rule.extras)

    # ---- what moves, and how --------------------------------------------------------------------

    def reads(self, node):
        """The names that a node reads, through the members of the aggregates that it reads."""
        found = set()
        for name in expr.names(node):
            found.add(name)
            if self.kind.get(name) == 'aggregate':
                for term in self.aggregates[name].terms:
                    found |= self.reads(term.node)
        return found

    def _forms(self):
        moving = set(self.moving_quantities)
        # A line reads nothing that moves; the others are numeric. A quantity that reads a numeric
        # one is numeric, and a line that a numeric one reads stays a line.
        # In a space of the general tier every quantity has the rate nodes of the whole space, so
        # what they read is found once for the space.
        of_space = {}

        def reads_of(name):
            space = self.space_of(name)
            found = of_space.get(space) if space in self.general else None
            if found is None:
                found = set().union(*(self.reads(node) for node in self.rate_nodes(name)))
                if space in self.general:
                    of_space[space] = found
            return found

        rate_reads = {name: reads_of(name) for name in moving}
        numeric = {name for name in moving if rate_reads[name] & (moving | {'t'})}
        # A space whose flows need the allocation in full is one block: the continuous engine runs
        # its quantities together, and says in each segment which of them move, and how.
        numeric |= {name for name in moving if self.space_of(name) in self.general}
        lines = moving - numeric
        # The blocks: the numeric quantities that read one another, by any path.
        parent = {name: name for name in numeric}

        def root(name):
            while parent[name] != name:
                parent[name] = parent[parent[name]]
                name = parent[name]
            return name

        for name in numeric:
            for other in rate_reads[name] & numeric:
                parent[root(name)] = root(other)
        first = {}
        for name in self.s.quantities:
            space = self.space_of(name)
            if name in numeric and space in self.general:
                parent[root(name)] = root(first.setdefault(space, name))
        members = {}
        for name in self.s.quantities:
            if name in numeric:
                members.setdefault(root(name), []).append(name)
        blocks = []
        block_of = {}
        for names in members.values():
            spaces = {self.space_of(name) for name in names}
            whole = len(spaces) > 1
            checked = set()
            for name in names:
                space = self.space_of(name)
                if space in self.general:
                    # The quantities of such a space have the same rate nodes: one of them is read.
                    if space in checked:
                        continue
                    checked.add(space)
                for node in self.rate_nodes(name):
                    for read in expr.names(node):
                        if read in numeric and self.space_of(read) != space:
                            whole = True
                        if self.kind.get(read) == 'aggregate' and self.reads(expr.ref(read)) & numeric:
                            whole = True
            net = min(spaces) in self.general
            if net and (whole or len(spaces) > 1):
                raise Outside(
                    f'{names[0]}: flows that move by one fraction and share a limit, in a thing whose rates '
                    'read another instance or another family',
                    tier=True,
                )
            block = Block(
                len(blocks),
                tuple(names),
                min(spaces),
                whole,
                not net and self._linear(names, moving | {'t'}),
                net,
            )
            blocks.append(block)
            for name in names:
                block_of[name] = block.index
        self.blocks = tuple(blocks)
        # The groups with a limit whose flows are parts of the rates of each block.
        self.block_groups = {
            block.index: tuple(
                dict.fromkeys(
                    self.groups[self.flow_group[key]]
                    for name in block.names
                    for key in self.part_flows[name]
                    if key in self.flow_group and self.groups[self.flow_group[key]].capacity is not None
                )
            )
            for block in blocks
        }
        self.quantities = {}
        for name, item in self.definitions.items():
            form = 'numeric' if name in numeric else 'line' if name in lines else 'value'
            self.quantities[name] = Quantity(form=form, block=block_of.get(name), **item)
            self.kind[name] = form
        moves = moving | {'t'}
        for name, found in list(self.aggregates.items()):
            if any(self.reads(term.node) & moves for term in found.terms):
                self.aggregates[name] = Aggregate(found.name, found.function, found.terms, True)
        self.moving = frozenset(moves | {name for name, found in self.aggregates.items() if found.moving})
        self._floors()
        for rule in self.rules:
            if rule.kind == 'crossing' and self.kind[rule.var] not in ('line', 'numeric'):
                raise Outside(f'the event {rule.name}: a crossing of a value that does not move')
            for node in (rule.gate, *rule.times, rule.value, rule.keep, *rule.each):
                if node is not None and self.reads(node) & (self.moving - {'t'}):
                    raise Outside(f'the event {rule.name}: a condition on values that move between moments')
            if rule.kind == 'discrete' and self.reads(rule.when) & self.moving:
                raise Outside(f'the event {rule.name}: a condition on values that move between moments')
            if rule.kind != 'face':
                continue
            # A condition on stocks at zero can change only where a segment of the block of the
            # stocks ends. The general tier reads the rules of a block there (`Run.ends`).
            where = f'the event {rule.name}: a condition on stocks at zero'
            for name in sorted(self.reads(rule.when) & (self.moving - {'t'})):
                space = self.space_of(name)
                if name not in expr.names(rule.when) or self.kind[name] == 'aggregate':
                    raise Outside(f'{where}, which reads a list')
                if space not in self.general:
                    raise Outside(f'{where}, in the fast tier', space=space)

    def _linear(self, names, moving):
        """Whether the rates of a block are linear in its quantities with constant factors: each
        rate reads nothing that moves but the quantities of the block, and its derivative by each of
        them reads nothing that moves at all. A rate with a choice, a least or a greatest on a
        quantity of the block has a derivative that reads the quantity, so it is not linear here."""
        own = set(names)
        for name in names:
            for node in self.rate_nodes(name):
                if (self.reads(node) & moving) - own:
                    return False
                for other in names:
                    if self.reads(derivative(node, other)) & moving:
                        return False
        return True

    # ---- the readers ----------------------------------------------------------------------------

    def _readers(self):
        """{name: the parts that read it}. A part is ('rule', index), ('line', name), ('block', index)
        or ('term', aggregate, place of the member); with it, how it reads the name."""
        readers = {}

        def add(name, reader, space, where, how=None):
            if name == 't':
                return
            entry = (*reader, how or self.how(space, name, where))
            found = readers.setdefault(name, [])
            if entry not in found:
                found.append(entry)

        for rule in self.rules:
            names = set()
            for node in (rule.gate, *rule.times, rule.value, rule.when, rule.keep, *rule.each):
                if node is not None:
                    names |= expr.names(node)
            if rule.var:
                names.add(rule.var)
            for name in names:
                add(name, ('rule', rule.index), rule.space, rule.name)
        nets = set()
        for name, quantity in self.quantities.items():
            if quantity.form == 'value':
                continue
            reader = ('line', name) if quantity.form == 'line' else ('block', quantity.block)
            own = set(self.blocks[quantity.block].names) if quantity.form == 'numeric' else set()
            if quantity.form == 'numeric' and self.blocks[quantity.block].net:
                # The block of a space of the general tier reads the rate nodes of the space, which
                # each of its quantities has: they are read once for the block.
                if quantity.block in nets:
                    continue
                nets.add(quantity.block)
            for node in self.rate_nodes(name):
                direct = expr.names(node)
                for read in direct - own:
                    add(read, reader, quantity.space, name)
                # What it reads through a list that moves: every instance of the member, and the
                # list keeps no value of its own that a step could bring up to date.
                for read in self.reads(node) - direct - own:
                    add(read, reader, quantity.space, name, ALL)
        for name, found in self.aggregates.items():
            if found.moving:
                continue
            for place, term in enumerate(found.terms):
                for read in expr.names(term.node):
                    add(read, ('term', name, place), term.space, name)
        # A check and a partition are read again when a step writes what they read, or changes the
        # path of a quantity that they read; a name that they read through a list is of every instance.
        for check in self.checks:
            direct = expr.names(check.node)
            for read in self.reads(check.node):
                add(read, ('check', check.index), check.space, check.name, None if read in direct else ALL)
        for partition in self.partitions:
            nodes = [partition.total, *([partition.tolerance] if partition.tolerance is not None else [])]
            direct = set().union(*(expr.names(node) for node in nodes))
            for read in set().union(*(self.reads(node) for node in nodes)):
                add(
                    read,
                    ('partition', partition.index),
                    partition.space,
                    partition.name,
                    None if read in direct else ALL,
                )
            for part in partition.parts:
                how = SAME if self.space_of(part) == partition.space else ALL
                add(part, ('partition', partition.index), partition.space, partition.name, how)
        self.readers = {name: tuple(found) for name, found in readers.items()}
