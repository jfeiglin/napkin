"""Declared solvers: the selection order of `spec.md` on the worked network, two bottlenecks,
staffing, water and electricity, a provider limit and the distance step, with the spec's numbers.
A request is soft and a capacity hard (decision D15)."""

from fractions import Fraction as F

import pytest

from tests.reference.model import (
    SINK,
    SOURCE,
    Model,
    N,
    after,
    all_,
    calc,
    event,
    flow,
    fmax,
    formula,
    fsum,
    if_,
    inp,
    link,
    lit,
    maximize,
    minimize,
    q,
    route,
    set_,
    solver,
    start,
    t,
    this,
    trigger,
    unknown,
    value,
)
from tests.reference.run import Run

PLACES = [('junction', 8, 0, False), ('clinic', 0, 6, True), ('garden', 0, 6, False)]
ROUTES = [
    ('junction_clinic', 'sites.junction', 'sites.clinic', False),
    ('garden_junction', 'sites.garden', 'sites.junction', True),
]
READINGS = [(0, 1), (1, F(1, 2)), (2, 1)]


def worked_network(clinic_first=False, unit='W', places=PLACES, routes=ROUTES, readings=READINGS):
    """The worked network of `spec.md`, its power inputs written in `unit`."""

    def power(watts):
        return q(F(watts) / {'W': 1, 'kW': 1000}[unit], unit)

    m = Model()
    m.template('Reading', fields=[inp('hour', 0), inp('factor', 1)])
    m.template(
        'Place',
        fields=[
            inp('base_need', 0),
            inp('supply_limit', 0),
            inp('critical', False),
            value('level', 0, -30, 30),
            value('power', 0, 0, 0),
            calc('need', this.base_need * N.Reading.instances.by(N.hour).at(t).factor),
            calc('unmet', fmax(0, this.use.request - this.use.actual_rate)),
        ],
        flows=[
            flow('supply', SOURCE, this.power, capacity=this.supply_limit),
            flow('use', this.power, SINK, request=formula(this.need), capacity=formula(this.need)),
        ],
    )
    close = event(
        'close',
        triggers=[trigger(this.closes_at_two & (t >= 2), [start(this.close)], reset=('when', lit(False)))],
        steps=[after(0, [set_(this.up, False)])],
    )
    m.template(
        'Route',
        fields=[
            link('origin'),
            link('destination'),
            inp('strength', power(1)),
            inp('closes_at_two', False),
            value('up', True),
            calc('pull', if_(this.up, this.strength, 0)),
            calc(
                'rate_follows_levels',
                this.carried.actual_rate == this.pull * (this.origin.level - this.destination.level),
            ),
        ],
        flows=[route('carried', this.origin.power, this.destination.power)],
        events=[close],
    )
    for name, supply, need, critical in places:
        m.instance(
            f'sites.{name}', 'Place', supply_limit=power(supply), base_need=power(need), critical=critical
        )
    for name, a, b, closes in routes:
        m.instance(f'links.{name}', 'Route', origin=a, destination=b, closes_at_two=closes)
    for i, (hour, factor) in enumerate(readings):
        m.instance(f'readings.r{i}', 'Reading', hour=hour, factor=factor)
    objective = [minimize(fsum(N.places.unmet))]
    if clinic_first:
        objective.insert(0, minimize(fsum(N.places.where(N.critical).unmet)))
    m.entity(
        'provider',
        solvers=[
            solver(
                'dispatch',
                inputs={'places': N.Place.instances, 'routes': N.Route.instances},
                solve_for=[
                    N.places.level,
                    N.places.supply.actual_rate,
                    N.places.use.actual_rate,
                    N.routes.carried.actual_rate,
                ],
                constraints=[all_(N.routes.rate_follows_levels)],
                objective=objective,
            )
        ],
    )
    return m


def rates(r, at, unit=None):
    s, links = N.sites, N.links
    paths = (
        s.clinic.use,
        s.garden.use,
        s.junction.supply,
        links.junction_clinic.carried,
        links.garden_junction.carried,
    )
    return tuple(r.read(p.actual_rate, at, unit=unit) for p in paths)


def levels(r, at):
    return tuple(r.read(getattr(N.sites, p).level, at) for p in ('junction', 'clinic', 'garden'))


@pytest.fixture(scope='module')
def baseline():
    return Run(worked_network(), horizon=3).run()


def test_worked_network_rows(baseline):
    """The four rows of rates: clinic use, garden use, junction supply, the two routes."""
    assert rates(baseline, 0) == (4, 4, 8, 4, -4)
    assert rates(baseline, 1) == (3, 3, 6, 3, -3)
    assert rates(baseline, 2) == (6, 0, 6, 6, 0)
    assert baseline.times('fire') == [2]
    assert rates(Run(worked_network(clinic_first=True), horizon=0).run(), 0) == (6, 2, 8, 6, -2)


