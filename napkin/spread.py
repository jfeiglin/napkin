"""Spreads: one run of a model sampled many times, with the runs that it is compared with.

`spread` draws every input that has a distribution, in the model or in the edit document. It runs
the run on these draws. It also runs, on the same draws, the run that the run is compared with
(`versus`) and each run that is compared with the run; or it runs the runs of a list, and no others;
or, with `options`, it runs one run with those options in place of its own (`Model.combination`).
The work is the engine's Monte Carlo study
(`engine.uncertainty.evaluate_uncertainty`; docs/engine.md, "Monte Carlo studies"):

1. The central study runs each run with each distribution at its central value. An edit document
   or a run that fails its checks rejects the spread.
2. Each sample is checked, then each sample runs. A sample that fails its checks rejects the spread
   before any sample runs. A sample whose run fails also rejects the spread.
3. The engine summarizes each outcome over the samples (`uncertainty_report`).

    from napkin.spread import spread

    found = spread('model.scn', 'a', samples=200, seed=0, times=[24])
    if found['status'] == 'completed':
        summaries = found['report']['uncertainty']['runs']

The arguments:

- `model`: the path of a model file, or a model that `load_scenario` built from a file. To sample
  several runs of one model, load the model once and give the model.
- `run`: the name of the run, which the spread samples with the runs of its comparisons
  (`sampled_runs`); or a list of the names of the runs to sample, with no other run.
- `edits`: an edit document, as `evaluate_study` takes it, or None for the model as it is written.
- `samples`, `seed` and `method`: the sampling settings (`SamplingSettings`).
- `times`: more times, in hours, at which each sample gives its outcomes and the report summarizes
  them (the `series` of each outcome). The report always gives `final`, the end of the run.
- `options`: the names of options to put into the run in place of its options of their groups. The
  spread then samples the model of that combination (`Model.combination`), whose one run is `run`,
  with no comparison: `run` names one run, as a name or a list of one name. Each run of a
  comparison takes a spread of its own; with the same seed, the spreads draw the same values. The
  edit document applies to the combination as to the run (`package.combined` gives the document
  that reaches it).
- `progress(phase, done, total)`: called when a phase starts and as its samples finish. The phase is
  `checking`, then `running`.
- `cancel`: an event, such as a `threading.Event`. When it is set, the spread stops between samples.
- `jobs`: the number of processes that check and run the samples. By default, it is one less than
  the number of processors. With 1, the samples run in this process, one after another.

Settings, times, jobs, options or a list of runs that are not valid raise ValueError before the
central study starts. A model file that does not build raises ModelError, as `load_scenario` does, and
so do options that the run cannot take (`Model.combination`).

The result is a dict:

- `model_hash` and `implementation_hash`: the revisions of the model and of the engine.
- `status`: `completed`; `rejected`, when the engine rejects the edit document, a run or a sample;
  `failed`, when the report of the samples is not numerically valid; or `cancelled`.
- `diagnostics`: the engine's diagnostics, made readable (`readable`).
- `report`: the engine's report (`uncertainty_report`). It is the report of the central study, with
  the settings and the summaries of each sampled run in `uncertainty`. A rejected or failed spread
  has no summaries. A cancelled spread has no report.
- `result`: the engine's study (`UncertaintyResult`), only for a completed spread. It holds the
  central study and, for each sampled run, the values, outcome rows and event counts of each sample.

The pool: each process loads the model from its file once, with the runs that this model admits
(`admission_runs`), and keeps it; with options, it makes the combination of the run with them once
and keeps it too. If the file changed after this process loaded the model, a process loads another
revision, and the spread stops with ValueError. A pool stays for the next spread, and its processes
end when this process ends. Each process of a pool imports the main module of the program. So a
script that uses more than one process calls `spread` under `if __name__ == '__main__':`.
"""

import math
import multiprocessing
import os
import re
import threading
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from functools import lru_cache
from pathlib import Path

from . import store
from .engine import SamplingSettings
from .engine.uncertainty import (
    StudyCancelled,
    check_sample,
    evaluate_uncertainty,
    run_sample,
    uncertainty_report,
)
from .model import load_scenario

# The processes of a pool by default: every processor but one, which this process keeps.
SAMPLE_WORKERS = max(1, (os.cpu_count() or 2) - 1)
# The pools of this process, by their number of processes and their run store.
_POOLS = {}


def input_id(model, name):
    """The name that an edit gives an input of the structure: `entity.field`, and `set.k.field` for an
    input of copy k of a set (the structure's `set_k.field`)."""
    entity, _, field = name.rpartition('.')
    return f'{model.entities.get(entity, entity)}.{field}'


