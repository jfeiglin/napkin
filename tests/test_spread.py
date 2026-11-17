"""Spreads (napkin/spread.py): a run and the runs that it is compared with, sampled in a
pool of processes or in this process, give the engine's Monte Carlo study of one process, bit for
bit, and so does a run with options in place of its own, whose combination each process makes. Each
sample of a tiny model holds its closed form, and the summaries hold the percentiles of those closed
forms. Every sample is checked before any sample runs, a cancelled spread stops between samples, and
the diagnostics name inputs as edits do and call them by their labels."""

import json
import math
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import spearmanr

from napkin import spread, store
from napkin.engine import SamplingSettings, edits_for, evaluate_uncertainty
from napkin.engine.uncertainty import uncertainty_report
from napkin.model import ModelError
from tests.build import (
    BASIS,
    check,
    compiled,
    edit,
    member,
    option,
    options,
    output,
    replace,
    scenario,
    system,
    timer,
    uncertain,
)
from tests.helpers import ROOT
from tests.owned import write_scenario


def recorder(calls):
    """A progress callback that keeps each call."""
    return lambda phase, done, total: calls.append((phase, done, total))


def no_sample(*arguments):
    raise AssertionError('A rejected spread runs no sample')


# ---- readable diagnostics -----------------------------------------------------------------------


@pytest.mark.parametrize('level', ['set', 'options', 'runs'])
def test_rejected_inputs_return_their_diagnostics_by_label_and_no_samples(level):
    """A number of people below the input's range, at each level of the edit document, rejects the
    spread of run b. The diagnostics are the report's, each about the input that it names by its
    label, and the spread keeps no sample."""
    model = compiled(scenario())
    low, _ = model.inputs['service.n']['range']
    values = {'service.n': low - 1}
    at = {
        'set': values,
        'options': {'Default': values},
        'runs': {'b': values},
    }[level]
    found = spread.spread(model, 'b', edits_for(model, {level: at}), samples=4, jobs=1)
    report = found['report']
    assert found['status'] == 'rejected' and 'result' not in found
    assert report['admissible'] is False and report['uncertainty']['runs'] == {}
    label = model.inputs['service.n']['doc']
    assert [d['code'] for d in found['diagnostics']] == [d['code'] for d in report['diagnostics']]
    assert {d['code'] for d in found['diagnostics']} == {'bounds'}
    for shown, reported in zip(found['diagnostics'], report['diagnostics'], strict=True):
        assert shown['input'] == 'service.n'
        assert 'service.n' in reported['message']
        assert shown['message'] == reported['message'].replace('service.n', f'“{label}”')


def test_an_input_of_a_copy_is_named_as_edits_name_it():
    """A copy's input is `set_k.field` in the structure and `set.k.field` in an edit; a diagnostic
    names it as the edits do, by either name."""
    copy = SimpleNamespace(inputs={'service_1.n': {'doc': 'People'}}, entities={'service_1': 'service.1'})
    found = spread.readable(
        copy,
        [
            {
                'code': 'bounds',
                'path': 'edits/set/service.1.n',
                'message': 'service.1.n: 0 is outside [1, 100]',
            },
            {'code': 'stale', 'input': 'service_1.n', 'message': 'The review of service_1.n is stale'},
            {'code': 'other', 'path': 'service/assert:/0', 'message': 'Conserve people'},
        ],
    )
    assert [(d.get('input'), d['message']) for d in found] == [
        ('service.1.n', '“People”: 0 is outside [1, 100]'),
        ('service.1.n', 'The review of “People” is stale'),
        (None, 'Conserve people'),
    ]
    assert spread.readable(compiled(scenario()), []) == []


# ---- spreads ------------------------------------------------------------------------------------


