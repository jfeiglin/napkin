"""The run store (`napkin/store.py`): a stored record is the fresh record, bit for bit; the key covers
what a run computes from and no label; a stored run serves a request that it covers, cut to it, and a
request for a later horizon or for a value that it lacks runs again; a failure is stored; a run with
edits is stored under its log, which its key digests with the code that plays it; a process waits
for a run that another holds; writes are atomic; the size limit removes the least recently used
files; and a run calls only code of the files that its key digests. The values are worked by hand:
the tank fills at its median rate, 2 L/h, so it holds 2 L for each hour; the dispatch of change 15
(`examples.pump_dispatch`) waits once unattended, and sends its one spare when its order is edited
to SEND."""

from __future__ import annotations

import multiprocessing
import os
import sys
import textwrap
import threading
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from napkin import store
from napkin.engine import read
from napkin.engine.timeline import run as fresh
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, CheckpointError
from napkin.program.config import SAMPLED, Configuration, Request
from napkin.program.record import Entry, Key, Manifest, Record, Unavailable
from napkin.session import Session, play
from tests.program.examples import DISPATCH, DISPATCH_SWITCH, EXAMPLES, UNITS, pump_dispatch

TANK = textwrap.dedent("""\
    scenario "Tank"
        horizon 4 h
    tank:
        input rate: L/h = uniform(1 L/h, 3 L/h).draw()  @measured
            "Inflow"
        water: L = 0 L in [0 L,]
            "Water in the tank"
        level = formula(this.water / 8 L)
        flow fill: SOURCE -> this.water
            request = this.rate
    record measured: source "A gauge reading."
    """)
WATER, LEVEL = Key('tank', ('water',)), Key('tank', ('level',))


def tank(text=TANK):
    return compile_text(text, UNITS)


def counted(work):
    """The result of `work()` and the store's hits and misses while it ran."""
    before = dict(store.counts)
    found = work()
    return found, {name: store.counts[name] - before[name] for name in before}


def water(record, model, times):
    return read(record, model.program, ['tank.water'], times)[0].values


def sampled(model, seed):
    return replace(model.configuration, mode=SAMPLED, seed=seed)


ONE_HOUR = Configuration(Request(1))


def dispatch_log(order='SEND'):
    """The dispatch and the log of a session stopped before its switch, its order edited to `order`."""
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [Breakpoint(DISPATCH_SWITCH, DISPATCH)])
    session.advance()
    session.edit(f'{DISPATCH}.order', order)
    return program, session.log


def sent(record, program):
    return read(record, program, ['sent'], [1])[0].values[0]


def test_a_stored_record_is_the_fresh_record_bit_for_bit(tmp_path):
    model = tank()
    alone = fresh(model.program, model.configuration)
    with store.use(tmp_path):
        cold, first = counted(lambda: store.run(model.program, model.configuration))
        warm, second = counted(lambda: store.run(model.program, model.configuration))
    assert first == {'hits': 0, 'misses': 1} and second == {'hits': 1, 'misses': 0}
    assert store.fingerprint(warm) == store.fingerprint(cold) == store.fingerprint(alone)
    assert warm == alone and water(warm, model, [4]) == pytest.approx((8,))


def test_a_label_edit_reuses_a_stored_run(tmp_path):
    """A label is no part of the program: the edited model's run is the stored one."""
    model = tank()
    edited = tank(TANK.replace('"Water in the tank"', '"Water held in the tank"'))
    assert edited.declared != model.declared and edited.program == model.program
    with store.use(tmp_path):
        store.run(model.program, model.configuration)
        again, used = counted(lambda: store.run(edited.program, edited.configuration))
    assert used == {'hits': 1, 'misses': 0} and water(again, edited, [2]) == pytest.approx((4,))


