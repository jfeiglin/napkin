"""The sum over a list that one member at a time can change (`napkin/engine/timeline/trees.py`).

The oracles: the exact sum of the same floats (`math.fsum`), the bound that the theory of a pairwise
sum gives for the error, and the property that the module promises and a running total does not have:
the total reads the present values only.
"""

import math
import random

import numpy as np
import pytest

from napkin.engine.timeline.trees import Pairwise


@pytest.mark.parametrize('count', [0, 1, 2, 3, 7, 8, 9, 100, 1023, 1024, 1025, 5000])
def test_the_total_is_the_sum_within_the_bound_of_a_pairwise_sum(count):
    choose = random.Random(count)
    values = [choose.uniform(-1, 1) * 10 ** choose.uniform(-6, 6) for _ in range(count)]
    tree = Pairwise(values)
    exact = math.fsum(values)
    depth = max(1, math.ceil(math.log2(max(count, 2))))
    bound = 2.0**-53 * depth * math.fsum(abs(value) for value in values)
    assert abs(tree.total - exact) <= bound
    assert list(tree.values()) == values


@pytest.mark.parametrize('seed', range(8))
def test_the_total_reads_the_present_values_only(seed):
    """After any changes, the total is that of a new tree of the present values, bit for bit. The
    values have very different sizes, so a total that adds each change would keep its history."""
    choose = random.Random(seed)
    count = choose.choice([5, 64, 300, 1000])
    values = [choose.uniform(-1, 1) * 10 ** choose.uniform(-9, 9) for _ in range(count)]
    tree, running = Pairwise(values), math.fsum(values)
    kept = False
    for _ in range(400):
        if choose.random() < 0.8:
            place, value = choose.randrange(count), choose.uniform(-1, 1) * 10 ** choose.uniform(-9, 9)
            running += value - values[place]
            values[place] = value
            tree.set(place, value)
        else:
            places = choose.sample(range(count), choose.randint(1, count))
            new = [choose.uniform(-1, 1) * 10 ** choose.uniform(-9, 9) for _ in places]
            for place, value in zip(places, new):
                running += value - values[place]
                values[place] = value
            tree.set_many(places, new)
        assert tree.total == Pairwise(values).total
        kept = kept or running != Pairwise(values).total
    # The counterexample: the running total of the same changes does not stay the sum of the values.
    assert kept


def test_a_change_of_one_member_touches_one_path_of_the_tree():
    values = np.arange(1.0, 1025.0)
    tree = Pairwise(values)
    before = tree.tree.copy()
    tree.set(600, -5.0)
    changed = np.flatnonzero(tree.tree != before)
    # The leaf and one place on each level above it: log2(1024) + 1.
    assert len(changed) == 11
    assert tree.total == values.sum() - 601.0 - 5.0
    with pytest.raises(IndexError):
        tree.set(1024, 0.0)
