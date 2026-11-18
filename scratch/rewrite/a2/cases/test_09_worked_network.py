"""Case 9: the worked network. The four rows of rates; levels (8/3, -4/3, -4/3) and (3, -3, 0); requests 2 W and
6 W with 4 W of supply give 1 W and 3 W; the same model in kW gives 0.004 kW; a reordered table changes no
named result."""
from fractions import Fraction as F

import pytest

from ref import (Model, N, SINK, SOURCE, add, after, all_, calc, event, flow, fmax, fsum, inp, link, lit, minimize,
                 route, set_, solver, start, t, this, trigger, value)
from ref.model import Field
from ref.run import Run

PLACES = [('junction', 8, 0, False), ('clinic', 0, 6, True), ('garden', 0, 6, False)]
ROUTES = [('junction_clinic', 'sites.junction', 'sites.clinic', False),
          ('garden_junction', 'sites.garden', 'sites.junction', True)]
READINGS = [(0, 1), (1, F(1, 2)), (2, 1)]


def build(clinic_first=False, unit=1, places=PLACES, routes=ROUTES, readings=READINGS):
    m = Model()
    m.template('Reading', fields=[inp('hour', 0), inp('factor', 1)])
    m.template('Place', fields=[
        inp('base_need', 0), inp('supply_limit', 0), inp('critical', False),
        value('level', 0, -30, 30), value('power', 0, 0, 0),
        calc('unmet', fmax(0, this.use.request - this.use.actual_rate))],
        flows=[flow('supply', SOURCE, this.power, capacity=this.supply_limit),
               flow('use', this.power, SINK, request=__import__('ref').formula(
                   this.base_need * N.Reading.instances.by(N.hour).at(t).factor))])
    close = event('close', triggers=[trigger(this.closes_at_two & (t >= 2), [start(this.close)], reset=('when', lit(False)))],
                  steps=[after(0, [set_(this.up, False)])])
    m.template('Route', fields=[
        link('origin'), link('destination'), inp('strength', unit), inp('closes_at_two', False), value('up', True),
        calc('pull', __import__('ref').if_(this.up, this.strength, 0)),
        calc('rate_follows_levels', this.carried.actual_rate == this.pull * (this.origin.level - this.destination.level))],
        flows=[route('carried', this.origin.power, this.destination.power)], events=[close])
    for name, supply, need, critical in places:
        m.instance(f'sites.{name}', 'Place', supply_limit=supply * unit, base_need=need * unit, critical=critical)
    for name, a, b, closes in routes:
        m.instance(f'links.{name}', 'Route', origin=a, destination=b, closes_at_two=closes)
    for i, (hour, factor) in enumerate(readings):
        m.instance(f'readings.r{i}', 'Reading', hour=hour, factor=factor)
    objective = [minimize(fsum(N.places.unmet))]
    if clinic_first:
        objective.insert(0, minimize(fsum(N.places.where(N.critical).unmet)))
    m.entity('provider', solvers=[solver(
        'dispatch', inputs={'places': N.Place.instances, 'routes': N.Route.instances},
        solve_for=[N.places.level, N.places.supply.actual_rate, N.places.use.actual_rate, N.routes.carried.actual_rate],
        constraints=[all_(N.routes.rate_follows_levels)], objective=objective)])
    return m


def row(r, at):
    s, l = N.sites, N.links
    return (r.read(s.clinic.use.actual_rate, at), r.read(s.garden.use.actual_rate, at),
            r.read(s.junction.supply.actual_rate, at), r.read(l.junction_clinic.carried.actual_rate, at),
            r.read(l.garden_junction.carried.actual_rate, at))


def levels(r, at):
    return tuple(r.read(getattr(N.sites, p).level, at) for p in ('junction', 'clinic', 'garden'))


@pytest.fixture(scope='module')
def baseline():
    return Run(build(), horizon=3).run()


def test_rows(baseline):
    assert row(baseline, 0) == (4, 4, 8, 4, -4)
    assert row(baseline, 1) == (3, 3, 6, 3, -3)
    assert row(baseline, 2) == (6, 0, 6, 6, 0)
    assert baseline.times('fire') == [2]


def test_clinic_first():
    r = Run(build(clinic_first=True), horizon=0).run()
    assert row(r, 0) == (6, 2, 8, 6, -2)


def test_levels(baseline):
    assert levels(baseline, 0) == (F(8, 3), F(-4, 3), F(-4, 3))
    assert levels(baseline, 2) == (3, -3, 0)


def test_unequal_claims():
    places = [('junction', 4, 0, False), ('clinic', 0, 2, True), ('garden', 0, 6, False)]
    r = Run(build(places=places), horizon=0).run()
    assert row(r, 0)[:2] == (1, 3)


def test_kilowatts():
    r = Run(build(unit=F(1, 1000)), horizon=0).run()
    assert row(r, 0)[:2] == (F(4, 1000), F(4, 1000))
    assert levels(r, 0) == (F(8, 3), F(-4, 3), F(-4, 3))


def test_reordered_tables(baseline):
    r = Run(build(places=PLACES[::-1], routes=ROUTES[::-1], readings=READINGS[::-1]), horizon=3).run()
    for at in (0, 1, 2):
        assert row(r, at) == row(baseline, at)
        assert levels(r, at) == levels(baseline, at)
