"""The run store: each simulated run, kept on disk, so that no command simulates the same run twice.

A run (`napkin.engine.run(program, configuration)`) reads only its program and its run
configuration, and its record depends only on those and on the engine code. The key of a stored run
(`key`, R-A4a-08) is a digest of exactly these:

- the canonical bytes of the program (`napkin/program/canonical.py`), which holds no label, text or
  evidence, so editing a label keeps the key;
- the canonical bytes of the configuration without its request: the inputs, the mode, the seed, the
  controllers and their picks, the limits, the budgets and the numerical settings. What to record,
  and until when, is no part of the key: a stored run serves a request that its manifest covers;
- a digest of the engine code: each package file that `engine/timeline/__init__.py`, the entry of a
  run, imports, directly or through other package files (its static import closure, with every
  parent package's `__init__.py`), and `expressions.py` and `distributions.py`;
- the Python, numpy and scipy versions, the machine, the processor and the numpy CPU features.

A change to any of these is a miss, never a stale result. The old compiled form's runs go through
the same store, unkeyed, until a later stage replaces them (`simulate_all`). A simulation that the store runs gets
only the units of the library (`_StoredLibrary`), so the engine cannot read an input that the key
leaves out. Every check of a study still runs: the store keeps only what `simulate` returns.

The store does nothing until a caller turns it on (`use`, `activate`): the catalogue tests (the
root conftest.py), the publisher and the comparisons. The engine, language and acceptance unit
tests never use it. Pools of worker processes pass the setting on (`pool_options`). A command that
runs one study at a time (`try` and the publisher when it has more jobs than scenarios) also lets the
store start helper processes: when a study needs several runs that the store does not hold, the
helpers simulate them beside it (`simulate_all`).

Each entry is a compressed pickle in `<directory>/<2 hex>/<key>.run`, written to a temporary file
and renamed into place. Each run has a lock (`<directory>/locks/<key>.lock`): a process that needs a
run that another process is simulating first simulates the next run of its list that no process
holds, then waits, so two processes that need one study share its runs. When the entries pass the
size limit (`NAPKIN_STORE_LIMIT`, in gigabytes, 4 by default), the least recently used go.

`NAPKIN_STORE` names the directory, or turns the store off with `off`. By default it is
`.cache/runs` in a source checkout, and `~/.cache/napkin/runs` (or under
`XDG_CACHE_HOME`) for an installed package.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import multiprocessing
import os
import pickle
import platform
import random
import subprocess
import sys
import tempfile
import uuid
import zlib
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path
from types import MappingProxyType

try:
    import fcntl
except ImportError:  # no file locks: each process simulates what it does not find
    fcntl = None

import numpy as np

# The folder of the package, whose files the key of a run digests (`closure`).
PACKAGE = Path(__file__).resolve().parent

FORMAT = 2
MAGIC = b'napkin run store 1\n'
# The modules whose code a simulation runs, as files of the package.
ENGINE_STARTS = ('engine/timeline/__init__.py', 'expressions.py', 'distributions.py')
DEFAULT_LIMIT_GB = 4.0

# The store that this process uses: its directory, or None, and the number of helper processes
# that may simulate the missing runs of a list beside this one.
_active = {'directory': None, 'helpers': 0}
# The runs of the lists that this process asked for: those that the store held when a list started
# (hits), those that it did not hold, simulated by this process, its helpers or another process
# (misses), and those simulated without a key (unkeyed).
counts = {'hits': 0, 'misses': 0, 'unkeyed': 0}


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


def activate(directory, helpers=0):
    """Use the store in `directory` (None: no store) from now on in this process, with up to
    `helpers` helper processes for the missing runs of a list (`simulate_all`). Without file locks,
    a helper could simulate a run that another process simulates, so there are none."""
    _active['directory'] = None if directory is None else Path(directory)
    _active['helpers'] = max(0, int(helpers)) if directory is not None and fcntl is not None else 0


@contextlib.contextmanager
def use(directory):
    """Use the store in `directory` (None: no store) inside the block, with no helpers."""
    previous = dict(_active)
    activate(directory)
    try:
        yield
    finally:
        activate(previous['directory'], previous['helpers'])


def helpers():
    """The number of helper processes that this process may start for a list of runs."""
    return _active['helpers']


def cores():
    """The number of processors that this process can use."""
    if hasattr(os, 'process_cpu_count'):
        return os.process_cpu_count() or 1
    if hasattr(os, 'sched_getaffinity'):
        return len(os.sched_getaffinity(0)) or 1
    return os.cpu_count() or 1


def _initialize(directory, helpers, initializer, initargs):
    activate(directory, helpers)
    if initializer is not None:
        initializer(*initargs)


def pool_options(initializer=None, initargs=(), helpers=0):
    """Keyword arguments for a `ProcessPoolExecutor` whose workers use the store of this process,
    each with up to `helpers` helper processes, then run `initializer(*initargs)`."""
    directory = None if _active['directory'] is None else str(_active['directory'])
    return {'initializer': _initialize, 'initargs': (directory, helpers, initializer, tuple(initargs))}


# --- Keys -------------------------------------------------------------------------------------


def _encode(value, out, strict):
    kind = type(value)
    if value is None:
        out.append(b'N')
    elif kind is bool:
        out.append(b'T' if value else b'F')
    elif kind is int:
        out.append(b'i%d;' % value)
    elif kind is float:
        out.append(b'f' + value.hex().encode() + b';')
    elif kind is str:
        data = value.encode('utf-8', 'surrogatepass')
        out.append(b's%d:' % len(data))
        out.append(data)
    elif isinstance(value, Mapping):
        out.append(b'{%d:' % len(value))
        for key, item in value.items():
            _encode(key, out, strict)
            _encode(item, out, strict)
        out.append(b'}')
    elif kind in (tuple, list):
        out.append(b'[%d:' % len(value))
        for item in value:
            _encode(item, out, strict)
        out.append(b']')
    elif kind in (set, frozenset):
        parts = sorted(_canonical(item, strict) for item in value)
        out.append(b'<%d:' % len(parts))
        out.extend(parts)
        out.append(b'>')
    elif isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        out.append(b'a' + array.dtype.str.encode() + repr(array.shape).encode() + b':')
        if array.dtype.hasobject:
            _encode(array.tolist(), out, strict)
        else:
            out.append(array.tobytes())
    elif isinstance(value, np.generic):
        out.append(b'g' + value.dtype.str.encode() + b':' + value.tobytes())
    elif strict:
        raise TypeError(f'The run store cannot key a {kind.__qualname__}')
    elif is_dataclass(value):
        out.append(b'D' + kind.__qualname__.encode() + b':')
        _encode({item.name: getattr(value, item.name) for item in fields(value)}, out, strict)
    elif hasattr(value, '__dict__'):
        out.append(b'O' + kind.__qualname__.encode() + b':')
        _encode(dict(sorted(vars(value).items())), out, strict)
    else:
        out.append(b'R' + repr(value).encode())


def _canonical(value, strict=True):
    out = []
    _encode(value, out, strict)
    return b''.join(out)


def canonical(value):
    """The canonical bytes of plain data: mappings and sequences in their order, sets sorted, floats
    exactly. Any other type is a TypeError, so two different inputs never share a key."""
    return _canonical(value, True)


def fingerprint(value):
    """A digest of any result, objects by their fields: equal digests mean equal values, bit for bit."""
    return hashlib.sha256(_canonical(value, False)).hexdigest()


def _module_file(parts):
    """The file of the package module `parts` (relative to the package), or None."""
    base = PACKAGE.joinpath(*parts)
    if base.with_suffix('.py').is_file() and parts:
        return base.with_suffix('.py')
    if (base / '__init__.py').is_file():
        return base / '__init__.py'
    return None


def _parts(path):
    relative = path.relative_to(PACKAGE).with_suffix('')
    parts = relative.parts
    return parts[:-1] if parts and parts[-1] == '__init__' else parts


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
                    stack.append(target)
    return sorted(files)


def _engine_digest():
    digest = hashlib.sha256()
    for path in closure():
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
# change while a long-lived process runs (as `model/compile.py` does for the implementation hash).
ENGINE_DIGEST = _engine_digest()
ENVIRONMENT = _environment()
_ENVIRONMENT_BYTES = canonical(ENVIRONMENT)


# The canonical bytes of each part of the last runs that were keyed as typed parts, by the part
# itself (`_part_bytes`).
PARTS = 256
_parts_kept = OrderedDict()


def _part_bytes(part):
    """The canonical bytes of one part of a resolved run as typed parts: a section of its structure,
    or its links, as the plain data that the part writes. A part cannot change, and the runs of one
    structure share its parts, so the bytes of a part are written once. They are kept by the part
    itself, which is held with them so that no other object can have its place in the memory. A
    part that is no read-only mapping could change: its bytes are written each time."""
    from .model.structure import thawed

    if not isinstance(part, MappingProxyType):
        return canonical(thawed(part))
    kept = _parts_kept.get(id(part))
    if kept is None:
        kept = _parts_kept[id(part)] = (part, canonical(thawed(part)))
        while len(_parts_kept) > PARTS:
            _parts_kept.popitem(last=False)
    else:
        _parts_kept.move_to_end(id(part))
    return kept[1]


def _typed_bytes(rs):
    """The canonical bytes of a resolved run as typed parts, piece by piece: the bytes of the plain
    data that the run writes (`Resolved.plain`), with each key in its place. The pieces of the parts
    that the run shares with its structure are kept (`_part_bytes`); what the run has of its own is
    written for each run."""
    from .model.structure import SECTIONS, Resolved, thawed

    own = rs.own() if isinstance(rs, Resolved) else {}
    shared = (*SECTIONS, 'links')
    yield b'{%d:' % (len(shared) + 1 + len(own))
    for name in shared:
        yield canonical(name)
        yield _part_bytes(getattr(rs, name))
    yield canonical('computed_order')
    yield canonical(thawed(rs.computed_order))
    for name, value in own.items():
        yield canonical(name)
        yield canonical(value)
    yield b'}'


def key(program, configuration):
    """The key of a stored run of a program under a run configuration (see the module): the
    canonical bytes of the program and of the configuration without its request, the engine code
    and the environment. Raises TypeError when a part has no canonical bytes."""
    from .program.canonical import configuration_bytes, program_bytes

    digest = hashlib.sha256(MAGIC)
    digest.update(ENGINE_DIGEST.encode())
    digest.update(_ENVIRONMENT_BYTES)
    # Each part is length-prefixed, so no two keys share their bytes across a boundary.
    for part in (program_bytes(program), configuration_bytes(configuration)):
        digest.update(b'%d:' % len(part))
        digest.update(part)
    return digest.hexdigest()


class _StoredLibrary(Mapping):
    """The part of the library that a simulation reads and the store keys: its units. Reading any
    other part fails, so the key cannot leave out an input of a stored run."""

    def __init__(self, units):
        self._units = units

    def __getitem__(self, name):
        if name == 'units':
            return self._units
        raise KeyError(f'A stored simulation reads only the library units, not {name!r}')

    def get(self, name, default=None):
        return self[name]

    def __iter__(self):
        return iter(('units',))

    def __len__(self):
        return 1


# --- Entries and locks ------------------------------------------------------------------------


def _entry(directory, run_key):
    return directory / run_key[:2] / f'{run_key}.run'


def _lock_file(directory, run_key):
    return directory / 'locks' / f'{run_key}.lock'


def _read(path):
    """The entry in `path`, or None when there is none or it is damaged."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if not data.startswith(MAGIC):
        return None
    try:
        entry = pickle.loads(zlib.decompress(data[len(MAGIC) :]))
    except Exception:  # a damaged entry is a miss: the run is simulated and written again
        return None
    if not isinstance(entry, dict) or entry.get('format') != FORMAT:
        return None
    # This cache holds completed runs only; a paused play session has a different
    # execution contract and must never satisfy an ordinary simulation request.
    if getattr(entry.get('trajectory'), 'paused', False):  # the store holds whatever simulate returns
        return None
    return entry


