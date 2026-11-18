"""The named failures of a solve.

A solve gives the answer of the selection order or raises a `SolveFailure`, and never gives another
answer in its place: a silent change in who is served would change the model (G0, D0). Each failure
has a name, the step of the selection order that stopped, and what that step had reached when it
stopped, so that a diagnostic can tell legitimate scale from a broken model.
"""

from __future__ import annotations

# The hard constraints have no answer: the bounds, the rows, or both contradict one another.
INFEASIBLE = 'infeasible'
# A written objective has no finite optimum over the answers that keep the earlier optima.
UNBOUNDED = 'unbounded'
# The fair-sharing step solved as many linear programs as its budget allows, with claims pending.
FAIR_BUDGET = 'fair-sharing budget exceeded'
# The distance method did not converge within its Newton steps, and the exact fallback (the QP of
# HiGHS) did not finish within its iterations.
DISTANCE_BUDGET = 'distance budget exceeded'
# The solver or an end check met a contradiction that the problem does not hold: a later rank that
# found no answer on a face that an earlier rank found feasible, a kept optimum that the answer
# lost, a status of HiGHS that is no answer.
NUMERICAL = 'numerical'

NAMES = (INFEASIBLE, UNBOUNDED, FAIR_BUDGET, DISTANCE_BUDGET, NUMERICAL)


class SolveFailure(RuntimeError):
    """A solve that cannot give the answer of the selection order.

    `name` is one of `NAMES`, `step` names the step that stopped (such as 'objective 2' or 'fair
    sharing, tier 0'), and `reached` holds what it had reached: counts of work, levels, residuals."""

    def __init__(self, name, step, message, reached=None):
        if name not in NAMES:
            raise ValueError(f'no failure is named {name!r}')
        super().__init__(f'{name} in {step}: {message}')
        self.name = name
        self.step = step
        self.reached = dict(reached or {})
