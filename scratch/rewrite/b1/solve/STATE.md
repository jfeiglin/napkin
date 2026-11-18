# B1-S state: the solve library (update at each milestone; 60 lines at most)

## Done (milestone 1: the package runs; the smoke cases and the 3,000-place bench pass)
- `napkin/engine/solve/`: `problem.py` (Problem, keyed unknowns/rows, positive parts, claims;
  `Arrays`), `scaled.py` (working units, reorder), `kept.py` (Kept: one HiGHS instance, tracks its
  bounds; `quadratic`: the QP fallback on its own instance), `failures.py`, `ranked.py` (Face, pin,
  exact duals, status -> failure), `fair.py` (sequential exact), `distance.py` (Newton + QP),
  `solver.py` (Budget, Work, Answer, Solver: sync by keys, order, end checks), `__init__.py`.
- `scratch/rewrite/b1/solve/bench.py`: A3's table at 3,000 places (imports a3/network.py).
  Sections fair, objective, after, join, again, small.

## Decisions (one line each, with the reason)
- Sync by keys: each solve takes the whole problem; the kept instance deletes what left, adds what
  joined, replaces a row whose working coefficients changed. The engine forms problems fresh.
- One Solver per run (never per plan), no module state; the QP fallback has its own instance.
- Budgets: fair = linear programs (1,000); distance = Newton steps per stage (500), then QP
  iterations (100,000). 3,000 places: fair 50-170 programs; Newton 99-179 after fair.
- Exact line search everywhere (A3 used Armijo with slacks): Armijo stalls on the after-fair face.
- Proximal weight continuation 1 -> 1e-3 (tenfold after a prox problem of <= 3 Newton steps): A3's
  1e-3 from the start never converged after fair; now 3,000 places after fair converges in 2-6 s.
- HiGHS's QP ends kSolveError on the after-fair face at 3,000 places (fresh or kept instance,
  presolve on or not); A3's one success did not reproduce. It stays the fallback (small cases ok).
- Pin only where the dual's sign matches the side the value rests on (A3 used the sign alone);
  a dual of the wrong sign beyond 1e-9 -> one more run with tolerances 1e-10 (`ranked.exact`).
  Sides read from values (HiGHS puts a nonbasic column exactly on its bound): no getBasis cost.
- Claims whose columns are all fixed are held at their value without a program (closed flows).
- Two claims on one column (flow and endpoint): np.maximum.at for the floors (A3 let the last win).
- Positive parts recomputed as max(0, e.x + e0) before the end checks and in the answer.
- Crossed bounds and failing empty rows -> 'infeasible' before any program (names the key).

## Bench at 3,000 places so far [load 0.5-1.2]
- fair: normal 50 programs 1.15 s; x1.45 125, 3.08 s; damaged 71 (61 levels) 1.28 s; x1.7 170, 4.05 s.
- objective face distance: 1.0, 1.4, 0.8 s (Newton 41/133/37 + 3).
- after fair distance: normal 3.5 s (101+3), x1.45 4.3 s (146), damaged 2.0 s (99), x1.7 5.8 s (179).
- small provider solve: 3.6 ms.

## In progress
- Tests in `tests/engine/solve/`.

## Remaining
1. Tests: spec answers, membership, failures, random (exact rational reference; distance vs
   enumeration; fair vs brute force). 2. Bench: join, again; verify Newton vs QP at 300 places.
3. Final STATE.md and last message.
