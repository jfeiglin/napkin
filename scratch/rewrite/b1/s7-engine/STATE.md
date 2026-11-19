# S7-E state: the engine of S7 (breakpoints, checkpoints, edits; no player machinery)

Brief: `briefs/s7.md` (opening, S7-E) with `COMMON-B.md`; owner: `PLAN.md` change 15.
Owns: `napkin/engine/`, `tests/engine/`, `napkin/program/checkpoint.py`, trace kinds of `program/record.py`.

## Decisions (docstrings of `program/checkpoint.py` and `engine/timeline/checkpoints.py` hold them)
- Checkpoint = documented data (`program/checkpoint.py`): `Stop` (why, breakpoint, at, owner, member,
  t, round, hit, next), `State` (values, occurrences, pending stages, triggers), record so far
  (trace ends with a `pause` entry: breakpoint, hit, next), program = `Artifact.digest`, engine
  version (SHA-256 of engine/, program/, core/, expressions.py, distributions.py, at import),
  configuration, breakpoints, `edits`. Text: `napkin checkpoint 1` + JSON (array = tuple;
  `{"$": class}` only for `RECORDS`; non-finite floats and fractions tagged).
- Breakpoint(at, owner): an event (step 0 of each occurrence, as the oracle), a stage (`After`
  step) or a statement of a stage or the setup; owner '' / member / occurrence. Trigger bodies and
  unknown origins refused. Breakpoints persist (stop at every hit). Hits counted (`Breaks`); a stop
  rewinds the count to the stage's start, so the rerun stage passes its earlier hits.
- Resume in place: `Run.resume()` reruns the held stage (`Moment.held`) from its start.
- Resume in a fresh process (`timeline.resume`): RUNS THE PROGRAM AGAIN from the start with the
  checkpoint's configuration and breakpoints, passing hits up to the stop, where stop, state and record
  so far must equal the checkpoint's (else CheckpointError). Chosen over "save numerical state / restart
  at each moment"; checkpoints.py lists what carries numerical state across a moment.
- Edits (`Checkpoint.edit`, `Run.edit`; `Edit(hit, target, value)`), canonical units, engine names:
  stored values only (not params, built-ins, inputs, links, formulas); type, enum members, bounds;
  finished occurrence frozen. Before a stage: commit at once; before a statement: joins tx.writes at
  each rerun of the stage, traced at its commit. Trace kind `edit` (part = the stop's location;
  breakpoint, target, old, new). report.py: an edit that lowered a value withdraws its never-falls
  proof (lag refused, names the edit); a stopped record says "stopped at ... at the breakpoint".
- M3: the engine has no choice, controller, pick, `sees`, `Paused` or `resume(*picks)`; a program that
  reads `choose(...)` meets the plan's refusal of an unknown read (with a hint), without importing
  `refs.Choice`. `paused(record)` = the stop's entry; `napkin.engine.resume` exported.

## Done
- M1: tests/engine/test_checkpoints.py (11 cases x three ways; fresh process = subprocess, PYTHONHASHSEED
  4321, loads the program from its artifact; boundary stop at 0/2/4 h; representation; refusals).
- M2: tests/engine/test_edits.py (before a stage, two stops in a stage, `examples.PAUSES` x4 against the
  oracle, refusals, never-falls withdrawal in the report).
- M3: chance.py, plan.py, run.py, moment.py, record.py, report.py; tests deleted (player only):
  test_pause, test_play, test_timeline_play, test_settled_decisions; ported: test_availability,
  test_timeline_outcomes, test_random_draws (draw of the boss's forecast), test_report (stopped run),
  test_programs (SUBSET: pump_dispatch_unattended; `LEFT` accepts the refusal of dispatcher_*).
- Measured (load 6-8): breakpoint checks within noise; 3000 places, stop at 22 h of 24: to the stop
  28 s, write 4.3 s (43 MB), read 3.7 s, resume 37.7 s (straight 27-33 s).

## For S7-F
- The engine no longer imports or reads `refs.Choice`, `Template.sees`, config `Controller`, `Pick`,
  `PLAYER`, `FORECAST`, `controllers`, `picks`: remove them. Dormant tests/test_session.py and
  tests/engine/test_decision_resolver.py imported the deleted test_pause/test_settled_decisions.
- When the dispatcher_* examples leave examples.py, `LEFT` in test_programs.py can go (mine).

## Not done
- Edits are in canonical units by engine name (the oracle's and PAUSES' are in declared units by key).
- A store's edit is in the books only as its trace entry (old, new); the report reads no ledger yet.
- A snapshot restore (resume without the replay) for long runs: the list in checkpoints.py is what it
  would have to save as data; not needed for exactness.
- Do not edit engine/program/core files while a test run is going: the fresh-process tests then see
  another engine version and refuse by name (16 such failures once, all of that kind).
