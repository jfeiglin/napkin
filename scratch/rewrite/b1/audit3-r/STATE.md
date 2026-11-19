# Audit 3, agent R: records, reports and solves

Brief: `briefs/audit3.md` part R (+ COMMON-B, PLAN changes 10 16 19-22, audit2). Rows 06 11 15 16 18.
Reproduced: 06 (`admits` (0, 1) True), 16 (below), 15 (lag on 5,000 links at limit 400), 11/18 (below).

## Where each cause acts (whole repository, listed before any change)
06 A change of a solve's answer is checked on every rank but the last (the distance):
- solve/solver.py `_end_checks` (`replaced`: objectives, served fractions, rows, bounds) and `Answer.admits`.
- timeline/declared.py `published` (polish, clip; every declared and moving solve): through `admits`.
- timeline/selection.py `_kept` (local sharing's snaps and `_exact`): rows and claims, not rank 4
  (nearest the targets). Not mine: For the main session.
- tests/engine/test_published_answers.py `no_worse`: the test's rule leaves out the distance too.
11/18 What a record holds and its budget are decided once a record is built; a cut keeps more:
- timeline/record.py `Recorder.record`: `.within` at the end only; a ledger opens at the store's
  start, so an edit at T adds a piece at 0 h (the budget then reaches back before the edit).
- timeline/checkpoints.py `Breaks._hit`/`checkpoint`: a stop gives a checkpoint whose record is past
  its budget. run.py `_go` (E): Stopped -> checkpoint, else the record.
- program/record.py `Record.within`, `Manifest.names` (a ledger with its store), `unavailable`.
- store.py `served` (keeps a ledger whose edits come after the cut), `_cut`, `run`.
- session.py `Session.advance` (nobody's): a run that its budget ended before a stop of the log is
  refused as "does not play again", where the cut of a stored run gives the record. Main session.
- tests: test_record_claims (18), test_store (budget), program/test_record (within).
15 Recursion in records and reports on a chain of 5,000 links at limit 400:
- program/proofs.py never falls: `rises`, `parts_rise`, `points_form`, `point_form`, `formula_init`,
  `linear`, `read_form` (through formulas, child links, member links); `constant`/`input_value`
  through inputs' defaults, cut at depth 50 (a hidden limit). report.py `report` (lag) calls it.
- Not mine (runs fail first): timeline/family.py `at` + core/arrays.py (a request that reads the end
  of a chain), timeline/component.py `_expand` + expressions.py `names_in` (the same, on a store).
- Checked, no recursion through a chain: engine Reader, `Recorder._needed_names`, report `_Trail`
  (`reached`, `read`), proofs `reads`/`_edges`, reach.py, saved.py, store `_encode`.
16 The trail of a value depends on what else the report holds:
- report.py `_Trail.reached`: a name evaluated at any of the path's times (by any path) is followed at
  every time (`again`, `read`); the start counts as read when another path evaluated it.
  `report()` shares one Reader across paths (its caches are deterministic: no cause there).
- Consumers: commands/run.py, tools/evidence/trail.py (`evidence`, `main`): through report.py.

## Rule tests (written first; each fails on 8b3a01a)
## Mechanisms and decisions
## For the main session
## For F / For E
## For the owner
## Status
