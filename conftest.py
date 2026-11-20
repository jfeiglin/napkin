"""Assertion rewriting for shared test helpers, the run store for the tests that use it, the
selection of scenarios (`--scenario`), and the examples of the property tests."""

import os
from pathlib import Path

import pytest
from hypothesis import settings

from napkin import store
from tests import selection
from tests.result_cache import clear_result_caches
from tools import catalogue

ROOT = Path(__file__).resolve().parent

# Every property test draws the same examples on every run, as a run of napkin gives the same result
# (PLAN, changes after G0, items 10 and 11): a seed from the test itself, and no database of the
# examples of earlier runs, which held examples of other code and made a test's examples depend on
# what ran before it on this machine. A test's own `@settings` adds to this profile.
settings.register_profile('napkin', derandomize=True, database=None)
settings.load_profile('napkin')


def catalogue_test_modules(root):
    """The modules of each `tests/` folder of the catalogue at `root`, by their names: a package's, a
    variant's and the catalogue's own (`scenarios/tests/`), but no conftest and no package's `__init__`."""
    return [
        '.'.join(path.relative_to(root).with_suffix('').parts)
        for path in sorted((root / catalogue.SCENARIOS).rglob('tests/*.py'))
        if path.name not in ('conftest.py', '__init__.py')
    ]


# One rule for the whole catalogue: the assertions of each module of a scenario's tests, its helpers
# included, are rewritten, so an assertion of a helper that a test imports reports its values as the
# test's own do. No scenario repeats this in a conftest of its own.
pytest.register_assert_rewrite('tests.helpers', 'tests.build', *catalogue_test_modules(ROOT))
# The engine, language and acceptance unit tests always simulate: they test the simulation itself,
# and some of them replace parts of the engine. Every other test takes its runs from the run store
# (`napkin/store.py`), so the test workers and the publisher share them.
UNSTORED = ('tests/engine/', 'tests/acceptance/', 'tests/model/')


def pytest_addoption(parser):
    parser.addoption(
        '--scenario',
        action='append',
        metavar='ID',
        help='Check only this scenario (repeatable): its own tests and the central cases of it. '
        'Tests of the catalogue as a whole still read every scenario.',
    )
    parser.addoption(
        '--scenario-selection',
        metavar='IDS',
        help='Authoritative comma-separated scenario selection for check subprocesses; '
        "'*' selects all and an empty value selects none. Overrides inherited scenario flags.",
    )
    parser.addoption(
        '--all-scenarios',
        action='store_true',
        help='Clear scenario selection, including inherited --scenario options.',
    )
    parser.addoption(
        '--focused',
        action='store_true',
        default=False,
        help='With a scenario selection, run its owned tests and marked central scenario contracts; '
        'leave unrelated unit tests and whole-catalogue checks for the full suite.',
    )
    parser.addoption(
        '--no-focused',
        action='store_false',
        dest='focused',
        default=False,
        help='Run the full suite, overriding an inherited --focused option.',
    )
    parser.addoption(
        '--result-cache-scope',
        choices=('session', 'test'),
        default=None,
        help='Keep registered study caches for the session, or clear them after '
        'each test. Defaults to test in focused mode and session otherwise. Compiled model caches remain.',
    )


def pytest_configure(config):
    is_focused = config.getoption('focused')
    os.environ[selection.FOCUSED_VARIABLE] = '1' if is_focused else '0'
    if config.getoption('result_cache_scope') is None:
        config.option.result_cache_scope = 'test' if is_focused else 'session'
    names = config.getoption('scenario')
    authoritative = config.getoption('scenario_selection')
    if authoritative is not None:
        names = None if authoritative == '*' else [name for name in authoritative.split(',') if name]
        if names is None:
            os.environ.pop(selection.VARIABLE, None)
    elif config.getoption('all_scenarios'):
        names = None
        os.environ.pop(selection.VARIABLE, None)
    if names is not None:
        # Each owner that `--scenario` names covers the scenarios that read its folder: a scenario
        # itself, the folder of a family's modules the scenarios of the family (`catalogue.covered`).
        readers = catalogue.readers(ROOT)
        unknown = sorted(set(names) - set(readers))
        if unknown:
            raise pytest.UsageError(f'No scenario folder for {", ".join(unknown)}')
        os.environ[selection.VARIABLE] = selection.encode(catalogue.covered(names, readers))
    if is_focused:
        selected = selection.chosen()
        if selected is None:
            raise pytest.UsageError(
                '--focused requires a scenario selection (--scenario or the selection environment variable)'
            )
        unknown = sorted(selected - set(catalogue.owners(ROOT)))
        if unknown:
            raise pytest.UsageError(f'No scenario folder for {", ".join(unknown)}')


def pytest_report_header(config):
    names = selection.chosen()
    if names is not None:
        mode = '; owned tests and central contracts only' if config.getoption('focused') else ''
        return f'scenarios: {", ".join(sorted(names)) or "none"} (of {len(catalogue.entries(ROOT))}){mode}'
    return None


def pytest_ignore_collect(collection_path, config):
    # A dormant test is not collected (`tests/dormant.txt`).
    if selection.dormant(collection_path, ROOT):
        return True
    # The folder of a scenario that the session does not check is not collected.
    names = selection.chosen()
    if names is None:
        return None
    if selection.scenario_path_selected(collection_path, ROOT, names) is False:
        return True
    return None


def pytest_collection_modifyitems(config, items):
    if not config.getoption('focused'):
        return
    names = selection.chosen()
    kept, deselected = [], []
    for item in items:
        owned = selection.scenario_path_selected(item.path, ROOT, names)
        destination = kept if owned is True or item.get_closest_marker('scenario_contract') else deselected
        destination.append(item)
    items[:] = kept
    if deselected:
        config.hook.pytest_deselected(items=deselected)


def uses_store(path):
    relative = Path(path).resolve().relative_to(ROOT).as_posix()
    return not relative.startswith(UNSTORED)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    # The whole protocol of a test, so the fixtures that its setup makes use the same store.
    try:
        with store.use(store.default_directory() if uses_store(item.path) else None):
            return (yield)
    finally:
        if item.config.getoption('result_cache_scope') == 'test':
            clear_result_caches()
