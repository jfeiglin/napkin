"""The columns of a run and its past: how a part reads a name, now or at an earlier time.

Moved from `run.py` with no change (step B0-6). `State` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from scipy.linalg import expm

from ...core import arrays, expr
from ...core.errors import ExpressionError
from ...expressions import names_in
from ..errors import SimulationError
from .plan import Outside
from .trees import Pairwise

ROOT_TOLERANCE = 1e-13
# How far the chances of an event's outcomes may miss 1 when it fires.
CHANCE_TOLERANCE = 1e-9
TRIGGER, FIRE = 1, 2
RULE, BOUND, ROOT, LIMIT, FLOOR, END = 0, 1, 2, 3, 4, 5
ONE = object()  # the one instance of a space of one
NEGATIVE = object()  # in the memo of an environment: a quantity with a flow that asks less than zero
POSITIVE = object()  # in the memo of an environment: the flows that deliver material at its state
SEEN = ('value', 'line', 'numeric', 'formula')  # the kinds of the names that a resolver reads


def _one(value):
    """The value of one instance from a result of `arrays.values`."""
    if isinstance(value, np.ndarray):
        return value.item(0)
    return value


def _spread(value, count):
    """A result of `arrays.values` as one value for each instance."""
    if isinstance(value, np.ndarray) and value.ndim == 1:
        return value
    return np.full(count, value)


def _pairwise(values):
    return Pairwise(values).total


@dataclass
class Trial:
    """The state of a numeric block that a solver tries: {name: values}. `whole`: the values are of
    every instance of the space of each name."""

    values: dict
    whole: bool


class Env:
    """The values that the parts of one space read at one time, for the instances `J` (None: all)."""

    __slots__ = ('J', 'count', 'memo', 'run', 'space', 't', 'trial')

    def __init__(self, run, space, J, t, trial=None):
        self.run, self.space, self.J, self.t, self.trial = run, space, J, t, trial
        self.memo = {}
        self.count = run.plan.spaces[space].count if J is None else len(J)

    def __contains__(self, name):
        return name == 't' or name in self.run.plan.kind

    def get(self, name, default=None):
        if name in self:
            return self[name]
        return default

    def __getitem__(self, name):
        if name == 't':
            return self.t
        found = self.memo.get(name, self)
        if found is self:
            found = self.memo[name] = self.run.read(name, self.space, self.J, self.t, self.trial)
        return found


class Seen(Mapping):
    """The values of the one instance of an environment, as a mapping that a caller only reads: what
    the resolver of a decision gets."""

    def __init__(self, env):
        self.env = env

    def __getitem__(self, name):
        if name not in self.env:
            raise KeyError(name)
        return _one(self.env[name])

    def __contains__(self, name):
        return name in self.env

    def __iter__(self):
        return iter(('t', *self.env.run.plan.kind))

    def __len__(self):
        return 1 + len(self.env.run.plan.kind)


class Unknown(Exception):
    """An expression read an output that the model does not estimate: it has no value."""


class Past(Env):
    """The values that the parts of one space read at a time of the past, from the record of the run."""

    __slots__ = ()

    def __getitem__(self, name):
        if name == 't':
            return self.t
        found = self.memo.get(name, self)
        if found is self:
            found = self.memo[name] = self.run.read_past(name, self.space, self.J, self.t)
        return found


class State:
    """See the module."""

    # ---- reading a name -------------------------------------------------------------------------

    def index(self, space, other, J):
        """The places, in the space `other` of a name, of the instances J of `space`."""
        plan = self.plan
        if plan.spaces[other].count == 1:
            return ONE
        if other == space:
            return J
        to = plan.spaces[space].links[other]
        return to if J is None else to[J]

    def read(self, name, space, J, t, trial):
        plan = self.plan
        kind = plan.kind[name]
        if kind == 'aggregate':
            return self.aggregate(name, t, trial)
        if kind == 'unknown':
            raise Unknown(name)
        at = self.index(space, plan.space_of(name), J)
        if kind == 'value' or self.starting:
            column = self.v[name]
        elif kind == 'line':
            if at is ONE:
                return float(self.y0[name][0] + self.rate[name][0] * (t - self.t0[name][0]))
            if at is None:
                return self.y0[name] + self.rate[name] * (t - self.t0[name])
            return self.y0[name][at] + self.rate[name][at] * (t - self.t0[name][at])
        elif trial is not None and name in trial.values:
            column = trial.values[name]
            if not trial.whole:
                return float(column[0]) if at is ONE else column
        else:
            column = self.numeric(name, at, t)
            return float(column[0]) if at is ONE else column
        if at is ONE:
            return column.item(0)
        return column if at is None else column[at]

    def read_past(self, name, space, J, t):
        """The value of a name at a time of the past (after the steps of that time), for the instances
        J of a space: the present value with each later change taken back, from the record."""
        plan = self.plan
        kind = plan.kind[name]
        if kind == 'aggregate':
            found = plan.aggregates[name]
            parts = []
            for term in found.terms:
                env = Past(self, term.space, None, t)
                parts.append(self.reduced(found.function, _spread(self.value(term.node, env), env.count)))
            return self.combined(found.function, parts)
        if kind == 'extra':
            raise SimulationError(f'{name}: a value of the past reads a value that a firing draws')
        at = self.index(space, plan.space_of(name), J)
        if kind == 'value':
            column = self.v[name].copy()
            for when, place, old in reversed(self.undo.get(name, ())):
                if when <= t:
                    break
                column[place] = old
        elif kind == 'line':
            y0, t0, rate = self.y0[name].copy(), self.t0[name].copy(), self.rate[name].copy()
            for when, places, old_y0, old_t0, old_rate in reversed(self.line_log.get(name, ())):
                if when <= t:
                    break
                y0[places], t0[places], rate[places] = old_y0, old_t0, old_rate
            column = y0 + rate * (t - t0)
        else:
            block = plan.blocks[plan.quantities[name].block]
            if block.whole:
                solution = self.segment((block.index, None), self.whole[block.index], t)
                column = solution.at(t)[solution.slices[name]]
            else:
                offset = self.single[block.index][0].slices[name].start
                column = self.past_states(block, t)[:, offset]
        if at is ONE:
            return column.item(0)
        return column if at is None else column[at]

    def past_states(self, block, t):
        """The state of each instance of a block of single instances at a time of the past: one row
        for each instance. The closed forms of the instances go together: one call gives the matrix
        exponential of each, as a call for it alone gives it. The states of a time before the
        present moment do not change, and neither do those of a run that ended, so the last ones are
        kept: a report reads several names of one block at each of its times."""
        key = (block.index, t)
        kept = self.past_kept.get(key)
        if kept is not None:
            return kept
        solutions = self.single[block.index]
        rows, closed = [None] * len(solutions), []
        for j, present in enumerate(solutions):
            solution = self.segment((block.index, j), present, t)
            if t > solution.t0:
                if solution.mode is None:
                    self.decide(solution)
                if solution.mode == 'closed':
                    closed.append((j, solution))
                    continue
            rows[j] = solution.at(t)
        if closed:
            powers = expm(np.stack([solution.matrix * (t - solution.t0) for _, solution in closed]))
            starts = np.stack([solution.y0 for _, solution in closed])
            starts = np.concatenate([starts, np.ones((len(closed), 1))], axis=1)
            for (j, _), state in zip(closed, np.einsum('nij,nj->ni', powers, starts)[:, :-1]):
                rows[j] = state
        states = np.stack(rows)
        if t < self.now or self.ended:
            self.past_kept[key] = states
            while len(self.past_kept) > 16:
                del self.past_kept[next(iter(self.past_kept))]
        return states

    def segment(self, key, solution, t):
        """The segment of a block that holds the time t: the present one, or one of the record."""
        for when, old in reversed(self.block_log.get(key, ())):
            if when <= t:
                break
            solution = old
        return solution

    def numeric(self, name, at, t):
        """The values of a numeric quantity at the places `at` of its space."""
        plan = self.plan
        block = plan.blocks[plan.quantities[name].block]
        if block.whole:
            solution = self.whole[block.index]
            cut = solution.slices[name]
            column = solution.at(t)[cut]
            return column if at is None or at is ONE else column[at]
        solutions = self.single[block.index]
        places = range(len(solutions)) if at is None or at is ONE else at
        offset = solutions[0].slices[name].start
        return np.array([solutions[j].at(t)[offset] for j in places])

    def column(self, name, t):
        """The value of a name for each instance of its space, at a time."""
        plan = self.plan
        space = plan.space_of(name)
        count = plan.spaces[space].count
        if plan.kind[name] == 'formula':
            # A formula or a status has no value of its own in the run: it is its expression.
            env = Env(self, space, None, t)
            return _spread(self.value(plan.node(expr.ref(name), space, name), env), count)
        return _spread(self.read(name, space, None, t, None), count)

    def value(self, node, env):
        return arrays.values(node, env, self.registry, env.count)

    def static(self, name, space, j, t):
        """The value at t, for the instance j of a space, of a name that does not move between
        moments, as one value."""
        found = self.read(name, space, np.array([j]), t, None)
        if isinstance(found, np.ndarray):
            return found.item(0)
        return found.item() if isinstance(found, np.generic) else found

    def sizes(self):
        """The size of each quantity for each instance, in execution units, as the continuous engine
        finds it (`continuous/system.System.sizes_of`): the size that the file writes, else the
        largest of one of its unit, its start value, its finite bounds, the largest start value of
        the quantities that flows and transfers connect it to, and the limit of an allocation group
        that rations a flow of it, over the horizon. The size sets the tolerance of the quantity."""
        plan = self.plan
        found = {}
        for name, quantity in plan.quantities.items():
            size = np.maximum(quantity.scale, np.abs(self.v[name]))
            for bound in (quantity.lower, quantity.upper):
                if math.isfinite(bound):
                    size = np.maximum(size, abs(bound))
            found[name] = size
        # The quantities that flows and transfers connect: each takes the largest start value of them.
        parent = {name: name for name in plan.quantities}

        def root(name):
            while parent[name] != name:
                parent[name] = parent[parent[name]]
                name = parent[name]
            return name

        pairs = [(flow.source, flow.target) for flow in plan.s.flows.values()]
        for rule in plan.rules:
            for outcome in rule.outcomes:
                pairs += [(source, target) for source, target, _ in outcome.moves]
        for a, b in pairs:
            if a in parent and b in parent:
                parent[root(a)] = root(b)
        sets = {}
        for name in plan.quantities:
            sets.setdefault(root(name), []).append(name)
        for members in sets.values():
            if len(members) == 1:
                continue
            counts = {len(self.v[name]) for name in members}
            if len(counts - {1}) > 1:
                raise Outside(f'{members[0]}: flows or transfers that connect quantities of two families')
            largest = np.zeros(max(counts))
            for name in members:
                largest = np.maximum(largest, np.abs(self.v[name]))
            for name in members:
                share = largest if len(self.v[name]) == len(largest) else largest.max()
                found[name] = np.maximum(found[name], share)
        # A rationed flow moves at most the limit of its group: over the horizon, that bounds what
        # its quantities can gain or lose. A limit that reads a formula bounds nothing here.
        for name, group in plan.groups.items():
            source = plan.s.allocation[name].capacity
            if source is None or group.capacity is None:
                continue
            if any(plan.kind.get(read) == 'formula' for read in names_in(source)):
                continue
            env = Env(self, group.space, None, 0.0)
            try:
                capacity = np.abs(_spread(self.value(group.capacity, env), env.count).astype(float))
            except (ExpressionError, ArithmeticError, ValueError, TypeError, KeyError):
                continue
            capacity = capacity * self.horizon
            for key in group.flows:
                flow = plan.s.flows[key]
                for end in (flow.source, flow.target):
                    if end in found:
                        found[end] = np.where(
                            np.isfinite(capacity), np.maximum(found[end], capacity), found[end]
                        )
        for name, quantity in plan.quantities.items():
            if quantity.size is not None:
                found[name] = np.full(len(self.v[name]), quantity.size)
            found[name] = np.broadcast_to(found[name], self.v[name].shape).astype(float)
        return found

    def rule_free_name(self, name, space, j):
        """The name of a part of the instance j of a space, as the flat structure names it."""
        family = self.plan.spaces[space].family
        return name if family is None else family.hosts[j] + name[len(family.host) :]

    # ---- the steps ------------------------------------------------------------------------------

    def rule_name(self, rule, j):
        family = self.plan.spaces[rule.space].family
        if family is None:
            return rule.name
        return family.hosts[j] + rule.name[len(family.host) :]

    def place(self, space, j, name):
        """The place, in the space of `name`, of the instance that instance j of `space` reads or writes."""
        other = self.plan.space_of(name)
        if other == space:
            return j
        if self.plan.spaces[other].count == 1:
            return 0
        links = self.plan.spaces[space].links
        if other not in links:
            raise Outside(f'a step of a family that writes {name}, a value of another family')
        return int(links[other][j])

    def flat_entity(self, rule, j):
        family = self.plan.spaces[rule.space].family
        return rule.entity if family is None or rule.entity != family.host else family.hosts[j]
