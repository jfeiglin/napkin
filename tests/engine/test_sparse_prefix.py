"""A moment can observe part of an accepted Radau step more than once."""

import pytest

from napkin.engine.timeline import Plan, Run, plan, resume
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from tests.engine.resume_parity import assert_resume_parity


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0)
    return compile_text(
        """scenario "Two metered pipes"
    horizon 2 h
tank:
    water: L = 10 L
    flow fill: SOURCE -> this.water
        request = formula(1 L/h + t * 1 L/h/h)
    flow drain: this.water -> SINK
        request = formula(0.5 L/h + t * 0.25 L/h/h)
    tick = event():
        after 1 h:
            this.pause.start()
    pause = event():
        after 0 h
tank.tick.start()
""",
        {'L': {'volume': 1}, 'h': {'time': 1}},
    )


def test_observe_commits_each_part_of_one_prepared_step_once(model):
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    way = run.ways.instance_of('tank.water')
    assert isinstance(way, Sparse)
    way.last_step = 1
    end = way.peek()
    solution = way.pending[2]
    first, second = end / 4, 3 * end / 4

    def assert_posted(t, starts):
        assert way.recorded_through == way.amounts.through == t
        for pipe, expected in [('tank.fill', t + t * t / 2), ('tank.drain', t / 2 + t * t / 8)]:
            assert float(way.transferred(pipe, t)) == pytest.approx(expected, rel=1e-12)
            assert float(way.amounts.numerical(way.leg_rows[pipe])) == pytest.approx(expected, rel=1e-12)
        assert [p[0] for p in run.recorder.pieces['tank.water']] == starts

    for t, starts in [(first, [0]), (second, [0, first])]:
        run.now = t
        way.incoming_history(t)
        assert_posted(t, starts)
        # The left endpoint still belongs to the original solver step after this prefix.
        assert way.level_at('tank.water', 0) == way.incoming_level('tank.water', 0) == 10
        assert way.level_at('tank.water', t) > 10
        before = {name: list(pieces) for name, pieces in run.recorder.pieces.items()}
        way.observe(t)
        assert_posted(t, starts)
        assert run.recorder.pieces == before
        assert way.pending[2] is solution

    way.step()
    assert_posted(end, [0, first, second])
    assert way.pending is None


def test_second_round_checkpoint_keeps_the_surviving_prefix(model):
    direct = Run(Plan.of(model.program, model.configuration)).run()
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint('tank.pause.step[0]'),))
    stop = live.run()
    assert (stop.stop.t, stop.stop.round) == (1, 2)
    way = live.ways.instance_of('tank.water')
    assert isinstance(way, Sparse)
    assert way.pending[0] < stop.stop.t < way.pending[1]
    assert way.amounts.through == way.recorded_through == stop.stop.t
    assert float(live.stock_balance('tank.water', stop.stop.t)) == pytest.approx(10.875)
    for record in (live.resume(), resume(model.program, loads(dumps(stop)))):
        assert_resume_parity(model.program, model.configuration, direct, record)
