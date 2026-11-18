"""Flows that no solver determines: each endpoint shares among its own flows by its own rule.

The rows of the acceptance table of `spec.md` on local allocation, reversible routes, flows with
legs and flows that join and leave during a run. The expected numbers are the spec's, or worked by
hand in the docstring of the test."""

from fractions import Fraction as F

import pytest

from tests.reference.model import (
    SINK,
    SOURCE,
    Endpoint,
    Model,
    N,
    after,
    count,
    event,
    flow,
    formula,
    fsum,
    leg,
    legs,
    lit,
    priority,
    proportional,
    route,
    set_,
    solver,
    start,
    t,
    this,
    until,
    value,
)
from tests.reference.run import Run


def test_tank_empties_at_two_hours_forty():
    """8 L at 3 L/h (capacity 5 L/h) empties at 8/3 h; then the rate is 0 and the settings stay."""
    m = Model()
    m.entity('tank', fields=[value('water', 8, 0, 20, readonly=True)])
    m.entity('clinic', flows=[flow('delivery', N.tank.water, SINK, capacity=5, request=3)])
    r = Run(m, horizon=4).run()
    assert r.read(N.clinic.delivery.actual_rate, 0) == 3
    assert r.read(N.tank.water, 2) == 2
    assert F(8, 3) in [f.t for f in r.frames]
    assert r.read(N.tank.water, F(8, 3)) == 0
    assert r.read(N.clinic.delivery.actual_rate, F(8, 3)) == 0
    assert r.read(N.clinic.delivery.capacity, 4) == 5
    assert r.read(N.clinic.delivery.request, 4) == 3
    assert r.conservation()['balanced']


def reversible(request):
    m = Model()
    m.entity('west', fields=[value('water', 10, 0, 100)])
    m.entity('east', fields=[value('water', 10, 0, 100)])
    m.entity('net', flows=[route('link', N.west.water, N.east.water, request=request)])
    return Run(m, horizon=1).run()


def test_reversible_route_backward():
    """At -3 L/h the forward leg reads 0 and the backward leg 3 L/h; each endpoint holds its leg."""
    r = reversible(-3)
    assert r.read(N.net.link.actual_rate, 0) == -3
    assert r.read(N.net.link.forward.actual_rate, 0) == 0
    assert r.read(N.net.link.backward.actual_rate, 0) == 3
    assert (r.read(N.west.water, 1), r.read(N.east.water, 1)) == (13, 7)
    assert r.read(count(N.west.water.outflow.flows), 0) == 1
    assert r.read(fsum(N.west.water.inflow.flows.actual_rate), 0) == 3
    assert r.read(N.west.water.outflow.actual_rate, 0) == 0


def test_reversible_route_at_zero():
    r = reversible(0)
    assert r.read(N.net.link.forward.actual_rate, 0) == r.read(N.net.link.backward.actual_rate, 0) == 0


def three_requests(cap_at):
    m = Model()
    seven = lit(7)
    m.entity(
        'a',
        fields=[
            value(
                'water',
                1000,
                0,
                1000,
                outflow=Endpoint(request=lit(10), capacity=seven if cap_at == 'source' else None),
            )
        ],
    )
    m.entity(
        'b',
        fields=[
            value(
                'water',
                0,
                0,
                1000,
                inflow=Endpoint(request=lit(6), capacity=seven if cap_at == 'sink' else None),
            )
        ],
    )
    m.entity(
        'net', flows=[flow('pipe', N.a.water, N.b.water, request=8, capacity=7 if cap_at == 'pipe' else None)]
    )
    return Run(m, horizon=1).run()


def test_one_pipe_three_requests():
    """The source, the pipe and the sink request 10, 8 and 6 L/h: the least transfer serving all is 10."""
    r = three_requests(None)
    assert r.read(N.net.pipe.actual_rate, 0) == 10
    assert (r.read(N.b.water, 1), r.read(N.a.water, 1)) == (10, 990)


