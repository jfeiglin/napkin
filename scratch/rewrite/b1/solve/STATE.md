# B1-S state: the solve library (update at each milestone; 80 lines at most)

## Done (milestone 3, final: package, tests, bench; S6: 180 tests in 3 s, deep sweep 16 s)
- `napkin/engine/solve/`: `problem.py` (Problem, Arrays: keyed unknowns/rows, positive parts,
  claims), `scaled.py` (working units, reorder), `kept.py` (Kept: one HiGHS instance tracking its
  bounds; `quadratic`: QP fallback on its own instance), `failures.py`, `ranked.py` (Face, pin, exact
  duals, status -> failure, `lost`), `fair.py`, `distance.py`, `solver.py` (Budget, Work, Answer,
  Solver: sync by keys, order, end checks), `__init__.py`.
- `tests/engine/solve/`: `cases.py` (spec problems), `exact.py` (rational reference: simplex,
  brute-force fair, Fourier-Motzkin, active sets), `test_spec_answers.py` (37), `test_membership.py`
  (8), `test_failures.py` (29, S6-S: +6), `test_random.py` (106 + 1 deep sweep of 684 cases).
- `scratch/rewrite/b1/solve/bench.py`: sections small, fair, objective, after, join, again, verify.

## Decisions (one line each, with the reason)
- Sync by keys: each solve takes the whole problem; the kept instance deletes what left, adds what
  joined, replaces a row whose working coefficients changed (equal to the fresh program).
