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
from napkin.engine import configurations
from napkin.model import load_json
from napkin.model.language.format import write
from napkin.model.language.parse import parse
from scenarios.tests.source_files import source_contract_files
from tests import selection
from tests.helpers import ROOT, catalogue_model
from tools import catalogue
from tools.publish import brief

# The two TOML files of a model, each with its reader and its check against the model.
SETTINGS = {
    style.STYLE_FILE: (style.read, style.check),
    brief.BRIEF_FILE: (brief.read_brief, brief.check_brief),
}


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
    assert write(parse(text)) == text


@pytest.mark.scenario_contract
@pytest.mark.parametrize('path', SCENARIOS, ids=_id)
def test_a_scenario_file_builds(path):
    owner = catalogue.owner_of(path)
    model = catalogue_model(owner)
    assert catalogue.name_of(style.origin_of(model)) == owner


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
    settings, and the engine admits it in the spread's runs (`configurations`): the briefs can sample
    them. No sample runs here."""
    owners = takers(path, ROOT, selection.chosen())
    assert owners, f'{_id(path)} is the file of no model of the catalogue'
    for owner in owners:
        model = catalogue_model(owner)
        spread = next(spread for spread in brief.brief_of(model).spreads if spread.id == ident)
        edits = load_json(brief.spread_document(model, spread), exact_numbers=True)
        resolved = configurations(model, spread.runs, edits)
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
