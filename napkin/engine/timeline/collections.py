"""Reductions and keyed reads of collections: what a plan holds of each, and how a run computes it.

A collection is a list of entries, in the order of creation of their members (spec, "Collections,
keys and projections"). Each entry has its member, the `where` tests that keep it (one node over
engine names, or None), its key (an engine name after `by(field)`, else the member's row, its natural
key) and, after a projection, the engine name of the value that it projects. A `where` reads only
what is fixed for each member (links, inputs, the ends of flows; the program's check refuses the
rest), so which entries a collection keeps is fixed for the run and found at its start.

- `Reduction`: `sum`, `count`, `any`, `all`, `min` or `max` of a collection's kept entries. An empty
  `sum` is zero in its unit, `count` zero, `any` false and `all` true; `min` and `max` of an empty
  collection fail when they are read (D4). A sum adds in the shape of a pairwise tree
  (`trees.Pairwise`), so its bits depend on the present values only.
- `Keyed`: `.at(x)`, the value that the entry with the greatest key at or below x projects; of equal
  keys the one created later wins (`pools.Keys`). Below the first key, or on an empty collection, it
  fails when it is read. A key x that reads only fixed values gives a value fixed for the run; x
  that is the time `t` gives a value that changes only at the keys, its key times (`stepped`).

`reduced` and `looked_up` compute a value from the values of engine names (`value(name)`), at the
start of a run, in a family's rates and in the reader. `node_of` gives a component the node of a
reduction over its kept entries. `history_of` gives the pieces of a reduction over the histories of
its members: a sum of lines is a line, which two pairwise trees follow from moment to moment, and a
count or a least value of values that hold between moments is followed by an integer or by a tree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.record import Curve, Unavailable
from .pools import Keys
from .trees import Pairwise


@dataclass(frozen=True)
class Entries:
    """A collection while a plan resolves a path. For each entry: the point that its path has
    reached (`('member', id)`, `('flow', engine name)` of a flow or a connection, or `('value',
    engine name)`: a link step moves an entry to the linked member, a value step projects it), its
    where tests and its key."""

    template: str | None
    points: tuple
    tests: tuple[nodes.Node | None, ...]
    keys: tuple[str | int, ...]
    whole: bool = False  # every member of the template, in its order: `T.instances`

    @property
    def names(self):
        """The engine names of the projected values, or None while an entry names no value."""
        if all(point[0] == 'value' for point in self.points):
            return tuple(point[1] for point in self.points)
        return None


@dataclass(frozen=True)
class Reduction:
    """A reduction of a plan: its operation and, for each entry, its test and the engine name of the
    value that it projects (`names` None: `count` of members)."""

    name: str
    op: str
    tests: tuple[nodes.Node | None, ...]
    names: tuple[str, ...] | None
    spelled: str

    def reads(self):
        """The engine names that the reduction reads: its tests' and its members' values."""
        found = {name for test in self.tests if test is not None for name in nodes.names(test)}
        return (found | set(self.names or ())) - {'t'}


@dataclass(frozen=True)
class Keyed:
    """A keyed read `.at(x)` of a plan: for each entry its test, its key (an engine name, or the
    member's row) and the engine name of the value that it projects; `key` is the node of x, and
    `by_time` says that x is the time `t`."""

    name: str
    tests: tuple[nodes.Node | None, ...]
    keys: tuple[str | int, ...]
    names: tuple[str, ...]
    key: nodes.Node
    by_time: bool
    spelled: str

    def reads(self):
        """The engine names that the keyed read reads, besides the time."""
        found = {name for test in self.tests if test is not None for name in nodes.names(test)}
        found |= {key for key in self.keys if isinstance(key, str)} | set(self.names)
        return (found | set(nodes.names(self.key))) - {'t'}


def _known(value):
    """A value that a reduction can take: an `Unavailable` one raises its reason (D7)."""
    if isinstance(value, Unavailable):
        raise ExpressionError(value.reason)
    return value


def holds(node, value, units):
    """The value of a node over engine names, from the values of the names it reads."""
    env = {name: _known(value(name)) for name in nodes.names(node) if name != 't'}
    return evaluate(node, env, units)


def kept(tests, value, units):
    """The places of the entries whose tests hold."""
    return [k for k, test in enumerate(tests) if test is None or bool(holds(test, value, units))]


def combined(op, values, spelled):
    """The reduction `op` of the values of the kept entries (None for `count` of members, where
    `values` are the entries themselves)."""
    if op == 'count':
        return len(values) if values and values[0] is None else sum(1 for value in values if value)
    if op == 'any':
        return any(bool(value) for value in values)
    if op == 'all':
        return all(bool(value) for value in values)
    if op == 'sum':
        return Pairwise([float(value) for value in values]).total if values else 0.0
    if not values:
        raise ExpressionError(f'{spelled}: {op} of an empty collection has no value')
    return min(values) if op == 'min' else max(values)


def reduced(reduction, value, units, entries=None):
    """The value of a reduction from the values of the names that it reads; `entries` are the kept
    entries when they are known."""
    entries = kept(reduction.tests, value, units) if entries is None else entries
    if reduction.names is None:
        return combined(reduction.op, [None] * len(entries), reduction.spelled)
    return combined(reduction.op, [_known(value(reduction.names[k])) for k in entries], reduction.spelled)


def index_of(keyed, value, units, entries=None):
    """The sorted index of the keys of the kept entries of a keyed read, and those entries."""
    entries = kept(keyed.tests, value, units) if entries is None else entries
    keys = [
        float(_known(value(keyed.keys[k]))) if isinstance(keyed.keys[k], str) else keyed.keys[k]
        for k in entries
    ]
    return Keys(keys), entries


def looked_up(keyed, value, units, t, index=None):
    """The value of a keyed read at time t (the time matters only to a read by the time)."""
    index, entries = index_of(keyed, value, units) if index is None else index
    env = {name: _known(value(name)) for name in nodes.names(keyed.key) if name != 't'}
    env['t'] = float(t)
    x = float(evaluate(keyed.key, env, units))
    place = index.find(x)
    if place is None:
        raise ExpressionError(f'{keyed.spelled}: no member has a key at or below {x:g}')
    return value(keyed.names[entries[place]])


def node_of(reduction, entries):
    """The node of a reduction over its kept entries, for the generated programs of a component.
    `min` and `max` of no entry have no node: the caller fails the run where a rate reads one."""
    op = reduction.op
    if reduction.names is None:
        return nodes.const(len(entries))
    names = [nodes.ref(reduction.names[k]) for k in entries]
    if op == 'count':
        if not names:
            return nodes.const(0)
        parts = [nodes.if_else(name, nodes.const(1), nodes.const(0)) for name in names]
        return parts[0] if len(parts) == 1 else nodes.call('sum', parts)
    if not names:
        empty = {'sum': 0.0, 'any': False, 'all': True}
        if op in empty:
            return nodes.const(empty[op])
        raise ExpressionError(f'{reduction.spelled}: {op} of an empty collection has no value')
    if len(names) == 1:
        return names[0]
    return nodes.call(op, names)


# ---- the history of a reduction ------------------------------------------------------------------


def _changes(histories, end):
    """The pieces of the members, merged by time: (time, member, value, rate), in time order and, at
    one time, in the order of the members and of their pieces."""
    found = []
    for k, pieces in enumerate(histories):
        for t, value, rate in pieces:
            if t <= end:
                found.append((t, k, value, rate))
    found.sort(key=lambda change: (change[0], change[1]))
    return found


def history_of(reduction, entries, histories, end):
    """The pieces (time, value, rate) of a reduction from the pieces of the values of its kept
    entries (`histories`, one list for each kept entry, as the recorder holds them), or None when no
    exact form applies (a curved piece, a value that is unavailable, a least value of lines): the
    recorder then fits the reduction as it fits a formula."""
    op, count = reduction.op, len(entries)
    if reduction.names is None or not entries:
        return None
    flat = [piece for pieces in histories for piece in pieces]
    if any(isinstance(rate, Curve) or isinstance(value, (str, Unavailable)) for _, value, rate in flat):
        return None
    changes = _changes(histories, end)
    if op == 'sum':
        if any(isinstance(value, bool) for _, value, _ in flat):
            return None
        # Each member is a line: value(t) = intercept + rate * t. Two trees hold the intercepts and
        # the rates, so the sum at a time reads the present lines only.
        intercepts, rates = Pairwise(np.zeros(count)), Pairwise(np.zeros(count))

        def lines(members, t, values, slopes):
            values, slopes = np.asarray(values, dtype=float), np.asarray(slopes, dtype=float)
            intercepts.set_many(members, values - slopes * t)
            rates.set_many(members, slopes)

        return _walk(changes, count, lines, lambda t: (intercepts.total + rates.total * t, rates.total))
    if any(rate != 0 for _, _, rate in flat):
        return None  # a count, an any or an all of values that move, or a least value of lines
    if op in ('count', 'any', 'all'):
        state = np.zeros(count, dtype=bool)
        total = [0]

        def flag(members, t, values, slopes):
            for k, value in zip(members, values):
                total[0] += int(bool(value)) - int(state[k])
                state[k] = bool(value)

        report = {
            'count': lambda t: (total[0], 0.0),
            'any': lambda t: (total[0] > 0, 0.0),
            'all': lambda t: (total[0] == count, 0.0),
        }[op]
        return _walk(changes, count, flag, report)
    tree = Pairwise(np.full(count, math.inf if op == 'min' else -math.inf), op)
    return _walk(
        changes,
        count,
        lambda members, t, values, slopes: tree.set_many(members, values),
        lambda t: (tree.total, 0.0),
    )


def _walk(changes, count, change, report):
    """The pieces of a reduction of `count` members: at each time at which a member has a piece,
    the changes at that time (`change(members, t, values, rates)`; of a member with two pieces at
    one time, the later), then the reduction there, once every member has a value."""
    pieces, seen, k = [], set(), 0
    while k < len(changes):
        t, at = changes[k][0], {}
        while k < len(changes) and changes[k][0] == t:
            _, member, value, rate = changes[k]
            at[member] = (value, rate)
            k += 1
        members = list(at)
        change(members, t, [at[member][0] for member in members], [at[member][1] for member in members])
        seen.update(members)
        if len(seen) == count:
            pieces.append((t, *report(t)))
    return pieces
