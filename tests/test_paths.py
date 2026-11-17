"""The files of a package, its variants and its entry files, and catalogue discovery, from filenames
alone without interpreting model contents. The catalogue's single lookup of an ID is the tools'
(`tests/test_locator.py`)."""

from pathlib import Path

import pytest

from napkin.paths import entry, package_of, variants


def touch(root, *names):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def no_reading(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('The lookup read a file')

    for name in ('open', 'read_text', 'read_bytes'):
        monkeypatch.setattr(Path, name, unexpected)


def test_the_entry_file_of_a_folder_is_its_model_file_whether_or_not_it_is_there(tmp_path):
    assert entry(tmp_path) == tmp_path / 'model.scn'
    assert entry(str(tmp_path / 'variants/east')) == tmp_path / 'variants/east/model.scn'


def test_the_variants_of_a_package_are_the_folders_of_its_variants_folder_with_an_entry_file(
    tmp_path, monkeypatch
):
    touch(
        tmp_path,
        'model.scn',
        'variants/west/model.scn',
        'variants/east/model.scn',
        'variants/east/water.scn',
        # No entry file: a folder without one, a model.scn that is a folder, and a file of variants/.
        'variants/north/README.md',
        'variants/south/model.scn/inside',
        'variants/model.scn',
        # A folder deeper than a variant is no variant.
        'variants/west/variants/up/model.scn',
    )
    no_reading(monkeypatch)
    found = variants(tmp_path)
    assert found == {
        'east': tmp_path / 'variants/east/model.scn',
        'west': tmp_path / 'variants/west/model.scn',
    }
    assert list(found) == ['east', 'west']
    assert variants(tmp_path / 'variants/east') == {}
    assert variants(tmp_path / 'nowhere') == {}


def test_the_package_of_a_path_is_the_nearest_folder_with_an_entry_file_or_a_variants_grandparent(
    tmp_path, monkeypatch
):
    package, other = tmp_path / 'scenarios/water', tmp_path / 'scenarios/loose'
    touch(
        tmp_path,
        'scenarios/water/model.scn',
        'scenarios/water/pumps.scn',
        'scenarios/water/variants/east/model.scn',
        'scenarios/water/variants/east/tests/test_east.py',
        'scenarios/water/variants/old/results/brief.md',
        'scenarios/water/inner/model.scn',
        # A variant whose package has no entry file of its own still belongs to it.
        'scenarios/loose/variants/one/model.scn',
        'scenarios/notes/README.md',
    )
    no_reading(monkeypatch)
    for path in (
        'scenarios/water',
        'scenarios/water/model.scn',
        'scenarios/water/pumps.scn',
        'scenarios/water/variants',
        'scenarios/water/variants/east',
        'scenarios/water/variants/east/model.scn',
        'scenarios/water/variants/east/tests/test_east.py',
        # A folder of variants without an entry file, and a file that is not there yet.
        'scenarios/water/variants/old/results/brief.md',
        'scenarios/water/missing.scn',
    ):
        assert package_of(tmp_path / path) == package, path
    # The nearest folder with an entry file is a package of its own when it is not a variant.
    assert package_of(tmp_path / 'scenarios/water/inner/model.scn') == package / 'inner'
    assert package_of(tmp_path / 'scenarios/loose/variants/one/model.scn') == other
    assert package_of(tmp_path / 'scenarios/loose/variants') is None
    assert package_of(tmp_path / 'scenarios/notes/README.md') is None
