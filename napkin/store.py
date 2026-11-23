"""The run store: the record of each run, kept on disk, so that no command runs the same run twice.

A run (`napkin.engine.run(program, configuration)`) reads only its program and its run configuration,
and its record depends only on those and on the engine code. The key of a stored run (`key`,
R-A4a-08) is a digest of exactly these:

- the canonical bytes of the program (`napkin/program/canonical.py`), which holds no label, text or
  evidence, so editing a label keeps the key;
- the canonical bytes of the configuration and its request, including the horizon, the requested
  keys sorted by owner and steps, the choice of every value, and the budget of pieces;
- a digest of the engine code: each package file that `engine/timeline/__init__.py`, the entry of a
  run, imports, directly or through other package files (its static import closure, with every
  parent package's `__init__.py`), and `expressions.py` and `distributions.py`;
- the Python, numpy and scipy versions, the machine, the processor and the numpy CPU features;
- for a run with edits, its log (`napkin.session.Log`): the breakpoints and each edit, with the stop
  of its hit, that a caller made at a checkpoint (docs/design/decisions.md, change 15). Such a run is the program
  stopped at each hit of the breakpoints, edited there and resumed, to the end
  (`napkin.session.play`), so the code that plays it, `session.py` and its closure, takes the place
  of the engine code in the key. A log with no edit keys as the run without it: a breakpoint alone
  changes no run. The stops of a log are what a session saw, which the run gives again: they are
  checked as the log plays, and they are no part of the key.

A change to any of these is a miss, never a stale result. The thread settings of the linear algebra
are not in the key: a run under other thread settings is not the same run bit for bit, and it agrees
within the tolerances of the run (change 11 of the plan).

**The reuse rule.** An entry holds the record of its exact request, including a failure or a stop
at its budget. A permutation of the requested keys uses the same entry and the caller receives its
manifest in the order requested. A different horizon, choice of values or budget has its own entry.
A run that raises an exception stores nothing. A session waiting at a breakpoint has no completed
record. The run of its edit log goes through the store.

Each entry is a compressed pickle in `<directory>/<2 hex>/<key>.run`, written to a temporary file and
renamed into place, with the configuration that it ran, its log (None for none) and the digest of its
program; the program is kept once, in `<directory>/programs/<digest>.program`, so that `verify` can
run an entry again. Each key has a lock (`<directory>/locks/<key>.lock`): a process that needs a run
that another process is running waits for it, then reads it. When the entries pass the size limit
(`NAPKIN_STORE_LIMIT`, in gigabytes, 4 by default), the least recently used go.

The store does nothing until a caller turns it on (`use`, `activate`): the commands, the catalogue
tests (the root conftest.py) and the tools. The engine, language and acceptance unit tests never use
it. The processes of a study use the store of the process that made them (`pool_options`).
`NAPKIN_STORE` names the directory, or turns the store off with `off`. By default it is `.cache/runs`
in a source checkout, and `~/.cache/napkin/runs` (or under `XDG_CACHE_HOME`) for an installed package.
"""

from __future__ import annotations

import ast
import contextlib
import functools
import hashlib
import os
import pickle
import platform
import random
import subprocess
import sys
import uuid
import zlib
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from fractions import Fraction
from pathlib import Path

try:
    import fcntl
except ImportError:  # no file locks: each process runs what it does not find
    fcntl = None

import numpy as np

# The folder of the package, whose files the key of a run digests (`closure`).
PACKAGE = Path(__file__).resolve().parent

FORMAT = 5
MAGIC = b'napkin run store 2\n'
# The modules whose code a run runs, as files of the package; and the module that plays a run with
# edits, which imports the engine.
ENGINE_STARTS = ('engine/timeline/__init__.py', 'expressions.py', 'distributions.py')
SESSION_STARTS = ('session.py',)
DEFAULT_LIMIT_GB = 4.0

# The store that this process uses: its directory, or None.
_active = {'directory': None}
# The runs that this process asked the store for: those that it held (hits), and those that it did not
# hold, which this process ran (misses).
counts = {'hits': 0, 'misses': 0}


