"""A capacity can change a running solver even when it did not limit the previous rate."""

from dataclasses import replace

import pytest

from napkin.engine.timeline import Plan, Run, resume
from napkin.engine.timeline.moment import Moment
from napkin.engine.timeline.sparse import Sparse
from napkin.engine.timeline.triggers import Triggers
from napkin.engine.timeline.ways import Ways
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, encode, loads
from napkin.program.config import Configuration, Request
from tests.comparison_bands import band_samples
from tests.engine.solver_guard import install

SOURCE = """scenario "A latent capacity"
    horizon {horizon} h
yard:
    water: L = 0 L
    spare: L = 1 L
    limit: L/h = {limit} L/h
    flow fill: SOURCE -> this.water
        request = {request}
        capacity = formula(this.limit)
    flow separate: SOURCE -> this.spare
        request = formula(0.1 * this.spare / (1 h))
    restrict = event():
        after 1 h:
            this.limit = {tightened} L/h
    arrived = event():
        when this.water >= {threshold} L:
            this.arrived.start()
        after 0 h
yard.restrict.start()
"""


def _model(monkeypatch, *, horizon=3, limit=3, request='2 L/h', tightened=0.5, threshold=2.5, source=SOURCE):
    # Exercise Sparse on both groups even if the planner can solve this small first group by lines.
    connect = Plan.connect

    def sparse_groups(plan, *args, **kwargs):
        return [replace(group, way='sparse') for group in connect(plan, *args, **kwargs)]

    monkeypatch.setattr(Plan, 'connect', sparse_groups)
    source = source.format(
        horizon=horizon, limit=limit, request=request, tightened=tightened, threshold=threshold
    )
    return compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})


@pytest.fixture
def model(monkeypatch):
    return _model(monkeypatch)


def test_new_capacity_restarts_its_group_and_revises_the_crossing(model, monkeypatch):
    baseline = Run(Plan.of(model.program, model.configuration)).run()
    survived = []
    guard = install()
    try:

        def observed(way, t):
            survived.append((t, tuple(way.stores)))
            guard.check_continuation(way, t)

        with monkeypatch.context() as changes:
            changes.setattr(Ways, '_check_continuation', staticmethod(observed))
            record = Run(Plan.of(model.program, model.configuration)).run()
    finally:
        guard.close()

    assert record.failure is None
    assert encode(record) == encode(baseline)
    assert (1, ('yard.spare',)) in survived and (1, ('yard.water',)) not in survived
    assert guard.report()['stores'] > 0
    fires = [entry.t for entry in record.entries('fire') if 'arrived' in entry.part]
    assert fires == pytest.approx([2])


def test_a_changed_capacity_discards_its_future_step_and_preserves_the_other_group(monkeypatch):
    # A condition on another moving store, at a time outside the authored calendar.
    source = SOURCE.replace(
        '        after 1 h:',
        """        when this.clock >= 1 L:
            this.restrict.start()
        after 0 h:""",
    ).replace(
        'yard.restrict.start()',
        """    clock: L = 0 L
    flow clock_tick: SOURCE -> this.clock
        request = 1 L/h""",
    )
    model = _model(monkeypatch, request='formula(1 L/h + t * 1 L/h/h)', threshold=2, source=source)
    retired, continued = [], []
    retire = Sparse.retire

    def observe(destination, way):
        if (
            way.run.clock.within(way.run.now, 1)
            and way.pending
            and way.pending[1] > way.run.clock.apart(way.t)
        ):
            # Both collocation polynomials have supplied their paid prefix at 1 h.
            assert way.amounts.through == way.t == way.run.now and way.pending_evaluations == 0
            destination.extend(way.stores)

    def retiring(way, key):
        observe(retired, way)
        return retire(way, key)

    monkeypatch.setattr(Sparse, 'retire', retiring)
    monkeypatch.setattr(Ways, '_check_continuation', staticmethod(lambda way, t: observe(continued, way)))
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert 'yard.water' in retired and 'yard.spare' in continued and 'yard.spare' not in retired
    assert record.failure is None
    assert [e.t for e in record.entries('fire')] == pytest.approx([1, 2])


