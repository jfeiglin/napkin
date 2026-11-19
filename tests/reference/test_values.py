"""Values: no absent value (decision D4), the stable record of a finished occurrence (decision D7),
writes to live occurrences, the written order of event locals (decision D14), and units by
canonical conversion (decision D12)."""

import pytest

from tests.reference import model as described
from tests.reference.errors import Diagnostic, RunFailed
from tests.reference.model import (
    SINK,
    SOURCE,
    Endpoint,
    Model,
    N,
    add,
    after,
    all_,
    any_,
    calc,
    count,
    event,
    flow,
    fmax,
    fmin,
    formula,
    fsum,
    inp,
    q,
    set_,
    since,
    start,
    t,
    this,
    value,
)
from tests.reference.run import Run, Unavailable


def gauge():
    m = Model()
    m.entity(
        'gauge',
        fields=[value('reading'), calc('shown', this.reading + 1)],
        events=[event('measure', steps=[after(1, [set_(this.reading, 4)])])],
    )
    m.setup = [start(N.gauge.measure)]
    return Run(m, horizon=2).run()


def test_there_is_no_absent_value():
    """The model has no `none`. A field declared without a value fails when it is read, also
    through a formula, until a stage gives it one."""
    assert not hasattr(described, 'none')
    r = gauge()
    with pytest.raises(RunFailed, match=r'gauge\.reading is read before it has a value'):
        r.read(N.gauge.shown, 0)
    assert r.read(N.gauge.shown, 1) == 5


def test_empty_reductions():
    """On an empty collection `sum` is zero, `count` zero, `any` false and `all` true; `min` and
    `max` fail; a scalar beside the collection still gives a value."""
    m = Model()
    m.template('Pump', fields=[value('rate', 1), value('on', True)])
    m.entity('site')
    r = Run(m, horizon=0).run()
    pumps = N.Pump.instances
    assert (
        r.read(fsum(pumps.rate)),
        r.read(count(pumps)),
        r.read(any_(pumps.on)),
        r.read(all_(pumps.on)),
    ) == (
        0,
        0,
        False,
        True,
    )
    for reduction in (fmax, fmin):
        with pytest.raises(RunFailed, match='reads an empty collection'):
            r.read(reduction(pumps.rate))
    assert r.read(fmax(0, pumps.rate)) == 0


def test_a_capacity_left_out_sets_no_limit_and_has_no_value():
    """A request left out reads zero; a capacity left out sets no limit, and a read of it fails."""
    m = Model()
    m.entity('tank', fields=[value('water', 8, 0)], flows=[flow('drain', this.water, SINK)])
    r = Run(m, horizon=0).run()
    assert r.read(N.tank.drain.request) == 0
    with pytest.raises(RunFailed, match=r'tank\.drain\.capacity is not declared'):
        r.read(N.tank.drain.capacity)


def jobs():
    """A job reads two formulas when it finishes at 1 h; the receiver changes at 2 h."""
    job = event(
        'job',
        locals=[calc('double', this.counter * 2), calc('since_repair', since(this.repair))],
        steps=[after(1, [])],
    )
    later = event('later', steps=[after(2, [set_(this.counter, 100), start(this.repair)])])
    m = Model()
    m.entity(
        'plant', fields=[value('counter', 7)], events=[job, later, event('repair', steps=[after(5, [])])]
    )
    m.setup = [start(N.plant.job), start(N.plant.later)]
    return Run(m, horizon=3).run()


def test_a_frozen_formula_keeps_its_result():
    """A formula of an occurrence that read 14 at its finish reads 14 afterwards."""
    r = jobs()
    finished = N.plant.job.occurrences.at(t)
    assert (r.read(finished.double, 1), r.read(finished.double, 3)) == (14, 14)
    assert r.read(N.plant.counter, 3) == 100


def test_a_formula_without_a_value_at_the_finish_keeps_its_reason():
    """No repair had started at the finish: the occurrence still finishes normally, a read of the
    frozen field raises the recorded reason, and the repair that starts later changes nothing."""
    r = jobs()
    finished = N.plant.job.occurrences.at(t)
    assert r.read(finished.done, 3) is True
    for at in (1, 3):
        with pytest.raises(
            RunFailed, match=r'since_repair was not available when plant\.job#0 finished at t = 1 h'
        ):
            r.read(finished.since_repair, at)
    shown = r.report(finished.since_repair, [3])[0]
    assert isinstance(shown, Unavailable) and 'before the first occurrence' in shown.reason


def crews(readonly=False, write_at=1):
    repair = event(
        'repair',
        locals=[value('crew_size', 1, readonly=readonly)],
        steps=[after(2, [add(this.work_done, N.crew_size)])],
    )
    dispatch = event('dispatch', steps=[after(write_at, [set_(this.repair.occurrences.at(t).crew_size, 3)])])
    m = Model()
    m.entity('site', fields=[value('work_done', 0)], events=[repair, dispatch])
    m.setup = [start(N.site.repair), start(N.site.dispatch)]
    return Run(m, horizon=4)


