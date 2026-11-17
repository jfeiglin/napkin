"""The run store (`napkin/store.py`): a stored run is the fresh run, bit for bit; each input
of a simulation is in its key; an edit simulates again only the runs that it changes; processes share
the runs of a study; writes are atomic; the size limit removes the least recently used runs; and a
simulation calls only code of the files that the key digests."""

import copy
import multiprocessing
import os
import pickle
import sys
import threading
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from napkin import store
from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.engine.runtime import NumericalSettings, simulate
from napkin.model.ir import thaw
from napkin.model.structure import Resolved
from tests import processes
from tests.acceptance.helpers import LIBRARY, model_of
from tests.build import compiled, play_scenario, scenario


@pytest.fixture
def model():
    """Two runs: `a` with the defaults, `b` with the profile Half rate."""
    return compiled(scenario())


def fingerprints(study):
    return {run: store.fingerprint(item['trajectory']) for run, item in study.runs.items()}


def counted(evaluate):
    """The result of `evaluate()` and the store's hits and misses while it ran."""
    before = dict(store.counts)
    result = evaluate()
    return result, {name: store.counts[name] - before[name] for name in before}


def fake(rs, library, settings):
    """A stand-in simulation for the store's own mechanics: it gives back its run."""
    return {'run': rs['run']}


def item(run):
    return ({'run': run}, {'units': {}}, None)


def test_a_stored_run_is_the_fresh_run_bit_for_bit(model, tmp_path):
    with store.use(None):
        fresh = evaluate_study(model)
    with store.use(tmp_path):
        cold, first = counted(lambda: evaluate_study(model))
        warm, second = counted(lambda: evaluate_study(model))
    assert first == {'hits': 0, 'misses': 2, 'unkeyed': 0}
    assert second == {'hits': 2, 'misses': 0, 'unkeyed': 0}
    assert fingerprints(cold) == fingerprints(warm) == fingerprints(fresh)
    assert store.fingerprint(sample_result(warm)) == store.fingerprint(sample_result(fresh))
    assert warm.diagnostics == fresh.diagnostics and warm.admissible and fresh.admissible


def test_an_edit_simulates_again_only_the_runs_that_it_changes(model, tmp_path):
    """The profile Half rate is in run `b` only: an edit of it leaves run `a` in the store."""
    edits = edits_for(model, {'options': {'Half rate': {'service.rate': 6}}})
    with store.use(tmp_path):
        counted(lambda: evaluate_study(model))
        edited, used = counted(lambda: evaluate_study(model, edits))
    assert edited.admissible and used == {'hits': 1, 'misses': 1, 'unkeyed': 0}
    with store.use(None):
        assert fingerprints(edited) == fingerprints(evaluate_study(model, edits))


def test_each_input_of_a_simulation_is_in_its_key(model, monkeypatch):
    rs, library = model.resolve('a'), thaw(model.library)
    base = store.key(rs, library)
    # The same inputs: the typed run or the plain data that it writes, and no settings or the
    # default ones.
    assert store.key(rs.plain(), library) == base
    assert store.key(rs, library, {}) == store.key(rs, library, NumericalSettings()) == base
    # A library's other parts are not inputs of a simulation.
    other = copy.deepcopy(library)
    other['claims'] = [{'id': 'another'}]
    assert store.key(rs, other) == base
    # Each input of a simulation changes the key.
    unit = next(iter(library['units']))
    units = copy.deepcopy(library)
    units['units'][unit]['scale'] = units['units'][unit]['scale'] * 2
    changed = {
        'run': store.key(model.resolve('b'), library),
        'value': store.key(model.resolve('a', {'service.end': 6}), library),
        'units': store.key(rs, units),
        'settings': store.key(rs, library, {'rtol': 1e-8}),
        # What a played run asks: who picks, and the picks.
        'control': store.key(rs, library, None, {'control': {'service': 'reader'}, 'picks': []}),
        'picks': store.key(
            rs, library, None, {'control': {'service': 'reader'}, 'picks': [{'event': 'e', 'outcome': 'o'}]}
        ),
    }
    monkeypatch.setattr(store, 'ENGINE_DIGEST', '0' * 64)
    changed['engine'] = store.key(rs, library)
    monkeypatch.undo()
    monkeypatch.setattr(store, '_ENVIRONMENT_BYTES', b'another computer')
    changed['environment'] = store.key(rs, library)
    assert len(set(changed.values()) | {base}) == len(changed) + 1, changed


