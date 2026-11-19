# Audit 2, agent C: what a record holds, and what a report claims from it

Brief: `briefs/audit2.md` part C, `COMMON-B.md`; re-audit rows 09 10 11 15 16 18 21 (all reproduced).

## Where each cause acts (listed before any change)
11 A missing value read as a default:
- engine/timeline/record.py `read`: a missing ledger `X.external` is 0.0; any LookupError of an
  occurrence's key becomes "has not started"; a ledger read checks the store's key, so a request of
  the ledger alone is refused; a non-store's ledger (`tank.ticks.external`) reads 0.
- record.py `Recorder.record`: keeps `X.external` only when X's history is kept and the key asked.
- record.py `_Values._finished`: a missing `active` history means "not finished" (formula read live).
- record.py `_Values.at`: a formula whose read is missing raises LookupError out of the reader.
- program/record.py `Record.value`: reads any history present, manifest or not; KeyError if none.
- store.py `served`: a cut keeps every history of the stored record, so the trail, the ledger and
  `Record.value` answer from histories that a fresh narrow run does not hold; `covers` by key set.
- report.py `_Trail.rates/moved`: reads every rate history present, held or not.
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
- 11: `Record.unavailable(key, t)` / `Record.value` (program/record.py) is the one rule of what a
  record holds: its manifest's keys (a ledger with its store: the books), to its end, from 0 h. The
  engine reader gives `Unavailable(reason)` for anything else. The ledger of every edited store is
  kept whatever the request names. A cut answers through the same rule, so it agrees with a fresh run.
- 10: the report reads each time on its own (the reader gives Unavailable after the stop).
- 09: `Proofs(program, configuration, changes)`: each edit is one more writer of its run (a number
  changes by a known amount; a named state can take its new value, re-derived by reach), so never
  falls, "cannot start" and formula definitions all follow from one premise. PLAN 15 ("an edit that
  breaks a proof withdraws it") keeps an edit that does not break it.
- 16: the reader records the names that each evaluation read; the trail reaches through what was
  read at the report's times, cases of a display are parts; reads only on a branch of a part that
  the run evaluated (a request, a guard) are `exercised=None`: the record cannot say.
- 21: only a number is lagged; anything else is refused by name. 18: `Record.within(pieces)`.

## Status
- in progress: state file written; no code changed yet.
