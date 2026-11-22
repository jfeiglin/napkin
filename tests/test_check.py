"""Focused validation never expands silently into a full catalogue check."""

import os
import sys
from pathlib import Path

import pytest

from tools import check

IDS = ('SC97', 'SC98', 'fake_case')


@pytest.mark.parametrize(
    'paths, scope',
    [
        # Changes in one scenario's folder, with docs, check that scenario.
        (['scenarios/SC98/model.scn', 'scenarios/SC98/tests/test_owned.py', 'docs/language.md'], ('SC98',)),
        (['scenarios/SC97/evidence/claims.json', 'scenarios/SC98/brief.toml'], ('SC97', 'SC98')),
        (['scenarios/SC98/results/brief.md', 'README.md', 'CHANGELOG.md'], ('SC98',)),
        (['scenarios/fake_case/model.scn', 'scenarios/SC97/style.toml'], ('SC97', 'fake_case')),
        # Docs alone check no scenario's own tests.
        (['docs/engine.md', 'CONTRIBUTING.md'], ()),
        # The package, the engine, the tests and the package's scenario code check everything.
        (['napkin/spread.py'], None),
        (['napkin/engine/study.py', 'scenarios/SC98/model.scn'], None),
        (['tests/helpers.py'], None),
        (['scenarios/__init__.py'], None),
        # The catalogue's own folders hold no scenario: a change in them is no scenario's change.
        (['scenarios/library/vocabulary.json'], None),
        (['scenarios/tests/sources.py', 'scenarios/SC98/model.scn'], None),
        # Data in a folder of docs (the source manifest) is read by the evidence tests: it is not documentation.
        (['scenarios/docs/evidence/source-manifest.json'], None),
        (['scenarios/docs/evidence/source-manifest.json', 'docs/engine.md'], None),
        # The catalogue's own docs and its index are written docs: they check no scenario's tests.
        (
            [
                'scenarios/docs/catalogue.md',
                'scenarios/docs/evidence/reviews/README.md',
                'scenarios/README.md',
            ],
            (),
        ),
        (['scenarios/docs/evidence/README.md', 'scenarios/SC98/model.scn'], ('SC98',)),
        (['scenarios/notes.md'], None),
        # A folder of a scenario that is gone, and no change at all, check everything.
        (['scenarios/SC99/model.scn'], None),
        ([], None),
    ],
)
def test_the_scope_covers_each_change(paths, scope):
    found, reason = check.scope_of(paths, IDS)
    assert found == scope and reason


def test_a_scoped_check_selects_its_scenarios_for_the_tests(monkeypatch):
    calls = []
    monkeypatch.setattr(
        check, 'run', lambda command, cwd=None, environment=None: calls.append(environment) or 0
    )
    check.tests('not deep', ('SC97', 'SC98'))
    check.tests('not deep', ())
    check.tests('not deep')
    assert calls == [{check.SELECTION: 'SC97,SC98'}, {check.SELECTION: None}]


def test_a_scoped_check_renders_only_its_owned_summaries_once(monkeypatch):
    calls = []
    monkeypatch.setattr(check, 'run', lambda command, cwd=None, environment=None: calls.append(command) or 0)
    check.summaries(('SC98',))
    assert len(calls) == 1
    assert calls[0][-2:] == ['--scenario', 'SC98']
    assert '--only' not in calls[0]
    calls.clear()
    check.summaries(())
    assert calls == []
    calls.clear()
    check.summaries(None)
    assert len(calls) == 1 and '--only' not in calls[0]


@pytest.mark.parametrize('scope', [None, (), ('SC98',)])
@pytest.mark.parametrize('jobs', [1, 3])
def test_publication_worker_limit_reaches_every_comparison(monkeypatch, scope, jobs):
    calls = []
    monkeypatch.setattr(check, 'run', lambda command, cwd=None, environment=None: calls.append(command) or 0)
    assert not check.summaries(scope, jobs)
    assert len(calls) == (0 if scope == () else 1)
    assert all(command[command.index('--jobs') + 1] == str(jobs) for command in calls)


