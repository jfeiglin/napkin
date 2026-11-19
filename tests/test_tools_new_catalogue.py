"""Starting a package of the catalogue (`tools/new.py`), against the catalogue itself: the new folder
has each file that every package of the catalogue has, and the publisher's brief settings read. It
reads the catalogue and the publisher, so it waits for their migration (stage M) in
`tests/dormant.txt`; `tests/test_tools_new.py` holds the rest."""

import json
import shutil

import pytest

from napkin.draw import style
from tests.helpers import ALL_SCENARIO_IDS, ROOT
from tools import catalogue, new
from tools.publish import brief


@pytest.fixture
def root(tmp_path):
    """A checkout with the shared library and no package."""
    shutil.copytree(ROOT / catalogue.LIBRARY, tmp_path / catalogue.LIBRARY)
    return tmp_path


def authored(folder):
    """The files of a package's folder that a person writes: not the generated results."""
    return {
        path.relative_to(folder).as_posix()
        for path in folder.rglob('*')
        if path.is_file()
        and 'results' not in path.relative_to(folder).parts
        and '__pycache__' not in path.parts
    }


def test_a_new_folder_has_each_file_that_every_package_has(root):
    folder = new.create(root, 'fake_case', 'A test of the folder')
    assert catalogue.entries(root) == {'fake_case': folder / 'model.scn'}
    everywhere = set.intersection(*(authored(catalogue.locate(sid, ROOT).folder) for sid in ALL_SCENARIO_IDS))
    assert everywhere and everywhere <= authored(folder), sorted(everywhere - authored(folder))
    for path in folder.rglob('*.json'):
        json.loads(path.read_text(encoding='utf-8'))
    for name in catalogue.COLLECTIONS:
        assert json.loads((folder / 'evidence' / f'{name}.json').read_text(encoding='utf-8')) == []
    # The stylesheet and the brief settings read, and leave each key to its default.
    for name, read, empty in (
        (style.STYLE_FILE, style.read, style.Style),
        (brief.BRIEF_FILE, brief.read_brief, brief.Brief),
    ):
        assert read((folder / name).read_text(encoding='utf-8'), name) == empty(origin=name)
