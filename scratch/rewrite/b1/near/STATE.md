# Near-ties and `where` over flows, before G2 (track b1/near)

Brief: the coordinator's task message, with `briefs/COMMON-B.md`; PLAN "Changes after G0" 10.
Owned: engine/timeline/moment.py, triggers.py, collections.py, plan.py, engine/report.py,
model/semantic.py, lowering.py, tests/language/, new files in tests/engine/; later also
model/language/parse.py and tests/model/ (for the five bugs).

## Scope
1. Near-ties not marked yet: a split of who is served (settling), a gate's release, a false guard,
   a trigger within tolerance that did not fire. Detail `near`, report message for each.
2. `where` over an endpoint's flows, front end and engine.
3. (added by the coordinator) five bugs held as xfail(strict) in tests/model/ (cleanup STATE):
   deep expressions (RecursionError), two `record shared`, a note citing no record, a value then
   an event/flow of its name (AttributeError), an assertion over a sum of two moving stores.

## Design (decided, see docstrings once written)
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

## Status
- the five bugs of tests/model (cleanup STATE "Bugs found")