@pytest.mark.parametrize('cap_at', ['source', 'pipe', 'sink'])
def test_one_pipe_capped_at_seven(cap_at):
    """A hard cap of 7 L/h at any of the three scopes: 7 L/h, and shortfalls of 3, 1 and 0."""
    r = three_requests(cap_at)
    rate = r.read(N.net.pipe.actual_rate, 0)
    assert rate == 7
    assert (10 - rate, 8 - rate, max(0, 6 - rate)) == (3, 1, 0)
    assert (r.read(N.a.water, 1), r.read(N.b.water, 1)) == (993, 7)


def test_junction_carries_through_a_store_held_at_zero():
    """A junction carries 8 W through a store held at [0, 0] Wh."""
    m = Model()
    m.entity(
        'junction',
        fields=[value('power', 0, 0, 0)],
        flows=[flow('supply', SOURCE, this.power, capacity=8), flow('use', this.power, SINK, request=8)],
    )
    r = Run(m, horizon=1).run()
    assert r.read(N.junction.supply.actual_rate, 0) == r.read(N.junction.use.actual_rate, 0) == 8
    assert r.read(N.junction.power, 1) == 0
    c = r.conservation()
    assert c['from_source'] == c['to_sink'] == 8 and c['balanced']


def reservoir(alloc):
    m = Model()
    m.entity(
        'reservoir', fields=[value('water', 20, 0, 20, outflow=Endpoint(capacity=lit(10), allocation=alloc))]
    )
    m.entity('hospital', flows=[flow('delivery', N.reservoir.water, SINK, request=8)])
    m.entity('garden', flows=[flow('delivery', N.reservoir.water, SINK, request=12)])
    r = Run(m, horizon=3).run()
    return r, (r.read(N.hospital.delivery.actual_rate, 0), r.read(N.garden.delivery.actual_rate, 0))


@pytest.mark.parametrize(
    'alloc, expected',
    [(priority(N.hospital.delivery, N.garden.delivery), (8, 2)), (proportional(), (4, 6)), (None, (4, 6))],
    ids=['priority', 'proportional', 'default'],
)
def test_reservoir_limited_to_ten(alloc, expected):
    """A reservoir limited to 10 L/h, requests of 8 and 12: priority 8 and 2, proportional 4 and 6
    (the default); either way 20 L empty in 2 h."""
    r, got = reservoir(alloc)
    assert got == expected
    assert r.read(N.reservoir.water, 2) == 0
    assert 2 in [f.t for f in r.frames]


def test_common_sink_requests_once():
    """A sink requests 6 L/h from main and backup with priority(main, backup); main is capped at 4."""
    m = Model()
    m.entity(
        'clinic',
        fields=[
            value(
                'water',
                0,
                0,
                100,
                inflow=Endpoint(request=lit(6), allocation=priority(N.pipes.main, N.pipes.backup)),
            )
        ],
    )
    m.entity(
        'pipes',
        flows=[flow('main', SOURCE, N.clinic.water, capacity=4), flow('backup', SOURCE, N.clinic.water)],
    )
    r = Run(m, horizon=1).run()
    assert (r.read(N.pipes.main.actual_rate, 0), r.read(N.pipes.backup.actual_rate, 0)) == (4, 2)
    assert r.read(N.clinic.water.inflow.actual_rate, 0) == 6


def test_a_request_on_each_pipe_is_two_claims():
    """The contrast that the spec draws: 6 L/h requested on each pipe is two claims, 4 and 6."""
    m = Model()
    m.entity('clinic', fields=[value('water', 0, 0, 100)])
    m.entity(
        'pipes',
        flows=[
            flow('main', SOURCE, N.clinic.water, capacity=4, request=6),
            flow('backup', SOURCE, N.clinic.water, request=6),
        ],
    )
    r = Run(m, horizon=1).run()
    assert (r.read(N.pipes.main.actual_rate, 0), r.read(N.pipes.backup.actual_rate, 0)) == (4, 6)


