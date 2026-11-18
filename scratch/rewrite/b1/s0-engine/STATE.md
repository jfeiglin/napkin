# S0-E state: the engine, first slice

## Design (decided)
- New S0 path, over the kept continuous engine: `timeline/plan.py` (rebuilt: `Plan.of(program,
  configuration)`), `timeline/run.py` (rebuilt `Run`: start values, sizes, the components to the
  horizon), `timeline/component.py` (kept `Network`; `Component` re-aimed: drives
  `continuous/segment.advance` for one connected set), `timeline/record.py` (new: pieces of each
  value, the trace, the reader `read`), `timeline/__init__.py` (`run(program, configuration)`).
- Why not feed the old `Run` (mixins state/segments/readers/checks/rules/steps/...): they read the
  old plan's flat spaces and the old structure (`plan.s`) through ~40 attributes; S0 has no rules,
  so a run is: start values, then each connected set to the horizon. The old mixin modules are
  left for the slices that re-aim or replace them; nothing on the new path imports them.
- Engine names: '.'.join((owner, *steps)) of a record Key (root owner '' left out):
  `tank.water`, flow id `clinic.delivery`, `clinic.delivery.request|capacity|actual_rate`.
- A flow's rate for the continuous engine: `min(request, capacity)`, request default 0.
- Kinds for the continuous engine: receive-only store with inflows -> 'cumulative' (monotone);
  lower == 0 -> 'stock'; else 'state'. No proven zero faces in S0.
- Record: stores and flow actual rates recorded per segment during the run (the field's bounds
  and faces are in force); affine segments exact linear pieces; curved segments Chebyshev-fitted
  pieces whose `rate` is a `Curve` (rate * elapsed = the increase), within the value's tolerance.
  Formulas, requests, capacities: fitted after the run from the histories they read.
- Step cap = numerics.max_step; no timescales (no spelling in the program).
- Constants of napkin/model/ir move into continuous/system.py (EVENT_TIME_TOLERANCE_H).

## Done
- (nothing yet)

## In progress
- plan.py

## Remaining
- run.py, component.py, record.py, __init__ exports, store.key, deletions, tests, ports.
