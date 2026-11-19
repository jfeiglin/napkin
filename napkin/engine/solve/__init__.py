"""The solve library: the selection order of a declared solver, on arrays.

A declared solver chooses an answer by the spec's selection order: the hard constraints, the written
objectives in order, fair sharing of the claims in each priority tier, the flows nearest their
requests, then the other unknowns nearest their references. This package does that on arrays, with
numpy, scipy, the HiGHS solver that SciPy bundles and the LDL' factorization of `qdldl`; the engine
forms the problems from programs.

- `Problem` (`problem`): unknowns, affine rows, ranked objectives and claims, in author units.
- `Solver` (`solver`): the selection order on one HiGHS instance that a run keeps (`kept`), in
  working units (`scaled`), with its steps in `ranked`, `fair` and `distance`.
- `Budget`: the budgets of fair sharing and of the distance steps, in deterministic work.
- `SolveFailure` (`failures`): a solve that cannot answer stops by name and never answers otherwise.

Sharing at an endpoint outside a declared solver is local and is not done here.
"""

from .failures import (
    DISTANCE_BUDGET,
    FAIR_BUDGET,
    INFEASIBLE,
    NUMERICAL,
    UNBOUNDED,
    SolveFailure,
)
from .problem import FLOW, INTERNAL, OTHER, Problem
from .solver import Answer, Budget, Solver, Work

__all__ = [
    'DISTANCE_BUDGET',
    'FAIR_BUDGET',
    'FLOW',
    'INFEASIBLE',
    'INTERNAL',
    'NUMERICAL',
    'OTHER',
    'UNBOUNDED',
    'Answer',
    'Budget',
    'Problem',
    'SolveFailure',
    'Solver',
    'Work',
]
