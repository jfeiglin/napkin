"""The library of a model: the prelude's units, the library that its main file names, and the units and
evidence of the folders of its package (docs/language.md, §2.12).

Units and evidence come, in this order, from the prelude (`napkin/std/units.json`), which every model
has; from the library that the main file's `library "PATH"` line names (`vocabulary.json` of that
folder), or none; then from the package's folder (`units.json` and `evidence/`); then, for a variant,
from the variant's folder. Every one of these files is optional: a model whose main file names no
library has the prelude's units and no records of a library. A name of the prelude cannot be
redefined, and a unit or a record is in one folder only. The library and the prelude are checked
together, so a record of the library can read a unit of the prelude.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path

from .evidence import basis_errors, dependencies, library_checks
from .identity import COLLECTIONS
from .ir import ModelError, diagnostic
from .load import load_json, schema_document, schema_errors

# The prelude: the units that every model has. Its names cannot be redefined, and it grows only in a
# major version of the language.
PRELUDE = Path(__file__).resolve().parents[1] / 'std' / 'units.json'
_PRELUDE_UNITS = load_json(PRELUDE)
# The version of the library's own format, as its schema states it.
LIBRARY_VERSION = schema_document('library')['properties']['schema_version']['const']


def prelude_units():
    """The units of the prelude, {name: definition}, in the order of its file: a copy."""
    return copy.deepcopy(_PRELUDE_UNITS)


def empty_library():
    """The library of a model whose main file names none: the prelude's units, and no records."""
    return {
        'schema_version': LIBRARY_VERSION,
        'id': 'prelude',
        'title': 'The prelude',
        'units': prelude_units(),
        'sources': [],
        'claims': [],
        'assumptions': [],
    }


def catalogue_root(model_path):
    """The folder that holds `scenarios/` for a model file below `scenarios/`: the root of a checkout of
    the catalogue."""
    path = Path(model_path)
    for parent in (*path.parents, *path.resolve().parents):
        if parent.name == 'scenarios':
            return parent.parent
    return path.parent.parent.parent


def vocabulary_path(model_path):
    """The library file of the model of the entry file `model_path`: `vocabulary.json` in the folder that
    the `library "PATH"` line of its package's main file names, from that file's folder; None when the
    main file names no library."""
    from .language.modules import library_line

    main, folder = library_line(model_path)
    return None if folder is None else Path(main).parent / folder / 'vocabulary.json'


def library_folders(model_path):
    """The folders whose units and evidence belong to the library of a model, as resolved paths: the
    folder of its package and, for a variant, the variant's folder (`language.modules`). A module's
    folder inside the package adds none."""
    from .language.modules import package_of, role_of

    path = Path(model_path)
    try:
        role = role_of(path.read_text(encoding='utf-8'))
    except OSError:
        role = 'module'
    package = package_of(path, role)
    folders = [(package or path.parent).resolve()]
    if role == 'variant' and package is not None:
        folders.append(path.parent.resolve())
    return folders


def folder_files(folder):
    """The units file and the evidence files of one folder, whether or not they are there."""
    return (
        folder / 'units.json',
        *(folder / 'evidence' / f'{collection}.json' for collection in COLLECTIONS),
    )


def folder_records(folder):
    """The units and the evidence records that one folder owns: {'units': {...}, collection: [...]}. A
    file that is not there holds none."""
    units_path, *record_paths = folder_files(Path(folder))
    out = {'units': load_json(units_path) if units_path.is_file() else {}}
    for collection, path in zip(COLLECTIONS, record_paths):
        out[collection] = load_json(path, evidence=collection == 'claims') if path.is_file() else []
    return out


def library_files(model_path):
    """The authored files whose contents define one model's library: the library file that its
    `library` line names, and the units and evidence files of the folders of its library
    (`library_folders`) that are there. The prelude is a file of the package (`PRELUDE`)."""
    vocabulary = vocabulary_path(model_path)
    return (
        *((vocabulary,) if vocabulary is not None else ()),
        *(path for folder in library_folders(model_path) for path in folder_files(folder) if path.is_file()),
    )


def source_files(model_path):
    """Every file that a model reads: its own files (the scenario file and the modules that it uses),
    the prelude and its library files."""
    from .language.modules import paths

    return (*paths(model_path), PRELUDE, *library_files(model_path))


def with_prelude(library, where='library'):
    """(the library `library` with the prelude's units first, then its own; the diagnostics of each unit
    of its own that redefines a name of the prelude)."""
    units = library.get('units', {}) if isinstance(library, Mapping) else {}
    errors = [
        diagnostic(
            'unit_collision',
            f'{where}/units/{name}',
            f'The unit {name} is a unit of the prelude, which a library cannot redefine',
        )
        for name in (units if isinstance(units, Mapping) else {})
        if name in _PRELUDE_UNITS
    ]
    if not isinstance(library, Mapping) or not isinstance(units, Mapping):
        return library, errors
    return {**library, 'units': {**prelude_units(), **copy.deepcopy(dict(units))}}, errors


