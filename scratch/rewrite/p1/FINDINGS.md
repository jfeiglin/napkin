# P1 findings: other solvers for fair sharing and the distance step

Records are in `/home/user/p1-data` (`distance.jsonl`, `fair.jsonl`, `correct.jsonl`, `logs/`). `table.py` prints the tables from them.

## What was measured

- **Library:** `napkin/engine/solve` of cb6661d (each answer checked, renewal on a miss), hash 922afd1210e6 in every record. The exceptions are three fair records (x1.7 at tol 1e-7; normal and x1.45 at UPDATES 1,000), which ran on ef2d9bf. Its change adds `Kept.fresh`/`of` and `Solver.renew`, which a first solve on a fresh Solver does not call.
- **Environment:** `/home/user/venvs/p1` with numpy 2.5.3 and scipy 1.18.1 as in the lock (SciPy bundles HiGHS 1.12.0). Added: clarabel 0.11.1, piqp 0.7.0, osqp 1.1.3, qpsolvers 4.13.0, highspy 1.16.0, qdldl 0.1.9.post1, and pytest 9.2.0 only to import the tests' helpers.
- **Settings:** one thread everywhere; four shared cores, with the load in every record. At 3,000 places each time is the best of three; at 30,000 there was one run, one case at a time, stopped at 15 minutes.
- **Problems:** A3's network as the library's bench forms it, in A3's four scenarios. Also the `Problem` the engine gives `Solver.solve` at its first solve, caught by replacing `Solver.solve` while running the engine's bench program.
- **Same problem for every candidate:** the face at the start of `distance.select`, and the face plus basis after the objective for fair sharing (`lab.export`).
- **Correctness** (`correct.py`): each method replaced the library's step in every test of `test_spec_answers.py` and `test_random.py`, including the deep sweep run seed by seed: 827 cases. Distance candidates get 822, because five cases test the library's own QP fallback.

## Correctness against the exact references

| method | spec | whole order (330) | distance alone (400) | fair on networks (60) |
|---|---|---|---|---|
| library | 37/37 | 330 (2e-6) | 400 (9e-9) | 60 (5e-7) |
| library + qdldl | 37/37 | 330 (2e-6) | 400 (9e-9) | 60 (5e-7) |
| Clarabel (default / tolerances 1e-10) | 28/32 (2e-4) / 30/32 (4e-5) | 251 (5e-4) / 329 | 343 (5e-4) / 355 | 59, 1 stop |
| PIQP (default / tolerances 1e-10) | 28/32 (8e-5) / 30/32 | 261 (2e-4) / 262 | 349 (4e-4) / 354 | 60 |
| OSQP (eps 1e-6 / 1e-9, polish on) | 32/32 | 329, 1 stop | 396 (7e-6) / 400 | 58 / 60 |
| PIQP, then OSQP's polish | 32/32 | 330 (1e-6) | 400 | 60 |
| Clarabel, then OSQP's polish | 32/32 | 330 | 400 | 48, 12 stops |
| Newton started from an IPM's point | 32/32 | 330 | 400 | 60 |
| fair: highspy primal / dual / parts | 37/37 | 330 | 400 | 60 |
| fair tol 1e-7 or 1e-6, FIX 1e-7 | 37/37 | 330 | 400 | 59, 1 stop |
| fair FIX 1e-6 | 35/37 | 329 | 400 | 39 (levels off by up to 1.5e-3) |
| distance TOL 1e-7 | 37/37 | 330 | 372 (9e-7) | 53, 7 stops |

A "stop" is a named `SolveFailure`. No method gave a quietly wrong answer: every failure was either a stop by name or an error measured above.

## The distance step

