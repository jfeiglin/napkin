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
- continuous/: no napkin.model import (System, initial_store, label_expression deleted; Context,
  step_cap(numerics), EVENT_TIME_TOLERANCE_H in system.py; fields/integrate/segment read a context).
- timeline/plan.py, run.py, component.py, record.py, __init__.py rebuilt (see the docstrings);
  napkin.engine.run/read exported; runtime.simulate deleted; sampling.py lost its model import.
- tank_delivery, unit_division, unit_product run right; every other example is refused by slice.
  Logistic over 20 y: 1e-10 relative at any time; cap 1 h takes ~20 s (the old test took 26.7 s).

- store.key(program, configuration) (ENGINE_STARTS = engine/timeline/__init__.py); trace.py deleted.
- New tests: tests/engine/test_programs.py (69), test_record.py (22), test_key.py (3).
- Ported: test_radau.py (two Roots tests on a program; 23), test_sizes.py (2),
  test_switching_surfaces.py (2). `Run.prepare()` gives the components at their start for tests.

## In progress
- Ports of test_resolution.py and test_cumulative_integration.py.

## Remaining
- Exit run (tests/core, tests/program, highs, rationing, sampling, solver_adapters); last message.
