"""Case 16: the horizon and a ramp. 7.5 L delivered and 12.5 L in transit at 1 h; 20 L and one completion at 2 h;
the falling ramp delivers 6.25 L by 2.5 h and the gate waits."""
from fractions import Fraction as F

from ref import Model, N, count, event, flow, fmax, formula, start, t, this, until, value
from ref.run import Run


def build(rate, change):
    receive = event('receive', params=['amount', 'starting_rate', 'rate_change'],
                    locals=[value('remaining', N.amount, 0, N.amount), value('started_at', t, readonly=True)],
                    flows=[flow('delivery', N.remaining, this.water,
                                request=formula(fmax(0, N.starting_rate + N.rate_change * (t - N.started_at))))],
                    steps=[until(N.remaining <= 0)])
    m = Model()
    m.entity('tank', fields=[value('water', 0, 0, 100)], events=[receive])
    m.setup = [start(N.tank.receive, 20, rate, change)]
    return m


DONE = count(N.tank.receive.occurrences.done)


def test_one_hour_horizon():
    r = Run(build(5, 5), horizon=1).run()
    assert r.view.t == 1
    assert r.read(N.tank.water) == F(15, 2)
    assert r.read(N.tank.receive.occurrences.at(t).remaining) == F(25, 2)
    assert r.read(count(N.tank.receive.occurrences)) == 1 and r.read(DONE) == 0
    assert r.conservation()['balanced']


def test_two_hour_horizon():
    r = Run(build(5, 5), horizon=2).run()
    assert r.read(N.tank.water) == 20
    assert r.read(DONE) == 1
    assert r.times('done') == [2]
    c = r.conservation()
    assert c['opening'] == 20 and c['balanced']  # the batch arrived from outside: an opening balance


def test_falling_ramp_waits():
    r = Run(build(5, -2), horizon=10).run()
    assert r.read(N.tank.water, F(5, 2)) == F(25, 4)
    assert r.read(N.tank.water, 10) == F(25, 4)
    assert r.read(DONE, 10) == 0
    assert r.read(N.tank.receive.occurrences.at(t).active, 10) is True
