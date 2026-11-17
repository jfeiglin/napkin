"""The committed model files: each one, a module included, reads, its formatted text is itself, each
scenario of the catalogue builds, each stylesheet and each file of brief settings reads and names
what each model that takes it declares, and those models admit the edit document of each spread of the
brief settings. A model takes the file of its own folder, else its package's (`style.lookup`), so a
package's file serves each variant without one of its own. The files are discovered; the test names
none of them."""

from __future__ import annotations

from pathlib import Path

import pytest

from napkin.draw import style
from napkin.engine import resolve_edits
from napkin.model import load_json
from napkin.model.language import front
from napkin.model.language.format import format_text
from napkin.model.language.modules import paths as model_paths
from napkin.model.library import library_folders
from tests import selection
from tests.helpers import ROOT, catalogue_model
from tools import catalogue
from tools.publish import brief

# The two TOML files of a model, each with its reader and its check against the model.
SETTINGS = {
    style.STYLE_FILE: (style.read, style.check),
    brief.BRIEF_FILE: (brief.read_brief, brief.check_brief),
}


def source_contract_files(root, ids=None, *, include_fixtures=True):
    """Find selected source files and their shared folders without compiling a model."""
    scenarios = sorted(path for sid, path in catalogue.entries(root).items() if ids is None or sid in ids)
    entries = set(scenarios)
    if ids is None:
        # The complete check reads every committed model file and stylesheet below `scenarios/`, in a
        # package's folder and in each of its variants' folders: also the modules that no current model
        # uses, a main file that only its variants read and the files of a folder that is no owner's,
        # so that none of them escapes the check.
        modules = sorted(
            path
            for path in (root / 'scenarios').rglob('*.scn')
            if path not in entries and 'tests' not in path.relative_to(root / 'scenarios').parts
        )
    else:
        # A selected model's check reads the files of its package's folder and of its variant's folder,
        # also the modules there that no current model uses, and each file of its package that it reads,
        # found from the `use` lines alone: a variant's main file and a module in a folder of the package.
        folders = {folder for path in scenarios for folder in library_folders(path)}
        found = {path for folder in folders for path in folder.glob('*.scn')}
        found.update(path.resolve() for scenario in scenarios for path in model_paths(scenario))
        entered = {path.resolve() for path in entries}
        modules = sorted(path for path in found if path not in entered)
    fixtures = sorted((root / 'tests' / 'acceptance').glob('*.scn')) if include_fixtures else []
    styles = sorted(
        (
            path
            for name in SETTINGS
            for pattern in (f'*/{name}', f'*/variants/*/{name}')
            for path in (root / 'scenarios').glob(pattern)
        )
        if ids is None
        # A selected model's own stylesheet and brief settings: its folder's, else its package's.
        else {taken for path in scenarios for name in SETTINGS if (taken := style.lookup(path, name))}
    )
    return scenarios, modules, fixtures, styles


def takers(path, root, ids=None):
    """The owners of the catalogue at `root` (of `ids`, when given) whose model takes the file `path`, a
    stylesheet or brief settings: each whose lookup of the file's name finds it (`style.lookup`), its
    own folder's first, then its package's. A file that no model takes has no owner."""
    found = Path(path).resolve()
    return [
        owner
        for owner, entry in catalogue.entries(root).items()
        if (ids is None or owner in ids)
        and (taken := style.lookup(entry, Path(path).name)) is not None
        and taken.resolve() == found
    ]


SCENARIOS, MODULES, FIXTURES, STYLES = source_contract_files(
    ROOT, selection.chosen(), include_fixtures=not selection.focused()
)


def _id(path):
    return path.relative_to(ROOT).as_posix()


# The spreads of the brief settings of the selected models (`[[spread]]`), each as (file, id).
SPREADS = [
    (path, spread.id)
    for path in STYLES
    if path.name == brief.BRIEF_FILE
    for spread in brief.read_brief(path.read_text(encoding='utf-8'), _id(path)).spreads
]


@pytest.mark.scenario_contract
@pytest.mark.parametrize('path', SCENARIOS + MODULES + FIXTURES, ids=_id)
def test_a_committed_file_reads_and_is_formatted(path):
    text = path.read_text(encoding='utf-8')
    front.read(text, _id(path))
    assert format_text(text) == text


@pytest.mark.scenario_contract
@pytest.mark.parametrize('path', SCENARIOS, ids=_id)
def test_a_scenario_file_builds(path):
    owner = catalogue.owner_of(path)
    model = catalogue_model(owner)
    assert catalogue.name_of(model.origin) == owner


@pytest.mark.scenario_contract
@pytest.mark.parametrize('path', STYLES, ids=_id)
def test_a_stylesheet_and_a_brief_read_and_name_what_their_model_declares(path):
    reader, checker = SETTINGS[path.name]
    owners = takers(path, ROOT, selection.chosen())
    assert owners, f'{_id(path)} is the file of no model of the catalogue'
    for owner in owners:
        assert checker(reader(path.read_text(encoding='utf-8'), _id(path)), catalogue_model(owner)) == []


@pytest.mark.scenario_contract
@pytest.mark.parametrize(('path', 'ident'), SPREADS, ids=[f'{_id(path)}:{ident}' for path, ident in SPREADS])
def test_the_model_admits_the_edit_document_of_each_spread_in_its_runs(path, ident):
    """The edit document of a spread is one of this revision of each model that takes the brief
    settings, and the engine admits it in the spread's runs (`resolve_edits`): the briefs can sample
    them. No sample runs here."""
    owners = takers(path, ROOT, selection.chosen())
    assert owners, f'{_id(path)} is the file of no model of the catalogue'
    for owner in owners:
        model = catalogue_model(owner)
        spread = next(spread for spread in brief.brief_of(model).spreads if spread.id == ident)
        resolved = resolve_edits(model, load_json(brief.spread_document(model, spread)), runs=spread.runs)
        assert set(resolved) == set(spread.runs)


def test_a_package_s_file_is_taken_by_each_variant_without_its_own(tmp_path):
    """In a synthetic catalogue (no model is built): the package SC97 has a stylesheet, and of its two
    variants only `west` has one of its own. The package's file is east's, west's own is west's, and
    each selection keeps only its owners. A package's file that every variant replaces is no model's."""
    package = tmp_path / catalogue.SCENARIOS / 'SC97'
    for folder in (package, package / 'variants' / 'east', package / 'variants' / 'west'):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'model.scn').write_text('# A file for tests only.\n', encoding='utf-8')
    (package / style.STYLE_FILE).write_text('', encoding='utf-8')
    own = package / 'variants' / 'west' / style.STYLE_FILE
    own.write_text('', encoding='utf-8')
    assert takers(package / style.STYLE_FILE, tmp_path) == ['SC97:east']
    assert takers(own, tmp_path) == ['SC97:west']
    assert takers(own, tmp_path, {'SC97:east'}) == []
    _, _, _, styles = source_contract_files(tmp_path, {'SC97:east', 'SC97:west'}, include_fixtures=False)
    assert styles == sorted([package / style.STYLE_FILE, own])
    (package / 'variants' / 'east' / style.STYLE_FILE).write_text('', encoding='utf-8')
    assert takers(package / style.STYLE_FILE, tmp_path) == []
