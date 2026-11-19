"""Copy a record and its evidence dependencies between independent scenario, variant or family folders.

A copy takes the record's dependency closure (`napkin.model.evidence.dependencies`) and the units that
the copied records name: the unit of each datum, and each declared unit that a composed one is made of
(`tunings/tuner*year` reaches tunings, tuner and year). A record or a unit that the destination holds
with another meaning is a conflict that the author resolves by hand.
"""

import argparse
import copy
import sys
from collections.abc import Mapping
from pathlib import Path

from napkin.expressions import ExpressionError, UnitSystem
from napkin.model.evidence import dependencies
from napkin.model.library import load_library

from .. import catalogue
from ..catalogue import ROOT
from .integrate import IntegrationError, write_owned
from .trail import package_document


def adopt(source, destination, identifier):
    """Return a copied destination library; conflicting IDs require an explicit author edit."""
    matches = [
        (kind, record)
        for kind in ('claims', 'assumptions', 'sources')
        for record in source[kind]
        if record['id'] == identifier
    ]
    if len(matches) != 1:
        raise IntegrationError([f'Expected one source record named {identifier}; found {len(matches)}'])
    kind, _record = matches[0]
    if kind == 'sources':
        reached = {'claims': [], 'assumptions': [], 'sources': [identifier]}
    else:
        reached = dependencies({'claim' if kind == 'claims' else 'assumption': identifier}, source)
    result = copy.deepcopy(destination)
    copied = {}
    for collection in ('sources', 'claims', 'assumptions'):
        index = {r['id']: r for r in result[collection]}
        copied[collection] = [r for r in source[collection] if r['id'] in reached[collection]]
        for item in copied[collection]:
            old = index.get(item['id'])
            if old is not None and old != item:
                raise IntegrationError([f'Conflicting destination {collection} record {item["id"]}'])
            if old is None:
                result[collection].append(copy.deepcopy(item))
    # The units that the copied records name (the units of their data), which the destination keeps.
    for name, definition in declared_units(source['units'], unit_names(copied)).items():
        held = result['units'].get(name)
        if held is None:
            result['units'][name] = copy.deepcopy(definition)
        elif _meaning(held) != _meaning(definition):
            raise IntegrationError([f'Conflicting destination unit {name}'])
    return result


def unit_names(value):
    """The unit names that records name: each text of a `unit` key, at any depth."""
    if isinstance(value, Mapping):
        found = {value['unit']} if isinstance(value.get('unit'), str) else set()
        return found.union(*(unit_names(child) for child in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(unit_names(child) for child in value))
    return set()


def declared_units(units, names):
    """{name: definition} of the declared units of `units` that the unit names `names` reach, sorted by
    name: a declared name itself, and each declared unit that a composed name is made of
    (`UnitSystem.factors`). A name that is no unit reaches none."""
    registry = UnitSystem(units)
    found = set()
    for name in names:
        try:
            found.update(part for part, _ in registry.factors(name))
        except ExpressionError:
            continue
    return {name: copy.deepcopy(units[name]) for name in sorted(found)}


def _meaning(definition):
    """What a unit means: its definition without its description, which the destination keeps."""
    return {key: value for key, value in definition.items() if key != 'description'}


def reader_path(root, owner):
    """The model whose library holds the records of `owner`: the owner's own entry file (a scenario's or
    a variant's), or, for a family folder of modules (`SCnn`), the entry file of the first scenario that
    reads it (`catalogue.readers`)."""
    entries = catalogue.entries(root)
    if owner in entries:
        return entries[owner]
    readers = catalogue.readers(root).get(owner)
    if not readers:
        raise KeyError(f'No scenario reads the folder {owner}')
    return entries[readers[0]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from', dest='source', required=True)
    parser.add_argument('--to', dest='destination', required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--write', action='store_true', help='Apply the copy; default is a dry run')
    args = parser.parse_args(argv)
    try:
        src = reader_path(args.root, args.source)
        dst = reader_path(args.root, args.destination)
        source, destination = (
            load_library(path, document=package_document(path), allow_unused=True) for path in (src, dst)
        )
        copied = adopt(source, destination, args.id)
        if args.write:
            write_owned(dst, copied, folder=catalogue.locate(args.destination, args.root).folder)
        print(f'{args.id}: {args.source} -> {args.destination}; {"written" if args.write else "dry run"}')
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