def test_another_seed_runs_again(tmp_path):
    model = tank()
    with store.use(tmp_path):
        first = store.run(model.program, sampled(model, 1))
        other, used = counted(lambda: store.run(model.program, sampled(model, 2)))
        _, again = counted(lambda: store.run(model.program, sampled(model, 1)))
    assert used == {'hits': 0, 'misses': 1} and again == {'hits': 1, 'misses': 0}
    # Two seeds draw two rates; each run holds its own rate times 4 h.
    rates = [record.entries('draw')[0].detail('value') for record in (first, other)]
    assert rates[0] != rates[1]
    assert [water(record, model, [4])[0] for record in (first, other)] == pytest.approx(
        [4 * r for r in rates]
    )


def test_a_window_that_the_stored_run_lacks_runs_again(tmp_path):
    """A stored run to 4 h serves no request to 6 h; the run to 6 h takes the entry's place and then
    serves the request to 4 h too."""
    model = tank()
    to_six = replace(model.configuration, request=Request(6))
    with store.use(tmp_path):
        store.run(model.program, model.configuration)
        longer, used = counted(lambda: store.run(model.program, to_six))
        shorter, again = counted(lambda: store.run(model.program, model.configuration))
    assert used == {'hits': 0, 'misses': 1} and again == {'hits': 1, 'misses': 0}
    assert water(longer, model, [6]) == pytest.approx((12,))
    assert shorter.manifest == Manifest(4) and water(shorter, model, [4]) == pytest.approx((8,))
    # The cut answers as a run to 4 h would: nothing at 5 h, though the entry holds the run to 6 h.
    assert water(shorter, model, [5]) == (
        Unavailable('the record holds no value at 5 h: it reaches to its horizon, 4 h'),
    )


def test_a_value_that_the_stored_run_lacks_runs_again_and_the_entry_then_holds_both(tmp_path):
    model = tank()

    def asking(*keys):
        return replace(model.configuration, request=Request(4, everything=False, keys=keys))

    with store.use(tmp_path):
        store.run(model.program, asking(WATER))
        level, used = counted(lambda: store.run(model.program, asking(LEVEL)))
        _, again = counted(lambda: store.run(model.program, asking(WATER)))
        _, whole = counted(lambda: store.run(model.program, model.configuration))
    assert used == {'hits': 0, 'misses': 1} and again == {'hits': 1, 'misses': 0}
    assert whole == {'hits': 0, 'misses': 1}  # every value is more than the two
    assert level.manifest == Manifest(4, everything=False, keys=(LEVEL,))
    assert read(level, model.program, ['tank.level'], [4])[0].values == pytest.approx((1,))
    (unheld,) = water(level, model, [4])
    assert unheld == Unavailable(
        'the record holds no value of tank.water: the request of its run names other values'
    )


def test_a_shorter_request_reads_the_stored_run_up_to_its_horizon_and_nothing_after(tmp_path):
    """An event at 3 h adds 5 L: a request to 2 h gets no entry of it, and its values are those of a
    run to 2 h."""
    model = tank(
        TANK.replace(
            '    flow fill:',
            '    top_up = event():\n        after 3 h:\n            this.water += 5 L\n    flow fill:',
        )
        + 'tank.top_up.start()\n'
    )
    to_two = replace(model.configuration, request=Request(2))
    with store.use(tmp_path):
        stored = store.run(model.program, model.configuration)
        cut = store.run(model.program, to_two)
    alone = fresh(model.program, to_two)
    assert water(stored, model, [4]) == pytest.approx((13,))
    assert [entry.t for entry in stored.entries('commit')] == [3] and cut.entries('commit') == ()
    assert cut.manifest == alone.manifest == Manifest(2)
    assert water(cut, model, [0, 1, 2]) == pytest.approx(water(alone, model, [0, 1, 2]), rel=1e-12)


def test_a_failure_is_stored(tmp_path):
    """The median rate, 2 L/h, breaks the assertion at the start: the stored run fails the same way."""
    failing = tank(TANK + 'assert tank.rate <= 1.5 L/h\n')
    with store.use(tmp_path):
        failed, first = counted(lambda: store.run(failing.program, failing.configuration))
        again, second = counted(lambda: store.run(failing.program, failing.configuration))
    assert failed.failure is not None and failed.failure.t == 0
    assert first == {'hits': 0, 'misses': 1} and second == {'hits': 1, 'misses': 0} and again == failed