def read_vocabulary(path):
    """The library of the file `path` (a `vocabulary.json`), with the prelude's units first, checked
    together with them: a record of the library can read a unit of the prelude, and no unit of the
    library redefines a name of the prelude."""
    library, errors = with_prelude(load_json(Path(path), evidence=True))
    if not errors:
        errors, _ = library_checks(library)
    if errors:
        raise ModelError([{**item, 'file': Path(path).as_posix()} for item in errors])
    return library


def shared_library(model_path):
    """The library that the main file of the model of the entry file `model_path` names, with the
    prelude's units first (`read_vocabulary`); without a `library` line, the prelude alone
    (`empty_library`)."""
    path = vocabulary_path(model_path)
    return read_vocabulary(path) if path is not None else empty_library()


def model_document(path):
    """What the evidence walkers read of a model: its records, by the path of each line that has
    evidence (`language.evidence.document`), from every file that the model reads, as the compiler
    reads them (`language.modules.files`, `compile.merged`): the modules that it uses and, for a
    variant, its package's main file."""
    from .compile import merged
    from .language.evidence import document
    from .language.modules import files
    from .language.parse import parse

    return document(merged([parse(text) for _, text in files(Path(path)).files])[0])


def load_library(model_path, *, document=None, allow_unused=False, references=True):
    """The complete effective library of a model: the prelude's units, the library that its `library`
    line names (`shared_library`), then the units and evidence of the folders of its library
    (`library_folders`), each file optional.

    Normal loading rejects missing records, and records of the scenario's own folder that it does not
    use. Evidence authoring may temporarily allow unused records while adopting or drafting them;
    compilation and publication do not. The evidence writer reads the library without the model's
    references (`references=False`): it checks them on the library that it writes, which may add the
    records that the model cites (`tools.evidence.integrate`).
    """
    model_path = Path(model_path)
    library = copy.deepcopy(shared_library(model_path))
    shared = set(library['units'])
    owners, errors, local = {}, [], {}
    for folder in library_folders(model_path):
        records = folder_records(folder)
        local_units = records.pop('units')
        errors += schema_errors(local_units, 'scenario-units')
        if isinstance(local_units, Mapping):
            for name in local_units:
                if name in _PRELUDE_UNITS:
                    message = f'The unit {name} is a unit of the prelude, which a units file cannot redefine'
                elif name in shared:
                    message = 'A local unit may not reuse a shared name'
                elif name in owners:
                    message = (
                        f'The unit {name} is defined in {owners[name].as_posix()} and in {folder.as_posix()}'
                    )
                else:
                    continue
                errors.append(diagnostic('unit_collision', f'units/{name}', message))
            owners.update(dict.fromkeys(local_units, folder))
        if errors:
            raise ModelError(errors)
        for collection, items in records.items():
            if not isinstance(items, list) or any(not isinstance(record, Mapping) for record in items):
                errors.append(
                    diagnostic(
                        'schema', f'evidence/{collection}', 'Evidence records must be an array of objects'
                    )
                )
        if errors:
            raise ModelError(errors)
        library['units'].update(local_units)
        for collection in COLLECTIONS:
            library[collection].extend(records[collection])
        if folder == model_path.parent.resolve():
            local = records
    errors, _ = library_checks(library)
    if errors:
        raise ModelError(errors)
    if not references:
        return library
    document = model_document(model_path) if document is None else document
    errors = basis_errors(document, library)
    if not allow_unused:
        # The records of the scenario's own folder; a folder of modules that several scenarios use has
        # its records checked over all of them (`unused_shared_records`).
        reached = dependencies(document, library)
        for collection, records in local.items():
            used = set(reached[collection])
            errors.extend(
                diagnostic(
                    'unused_evidence',
                    f'evidence/{collection}/{record["id"]}',
                    'Local record is not used by this scenario',
                )
                for record in records
                if record['id'] not in used
            )
    if errors:
        raise ModelError(errors)
    return library


def unused_shared_records(package):
    """The diagnostics of the records of the folder of the package `package` that none of its variants
    reaches: a package with variants runs as its variants, so each record of its folder must be used by
    one of them at least, as each model's own records are used by it (`load_library`). A package
    without variants checks its own records when its model loads, so it has none here. The check reads
    the package and its variants only."""
    from ..paths import variants

    folder = Path(package).resolve()
    readers = list(variants(folder).values())
    if not readers:
        return []
    reached = {collection: set() for collection in COLLECTIONS}
    for path in readers:
        found = dependencies(model_document(path), load_library(path, allow_unused=True))
        for collection in COLLECTIONS:
            reached[collection] |= set(found[collection])
    owned = folder_records(folder)
    return [
        diagnostic(
            'unused_evidence',
            f'{folder.name}/evidence/{collection}/{record["id"]}',
            'Local record is used by no scenario that reads this folder',
        )
        for collection in COLLECTIONS
        for record in owned[collection]
        if record['id'] not in reached[collection]
    ]
