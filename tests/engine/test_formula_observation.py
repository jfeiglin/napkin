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


def put_stock(recorder, since, end, slope, complete):
    def fit(left):
        span = end - left
        shape = Curve(span, (slope * (left + end) / 2, slope * span / 2))
        return [[(left, slope * left, shape)]]

    recorder.store_step(['plant.stock'], fit, since, complete=complete)


@pytest.mark.parametrize('landed', [False, True])
def test_stock_extension_preserves_subdivisions_in_readers_and_aliases(landed):
    program = model()
    live = recorder(program)
    put_stock(live, 0, 1, 1, False)
    first = observe(live, 1)
    old = visible(first, 'crossed')
    assert any(0 < p.t < 1 for p in old)
    edge, end = 1 + 1e-9, 1 + 3e-9
    if landed:
        # A new hard input start shortly after the observation must still land.
        live.add('plant.offset', edge, -2, 0)
    put_stock(live, 1, end, 1 + 1e-7, True)
    second = observe(live, end)
    # The observation at hour one permanently closed the incoming fit.
    assert any(p.t == 1 for p in visible(second, 'twice'))
    for name in ('crossed', 'again'):
        pieces = visible(second, name)
        assert [p.t for p in pieces if p.t <= 1] == [p.t for p in old]
        assert second.history(Key('plant', (name,))).at(end) == (0 if landed else 1)

    def cold():
        fresh = recorder(program)
        fresh.pieces = {name: list(rows) for name, rows in live.saved_pieces()}
        fresh.fits.ends = list(live.fits.ends)
        fresh._dirty.update(fresh.pieces)
        return fresh

    # These are the actual saved stock rows, including the new curve's coefficients.
    # Their cold fit of the old threshold can differ from the witnessed one.
    if not landed:
        unwitnessed = visible(observe(cold(), end), 'crossed')
        assert [p.t for p in unwitnessed] != [p.t for p in visible(second, 'crossed')]
    fresh = cold()
    fresh.observe_checkpoint(second)
    restored = observe(fresh, end)
    for name in ('crossed', 'again'):
        assert visible(restored, name) == visible(second, name)


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