def test_worked_network_levels(baseline):
    assert levels(baseline, 0) == (F(8, 3), F(-4, 3), F(-4, 3))
    assert levels(baseline, 2) == (3, -3, 0)


def test_worked_network_unequal_claims():
    """Requests of 2 W and 6 W with 4 W of supply: proportional service gives 1 W and 3 W."""
    places = [('junction', 4, 0, False), ('clinic', 0, 2, True), ('garden', 0, 6, False)]
    assert rates(Run(worked_network(places=places), horizon=0).run(), 0)[:2] == (1, 3)


def test_worked_network_in_kilowatts():
    """With inputs expressed in kW the two baseline deliveries are each 0.004 kW."""
    r = Run(worked_network(unit='kW'), horizon=0).run()
    assert rates(r, 0, unit='kW')[:2] == (F(4, 1000), F(4, 1000))
    assert levels(r, 0) == (F(8, 3), F(-4, 3), F(-4, 3))


def test_worked_network_reordered_tables(baseline):
    """Reordering every table changes no named result."""
    reordered = worked_network(places=PLACES[::-1], routes=ROUTES[::-1], readings=READINGS[::-1])
    r = Run(reordered, horizon=3).run()
    for at in (0, 1, 2):
        assert rates(r, at) == rates(baseline, at)
        assert levels(r, at) == levels(baseline, at)


def bottlenecks(objective):
    m = Model()
    m.template(
        'Consumer',
        fields=[calc('unmet', fmax(0, this.use.request - this.use.actual_rate))],
        flows=[flow('use', SOURCE, SINK, capacity=6, request=6)],
    )
    for name in 'abc':
        m.instance(name, 'Consumer')
    m.entity(
        'provider',
        solvers=[
            solver(
                'share',
                inputs={'consumers': N.Consumer.instances, 'a': N.a.use, 'b': N.b.use, 'c': N.c.use},
                solve_for=[N.consumers.use.actual_rate],
                constraints=[N.a.actual_rate + N.b.actual_rate <= 4, N.b.actual_rate + N.c.actual_rate <= 5],
                objective=[minimize(fsum(N.consumers.unmet))] if objective else [],
            )
        ],
    )
    r = Run(m, horizon=0).run()
    return tuple(r.read(x.use.actual_rate) for x in (N.a, N.b, N.c)), r.read(fsum(N.Consumer.instances.unmet))


def test_two_bottlenecks():
    """a + b <= 4 W and b + c <= 5 W: (2, 2, 3) W with no objective, 11 W unmet; (4, 0, 5) W with
    total unmet first, 9 W unmet."""
    assert bottlenecks(False) == ((2, 2, 3), 11)
    assert bottlenecks(True) == ((4, 0, 5), 9)


def staffing():
    """The clinic's staffing solver of `spec.md`."""
    return solver(
        'staffing',
        inputs={'available': this.staff_hours, 'minimum_outreach': this.outreach_minimum},
        solve_for=[unknown('care', 0, N.available), unknown('outreach', N.minimum_outreach, N.available)],
        constraints=[N.care + N.outreach == N.available],
        objective=[maximize(N.care)],
    )


@pytest.mark.parametrize('hours, expected', [(100, (70, 30)), (80, (56, 24))])
def test_staffing(hours, expected):
    m = Model()
    m.entity(
        'clinic',
        fields=[value('staff_hours', hours), calc('outreach_minimum', F(3, 10) * this.staff_hours)],
        solvers=[staffing()],
    )
    r = Run(m, horizon=0).run()
    assert (r.read(N.clinic.staffing.care), r.read(N.clinic.staffing.outreach)) == expected


def pump(water=0, requests=6):
    m = Model()
    m.entity('tank', fields=[value('water', water, 0, 20)])
    m.entity(
        'battery', fields=[value('energy', 0, 0, 4)], flows=[flow('charge', SOURCE, this.energy, capacity=1)]
    )
    m.entity(
        'pump', flows=[flow('fill', SOURCE, N.tank.water, capacity=4), flow('power', N.battery.energy, SINK)]
    )
    m.entity('clinic', flows=[flow('delivery', N.tank.water, SINK, request=requests)])
    m.entity('town', flows=[flow('delivery', N.tank.water, SINK, request=requests)])
    inputs = {
        'charge': N.battery.charge,
        'motor': N.pump.power,
        'fill': N.pump.fill,
        'clinic_use': N.clinic.delivery,
        'town_use': N.town.delivery,
    }
    objective = [
        minimize(fmax(0, N.clinic_use.request - N.clinic_use.actual_rate)),
        minimize(fmax(0, N.town_use.request - N.town_use.actual_rate)),
        minimize(N.fill.actual_rate),
        minimize(N.charge.actual_rate),
    ]
    solve_for = [
        N.charge.actual_rate,
        N.motor.actual_rate,
        N.fill.actual_rate,
        N.clinic_use.actual_rate,
        N.town_use.actual_rate,
    ]
    constraints = [N.motor.actual_rate == N.fill.actual_rate * q(0.5, 'Wh/L')]
    m.entity('provider', solvers=[solver('distribution', inputs, solve_for, constraints, objective)])
    r = Run(m, horizon=0).run()
    return tuple(
        r.read(p.actual_rate)
        for p in (N.pump.fill, N.clinic.delivery, N.town.delivery, N.battery.charge, N.pump.power)
    )


