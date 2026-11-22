"""Validate a focused change, or explicitly request the complete repository check.

Scenario changes select their readers, owned tests, central scenario contracts and
owned summaries. They use one test process to reuse compiled models. Documentation
changes run lint only. Shared-code changes require --tests PATH or explicit --all;
they never silently launch the full catalogue. --plan shows the stages without work.

--tests PATH runs only the requested pytest paths and lint, without rendering summaries.
Repeat it for several paths. --deep adds matching deep tests.
--skip-summaries reuses existing publication results for a focused scenario check.

The evidence stage compiles each selected package (every one with --all) and fails when a value of
it rests on no record, the compiler's `no_record` warning (the evidence rule, change 16), or is not
the datum that its record cites, its `datum` warning: another number, or a value that only the run
computes, which a datum, being a number, cannot be.

--all retains the complete tests and catalogue publication comparison.
--all --deep also runs exhaustive admission tests and replays three stored simulations.
--release adds release metadata, current declared spread studies and wheel checks and uses an
empty run store. The current publication check covers readings, source dossiers and the source manifest.

The run store reuses simulations, not compilation or rendering. A cache hit is not a
promise of a fast full-catalogue check. Use targeted tests during development and run
exhaustive validation only when it is needed.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

from . import catalogue
from .catalogue import ROOT

# The variable that selects the scenarios of the tests (tests/selection.py).
SELECTION = 'NAPKIN_TEST_SCENARIOS'
# One thread for the linear algebra of each process: the test workers already use every core.
THREADS = {name: '1' for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')}


def run(command, cwd=ROOT, environment=None):
    """Run one command in the checkout, its output streaming through; return its exit status."""
    environment = {
        key: value
        for key, value in {
            **os.environ,
            **THREADS,
            'PYTHONDONTWRITEBYTECODE': '1',
            **(environment or {}),
        }.items()
        if value is not None
    }
    return subprocess.run([str(part) for part in command], cwd=cwd, env=environment, check=False).returncode


def python(*arguments):
    return [sys.executable, '-B', *arguments]


def lint():
    paths = ('napkin', 'tools', 'tests', 'scenarios', 'conftest.py')
    return run(python('-m', 'ruff', 'check', *paths)) or run(
        python('-m', 'ruff', 'format', '--check', *paths)
    )


def tests(marker, scope=None, *, paths=(), jobs=None):
    """Run explicit paths or selected scenario contracts; full coverage is explicit."""
    if scope == () and not paths:
        return 0
    selection = {SELECTION: None if scope is None else ','.join(scope)}
    focused = scope is not None and not paths
    workers = jobs if jobs is not None else (0 if scope is not None or paths else 'auto')
    return run(
        python(
            '-m',
            'pytest',
            '-q',
            '-p',
            'no:cacheprovider',
            '-n',
            str(workers),
            '--maxfail=1',
            '--focused' if focused else '--no-focused',
            *(['--all-scenarios'] if scope is None else []),
            '--scenario-selection',
            '*' if scope is None else ','.join(scope),
            *(['--result-cache-scope=test'] if focused else []),
            '--durations=0',
            '--durations-min=10',
            '-m',
            marker,
            *(['--'] if paths else []),
            *paths,
        ),
        environment=selection,
    )


def verify_store():
    """Three stored runs, simulated again, are the same bit for bit. They run in a process of their
    own (`--verify-store`), which starts with one thread for the linear algebra (`run`)."""
    return run(python('-m', 'tools.check', '--verify-store', '3'))


def stored_runs_again(number):
    """Simulate `number` stored runs again and compare each with the store: 0 when none differs."""
    from napkin import store

    return 1 if store.verify(store.default_directory(), number) else 0


def summaries(scope=None, jobs=4, spreads=False):
    """Check current readings and dossiers. A full check also verifies the manifest. Sampling
    replays the current declared spreads at their authored sizes when requested."""
    if scope == ():
        return 0
    publish = python(
        '-m', 'tools.publish', '--check', '--jobs', str(jobs), *(['--sample-spreads'] if spreads else [])
    )
    if scope is None:
        return run(publish)
    selected = [part for sid in scope for part in ('--scenario', sid)]
    return run([*publish, *selected])


def changed_files(base='main'):
    """The files that differ from the merge base of HEAD with `base` (or `origin/<base>`): committed,
    staged, unstaged and new. None when git cannot tell."""

    def git(*arguments):
        done = subprocess.run(['git', *arguments], cwd=ROOT, capture_output=True, text=True, check=False)
        return done.stdout.splitlines() if done.returncode == 0 else None

    for reference in (base, f'origin/{base}'):
        found = git('merge-base', 'HEAD', reference)
        if found:
            break
    else:
        return None
    tracked = git('diff', '--name-only', '--no-renames', found[0])
    new = git('ls-files', '--others', '--exclude-standard')
    if tracked is None or new is None:
        return None
    return sorted({name for name in (*tracked, *new) if name})


def readers_of(root=ROOT):
    """{owner: the owners whose models read a file of its folder} (`catalogue.readers`): each owner with
    a model reads its own folder, and the folder of a family's modules is read by the models that use
    them."""
    return catalogue.readers(root)


def scope_of(paths, scenario_ids, readers=None):
    """(scope, reason): the scenarios whose checks cover every change in `paths`, or None when the
    change needs the whole check, with the reason in words. A change in the folder of an owner
    (`catalogue.owner_of`) covers the scenarios that read the folder (`readers`, {owner: scenarios}; by
    default each scenario reads only its own folder), so a change in a folder of modules covers the
    scenarios that use them."""
    if not paths:
        return None, 'no file differs from main'
    readers = readers if readers is not None else {sid: (sid,) for sid in scenario_ids}
    scope = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        owner = catalogue.owner_of(path)
        if owner is not None:
            if not readers.get(owner):
                return None, f'{path} is in the folder of a scenario that is gone, or of no scenario'
            scope |= set(readers[owner])
        elif not path.endswith('.md') or not (
            len(parts) == 1
            or parts[0] == 'docs'
            or PurePosixPath(path).is_relative_to(catalogue.DOCS)
            or path == catalogue.INDEX
        ):
            # The written docs: those at the root, the engine's in docs/, the catalogue's in
            # scenarios/docs/ and its index. Data in a folder of docs (the source manifest) is read by
            # the tests, so it is not documentation: it needs the tests that read it.
            return None, f'{path} is outside the scenario folders and the written docs'
    names = ', '.join(sorted(scope)) or 'no scenario'
    return tuple(sorted(scope)), f'every change is in the docs or in the folder of {names}'


def unsupported(scope=None, root=ROOT):
    """{owner: [message]} of each owner of the catalogue at `root` that runs as a model of its own
    (`catalogue.entries`), or of those that `scope` names, whose model a record does not support: the
    warnings of the evidence rule (item 16 of the plan's changes after G0), the reports of its compile
    with the code `no_record`, a value that rests on no record, or `datum`, a value that differs from a
    datum that its record cites (`napkin.model.support`), each at its file and line. A model being
    explored still runs with them, but a scenario package of the catalogue has none. A model that does
    not compile gives its first problem, since its evidence cannot be read."""
    from napkin.model.compile import load_scenario
    from napkin.model.language.problems import LanguageError
    from napkin.model.support import CODE, DATUM

    def place(problem):
        file = Path(problem.file)
        return f'{file.relative_to(root).as_posix() if file.is_relative_to(root) else file}:{problem.line}'

    found = {}
    for name, entry in catalogue.entries(root).items():
        if scope is not None and name not in scope:
            continue
        try:
            reports = load_scenario(entry).reports
        except LanguageError as error:
            first = error.problems[0]
            found[name] = [
                f'{place(first)}: it does not compile, so its evidence is not read: {first.message}'
            ]
            continue
        warned = [f'{place(item)}: {item.message}' for item in reports if item.code in (CODE, DATUM)]
        if warned:
            found[name] = warned
    return found


def evidence(scope=None, root=ROOT):
    """The stage of the evidence rule: 0 when a record supports every value of each selected package
    (`unsupported`), else 1, with each warning."""
    if scope == ():
        return 0
    found = unsupported(scope, root)
    for name, messages in found.items():
        count = len(messages)
        print(f'{name}: {count} {"part" if count == 1 else "parts"} without the support of a record')
        for message in messages:
            print(f'  {message}')
    return 1 if found else 0


def catalogue_problems(model):
    """The problems of a model of the catalogue against the catalogue's own rules, which the language
    leaves open (scenarios/docs/catalogue.md): each output says whom it covers, with a scope of its own or the
    scope on the scenario line. Each problem names the output as the file names it."""

    from tools.publish.brief import brief_of, reported_paths, shown, value_note

    if model.declared.scenario.scope is not None:
        return []
    paths = dict.fromkeys([*(reported_paths(model) or ()), *shown(brief_of(model), model)])
    return [
        {
            'code': 'catalogue',
            'path': name,
            'message': 'an output of the catalogue says whom it covers: give it scope "…", or the scenario one',
        }
        for name in paths
        if value_note(model, 'reporting', name, 'scope') is None
    ]


def release_notes():
    """The package version has notes under its heading in CHANGELOG.md, and a v* tag at HEAD names it."""
    from napkin import __version__

    notes, keep = [], False
    for line in (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('## '):
            keep = line == f'## {__version__}' or line.startswith(f'## {__version__} ')
        elif keep:
            notes.append(line)
    if not any(line.strip() for line in notes):
        print(f'CHANGELOG.md has no notes under a "## {__version__}" heading')
        return 1
    tags = subprocess.run(
        ['git', 'tag', '--points-at', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    versions = [tag for tag in tags if re.fullmatch(r'v\d+\.\d+\.\d+.*', tag)]
    if versions and f'v{__version__}' not in versions:
        print(f'The tag {versions[0]} at HEAD does not name the package version {__version__}')
        return 1
    print(f'Release {__version__}: notes found; tag HEAD v{__version__} once the check passes')
    return 0


def build_leftovers(root):
    """The folders of an earlier build in the checkout `root`: `build/` and each `*.egg-info`. A
    leftover `build/lib/napkin/scenarios` goes into the next wheel, as `pip wheel` builds in the tree."""
    return [path for path in [root / 'build', *sorted(root.glob('*.egg-info'))] if path.exists()]


def remove_build_leftovers(root):
    """Delete the folders of an earlier build in the checkout `root` (`build_leftovers`)."""
    for path in build_leftovers(root):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def wheel():
    """Build the wheel and install it in a fresh environment outside the checkout, then run the smoke
    test there (`tests/release/wheel_smoke.py`).

    It deletes `build/` and `*.egg-info` before the build, and again after it. The commands of the
    fresh environment run from its temporary folder, without the `PYTHON*` variables of this
    process: a `PYTHONPATH` that holds the checkout would show its modules, and a `*.egg-info` there
    reads as an installed `napkin-sim`, which pip then does not install."""
    remove_build_leftovers(ROOT)
    try:
        with tempfile.TemporaryDirectory(prefix='napkin-wheel-') as name:
            temporary = Path(name)
            dist, environment = temporary / 'dist', temporary / 'venv'
            build = python(
                '-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps', ROOT, '--wheel-dir', dist
            )
            if run(build, cwd=ROOT):
                return 1
            remove_build_leftovers(ROOT)
            isolated = {
                key: None
                for key in os.environ
                if key.startswith('PYTHON') and key != 'PYTHONDONTWRITEBYTECODE'
            }

            def fresh(command):
                return run(command, cwd=temporary, environment=isolated)

            if fresh([sys.executable, '-m', 'venv', environment]):
                return 1
            interpreter = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            wheels = sorted(dist.glob('*.whl'))
            return (
                fresh([interpreter, '-m', 'pip', 'install', '-c', ROOT / 'requirements.lock', *wheels])
                or fresh([interpreter, '-m', 'pip', 'check'])
                or fresh([interpreter, '-I', ROOT / 'tests/release/wheel_smoke.py', ROOT])
            )
    finally:
        remove_build_leftovers(ROOT)


def stored_runs():
    """The number of runs in the run store, or None when it is off."""
    from napkin import store

    directory = store.default_directory()
    if directory is None or not directory.is_dir():
        return None if directory is None else 0
    return sum(1 for _ in directory.glob('??/*.run'))


def positive_integer(text):
    """A positive worker count at the CLI boundary."""
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('must be a positive integer') from exc
    if value < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return value


def worker_count(text):
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('must be a nonnegative integer') from exc
    if value < 0:
        raise argparse.ArgumentTypeError('must be a nonnegative integer')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--scenario', action='append', metavar='ID', help='Check this scenario (repeatable), not the changes'
    )
    parser.add_argument('--all', action='store_true', help='Check everything, whatever the changes')
    parser.add_argument('--deep', action='store_true', help='Also run the deep tests (pytest -m deep)')
    parser.add_argument(
        '--tests',
        action='append',
        metavar='PATH',
        help='Run only these pytest paths or node IDs (repeatable)',
    )
    parser.add_argument(
        '--test-jobs',
        type=worker_count,
        metavar='N',
        help='Pytest workers; 0 runs in one process (default for focused checks)',
    )
    parser.add_argument(
        '--skip-summaries',
        action='store_true',
        help='Reuse existing summaries without comparing a fresh render',
    )
    parser.add_argument(
        '--spreads',
        action='store_true',
        help='Also run the current declared spreads at their authored sample counts. A release does this.',
    )
    parser.add_argument(
        '--plan', action='store_true', help='Show the scope and stages without running checks'
    )
    parser.add_argument(
        '--release',
        action='store_true',
        help='The check of a release: notes, --deep, an empty store, the wheel',
    )
    parser.add_argument(
        '--publish-jobs',
        type=positive_integer,
        default=None,
        metavar='N',
        help='Publication workers (default: 1 for selected scenarios, 4 for the full catalogue)',
    )
    # The stage "Stored runs" of a deep check runs this in a process of its own (`verify_store`).
    parser.add_argument('--verify-store', type=positive_integer, metavar='N', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.verify_store:
        from napkin import store

        if store.default_directory() is None:
            parser.error('the store is off (NAPKIN_STORE=off)')
        return stored_runs_again(args.verify_store)
    if args.all and (args.scenario or args.tests):
        parser.error('--all cannot be combined with --scenario or --tests')
    for test_path in args.tests or ():
        source = test_path.split('::', 1)[0]
        if not source or source.startswith('-') or not (ROOT / source).exists():
            parser.error(f'--tests must name an existing path or node ID: {test_path!r}')
    if args.release and (args.scenario or args.all or args.tests or args.skip_summaries):
        parser.error('a release checks everything; do not restrict tests, scenarios or summaries')
    if args.release:
        scope, reason = (
            None,
            'the current release checks tests, publications, declared spreads, notes and wheel',
        )
    elif args.all:
        scope, reason = None, '--all'
    elif args.scenario:
        # An owner covers the scenarios that read its folder: a scenario covers itself, and the folder of
        # a family's modules the scenarios of the family (`catalogue.covered`).
        readers = readers_of()
        unknown = sorted(set(args.scenario) - set(readers))
        if unknown:
            parser.error(f'no scenario folder for {", ".join(unknown)}')
        scope, reason = catalogue.covered(args.scenario, readers), 'named with --scenario'
    elif args.tests:
        scope, reason = None, 'explicit test paths only'
    else:
        changed = changed_files()
        readers = readers_of()
        scope, reason = (
            (None, 'git cannot list the changes')
            if changed is None
            else scope_of(changed, tuple(readers), readers)
        )
        if scope is None:
            parser.error(
                f'{reason}; choose --tests PATH, --scenario ID, or --all explicitly (use --plan to inspect the stages)'
            )
    scope_label = (
        ('explicit test paths' if args.tests else 'everything')
        if scope is None
        else ', '.join(scope) or 'no scenario'
    )
    print(f'Scope: {scope_label} ({reason})')
    paths_only = bool(args.tests and not args.all and not args.release)
    deep = args.deep or args.release
    publish_jobs = args.publish_jobs if args.publish_jobs is not None else (4 if scope is None else 1)
    with_summaries = not args.skip_summaries and not paths_only and scope != ()
    test_options = {'paths': tuple(args.tests or ()), 'jobs': args.test_jobs}
    steps = [
        *([('Release notes', release_notes)] if args.release else []),
        ('Lint', lint),
        *(
            [
                (
                    'Python tests (including deep)' if deep else 'Python tests',
                    lambda: tests('' if deep else 'not deep', scope, **test_options),
                )
            ]
            if scope != () or args.tests
            else []
        ),
        *([('Evidence', lambda: evidence(scope))] if not paths_only and scope != () else []),
        *([('Stored runs', verify_store)] if deep and scope is None and not paths_only else []),
        *(
            [
                (
                    'Committed summaries',
                    lambda: summaries(scope, publish_jobs, spreads=args.spreads or args.release),
                )
            ]
            if with_summaries
            else []
        ),
        *([('Wheel', wheel)] if args.release else []),
    ]
    print('Stages: ' + ', '.join(label for label, _ in steps))
    if args.tests:
        print('Test paths: ' + ', '.join(args.tests))
    elif scope:
        print(
            'Tests: owned scenario/family tests and marked scenario contracts; unrelated central tests excluded'
        )
    print(
        'Pytest workers: '
        + str(
            args.test_jobs
            if args.test_jobs is not None
            else (0 if scope is not None or args.tests else 'auto')
        )
    )
    if not with_summaries:
        print('Summary comparison: not selected')
    if args.plan:
        return 0
    with tempfile.TemporaryDirectory(prefix='napkin-release-store-') as empty:
        if args.release:
            # A release never depends on stored runs: every run is simulated afresh.
            os.environ['NAPKIN_STORE'] = empty
        before = stored_runs()
        started = time.monotonic()
        for label, step in steps:
            print(f'[check {time.monotonic() - started:6.1f}s] {label}', flush=True)
            if step():
                print(f'[check {time.monotonic() - started:6.1f}s] {label}: FAILED')
                return 1
        after = stored_runs()
    print(f'[check {time.monotonic() - started:6.1f}s] All checks passed')
    if before is not None and after is not None:
        print(f'The check simulated {max(0, after - before)} runs; the run store holds {after}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
