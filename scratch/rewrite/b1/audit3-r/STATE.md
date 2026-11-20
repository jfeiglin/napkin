# Audit 3, agent R: records, reports and solves (rows 06 11 15 16 18)

## Round 1 (done, in 66797b7/f89831e)
- 06 `solver.farther` (distance after the claims, per coordinate); 16 trail by (name, time) pairs;
  11/18 ledger from its first edit, `OverBudget` at a stop, the store cuts only where no held value
  is on a curve (owner, change 24 a: keep); 15 proofs on a stack (`_find`, inputs).
- Tests: solve/test_ranks.py, test_trail_order.py, test_budget_rule.py, test_report_chains.py.

## Round 2: places (whole repository, listed before any change)
- N15 named collection in proofs: proofs `_step` root, `_local` (event local); through them a
  solver's input. Consumers: report lag/trail, commands/run.py, tools/evidence/trail.py. Not mine:
  reach.py reads paths through check.Resolver (F).
- R12 formula failing inside a piece: record.py `formula` (`_switches` escaped `run()`; `fitted` made
  the whole piece Unavailable): every formula, keyed, reduction and dynamic read made through it.
- R15 constant-key chains: record.py `_lookup` (n^2 holders), `_needed_names` (expansion per name).
- F14 checkpoints.checked (`live[owner]` beside `occurrences.frozen`).
- 11/18 session.py `advance` (a log's stops after a budget's end "missing").
- 06 selection.py `_kept` (rank 4 unchecked); every other change of an answer: declared.published.
- R15 recursion: declared.py `value/_name/_reduced` (per formula, per tree level); family.py
  `Columns.one/at` (per formula, through arrays.values). Not mine: component.py, sparse.py, core.
- M12 a constraint's membership: lowering._relations, build.in_range (F) write two relations, and
  declared.value refused a `within` ("the function within of an unknown"); oracle network.py (F).

## Round 2: rule tests (first; failure on the code as it was) and mechanisms
- N15 test_named_collection_reports.py: 20/33 failed. proofs `points` follows a root COLLECTION and
  an event's collection local to their members, on a stack (`_walked`, generators); report chains
  `..._named_collections_...` (lag refused before), 1,500 and 5,000 links at limit 400.
- R12 test_formula_failures.py: 6/6 failed. record `formula`: `tried`; a failure is one value of
  `_switches` (`_same`); a number `_numbers`: fitted, else split where it can be evaluated.
- R15 report chains `..._keyed_reads_..._one_history_a_link`: 89,999 holders at 300 (narrow walk
  181,197). `_lookup` reads `plan.reads` (the chosen entry); `_needed_names` walks direct reads.
- F14 `occurrences.frozen` (no change of behaviour; E's test covers it).
- 11/18 test_session `..._the_budget_gives_...`: failed. advance skips a log's stops at or after
  the end (within crossing) of a record that its budget ended; one before must come.
- 06 test_published_answers (local sharing): hand + 13/60 networks admitted a farther point.
  `solver.farther(x, before, target, precision)` shared; `_kept` checks it (FEASIBLE of units).
- R15 declared `Former.value/_name/_reduced`, family `Columns`: on `walk.walked` (Pending, evaluated
  again with reads kept; a name once at an instant). E's strict xfails pass at 1,500 and 5,000.
- M12 test_solver_memberships.py: 5/5 failed. `Former._membership`: x and ends read once, known
  ends checked (`ops.REVERSED`), then the chain's relations; lines, moving, stage, edit, fresh.
- test_budget_rule: the skip of curves' rates at the horizon dropped (others fixed ways.finish).

## Decisions
- A formula that only the record evaluates is `Unavailable` by name where it fails (D7, F's rule
  test: a formula read is Unavailable), not the run's failure: the run never evaluated it.
- A stop at the end of a budget's record within the crossing tolerance counts as after it.

## For the main session
- F: keep `within` in a constraint (lowering._relations, build.in_range) and read it in the oracle
  (network.py `se.val`: known ends checked, then its chain). Strict xfail in test_solver_memberships.
- Seen (others' work in progress): deep paths component XPASS(strict); test_timeline_long_steps
  `..._three_compartments_...` fails at 24 h ("rests on a bound") also with HEAD's family/selection.
## For F / For E (optional)
- F: `parts.Template.part` is a linear search: quadratic proofs on 5,000 parts (1 s).
- E: `Recorder.transfers` keeps a store's start only for `moment._Savepoint` ([1]).
## Status: items 1-3 done; final runs next.
