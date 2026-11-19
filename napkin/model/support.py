"""The owner's evidence rule (item 16 of the plan's changes after G0): what a model warns of when it
gives no record.

Every choice of a model shows its support, a record (`@name`, or `@kind "explanation"` under its
line). The compiler warns of each part below that has none, the kinds for which the compiler before
the rewrite refused a model (`docs/language.md` 2.10 at commit 8488047). A model being explored still
runs; `tools.check` and the publisher refuse a scenario package with a warning of this kind.

- an input, but a text input;
- a stored number or yes/no of an entity, a template or the top level (a stock, a tally, a state); a
  yes/no rests on its thing's records when it has none of its own;
- an event that acts at a time, with a stage or a trigger;
- a case of a status display, which rests on its thing's records when it has none of its own;
- an assertion;
- a number, a yes/no or a distribution that a member written by hand gives as its own value;
- a column of a table that holds such values, whose records are in the column's header.

A text, a member of an enum, a link, a collection and a formula, which calculates, need none, as for
a value that an option or a `change` sets; that value's missing record is an error, not a warning
(R-A5-05, `semantic.Resolver.recorded`). An entity, a template and a member rest on nothing of their
own: their parts do. Each warning is a `Problem` with the code `no_record` at the line of the part,
and a column's at the header of its table's file.
"""

from __future__ import annotations

from . import semantic as s
from .language.problems import Problem

CODE = 'no_record'


def _needs(value):
    """Whether a value of this kind and type needs a record: a number, a yes/no or a distribution,
    and no formula."""
    typed = value.type.of if isinstance(value.type, s.Dist) else value.type
    numeric = isinstance(typed, s.Num) or typed == s.BOOL or isinstance(value.type, s.Dist)
    return numeric and value.kind != s.FORMULA


def _value(value, thing):
    """What a value of an entity, a template or the top level lacks, or None: `thing` is its
    entity's or template's declaration, None at the top level."""
    if value.evidence or not _needs(value):
        return None
    if value.kind == s.INPUT:
        return 'an input'
    if value.kind != s.STATE:
        return None
    if value.type == s.BOOL and thing is not None and thing.evidence:
        return None  # a yes/no rests on its thing's records
    return 'a stored value'


def _warning(path, what, line, file=''):
    return Problem(
        CODE, f'{path}: {what} rests on no record: cite one (@name) or write one under it', line, 0, file
    )


def unsupported(model):
    """The warnings of the parts of a declared model that rest on no record (see the module), in the
    order of the model: its entities and templates with their parts, its members, its tables, the
    values and assertions of its top level."""
    found = []
    for thing in model.entities:
        for part in thing.parts:
            if isinstance(part, s.DeclaredValue):
                what = _value(part, thing)
                if what is not None:
                    found.append(_warning(part.path, what, part.line))
            elif isinstance(part, s.DeclaredEvent):
                timed = part.triggers or any(isinstance(step, s.DeclaredStage) for step in part.steps)
                if timed and not part.evidence:
                    found.append(_warning(part.path, 'an event that acts at a time', part.line))
            elif isinstance(part, s.DeclaredAssert) and not part.evidence:
                found.append(_warning(part.path, 'an assertion', part.line))
        if thing.status is not None and not thing.evidence:
            for case in thing.status.cases:
                if not case.evidence:
                    found.append(_warning(case.path, 'a case of a status display', case.line))
    for member in model.members:
        if member.table is not None:
            continue
        for given in member.values:
            value = model.part(f'{member.template}.{given.name}')
            if isinstance(value, s.DeclaredValue) and _needs(value) and not given.evidence:
                found.append(_warning(f'{member.path}.{given.name}', "a member's own value", given.line))
    for table in model.tables:
        for column in table.columns:
            value = model.part(f'{table.template}.{column.name}')
            if isinstance(value, s.DeclaredValue) and _needs(value) and not column.cites:
                found.append(_warning(f'{table.path}.{column.name}', 'a column of a table', 1, table.origin))
    for value in model.root:
        what = _value(value, None)
        if what is not None:
            found.append(_warning(value.path, what, value.line))
    for check in model.asserts:
        if not check.evidence:
            found.append(_warning(check.path, 'an assertion', check.line))
    return tuple(found)
