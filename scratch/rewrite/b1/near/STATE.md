# Near-ties and `where` over flows, before G2 (track b1/near)

Brief: the coordinator's task message, with `briefs/COMMON-B.md`; PLAN "Changes after G0" 10.
Owned: engine/timeline/moment.py, triggers.py, collections.py, plan.py, engine/report.py,
model/semantic.py, lowering.py, tests/language/, new files in tests/engine/; later also
model/language/parse.py and tests/model/ (for the five bugs).

Scope: the near-ties not yet marked; `where` over an endpoint's flows; the five bugs that the
cleanup held as xfail(strict) in tests/model/ (its STATE, "Bugs found").

## Design (see the docstrings)
- New trace kinds, each only with a detail `near`: `skip` (a stage guard false within tolerance),
  `miss` (an armed trigger false within tolerance, now and 1e-6 h later; once per arming unless its
  near-ties change: memory derived from the trace, so a restored run agrees), `release` (a gate
  released within tolerance), `settle` (a priority endpoint whose limit, its capacity or what
  reaches a store at its bound, is within tolerance of the claims of the classes ahead of a class
  that asks more; checked at each settling for the rebuilt sets, and in round zero for all sets).
- `near_ties` keeps the near-ties of the terms that decide: `and` false / `or` true keep only the
  deciding term's; a false comparison chain only its failing link.
- `where` over an endpoint's flows: the test compares an end of the member (`source`, `sink`) with
  `==`/`!=` to a stored number, by identity (the oracle compares amounts and crashes at SINK: not
  covered, not edited).

## Done
- Item 1: moment.py (`near_ties` keeps deciding terms; `skip`; `Moment.splits`/`split_ties` after
  each settling and in round zero), triggers.py (`miss` with `_truth(close)` pre-filter and
  `widest()`; `release`), report.py `_NEAR` (six messages), plan `End.origin`, `Plan.incident`.
  Tests: tests/engine/test_near_tie_kinds.py (11). Engine suite passed (2088) after item 1.
- Item 2: semantic.py (`Flows`, `FlowEnd`, `flows_where`, `ends_alike`), lowering docstring;
  plan.py (`_ends`, `_dynamic_where`, item points, `_refuse_kept_in_solvers`), collections.py
  (`Ends`, `Dynamic.keep`, filter in `dynamic_value`). Tests: tests/language/test_endpoints.py
  (+13), tests/engine/test_where_over_flows.py (10).
- Five bugs (marks removed in tests/model): (1) parse.py is precedence climbing (`operation`,
  `factor`, `dots`; ~3 calls of Python per nested bracket; signs and `not` in loops), nesting past
  DEEPEST (150: brackets, call arguments, `else`, powers, intervals; `enter`) refused `deep`;
  semantic.py reads `+ -` and `* /` chains and sign chains in loops: a sum past DEEPEST operations
  is one `sum(...)` (bit for bit the same), a sign chain past it folds, a longer product `deep`.
  (2) a second `record X` is `duplicate_name` naming both lines. (3) `note_records`: a note's
  `@X` must name a record. (4) entity members: first declaration of a name keeps `syntax`, later
  ones are skipped (check_names reports them). (5) triggers.py `_certified`/`_monotone`/`_signs`:
  a plain sum of stores whose group total only rises or falls is certified on curves.
  Tests: tests/language/test_parse.py (+7), test_semantic.py (+3), tests/model (361 pass).

## Tests (final)
- core, program, reference, language, engine: 4095 passed; with tests/model: 4456 passed (-n 2).
  ruff check and format clean on every touched file.

## For others (not my files)
- napkin/program/record.py: KINDS and its near-tie paragraph should list skip, miss, release, settle.
- napkin/commands/run.py docstring still says a near-tie is "a firing or a test".
- A split that a way makes between moments (a store meets a bound inside its instance) is not
  marked: it needs a call of `moment.split_ties` after `instance.step()` in run.py `next_moment`.
- The oracle reads `item.sink` in a where as the amount at that end and raises TypeError at SINK:
  it does not cover a where over flows (not edited).

## Status
- done
