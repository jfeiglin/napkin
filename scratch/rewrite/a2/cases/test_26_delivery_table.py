"""Case 26: the delivery table of the pinned engine. Both deliveries request 10 L/h, 20 L each."""
from fractions import Fraction as F

from ref import Endpoint, Model, N, after, event, flow, start, this, until, value
from ref.model import lit
from ref.run import Run


def build(shared, b_at=0):
    if shared:
        deliver = event('deliver', params=['amount', 'dest'],
                        flows=[flow('pipe', this.supply, N.dest.water, request=10)], steps=[until(N.dest.water >= N.amount)])
    else:
        deliver = event('deliver', params=['amount', 'dest'], locals=[value('batch', N.amount, 0, N.amount)],
                        flows=[flow('pipe', N.batch, N.dest.water, request=10)], steps=[until(N.batch <= 0)])
    plan = event('plan', steps=[after(0, [start(this.deliver, 20, N.a)]), after(b_at, [start(this.deliver, 20, N.b)])])
    m = Model()
    m.entity('a', fields=[value('water', 0, 0, 100)])
    m.entity('b', fields=[value('water', 0, 0, 100)])
    m.entity('site', fields=[value('supply', 40, 0, 40, outflow=Endpoint(capacity=lit(10) if shared else None))],
             events=[deliver, plan])
    m.setup = [start(N.site.plan)]
    return m


def ab(r, at):
    return r.read(N.a.water, at), r.read(N.b.water, at)


def done(r):
    return [e[1] for e in r.trace if e[0] == 'done' and e[2].startswith('site.deliver')]


def test_separate_batches():
    r = Run(build(False), horizon=5).run()
    assert ab(r, 1) == (10, 10) and done(r) == [2, 2]


def test_shared_supply():
    r = Run(build(True), horizon=5).run()
    assert ab(r, 1) == (5, 5) and done(r) == [4, 4]


def test_shared_supply_b_later():
    r = Run(build(True, b_at=1), horizon=5).run()
    assert ab(r, 1) == (10, 0) and done(r) == [3, 4]
    assert [ab(r, h) for h in (2, 3, 4)] == [(15, 5), (20, 10), (20, 20)]
    assert r.conservation()['balanced']
