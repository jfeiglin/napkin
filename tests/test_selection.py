"""Focused collection selects owned tests and declared contracts without running models."""

from pathlib import Path

import pytest

from tests import selection

pytest_plugins = ['pytester']
ROOT = Path(__file__).resolve().parents[1]


def catalogue_files(root):
    """The package SC97, whose variants alpha and beta read its folder, and SC97_alphabet, a package of
    its own; the package SC98, whose variant east reads its folder; and SC99's modules, which no model
    uses."""
    files = {
        'SC97/model.scn': 'scenario "Shared"\nuse shared\n',
        'SC97/shared.scn': '',
        'SC97/variants/alpha/model.scn': 'variant "Alpha"\n',
        'SC97/variants/beta/model.scn': 'variant "Beta"\n',
        'SC97_alphabet/model.scn': '',
        'SC98/model.scn': 'scenario "Other"\nuse common\n',
        'SC98/common.scn': '',
        'SC98/variants/east/model.scn': 'variant "East"\n',
        'SC99/unused.scn': '',
    }
    for name, text in files.items():
        path = root / 'scenarios' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


@pytest.mark.parametrize(
    'path, expected',
    [
        ('scenarios/SC97/tests/test_shared.py', True),
        ('scenarios/SC97/variants/alpha/tests/test_local.py', True),
        ('scenarios/SC97/variants/beta/tests/test_local.py', False),
        ('scenarios/SC97_alphabet/tests/test_local.py', False),
        ('scenarios/SC98/tests/test_local.py', False),
        # A folder of modules that the selected scenario does not read is not its, whatever its name.
        ('scenarios/SC99/tests/test_local.py', False),
        ('tests/test_central.py', None),
        ('scenarios/Notes/test_local.py', None),
        # The catalogue's own folders are no scenario's: its central tests, docs and library.
        ('scenarios/tests/test_central.py', None),
        ('scenarios/docs/test_local.py', None),
        ('scenarios/library/test_local.py', None),
        # A package that no model of the selection reads, by a name of letters.
        ('scenarios/notes/test_local.py', False),
    ],
)
def test_owned_paths_respect_family_boundaries(tmp_path, path, expected):
    catalogue_files(tmp_path)
    assert selection.scenario_path_selected(tmp_path / path, tmp_path, {'SC97:alpha'}) is expected


def test_a_family_folder_belongs_only_to_the_scenarios_that_read_it(tmp_path):
    catalogue_files(tmp_path)
    shared = tmp_path / 'scenarios/SC97/tests/test_shared.py'
    assert selection.scenario_path_selected(shared, tmp_path, {'SC97:beta'}) is True
    assert selection.scenario_path_selected(shared, tmp_path, {'SC97_alphabet', 'SC98'}) is False
    # A file in a variant's folder that is no variant does not read the package's folder.
    (tmp_path / 'scenarios/SC97/variants/alpha/model.scn').write_text('')
    selection._readers.cache_clear()
    assert selection.scenario_path_selected(shared, tmp_path, {'SC97:alpha'}) is False


@pytest.mark.parametrize(
    'names, package, variant', [({'SC98:east'}, True, True), ({'SC97:alpha'}, False, False)]
)
def test_a_variant_owns_its_folder_and_shares_the_folder_of_its_package(tmp_path, names, package, variant):
    catalogue_files(tmp_path)
    folder = tmp_path / 'scenarios/SC98'
    assert selection.scenario_path_selected(folder / 'tests/test_package.py', tmp_path, names) is package
    assert (
        selection.scenario_path_selected(folder / 'variants/east/tests/test_east.py', tmp_path, names)
        is variant
    )


def test_empty_scope_does_not_own_any_scenario(tmp_path):
    path = tmp_path / 'scenarios/SC97/tests/test_local.py'
    assert selection.scenario_path_selected(path, tmp_path, set()) is False
    assert selection.scenario_path_selected(path, tmp_path, None) is True
    assert selection.scenario_path_selected(tmp_path.parent / 'outside.py', tmp_path, set()) is None


