# Brief B1-S: the solve library

Read `briefs/COMMON-B.md` first. You own `napkin/engine/solve/` and `tests/engine/solve/`, and
nothing else. Bench scripts go in `scratch/rewrite/b1/solve/`. State file:
`scratch/rewrite/b1/solve/STATE.md`.

## Why

A declared solver chooses an answer by the spec's selection order: hard constraints, the written
objectives in order, fair sharing of the claims in each priority tier, the flows nearest their
requests, then the other unknowns nearest their references. Prototype A3 built and measured this
on sparse arrays (`scratch/rewrite/a3/`). You turn it into a library of the package, on arrays only:
the engine will form problems from programs in a later stage. Sharing at an endpoint outside a
solver is local and is not your concern.

## Read

- `scratch/rewrite/g0-decisions.md`: D0 and D15, and the part "Flow, solver, and event decisions".
- `scratch/rewrite/spec.md`: "An entity owns its solver" with its examples, "Solver and execution
  contract", and the solver rows of "Acceptance cases".
- `scratch/rewrite/a3/FINDINGS.md` and `scratch/rewrite/a3/STATE.md`, then `scratch/rewrite/a3/solve/`,
  `cases.py` and `checks.py`; and `scratch/networks/nearest.py`, an earlier distance method for
  problems with equality rows and bounds only, measured at 0.1 to 2.7 s on 30,000 places.

## What to build

1. **A problem**: unknowns with bounds (either side open), a scale and a reference value, each marked
   a flow or another unknown; affine rows (`==`, `<=`, `>=`); ranked objectives (a positive part such
   as `max(0, request - rate)` becomes an extra unknown); the claims of fair sharing, by priority
   tier, with a request each, and one served fraction for a flow with legs; the targets of the
   distance steps.
2. **A solver** that keeps one HiGHS instance for a run, never for a plan, so that sample k gives the
   same answer alone and in a batch. Unknowns that join and leave are columns that are added and
   deleted, and each answer equals that of the problem formed fresh. Work in working units, so that
   W against kW changes nothing beyond rounding.
3. **The ranks** as A3 chose them: optima kept by pinning from the duals and checked at the end; fair
   sharing by the exact sequential method, a fixed claim held by a lower bound and never by an
   equality; the distance step with the fast method of `nearest.py` when a problem has no
   inequality row, A3's method with slacks when it has one, and the QP of HiGHS as an exact fallback
   when the method does not converge within its budget.
4. **Budgets** (D0): the fair-sharing step and the distance step each have a budget, counted in
   deterministic work (programs solved, iterations, Newton steps), never in seconds. A step that
   cannot answer within its budget and its tolerances raises a named failure that names the step
   and what it reached, such as "fair-sharing budget exceeded" with the count of levels. Also named:
   infeasible hard constraints, an unbounded written objective, a numerical failure. The library
   never returns a different answer in their place. Choose default budgets that the 3,000-place cases
   of A3 pass, and say what they are.
5. **Tests** (`tests/engine/solve/`): every solver answer of the spec, with its exact numbers: the two
   bottlenecks (2, 2, 3) and (4, 0, 5); staffing 70/30 and 56/24; the pump; the provider 6/2, 2/6
   and 0/6; the worked network's rates and levels (8/3, -4/3, -4/3) and (3, -3, 0), also in kW;
   `4 <= x + y <= 6` giving (2, 2) and (3, 3); `x + y == 1` giving (1/2, 1/2); membership 2, then
   1.5 each, then 2, then nothing; the bridge where a flow takes more than its request (unmet 4.65
   against 9.20). Also: small seeded random problems against an exact enumeration and against brute
   force; each named failure, with a tiny budget where a budget is meant. Keep the tests fast.
6. A bench script (not a test) that makes A3's table at 3,000 places again.

Import only numpy and scipy (SciPy's bundled HiGHS, as `napkin/engine/continuous/highs.py` does).
Do not change `napkin/engine/continuous/` or any other existing file.

## Exit

`tests/engine/solve/` passes in under a minute. Your last message gives the default budgets, the
bench numbers at 3,000 places, and the decisions that you made beyond A3's.
