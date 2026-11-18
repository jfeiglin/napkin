"""Case 1: the grinder. 8 g, refill.start(50 g), 58 g after half an hour, low_on_beans false."""
from fractions import Fraction as F

from ref import Model, N, add, after, calc, event, start, this, value
from ref.run import Run


def build():
    m = Model()
    m.entity('grinder', fields=[value('beans', 8), calc('low_on_beans', this.beans <= 10, readonly=True)],
             events=[event('refill', params=['amount'], steps=[after(F(1, 2), [add(this.beans, N.amount)])])])
    m.setup = [start(N.grinder.refill, 50)]
    return m


def test_grinder():
    r = Run(build(), horizon=1).run()
    assert r.read(N.grinder.beans, 0) == 8
    assert r.read(N.grinder.low_on_beans, 0) is True
    assert r.read(N.grinder.beans, F(1, 2)) == 58
    assert r.read(N.grinder.low_on_beans, F(1, 2)) is False
    assert r.times('done') == [F(1, 2)]
