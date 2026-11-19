"""The measurements of the benchmark, and the document that holds them (the contract is in
`tools/bench/__init__.py`).

Three tasks measure one workload, each in a process of its own (`isolated`): `compile_task` the cold
compile, `first_task` the time to the first result, and `warm_task` the warm runs, the report of a run,
where the time of a run and its report goes and, when samples are asked, a Monte Carlo study. A task is
a plain mapping and gives a plain mapping back, so it crosses the process boundary as JSON. A task that
raises gives `{'failed': ...}` (`perform`), and so does a process that ends without a result or that
passes its time limit: no workload stops the harness.

`bench` measures a list of workloads and `document` adds the revision, the machine and the settings.
`attribution` is a pure function of a profile's statistics: a test gives it made-up statistics.
"""

from __future__ import annotations

import ast
import cProfile
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from tools.catalogue import ROOT

from . import families
from .workloads import ALL

# The groups of "where the time goes". A group is a role, and `FILES` says which files have that role
# in this revision: a function is of the first group that names its file. A change that moves code
# between files changes `FILES` with it, and the document of each run holds the `FILES` that made it,
# so two documents compare by role. The roles:
# - `analysis`: what the compiler, the program's checker and its proofs find out about a model;
# - `expressions`: the evaluation of the model's expressions, of its collections and of its reads;
# - `field`: the rates of the flows: local sharing, the network, the declared solvers and the solve
#   library;
# - `solver`: the steps of the integrators and the search for the roots;
# - `linear_algebra`: factorizations, solves and matrix exponentials, wherever they are called from;
# - `scheduler`: the timeline: the loop of a run, the moments and their rounds, the occurrences, the
#   triggers and the record;
# - `reporting`: the report of a record;
# - `other`: the time that no function of a group calls for.
GROUPS = ('analysis', 'expressions', 'field', 'solver', 'linear_algebra', 'scheduler', 'reporting', 'other')
EXPRESSIONS = 'napkin/expressions.py'
# The functions and the classes of `napkin/expressions.py` that are analysis and not evaluation, with
# what is inside them (`analysis_spans`).
ANALYSIS = (
    'stock_face_dependencies',
    'names_in',
    '_formula',
    'domain_prover',
    'compile_expression',
    'infer',
)
# The file names that the engine gives the programs and expressions that it generates.
GENERATED = ('<model>', '<string>', '<expression>')
FILES = (
    (
        'analysis',
        (
            'napkin/model/',
            'napkin/program/',
            *(f'napkin/core/{name}.py' for name in ('expr', 'ops', 'units', 'intervals', 'faces')),
        ),
    ),
    (
        'expressions',
        (
            'napkin/core/evaluation.py',
            'napkin/core/arrays.py',
            'napkin/engine/timeline/reads.py',
            'napkin/engine/timeline/collections.py',
        ),
    ),
    (
        'field',
        (
            'napkin/engine/allocation.py',
            'napkin/engine/solve/',
            *(f'napkin/engine/timeline/{name}.py' for name in ('network', 'selection', 'declared')),
            *(
                f'napkin/engine/continuous/{name}.py'
                for name in ('fields', 'kernels', 'bounds', 'system', 'highs')
            ),
        ),
    ),
    (
        'solver',
        ('napkin/engine/continuous/integrate.py', 'napkin/engine/timeline/sparse.py', 'scipy/integrate/'),
    ),
    ('linear_algebra', ('scipy/sparse/', 'scipy/linalg/', 'numpy/linalg/')),
    (
        'scheduler',
        (
            'napkin/engine/timeline/',
            # The step of a component between two moments.
            'napkin/engine/continuous/segment.py',
        ),
    ),
    ('reporting', ('napkin/engine/report.py',)),
)
# The file of a function of C in a profile's statistics, which has none.
BUILT_IN = '~'
# A function of C is linear algebra when its name holds one of these, whatever calls it: the solver
# calls the factorization and the solves of SuperLU from its own file, and their time is no step of
# the solver.
LINEAR = ('SuperLU', '_superlu', '_umath_linalg', 'lapack', 'blas')
# The longest text of a failure in the document, and in a line of the table.
LONGEST = 300
SHOWN = 120
STUDY_SEED = 0