# A quantity whose upper bound reads an input: each run has the number of the bound for its values.
BOUND = (
    'var served: people = 0 size 10 people  @fixture',
    'var served: people = 0 in 0 people to 4 * n size 10 people  @fixture',
)


def test_the_key_of_typed_parts_is_the_key_of_the_plain_data_that_they_write():
    """The store keys a resolved run as typed parts by the plain data that the parts write, piece
    by piece: the parts that the runs of a structure share, and what each run has of its own. For
    two runs, a run with other values (which give its bound another number) and a run with the
    luck of a sample, the key is the key of that plain data as one mapping, and each run has a key
    of its own. A run that is read again from the plain data, whose parts are other objects, has
    the same key."""
    text = scenario()
    assert text.count(BOUND[0]) == 1
    model = compiled(text.replace(*BOUND))
    library = thaw(model.library)
    first = model.resolve('a')
    runs = [
        first,
        model.resolve('b'),
        model.resolve('a', {'service.n': 20}),
        first.adding(luck={'seed': 3, 'sample': 7}),
    ]
    assert runs[0].quantities['service.served'].maximum != runs[2].quantities['service.served'].maximum
    keys = [store.key(rs, library) for rs in runs]
    assert len(set(keys)) == len(runs)
    for rs, found in zip(runs, keys):
        written = rs.plain()
        assert store.key(written, library) == found
        assert store.key(Resolved.of(written), library) == found
        # The same run again: the pieces that the store kept give the same key.
        assert store.key(rs, library) == found


def played(rs, library, settings, play=None):
    """A stand-in simulation that gives back its run and what the run was asked."""
    return {'run': rs['run'], 'play': play}


def test_what_a_played_run_asks_goes_to_its_simulation_and_into_its_key(tmp_path):
    """An item of a played run has a fourth part: who picks, and the picks. The simulation gets it
    as `play`; an item with no such part is simulated with no `play`. With a store, each play of one
    run is its own entry, and the same play is read from the store."""
    first = {'control': {'actor': 'reader'}, 'picks': []}
    second = {'control': {'actor': 'reader'}, 'picks': [{'event': 'actor.decide', 'outcome': 'yes'}]}
    items = [item('a'), (*item('a'), first), (*item('a'), second)]
    asked = [None, first, second]
    assert [found['play'] for found in store.simulate_all(played, items)] == asked
    with store.use(tmp_path):
        results, used = counted(lambda: store.simulate_all(played, items))
        assert [found['play'] for found in results] == asked
        assert used == {'hits': 0, 'misses': 3, 'unkeyed': 0}
        results, used = counted(lambda: store.simulate_all(played, items))
        assert [found['play'] for found in results] == asked
        assert used == {'hits': 3, 'misses': 0, 'unkeyed': 0}
    assert len(list(tmp_path.glob('??/*.run'))) == 3


def test_a_key_holds_only_plain_data():
    with pytest.raises(TypeError):
        store.canonical({'value': object()})


def test_a_stored_simulation_reads_only_the_units_of_the_library(tmp_path):
    def reads_claims(rs, library, settings):
        return library['claims']

    with store.use(tmp_path), pytest.raises(KeyError, match='only the library units'):
        store.simulate(reads_claims, *item('a'))


def test_a_process_simulates_a_free_run_while_another_holds_a_run(tmp_path):
    """Another process holds the first run: this one simulates the second, then waits for the first.
    The holder ends without storing it, so this one simulates it too."""
    computed = []

    def compute(rs, library, settings):
        computed.append(rs['run'])
        return fake(rs, library, settings)

    held = store._try_lock(tmp_path, store.key(*item('held')))
    release = threading.Timer(0.3, store._unlock, (held,))
    release.start()
    with store.use(tmp_path):
        results = store.simulate_all(compute, [item('held'), item('free')])
    release.join()
    assert computed == ['free', 'held']
    assert results == [{'run': 'held'}, {'run': 'free'}]