| problem | method | s | steps (two stages) | status | rows missed | vs library (flows, levels) |
|---|---|---|---|---|---|---|
| 30k normal | library | 342 | 447+3 | | 9e-14 | – |
| 30k normal | library + qdldl | 75 | 446+3 | | 1e-13 | 6e-7, 6e-7 |
| 30k normal | Clarabel | 4.4 | 29+7 | solved | 8e-9 | 9e-6, 1e-6 |
| 30k normal | Clarabel, boxed second stage | 16.5 | 29+85 | solved | 5e-9 | 9e-6, 1e-6 |
| 30k normal | PIQP / boxed / 1,000 iterations | 16 / 24 / 99 | iteration cap | | 5e-8 / 4e-8 / 4e-8 | 4e-6 / 4e-6 / 2e-6 |
| 30k normal | OSQP | stopped after 269 s | | | | |
| 30k damaged | library + qdldl | 60 | 355+4 | | 3e-14 | |
| 30k damaged | Clarabel | 5.2 | 32+7 | solved | 6e-9 | |
| 30k x1.45 | library + qdldl | did not finish in 15 min | | | | |
| 30k x1.45 | Clarabel | fails: a row of fixed columns misses | | | | |
| 30k x1.7 | library | stops after 315 s | 500 steps | QP fallback: infeasible | | |
| 30k x1.7 | library + qdldl, 500 / 2,000 steps | stops after 93 / 368 s | | same | | |
| 30k x1.7 | Clarabel, boxed | 14.6 | | almost solved, then primal infeasible | 8e-2 | |
| 30k x1.7 | PIQP, boxed | 23.6 | iteration cap | | 8e-7 | |
| 30k engine | library / library + qdldl | did not finish in 15 min | | | | |
| 30k engine, rows merged | library / library + qdldl | 377 / 81 | 455+3 / 448+3 | | | |
| 30k engine | Clarabel (also merged) | fails | | insufficient progress / primal infeasible | 1e-3 (0.5 merged) | |
| 30k engine | PIQP | iteration cap | | | 3e-6 | |

**At 3,000, distance step, best of three** (all bitwise repeatable). Seconds per method, Newton steps or IPM iterations in brackets; problems are the four bench scenarios and the engine's problem:

| problem | library | library + qdldl | Clarabel | PIQP, boxed | OSQP | library TOL 1e-7 |
|---|---|---|---|---|---|---|
| normal | 3.62 (99+3) | 1.35 (114+23) | 0.34 | 0.12 | 0.72 | 3.51 (93+3) |
| x1.45 | 4.67 (144+3) | 1.77 (161+3) | 0.34 | 1.56 (cap) | 1.87 | 4.18 |
| damaged | 2.21 | 1.27 | 0.32 | 0.77 | 0.76 | 2.25 |
| x1.7 | 6.22 (177+3) | 2.29 (193+3) | 0.35 | 1.51 (cap) | 2.28 | 5.91 |
| engine | 8.41 (94+3) | 1.69 (94+3) | 0.67 (second stage fails, rows 0.5) | 0.16 | stops | 8.62 |

At 3,000, qdldl's answers are within 1e-14 to 4e-8 of the library's; Clarabel's within 2e-7 to 6e-6; OSQP's within 4e-6 to 9e-5.

**Notes on the candidates:**
- **Precision of interior-point methods.** An IPM stops about √tolerance away from a bound or row that holds the nearest point with no multiplier, that is, a target exactly on its bound. Examples: a supply at a target of 0, a use at its need, the spec's pump serving 6.00017 L/h for 6.
- **Second stage.** Fixing first-stage flows that meet their rows only to the IPM's tolerance leaves the levels' rows inconsistent. Clarabel then reports almost-infeasible and returns x anyway, so an adopter must check its status. PIQP needs the box.
- **OSQP's polish** makes small problems exact, but at 3,000 it fails and its iterate is no better than the IPM's.
- **Newton started from an IPM:** from the IPM's dual it stalls (residual 6e-6 rising to 1.7e-4); from the IPM's centres it takes 78 steps instead of 99.
- **qdldl regularized** to -1e-10 in the (2,2) block and refined against the true system: it reproduces SuperLU's answers on the bench faces, but fails the engine's 3,000 face and does not finish the 30,000 normal case. Not recommended.
- **Looser distance TOL (1e-7):** 6% fewer steps, the same time, and 7 stops on small networks. Not worth it.

## The engine's problem is harder

