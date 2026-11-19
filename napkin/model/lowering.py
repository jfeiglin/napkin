"""The lowering: a declared model (`semantic.py`) written as a program, through `napkin.program.build`.

Each template is a template of the program with its parts, and each entity written once a template
of one member with its name. Each member written by hand is a member of its template with its own
values and the member that each link names (its own, or the link's initializer); the rows of a table
go to `Builder.table`, which names a row with an id `table.id` and keeps those rows in the order of
their ids, so a reordered file gives the same program. The values and the assertions of the top
level are the root's. `Builder.finish` gives each part its origin, which is the path of the declared
part it comes from.

An expression is written as a node of `napkin/core/expr` with the read of each of its names
(`refs.Path`, `refs.Reduce`, `refs.TIME`), the form in which the builder's own handles write it, so a
source text and the program that a test builds by hand have the same canonical bytes. A read through
a collection starts at `Instances`, `Literal`, `Where`, `By` or `Lookup`, and a test or a key inside
one is an `Expr` of its own; in the test of a `where` over an endpoint's flows, an end of the member
is `ITEM.source` or `ITEM.sink`, which the engine compares with a store by identity. A number with a unit is the core's literal `q(number, unit)`; a bare
number that takes a unit is written with it. The settings of a store's outflow and inflow are its
`build.endpoint`; a side that sets nothing but `proportional()`, the default, is a side that sets
nothing, so the two texts are one program. A reversible route is a `build.route`, and a flow with
legs a `build.legs` of its legs, each a directed flow. A read of a flow's end reaches the lowering
as the read of its store (`semantic.Resolver.end`), so the program reads the store by its path.

An event is a `build.event` of its parameters, its locals and flows, its steps and its triggers; a
statement is the builder's assignment, move, start or branch, and the setup's starts are
`Builder.setup`. A bare name of an event is `refs.Local`. An enum is declared once by its spelling
(`enum[OPEN, CLOSED]`), its members a `refs.EnumValue`; a draw carries a temporary site
until `Builder.finish` gives each its place, as the builder's own `draw` does.

A solver is a `build.solver` of its inputs, the fields that it determines, its new unknowns, its
constraints and its objectives; a bare name of it is `refs.Local`, and a caller reads its unknowns by
their paths (`this.staffing.care`). What its constraints and objectives may say is checked on the
finished program (`solvers.problems`).

A status display is `build.status` of its cases in written order, each `build.rating` of its rating
and its condition; the last has none. A refusal of the program's checker, or of `solvers.problems`, is given at the line of the declared
part that it names, and so is each of the setup's reports (`reports`), which refuse nothing.

`side_table` gives the program's side table (`napkin.program.artifact.SideTable`): the place in the
source of each part of the program that has an origin, its label, its evidence and its title, from
the declared part of that path, and the same of each member written by hand, so the table is outside
the program: a title edit moves no hash (PLAN, change 19).
"""

from __future__ import annotations

import itertools
from dataclasses import fields, is_dataclass
from fractions import Fraction

from ..core import expr as nodes
from ..program import build, check
from ..program import parts as p
from ..program.artifact import MEMBER, Evidence, Location, SideTable, kind_of, origins
from ..program.check import ProgramError
from ..program.refs import (
    ITEM,
    ROOT,
    THIS,
    TIME,
    By,
    Distribution,
    Draw,
    Elapsed,
    EnumValue,
    Instances,
    Literal,
    Local,
    Lookup,
    Named,
    Path,
    Reduce,
    Since,
    Where,
    spelled,
)
from . import semantic as s
from . import solvers
from .language import nodes as n
from .language.problems import LanguageError, Problem

_SITES = itertools.count()
# The core's names of the operations of the declared model.
OPERATIONS = {'add': 'add', 'sub': 'sub', 'mul': 'mul', 'div': 'div', 'pow': 'pow'}
COMPARISONS = {'<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge', '==': 'eq', '!=': 'ne'}


