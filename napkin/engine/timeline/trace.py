"""What a run keeps for its readers: the entries of the trace, the snapshots and the result.

Moved from `run.py` with no change (step B0-6). `Trace` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ...model.ir import COUNT, ENTERED, TIME
from .plan import SCALARS
from .state import Env, Unknown, _one


def _basis_ref(basis):
    """The identity of a basis for a trace entry: its name, kind and the records it cites."""
    if isinstance(basis, (list, tuple)):
        return [_basis_ref(item) for item in basis]
    if not isinstance(basis, dict):
        return basis
    out = {key: basis[key] for key in ('name', 'kind', 'assumption') if key in basis}
    claims = sorted({link['claim'] for link in basis.get('links', []) if 'claim' in link})
    return out | ({'claims': claims} if claims else {})


@dataclass
class Result:
    """What a run gives: the events in their order, as (time, rule, outcome), where the outcome is
    None for a rule that starts to wait; the value of each output at the horizon; and the counts of
    the work."""

    horizon: float
    trace: list
    outputs: dict
    counts: dict
    reading: str
    run: object = field(repr=False, default=None)
    # The outputs that the model does not estimate: they have no value, which is not the value 0.
    unestimated: tuple = ()
    # A played run: the first decision that waits for a pick, whether the run stopped there, and the
    # time to which the run went (the horizon, or the time of that decision).
    decision: dict | None = None
    paused: bool = False
    end_time: float | None = None
    # A run with given outcomes (`Run.taken`): each firing that went by chance, in its order.
    firings: tuple = ()

    def __post_init__(self):
        if self.end_time is None:
            self.end_time = self.horizon

    @property
    def entries(self):
        """Each step of the trace as a report reads it: its rule, thing, event, outcome
        and text, what it set and moved, its place in the file and its basis, and who picked its
        outcome. They are made when a reader asks: a run of many instances does not pay for them."""
        return [self.run.entry_at(k) for k in range(len(self.run.log))]

    def final(self, name):
        """The value of a name at the end of the run (the horizon, or the time at which a played run
        stopped), for each instance of its space."""
        return self.run.column(name, self.end_time)

    def trajectory(self):
        """The run as a trajectory (`engine/runtime.Trajectory`), which the reports, the studies and
        the tools read: for a run that kept its whole record (`keep`), of a model with no table."""
        from ..continuous.kernels import Affine, Segment
        from ..continuous.system import System
        from ..runtime import Trajectory

        run = self.run
        if not run.keep:
            raise ValueError('the run did not keep its whole record: Run(…, keep=True)')
        plan = run.plan
        s = System(run.resolved, plan.library, run.cfg)
        s.values = {**s.values, **{name: run.v[name].item(0) for name in plan.parameter_scale}}
        diagnostics, settings = [], s.settings
        for component in run.components:
            if component.system is not None:
                diagnostics, settings = component.trajectory.diagnostics, component.system.settings
        segments = [Segment(piece.start, piece.end, piece.solution, piece.store) for piece in run.pieces]
        if not run.components:
            # Nothing moves between two moments: each quantity keeps the value of the last step.
            still = np.zeros(len(s.state_ids))
            for (start, state, store), (end, _, _) in zip(run.snapshots, run.snapshots[1:]):
                if end > start:
                    segments.append(Segment(start, end, Affine(start, state.copy(), still), dict(store)))
            if run.snapshots and self.end_time > run.snapshots[-1][0]:
                start, state, store = run.snapshots[-1]
                segments.append(
                    Segment(start, self.end_time, Affine(start, state.copy(), still), dict(store))
                )
        made = Trajectory(
            s.horizon,
            self.entries,
            diagnostics,
            settings,
            s.state_ids,
            s.values,
            s.computed,
            s.units,
            s.bounds,
            _segments=segments,
            _snapshots=list(run.snapshots),
            _steps=list(run.after_steps),
            layers=list(range(len(self.entries))),
            moved=set(run.moved),
            evaluations=int(self.counts['evaluations']),
            decision=self.decision,
            paused=self.paused,
            end_time=self.end_time,
        )
        if run.snapshots:
            # The order of the formulas is a field of a trajectory: a trajectory has it whether a
            # reader asked or not.
            made._environment(*run.snapshots[0])
        return made


class Trace:
    """See the module."""

    def entry(self, rule, j, outcome, t, sets, modes, moved, before):
        """Keep one step of the trace: a trigger that waits (`outcome` None), or a firing and its
        outcome, with what it set and moved and who picked its outcome (`entry_at` writes it out)."""
        picked = None
        if outcome is not None and self.picking is not None:
            picked, self.picking = self.picking, None
        self.log.append((float(t), self.steps, rule.index, j, outcome, sets, modes, moved, before, picked))

    def entry_at(self, k):
        """The step k of the trace as a report reads it."""
        made = self.written_entries.get(k)
        if made is not None:
            return made
        plan = self.plan
        t, step, index, j, outcome, sets, modes, moved, before, picked = self.log[k]
        rule = plan.rules[index]

        def flat(name):
            space = plan.space_of(name)
            return self.rule_free_name(name, space, self.place(rule.space, j, name)) if space else name

        def placed(key):
            return self.rule_free_name(key[0], plan.space_of(key[0]), key[1])

        # A firing reads as the text of its outcome; an event that fires as it triggers also as its own.
        label = rule.label
        if outcome is not None and outcome.label is not None:
            label = outcome.label
        elif outcome is not None and rule.delay is not None:
            label = None
        basis = rule.basis if outcome is None else outcome.basis or rule.basis
        name = self.rule_name(rule, j)
        made = self.written_entries[k] = {
            't': t,
            'step': step,
            'rule': name,
            'entity': self.flat_entity(rule, j),
            'event': name if outcome is None else flat(outcome.emits[0]),
            'outcome': None if outcome is None else outcome.name,
            'label': label,
            'changes': {placed(key): value for key, value in (*sets.items(), *modes.items())},
            'before': {placed(key): value for key, value in before.items()},
            'transfers': [[placed(source), placed(target), amount] for source, target, amount in moved],
            'path': rule.path if outcome is None else outcome.path,
            'basis': _basis_ref(basis),
            'fires': [] if outcome is None else [flat(target) for target in outcome.fires],
            'semantic': label is not None,
            # Who picked the outcome in a played run, or None when the model chose it.
            'picked': picked,
        }
        return made

    # ---- the moments ----------------------------------------------------------------------------

    def state_now(self, t):
        """The value of each quantity at t, in the order of the model."""
        return np.array([float(self.column(name, t)[0]) for name in self.plan.quantities])

    def store_now(self):
        """The store of a trajectory: each state with the time at which it took its value, and for
        each event how many times it happened and when."""
        plan, found = self.plan, {}
        for name in plan.s.modes:
            found[name] = self.v[name].item(0)
            found[name + ENTERED] = float(self.v[name + ENTERED][0])
        for name in plan.s.events:
            found[name + COUNT] = int(self.v[name + COUNT][0])
            found[name + TIME] = float(self.v[name + TIME][0])
        return found

    def snapshot(self, t, step=False):
        if self.keep:
            self.snapshots.append((float(t), self.state_now(t), self.store_now()))
            if step:
                self.after_steps.append(self.snapshots[-1])

    def result(self, paused=False):
        """What the run gives. A run that stopped at a decision (`paused`) has its trace and its
        state up to that time, and no value of an output: an output is a value at the horizon."""
        plan, t = self.plan, self.horizon
        trace = [(at, self.rule_name(plan.rules[index], j), outcome) for at, index, j, outcome in self.trace]
        outputs, unestimated = {}, list(plan.unestimated)
        if not paused:
            self.check_all(t)
            env = Env(self, SCALARS, None, t)
            for name, node in plan.outputs.items():
                # An output is one value, so only the branch of a choice that holds is read. An
                # output that reads an output with no estimate there has no value either.
                try:
                    outputs[name] = _one(self.value(node, env))
                except Unknown:
                    unestimated.append(name)
            self.ended = True  # nothing of the run changes now: a report can keep what it reads
        return Result(
            t,
            trace,
            outputs,
            dict(self.counts),
            self.reading,
            self,
            tuple(unestimated),
            self.decision,
            paused,
            self.now if paused else t,
            tuple(self.firings),
        )