@pytest.mark.parametrize('extra, jobs', [([], 1), (['--publish-jobs', '3'], 3)])
def test_check_cli_selects_publication_workers_without_changing_scope(monkeypatch, extra, jobs):
    calls = []
    monkeypatch.setattr(check, 'readers_of', lambda: {sid: (sid,) for sid in IDS})
    monkeypatch.setattr(check, 'lint', lambda: 0)
    monkeypatch.setattr(check, 'tests', lambda marker, scope, **kwargs: 0)
    monkeypatch.setattr(check, 'stored_runs', lambda: 0)
    monkeypatch.setattr(
        check, 'summaries', lambda scope, jobs, spreads=False: calls.append((scope, jobs)) or 0
    )
    assert check.main(['--scenario', 'SC98', *extra]) == 0
    assert calls == [(('SC98',), jobs)]


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'none'])
def test_publication_workers_require_a_positive_integer(value, capsys):
    with pytest.raises(SystemExit) as error:
        check.main(['--publish-jobs', value])
    assert error.value.code == 2
    assert 'must be a positive integer' in capsys.readouterr().err


def test_a_change_in_a_folder_of_modules_checks_the_scenarios_that_read_it():
    readers = {'SC97': {'SC97_a', 'SC97_b'}, 'SC97_a': {'SC97_a'}, 'SC97_b': {'SC97_b'}, 'SC98': {'SC98'}}
    ids = ('SC97_a', 'SC97_b', 'SC98')
    assert check.scope_of(['scenarios/SC97/water.scn'], ids, readers)[0] == ('SC97_a', 'SC97_b')
    assert check.scope_of(['scenarios/SC97_b/model.scn', 'scenarios/SC98/style.toml'], ids, readers)[0] == (
        'SC97_b',
        'SC98',
    )
    # A folder that no scenario reads checks everything.
    assert check.scope_of(['scenarios/SC99/water.scn'], ids, readers)[0] is None


def test_a_change_in_a_variant_checks_the_variant_and_one_in_its_package_checks_the_readers():
    readers = {'SC97': ('SC97', 'SC97:a', 'SC97:b'), 'SC97:a': ('SC97:a',), 'SC97:b': ('SC97:b',)}
    ids = tuple(readers)
    assert check.scope_of(['scenarios/SC97/variants/a/model.scn'], ids, readers)[0] == ('SC97:a',)
    assert check.scope_of(['scenarios/SC97/variants/b/tests/test_b.py'], ids, readers)[0] == ('SC97:b',)
    assert check.scope_of(['scenarios/SC97/water.scn'], ids, readers)[0] == ('SC97', 'SC97:a', 'SC97:b')
    # A variant that is gone checks everything.
    assert check.scope_of(['scenarios/SC97/variants/c/model.scn'], ids, readers)[0] is None


def test_a_named_folder_of_modules_selects_the_scenarios_that_read_it(monkeypatch, capsys):
    calls = stub_stages(monkeypatch)
    readers = {'SC97_a': ('SC97_a',), 'SC97_b': ('SC97_b',), 'SC98': ('SC98',), 'SC97': ('SC97_a', 'SC97_b')}
    monkeypatch.setattr(check, 'readers_of', lambda: readers)
    assert check.main(['--scenario', 'SC97', '--scenario', 'SC98', '--skip-summaries']) == 0
    assert [row[2] for row in calls if row[0] == 'tests'] == [('SC97_a', 'SC97_b', 'SC98')]
    assert 'Scope: SC97_a, SC97_b, SC98 (named with --scenario)' in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        check.main(['--scenario', 'SC99'])
    assert error.value.code == 2 and 'SC99' in capsys.readouterr().err


def stub_stages(monkeypatch):
    calls = []
    monkeypatch.setattr(check, 'readers_of', lambda: {sid: (sid,) for sid in IDS})
    monkeypatch.setattr(check, 'stored_runs', lambda: 0)
    monkeypatch.setattr(check, 'lint', lambda: calls.append(('lint',)) or 0)
    monkeypatch.setattr(
        check, 'tests', lambda marker, scope, **kwargs: calls.append(('tests', marker, scope, kwargs)) or 0
    )
    monkeypatch.setattr(
        check,
        'summaries',
        lambda scope, jobs, spreads=False: calls.append(('summaries', scope, jobs, spreads)) or 0,
    )
    monkeypatch.setattr(check, 'verify_store', lambda: calls.append(('store',)) or 0)
    monkeypatch.setattr(check, 'evidence', lambda scope: calls.append(('evidence', scope)) or 0)
    return calls