def test_samples_in_a_pool_of_processes_give_the_study_of_one_process(tmp_path, monkeypatch):
    """Eight samples run in two processes, each of which loads its own model from the file. The report
    is the one of the engine's study in one process, bit for bit, and so is the report of a spread in
    this process. Each sample serves rate * min(t, end) people by time t, each summary holds the type-7
    percentiles of those closed forms, and the progress counts every check and every sample."""
    path, model = write_scenario(tmp_path, timer())
    monkeypatch.setattr(spread, '_POOLS', {})
    times, calls = [1, 6, 12, 24], []
    # No run comes from the run store: each process simulates its own.
    with store.use(None):
        try:
            pooled = spread.spread(
                path, 'a', samples=8, seed=3, times=times, progress=recorder(calls), jobs=2
            )
        finally:
            for pool in spread._POOLS.values():
                pool.shutdown()
        alone = spread.spread(model, 'a', samples=8, seed=3, times=times, jobs=1)
        reference = evaluate_uncertainty(model, None, SamplingSettings(8, 3), runs=['a'], times=times)
    expected = json.dumps(uncertainty_report(reference, reference.times), sort_keys=True)
    for found in (pooled, alone):
        assert found['status'] == 'completed', found['diagnostics']
        assert json.dumps(found['report'], sort_keys=True) == expected
    assert pooled['result'].samples == alone['result'].samples
    served, sampled = model.outputs['served'], pooled['result'].samples['a']
    horizon = model.time['horizon']
    # Each sample gives its rows at the asked times and at the end of the run, and at no other time.
    at = sorted({*times, horizon})
    for values, rows in zip(sampled['values'], sampled['rows'], strict=True):
        assert [row['t'] for row in rows] == at
        for row in rows:
            closed = values['s.rate'] * min(row['t'], values['s.end'])
            assert row['values'][served] == pytest.approx(closed, rel=1e-9, abs=1e-9)
    summary = pooled['report']['uncertainty']['runs']['a']['outcomes'][served]
    assert [entry['t'] for entry in summary['series']] == times
    for entry in summary['series']:
        closed = [values['s.rate'] * min(entry['t'], values['s.end']) for values in sampled['values']]
        for p in (5, 25, 50, 75, 95):
            assert entry[f'p{p}'] == pytest.approx(np.percentile(closed, p), rel=1e-9, abs=1e-9)
    final = summary['points']['final']
    closed = [values['s.rate'] * min(horizon, values['s.end']) for values in sampled['values']]
    assert final['mean'] == pytest.approx(np.mean(closed), rel=1e-9)
    assert final['sd'] == pytest.approx(np.std(closed, ddof=1), rel=1e-9)
    for p in (5, 25, 50, 75, 95):
        assert final[f'p{p}'] == pytest.approx(np.percentile(closed, p), rel=1e-9)
    # The samples are checked, then they run: each phase counts up from none to all eight.
    assert [phase for phase, _, _ in calls] == sorted(
        (phase for phase, _, _ in calls), key=['checking', 'running'].index
    )
    for phase in ('checking', 'running'):
        counts = [(done, total) for name, done, total in calls if name == phase]
        assert counts[0] == (0, 8) and counts[-1] == (8, 8)
        assert [done for done, _ in counts] == sorted(done for done, _ in counts)


def test_the_drivers_of_an_outcome_are_the_rank_correlations_of_the_draws_with_it():
    """served(24 h) = rate * end in each sample, so the drivers of the served at the end are the rank
    correlations of the drawn rate and end with these closed forms (scipy's Spearman correlation, not
    the engine's own); the elapsed time reads no uncertain input, so it has no driver, and its band has
    no width."""
    model = compiled(timer())
    times = [0, 6, 12, 24]
    found = spread.spread(model, 'a', samples=32, seed=5, times=times, jobs=1)
    assert found['status'] == 'completed', found['diagnostics']
    drawn = found['result'].samples['a']['values']
    served = [values['s.rate'] * values['s.end'] for values in drawn]
    outcomes = found['report']['uncertainty']['runs']['a']['outcomes']
    drivers = outcomes[model.outputs['served']]['points']['final']['drivers']
    assert set(drivers) == {'s.rate', 's.end'}
    for name, rho in drivers.items():
        expected = spearmanr([values[name] for values in drawn], served).statistic
        assert rho == pytest.approx(expected, rel=1e-12), name
    elapsed = outcomes[model.outputs['elapsed_time']]
    assert list(elapsed['uncertain_inputs']) == [] and elapsed['points']['final']['drivers'] == {}
    assert [entry['t'] for entry in elapsed['series']] == times
    assert all(entry['p5'] == entry['p95'] == entry['t'] for entry in elapsed['series'])


