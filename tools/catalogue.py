"""The one locator of the catalogue: its owners, and the files of each owner.

The catalogue is the folder `scenarios/` of the checkout. An owner is a folder of it that owns a model,
evidence or results:

- a package: a folder `scenarios/<package>/` named as a package (`PACKAGE`: `water_wipe`, or a test's
  reserved ID such as `SC97`), with its entry file `model.scn` (`napkin.paths.entry`); the owner is the
  name of the folder. The catalogue's own folders (`RESERVED`: its library, its docs and its central
  tests) are no packages;
- a variant of a package: a folder `scenarios/<package>/variants/<name>/` with an entry file of its own
  (`napkin.paths.variants`); the owner is `<package>:<name>`;
- a package's folder that runs as no model of its own: an owner only when the model of a variant reads
  it (`napkin.model.library.library_folders`), with no entry file. A package with variants runs as its
  variants, because its main file is part of each variant's model; a package's folder without a main
  file has variants or is no owner. A `use` line names a module of the model's own package, so the model
  of an owner reads no other folder.

Each owner keeps its units (`units.json`), its evidence (`evidence/`) and its results (`results/`) in
its folder. The owners come in the catalogue's order: the packages without variants and the variants,
by the names of their folders, each package's variants by name; then each package's folder that runs as
no model of its own and that a variant reads.

The readers of an owner are the owners whose models read a file of its folder: the owner itself when it
has an entry file, and, for a package, its variants, which read its main file and its modules. Every
tool that finds the catalogue's owners, their files or the owner of a path asks this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from napkin import paths

# The checkout of the catalogue: the folder that holds `tools/`, which no wheel ships.
ROOT = Path(__file__).resolve().parents[1]
# The catalogue's folder in the checkout, and the folder of its shared library in it, which each main
# file of the catalogue names (`library "../library"`).
SCENARIOS = 'scenarios'
LIBRARY = f'{SCENARIOS}/library'
# The catalogue's own docs (its rules, its guides and the evidence guides) and its index, the table of
# the briefs that the publisher writes.
DOCS = f'{SCENARIOS}/docs'
INDEX = f'{SCENARIOS}/README.md'
# The folders of `scenarios/` that are the catalogue's own and hold no package: its shared library, its
# docs and its central tests.
RESERVED = ('docs', 'library', 'tests')
# The name of a package's folder: a lowercase letter, then lowercase letters, digits and `_`, and no name
# of RESERVED (`water_wipe`); or a reserved ID of the tests' synthetic packages: SC and two digits, and a
# name after an underscore for some (`SC97`, `SC97_east`).
_NAMED = rf'(?!(?:{"|".join(RESERVED)})\b)[a-z][a-z0-9_]*'
PACKAGE = rf'{_NAMED}|SC[0-9]{{2}}(?:_[a-z][a-z0-9_]*)?'
# The name of a variant's folder, and an owner: a package, or a variant of it (`package:variant`).
VARIANT = r'[a-z][a-z0-9_]*'
OWNER = rf'(?:{PACKAGE})(?::{VARIANT})?'
# The files and folders of an owner, in its folder.
UNITS = 'units.json'
EVIDENCE = 'evidence'
RESULTS = 'results'
COLLECTIONS = ('sources', 'claims', 'assumptions')


@dataclass(frozen=True)
class Owner:
    """An owner of the catalogue: its name (`package` or `package:variant`), its folder and its entry
    file, None for a package's folder without one. Among the owners of the catalogue (`owners`), the
    entry file is None also for a package with variants, which runs as its variants."""

    name: str
    folder: Path
    entry: Path | None

    @property
    def package(self):
        return self.name.partition(':')[0]

    @property
    def variant(self):
        return self.name.partition(':')[2] or None

    @property
    def units(self):
        return self.folder / UNITS

    @property
    def evidence(self):
        return self.folder / EVIDENCE

    @property
    def results(self):
        return self.folder / RESULTS

    def collections(self):
        """{collection: records} of the evidence that the owner's folder owns."""
        from napkin.model import load_json

        if self.folder.is_dir() and not self.evidence.exists() and not self.evidence.is_symlink():
            # Inline records and evidence inherited from a model's library need no owned files.
            # Validate those references before accepting the absence of the entire directory.
            from napkin.model.library import load_library

            entry = paths.entry(self.folder)
            if entry.is_file():
                load_library(entry)
            return {kind: [] for kind in COLLECTIONS}
        return {
            kind: load_json(self.evidence / f'{kind}.json', evidence=kind == 'claims') for kind in COLLECTIONS
        }


