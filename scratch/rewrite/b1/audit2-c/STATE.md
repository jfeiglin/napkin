# Audit 2, agent C: what a record holds, and what a report claims from it

Brief: `briefs/audit2.md` part C, `COMMON-B.md`; re-audit rows 09 10 11 15 16 18 21 (all reproduced).

## Where each cause acts (listed before any change)
11 A missing value read as a default:
- engine/timeline/record.py `read`: a missing ledger `X.external` is 0.0; any LookupError of an
  occurrence's key becomes "has not started"; a ledger read checks the store's key, so a request of
  the ledger alone is refused; a non-store's ledger (`tank.ticks.external`) reads 0.
- record.py `Recorder.record`: keeps `X.external` only when X's history is kept and the key asked.
- record.py `_Values._finished` (no `active`: "not finished"), `_Values.at` (a missing read raises).
- program/record.py `Record.value`: reads any history present, manifest or not; KeyError if none.
- store.py `served`/`covers`, report.py `_Trail.rates/moved`: read histories the request does not hold.
- report.py `_lagged`: the part of a window before 0 h reads the value at 0 h; KeyError -> Lookup.
10 Values paired with times by position: report.py `report` (`within` + trailing Unavailable).
09 Proofs computed once, patched by kind of edit: proofs.py `Proofs.__init__` (reach once, from the
   configuration), `check` (`_changes` for numbers only), `formula_init`, `reads().blocked`;
   report.py `_changes` (skips yes/no and text edits), `_Trail.edited` (any edit withdraws every
   "cannot start"), `_Trail.acted` (the withdrawn message).
16 Exercised read from what can be read: report.py `_Trail.evaluated` (value/status/trigger always
   evaluated), `_Trail.acted` (every value "read"); proofs.py `_edges` (a status display is one part
   that reads every case); tools/evidence/trail.py `part_uses` (a display cites every case) and
   `evidence` (exercised by part); reads.py `Reads` keeps what was read and nobody uses it.
21 A lag of any type: proofs.py `value` (an input or link "fixed" before the type check); report.py
   `report` (only a status display refused by name), `_lagged` (`float(value)`).
18 Budget declared, not enforced: config.py `Request.pieces` (unchecked); record.py `Recorder.record`;
   store.py `served`, `covers`, `_widened` (a cut and a reuse ignore the budget).
15 Reader recursion: record.py `_Values.at` -> `lazily` -> `at` (also `_derived`, `_dynamic`).

## The mechanisms (decisions)
- 11: `Record.unavailable(key, t)` is the one rule of what a record holds (its manifest's keys, a
  ledger with its store, from 0 h to its end); readers give `Unavailable(reason)` for anything else.
  Every edited store's ledger is kept; a cut answers by the same rule, as a fresh run does.
- 10: the report reads each time on its own (the reader gives Unavailable after the stop).
- 09: `Proofs(program, configuration, changes)`: each edit is one more writer of its run (a number
  changes by a known amount; a named state can take its new value, re-derived by reach), so never
  falls, "cannot start" and formula definitions all follow from one premise. PLAN 15 ("an edit that
  breaks a proof withdraws it") keeps an edit that does not break it.
- 16: the reader keeps what each evaluation read; the trail reaches through it; cases are parts; a
  branch-only read of a run-time part is `exercised=None` unless the record shows it (`ran`).
- 21: only a number is lagged; anything else is refused by name. 18: `Record.within(pieces)`.

## Status (done; the final command is in the last message)
- code: program/record.py (`Key.store/__str__`, `Manifest.names`, `Record.unavailable, value,
  within`), config.py, timeline/record.py (`Reader`: iterative, read sets, ledgers kept, `declared`
  exact scales, references refused; `Recorder.record` -> `within`), reads.py, proofs.py (`Change(key,
  old, new)`, `Proofs(..., changes)`, `withdrawn`, `kind_of`, `always`, cases, `sometimes`, branches of
  stages, references read through, exact scales: D's "For C"), report.py, store.py, evidence/trail.py.
- tests: tests/engine/test_record_claims.py (rule tests, rows 09 10 11 15 16 18 21, references);
  program/test_proofs.py (exact scales, a read through a reference), program/test_record.py,
  test_store.py (budget), evidence/test_evidence_report.py (row 16). The rule tests fail on 9eaecb8.
- Expectations changed (traced): LookupError -> Unavailable for a read the record does not hold
  (test_record, test_store x2, commands/test_contract); a lag window before 0 h is Unavailable (spec
  "averages that history": none before the run; test_report x3, commands/test_run_report x2); edit
  wording (test_edits x2); the stop's reason is the reader's (test_report).
## For B (optional, no claim depends on it)
- A trigger's condition and a stage's guard or branch that read on a branch are `exercised=None` in a
  trail. To make them exact, record per stage/trigger the names that its evaluations read
  (`Reads.found`) in the trace (a detail `read` of each commit/fire entry); the trail would use it.
## After the merge
- The owner chose `Unavailable` for a lag window before 0 h (PLAN.md, change 22).
- `commands/run.py held()` now filters by `manifest.names` (main session).
