"""Case 5: one pipe and three requests (10, 8, 6): 10 L/h; a cap of 7 at any scope gives 7, shortfalls 3, 1, 0."""
import pytest

from ref import Endpoint, Model, N, flow, value
from ref.model import lit
from ref.run import Run


def build(cap_at):
    m = Model()
    m.entity('a', fields=[value('water', 1000, 0, 1000, outflow=Endpoint(request=lit(10), capacity=lit(7) if cap_at == 'source' else None))])
    m.entity('b', fields=[value('water', 0, 0, 1000, inflow=Endpoint(request=lit(6), capacity=lit(7) if cap_at == 'sink' else None))])
    m.entity('net', flows=[flow('pipe', N.a.water, N.b.water, request=8, capacity=7 if cap_at == 'pipe' else None)])
    return m


def test_no_cap():
    r = Run(build(None), horizon=1).run()
    assert r.read(N.net.pipe.actual_rate, 0) == 10
    assert r.read(N.b.water, 1) == 10 and r.read(N.a.water, 1) == 990


@pytest.mark.parametrize('cap_at', ['source', 'pipe', 'sink'])
def test_cap_seven(cap_at):
    r = Run(build(cap_at), horizon=1).run()
    rate = r.read(N.net.pipe.actual_rate, 0)
    assert rate == 7
    assert (10 - rate, 8 - rate, max(0, 6 - rate)) == (3, 1, 0)
    assert r.read(N.a.water, 1) == 993 and r.read(N.b.water, 1) == 7
