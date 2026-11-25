"""A moment can observe part of an accepted Radau step more than once."""

from dataclasses import replace

import pytest

from napkin.engine.errors import SimulationError
from napkin.engine.timeline import Plan, Run, plan
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
        (prefix,) = dict(run.recorder.saved_pieces())['tank.water']
        assert prefix[0] == 0 and prefix[2].length == t

    for t in (first, second):
        run.now = t
        way.incoming_history(t)
        assert_posted(t, [])
        # The left endpoint still belongs to the original solver step after this prefix.
        assert way.level_at('tank.water', 0) == way.incoming_level('tank.water', 0) == 10
        assert way.level_at('tank.water', t) > 10
        before = {name: list(pieces) for name, pieces in run.recorder.pieces.items()}
        way.observe(t)
        assert_posted(t, [])
        assert run.recorder.pieces == before
        assert way.pending[2] is solution

    way.step()
    assert_posted(end, [0])
    assert way.pending is None


def test_second_round_checkpoint_keeps_the_surviving_prefix(model):
    config = model.configuration
    direct = Run(Plan.of(model.program, config)).run()
    live = Run(Plan.of(model.program, config), (Breakpoint('tank.pause.step[0]'),))
    stop = live.run()
    assert (stop.stop.t, stop.stop.round) == (1, 2)
    way = live.ways.instance_of('tank.water')
    assert isinstance(way, Sparse)
    assert way.pending[0] < stop.stop.t < way.pending[1] - live.plan.numerics.crossing
    assert way.amounts.through == way.recorded_through == stop.stop.t
    assert float(live.stock_balance('tank.water', stop.stop.t)) == pytest.approx(10.875)
    assert float(way.transferred('tank.fill', stop.stop.t)) == pytest.approx(1.5)
    assert float(way.transferred('tank.drain', stop.stop.t)) == pytest.approx(0.625)
    recovered = Run.restored(Plan.of(model.program, config), loads(dumps(stop)))
    restored = recovered.ways.instance_of('tank.water')
    assert restored.evaluations == way.evaluations
    assert restored.pending_evaluations == way.pending_evaluations == 0
    for record in (live.resume(), recovered.resume()):
        assert_resume_parity(model.program, config, direct, record)


def test_new_rate_evaluations_after_restore_use_the_remaining_allowance(model):
    def restore(config):
        live = Run(Plan.of(model.program, config), (Breakpoint('tank.pause.step[0]'),))
        stop = live.run()
        fresh = Run.restored(Plan.of(model.program, config), loads(dumps(stop)))
        paid = live.ways.instance_of('tank.water').evaluations
        assert fresh.ways.instance_of('tank.water').evaluations == paid
        return fresh, paid

    config = model.configuration
    reference, paid = restore(config)
    assert reference.resume().failure is None
    required = reference.ways.instance_of('tank.water').evaluations
    assert required > paid
    for limit in (required - 1, required):
        fresh, inherited = restore(replace(config, numerics=replace(config.numerics, max_evaluations=limit)))
        assert inherited == paid
        record = fresh.resume()
        if limit == required:
            assert record.failure is None and record.end == config.request.horizon
        else:
            assert record.failure.detail('message') == 'Numerical evaluation budget exceeded'


def test_failure_beyond_an_earlier_stop_waits_until_the_failed_interval(model, monkeypatch):
    field = Sparse.field
    failed_at = []

    def fail_after(self, t, y, *, allocation=False):
        if t > 1.1:
            failed_at.append(t)
            raise ArithmeticError('past the permitted rate interval')
        return field(self, t, y, allocation=allocation)

    monkeypatch.setattr(Sparse, 'field', fail_after)
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint('tank.pause.step[0]'),))
    stop = live.run()
    assert stop.stop.t == 1
    assert failed_at
    finished = live.resume()
    assert finished.failure is not None
    assert finished.end >= stop.stop.t
    assert 'past the permitted rate interval' in str(finished.failure)


def _prepared_way(model, config=None):
    live = Run(Plan.of(model.program, config or model.configuration))
    live.prepare()
    way = live.ways.instance_of('tank.water')
    live.limit = 0.4
    way.last_step = 0.1
    assert way.peek() == 0.1
    way.step()
    return way


@pytest.mark.parametrize('keep_prefix', (False, True))
def test_a_speculative_step_is_charged_once_when_its_first_prefix_is_used(model, keep_prefix):
    way = _prepared_way(model)
    spent = way.evaluations
    assert way.peek() > way.run.limit
    assert way.evaluations == spent
    trial = way.pending_evaluations
    assert trial > 0
    if keep_prefix:
        way.observe(0.2)
        way.observe(0.3)
    way.cut(way.t)
    assert way.evaluations == spent + (trial if keep_prefix else 0)
    assert way.pending_evaluations == 0


@pytest.mark.parametrize('small_limit', (False, True))
def test_expensive_future_step_at_the_evaluation_limit_retries_only_the_required_prefix(
    monkeypatch, small_limit
):
    monkeypatch.setattr(plan, 'LIMIT', 0)
    model = compile_text(
        """scenario "A pulse beyond the required interval"
    horizon 2 h
tank:
    water: L = 10 L
    flow fill: SOURCE -> this.water
        request = formula(1 L/h + t * 1 L/h/h + 2 L/h * exp(-((t - 0.8 h) / 0.03 h)**2))
    flow drain: this.water -> SINK
        request = formula(0.5 L/h + t * 0.25 L/h/h)
""",
        {'L': {'volume': 1}, 'h': {'time': 1}},
    )
    control = _prepared_way(model)
    spent = control.evaluations
    assert control.peek(control.run.limit) == control.run.limit
    required = control.evaluations - spent

    if small_limit:
        config = model.configuration
        config = replace(config, numerics=replace(config.numerics, max_evaluations=spent + required))
    else:
        config = model.configuration
    way = _prepared_way(model, config)
    limit = way.plan.numerics.max_evaluations
    if small_limit:
        assert way.evaluations + required == limit
    else:
        # Start a default-budget group on the same last few evaluations.
        way.evaluations = limit - required
    assert way.peek() == control.run.limit
    # The rejected trial reached the far side of the calendar. Its retry used
    # the same Radau state and transfer samples as the directly bounded control.
    assert not way.local_steps
    assert way.evaluations == limit
    assert (way.pending[2].Q == control.pending[2].Q).all()
    assert all(
        (a == b).all() for a, b in zip(way.pending[2].leg_rates, control.pending[2].leg_rates, strict=True)
    )
    way.step()
    assert way.evaluations == limit
    assert way.incoming_rates(way.t)('tank.fill') == pytest.approx(1.4)
    way.run.limit = way.plan.horizon
    with pytest.raises(SimulationError, match='evaluation budget exceeded'):
        way.peek()
