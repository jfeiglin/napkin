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

import math
from collections.abc import Mapping
from functools import lru_cache

from ...core import expr as nodes
from ...core import ops
from ...core.errors import ExpressionError
from ...core.evaluation import COMPARISONS
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


@lru_cache(maxsize=1024)
def _choices(node):
    """Replace comparisons by reads of their answers. Their operands can then use the incoming
    or outgoing side, while the number computed on that branch uses the moment's exact time."""
    choices = {}
    made = {}
    pending = [node]
    while pending:
        part = pending[-1]
        if part in made:
            pending.pop()
            continue
        if isinstance(part, nodes.Compare) or nodes.membership(part) is not None:
            name = f'\0choice{len(choices)}'
            choices[name] = part
            made[part] = nodes.ref(name)
            continue
        missing = [child for child in part.children if child not in made]
        if missing:
            pending.extend(missing)
            continue
        if all(made[child] is child for child in part.children):
            made[part] = part
        else:
            fields = []
            for field in part.FIELDS:
                value = getattr(part, field)
                if isinstance(value, tuple):
                    value = tuple(made.get(each, each) for each in value)
                fields.append(made.get(value, value))
            made[part] = nodes.made(type(part), *fields)
    return made[node], choices


def on_side(node, read, units, t, probe, crossing, read_probe):
    """Read the number at t, with switches evaluated on the side towards probe. If two moving
    operands round to the same number there, compare them farther along their trajectories."""
    calculation, choices = _choices(node)
    if not choices:
        return lazily(node, read, units, t)
    farther = t + math.copysign(max(crossing, abs(probe - t)), probe - t)
    samples = {}

    def sample(operand, at):
        key = (operand, at)
        if key not in samples:
            reader = read if at == t else lambda other: read_probe(other, at)
            samples[key] = lazily(operand, reader, units, at)
        return samples[key]

    def compare(op, left, right):
        a, b = sample(left, probe), sample(right, probe)
        if a == b and not isinstance(a, bool | str):
            here, there = sample(left, t), sample(right, t)
            if here == there and a != here:
                # Both moved to the same adjacent number. Compare their motion on this side.
                a, b = sample(left, farther), sample(right, farther)
        return COMPARISONS[op][1](a, b)

    def value(name):
        if name not in choices:
            return read(name)
        choice = choices[name]
        membership = nodes.membership(choice)
        if membership is not None:
            choice, low, high = membership
            for operand in choices[name].args:
                sample(operand, probe)  # a membership evaluates all three arguments
            if compare('gt', low, high):
                raise ExpressionError(f'{ops.REVERSED}: [{sample(low, probe)!r}, {sample(high, probe)!r}]')
        return all(compare(op, a, b) for op, a, b in zip(choice.ops, choice.operands, choice.operands[1:]))

    return lazily(calculation, value, units, t)


def side_level(at, t, probe, crossing):
    """A store's adjacent value for a switch. When the smallest step of the clock rounds to the
    same level, take one step of the level in the direction its trajectory moves."""
    near = at(probe)
    level = at(t)
    if near != level:
        return near
    return math.nextafter(level, at(t + math.copysign(crossing, probe - t)))


def lazily(node, read, units, t=None):
    """The value of a node whose names are read with `read(name)` as its evaluation asks for them."""
    return evaluate(node, Reads(nodes.names(node), read, t), units)
