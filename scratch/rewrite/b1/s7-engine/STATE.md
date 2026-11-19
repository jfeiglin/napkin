# S7-E state: the engine of S7 (breakpoints, checkpoints, edits; no player machinery)

Brief: `briefs/s7.md` (opening, S7-E) with `COMMON-B.md`; owner: `PLAN.md` change 15.
Owns: `napkin/engine/`, `tests/engine/`, `napkin/program/checkpoint.py`, trace kinds of `program/record.py`.

## Decisions (docstrings of `program/checkpoint.py` and `engine/timeline/checkpoints.py` hold them)
- Checkpoint = documented data (`program/checkpoint.py`): `Stop` (why, breakpoint, at, owner, member,
  t, round, hit, next), `State` (values, occurrences, pending stages, triggers), record so far
  (trace ends with a `pause` entry: breakpoint, hit, next), program SHA-256 (= S7-F's
  `Artifact.digest`), engine version (SHA-256 of engine/, program/, core/, expressions.py,
  distributions.py at import), configuration, breakpoints, `edits`. Text: `napkin checkpoint 1` +
  JSON (array = tuple; `{"$": class}` only for `RECORDS`; non-finite floats, fractions tagged).
- Breakpoint(at, owner): at = origin of an event (step 0 of each occurrence, as the oracle), a stage
  (`After` step) or a statement of a stage or the setup; owner '' / member / occurrence. Trigger
  bodies and unknown origins refused. Breakpoints persist (stop at every hit).
- Hits counted (`Breaks`); a stop rewinds the count to the stage's start, so a rerun stage recounts
  its hits and passes those up to the stop.
- Resume in place: `Run.resume()` reruns the held stage (S4b `Moment.held`) from its start.
- Resume in a fresh process (`timeline.resume`): RUNS THE PROGRAM AGAIN from the start with the
  checkpoint's configuration and breakpoints, passing hits up to the stop, where stop, state and record
  so far must equal the checkpoint's (else CheckpointError). Chosen over "save numerical state / restart
  at each moment"; checkpoints.py lists what carries numerical state across a moment.
- Edits (`Checkpoint.edit`, `Run.edit`; `Edit(hit, target, value)`), canonical units, engine names:
  stored values only (not params, built-ins, inputs, links, formulas); type, enum members, bounds;
  finished occurrence frozen. At a stop before a stage: commit at once (`run.write`, entry now); before
  a statement: joins tx.writes at each rerun of the stage, traced at its commit (after the `commit`
  entry, like moves). Trace kind `edit` (part = stop.at; breakpoint, target, old, new).
  report.py: an edit that lowered a value withdraws its never-falls proof (lag refused, says which).

## Done
- M1: checkpoint.py, checkpoints.py (new); run.py, moment.py, timeline/__init__.py (`run(...,
  breakpoints)`, `resume`). tests/engine/test_checkpoints.py: 10 cases x three ways (component and
  sparse near a threshold, family, lines, draw+child+write stage with two stops, declared x2, moving
  declared, acceptance dispatch x2); the fresh process is a subprocess (PYTHONHASHSEED=4321) that
  builds the program from this module's code (S7-F's loader `artifact.load` exists now; not yet used).
- M2: edits (above); tests/engine/test_edits.py incl. `examples.PAUSES` x4 against the oracle.
- Measured (load 6-8, noisy): breakpoint checks within noise (27-33 s both ways at 3000 places);
  stop at 22 h of 24 at 3000 places: to the stop 28 s, write 4.3 s (43 MB), read 3.7 s, resume in a
  fresh run 37.7 s; at 300 places 46 h of 48: resume 6.4 s against 4.7 s straight.
- Cross-process determinism: 67 examples equal under 3 hash seeds.

## Next: M3 (S7-F waits for it to remove Choice/Controller/Pick/sees from the program package)
- Engine: remove Chosen/choices/_choice/observed (plan), choose/seen/Paused/players/picks (chance),
  pause/resume(*picks) (run), Recorder.pause, Tx.choices; refuse a Choice read and controllers/picks
  by name (Outside) until S7-F removes them. `paused` stays (the pause entry); `resume` exported.
- Tests: port/delete test_pause, test_play, test_timeline_play, test_settled_decisions,
  test_timeline_outcomes (pick parts), test_availability (chooser parts), test_random_draws
  (choose in random programs); SUBSET in test_programs: pump_dispatch_unattended for dispatcher_*.
