"""An observed stock fit and the formulas that read it keep their charged starts."""

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.record import Recorder
from napkin.program.build import Builder, formula, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Curve, Entry, History, Key, Piece


def model():
    builder = Builder({'h': {'time': 1}})
    builder.entity(
        'plant',
        value('stock', '', 0),
        value('offset', '', 0),
        value('crossed', '', formula(this.stock + this.offset > 0.3887112)),
        value('again', '', formula(this.crossed)),
        value('twice', '', formula(2 * this.stock)),
    )
    return builder.finish()


def recorder(program):
    run = Run(Plan.of(program, Configuration(Request(2))))
    run.prepare()
    return run.recorder


def observe(recorder, end):
    recorder.fits.advance(end)
    return recorder.record(end, pause=Entry(end, 1, 'pause', '', ''), ongoing=True)


def visible(record, name):
    return record.history(Key('plant', (name,))).pieces


def test_preserving_a_start_restricts_the_outgoing_polynomial_to_its_new_interval():
    key = Key('plant', ('reading',))
    prior = History(key, (Piece(0, 0), Piece(0.65, 1)))
    curve = Piece(0.6, 1.2, curve=Curve(2.4, (1, 0.4, 0.5, -0.6, 0.125)))
    candidate = History(key, (Piece(0, 0), curve))
    result = Recorder._join_history(prior, candidate, 1, 3)
    shorter = Recorder._join_history(prior, candidate, 1, 2)
    assert shorter.pieces == result.pieces
    assert [p.t for p in result.pieces] == [0, 0.65, 1]
    assert result.pieces[-1].curve.length == 2
    for at in (1, 1.25, 1.5, 2, 2.75, 3):
        assert result.at(at) == pytest.approx(candidate.at(at), rel=1e-14, abs=1e-14)
