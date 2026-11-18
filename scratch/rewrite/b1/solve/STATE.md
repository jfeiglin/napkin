# B1-S state: the solve library (update at each milestone; 60 lines at most)

## Done (milestone 2: package, tests and bench; 169 tests pass in 3 s)
- `napkin/engine/solve/`: `problem.py` (Problem, Arrays: keyed unknowns/rows, positive parts,
  claims), `scaled.py` (working units, reorder), `kept.py` (Kept: one HiGHS instance tracking its
  bounds; `quadratic`: QP fallback on its own instance), `failures.py`, `ranked.py` (Face, pin, exact
  duals, status -> failure, `lost`), `fair.py`, `distance.py`, `solver.py` (Budget, Work, Answer,
  Solver: sync by keys, order, end checks), `__init__.py`.
- `tests/engine/solve/`: `cases.py` (spec problems), `exact.py` (rational reference: simplex,
  brute-force fair, Fourier-Motzkin, active sets), `test_spec_answers.py` (33), `test_membership.py`
  (7), `test_failures.py` (23), `test_random.py` (106).
- `scratch/rewrite/b1/solve/bench.py`: sections small, fair, objective, after, join, again, verify.

## Decisions (one line each, with the reason)
- Sync by keys: each solve takes the whole problem; the kept instance deletes what left, adds what
  joined, replaces a row whose working coefficients changed (equal to the fresh program).
- One Solver per run, no module state; the QP fallback has its own instance (bitwise alone/batch).
- Budgets: fair 1,000 programs; distance 500 Newton steps per stage, then 100,000 QP iterations.
- Exact line search everywhere (Armijo stalls on fair faces: two bottlenecks fail with Armijo).
- Proximal weight 1 -> 1e-3, tenfold after a prox problem of <= 3 Newton steps (A3's 1e-3 from the
  start never converged after fair).
- Prox stop: eps * move <= precision of the rows (A3's move <= 1e-9 cycled on tiny problems).
- Stall rule: 10 steps without halving the residual and all rows within 1e-7 -> met at 1e-7
  (1,000 places x1.45: 1,059 -> 163 steps).
- HiGHS QP ended kSolveError on the 3,000-place fair face (A3's success did not reproduce); kept as
  the fallback (300 and 1,000 places: it finishes and agrees with the method to 6.4e-7).
- QP answer clipped into the face's bounds; kept-optimum check per term: 1e-7 * sum |c|(1+|x|)
  (A3's 1e-7 * max(1, |c|.|x|) refused the QP's answer: 300 terms lost 6.7e-6 of 0.38).
- Pin only where the dual's sign matches the side the value rests on; wrong sign > 1e-9 -> one
  more run at tolerances 1e-10. Sides read from values (no getBasis conversions: 5 ms a program).
- Constant claims (all columns fixed) held without a program; np.maximum.at for shared columns.
- Positive parts recomputed as max(0, e.x + e0) before the end checks and in the answer.
- Crossed bounds and failing empty rows -> 'infeasible' before any program (names the key).

## Bench at 3,000 places (A3's network; 4 shared cores, load 0.4-0.8)
- fair (objective + fair): normal 0.18 + 1.11 s, 50 programs; x1.45 0.21 + 2.99 s, 125; damaged
  0.15 + 1.28 s, 71 (61 levels); x1.7 0.23 + 4.37 s, 170. No tight run.
- objective face distance: 1.23 / 1.34 / 0.67 s (Newton 35/50/34 + 3).
- after fair distance: 3.66 / 4.45 / 2.44 / 5.93 s (Newton 98/144/98/178 + 3); no QP.
- join 300 flows: warm 0.06 s vs fresh 0.26 s; leave 0.11 s; optima equal (677.730970160).
- again: optimum cold = warm = 601.853501921; levels within 1.8e-11; two fresh solvers bitwise.
- small (provider, whole order): 3.8 ms fresh, 3.6 ms kept.

## In progress
- Review pass; a test of the QP fallback through the whole order; tests/core; last message.