def test_a_run_with_edits_is_stored_under_its_log_and_a_log_without_edits_is_the_plain_run(tmp_path):
    """Edited to SEND, the dispatch sends one pump; unattended it sends none. The run of the log is
    the session's run, bit for bit, and its entry keeps the log."""
    program, log = dispatch_log()
    with store.use(tmp_path):
        edited, first = counted(lambda: store.run(program, ONE_HOUR, log))
        again, second = counted(lambda: store.run(program, ONE_HOUR, log))
        plain, third = counted(lambda: store.run(program, ONE_HOUR))
        untouched, fourth = counted(lambda: store.run(program, ONE_HOUR, replace(log, edits=())))
    assert first == third == {'hits': 0, 'misses': 1} and second == fourth == {'hits': 1, 'misses': 0}
    assert (
        store.fingerprint(again)
        == store.fingerprint(edited)
        == store.fingerprint(play(program, ONE_HOUR, log))
    )
    assert (sent(edited, program), sent(plain, program)) == (1, 0) and untouched == plain
    entry = store._stored(tmp_path, store.key(program, ONE_HOUR, log))
    assert entry['log'] == log and entry['engine'] == store.SESSION_DIGEST
    assert store._stored(tmp_path, store.key(program, ONE_HOUR))['log'] is None


def test_the_key_of_a_log_covers_its_breakpoints_its_edits_and_the_code_that_plays_it(monkeypatch):
    """The session's code imports the engine's, so its digest covers both. The stops of a log are what
    the run gives again, and no part of the key."""
    program, log = dispatch_log()
    base = store.key(program, ONE_HOUR, log)
    assert store.key(program, ONE_HOUR, replace(log, stops=())) == base
    changed = [
        store.key(program, ONE_HOUR, dispatch_log('WAIT')[1]),
        store.key(program, ONE_HOUR, replace(log, breakpoints=(Breakpoint(DISPATCH_SWITCH),))),
        store.key(program, Configuration(Request(1), mode=SAMPLED, seed=3), log),
        store.key(program, ONE_HOUR),
    ]
    monkeypatch.setattr(store, 'SESSION_DIGEST', '0' * 64)
    changed.append(store.key(program, ONE_HOUR, log))
    assert len({base, *changed}) == 1 + len(changed)
    assert set(store.closure(store.ENGINE_STARTS)) < set(store.closure(store.SESSION_STARTS))


def test_a_log_that_does_not_play_again_stores_nothing(tmp_path):
    program, log = dispatch_log()
    moved = replace(log, stops=(replace(log.stops[0], t=0.5),))
    with store.use(tmp_path), pytest.raises(CheckpointError, match='does not play again'):
        store.run(program, ONE_HOUR, moved)
    assert not list(tmp_path.glob('??/*.run'))


def test_verify_plays_a_stored_log_again(tmp_path, capsys):
    program, log = dispatch_log()
    with store.use(tmp_path):
        store.run(program, ONE_HOUR, log)
    assert store.verify(tmp_path, 1) == []
    (path,) = tmp_path.glob('??/*.run')
    entry = store._read(path)
    entry['log'] = dispatch_log('WAIT')[1]
    store._write(path, entry)
    assert store.verify(tmp_path, 1) == [path]
    assert '1 stored runs run again, 1 differ' in capsys.readouterr().out


