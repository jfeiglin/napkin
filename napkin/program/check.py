"""The checker: the invariants of a program that an engine relies on, each refused with a code.

`check(program)` gives the diagnostics of a program in the order in which it meets them; a program
with none can run. `build.Builder.finish` runs it and raises `ProgramError` with them. Each
diagnostic has a code, the origin of the part that breaks the rule, and a message that names it.
`reports(program)` gives the setup's reports, which refuse nothing: equal keys in a keyed view that
`.at(...)` reads (`equal_keys`), and a lookup below the first key at a known lower bound
(`below_first_key`).

The resolver (`Resolver.resolve`) gives what a path names (`Found`) in the scope of the part that
holds it: the receiver's template, an event's parameters and locals, a trigger's captures, a
solver's inputs and unknowns, the member of a `where`. It resolves each step by what precedes it,
never by the spelling of a name, so it serves the engine and the oracle as it serves the checker.

The codes:

- `unknown_name`: a path, a member's value, a link or a start that names nothing in its scope.
- `unbound_symbol`: a name of a node with no read, or a read with no name in the node.
- `none_value`: a constant None; the language has no `none` (D4).
- `duplicate_name`: two templates, enums, members, or parts of one scope with one name.
- `unknown_unit`: a unit spelling that is not in the program's table.
- `kind`: a record whose kind and contents disagree (a formula without a `Formula`, a range on a
  yes/no, a flow with legs and ends, a parameter with an initializer, an unknown rating, a reference
  to an occurrence that is no local of an event or starts from no path of an occurrence of its
  event, `parts.OccurrenceType`).
- `link_unset`, `no_value`: a member that leaves a link without a row, or a value with no starting
  value (D4).
- `two_writers`: a value or a rate that a solver determines and a stage, a second solver or a flow
  also writes. A flow's actual rate is the engine's, or one solver's.
- `readonly_write`, `fixed_write`, `result_write`, `assign_value`: an assignment to a readonly
  value; to what is fixed for the run (an input, a link, a flow's end, an event) or once its
  occurrence enters (a reference to an occurrence); to what the run
  computes (an actual rate, a served fraction, a solver's unknown, an occurrence's built-in); or of
  a value of the wrong form (a scalar into a formula, `+=` on a yes/no).
- `flow_end`, `parameter_end`, `route_end`, `flow_units`, `move_end`: a flow's end that is no stored
  number, or `SINK` as a source; a parameter as an end (D13); `SOURCE` or `SINK` at an end of a
  reversible route; ends of two dimensions, or a rate whose unit is not the end's per time; a
  move's end that is no stored number.
- `formula_draws`: a draw in a formula, or in a condition that is read again (a
  trigger, a reset, a gate, a where, a status, an assertion, a solver).
- `trigger_start`: a trigger that does anything but start its own event.
- `local_order`: a plain initializer of an event local, or a plain property of an event's flow,
  that reads a local declared below it (D14).
- `solve_for`: an entry that a solver cannot determine.
- `priority_item`: a `priority(...)` item that is not a flow or a leg at that endpoint.
- `enum_member`, `distribution`: a member that is not in its enum; a distribution with an unknown
  family or the wrong parameters.
- `collection`, `duplicate_literal`, `where_live`: one thing where a collection is needed or the
  reverse; a member twice in a literal; a `where` that tests a member's live state.
- `status_fallback`: a status display whose last case is not its one unconditional case; and
  `duplicate_name` for a template with a display and a part named `status`, which the record of a
  member's display takes (`member.status`).
- `arguments`: a start with another number of arguments than its event has parameters.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from ..core import expr as nodes
from . import parts as p
from .refs import (
    FAMILIES,
    ITEM,
    REDUCTIONS,
    THIS,
    By,
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

ROOT_OWNER = ''  # the owner key of the root's values


def _silent(code, part, message):
    """The refusals of a resolver that only looks."""


@dataclass(frozen=True)
class Diagnostic:
    """A refusal: its code, the origin of the part, and a message that names the part."""

    code: str
    part: str
    message: str


class ProgramError(ValueError):
    """A program that breaks an invariant; `diagnostics` has each refusal."""

    def __init__(self, diagnostics):
        self.diagnostics = tuple(diagnostics)
        super().__init__('\n'.join(f'{d.code} at {d.part}: {d.message}' for d in self.diagnostics))


@dataclass(frozen=True)
class Found:
    """What a path names. `kind` is `member` (a member of the template `part`), `root`, `value`,
    `flow` (`part` None for any flow of an endpoint's `flows`), `leg` (`forward` or `backward` of
    the route `part`), `endpoint` (`name` is `outflow` or `inflow` of the value `part`), `event`,
    `occurrence` (of the event `part`), `solver`, `unknown` or `property` (`name` of `of`). `owner`
    is the template, event, trigger or solver that declares `part`, or ROOT_OWNER. `many` says that
    it is a collection, or a projection over one."""

    kind: str
    part: Any = None
    owner: Any = ROOT_OWNER
    many: bool = False
    name: str = ''
    of: Found | None = None


@dataclass(frozen=True)
class Scope:
    """Where an expression is: the receiver's template, and the event, trigger or solver whose bare
    names it reads, and what `ITEM` names inside a `where`."""

    template: p.Template | None = None
    event: p.Event | None = None
    trigger: p.Trigger | None = None
    solver: p.Solver | None = None
    item: Found | None = None


def owner_key(owner):
    """The name of the scope that declares a part: a template's name, or the origin of an event, a
    trigger or a solver, or ROOT_OWNER."""
    if isinstance(owner, p.Template):
        return owner.name
    return owner if isinstance(owner, str) else owner.origin


def entity_template(value_type):
    """The template that a link, an entity parameter or a collection value names, or None."""
    if isinstance(value_type, (p.EntityType, p.CollectionType)):
        return value_type.template
    return None


FLOW_PROPERTIES = ('actual_rate', 'request', 'capacity', 'source', 'sink')
ROUTE_PROPERTIES = ('actual_rate', 'request', 'capacity')
LEG_VIEW_PROPERTIES = ('actual_rate', 'request', 'source', 'sink')
ENDPOINT_PROPERTIES = ('actual_rate', 'capacity', 'request', 'allocation')
FIXED_PROPERTIES = ('source', 'sink')
SETTABLE_PROPERTIES = ('request', 'capacity', 'allocation')


class Resolver:
    """Resolves paths of one program. `fail(code, part, message)` takes each refusal; with none, the
    resolver only looks."""

    def __init__(self, program, fail=None):
        self.program = program
        self.fail = fail or _silent
        self._quiet = None
        self.templates = {template.name: template for template in program.templates}
        self.members = {}
        for template in program.templates:
            for member in template.members:
                self.members.setdefault(member.id, template)

    def quiet(self):
        """A resolver of the same program that refuses nothing: for a second look at a path."""
        if self._quiet is None:
            self._quiet = self if self.fail is _silent else Resolver(self.program, _silent)
        return self._quiet

    def resolve(self, path, scope, where, retained=None):
        """What a path names in a scope, or None after a diagnostic. `retained` names the place of a
        condition that is read again, where no draw may be."""
        found = self.start(path.start, scope, where, retained)
        for step in path.steps:
            if found is None:
                return None
            following = self.step(found, step)
            if following is None:
                self.fail('unknown_name', where, f'`{spelled(path)}`: {step!r} names nothing')
            found = following
        return found

    def start(self, start, scope, where, retained):
        if isinstance(start, This):
            if scope.template is None:
                self.fail('unknown_name', where, '`this` has no receiver here')
                return None
            return Found('member', scope.template)
        if isinstance(start, Root):
            return Found('root')
        if isinstance(start, Item):
            if scope.item is None:
                self.fail('unknown_name', where, 'a member of a where is read outside a where')
            return scope.item
        if isinstance(start, Named):
            template = self.members.get(start.id)
            if template is None:
                self.fail('unknown_name', where, f'no member has the id {start.id!r}')
                return None
            return Found('member', template)
        if isinstance(start, Local):
            return self.local(start.name, scope, where)
        if isinstance(start, Instances):
            template = self.templates.get(start.template)
            if template is None:
                self.fail('unknown_name', where, f'no template {start.template!r}')
                return None
            return Found('member', template, many=True)
        if isinstance(start, Literal):
            return self.literal(start, scope, where, retained)
        source = self.collection(start.source, scope, where, retained)
        if source is None:
            return None
        if isinstance(start, Where):
            item = dataclasses.replace(source, many=False)
            inner = dataclasses.replace(scope, item=item)
            self.check_expr(start.test, inner, where, retained or 'a where test')
            self.fixed_test(start.test, inner, where)
            return source
        if isinstance(start, By):
            if self.step(dataclasses.replace(source, many=False), start.key) is None:
                self.fail('unknown_name', where, f'`by({start.key})`: no such field of a member')
            return source
        if isinstance(start, Lookup):
            self.check_expr(start.key, scope, where, retained)
            return dataclasses.replace(source, many=False)
        raise TypeError(f'no start: {type(start).__name__}')

    def collection(self, path, scope, where, retained):
        """What a path names, which must be a collection: a collection or a projection over one, or
        a value that holds a collection (`this.pumps`), which names its members."""
        found = self.resolve(path, scope, where, retained)
        if found is None or found.many:
            return found
        if found.kind == 'value' and isinstance(found.part.type, p.CollectionType):
            return Found('member', self.templates.get(found.part.type.template), many=True)
        self.fail('collection', where, f'`{spelled(path)}` is no collection')
        return None

    def literal(self, literal, scope, where, retained):
        templates = set()
        for item in literal.items:
            found = self.resolve(item, scope, where, retained)
            if found is not None and found.kind == 'value' and isinstance(found.part.type, p.EntityType):
                found = Found('member', self.templates.get(found.part.type.template))
            if found is None or found.kind != 'member' or found.many:
                if found is not None:
                    self.fail('collection', where, f'`{spelled(item)}` in a literal is no member')
                continue
            templates.add(found.part.name)
        if len(set(literal.items)) < len(literal.items):
            self.fail('duplicate_literal', where, 'a literal names a member twice')
        if len(templates) > 1:
            self.fail('collection', where, f'a literal of two templates: {", ".join(sorted(templates))}')
        if not templates:
            return Found('member', None, many=True)
        return Found('member', self.templates[templates.pop()], many=True)

    def local(self, name, scope, where):
        """A bare name: an input or an unknown of the solver, a capture of the trigger, or a
        parameter, a local or a flow of the event."""
        if scope.solver is not None:
            for binding in scope.solver.inputs:
                if binding.name == name:
                    # The solver's own check refuses a broken source once, at its binding.
                    return self.quiet().resolve(binding.source, Scope(scope.template), where)
            for unknown in scope.solver.unknowns:
                if unknown.name == name:
                    return Found('unknown', unknown, scope.solver)
        if scope.trigger is not None:
            for capture in scope.trigger.captures:
                if capture.name == name:
                    return Found('value', capture, scope.trigger)
        if scope.event is not None:
            for part in (*scope.event.params, *scope.event.locals):
                if part.name == name:
                    return Found('value' if isinstance(part, p.Value) else 'flow', part, scope.event)
        self.fail('unknown_name', where, f'no bare name {name!r} in this scope')
        return None

    def step(self, found, name):
        """What a step from what a path has named so far names, or None."""
        kind, many = found.kind, found.many
        if kind == 'root':
            value = self.program.root_value(name)
            return None if value is None else Found('value', value, ROOT_OWNER)
        if kind == 'member':
            part = found.part.part(name) if found.part is not None else None
            if isinstance(part, p.Value):
                return Found('value', part, found.part, many)
            if isinstance(part, p.Flow):
                return Found('flow', part, found.part, many)
            if isinstance(part, p.Event):
                return Found('event', part, found.part, many)
            if isinstance(part, p.Solver):
                return Found('solver', part, found.part, many)
            return None
        if kind == 'value':
            value = found.part
            if isinstance(value.type, p.OccurrenceType):
                event = self.occurrence_event(value.type)
                return (
                    None if event is None else self.step(Found('occurrence', event[1], event[0], many), name)
                )
            target = entity_template(value.type)
            if target is not None:
                collection = isinstance(value.type, p.CollectionType)
                member = Found('member', self.templates.get(target), many=many or collection)
                return self.step(member, name)
            if isinstance(value.type, p.Number):
                if name in ('outflow', 'inflow'):
                    return Found('endpoint', value, found.owner, many, name)
                if name in ('lower', 'upper') and getattr(value, name) is not None:
                    return Found('property', many=many, name=name, of=found)
            if isinstance(value.type, p.DistributionType) and name in ('mean', 'std'):
                return Found('property', many=many, name=name, of=found)
            return None
        if kind == 'endpoint':
            if name == 'flows':
                return Found('flow', None, found.owner, True, of=found)
            if name in ENDPOINT_PROPERTIES:
                return Found('property', many=many, name=name, of=found)
            return None
        if kind == 'flow':
            flow = found.part
            if flow is None or flow.kind == p.DIRECTED:
                names = FLOW_PROPERTIES
            elif flow.kind == p.REVERSIBLE:
                if name in ('forward', 'backward'):
                    return Found('leg', flow, found.owner, many, name)
                names = ROUTE_PROPERTIES
            else:
                for leg in flow.legs:
                    if leg.name == name:
                        return Found('flow', leg, found.owner, many, of=found)
                names = ('served_fraction',)
            return Found('property', many=many, name=name, of=found) if name in names else None
        if kind == 'leg':
            return Found('property', many=many, name=name, of=found) if name in LEG_VIEW_PROPERTIES else None
        if kind == 'event':
            return Found('occurrence', found.part, found.owner, True) if name == 'occurrences' else None
        if kind == 'occurrence':
            for part in (*found.part.params, *found.part.locals):
                if part.name == name:
                    kind = 'value' if isinstance(part, p.Value) else 'flow'
                    return Found(kind, part, found.part, many)
            if name in p.OCCURRENCE_PROPERTIES:
                return Found('property', many=many, name=name, of=found)
            return None
        if kind == 'solver':
            for unknown in found.part.unknowns:
                if unknown.name == name:
                    return Found('unknown', unknown, found.part, many)
            return None
        return None

    def occurrence_event(self, value_type):
        """(template, event) that an `OccurrenceType` names, or None."""
        template = self.templates.get(value_type.template)
        event = template.part(value_type.event) if template is not None else None
        return (template, event) if isinstance(event, p.Event) else None

    def fixed_test(self, test, scope, where):
        """A `where` filters on what is fixed for each member: links, inputs and the ends of flows."""
        for name, read in test.reads:
            if not isinstance(read, Path) or read.start != ITEM:
                continue
            found = self.quiet().resolve(read, scope, where)
            fixed = found is None or found.kind == 'member'
            if found is not None and found.kind == 'value':
                fixed = found.part.kind in (p.INPUT, p.LINK)
            if found is not None and found.kind == 'property':
                fixed = found.name in FIXED_PROPERTIES
            if not fixed:
                self.fail(
                    'where_live', where, f'`{name}` in a where is live state: put a formula on the member'
                )

    def check_expr(self, expression, scope, where, retained=None):
        """Check an expression: its names, its constants, its units and each of its reads."""
        if expression is None:
            return
        if not isinstance(expression, Expr):
            self.fail('kind', where, f'an expression is expected, not {type(expression).__name__}')
            return
        named = {name for name, _ in expression.reads}
        if nodes.names(expression.node) != named:
            loose = sorted(nodes.names(expression.node) ^ named)
            self.fail('unbound_symbol', where, f'names without their reads: {", ".join(loose)}')
        for node in nodes.walk(expression.node):
            if isinstance(node, nodes.Const) and node.value is None:
                self.fail('none_value', where, 'a constant None: the language has no none value')
            if isinstance(node, nodes.Call) and node.function == 'q' and len(node.args) == 2:
                unit = node.args[1]
                if isinstance(unit, nodes.Const) and isinstance(unit.value, str):
                    self.unit(unit.value, where)
        for _, read in expression.reads:
            self.check_read(read, scope, where, retained)

    def check_read(self, read, scope, where, retained):
        if isinstance(read, Time):
            return
        if isinstance(read, Path):
            self.resolve(read, scope, where, retained)
        elif isinstance(read, EnumValue):
            self.enum_member(read.enum, read.member, where)
        elif isinstance(read, Reduce):
            if read.op not in REDUCTIONS:
                self.fail('kind', where, f'no reduction {read.op!r}')
            self.collection(read.source, scope, where, retained)
        elif isinstance(read, Draw):
            if retained:
                self.fail('formula_draws', where, f'{retained} cannot draw: `{spelled(read)}`')
            self.drawn(read.source, scope, where)
        elif isinstance(read, Since):
            found = self.resolve(read.event, scope, where, retained)
            if found is not None and (found.kind != 'event' or found.many):
                self.fail('kind', where, f'`{spelled(read.event)}` is no event')
        elif isinstance(read, Elapsed):
            found = self.resolve(read.value, scope, where, retained)
            if found is not None and found.kind != 'value':
                self.fail('kind', where, f'`{spelled(read.value)}` is no value')
        else:
            self.fail('kind', where, f'no read: {type(read).__name__}')

    def drawn(self, source, scope, where):
        """The source of a draw: a distribution, or a value that holds one."""
        if isinstance(source, Distribution):
            self.distribution(source, where)
            return
        found = self.resolve(source, scope, where)
        if found is not None and not (
            found.kind == 'value' and isinstance(found.part.type, p.DistributionType) and not found.many
        ):
            self.fail('distribution', where, f'`{spelled(source)}` holds no distribution')

    def distribution(self, item, where):
        counts = FAMILIES.get(item.family)
        if counts is None:
            self.fail('distribution', where, f'no family of distributions {item.family!r}')
        elif item.family == 'categorical':
            if not item.outcomes or len(item.outcomes) != len(item.params):
                self.fail('distribution', where, 'a categorical needs one weight for each outcome')
            if any(weight < 0 for weight in item.params) or sum(item.params) <= 0:
                self.fail('distribution', where, 'the weights of a categorical are nonnegative, not all zero')
            for outcome in item.outcomes:
                self.enum_member(item.enum, outcome, where)
        elif len(item.params) not in counts:
            self.fail(
                'distribution', where, f'{item.family} takes {" or ".join(map(str, counts))} parameters'
            )
        if item.family != 'categorical':
            self.unit(item.unit, where)

    def enum_member(self, enum, member, where):
        try:
            members = self.program.enum(enum).members
        except KeyError:
            self.fail('enum_member', where, f'no enum {enum!r}')
            return
        if member not in members:
            self.fail('enum_member', where, f'{member} is not a member of {enum} ({", ".join(members)})')

    def unit(self, name, where):
        try:
            return self.program.unit(name)
        except KeyError:
            self.fail('unknown_unit', where, f'no unit {name!r} in the program')
            return None


class _Checker(Resolver):
    """The checks of `check`, over every part of one program, with the writers of each value."""

    def __init__(self, program):
        self.diagnostics = []
        super().__init__(
            program, lambda code, part, message: self.diagnostics.append(Diagnostic(code, part, message))
        )
        self.solved = {}  # the key of a value or a rate -> the origins of the solvers that set it
        self.assigned = {}  # the key of a value -> the origins of the statements that assign it
        self.ends = {}  # the key of a store -> the origins of the flows and moves that name it

    def run(self):
        program = self.program
        self.unique([u.name for u in program.units], 'units', 'a unit')
        self.unique([e.name for e in program.enums], 'enums', 'an enum')
        self.unique([t.name for t in program.templates], 'templates', 'a template')
        self.unique([m.id for t in program.templates for m in t.members], 'members', 'a member id')
        for unit in program.units:
            if unit.scale <= 0:
                self.fail('unknown_unit', unit.name, f'the unit {unit.name!r} has no positive scale')
        root = Scope()
        self.unique([v.name for v in program.root], 'root', 'a root value')
        for value in program.root:
            self.value(value, root, members=None)
        for template in program.templates:
            self.template(template)
        for statement in program.setup:
            self.statement(statement, root)
        for check in program.asserts:
            self.check_expr(check.test, root, check.origin, 'an assertion')
        self.writers()
        return tuple(self.diagnostics)

    def unique(self, names, where, what):
        twice = sorted(name for name, count in Counter(names).items() if count > 1)
        for name in twice:
            self.fail('duplicate_name', where, f'{what} is declared twice: {name}')

    # ---- templates and their members ---------------------------------------------------------------

    def template(self, template):
        scope = Scope(template)
        names = [
            part.name
            for group in (template.values, template.flows, template.events, template.solvers)
            for part in group
        ]
        self.unique(names, template.origin, f'a part of {template.name}')
        for value in template.values:
            self.value(value, scope, template.members)
        for flow in template.flows:
            self.flow(flow, scope)
        for event in template.events:
            self.event(event, template)
        for solver in template.solvers:
            self.solver(solver, template)
        if template.status is not None:
            self.status(template.status, scope)
        for check in template.asserts:
            self.check_expr(check.test, scope, check.origin, 'an assertion')
        for member in template.members:
            self.member(member, template)

    def member(self, member, template):
        for name, init in member.values:
            value = template.part(name)
            if not isinstance(value, p.Value):
                self.fail('unknown_name', member.id, f'{name!r} is no value of {template.name}')
            elif value.kind == p.LINK:
                self.fail('kind', member.id, f'the link {name!r} is set by its row, in links')
            else:
                self.init(value, init, Scope(template), member.id)
        for name, row in member.links:
            value = template.part(name)
            if not isinstance(value, p.Value) or value.kind != p.LINK:
                self.fail('unknown_name', member.id, f'{name!r} is no link of {template.name}')
                continue
            target = self.templates.get(entity_template(value.type))
            if target is not None and not 0 <= row < len(target.members):
                self.fail(
                    'link_unset',
                    member.id,
                    f'the link {name!r} names row {row} of {target.name}, which has none',
                )
        for value in template.values:
            if value.kind == p.LINK and member.link(value.name) is None:
                self.fail(
                    'link_unset',
                    member.id,
                    f'the link {value.name!r} names no member: there is no none value',
                )
            elif value.kind != p.LINK and value.init is None and member.value(value.name) is None:
                self.fail('no_value', member.id, f'{value.name!r} has no starting value')

    # ---- values -------------------------------------------------------------------------------------

    def value(self, value, scope, members, parameter=False):
        """A value of a template (with its members), of the root (members None), or of an event."""
        where = value.origin
        if value.kind not in p.KINDS:
            self.fail('kind', where, f'no kind of value {value.kind!r}')
            return
        self.type(value.type, where)
        number = isinstance(value.type, p.Number)
        if (value.lower is not None or value.upper is not None or value.scale is not None) and not number:
            self.fail('kind', where, f'a range or a scale on {value.name!r}, which is no number')
        if (value.outflow is not None or value.inflow is not None) and not (number and value.kind == p.STATE):
            self.fail('kind', where, f'endpoint settings on {value.name!r}, which is no stored number')
        if value.kind == p.LINK and not isinstance(value.type, p.EntityType):
            self.fail('kind', where, f'the link {value.name!r} names no template')
        if isinstance(value.type, p.OccurrenceType) and (
            scope.event is None or parameter or value.kind != p.STATE or members is not None
        ):
            self.fail(
                'kind', where, f'{value.name!r} refers to an occurrence: only a local of an event holds one'
            )
            return
        if parameter or value.kind == p.LINK:
            if value.init is not None:
                self.fail('kind', where, f'{value.name!r} takes its value from its argument or its row')
        elif value.init is None and members is None:
            self.fail('no_value', where, f'{value.name!r} has no starting value')
        elif value.init is not None:
            self.init(value, value.init, scope, where)
        for bound in (value.lower, value.upper, value.scale):
            self.check_expr(bound, scope, where)
        for endpoint in (value.outflow, value.inflow):
            if endpoint is not None:
                self.endpoint(endpoint, value, scope)

    def init(self, value, init, scope, where):
        """An initializer of a value: its form must fit the value's kind."""
        expected = {
            p.FORMULA: (Formula,),
            p.COLLECTION: (Path,),
            p.DISTRIBUTION: (Distribution, Path),
            p.INPUT: (Distribution,) if isinstance(value.type, p.DistributionType) else (Expr,),
        }.get(value.kind, (Path,) if isinstance(value.type, p.OccurrenceType) else (Expr,))
        if not isinstance(init, expected):
            self.fail('kind', where, f'{value.name!r} ({value.kind}) cannot start from {type(init).__name__}')
            return
        if isinstance(value.type, p.OccurrenceType):
            found = self.resolve(init, scope, where)
            if found is not None and found.kind == 'value' and found.part.type == value.type:
                return  # another reference to an occurrence of the event
            event = self.occurrence_event(value.type)
            if found is not None and (
                found.kind != 'occurrence' or found.many or event is None or found.part != event[1]
            ):
                self.fail(
                    'kind',
                    where,
                    f'{value.name!r} refers to an occurrence of {value.type.template}.{value.type.event}: it starts '
                    f'from the path of one, not `{spelled(init)}`',
                )
            return
        if isinstance(init, Formula):
            self.check_expr(init.expr, scope, where, 'a formula')
        elif isinstance(init, Distribution):
            self.distribution(init, where)
        elif isinstance(init, Path):
            if value.kind == p.COLLECTION:
                self.collection(init, scope, where, None)
            else:
                self.resolve(init, scope, where)
        else:
            self.check_expr(init, scope, where)

    def type(self, value_type, where):
        if isinstance(value_type, p.Number):
            self.unit(value_type.unit, where)
        elif isinstance(value_type, p.EnumType):
            if value_type.enum not in {enum.name for enum in self.program.enums}:
                self.fail('enum_member', where, f'no enum {value_type.enum!r}')
        elif isinstance(value_type, (p.EntityType, p.CollectionType)):
            if value_type.template not in self.templates:
                self.fail('unknown_name', where, f'no template {value_type.template!r}')
        elif isinstance(value_type, p.DistributionType):
            self.type(value_type.of, where)
        elif isinstance(value_type, p.OccurrenceType):
            if self.occurrence_event(value_type) is None:
                self.fail('unknown_name', where, f'no event {value_type.template}.{value_type.event}')
        elif not isinstance(value_type, (p.Bool, p.Text)):
            self.fail('kind', where, f'no type: {type(value_type).__name__}')

    def endpoint(self, endpoint, value, scope):
        where = endpoint.origin or value.origin
        for setting in (endpoint.capacity, endpoint.request):
            self.setting(setting, scope, where)
        if isinstance(endpoint.allocation, p.Priority):
            side = 'source' if endpoint is value.outflow else 'sink'
            store = (owner_key(scope.event or scope.template), value.name)
            for item in endpoint.allocation.items:
                self.priority_item(item, side, store, scope, where)
        elif not isinstance(endpoint.allocation, p.Proportional):
            self.fail('kind', where, 'an allocation is priority(...) or proportional()')

    def setting(self, setting, scope, where):
        """A request or a capacity: captured once, or a live formula."""
        if isinstance(setting, Formula):
            self.check_expr(setting.expr, scope, where, 'a formula')
        else:
            self.check_expr(setting, scope, where)

    def priority_item(self, item, side, store, scope, where):
        """An item of a priority at an endpoint: a flow or a leg whose `side` is that store."""
        found = self.resolve(item, scope, where)
        if found is None:
            return
        if found.kind == 'leg':
            route = found.part
            end = route.source if (found.name == 'forward') == (side == 'source') else route.sink
            flow_owner = found.owner
        elif found.kind == 'flow' and found.part is not None and found.part.kind == p.DIRECTED:
            end, flow_owner = getattr(found.part, side), found.owner
        else:
            self.fail(
                'priority_item',
                where,
                f'`{spelled(item)}` is no directed flow or leg: name `.forward` or `.backward` of a route',
            )
            return
        if self.store_key(end, self.scope_of(flow_owner)) != store:
            self.fail('priority_item', where, f'`{spelled(item)}` is not at this endpoint')

    def scope_of(self, owner):
        """The scope of a template's or an event's own parts."""
        if isinstance(owner, p.Event):
            template = next((t for t in self.program.templates if owner in t.events), None)
            return Scope(template, owner)
        return Scope(owner if isinstance(owner, p.Template) else None)

    def store_key(self, end, scope):
        """(owner key, name) of the store that a flow's end names, or None; with no diagnostic."""
        if not isinstance(end, Path):
            return None
        found = self.quiet().resolve(end, scope, '')
        if found is None or found.kind != 'value':
            return None
        return (owner_key(found.owner), found.part.name)

    # ---- flows ----------------------------------------------------------------------------------------

    def flow(self, flow, scope):
        where = flow.origin
        if flow.kind == p.LEGS:
            if (
                flow.source is not None
                or flow.sink is not None
                or flow.request is not None
                or flow.capacity is not None
                or not flow.legs
            ):
                self.fail('kind', where, 'a flow with legs has its legs and nothing else')
            self.unique([leg.name for leg in flow.legs], where, 'a leg')
            for leg in flow.legs:
                if leg.kind != p.DIRECTED:
                    self.fail('kind', leg.origin, 'a leg is a directed flow')
                self.flow(leg, scope)
            return
        if flow.kind not in (p.DIRECTED, p.REVERSIBLE) or flow.legs:
            self.fail('kind', where, f'no kind of flow {flow.kind!r}')
            return
        units = []
        for side, end in (('source', flow.source), ('sink', flow.sink)):
            if flow.kind == p.REVERSIBLE and isinstance(end, p.Outside):
                self.fail(
                    'route_end',
                    where,
                    f'a reversible route cannot end at {end.name}: both ends supply and receive',
                )
            elif isinstance(end, p.Outside):
                if end != (p.SOURCE if side == 'source' else p.SINK):
                    self.fail('flow_end', where, f'{end.name} cannot be the {side} of a flow')
            elif isinstance(end, Path):
                found = self.store(end, scope, where, f'the {side} of {flow.name!r}', 'flow_end')
                if found is not None:
                    units.append(found.part.type.unit)
                    self.ends.setdefault((owner_key(found.owner), found.part.name), []).append(where)
            else:
                self.fail('flow_end', where, f'{flow.name!r} has no {side}')
        self.rate_unit(flow, units, where)
        for setting in (flow.request, flow.capacity):
            self.setting(setting, scope, where)

    def store(self, end, scope, where, what, code):
        """The stored number that a path names, or None after a diagnostic."""
        found = self.resolve(end, scope, where)
        if found is None:
            return None
        value = found.part if found.kind == 'value' else None
        if (
            value is not None
            and scope.event is not None
            and value in scope.event.params
            and found.owner is scope.event
        ):
            self.fail(
                'parameter_end',
                where,
                f'{what}, `{spelled(end)}`, is a parameter: pass the entity and use its field (D13)',
            )
            return None
        if value is None or found.many or value.kind != p.STATE or not isinstance(value.type, p.Number):
            self.fail(code, where, f'{what}, `{spelled(end)}`, is no stored number')
            return None
        return found

    def rate_unit(self, flow, units, where):
        """The unit of a flow's rates is its ends' unit per time; two ends have one dimension."""
        rate = self.unit(flow.unit, where) if flow.unit else None
        if not flow.unit:
            self.fail('flow_units', where, f'{flow.name!r} needs the unit of its rates')
        stores = [self.unit(unit, where) for unit in units]
        stores = [unit for unit in stores if unit is not None]
        if len(stores) == 2 and not stores[0].compatible(stores[1]):
            self.fail('flow_units', where, f'the ends of {flow.name!r} are in {units[0]} and {units[1]}')
        if rate is not None and stores:
            per_time = dict(stores[0].dimension)
            per_time['time'] = per_time.get('time', 0) - 1
            if tuple(sorted((k, v) for k, v in per_time.items() if v)) != rate.dimension:
                self.fail(
                    'flow_units',
                    where,
                    f'the rates of {flow.name!r} in {flow.unit} are not {units[0]} per time',
                )

    # ---- events --------------------------------------------------------------------------------------

    def event(self, event, template):
        scope = Scope(template, event)
        names = [part.name for part in (*event.params, *event.locals)]
        self.unique(names, event.origin, f'a parameter or a local of {event.name}')
        for param in event.params:
            if param.kind not in (p.STATE, p.LINK):
                self.fail('kind', param.origin, f'the parameter {param.name!r} is a value or an entity')
            self.value(param, scope, None, parameter=True)
        for index, part in enumerate(event.locals):
            if isinstance(part, p.Flow):
                self.flow(part, scope)
                plain = [s for s in (part.request, part.capacity) if isinstance(s, Expr)]
                plain += [s for leg in part.legs for s in (leg.request, leg.capacity) if isinstance(s, Expr)]
            else:
                if part.kind in (p.INPUT, p.LINK):
                    self.fail('kind', part.origin, f'the local {part.name!r} is no input or link')
                self.value(part, scope, None)
                # Plain endpoint settings take their values just after the store's initializer.
                self.local_order(
                    event,
                    index + 1,
                    part,
                    [
                        setting
                        for end in (part.inflow, part.outflow)
                        if end is not None
                        for setting in (end.capacity, end.request)
                        if isinstance(setting, Expr)
                    ],
                )
                plain = [s for s in (part.init, part.lower, part.upper) if isinstance(s, (Expr, Path))]
            self.local_order(event, index, part, plain)
        for step in event.steps:
            if isinstance(step, p.After):
                self.check_expr(step.delay, scope, step.origin)
                self.check_expr(step.guard, scope, step.origin)
                for statement in step.body:
                    self.statement(statement, scope)
            elif isinstance(step, p.Until):
                self.check_expr(step.test, scope, step.origin, 'a gate')
            else:
                self.fail('kind', event.origin, f'no step: {type(step).__name__}')
        for trigger in event.triggers:
            self.trigger(trigger, template, event)

    def local_order(self, event, index, part, plain):
        """D14: a plain initializer reads parameters and the locals above it, never one below."""
        above = {param.name for param in event.params} | {local.name for local in event.locals[:index]}
        below = {local.name for local in event.locals[index:]} - above
        for expression in plain:
            for name in sorted(_locals_read(expression) & below):
                self.fail(
                    'local_order',
                    part.origin,
                    f'{part.name!r} reads {name!r}, declared below it: a plain initializer runs in '
                    'written order (D14)',
                )

    def trigger(self, trigger, template, event):
        scope = Scope(template, trigger=trigger)
        self.check_expr(trigger.test, scope, trigger.origin, 'a trigger')
        self.unique([capture.name for capture in trigger.captures], trigger.origin, 'a capture')
        for capture in trigger.captures:
            self.value(capture, scope, None)
        own = Path(THIS, (event.name,))
        for statement in trigger.body:
            if not isinstance(statement, p.Start) or statement.event != own:
                self.fail(
                    'trigger_start',
                    trigger.origin,
                    f'a trigger only starts its own event, `this.{event.name}`',
                )
            self.statement(statement, scope)
        if trigger.reset is not None:
            if trigger.reset.kind not in ('when', 'after'):
                self.fail('kind', trigger.origin, 'a reset is `when` or `after`')
            self.check_expr(
                trigger.reset.expr, scope, trigger.origin, 'a reset' if trigger.reset.kind == 'when' else None
            )

    # ---- statements ----------------------------------------------------------------------------------

    def statement(self, statement, scope):
        where = statement.origin
        if isinstance(statement, p.Assign):
            self.assign(statement, scope)
        elif isinstance(statement, p.Move):
            self.check_expr(statement.amount, scope, where)
            for end in (statement.source, statement.destination):
                found = self.store(end, scope, where, 'an end of a move', 'move_end')
                if found is not None:
                    self.ends.setdefault((owner_key(found.owner), found.part.name), []).append(where)
        elif isinstance(statement, p.Start):
            found = self.resolve(statement.event, scope, where)
            if found is not None and found.kind != 'event':
                self.fail('unknown_name', where, f'`{spelled(statement.event)}` names no event')
            elif found is not None and len(statement.args) != len(found.part.params):
                wanted = len(found.part.params)
                self.fail(
                    'arguments',
                    where,
                    f'`{spelled(statement.event)}` takes {wanted} arguments, not {len(statement.args)}',
                )
            for arg in statement.args:
                self.check_expr(arg, scope, where)
        elif isinstance(statement, p.If):
            self.check_expr(statement.test, scope, where)
            for inner in (*statement.then, *statement.orelse):
                self.statement(inner, scope)
        elif isinstance(statement, p.Switch):
            self.check_expr(statement.selector, scope, where)
            enum = self.selector_enum(statement.selector, scope)
            self.unique([case.member for case in statement.cases], where, 'a case')
            for case in statement.cases:
                if enum is not None:
                    self.enum_member(enum, case.member, case.origin)
                self.check_expr(case.guard, scope, case.origin)
                for inner in case.body:
                    self.statement(inner, scope)
            for inner in statement.orelse:
                self.statement(inner, scope)
        else:
            self.fail('kind', getattr(statement, 'origin', ''), f'no statement: {type(statement).__name__}')

    def selector_enum(self, selector, scope):
        """The enum of a switch's selector, when the selector is one read whose enum is known."""
        if not isinstance(selector.node, nodes.Ref) or len(selector.reads) != 1:
            return None
        read = selector.reads[0][1]
        if isinstance(read, EnumValue):
            return read.enum
        source = read.source if isinstance(read, Draw) else read
        if isinstance(source, Distribution):
            return source.enum or None
        if isinstance(source, Path):
            found = self.quiet().resolve(source, scope, '')
            if found is not None and found.kind == 'value':
                value_type = found.part.type
                if isinstance(value_type, p.DistributionType):
                    value_type = value_type.of
                if isinstance(value_type, p.EnumType):
                    return value_type.enum
        return None

    def assign(self, statement, scope):
        where, target = statement.origin, statement.target
        found = self.resolve(target, scope, where)
        value = statement.value
        if isinstance(value, Formula):
            self.check_expr(value.expr, scope, where, 'a formula')
            self.lifetime(target, value, scope, where)
        elif isinstance(value, Distribution):
            self.distribution(value, where)
        elif isinstance(value, Path):
            self.resolve(value, scope, where)
        elif isinstance(value, p.Priority):
            for item in value.items:
                self.resolve(item, scope, where)
        elif isinstance(value, Expr):
            self.check_expr(value, scope, where)
        if found is None:
            return
        if statement.op not in ('=', '+=', '-='):
            self.fail('kind', where, f'no assignment {statement.op!r}')
        if found.many:
            self.fail('collection', where, f'`{spelled(target)}` is a projection, which no statement assigns')
            return
        if found.kind == 'property':
            if found.name in FIXED_PROPERTIES:
                self.fail(
                    'fixed_write', where, f'the ends of a flow are fixed for the run: `{spelled(target)}`'
                )
            elif found.name not in SETTABLE_PROPERTIES or found.of.kind == 'leg':
                self.fail(
                    'result_write', where, f'the run computes `{spelled(target)}`; no statement assigns it'
                )
            elif found.name == 'allocation':
                if not isinstance(value, (p.Priority, p.Proportional)) or statement.op != '=':
                    self.fail('assign_value', where, 'an allocation takes priority(...) or proportional()')
            elif not isinstance(value, (Expr, Formula)) or (
                isinstance(value, Formula) and statement.op != '='
            ):
                self.fail('assign_value', where, f'`{spelled(target)}` takes a rate or a formula')
            return
        if found.kind == 'unknown':
            self.fail(
                'result_write', where, f"`{spelled(target)}` is a solver's result, read-only to callers"
            )
            return
        if found.kind != 'value':
            self.fail('fixed_write', where, f'`{spelled(target)}` is no value that a statement can assign')
            return
        part = found.part
        if part.kind in (p.INPUT, p.LINK) or isinstance(part.type, p.EntityType):
            self.fail('fixed_write', where, f'`{spelled(target)}` is fixed for the run')
            return
        if isinstance(part.type, p.OccurrenceType):
            self.fail(
                'fixed_write', where, f'`{spelled(target)}` refers to an occurrence, set when its own enters'
            )
            return
        if part.readonly:
            self.fail(
                'readonly_write',
                where,
                f'`{spelled(target)}` is readonly; a flow or a move can still change a stock',
            )
            return
        form = {p.FORMULA: Formula, p.DISTRIBUTION: Distribution, p.COLLECTION: Path}.get(part.kind, Expr)
        if not isinstance(value, form) or (
            statement.op != '=' and not (form is Expr and isinstance(part.type, p.Number))
        ):
            self.fail(
                'assign_value',
                where,
                f'`{spelled(target)}` ({part.kind}) cannot take {statement.op} {type(value).__name__}',
            )
            return
        self.assigned.setdefault((owner_key(found.owner), part.name), []).append(where)

    def lifetime(self, target, formula, scope, where):
        """A formula that a stage installs on a place that outlives the stage's occurrence may not read
        one of the occurrence's own names (spec, "State owned by an invocation"). A place lives as long
        as the owner of the target that it resolves to: a bare name of the occurrence, and a step from
        it to the settings of its own flows and stores, is the occurrence's; a step from a parameter
        that names an entity, a local that names another occurrence or a collection reaches a place of
        that thing, and any other start (`this`, a member, the root) a place that lives for the run."""
        if scope.event is None:
            return
        if isinstance(target.start, Local) and not self.refers(target.start.name, scope):
            return
        for name in sorted(self.own_names(formula.expr, scope)):
            self.fail(
                'lifetime',
                where,
                f'`{spelled(target)}` outlives the occurrence of {scope.event.origin}, and its formula '
                f'reads `{name}`, which ends with the occurrence',
            )

    def refers(self, name, scope):
        """Whether a bare name of an event refers to something else than the occurrence: a parameter
        that names an entity, a local that names another occurrence, a collection."""
        found = self.quiet().resolve(Path(Local(name), ()), scope, '')
        if found is None or found.kind != 'value':
            return False
        return isinstance(found.part.type, (p.EntityType, p.OccurrenceType, p.CollectionType))

    def own_names(self, expression, scope):
        """The bare names of the occurrence that an expression reads, at any depth of its reads: the
        start of a path, and the paths, keys and tests of its collections."""
        found, pending = set(), [read for _, read in expression.reads]
        while pending:
            read = pending.pop()
            if isinstance(read, (Reduce, Since)):
                read = read.source if isinstance(read, Reduce) else read.event
            elif isinstance(read, Elapsed):
                read = read.value
            elif isinstance(read, Draw):
                read = read.source
            if not isinstance(read, Path):
                continue
            start = read.start
            if isinstance(start, Local) and scope.event is not None:
                found.add(start.name)
            elif isinstance(start, (Where, Lookup)):
                pending.append(start.source)
                pending += [
                    inner for _, inner in (start.test if isinstance(start, Where) else start.key).reads
                ]
            elif isinstance(start, By):
                pending.append(start.source)
            elif isinstance(start, Literal):
                pending += list(start.items)
        return found

    # ---- solvers, displays ------------------------------------------------------------------------------

    def solver(self, solver, template):
        scope = Scope(template, solver=solver)
        self.unique(
            [b.name for b in solver.inputs] + [u.name for u in solver.unknowns],
            solver.origin,
            'a name of a solver',
        )
        for binding in solver.inputs:
            self.resolve(binding.source, Scope(template), binding.origin)
        for unknown in solver.unknowns:
            if unknown.kind != p.STATE or not isinstance(unknown.type, p.Number):
                self.fail('kind', unknown.origin, f'the unknown {unknown.name!r} is a number')
            for part in (unknown.init, unknown.lower, unknown.upper, unknown.scale):
                self.check_expr(part, scope, unknown.origin, 'a solver')
            self.type(unknown.type, unknown.origin)
        for entry in solver.solve_for:
            self.solve_for(entry, scope, solver)
        for constraint in solver.constraints:
            self.check_expr(constraint.test, scope, constraint.origin, 'a solver')
        for objective in solver.objective:
            if objective.sense not in ('minimize', 'maximize'):
                self.fail(
                    'kind', objective.origin, f'an objective minimizes or maximizes, not {objective.sense!r}'
                )
            self.check_expr(objective.expr, scope, objective.origin, 'a solver')

    def solve_for(self, entry, scope, solver):
        """An entry of `solve_for`: a stored number, or a flow's actual rate or served fraction."""
        found = self.resolve(entry, scope, solver.origin)
        if found is None:
            return
        key = None
        if found.kind == 'value' and found.part.kind == p.STATE and isinstance(found.part.type, p.Number):
            key = ('value', owner_key(found.owner), found.part.name)
        elif found.kind == 'property' and found.of.kind == 'flow' and found.of.part is not None:
            flow, parent = found.of.part, found.of.of
            names = ('served_fraction',) if flow.kind == p.LEGS else ('actual_rate',)
            if found.name in names and not (parent is not None and parent.kind == 'flow'):
                key = ('rate', owner_key(found.of.owner), flow.name)
        if key is None:
            self.fail(
                'solve_for',
                solver.origin,
                f'a solver cannot determine `{spelled(entry)}`: name a stored number, '
                "a flow's actual_rate, or a served_fraction",
            )
            return
        # One solver that names a value twice (by its path and through an input) is its one writer.
        writers = self.solved.setdefault(key, [])
        if solver.origin not in writers:
            writers.append(solver.origin)

    def writers(self):
        """One writer for each value: a solver's result has no other solver, stage or flow."""
        for key, solvers in self.solved.items():
            others = solvers[1:]
            if key[0] == 'value':
                others += self.assigned.get(key[1:], []) + self.ends.get(key[1:], [])
            if others:
                self.fail(
                    'two_writers',
                    solvers[0],
                    f'{key[1]}.{key[2]} has two writers: {", ".join(solvers[:1] + others)}',
                )

    def status(self, status, scope):
        if scope.template.part('status') is not None:
            self.fail(
                'duplicate_name', status.origin, 'a template with a status display has no part named status'
            )
        for index, case in enumerate(status.cases):
            if case.rating not in p.RATINGS:
                self.fail('kind', case.origin, f'a rating is one of {", ".join(p.RATINGS)}')
            last = index == len(status.cases) - 1
            if (case.test is None) != last:
                self.fail(
                    'status_fallback',
                    status.origin,
                    'the last case of a status, and only it, has no condition',
                )
            self.check_expr(case.test, scope, case.origin, 'a status')