# --- Turning the store on ---------------------------------------------------------------------


def source_checkout():
    """The source checkout that holds this package, or None for an installed package: the folder above
    the package, when it holds the checkout's `pyproject.toml` and its catalogue, `scenarios/`."""
    parent = PACKAGE.parent
    return parent if (parent / 'pyproject.toml').is_file() and (parent / 'scenarios').is_dir() else None


def default_directory():
    """The store of this checkout or installation, or None when `NAPKIN_STORE` is `off`."""
    value = os.environ.get('NAPKIN_STORE', '')
    if value == 'off':
        return None
    if value:
        return Path(value)
    checkout = source_checkout()
    if checkout is not None:
        return checkout / '.cache' / 'runs'
    base = os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache'
    return Path(base) / 'napkin' / 'runs'


def current():
    """The directory of the store that this process uses, or None."""
    return _active['directory']


def activate(directory):
    """Use the store in `directory` (None: no store) from now on in this process."""
    _active['directory'] = None if directory is None else Path(directory)


@contextlib.contextmanager
def use(directory):
    """Use the store in `directory` (None: no store) inside the block."""
    previous = _active['directory']
    activate(directory)
    try:
        yield
    finally:
        activate(previous)


def cores():
    """The number of processors that this process can use."""
    if hasattr(os, 'process_cpu_count'):
        return os.process_cpu_count() or 1
    if hasattr(os, 'sched_getaffinity'):
        return len(os.sched_getaffinity(0)) or 1
    return os.cpu_count() or 1


def _initialize(directory, initializer, initargs):
    activate(directory)
    if initializer is not None:
        initializer(*initargs)


def pool_options(initializer=None, initargs=()):
    """Keyword arguments for a `ProcessPoolExecutor` whose workers use the store of this process, then
    run `initializer(*initargs)`."""
    directory = None if _active['directory'] is None else str(_active['directory'])
    return {'initializer': _initialize, 'initargs': (directory, initializer, tuple(initargs))}


# --- Keys -------------------------------------------------------------------------------------


def _encode(value, out):
    """The canonical bytes of a value of a run, objects by their fields (`fingerprint`)."""
    kind = type(value)
    if value is None:
        out.append(b'N')
    elif kind is bool:
        out.append(b'T' if value else b'F')
    elif kind is int:
        out.append(b'i%d;' % value)
    elif kind is float:
        out.append(b'f' + value.hex().encode() + b';')
    elif kind is Fraction:
        out.append(b'q%d/%d;' % (value.numerator, value.denominator))
    elif kind is str:
        data = value.encode('utf-8', 'surrogatepass')
        out.append(b's%d:' % len(data))
        out.append(data)
    elif isinstance(value, Mapping):
        out.append(b'{%d:' % len(value))
        for name, item in value.items():
            _encode(name, out)
            _encode(item, out)
        out.append(b'}')
    elif kind in (tuple, list):
        out.append(b'[%d:' % len(value))
        for item in value:
            _encode(item, out)
        out.append(b']')
    elif isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        out.append(b'a' + array.dtype.str.encode() + repr(array.shape).encode() + b':' + array.tobytes())
    elif isinstance(value, np.generic):
        out.append(b'g' + value.dtype.str.encode() + b':' + value.tobytes())
    elif is_dataclass(value):
        out.append(b'D' + kind.__qualname__.encode() + b':')
        _encode({item.name: getattr(value, item.name) for item in fields(value)}, out)
    else:
        raise TypeError(f'no canonical bytes for a {kind.__qualname__}')


def fingerprint(value):
    """A digest of a record, or of any value that a record is made of: equal digests mean equal
    values, bit for bit (floats exactly, a NaN as itself). A type of no record is a TypeError."""
    out = []
    _encode(value, out)
    return hashlib.sha256(b''.join(out)).hexdigest()


@functools.cache
def _module_names(directory):
    """The actual spellings of a directory's modules, including on case-insensitive file systems."""
    return frozenset(os.listdir(directory))