- **Doubled rows.** The engine writes a store held at [0, 0] as two rows, `-b.x <= 0` and `b.x <= 0`. The objective's pinning makes one an equality; the other keeps a slack.
- **Size at 30,000:** the Newton system grows from 233k to 316k unknowns (81k slacks instead of 25k), SuperLU's fill from 4.0M to 9.4M, and each factorization from 0.69 s to 2.79 s. The Newton steps also do not converge in 15 minutes, with either factorization.
- **Merged into one equality,** the face matches the bench's numbers: 377 s with SuperLU, 81 s with qdldl.
- **Smaller differences:** the levels' scale is 60 (their finite width) instead of 1, and there is one supply per place.

## Fair sharing

Fair-only iterations; the 30,000 baselines come from the exports.

| problem | variant | s | programs | levels | iterations | renewals | vs library | load |
|---|---|---|---|---|---|---|---|---|
| 30k normal | library | 150 | 459 | 459 | 28,436 | 0 | – | 1.1 |
| 30k normal | highspy, primal | 158 | 459 | 459 | 28,436 | 0 | bitwise equal | 1.9 |
| 30k normal | UPDATES 1,000 | 143 | 459 | 459 | 28,296 | 0 | 1e-10 | 2.8 |
| 30k x1.45 | library | 396 | 1,287 | 1,282 | 108,299 | 29 | – | 2.2 |
| 30k x1.45 | tol 1e-7 | 439 | 1,287 | 1,280 | 49,391 | 0 | 7e-8 | 3.2 |
| 30k x1.45 | UPDATES 1,000 | 490 | 1,287 | 1,282 | 41,230 | 114 | 6e-8 | 1.2 |
| 30k damaged | library | 174 | 693 | 531 | 28,598 | 0 | – | 1.6 |
| 30k damaged | connected parts | 67 | 22 | 531 | 97,308 | 0 | 5e-11 | 1.5 |
| 30k x1.7 | library | 602 | 1,779 | 1,771 | 244,863 | 43 (1 tight) | – | 1.7 |
| 30k x1.7 | tol 1e-7 | 658 | 1,778 | 1,771 | 67,336 | 0 (1 tight) | one claim off by 1.2e-6 | 2.1 |
| 30k engine | library | 225 | 459 | 459 | 88,539 | 16 (3 tight) | – | 2.5 |
| 30k engine | tol 1e-7 | 176 | 459 | 459 | 26,157 | 0 | 7e-10 | 1.1 |

**At 3,000** (normal / x1.45 / damaged / x1.7 / engine, seconds):

| variant | normal | x1.45 | damaged | x1.7 | engine |
|---|---|---|---|---|---|
| library | 1.44 | 2.98 (1 renewal) | 1.53 (71 programs, 61 levels) | 4.93 | 1.70 |
| highspy, primal | 1.26 | 2.97 | 1.47 | 4.81 | 1.47 |
| highspy, dual | 2.64 (21,057 iterations against 2,188) | | | | |
| connected parts | 1.26 | 2.89 | 0.51 (9 programs) | 4.68 | 1.43 |
| tol 1e-7 | 1.28 | 3.38 (0 renewals) | 1.44 | 4.69 | 1.56 |
| tol 1e-6 | 0.81 | stops: infeasible at program 85 | 1.10 | its distance face fails | 0.97 |

At 3,000, levels agree with the library's within 3e-11 in every variant except tol 1e-6, which stopped or failed as shown.

**Why there are not fewer programs:**
- Programs nearly equal levels: 459 for 459, 1,287 for 1,282, 1,779 for 1,771. Damaged is the exception (693 for 531), and parts already remove its repeats.
- The sequential rule needs one program per level on a connected face, and every route's law row links the levels at its two ends, so A3's normal, x1.45 and x1.7 faces are each one part.
- Holding every claim that cannot rise would save at most the repeats. A bisection costs about 30 feasibility programs per level, and a parametric simplex in t is in neither HiGHS binding.
- **Cost per program at 30,000:** 0.33 s, of which 31 ms is a run with no change. The rest is simplex iterations and refactorizations.

## Tolerances, robustness, near-ties