def test_a_dispatch_raises_the_crew_of_a_running_repair():
    """`this.repair.occurrences.at(t).crew_size = 3` writes a writable local of a running repair."""
    assert crews().run().read(N.site.work_done) == 3


def test_a_readonly_local_cannot_be_assigned():
    with pytest.raises(Diagnostic, match='crew_size is readonly'):
        crews(readonly=True).run()


def test_a_finished_occurrence_is_frozen():
    with pytest.raises(RunFailed, match=r'site\.repair#0\.crew_size belongs to the finished occurrence'):
        crews(write_at=3).run()


def locals_in_order(*declarations):
    m = Model()
    m.entity(
        'tank',
        fields=[value('water', 100, 0)],
        events=[event('job', params=['amount'], locals=list(declarations), steps=[after(1, [])])],
    )
    m.setup = [start(N.tank.job, 6)]
    return Run(m, horizon=2)


def test_plain_initializers_run_in_written_order():
    """`doubled = amount * 2` reads an earlier local; a plain initializer that names a later one is
    refused."""
    r = locals_in_order(value('left', N.amount), value('doubled', N.left * 2)).run()
    assert r.read(N.tank.job.occurrences.at(t).doubled) == 12
    with pytest.raises(Diagnostic, match='names left, declared below it'):
        locals_in_order(value('doubled', N.left * 2), value('left', N.amount)).run()


def test_a_flow_property_follows_the_written_order_and_a_formula_may_look_ahead():
    """A plain `request = left / (2 h)` needs `left` above the flow; `formula(left / (2 h))` may name
    a later local, because it is read after entry is complete: 6 L at 3 L/h for 1 h."""
    with pytest.raises(Diagnostic, match='names left, declared below it'):
        locals_in_order(flow('out', this.water, SINK, request=N.left / 2), value('left', N.amount)).run()
    r = locals_in_order(
        flow('out', this.water, SINK, request=formula(N.left / 2)), value('left', N.amount)
    ).run()
    assert r.read(N.tank.water) == 97


def test_an_endpoint_setting_follows_the_written_order():
    """A plain `outflow.capacity = cap` written under a local store needs `cap` above it; a formula
    may name a later local, and keeps the 6 L/h that it read when the occurrence finished."""

    def store(capacity):
        return value('stock', 0, 0, outflow=Endpoint(capacity=capacity))

    with pytest.raises(Diagnostic, match='names cap, declared below it'):
        locals_in_order(store(N.cap), value('cap', N.amount)).run()
    r = locals_in_order(store(formula(N.cap)), value('cap', N.amount)).run()
    assert r.read(N.tank.job.occurrences.at(t).stock.outflow.capacity) == 6


def test_the_water_model_keeps_the_loss():
    """D17: each utility's tally fills at its unserved rate. North (4 L/h) is out of service until
    hour 5, South (2 L/h) is served. At hour 6 the rate is 0 and the volume still holds the 20 L
    missed through hour 5; at hour 3 they are 4 L/h and 12 L."""
    m = Model()
    m.template(
        'Utility',
        fields=[
            inp('demand', 0),
            value('service', 10),
            calc('unserved_rate', fmax(0, this.demand - this.delivery.actual_rate)),
            value('unserved', 0, 0),
        ],
        flows=[
            flow('delivery', SOURCE, SINK, request=formula(this.demand), capacity=formula(this.service)),
            flow('count_unserved', SOURCE, this.unserved, request=formula(this.unserved_rate)),
        ],
        events=[event('restore', steps=[after(5, [set_(this.service, 10)])])],
    )
    m.instance('north', 'Utility', demand=4, service=0)
    m.instance('south', 'Utility', demand=2)
    m.entity(
        'region',
        fields=[
            value('initial_unserved', fsum(N.Utility.instances.unserved)),
            calc('unserved_volume', fsum(N.Utility.instances.unserved)),
            calc('unserved_now', fsum(N.Utility.instances.unserved_rate)),
        ],
    )
    m.setup = [start(N.north.restore)]
    r = Run(m, horizon=8).run()
    region = N.region
    assert [r.read(region.unserved_now, at) for at in (3, 6)] == [4, 0]
    assert [r.read(region.unserved_volume, at) for at in (3, 5, 6, 8)] == [12, 20, 20, 20]
    assert (r.read(region.initial_unserved, 6), r.read(N.north.unserved_rate, 6)) == (0, 0)


def test_units_by_ordinary_division():
    """`48 h / 2` is 24 h; the oracle reads the same quantity in any unit of time."""
    m = Model()
    m.entity('clock', fields=[value('half', q(48, 'h') / 2)])
    r = Run(m, horizon=0).run()
    assert (
        r.read(N.clock.half, unit='h'),
        r.read(N.clock.half, unit='min'),
        r.read(N.clock.half, unit='day'),
    ) == (24, 1440, 1)


def test_units_by_ordinary_multiplication():
    """`(3 person) * (2 year)` gives 6 person * year."""
    m = Model()
    m.entity('team', fields=[value('effort', q(3, 'person') * q(2, 'year'))])
    assert Run(m, horizon=0).run().read(N.team.effort, unit='person*year') == 6
