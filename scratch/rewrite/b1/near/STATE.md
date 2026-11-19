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

## Status
- reading (no code changed yet)
