"""Case 12: water and electricity in one decision. Empty tank: fill 2 L/h, clinic 2, town 0. With 10 L in the
tank: 6 and 6 with no fill and no charge. Both requests withdrawn: everything idle."""
from fractions import Fraction as F

from ref import Model, N, SINK, SOURCE, flow, fmax, minimize, solver, this, value
from ref.run import Run


def build(water=0, requests=6):
    m = Model()
    m.scales = {'W': 1, 'L/h': 1}
    m.entity('tank', fields=[value('water', water, 0, 20)])
    m.entity('battery', fields=[value('energy', 0, 0, 4)], flows=[flow('charge', SOURCE, this.energy, capacity=1, dim='W')])
    m.entity('pump', flows=[flow('fill', SOURCE, N.tank.water, capacity=4, dim='L/h'),
                            flow('power', N.battery.energy, SINK, dim='W')])
    m.entity('clinic', flows=[flow('delivery', N.tank.water, SINK, request=requests, dim='L/h')])
    m.entity('town', flows=[flow('delivery', N.tank.water, SINK, request=requests, dim='L/h')])
    m.entity('provider', solvers=[solver(
        'distribution',
        inputs={'charge': N.battery.charge, 'motor': N.pump.power, 'fill': N.pump.fill,
                'clinic_use': N.clinic.delivery, 'town_use': N.town.delivery},
        solve_for=[N.charge.actual_rate, N.motor.actual_rate, N.fill.actual_rate, N.clinic_use.actual_rate,
                   N.town_use.actual_rate],
        constraints=[N.motor.actual_rate == N.fill.actual_rate * F(1, 2)],
        objective=[minimize(fmax(0, N.clinic_use.request - N.clinic_use.actual_rate)),
                   minimize(fmax(0, N.town_use.request - N.town_use.actual_rate)),
                   minimize(N.fill.actual_rate), minimize(N.charge.actual_rate)])])
    return m


PATHS = (N.pump.fill, N.clinic.delivery, N.town.delivery, N.battery.charge, N.pump.power)


def rates(**kw):
    r = Run(build(**kw), horizon=0).run()
    return tuple(r.read(p.actual_rate) for p in PATHS)


def test_empty_tank():
    assert rates() == (2, 2, 0, 1, 1)


def test_ten_litres():
    assert rates(water=10) == (0, 6, 6, 0, 0)


def test_withdrawn():
    assert rates(requests=0) == (0, 0, 0, 0, 0)
