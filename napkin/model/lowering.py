"""The lowering: a declared model (`semantic.py`) written as a program, through `napkin.program.build`.

Each entity written once is a template of one member with its name; its values and flows are the
template's, the values of the top level are the root's, and `Builder.finish` gives each part its
origin, which is the path of the declared part it comes from. An expression is written as a node of
`napkin/core/expr` with the read of each of its names (`refs.Path`, `refs.TIME`), the form in which
the builder's own handles write it, so a source text and the program that a test builds by hand have
the same canonical bytes. A number with a unit is the core's literal `q(number, unit)`; a bare number
that takes a unit is written with it.

A part that a later slice brings is refused by name (`later_slice`), with the slice that brings it.
A refusal of the program's checker is given at the line of the declared part that it names.
"""

from __future__ import annotations

import itertools
from fractions import Fraction

from ..core import expr as nodes
from ..program import build
from ..program.check import ProgramError
from ..program.refs import ROOT, THIS, TIME, Distribution, Draw, Named, Path, spelled
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
    for entity in model.entities:
        builder.entity(entity.path, *(part_of(part) for part in entity.parts))
    builder.root(*(value_of(value) for value in model.root))
    try:
        return builder.finish()
    except ProgramError as error:
        raise LanguageError([_located(model, item) for item in error.diagnostics]) from None


def _located(model, item):
    """A refusal of the checker at the line of the declared part whose path is its origin, or a part
    above it (`tank.water.outflow` is about `tank.water`)."""
    path = item.part
    while path and model.part(path) is None:
        path = path.rpartition('.')[0]
    found = model.part(path) if path else None
    return Problem(item.code, f'{item.part}: {item.message}', getattr(found, 'line', 0))


# ---- parts ------------------------------------------------------------------------------------------


def _type(kind):
    if isinstance(kind, s.Num):
        return kind.unit
    if isinstance(kind, s.Dist):
        return build.dist_of(kind.of.unit)
    return build.BOOL if kind == s.BOOL else build.TEXT


def part_of(part):
    return value_of(part) if isinstance(part, s.DeclaredValue) else flow_of(part)


def value_of(value):
    """The program's value of a declared value."""
    bounds = {
        'lower': None if value.lower is None else handle(value.lower),
        'upper': None if value.upper is None else handle(value.upper),
        'scale': None if value.scale is None else handle(value.scale),
    }
    init = initial(value.init)
    if value.kind == s.INPUT:
        return build.input_(value.name, _type(value.type), init, **bounds)
    return build.value(value.name, _type(value.type), init, readonly=value.readonly, **bounds)


def initial(init):
    if isinstance(init, s.Retain):
        return build.formula(handle(init.body))
    if isinstance(init, s.Distribution):
        return distribution(init)
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
    start = read.start[0]
    if start == 'this':
        return Path(THIS, read.steps)
    if start == 'named':
        return Path(Named(read.start[1]), read.steps)
    return Path(ROOT, read.steps)


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