def readable(model, diagnostics):
    """The diagnostics for a reader: one about an input names it as edits do (`input`) and calls it
    by its label in its message. The report keeps the engine's own."""
    inputs = getattr(model, 'inputs', None) or {}
    names = {}
    for key in inputs:
        names[key] = names[input_id(model, key)] = key
    out = []
    for given in diagnostics:
        item = dict(given)
        found = item.get('input') or (item.get('path') or '').rpartition('/')[2]
        if found in names:
            key = names[found]
            item['input'] = input_id(model, key)
            label = inputs[key].get('doc')
            if label:
                spelled = '|'.join(
                    re.escape(name) for name in sorted({found, key, item['input']}, key=len, reverse=True)
                )
                item['message'] = re.sub(
                    rf'(?<![\w.])(?:{spelled})(?![\w.])', lambda _: f'“{label}”', item['message']
                )
        out.append(item)
    return out


def sampled_runs(model, run):
    """The runs of a spread of `run`, in the order of the file: the run, the run that it is compared
    with, and each run that is compared with it. An unknown run stands alone: the study rejects it."""
    info = model.runs.get(run)
    if info is None:
        return [run]
    pairs = {run, info['comparison_of']} | {
        r for r, other in model.runs.items() if other['comparison_of'] == run
    }
    return [r for r in model.runs if r in pairs]


def _runs(model, run, options=()):
    """The runs of a spread: `run` and the runs of its comparisons (`sampled_runs`), or the runs that a
    list names, each once. The study takes them in the order of the file. With `options`, the one run
    that `run` names, as a name or a list of one name."""
    if isinstance(run, str) and not options:
        return sampled_runs(model, run)
    try:
        runs = [run] if isinstance(run, str) else list(run)
    except TypeError:
        runs = []
    if not runs or not all(isinstance(name, str) and name for name in runs) or len(set(runs)) != len(runs):
        raise ValueError(f'run is the name of a run, or a list that names each of its runs once, not {run!r}')
    if options and len(runs) > 1:
        raise ValueError(f'A spread with options samples one run, not {runs!r}')
    return runs


def _options(options):
    """The options of a spread as a tuple, each named once."""
    if isinstance(options, str):
        raise ValueError(f'options is a list of the names of options, not {options!r}')
    try:
        found = tuple(options or ())
    except TypeError:
        raise ValueError(f'options is a list of the names of options, not {options!r}') from None
    if not all(isinstance(name, str) and name for name in found) or len(set(found)) != len(found):
        raise ValueError(f'options is a list that names each of its options once, not {options!r}')
    return found


def _times(model, times):
    """The asked times, each a number of hours from 0 to the end of the run."""
    horizon = model.time['horizon']
    try:
        asked = [] if times is None else list(times)
    except TypeError:
        raise ValueError(f'times is a list of hours, not {times!r}') from None
    for t in asked:
        if (
            isinstance(t, bool)
            or not isinstance(t, (int, float))
            or not math.isfinite(t)
            or not 0 <= t <= horizon
        ):
            raise ValueError(f'A reporting time is a number of hours from 0 to {horizon}, not {t!r}')
    return asked


def _kept(outcome):
    """What a spread keeps of one sample (`run_sample`): its outcome rows, its failures and the counts
    of its outcomes by chance. Its run is large, and the rows hold what the summaries read. A sample
    whose run fails can give no counts."""
    return {
        'completed': None,
        'rows': outcome['rows'],
        'failures': outcome['failures'],
        'events': outcome.get('events'),
    }


@lru_cache(maxsize=4)
def _model(path, admission_runs, revisions):
    """The model of a spread in a process of the pool: loaded from its file once, and kept for each
    revision that a spread asks for."""
    model = load_scenario(path, admission_runs=admission_runs)
    if (model.model_hash, model.implementation_hash) != revisions:
        raise ValueError(f'A sample process loaded another model or implementation revision from {path}')
    return model


@lru_cache(maxsize=4)
def _combination(path, admission_runs, revisions, run, options):
    """The combination of a run with options in a process of the pool (`Model.combination`), made once
    from the model of the file (`_model`) and kept."""
    return _model(path, admission_runs, revisions).combination(run, options)


def _model_of(path, admission_runs, revisions, run, options):
    """The model that a sample of `run` runs in a process of the pool: the model of the file, or, with
    options, the combination of the run with them."""
    if options:
        return _combination(path, admission_runs, revisions, run, options)
    return _model(path, admission_runs, revisions)


def _check(task):
    """One sample's resolution in a process of the pool: its diagnostics, none when it can run."""
    path, admission_runs, revisions, run, options, point = task
    return check_sample(_model_of(path, admission_runs, revisions, run, options), run, point)


def _sample(task):
    """One sample in a process of the pool: its outcome rows at the spread's times, its failures and
    the counts of its outcomes by chance."""
    path, admission_runs, revisions, run, options, point, times, luck = task
    model = _model_of(path, admission_runs, revisions, run, options)
    return _kept(run_sample(model, run, point, None, times, luck))


