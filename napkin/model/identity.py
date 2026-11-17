"""What the hashes of a model cover: the content that the model reaches (docs/python-api.md).

The model hash covers the meaning of the files of a model, the units that it uses, the records that it
reaches and the version of the language. It covers no name, path or storage label: not the names of
the package and its variants, not the folder of the library, and no unit or record of the library that
the model does not reach. So a rename keeps the hash, a new variant leaves the hashes of its siblings,
and a unit that a later prelude adds changes no hash. The library hash covers the same units and
records. Only the hashed form sorts the records; the order of the compiler is untouched.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping

from ..expressions import ExpressionError, UnitSystem
from .evidence import dependencies, digest

# The record collections of a folder's evidence; a library also holds conventions, which its own file
# declares (`vocabulary.json`).
COLLECTIONS = ('sources', 'claims', 'assumptions')
RECORDS = (*COLLECTIONS, 'conventions')
# A number with its unit in an expression of a structure: `q(24, 'h')`.
_QUANTITY = re.compile(r"\bq\(\s*[^,()]+,\s*'([^']+)'\s*\)")


def unit_names(value):
    """The unit names that a part of a model names: each text of a `unit` or a `type` key, and the
    unit of each number that an expression writes (`q(24, 'h')`)."""
    found = set()

    def walk(item, key=None):
        if isinstance(item, Mapping):
            for name, child in item.items():
                walk(child, name)
        elif isinstance(item, (list, tuple)):
            for child in item:
                walk(child, key)
        elif isinstance(item, str):
            if key in ('unit', 'type'):
                found.add(item)
            found.update(_QUANTITY.findall(item))

    walk(value)
    return found


def declared_units(units, names):
    """{name: definition} of the declared units of `units` that the unit names `names` reach, sorted by
    name: a declared name itself, and each declared unit that a composed name is made of
    (`expressions.UnitRegistry.factors`: `tunings/tuner-year` reaches tunings, tuner and year). A name
    that is no unit, such as a type `bool`, reaches none."""
    registry = UnitSystem(units)
    found = set()
    for name in names:
        try:
            found.update(part for part, _ in registry.factors(name))
        except ExpressionError:
            continue
    return {name: copy.deepcopy(units[name]) for name in sorted(found)}


def reached(document, library, *, types=(), structures=()):
    """(the library of a model: every unit of `library`, which a value or an edit may write, and the
    records that the model reaches, in the order of `library`; what the hashes of the model cover: those
    records and the units that the model uses).

    `document` is what the evidence walkers read of the model's files (its records and the units that
    they write); `types` and `structures` are what the build makes of them: the types of its values,
    as plain data, and its structures (`structure.Structure`), whose plain data is read
    (`Structure.plain`: the text of each expression, as the lowering writes it). The model uses each
    unit that they name, and each unit of the data of the records that it reaches."""
    found = dependencies(document, library)
    records = {
        collection: [
            copy.deepcopy(record)
            for record in library.get(collection, ())
            if record['id'] in set(found[collection])
        ]
        for collection in RECORDS
        if collection in library or collection in COLLECTIONS
    }
    effective = {**copy.deepcopy(dict(library)), **records}
    names = unit_names(document) | unit_names(types) | unit_names(records)
    for structure in structures:
        names |= unit_names(structure.plain())
    return effective, {'units': declared_units(library['units'], names), **copy.deepcopy(records)}


def library_content(library):
    """What a hash covers of a library: its units and its records, each collection sorted by ID; its
    other keys, such as its ID, title and metadata, are storage labels."""
    result = {'units': copy.deepcopy(dict(library['units']))}
    for collection in RECORDS:
        if collection not in library and collection not in COLLECTIONS:
            continue
        result[collection] = sorted(
            copy.deepcopy(list(library.get(collection, ()))), key=lambda record: record['id']
        )
    return result


def model_identity(document, library, language):
    """Hash authored model and effective scenario content and the version of the language, never
    implementation bytes or the version of the package."""
    return digest({'document': document, 'library': library_content(library), 'language': language})
