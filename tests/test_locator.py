"""The catalogue's locator (`tools/catalogue.py`): its owners, the files of each owner and the owner of a
path. On the old layout, packages without variants, it finds what that layout's discovery found
(`old_discovery`); on packages with variants it finds each variant beside its package, and
a package with variants runs as its variants. It reads the names of folders and files, and only the
first declaration of each entry file to find the readers of a folder."""

import re
from pathlib import Path

import pytest

from napkin.model import load_scenario
from napkin.model.library import library_folders
from tools import catalogue


def write(root, *names, text=''):
    """Files below `root/scenarios`, each with `text`."""
    for name in names:
        path = root / 'scenarios' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


# ---- the old layout: packages without variants ------------------------------------------------------


# The catalogue ID of the old layout: SC and two digits, and a name after an underscore for some.
OLD_ID = r'SC[0-9]{2}(?:_[a-z][a-z0-9_]*)?'


def old_discovery(root):
    """The discovery of the old layout, the oracle of the tests below: {ID: entry file} of each folder of
    `scenarios/` named by a catalogue ID of that layout (`OLD_ID`) that holds its `model.scn`, by name."""
    return {
        path.parent.name: path
        for path in sorted((Path(root) / 'scenarios').glob('SC[0-9][0-9]*/model.scn'))
        if path.is_file() and re.fullmatch(OLD_ID, path.parent.name, re.ASCII)
    }


def old_layout(root):
    """The catalogue's layout before its packages had variants, below `root`: the package SC97 with its
    module, the packages SC98_east, SC98_west and SC99, and SC98, a folder of modules without a main
    file beside them. Its discovery (`old_discovery`) is the oracle of the tests below."""
    write(root, 'SC97/model.scn', text='scenario "A"\nuse common\n')
    write(root, 'SC97/common.scn', 'SC98/water.scn', 'SC98/README.md', 'SC99/model.scn')
    write(root, 'SC98_east/model.scn', 'SC98_west/model.scn', text='scenario "B"\n')


def test_on_the_old_layout_the_entries_are_the_files_that_its_discovery_finds(tmp_path):
    old_layout(tmp_path)
    found = catalogue.entries(tmp_path)
    assert found == old_discovery(tmp_path)
    assert list(found) == list(old_discovery(tmp_path)) == ['SC97', 'SC98_east', 'SC98_west', 'SC99']


def test_on_the_old_layout_the_owners_are_its_packages(tmp_path):
    """The evidence owners of the old layout: each package with an entry file, in the order of its
    discovery. A `use` line names a module of the model's own package, so no model reads a folder of
    modules without a main file, and no such folder is an owner."""
    old_layout(tmp_path)
    scenarios = old_discovery(tmp_path)
    owners = catalogue.owners(tmp_path)
    assert list(owners) == list(scenarios)
    for name, path in scenarios.items():
        assert (owners[name].entry, owners[name].folder) == (path, path.parent)
    for owner in owners.values():
        assert (owner.units, owner.evidence, owner.results) == tuple(
            owner.folder / name for name in ('units.json', 'evidence', 'results')
        )


def test_on_the_old_layout_a_folder_is_read_by_the_scenarios_whose_models_read_a_file_of_it(tmp_path):
    old_layout(tmp_path)
    readers = catalogue.readers(tmp_path)
    assert list(readers) == list(catalogue.owners(tmp_path))
    for name, owner in catalogue.owners(tmp_path).items():
        expected = [
            sid
            for sid, path in old_discovery(tmp_path).items()
            if owner.folder.resolve() in library_folders(path)
        ]
        assert list(readers[name]) == expected, name
        assert (name in readers[name]) == (owner.entry is not None)


# ---- discovery --------------------------------------------------------------------------------------


