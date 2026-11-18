"""Case 18: the grinder's trigger and a manual 50 g start together bring 8 g to 108 g."""
from fractions import Fraction as F

from ref import Model, N, add, after, calc, count, event, set_, start, t, this, trigger, value
from ref.run import Run


def build(manual=True):
    refill = event('refill', params=['amount'], locals=[value('status', 'WEIGHING')],
                   triggers=[trigger(this.low_on_beans, [start(this.refill, 50)], reset=('when', this.beans >= 30))],
                   steps=[after(F(1, 2), [add(this.beans, N.amount), set_(N.status, 'ADDED')])])
    m = Model()
    m.entity('grinder', fields=[value('beans', 8), calc('low_on_beans', this.beans <= 10)], events=[refill])
    m.setup = [start(N.grinder.refill, 50)] if manual else []
    return m


def test_108_g():
    r = Run(build(), horizon=2).run()
    assert r.read(N.grinder.beans, 1) == 108
    assert r.read(count(N.grinder.refill.occurrences), 1) == 2
    assert r.times('fire') == [0]  # the manual start neither consumes nor resets the trigger
    assert r.read(N.grinder.refill.occurrences.at(t).status, 1) == 'ADDED'


def test_trigger_alone():
    r = Run(build(manual=False), horizon=2).run()
    assert r.read(N.grinder.beans, 1) == 58
