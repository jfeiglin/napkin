"""A sum over the members of a list that one member at a time can change.

`Pairwise(values)` holds the sum of n numbers in a binary tree of a fixed shape: the leaves are the
numbers in their order, filled with zeros to a power of two, and each inner place holds the sum of the
two places below it. `total` is the root.

What holds:

- **The total reads the present values only.** The shape of the tree depends only on n, and each
  place is the float sum of the two below it. So two trees with the same values have the same total
  bit for bit, whatever the order and the number of the changes that led to those values. A running
  total that adds each change (`total += new - old`) does not have this property: its roundoff keeps
  the history.
- **A change of one member costs log2(n) additions** (`set`); a change of many members at once is
  one pass over the tree (`set_many`).
- **The error is that of a pairwise sum.** With u the unit roundoff, the total differs from the true
  sum by at most about `u * ceil(log2 n) * sum(abs(values))`, where a sum in the order of the list can
  differ by about `u * n * sum(abs(values))`.

The order of the additions is not the order of the list, so the total can differ from a sum in the
order of the list by that roundoff. The language promises no order of a sum over a list.
"""

from __future__ import annotations

import numpy as np

# Above this share of the members, a change of many is one pass over the whole tree.
REBUILD_SHARE = 0.05


class Pairwise:
    def __init__(self, values):
        values = np.asarray(values, dtype=float)
        self.count = n = len(values)
        self.size = size = 1 if n <= 1 else 1 << (n - 1).bit_length()
        self.tree = np.zeros(2 * size)
        self.tree[size : size + n] = values
        self._fill()

    def _fill(self):
        tree, level = self.tree, self.size
        while level > 1:
            half = level // 2
            tree[half:level] = tree[level : 2 * level : 2] + tree[level + 1 : 2 * level : 2]
            level = half

    @property
    def total(self):
        """The sum of the members."""
        return float(self.tree[1])

    def values(self):
        """The members, in their order (a view: do not write into it)."""
        return self.tree[self.size : self.size + self.count]

    def set(self, index, value):
        """Member `index` takes `value`."""
        if not 0 <= index < self.count:
            raise IndexError(index)
        tree, k = self.tree, self.size + index
        tree[k] = value
        k >>= 1
        while k:
            tree[k] = tree[2 * k] + tree[2 * k + 1]
            k >>= 1

    def set_many(self, index, values):
        """The members at the places `index` take `values`."""
        index = np.asarray(index, dtype=int)
        if len(index) > REBUILD_SHARE * self.count:
            self.tree[self.size + index] = values
            self._fill()
            return
        for i, value in zip(index.tolist(), np.broadcast_to(values, index.shape).tolist()):
            self.set(i, value)