def test_discovery_finds_each_package_before_its_variants_and_reads_no_file(tmp_path, monkeypatch):
    write(
        tmp_path,
        'SC98/model.scn',
        'SC97/model.scn',
        'SC97/variants/b/model.scn',
        'SC97/variants/a/model.scn',
        'SC97_x/model.scn',
        # A package named in lowercase, with a variant.
        'fake_case/model.scn',
        'fake_case/variants/east/model.scn',
        # A variant whose package has no entry file of its own.
        'SC99/variants/c/model.scn',
        # No entry file: a folder of variants without one, one where model.scn is a folder, and names
        # that are no package's or variant's, among them the catalogue's own folders.
        'SC97/variants/d/notes.md',
        'SC98/variants/e/model.scn/inside',
        'SC97/variants/B/model.scn',
        'SC97/variants/a.b/model.scn',
        'SC97/variants/_a/model.scn',
        'SC1/model.scn',
        'SC１２/model.scn',
        'Notes/model.scn',
        '9lives/model.scn',
        'docs/model.scn',
        'library/model.scn',
        'tests/model.scn',
        'tests/variants/a/model.scn',
        'SC97/sub/model.scn',
    )
    (tmp_path / 'scenarios/SC98.json').write_text('{}')

    def unexpected(*args, **kwargs):
        pytest.fail('Discovery read a file')

    for name in ('open', 'read_text', 'read_bytes'):
        monkeypatch.setattr(Path, name, unexpected)
    scenarios = tmp_path / 'scenarios'
    entries = catalogue.entries(tmp_path)
    # SC97 runs as its variants, so its main file is no entry; SC98 has no variant with an entry file.
    assert list(entries) == ['SC97:a', 'SC97:b', 'SC97_x', 'SC98', 'SC99:c', 'fake_case:east']
    assert entries['SC97:a'] == scenarios / 'SC97/variants/a/model.scn'
    assert entries['SC99:c'] == scenarios / 'SC99/variants/c/model.scn'
    assert entries['fake_case:east'] == scenarios / 'fake_case/variants/east/model.scn'
    # The folders that can hold an owner, with or without an entry file.
    folders = catalogue.folders(tmp_path)
    assert list(folders) == [
        'SC97',
        'SC97:a',
        'SC97:b',
        'SC97:d',
        'SC97_x',
        'SC98',
        'SC98:e',
        'SC99',
        'SC99:c',
        'fake_case',
        'fake_case:east',
    ]
    assert {name for name, owner in folders.items() if owner.entry is None} == {'SC97:d', 'SC98:e', 'SC99'}


def test_discovery_orders_the_packages_and_excludes_other_names(tmp_path):
    folder = tmp_path / 'scenarios'
    folder.mkdir()
    for name in (
        'SC98',
        'SC99',
        'fake_case',
        'SC97',
        'SC1',
        'SC001',
        'SC99.json',
        'Notes',
        'fake-case',
        'SC１２',
        # The catalogue's own folders: its docs, its shared library and its central tests.
        *catalogue.RESERVED,
    ):
        (folder / name).mkdir()
        (folder / name / 'model.scn').write_text('not a valid model: [')
    # A folder without a model.scn is not a scenario of the catalogue.
    (folder / 'SC96').mkdir()
    (folder / 'SC96' / 'model.yaml').write_text('version: 3')
    other = tmp_path / 'directories'
    (other / 'scenarios/SC99/model.scn').mkdir(parents=True)
    assert catalogue.entries(other) == {}
    assert catalogue.entries(tmp_path) == {
        sid: folder / sid / 'model.scn' for sid in ('SC97', 'SC98', 'SC99', 'fake_case')
    }
    assert list(catalogue.entries(tmp_path)) == ['SC97', 'SC98', 'SC99', 'fake_case']


def test_a_scenario_of_a_family_is_found_by_its_folder(tmp_path):
    folder = tmp_path / 'scenarios'
    for name in ('SC97', 'SC97_a', 'SC97_los_b2', 'SC97_B', 'SC97_', 'SC97.a', 'SC97__a'):
        (folder / name).mkdir(parents=True)
        (folder / name / 'model.scn').touch()
    # The family's folder of modules holds no model.scn of its own here.
    (folder / 'SC98').mkdir()
    (folder / 'SC98' / 'water.scn').touch()
    assert list(catalogue.entries(tmp_path)) == ['SC97', 'SC97_a', 'SC97_los_b2']


