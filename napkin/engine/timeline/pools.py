"""Pools of members: each template's members as rows, its links as columns of row numbers, and the
indexes that collections read (R-A4a-01).

- `Pool`: the members of one template, in the order of the program (hand-written instances, then
  the rows of tables, each table in the order of its ids, R-A4a-02). A member's row is its creation
  number, the natural key of the member. A link field is a column of the rows that it names in its
  template, which the program gives (`Member.links`).
- `Csr`: for each of `count` keys, the places that have that key. `Pool.back(field)` is the reverse
  of a link column: for each row of the linked template, the rows that link to it, in their order.
  It serves `T.instances.where(field == this)` without a test of each pair.
- `Keys`: the sorted index of the keys of a collection for `.at(x)`: the member with the greatest
  key at or below x, and of equal keys the one created later (spec, "Collections, keys and
  projections"). The keys are sorted once, stably, so equal keys keep their order of creation.
"""

from __future__ import annotations

import numpy as np

from ...program import parts as p


class Csr:
    """For each of `count` keys, the places that have that key: `of(k)` is a view, in the order of
    the places. Places with a negative key are left out."""

    def __init__(self, keys, count):
        keys = np.asarray(keys, dtype=np.int64)
        inside = np.flatnonzero(keys >= 0)
        order = inside[np.argsort(keys[inside], kind='stable')]
        self.items = order.astype(np.int64)
        self.start = np.searchsorted(keys[order], np.arange(count + 1)).astype(np.int64)

    def of(self, k):
        """The places whose key is k."""
        return self.items[self.start[k] : self.start[k + 1]]


class Pool:
    """The members of one template as rows (see the module)."""

    def __init__(self, template, rows_of):
        self.template = template
        self.name = template.name
        self.ids = tuple(member.id for member in template.members)
        self.row_of = {id: row for row, id in enumerate(self.ids)}
        self.links = {}  # field -> (the linked template's name, the row that each member names)
        for value in template.values:
            if value.kind == p.LINK:
                target = value.type.template
                column = np.full(len(self.ids), -1, dtype=np.int64)
                for row, member in enumerate(template.members):
                    found = member.link(value.name)
                    if found is not None:
                        column[row] = found
                self.links[value.name] = (target, column)
        self._rows_of = rows_of  # the number of rows of each template, by name
        self._back = {}

    def __len__(self):
        return len(self.ids)

    def back(self, field):
        """The reverse of the link column `field` (`Csr` over the rows of the linked template)."""
        if field not in self._back:
            target, column = self.links[field]
            self._back[field] = Csr(column, self._rows_of[target])
        return self._back[field]


def pools_of(program):
    """{template name: Pool} of every template of a program."""
    counts = {template.name: len(template.members) for template in program.templates}
    return {template.name: Pool(template, counts) for template in program.templates}


class Keys:
    """The sorted index of a collection's keys (see the module). `keys` holds one number for each
    entry, in the order of creation of the entries."""

    def __init__(self, keys):
        keys = np.asarray(keys, dtype=float)
        self.order = np.argsort(keys, kind='stable')  # equal keys keep their order of creation
        self.sorted = keys[self.order]

    def find(self, x):
        """The entry with the greatest key at or below x (of equal keys the later), or None."""
        place = int(np.searchsorted(self.sorted, x, side='right')) - 1
        return None if place < 0 else int(self.order[place])

    def times(self):
        """The distinct keys, in order: the times at which a lookup by the time changes."""
        return np.unique(self.sorted)