def two_junctions(with_c=True, solver_over_four=False):
    """1 L/h reaches a junction with two pipes of 1 L/h: one serves A, one feeds a second junction
    where B (and C) request 1 L/h."""
    m = Model()
    m.entity(
        'first',
        fields=[value('water', 0, 0, 0)],
        flows=[
            flow('feed', SOURCE, this.water, capacity=1),
            flow('to_a', this.water, SINK, request=1),
            flow('onward', this.water, N.second.water, request=1),
        ],
    )
    ends = [flow('to_b', this.water, SINK, request=1)] + (
        [flow('to_c', this.water, SINK, request=1)] if with_c else []
    )
    m.entity('second', fields=[value('water', 0, 0, 0)], flows=ends)
    if solver_over_four:
        inputs = {'a': N.first.to_a, 'onward': N.first.onward, 'b': N.second.to_b, 'c': N.second.to_c}
        solve_for = [N.a.actual_rate, N.onward.actual_rate, N.b.actual_rate, N.c.actual_rate]
        m.entity('provider', solvers=[solver('share', inputs=inputs, solve_for=solve_for)])
    r = Run(m, horizon=1).run()
    names = [N.first.to_a, N.second.to_b] + ([N.second.to_c] if with_c else [])
    return tuple(r.read(x.actual_rate, 0) for x in names)


def test_two_junctions_share_locally():
    """The first junction sends half down each pipe; the second splits its half: 1/2, 1/4, 1/4.
    Without C, B gets 1/2: adding C changes B's share and not A's."""
    assert two_junctions() == (F(1, 2), F(1, 4), F(1, 4))
    assert two_junctions(with_c=False) == (F(1, 2), F(1, 2))


def test_two_junctions_under_one_solver_share_fairly():
    """One solver over the four requesting flows, with no objective: fair sharing across all of its
    claims gives 1/3 L/h to A, B and C."""
    assert two_junctions(solver_over_four=True) == (F(1, 3), F(1, 3), F(1, 3))


def test_upstream_supply_first_with_legs():
    """Local sharing across a flow with legs, worked by hand. x is empty and receives 1/h. Its
    outflow shares between a (1/h) and the leg x -> y of `feed` (1/h, with a second leg reserve ->
    used): 1/2 each. y, empty, splits its 1/2 between c and d: 1/4 each."""
    m = Model()
    for name in ('x', 'y', 'a', 'c', 'd', 'used'):
        m.entity(name, fields=[value('stock', 0, 0)])
    m.entity('reserve', fields=[value('stock', 100, 0)])
    m.entity(
        'net',
        flows=[
            flow('supply', SOURCE, N.x.stock, capacity=1),
            flow('a_flow', N.x.stock, N.a.stock, request=1),
            legs(
                'feed',
                leg('there', N.x.stock, N.y.stock, request=1),
                leg('use', N.reserve.stock, N.used.stock, request=1),
            ),
            flow('c_flow', N.y.stock, N.c.stock, request=1),
            flow('d_flow', N.y.stock, N.d.stock, request=1),
        ],
    )
    r = Run(m, horizon=1).run()
    got = {name: r.read(getattr(N, name).stock, 1) for name in ('x', 'y', 'a', 'c', 'd', 'used')}
    assert got == {'x': 0, 'y': 0, 'a': F(1, 2), 'c': F(1, 4), 'd': F(1, 4), 'used': F(1, 2)}


@pytest.mark.parametrize('order', [('x', 'y'), ('y', 'x')])
def test_a_flow_with_legs_spanning_two_endpoints(order):
    """x receives 0.6/h and y 1/h; a takes from x, c from y, and b has a leg at each. At x, a and b
    share 0.6: 0.3 each. b's leg at y is then held at 0.3, and c takes the rest of y: 0.7. The
    order in which x and y are declared changes nothing."""
    m = Model()
    for name in (*order, 'a', 'b', 'b_y', 'c'):
        m.entity(name, fields=[value('stock', 0, 0)])
    m.entity(
        'net',
        flows=[
            flow('sx', SOURCE, N.x.stock, capacity=F(3, 5)),
            flow('sy', SOURCE, N.y.stock, capacity=1),
            flow('a_flow', N.x.stock, N.a.stock, request=1),
            legs(
                'b_flow',
                leg('at_x', N.x.stock, N.b.stock, request=1),
                leg('at_y', N.y.stock, N.b_y.stock, request=1),
            ),
            flow('c_flow', N.y.stock, N.c.stock, request=1),
        ],
    )
    r = Run(m, horizon=1).run()
    got = {name: r.read(getattr(N, name).stock, 1) for name in ('x', 'y', 'a', 'b', 'b_y', 'c')}
    assert got == {'x': 0, 'y': 0, 'a': F(3, 10), 'b': F(3, 10), 'b_y': F(3, 10), 'c': F(7, 10)}


