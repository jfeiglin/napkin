"""Reductions and keyed reads of collections: what a plan holds of each, and how a run computes it.

A collection is a list of entries, in the order of creation of their members (spec, "Collections,
keys and projections"). Each entry has its member, the `where` tests that keep it (one node over
engine names, or None), its key (an engine name after `by(field)`, else the member's row, its natural
key) and, after a projection, the engine name of the value that it projects. A `where` reads only
what is fixed for each member (links, inputs, the ends of flows; the program's check refuses the
rest). An enclosing operand or an occurrence argument can change, so selection reads its current value.

A `where` over flows (`MemberFilter`) tests the ends of each member: `item.source` and `item.sink` are the
stores at them, or none at SOURCE and SINK, and compare with `==` or `!=` by identity, as entities
do (spec, "What each scope can see": a connection reads its two endpoint identities). Each such
comparison is answered for each flow, so the test of an entry is the rest of the test, with those
answers in place. Over the flows of an endpoint whose members change in a run (`Dynamic`), the
answers are found as each member is read, from the ends of its connection, which never change.

- `Reduction`: `sum`, `count`, `any`, `all`, `min` or `max` of a collection's kept entries. An empty
  `sum` is zero in its unit, `count` zero, `any` false and `all` true; `min` and `max` of an empty
  collection fail when they are read (D4). A sum adds in the shape of a pairwise tree
  (`trees.Pairwise`), so its bits depend on the present values only.
- `Keyed`: `.at(x)`, the value that the entry with the greatest key at or below x projects; of equal
  keys the one created later wins (`pools.Keys`). Below the first key, or on an empty collection, it
  fails when it is read. x the time `t` on fixed keys selects its entry only at the keys, its key
  times (`Plan.stepped`); any other x, and keys that change, select it where the read is evaluated
  (`selected`). The keyed reads of one collection share its entries, its kept entries and, where
  the inputs fix its keys, its index (`Plan.lookup_reads`, `Run.index_for`).

`reduced` and `looked_up` compute a value from the values of engine names (`value(name)`), at the
start of a run, in a family's rates and in the reader. `node_of` gives a component the node of a
reduction over its kept entries. `history_of` gives the pieces of a reduction over the histories of
its members: a sum of lines is a line, which two pairwise trees follow from moment to moment, and a
count or a least value of values that hold between moments is followed by an integer or by a tree.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import islice

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...program.record import Curve, Unavailable
from .pools import Keys
from .reads import lazily
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


@dataclass(eq=False)
class MemberFilter:
    """A filter bound to each realized member. Cache its expression, whose operands remain live."""

    bind: Callable
    before: MemberFilter | None = None
    _nodes: dict = field(default_factory=dict)

    def node(self, point):
        if point not in self._nodes:
            self._nodes[point] = self.bind(point)
        return self._nodes[point]

    def keeps(self, point, value, units, t):
        if self.before is not None and not self.before.keeps(point, value, units, t):
            return False
        return bool(lazily(self.node(point), value, units, t))

    def reads(self, members):
        """Operands read by any of the filters on the supplied members."""
        found = self.before.reads(members) if self.before is not None else set()
        for point in members:
            found.update(nodes.names(self.node(point)))
        return found


@dataclass
class OccurrenceHistory(Sequence):
    """Occurrence points and their immutable start times, in creation order. A historical
    selection shares both arrays and limits its visible prefix."""

    points: list = field(default_factory=list)
    starts: list = field(default_factory=list)
    stop: int | None = None

    def __len__(self):
        return len(self.points) if self.stop is None else self.stop

    def __getitem__(self, index):
        places = range(len(self))[index]
        if isinstance(places, range):
            return [self.points[i] for i in places]
        return self.points[places]

    def __iter__(self):
        return islice(self.points, len(self))

    def append(self, owner, started):
        self.points.append(('occurrence', owner))
        self.starts.append(started)

    def prefix(self, count):
        return OccurrenceHistory(self.points, self.starts, count)

    def through(self, time):
        return self.prefix(bisect_right(self.starts, time, 0, len(self)))


@dataclass(frozen=True)
class Dynamic:
    """A reduction, lookup or latest start over event occurrences or active endpoint flows.
    Members retain creation order. An explicit rank replaces their natural creation or start key.
    Each projection reads its selected member in the state of the caller."""

    name: str
    op: str
    source: tuple
    steps: tuple[str, ...]
    spelled: str
    keep: MemberFilter | None = None
    key: nodes.Node | None = None  # None for the current time on a natural occurrence lookup
    by: str | None = None

    def controls(self, members, plan):
        """The names consulted to filter or select these members, before reading their values."""
        found = self.keep.reads(members) if self.keep else set()
        if self.key is not None:
            found.update(nodes.names(self.key))
        if self.op == 'at':
            if self.by is not None:
                found.update(plan.project(point, (self.by,)) for point in members)
            elif self.source[0] == 'occurrences' and self.key is not None:
                found.update(f'{point[1]}.started' for point in members)
        return found

    def member_at(self, members, plan, read, t, units):
        return member_at(
            members, self.source, self.key, read, units, t, self.spelled, plan, self.keep, self.by
        )

    def selected(self, members, value, units, t=None):
        """The members retained by the authored filter at this read."""
        return members if self.keep is None else [m for m in members if self.keep.keeps(m, value, units, t)]


def member_at(members, source, key, read, units, t, spelled, plan, keep=None, by=None, entering=None):
    """Greatest eligible key, with later creation winning a tie, across active flows or occurrences."""
    if entering is not None and (keep is not None or by is not None):
        members = [*members, entering]
        entering = None
    if keep is not None:
        members = [member for member in members if keep.keeps(member, read, units, t)]
    if source[0] == 'occurrences' and by is None:
        if key is None and entering is not None:
            return entering
        if key is None and len(members):
            return members[-1]
        if key is not None:
            limit = lazily(key, read, units, t)
            if entering is not None and t <= limit:
                return entering
            if isinstance(members, OccurrenceHistory):
                place = bisect_right(members.starts, limit, 0, len(members))
            else:
                # Filtering preserves start order, including creation order for equal starts.
                place = bisect_right(members, limit, key=lambda m: known(read(f'{m[1]}.started')))
            if place:
                return members[place - 1]
        raise ExpressionError(f'{spelled}: no occurrence has started at or before the requested time')
    limit = lazily(key, read, units, t)
    keys = [known(read(plan.project(m, (by,)))) if by is not None else plan.number(m[1]) for m in members]
    index = Keys(keys).find(limit)
    if index is None:
        raise ExpressionError(f'{spelled}: no member has a key at or below {limit}')
    return members[index]


def dynamic_value(dynamic, members, plan, value, t, units):
    """Evaluate a dynamic collection using the membership and value reader for this time."""
    op = dynamic.op
    if op == 'at':
        point = dynamic.member_at(members, plan, value, t, units)
        return known(value(plan.project(point, dynamic.steps)))
    members = dynamic.selected(members, value, units, t)
    if op == 'latest':
        if not members:
            raise ExpressionError(f'{dynamic.spelled}: the event has not started')
        return float(known(value(f'{members[-1][1]}.started')))
    if not dynamic.steps:
        return combined(op, [None] * len(members), dynamic.spelled)
    return combined(
        op, [known(value(plan.project(member, dynamic.steps))) for member in members], dynamic.spelled
    )


def known(value):
    """A value that a reduction can take: an `Unavailable` one raises its reason (D7)."""
    if isinstance(value, Unavailable):
        raise ExpressionError(value.reason)
    return value


def holds(node, value, units):
    """The value of a node over engine names, from the values of the names that its evaluation reads
    (`reads.py`)."""
    return lazily(node, value, units)


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
    return combined(reduction.op, [known(value(reduction.names[k])) for k in entries], reduction.spelled)


def index_of(keyed, value, units, entries=None):
    """The sorted index of the keys of the kept entries of a keyed read, and those entries."""
    entries = kept(keyed.tests, value, units) if entries is None else entries
    keys = [
        float(known(value(keyed.keys[k]))) if isinstance(keyed.keys[k], str) else keyed.keys[k]
        for k in entries
    ]
    return Keys(keys), entries


def selected(keyed, value, units, t, index=None):
    """The entry that a keyed read selects at time t (the place of its member), or None below its
    first key: the time matters to a key that reads it."""
    index, entries = index_of(keyed, value, units) if index is None else index
    place = index.find(float(lazily(keyed.key, value, units, t)))
    return None if place is None else entries[place]


def looked_up(keyed, value, units, t, index=None):
    """The value of a keyed read at time t (the time matters to a key that reads it)."""
    found = selected(keyed, value, units, t, index)
    if found is None:
        x = float(lazily(keyed.key, value, units, t))
        raise ExpressionError(f'{keyed.spelled}: no member has a key at or below {x:g}')
    return value(keyed.names[found])


def node_of(reduction, entries):
    """The node of a reduction over its kept entries, for the generated programs of a component.
    `min` and `max` of no entry have no node: the caller fails the run where a rate reads one."""
    if reduction.names is None:
        return nodes.const(len(entries))
    return aggregate_node(reduction.op, (reduction.names[k] for k in entries), reduction.spelled)


def guarded_reduction(reduction, fallback=None):
    """A reduction with changing membership is an ordinary formula.
    Each branch reads the projected field only while its member qualifies. Integration and
    event detection therefore see the same comparisons as point and historical evaluations."""
    op = reduction.op
    if fallback is None:
        fallback = nodes.const({'sum': 0, 'count': False, 'any': False, 'all': True}[op])
    parts = []
    for i, condition in enumerate(reduction.tests):
        member = nodes.const(True) if reduction.names is None else nodes.ref(reduction.names[i])
        parts.append(member if condition is None else nodes.if_else(condition, member, fallback))
    return _aggregate(op, parts, reduction.spelled)


def aggregate_node(op, members, spelled):
    """The scalar expression for an operation on its selected member names."""
    return _aggregate(op, [nodes.ref(name) for name in members], spelled)


def _aggregate(op, names, spelled):
    if op == 'count':
        if not names:
            return nodes.const(0)
        parts = [nodes.if_else(name, nodes.const(1), nodes.const(0)) for name in names]
        return parts[0] if len(parts) == 1 else nodes.call('sum', parts)
    if not names:
        empty = {'sum': 0.0, 'any': False, 'all': True}
        if op in empty:
            return nodes.const(empty[op])
        raise ExpressionError(f'{spelled}: {op} of an empty collection has no value')
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


def exact_member(op, value, rate):
    """Whether this member's current piece can participate in an exact reduction."""
    if isinstance(rate, Curve) or isinstance(value, (str, Unavailable)):
        return False
    return not isinstance(value, bool) if op == 'sum' else rate == 0


def history_of(reduction, entries, histories, end):
    """The pieces (time, value, rate) of a reduction from the pieces of the values of its kept
    entries (`histories`, one list for each kept entry, as the recorder holds them), or None when no
    exact form applies (a curved piece, a value that is unavailable, a least value of lines): the
    recorder then fits the reduction as it fits a formula."""
    op, count = reduction.op, len(entries)
    if reduction.names is None or not entries:
        return None
    flat = [piece for pieces in histories for piece in pieces]
    if any(not exact_member(op, value, rate) for _, value, rate in flat):
        return None
    changes = _changes(histories, end)
    if op == 'sum':
        # Each member is a line: value(t) = intercept + rate * t. Two trees hold the intercepts and
        # the rates, so the sum at a time reads the present lines only.
        intercepts, rates = Pairwise(np.zeros(count)), Pairwise(np.zeros(count))

        def lines(members, t, values, slopes):
            values, slopes = np.asarray(values, dtype=float), np.asarray(slopes, dtype=float)
            intercepts.set_many(members, values - slopes * t)
            rates.set_many(members, slopes)

        return _walk(changes, count, lines, lambda t: (intercepts.total + rates.total * t, rates.total))
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
