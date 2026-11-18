# S0-E state: the engine, first slice — DONE

## Design (decided)
- New S0 path over the kept continuous engine: `timeline/plan.py` (rebuilt: `Plan.of(program,
  configuration)`), `timeline/run.py` (rebuilt `Run`: start values, sizes, components to the
  horizon; `prepare()` gives the components at their start), `timeline/component.py` (`Network`
  kept as the system of one connected set; `Component` drives `continuous/segment.advance`),
  `timeline/record.py` (recorder, `Curve`, reader `read`), `timeline/__init__.py` (`run`).
- Why not feed the old `Run` with its mixins: they read the old plan's flat spaces and the old
  structure (`plan.s`) through ~40 attributes; S0 has no rules, so a run is the start, then each
  connected set to the horizon. The old mixin modules (state, segments, readers, checks, rules,
  steps, choices, lists, sharing) and reports.py are left; nothing on the new path imports them.
- Engine names: '.'.join((owner, *steps)) of a record Key (root has no owner): `tank.water`,
  flow id `clinic.delivery`, `clinic.delivery.request|capacity|actual_rate`.
- A flow's rate: `min(request, capacity)`, request default 0. Kinds: receive-only store ->
  'cumulative'; lower == 0 -> 'stock'; else 'state'. No proven faces in S0.
- Record: stores and actual rates from each segment while it is the present one (bounds/faces in
  force); affine segments exact lines; curved ones Chebyshev pieces (degree 8, `Curve` as rate,
  rate * elapsed = increase) to the value's tolerance (atol_factor * size; RELATIVE floor 1e-12;
  no check at a piece's end, whose value is the next piece's; at most 4096 cuts). Formulas,
  requests, capacities fitted after the run from the histories they read (read by bisection);
  a formula's size is its largest value at the knots.
- Refused up front (Outside, with the slice): setup starts, events, solvers, asserts, status,
  links, collections, keyed reads, endpoints, two flows out of or into one store, a rate reading
  an actual rate, routes, legs, enums, texts, categorical draws.
- Step cap = numerics.max_step; no timescales (no spelling in a program).
- EVENT_TIME_TOLERANCE_H moved into continuous/system.py; `typed.node` -> `nodes.read`.
- store.key(program, configuration); ENGINE_STARTS = engine/timeline/__init__.py.

## Done
- Everything of the brief. New tests: test_programs (69), test_record (22), test_key (3). Ported:
  test_radau (23), test_sizes (2), test_switching_surfaces (2), test_resolution (1 + 1 deep,
  22 s), test_cumulative_integration (18). Exit set (tests/core, tests/program, highs, rationing,
  sampling, solver_adapters): 927 passed.

## For the main session
- Deleted tests/engine/test_timeline_unclassified.py (Plan.flat; triage DELETE S0).
- Take off tests/dormant.txt: test_cumulative_integration, test_resolution, test_sizes,
  test_switching_surfaces, test_radau. tests/test_api.py CLOSURE must follow store.closure().
- Old path now broken at import: study.py, uncertainty.py, session.py, dynamics/*, store.verify,
  timeline/reports.py, tools/bench/measure.py.