def compared():
    """The timer with an option group of fixed rates and three runs: run b, at a fixed rate, is the
    comparison of run a, and run c, at a lower fixed rate, stands alone."""
    rates = options(
        'Rate',
        option('Fixed rate', 'A fixed rate.', f's.rate = 2 people/h  {BASIS}'),
        option('Low rate', 'A low rate.', f's.rate = 1 people/h  {BASIS}'),
    )
    return edit(
        timer(),
        replace('runs:\n', f'{rates}\n\nruns:\n'),
        member('runs:', 'b = "Default" + "Fixed rate" versus a', 'c = "Default" + "Low rate"'),
    )


def test_a_spread_samples_the_run_and_its_comparison_on_the_same_draws():
    """Run b is the comparison of run a, and run c stands alone: a spread of a or of b samples both, in
    the order of the file, and a spread of c samples c. Each run reads the same stream of an input: b
    and c draw the end time of each sample as a does. Each sample serves rate * min(t, end) people by
    time t. An unknown run stands alone, and the study rejects it."""
    model = compiled(compared())
    found = {run: spread.spread(model, run, samples=8, seed=5, jobs=1) for run in ('a', 'b', 'c')}
    for run, runs in (('a', ['a', 'b']), ('b', ['a', 'b']), ('c', ['c'])):
        assert found[run]['status'] == 'completed', found[run]['diagnostics']
        assert list(found[run]['report']['runs']) == runs
        assert list(found[run]['report']['uncertainty']['runs']) == runs
    # The spread of the pair is the same whichever run of the pair it is asked for.
    assert json.dumps(found['a']['report'], sort_keys=True) == json.dumps(
        found['b']['report'], sort_keys=True
    )
    samples = {**found['a']['result'].samples, 'c': found['c']['result'].samples['c']}
    ends = {run: [values['s.end'] for values in sampled['values']] for run, sampled in samples.items()}
    assert ends['a'] == ends['b'] == ends['c']
    rates = {run: {values['s.rate'] for values in sampled['values']} for run, sampled in samples.items()}
    assert len(rates['a']) == 8 and len(rates['b']) == len(rates['c']) == 1 and rates['b'] != rates['c']
    served, horizon = model.outputs['served'], model.time['horizon']
    for sampled in samples.values():
        for values, rows in zip(sampled['values'], sampled['rows'], strict=True):
            (row,) = [row for row in rows if row['t'] == horizon]
            closed = values['s.rate'] * min(horizon, values['s.end'])
            assert row['values'][served] == pytest.approx(closed, rel=1e-9, abs=1e-9)
    unknown = spread.spread(model, 'z', samples=8, jobs=1)
    assert unknown['status'] == 'rejected' and 'result' not in unknown
    assert [d['code'] for d in unknown['diagnostics']] == ['run']


def test_a_spread_of_a_list_samples_those_runs_and_no_others():
    """A list of runs samples those runs alone, in the order of the file, whatever the order of the list:
    a spread of [b] samples b without a, the run that b is compared with. Each run reads the same
    streams in every spread, so a run's samples and summaries are the same alone or with others."""
    model = compiled(compared())
    pair = spread.spread(model, 'a', samples=8, seed=5, jobs=1)
    alone = spread.spread(model, ['b'], samples=8, seed=5, jobs=1)
    listed = spread.spread(model, ['c', 'a'], samples=8, seed=5, jobs=1)
    for found in (pair, alone, listed):
        assert found['status'] == 'completed', found['diagnostics']
    assert list(alone['report']['uncertainty']['runs']) == ['b']
    assert list(listed['report']['uncertainty']['runs']) == ['a', 'c']

    def summary(found, run):
        return json.dumps(found['report']['uncertainty']['runs'][run], sort_keys=True)

    assert summary(alone, 'b') == summary(pair, 'b')
    assert summary(listed, 'a') == summary(pair, 'a')
    assert alone['result'].samples['b'] == pair['result'].samples['b']
    assert listed['result'].samples['a'] == pair['result'].samples['a']


def started():
    """The timer with an option group of start values: "Ahead" starts the tally of the served, so it
    changes the structure of a run, not only its values. Run a takes none of the group, and run b
    names "Ahead"."""
    starts = options(
        'Start',
        option('Empty', 'No one is served at the start.'),
        option('Ahead', 'Some people are served at the start.', f's.served = 5 people  {BASIS}'),
    )
    return edit(
        timer(),
        replace('runs:\n', f'{starts}\n\nruns:\n'),
        member('runs:', 'b = "Default" + "Ahead"'),
    )


