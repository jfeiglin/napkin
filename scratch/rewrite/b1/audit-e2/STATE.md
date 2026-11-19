# Audit after G2, engine and report: state (track b1/audit-e2)

Brief: the coordinator's task message (seven bugs; then member titles) with `briefs/COMMON-B.md`;
PLAN "Changes after G0" 10, 11, 15, 16, 19. Owns: engine/timeline/{moment,occurrences,run,record,
chance,checkpoints,saved}.py, engine/report.py, program/{proofs,record,checkpoint}.py,
commands/run.py (titles only), new files in tests/engine/.

## Done (each a failing test first: `tests/engine/test_audit_after_g2.py`, 23 tests)
1. moment.move: one store at both ends: the debit and the credit cancel; the move is traced, nothing
   is written, nothing checked (its resulting inventory is its own).
2. moment.commit = `_Savepoint` + `_publish`: a failure in the commit takes back what the record reads
   (trace from `tx.mark`, set at the end of `execute`, so the commit/fire entry goes too; pieces and
   `run.changes` of the written names; definitions, restored through `Plan.define` so the expansion
   caches are found again; edits' transfers). `Recorder.record` keeps only the occurrences that its
   trace starts. Covers stages, the setup and firings.
3. chance.distribution/draw/outcomes/described take the stage's tx (run.value, moment.select pass it).
4. Occurrences.due(until) sorts by creation (D5); the first round of a moment takes due <= t + crossing.
5. report._Trail.moved: None when a record of some values lacks the flow's (or a started
   occurrence's) rate: `Used.exercised` None, why "not recorded: ...".
6. proofs.Change + never_falls(key, changes): `check` treats each edit as a writer of known sign;
   report._changes builds them ("it" for the value itself); `_lowered` gone.
7. Record.stop/end/stopped()/after(t); Record.value and timeline.read give Unavailable after the end;
   report._end uses them.
- Titles: `Reported.title`, `Used.title`, `NearTie.title` (`report._title`, receiver of an
  occurrence); run.py `row_name` "path (Title)", JSON `title`. Tests: test_report (1), test_run (1).

## Decisions
- Bug 4 by the time tolerance, not exact times: 0.1, 0.2 and 0.3 h have no exact binary value and no
  exact sum of the binary numbers gives 0.3 (the sum is a tie that rounds to 0.30000000000000004);
  delays are computed by float expressions; `Numerics.crossing` is "the time between two moments
  that the engine tells apart". Only the first round windows, so a positive delay reached in a moment
  (a loop of 1e-9 h) goes to a later moment and never hits max_rounds.
- A self-move of more than the store holds succeeds and changes nothing (spec: the resulting
  inventories are checked, and the debit and the credit are accounted together).
- A failed commit drops its commit/fire entry and its edits; the draws made by its statements stay,
  as for a failure while they run.

## For E1 (the oracle, tests/reference/run.py)
- Bug 1: `Run._move` with src == dst must leave the cell as it is (no write; keep the ledger entry).
  Until then 25 of the 300 random programs of tests/engine/test_occurrences.py fail (and more of the
  deep set): the oracle creates water or fails a bound. A scratch patch of exactly that change makes
  all 300 agree.
- Bug 2: `Run._commit` writes the cells before `_register`; a RunFailed in a later start leaves the
  writes and the earlier children in `view` (and `read(at=view.t)` shows them): snapshot and restore.
- Bugs 3, 4, 7 are not in the oracle (it reads the stage's writes, computes in exact decimals, and
  refuses a read after its stop).

## Tests (final)
- The brief's command: 27 failed, 3565 passed. 2 fresh-process tests (test_session, test_play) met
  "another version of the engine" (E1 edited declared.py meanwhile) and pass rerun alone; 25 are
  test_occurrences' random programs: the oracle's self-move (For E1). `-m deep test_occurrences`:
  154 failed, 1846 passed; the 154 agree with the oracle once its self-move is patched (scratch).
- ruff check and format clean on every touched file.

## Status
- done