def test_what_a_run_computes_from_is_in_its_key_and_no_label_is(monkeypatch):
    model = tank()
    base = store.key(model.program, model.configuration)
    labelled = tank(TANK.replace('"Inflow"', '"The inflow"'))
    assert store.key(labelled.program, labelled.configuration) == base
    changed = [
        store.key(tank(TANK.replace('3 L/h).draw()', '4 L/h).draw()')).program, model.configuration),
        store.key(model.program, sampled(model, 0)),
    ]
    monkeypatch.setattr(store, 'ENGINE_DIGEST', '0' * 64)
    changed.append(store.key(model.program, model.configuration))
    monkeypatch.undo()
    monkeypatch.setattr(store, '_ENVIRONMENT_BYTES', b'another computer')
    changed.append(store.key(model.program, model.configuration))
    assert len({base, *changed}) == 1 + len(changed)


def test_a_process_waits_for_a_run_that_another_holds_and_reads_it(tmp_path):
    """Another process holds the key's lock and stores the run meanwhile: this one waits, then reads it."""
    model = tank()
    run_key = store.key(model.program, model.configuration)
    found = []

    def ask():
        found.append(counted(lambda: store.run(model.program, model.configuration)))

    with store.use(tmp_path):
        record = fresh(model.program, model.configuration)
        with store._locked(tmp_path, run_key):
            waiting = threading.Thread(target=ask)
            waiting.start()
            waiting.join(0.3)
            assert waiting.is_alive()
            store._save(tmp_path, run_key, model.program, model.configuration, record)
        waiting.join()
    ((again, used),) = found
    assert used == {'hits': 1, 'misses': 0} and again == record


def test_a_write_is_atomic_and_a_damaged_entry_runs_again(tmp_path):
    model = tank()
    with store.use(tmp_path):
        store.run(model.program, model.configuration)
        (entry,) = tmp_path.glob('??/*.run')
        assert not list(tmp_path.rglob('*.tmp'))
        entry.write_bytes(entry.read_bytes()[:40])
        _, used = counted(lambda: store.run(model.program, model.configuration))
        _, again = counted(lambda: store.run(model.program, model.configuration))
    assert used == {'hits': 0, 'misses': 1} and again == {'hits': 1, 'misses': 0}


def test_the_size_limit_removes_the_least_recently_used_files(tmp_path, monkeypatch):
    """Two entries and their program, the first used least recently; a limit that a third entry passes
    and that leaves room for the rest once the first is gone."""
    model = tank()
    with store.use(tmp_path):
        for seed in (0, 1):
            store.run(model.program, sampled(model, seed))
    first, second = sorted(tmp_path.glob('??/*.run'), key=lambda path: path.stat().st_mtime_ns)
    (program,) = tmp_path.glob('programs/*.program')
    for age, path in enumerate((first, second, program)):
        os.utime(path, (1_000_000 + age, 1_000_000 + age))
    sizes = [path.stat().st_size for path in (first, second, program)]
    monkeypatch.setenv('NAPKIN_STORE_LIMIT', str(1.02 * sum(sizes) / 0.9 / 1e9))
    with store.use(tmp_path):
        store.run(model.program, sampled(model, 2))
    remaining = set(tmp_path.glob('??/*.run'))
    assert len(remaining) == 2 and first not in remaining and second in remaining and program.is_file()


def test_verify_runs_stored_runs_again_and_finds_one_that_differs(tmp_path, capsys):
    model = tank()
    with store.use(tmp_path):
        for seed in (1, 2):
            store.run(model.program, sampled(model, seed))
    assert store.verify(tmp_path, 2) == []
    path = sorted(tmp_path.glob('??/*.run'))[0]
    entry = store._read(path)
    entry['record'] = replace(entry['record'], trace=())
    store._write(path, entry)
    assert store.verify(tmp_path, 2) == [path]
    assert '2 stored runs run again, 1 differ' in capsys.readouterr().out


def test_the_processes_of_a_pool_use_the_store_of_their_parent(tmp_path):
    with store.use(tmp_path):
        options = store.pool_options()
    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context('spawn'), **options) as pool:
        assert pool.submit(store.current).result() == tmp_path