# --- What one process measures ----------------------------------------------------------------------


def peak_mb():
    """The peak memory of this process in MB (`ru_maxrss`), or None where the system gives none.

    On Linux a process that a larger one starts reports that parent's peak here. The high-water mark
    of its own memory (`VmHWM` in /proc/self/status) is then the smaller number, and it is the
    process's own peak."""
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = peak / 2**20 if sys.platform == 'darwin' else peak / 2**10  # bytes on macOS, kB elsewhere
    try:
        with open('/proc/self/status', encoding='ascii') as status:
            for line in status:
                if line.startswith('VmHWM:'):
                    peak = min(peak, int(line.split()[1]) / 2**10)
    except (OSError, ValueError, IndexError):
        pass
    return peak


def shortened(text, most):
    """A text on one line, of about `most` characters at most: a longer one keeps its two ends, where
    an error says what failed and why, with … between them."""
    text = ' '.join(str(text).split())
    return text if len(text) <= most else f'{text[: most // 2]} … {text[-(most // 2) :]}'


def failure(exc):
    """The record of a measurement that failed: `{'failed': '<ExceptionType>: <message>'}`, with the
    message on one line and its middle left out when it is long (`shortened`)."""
    return {'failed': f'{type(exc).__name__}: {shortened(exc, LONGEST)}'}


def size(program, record):
    """The size of one run: the parts of its program (templates, members, values, flows and events,
    each counted once for its template) and the work of its record: its histories, their pieces, and
    the entries of its trace, in all and by kind."""
    templates = program.templates
    kinds = Counter(entry.kind for entry in record.trace)
    return {
        'templates': len(templates),
        'members': sum(len(template.members) for template in templates),
        'values': sum(len(template.values) for template in templates) + len(program.root),
        'flows': sum(len(template.flows) for template in templates),
        'events': sum(len(template.events) for template in templates),
        'histories': len(record.histories),
        'pieces': sum(len(history.pieces) for history in record.histories),
        'trace': len(record.trace),
        'trace_kinds': dict(sorted(kinds.items())),
    }


def runs_of(model):
    """The runs of a compiled model: the names of its named runs, else [None] for its default run."""
    return [run.name for run in model.declared.runs] or [None]


def configured(model, run):
    """The configuration of a run of a compiled model (None for its default run)."""
    return model.configuration if run is None else model.configure(run)


def compile_task(task, save=None):
    """The cold compile of `task['path']`: the seconds of `napkin.load_scenario` and of the imports
    before it, the peak memory, and the model's runs."""
    began = time.perf_counter()
    import napkin

    load = napkin.load_scenario
    imported = time.perf_counter()
    model = load(task['path'])
    return {
        'seconds': time.perf_counter() - imported,
        'import_seconds': imported - began,
        'peak_mb': peak_mb(),
        'runs': runs_of(model),
    }


def first_task(task, save=None):
    """The time to the first result: the seconds from `task['started']`, the wall-clock time at which
    the harness started this process, to the end of the run `task['run']` (None: the default run).
    `parts` splits them: the start of the process, the imports, the compile, the run. A run that stops
    before its horizon is a failure."""
    began = time.perf_counter()
    import napkin

    load = napkin.load_scenario
    imported = time.perf_counter()
    model = load(task['path'])
    compiled = time.perf_counter()
    run = task.get('run')
    record = napkin.run(model.program, configured(model, run))
    done = time.perf_counter()
    if record.failure is not None:
        raise RuntimeError(
            f'the run stops at {float(record.failure.t):g} h: {record.failure.detail("message")}'
        )
    seconds = time.time() - task['started']
    return {
        'seconds': seconds,
        'peak_mb': peak_mb(),
        'run': run,
        'parts': {
            'start': seconds - (done - began),
            'import': imported - began,
            'compile': compiled - imported,
            'run': done - compiled,
        },
    }


def _part(make):
    """One measurement of a task, or the record of its failure."""
    try:
        return make()
    except Exception as exc:
        return failure(exc)