def test_discovery_observes_additions_and_removals(tmp_path):
    assert catalogue.entries(tmp_path) == {}
    write(tmp_path, 'SC97/model.scn')
    assert list(catalogue.entries(tmp_path)) == ['SC97']
    # With a variant, the package runs as its variants; without one, it runs as itself again.
    write(tmp_path, 'SC97/variants/east/model.scn')
    assert list(catalogue.entries(tmp_path)) == ['SC97:east']
    (tmp_path / 'scenarios/SC97/variants/east/model.scn').unlink()
    assert list(catalogue.entries(tmp_path)) == ['SC97']
    write(tmp_path, 'SC97/variants/east/model.scn')
    (tmp_path / 'scenarios/SC97/model.scn').unlink()
    assert list(catalogue.entries(tmp_path)) == ['SC97:east']


def test_a_package_with_variants_runs_as_its_variants(tmp_path):
    """A package with variants runs only through its variants: its main file is part of each variant's
    model, so it is no entry, and its folder is read by its variants alone. The package stays the owner of
    the evidence of its folder, with no entry file. A package without variants runs as itself."""
    write(tmp_path, 'SC97/model.scn', 'SC98/model.scn', text='scenario "A"\n')
    write(tmp_path, 'SC97/variants/a/model.scn', 'SC97/variants/b/model.scn', text='variant "A"\n')
    scenarios = tmp_path / 'scenarios'
    assert catalogue.entries(tmp_path) == {
        'SC97:a': scenarios / 'SC97/variants/a/model.scn',
        'SC97:b': scenarios / 'SC97/variants/b/model.scn',
        'SC98': scenarios / 'SC98/model.scn',
    }
    # The folder holds the main file, and the owner of the folder runs as no model of its own.
    assert catalogue.folders(tmp_path)['SC97'].entry == scenarios / 'SC97/model.scn'
    owner = catalogue.owners(tmp_path)['SC97']
    assert (owner.folder, owner.entry, owner.evidence) == (
        scenarios / 'SC97',
        None,
        scenarios / 'SC97/evidence',
    )
    readers = catalogue.readers(tmp_path)
    assert readers['SC97'] == ('SC97:a', 'SC97:b') and readers['SC98'] == ('SC98',)


def test_a_folder_of_modules_without_an_entry_file_is_no_owner(tmp_path):
    """A `use` line names a module of its own package, so no model reads a folder of modules that has no
    entry file: such a folder is no owner. A package's folder is read by its variants, and the package
    with variants comes after the owners that run, as the owner of its folder."""
    write(tmp_path, 'SC97/common.scn', 'SC99/unused.scn', 'SC98/model.scn')
    write(tmp_path, 'SC97/model.scn', text='scenario "A"\n')
    write(tmp_path, 'SC97/variants/a/model.scn', 'SC97/variants/b/model.scn', text='variant "A"\n')
    owners = catalogue.owners(tmp_path)
    assert list(owners) == ['SC97:a', 'SC97:b', 'SC98', 'SC97']
    assert owners['SC97'].folder == tmp_path / 'scenarios/SC97'
    assert catalogue.readers(tmp_path) == {
        'SC97': ('SC97:a', 'SC97:b'),
        'SC97:a': ('SC97:a',),
        'SC97:b': ('SC97:b',),
        'SC98': ('SC98',),
    }
    assert list(catalogue.owners(tmp_path, scenario_ids=['SC97', 'SC98'])) == ['SC98', 'SC97']
    with pytest.raises(ValueError, match='SC99'):
        catalogue.owners(tmp_path, scenario_ids=['SC99'])


