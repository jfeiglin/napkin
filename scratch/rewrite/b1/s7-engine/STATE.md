# S7-E state: the engine of S7 (breakpoints, checkpoints, edits; no player machinery)

Brief: `briefs/s7.md` (opening, S7-E) with `COMMON-B.md`; owner: `PLAN.md` change 15 and its
2026-11-19 line (restore, not replay; edits in declared units; a store's edit in its books).
Owns: `napkin/engine/`, `tests/engine/`, `napkin/program/checkpoint.py`, trace kinds of `program/record.py`.

## Decisions (docstrings of `program/checkpoint.py`, `timeline/checkpoints.py`, `timeline/saved.py`)
- Checkpoint (format 2): Stop, State, record so far, edits, program (`Artifact.digest`), engine
  version (SHA-256 of engine/, program/, core/, expressions.py, distributions.py at import),
  configuration, breakpoints, `saved` (the engine's state, `saved.save`). Text + JSON of `RECORDS`.
- Resume in a fresh process = `Run.restored(plan, checkpoint)` (`saved.restore`), then `resume()`:
  nothing before the stop runs again. Guard: the restored run's State must equal the checkpoint's.
- Saved as data: the plan log (`Plan.log`: occurrences, first reads that named values, definitions,
  allocations, presence of flows, moving stores; expressions by their place in `_expressions`), the
  run's values/bounds/sizes/frozen/changes/round in progress, recorder (pieces, trace, transfers),
  draws kept, breaks (hits, edits, done), occurrences, triggers, moment, ways (sets by id, instances
  with live sets only, lines, rates, asked, flags, due; component captured parameters/rigid/missing;
  sparse constants and switches; declared solver program+basis, last digest+answer).
- Restarted at each moment on every path: sparse Radau (`Sparse.cut` drops it), a moving solver's
  pending segment and trial cache (`MovingDeclared.cut`), the HiGHS instance (`Solver.renew` at each
  round's stages: next solve on `Kept.fresh()` = program + basis), trigger predictions. Canonical
  orders: `sorted(touched)` in settle, `sorted(ids)` in `Ways.retire`; `_signature` is a SHA-256.
- Edits: `Checkpoint.edit(target, value, key=False)` / `Run.edit`: a record Key (or path with key=True)
  in declared units, or an engine name in canonical units. A store's edit: `Recorder.external` ->
  history `<store>.external` (cumulative from outside; read gives 0 for none). The report: lowered
  value withdraws never-falls; any edit withdraws reach's "cannot start" (trail says which edit);
  `report(..., options=())` -> `DeclaredModel.evidence(origin, member, options)`.
- Bugs: R-A3-02 (`Plan._tolerate_enforced`: readers of an enforced equality read |a-b| <= 1e-7
  max(1,|a|,|b|); the solver reads `plan.enforced`); sparse `Vector` keeps enum/text/bool constants
  as objects; `continuous/kernels.expm` (Pade 13, NumPy) replaces SciPy's (OpenBLAS threads: 6 ms
  for a 4x4 matrix); chain of 3 compartments 12 s -> 0.16 s.

## Done
- M1-M3 and the owner's restore; tests: test_checkpoints (24), test_edits (14), bug tests in
  test_solvers, test_moving_reads, test_timeline_long_steps; tests/test_api.py CLOSURE + saved.py.
- Measured at 3000 places, stop at 22 h of 24: straight 26.9 s; to the stop 25.8 s; written 6.9 s,
  72.3 MB; fresh process: read 5.0 s, restore and run on 7.1 s (replay was 37.7 s).

## Not done / for others
- C-K: `commands/run.py` `reported()` should pass the run's options to `report(..., options=...)`.
- Fresh-process tests refuse by name ("another version of the engine") when napkin/program or
  napkin/engine changes during a test run (another agent's edit): rerun.