def test_a_run_that_another_process_stores_is_read_not_simulated(tmp_path):
    computed = []

    def compute(rs, library, settings):
        computed.append(rs['run'])
        return fake(rs, library, settings)

    run_key = store.key(*item('held'))
    held = store._try_lock(tmp_path, run_key)

    def finish():
        store._save(tmp_path, run_key, item('held'), {'run': 'held'})
        store._unlock(held)

    holder = threading.Timer(0.3, finish)
    holder.start()
    with store.use(tmp_path):
        results = store.simulate_all(compute, [item('held')])
    holder.join()
    assert computed == [] and results == [{'run': 'held'}]


def test_a_write_is_atomic_and_a_damaged_run_is_simulated_again(tmp_path):
    with store.use(tmp_path):
        store.simulate_all(fake, [item('a')])
        (entry,) = tmp_path.glob('??/*.run')
        assert not list(tmp_path.glob('??/*.tmp'))
        entry.write_bytes(entry.read_bytes()[:20])
        _, used = counted(lambda: store.simulate_all(fake, [item('a')]))
        assert used['misses'] == 1
        _, used = counted(lambda: store.simulate_all(fake, [item('a')]))
        assert used['hits'] == 1


def test_a_failure_is_never_stored(tmp_path):
    class Failure(Exception):
        pass

    def fails(rs, library, settings):
        raise Failure('no result')

    with store.use(tmp_path):
        (outcome,) = store.simulate_all(fails, [item('a')], (Failure,))
    assert isinstance(outcome, Failure) and not list(tmp_path.glob('??/*.run'))


def test_the_size_limit_removes_the_least_recently_used_runs(tmp_path, monkeypatch):
    with store.use(tmp_path):
        store.simulate_all(fake, [item('first'), item('second')])
    entries = {path: path.stat().st_size for path in tmp_path.glob('??/*.run')}
    for age, path in enumerate(sorted(entries, key=lambda path: path.name)):
        os.utime(path, (1_000_000 + age, 1_000_000 + age))
    oldest = min(entries, key=lambda path: path.stat().st_mtime)
    # Room for two runs and a half: the third run removes the one least recently used.
    monkeypatch.setenv('NAPKIN_STORE_LIMIT', str(2.5 * max(entries.values()) / 1e9))
    with store.use(tmp_path):
        store.simulate_all(fake, [item('third')])
    remaining = set(tmp_path.glob('??/*.run'))
    assert len(remaining) == 2 and oldest not in remaining


def test_verify_finds_a_stored_run_that_differs_from_a_fresh_one(model, tmp_path):
    with store.use(tmp_path):
        evaluate_study(model)
    assert store.verify(tmp_path, 2) == []
    path = sorted(tmp_path.glob('??/*.run'))[0]
    entry = store._read(path)
    entry['trajectory'].trace.append({'rule': 'never'})
    data = pickle.dumps(entry, protocol=pickle.HIGHEST_PROTOCOL)
    path.write_bytes(store.MAGIC + zlib.compress(data, 1))
    assert store.verify(tmp_path, 2) == [path]


def test_verify_simulates_a_played_run_with_what_it_was_asked(tmp_path):
    """A played run that is stored has what it was asked beside its inputs: the check of the store
    simulates it again with the same picks, so it finds no difference. The picks change the run: the
    stored run of the same model that nobody plays is another entry."""
    played_model = compiled(play_scenario())
    with store.use(tmp_path):
        free = evaluate_study(played_model)
        waits = evaluate_study(played_model, play={'run': 'a', 'control': {'guard': 'reader'}, 'picks': []})
        event = waits.decision['event']
        outcome = waits.decision['outcomes'][-1]['name']
        study = evaluate_study(
            played_model,
            play={
                'run': 'a',
                'control': {'guard': 'reader'},
                'picks': [{'event': event, 'outcome': outcome}],
            },
        )
    assert free.admissible and study.admissible, (free.diagnostics, study.diagnostics)
    assert len(list(tmp_path.glob('??/*.run'))) == 3
    assert store.verify(tmp_path, 3) == []


