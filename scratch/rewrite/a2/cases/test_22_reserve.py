"""Case 22: reserving a delivery, both versions of the spec."""
from fractions import Fraction as F

from ref import Model, N, SINK, after, event, flow, formula, link, move, none, set_, start, this, until, value
from ref.run import Run


def build(version):
    if version == 1:
        deliver = event('deliver', params=['amount', 'setup'], locals=[value('batch', 0, 0, N.amount)],
                        flows=[flow('delivery', N.batch, this.customer.water, request=formula(this.delivery_request))],
                        steps=[after(N.setup, [move(N.amount, this.supply, N.batch)]), until(N.batch <= 0)])
        args = (10, 1)
    else:
        deliver = event('deliver', params=['amount', 'target_rate', 'setup'], locals=[value('batch', 0, 0, N.amount)],
                        flows=[flow('delivery', N.batch, this.customer.water, capacity=0, request=N.target_rate)],
                        steps=[after(0, [move(N.amount, this.supply, N.batch)]),
                               after(N.setup, [set_(N.delivery.capacity, none)]), until(N.batch <= 0)])
        args = (10, 5, 1)
    m = Model()
    m.entity('home', fields=[value('water', 0, 0, 100)])
    m.entity('depot', fields=[value('supply', 12, 0, 100), value('delivery_request', 5), link('customer', 'home')],
             flows=[flow('other', this.supply, SINK, request=1)], events=[deliver])
    m.setup = [start(N.depot.deliver, *args)]
    return m


def test_move_after_setup():
    r = Run(build(1), horizon=5).run()
    assert r.read(N.depot.supply, 1) == 1  # 12 - 1 h of the other consumer - 10 reserved at 1 h
    assert r.read(N.home.water, 2) == 5
    assert r.times('done') == [3]
    assert r.read(N.home.water, 5) == 10
    assert r.conservation()['balanced']


def test_reserve_at_outset():
    r = Run(build(2), horizon=5).run()
    assert r.read(N.depot.supply, 0) == 2  # reserved at once
    assert r.read(N.home.water, 1) == 0  # capacity 0 during setup
    assert r.read(N.home.water, 2) == 5
    assert r.times('done') == [3]
    assert r.read(N.depot.supply, 5) == 0  # the other consumer drained what was left, at 2 h
    assert r.conservation()['balanced']