def _locals_read(expression):
    """The bare names that an expression reads, also inside its collections and keyed reads; or that
    a path reads (the initializer of a reference to an occurrence)."""
    found = set()

    def path(item):
        start = item.start
        if isinstance(start, Local):
            found.add(start.name)
        elif isinstance(start, Literal):
            for inner in start.items:
                path(inner)
        elif isinstance(start, (Where, By, Lookup)):
            path(start.source)
            if isinstance(start, (Where, Lookup)):
                found.update(_locals_read(start.test if isinstance(start, Where) else start.key))

    for _, read in ((None, expression),) if isinstance(expression, Path) else expression.reads:
        for item in (
            read,
            getattr(read, 'source', None),
            getattr(read, 'event', None),
            getattr(read, 'value', None),
            getattr(read, 'actor', None),
        ):
            if isinstance(item, Path):
                path(item)
    return found


def check(program):
    """The diagnostics of a program: each invariant that it breaks, with its code and its part."""
    return _Checker(program).run()


# ---- the setup's reports ------------------------------------------------------------------------------


def reports(program):
    """The setup's reports of a checked program: what it says of a program before a run, refusing
    nothing (spec, "Collections, keys and projections"). Each is a `Diagnostic`:

    - `equal_keys`, at the member that wins: members of a keyed view that `.at(...)` reads have one
      key. Of equal keys a lookup reads the member created later, the later row of the program, and
      the report names it. A `where` limits the check to the members that pass its test.
    - `below_first_key`, at the part that reads the lookup: its key has a known lower bound (a
      number, `t` from 0 h, or a stored value or an input with a lower bound) below the first key of
      its view, or the view is empty. Such a read fails when it is evaluated.

    The views are those that the program fixes before a run: `Template.instances`, a literal of
    named members, a collection value of the root, and `where` and `by` of a view. A key, or a
    `where` test, is known when the member's value of each field that it reads is a number, a
    yes/no or a text written in place (its own, or its template's initializer); the inputs keep the
    program's values, before a configuration overrides them. A view whose test is not known for
    every member takes no part, nor a member whose key is not known, nor a lookup by an unkeyed
    view (its creation numbers are distinct)."""
    return tuple(_Reports(program).run())