def test_a_spread_with_options_samples_their_combination_in_every_process(tmp_path, monkeypatch):
    """A spread of run a with the option "Ahead" samples the combination of a with it: in two
    processes, each of which loads the model from the file and makes the combination, as in this
    process, bit for bit. Its samples are those of run b, which names the option, on the same draws.
    Each sample serves rate * min(t, end) people more than the same sample of run a alone, by the
    same number of people in every sample, so a process that sampled run a with its own options
    would fail."""
    path, model = write_scenario(tmp_path, started())
    monkeypatch.setattr(spread, '_POOLS', {})
    with store.use(None):
        try:
            pooled = spread.spread(path, 'a', options=['Ahead'], samples=8, seed=3, jobs=2)
        finally:
            for pool in spread._POOLS.values():
                pool.shutdown()
        alone = spread.spread(model, ['a'], options=('Ahead',), samples=8, seed=3, jobs=1)
        named = spread.spread(model, 'b', samples=8, seed=3, jobs=1)
        own = spread.spread(model, 'a', samples=8, seed=3, jobs=1)
    for found in (pooled, alone, named, own):
        assert found['status'] == 'completed', found['diagnostics']
    assert json.dumps(pooled['report'], sort_keys=True) == json.dumps(alone['report'], sort_keys=True)
    assert pooled['result'].samples == alone['result'].samples
    assert list(pooled['report']['runs']) == ['a']
    assert pooled['report']['runs']['a']['options'] == list(model.runs['b']['options'])
    combined, by_name, plain = (found['result'].samples for found in (pooled, named, own))
    assert combined['a']['values'] == by_name['b']['values'] == plain['a']['values']
    assert combined['a']['rows'] == by_name['b']['rows']
    served, horizon = model.outputs['served'], model.time['horizon']

    def final(rows):
        (row,) = [row for row in rows if row['t'] == horizon]
        return row['values'][served]

    starts = set()
    for values, with_option, without in zip(
        combined['a']['values'], combined['a']['rows'], plain['a']['rows'], strict=True
    ):
        closed = values['s.rate'] * min(horizon, values['s.end'])
        assert final(without) == pytest.approx(closed, rel=1e-9, abs=1e-9)
        starts.add(round(final(with_option) - closed, 9))
    (start,) = starts
    assert start > 0


@pytest.mark.parametrize('jobs', [1, 2])
def test_a_rejected_spread_runs_no_sample(jobs, tmp_path, monkeypatch):
    """Every sample is checked before any sample runs: shares drawn alone break their sum check, so the
    spread is rejected with the diagnostics of its samples, each with the seed and its drawn shares,
    and no sample runs. A pool of threads stands in for the processes."""
    source = system(
        uncertain('w1', 'fraction', 0, 1, 'uniform(0.25, 0.5)'),
        uncertain('w2', 'fraction', 0, 1, 'uniform(0.5, 0.75)'),
        horizon=2,
        checks=(check('abs(s.w1 + s.w2 - 1) <= 1e-12', 'The shares add up to 1.'),),
        outputs=(output('served', 's.w1', 'fraction', 'level'),),
    )
    path, _ = write_scenario(tmp_path, source)
    pool, calls = ThreadPoolExecutor(max_workers=2), []
    monkeypatch.setattr(spread, '_pool', lambda workers: pool)
    monkeypatch.setattr(spread, 'run_sample', no_sample)
    try:
        found = spread.spread(path, 'a', samples=8, seed=4, progress=recorder(calls), jobs=jobs)
    finally:
        pool.shutdown()
    assert found['status'] == 'rejected' and 'result' not in found
    assert found['report']['uncertainty']['runs'] == {}
    assert {phase for phase, _, _ in calls} == {'checking'} and calls[-1] == ('checking', 8, 8)
    failed = [d for d in found['diagnostics'] if 'sample' in d]
    assert sorted({d['sample'] for d in failed}) == list(range(8))
    for item in failed:
        assert (item['run'], item['seed']) == ('a', 4)
        assert abs(item['drawn']['s.w1'] + item['drawn']['s.w2'] - 1) > 1e-12


