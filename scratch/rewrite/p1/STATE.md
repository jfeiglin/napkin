# P1 state: other solvers for fair sharing and the distance step (60 lines at most)

Brief `briefs/p1-solvers.md` (+ COMMON-B rules). Prototype: code here, data in /home/user/p1-data
(pickled faces, answers, `*.jsonl` records, `logs/`), environment /home/user/venvs/p1 (numpy 2.5.3,
scipy 1.18.1 as the lock; clarabel 0.11.1, piqp 0.7.0, osqp 1.1.3, qpsolvers 4.13.0, highspy 1.16.0,
pytest 9.2.0 to import the tests' helpers). Library measured: `napkin/engine/solve` of cb6661d (the
check of each answer and the renewal), unchanged since (hash 922afd1210e6 in every record).

## Files
- `lab.py`: problems (bench, engine's first-solve Problem), `prefix` (library up to the distance
  start), `export` (pickles the state after the objective and at the distance start), `measures`.
- `qp.py`: distance candidates through qpsolvers (`-box`: second stage holds flows within 1e-8).
- `fairs.py`: fair variants on highspy (`highs-primal`, `highs-dual`, `pieces`), `--tol`, `--fix`.
- `correct.py`: each method in the library's place on test_spec_answers + test_random (with its deep
  sweep, seed by seed: 827 cases), errors recorded against each test's tolerance.
- `hybrid.py`: IPM then the library's Newton from the IPM's point (no gain: 500 steps from its dual,
  78 instead of 99 from its centres; kept as a negative result).
- `harder.py`: why the engine's problem is harder (SuperLU fill, store rows merged).
- `exports.sh`, `queue.sh`: the 30,000-place runs, one at a time, 15 minutes each.

## Findings so far (3,000 places unless said)
- Engine's problem: each store held at [0, 0] is two `<=` rows; after pinning one is an equality and
  the other keeps a slack (3,000 more rows, 5,430 more slacks); level scale 60. Merged into one
  equality, the library's distance takes 3.1 s instead of 8.3 s (the bench's 3.3 s).
- Raw IPMs lose precision where a target lies on a bound held with no multiplier (sqrt(tol)): vs the
  exact references Clarabel 4.6e-4, PIQP 3.6e-4 (library 1.8e-6); 141 / 124 of 822 cases fail.
- Clarabel's second stage can end AlmostPrimalInfeasible (engine 3,000; x1.7 with box) and its x
  then misses rows by 0.5; PIQP with the box solved all five problems; OSQP loose (1e-7 rows, 6e-5
  answers), fails the engine's problem.
- Distance at 3,000: library 2.2-8.1 s; PIQP-box 0.12-1.5 s; Clarabel 0.3-0.6 s; TOL 1e-7 saves
  6% of Newton steps only (the steps find the free set; the last digits are cheap).
- Fair: highspy 1.16 = SciPy's 1.12 in time; dual simplex 2x slower (the warm basis is primal
  feasible); pieces: damaged 71 -> 9 programs (3x), others 1 big part (no gain). Primal tolerance
  1e-7 keeps every level (<= 3e-11), FIX must stay 1e-7: FIX 1e-6 moves later levels by up to
  1.5e-3 on random 9-place networks (amplified 1,000x through the routes' loops).
- Tol 1e-6: shortage stops by name (kInfeasible at program 85), x1.7's distance face infeasible.
- Every method gave bitwise equal answers on three runs in one process (threads 1).

## In progress
- Queue (`/home/user/p1-data/queue.txt`, log `logs/queue.log`): library and candidates at 30,000,
  engine at 30,000, fair variants at 30,000.

## Remains
- 30,000 results into FINDINGS.md; determinism across processes; recommendation.