def test_focused_commands_reuse_one_process_and_explicit_paths_bypass_contract_filter(monkeypatch):
    calls = []
    monkeypatch.setattr(check, 'run', lambda command, **kwargs: calls.append(command) or 0)
    check.tests('not deep', ('SC98',))
    check.tests('not deep', ('SC98',), paths=('tests/test_check.py',), jobs=2)
    check.tests('deep', None)
    check.tests('not deep', None, jobs=4)
    assert calls[0][calls[0].index('-n') + 1] == '0'
    assert '--focused' in calls[0] and '--result-cache-scope=test' in calls[0]
    assert calls[1][-1] == 'tests/test_check.py' and '--no-focused' in calls[1]
    assert calls[1][-2] == '--'
    assert calls[1][calls[1].index('-n') + 1] == '2'
    assert '--no-focused' in calls[2] and '--focused' not in calls[2]
    assert '--all-scenarios' in calls[2]
    assert '--dist=loadfile' in calls[3]
    assert all('--dist=loadfile' not in command for command in calls[:3])


def test_global_environment_removes_an_inherited_scenario_selection(monkeypatch):
    monkeypatch.setenv(check.SELECTION, 'SC98')
    captured = {}

    def execute(command, **kwargs):
        captured.update(kwargs['env'])
        return type('Completed', (), {'returncode': 0})()

    monkeypatch.setattr(check.subprocess, 'run', execute)
    check.run(['unused'], environment={check.SELECTION: None})
    assert check.SELECTION not in captured


def test_docs_only_changes_run_no_models_or_summaries(monkeypatch):
    calls = stub_stages(monkeypatch)
    monkeypatch.setattr(check, 'changed_files', lambda: ['docs/engine.md'])
    assert check.main(['--deep']) == 0
    assert calls == [('lint',)]


def test_shared_code_requires_explicit_test_paths_or_full_scope(monkeypatch):
    calls = stub_stages(monkeypatch)
    monkeypatch.setattr(check, 'changed_files', lambda: ['tools/check.py'])
    with pytest.raises(SystemExit) as error:
        check.main([])
    assert error.value.code == 2 and calls == []


def test_explicit_test_paths_do_not_run_publication_or_store_replay(monkeypatch, capsys):
    calls = stub_stages(monkeypatch)
    assert check.main(['--tests', 'tests/test_check.py', '--deep']) == 0
    assert [row[0] for row in calls] == ['lint', 'tests']
    assert calls[1][3]['paths'] == ('tests/test_check.py',)
    assert calls[1][1] == ''  # Core and deep tests together, without another model compile.
    assert 'Scope: explicit test paths' in capsys.readouterr().out


def test_focused_deep_check_does_not_replay_unrelated_stored_runs(monkeypatch):
    calls = stub_stages(monkeypatch)
    assert check.main(['--scenario', 'SC98', '--deep', '--skip-summaries']) == 0
    assert calls[2:] == [('evidence', ('SC98',))]
    assert [row[0] for row in calls] == ['lint', 'tests', 'evidence']


def test_full_deep_check_retains_exhaustive_stages(monkeypatch):
    calls = stub_stages(monkeypatch)
    assert check.main(['--all', '--deep']) == 0
    assert [row[0] for row in calls] == ['lint', 'tests', 'evidence', 'store', 'summaries']
    assert calls[-1] == ('summaries', None, 4, False)


def test_plan_executes_no_stages(monkeypatch):
    calls = stub_stages(monkeypatch)
    assert check.main(['--scenario', 'SC98', '--plan']) == 0
    assert calls == []


@pytest.mark.parametrize('extra', [['--tests', 'tests/test_check.py'], ['--skip-summaries']])
def test_release_cannot_skip_required_work(monkeypatch, extra):
    calls = stub_stages(monkeypatch)
    with pytest.raises(SystemExit) as error:
        check.main(['--release', *extra])
    assert error.value.code == 2 and calls == []


def test_a_failed_test_stage_reports_its_status(monkeypatch):
    # pytest's own status passes through: 5 (nothing collected) and 4 (bad paths) both fail.
    monkeypatch.setattr(check, 'run', lambda *args, **kwargs: 5)
    assert check.tests('not deep', ('SC98',), paths=('missing.py',)) == 5
    monkeypatch.setattr(check, 'run', lambda *args, **kwargs: 4)
    assert check.tests('', ('SC98',), paths=('missing.py',)) == 4


