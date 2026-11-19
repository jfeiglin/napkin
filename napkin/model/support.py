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

A value that its record ties to a datum of a claim (`claims:` with `datum: key`) is that number
(`cited_data`, code `datum`): a number fixed when the model compiles (written out, or arithmetic of
such numbers), equal to the datum in dimension and scale, both read exactly (`semantic.exact_value`,
`core.units.rational`), so `0.1 day` is the datum 2.4 h and `48 people/day` the datum 2 people/h. A
datum states a number and a unit and no precision, so a value near it is not it: any other value
needs a derivation, a transfer or an assumption (`docs/language.md` 2.10 at commit 8488047, where a
difference was an error). A difference is a warning with both numbers: a model being explored still
runs, and `tools.check` refuses a package with one, as it does one with a value that rests on no
record.
The values are those of the entities, the templates and the top level, the members' own values and
cells, and the settings of the options.
"""

from __future__ import annotations

from fractions import Fraction

from ..core.errors import ExpressionError
from ..core.units import UnitSystem, rational
from . import semantic as s
from .language import nodes as n
from .language.problems import Problem

CODE = 'no_record'
DATUM = 'datum'


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


# ---- a value and the datum that its record cites ------------------------------------------------------


def _datum_unit(spelling, units, registry):
    """(dimension, exact scale) of the unit of a datum: a spelling of the model's units (`L/h`,
    `person*year`), or one in the library's notation, whose products join with `-` and powers with `^`
    (`gal/person-day`); None when it names no unit."""
    found = units.of(spelling)
    if found is not None:
        return found
    try:
        factors = registry.factors(spelling)
    except ExpressionError:
        return None
    dimension, scale = {}, Fraction(1)
    for name, power in factors:
        own = units.of(name)
        if own is None:
            return None
        for key, value in own[0]:
            dimension[key] = dimension.get(key, 0) + value * power
        scale *= own[1] ** power
    return tuple(sorted((key, value) for key, value in dimension.items() if value)), scale


def _written(number):
    """A datum's number as its file writes it: `34`, `34.0`, `0.48`."""
    return str(number) if isinstance(number, int) else float.__repr__(float(number))


def _number(value):
    """A rational for a message, as a decimal: `34`, `0.48`, `2.4`."""
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return format(float(value), '.12g')


def cited_data(model, library):
    """The warnings of the values of a declared model that differ from a datum that their records
    cite (see the module), each a `Problem` with the code `datum` at the line of the value, naming the
    value and the datum with both numbers. `library` is the model's library (`library.load_library`),
    whose claims hold the data; a datum that the library does not hold is its own diagnostic
    (`evidence.basis_errors`)."""
    claims = {claim['id']: claim for claim in library.get('claims', ())}
    records = {record.name: record for record in model.records}
    registry = UnitSystem(library.get('units', {}))
    found = []

    def cited(evidence):
        """(how the value cites the record, its claim, the key of the datum) of each datum that the
        records of a value name."""
        for item in evidence:
            record = records.get(item.name) if isinstance(item, n.Cite) else item
            label = f'@{item.name}' if isinstance(item, n.Cite) else 'its record'
            for claim in getattr(record, 'claims', ()):
                if claim.datum:
                    yield label, claim.id, claim.datum

    def check(path, value, evidence, line, file=''):
        if not isinstance(getattr(value, 'type', None), s.Num) or not evidence:
            return
        at = s.exact_value(value, model.units)
        if at is None:
            return
        for label, claim, key in cited(evidence):
            datum = claims.get(claim, {}).get('data', {}).get(key)
            unit = None if datum is None else _datum_unit(datum['unit'], model.units, registry)
            if unit is None:
                continue
            stated = rational(datum['value']) * unit[1]
            if unit[0] == value.type.dimension and at == stated:
                continue
            scale = model.units.of(value.type.unit)[1] if value.type.unit else 1
            written = f'{_number(at / scale)} {value.type.unit}'.strip()
            datum_written = f'{_written(datum["value"])} {datum["unit"]}'
            if unit[0] != value.type.dimension:
                why = f'{written} is of another dimension'
            else:
                why = f'{written} differs from it'
            message = f'{path}: {label} cites the datum {key} of {claim}, {datum_written}, and {why}'
            found.append(Problem(DATUM, message, line, 0, file))

    for thing in model.entities:
        for part in thing.parts:
            if isinstance(part, s.DeclaredValue) and part.kind in (s.INPUT, s.STATE):
                check(part.path, part.init, part.evidence, part.line)
    for member in model.members:
        for given in member.values:
            check(f'{member.path}.{given.name}', given.init, given.evidence, given.line, member.file)
    for value in model.root:
        if value.kind in (s.INPUT, s.STATE):
            check(value.path, value.init, value.evidence, value.line)
    for option in model.options:
        for setting in option.settings:
            check(setting.path, setting.value, setting.evidence, setting.line)
    return tuple(found)
