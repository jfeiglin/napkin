# S7-E state: the engine of S7 (breakpoints, checkpoints, edits; no player machinery)

Brief: `briefs/s7.md` (opening, S7-E) with `COMMON-B.md`; owner: `PLAN.md` change 15.
Owns: `napkin/engine/`, `tests/engine/`, `napkin/program/checkpoint.py`, trace kinds of `program/record.py`.

## Decisions (docstrings of `program/checkpoint.py` and `engine/timeline/checkpoints.py` hold them)
- Checkpoint = documented data (`program/checkpoint.py`): `Stop` (why, breakpoint, at, owner, member,
  t, round, hit, next), `State` (values, occurrences, pending stages, triggers), the record so far
  (trace ends with a `pause` entry: breakpoint, hit, next), program SHA-256, engine version (SHA-256 of
  engine/, program/, core/, expressions.py, distributions.py), configuration, breakpoints.
  Text: `napkin checkpoint 1` + JSON (array = tuple; `{"$": class}` for the records in `RECORDS` only;
  non-finite floats and fractions tagged). `encode`/`decode` for any such value.
- Breakpoint(at, owner): at = origin of an event (each stage), a stage (`After` step) or a statement
  of a stage or the setup; owner '' / member / occurrence. A trigger body or unknown origin: refused.
- Hits are counted (`Breaks`); a stop rewinds the count to the stage's start, so the rerun stage
  recounts its hits and passes those up to the stop (two stops in one stage work).
- Resume in place: `Run.resume()` reruns the held stage (S4b `Moment.held`) from its start.
- Resume in a fresh process (`timeline.resume(program, checkpoint)`): RUNS THE PROGRAM AGAIN from
  the start with the checkpoint's configuration and breakpoints, passing hits up to the stop, where
  stop, state and record so far must equal the checkpoint's (else CheckpointError by name). Chosen
  over "save numerical state as data / restart at each moment": see checkpoints.py docstring for
  what carries numerical state across a moment (sparse Radau at a step-aligned moment, the kept HiGHS
  instance and `ways.last`, line anchors of family/lines/declared, build-time captures of instances,
  lazily named plan values). Cost: none on a run that does not stop; resume = the run to the stop.
- Cross-process determinism checked: all 67 examples give equal record digests under 3 hash seeds.

## Done (M1)
- `napkin/program/checkpoint.py` (new); `napkin/engine/timeline/checkpoints.py` (new); run.py
  (`Run(plan, breakpoints, expected)`, Stopped in `_go`, `resume()`); moment.py (hits in `stage`,
  `_setup`, `execute`); timeline/__init__.py (`run(..., breakpoints)`, `resume`).
- `tests/engine/test_checkpoints.py`: 8 cases x three ways (component and sparse near a threshold,
  family, lines, stage with draw+child+write and two stops, declared x2, moving declared); the
  fresh process is a subprocess (PYTHONHASHSEED=4321) that builds the program from this module's
  code (until S7-F's loader lands); representation, refusals, owner filters.

## In progress / next
- Measure: resume cost on a larger model (S4a/S1 bench); breakpoint overhead.
- M2 edits, M3 removal of choices/picks/controllers (not started).