def test_scheduled_parent_bounds_only_the_group_its_child_changes(monkeypatch):
    source = SOURCE.replace(
        '    restrict = event():\n        after 1 h:', '    restrict = event():\n        after 0 h:'
    ).replace(
        'yard.restrict.start()',
        """dispatcher:
    review = event():
        after 1 h:
            yard.restrict.start()
dispatcher.review.start()""",
    )
    model = _model(monkeypatch, request='formula(1 L/h + t * 1 L/h/h)', threshold=2, source=source)
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare(now=False)
    run.moment.setup()
    limited = run.ways.instance_of('yard.water')
    independent = run.ways.instance_of('yard.spare')
    assert run.ways.deadlines.get(limited) == 1
    assert independent not in run.ways.deadlines and run.ways.shared_deadline == 3
    moment = run.next_moment()
    assert moment[0] == 1
    assert limited.pending[2].t <= run.clock.apart(1)
    assert independent.pending[2].t > run.clock.apart(1)
    run.moment.at(*moment)
    assert not limited.alive and independent.alive
    run.loop()
    assert [entry.t for entry in run.recorder.trace if entry.kind == 'fire'] == pytest.approx([2])


def test_guard_detects_a_deliberately_missing_capacity_dependency(model, monkeypatch):
    touched_by = Ways.touched_by

    def omit_capacity(ways, names):
        touched = touched_by(ways, names)
        if 'yard.limit' in names and 'yard.fill' in ways.set_of:
            touched.discard(ways.set_of['yard.fill'])
        return touched

    monkeypatch.setattr(Ways, 'touched_by', omit_capacity)
    guard = install()
    try:
        with pytest.raises(AssertionError, match='Continued Radau derivative'):
            Run(Plan.of(model.program, model.configuration)).run()
        failed = guard.report()['first_failure']
        assert (failed['time'], failed['store']) == (1, 'yard.water')
        assert (failed['dense_rate'], failed['fresh_rate']) == pytest.approx((2, 0.5))
    finally:
        guard.close()


def test_a_limit_that_still_does_not_bind_replaces_the_group_immediately(monkeypatch):
    model = _model(
        monkeypatch,
        horizon=5,
        limit=6,
        request='formula(1 L/h * (1 + t / (1 h)))',
        tightened=4,
        threshold=9.5,
    )
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare(now=False)
    run.moment.setup()
    old = run.ways.instance_of('yard.water')
    spare = run.ways.instance_of('yard.spare')
    moment = run.next_moment()
    assert moment[0] == 1
    before = old.incoming_rates(1)('yard.fill')
    run.moment.at(*moment)
    new = run.ways.instance_of('yard.water')
    assert new is not old and not old.alive and run.ways.instance_of('yard.spare') is spare
    assert (before, new.rate_at('yard.fill.actual_rate', 1)) == pytest.approx((2, 2))
    run.loop()
    assert float(run.stock_balance('yard.water', 5)) == pytest.approx(15.5)
    fires = [e.t for e in run.recorder.trace if e.kind == 'fire' and 'arrived' in e.part]
    assert fires == pytest.approx([3.5])


@pytest.mark.parametrize('threshold', [0, 50], ids=['band-entry', 'physical-crossing'])
def test_only_a_band_entry_passes_its_moving_operand_to_settlement(monkeypatch, threshold):
    # Exponential decay approaches zero without reaching it, and crosses 50 L exactly once.
    source = f"""scenario "A watched drain"
    horizon 300 h
tank:
    water: L = 100 L scale 100 L
    drained: L = 0 L scale 100 L
    permit: L = 1 L
    flow drain: this.water -> this.drained
        request = formula(0.1 * this.water / (1 h))
    low = event():
        when this.permit == 1 L and this.water <= {threshold} L:
            this.low.start()
        after 0 h
"""
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare(now=False)
    run.moment.setup()

    arrivals, regions = [], []
    arrival_at, region = Triggers.arrival_at, Moment._region

    def observe_arrival(triggers, t, levels):
        levels, changed, crossings = arrival_at(triggers, t, levels)
        arrivals.append((dict(levels), set(changed)))
        return levels, changed, crossings

    def observe_region(moment, names, joined, left):
        regions.append(set(names))
        return region(moment, names, joined, left)

    monkeypatch.setattr(Triggers, 'arrival_at', observe_arrival)
    monkeypatch.setattr(Moment, '_region', observe_region)
    moment = run.next_moment()
    run.moment.at(*moment)
    (firing,) = (e for e in run.recorder.trace if e.kind == 'fire')
    assert firing.t == moment[0]
    ((placement, band_reads),) = arrivals
    if threshold == 0:
        assert placement == {}
        assert band_reads == regions[0] == {'tank.water'}
        remainder = float(run.stock_balance('tank.water', moment[0]))
        assert 0 < remainder < 1e-6
        (tie,) = firing.detail('band_entry')
        origin, comparison, difference, band = tie
        assert origin == firing.part and 'tank.water' in comparison and 'tank.permit' not in comparison
        assert 0 < difference == remainder <= band
        assert tie in firing.detail('near')
    else:
        assert band_reads == set()
        assert placement == {'tank.water': pytest.approx(50)}
        assert firing.detail('band_entry') is None


