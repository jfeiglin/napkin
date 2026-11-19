# C-R: the report — state (done)

Brief: `briefs/c.md` (C-R) with `COMMON-B.md`; PLAN "Changes after G0" 7, 10-14. Baseline c3542cd (G1).

## Done
- `napkin/program/proofs.py` (new): `Proofs(program, configuration)` with `never_falls(key)` ->
  `Proof(holds, reason)` and `reads(key)` -> `Reads` (parts, edges, `blocked` events); functions of
  the same names. tests/program/test_proofs.py (24).
- Status display: semantic `DeclaredStatus`/`DeclaredStatusCase` on `DeclaredEntity.status`
  (`owner.status.case[k]`); `Deferred`, `deferred`, `later_slice` refusal gone; lowering
  `status_of`; program/check `duplicate_name` for a part `status` beside a display; plan
  `_declare_status` (formula `member.status` = text `case[k]`); record `unit_of`. tests/language/
  test_status.py (7); test_semantic/test_lowering updated; tests/commands/test_compile.py's one
  refusal test now checks that a display compiles (C-K's file).
- Near-ties: `moment.near_ties`; `Triggers.near`/`tolerance` (fire entries); `Moment.test` (guard,
  `if`, case guard: commit entries); detail `near` = ((origin, comparison, difference, tolerance),);
  `Record.near_ties()` (program/record.py). tests/engine/test_near_ties.py (8).
- `napkin/engine/report.py` rewritten in place: `report(record, program, configuration, paths,
  times, lags=None, model=None)` -> `Report` (values `Reported`, `Shown`, `Lag`, trail `Used`,
  `NearTie`, `end`, `stopped`, `records`). tests/engine/test_report.py (13).
- Deleted the six old dormant files: tests/engine/test_reporting.py, test_timeline_reports.py,
  test_evidence_trail.py, test_run_evidence.py, test_paused_results.py, tests/model/test_categories.py.

## Tests
- Final: core, program, reference, language, model, engine, acceptance, commands: 4170 passed (-n 2).
- Files that can leave tests/dormant.txt: the six deleted above, and test_timeline_derivatives.py,
  tests/test_cli_derivatives.py (already gone in cf5c8d3).

## Decisions
- Before time 0 a lag reads the value at time 0 (the record has no history before the run).
- Setup writes are no writers for never-falls: round zero precedes every read at time 0.
- An end of a flow/move/target is one of its candidates; only a `where` widens to zero.
- A stored number's bounds give signs; an input's do not (a drawn default is not range-checked).
- Near-tie: |difference| <= tolerance of what the sides read (stores, rates, crossing for t), and
  for a trigger still so an instant later (a crossing moves through: no near-tie).
- Trail: reached through parts the run evaluated (values, triggers, flows that existed, events,
  stages and solvers that acted); exercised = reached and acted.

## Not done / for others
- Split of who is served (local sharing) is not marked: settlings have no trace entry.
- `napkin/model/analysis/values.py` stays (dead); study.py/session.py (C-S) still import it.
- `sample_result` in napkin/__init__.py and engine/__init__.py names nothing now (C-K).
- tests/acceptance/test_every_construct.py docstring still says a display is refused.