@pytest.fixture
def collection_repo(pytester, monkeypatch):
    monkeypatch.delenv(selection.VARIABLE, raising=False)
    monkeypatch.delenv(selection.FOCUSED_VARIABLE, raising=False)
    monkeypatch.delenv('PYTEST_ADDOPTS', raising=False)
    monkeypatch.setenv('PYTHONPATH', str(ROOT))
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    monkeypatch.setenv('EXPECTED_CACHE', 'session')
    pytester.makeconftest((ROOT / 'conftest.py').read_text())
    pytester.makeini(
        '[pytest]\naddopts = --import-mode=importlib --strict-markers\n'
        'markers =\n    deep: expensive coverage\n    scenario_contract: selected scenario contract\n'
    )
    # The package SC97, whose variants alpha and beta read its folder; and SC98.
    texts = {
        'SC97': 'scenario "Shared"\nuse shared\n',
        'SC97/variants/alpha': 'variant "Alpha"\n',
        'SC97/variants/beta': 'variant "Beta"\n',
        'SC98': '',
    }
    for name, model in texts.items():
        directory = pytester.path / 'scenarios' / name
        (directory / 'tests').mkdir(parents=True)
        (directory / 'model.scn').write_text(model)
        (directory / 'tests/test_owned.py').write_text('def test_owned():\n    assert True\n')
    (pytester.path / 'scenarios/SC97/shared.scn').touch()
    central = pytester.path / 'tests'
    central.mkdir()
    (central / 'test_central.py').write_text(
        'import os\nimport pytest\n'
        '@pytest.mark.scenario_contract\n'
        'def test_contract(request):\n'
        '    assert request.config.getoption("result_cache_scope") == os.environ["EXPECTED_CACHE"]\n'
        'def test_engine_unit():\n    assert True\n'
        '@pytest.mark.deep\n'
        'def test_exhaustive_admission():\n    assert True\n'
        '@pytest.mark.deep\n@pytest.mark.scenario_contract\n'
        'def test_deep_contract():\n    assert True\n'
    )
    return pytester


def test_focused_collection_keeps_owned_tests_and_marked_contracts(collection_repo, monkeypatch):
    monkeypatch.setenv('EXPECTED_CACHE', 'test')
    result = collection_repo.runpytest_subprocess('--scenario', 'SC97:alpha', '--focused', '-m', 'not deep')
    result.assert_outcomes(passed=3, deselected=3)


def test_focused_deep_keeps_contract_but_not_exhaustive_unit(collection_repo):
    result = collection_repo.runpytest_subprocess('--scenario', 'SC97:alpha', '--focused', '-m', 'deep')
    result.assert_outcomes(passed=1, deselected=5)


def test_a_named_folder_of_modules_selects_the_scenarios_that_use_it(collection_repo, monkeypatch):
    # SC97 names the package: its own tests and those of its variants alpha and beta, not SC98's.
    monkeypatch.setenv('EXPECTED_CACHE', 'test')
    result = collection_repo.runpytest_subprocess('--scenario', 'SC97', '--focused', '-m', 'not deep')
    result.assert_outcomes(passed=4, deselected=3)
    result = collection_repo.runpytest_subprocess('--scenario', 'SC99', '--focused')
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(['*No scenario folder for SC99*'])


def test_ordinary_selected_pytest_still_runs_explicit_unit_tests(collection_repo):
    result = collection_repo.runpytest_subprocess('--scenario', 'SC97:alpha', '-m', 'not deep')
    result.assert_outcomes(passed=4, deselected=2)


def test_full_override_clears_inherited_options_and_scope(collection_repo, monkeypatch):
    monkeypatch.setenv(selection.VARIABLE, 'SC98')
    monkeypatch.setenv('PYTEST_ADDOPTS', '--scenario SC97:alpha --focused')
    result = collection_repo.runpytest_subprocess('--all-scenarios', '--no-focused', '-m', 'not deep')
    result.assert_outcomes(passed=6, deselected=2)


