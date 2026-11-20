# Audit 3, agent R: records, reports and solves (rows 06 11 15 16 18)

## Round 1 (done, in 66797b7/f89831e): 06 `solver.farther`; 16 trail by (name, time); 11/18 ledger
from its first edit, `OverBudget` at a stop; 15 proofs on a stack. Tests: solve/test_ranks.py,
test_trail_order.py, test_budget_rule.py, test_report_chains.py.

## Round 2: places (whole repository, listed before any change)
- N15 proofs `_step` root, `_local` (and solver inputs through them; consumers: report, commands/run,
  tools/evidence/trail). R12 record `formula` (`_switches`, `fitted`). R15 record `_lookup`,
  `_needed_names`. F14 checkpoints.checked (now `frozen`). 11/18 session `advance`. 06 selection
  `_kept` (rank 4). R15 declared `value/_name/_reduced`, family `Columns` (not mine: component,
  sparse, core). M12 a constraint's `within`: lowering._relations, build.in_range, oracle (F).

## Round 2: rule tests (first; failure on the code as it was) and mechanisms
- N15 test_named_collection_reports.py: 20/33 failed. proofs `points` follows a root COLLECTION and
  an event's collection local to their members, on a stack (`_walked`, generators); report chains
  `..._named_collections_...` (lag refused before), 1,500 and 5,000 links at limit 400.
- R12 test_formula_failures.py: 6/6 failed. record `formula`: `tried`; a failure is one value of
  `_switches` (`_same`); a number `_numbers`: fitted, else split where it can be evaluated.
- R15 report chains `..._keyed_reads_..._one_history_a_link`: 89,999 holders at 300 (narrow walk
  181,197). `_lookup` reads `plan.reads` (the chosen entry); `_needed_names` walks direct reads.
- 11/18 test_session `..._the_budget_gives_...`: failed. advance skips a log's stops at or after
  the end (within crossing) of a record that its budget ended; one before must come.
- 06 test_published_answers (local sharing): hand + 13/60 networks admitted a farther point.
  `solver.farther(x, before, target, precision)` shared; `_kept` checks it (FEASIBLE of units).
- R15 declared `Former.value/_name/_reduced`, family `Columns`: on `walk.walked` (Pending, evaluated
  again with reads kept; a name once at an instant). E's strict xfails pass at 1,500 and 5,000.
- M12 test_solver_memberships.py: 5/5 failed. `Former._membership`: x and ends read once, known
  ends checked (`ops.REVERSED`), then the chain's relations; lines, moving, stage, edit, fresh.
- Coordinator: a warm cut held more histories than the cold run. `record.requested` (one rule: the
  manifest's, `needed` under the trace's occurrences and definitions on a declared plan `plan_for`,
  ledgers; sorted by key; an end piece holds its value, `_finished`), used by Recorder.record and
  store.served(record, request, program); `settled`: no fit (a fitted line is now a degree-1 Curve)
  nor bisected change of a calculated value; served only so at an earlier horizon or budget end.
  Rule tests assert record equality: budget_rule (cut == alone == later: 5 failed before), record
  claims, formula failures, session; test_store window: a shorter everything request runs alone;
  commands/test_run: the listing's unwritten values follow the record's order (by key). The
  budget test's skip of curves' rates at the horizon dropped (others fixed ways.finish).

## Decisions
- A formula that only the record evaluates is `Unavailable` by name where it fails (D7, F's rule
  test: a formula read is Unavailable), not the run's failure: the run never evaluated it.
- A stop at the end of a budget's record within the crossing tolerance counts as after it.
- 24(a) "only where the cut is what a fresh run gives": a fitted line counts as a curve (its slope
  follows the fit's span), so a shorter request with a formula over moving values runs fresh.

## For the main session
- F: keep `within` in a constraint (lowering._relations, build.in_range) and read it in the oracle
  (network.py `se.val`: known ends checked, then its chain). Strict xfail in test_solver_memberships.
## Coordinator, E's items (round 3)
- saved.py keeps a component's `bounded`, `active_bounds`, `zero_faces`, `right_faces`.
  test_checkpoints `emptying` (a store empties at ln 2 h, a stage settles it, the stop after it):
  three ways equal before and after; the restored state (False, no bound) differed: now held.
- Near ties: `ranked.exact` reruns tight where an answer misses a row by more than TIGHT (a pin of
  the looser of two near-tied rows left an empty face). solve/test_near_ties.py: 23/102 gaps and
  both runs (2 L, 3 L deep) failed before.
## Status: done. Deep: 8,181 passed (local sharing, random solvers, published answers, ranks, near
ties); report chains 14/14 (5,000 links 65-246 s each). A stall was my test's spy of `_kept` left on
while its checks called `_kept` (it appended to the list that it walked): fixed in the test.