def restore(labor, work, plan=()):
    m = Model()
    m.entity(
        'crew',
        fields=[value('hours', 1000, 0, 1000, outflow=Endpoint(capacity=lit(2))), value('used', 0, 0, 1000)],
    )
    m.entity(
        'site',
        fields=[value('controls_work', 1000, 0, 1000), value('controls_done', 0, 0, 1000)],
        flows=[
            legs(
                'restore',
                leg('labor', N.crew.hours, N.crew.used, request=labor),
                leg('work', this.controls_work, this.controls_done, request=work),
            )
        ],
        events=[event('plan', steps=list(plan))],
    )
    m.setup = [start(N.site.plan)]
    return Run(m, horizon=3).run()


def served(r, at):
    s = N.site.restore
    return (r.read(s.served_fraction, at), r.read(s.labor.actual_rate, at), r.read(s.work.actual_rate, at))


@pytest.mark.parametrize(
    'labor, work, expected',
    [(4, 8, (F(1, 2), 2, 4)), (0, 8, (1, 0, 8)), (0, 0, (0, 0, 0))],
    ids=['half service', 'zero and eight', 'zero and zero'],
)
def test_legs(labor, work, expected):
    """Legs that request 4 and 8 with labor limited to 2: half service, 2 and 4. Legs that request
    0 and 8 with ample capacity: 0 and 8, fraction 1. Legs that request 0 and 0: fraction 0."""
    assert served(restore(labor, work), 0) == expected


def test_a_leg_request_that_crosses_zero():
    plan = [
        after(1, [set_(N.site.restore.labor.request, 0)]),
        after(1, [set_(N.site.restore.labor.request, 4)]),
    ]
    r = restore(4, 8, plan)
    assert [served(r, at) for at in (F(1, 2), F(3, 2), F(5, 2))] == [
        (F(1, 2), 2, 4),
        (1, 0, 8),
        (F(1, 2), 2, 4),
    ]
    assert r.read(N.site.controls_done, 3) == 4 + 8 + 4


def deliveries():
    deliver = event(
        'deliver', locals=[flow('pipe', this.water, SINK, request=formula(this.pace))], steps=[after(1, [])]
    )
    plan = event(
        'plan',
        steps=[
            after(1, [start(this.deliver)]),  # A runs from 1 h to 2 h
            after(F(3, 2), [set_(this.pace, 5)]),  # at 2.5 h the formula would now give 5
            after(F(1, 2), [set_(this.pace, 2), start(this.deliver)]),  # B runs from 3 h to 4 h
        ],
    )
    m = Model()
    m.entity('tank', fields=[value('water', 100, 0, 100), value('pace', 2)], events=[deliver, plan])
    m.setup = [start(N.tank.plan)]
    return Run(m, horizon=5).run()


def test_flows_created_during_a_run():
    """Deliveries A and B, each owning one pipe of 2 L/h: occurrences 0, 1, 1, 2; current flows 0,
    1, 0, 1. Between A and B the read through A gives its frozen 2 L/h."""
    r = deliveries()
    tank = N.tank
    row = (
        count(tank.deliver.occurrences),
        count(tank.water.outflow.flows),
        fsum(tank.water.outflow.flows.request),
    )
    got = [
        (*(r.read(x, at) for x in row), r.read(tank.water.outflow.actual_rate, at))
        for at in (0.5, 1.5, 2.5, 3.5)
    ]
    assert got == [(0, 0, 0, 0), (1, 1, 2, 2), (1, 0, 0, 0), (2, 1, 2, 2)]
    newest = tank.deliver.occurrences.at(t)
    assert r.read(newest.pipe.request, 2.5) == 2  # A's final request, though pace is now 5
    assert r.read(newest.pipe.actual_rate, 2.5) == 0
    assert r.read(newest.started, 3.5) == 3  # B, the newest start
    assert r.read(tank.water, 5) == 96