def test_pump_and_battery():
    """Empty stocks: fill 2 L/h, clinic 2 L/h, town 0 (charge and motor 1 W). With 10 L in the tank,
    6 and 6 with no fill and no charge. With both requests withdrawn, every transfer is idle."""
    assert pump() == (2, 2, 0, 1, 1)
    assert pump(water=10) == (0, 6, 6, 0, 0)
    assert pump(requests=0) == (0, 0, 0, 0, 0)


def provider(east_request=6, west_request=6, east_energy=0, horizon=0):
    m = Model()
    m.entity(
        'east_site',
        fields=[value('energy', east_energy, 0, 10)],
        flows=[flow('charge', SOURCE, this.energy, capacity=6, request=east_request)],
    )
    m.entity(
        'west_site',
        fields=[value('energy', 0, 0, 10)],
        flows=[flow('charge', SOURCE, this.energy, capacity=6, request=west_request)],
    )
    objective = [
        minimize(fmax(0, N.east.request - N.east.actual_rate)),
        minimize(fmax(0, N.west.request - N.west.actual_rate)),
        minimize(N.east.actual_rate + N.west.actual_rate),
    ]
    charging = solver(
        'charging',
        inputs={'east': N.east_site.charge, 'west': N.west_site.charge, 'limit': this.contract_limit},
        solve_for=[N.east.actual_rate, N.west.actual_rate],
        constraints=[N.east.actual_rate + N.west.actual_rate <= N.limit],
        objective=objective,
    )
    m.entity('provider', fields=[value('contract_limit', 8)], solvers=[charging])
    return Run(m, horizon=horizon).run()


def charges(r, at=None):
    return r.read(N.east_site.charge.actual_rate, at), r.read(N.west_site.charge.actual_rate, at)


def test_provider_limit():
    """A contract limit of 8 W: 6 W and 2 W; with East asking 2 W, 2 W and 6 W; with East full, 0 and
    6 W. East filling during a run from 0 Wh at 6 W is full at 5/3 h, and then West draws 6 W."""
    assert charges(provider()) == (6, 2)
    assert charges(provider(east_request=2)) == (2, 6)
    assert charges(provider(east_energy=10)) == (0, 6)
    r = provider(horizon=3)
    assert r.read(N.east_site.energy, 2) == 10
    assert charges(r, 2) == (0, 6)


def charging(objective, capacity):
    m = Model()
    m.entity(
        'site',
        fields=[value('energy', 0, 0, 10)],
        flows=[flow('charge', SOURCE, this.energy, capacity=capacity, request=2)],
    )
    m.entity(
        'provider', solvers=[solver('charging', {'c': N.site.charge}, [N.c.actual_rate], objective=objective)]
    )
    r = Run(m, horizon=0).run()
    return r.read(N.site.charge.request), r.read(N.site.charge.capacity), r.read(N.site.charge.actual_rate)


def test_a_request_is_soft_and_a_capacity_hard():
    """Requested 2 W, permitted 6 W: an objective that ranks higher than the request makes 6 W useful.
    A capacity that follows the request holds the rate at 2 W; with no objective the final target is
    the request (decision D15)."""
    assert charging([maximize(N.c.actual_rate)], 6) == (2, 6, 6)
    assert charging([maximize(N.c.actual_rate)], formula(this.charge.request)) == (2, 2, 2)
    assert charging([], 6) == (2, 6, 2)


def pick(target, rows):
    m = Model()
    m.entity(
        'box',
        solvers=[
            solver('pick', solve_for=[unknown('x', init=target), unknown('y', init=target)], constraints=rows)
        ],
    )
    r = Run(m, horizon=0).run()
    return r.read(N.box.pick.x), r.read(N.box.pick.y)


@pytest.mark.parametrize('target, expected', [(0, (2, 2)), (5, (3, 3))])
def test_distance_step_with_a_band(target, expected):
    """4 <= x + y <= 6 in the distance step: targets (0, 0) give (2, 2); targets (5, 5) give (3, 3)."""
    assert pick(target, [N.x + N.y >= 4, N.x + N.y <= 6]) == expected


def test_distance_step_with_an_equality():
    """x + y == 1 with targets zero gives (1/2, 1/2), where a linear program may give (1, 0)."""
    assert pick(0, [N.x + N.y == 1]) == (F(1, 2), F(1, 2))