- One Solver per run, no module state; the QP fallback has its own instance: the same run, repeated,
  is identical; alone and in a batch agree within the tolerances (the owner's rule, S6).
- Budgets: fair 1,000 programs; distance 500 Newton steps per stage, then 100,000 QP iterations.
- Exact line search everywhere (Armijo stalls on fair faces: two bottlenecks fail with Armijo).
- Proximal weight 1 -> 1e-3, tenfold after a prox problem of <= 3 Newton steps (A3's 1e-3 from the
  start never converged after fair).
- Prox stop: eps * move <= precision of the rows (A3's move <= 1e-9 cycled on tiny problems).
- Stall rule: 10 steps without halving the residual and all rows within 1e-7 -> met at 1e-7
  (1,000 places x1.45: 1,059 -> 163 steps). A stall-triggered LM term was tried: worse; removed.
- Fair programs at HiGHS's tightest primal tolerance (1e-10): at 1e-7 t* overshot FIX on a random
  8-place network, the face was empty at 1e-9 and the method cycled. P1 (`scratch/rewrite/p1/`)
  decides this tolerance and FIX (S6); the code keeps them.
- HiGHS QP: kSolveError on the 3,000-place fair face, cycles on the worked network's fair face
  (A3's success did not reproduce); kept as the fallback; it agrees with the method at 300/1,000.
- QP answer clipped into the face's bounds; kept-optimum check per term: 1e-7 * sum |c|(1+|x|).
- Pin only where the dual's sign matches the side the value rests on; wrong sign > 1e-9 -> one
  more run at tolerances 1e-10. Sides read from values (no getBasis conversions: 5 ms a program).
- Constant claims held without a program; np.maximum.at for claims sharing a column.
- Positive parts recomputed as max(0, e.x + e0) before the end checks and in the answer.
- Crossed bounds and failing empty rows -> 'infeasible' before any program (names the key).

## Bench at 3,000 places (A3's network; 4 shared cores, load 0.4-0.8; fair and after: S6)
- fair (objective + fair): normal 0.19 + 1.48 s, 50 programs; x1.45 0.28 + 3.19 s, 125 (1 renewal);
  damaged 0.18 + 1.68 s, 71 (61 levels); x1.7 0.28 + 5.10 s, 170. Levels as with UPDATES 5,000 to 2.3e-11.
- after fair, distance: 4.17 / 5.20 / 2.57 / 6.66 s (Newton 99/144/98/177 + 3); no QP.
- objective face distance: 1.23 / 1.34 / 0.67 s (Newton 35/50/34 + 3).
- join 300 flows: warm 0.06 s vs fresh 0.26 s; leave 0.11 s; optima equal (677.730970160).
- again: optimum cold = warm = 601.853501921; levels within 1.1e-11; the same run repeated: bitwise.
- small (provider, whole order): 3.8 ms fresh, 3.6 ms kept.
- verify (method vs QP): 300 and 1,000 places agree to 6.4e-7 (flows), 2.1e-7 (levels).

## S6-S: fair sharing at 30,000 places (`bench.py fair --share 1.0`; probes were scratchpad only)
- Cause 1, need x1.45: program 678 (fair, t* 0.779, primal tolerance 1e-10) ended kUnknown: an
  optimal basis of HiGHS's scaled program, a bound of the unscaled answer missed by 1.3e-7, and the
  cleanup met a basis change made taboo (HEkkPrimal, kSolvePhaseTabooBasis). The program is sound: a
  fresh instance from the failed run's basis took 0 iterations; dual simplex and cold: t* to 1e-14.
- Cause 2, need x1.7: the kept factorization (HiGHS refactorizes after 5,000 updates) drifted over
  warm programs; HiGHS checks its updated activities, so A x missed a balance row by 1.1e-4 (3.4e-5
  of its size) at program 145, reported optimal, t* 3.4e-7 above the cold fresh solve: the holds cut
  the face, and program 147 was infeasible on every instance (kept, fresh warm, fresh cold).
- Mend: `fair.UPDATES` 100 (drift <= 5.1e-8 there, t* of the fresh solve); `Kept.run`: a status
  outside STATED, or an optimum whose A x (own copy `Kept.A`) misses a row or bound by > MISS 10 x
  the run's primal tolerance (relative), runs again on a fresh instance (program, options, basis),
  then cold (dual simplex); else 'numerical' naming status or miss and size. Same program, same
  answer (D0). Tests: no renewal in 1,588 runs, largest miss 1.2e-3 x tolerance. The engine's calls
  are unchanged; new `Work.renewals`, `Run.answered`/`missed`, `reached` 'rows'/'columns'/'missed'.
- 30,000, fair (`--fair-programs 5000`), objective + fair: normal 4.2 + 152.0 s, 459 programs, no
  renewal; x1.45 6.1 + 396.3 s, 1,287 (1,282 levels), 29 renewals; damaged 3.8 + 175.4 s, 693 (531),
  none; x1.7 6.3 + 586.8 s, 1,779 (1,771), 43. Before: x1.45 kUnknown at 678 (renewal alone: 450 s,
  1 renewal, one program 50 s); x1.7 'no answer on the face' at 147. Budget 1,000: x1.45, x1.7 stop.
- 30,000, whole order, normal (renewal only): objective 4.3, fair 140.8, distance 349.5 s (Newton 439+3).
- Engine (`b1/s5-engine/bench.py`, 30,000, started 08:52:59 UTC): stopped at the owner's cap of 45
  min, still in the first solve (0 h, normal supply), past fair sharing, in the distance step of the
  flows (`distance.nearest`, SuperLU at every sample from 23 to 38 min). No build/plan time printed.

## Decisions (S6-S)
- Default budget 1,000 programs kept (x1.45 at 30,000 stops by name); the engine's is its config's.
- A later program's 'infeasible' is not renewed: HiGHS states it; the drift behind it is checked.
- Owner's rule (`solver`): other runs agree within 1e-6 x size, the same run repeated bit for bit.

## Not done
- Registering the package (`pyproject.toml` packages, `tests/test_api.py` CLOSURE): existing files.
- The engine's problem at 30,000: its distance step did not finish (the bench's in 349.5 s); P1
  looks at why. Fair sharing there costs 150-590 s (one program per level); P1 measures fewer.
