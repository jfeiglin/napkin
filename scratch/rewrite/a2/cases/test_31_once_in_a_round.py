"""Case 31: once in a round. Two writes in one round make one solve; a trigger that reacts to the result
starts a second round and a second solve at the same time."""
from fractions import Fraction as F

from ref import (Model, N, add, after, calc, event, maximize, solver, start, sub, this, trigger, unknown, value)
from ref.model import lit
from ref.run import Run


def staffing():
    return solver('staffing', inputs={'available': this.staff_hours, 'minimum_outreach': this.outreach_minimum},
                  solve_for=[unknown('care', 0, N.available), unknown('outreach', N.minimum_outreach, N.available)],
                  constraints=[N.care + N.outreach == N.available], objective=[maximize(N.care)])


def build(react):
    cut = event('cut', steps=[after(1, [sub(this.staff_hours, 10)])])
    top_up = event('top_up', steps=[after(0, [add(this.staff_hours, 5)])],
                   triggers=[trigger(this.staffing.care <= 60, [start(this.top_up)], reset=('when', lit(False)))] if react else [])
    m = Model()
    m.entity('clinic', fields=[value('staff_hours', 100), calc('outreach_minimum', F(3, 10) * this.staff_hours)],
             events=[cut, top_up], solvers=[staffing()])
    m.setup = [start(N.clinic.cut), start(N.clinic.cut)]
    return m


def solves_at(r, at):
    return sum(1 for e in r.trace if e[0] == 'solve' and e[1] == at)


def test_two_writes_one_solve():
    r = Run(build(False), horizon=2).run()
    assert solves_at(r, 1) == 1
    assert r.read(N.clinic.staffing.care, 1) == 56


def test_reaction_second_round_second_solve():
    r = Run(build(True), horizon=2).run()
    assert solves_at(r, 1) == 2
    assert r.times('fire') == [1]
    assert r.read(N.clinic.staff_hours, 1) == 85
    assert r.read(N.clinic.staffing.care, 1) == F(119, 2)  # 0.7 * 85