@pytest.mark.parametrize('extra', [['--scenario', 'SC98'], ['--tests', 'tests/test_check.py']])
def test_full_mode_cannot_be_accidentally_restricted(extra):
    with pytest.raises(SystemExit) as error:
        check.main(['--all', *extra])
    assert error.value.code == 2


@pytest.mark.parametrize('path', ['-q', '', 'does-not-exist.py'])
def test_bad_explicit_paths_cannot_expand_to_full_collection(monkeypatch, path):
    calls = stub_stages(monkeypatch)
    with pytest.raises(SystemExit) as error:
        check.main([f'--tests={path}'])
    assert error.value.code == 2 and calls == []


@pytest.mark.parametrize('differ, status', [([], 0), (['a stored run'], 1)])
def test_the_stored_run_check_fails_on_a_run_that_differs(monkeypatch, tmp_path, differ, status):
    from napkin import store

    calls = []
    monkeypatch.setattr(store, 'default_directory', lambda: tmp_path)
    monkeypatch.setattr(
        store, 'verify', lambda directory, number: calls.append((directory, number)) or differ
    )
    assert check.main(['--verify-store', '3']) == status
    assert calls == [(tmp_path, 3)]


def test_the_stored_run_check_needs_the_store(monkeypatch, capsys):
    from napkin import store

    monkeypatch.setattr(store, 'default_directory', lambda: None)
    with pytest.raises(SystemExit) as error:
        check.main(['--verify-store', '3'])
    assert error.value.code == 2 and 'the store is off' in capsys.readouterr().err


def test_the_stored_runs_stage_runs_in_a_process_of_its_own(monkeypatch):
    calls = []
    monkeypatch.setattr(check, 'run', lambda command, **kwargs: calls.append(command) or 0)
    assert check.verify_store() == 0
    assert calls == [[sys.executable, '-B', '-m', 'tools.check', '--verify-store', '3']]


def test_the_evidence_stage_refuses_a_package_that_rests_a_value_on_no_record(tmp_path, capsys):
    """Item 16 of the plan's changes after G0: a package of the catalogue has no part that rests on no
    record. The synthetic catalogue holds the queue of `tests/evidence/support.py`, each of whose parts
    cites its record, and a copy whose arrivals cite none."""
    from tests.evidence.support import QUEUE, write_package

    write_package(tmp_path, {'model.scn': QUEUE}, owner='SC97')
    bare = QUEUE.replace('in [0 people/h, 10 people/h]  @fixture', 'in [0 people/h, 10 people/h]')
    write_package(tmp_path, {'model.scn': bare}, owner='SC98')
    line = (
        bare.split('\n').index('    input arrivals: people/h = 1 people/h in [0 people/h, 10 people/h]') + 1
    )
    found = check.unsupported(None, tmp_path)
    assert list(found) == ['SC98'] and len(found['SC98']) == 1
    assert found['SC98'][0].startswith(f'scenarios/SC98/model.scn:{line}: queue.arrivals:')
    assert check.evidence(('SC97',), tmp_path) == 0 and check.evidence((), tmp_path) == 0
    capsys.readouterr()
    assert check.evidence(None, tmp_path) == 1
    assert 'SC98: 1 part without the support of a record' in capsys.readouterr().out


def test_the_summaries_sample_current_spreads_only_when_requested(monkeypatch):
    calls = []
    monkeypatch.setattr(check, 'run', lambda command, cwd=None, environment=None: calls.append(command) or 0)
    check.summaries(('SC98',))
    check.summaries(('SC98',), spreads=True)
    check.summaries(None)
    assert ['--sample-spreads' in command for command in calls] == [False, True, False]
    assert all('--committed-spreads' not in command for command in calls)
    assert calls[0][-2:] == ['--scenario', 'SC98']


@pytest.mark.parametrize('extra, spreads', [([], False), (['--spreads'], True)])
def test_the_check_samples_the_spreads_only_when_asked(monkeypatch, extra, spreads):
    calls = stub_stages(monkeypatch)
    assert check.main(['--scenario', 'SC98', *extra]) == 0
    assert calls[-1] == ('summaries', ('SC98',), 1, spreads)


def test_a_release_samples_the_spreads(monkeypatch):
    calls = stub_stages(monkeypatch)
    monkeypatch.setattr(check, 'release_notes', lambda: 0)
    monkeypatch.setattr(check, 'wheel', lambda: 0)
    assert check.main(['--release']) == 0
    assert ('summaries', None, 4, True) in calls