def warm_task(task, save):
    """The warm measurements of `task['run']` in one process, after the compile.

    - `warm`: the seconds of each of `task['repeats']` repeats of the run (`napkin.run`) in their
      order, their median and their minimum, the peak memory of the process after them, and the size
      of the run. This is the engine alone.
    - `report`: what a report of a run costs, once: the seconds of the report of every named value of
      the run at its start and its horizon (`napkin.report`), with its evidence trails and near-ties.
    - `where`: one more run and report under cProfile, by group (`attribution`).
    - `every_run`: with `task['survey']`, the seconds of one run of each run of the model, in the
      model's order, with its histories and its trace entries, and the name of the slowest. A run that
      fails is a failure record, and the survey goes on.
    - `batch`: the Monte Carlo study of `task['samples']` samples on `task['jobs']` processes, when
      samples are asked (`study`). It samples the run of the task, or, with a survey, the slowest run
      that the survey found.

    `save` gets the result so far after each measurement, so a slow profile or study cannot lose the
    measurements before it."""
    import napkin
    from napkin.commands.run import named

    model = napkin.load_scenario(task['path'])
    run = task.get('run')
    configuration = configured(model, run)

    def once():
        return napkin.run(model.program, configuration)

    seconds = []
    for _ in range(task['repeats']):
        started = time.perf_counter()
        record = once()
        seconds.append(time.perf_counter() - started)
    if record.failure is not None:
        raise RuntimeError(f'the run stops: {record.failure.detail("message")}')
    warm = {
        'median_seconds': statistics.median(seconds),
        'min_seconds': min(seconds),
        'seconds': seconds,
        'repeats': len(seconds),
        'peak_mb': peak_mb(),
        'size': size(model.program, record),
    }
    paths = named(model, record)
    times = (0, configuration.request.horizon)

    def reported(found):
        return napkin.report(found, model.program, configuration, paths, times, model=model.declared)

    def report():
        started = time.perf_counter()
        reported(record)
        return {'report_seconds': time.perf_counter() - started, 'values': len(paths), 'peak_mb': peak_mb()}

    def where():
        from napkin import expressions

        profile = cProfile.Profile()
        profile.enable()
        try:
            reported(once())
        finally:
            profile.disable()
        spans = analysis_spans(Path(expressions.__file__).read_text(encoding='utf-8'))
        return attribution(profile_stats(profile), spans)

    found = {'run': run, 'warm': warm}
    save(dict(found))
    found['report'] = _part(report)
    save(dict(found))
    found['where'] = _part(where)
    save(dict(found))

    def survey():
        runs = {}
        for name in runs_of(model):
            started = time.perf_counter()
            try:
                done = napkin.run(model.program, configured(model, name))
            except Exception as exc:
                runs[str(name)] = failure(exc)
                continue
            if done.failure is not None:
                runs[str(name)] = {'failed': f'the run stops: {done.failure.detail("message")}'}
                continue
            runs[str(name)] = {
                'seconds': time.perf_counter() - started,
                'histories': len(done.histories),
                'trace': len(done.trace),
            }
        timed = {name: item['seconds'] for name, item in runs.items() if 'seconds' in item}
        return {'runs': runs, 'slowest': max(timed, key=timed.get) if timed else None}

    found['every_run'] = _part(survey) if task.get('survey') else {'skipped': 'no survey asked'}
    save(dict(found))
    samples = task.get('samples')
    if samples:
        # With a survey, the study is of the model's slowest run: a target names the heaviest run.
        slowest = found['every_run'].get('slowest')
        sampled = run if slowest in (None, 'None') else slowest
        found['batch'] = _part(lambda: study(model, sampled, samples, task.get('jobs') or 1))
    else:
        found['batch'] = {'skipped': 'no samples asked'}
    return found


