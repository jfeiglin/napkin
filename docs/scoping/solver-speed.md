# Speed of declared solvers

**Status:** in progress. Three speedups that change no answer are done (2026-11-19,
[change 18](../design/decisions.md#change-18) of the owner). The rest of this page is the plan for
what the owner deferred. The words in **bold** type have the meanings that
[the terms](../language/README.md#terms) give.

## The need

A declared **solver** selects its answer by the selection order of the language
([D0](../design/decisions.md#d0)):

1. the hard constraints
2. the written objectives in order
3. fair sharing of the claims
4. the flows nearest their **requests** and the other unknowns nearest their references.

The solve library (`napkin/engine/solve/`) does this with an exact rule for each step.

On the network of prototype A3 at 30,000 places (30,000 places, 35,000 **routes**, 15,000 sources),
the last two steps were too slow for use:

- fair sharing took 150 to 600 s, one linear program for each level (459 programs at normal need,
  1,779 at need x1.7);
- the distance step took 342 s at normal need, and gave no answer under shortage;
- the problem that the engine forms for that network did not finish its first solve in 45 minutes.

The owner ranks defensibility first, then speed, then precision
([change 10](../design/decisions.md#change-10)). A **run** of 20 minutes is not used. The inputs are
uncertain by tens of percent, so 1e-7 against 1e-10 is not a reason to be slow. What is
defensibility stays exact:

- the books of each **stock** balance
- equal claims get equal shares
- each value stays in its range
- a run that cannot answer stops with a named failure.

## What was measured

Prototype P1 measured other libraries and other settings for the two steps. Its scripts and its
findings (`scratch/rewrite/p1/`, with `FINDINGS.md`) are in the archive at commit `ARCHIVE_SHA`
([docs/design/README.md](../design/README.md#archive)). Read them from that commit, for example
`git show ARCHIVE_SHA:scratch/rewrite/p1/FINDINGS.md`. The measurements are of commit `48a276c`.
The scripts of the two adopted speedups (`scratch/rewrite/p1/adopted.py` and
`scratch/rewrite/p1/engine_solves.py`, in the same archive) came after it. The data files of P1 were
outside the repository and are not part of the archive. The scripts make them again.

- The solve library as of commit `cb6661d`, numpy 2.5.3 and scipy 1.18.1 (the lock; SciPy holds
  HiGHS 1.12.0). In a separate environment: clarabel 0.11.1, piqp 0.7.0, osqp 1.1.3, qpsolvers
  4.13.0, highspy 1.16.0 and qdldl 0.1.9.post1.
- One thread in each library, four shared cores, and the load of the machine with each time. At
  3,000 places a time is the best of three runs. At 30,000 places there is one run, one case at a
  time, stopped at 15 minutes.
- The problems: the network of A3 as the bench of the solve library forms it
  (`scratch/rewrite/b1/solve/bench.py` at commit `ARCHIVE_SHA`). The cases are the four cases of A3:
  normal need, need x1.45, 1,000 routes down ("damaged"), and need x1.7. Also the problem that the
  engine forms for the same network at its first solve (`tools/bench/port/s5-engine/bench.py`).
- Each candidate solved the same problem as the step of the library. For the distance step, it is
  the face at the start of that step. For fair sharing, it is the face and the basis after the
  objective.
- Correctness came first. Each candidate took the place of the step of the library in each test of
  `tests/engine/solve/test_spec_answers.py` and `test_random.py`. The first holds the answers of the
  language. The second holds exact rational references, with its deep sweep. That is 827 cases, or
  822 for a candidate of the distance step, because five cases test the fallback of the library.
  The tables give each error against the tolerance of its test.

## The measured tables

### Correctness against the exact references

| Candidate | Cases of the language | Whole order (330) | Distance alone (400) | Fair on networks (60) |
| --- | --- | --- | --- | --- |
| library | 37/37 | 330 (2e-6) | 400 (9e-9) | 60 (5e-7) |
| library with qdldl | 37/37 | 330 (2e-6) | 400 (9e-9) | 60 (5e-7) |
| Clarabel | 28/32 (2e-4) | 251 (5e-4) | 343 (5e-4) | 59, 1 named stop |
| Clarabel, tolerances 1e-10 | 30/32 (4e-5) | 329 | 355 | 59, 1 named stop |
| PIQP | 28/32 (8e-5) | 261 (2e-4) | 349 (4e-4) | 60 |
| OSQP, eps 1e-9 with polish | 32/32 | 329, 1 named stop | 400 (4e-9) | 60 |
| PIQP, then the polish of OSQP | 32/32 | 330 (1e-6) | 400 | 60 |
| fair: highspy / parts | 37/37 | 330 | 400 | 60 (5e-7) |
| fair tolerance 1e-7, FIX 1e-7 | 37/37 | 330 | 400 | 59, 1 named stop |
| fair FIX 1e-6 | 35/37 | 329 | 400 | 39 (levels off by up to 1.5e-3) |
| distance tolerance 1e-7 | 37/37 | 330 | 372 (9e-7) | 53, 7 named stops |

A number in brackets is the largest error. A named stop is a `SolveFailure`. No candidate gave a
different answer without a stop.

### The distance step, P1

| Problem | Candidate | Time | Newton steps or iterations | Rows missed | Against the library |
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
| 30,000, problem of the engine | library, SuperLU or qdldl | did not finish in 15 min | | | |
| 30,000, problem of the engine, rows merged | library, SuperLU / qdldl | 377 s / 81 s | 455 + 3 / 448 + 3 | | |
| 30,000, problem of the engine | Clarabel, PIQP | fail, or stop at their iteration limit | | 1e-3, 3e-6 | |
| 3,000 normal / x1.45 / damaged / x1.7 | library | 3.6 / 4.7 / 2.2 / 6.2 s | 99 / 144 / 98 / 177 + 3 | 1e-13 | - |
| 3,000, same | library, qdldl | 1.4 / 1.8 / 1.3 / 2.3 s | 114 / 161 / 130 / 193 + 3 to 23 | 2e-8 | 4e-8 |
| 3,000, same | Clarabel | 0.3 s each | 24 to 28 + 7 | 1e-8 | 6e-6 |
| 3,000, problem of the engine | library / qdldl / Clarabel | 8.4 / 1.7 / 0.7 s | 94 + 3 | | Clarabel misses rows by 0.5 |

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
| 30,000, problem of the engine | library | 225 s | 459 | 16 | - |
| 30,000, problem of the engine | tolerance 1e-7 | 176 s | 459 | 0 | 7e-10 |
| 3,000 damaged | library / parts | 1.5 / 0.5 s | 71 / 9 | 0 | 3e-12 |
| 3,000 normal | primal / dual simplex | 1.3 / 2.6 s | 50 | 0 | 9e-13 |

The loads were 1 to 3. Each candidate gave the same answer bit for bit when it ran again, in one
process and in two, with one thread.

## What was adopted, and why

[Change 18](../design/decisions.md#change-18) takes the speedups that give the same answers up to the
tolerances of the steps. All three keep the rules of the selection order, and none adds a tolerance.

1. **A stock held at both bounds is one equality** (`napkin/engine/timeline/declared.py`,
   `Former.problem`). The engine wrote such a stock, for example one held at 0 Wh, as two rows of
   opposite sign. The step of the objective makes one of them an equality, and the other keeps a
   slack in the distance step. At 30,000 places, this gave a Newton system of 316,000 unknowns
   instead of 233,000, and 2.8 s for one factorization instead of 0.7 s. One row `==` gives the same
   set of answers.
2. **LDL' by qdldl in the distance step** (`napkin/engine/solve/distance.py`). The Newton system of
   the step is quasi-definite, and its pattern stays the same over a stage. qdldl orders the system
   and analyses its pattern one time in each stage, and each step factorizes only the new values.
   Without pivots, LDL' can be inaccurate on these systems. A solve can have a backward error above
   1e-10, or qdldl can refuse a factorization. In either case, the stage continues by SuperLU from
   the point that it reached. A stage that does not converge so runs again by SuperLU alone. qdldl
   0.1.9 has the Apache-2.0 license, with wheels for CPython 3.8 to 3.14 on Linux, macOS and
   Windows, x86-64 and ARM.
3. **Fair sharing in connected parts** (`napkin/engine/solve/fair.py`). Claims that share no row,
   through the columns that the face leaves free, are independent. Each part gets its own level
   variable in one program, which is the programs of the parts side by side. The number of programs
   is that of the part with the most levels, not their sum. A connected network is one part, as
   before.

The new times, with the bench of the solve library (`scratch/rewrite/b1/solve/bench.py` at commit
`ARCHIVE_SHA`) and `scratch/rewrite/p1/adopted.py` (at the same commit):

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

The bench of the engine (`tools/bench/port/s5-engine/bench.py`, two solves over 48 h) gave these
times. At 3,000 places, the run takes 18.2 s instead of 31.7 s, and the solve library 5.9 s instead
of 21.8 s. At 30,000 places, the first solve, at normal supply, takes 166 s (459 fair-sharing
programs, 25 renewals, 445 + 3 Newton steps). Before, it did not finish in 45 minutes. The second
solve, with the supply cut to 0.8 at 24 h, is a case of shortage. It did not finish in the 10.6
minutes left of the 15 (`scratch/rewrite/p1/engine_solves.py` at commit `ARCHIVE_SHA`).

## What was deferred

### Fair sharing at the primal tolerance 1e-7

The programs of fair sharing run at the tightest primal tolerance of HiGHS, 1e-10. Each answer has
a check, and an instance that fails the check is renewed. At 1e-7 (FIX stays at 1e-7) the renewals
stop at 30,000 places (29, 43 and 16 become 0) and the levels stay within 7e-8. But one claim at
need x1.7 moves by 1.2e-6, and the time is the same. On one random network of 60, two claims whose
levels are 9e-7 apart stay together at a level that the first cannot keep. The face is then empty,
and the solve stops by name. FIX itself must stay at 1e-7. At 1e-6 the later levels move by up to
1.5e-3: the loops of the routes amplify the slack of the held floors.

### The interior-point path

Clarabel answered the distance step at 30,000 places at normal need in 4.4 s (45 s now with qdldl).
But an interior-point algorithm stops about the square root of its tolerance away from a bound that
holds the nearest point with no multiplier. The pump of the language serves 6.00017 L/h where the
answer is 6. Clarabel also failed on the problem of the engine and under shortage, and PIQP stopped
at its iteration limit there. The polish of OSQP made the small cases exact, but not the large ones.
A path by an interior-point algorithm needs a polish that is exact at scale, and a fallback by name.

### Precision profiles

A precision profile is a named set of tolerances and algorithms for the solvers, such as `default`
and `fast`. The design:

- The profile is part of the identity of the run. Its store key, its **record**, its **checkpoint**
  and the line of its report name it. Thus, two runs with different profiles are never the same
  run.
- The strict invariants are exact in each profile:
  - the books of each stock balance
  - equal claims get equal shares
  - each value stays in its range
  - a proof that a value never falls holds
  - a near-tie (a choice of who is served within the tolerance of its boundary) has a report with
    its size.
- A profile that cannot answer falls back by name. The record says which step fell back to which
  profile. A step that `default` cannot answer either stops with its named failure.
- Published runs use `default`.

## The open cases

Need x1.45 and need x1.7 at 30,000 places. In P1 the distance step gave no answer. At x1.45 it did
not finish in 15 minutes. At x1.7 the Newton iteration did not converge in 500 Newton steps (nor in
2,000). The QP algorithm of HiGHS then called the face infeasible. That face is feasible at the
primal tolerance 1e-9 of HiGHS, and infeasible to HiGHS at 1e-7. After the adoption, the two cases
are still open. Fair sharing takes 396 s and 607 s, and the distance step does not finish in what is
left of 15 minutes.

## The changes

- `napkin/engine/timeline/declared.py`: one row `==` for a stock at both bounds.
- `napkin/engine/solve/distance.py`: `_LDL` (qdldl, two refinement steps), the change to SuperLU in
  `_Dual`, and the second run of a stage by SuperLU alone in `stage`.
- `napkin/engine/solve/fair.py`: `_parts`, and one level variable for each part in `_tier`.
  `kept.Kept.start_at_upper` takes several columns.
- `napkin/engine/solve/solver.py`: `Work.superlu`, the runs of a stage that SuperLU factorized.
- `pyproject.toml` and `requirements.lock`: `qdldl`.

What stays:

- the tolerance 1e-10 of fair sharing with its renewals
- FIX 1e-7
- a refactorization every 100 updates
- the HiGHS of SciPy
- the primal simplex after the first program
- the QP algorithm of HiGHS as the last fallback of the distance step.

A checkpoint holds the same state of a solver as before (its program, its basis and its last
problem). None of the three changes keeps anything between two solves.

## The checks

- `tests/engine/solve/`: 182 tests and the deep sweep. New tests: parts that share no row share
  their programs, and a stage whose LDL' solve misses its accuracy continues by SuperLU.
- `tests/engine/test_solvers.py` (new: a stock held at both bounds is one equality),
  `test_random_solvers.py` (with its 900 deep cases), `test_programs.py`, `test_checkpoints.py` and
  `test_edits.py`: 287 tests.
- Exact resume in three ways for a solver with two stocks held at 0 L and two parts: the same
  record. The three ways are no stop, a stop resumed in one process, and a stop resumed in a fresh
  process.

## The risks and the open questions

- The Newton iteration can need a different number of steps when its factorization changes. On
  some faces LDL' sends it in a wrong direction. The change to SuperLU and the second run guard the
  answer, at a cost of time where they act.
- Fair sharing on a connected network is still one program for each level (155 to 660 s at 30,000
  places). One program could hold each claim that cannot rise. It would save at most the programs
  that repeat a level (less than 1% on a connected network).
- What the distance step needs to answer under shortage at 30,000 places (need x1.45 and x1.7, and
  the second solve of the engine). Its Newton iteration did not converge there in P1, by either
  factorization.