@pytest.mark.parametrize(
    'authoritative, mode, passed, deselected',
    [('SC97:alpha', '--focused', 3, 3), ('', '--focused', 1, 3), ('*', '--no-focused', 6, 2)],
)
def test_authoritative_scope_overrides_all_inherited_selectors(
    collection_repo, monkeypatch, authoritative, mode, passed, deselected
):
    monkeypatch.setenv(selection.VARIABLE, 'SC98')
    monkeypatch.setenv('PYTEST_ADDOPTS', '--scenario SC97:beta --all-scenarios --focused')
    monkeypatch.setenv('EXPECTED_CACHE', 'test' if mode == '--focused' else 'session')
    result = collection_repo.runpytest_subprocess(
        '--scenario-selection', authoritative, mode, '-m', 'not deep'
    )
    result.assert_outcomes(passed=passed, deselected=deselected)


def test_focused_requires_scope_but_accepts_empty_scope(collection_repo, monkeypatch):
    result = collection_repo.runpytest_subprocess('--focused')
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(['*--focused requires a scenario selection*'])
    monkeypatch.setenv(selection.VARIABLE, '')
    monkeypatch.setenv('EXPECTED_CACHE', 'test')
    result = collection_repo.runpytest_subprocess('--focused', '-m', 'not deep')
    result.assert_outcomes(passed=1, deselected=3)


def test_explicit_cache_scope_overrides_focused_default(collection_repo):
    result = collection_repo.runpytest_subprocess(
        '--scenario', 'SC97:alpha', '--focused', '--result-cache-scope=session', '-m', 'not deep'
    )
    result.assert_outcomes(passed=3, deselected=3)


def test_the_root_conftest_rewrites_the_assertions_of_each_module_of_a_scenarios_tests(collection_repo):
    """One rule of the root conftest.py rewrites the assertions of every module of a `tests/` folder of
    the catalogue, so a failed assertion of a helper that a scenario's test imports shows its values,
    with no conftest of the scenario's own. A module outside such a folder is not rewritten: its failed
    assertion shows no values."""
    root = collection_repo.path
    # The fake catalogue is the package `scenarios` of this checkout, ahead of the real one.
    (root / 'scenarios/__init__.py').write_text('')
    for folder in ('tests', 'parts'):
        (root / 'scenarios/SC98' / folder).mkdir(exist_ok=True)
        (root / 'scenarios/SC98' / folder / 'helper.py').write_text(
            'def check(value):\n    assert value == 1\n'
        )
    # A test of the package's tests imports the helper of its own folder, another the helper in `parts/`.
    for module, test in (('tests.helper', 'test_helper.py'), ('parts.helper', 'test_part.py')):
        (root / 'scenarios/SC98/tests' / test).write_text(
            f'from scenarios.SC98.{module} import check\n\n\ndef test_check():\n    check(2)\n'
        )
    rewritten = collection_repo.runpytest_subprocess('scenarios/SC98/tests/test_helper.py')
    rewritten.assert_outcomes(failed=1)
    rewritten.stdout.fnmatch_lines(['*assert 2 == 1*'])
    plain = collection_repo.runpytest_subprocess('scenarios/SC98/tests/test_part.py')
    plain.assert_outcomes(failed=1)
    assert 'assert 2 == 1' not in plain.stdout.str()


def test_a_dormant_list_names_files_and_folders(tmp_path):
    """A dormant list names a file, or a folder for each file in it. A comment and an empty line
    name nothing, and neither does a path outside the checkout."""
    (tmp_path / 'tests').mkdir()
    (tmp_path / selection.DORMANT).write_text('# a comment\n\ntests/engine/test_old.py\ntests/draw/\n')
    assert selection.dormant(tmp_path / 'tests/engine/test_old.py', tmp_path)
    assert selection.dormant(tmp_path / 'tests/draw/test_any.py', tmp_path)
    assert selection.dormant(tmp_path / 'tests/draw', tmp_path)
    assert not selection.dormant(tmp_path / 'tests/engine/test_new.py', tmp_path)
    assert not selection.dormant(tmp_path / 'tests/engine', tmp_path)
    assert not selection.dormant(tmp_path.parent / 'tests/engine/test_old.py', tmp_path)


def test_a_checkout_without_a_dormant_list_has_no_dormant_test(tmp_path):
    assert not selection.dormant(tmp_path / 'tests/engine/test_old.py', tmp_path)