def shared_limit():
    deliver = event('deliver', locals=[flow('pipe', this.water, SINK, request=2)], steps=[after(2, [])])
    plan = event('plan', steps=[after(0, [start(this.deliver)]), after(1, [start(this.deliver)])])
    m = Model()
    m.entity(
        'tank',
        fields=[value('water', 100, 0, 100, outflow=Endpoint(capacity=lit(3)))],
        events=[deliver, plan],
    )
    m.setup = [start(N.tank.plan)]
    return m


def rates(r):
    return [
        [v for _, _, v in r.read(N.tank.water.outflow.flows.actual_rate, at).items]
        for at in (0.5, 1.5, 2.5, 3.5)
    ]


def test_a_shared_limit_as_occurrences_join_and_leave():
    """A shared limit of 3 L/h, each occurrence requests 2 L/h: A alone 2; A and B 1.5 each; B alone 2;
    then none."""
    r = Run(shared_limit(), horizon=4).run()
    assert rates(r) == [[2], [F(3, 2), F(3, 2)], [2], []]
    assert r.read(count(N.tank.water.outflow.flows), 3.5) == 0
    assert r.read(N.tank.water, 4) == 100 - (2 + 3 + 2)


def test_each_moment_equals_a_problem_formed_fresh():
    """The published rates equal those of a run that keeps no cache of earlier problems."""

    class NoCache(dict):
        def __setitem__(self, key, value):
            pass

    fresh = Run(shared_limit(), horizon=4)
    fresh.cache = NoCache()
    assert rates(fresh.run()) == rates(Run(shared_limit(), horizon=4).run())


def delivery_table(shared, b_at=0):
    """Two deliveries of 20 L at 10 L/h each, from a shared supply limited to 10 L/h or from batches."""
    if shared:
        locals_ = [flow('pipe', this.supply, N.dest.water, request=10)]
        wait = until(N.dest.water >= N.amount)
    else:
        locals_ = [value('batch', N.amount, 0, N.amount), flow('pipe', N.batch, N.dest.water, request=10)]
        wait = until(N.batch <= 0)
    deliver = event('deliver', params=['amount', 'dest'], locals=locals_, steps=[wait])
    plan = event(
        'plan', steps=[after(0, [start(this.deliver, 20, N.a)]), after(b_at, [start(this.deliver, 20, N.b)])]
    )
    m = Model()
    m.entity('a', fields=[value('water', 0, 0, 100)])
    m.entity('b', fields=[value('water', 0, 0, 100)])
    limit = Endpoint(capacity=lit(10)) if shared else None
    m.entity('site', fields=[value('supply', 40, 0, 40, outflow=limit)], events=[deliver, plan])
    m.setup = [start(N.site.plan)]
    r = Run(m, horizon=5).run()
    done = [e[1] for e in r.trace if e[0] == 'done' and e[2].startswith('site.deliver')]
    return r, done


def at_a_and_b(r, at):
    return r.read(N.a.water, at), r.read(N.b.water, at)


def test_delivery_table():
    """Separate batches: 10 and 10 at 1 h, both done at 2 h. A shared supply: 5 and 5, done at 4 h.
    B a hour later: 10 and 0 at 1 h, then 15/5, 20/10 and 20/20, done at 3 h and 4 h."""
    r, done = delivery_table(False)
    assert at_a_and_b(r, 1) == (10, 10) and done == [2, 2]
    r, done = delivery_table(True)
    assert at_a_and_b(r, 1) == (5, 5) and done == [4, 4]
    r, done = delivery_table(True, b_at=1)
    assert [at_a_and_b(r, h) for h in (1, 2, 3, 4)] == [(10, 0), (15, 5), (20, 10), (20, 20)]
    assert done == [3, 4] and r.conservation()['balanced']