@pytest.mark.parametrize('jobs', [1, 2])
def test_a_sample_whose_run_fails_rejects_the_spread(jobs, tmp_path, monkeypatch):
    """The run of sample 2 fails, as `run_sample` gives a run that fails its checks: with no counts of
    its outcomes. The spread is rejected with that failure, which names the run, the sample, the seed
    and the drawn values, and it keeps no sample. A pool of threads stands in for the processes."""
    path, _ = write_scenario(tmp_path, timer())
    real, points = spread.run_sample, {}
    failure = {'code': 'initiation', 'severity': 'error', 'message': 'The run of the sample fails'}

    def sample(model, run, point, numerical_settings, times, luck):
        points[luck['sample']] = point
        if luck['sample'] == 2:
            return {'completed': None, 'rows': None, 'failures': [failure]}
        return real(model, run, point, numerical_settings, times, luck)

    pool = ThreadPoolExecutor(max_workers=2)
    monkeypatch.setattr(spread, '_pool', lambda workers: pool)
    monkeypatch.setattr(spread, 'run_sample', sample)
    try:
        found = spread.spread(path, 'a', samples=4, seed=7, jobs=jobs)
    finally:
        pool.shutdown()
    assert found['status'] == 'rejected' and 'result' not in found
    assert found['report']['uncertainty']['runs'] == {}
    (failed,) = [d for d in found['diagnostics'] if d['code'] == failure['code']]
    assert (failed['run'], failed['sample'], failed['seed']) == ('a', 2, 7)
    assert failed['drawn'] == {name: points[2][name] for name in ('s.rate', 's.end')}


@pytest.mark.parametrize('jobs', [1, 2])
def test_a_cancelled_spread_stops_between_samples(jobs, tmp_path, monkeypatch):
    """The cancel event comes while the first sample runs: the spread ends cancelled with no report,
    its progress shows the one finished sample, and no queued sample starts. In a pool, here of one
    thread, the next sample can have started when the event came; in this process, none has."""
    path, model = write_scenario(tmp_path, timer())
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(spread, '_pool', lambda workers: pool)
    cancel, release, ran, calls = threading.Event(), threading.Event(), [], []

    def sample(model, run, point, numerical_settings, times, luck):
        ran.append(luck['sample'])
        if len(ran) == 1:
            cancel.set()
        else:
            release.wait(10)
        return {'completed': None, 'rows': [], 'failures': [], 'events': {}}

    monkeypatch.setattr(spread, 'run_sample', sample)
    try:
        found = spread.spread(
            path, 'a', samples=4, seed=1, progress=recorder(calls), cancel=cancel, jobs=jobs
        )
    finally:
        release.set()
        pool.shutdown()
    assert found == {
        'model_hash': model.model_hash,
        'implementation_hash': model.implementation_hash,
        'diagnostics': [],
        'status': 'cancelled',
    }
    assert calls[-1] == ('running', 1, 4)
    assert ran[0] == 0
    # The one sample that may have started when the event came ends; the queued ones never start.
    if jobs == 1:
        assert len(ran) == 1
    else:
        assert 1 <= len(ran) <= 2


class Reached(Exception):
    """The central study starts."""


def reached(*arguments, **keywords):
    raise Reached


def test_invalid_settings_times_or_jobs_stop_before_the_central_study(monkeypatch):
    """Each setting, time or number of processes that is not valid raises ValueError before the
    central study starts, and so does a pool for a model with no file. The first and the last time of
    the run are valid."""
    model = compiled(timer())
    horizon = model.time['horizon']
    monkeypatch.setattr(spread, 'evaluate_uncertainty', reached)
    with pytest.raises(Reached):
        spread.spread(model, 'a', times=[0, horizon], jobs=1)
    cases = [
        {'samples': 0},
        {'samples': 2.5},
        {'seed': -1},
        {'method': 'halton'},
        {'method': 'sobol', 'samples': 12},
        {'times': horizon},
        {'times': [-1]},
        {'times': [math.nextafter(horizon, math.inf)]},
        {'times': [math.nan]},
        {'times': [True]},
        {'times': ['1']},
        {'jobs': 0},
        {'jobs': True},
        # The processes of a pool load the model from its file, and a model built from a text has none.
        {'jobs': 2},
    ]
    for given in cases:
        with pytest.raises(ValueError):
            spread.spread(model, 'a', **{'jobs': 1, **given})
    # A list of runs names one run or more, each once, by its name.
    for runs in ([], ['a', 'a'], ['a', 3], [''], 3):
        with pytest.raises(ValueError):
            spread.spread(model, runs, jobs=1)


