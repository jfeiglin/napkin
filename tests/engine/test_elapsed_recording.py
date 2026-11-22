"""Elapsed clocks retain only the committed timestamps present in the saved prefix."""

from dataclasses import replace

from napkin import store
from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.artifact import value_of
from napkin.program.canonical import value_bytes
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.record import ChangeHistory, History, Key, Piece

AMOUNT = Key('meter', ('amount',))
AGE = Key('meter', ('age',))
SOURCE = """scenario "A record of reversible writes"
    horizon 4 h
meter:
    amount: L = 0 L
    other: L = 1 L
    age = formula(elapsed(this.amount))
    restore = event():
        after 0 h:
            this.amount = 0 L
    work = event():
        after 1 h:
            this.amount = 1 L
            this.restore.start()
        after 1 h:
            this.amount = 3 L
        after 1 h:
            this.amount = 4 L
meter.work.start()
"""


def test_the_clock_survives_checkpoint_resume_and_each_budget_cutoff(tmp_path):
    model = compile_text(SOURCE, {'L': {'volume': 1}, 'h': {'time': 1}})
    program = model.program
    config = replace(
        model.configuration, request=replace(model.configuration.request, everything=False, keys=(AGE,))
    )
    stop = Run(Plan.of(program, config), (Breakpoint('meter.work.step[1]'),)).run()
    saved = loads(dumps(stop))
    assert saved.stop.t == 2
    assert saved.record.history(AMOUNT).changes == (0, 1, 1)
    assert read(saved.record, program, [AGE], [1.5, 1, 0.5])[0].values == (0.5, 0, 0.5)

    resumed = Run.restored(Plan.of(program, config), saved).resume()
    with store.use(tmp_path):
        fresh = store.run(program, config)
        hits = store.counts['hits']
        cached = store.run(program, config)
        assert store.counts['hits'] == hits + 1
    assert resumed == fresh == cached == value_of(value_bytes(fresh))
    assert cached.history(AMOUNT).changes == (0, 1, 1, 2, 3)
    for cutoff in (1, 2, 3):
        count = sum(
            piece.t < cutoff for h in fresh.histories if fresh.manifest.names(h.key) for piece in h.pieces
        )
        short = fresh.within(count)
        assert short.end == cutoff
        assert short.history(AMOUNT).changes == tuple(t for t in cached.history(AMOUNT).changes if t < cutoff)
        assert read(short, program, [AGE], [cutoff - 0.5])[0].values == (0.5,)


def test_only_the_elapsed_target_needs_clocks_and_older_plain_histories_still_decode():
    model = compile_text(SOURCE, {'L': {'volume': 1}, 'h': {'time': 1}})
    result = run(model.program, model.configuration)
    assert {h.key for h in result.histories if isinstance(h, ChangeHistory)} == {AMOUNT}
    old = replace(result, histories=tuple(History(h.key, h.pieces) for h in result.histories))
    restored = value_of(value_bytes(old))
    assert restored == old
    # The change from 0 to 3 at 2 h is visible even in a record from before commit times were kept.
    assert read(restored, model.program, [AGE], [2, 2.5])[0].values == (0, 0.5)


def test_older_held_pieces_expose_a_tiny_jump_and_an_unchanged_write():
    model = compile_text(SOURCE, {'L': {'volume': 1}, 'h': {'time': 1}})
    record = run(model.program, model.configuration)
    old_amount = History(AMOUNT, (Piece(0, 0), Piece(1, 0.5e-12), Piece(2, 0.5e-12)))
    old = replace(record, histories=tuple(old_amount if h.key == AMOUNT else h for h in record.histories))
    restored = value_of(value_bytes(old))
    assert read(restored, model.program, [AGE], [2.5, 1.5, 0.5])[0].values == (1.5, 0.5, 0.5)
