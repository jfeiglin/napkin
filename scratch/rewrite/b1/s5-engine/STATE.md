# S5-E state: the engine, declared solvers

Brief: `briefs/s5.md` (S5-E) with `COMMON-B.md`, `s0-engine.md`; S4 in `b1/s4a-engine`, `b1/s4b-engine`;
the solve library in `b1/solve/STATE.md`. Baseline: S4 committed (5a8be4b), 3,814 live tests.

## Design (decided; the docstrings of napkin/engine/timeline/ hold it)
- plan.py: a solver of a member is a `Declared` (id `member.solver`, frame of its bare names,
  flows and stored values that it determines, unknowns, relations, objectives); a non-flow result
  (a solved stored number, a solver's own unknown) is a value of kind RESULT; `connect(flows,
  moving, solvers)` joins a solver's flows and every flow sharing their stores into one set of way
  DECLARED (`Connected.solver`, `.results`, `.moves`); two solvers in one set fail by name; a setting
  that reads a rate of its own set fails ("needs a declared solver") instead of Outside (S5).
- declared.py (new): `Former` forms the problem of an instant (affine forms `Affine`, positive parts
  as INTERNAL unknowns, refusals by name as `Unsupported`); `DeclaredWay` runs the set on lines;
  a store reaching a bound re-solves; same problem as last solve -> no solve, no trace (oracle's
  cache); 'solve' traced (part = solver origin). One `solve.Solver` per solver for the run
  (`Ways.kept`). `polished`: answer put on its active bounds/rows (NEAR 1e-6), fair groups on equal
  fractions, full claims on their requests -> exact vertices (examples to 1e-8; event times exact).
- ways.py: `result_of`, `result()`, `fresh()` (stale read during stages, D5; never solved);
  levels include results. run.py: RESULT reads; sets of solvers (and their readers) wait for the
  setup's settle (`Run.waiting`). moment.py: settle builds waiting sets, passes solvers to connect;
  `occurrences.delays()` after settle: a delay reaching a rate/result waits, other reads captured.

## Done
- 17 solver examples in `test_programs.SUBSET` (as `SOLVED`, compared at rel 1e-6; all pass at 1e-8).
- tests/engine/test_solvers.py (10: rounds, stale reads, first solve, infeasible, join/leave).
- tests/engine/test_random_solvers.py (100 normal; 900 deep), against the oracle.
- test_record: the own-rate refusal is now a run failure naming the rate.

## Next
- deep random run; full suite; moving inputs (trial states, small component; refuse at scale);
  carry-over (S4: formula/collection assignment in a stage, keyed reads of moving values); dormant
  files; bench (A3 network 30k/35k, 48 h, supply change at 24 h).
