# S5-E state: the engine, declared solvers — done

Brief: `briefs/s5.md` (S5-E) with `COMMON-B.md`, `s0-engine.md`; S4 in `b1/s4a-engine`, `b1/s4b-engine`;
the solve library in `b1/solve/STATE.md`. Baseline: S4 committed (5a8be4b), 3,814 live tests.

## Design (decided; the docstrings of napkin/engine/timeline/ hold it)
- plan.py: a solver of a member is a `Declared` (id `member.solver`, frame of its bare names,
  flows and stored values that it determines, unknowns, relations, objectives); a non-flow result
  is a value of kind RESULT; `connect(flows, moving, solvers)` makes one set of way DECLARED of a
  solver's flows, every flow sharing their stores (the oracle's rule), and the moving stores its
  problem reads; two solvers in one set fail by name; a setting that reads a rate of its own set
  fails ("needs a declared solver", the oracle's diagnostic) instead of Outside (S5).
- declared.py (new): `Former` forms the problem of an instant (`Affine`; positive parts batched
  by depth as INTERNAL unknowns; rows in one matrix; refusals `Unsupported`, by form);
  `DeclaredWay` on lines (store at a bound -> solve again); `MovingDeclared` (problem reads a
  moving store or t): Radau, a solve at each trial state (untraced), at most MOVING = 20 stores,
  else a failure by name (D3). Same problem as last solve -> no solve, no trace (oracle's cache).
  One `solve.Solver` per solver per run (`Ways.kept`). `polished`: answer put on its active
  bounds/rows (NEAR 1e-6), fair groups on equal fractions, full claims on their requests, by one
  regularized KKT factorization -> vertices exact (examples to 1e-8; event times exact).
- ways.py: `result_of`, `result()`, `fresh()` (stale read during stages, D5; never solved);
  levels include results. run.py: RESULT reads; sets of solvers and their readers wait for the
  setup's settle (`Run.waiting`). moment.py: settle builds waiting sets, passes solvers to connect;
  `occurrences.delays()` after settle: a delay reaching a rate/result waits, other reads captured.

## Done
- 17 solver examples in `test_programs.SUBSET` (`SOLVED`, compared at rel 1e-6; all exact to 1e-8).
- tests/engine/test_solvers.py (18), test_random_solvers.py (100; 900 deep: all pass) vs oracle.
- test_record: own-rate refusal is a run failure. Ported in place (dormant-listed, for the main
  session to take off tests/dormant.txt): test_erf.py (22), test_continuous_domains.py (2).
- Final: engine+core+program+reference 3173 passed (131 s, -n 2); deep random 900 passed (53 s).

## Measured once (bench.py here; OPENBLAS_NUM_THREADS=1; load ~1, quiet machine)
- 30,000 places / 35,000 routes / 15,000 sources: build 5.8 s, plan 26.5 s, run+record 132.2 s
  (forming 22.8 s, solve library 42.8 s), peak RSS 3.16 GB. The first solve stops at 0 h:
  "numerical in fair sharing, tier 0: HiGHS ended with the status kUnknown"; the library's own
  `b1/solve/bench.py fair --share 1.0` stops the same way, so the 24 h solve is not reached.
- 3,000: plan 2.1 s, run+record 31.7 s (forming 3.0 s, library 21.8 s, 2 solves), 0.52 GB.

## Not done
- S4 carry-over left "(S4)": formula/collection assignment in a stage; keyed reads of moving
  values and keys. A setting or problem that reads a moving rate of another set: Outside, no
  stage of the plan brings it. Prefs (priority endpoint with a request) inside a solver: refused.
- Dormant test_runtime.py, test_timeline.py: not ported (old language throughout).
- The oracle applies the stale-read rule to local rates too; the engine to solver sets only.