def lower(model):
    """The program of a declared model, checked (`Builder.finish`). Raises `LanguageError` with each
    refusal of the checker."""
    builder = build.Builder(model.units.table)
    enums = _enums(model)
    for name in sorted(enums):
        builder.enum(name, *enums[name].members)
    templates = {}
    for entity in model.entities:
        templates[entity.path] = entity
        parts = [part_of(part) for part in entity.parts]
        if entity.status is not None:
            parts.append(status_of(entity.status))
        if isinstance(entity, s.DeclaredTemplate):
            builder.template(entity.path, *parts)
        else:
            builder.entity(entity.path, *parts, **_links(entity, ()))
    tables = set()
    for member in model.members:
        template = templates[member.template]
        if member.table is None:
            builder.member(member.template, member.path, **_given(member, template))
        elif member.table not in tables:
            tables.add(member.table)
            rows = [_row(each, template) for each in model.members if each.table == member.table]
            builder.table(member.table, member.template, rows)
    builder.root(*(value_of(value) for value in model.root), *(_assertion(item) for item in model.asserts))
    builder.setup(*(_statement(start) for start in model.setup))
    try:
        program = builder.finish()
    except ProgramError as error:
        raise LanguageError([_located(model, item) for item in error.diagnostics]) from None
    found = solvers.problems(program)
    if found:
        raise LanguageError([_located(model, item) for item in found])
    return program


def reports(model, program):
    """The setup's reports of a lowered model (`check.reports`: equal keys in a view that `.at`
    reads, a lookup below its first key), each a `Problem` at the line of its part, which refuses
    nothing."""
    return tuple(_located(model, item) for item in check.reports(program))


def side_table(model, program, file=''):
    """The side table of a lowered model: for each part of the program with an origin, in the
    program's order, its kind, its name, its place (the file of its line, `file` for a model of one
    text, and the column of the line's first word) and the label, the evidence and the title of the
    declared part of its path; then each member written by hand, of the kind `MEMBER`, in the order
    of the program's members, with its text, its evidence and its title. A cited record is given with
    its content."""
    columns = _columns(model.tree)
    records = {item.name: item for item in model.records}

    def located(origin, kind, name, declared):
        line = getattr(declared, 'line', 0)
        where, at = model.place(line) if line else ('', 0)
        return Location(
            origin,
            kind,
            name,
            where or (file if line else ''),
            at,
            columns.get(line, 0),
            getattr(declared, 'text', None),
            tuple(_evidence(item, records) for item in getattr(declared, 'evidence', ())),
            getattr(declared, 'title', None),
        )

    found = [
        located(
            origin,
            kind_of(part),
            getattr(part, 'name', None) or getattr(part, 'member', ''),
            model.part(origin),
        )
        for origin, part in origins(program).items()
    ]
    for template in program.templates:
        for member in template.members:
            declared = model.part(member.id)
            # An entity written once is its template's location; a row of a table has none.
            if isinstance(declared, s.DeclaredMember) and declared.table is None:
                found.append(located(member.id, MEMBER, member.id, declared))
    return SideTable(tuple(found))


def _columns(tree):
    """The column of each line of a parsed model, its first word's, by the line's number."""
    found = {}

    def walk(node):
        if isinstance(node, n.Line):
            found.setdefault(node.line, node.column)
        for item in fields(node):
            value = getattr(node, item.name)
            for each in value if isinstance(value, tuple) else (value,):
                if isinstance(each, n.Node):
                    walk(each)

    for item in tree.items:
        walk(item)
    return found


def _evidence(item, records):
    """A record of a declared part's evidence (`nodes.Cite` of a record of the model, or
    `nodes.Inline`) as the side table gives it, with its content."""
    if isinstance(item, n.Cite):
        named = records[item.name]
        return Evidence(item.name, *_content(named))
    return Evidence('', *_content(item))


def _content(record):
    claims = tuple((claim.id, claim.datum) for claim in record.claims)
    return record.kind, record.text, tuple(record.relations), claims


def _located(model, item):
    """A refusal of the checker at the line of the declared part whose path is its origin, or a part
    above it (`tank.water.outflow` is about `tank.water`); a row's line is in the file of its table."""
    path = item.part
    while path and model.part(path) is None:
        path = path.rpartition('.')[0]
    found = model.part(path) if path else None
    return Problem(
        item.code, f'{item.part}: {item.message}', getattr(found, 'line', 0), 0, getattr(found, 'file', '')
    )


# ---- members --------------------------------------------------------------------------------------