class _Reports:
    """The reports of `reports`, each at most once: a tie once for each view, a lookup below its
    first key once for each place that reads it."""

    def __init__(self, program):
        self.program = program
        self.resolver = Resolver(program)
        self.done = set()

    def run(self):
        for scope, origin, lookup in _lookups(self.program):
            yield from self.lookup(scope, origin, lookup)

    def lookup(self, scope, origin, lookup):
        view = lookup.source
        field = _key_field(view)
        found = None if field is None else self.members(view)
        if found is None:
            return
        template, rows = found
        part = template.part(field)
        if not isinstance(part, p.Value) or not isinstance(part.type, p.Number):
            return
        unit = part.type.unit
        keys = {row: self.written(template, template.members[row], field) for row in rows}
        known = sorted((key, row) for row, key in keys.items() if key is not None)
        if ('tie', view) not in self.done:
            self.done.add(('tie', view))
            ties = {}
            for key, row in known:
                ties.setdefault(key, []).append(template.members[row].id)
            for key, ids in ties.items():
                if len(ids) > 1:
                    yield Diagnostic(
                        'equal_keys',
                        ids[-1],
                        f'{", ".join(ids)} have the key {_quantity(key, unit, self.program)} in '
                        f'`{spelled(view)}`, which `.at(...)` reads: of equal keys it reads the member '
                        f'created later, {ids[-1]}',
                    )
        lowest = self.lower(lookup.key, scope)
        if lowest is None or ('below', origin, lookup) in self.done or None in keys.values():
            return
        self.done.add(('below', origin, lookup))
        reader = f'`{spelled(Path(lookup))}`'
        if not known:
            yield Diagnostic(
                'below_first_key',
                origin,
                f'{reader} reads an empty collection: such a read fails when it is evaluated',
            )
        elif lowest < known[0][0]:
            yield Diagnostic(
                'below_first_key',
                origin,
                f'{reader} reads at {_quantity(lowest, unit, self.program)} at the least, below the '
                f'first key {_quantity(known[0][0], unit, self.program)}: such a read fails when it '
                'is evaluated',
            )

    def members(self, path):
        """(template, rows) of a view that the program fixes before a run, with the rows that pass
        its `where` tests in row order (the order of creation), or None."""
        start = path.start
        if isinstance(start, Root) and len(path.steps) == 1:
            value = self.program.root_value(path.steps[0])
            if value is None or value.kind != p.COLLECTION or not isinstance(value.init, Path):
                return None
            return self.members(value.init)
        if path.steps:
            return None
        if isinstance(start, Instances):
            template = self.resolver.templates.get(start.template)
            return None if template is None else (template, list(range(len(template.members))))
        if isinstance(start, Literal):
            if not start.items or not all(_named(item) for item in start.items):
                return None
            try:
                found = [self.program.member(item.start.id) for item in start.items]
            except KeyError:
                return None
            return found[0][0], sorted(row for _, row in found)
        if isinstance(start, By):
            return self.members(start.source)
        if isinstance(start, Where):
            found = self.members(start.source)
            if found is None:
                return None
            template, rows = found
            kept = []
            for row in rows:
                passed = self.passes(start.test, template, template.members[row])
                if passed is None:
                    return None
                if passed:
                    kept.append(row)
            return template, kept
        return None

    def written(self, template, member, name):
        """The exact value of a member's field written in place (its own initializer, or its
        template's), or None."""
        part = template.part(name)
        if not isinstance(part, p.Value) or part.kind not in (p.INPUT, p.STATE):
            return None
        init = member.value(name)
        init = part.init if init is None else init
        return _exact(init.node, {}, self.program) if isinstance(init, Expr) and not init.reads else None

    def passes(self, test, template, member):
        """Whether a member passes a `where` test that reads only its fields written in place, or
        None."""
        values = {}
        for name, read in test.reads:
            if not (isinstance(read, Path) and read.start == ITEM and len(read.steps) == 1):
                return None
            values[name] = self.written(template, member, read.steps[0])
            if values[name] is None:
                return None
        found = _exact(test.node, values, self.program)
        return found if isinstance(found, bool) else None

    def lower(self, key, scope):
        """The known lower bound of a lookup's key, exact in the canonical unit, or None: a number,
        `t` (a run starts at 0 h), or a stored value or an input with a lower bound written in
        place."""
        if not key.reads:
            found = _exact(key.node, {}, self.program)
            return None if isinstance(found, (bool, str)) else found
        if not isinstance(key.node, nodes.Ref) or len(key.reads) != 1:
            return None
        read = key.reads[0][1]
        if isinstance(read, Time):
            return Fraction(0)
        if not isinstance(read, Path):
            return None
        found = self.resolver.resolve(read, scope, '')
        if found is None or found.kind != 'value' or found.many:
            return None
        value = found.part
        if value.kind not in (p.INPUT, p.STATE) or not isinstance(value.lower, Expr) or value.lower.reads:
            return None
        bound = _exact(value.lower.node, {}, self.program)
        return None if isinstance(bound, (bool, str)) else bound