# --- The wheel ------------------------------------------------------------------------------------


def fake_checkout(root):
    """A checkout with the leftovers of an earlier build: a `build/` folder that holds an old copy of
    the catalogue, and two `*.egg-info` (a folder and a file). Gives the paths of its own files."""
    own = ['pyproject.toml', 'requirements.lock', 'napkin/__init__.py', 'tests/release/wheel_smoke.py']
    for name in own:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text('')
    old = root / 'build' / 'lib' / 'napkin' / 'scenarios' / 'old'
    old.mkdir(parents=True)
    (old / 'model.scn').write_text('')
    (root / 'napkin_sim.egg-info').mkdir()
    (root / 'napkin_sim.egg-info' / 'PKG-INFO').write_text('')
    (root / 'old.egg-info').write_text('')
    return own


def stub_wheel_steps(monkeypatch, root, fails=None):
    """Stub `check.run` for `check.wheel` on the fake checkout `root`, with a `PYTHONPATH` that holds
    it: each call is recorded as (command, cwd, environment, the build leftovers at that time). The
    build makes leftovers in the tree and a wheel, as `pip wheel` does; the call number `fails` (from
    0) fails."""
    calls = []

    def run(command, cwd=None, environment=None):
        command = [str(part) for part in command]
        calls.append((command, cwd, environment, check.build_leftovers(root)))
        if '--wheel-dir' in command:
            (root / 'build' / 'lib' / 'napkin').mkdir(parents=True)
            (root / 'napkin_sim.egg-info').mkdir()
            dist = Path(command[command.index('--wheel-dir') + 1])
            dist.mkdir(parents=True)
            (dist / 'napkin_sim-0-py3-none-any.whl').write_text('')
        return 1 if len(calls) - 1 == fails else 0

    monkeypatch.setenv('PYTHONPATH', str(root))
    monkeypatch.setattr(check, 'ROOT', root)
    monkeypatch.setattr(check, 'run', run)
    return calls


def test_the_wheel_is_built_without_an_earlier_builds_leftovers_and_leaves_none(monkeypatch, tmp_path):
    root = tmp_path / 'checkout'
    own = fake_checkout(root)
    assert len(check.build_leftovers(root)) == 3
    calls = stub_wheel_steps(monkeypatch, root)
    assert check.wheel() == 0
    (build, build_cwd, _, _), *fresh = calls
    venv, install, pip_check, smoke = (command for command, *_ in fresh)
    # No step sees a leftover: the build starts in a clean tree, and the fresh environment's steps
    # start after the build's own leftovers are gone. The tree keeps none after the check.
    assert [leftovers for *_, leftovers in calls] == [[]] * 5 and check.build_leftovers(root) == []
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())
    assert files == sorted(own)
    tail = ['wheel', '--no-build-isolation', '--no-deps', str(root), '--wheel-dir']
    assert build_cwd == root and build[1:-1] == ['-B', '-m', 'pip', *tail]
    # The wheel goes into a fresh environment in the same temporary folder, outside the checkout, and
    # the check deletes that folder. Its steps run there, without the PYTHONPATH of the checkout.
    dist = Path(build[-1])
    temporary = dist.parent
    assert root not in temporary.parents and not temporary.exists()
    assert venv[1:] == ['-m', 'venv', str(temporary / 'venv')]
    interpreter = str(temporary / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
    lock, wheels = str(root / 'requirements.lock'), [str(dist / 'napkin_sim-0-py3-none-any.whl')]
    assert install == [interpreter, '-m', 'pip', 'install', '-c', lock, *wheels]
    assert pip_check == [interpreter, '-m', 'pip', 'check']
    assert smoke == [interpreter, '-I', str(root / 'tests/release/wheel_smoke.py'), str(root)]
    assert [cwd for _, cwd, _, _ in fresh] == [temporary] * 4
    assert all(environment['PYTHONPATH'] is None for _, _, environment, _ in fresh)


@pytest.mark.parametrize('fails', range(5), ids=['build', 'venv', 'install', 'pip-check', 'smoke'])
def test_a_failed_step_ends_the_wheel_check_and_removes_the_build_leftovers(monkeypatch, tmp_path, fails):
    root = tmp_path / 'checkout'
    fake_checkout(root)
    calls = stub_wheel_steps(monkeypatch, root, fails)
    assert check.wheel() == 1
    assert len(calls) == fails + 1 and check.build_leftovers(root) == []