def _links(entity, own):
    """The member that each link of a member names: its own, or the link's initializer."""
    targets = {given.name: given.init for given in own}
    for part in entity.parts:
        if isinstance(part, s.DeclaredValue) and part.kind == s.LINK and part.init is not None:
            targets.setdefault(part.name, part.init.start[1])
    return {name: build.named(target) for name, target in targets.items()}


def _given(member, template):
    """A member's own values and its links, as `Builder.member` takes them."""
    return {
        **{given.name: initial(given.init) for given in member.values},
        **_links(template, member.links),
    }


def _row(member, template):
    """A row of a table as `Builder.table` takes it: with its id when the table has ids."""
    _, _, id = member.path.partition('.')
    return {'id': id, **_given(member, template)} if id else _given(member, template)


# ---- parts ------------------------------------------------------------------------------------------


def _enums(model):
    """Each enum that the types, the values and the distributions of a model name, by its spelling
    (an enum is its members, `semantic.EnumOf`). A member's own value is of its template's type, so
    the members need no walk."""
    found = {}

    def walk(item):
        if isinstance(item, s.EnumOf):
            found.setdefault(str(item), item)
        elif isinstance(item, tuple):
            for each in item:
                walk(each)
        elif is_dataclass(item) and not isinstance(item, type):
            for each in fields(item):
                walk(getattr(item, each.name))

    walk((model.entities, model.root, model.asserts, model.setup))
    return found


def _type(kind):
    if isinstance(kind, s.Num):
        return kind.unit
    if isinstance(kind, s.EnumOf):
        return p.EnumType(str(kind))
    if isinstance(kind, s.Dist):
        return build.dist_of(_type(kind.of))
    if isinstance(kind, s.Ent):
        return build.ref_to(kind.template)
    if isinstance(kind, s.Occ):
        template, _, event = kind.event.rpartition('.')
        return build.occurrence_of(template, event)
    return build.BOOL if kind == s.BOOL else build.TEXT


def part_of(part):
    if isinstance(part, s.DeclaredEvent):
        return event_of(part)
    if isinstance(part, s.DeclaredSolver):
        return solver_of(part)
    if isinstance(part, s.DeclaredLegs):
        return build.legs(part.name, *(flow_of(leg) for leg in part.legs))
    if isinstance(part, s.DeclaredFlow):
        return flow_of(part)
    if isinstance(part, s.DeclaredAssert):
        return _assertion(part)
    return value_of(part)


def value_of(value):
    """The program's value of a declared value."""
    if value.kind == s.LINK:
        return build.link(value.name, value.type.template)
    if value.kind == s.COLLECTION:
        init = None if value.init is None else initial(value.init)
        return build.value(value.name, build.group_of(value.type.of.template), init, readonly=value.readonly)
    bounds = {
        'lower': None if value.lower is None else handle(value.lower),
        'upper': None if value.upper is None else handle(value.upper),
        'scale': None if value.scale is None else handle(value.scale),
    }
    init = None if value.init is None else initial(value.init)
    if value.kind == s.INPUT:
        return build.input_(value.name, _type(value.type), init, **bounds)
    ends = {'outflow': _endpoint(value.outflow), 'inflow': _endpoint(value.inflow)}
    return build.value(value.name, _type(value.type), init, readonly=value.readonly, **bounds, **ends)


def _endpoint(declared):
    """The settings of an outflow or an inflow (`build.endpoint`), or None for a side that sets
    nothing but the default `proportional()`, which is the program of a side that sets nothing."""
    if declared is None:
        return None
    rule, *items = declared.allocation
    if declared.capacity is None and declared.request is None and rule == 'proportional':
        return None
    allocation = (
        build.priority(*(build.X.read(_path(item)) for item in items[0]))
        if rule == 'priority'
        else build.proportional()
    )
    return build.endpoint(
        capacity=None if declared.capacity is None else initial(declared.capacity),
        request=None if declared.request is None else initial(declared.request),
        allocation=allocation,
    )


def _assertion(declared):
    return build.assertion(handle(declared.test))


def status_of(display):
    """The program's status display: its cases in written order, the last with no condition."""
    return build.status(
        *(
            build.rating(case.rating, None if case.test is None else handle(case.test))
            for case in display.cases
        )
    )