def test_a_run_calls_only_code_of_the_files_that_its_key_digests():
    """Each package function that a run calls is defined in a file of the engine's import closure, so
    a change to any code that a run runs changes every key. The worked examples of the spec run every
    construct that the engine runs."""
    examples = [make() for make in EXAMPLES.values()]
    called = set()

    def profile(frame, event, argument):
        if event == 'call':
            called.add(frame.f_code.co_filename)

    sys.setprofile(profile)
    try:
        for example in examples:
            fresh(example.program, example.configuration)
    finally:
        sys.setprofile(None)
    files = {Path(name).resolve() for name in called}
    package = {path for path in files if path.is_relative_to(store.PACKAGE)}
    assert package and package <= set(store.closure()), sorted(package - set(store.closure()))


def test_the_run_of_a_log_calls_only_code_of_the_files_that_its_key_digests():
    """A log played through the session and the engine's checkpoints runs code of the session's
    closure only."""
    program, log = dispatch_log()
    called = set()

    def profile(frame, event, argument):
        if event == 'call':
            called.add(frame.f_code.co_filename)

    sys.setprofile(profile)
    try:
        play(program, ONE_HOUR, log)
    finally:
        sys.setprofile(None)
    files = {Path(name).resolve() for name in called}
    package = {path for path in files if path.is_relative_to(store.PACKAGE)}
    closure = set(store.closure(store.SESSION_STARTS))
    assert package and package <= closure, sorted(package - closure)


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
    monkeypatch.setattr(store, 'source_checkout', lambda: None)
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    assert store.default_directory() == tmp_path / 'cache' / 'napkin' / 'runs'


def test_a_fingerprint_reads_a_record_and_nothing_else():
    record = Record(Manifest(1), (), (Entry(0.5, 1, 'fire', 'tank.when[0]', 'tank'),))
    assert store.fingerprint(record) == store.fingerprint(replace(record))
    assert store.fingerprint(record) != store.fingerprint(replace(record, trace=()))
    with pytest.raises(TypeError):
        store.fingerprint(object())


# ---- the budget of pieces (the re-audit's row 18) ------------------------------------------------


def test_a_request_with_a_budget_is_cut_from_the_stored_run_as_a_fresh_run_would_be(tmp_path):
    """The whole run is stored; a request of it within two pieces is a hit, cut where a fresh run of
    that request ends, with the same failure that names the budget."""
    model = tank()
    small = replace(model.configuration, request=Request(4, pieces=2))
    with store.use(tmp_path):
        store.run(model.program, model.configuration)
        cut, used = counted(lambda: store.run(model.program, small))
    alone = fresh(model.program, small)
    assert used == {'hits': 1, 'misses': 0}
    assert cut.end == alone.end and cut.failure == alone.failure and cut.failure.detail('budget') == 2


def test_a_record_that_its_budget_cuts_is_not_stored_and_a_wider_cut_run_gives_way_to_the_request(tmp_path):
    """A record that its budget cuts is not stored: the same request misses again. The stored run of
    the water serves no request of the level; the run of both would not fit the level's budget, so the
    level runs alone, holds its whole run, and the entry of the water stays."""
    model = tank()

    def asking(*keys, pieces=10_000_000):
        return replace(model.configuration, request=Request(4, everything=False, keys=keys, pieces=pieces))

    with store.use(tmp_path):
        first, one = counted(lambda: store.run(model.program, asking(WATER, pieces=1)))
        _, two = counted(lambda: store.run(model.program, asking(WATER, pieces=1)))
        assert one == two == {'hits': 0, 'misses': 1} and first.failure.detail('budget') == 1
        store.run(model.program, asking(WATER))
        level = fresh(model.program, asking(LEVEL))
        budget = sum(len(history.pieces) for history in level.histories if level.manifest.names(history.key))
        found, used = counted(lambda: store.run(model.program, asking(LEVEL, pieces=budget)))
        _, water_again = counted(lambda: store.run(model.program, asking(WATER)))
    assert used == {'hits': 0, 'misses': 1} and found.failure is None and found.end == 4
    assert water_again == {'hits': 1, 'misses': 0}
