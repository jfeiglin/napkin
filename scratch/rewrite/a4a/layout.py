"""The layout that A4a proposes for members, links and flows across tables. A prototype.

Three things, each as plain arrays:

- `Pool`: the members of one template. A table gives one member for each row. A member has a row
  number in the pool, an id (the cell of the column `id`) and a creation number (its place in the
  file). Each field is one column over the rows. A link field is a column of row numbers of the pool
  that it links into, found once from the ids when the pool is built.
- `Stores`: every stored quantity of the model as one vector. The store `field` of the row `k` of a
  pool has the place `offset[pool, field] + k`. A flow names its two ends by these places, so a flow
  can join two rows of one pool, or rows of two pools, or a row and the outside (-1).
- `Network`: the flows as columns. `src[f]` and `dst[f]` are the places of the two ends of flow `f`.
  The incidence `B` (stores by flows, -1 at the source and +1 at the sink) is sparse. `out_of` and
  `into` are the same incidence by rows: the flows out of a store, and the flows into it.

The order of the rows in memory is the order of their ids, not the order of the file. So a file with
its rows in another order gives the same arrays, and the same results bit for bit. A table with no
column `id` keeps the order of its file.

Nothing here imports the package. `request_values` evaluates an expression node of
`napkin.core.expr` over the rows of a pool, with the package's own `napkin.core.arrays.values`,
when a caller gives it the two modules.
"""

from __future__ import annotations

import csv

import numpy as np
import scipy.sparse as sp

OUTSIDE = -1  # an end of a flow that is outside the model: SOURCE on the left, SINK on the right


class LayoutError(ValueError):
    """A table that cannot be a pool: the message names the table, the row and the cell."""


def read_table(path):
    """(the names of the columns, the unit of each or None, the rows as lists of cells)."""
    with open(path, newline='', encoding='utf-8-sig') as handle:
        rows = [[cell.strip() for cell in row] for row in csv.reader(handle)]
    names, units = [], []
    for cell in rows[0]:
        name, _, unit = cell.split('@')[0].partition(':')  # after `@`: the records of the column
        names.append(name.strip())
        units.append(unit.strip() or None)
    return names, units, rows[1:]


class Csr:
    """For each of `count` keys, the places that have that key: `of(k)` is a view, in the order of
    the places. It is the reverse of a column of keys: the flows out of each store, the rows that
    link to each row."""

    def __init__(self, keys, count):
        keys = np.asarray(keys)
        inside = np.flatnonzero(keys >= 0)
        order = inside[np.argsort(keys[inside], kind='stable')]
        self.items = order.astype(np.int32)
        self.start = np.searchsorted(keys[order], np.arange(count + 1)).astype(np.int64)

    def of(self, k):
        return self.items[self.start[k] : self.start[k + 1]]

    def counts(self):
        return np.diff(self.start)


class Pool:
    """The members of one template."""

    def __init__(self, name, ids, created=None):
        self.name = name
        self.n = len(ids)
        self.ids = list(ids)
        self.row_of = {key: k for k, key in enumerate(self.ids)}
        if len(self.row_of) != self.n:
            seen = set()
            twice = next(key for key in self.ids if key in seen or seen.add(key))
            raise LayoutError(f'{name}: two rows have the id {twice}')
        # The creation number of each row: its place in the file, from 0. It is the natural key of a
        # member, for `.at(...)` and for the order of equal ranks. It is no place in memory.
        self.created = np.arange(self.n) if created is None else np.asarray(created)
        self.cols = {}  # field -> a column of numbers or of yes/no, in execution units
        self.units = {}  # field -> the unit that the header of its column writes
        self.links = {}  # field -> (the pool that it links into, the row of that pool for each row)
        self._back = {}

    @classmethod
    def from_csv(cls, name, path, canonical=True):
        """The pool of a table. With `canonical`, and a column `id`, the rows are kept in the order
        of their ids. The cells of the other columns stay texts in `cells` until `number`,
        `flag` or `link` reads a column."""
        names, units, rows = read_table(path)
        if 'id' in names:
            at = names.index('id')
            ids = [row[at] for row in rows]
            for k, key in enumerate(ids, 1):
                if not key:
                    raise LayoutError(f'{name}: row {k} has no id')
        else:
            ids = [str(k) for k in range(1, len(rows) + 1)]
            canonical = False
        order = sorted(range(len(rows)), key=ids.__getitem__) if canonical else list(range(len(rows)))
        pool = cls(name, [ids[k] for k in order], created=np.array(order, dtype=np.int64))
        pool.cells = {field: [rows[k][j] for k in order] for j, field in enumerate(names)}
        pool.units = dict(zip(names, units))
        return pool

    def number(self, field, scale=1.0):
        """The column `field` as numbers, times the scale of its unit."""
        try:
            column = np.array(self.cells[field], dtype=float) * scale
        except ValueError:
            k = next(k for k, cell in enumerate(self.cells[field]) if not _is_number(cell))
            raise LayoutError(
                f'{self.name}.{self.ids[k]}: the cell {self.cells[field][k]!r} of {field} is no number'
            ) from None
        self.cols[field] = column
        return column

    def flag(self, field):
        cells = self.cells[field]
        wrong = next((k for k, cell in enumerate(cells) if cell not in ('true', 'false')), None)
        if wrong is not None:
            raise LayoutError(f'{self.name}.{self.ids[wrong]}: the cell {cells[wrong]!r} of {field} is not true or false')
        column = self.cols[field] = np.array([cell == 'true' for cell in cells])
        return column

    def link(self, field, target, table=None):
        """The link column `field`: each cell is `table.id`, and names one row of `target`."""
        prefix = (table or target.name) + '.'
        rows = np.empty(self.n, dtype=np.int32)
        row_of = target.row_of
        for k, cell in enumerate(self.cells[field]):
            if not cell.startswith(prefix) or cell[len(prefix) :] not in row_of:
                raise LayoutError(
                    f'{self.name}.{self.ids[k]}: the cell {cell!r} of {field} names no row of {prefix[:-1]}'
                )
            rows[k] = row_of[cell[len(prefix) :]]
        self.links[field] = (target, rows)
        return rows

    def back(self, field):
        """The reverse of a link: for each row of the pool that it links into, the rows that link
        to it. It serves `where(field == this)` and the readers of a value through the link."""
        if field not in self._back:
            target, rows = self.links[field]
            self._back[field] = Csr(rows, target.n)
        return self._back[field]


