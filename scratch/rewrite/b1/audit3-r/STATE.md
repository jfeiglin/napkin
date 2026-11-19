# Audit 3, agent R: records, reports and solves (rows 06 11 15 16 18)

## Where each cause acts (whole repository, listed before any change)
- 06 (a change of an answer checked on every rank but the distance): solve/solver.py `_end_checks`,
  `Answer.admits`; declared.py `published` (polish, clip; declared and moving solves) through it;
  selection.py `_kept` (local sharing, rank 4 unchecked: not mine); test_published_answers `no_worse`.
- 11/18 (holds and budget decided once a record is built; a cut holds more): record.py
  `Recorder.record` (`within` at the end; a ledger opened at the store's start, so an edit at T
  added a piece at 0 h); checkpoints.py `_hit`/`checkpoint` (a checkpoint past its budget); run.py
  `_go` (E); program/record.py `within`, `Manifest.names`; store.py `served`, `run`; session.py
  `advance` (not mine); a curve cut at an earlier horizon (store) has other pieces than a fresh run.
- 15 (recursion on 5,000 links at limit 400): proofs.py never falls (`rises`, `parts_rise`,
  `points_form`, `point_form`, `formula_init`, `linear`, `read_form`; `constant`/`input_value` cut
  at depth 50), called by report.py's lag. Checked, no recursion through a chain: the engine Reader,
  `Recorder._needed_names`, `_Trail.reached/read`, proofs `reads/_edges`, reach.py, saved.py, store.
- 16 (a trail depends on its report): report.py `_Trail.reached` followed a name evaluated at any of
  the path's times at every time, and took the start as read where another path evaluated it.
  Consumers through it: commands/run.py, tools/evidence/trail.py.

## Rule tests (written first; failures on 8b3a01a)
- tests/engine/solve/test_ranks.py (06): hand cases fail; 31/60 library problems, 31/80 engine
  programs admit a farther alternative. tests/engine/test_trail_order.py (16): 8/80 models + hand case.
- tests/engine/test_budget_rule.py (11/18): lines 34 checkpoints past budget + 2 outcomes (cut
  ledger) + 2 audit cases; curves 6/40 with the old cut. tests/engine/test_report_chains.py (15): the
  lag fails on every chain form (RecursionError; inputs: lag refused by the depth cap).

## Mechanisms and decisions
- 06 `_farther`: the distance is ranked after the claims, flows then others; a coordinate moved by at
  most CHECK*(1+|x|) over its scale is a rounding (the end checks' precision), any other change must
  not take the stage farther. Per coordinate, so large deviations elsewhere hide no moved delivery.
  Spec 548-556: "selects a unique published answer", "a numerical tolerance may approximate it".
- 16: the trail follows (name, time) pairs, each read at its own time; a time counts only where the
  path's own read reached the reader (`Reader.refusal`).
- 11/18: a ledger's first piece is its first edit (reads 0 before), so pieces up to a time are
  settled once the run is past it; a stop whose record so far is past its budget raises
  `OverBudget` (a SimulationError, recorded by `Run._go`, ended by `within` at its budget's time):
  no checkpoint past its budget. The store cuts an earlier horizon only where no held value is on a
  curve by then (a curve is fitted to the run's own end); else it runs the request alone, unstored.
  PLAN 10 ("the same run gives the same result again"), 11 (the same configuration is deterministic).
- 15: each formula's linear form and parts-proof once, on a stack (`_find`, `_Pending`); inputs'
  values on a stack (the depth cap of 50 is gone: a deeper chain of defaults is now known).
- Expectation changed (traced to row 18's rule): test_record_claims one-piece budget at a pause.

## For the main session
- session.py `Session.advance`: a run that its budget ends before a stop of a log (a record now, not
  a checkpoint) is refused "does not play again", while the store's cut gives the record. Fix: skip
  the log's stops at or after `found.end` when `found.failure.detail('budget')`.
- selection.py `_kept`: check the candidates on rank 4 too, as `solver._farther` does.
- ways.py `finish` (+ component.py): at the horizon a set on curves records no rate from its
  commits (a run to 1 h reads 2 L/h at 1 h, one to 4 h 1 L/h): strict xfail in test_budget_rule.
- Recursion outside my files (a request that reads the end of a 5,000-link chain): family.py `at` +
  core/arrays.py; component.py `_expand` + expressions.py `names_in`.
## For F / For E (optional)
- F: `parts.Template.part` is a linear search: quadratic proofs on 5,000 parts (1 s).
- E: `Recorder.transfers` keeps a store's start only for `moment._Savepoint` ([1]).
## For the owner
- R-A4a-08 serves every covered request; for values on curves at an earlier horizon the store now
  runs the request instead (a cut's budget outcome differed in 10/180 sparse, 97/180 moving-solver
  cases). Keep it (defensibility), or serve the cut within tolerance and accept the difference?
## Status: all five rows done, code and tests; final runs in the last message.