def _named(path):
    return isinstance(path.start, Named) and not path.steps


def _key_field(path):
    """The field that keys a view (`c.by(hour)`, or a `where` of one), or None."""
    while not path.steps and isinstance(path.start, Where):
        path = path.start.source
    return path.start.key if not path.steps and isinstance(path.start, By) else None


def _lookups(program):
    """(scope, origin, lookup) of each `.at(...)` of a program: in its templates' parts and members,
    in its root, its setup and its assertions."""
    for template in program.templates:
        scope = Scope(template)
        status = (template.status,) if template.status is not None else ()
        for part in (*template.values, *template.flows, *template.asserts, *status):
            yield from _found_in(part, scope, part.origin)
        for event in template.events:
            yield from _found_in(
                (event.params, event.locals, event.steps), Scope(template, event), event.origin
            )
            for trigger in event.triggers:
                yield from _found_in(trigger, Scope(template, trigger=trigger), trigger.origin)
        for solver in template.solvers:
            yield from _found_in(solver, Scope(template, solver=solver), solver.origin)
        for member in template.members:
            yield from _found_in(member.values, scope, member.id)
    for part in (*program.root, *program.setup, *program.asserts):
        yield from _found_in(part, Scope(), part.origin)


def _found_in(value, scope, origin):
    """The lookups inside a record, a tuple or a read, each with the origin of the nearest part."""
    if isinstance(value, Lookup):
        yield scope, origin, value
    if isinstance(value, Expr):
        # Most expressions of a large table read nothing: only their reads can hold a lookup.
        for _, read in value.reads:
            yield from _found_in(read, scope, origin)
    elif isinstance(value, tuple):
        for each in value:
            yield from _found_in(each, scope, origin)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        here = getattr(value, 'origin', '') or origin
        for item in dataclasses.fields(value):
            yield from _found_in(getattr(value, item.name), scope, here)