def test_a_package_is_read_by_its_variants(tmp_path):
    # A file in a variant's folder that is no variant (`c`, a module by its first declaration) is not.
    write(tmp_path, 'SC97/common.scn', 'SC97/variants/c/model.scn', 'SC98/model.scn')
    write(tmp_path, 'SC97/model.scn', text='scenario "A"\nuse common\n')
    write(tmp_path, 'SC97/variants/a/model.scn', 'SC97/variants/b/model.scn', text='variant "A"\n')
    readers = catalogue.readers(tmp_path)
    assert readers['SC97'] == ('SC97:a', 'SC97:b')
    assert readers['SC97:a'] == ('SC97:a',) and readers['SC97:c'] == ('SC97:c',)
    # A selection covers the readers of each owner that it names, in the catalogue's order.
    assert catalogue.covered(['SC97'], readers) == ('SC97:a', 'SC97:b')
    assert catalogue.covered(['SC98', 'SC97:c', 'SC97:a'], readers) == ('SC97:a', 'SC97:c', 'SC98')
    with pytest.raises(KeyError):
        catalogue.covered(['SC97:d'], readers)


def test_a_package_covers_its_variants(tmp_path):
    write(tmp_path, 'SC97/common.scn', 'SC98/model.scn')
    write(tmp_path, 'SC97/model.scn', text='scenario "A"\nuse common\n')
    write(tmp_path, 'SC97/variants/a/model.scn', 'SC97/variants/b/model.scn', text='variant "A"\n')
    readers = catalogue.readers(tmp_path)
    assert catalogue.covered(['SC97'], readers) == ('SC97:a', 'SC97:b')
    assert catalogue.covered(['SC97:b', 'SC97'], readers) == ('SC97:a', 'SC97:b')
    assert catalogue.covered(['SC97:b'], readers) == ('SC97:b',)
    assert catalogue.covered([], readers) == ()


# ---- the owner of a path and the files of an owner --------------------------------------------------


@pytest.mark.parametrize(
    'path, owner',
    [
        ('scenarios/SC97/model.scn', 'SC97'),
        ('scenarios/SC97/tests/test_owned.py', 'SC97'),
        ('scenarios/SC97', 'SC97'),
        ('scenarios/SC97_east/evidence/claims.json', 'SC97_east'),
        ('scenarios/SC97/variants/east/model.scn', 'SC97:east'),
        ('scenarios/SC97/variants/east', 'SC97:east'),
        ('scenarios/SC97/variants/east/tests/test_owned.py', 'SC97:east'),
        ('scenarios/SC97_a/variants/b_2/results/brief.md', 'SC97_a:b_2'),
        # A package is named in lowercase letters, digits and `_`, a letter first.
        ('scenarios/fake_case/model.scn', 'fake_case'),
        ('scenarios/fake_case/variants/east/tests/test_owned.py', 'fake_case:east'),
        ('scenarios/notes/model.scn', 'notes'),
        ('scenarios/docs_2/model.scn', 'docs_2'),
        # The folder of the variants, a file in it and a folder that no variant can have are the package's.
        ('scenarios/SC97/variants', 'SC97'),
        ('scenarios/SC97/variants/README.md', 'SC97'),
        ('scenarios/SC97/variants/East/model.scn', 'SC97'),
        ('scenarios/SC97/sub/variants/east/model.scn', 'SC97'),
        # Outside the folders of the catalogue: a file of `scenarios/`, a folder not named as a package,
        # and the catalogue's own folders, its docs, its shared library and its central tests.
        ('scenarios', None),
        ('scenarios/__init__.py', None),
        ('scenarios/README.md', None),
        ('scenarios/SC97.json', None),
        ('scenarios/Notes/model.scn', None),
        ('scenarios/fake-case/model.scn', None),
        ('scenarios/9lives/model.scn', None),
        ('scenarios/SC1/model.scn', None),
        ('scenarios/SC97_B/model.scn', None),
        ('scenarios/docs/catalogue.md', None),
        ('scenarios/docs/variants/east/model.scn', None),
        ('scenarios/library/vocabulary.json', None),
        ('scenarios/tests/sources.py', None),
        ('scenarios/tests/variants/east/test_owned.py', None),
        ('docs/scenarios/SC97/brief.md', None),
        ('tests/scenarios/SC97/test_owned.py', None),
    ],
)
def test_the_owner_of_a_path_is_named_by_its_folders(tmp_path, path, owner):
    assert catalogue.owner_of(path, tmp_path) == owner
    assert catalogue.owner_of(tmp_path / path, tmp_path) == owner