def _is_number(cell):
    try:
        float(cell)
    except ValueError:
        return False
    return True


class Stores:
    """Every stored quantity as one vector."""

    def __init__(self):
        self.offset, self.fields, self.count = {}, [], 0

    def add(self, pool, field):
        self.offset[pool.name, field] = self.count
        self.fields.append((pool, field, self.count))
        self.count += pool.n
        return self.count - pool.n

    def place(self, pool, field, rows):
        """The places of the store `field` of some rows of a pool."""
        return self.offset[pool.name, field] + np.asarray(rows)

    def start(self):
        y = np.empty(self.count)
        for pool, field, at in self.fields:
            y[at : at + pool.n] = pool.cols[field]
        return y

    def name(self, place):
        """`pool.id.field` of a place: the name that a message or a report gives it."""
        for pool, field, at in self.fields:
            if at <= place < at + pool.n:
                return f'{pool.name}.{pool.ids[place - at]}.{field}'
        raise IndexError(place)


class Network:
    """The flows of a model, across pools. Each family of flows (one declaration of a template, such
    as `Route.carried`) adds one flow for each row of its owner."""

    def __init__(self, stores):
        self.stores = stores
        self.families = []  # (name, owner pool, the place of its first flow)
        self._src, self._dst = [], []
        self.count = 0

    def add(self, name, owner, src, dst):
        """One flow for each row of `owner`: `src` and `dst` are the places of its ends, one for
        each row, or OUTSIDE."""
        src = np.broadcast_to(np.asarray(src, dtype=np.int64), (owner.n,))
        dst = np.broadcast_to(np.asarray(dst, dtype=np.int64), (owner.n,))
        self.families.append((name, owner, self.count))
        self._src.append(src)
        self._dst.append(dst)
        self.count += owner.n
        return self.count - owner.n

    def finish(self):
        S, F = self.stores.count, self.count
        self.src = np.concatenate(self._src) if self._src else np.zeros(0, dtype=np.int64)
        self.dst = np.concatenate(self._dst) if self._dst else np.zeros(0, dtype=np.int64)
        flows = np.arange(F)
        out, into = self.src >= 0, self.dst >= 0
        self.B = sp.csr_array(
            (
                np.concatenate([-np.ones(out.sum()), np.ones(into.sum())]),
                (np.concatenate([self.src[out], self.dst[into]]), np.concatenate([flows[out], flows[into]])),
            ),
            shape=(S, F),
        )
        self.out_of = Csr(self.src, S)  # the flows out of each store
        self.into = Csr(self.dst, S)  # the flows into each store
        return self

    def flow_name(self, f):
        for name, owner, at in self.families:
            if at <= f < at + owner.n:
                return f'{owner.name}.{owner.ids[f - at]}.{name}'
        raise IndexError(f)

    def islands(self):
        """The connected sets of stores that flows join: (count, the set of each store)."""
        both = (self.src >= 0) & (self.dst >= 0)
        S = self.stores.count
        graph = sp.coo_array((np.ones(both.sum()), (self.src[both], self.dst[both])), shape=(S, S))
        return sp.csgraph.connected_components(graph, directed=False)


def request_values(node, pool, expr, arrays, registry, extra=None):
    """The value of an expression node for each row of a pool, with the evaluator of the package
    (`napkin.core.arrays.values`). A name `field` reads the column of the row. A name
    `link__field` reads the column of the row that the link names: one gather. `extra` gives the
    names that are no column: the time, and the stores as they are at a state."""
    env = {}
    for name in expr.names(node):
        if extra is not None and name in extra:
            env[name] = extra[name]
        elif '__' in name:
            link, _, field = name.partition('__')
            target, rows = pool.links[link]
            source = extra[target.name, field] if extra is not None and (target.name, field) in extra else target.cols[field]
            env[name] = source[rows]
        else:
            env[name] = pool.cols[name]
    found = arrays.values(node, env, registry, pool.n)
    return np.broadcast_to(np.asarray(found, dtype=float), (pool.n,))