def initial(init):
    """An initializer as the builder takes it: a formula, a distribution, the path of a collection or
    of an occurrence (a reference to it), or an expression."""
    if isinstance(init, s.Retain):
        return build.formula(handle(init.body))
    if isinstance(init, s.Distribution):
        return distribution(init)
    if isinstance(init, s.Read) and isinstance(init.type, (s.Many, s.Occ)):
        return build.X.read(_path(init))
    return handle(init)


def distribution(found):
    """The program's distribution: a numeric family in one unit, or a categorical over its enum."""
    if found.family == 'categorical':
        return Distribution('categorical', found.params, enum=str(found.type.of), outcomes=found.outcomes)
    return Distribution(found.family, found.params, found.type.of.unit)


def _source(source):
    """What a draw or a choice reads: a distribution written in place, or the path of a value."""
    return distribution(source) if isinstance(source, s.Distribution) else _path(source)


# ---- events -----------------------------------------------------------------------------------------


def event_of(event):
    """The program's event: its parameters, its locals and flows in written order, its steps and its
    triggers (`build.event` keeps each group in its order)."""
    parts = [
        build.param(
            param.name,
            _type(param.type),
            lower=None if param.lower is None else handle(param.lower),
            upper=None if param.upper is None else handle(param.upper),
        )
        for param in event.params
    ]
    parts += [part_of(local) for local in event.locals]
    parts += [_timing(step) for step in event.steps]
    parts += [_trigger(trigger) for trigger in event.triggers]
    return build.event(event.name, *parts)


def _timing(step):
    if isinstance(step, s.DeclaredGate):
        return build.until(handle(step.test))
    guard = None if step.guard is None else handle(step.guard)
    return build.after(handle(step.delay), *_statements(step.body), when=guard)


def _trigger(trigger):
    reset = None
    if trigger.reset is not None:
        kind, expression = trigger.reset
        reset = (build.reset_when if kind == 'when' else build.reset_after)(handle(expression))
    captures = tuple(
        build.value(capture.name, _type(capture.type), handle(capture.init)) for capture in trigger.captures
    )
    return build.when(handle(trigger.test), *_statements(trigger.starts), captures=captures, reset=reset)


def _statements(body):
    return [_statement(item) for item in body]


def _statement(item):
    """The program's statement of a declared one: an assignment, a move, a start or a branch."""
    if isinstance(item, s.DeclaredAssign):
        make = {'=': build.assign, '+=': build.add, '-=': build.subtract}[item.op]
        return make(build.X.read(_path(item.target)), _assigned(item.value))
    if isinstance(item, s.DeclaredMove):
        ends = (build.X.read(_path(end)) for end in (item.source, item.destination))
        return build.move(handle(item.amount), *ends)
    if isinstance(item, s.DeclaredStart):
        return build.start(build.X.read(_path(item.event)), *(handle(arg) for arg in item.args))
    if isinstance(item, s.DeclaredIf):
        return build.if_(handle(item.test), _statements(item.then), _statements(item.orelse))
    cases = [
        build.case(
            case.member, *_statements(case.body), when=None if case.guard is None else handle(case.guard)
        )
        for case in item.cases
    ]
    return build.switch(handle(item.selector), *cases, orelse=_statements(item.orelse))


def _assigned(value):
    """An assigned value as the builder takes it: an allocation, or an initializer."""
    if isinstance(value, tuple):
        rule, *items = value
        if rule == 'priority':
            return build.priority(*(build.X.read(_path(item)) for item in items[0]))
        return build.proportional()
    return initial(value)


def flow_of(flow):
    """The program's flow of a declared directed flow, leg or reversible route (`build.route`). Its
    unit is the builder's to give: a rate written with its unit, or its store's unit per hour; a
    plain store's rate is `1/h`."""
    ends = [
        build.X.read(_path(end)) if isinstance(end, s.Read) else getattr(build, end)
        for end in (flow.source, flow.sink)
    ]
    settings = {
        key: None if setting is None else initial(setting)
        for key, setting in (('request', flow.request), ('capacity', flow.capacity))
    }
    unit = flow.rate.unit if flow.rate.unit == '1/h' else ''
    make = build.route if isinstance(flow, s.DeclaredRoute) else build.flow
    return make(flow.name, *ends, unit=unit, **settings)