def vocabulary(root=ROOT):
    """The shared library of the catalogue at `root`, `scenarios/library/vocabulary.json`, with the prelude's units
    first (`napkin.model.library.read_vocabulary`): the library that each main file of the catalogue
    names."""
    from napkin.model.library import read_vocabulary

    return read_vocabulary(Path(root) / LIBRARY / 'vocabulary.json')


def _place(name):
    """The folder of the owner `name` in the checkout: `scenarios/P`, or `scenarios/P/variants/v` for the
    variant `P:v`."""
    package, _, variant = name.partition(':')
    return PurePosixPath(SCENARIOS, package, *((paths.VARIANTS, variant) if variant else ()))


def locate(name, root=ROOT):
    """The owner `name` at `root`, by its name alone: its folder, and its entry file when the file is
    there. It does not check that the owner exists."""
    folder = Path(root) / _place(name)
    found = paths.entry(folder)
    return Owner(name, folder, found if found.is_file() else None)


def name_of(path):
    """The catalogue's name of a model file, by its folders (`napkin.paths.names_of`): `package`, or
    `package:variant` for a variant's entry file. A file outside a package is named by its stem."""
    package, variant = paths.names_of(path)
    return f'{package}:{variant}' if variant else package


def in_package(name, *parts):
    """The path, as text relative to the checkout, of a file of the package of the owner `name`, from
    the package's folder: `in_package('water_wipe:east', 'variants/east/evidence/research.md')` is
    `scenarios/water_wipe/variants/east/evidence/research.md`. A note of a model names its files so."""
    return PurePosixPath(SCENARIOS, name.partition(':')[0], *parts).as_posix()


def result(name, *parts):
    """The path, as text relative to the checkout, of the results folder of the owner `name`, or of a
    file in it: `result('water_wipe:east', 'brief.md')` is
    `scenarios/water_wipe/variants/east/results/brief.md`."""
    return PurePosixPath(_place(name), RESULTS, *parts).as_posix()


def scenario_path(root, scenario_id):
    """The entry file of one owner (`water_wipe`, `water_wipe:east`, `SC97_name`), whether or not it is
    there: a missing file keeps the caller's filesystem error, and a malformed name raises KeyError.
    A name is ASCII, as in discovery and publication selection: the digits of a test's ID are 0 to 9.
    """
    if not re.fullmatch(OWNER, scenario_id, re.ASCII):
        raise KeyError(scenario_id)
    return paths.entry(Path(root) / _place(scenario_id))


def owner_of(path, root=ROOT):
    """The owner of the folder of the catalogue that holds `path` (a file or a folder, which need not be
    there; a relative path is read from `root`), by the names of its folders: `scenarios/P/...` is the
    package P's and `scenarios/P/variants/v/...` the variant P:v's. None outside those folders: in a
    folder of `scenarios/` that is not named as a package, such as the catalogue's own (`RESERVED`), and
    for a file of `scenarios/` itself."""
    path, base = Path(path), Path(root) / SCENARIOS
    if not path.is_absolute():
        path = Path(root) / path
    for candidate, folder in ((path, base), (path.resolve(), base.resolve())):
        try:
            parts = candidate.relative_to(folder).parts
            break
        except ValueError:
            continue
    else:
        return None
    if not parts or not re.fullmatch(PACKAGE, parts[0], re.ASCII):
        return None
    if len(parts) >= 3 and parts[1] == paths.VARIANTS and re.fullmatch(VARIANT, parts[2], re.ASCII):
        return f'{parts[0]}:{parts[2]}'
    return parts[0]


def folders(root=ROOT):
    """{name: owner} of each folder of the catalogue that can hold an owner, whether or not it holds one:
    each folder of `scenarios/` named as a package (`PACKAGE`) and each folder of its `variants/` named as
    a variant, in the catalogue's order. The entry file of a folder without one is None. It reads no file."""
    found = {}
    for folder in sorted((Path(root) / SCENARIOS).glob('*')):
        if not folder.is_dir() or not re.fullmatch(PACKAGE, folder.name, re.ASCII):
            continue
        found[folder.name] = locate(folder.name, root)
        for variant in sorted((folder / paths.VARIANTS).glob('*')):
            if variant.is_dir() and re.fullmatch(VARIANT, variant.name, re.ASCII):
                name = f'{folder.name}:{variant.name}'
                found[name] = locate(name, root)
    return found