def test_only_a_comparison_on_the_firing_path_can_mark_a_band_entry():
    (sample,) = band_samples(Configuration(Request(1)), 100, multiples=(0.1,))
    source = f"""scenario "Separate firing paths"
    horizon 1 h
tank:
    water: L = {sample} L scale 100 L
    allow: L = 1 L
    low = event():
        when this.allow == 1 L or this.water <= 0 L:
            this.low.start()
        after 0 h
    inside = event():
        when this.water <= 0 L or 1 L / this.empty > 1:
            this.inside.start()
        after 0 h
    empty: L = 0 L
"""
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    record = Run(Plan.of(model.program, model.configuration)).run()
    exact, inside = record.entries('fire')
    assert exact.detail('near') and exact.detail('band_entry') is None
    (tie,) = inside.detail('band_entry')
    assert 'tank.water' in tie[1] and tie in inside.detail('near')


@pytest.mark.parametrize('change_level', [False, True], ids=['landed', 'stage-changes-threshold'])
def test_landed_crossing_with_one_ulp_of_ledger_residue_survives_stage_stop(change_level, monkeypatch):
    # At hour 41.6 the physical watch lands on its threshold. The exact ledger credits 0.104 L.
    action = ':\n            this.threshold = 0.1040000005 L' if change_level else ''
    source = f"""scenario "Crossing during a scheduled stage"
    horizon 42 h
tank:
    water: L = 0 L
    threshold: L = 0.10400000000000001 L
    flow fill: SOURCE -> this.water
        request = 0.0025 L/h
        capacity = 0.0025 L/h
    close = event():
        when this.water >= this.threshold:
            this.close.start()
        after 0 h
    clock = event():
        after 41.6 h{action}
tank.clock.start()
"""
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    fire_at = Triggers.fire
    ledger = []

    def capture(triggers, *args):
        ledger.append(triggers.run.value('tank.water'))
        return fire_at(triggers, *args)

    monkeypatch.setattr(Triggers, 'fire', capture)
    direct = Run(Plan.of(model.program, model.configuration)).run()
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint('tank.clock.step[0]'),))
    stop = live.run()
    assert stop.stop.t == 41.6 and not stop.record.entries('fire')
    for record in (direct, live.resume(), resume(model.program, loads(dumps(stop)))):
        (fire,) = record.entries('fire')
        assert fire.t == 41.6
        if change_level:
            (tie,) = fire.detail('band_entry')
            assert tie in fire.detail('near') and tie[2] == 0.104 - 0.1040000005
        else:
            assert fire.detail('band_entry') is None
    assert ledger == [0.104, 0.104, 0.104]


def test_a_newly_scheduled_deadline_keeps_the_prepared_step_to_its_moment(monkeypatch):
    """The stage at 1 h schedules a change of the group at 1.01 h, inside the step that the group
    prepared. The step stays: it is valid to 1.01 h, where settlement retires the group, and its trial
    is charged once. The independent group goes on."""
    source = SOURCE.replace('        after 1 h:', '        after 0.01 h:').replace(
        'yard.restrict.start()',
        """dispatcher:
    review = event():
        after 1 h:
            yard.restrict.start()
dispatcher.review.start()""",
    )
    model = _model(monkeypatch, request='formula(1 L/h + t * 1 L/h/h)', threshold=2, source=source)
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare(now=False)
    run.moment.setup()
    group = run.ways.instance_of('yard.water')
    independent = run.ways.instance_of('yard.spare')
    first = run.next_moment()
    assert first[0] == 1 and group.pending[2].t > 1.01 and independent.pending[2].t > 1.01
    earlier, other = group.pending[2], independent.pending[2]
    run.moment.at(*first)
    assert group.alive and run.ways.deadlines[group] == 1.01
    assert float(run.stock_balance('yard.water', 1)) == pytest.approx(earlier(1)[0])
    paid = group.evaluations
    assert group.pending_evaluations == 0  # the first prefix paid for the whole trial
    second = run.next_moment()
    assert second[0] == 1.01
    assert group.pending[2] is earlier and independent.pending[2] is other
    run.moment.at(*second)
    assert not group.alive and independent.alive
    assert group.evaluations == paid
    assert float(run.stock_balance('yard.water', 1.01)) == pytest.approx(earlier(1.01)[0])