def _end_with_parent():
    """In a sample process: end this process when the process that made it ends, stopped or killed,
    so that no sample process waits for work that can never come."""
    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch():
        parent.join()
        os._exit(1)

    threading.Thread(target=watch, daemon=True).start()


def _pool(workers):
    """The pool of `workers` sample processes of this process, made once for each run store: its
    processes keep their models."""
    key = (workers, store.current())
    if key not in _POOLS:
        _POOLS[key] = ProcessPoolExecutor(
            workers,
            mp_context=multiprocessing.get_context('spawn'),
            **store.pool_options(initializer=_end_with_parent),
        )
    return _POOLS[key]


def spread(
    model,
    run,
    edits=None,
    *,
    samples=200,
    seed=0,
    method='random',
    times=(),
    options=(),
    progress=None,
    cancel=None,
    jobs=None,
):
    """The spread of `run` and of the runs of its comparisons, or of the runs of a list, or of one run
    with `options`, under `edits`. The module's docstring describes the arguments and the result."""
    settings = SamplingSettings(samples, seed, method)
    workers = SAMPLE_WORKERS if jobs is None else jobs
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError(f'jobs is a whole number from 1, not {jobs!r}')
    if isinstance(model, (str, os.PathLike)):
        path = Path(model).resolve()
        model = load_scenario(path)
    else:
        path = Path(model.origin).resolve()
    options = _options(options)
    asked = _times(model, times)
    runs = _runs(model, run, options)
    if workers > 1 and not path.is_file():
        raise ValueError(
            f'The processes of a pool load the model from its file, and {model.origin} is not a file: '
            'use jobs=1'
        )
    revisions = (model.model_hash, model.implementation_hash)
    # The processes of the pool load the model as this model was loaded, with its admitted runs, then
    # make the combination; the combination keeps the model's revisions.
    admission_runs = None if model.admission_runs is None else tuple(model.admission_runs)
    if options:
        model = model.combination(runs[0], options)
    where = (str(path), admission_runs, revisions)

    def stop():
        if cancel is not None and cancel.is_set():
            raise StudyCancelled

    def tell(phase, done, total):
        if progress is not None:
            progress(phase, done, total)

    def in_pool(phase, function, tasks):
        """`function` of each task in the pool, in order: the progress of the phase goes to
        `progress`, and the spread stops when `cancel` is set. A task that fails stops the spread
        at once, and the queued tasks never start."""
        stop()
        if not tasks:
            return []
        pool = _pool(workers)
        futures = [pool.submit(function, task) for task in tasks]
        pending, done = set(futures), 0
        tell(phase, 0, len(futures))
        try:
            while pending:
                finished, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in finished:
                    future.result()
                if finished:
                    done += len(finished)
                    tell(phase, done, len(futures))
                if pending:
                    stop()  # between samples
            return [future.result() for future in futures]
        finally:
            for future in futures:
                future.cancel()

    def in_process(phase, function, tasks):
        """`function` of each task in this process, in order, with the same progress and stops."""
        stop()
        if not tasks:
            return []
        out = []
        tell(phase, 0, len(tasks))
        for task in tasks:
            if out:
                stop()  # between samples
            out.append(function(task))
            tell(phase, len(out), len(tasks))
        return out

    def checked(task):
        name, _, point = task
        return check_sample(model, name, point)

    def ran(task):
        name, _, point, at, luck = task
        return _kept(run_sample(model, name, point, None, at, luck))

    def check_samples(tasks):
        if workers == 1:
            return in_process('checking', checked, tasks)
        return in_pool('checking', _check, [(*where, name, options, point) for name, _, point in tasks])

    def run_samples(tasks):
        if workers == 1:
            return in_process('running', ran, tasks)
        return in_pool(
            'running',
            _sample,
            [(*where, name, options, point, at, luck) for name, _, point, at, luck in tasks],
        )

    try:
        stop()
        result = evaluate_uncertainty(
            model,
            edits,
            settings,
            runs=runs,
            times=asked,
            run_samples=run_samples,
            check_samples=check_samples,
        )
    except StudyCancelled:
        return {**_revisions(model), 'diagnostics': [], 'status': 'cancelled'}
    report = uncertainty_report(result, result.times)
    out = {
        **_revisions(model),
        'diagnostics': readable(model, report['diagnostics']),
        'status': 'completed'
        if report['admissible']
        else 'failed'
        if report['status'] == 'reporting_failure'
        else 'rejected',
        'report': report,
    }
    if report['admissible']:
        out['result'] = result
    return out


def _revisions(model):
    return {'model_hash': model.model_hash, 'implementation_hash': model.implementation_hash}
