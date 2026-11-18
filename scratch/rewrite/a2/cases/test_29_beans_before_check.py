"""Case 29: beans go from 8 g to 12 g before the round's trigger check: `beans <= 10 g` is false."""
from fractions import Fraction as F

from ref import Model, N, add, after, calc, event, set_, start, this, trigger, value
from ref.run import Run


def build(two_stages):
    refill = event('refill', triggers=[trigger(this.low_on_beans, [start(this.refill)], reset=('when', this.beans >= 30))])
    if two_stages:
        extra = [event('use', steps=[after(1, [set_(this.beans, 8)])]), event('top', steps=[after(1, [add(this.beans, 4)])])]
        setup = [start(N.grinder.use), start(N.grinder.top)]
    else:
        extra = [event('use', steps=[after(1, [set_(this.beans, 8), add(this.beans, 4)])])]
        setup = [start(N.grinder.use)]
    m = Model()
    m.entity('grinder', fields=[value('beans', 20), calc('low_on_beans', this.beans <= 10)], events=[refill] + extra)
    m.setup = setup
    return m


def test_two_stages_of_one_round():
    r = Run(build(True), horizon=2).run()
    assert r.read(N.grinder.beans, 1) == 12
    assert r.times('fire') == []


def test_one_stage():
    r = Run(build(False), horizon=2).run()
    assert r.times('fire') == []
