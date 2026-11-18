"""Case 30: a flow that joins moves a crossing. 10 L, +1 L/h; an occurrence drains 2 L/h more from 2 h to 4 h;
`>= 16 L` fires at 10 h, not at 6 h (the prediction made at 0 h)."""
from ref import Model, N, SINK, SOURCE, after, event, flow, start, this, trigger, value
from ref.model import lit
from ref.run import Run


def test_crossing_moves():
    drain = event('drain', flows=[flow('out', this.water, SINK, request=2)], steps=[after(2, [])])
    alarm = event('alarm', triggers=[trigger(this.water >= 16, [start(this.alarm)], reset=('when', lit(False)))])
    plan = event('plan', steps=[after(2, [start(this.drain)])])
    m = Model()
    m.entity('tank', fields=[value('water', 10, 0, 100)], flows=[flow('fill', SOURCE, this.water, request=1)],
             events=[drain, alarm, plan])
    m.setup = [start(N.tank.plan)]
    r = Run(m, horizon=12).run()
    assert r.times('fire') == [10]
    assert r.read(N.tank.water, 6) == 12
    assert r.read(N.tank.water, 10) == 16
