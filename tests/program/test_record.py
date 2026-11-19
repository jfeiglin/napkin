"""The record of a run (`napkin/program/record.py`): histories of pieces, the trace, the manifest.

A history is read at any time from its pieces, exactly when its numbers are exact. The cases are the
spec's: the tank of 8 L that a delivery of 3 L/h empties at 2 h 40 min, and the 20 g that one stage
sets to 8 g and a later stage of the same round raises to 12 g.
"""

from fractions import Fraction

import pytest

from napkin.program.record import Entry, History, Key, Manifest, Piece, Record, Unavailable

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


def test_a_budget_of_pieces_ends_a_record_before_the_first_piece_that_does_not_fit():
    """Two values with pieces at 0, 1 and 2 h and at 0 and 2 h: within 3 pieces the record holds the
    three before 2 h and ends at 2 h; within 1 piece not even the two at 0 h fit, and it holds none;
    within 5 it is itself. A value that the manifest does not hold does not count."""
    level = Key('tank', ('level',))
    record = Record(
        Manifest(4, everything=False, keys=(WATER, level)),
        (
            History(WATER, (Piece(0, 8, -1), Piece(1, 7), Piece(2, 5))),
            History(level, (Piece(0, 1), Piece(2, 2))),
            History(Key('tank', ('kept',)), (Piece(0, 0), Piece(1, 1), Piece(3, 2))),
        ),
        (
            Entry(0, 0, 'start', 'tank.tick', 'tank.tick#0'),
            Entry(2, 1, 'commit', 'tank.tick.step[0]', 'tank.tick#0'),
        ),
    )
    assert record.within(5) is record
    three = record.within(3)
    assert three.end == 2 and three.failure.detail('budget') == 3
    assert [entry.kind for entry in three.trace] == ['start', 'failure']
    assert three.value(WATER, 1.5) == 7 and three.value(level, 1) == 1
    assert three.value(WATER, 2).reason.startswith(
        'the record stops at 2 h: from this time the values that it'
    )
    assert sum(len(history.pieces) for history in three.histories if three.manifest.names(history.key)) == 3
    one = record.within(1)
    assert one.end == 0 and not one.histories and isinstance(one.value(WATER, 0), Unavailable)