# ---- solvers ----------------------------------------------------------------------------------------


def solver_of(solver):
    """The program's solver: its inputs (`build.given`, each the path of its source), the fields that
    it determines, its new unknowns (each with its domain, its preferred value and its scale), its
    constraints and its objectives, each group in written order. A bare name of a solver is
    `refs.Local`."""

    def optional(expression):
        return None if expression is None else handle(expression)

    parts = [build.given(item.name, build.X.read(_path(item.read))) for item in solver.inputs]
    parts += [build.solve_for(build.X.read(_path(entry))) for entry in solver.solve_for]
    parts += [
        build.unknown(
            value.name,
            _type(value.type),
            lower=optional(value.lower),
            upper=optional(value.upper),
            init=optional(value.init),
            scale=optional(value.scale),
        )
        for value in solver.unknowns
    ]
    parts += [build.constraint(handle(item.test)) for item in solver.constraints]
    parts += [getattr(build, item.sense)(handle(item.test)) for item in solver.objective]
    return build.solver(solver.name, *parts)


# ---- expressions ---------------------------------------------------------------------------------------


def _path(read):
    """The program's path of a read, from its start through its steps."""
    kind, *rest = read.start
    if kind == 'this':
        start = THIS
    elif kind == 'local':
        start = Local(rest[0])
    elif kind == 'named':
        start = Named(rest[0])
    elif kind == 'root':
        start = ROOT
    elif kind == 'item':
        start = ITEM
    elif kind == 'instances':
        start = Instances(rest[0])
    elif kind == 'literal':
        start = Literal(tuple(_path(item) for item in rest[0]))
    elif kind == 'where':
        start = Where(_path(rest[0]), build.expr_of(handle(rest[1])))
    elif kind == 'by':
        start = By(_path(rest[0]), rest[1])
    else:
        start = Lookup(_path(rest[0]), build.expr_of(handle(rest[1])))
    return Path(start, read.steps)


def handle(expression):
    """A handle (`build.X`) on the program's form of a typed expression."""
    reads = {}
    node = _node(expression, reads)
    return build.X(node, {name: read for read, name in reads.items()})


def _named(read, reads):
    """The name of a read in a node: its spelling, made distinct from another read's."""
    if read not in reads:
        name, k = spelled(read), 1
        while name in reads.values():
            name, k = f'{spelled(read)}#{k}', k + 1
        reads[read] = name
    return nodes.ref(reads[read])


def _number(value):
    """A number as the builder writes it: a fraction as the quotient of two whole numbers."""
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return nodes.written(value.numerator)
        return nodes.binary('div', nodes.written(value.numerator), nodes.const(value.denominator))
    return nodes.written(value)


def _node(item, reads):
    if isinstance(item, s.Const):
        if isinstance(item.type, s.EnumOf):
            return _named(EnumValue(str(item.type), item.value), reads)
        if isinstance(item.value, (bool, str)):
            return nodes.const(item.value)
        if isinstance(item.type, s.Num) and item.type.unit:
            return nodes.call('q', [_number(item.value), nodes.const(item.type.unit)])
        return _number(item.value)
    if isinstance(item, s.Read):
        return _named(TIME if item.start == ('time',) else _path(item), reads)
    if isinstance(item, s.Reduced):
        return _named(Reduce(item.op, _path(item.source)), reads)
    if isinstance(item, s.Drawn):
        # A temporary site, distinct for each draw, until `Builder.finish` gives the draw its place.
        return _named(Draw(_source(item.source), f'?lowered{next(_SITES)}'), reads)
    if isinstance(item, s.History):
        source = _path(item.source)
        if item.op == 'since':
            return _named(Since(source), reads)
        return _named(Elapsed(source), reads)
    args = [_node(arg, reads) for arg in item.args]
    if item.op in OPERATIONS:
        return nodes.binary(OPERATIONS[item.op], *args)
    if item.op in ('neg', 'not'):
        return nodes.unary(item.op, args[0])
    if item.op in ('and', 'or'):
        return nodes.boolean(item.op, args)
    if item.op == 'if':
        test, body, orelse = args
        return nodes.if_else(test, body, orelse)
    if item.op == 'compare':
        return nodes.compare([COMPARISONS[op] for op in item.detail], args)
    return nodes.call(item.detail, args)
