"""Case 25: members that join and leave. Shared limit 3 L/h, 2 L/h per occurrence: 2; then 1.5 each; then 2; then nothing."""
from fractions import Fraction as F

from ref import Endpoint, Model, N, SINK, after, count, event, flow, start, this, value
from ref.model import lit
from ref.run import Run


def build():
    deliver = event('deliver', flows=[flow('pipe', this.water, SINK, request=2)], steps=[after(2, [])])
    plan = event('plan', steps=[after(0, [start(this.deliver)]), after(1, [start(this.deliver)])])
    m = Model()
    m.entity('tank', fields=[value('water', 100, 0, 100, outflow=Endpoint(capacity=lit(3)))], events=[deliver, plan])
    m.setup = [start(N.tank.plan)]
    return m


def test_membership():
    r = Run(build(), horizon=4).run()
    flows = N.tank.water.outflow.flows.actual_rate
    got = {}
    for at in (F(1, 2), F(3, 2), F(5, 2), F(7, 2)):
        c = r.read(flows, at)
        got[at] = [v for _, _, v in c.items]
    assert got[F(1, 2)] == [2]
    assert got[F(3, 2)] == [F(3, 2), F(3, 2)]
    assert got[F(5, 2)] == [2]
    assert got[F(7, 2)] == []
    assert r.read(count(N.tank.water.outflow.flows), F(7, 2)) == 0
    assert r.read(N.tank.water, 4) == 100 - (2 + 3 + 2)


def test_same_as_a_fresh_problem():
    """At each moment the published rates equal those of a run that forms its problem afresh (no cache)."""
    a = Run(build(), horizon=4).run()
    b = Run(build(), horizon=4)
    b.cache = _NoCache()
    b.run()
    for at in (F(1, 2), F(3, 2), F(5, 2), F(7, 2)):
        assert [v for _, _, v in a.read(N.tank.water.outflow.flows.actual_rate, at).items] == \
               [v for _, _, v in b.read(N.tank.water.outflow.flows.actual_rate, at).items]


class _NoCache(dict):
    def __setitem__(self, k, v):
        pass