def test_worker_processes_use_the_store_of_their_parent(tmp_path):
    with store.use(tmp_path):
        options = store.pool_options(helpers=2)
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(1, mp_context=context, **options) as pool:
        assert pool.submit(store.current).result() == tmp_path
        assert pool.submit(store.helpers).result() == (2 if store.fcntl is not None else 0)


def slow(name, **extra):
    return ({'run': name, 'seconds': 1.5, **extra}, {'units': {}}, None)


@pytest.mark.skipif(store.fcntl is None, reason='helpers need file locks')
def test_helpers_simulate_the_missing_runs_of_a_list_beside_the_process(tmp_path):
    """Four runs of 1.5 s, three helpers: the helpers take runs while this process simulates the
    first, each run is simulated once, and every one counts as simulated."""
    with store.use(tmp_path):
        store.activate(tmp_path, helpers=3)
        results, used = counted(lambda: store.simulate_all(processes.slow_run, [slow(n) for n in 'abcd']))
    assert [result['run'] for result in results] == list('abcd')
    assert len({result['process'] for result in results}) > 1
    assert used == {'hits': 0, 'misses': 4, 'unkeyed': 0}
    assert len(list(tmp_path.glob('??/*.run'))) == 4


@pytest.mark.skipif(store.fcntl is None, reason='helpers need file locks')
def test_a_run_that_fails_in_a_helper_fails_in_the_process_that_needs_it(tmp_path):
    """A helper does not store a failure, so this process simulates the run again and reports it."""
    with store.use(tmp_path):
        store.activate(tmp_path, helpers=2)
        results = store.simulate_all(
            processes.slow_run, [slow('a'), slow('b', fails=True), slow('c')], (processes.Failure,)
        )
    assert results[0]['run'] == 'a' and results[2]['run'] == 'c'
    assert isinstance(results[1], processes.Failure) and str(results[1]) == 'b fails'
    assert len(list(tmp_path.glob('??/*.run'))) == 2


@pytest.mark.parametrize('name', ['scenario', 'F5'])
def test_a_simulation_calls_only_code_of_the_files_that_its_key_digests(name):
    """Each package function that a simulation calls is defined in a file of the engine's import
    closure, so a change to any code that a simulation runs changes every key. The acceptance fixture
    F5 has every construct of the language once; each of its runs is simulated."""
    if name == 'scenario':
        model, library = compiled(scenario()), None
    else:
        model, library = model_of(name), thaw(LIBRARY)
    structures = [model.resolve(run) for run in model.runs]
    called = set()

    def profile(frame, event, argument):
        if event == 'call':
            called.add(frame.f_code.co_filename)

    sys.setprofile(profile)
    try:
        for rs in structures:
            simulate(rs, library or thaw(model.library))
    finally:
        sys.setprofile(None)
    files = {Path(filename).resolve() for filename in called}
    package = {path for path in files if path.is_relative_to(store.PACKAGE)}
    assert package and package <= set(store.closure()), sorted(package - set(store.closure()))


def test_the_store_folder_follows_its_settings(monkeypatch, tmp_path):
    """`NAPKIN_STORE` turns the store off or names its folder. Without it, a checkout keeps its runs in
    `.cache/runs`, and an installed package under the user's cache folder (`XDG_CACHE_HOME`)."""
    monkeypatch.setenv('NAPKIN_STORE', 'off')
    assert store.default_directory() is None
    monkeypatch.setenv('NAPKIN_STORE', str(tmp_path / 'elsewhere'))
    assert store.default_directory() == tmp_path / 'elsewhere'
    monkeypatch.delenv('NAPKIN_STORE')
    assert store.default_directory() == store.source_checkout() / '.cache' / 'runs'
    assert store.source_checkout() == store.PACKAGE.parent
    # An installed package has no checkout around it.
    monkeypatch.setattr(store, 'source_checkout', lambda: None)
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    assert store.default_directory() == tmp_path / 'cache' / 'napkin' / 'runs'
