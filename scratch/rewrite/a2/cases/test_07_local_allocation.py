"""Case 7: local allocation. priority gives 8 and 2; proportional gives 4 and 6; both empty in 2 h."""
from ref.model import lit
from ref import Endpoint, Model, N, SINK, flow, priority, proportional, value
from ref.run import Run


def build(alloc):
    m = Model()
    m.entity('reservoir', fields=[value('water', 20, 0, 20, outflow=Endpoint(capacity=lit(10), allocation=alloc))])
    m.entity('hospital', flows=[flow('delivery', N.reservoir.water, SINK, request=8)])
    m.entity('garden', flows=[flow('delivery', N.reservoir.water, SINK, request=12)])
    return m


def rates(alloc):
    r = Run(build(alloc), horizon=3).run()
    return r, (r.read(N.hospital.delivery.actual_rate, 0), r.read(N.garden.delivery.actual_rate, 0))


def test_priority():
    r, got = rates(priority(N.hospital.delivery, N.garden.delivery))
    assert got == (8, 2)
    assert r.read(N.reservoir.water, 2) == 0
    assert 2 in [f.t for f in r.frames]


def test_proportional():
    r, got = rates(proportional())
    assert got == (4, 6)
    assert r.read(N.reservoir.water, 2) == 0


def test_default_is_proportional():
    r, got = rates(None)
    assert got == (4, 6)
