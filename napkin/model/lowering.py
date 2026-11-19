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
one is an `Expr` of its own. A number with a unit is the core's literal `q(number, unit)`; a bare
number that takes a unit is written with it. The settings of a store's outflow and inflow are its
`build.endpoint`; a side that sets nothing but `proportional()`, the default, is a side that sets
nothing, so the two texts are one program.

A part that a later slice brings is refused by name (`later_slice`), with the slice that brings it.
A refusal of the program's checker is given at the line of the declared part that it names, and so
is each of the setup's reports (`reports`), which refuse nothing.
"""

from __future__ import annotations

import itertools
from fractions import Fraction

from ..core import expr as nodes
from ..program import build, check
from ..program.check import ProgramError
from ..program.refs import (
    ITEM,
    ROOT,
    THIS,
    TIME,
    By,
    Distribution,
    Draw,
    Instances,
    Literal,
    Lookup,
    Named,
    Path,
    Reduce,
    Where,
    spelled,
)
from . import semantic as s
from .language.problems import LanguageError, Problem

_SITES = itertools.count()
# The core's names of the operations of the declared model.
OPERATIONS = {'add': 'add', 'sub': 'sub', 'mul': 'mul', 'div': 'div', 'pow': 'pow'}
COMPARISONS = {'<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge', '==': 'eq', '!=': 'ne'}


def refusal(part):
    """The diagnostic of a part that a later slice brings."""
    return Problem(
        'later_slice', f'{part.path}: {part.construct} comes with a later slice ({part.slice})', part.line
    )


def lower(model):
    """The program of a declared model, checked (`Builder.finish`). Raises `LanguageError` with each
    part that a later slice brings, or with each refusal of the checker."""
    if model.deferred:
        raise LanguageError([refusal(part) for part in model.deferred])
    builder = build.Builder(model.units.table)
    templates = {}
    for entity in model.entities:
        templates[entity.path] = entity
        parts = [part_of(part) for part in entity.parts]
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
    try:
        return builder.finish()
    except ProgramError as error:
        raise LanguageError([_located(model, item) for item in error.diagnostics]) from None


def reports(model, program):
    """The setup's reports of a lowered model (`check.reports`: equal keys in a view that `.at`
    reads, a lookup below its first key), each a `Problem` at the line of its part, which refuses
    nothing."""
    return tuple(_located(model, item) for item in check.reports(program))


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


def _type(kind):
    if isinstance(kind, s.Num):
        return kind.unit
    if isinstance(kind, s.Dist):
        return build.dist_of(kind.of.unit)
    return build.BOOL if kind == s.BOOL else build.TEXT


def part_of(part):
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


def initial(init):
    """An initializer as the builder takes it: a formula, a distribution, the path of a collection, or
    an expression."""
    if isinstance(init, s.Retain):
        return build.formula(handle(init.body))
    if isinstance(init, s.Distribution):
        return distribution(init)
    if isinstance(init, s.Read) and isinstance(init.type, s.Many):
        return build.X.read(_path(init))
    return handle(init)


def distribution(found):
    return Distribution(found.family, found.params, found.type.of.unit)


def flow_of(flow):
    """The program's flow of a declared directed flow. Its unit is the builder's to give: a rate
    written with its unit, or its store's unit per hour; a plain store's rate is `1/h`."""
    ends = [
        build.X.read(_path(end)) if isinstance(end, s.Read) else getattr(build, end)
        for end in (flow.source, flow.sink)
    ]
    settings = {
        key: None if setting is None else initial(setting)
        for key, setting in (('request', flow.request), ('capacity', flow.capacity))
    }
    unit = flow.rate.unit if flow.rate.unit == '1/h' else ''
    return build.flow(flow.name, *ends, unit=unit, **settings)


# ---- expressions ---------------------------------------------------------------------------------------


def _path(read):
    """The program's path of a read, from its start through its steps."""
    kind, *rest = read.start
    if kind == 'this':
        start = THIS
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
        return _named(Draw(distribution(item.source), f'?lowered{next(_SITES)}'), reads)
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
