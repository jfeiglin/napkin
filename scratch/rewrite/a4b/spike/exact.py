"""A sum that members can join and leave, with a total that reads the present members only.

`ExactSum` keeps the exact sum of the numbers added so far, as a short list of doubles that do not
overlap (Shewchuk's expansion, the method of `math.fsum`). `add(x)` and `add(-x)` are exact, so a
member that leaves is gone without a trace: the total is the correctly rounded sum of the members
that are present, whatever the order and the number of the joins and leaves that led there.

A running total (`total += x`, then `total -= x`) does not have this property: its roundoff keeps
the history. A tree of pairwise sums (`timeline/trees.py`) has it only while each member keeps its
place, and a place is what a member that comes and goes does not have.
"""

from __future__ import annotations

import math


class ExactSum:
    __slots__ = ('partials',)

    def __init__(self, values=()):
        self.partials = []
        for value in values:
            self.add(value)

    def add(self, x):
        """Add x (a finite double) to the sum, exactly."""
        partials, i = self.partials, 0
        for y in partials:
            if abs(x) < abs(y):
                x, y = y, x
            high = x + y
            low = y - (high - x)
            if low:
                partials[i] = low
                i += 1
            x = high
        partials[i:] = [x]

    @property
    def value(self):
        """The double nearest to the exact sum."""
        return math.fsum(self.partials)


def total(values):
    """The correctly rounded sum of some doubles: what an `ExactSum` of them gives."""
    return math.fsum(values)
