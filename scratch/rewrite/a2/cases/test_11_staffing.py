"""Case 11: staffing. 70 h and 30 h; with 80 h available, 56 h and 24 h."""
from fractions import Fraction as F

from ref import Model, N, calc, value
from ref.run import Run
from test_31_once_in_a_round import staffing


def result(hours):
    m = Model()
    m.entity('clinic', fields=[value('staff_hours', hours), calc('outreach_minimum', F(3, 10) * N.clinic.staff_hours)],
             solvers=[staffing()])
    r = Run(m, horizon=0).run()
    return r.read(N.clinic.staffing.care), r.read(N.clinic.staffing.outreach)


def test_hundred():
    assert result(100) == (70, 30)


def test_eighty():
    assert result(80) == (56, 24)