def _load(directory, run_key):
    path = _entry(directory, run_key)
    entry = _read(path)
    if entry is None:
        return None
    with contextlib.suppress(OSError):
        os.utime(path)  # the entry was used now: it is the last to go when the store is full
    return entry['trajectory']


def _save(directory, run_key, inputs, trajectory):
    """Write the entry and give back its trajectory as a reader of the store sees it."""
    return pickle.loads(_write(directory, run_key, inputs, trajectory))['trajectory']


def _write(directory, run_key, inputs, trajectory):
    """Write the entry; give its pickled data."""
    if getattr(trajectory, 'paused', False):
        raise ValueError('The completed-run store cannot cache a paused trajectory')
    data = pickle.dumps(
        {
            'format': FORMAT,
            'key': run_key,
            'engine': ENGINE_DIGEST,
            'environment': ENVIRONMENT,
            'inputs': inputs,
            'trajectory': trajectory,
        },
        protocol=pickle.HIGHEST_PROTOCOL,
    )
    path = _entry(directory, run_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    temporary.write_bytes(MAGIC + zlib.compress(data, 1))
    os.replace(temporary, path)
    _limit_size(directory)
    return data


def _try_lock(directory, run_key):
    """A held lock of the run, or None when another process holds it."""
    if fcntl is None:
        return -1
    path = _lock_file(directory, run_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(handle)
        return None
    return handle


def _unlock(handle):
    if handle >= 0:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _wait(directory, run_key):
    """Wait until no process holds the run's lock."""
    if fcntl is None:
        return
    handle = os.open(_lock_file(directory, run_key), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(handle)


def _entries(directory):
    found = []
    for path in directory.glob('??/*.run'):
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
    """Remove the least recently used entries while the store is over its limit, down to 90%."""
    limit = _limit()
    entries = _entries(directory)
    total = sum(size for _, size, _ in entries)
    if total <= limit:
        return
    for _, size, path in sorted(entries):
        if total <= 0.9 * limit:
            break
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
            total -= size


# --- Simulating through the store -------------------------------------------------------------


def _item(item):
    """(rs, library, settings, play) of an item of a list: the play request is None when it has none."""
    rs, library, settings, play = (*item, None)[:4]
    return rs, library, settings, play


def _computed(compute, rs, library, settings, play):
    """`compute` of one item. A run that is not played is asked with no `play`."""
    if play is None:
        return compute(rs, library, settings)
    return compute(rs, library, settings, play=play)


def _call(compute, arguments, failures):
    try:
        return _computed(compute, *arguments)
    except failures as exc:
        return exc


def _help(directory, work):
    """The work of a helper process: each entry `(key, rs, units, settings, play)` of the file `work` that
    the store does not hold and no process holds, in order, simulated with its `compute` and
    stored. A failed run is not stored, so the process that needs it simulates it again and
    reports it."""
    directory = Path(directory)
    try:
        compute, entries = pickle.loads(Path(work).read_bytes())
    except FileNotFoundError:  # the list is complete
        return
    for run_key, rs, units, settings, play in entries:
        if _entry(directory, run_key).is_file():
            continue
        handle = _try_lock(directory, run_key)
        if handle is None:
            continue
        try:
            if _entry(directory, run_key).is_file():
                continue
            try:
                trajectory = _computed(compute, rs, _StoredLibrary(units), settings, play)
            except Exception:  # the process that needs the run reports its failure
                continue
            _write(directory, run_key, (rs, units, settings, play), trajectory)
        finally:
            _unlock(handle)


def _start_helpers(directory, compute, entries):
    """Helper processes for the missing runs of a list, as many as the setting allows and one fewer
    than the runs, as this process simulates too, with the file that holds their work. None when
    `compute` cannot go to another process. A process starts with the name of the file only: a long
    list in its arguments would hold this one until the new process had read it."""
    count = min(_active['helpers'], len(entries) - 1)
    if count <= 0:
        return [], None
    try:
        data = pickle.dumps((compute, entries), protocol=pickle.HIGHEST_PROTOCOL)
    except (pickle.PicklingError, AttributeError, TypeError):
        return [], None
    handle, name = tempfile.mkstemp(prefix='napkin-helpers-', suffix='.pickle')
    with os.fdopen(handle, 'wb') as file:
        file.write(data)
    context = multiprocessing.get_context('spawn')
    started = []
    try:
        for _ in range(count):
            process = context.Process(target=_help, args=(str(directory), name), daemon=True)
            process.start()
            started.append(process)
    except (OSError, AssertionError):  # no process to start: simulate alone
        pass
    return started, name


def _stop_helpers(processes, work):
    """Stop the helpers and remove their work. When this process has every result, a helper either
    still starts or simulates a run that fails, which it would not store."""
    for process in processes:
        process.terminate()
    for process in processes:
        process.join()
    if work is not None:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(work)


def simulate_all(compute, items, failures=()):
    """The result of `compute(rs, library, settings)` for each item, in order: its trajectory, or
    the exception when it raises one of `failures` (any other exception raises). An item of a played
    run is `(rs, library, settings, play)`: it is computed as `compute(rs, library, settings,
    play=play)`, and the play request is a part of its key.

    Without a store, each item is computed in turn. With one, each result comes from the store or
    is computed, stored and read back, so a stored and a fresh result are the same objects. A
    failure is never stored. While another process holds an item, this one computes the next free
    item first, and waits only when every remaining item is held. When the store allows helpers
    (`activate`) and two or more items are not stored, helper processes compute them beside this
    one, through the same locks (`_help`)."""
    items = [_item(item) for item in items]
    directory = _active['directory']
    if directory is None:
        return [_call(compute, item, failures) for item in items]
    results = [None] * len(items)
    keys = []
    for rs, library, settings, play in items:
        try:
            keys.append(key(rs, library, settings, play))
        except Exception:  # an input outside the key (or invalid settings): compute it as given
            keys.append(None)
    held_at_start = [run_key is not None and _entry(directory, run_key).is_file() for run_key in keys]
    missing = [
        (keys[i], items[i][0], items[i][1]['units'], items[i][2], items[i][3])
        for i in range(len(items))
        if keys[i] is not None and not held_at_start[i]
    ]
    helpers, work = _start_helpers(directory, compute, missing) if _active['helpers'] else ([], None)
    try:
        pending = list(range(len(items)))
        while pending:
            held = []
            for index in pending:
                rs, library, settings, play = items[index]
                run_key = keys[index]
                if run_key is None:
                    counts['unkeyed'] += 1
                    results[index] = _call(compute, items[index], failures)
                    continue
                stored = _load(directory, run_key)
                if stored is not None:
                    counts['hits' if held_at_start[index] else 'misses'] += 1
                    results[index] = stored
                    continue
                handle = _try_lock(directory, run_key)
                if handle is None:
                    held.append(index)
                    continue
                try:
                    stored = _load(directory, run_key)
                    if stored is not None:
                        counts['hits' if held_at_start[index] else 'misses'] += 1
                        results[index] = stored
                        continue
                    counts['misses'] += 1
                    units = library['units']
                    outcome = _call(compute, (rs, _StoredLibrary(units), settings, play), failures)
                    if not isinstance(outcome, BaseException):
                        outcome = _save(directory, run_key, (rs, units, settings, play), outcome)
                    results[index] = outcome
                finally:
                    _unlock(handle)
            if held:
                _wait(directory, keys[held[0]])
            pending = held
    finally:
        _stop_helpers(helpers, work)
    return results


def simulate(compute, rs, library, settings=None):
    """`compute(rs, library, settings)` through the store: one run's trajectory."""
    (outcome,) = simulate_all(compute, [(rs, library, settings)], (Exception,))
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


# --- Verification -------------------------------------------------------------------------------


def verify(directory, number, rng=None):
    """Simulate `number` stored runs of this engine and environment again and compare each with its
    entry, bit for bit. Gives the paths of the runs that differ."""
    from .engine.runtime import simulate as compute

    candidates = []
    for _, _, path in _entries(directory):
        entry = _read(path)
        if entry and entry['engine'] == ENGINE_DIGEST and entry['environment'] == ENVIRONMENT:
            candidates.append(path)
    chosen = (rng or random.Random()).sample(candidates, min(number, len(candidates)))
    differ = []
    for path in chosen:
        entry = _read(path)
        rs, units, settings, play = entry['inputs']
        again = _computed(compute, rs, _StoredLibrary(units), settings, play)
        if fingerprint(again) != fingerprint(entry['trajectory']):
            differ.append(path)
    print(f'{directory}: {len(chosen)} stored runs simulated again, {len(differ)} differ')
    return differ