def study(model, run, samples, jobs=1):
    """The throughput of a Monte Carlo study of one run (`napkin.spread.spread`) with `samples`
    samples on `jobs` processes, of the values that the run names at its horizon.

    `seconds` is the whole study; `samples_per_second` the samples over it, the central run included,
    which is paid once. With more than one process, the study runs twice and the numbers are of the
    second: the first starts the processes of the pool (`first_seconds`). The peak memory is that of
    this process, without the processes of the pool. A run that draws nothing has no spread: it is
    skipped."""
    import napkin
    from napkin.commands.run import named

    configuration = configured(model, run)
    paths = named(model, napkin.run(model.program, configuration))

    def sampled():
        started = time.perf_counter()
        found = napkin.spread.spread(model, paths, run=run, samples=samples, seed=STUDY_SEED, jobs=jobs)
        return found, time.perf_counter() - started

    found, seconds = sampled()
    first = None
    if jobs > 1 and found.refused is None:
        first = {'first_seconds': seconds}
        found, seconds = sampled()
    if found.refused is not None:
        return failure(RuntimeError(f'the study is refused: {found.refused}'))
    if not any(sample.draws for sample in found.samples):
        return {'skipped': 'no draw'}
    return {
        'run': run,
        'samples': samples,
        'jobs': jobs,
        'seconds': seconds,
        'samples_per_second': samples / seconds,
        **(first or {}),
        'peak_mb': peak_mb(),
    }


TASKS = {'compile': compile_task, 'first': first_task, 'warm': warm_task}


def perform(task, save=None):
    """The result of one task, or the record of its failure: a failing workload never raises. A task
    of several measurements gives `save` what it has measured after each one."""
    try:
        return TASKS[task['kind']](task, save or (lambda found: None))
    except Exception as exc:
        return failure(exc)


# --- Where the time goes ----------------------------------------------------------------------------


def _label(code):
    """The key of a function in a profile's statistics, as cProfile makes it."""
    if isinstance(code, str):
        return (BUILT_IN, 0, code)
    return (code.co_filename, code.co_firstlineno, code.co_name)


def profile_stats(profile):
    """The statistics of a `cProfile.Profile`, in the shape of `pstats.Stats(profile).stats`:
    `{(file, line, name): (primitive calls, calls, own seconds, cumulative seconds, callers)}`, with
    `callers` `{caller: (calls, primitive calls, own seconds, cumulative seconds)}`.

    Functions that share a key are added up. `pstats` keeps one of them only, and the engine's
    generated programs all share one key (`program`, at line 1 of `<model>`), so `pstats` would lose
    the time of all but one."""
    entries = profile.getstats()
    stats, orphans = {}, set()
    for entry in entries:
        key = _label(entry.code)
        old = stats.get(key, (0, 0, 0.0, 0.0, {}))
        stats[key] = (
            old[0] + entry.callcount - entry.reccallcount,
            old[1] + entry.callcount,
            old[2] + entry.inlinetime,
            old[3] + entry.totaltime,
            old[4],
        )
    for entry in entries:
        caller = _label(entry.code)
        for call in entry.calls or ():
            callee = _label(call.code)
            if callee not in stats:
                # The profiler gives some functions no entry of their own, only their calls under a
                # caller. Such a function takes the sum of those calls, so its time is not lost.
                stats[callee] = (0, 0, 0.0, 0.0, {})
                orphans.add(callee)
            if callee in orphans:
                found = stats[callee]
                stats[callee] = (
                    found[0] + call.callcount - call.reccallcount,
                    found[1] + call.callcount,
                    found[2] + call.inlinetime,
                    found[3] + call.totaltime,
                    found[4],
                )
            callers = stats[callee][4]
            old = callers.get(caller, (0, 0, 0.0, 0.0))
            callers[caller] = (
                old[0] + call.callcount,
                old[1] + call.callcount - call.reccallcount,
                old[2] + call.inlinetime,
                old[3] + call.totaltime,
            )
    return stats


def analysis_spans(source):
    """The line spans, `(first, last)`, of the functions of `ANALYSIS` at the top of the module text
    `source` (the text of `napkin/expressions.py`). A function inside one of them is in its span."""
    spans = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in ANALYSIS:
            first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
            spans.append((first, node.end_lineno))
    return tuple(spans)


def group_of(function, spans=()):
    """The group of one function of a profile, `(file, line, name)`, by its file. In
    `napkin/expressions.py`, a function is `analysis` when its name is in `ANALYSIS` or its line is in
    one of `spans` (`analysis_spans`), and `expressions` otherwise. A function of C has no file: it is
    `linear_algebra` when its name is of `LINEAR`, and of no group otherwise."""
    file, line, name = function
    if file in GENERATED:
        return 'expressions'
    if file == BUILT_IN:
        return 'linear_algebra' if any(mark in str(name) for mark in LINEAR) else 'other'
    path = '/' + str(file).replace('\\', '/').lstrip('/')
    if path.endswith('/' + EXPRESSIONS):
        inside = any(first <= line <= last for first, last in spans)
        return 'analysis' if name in ANALYSIS or inside else 'expressions'
    for group, places in FILES:
        for place in places:
            if ('/' + place in path) if place.endswith('/') else path.endswith('/' + place):
                return group
    return 'other'


