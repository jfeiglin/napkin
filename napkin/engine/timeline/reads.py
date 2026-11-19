"""The names of an expression as its evaluation reads them (spec, "since(e) is an ordinary duration":
Boolean operators short-circuit left to right, and a conditional evaluates only its selected side).

The code of a node (`napkin/core/evaluation`) reads a name only where its evaluation gets to it: the
side of `a if c else b` that the test selects, and the terms of `and` and `or` up to the one that
decides. `Reads` is the environment that gives each name then, and not before: it reads the name
from the run (or from a record) when the evaluation first asks for it, and keeps it. So a read that
has no value, on a side that is not taken, never happens and fails nothing, and a draw there draws
nothing (`chance.py`). A value that is `Unavailable` (D7) raises its reason where it is read.

Each evaluation of an expression of the engine reads its names through `Reads`: in a stage, at an
entry, in a condition, in a setting or a formula of each way of running, in the test of a collection,
at the start of a run, and in the reader of a record. An evaluation over arrays (`napkin/core/arrays`)
asks for each column as it gets to it, so a column that no instance's branch reads is never made.

What an evaluation read is what it asked for: `Reads.found` (with `t`), which the reader of a record
keeps for each value at each time that it evaluates (`record.Reader`), so a report says exercised for
what a value read, and not for a side that it did not take. Of an evaluation that it did not see (a
rate, a guard or a condition that the run evaluated), a reader knows only what every evaluation of
the expression reads (`napkin.program.proofs.always`): the names outside the sides of a choice and
the later terms of `and`, `or` and a chain of comparisons.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.record import Unavailable

_MISSING = object()


class Reads(Mapping):
    """The names `names` of a node, each read with `read(name)` when the evaluation first asks for it,
    and the time `t` (none when `t` is None)."""

    __slots__ = ('found', 'names', 'read')

    def __init__(self, names, read, t=None):
        self.names, self.read = names, read
        self.found = {} if t is None else {'t': float(t)}

    def __getitem__(self, name):
        found = self.found.get(name, _MISSING)
        if found is _MISSING:
            if name not in self.names:
                raise KeyError(name)
            found = self.read(name)
            if isinstance(found, Unavailable):
                raise ExpressionError(found.reason)
            self.found[name] = found
        return found

    def __contains__(self, name):
        return name in self.found or name in self.names

    def __iter__(self):
        return iter({*self.found, *self.names})

    def __len__(self):
        return len({*self.found, *self.names})


def lazily(node, read, units, t=None):
    """The value of a node whose names are read with `read(name)` as its evaluation asks for them."""
    return evaluate(node, Reads(nodes.names(node), read, t), units)