def _module_file(parts):
    """The file of the package module `parts` (relative to the package), or None."""
    base = PACKAGE
    for i, part in enumerate(parts):
        names = _module_names(base)
        if i == len(parts) - 1 and f'{part}.py' in names:
            return base / f'{part}.py'
        if part not in names or not (base / part).is_dir():
            return None
        base = base / part
    if '__init__.py' in _module_names(base):
        return base / '__init__.py'
    return None


def _parts(path):
    relative = path.relative_to(PACKAGE).with_suffix('')
    parts = relative.parts
    return parts[:-1] if parts and parts[-1] == '__init__' else parts


# The files that each file imports, as `_imports` found them in this process.
_IMPORTS = {}


def _imports(path, package):
    """The package files that the module at `path`, of the package `package`, imports (see
    `closure`), read once for each file: the closure of the session holds the engine's."""
    found = _IMPORTS.get(path)
    if found is not None:
        return found
    found = []
    for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
        names = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                head, *rest = alias.name.split('.')
                if head == PACKAGE.name:
                    names.append((tuple(rest), None))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(package):
                    continue
                base = package[: len(package) - (node.level - 1)]
                base += tuple(node.module.split('.')) if node.module else ()
            else:
                head, *rest = (node.module or '').split('.')
                if head != PACKAGE.name:
                    continue
                base = tuple(rest)
            names.extend((base, alias.name) for alias in node.names)
        for base, name in names:
            submodule = _module_file((*base, name)) if name not in (None, '*') else None
            target = submodule or _module_file(base)
            if target is not None:
                found.append(target)
    _IMPORTS[path] = found
    return found


def closure(starts=ENGINE_STARTS):
    """The package files that the modules `starts` import, directly or through each other: each
    module that an import names, and each module whose names an import takes (so a package that
    passes on a name brings the module that defines it). A module's parent packages run on import, so
    their `__init__.py` files count too; only the names that the code imports are followed."""
    followed, files = set(), set()
    stack = [PACKAGE / start for start in starts]
    while stack:
        path = stack.pop()
        if path in followed:
            continue
        followed.add(path)
        files.add(path)
        parts = _parts(path)
        package = parts if path.name == '__init__.py' else parts[:-1]
        for depth in range(len(package) + 1):
            parent = _module_file(package[:depth])
            if parent is not None:
                files.add(parent)
        stack.extend(_imports(path, package))
    return sorted(files)