def _landing(stats, free, groups, spans):
    """For each function of `free` (the functions of no group), the share of its time that each group
    takes in the end: an array of len(free) rows and len(GROUPS) columns.

    A function of no group gives its time to its callers, in proportion to its own time under each
    (to the number of calls, when no time was measured). A caller of a group keeps its part; a caller
    of no group gives it to its own callers in the same way. Functions that call each other, as a
    recursive copy does, make this a set of linear equations, which is solved exactly. What no caller
    takes stays in `other`."""
    import numpy as np
    from scipy.sparse import csc_matrix, identity
    from scipy.sparse.linalg import splu

    place = {function: k for k, function in enumerate(free)}
    column = {group: k for k, group in enumerate(GROUPS)}
    direct = np.zeros((len(free), len(GROUPS)))
    rows, columns, shares = [], [], []
    for function, k in place.items():
        callers = {
            caller: entry for caller, entry in (stats[function][4] or {}).items() if caller != function
        }
        weights = {caller: entry[2] for caller, entry in callers.items() if entry[2] > 0}
        if not weights:
            weights = {caller: entry[0] for caller, entry in callers.items() if entry[0] > 0}
        whole = sum(weights.values())
        for caller, weight in weights.items():
            if caller in place:
                rows.append(k)
                columns.append(place[caller])
                shares.append(weight / whole)
            else:
                direct[k, column[groups.get(caller) or group_of(caller, spans)]] += weight / whole
    moves = csc_matrix((shares, (rows, columns)), shape=(len(free), len(free)))
    # A little less than the whole moves on at each step, so the equations have one solution even for
    # functions that only call each other.
    system = (identity(len(free), format='csc') - (1 - 1e-12) * moves).tocsc()
    return np.clip(splu(system).solve(direct), 0.0, 1.0)


def attribution(stats, spans=()):
    """Where the time of a profile goes: `{'seconds': the whole, 'groups': {group: {'seconds', 'share',
    'own_seconds'}}}` for each group of `GROUPS`, from statistics in the shape of
    `pstats.Stats(…).stats`. The shares add up to 1.

    `own_seconds` is the own time (`tottime`) of the functions of the group's files (`group_of`), and
    of every other function for `other`. `seconds` and `share` add the helpers: a function of no group
    (a library, the interpreter, a function of C, which has no file) gives its own time to the
    functions that call it, and so on up the calls, until a function of a group takes it
    (`_landing`). `other` keeps the time that no function of a group calls for."""
    groups = {function: group_of(function, spans) for function in stats}
    own = dict.fromkeys(GROUPS, 0.0)
    for function, entry in stats.items():
        own[groups[function]] += entry[2]
    seconds = {**own, 'other': 0.0}
    free = [function for function in stats if groups[function] == 'other']
    if free:
        for function, row in zip(free, _landing(stats, free, groups, spans)):
            taken = 0.0
            for group, share in zip(GROUPS, map(float, row)):
                seconds[group] += stats[function][2] * share
                taken += share
            seconds['other'] += stats[function][2] * max(0.0, 1.0 - taken)
    whole = sum(own.values())
    return {
        'seconds': whole,
        'groups': {
            group: {
                'seconds': seconds[group],
                'share': seconds[group] / whole if whole else 0.0,
                'own_seconds': own[group],
            }
            for group in GROUPS
        },
    }


# --- One measurement in a process of its own --------------------------------------------------------


def inline(task, timeout=None):
    """The result of a task in this process, with no time limit: for a test, which then needs no
    process for each measurement. The process is not fresh, so its times are not cold."""
    return perform({**task, 'started': time.time()})