def _running(found):
    """{name: owner} of the owners of `found` (`folders`) that run as models of their own: each variant
    with an entry file, and each package with one that has no such variant. A package with variants runs
    as its variants: its main file is part of each variant's model, so it never builds alone."""
    varied = {
        owner.package for owner in found.values() if owner.variant is not None and owner.entry is not None
    }
    return {
        name: owner
        for name, owner in found.items()
        if owner.entry is not None and (owner.variant is not None or name not in varied)
    }


def entries(root=ROOT):
    """{owner: its entry file} of every owner that runs as a model of its own, in the catalogue's order:
    each package that has a `model.scn` and no variants, and each variant. A package with variants runs
    as its variants, so its main file is no entry. It reads no file."""
    return {name: owner.entry for name, owner in _running(folders(root)).items()}


def completed_study(model, runs=None, edits=None, *, jobs=1):
    """The selected run records of a compiled catalogue model, each complete to its horizon."""
    from napkin.engine.study import study

    records = study(model, runs=runs, edits=edits, jobs=jobs)
    for name, record in records.items():
        if record.stop is not None or record.end != model.base.request.horizon:
            raise ValueError(f'{name or "default"} stopped at {record.end} h: {record.stopped()}')
    return records


def _survey(root):
    """(the owners, {owner: its readers}) of the catalogue at `root`. The folders that each model reads
    are found from the first declaration of its entry file (`library_folders`); no model is built."""
    from napkin.model.library import library_folders

    entered = _running(folders(root))
    readers = {}
    for name, owner in entered.items():
        for folder in library_folders(owner.entry):
            read = owner_of(folder, root)
            if read is not None and name not in readers.setdefault(read, []):
                readers[read].append(name)
    found = dict(entered)
    for read in readers:
        if read not in found and ':' not in read:
            # A package's folder that runs as no model of its own, the owner of its evidence: a package
            # with variants, or a folder without a main file.
            found[read] = Owner(read, locate(read, root).folder, None)
    return found, {name: tuple(readers.get(name, ())) for name in found}


def owners(root=ROOT, *, scenario_ids=None):
    """{name: owner} of every owner of the catalogue in its order: each owner that runs as a model of its
    own (`entries`), then each package's folder that a variant reads and that runs as no model of its
    own, with no entry file: a package with variants, or a folder without a main file. `scenario_ids`
    selects owners by name, and an unknown one raises ValueError."""
    found, _ = _survey(root)
    if scenario_ids is not None:
        unknown = set(scenario_ids) - found.keys()
        if unknown:
            raise ValueError(f'Unknown scenarios: {sorted(unknown)}')
        found = {name: owner for name, owner in found.items() if name in scenario_ids}
    return found


def readers(root=ROOT):
    """{owner: the owners whose models read a file of its folder}, both in the catalogue's order. An owner
    with an entry file is its own first reader, and a package's folder is read by its variants: only by
    them when it has variants, because the package then runs as its variants."""
    return _survey(root)[1]


def covered(names, readers):
    """The owners with an entry file that a selection of owners covers, in the catalogue's order, from the
    readers of the catalogue (`readers(root)`): each named owner covers its readers, so an owner with an
    entry file covers itself and a package covers its variants too. A name that is no owner raises
    KeyError."""
    chosen = {reader for name in names for reader in readers[name]}
    return tuple(name for name in readers if name in chosen)


def records(root=ROOT, *, allow_unused=False, scenario_ids=None):
    """{owner: its model's document, its library and the evidence of its folder} of each owner that runs as
    a model of its own (`entries`), or of those that `scenario_ids` names; an unknown one raises
    ValueError."""
    from napkin.model.library import load_library, model_document

    found = entries(root)
    if scenario_ids is not None:
        unknown = set(scenario_ids) - found.keys()
        if unknown:
            raise ValueError(f'Unknown scenarios: {sorted(unknown)}')
        found = {name: path for name, path in found.items() if name in scenario_ids}
    return {
        name: {
            'document': model_document(path),
            'library': load_library(path, allow_unused=allow_unused),
            'owned': locate(name, root).collections(),
        }
        for name, path in found.items()
    }
