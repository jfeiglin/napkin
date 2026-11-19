"""The installed wheel, outside the checkout, in five steps (P4.12):

1. The wheel ships the engine only: the `napkin` package as the checkout has it, its prelude and its
   schemas, the `napkin` script and the three libraries of the engine. No catalogue, library, tool,
   publisher, evidence or workbench ships.
2. `napkin new`, then `napkin run`: the plain starter, and a starter with the variants `east` and
   `west`, whose main file and each variant run (a variant is the MODEL of its own folder).
3. The examples, copied from the checkout's `examples/`: `napkin compile`, `run`, `sample` and `draw`
   each one. (`napkin play` comes back as a client of the checkpoints of slice S7.)
4. `napkin fmt --check` on the starters, the examples and each catalogue package of the checkout.
5. `napkin compile` each model of each catalogue package of the checkout (its main file, or each
   variant), which finds the library through its own `library "../library"` line.

Steps 3 to 5 read the examples and the catalogue in the language of the rewrite: they pass once
stage M has migrated them (`examples/reservoir` and `scenarios/`).

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
    """The JSON document that `napkin ARGV` writes, after a check that it exits 0."""
    return json.loads(expect(napkin_command(*argv, cwd=cwd)).stdout)


def admissible(report, name):
    """Check a report of `napkin run --json`: no diagnostic, a run to its horizon, values at its
    times, and each number finite."""
    assert report['diagnostics'] == [] and report['stopped'] is None, (name, report['diagnostics'])
    assert report['values'] and report['times'], name
    for path, value in report['values'].items():
        assert len(value['values']) == len(report['times']), (name, path)
        for item in value['values']:
            if isinstance(item, float):
                assert math.isfinite(item), (name, path)


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
    assert report['run'] is None
    expect(napkin_command('new', 'regions', '--variants', ','.join(VARIANTS), cwd=folder))
    assert (folder / 'regions' / ENTRY).is_file()
    assert all((folder / 'regions' / 'variants' / name / ENTRY).is_file() for name in VARIANTS)
    admissible(json_of('run', '--json', 'regions', cwd=folder), 'regions')
    for name in VARIANTS:
        report = json_of('run', '--json', f'regions/variants/{name}', cwd=folder)
        admissible(report, f'regions:{name}')
        assert report['title'].endswith(f': {name}'), report['title']


# --- 3. The examples ------------------------------------------------------------------------------


def sampled(doc, name):
    """1 when a `napkin sample --json` document has a spread, else 0, after a check of it: SAMPLES
    samples, and each summary in order (least <= p5 <= ... <= p95 <= greatest, the mean between the
    least and the greatest)."""
    assert doc['samples'] == SAMPLES and len(doc['draws']) == SAMPLES, name
    for path, value in doc['values'].items():
        if value['estimated']:
            order = [
                value['least'],
                *(value['percentiles'][f'p{p}'] for p in (5, 25, 50, 75, 95)),
                value['greatest'],
            ]
            assert order == sorted(order), (name, path, order)
            assert value['least'] <= value['mean']['value'] <= value['greatest'], (name, path)
    return 1 if doc['drawn'] else 0


def drawn(path, model):
    """Check the SVG of `napkin draw`: it parses, its root is an SVG element, each thing that it draws
    is a thing of the model, and each part and each arrow belongs to a drawn thing."""
    from napkin.draw.things import Things

    root = ET.parse(path).getroot()
    assert root.tag == f'{SVG}svg', root.tag
    things = set(Things(model).cards)
    cards = {element.get('data-thing') for element in root.iter() if element.get('data-thing')}
    assert cards and cards <= things, (cards, things)
    for element in root.iter():
        for part in ('data-stock', 'data-flow', 'data-var', 'data-event'):
            if element.get(part):
                assert element.get(part).rpartition('.')[0] in cards, (part, element.get(part))
        for part in ('data-from', 'data-to'):
            if element.get(part):
                assert element.get(part) in cards, (part, element.get(part))


def examples(checkout, folder, scratch):
    shutil.copytree(checkout / 'examples', folder, ignore=shutil.ignore_patterns('__pycache__', '.*'))
    found = sorted(path for path in folder.iterdir() if (path / ENTRY).is_file())
    assert found, 'no example'
    pictures = scratch / 'pictures'
    pictures.mkdir()
    sampled_runs = 0
    for example in found:
        start = time.perf_counter()
        doc = json_of('compile', '--json', example, cwd=scratch)
        assert doc['diagnostics'] == [], doc['diagnostics']
        admissible(json_of('run', '--json', example, cwd=scratch), example.name)
        doc = json_of('sample', '--samples', SAMPLES, '--jobs', JOBS, '--json', example, cwd=scratch)
        sampled_runs += sampled(doc, example.name)
        picture = pictures / f'{example.name}.svg'
        expect(napkin_command('draw', example, '-o', picture, cwd=scratch))
        drawn(picture, napkin.load_scenario(example / ENTRY))
        print(f'  {example.name}: {time.perf_counter() - start:.1f} s', flush=True)
    assert sampled_runs, 'no example has an input with a distribution'
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
        folder = checkout / 'scenarios' / name
        entries = [folder / 'variants' / variant for variant in variants] or [folder]
        for entry in entries:
            doc = json_of('compile', '--json', entry, cwd=scratch)
            assert doc['diagnostics'] == [], (entry, doc['diagnostics'])
        print(f'  {name} ({len(entries)} models): {time.perf_counter() - start:.1f} s', flush=True)
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
