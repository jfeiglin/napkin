"""Case 21: a flow with legs. Labor limited to 2 gives fraction 0.5, rates 2 and 4. Leg requests (0, 8) give
(0, 8) and fraction 1. (0, 0) gives fraction 0. A request that crosses zero during a run stops no run."""
from ref import Endpoint, Model, N, after, event, leg, legs, set_, start, this, value
from ref.model import lit
from ref.run import Run


def build(labor, work, cap=2, plan=()):
    m = Model()
    m.entity('crew', fields=[value('hours', 1000, 0, 1000, outflow=Endpoint(capacity=lit(cap))), value('used', 0, 0, 1000)])
    m.entity('site', fields=[value('controls_work', 1000, 0, 1000), value('controls_done', 0, 0, 1000)],
             flows=[legs('restore', leg('labor', N.crew.hours, N.crew.used, request=labor),
                         leg('work', this.controls_work, this.controls_done, request=work))],
             events=[event('plan', steps=list(plan))])
    m.setup = [start(N.site.plan)]
    return m


def read3(r, at):
    return (r.read(N.site.restore.served_fraction, at), r.read(N.site.restore.labor.actual_rate, at),
            r.read(N.site.restore.work.actual_rate, at))


def test_labor_limited():
    r = Run(build(4, 8), horizon=1).run()
    assert read3(r, 0) == (0.5, 2, 4)


def test_zero_and_eight():
    r = Run(build(0, 8), horizon=1).run()
    assert read3(r, 0) == (1, 0, 8)


def test_all_zero():
    r = Run(build(0, 0), horizon=1).run()
    assert read3(r, 0) == (0, 0, 0)


def test_request_crosses_zero():
    plan = [after(1, [set_(N.site.restore.labor.request, 0)]), after(1, [set_(N.site.restore.labor.request, 4)])]
    r = Run(build(4, 8, plan=plan), horizon=3).run()
    assert read3(r, 0.5) == (0.5, 2, 4)
    assert read3(r, 1.5) == (1, 0, 8)
    assert read3(r, 2.5) == (0.5, 2, 4)
    assert r.read(N.site.controls_done, 3) == 4 + 8 + 4
