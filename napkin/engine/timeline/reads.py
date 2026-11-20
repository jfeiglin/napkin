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

import heapq
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.record import Unavailable
from ..continuous.walk import walked

if TYPE_CHECKING:
    from .region import Region

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


@dataclass
class _Pipe:
    """The calculation and the inputs of a shared outside rate."""

    region: Region
    inputs: set
    stepped: frozenset
    version: int
    switches: dict
    held: bool = False


class OutsideRates:
    """Flows from SOURCE to SINK, indexed by the inputs that change their sharing."""

    def __init__(self, run):
        self.run = run
        self.active = {}
        self.users = {}
        self.moving = set()
        self.arrived = set()
        self.contacts = {}
        self.heap = []
        self.recheck = set()
        self.recording = {}  # observed moving arithmetic on a selected branch -> fitted through

    def selections(self):
        """The active sides and key rows shared with stages until the next crossing."""
        found = []
        for name in sorted(self.moving):
            pipe = self.active[name]
            signs = tuple(sorted((pipe.switches[pair][2], sign) for pair, sign in pipe.region.signs.items()))
            found.append((name, signs, tuple(sorted(pipe.region.rows.items())), pipe.held))
        return tuple(found)

    def restore(self, contacts, selections):
        """Rebuild the dependency index for the active pipes of a restored sharing."""
        for name in self.run.plan.outside:
            if name in self.run.published and name not in self.run.frozen:
                self._index(name)
        for name, saved, rows, held in selections:
            pipe = self.active[name]
            labels = {label: pair for pair, (_, _, label) in pipe.switches.items()}
            pipe.region.set({labels[label]: sign for label, sign in saved}, dict(rows))
            pipe.held = held
            if not held and (pipe.switches or pipe.stepped) and self.run.recorder.wanted(name):
                self.recording[name] = self.run.now
        self.contacts.update(contacts)
        self.heap = [(roots[0][0], name) for name, roots in self.contacts.items()]
        heapq.heapify(self.heap)

    def next_contact(self):
        """The next switch on the actual store segments, extending only changed predictions."""
        due, self.recheck = self.recheck, set()
        for name in sorted(due):
            pipe = self.active[name]
            choices = []
            for (a, b), (moving, affine, label) in pipe.switches.items():
                if (a, b) not in pipe.region.signs:
                    continue  # an undefined operand in an untaken branch
                outgoing = pipe.region.signs[a, b]
                when = self.run.triggers.switching_time(a, b, moving, outgoing, affine)
                if when is not None:
                    choices.append((when, label))
            if choices:
                roots = tuple(sorted(choices))
                if self.contacts.get(name) != roots:
                    self.contacts[name] = roots
                    heapq.heappush(self.heap, (roots[0][0], name))
            else:
                self.contacts.pop(name, None)
        while self.heap:
            t, name = self.heap[0]
            roots = self.contacts.get(name)
            if roots and roots[0][0] == t and t > self.run.now:
                return t
            heapq.heappop(self.heap)
        return math.inf

    def changed_segment(self, names):
        """Extend the windows of pipes that read a segment that has just ended."""
        for key in names:
            for name in self.users.get(key, ()):
                if self.active[name].switches:
                    self.recheck.add(name)

    def reads_any(self, names):
        """Whether a physical jump can affect an outside pipe."""
        return any(name in self.users for name in names)

    def record_to(self, end, changed=None):
        """Fit the arithmetic of selected branches on the physical segments about to be committed."""
        import numpy as np

        from .record import fitted

        due = (
            self.recording
            if changed is None
            else {name for key in changed for name in self.users.get(key, ()) if name in self.recording}
        )
        run = self.run
        for name in due:
            since = self.recording[name]
            if since >= end:
                continue
            region = self.active[name].region

            def sample(times, name=name, region=region):
                return np.array([[float(run.in_region(name, t, region))] for t in times])

            tolerance = run.plan.numerics.atol_factor * max(1, abs(run.published[name]))
            pieces = fitted(sample, since, end, np.array([tolerance]))[0]
            run.recorder.add_pieces(name, pieces)
            self.recording[name] = end

    def timing_events(self, through):
        """Outside switches through a grouped contact, walking only the due part of their heap."""
        pending = [0] if self.heap else []
        while pending:
            index = pending.pop()
            at, name = self.heap[index]
            if at > through:
                continue
            roots = self.contacts.get(name)
            if roots and roots[0][0] == at:
                yield from ((when, name, label) for when, label in roots if when <= through)
            pending.extend(child for child in (2 * index + 1, 2 * index + 2) if child < len(self.heap))

    def _forget(self, name):
        if name in self.active:
            for key in self.active.pop(name).inputs:
                users = self.users[key]
                users.discard(name)
                if not users:
                    del self.users[key]
        self.moving.discard(name)
        self.arrived.discard(name)
        self.contacts.pop(name, None)
        self.recheck.discard(name)
        self.recording.pop(name, None)

    def _index(self, name):
        from ..continuous.integrate import surfaces_of
        from .region import Region, key_surfaces
        from .triggers import _affine

        run, plan = self.run, self.run.plan
        self._forget(name)
        found = plan.reads_now(plan.expanded(name))
        deps = set(found.formulas | found.leaves | found.stepped)
        deps.discard(name)
        live = found.leaves & plan.moving
        deps.update(f'{store}.{side}.actual_rate' for store in live for side in ('inflow', 'outflow'))
        for key in deps:
            self.users.setdefault(key, set()).add(name)
        moving_names = set(live)
        for leaf in found.leaves:
            owner = run.ways.result_of.get(leaf)
            if owner is None and plan._is_rate(leaf):
                owner = run.ways.set_of.get(leaf.rsplit('.', 1)[0])
            if owner is not None and run.ways.moving(owner):
                moving_names.add(leaf)
        if found.time or found.stepped or moving_names:
            self.moving.add(name)
        formulas = {key: plan.values[key].node for key in found.formulas if plan.values[key].node is not None}

        def moves(node):
            expansion = plan.expansion(node)
            return expansion.time or bool(expansion.leaves & moving_names)

        surfaces = surfaces_of([plan.values[name].node], formulas, moves)
        region = Region(surfaces, key_surfaces(plan, found.leaves, moves))
        switches = {}
        for a, b in region.surfaces:
            left, right = plan.expansion(a), plan.expansion(b)
            stores = (left.leaves | right.leaves) & moving_names
            moving = stores | ({'t'} if left.time or right.time else set())
            if moving:
                affine = stores <= live and _affine(a, live, plan) and _affine(b, live, plan)
                label = f'switch ({nodes.text(a)}, {nodes.text(b)})'
                switches[a, b] = (moving, affine, label)
        self.active[name] = _Pipe(region, deps, found.stepped, plan.version, switches)
        if switches:
            self.recheck.add(name)

    def refresh(self, changes, joined, left, t, incoming=False):
        """Publish the incoming rates at t, or the rates of a sharing after its stages."""
        run, plan = self.run, self.run.plan
        if changes is None:
            due = set(plan.outside) - run.frozen.keys()
            for name in due:
                self._index(name)
        elif incoming:
            keyed = run.keyed_changes(t)
            for name in self.moving:
                pipe = self.active[name]
                if not pipe.held:
                    run.published[name] = float(run.in_region(name, t, pipe.region, shared=True))
                if pipe.stepped.intersection(keyed) or any(
                    run.clock.within(when, t) for when, _ in self.contacts.get(name, ())
                ):
                    self.arrived.add(name)
                if pipe.switches:
                    self.recheck.add(name)
            return
        else:
            due, self.arrived = self.arrived, set()
            for key in changes:
                due.update(self.users.get(key, ()))
                if key in plan.outside:
                    if key in run.frozen:
                        self._forget(key)
                        due.discard(key)
                        run.published[key] = 0.0
                    else:
                        if key not in self.active:
                            self._index(key)
                        due.add(key)
            for flow in joined:
                name = f'{flow}.actual_rate'
                if name in plan.outside:
                    self._index(name)
                    due.add(name)
        for flow in left:
            name = f'{flow}.actual_rate'
            if name in plan.outside:
                self._forget(name)
                due.discard(name)
                run.published[name] = 0.0
        for name in sorted(due):
            if name not in self.active:
                continue
            if self.active[name].version != plan.version:
                self._index(name)
            value, holds = self._at(name, t)
            run.published[name] = value
            self.active[name].held = holds
            if run.recorder.wanted(name):
                if not holds and (self.active[name].switches or self.active[name].stepped):
                    self.recording[name] = t
                else:
                    self.recording.pop(name, None)
                # Smooth arithmetic without selected branches can be fitted from its input histories.
                run.recorder.add(name, t, value, 0.0 if holds or name in self.recording else None)
            if self.active[name].switches:
                self.recheck.add(name)

    def holds_between(self, names, region=None):
        """Whether these reads hold between known contacts, on the pipe's selected branch
        when sharing it, or using the already shared outside rates when watching a condition."""
        plan = self.run.plan
        pending, seen = list(names), set()
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            if region is None and key in self.active:
                if not self.active[key].held:
                    return False
                continue
            if key == 't' or key in plan.moving or key in plan.results or plan._is_rate(key):
                return False
            value = plan.values.get(key)
            if value is None:
                continue
            if value.kind == 'formula':
                node = value.node if region is None else region.expression(value.node)
                pending.extend(nodes.names(node))
            elif region is not None and key in region.rows:
                pending.append(region.rows[key])
            elif key in plan.reductions or key in plan.keyed or key in plan.dynamic:
                return False
        return True

    def _at(self, name, t):
        from ..continuous.integrate import branch_sides
        from .region import trend

        run, plan = self.run, self.run.plan
        pipe = self.active[name]
        region = pipe.region

        def read(key):
            return run.in_region(key, t, None, shared=True)

        units = plan.units

        def operand(node):
            return lazily(node, read, units, t)

        sides = branch_sides(region.surfaces, operand)
        speeds = {}

        def slope(key):
            if key in plan.moving:
                speeds[key] = run.ways.shared_value(f'{key}.inflow.actual_rate') - run.ways.shared_value(
                    f'{key}.outflow.actual_rate'
                )
            elif key in plan.values and plan.values[key].kind == 'formula':
                node = plan.values[key].node
                for child in nodes.names(node):
                    if child != 't' and child not in speeds:
                        yield slope(child)
                speeds[key] = trend(node, read, speeds.__getitem__, units, t)
            else:
                speeds[key] = 0.0

        def velocity(key):
            if key not in speeds:
                walked(slope(key))
            return speeds[key]

        reached = {label for when, label in self.contacts.get(name, ()) if run.clock.within(when, t)}
        reached.update(label for when, owner, label in run.prior_contacts if owner == name and when >= t)
        for (a, b), sign in sides.items():
            switch = pipe.switches.get((a, b))
            grouped = bool(switch and switch[2] in reached)
            if sign == 0 or grouped:
                delta = trend(a, read, velocity, units, t) - trend(b, read, velocity, units, t)
                on_surface = sign == 0
                if grouped and delta:
                    margin = operand(a) - operand(b)
                    on_surface |= run.clock.within(t - margin / delta, t)
                if delta and on_surface:
                    direction = int(delta > 0) - int(delta < 0)
                    sides[a, b] = direction
        rows = region.selected_rows(run, sides, operand)
        for key in pipe.stepped:
            lookup = run.stepped_of(key)
            try:
                rows[key] = lookup.name_at(t)
            except ExpressionError:
                continue  # below the first key, an untaken branch can still have a value
        region.set(sides, rows)
        holds = len(pipe.switches) == len(sides) and self.holds_between([name], region)
        return float(run.in_region(name, t, region, shared=True)), holds
