"""A study: runs of one program under several configurations (D9).

One engine invocation runs one program under one configuration and gives one record
(`napkin.engine.run`). A study runs one program under several: the named runs of a model under one
edit document (`study`), or the samples of a Monte Carlo study (`uncertainty.py`). Each run goes
through the run store (`napkin.store.run`), so a run that the store holds is read, not run again.

- `edits_for(model, edits)`: an edit document for a model's revision.
- `configurations(model, runs, edits)`: {name: configuration} of the named runs of a compiled model
  (`napkin.model.compile.Compiled`), or of each run that it declares, or of its default run (named
  None) when it declares none, under one edit document. The document is one transaction: the front
  end checks it whole, in every run of the model (`model/runs.py`), and every problem of it or of a
  run's name refuses the study at once (`LanguageError`), before any run starts.
- `run_all(program, configurations, work)`: `work(program, configuration, record)` for each
  configuration, in their order. A study of named runs keeps each whole record; a sample keeps a few
  values of its record.
- `study(model, runs, edits)`: the record of each named run (`configurations`, then `run_all`).

**Runs in processes** (change 10 of the plan): with `jobs` above 1, the runs go to a pool of `jobs`
new processes, started by `spawn`, which take the program once, when they start, and the store of
this process (`store.pool_options`). The configurations go to them in chunks, in their order, a few
for each process, and only what `work` gives back crosses to this process, so a sample never sends
its record. The results come in the order of the configurations, whatever order the processes finish
in. A run alone, in a batch in this process or in another process is one run of the engine, whose
answers agree within its stated tolerances, and the same study gives the same results again, bit for
bit (change 11): no run reads the state of another, but for the records of the store. The processes
end with the process that made them. `progress(done, total)` is called as runs finish; `cancel`, an
event such as a `threading.Event`, stops the study between runs, or chunks, with `Cancelled`.

A run that fails gives its record with the failure, as the engine gives it; a part that the engine
does not run, or a configuration that the program cannot take, raises as `napkin.engine.run` raises.
"""

from __future__ import annotations

import multiprocessing
import os
import threading
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from functools import partial

from .. import SCHEMA_VERSION, store
from ..model.language.problems import LanguageError
from ..model.runs import check, options_of

# The chunks of a pool for each of its processes: enough to keep each busy to the end, few enough that
# the program's results come back in large parts.
CHUNKS = 4
# How often a study in a pool looks at `cancel`, in seconds.
POLL = 0.25


class Cancelled(Exception):
    """The caller stopped a study before all its runs ran."""


def edits_for(model, edits=None):
    """An edit document for this revision of a compiled model: the schema version and the model's hash,
    with the given edits (`set`, `options`, `runs`, `reason`)."""
    return {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **(edits or {})}


def configurations(model, runs=None, edits=None):
    """{name: configuration} of the named `runs` of a compiled model, or of each run that it declares,
    in its order, or {None: its default run} when it declares none, under the edit document `edits`
    (see the module). Raises `LanguageError` with every problem."""
    if runs is None:
        runs = [item.name for item in model.declared.runs] or [None]
    elif isinstance(runs, str) or len(set(runs)) != len(runs):
        raise ValueError(f'runs is a list that names each run once, not {runs!r}')
    problems = list(check(model.declared, edits, model.model_hash))
    for name in runs:
        try:
            options_of(model.declared, name)
        except LanguageError as error:
            problems += error.problems
    if problems:
        raise LanguageError(problems)
    return {name: model.configure(name, edits) for name in runs}


def whole(program, configuration, record):
    """What a study of named runs keeps of a run: its record."""
    return record


def run_all(program, configurations, work=whole, *, jobs=1, progress=None, cancel=None):
    """[`work(program, configuration, record)` of each configuration], in their order, each record from
    the run store (see the module). With `jobs` above 1, `work` must be a function that another process
    can import, or a `functools.partial` of one."""
    configurations = list(configurations)
    if isinstance(jobs, bool) or not isinstance(jobs, int) or jobs < 1:
        raise ValueError(f'jobs is a whole number from 1, not {jobs!r}')
    if jobs == 1 or len(configurations) < 2:
        return _here(program, configurations, work, progress, cancel)
    return _pool(program, configurations, work, jobs, progress, cancel)


def study(model, runs=None, edits=None, *, jobs=1, progress=None, cancel=None):
    """{name: record} of the named runs of a compiled model under one edit document (`configurations`),
    run through the store (`run_all`)."""
    found = configurations(model, runs, edits)
    records = run_all(model.program, found.values(), jobs=jobs, progress=progress, cancel=cancel)
    return dict(zip(found, records))


def _stop(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled


def _here(program, configurations, work, progress, cancel):
    """The runs one after another in this process."""
    out = []
    for configuration in configurations:
        _stop(cancel)
        out.append(work(program, configuration, store.run(program, configuration)))
        if progress is not None:
            progress(len(out), len(configurations))
    return out


def _pool(program, configurations, work, jobs, progress, cancel):
    """The runs in a pool of `jobs` new processes (see the module)."""
    _stop(cancel)
    size = max(1, -(-len(configurations) // (jobs * CHUNKS)))
    chunks = [configurations[at : at + size] for at in range(0, len(configurations), size)]
    pool = ProcessPoolExecutor(
        min(jobs, len(chunks)),
        mp_context=multiprocessing.get_context('spawn'),
        **store.pool_options(initializer=_start, initargs=(program,)),
    )
    futures = [pool.submit(_chunk, work, chunk) for chunk in chunks]
    done, pending = 0, set(futures)
    try:
        while pending:
            finished, pending = wait(pending, timeout=POLL, return_when=FIRST_COMPLETED)
            for future in finished:
                done += len(future.result())
            if finished and progress is not None:
                progress(done, len(configurations))
            if pending:
                _stop(cancel)
        return [result for future in futures for result in future.result()]
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


# The program of a process of a pool, which it took when it started.
_WORKER = {}


def _start(program):
    """The start of a process of a pool: it keeps the program, and ends when the process that made it
    ends, stopped or killed, so that no process waits for work that can never come."""
    _WORKER['program'] = program
    parent = multiprocessing.parent_process()
    if parent is not None:
        threading.Thread(target=partial(_end_with, parent), daemon=True).start()


def _end_with(parent):
    parent.join()
    os._exit(1)


def _chunk(work, configurations):
    """The runs of one chunk in a process of a pool, one after another."""
    program = _WORKER['program']
    return [
        work(program, configuration, store.run(program, configuration)) for configuration in configurations
    ]
