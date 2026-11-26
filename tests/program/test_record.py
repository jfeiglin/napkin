"""The record of a run (`napkin/program/record.py`): histories of pieces, the trace, the manifest.

A history is read at any time from its pieces, exactly when its numbers are exact. The cases are the
spec's: the tank of 8 L that a delivery of 3 L/h empties at 2 h 40 min, and the 20 g that one stage
sets to 8 g and a later stage of the same round raises to 12 g.
"""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.program.checkpoint import decode, encode
from napkin.program.record import (
    BalancePoint,
    ChangeHistory,
    Curve,
    Entry,
    History,
    Key,
    Manifest,
    Piece,
    Record,
    Unavailable,
)

WATER = Key('tank', ('water',))


def test_a_history_reads_its_pieces_at_any_time():
    """The tank: `8 - 3 t` until 8/3 h, then 0."""
    history = History(WATER, (Piece(0, Fraction(8), Fraction(-3)), Piece(Fraction(8, 3), Fraction(0))))
    assert history.at(0) == 8
    assert history.at(2) == 2
    assert history.at(Fraction(5, 2)) == Fraction(1, 2)
    assert history.at(Fraction(8, 3)) == 0
    assert history.at(10) == 0
    with pytest.raises(LookupError):
        history.at(-1)


def test_a_jump_is_a_piece_at_the_same_time():
    """20 g; at 1 h one stage sets 8 g and a later one of the same round adds 4 g: a read at 1 h
    sees what the last round committed."""
    history = History(Key('jar', ('amount',)), (Piece(0, 20), Piece(1, 8), Piece(1, 12)))
    assert history.at(Fraction(1, 2)) == 20
    assert history.at(1) == 12
    assert history.at(2) == 12


def test_a_value_that_is_not_a_number_is_read_as_it_is():
    history = History(Key('gate', ('open',)), (Piece(0, False), Piece(2, True)))
    assert history.at(1) is False
    assert history.at(3) is True
    unavailable = Unavailable('no repair has started')
    assert History(Key('m', ('since',)), (Piece(0, unavailable),)).at(4) == unavailable


def test_a_record_finds_its_values_and_its_entries():
    record = Record(
        Manifest(3),
        (History(WATER, (Piece(0, 8, -3), Piece(Fraction(8, 3), 0))),),
        (
            Entry(0, 0, 'start', 'grinder.refill', 'grinder', (('occurrence', 'grinder.refill#0'),)),
            Entry(Fraction(1, 2), 1, 'commit', 'grinder.refill.step[0]', 'grinder.refill#0'),
            Entry(Fraction(1, 2), 1, 'finish', 'grinder.refill', 'grinder.refill#0'),
        ),
    )
    assert record.value(WATER, 1) == 5
    assert [entry.t for entry in record.entries('commit')] == [Fraction(1, 2)]
    assert len(record.entries(part='grinder.refill')) == 2
    assert record.trace[0].detail('occurrence') == 'grinder.refill#0'
    assert record.trace[0].detail('value') is None
    assert record.failure is None
    with pytest.raises(KeyError):
        record.history(Key('tank', ('other',)))


def test_a_manifest_serves_what_it_holds():
    """R-A4a-08: a stored run serves a read of a value that it holds, inside its horizon."""
    everything = Manifest(10)
    some = Manifest(10, everything=False, keys=(WATER,))
    assert everything.holds(Key('clinic', ('delivery', 'actual_rate')), 10)
    assert not everything.holds(WATER, 11)
    assert some.holds(WATER, 5)
    assert not some.holds(Key('clinic', ('delivery', 'actual_rate')), 5)


def test_a_record_holds_a_stores_ledger_with_the_store_and_nothing_before_the_run():
    """A store's ledger belongs to its books: a record of the store holds it, and a request may name
    the ledger alone; nothing is held before 0 h."""
    ledger = Key('tank', ('water', 'external'))
    some = Manifest(10, everything=False, keys=(WATER,))
    alone = Manifest(10, everything=False, keys=(ledger,))
    assert some.holds(ledger, 5) and alone.holds(ledger, 5) and not alone.holds(WATER, 5)
    assert not some.holds(WATER, -1) and ledger.store == WATER and WATER.store is None
    assert str(ledger) == 'tank.water.external' and str(Key('', ('peak',))) == 'peak'


