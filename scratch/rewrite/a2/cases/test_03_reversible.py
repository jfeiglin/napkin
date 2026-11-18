"""Case 3: a reversible route at -3 L/h: forward leg 0, backward leg 3; at zero both read zero."""
from ref import Model, N, count, fsum, route, value
from ref.run import Run


def build(req):
    m = Model()
    m.entity('west', fields=[value('water', 10, 0, 100)])
    m.entity('east', fields=[value('water', 10, 0, 100)])
    m.entity('net', flows=[route('link', N.west.water, N.east.water, request=req)])
    return m


def test_backward():
    r = Run(build(-3), horizon=1).run()
    assert r.read(N.net.link.actual_rate, 0) == -3
    assert r.read(N.net.link.forward.actual_rate, 0) == 0
    assert r.read(N.net.link.backward.actual_rate, 0) == 3
    assert r.read(N.west.water, 1) == 13 and r.read(N.east.water, 1) == 7
    # each endpoint collection holds the incident leg
    assert r.read(count(N.west.water.outflow.flows), 0) == 1
    assert r.read(fsum(N.west.water.inflow.flows.actual_rate), 0) == 3
    assert r.read(N.west.water.outflow.actual_rate, 0) == 0


def test_zero():
    r = Run(build(0), horizon=1).run()
    assert r.read(N.net.link.forward.actual_rate, 0) == 0
    assert r.read(N.net.link.backward.actual_rate, 0) == 0