_EXACT_BINARY = {
    'add': lambda a, b: a + b,
    'sub': lambda a, b: a - b,
    'mul': lambda a, b: a * b,
    'div': lambda a, b: a / b if b else None,
}
_EXACT_COMPARE = {
    'eq': lambda a, b: a == b,
    'ne': lambda a, b: a != b,
    'lt': lambda a, b: a < b,
    'le': lambda a, b: a <= b,
    'gt': lambda a, b: a > b,
    'ge': lambda a, b: a >= b,
}


def _exact(node, values, program):
    """The exact value of a node whose names are in `values`: a number (a Fraction in the canonical
    unit of its dimension, as `q(number, unit)` scales it), a yes/no or a text; or None when a part
    of it is not known, or is not one of these operations."""
    if isinstance(node, nodes.Const):
        value = node.value
        if isinstance(value, (bool, str)):
            return value
        return Fraction(value) if isinstance(value, (int, float)) else None
    if isinstance(node, nodes.Ref):
        return values.get(node.name)
    if isinstance(node, nodes.Call) and node.function == 'q' and len(node.args) == 2:
        number, unit = _exact(node.args[0], values, program), node.args[1]
        if not isinstance(number, Fraction) or not isinstance(unit, nodes.Const):
            return None
        try:
            return number * program.unit(unit.value).scale
        except KeyError:
            return None
    parts = [_exact(child, values, program) for child in node.children]
    if any(part is None for part in parts):
        return None
    numbers = all(isinstance(part, Fraction) for part in parts)
    if isinstance(node, nodes.Unary):
        if node.op == 'not':
            return not parts[0] if isinstance(parts[0], bool) else None
        return (-parts[0] if node.op == 'neg' else parts[0]) if numbers else None
    if isinstance(node, nodes.Binary) and node.op in _EXACT_BINARY:
        return _EXACT_BINARY[node.op](*parts) if numbers else None
    if isinstance(node, nodes.Compare):
        if not numbers and node.ops not in (('eq',), ('ne',)):
            return None
        return all(_EXACT_COMPARE[op](a, b) for op, a, b in zip(node.ops, parts, parts[1:]))
    if isinstance(node, nodes.BoolOp) and all(isinstance(part, bool) for part in parts):
        return all(parts) if node.op == 'and' else any(parts)
    return None


def _quantity(value, unit, program):
    """A canonical value written in a unit, for a message: `10 h`, `0.5 kW`."""
    number = value / program.unit(unit).scale
    written = str(number.numerator) if number.denominator == 1 else f'{float(number):g}'
    return f'{written} {unit}'.strip()
