"""A check over a segment reads the branches that the segment ran on.

A pipe's limit is `2 L/h if the tank holds more than 2 L, else 1 L/h`, as a capacity, a solver's
hard row or a keyed table. The run drains the tank to 2 L, locates that moment, and switches the
limit there. The checks that a placement stays within the limit integrate it over the accepted
window of the present segment (`Stocks._over_capacity`, `MovingDeclared._moving_relation`). Read
as a fresh comparison at each time, the limit drops to 1 L/h about 1e-9 h before the located switch,
inside its band, where the tank's computed level first touches 2 L. The run itself carried 2 L/h to
the switch. The integral then met a step that the run never took, and whether QUADPACK gave up on
it depended on the platform's arithmetic (the Linux failure of `-0.5-capacity`).

So every integrand that the run certifies here is constant on its window: the segment's own branch
(`Way.held_value`, `integrate.branch_expression`), which only a located switch changes.

Whether a placement at the switch adds to the drain or takes from it is the sign of a roundoff
residue, which differs by platform; a placement that takes from it needs no capacity integral
(`Stocks._over_capacity` returns at `change <= 0`). So each check that the run makes, of either
sign, is also made once with an added amount, which always integrates the window. The cases of
one source together must check at least one window.
"""

from fractions import Fraction

import numpy as np
import pytest

from napkin.engine.timeline import declared, stocks
from tests.engine.test_declared_switches import (
    test_a_moving_solver_drains_at_the_incoming_rate_until_the_tank_reaches_two_litres as drain,
)

PLACEMENTS = [(False, 0), (True, 0), (False, -0.5), (False, -0.025), (False, 0.5)]
ADDED = Fraction(1, 2**60)  # an amount to add, far below anything the capacity could refuse


@pytest.mark.parametrize('source', ['constraint', 'capacity', 'keyed store'])
def test_a_limit_integrated_over_a_segment_keeps_the_branch_that_the_segment_ran_on(source, monkeypatch):
    windows = []
    for module in (stocks, declared):
        real = module.certified_amount

        def seen(rate, a, b, label, real=real):
            windows.append((case, a, b, sorted({float(rate(at)) for at in np.linspace(a, b, 17)})))
            return real(rate, a, b, label)

        monkeypatch.setattr(module, 'certified_amount', seen)
    checked = stocks.Stocks._over_capacity

    def both_signs(self, way, names, capacity, change, t, rates, interval):
        if change <= 0 and rates is None:
            checked(self, way, names, capacity, ADDED, t, rates, interval)
        return checked(self, way, names, capacity, change, t, rates, interval)

    monkeypatch.setattr(stocks.Stocks, '_over_capacity', both_signs)
    for case in PLACEMENTS:
        drain(source, *case)
    assert windows
    assert [w for w in windows if len(w[3]) > 1] == []