def test_the_options_of_a_spread_name_options_for_one_run(monkeypatch):
    """Options that are not a list of names, or a list of runs with options, raise ValueError before
    the central study starts; an option that the model does not have, or a run that it does not
    have, is the engine's ModelError (`Model.combination`)."""
    model = compiled(started())
    monkeypatch.setattr(spread, 'evaluate_uncertainty', reached)
    with pytest.raises(Reached):
        spread.spread(model, 'a', options=['Ahead'], jobs=1)
    with pytest.raises(Reached):
        spread.spread(model, ['a'], options=(), jobs=1)
    for run, given in (
        ('a', 'Ahead'),
        ('a', ['Ahead', 'Ahead']),
        ('a', [3]),
        ('a', ['']),
        ('a', 3),
        (['a', 'b'], ['Ahead']),
    ):
        with pytest.raises(ValueError):
            spread.spread(model, run, options=given, jobs=1)
    for run, given in (('a', ['Late']), ('z', ['Ahead'])):
        with pytest.raises(ModelError):
            spread.spread(model, run, options=given, jobs=1)


def test_a_process_that_loads_another_revision_stops_the_spread(tmp_path, monkeypatch):
    """The model file changes after this process loaded the model: a process of the pool loads another
    revision, and the spread stops at the first check, before any sample runs; the queued checks never
    load the model. A spread of the file as it is now loads the new revision, in this process and once
    in the pool. A pool of threads stands in for the processes."""
    path, model = write_scenario(tmp_path, timer())
    path.write_text(timer(rate='uniform(1 people/h, 2 people/h)'), encoding='utf-8')
    real_load, real_sample, loads, ran = spread.load_scenario, spread.run_sample, [], []

    def load(*arguments, **keywords):
        loads.append(arguments[0])
        return real_load(*arguments, **keywords)

    def sample(*arguments):
        ran.append(arguments[1])
        return real_sample(*arguments)

    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(spread, '_pool', lambda workers: pool)
    monkeypatch.setattr(spread, 'load_scenario', load)
    monkeypatch.setattr(spread, 'run_sample', sample)
    try:
        with pytest.raises(ValueError, match='another model or implementation revision'):
            spread.spread(model, 'a', samples=4, jobs=2)
        # The thread can start further queued checks before the first failure stops the spread (how
        # many is a matter of timing), but each loads the model once at most and no sample runs. They
        # end before the next task of the one thread, so the counts below are final.
        pool.submit(lambda: None).result()
        assert ran == [] and 1 <= len(loads) <= 4
        loads.clear()
        found = spread.spread(path, 'a', samples=4, jobs=2)
    finally:
        pool.shutdown()
    assert found['status'] == 'completed', found['diagnostics']
    assert found['model_hash'] != model.model_hash
    assert len(loads) == 2 and ran == ['a'] * 4


def _running(pid):
    """Whether a process runs: it exists and has not ended (a zombie waits for its parent to read it)."""
    status = Path(f'/proc/{pid}/stat')
    try:
        return status.read_text().split(') ')[-1].split()[0] != 'Z'
    except OSError:
        return False


@pytest.mark.skipif(not Path('/proc/self/stat').is_file(), reason='reads the states of processes from /proc')
def test_the_sample_processes_end_with_the_process_that_made_them():
    """A process that ends, stopped or killed, takes its sample processes with it: none waits for work
    that can never come."""
    script = (
        'import time\n'
        'from napkin import spread\n'
        'pool = spread._pool(2)\n'
        'list(pool.map(int, [1, 2]))\n'
        'print(*[process.pid for process in pool._processes.values()], flush=True)\n'
        'time.sleep(60)\n'
    )
    owner = subprocess.Popen(
        [sys.executable, '-B', '-c', script], cwd=ROOT, stdout=subprocess.PIPE, text=True
    )
    try:
        pids = [int(pid) for pid in owner.stdout.readline().split()]
        assert len(pids) == 2 and all(_running(pid) for pid in pids)
    finally:
        owner.kill()
        owner.wait()
    deadline = time.monotonic() + 10
    while any(_running(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(_running(pid) for pid in pids)