def isolated(task, timeout):
    """The result of a task in a fresh process, `python -m tools.bench --measure TASK`, which gets
    `timeout` seconds. The process runs from the checkout with the run store off. A process that
    passes the limit is stopped. That, and a process that ends before its whole result, gives a
    failure record, with the measurements that the process had saved (`outcome`)."""
    environment = {
        **os.environ,
        'PYTHONPATH': os.pathsep.join(filter(None, (str(ROOT), os.environ.get('PYTHONPATH')))),
        'PYTHONDONTWRITEBYTECODE': '1',
        'NAPKIN_STORE': 'off',
    }
    with tempfile.TemporaryDirectory(prefix='napkin-bench-') as folder:
        out = Path(folder) / 'result.json'
        command = [sys.executable, '-B', '-m', 'tools.bench', '--result', str(out), '--measure']
        command.append(json.dumps({**task, 'started': time.time()}))
        try:
            done = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return outcome(out, TimeoutError(f'no result after {timeout:g} s'))
        last = (done.stderr.strip().splitlines() or [''])[-1]
        problem = f'the process ended with status {done.returncode} before its result: {last}'
        return outcome(out, ChildProcessError(problem))


def outcome(out, problem):
    """The result that a process wrote to the file `out`. When the file holds no whole result (none,
    or the measurements that the process saved on its way, marked `partial`), the result is what the
    file holds with the failure record of `problem`, the exception that says how the process ended."""
    try:
        found = json.loads(Path(out).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return failure(problem)
    return {**found, **failure(problem)} if found.pop('partial', False) else found


def child(task, out):
    """What the process of one measurement does: perform the task and write its result to `out`. A
    task also saves there what it has measured so far, marked `partial`; each write replaces the file
    whole, so a process that is stopped leaves a file that reads."""
    out = Path(out)

    def write(found):
        scratch = out.with_name(out.name + '.part')
        scratch.write_text(json.dumps(found), encoding='utf-8')
        os.replace(scratch, out)

    write(perform(json.loads(task), lambda found: write({**found, 'partial': True})))
    return 0


# --- The harness ------------------------------------------------------------------------------------


# The measurements of the warm process, in the order in which it makes them, with their names as stages.
WARM = (
    ('warm', 'warm run'),
    ('report', 'report'),
    ('where', 'where'),
    ('every_run', 'survey'),
    ('batch', 'batch'),
)


def _after(found, stage):
    """The record of a measurement that was not tried, because the stage that it needs failed."""
    return {'failed': found['failed'], 'from': stage}


def _warmed(found):
    """The measurements of a warm process (`WARM`) from its result. A process that failed gives
    its failure to the first measurement that it did not finish, and each later one names that stage."""
    parts, failed = {}, None
    for key, stage in WARM:
        if key in found:
            parts[key] = found[key]
        elif failed is None:
            parts[key], failed = {'failed': found['failed']}, stage
        else:
            parts[key] = _after(found, failed)
    return parts


def _shown(workload, root):
    """The path of a workload in the document: from the checkout, or from the folder of the families."""
    path = Path(workload.path)
    if workload.family:
        return f'{path.parent.name}/{path.name}'
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def record(workload, run, compiled, first, warmed, root=ROOT):
    """The record of one workload and run in the document. One run and a batch are apart (`one_run`,
    `batch`), and cold and warm are apart."""
    return {
        'kind': workload.kind,
        'name': workload.name,
        'path': _shown(workload, root),
        'run': run,
        **({'family': workload.family, 'size': workload.size} if workload.family else {}),
        'compile': {'cold': {key: value for key, value in compiled.items() if key != 'runs'}},
        'values': {
            'one_run': {
                'cold': first,
                'warm': warmed['warm'],
                'report': warmed['report'],
                'where': warmed['where'],
            },
            'every_run': warmed['every_run'],
            'batch': warmed['batch'],
        },
    }


def bench(
    workloads,
    *,
    repeats=3,
    samples=None,
    jobs=1,
    survey=False,
    timeout=600,
    run_task=isolated,
    say=None,
    root=ROOT,
):
    """Measure each workload and return the records, one for each workload and run, in order.

    Each task is one call of `run_task(task, timeout)`, by default a fresh process: the cold compile,
    the first result, and the warm process (the warm runs, the study of the run with its report, where
    the time of that goes, one run of each run of the model with `survey`, and the Monte Carlo study on
    `jobs` processes). The cold
    compile of a model file is measured once and stands in the record of each of its runs. A
    measurement that fails is a failure record, and the harness goes on. A measurement that needs a
    stage that failed is not tried: the first result and the warm process after a failed compile, the
    warm process after a failed first result, and what the warm process had not yet measured when it
    failed. Its record repeats the failure and names the stage (`from`). `say(line)` gets one line
    for each record."""
    records, compiles = [], {}
    for workload in workloads:
        path = str(workload.path)
        if path not in compiles:
            if workload.family:
                families.write(workload.family, workload.size, Path(workload.path).parent.parent)
            compiles[path] = run_task({'kind': 'compile', 'path': path}, timeout)
        compiled = compiles[path]
        if 'failed' in compiled:
            runs = [None if workload.run == ALL else workload.run]
        else:
            runs = compiled['runs'] if workload.run == ALL else [workload.run or compiled['runs'][0]]
        for run in runs:
            if 'failed' in compiled:
                first = _after(compiled, 'compile')
            else:
                first = run_task({'kind': 'first', 'path': path, 'run': run}, timeout)
            if 'failed' in first:
                again = _after(first, first.get('from', 'first result'))
                warmed = dict.fromkeys((key for key, _ in WARM), again)
            else:
                task = {'kind': 'warm', 'path': path, 'run': run, 'repeats': repeats, 'survey': survey}
                warmed = _warmed(run_task({**task, 'samples': samples, 'jobs': jobs}, timeout))
            records.append(record(workload, run, compiled, first, warmed, root))
            if say is not None:
                say(_line(records[-1]))
    return records


def _git(root, *arguments):
    try:
        done = subprocess.run(['git', *arguments], cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def machine():
    """The machine and the numerical libraries of this process, as the run store keys them
    (`napkin.store.ENVIRONMENT`)."""
    from napkin.store import ENVIRONMENT

    return json.loads(json.dumps(ENVIRONMENT, ensure_ascii=False))


def document(records, settings, root=ROOT):
    """The result document: the revision of the checkout at `root` and whether its tree is dirty, the
    machine, the number of processors, the settings of the harness, the files of each group of "where
    the time goes" in this revision (`groups`), and the records of the workloads."""
    status = _git(root, 'status', '--porcelain')
    return {
        'tool': 'tools.bench',
        'commit': _git(root, 'rev-parse', 'HEAD'),
        'dirty': None if status is None else bool(status),
        'machine': machine(),
        'processors': os.cpu_count(),
        'settings': dict(settings),
        'groups': {
            **{group: list(places) for group, places in FILES},
            'analysis': [*dict(FILES)['analysis'], f'{EXPRESSIONS}: {", ".join(ANALYSIS)}'],
            'expressions': [EXPRESSIONS, *dict(FILES)['expressions'], *GENERATED],
            'linear_algebra': [*dict(FILES)['linear_algebra'], *(f'{BUILT_IN} {mark}' for mark in LINEAR)],
        },
        'workloads': list(records),
    }


# --- The table --------------------------------------------------------------------------------------


def _seconds(value):
    if value is None:
        return '-'
    return f'{value:.3f}' if value < 100 else f'{value:.1f}'


def _whole(value):
    return '-' if value is None else f'{value:.0f}'


def _get(found, *keys):
    for key in keys:
        if not isinstance(found, dict) or key not in found:
            return None
        found = found[key]
    return found


def _failures(item):
    """[(the stage, the failure)] of one record: each failure once, at the stage that it came from."""
    one, found = item['values']['one_run'], []
    stages = (
        ('compile', item['compile']['cold']),
        ('first result', one['cold']),
        ('warm run', one['warm']),
        ('report', one['report']),
        ('where', one['where']),
        ('survey', item['values']['every_run']),
        ('batch', item['values']['batch']),
    )
    for stage, measurement in stages:
        if 'failed' in measurement and 'from' not in measurement:
            found.append((stage, measurement['failed']))
    return found


def _where(item, most=3):
    groups = _get(item, 'values', 'one_run', 'where', 'groups')
    if not groups:
        return ''
    ranked = sorted(groups.items(), key=lambda pair: -pair[1]['share'])[:most]
    return ', '.join(f'{name} {entry["share"]:.0%}' for name, entry in ranked if entry['share'] > 0)


def _slowest(item):
    """The slowest run of a record's survey, and how many runs the survey timed and how many failed."""
    runs = _get(item, 'values', 'every_run', 'runs')
    slowest = _get(item, 'values', 'every_run', 'slowest')
    if not runs or slowest is None:
        return ''
    failed = sum('failed' in found for found in runs.values())
    text = f'slowest of {len(runs)} runs: {slowest} {_seconds(runs[slowest]["seconds"])} s'
    return text + (f', {failed} failed' if failed else '')


def _line(item):
    """One line of progress for a record: its name, its run and its main times, or what failed."""
    failed = _failures(item)
    if failed:
        stage, text = failed[0]
        return f'  {item["name"]} ({item["run"] or "-"}): FAILED at the {stage}: {shortened(text, SHOWN)}'
    one = item['values']['one_run']
    return (
        f'  {item["name"]} ({item["run"]}): compile {_seconds(item["compile"]["cold"]["seconds"])} s, '
        f'first result {_seconds(one["cold"]["seconds"])} s, warm run {_seconds(one["warm"]["median_seconds"])} s'
    )


LEGEND = (
    'compile, first: the cold compile and the time to the first result, each with the peak memory of its '
    'process; warm, min: the median and the least of the warm runs of the engine alone; report: the report '
    'of every named value at the start and the horizon; members, values, flows: of the program; hist, '
    'pieces, trace: the histories, their pieces and the trace entries of the record; where the time goes: '
    'of a run and its report.'
)


def table(document):
    """The printed table of a result document: one row for each workload and run, with the cold
    compile, the first result, the warm run, the report of the run, the size of the run,
    the Monte Carlo study's samples in a second when samples were asked, and the three largest groups
    of the time of the study and its report. A failure shows at the end of
    its row, with its stage and the start of its text; the document holds the whole text."""
    batch = bool(document['settings'].get('samples'))
    heads = [
        'workload',
        'run',
        'compile s',
        'MB',
        'first s',
        'MB',
        'warm s',
        'min s',
        'MB',
        'report s',
    ]
    heads += ['members', 'values', 'flows', 'hist', 'pieces', 'trace']
    heads += (['samples/s'] if batch else []) + ['where the time goes']
    rows = []
    for item in document['workloads']:
        one = item['values']['one_run']
        facts = _get(one, 'warm', 'size') or {}
        row = [
            item['name'],
            item['run'] or '-',
            _seconds(_get(item, 'compile', 'cold', 'seconds')),
            _whole(_get(item, 'compile', 'cold', 'peak_mb')),
            _seconds(_get(one, 'cold', 'seconds')),
            _whole(_get(one, 'cold', 'peak_mb')),
            _seconds(_get(one, 'warm', 'median_seconds')),
            _seconds(_get(one, 'warm', 'min_seconds')),
            _whole(_get(one, 'warm', 'peak_mb')),
            _seconds(_get(one, 'report', 'report_seconds')),
            *(
                _whole(facts.get(key))
                for key in ('members', 'values', 'flows', 'histories', 'pieces', 'trace')
            ),
        ]
        if batch:
            row.append(_seconds(_get(item, 'values', 'batch', 'samples_per_second')))
        skipped = _get(item, 'values', 'batch', 'skipped') if batch else None
        notes = [_where(item), f'({skipped})' if skipped else '', _slowest(item)]
        notes += [f'FAILED at the {stage}: {shortened(text, SHOWN)}' for stage, text in _failures(item)]
        row.append('; '.join(filter(None, notes)))
        rows.append(row)
    widths = [max(len(head), *(len(row[k]) for row in rows)) for k, head in enumerate(heads[:-1])]
    lines = []
    for row in (heads, *rows):
        cells = [row[0].ljust(widths[0]), row[1].ljust(widths[1])]
        cells += [cell.rjust(width) for cell, width in zip(row[2:-1], widths[2:])]
        lines.append('  '.join((*cells, row[-1])).rstrip())
    failures = sum(bool(_failures(item)) for item in document['workloads'])
    lines += [f'Rows: {len(rows)}; with a failure: {failures}', LEGEND]
    return '\n'.join(lines)
