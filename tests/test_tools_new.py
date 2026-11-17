"""Starting a package of the catalogue (`tools/new.py`): the new folder has every file that each
package of the catalogue has, in its shape; the catalogue finds it; its model names the catalogue's
library; it takes the name of a real package only; and the commands and docs that its checklist and
README name exist."""

import importlib.util
import json
import re
import shutil

import pytest

from napkin import commands
from napkin.draw import style
from napkin.model import load_scenario
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


def made(root):
    """The folders of the catalogue at `root` other than its library."""
    return sorted(path.name for path in (root / catalogue.SCENARIOS).iterdir() if path.name != 'library')


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


def test_the_new_model_names_the_catalogues_library_and_the_title(root):
    # The title comes on one line, with one space between its words.
    folder = new.create(root, 'fake_case', ' A test\tof  the\nfolder ')
    model = load_scenario(folder / 'model.scn')
    assert model.scenario.title == 'A test of the folder'
    # Each unit of the shared vocabulary is a unit of the model: its file names the library.
    shared = catalogue.vocabulary(root)['units']
    assert shared and set(shared) <= set(model.library['units'])


def test_a_name_that_is_taken_is_refused_and_its_folder_kept(root):
    folder = new.create(root, 'fake_case', 'A test')
    before = {name: (folder / name).read_bytes() for name in authored(folder)}
    with pytest.raises(ValueError, match='there already'):
        new.create(root, 'fake_case', 'Another test')
    assert {name: (folder / name).read_bytes() for name in authored(folder)} == before


@pytest.mark.parametrize(
    'name',
    [
        '',
        # The tests' reserved IDs name synthetic packages only.
        'SC97',
        'SC97_east',
        'Fake_case',
        '9lives',
        '_case',
        'fake-case',
        'fake case',
        'fake.case',
        '../fake',
        'fake/case',
        'fake_case:east',
        # Full-width letters and digits are not ASCII.
        'ｆake',
        'fake１',
        # The catalogue's own folders hold no package.
        *catalogue.RESERVED,
    ],
)
def test_a_name_that_is_no_real_package_name_is_refused(root, name, capsys):
    with pytest.raises(ValueError, match='not a package name'):
        new.create(root, name, 'A test')
    with pytest.raises(SystemExit) as refused:
        new.main([name, '--root', str(root)])
    assert refused.value.code == 2 and 'usage: python -m tools.new' in capsys.readouterr().err
    assert made(root) == []


@pytest.mark.parametrize('name', ['docs_2', 'library_x', 'tests_a', 'a', 'water_wipe2'])
def test_a_name_that_only_starts_like_a_reserved_folder_is_a_package(root, name):
    folder = new.create(root, name, 'A test')
    assert catalogue.entries(root) == {name: folder / 'model.scn'}


def test_a_title_with_a_quote_or_no_words_is_refused(root):
    for title in ('A "quoted" title', ' \t '):
        with pytest.raises(ValueError):
            new.create(root, 'fake_case', title)
    assert made(root) == []


def test_the_checklist_and_the_readme_name_commands_and_docs_that_exist(root, capsys):
    assert new.main(['fake_case', '--root', str(root)]) == 0
    checklist = capsys.readouterr().out
    folder = root / catalogue.SCENARIOS / 'fake_case'
    readme = (folder / 'README.md').read_text(encoding='utf-8')
    for text in (checklist, readme):
        # The commands of `napkin`, each on the new folder as the checkout's root names it.
        used = {
            (command, target.rstrip('.'))
            for command, target in re.findall(r'\bnapkin ([a-z]+) ([\w./-]+)', text)
        }
        assert used and {command for command, _ in used} <= set(commands.NAMES), used
        assert {target for _, target in used} == {f'{catalogue.SCENARIOS}/fake_case'}, used
        # The tools of the checkout, each a module that is there; no command of the old modules.
        tools = re.findall(r'-m (tools(?:\.[a-z_]+)+)', text)
        assert tools and all(importlib.util.find_spec(module) for module in tools), tools
        assert not re.search(r'-m napkin\b', text)
        if text is checklist:
            assert {'compile', 'run'} <= {command for command, _ in used}
    # The docs that the checklist names are in the checkout.
    docs = re.findall(r'\b((?:scenarios/)?docs/[\w/.-]+\.md)', checklist)
    assert docs and all((ROOT / doc).is_file() for doc in docs), docs