def test_a_record_gives_a_value_only_from_what_it_holds_else_the_reason():
    """`Record.value` reads a held history; a value outside the manifest, a time before the run or after
    the horizon, and a key with no history are `Unavailable`, each with its reason."""
    other = Key('tank', ('other',))
    record = Record(Manifest(3, everything=False, keys=(WATER, other)), (History(WATER, (Piece(0, 8, -3),)),))
    assert record.value(WATER, 1) == 5
    assert record.value(Key('tank', ('level',)), 1) == Unavailable(
        'the record holds no value of tank.level: the request of its run names other values'
    )
    assert record.value(WATER, -1) == Unavailable('the record holds no value at -1 h: the run starts at 0 h')
    assert record.value(WATER, 4) == Unavailable(
        'the record holds no value at 4 h: it reaches to its horizon, 3 h'
    )
    assert record.value(other, 1) == Unavailable('the record keeps no history of tank.other')


def test_offline_quota_uses_the_completed_prefix_at_a_recorded_check():
    # A fit splits the two half-hour intervals into sixteen pieces. A budget
    # of nine fits more than the first half's eight, but does not reach the next check.
    manifest = Manifest(1, check_times=(0.0, 0.5, 1.0))
    starts = tuple(Piece(i / 16, i) for i in range(16))
    record = decode(encode(Record(manifest, (History(WATER, starts),))))
    cut = record.within(9)
    assert cut.end == 0.5
    assert cut.history(WATER).pieces == starts[:8]
    assert cut.manifest.check_times == (0.0, 0.5)
    assert cut.within(8) == record.within(8)
    assert cut.within(6) == record.within(6)
    assert record.within(16) is record
    assert cut.within(9) is cut


def test_an_open_steps_late_pieces_can_disqualify_earlier_checks():
    # The last step was still open at .75 and 1 h. Once complete, its
    # genuine opening at .375 makes both retrospective prefix counts five.
    times = (0.0, 0.003, 0.037, 0.375, 0.75, 1.0, 2.0)
    starts = tuple(Piece(t, i) for i, t in enumerate((0, 0, 0.003, 0.037, 0.375)))
    record = Record(Manifest(2, check_times=times), (History(WATER, starts),))
    cut = record.within(4)
    assert cut.end == 0.375
    assert cut.history(WATER).pieces == starts[:4]
    assert isinstance(cut.value(WATER, 0.375), Unavailable)
    assert cut.value(WATER, 0.374) == 3
    assert record.within(1).end == 0


def test_boundary_rollback_keeps_only_prior_rounds_metadata_and_curve_bases():
    old, new = 'tank.tick#0', 'tank.tick#1'
    ledger = Key('tank', ('water', 'external'))
    hidden = Key('tank', ('helper',))
    manifest = Manifest(
        2,
        everything=False,
        keys=(WATER,),
        comparison_scales=(('tank.water', 8.0), (f'{old}.capacity', 1.0), (f'{new}.capacity', 2.0)),
        unchecked_time_rates=(('first', 0.5), ('second', 1.0)),
        check_times=(0.0, 1.0, 2.0),
    )
    moving = Piece(0, 4, curve=Curve(1.25, (5, 1)))
    rows = (moving, Piece(1.25, 2), BalancePoint(2, 2))
    changes = ChangeHistory(hidden, (Piece(0, False), Piece(1, True)), (0.0, 1.0))
    transfers = History(ledger, (Piece(0.5, 1), Piece(1.5, 2)))
    trace = (
        Entry(0, 0, 'start', 'tank.tick', old),
        Entry(1, 1, 'finish', 'tank.tick', old),
        Entry(1, 2, 'start', 'tank.tick', new),
    )
    record = Record(manifest, (History(WATER, rows), changes, transfers), trace)
    assert record.within(4) is record  # physical postings count, display-only endpoint does not
    cut = record.within(2)
    assert cut.end == 1 and cut.failure.round == 0
    assert cut.trace == (trace[0], cut.failure)
    assert cut.manifest == replace(
        manifest,
        comparison_scales=manifest.comparison_scales[:2],
        unchecked_time_rates=manifest.unchecked_time_rates[:1],
        check_times=(0.0, 1.0),
    )
    assert cut.history(WATER).pieces == (moving,)
    assert cut.history(hidden) == ChangeHistory(hidden, changes.pieces[:1], (0.0,))
    assert cut.history(ledger).pieces == transfers.pieces[:1]
    assert cut.value(WATER, 0.75) == record.value(WATER, 0.75)
    assert isinstance(cut.value(WATER, 1.0), Unavailable)
