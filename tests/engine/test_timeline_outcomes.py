"""The outcomes of categorical draws (D1; `chance.py`).

A sampled draw takes the outcome whose share of (0, 1), in declared order, holds its uniform number:
the share of each outcome is the part of the uniform numbers that takes it, which exact fractions
give; outcomes that a guard bars give their share to the others in proportion. The expected values
are exact fractions.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from napkin.engine.timeline.chance import outcome
from napkin.program.refs import Distribution

UNITS = {'h': {'time': 1}}


@pytest.mark.parametrize(
    'weights',
    [
        {'A': Fraction(1, 2), 'B': Fraction(1, 2)},
        {'A': Fraction(1, 4), 'B': Fraction(1, 2), 'C': Fraction(1, 4)},
        {'A': Fraction(1, 8), 'B': Fraction(5, 8), 'C': Fraction(2, 8)},
    ],
)
def test_the_share_of_each_outcome_is_the_part_of_the_uniform_numbers_that_takes_it(weights):
    """At the midpoints (k + 1/2) / 512 of (0, 1), each outcome takes 512 times its weight of them."""
    names = tuple(weights)
    d = Distribution('categorical', tuple(float(w) for w in weights.values()), enum='E', outcomes=names)
    points = 512
    taken = [outcome(d, None, (k + 0.5) / points) for k in range(points)]
    assert {name: taken.count(name) for name in names} == {name: points * w for name, w in weights.items()}
    # The outcomes come in their declared order along (0, 1).
    assert taken == sorted(taken, key=names.index)


def test_barred_outcomes_give_their_share_to_the_others_in_proportion():
    """With A barred, B and C share (0, 1) as 5 to 2."""
    d = Distribution('categorical', (0.125, 0.625, 0.25), enum='E', outcomes=('A', 'B', 'C'))
    taken = [outcome(d, ('B', 'C'), (k + 0.5) / 700) for k in range(700)]
    assert (taken.count('B'), taken.count('C')) == (500, 200)
