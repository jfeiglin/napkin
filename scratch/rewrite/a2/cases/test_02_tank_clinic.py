"""Case 2: tank and clinic. 3 L/h until the tank is empty at 2 h 40 min, then zero."""
from fractions import Fraction as F

from ref import Model, N, flow, value, SINK
from ref.run import Run


def build():
    m = Model()
    m.entity('tank', fields=[value('water', 8, 0, 20, readonly=True)])
    m.entity('clinic', flows=[flow('delivery', N.tank.water, SINK, capacity=5, request=3)])
    return m


def test_tank_empties_at_two_hours_forty():
    r = Run(build(), horizon=4).run()
    assert r.read(N.clinic.delivery.actual_rate, 0) == 3
    assert r.read(N.tank.water, 2) == 2
    assert F(8, 3) in [f.t for f in r.frames]
    assert r.read(N.tank.water, F(8, 3)) == 0
    assert r.read(N.clinic.delivery.actual_rate, F(8, 3)) == 0
    assert r.read(N.clinic.delivery.actual_rate, 4) == 0
    assert r.read(N.clinic.delivery.capacity, 4) == 5
    assert r.read(N.clinic.delivery.request, 4) == 3
    assert r.read(N.tank.water, 4) == 0
    assert r.conservation()['balanced']
