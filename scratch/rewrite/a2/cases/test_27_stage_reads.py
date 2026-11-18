"""Case 27: inside a stage `x = 2` then `y = x` gives 2. Staff hours fall to 80 h: a delay of
`this.staffing.care` is 56 h (finished with the newly settled result)."""
from fractions import Fraction as F

from ref import Model, N, after, calc, event, set_, start, this, value
from ref.run import Run
from test_31_once_in_a_round import staffing


def test_sequential_reads_in_a_stage():
    m = Model()
    m.entity('box', fields=[value('x', 0), value('y', 0)],
             events=[event('go', steps=[after(1, [set_(this.x, 2), set_(this.y, this.x)])])])
    m.setup = [start(N.box.go)]
    r = Run(m, horizon=2).run()
    assert r.read(N.box.y, 2) == 2


def test_delay_reads_settled_result():
    go = event('go', steps=[after(1, [set_(this.staff_hours, 80)]), after(this.staffing.care, [])])
    m = Model()
    m.entity('clinic', fields=[value('staff_hours', 100), calc('outreach_minimum', F(3, 10) * this.staff_hours)],
             events=[go], solvers=[staffing()])
    m.setup = [start(N.clinic.go)]
    r = Run(m, horizon=100).run()
    assert r.times('done') == [57]
