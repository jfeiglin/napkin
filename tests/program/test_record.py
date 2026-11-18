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
