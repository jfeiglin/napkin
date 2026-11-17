"""Write a complete independent scenario fixture using the authored library partition."""

import copy
import json

from napkin.model.evidence import dependencies
from napkin.model.identity import COLLECTIONS
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.library import prelude_units
from napkin.model.model import build_model
from napkin.model.semantic import path_text
from napkin.paths import entry
from tests.build import UNITS, compiled, library
from tools import catalogue

PRELUDE = prelude_units()


def vocabulary_of(evidence):
    """The shared vocabulary that the test library `evidence` writes, as a `vocabulary.json`: the units of
    the standard test library (`tests.build.UNITS`) that the prelude does not hold, its conventions, and
    the records that the conventions rest on, with their dependencies. Every other unit of `evidence`, apart from the
    prelude's, and every other record are the folder's own."""
    shared = dependencies({'conventions': evidence.get('conventions', [])}, evidence)
    return {
        'schema_version': '0.0.1',
        'id': 'vocabulary',
        'title': 'Shared vocabulary',
        **({'conventions': copy.deepcopy(evidence['conventions'])} if 'conventions' in evidence else {}),
        'units': {
            name: copy.deepcopy(unit)
            for name, unit in evidence['units'].items()
            if name in UNITS and name not in PRELUDE
        },
        **{
            collection: [
                copy.deepcopy(record)
                for record in evidence.get(collection, ())
                if record['id'] in set(shared[collection])
            ]
            for collection in COLLECTIONS
        },
    }


def own_units(evidence, vocabulary):
    """The units of the test library `evidence` that a folder owns: neither the prelude's nor the shared
    vocabulary's."""
    return {
        name: copy.deepcopy(unit)
        for name, unit in evidence['units'].items()
        if name not in vocabulary['units'] and name not in PRELUDE
    }


def write_scenario(root, text, evidence=None, *, owner='SC99', style=None, brief=None):
    """(the entry file, its model): the folder of a catalogue scenario with the model file `text`, its
    stylesheet `style` (`style.toml`) and its brief settings `brief` (`brief.toml`) when they are given,
    its units and its own evidence. The folder is the owner's (`tools.catalogue.locate`): the reserved
    fake package `SC99` by default, or `owner`, such as a variant `SC97:east`."""
    evidence = library() if evidence is None else evidence
    model = compiled(text, evidence)
    vocabulary = vocabulary_of(evidence)
    path = entry(catalogue.locate(owner, root).folder)
    values = {
        root / catalogue.LIBRARY / 'vocabulary.json': vocabulary,
        path.parent / 'units.json': own_units(evidence, vocabulary),
    }
    for collection in COLLECTIONS:
        shared = {record['id'] for record in vocabulary[collection]}
        values[path.parent / 'evidence' / f'{collection}.json'] = [
            record for record in model.library[collection] if record['id'] not in shared
        ]
    for destination, value in values.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(thaw(value)), encoding='utf-8')
    path.write_text(text, encoding='utf-8')
    for name, written in (('style.toml', style), ('brief.toml', brief)):
        if written is not None:
            path.with_name(name).write_text(written, encoding='utf-8')
    return path, build_model(path)


def write_family(root, files, evidence=None):
    """{name: path} of the files of a family of scenarios and modules written below `root/scenarios`,
    from `files` {path below scenarios/: text}, with the shared vocabulary of `evidence` (by default the
    test library), the units that it leaves out in the folder of the first file, and empty units and
    evidence in each other folder."""
    evidence = library() if evidence is None else evidence
    vocabulary = vocabulary_of(evidence)
    (root / catalogue.LIBRARY).mkdir(parents=True, exist_ok=True)
    (root / catalogue.LIBRARY / 'vocabulary.json').write_text(json.dumps(thaw(vocabulary)), encoding='utf-8')
    local = own_units(evidence, vocabulary)
    written, folders = {}, []
    for relative, text in files.items():
        path = root / catalogue.SCENARIOS / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        written[relative] = path
        if path.parent not in folders:
            folders.append(path.parent)
    for k, folder in enumerate(folders):
        (folder / 'units.json').write_text(json.dumps(thaw(local) if k == 0 else {}), encoding='utf-8')
        (folder / 'evidence').mkdir(exist_ok=True)
        for collection in COLLECTIONS:
            (folder / 'evidence' / f'{collection}.json').write_text('[]', encoding='utf-8')
    return written


def block_at(text, place):
    """The rows of the line of a model file at `place` (its text, `semantic.path_text`) and of the
    lines under it, or None when no line of the file has that place. A line goes on while a bracket or
    a text that it opens is open."""
    lines = {path_text(where): number for where, number in front.read(text, 'model.scn').lines.items()}
    if place not in lines:
        return None
    rows = text.split('\n')
    start = lines[place] - 1
    open_ = {'depth': 0, 'text': False}

    def indent(row):
        return len(row) - len(row.lstrip(' '))

    def scan(row):
        if not open_['text'] and row.lstrip().startswith('#'):
            return
        for char in row:
            if char == '"':
                open_['text'] = not open_['text']
            elif not open_['text'] and char in '([{':
                open_['depth'] += 1
            elif not open_['text'] and char in ')]}':
                open_['depth'] -= 1

    scan(rows[start])
    end = start + 1
    while end < len(rows) and (
        open_['depth'] > 0
        or open_['text']
        or not rows[end].strip()
        or indent(rows[end]) > indent(rows[start])
    ):
        scan(rows[end])
        end += 1
    return '\n'.join(rows[start:end])
