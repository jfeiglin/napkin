"""The checks of the inputs and of the state, and the partitions.

Moved from `run.py` with no change (step B0-6). `Checks` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import numpy as np

from ...core.errors import ExpressionError
from ...model.ir import ModelError
from ..errors import SimulationError
from .state import Env, _pairwise, _spread


class Checks:
    """See the module."""

    def check_readers(self, block, j, t):
        """The checks of the state and the partitions that read a quantity of a component hold at
        the time t of its present segment, or the run stops."""
        found = self.block_checks.get((block, j))
        if found is None:
            names = [(name, {j}) for name in self.plan.blocks[block].names]
            local = self.plan.nets[self.plan.blocks[block].space].local
            found = self.block_checks[(block, j)] = [
                item for item in self.closure(names)[4].items() if item[0] not in local
            ]
        for (kind, index), J in found:
            places = None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            (self.check if kind == 'check' else self.partition)(index, places, t)

    def holds_at_start(self, found):
        """Whether a check that reads only inputs and named states holds, for each instance of its
        space, with each state at its start value."""
        env = Env(self, found.space, None, 0.0)
        return _spread(self.value(found.node, env), env.count).astype(bool)

    def check(self, index, J, t):
        """A check of the state holds for the instances J (None: all), or the run stops."""
        found = self.plan.checks[index]
        env = Env(self, found.space, J, t)
        try:
            holds = _spread(self.value(found.node, env), env.count).astype(bool)
        except ExpressionError as problem:
            # A failure names the expression, as the evaluation of an expression of the model does.
            raise ExpressionError(f'{found.source!r}: {problem}') from problem
        if holds.all():
            return
        at = int(np.flatnonzero(~holds)[0])
        name = self.plan.check_name(found.name, found.space, at if J is None else int(J[at]))
        raise SimulationError(
            f'Check {name}: {found.message}',
            [{'code': 'check_failed', 'severity': 'error', 't': float(t), 'check': name, 'path': found.path}],
        )

    def partition(self, index, J, t):
        """The parts of a partition add up to its total for the instances J (None: all), within its
        tolerance, or within 1e-9 of the size of the total when it has none; else the run stops."""
        found = self.plan.partitions[index]
        env = Env(self, found.space, J, t)
        total = _spread(self.value(found.total, env), env.count).astype(float)
        parts = np.zeros(env.count)
        for part in found.parts:
            if self.plan.space_of(part) == found.space:
                parts = parts + _spread(env[part], env.count)
            else:
                parts = parts + _pairwise(self.column(part, t))
        if found.tolerance is None:
            limit = 1e-9 * np.maximum(1.0, np.abs(total))
        else:
            limit = _spread(self.value(found.tolerance, env), env.count).astype(float)
        wrong = np.abs(parts - total) > limit
        if not wrong.any():
            return
        at = int(np.flatnonzero(wrong)[0])
        name = self.plan.check_name(found.name, found.space, at if J is None else int(J[at]))
        raise SimulationError(
            f'Partition {name}: its parts add up to {parts[at]}, not {total[at]}',
            [
                {
                    'code': 'partition_failed',
                    'severity': 'error',
                    't': float(t),
                    'partition': name,
                    'path': found.path,
                }
            ],
        )

    def check_all(self, t):
        for found in self.plan.checks:
            self.check(found.index, None, t)
        for found in self.plan.partitions:
            self.partition(found.index, None, t)

    def input_failures(self):
        """The failing checks of the inputs of the run (an `assert` that reads only inputs and named
        states), for every instance of each space, with the flat name of the check of each instance:
        what `analysis.values.input_check_failures` gives of a flat structure."""
        plan, found = self.plan, []
        for check_, severity, basis in plan.input_checks:
            holds = self.holds_at_start(check_)
            for j in np.flatnonzero(~holds).tolist():
                found.append(
                    {
                        'code': 'check:' + plan.check_name(check_.name, check_.space, j),
                        'severity': 'error' if severity == 'block' else 'warning',
                        'message': check_.message,
                        'path': check_.path,
                        'evidence': basis,
                    }
                )
        return found

    def admit(self):
        """A run of a model with a table is refused when its inputs fail a blocking check for some
        row, as `Model.resolve` refuses a run of a flat model: the model of the representatives has
        that check for one row of each class only. A resolved run of a model with no table comes
        from `Model.resolve`, which made the check."""
        plan = self.plan
        if not plan.core.families:
            return
        blocked = [item for item in self.input_failures() if item['severity'] == 'error']
        if blocked:
            raise ModelError(blocked)
        if self.given:
            # The plan was proved for the values of its run and of its tables. For the values that
            # this run was given, the core makes the proofs over the rows again: a failure refuses
            # the run. A proof that gives other facts than those that the plan was made with needs
            # another plan.
            proved = plan.core.proved(plan.resolved.run, plan.resolved, self.given)
            for name, found in (proved or {}).items():
                if name.startswith('proven_') and set(found) != set(getattr(plan.resolved, name)):
                    raise ModelError(
                        [
                            {
                                'code': 'rows',
                                'severity': 'error',
                                'path': f'runs/{plan.resolved.run}',
                                'message': 'The values of the run change what the compiler proves of '
                                f'the model ({name}): the plan of the run does not hold for them',
                            }
                        ]
                    )
