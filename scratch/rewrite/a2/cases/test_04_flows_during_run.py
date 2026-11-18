"""Case 4: flows created during a run. Counts 0, 1, 1, 2 and 0, 1, 0, 1; A's frozen request of 2 L/h."""
from fractions import Fraction as F

from ref import Model, N, SINK, after, count, event, flow, formula, fsum, set_, start, t, this, value
from ref.run import Run


def build():
    deliver = event('deliver', flows=[flow('pipe', this.water, SINK, request=formula(this.pace))], steps=[after(1, [])])
    plan = event('plan', steps=[after(1, [start(this.deliver)]),  # A runs 1 h to 2 h
                                after(F(3, 2), [set_(this.pace, 5)]),  # t = 2.5: the formula would now give 5
                                after(F(1, 2), [set_(this.pace, 2), start(this.deliver)])])  # B runs 3 h to 4 h
    m = Model()
    m.entity('tank', fields=[value('water', 100, 0, 100), value('pace', 2)], events=[deliver, plan])
    m.setup = [start(N.tank.plan)]
    return m


ROW = (count(N.tank.deliver.occurrences), count(N.tank.water.outflow.flows),
       fsum(N.tank.water.outflow.flows.request), N.tank.water.outflow.actual_rate)


def test_table():
    r = Run(build(), horizon=5).run()
    rows = [tuple(r.read(x, at) for x in ROW) for at in (F(1, 2), F(3, 2), F(5, 2), F(7, 2))]
    assert rows == [(0, 0, 0, 0), (1, 1, 2, 2), (1, 0, 0, 0), (2, 1, 2, 2)]


def test_frozen_request():
    r = Run(build(), horizon=5).run()
    pipe_request = N.tank.deliver.occurrences.at(t).pipe.request
    assert r.read(pipe_request, F(5, 2)) == 2  # A's final request, though pace is now 5
    assert r.read(N.tank.deliver.occurrences.at(t).pipe.actual_rate, F(5, 2)) == 0
    assert r.read(N.tank.deliver.occurrences.at(t).started, F(7, 2)) == 3  # B, the newest start
    assert r.read(N.tank.water, 5) == 96
