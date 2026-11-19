# Speed of declared solvers

**Status:** in progress. Three speedups that change no answer are done (2026-11-19, the owner's
change 18 of the rewrite plan). The rest of this page is the plan for what was deferred.

## The need

A declared solver chooses its answer by the selection order of the specification: the hard
constraints, the written objectives in order, fair sharing of the claims, then the flows nearest
their requests and the other unknowns nearest their references. The solve library
(`napkin/engine/solve/`) does this with an exact rule for each step.

On the network of prototype A3 at 30,000 places (30,000 places, 35,000 routes, 15,000 sources), the
two last steps were too slow for use:

- fair sharing took 150 to 600 s, one linear program for each level (459 programs at normal need,
  1,779 at need x1.7);
- the distance step took 342 s at normal need, and gave no answer under shortage;
- the engine's own problem for that network did not finish its first solve in 45 minutes.

The owner's priorities are defensibility, then speed, then precision. A run of 20 minutes is not
used, and inputs are uncertain by tens of percent, so 1e-7 against 1e-10 is not a reason to be slow.
What is defensibility is kept exact: each store's books balance, equal claims get equal shares, each
value stays in its range, and a run that cannot answer stops with a named failure.

## What was measured

Prototype P1 measured other solvers and other settings for the two steps. Its scripts are in
`scratch/rewrite/p1/` at commit `48a276c`, with its findings (`FINDINGS.md`). Its data files were
kept outside the repository and are not part of the record; the scripts make them again.

- The library as of commit `cb6661d`, numpy 2.5.3 and scipy 1.18.1 (the lock; SciPy holds HiGHS
  1.12.0), and in a separate environment clarabel 0.11.1, piqp 0.7.0, osqp 1.1.3, qpsolvers 4.13.0,
  highspy 1.16.0 and qdldl 0.1.9.post1.
- One thread in every solver, four shared cores, the machine load with each time. At 3,000 places a
  time is the best of three runs; at 30,000 places there is one run, one case at a time, stopped at
  15 minutes.
- The problems: A3's network as the library's bench forms it (`scratch/rewrite/b1/solve/bench.py`),
  in A3's four cases: normal need, need x1.45, 1,000 routes down ("damaged"), need x1.7. Also the
  problem that the engine forms for the same network at its first solve
  (`scratch/rewrite/b1/s5-engine/bench.py`).
- Each method solved the same problem as the library's step: the face at the start of the distance
  step, or the face and basis after the objective for fair sharing.