def _code_digest(starts):
    """The SHA-256 of the files of the closure of `starts`, each by its path and its bytes."""
    digest = hashlib.sha256()
    for path in closure(starts):
        digest.update(path.relative_to(PACKAGE).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _processor():
    try:
        with open('/proc/cpuinfo', encoding='utf-8', errors='replace') as info:
            for line in info:
                name, _, value = line.partition(':')
                if name.strip() in ('model name', 'Hardware', 'cpu model', 'Processor'):
                    return value.strip()
    except OSError:
        pass
    if sys.platform == 'darwin':
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            return subprocess.run(
                ['sysctl', '-n', 'machdep.cpu.brand_string'],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip()
    return platform.processor()


def _environment():
    import scipy

    try:
        from numpy._core._multiarray_umath import __cpu_features__ as features
    except ImportError:
        features = {}
    return {
        'python': sys.version,
        'numpy': np.__version__,
        'scipy': scipy.__version__,
        'machine': platform.machine(),
        'processor': _processor(),
        'cpu_features': sorted(name for name, enabled in features.items() if enabled),
        'kernels': [os.environ.get(name, '') for name in ('OPENBLAS_CORETYPE', 'NPY_DISABLE_CPU_FEATURES')],
    }


# The code is digested once, at import: this names what the process loaded even if source files
# change while a long-lived process runs. The session's code holds the engine's.
ENGINE_DIGEST = _code_digest(ENGINE_STARTS)
SESSION_DIGEST = _code_digest(SESSION_STARTS)
ENVIRONMENT = _environment()
_ENVIRONMENT_BYTES = repr(sorted(ENVIRONMENT.items())).encode()

# The digest of the canonical bytes of the last programs that were keyed, by the program itself: the
# samples of a study key one program many times. The program is held with its digest, so that no
# other object can take its place in the memory.
_PROGRAMS = 8
_programs = OrderedDict()


def program_digest(program):
    """The SHA-256 of the canonical bytes of a program (`program.canonical.program_bytes`), made once
    for each of the last programs that were keyed."""
    from .program.canonical import program_bytes

    kept = _programs.get(id(program))
    if kept is None or kept[0] is not program:
        kept = _programs[id(program)] = (program, hashlib.sha256(program_bytes(program)).hexdigest())
        while len(_programs) > _PROGRAMS:
            _programs.popitem(last=False)
    _programs.move_to_end(id(program))
    return kept[1]


def _edited(log):
    """Whether a log makes another run than the run without it: whether it has an edit."""
    return log is not None and bool(log.edits)


def _code(log):
    """The digest of the code of a run with this log (see the module)."""
    return SESSION_DIGEST if _edited(log) else ENGINE_DIGEST


def key(program, configuration, log=None):
    """The key of a stored run of a program under a run configuration (see the module): the program's
    digest, the canonical bytes of the configuration and its request, the code and the
    environment, and for a run with edits its log (`napkin.session.Log`), including each expected stop and its edits. Raises TypeError when a part has no canonical bytes."""
    from .program.canonical import configuration_bytes, value_bytes

    request = configuration.request
    keys = tuple(sorted(request.keys, key=lambda key: (key.owner, key.steps)))
    parts = [
        _code(log).encode(),
        _ENVIRONMENT_BYTES,
        program_digest(program).encode(),
        configuration_bytes(configuration),
        value_bytes(replace(request, keys=keys)),
    ]
    if _edited(log):
        out = []
        _encode(log, out)
        parts.append(b''.join(out))
    digest = hashlib.sha256(MAGIC)
    # Each part is length-prefixed, so no two keys share their bytes across a boundary.
    for part in parts:
        digest.update(b'%d:' % len(part))
        digest.update(part)
    return digest.hexdigest()


# --- Entries and locks ------------------------------------------------------------------------


def _entry(directory, run_key):
    return directory / run_key[:2] / f'{run_key}.run'


def _program_file(directory, digest):
    return directory / 'programs' / f'{digest}.program'


def _lock_file(directory, run_key):
    return directory / 'locks' / f'{run_key}.lock'


def _read(path):
    """The data of the file at `path`, or None when there is none or it is damaged."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if not data.startswith(MAGIC):
        return None
    try:
        return pickle.loads(zlib.decompress(data[len(MAGIC) :]))
    except Exception:  # a damaged file is a miss: the run is run and written again
        return None


def _stored(directory, run_key):
    """The entry of a key, or None. A file that is no entry of this format is none."""
    entry = _read(_entry(directory, run_key))
    if not isinstance(entry, dict) or entry.get('format') != FORMAT or entry.get('key') != run_key:
        return None
    return entry


def _write(path, value):
    """Write a value to `path` whole or not at all: to a temporary file of the folder, then renamed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    temporary.write_bytes(MAGIC + zlib.compress(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL), 1))
    os.replace(temporary, path)


def _save(directory, run_key, program, configuration, record, log=None):
    """Store the record of a run with the configuration that it ran and its log (None for a run
    without edits), and its program once."""
    from .program.record import Record

    digest = program_digest(program)
    if not _program_file(directory, digest).is_file():
        _write(_program_file(directory, digest), program)
    entry = {
        'format': FORMAT,
        'key': run_key,
        'engine': _code(log),
        'environment': ENVIRONMENT,
        'program': digest,
        'configuration': configuration,
        'log': log if _edited(log) else None,
        # A fresh copy: a record keeps the index of its histories beside it once it is read.
        'record': Record(record.manifest, record.histories, record.trace, record.failure),
    }
    _write(_entry(directory, run_key), entry)
    _limit_size(directory)


@contextlib.contextmanager
def _locked(directory, run_key):
    """Hold the lock of a key inside the block, waiting while another process holds it."""
    if fcntl is None:
        yield
        return
    path = _lock_file(directory, run_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _files(directory):
    """(time of last use, size, path) of each entry and program of the store."""
    found = []
    for pattern in ('??/*.run', 'programs/*.program'):
        for path in directory.glob(pattern):
            with contextlib.suppress(FileNotFoundError):
                stat = path.stat()
                found.append((stat.st_mtime, stat.st_size, path))
    return found


def _limit():
    try:
        return float(os.environ.get('NAPKIN_STORE_LIMIT', DEFAULT_LIMIT_GB)) * 1e9
    except ValueError:
        return DEFAULT_LIMIT_GB * 1e9


def _limit_size(directory):
    """Remove the least recently used files while the store is over its limit, down to 90%."""
    limit = _limit()
    found = _files(directory)
    total = sum(size for _, size, _ in found)
    if total <= limit:
        return
    for _, size, path in sorted(found):
        if total <= 0.9 * limit:
            break
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
            total -= size


def _touch(*paths):
    """Mark files as used now: they are the last to go when the store is full."""
    for path in paths:
        with contextlib.suppress(OSError):
            os.utime(path)


def _held(directory, run_key, request):
    """The record of this exact request, with its manifest in the order the caller asked for."""
    entry = _stored(directory, run_key)
    if entry is None:
        return None
    _touch(_entry(directory, run_key), _program_file(directory, entry['program']))
    record = entry['record']
    if record.manifest.keys != request.keys:
        return replace(record, manifest=replace(record.manifest, keys=request.keys))
    return record


# --- Running through the store ------------------------------------------------------------------


def _fresh(program, configuration, log):
    """A new run: the engine's (`napkin.engine.run`), or for a run with edits the run of its log,
    played through the engine's checkpoints and resumed in place past each stop to the end
    (`napkin.session.play`)."""
    if not _edited(log):
        from .engine.timeline import run as fresh

        return fresh(program, configuration)
    from .session import play

    return play(program, configuration, log)


def run(program, configuration, log=None):
    """The record of a run of a program under a configuration (`napkin.engine.run`), or of the run of
    a log of its edits at the stops of its breakpoints (`log`, `napkin.session.Log`), through the
    store of this process when one is on (see the module): the stored record of this request
    or a new run, which is stored. An exception of the engine (a part that it does not
    run, a configuration that the program cannot take, a log that does not play again) stores
    nothing and propagates."""
    directory = _active['directory']
    if directory is None:
        return _fresh(program, configuration, log)
    run_key = key(program, configuration, log)
    request = configuration.request
    record = _held(directory, run_key, request)
    if record is None:
        with _locked(directory, run_key):
            # Another process may have stored the run while this one waited.
            record = _held(directory, run_key, request)
            if record is None:
                counts['misses'] += 1
                record = _fresh(program, configuration, log)
                _save(directory, run_key, program, configuration, record, log)
                return record
    counts['hits'] += 1
    return record


# --- Verification -------------------------------------------------------------------------------


def verify(directory, number, rng=None):
    """Run `number` stored runs of this code and environment again, each with the configuration that
    it ran, its log and its program, and compare each record with its entry, bit for bit
    (`fingerprint`). Gives the paths of the entries that differ."""
    directory = Path(directory)
    candidates = []
    for _, _, path in _files(directory):
        if path.suffix != '.run':
            continue
        entry = _stored(directory, path.stem)
        if (
            entry is not None
            and entry['engine'] == _code(entry['log'])
            and entry['environment'] == ENVIRONMENT
            and _program_file(directory, entry['program']).is_file()
        ):
            candidates.append(path)
    chosen = (rng or random.Random()).sample(sorted(candidates), min(number, len(candidates)))
    differ = []
    for path in chosen:
        entry = _stored(directory, path.stem)
        program = _read(_program_file(directory, entry['program']))
        again = _fresh(program, entry['configuration'], entry['log'])
        if fingerprint(again) != fingerprint(entry['record']):
            differ.append(path)
    print(f'{directory}: {len(chosen)} stored runs run again, {len(differ)} differ')
    return differ
