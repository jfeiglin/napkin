"""The types and the written numbers of the values of a model file (docs/language/values-and-types.md, "Types").

A type is a unit of the library (`duration` is hours, and braces name a text value of the entity:
`{item}/h`), `bool`, named values, or `text`. Every number has its unit: `72 h`, `3 days`,
`1000 people`. Only `0`, and a number of a dimensionless unit, can be bare. The value of an input or
a fixed value can also be a distribution: `pert(24 h, 72 h, 336 h)`, `bernoulli(0.3)` for a bool,
`categorical(low=0.7, high=0.3)` for named values. The front end, the builder and the runs read
numbers and units here, so that a value is read one way.
"""

from __future__ import annotations

import re

from ..distributions import FAMILIES

# The kinds of value whose number the run holds, and the engine's kind of each quantity.
QUANTITY_KINDS = {'stock': 'stock', 'tally': 'cumulative', 'state': 'variable'}
# The kinds of value whose start value a profile or an edit can set.
STARTS = ('state', 'stock', 'tally')
BOOL = 'bool'
# The unit of a type that is not a unit's own name.
TYPE_UNITS = {'duration': 'h'}
# The kind of type that the values of each kind of distribution have.
FAMILY_TYPES = {'number': 'unit', 'bool': 'bool', 'names': 'names'}
# A call of a family of distributions: `pert(24 h, 72 h, 336 h)`.
_CALL = re.compile(r'\s*([a-z]+)\s*\(.*\)\s*', re.DOTALL)
# A number and a unit in an expression, `48 h`; a compound unit joins names with `/` or `-`, and a
# name can have a whole power (`0 L/h`, `2 person-hours`, `5 m^2`).
_UNIT_NAME = r'[A-Za-z_][A-Za-z0-9_]*(?:\^-?[0-9]+)?'
_LITERAL = re.compile(
    r'(?<![\w.\'"])(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+'
    rf'({_UNIT_NAME}(?:[/-]{_UNIT_NAME})*)(?![\w(.\'"])'
)
# Where a compound unit can end: before a `/`, or before a `-` that is not the sign of a power.
_UNIT_END = re.compile(r'(?=/)|(?=(?<!\^)-)')
# A number as the language reads one, then the unit that it is in.
_INT = re.compile(r'-?(?:0|[1-9][0-9]*)')
_NUMBER = r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?'
_QUANTITY = re.compile(rf'\s*({_NUMBER})\s+(\S+)\s*')


def family_of(written):
    """The family of a written distribution, `pert(24 h, 72 h, 336 h)`, or None for anything else.
    A name of a named value never holds a parenthesis, so a text is one or the other."""
    match = _CALL.fullmatch(written) if isinstance(written, str) else None
    return match.group(1) if match and match.group(1) in FAMILIES else None


def family_type(family):
    """The kind of type (`unit`, `bool` or `names`) whose values a family of distributions gives."""
    return FAMILY_TYPES[FAMILIES[family].kind]


def engine_number(value):
    """The engine's number of a bool: 1 or 0."""
    return 1 if value else 0


def type_unit(written):
    """The unit of a written unit type, before its braces are filled: `duration` is `h`."""
    return TYPE_UNITS.get(written, written)


def is_number(value):
    """A number that is not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def quantity(written):
    """(number, unit) of a number written with its unit, `72 h`, or None. The number reads as the
    language reads a number: an int without a point or an exponent, else a float."""
    match = _QUANTITY.fullmatch(written) if isinstance(written, str) else None
    if match is None:
        return None
    text, unit = match.groups()
    return (int(text) if _INT.fullmatch(text) else float(text)), unit


class UnitProblem(ValueError):
    """A number that its value cannot take, with the reason."""


def number_in(written, unit, units, fill=lambda text: text):
    """The number of a written value in `unit`, a library unit: `72 h` in `h` is 72, `3 days` is 72,
    and `0` is 0 in any unit. A bare number is a number of `unit` only when `unit` is dimensionless.

    `units` is a `UnitSystem` (or a registry with `parse_unit`). `fill` fills the braces of a written
    unit (`{item}/h`) as the value's type fills its own. A number in the value's own unit keeps its
    value bit for bit. Raises `UnitProblem`."""
    if is_number(written):
        if written == 0:
            return written
        if not units.parse_unit(unit).dimensions:
            return written
        raise UnitProblem(f'write the unit of the number: {written} {unit}')
    found = quantity(written)
    if found is None:
        raise UnitProblem(f'a value is a number with its unit, such as 72 h, not {written!r}')
    number, given = found
    given = fill(type_unit(given))
    if given == unit:
        return number
    target, source = units.parse_unit(unit), units.parse_unit(given)
    if not source.compatible(target):
        raise UnitProblem(f'{written!r} is not in a unit of {unit}')
    return number * source.scale / target.scale


def literal_quantities(text, unit_names, spaced=False):
    """Each number with a unit in an expression, as `q(number, 'unit')`: the longest unit of
    `unit_names` that the names after the number spell (`0 L/h`; in `2 h/self.x` the unit is `h`).
    `unit_names` is anything that `in` asks: a set of names, or a `UnitSystem`, whose units include the
    compositions of its declared units.

    With `spaced`, the expression stays as the language writes it, and a space ends each unit where
    the word goes on: `2 h/self.x` is `2 h /self.x`. The language reads the whole word after a number
    as its unit, so this is the same expression for a reader of the language."""

    def replace(match):
        number, unit = match.groups()
        parts = _UNIT_END.split(unit)
        for k in range(len(parts), 0, -1):
            name = ''.join(parts[:k])
            if name in unit_names:
                rest = ''.join(parts[k:])
                if spaced:
                    # The language takes the word after a number as its unit, up to a space, a
                    # comma, a bracket, a colon or a bar: a space ends the unit before anything else.
                    after = rest or match.string[match.end() : match.end() + 1]
                    return (
                        f'{number} {name} {rest}'
                        if after and after[0] not in ' \t\n,()[]:|'
                        else match.group(0)
                    )
                return f'q({number}, {name!r})' + rest
        return match.group(0)

    return _LITERAL.sub(replace, text)


# A text value of its own entity, which braces name in a unit or a distribution: `{item}/h`.
OWN_TEXT = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')


def time_units(units):
    """{unit: hours in one unit} of the units of time of a unit table (the library's `units`)."""
    return {
        name: spec.get('scale', 1)
        for name, spec in (units or {}).items()
        if dict(spec.get('dimensions') or {}) == {'time': 1}
    }


def hours(value, units=None):
    """The number of hours of a time written with its unit (`24 h`, `3 days`, any unit of time that
    `units`, from `time_units`, lists), or of `0`; None for anything else."""
    if is_number(value):
        return value if value == 0 else None
    found = quantity(value)
    if found is None:
        return None
    number, unit = found
    scale = (units or {'h': 1}).get(unit)
    if scale is None:
        return None
    value = number * scale
    return int(value) if float(value).is_integer() else value


def written_unit(written, text):
    """The unit that a `type` writes: each `{name}` is `text(name)`, the value of that text value of
    the entity, and `duration` is hours. A brace that names anything else is a ValueError: a unit
    names a text value of its own entity (docs/language/values-and-types.md, "Types")."""
    unit = OWN_TEXT.sub(lambda match: text(match.group(1)), written)
    if '{' in unit or '}' in unit:
        raise ValueError('a unit names a text value of its own entity in braces: {item}')
    return TYPE_UNITS.get(unit, unit)