def test_a_path_outside_the_root_has_no_owner(tmp_path):
    assert catalogue.owner_of(tmp_path.parent / 'scenarios/SC97/model.scn', tmp_path) is None


@pytest.mark.parametrize(
    'name, folder, package, variant',
    [
        ('SC97', 'scenarios/SC97', 'SC97', None),
        ('SC97_east', 'scenarios/SC97_east', 'SC97_east', None),
        ('SC97:east', 'scenarios/SC97/variants/east', 'SC97', 'east'),
        ('SC97_a:b_2', 'scenarios/SC97_a/variants/b_2', 'SC97_a', 'b_2'),
        ('fake_case', 'scenarios/fake_case', 'fake_case', None),
        ('fake_case:east_2', 'scenarios/fake_case/variants/east_2', 'fake_case', 'east_2'),
    ],
)
def test_each_owner_keeps_its_files_in_its_folder(tmp_path, name, folder, package, variant):
    owner = catalogue.locate(name, tmp_path)
    assert (owner.name, owner.folder, owner.entry) == (name, tmp_path / folder, None)
    assert (owner.package, owner.variant) == (package, variant)
    assert (owner.units, owner.evidence, owner.results) == tuple(
        tmp_path / folder / part for part in ('units.json', 'evidence', 'results')
    )
    assert catalogue.result(name) == f'{folder}/results'
    assert catalogue.result(name, 'brief.md') == f'{folder}/results/brief.md'
    assert catalogue.owner_of(owner.folder, tmp_path) == catalogue.owner_of(owner.results, tmp_path) == name
    assert catalogue.owner_of(catalogue.result(name, 'brief.md'), tmp_path) == name
    write(tmp_path, f'{folder.removeprefix("scenarios/")}/model.scn')
    assert catalogue.locate(name, tmp_path).entry == tmp_path / folder / 'model.scn'


def test_an_owner_reads_the_evidence_of_its_own_folder(tmp_path):
    write(tmp_path, 'SC97/variants/east/model.scn')
    for kind in catalogue.COLLECTIONS:
        write(tmp_path, f'SC97/variants/east/evidence/{kind}.json', text=f'[{{"id": "{kind}"}}]')
        write(tmp_path, f'SC97/evidence/{kind}.json', text='[]')
    owner = catalogue.owners(tmp_path)['SC97:east']
    assert owner.collections() == {kind: [{'id': kind}] for kind in catalogue.COLLECTIONS}


@pytest.mark.parametrize(
    'identifier',
    [
        '',
        'SC1',
        'SC001',
        # The digits of a test's ID are ASCII: full-width digits are not.
        'SC１２',
        'Sc99',
        '9lives',
        '_case',
        'fake-case',
        'Fake_case',
        '../SC97',
        'SC97/other',
        'SC97.a',
        'SC97:',
        'SC97:East',
        'SC97:a:b',
        'fake_case:',
        # The catalogue's own folders hold no scenario.
        'docs',
        'library:east',
        'tests',
    ],
)
def test_single_lookup_preserves_malformed_identifier_error(tmp_path, identifier):
    with pytest.raises(KeyError) as error:
        catalogue.scenario_path(tmp_path, identifier)
    assert error.value.args == (identifier,)


@pytest.mark.parametrize(
    'identifier, folder',
    [
        ('SC99', 'SC99'),
        ('SC97_a', 'SC97_a'),
        ('SC97:east', 'SC97/variants/east'),
        ('fake_case', 'fake_case'),
        ('sc99', 'sc99'),
        ('docs_2:east', 'docs_2/variants/east'),
    ],
)
def test_valid_shaped_missing_identifier_retains_filesystem_error(tmp_path, identifier, folder):
    path = catalogue.scenario_path(tmp_path, identifier)
    assert path == tmp_path / 'scenarios' / folder / 'model.scn'
    # The loader that the publisher and the tests call on the path keeps the filesystem's error.
    with pytest.raises(FileNotFoundError):
        load_scenario(path)