- **Fair tolerance 1e-7 (FIX 1e-7):**
  - Renewals at 30,000 go to zero (29, 43 and 16 go to 0, and the engine's 3 tight runs to 0). Iterations halve or better, and the time is about the same.
  - Levels stay within 7e-8, except one claim at x1.7 that moves by 1.2e-6 (claim 15965, from 0.9999248 to 0.9999237), a near-tie.
  - Cost: on 1 of 60 random networks (seed 58), two claims whose exact levels are 0.9999989 and 0.9999998 (9e-7 apart) are held together at 0.9999993. That is 4e-7 above the first claim's maximum and larger than FIX, so the face is empty and the solve stops by name. This is the case the library's docstring describes.
- **Fair tolerance 1e-6:** stops on x1.45 at 3,000, and x1.7's distance face fails.
- **FIX 1e-6:** later levels move by up to 1.5e-3 (seed 31: 0.999838 to 0.99838; 0.0412624 to 0.0421402). The held floors' slack is amplified about 900x through the routes' loops. FIX shapes the answer itself and must stay 1e-7.
- **UPDATES:** 1,000 instead of 100 gives normal -5%, but x1.45 +24% with 114 renewals.
- **x1.7 at 30,000:** the face at the start of the distance step is feasible at HiGHS primal tolerance 1e-9 (no floor needs widening) but infeasible at 1e-7. The Newton method does not converge in 500 or 2,000 steps, and the QP fallback then reports infeasible.

## Strict invariants

- **Library's own answers:**
  - books balance to 6e-15 relative;
  - bounds hold exactly;
  - equal claims are equal only to within FIX divided by their dual: one level's claims differ by up to 1.2e-5 at 3,000 and 7.9e-6 at 30,000.
- **After the engine's `polished` (NEAR 1e-6):** books ≤ 4e-15 W, equal-share spread ≤ 4e-16, bounds 0. This holds for every method whose answer met its rows to 1e-6.
- **Where the polish cannot help:** Clarabel's failed stages (rows missed by 1e-3 to 0.5).

## Determinism

Bitwise equal in three runs within one process, in two processes, and at 30,000 for Clarabel and for the connected-parts variant, all with one thread. What each needs:
- **HiGHS:** fixed threads.
- **Clarabel:** its default QDLDL solver; the `faer` solver is threaded.
- **PIQP:** nothing, but it loads an AVX-512, AVX2 or plain build by CPU, so another CPU gives other bits within tolerance.
- **OSQP 1.1:** adapts rho every 50 iterations, which is deterministic.
- **qdldl:** serial.

For parallel samples: each Solver is independent and single-threaded, and connected parts could be solved in parallel.

## Packages

| package | version | license | wheels |
|---|---|---|---|
| clarabel | 0.11.1 | Apache-2.0 (needs cffi) | abi3 for CPython 3.9+: Linux x86-64/aarch64, macOS x86-64/arm64, Windows x64 |
| piqp | 0.7.0 | BSD-2 | CPython 3.8–3.14: Linux glibc/musl x86-64/aarch64/i686, macOS, Windows x64 |
| osqp | 1.1.3 | Apache-2.0 | CPython 3.8–3.14: Linux, macOS, Windows x64 |
| qpsolvers | 4.13.0 | LGPL-3.0 | pure Python |
| highspy | 1.16.0 | MIT | CPython 3.9–3.15: all major platforms |
| qdldl | 0.1.9.post1 | Apache-2.0 | CPython 3.8–3.14: Linux and macOS x86-64/arm64, Windows x64/arm64 |

## Recommendation

1. **Engine** (`timeline/declared.py`, `Former.problem`): write a store at both bounds as one row with lower equal to upper. No new dependency, the same rule, and the engine's first solve at 30,000 answers.
2. **Library** (`distance._Dual.solve`):
   - factorize by qdldl, with the pattern analysed once per stage and two refinement steps;
   - fall back to SuperLU for a stage that qdldl leaves unconverged;
   - new dependency qdldl (Apache-2.0); 4.6x faster at 30,000.
3. **Library** (`fair._tier`): connected parts in one program, one level variable per part. Exact, no new dependency.
4. **Keep** SciPy's HiGHS, the primal simplex, tolerance 1e-10 with renewals, FIX 1e-7 and UPDATES 100.
5. **Do not adopt** Clarabel, PIQP, OSQP or qpsolvers for the distance step.
6. **Open:**
   - distance answers for x1.45 and x1.7 at 30,000;
   - one fair-sharing program per level on connected faces (150–660 s at 30,000).
