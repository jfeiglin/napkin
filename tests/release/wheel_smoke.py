"""The installed wheel, outside the checkout, in five steps (P4.12):

1. The wheel ships the engine only: the `napkin` package as the checkout has it, its prelude and its
   schemas, the `napkin` script and the three libraries of the engine. No catalogue, library, tool,
   publisher, evidence or workbench ships.
2. `napkin new`, then `napkin run`: the plain starter, and a starter with the variants `east` and
   `west`, which `run` lists without `--variant` (exit 2) and runs with it.
3. The examples, copied from the checkout's `examples/`: `napkin compile`, `run`, `sample` and `draw`
   each one, and `napkin play` each one that has an actor.
4. `napkin fmt --check` on the starters, the examples and each catalogue package of the checkout.
5. `napkin compile` each catalogue package of the checkout, which finds the library through its own
   `library "../library"` line.

    python -I tests/release/wheel_smoke.py CHECKOUT

`check --release` runs it (`tools.check.wheel`) with the interpreter of a fresh environment that has
the wheel installed, from a temporary folder outside the checkout. Each command is the installed
`napkin` script, run from a temporary folder with no run store (`NAPKIN_STORE=off`) and no `PYTHON*`
variable, so it imports the installed package only. The checks read exit codes, JSON fields and
files, never the words of a message. Each step prints its time.
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from importlib import metadata, util
from pathlib import Path, PurePosixPath

import napkin

# The name of the distribution, and of the command that it installs.
DISTRIBUTION = 'napkin-sim'
SCRIPT = Path(sysconfig.get_path('scripts')) / ('napkin.exe' if os.name == 'nt' else 'napkin')
# The libraries of the engine: the only requirements of the wheel outside its extras.
REQUIRED = {'jsonschema', 'numpy', 'scipy'}
# Names that no part of the wheel takes, as a folder of the package or beside it: the catalogue, its
# library, the maintainer tools and the removed workbench.
NOT_SHIPPED = ('scenarios', 'library', 'tools', 'publish', 'evidence', 'workbench', 'presentation')
# A catalogue package is a folder of `scenarios/` named by this rule, which holds a `model.scn`; so is
# a variant, in its package's `variants/`. The catalogue's own folders are never packages.
NAME = re.compile(r'[a-z][a-z0-9_]*', re.ASCII)
CATALOGUE_FOLDERS = {'docs', 'library', 'tests'}
ENTRY = 'model.scn'
# The commands' environment: no variable that can point Python at the checkout, and no run store.
ENVIRONMENT = {
    **{key: value for key, value in os.environ.items() if not key.startswith('PYTHON')},
    'PYTHONDONTWRITEBYTECODE': '1',
    'NAPKIN_STORE': 'off',
}
# The longest that one command may take, in seconds.
TIMEOUT = 900
# The variants of the second starter (`napkin new --variants`).
VARIANTS = ('east', 'west')
# The samples and the workers of `napkin sample`.
SAMPLES, JOBS = 20, 2
SVG = '{http://www.w3.org/2000/svg}'


# --- Commands -------------------------------------------------------------------------------------


def napkin_command(*argv, cwd):
    """`napkin ARGV`, the installed script, run from `cwd`: the completed process, its output as text."""
    return subprocess.run(
        [str(SCRIPT), *map(str, argv)],
        cwd=cwd,
        env=ENVIRONMENT,
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=TIMEOUT,
        check=False,
    )


def expect(done, code=0):
    """`done`, after a check that it exited with `code`; else the command, its exit code and its
    standard error."""
    assert done.returncode == code, (done.args, done.returncode, done.stderr[-4000:])
    return done


def json_of(*argv, cwd):
    """The JSON document that `napkin ARGV` writes, after a check that it exits 0 with schema 1."""
    doc = json.loads(expect(napkin_command(*argv, cwd=cwd)).stdout)
    assert doc['schema_version'] == '0.0.1', (argv, doc.get('schema_version'))
    return doc


def admissible(report, name):
    """Check a report of `napkin run --json`: admitted with no error, with runs, and each estimated
    value finite."""
    errors = [item for item in report['diagnostics'] if item.get('severity', 'error') == 'error']
    assert report['admissible'] is True and not errors, (name, report['diagnostics'])
    assert report['runs'], name
    for run, shown in report['runs'].items():
        for point, row in shown['reporting_points'].items():
            assert set(row['statuses']) == set(shown['outcomes']), (name, run, point)
            for key, status in row['statuses'].items():
                if status == 'estimated':
                    assert math.isfinite(row['values'][key]), (name, run, point, key)


def timed(title, step, *args):
    """Run `step(*args)` and print its time."""
    start = time.perf_counter()
    found = step(*args)
    print(f'{title}: {time.perf_counter() - start:.1f} s', flush=True)
    return found


# --- 1. The engine only ---------------------------------------------------------------------------


def files_below(folder):
    """{path in `folder`: its bytes} of each file below `folder`, outside `__pycache__` and the names
    that start with a dot."""
    return {
        PurePosixPath(*path.relative_to(folder).parts): path.read_bytes()
        for path in folder.rglob('*')
        if path.is_file()
        and '__pycache__' not in path.parts
        and not any(part.startswith('.') for part in path.relative_to(folder).parts)
    }


def packages_of(files):
    """The dotted names of the packages of `napkin` among `files` (each folder with an `__init__.py`)."""
    return sorted('.'.join(('napkin', *path.parent.parts)) for path in files if path.name == '__init__.py')


def engine_only(checkout, scratch):
    package = Path(napkin.__file__).resolve().parent
    environment = Path(sys.prefix).resolve()
    assert sys.prefix != sys.base_prefix, 'the smoke test runs outside a virtual environment'
    assert environment in package.parents, f'napkin is imported from {package}'
    assert checkout not in package.parents, f'napkin is imported from {package}'
    # A command imports the same package.
    done = subprocess.run(
        [sys.executable, '-c', 'import napkin; print(napkin.__file__)'],
        cwd=scratch,
        env=ENVIRONMENT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert Path(done.stdout.strip()).resolve().parent == package, done.stdout
    # The package is the checkout's `napkin`, file for file and byte for byte: its subpackages, its
    # modules, the prelude and the schemas. A file of an old build folder would differ.
    shipped, source = files_below(package), files_below(checkout / 'napkin')
    assert packages_of(shipped) == packages_of(source), (packages_of(shipped), packages_of(source))
    assert sorted(shipped) == sorted(source), sorted(set(shipped) ^ set(source))
    assert [path for path in shipped if shipped[path] != source[path]] == []
    assert PurePosixPath('std/units.json') in shipped, 'the prelude does not ship'
    assert [path for path in shipped if path.parent.name == 'schema' and path.suffix == '.json']
    # No model ships: no catalogue, no library and no example.
    assert not [path for path in shipped if path.suffix == '.scn' or path.name == 'vocabulary.json']
    for name in NOT_SHIPPED:
        assert not (package / name).exists(), f'napkin/{name} ships'
        assert not (package.parent / name).exists(), f'{name} ships beside napkin'
        assert util.find_spec(name) is None, f'{name} is importable'
    # The RECORD: the package's files, one dist-info folder and the script; nothing else.
    record = [PurePosixPath(str(path)) for path in metadata.files(DISTRIBUTION)]
    infos = {path.parts[0] for path in record if path.parts[0].endswith('.dist-info')}
    assert len(infos) == 1 and next(iter(infos)).startswith('napkin_sim-'), infos
    tops = {path.parts[0] for path in record} - infos - {'napkin'}
    assert tops <= {'..'}, tops
    assert {path.name for path in record if path.parts[0] == '..'} == {SCRIPT.name}
    recorded = {
        PurePosixPath(*path.parts[1:])
        for path in record
        if path.parts[0] == 'napkin' and '__pycache__' not in path.parts
    }
    assert recorded == set(shipped), sorted(recorded ^ set(shipped))
    # The requirements: the engine's three libraries; the others are the extras of a checkout.
    needed = {
        re.split(r'[<>=!~ ;\[]', item, maxsplit=1)[0]
        for item in metadata.requires(DISTRIBUTION)
        if 'extra ==' not in item
    }
    assert needed == REQUIRED, needed
    # The script, and the module.
    assert SCRIPT.is_file(), f'no script {SCRIPT}'
    version = expect(napkin_command('--version', cwd=scratch)).stdout.strip()
    assert version == napkin.__version__ == metadata.version(DISTRIBUTION), version
    done = subprocess.run(
        [sys.executable, '-m', 'napkin', '--help'],
        cwd=scratch,
        env=ENVIRONMENT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and done.stdout, (done.returncode, done.stderr)
    return len(shipped)


# --- 2. napkin new, then napkin run ---------------------------------------------------------------


def starters(folder):
    folder.mkdir()
    expect(napkin_command('new', 'plain', cwd=folder))
    assert (folder / 'plain' / ENTRY).is_file()
    assert expect(napkin_command('run', 'plain', cwd=folder)).stdout
    report = json_of('run', '--json', 'plain', cwd=folder)
    admissible(report, 'plain')
    assert report['variant'] is None
    expect(napkin_command('new', 'regions', '--variants', ','.join(VARIANTS), cwd=folder))
    assert (folder / 'regions' / ENTRY).is_file()
    assert all((folder / 'regions' / 'variants' / name / ENTRY).is_file() for name in VARIANTS)
    # Without --variant, run lists the variants, each by its name, and stops.
    done = expect(napkin_command('run', 'regions', cwd=folder), 2)
    words = set(re.findall(r'[A-Za-z0-9_]+', done.stdout + done.stderr))
    assert set(VARIANTS) <= words, (VARIANTS, done.stderr)
    for name in VARIANTS:
        report = json_of('run', '--json', 'regions', '--variant', name, cwd=folder)
        admissible(report, f'regions:{name}')
        assert report['variant'] == name, report['variant']


# --- 3. The examples ------------------------------------------------------------------------------


def sampled(doc, name):
    """The number of runs of a `napkin sample --json` document that have samples, after a check of
    each one: SAMPLES samples, and each summary in order (min ≤ p5 ≤ … ≤ p95 ≤ max, the mean between
    min and max)."""
    for run, record in doc['runs'].items():
        assert record['settings']['samples'] == SAMPLES and len(record['samples']) == SAMPLES, (name, run)
        for key, summary in record['summary'].items():
            if summary['estimated']:
                order = [summary[q] for q in ('min', 'p5', 'p25', 'p50', 'p75', 'p95', 'max')]
                assert order == sorted(order), (name, run, key, order)
                assert summary['min'] <= summary['mean'] <= summary['max'], (name, run, key)
    return len(doc['runs'])


def drawn(path, model):
    """Check the SVG of `napkin draw`: it parses, its root is an SVG element, each thing that it draws
    is a thing of the model, and each part and each arrow belongs to a drawn thing."""
    root = ET.parse(path).getroot()
    assert root.tag == f'{SVG}svg', root.tag
    things = {entity.name for entity in model.scenario.entities}
    cards = {element.get('data-thing') for element in root.iter() if element.get('data-thing')}
    assert cards and cards <= things, (cards, things)
    for element in root.iter():
        for part in ('data-stock', 'data-flow', 'data-var', 'data-event'):
            if element.get(part):
                assert element.get(part).rpartition('.')[0] in cards, (part, element.get(part))
        for part in ('data-from', 'data-to'):
            if element.get(part):
                assert element.get(part) in cards, (part, element.get(part))


def played(folder, scratch, control):
    """`napkin play --json --control CONTROL` on `folder`, which picks the first outcome that can
    happen at each decision: the result line, after a check that the run is finished."""
    errors = scratch / f'{folder.name}.play.err'
    with errors.open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(
            [str(SCRIPT), 'play', '--json', '--control', control, folder],
            cwd=scratch,
            env=ENVIRONMENT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            encoding='utf-8',
        )
        watchdog = threading.Timer(TIMEOUT, process.kill)
        watchdog.start()
        picks, result = [], None
        try:
            while result is None:
                text = process.stdout.readline()
                if not text:
                    break
                line = json.loads(text)
                assert line['schema_version'] == '0.0.1', line
                assert line['type'] in ('decision', 'result'), (line, errors.read_text('utf-8'))
                if line['type'] == 'result':
                    result = line
                    continue
                pick = next(item['name'] for item in line['outcomes'] if item['available'])
                picks.append((line['event'], pick))
                process.stdin.write(json.dumps({'pick': pick, 'reason': None}) + '\n')
                process.stdin.flush()
            process.stdin.close()
            code = process.wait()
        finally:
            watchdog.cancel()
            process.kill()
    assert result is not None, ('no result line', errors.read_text('utf-8'))
    assert code == 0 and result['finished'] is True, (code, result, errors.read_text('utf-8'))
    assert picks, f'{control} decided nothing in {folder.name}'
    assert [(item['event'], item['outcome']) for item in result['picks']] == picks
    admissible(result['report'], f'{folder.name} played')
    return len(picks)


def examples(checkout, folder, scratch):
    shutil.copytree(checkout / 'examples', folder, ignore=shutil.ignore_patterns('__pycache__', '.*'))
    found = sorted(path for path in folder.iterdir() if (path / ENTRY).is_file())
    assert found, 'no example'
    pictures = scratch / 'pictures'
    pictures.mkdir()
    sampled_runs = plays = 0
    for example in found:
        start = time.perf_counter()
        doc = json_of('compile', '--json', example, cwd=scratch)
        models = doc['models'].values()
        assert models and all(item['admissible'] for item in models), doc['diagnostics']
        actors = [actor['name'] for item in models for actor in item['actors']]
        admissible(json_of('run', '--json', example, cwd=scratch), example.name)
        doc = json_of('sample', '--samples', SAMPLES, '--jobs', JOBS, '--json', example, cwd=scratch)
        sampled_runs += sampled(doc, example.name)
        picture = pictures / f'{example.name}.svg'
        expect(napkin_command('draw', example, '-o', picture, cwd=scratch))
        drawn(picture, napkin.load_scenario(example / ENTRY))
        if actors:
            plays += played(example, scratch, actors[0])
        print(f'  {example.name}: {time.perf_counter() - start:.1f} s', flush=True)
    assert sampled_runs, 'no example has an input with a distribution'
    assert plays, 'no example has an actor'
    return len(found)


# --- 4. napkin fmt --check ------------------------------------------------------------------------


def catalogue(checkout):
    """The catalogue packages of the checkout, by their folders: {name: [its variants' names]}."""
    found = {}
    for folder in sorted((checkout / 'scenarios').iterdir()):
        if folder.name in CATALOGUE_FOLDERS or not NAME.fullmatch(folder.name):
            continue
        if (folder / ENTRY).is_file():
            variants = folder / 'variants'
            found[folder.name] = sorted(
                path.name
                for path in (variants.iterdir() if variants.is_dir() else ())
                if NAME.fullmatch(path.name) and (path / ENTRY).is_file()
            )
    return found


def formatted(paths, model, scratch):
    expect(napkin_command('fmt', '--check', *paths, cwd=scratch))
    # A counterexample: `model` with spaces at the end of each line is not formatted, and `--check`
    # lists it and leaves it as it is.
    spaced = scratch / 'spaced'
    spaced.mkdir()
    text = '\n'.join(f'{line}   ' if line else line for line in model.read_text('utf-8').split('\n'))
    (spaced / ENTRY).write_text(text, encoding='utf-8')
    done = expect(napkin_command('fmt', '--check', spaced, cwd=scratch), 1)
    assert done.stdout.strip() and (spaced / ENTRY).read_text('utf-8') == text


# --- 5. The catalogue -----------------------------------------------------------------------------


def compiled(checkout, scratch, packages):
    assert packages, 'no catalogue package'
    for name, variants in packages.items():
        start = time.perf_counter()
        doc = json_of('compile', '--json', checkout / 'scenarios' / name, cwd=scratch)
        assert doc['package'] == name, doc['package']
        expected = [f'{name}:{variant}' for variant in variants] or [name]
        assert sorted(doc['models']) == expected, sorted(doc['models'])
        assert all(item['admissible'] for item in doc['models'].values()), doc['diagnostics']
        print(f'  {name} ({len(expected)} models): {time.perf_counter() - start:.1f} s', flush=True)
    return len(packages)


def main(argv):
    checkout = Path(argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='napkin-smoke-') as name:
        scratch = Path(name).resolve()
        here = Path.cwd().resolve()
        assert checkout not in (scratch, *scratch.parents) and checkout not in (here, *here.parents)
        start = time.perf_counter()
        shipped = timed('1. the engine only', engine_only, checkout, scratch)
        timed('2. napkin new, then napkin run', starters, scratch / 'starters')
        count = timed('3. the examples', examples, checkout, scratch / 'examples', scratch)
        packages = catalogue(checkout)
        folders = [
            scratch / 'starters',
            scratch / 'examples',
            *(checkout / 'scenarios' / p for p in packages),
        ]
        plain = scratch / 'starters' / 'plain' / ENTRY
        timed('4. napkin fmt --check', formatted, folders, plain, scratch)
        timed('5. napkin compile the catalogue', compiled, checkout, scratch, packages)
        print(
            f'Wheel {napkin.__version__}: {shipped} files of the engine; {count} examples and '
            f'{len(packages)} catalogue packages pass ({time.perf_counter() - start:.1f} s)'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