- Correctness first: each method took the place of the library's step in every test of
  `tests/engine/solve/test_spec_answers.py` (the specification's answers) and `test_random.py` (exact
  rational references, its deep sweep included): 827 cases, or 822 for a distance method (five
  cases test the library's own fallback). Each error was recorded against the test's own tolerance.

## The measured tables

### Correctness against the exact references

| Method | Spec cases | Whole order (330) | Distance alone (400) | Fair on networks (60) |
| --- | --- | --- | --- | --- |
| library | 37/37 | 330 (2e-6) | 400 (9e-9) | 60 (5e-7) |
| library with qdldl | 37/37 | 330 (2e-6) | 400 (9e-9) | 60 (5e-7) |
| Clarabel | 28/32 (2e-4) | 251 (5e-4) | 343 (5e-4) | 59, 1 named stop |
| Clarabel, tolerances 1e-10 | 30/32 (4e-5) | 329 | 355 | 59, 1 named stop |
| PIQP | 28/32 (8e-5) | 261 (2e-4) | 349 (4e-4) | 60 |
| OSQP, eps 1e-9 with polish | 32/32 | 329, 1 named stop | 400 (4e-9) | 60 |
| PIQP, then OSQP's polish | 32/32 | 330 (1e-6) | 400 | 60 |
| fair: highspy / parts | 37/37 | 330 | 400 | 60 (5e-7) |
| fair tolerance 1e-7, FIX 1e-7 | 37/37 | 330 | 400 | 59, 1 named stop |
| fair FIX 1e-6 | 35/37 | 329 | 400 | 39 (levels off by up to 1.5e-3) |
| distance tolerance 1e-7 | 37/37 | 330 | 372 (9e-7) | 53, 7 named stops |

A number in brackets is the largest error. A named stop is a `SolveFailure`: no method gave a
different answer without a stop.

### The distance step, P1

| Problem | Method | Time | Newton steps or iterations | Rows missed | Against the library |
| --- | --- | --- | --- | --- | --- |
| 30,000 normal | library (SuperLU) | 342 s | 447 + 3 | 9e-14 | - |
| 30,000 normal | library, qdldl | 75 s | 446 + 3 | 1e-13 | 6e-7 |
| 30,000 normal | Clarabel | 4.4 s | 29 + 7 | 8e-9 | 9e-6 |
| 30,000 normal | PIQP | 16 s | at its iteration limit | 5e-8 | 4e-6 |
| 30,000 normal | OSQP | named stop after 269 s | | | |
| 30,000 damaged | library, qdldl | 60 s | 355 + 4 | 3e-14 | |
| 30,000 x1.45 | library, qdldl | did not finish in 15 min | | | |
| 30,000 x1.7 | library, SuperLU or qdldl | named stop after 315 s or 93 s | 500 (also 2,000) | | |
| 30,000 x1.45 and x1.7 | Clarabel, PIQP | fail, or stop at their iteration limit | | up to 8e-2 | |
| 30,000, engine's problem | library, SuperLU or qdldl | did not finish in 15 min | | | |
| 30,000, engine's, rows merged | library, SuperLU / qdldl | 377 s / 81 s | 455 + 3 / 448 + 3 | | |
| 30,000, engine's problem | Clarabel, PIQP | fail, or stop at their iteration limit | | 1e-3, 3e-6 | |
| 3,000 normal / x1.45 / damaged / x1.7 | library | 3.6 / 4.7 / 2.2 / 6.2 s | 99 / 144 / 98 / 177 + 3 | 1e-13 | - |
| 3,000, same | library, qdldl | 1.4 / 1.8 / 1.3 / 2.3 s | 114 / 161 / 130 / 193 + 3 to 23 | 2e-8 | 4e-8 |
| 3,000, same | Clarabel | 0.3 s each | 24 to 28 + 7 | 1e-8 | 6e-6 |
| 3,000, engine's problem | library / qdldl / Clarabel | 8.4 / 1.7 / 0.7 s | 94 + 3 | | Clarabel misses rows by 0.5 |

### Fair sharing, P1

| Problem | Variant | Time | Programs | Renewals | Levels against the library |
| --- | --- | --- | --- | --- | --- |
| 30,000 normal | library | 150 s | 459 | 0 | - |
| 30,000 normal | highspy 1.16 | 158 s | 459 (same iterations) | 0 | the same bits |
| 30,000 x1.45 | library | 396 s | 1,287 | 29 | - |
| 30,000 x1.45 | tolerance 1e-7 | 439 s | 1,287 | 0 | 7e-8 |
| 30,000 x1.45 | refactorization every 1,000 updates | 490 s | 1,287 | 114 | 6e-8 |
| 30,000 damaged | library | 174 s | 693 | 0 | - |
| 30,000 damaged | parts | 67 s | 22 | 0 | 5e-11 |
| 30,000 x1.7 | library | 602 s | 1,779 | 43 | - |
| 30,000 x1.7 | tolerance 1e-7 | 658 s | 1,778 | 0 | one claim 1.2e-6 (a near-tie) |
| 30,000, engine's problem | library | 225 s | 459 | 16 | - |
| 30,000, engine's problem | tolerance 1e-7 | 176 s | 459 | 0 | 7e-10 |
| 3,000 damaged | library / parts | 1.5 / 0.5 s | 71 / 9 | 0 | 3e-12 |
| 3,000 normal | primal / dual simplex | 1.3 / 2.6 s | 50 | 0 | 9e-13 |

The loads were 1 to 3. Each method gave the same answer bit for bit when it ran again, in one
process and in two, with one thread.

## What was adopted, and why

The owner's change 18 takes the speedups that give the same answers up to the tolerances of the
steps. All three keep the rules of the selection order; none adds a tolerance.

1. **A store held at both bounds is one equality** (`napkin/engine/timeline/declared.py`,
   `Former.problem`). The engine wrote such a store, for example one held at 0 Wh, as two rows of
   opposite sign. The objective's step makes one of them an equality, and the other keeps a slack in
   the distance method: at 30,000 places a Newton system of 316,000 unknowns instead of 233,000, and
   2.8 s for one factorization instead of 0.7 s. One row `==` is the same set of answers.
2. **LDL' by qdldl in the distance method** (`napkin/engine/solve/distance.py`). The method's
   Newton system is quasi-definite, and its pattern stays the same over a stage. qdldl orders it and
   analyses its pattern once a stage, and each step factorizes the new values alone. Without
   pivoting, LDL' can be inaccurate on these systems: a solve whose backward error is above 1e-10,
   or a factorization that qdldl refuses, makes the stage go on by SuperLU from the point that it has
   reached. A stage that does not converge so runs again by SuperLU alone. qdldl 0.1.9 is Apache-2.0,
   with wheels for CPython 3.8 to 3.14 on Linux, macOS and Windows, x86-64 and ARM.
3. **Fair sharing in connected parts** (`napkin/engine/solve/fair.py`). Claims that share no row,
   through the columns that the face leaves free, are independent. Each part gets its own level
   variable in one program, which is the parts' programs side by side. The number of programs is that
   of the part with the most levels, not their sum. A connected network is one part, as before.

The new times, with the library's bench (`scratch/rewrite/b1/solve/bench.py`) and
`scratch/rewrite/p1/adopted.py`:

| Problem | Objective | Fair sharing | Distance | Before (fair, distance) |
| --- | --- | --- | --- | --- |
| 30,000 normal | 4.8 s | 155 s, 459 programs | 45 s, 446 + 3 steps | 150 s, 342 s |
| 30,000 damaged | 4.5 s | 35 s, 22 programs | 25 s, 341 + 3 steps | 174 s, not measured |
| 30,000 x1.45 | 6.5 s | 396 s, 1,261 programs, 34 renewals | did not finish in the 8 minutes left of the 15 | 396 s, no answer |
| 30,000 x1.7 | 7.5 s | 607 s, 1,748 programs, 42 renewals | did not finish in the 5 minutes left of the 15 | 602 s, no answer |
| 3,000 normal | 0.2 s | 1.4 s | 1.0 s | 1.2 s, 3.7 s |
| 3,000 x1.45 | 0.2 s | 3.2 s | 1.5 s | 3.1 s, 4.4 s |
| 3,000 damaged | 0.2 s | 0.5 s, 9 programs | 0.7 s | 1.4 s, 2.1 s |
| 3,000 x1.7 | 0.3 s | 3.9 s | 1.2 s | 4.2 s, 5.3 s |

The engine's bench (`scratch/rewrite/b1/s5-engine/bench.py`, two solves over 48 h): at 3,000 places
the run takes 18.2 s instead of 31.7 s, and the solve library 5.9 s instead of 21.8 s. At 30,000
places: PENDING.

## What was deferred

### Fair sharing at the primal tolerance 1e-7

The programs of fair sharing run at HiGHS's tightest primal tolerance, 1e-10, with the check of each
answer and the renewal of an instance that fails. At 1e-7 (FIX staying at 1e-7) the renewals end at
30,000 places (29, 43 and 16 become 0) and the levels stay within 7e-8, but one claim at need x1.7
moves by 1.2e-6, and the time is the same. On one random network of 60, two claims whose levels are
9e-7 apart are held together at a level that the first cannot keep, the face is empty, and the solve
stops by name. FIX itself must stay at 1e-7: at 1e-6 the later levels move by up to 1.5e-3, the slack
of the held floors amplified through the loops of the routes.

### The interior-point path

Clarabel answered the distance step at 30,000 places at normal need in 4.4 s (45 s now with qdldl).
But an interior-point method stops about the square root of its tolerance away from a bound that
holds the nearest point with no multiplier: the specification's pump serves 6.00017 L/h where the
answer is 6. Clarabel also failed on the engine's problem and under shortage, and PIQP stopped at
its iteration limit there. OSQP's polish made the small cases exact but not the large ones. A path
by an interior-point method needs a polish that is exact at scale, and a fallback by name.

### Precision profiles

A precision profile is a named set of tolerances and methods for the solvers, such as `default` and
`fast`. The design:

- The profile is part of the run's identity: its store key, its record, its checkpoint and the line
  of its report name it, so that two runs with different profiles are never the same run.
- The strict invariants are exact in every profile: each store's books balance, equal claims get
  equal shares, each value stays in its range, a never-falls proof holds, and a near-tie (a choice of
  who is served within the tolerance of its boundary) is reported with its size.
- A profile that cannot answer falls back by name: the record says which step fell back to which
  profile, and a step that `default` cannot answer either stops with its named failure.
- Published runs use `default`.

## The open cases

Need x1.45 and need x1.7 at 30,000 places. In P1 the distance step gave no answer: at x1.45 it did
not finish in 15 minutes, and at x1.7 the method did not converge in 500 Newton steps (nor 2,000),
and HiGHS's QP then called the face infeasible. That face is feasible at HiGHS's primal tolerance
1e-9 and infeasible to HiGHS at 1e-7. After the adoption the two cases are still open: fair sharing
takes 396 s and 607 s, and the distance step does not finish in what is left of 15 minutes.

## The changes

- `napkin/engine/timeline/declared.py`: one row `==` for a store at both bounds.
- `napkin/engine/solve/distance.py`: `_LDL` (qdldl, two refinement steps), the switch to SuperLU in
  `_Dual`, the second run of a stage by SuperLU alone in `stage`.
- `napkin/engine/solve/fair.py`: `_parts` and one level variable for each part in `_tier`;
  `kept.Kept.start_at_upper` takes several columns.
- `napkin/engine/solve/solver.py`: `Work.superlu`, the runs of a stage that SuperLU factorized.
- `pyproject.toml` and `requirements.lock`: `qdldl`.

What stays: the tolerance 1e-10 of fair sharing with its renewals, FIX 1e-7, a refactorization
every 100 updates, SciPy's HiGHS, the primal simplex after the first program, and the QP of HiGHS as
the last fallback of the distance step. A checkpoint holds the same state of a solver as before (its
program, basis and last problem): none of the three changes keeps anything between two solves.

## The checks

- `tests/engine/solve/`: 182 tests and the deep sweep; new: parts that share no row share their
  programs, and a stage whose LDL' solve misses its accuracy goes on by SuperLU.
- `tests/engine/test_solvers.py` (new: a store held at both bounds is one equality),
  `test_random_solvers.py` (with its 900 deep cases), `test_programs.py`, `test_checkpoints.py` and
  `test_edits.py`: 287 tests.
- Exact resume three ways (no stop, a stop resumed in one process, a stop resumed in a fresh process)
  for a solver with two stores held at 0 L and two parts: the same record.

## The risks and the open questions

- The Newton method can need a different number of steps when its factorization changes, and on some
  faces LDL' leads it astray; the switch to SuperLU and the second run guard the answer, at the cost
  of time where they act.
- Fair sharing on a connected network is still one program for each level (155 to 660 s at 30,000
  places). Holding every claim that cannot rise in one program would save at most the programs that
  repeat a level (under 1 % on a connected network).
- Whether need x1.45 and x1.7 at 30,000 places answer now (above), and if not, what the distance step
  needs there.
