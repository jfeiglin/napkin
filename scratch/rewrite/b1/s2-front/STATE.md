# S2-F: the front end, third slice — state (done)

Brief: `scratch/rewrite/briefs/s2.md` (with `COMMON-B.md`, `s0-front.md`, `s1.md`).

## Done

- Contract changes (napkin/program/, this slice only):
  - check.py `Resolver.collection`: a value that holds a collection (`count(this.pumps)`,
    `customers.by(rank)` of a root value) names its members; a collection value's initializer too.
  - build.py `_Operation`/`_Step`: `this.start` reads the field `start`, `this.start()` starts (also
    draw, where, by, at, choose).
  - check.py `reports(program)`: `equal_keys` (at the member that wins), `below_first_key` (at the
    reading part); they refuse nothing. Exact mini evaluator `_exact` of constant keys and tests.
- semantic.py: `EndOf` (outflow/inflow: actual_rate, request, capacity, flows), `FlowOf.flow`,
  `Read.stored`; `DeclaredEndpoint` on `DeclaredValue.outflow/inflow` (`endpoints`, `allocation`,
  `rate_setting`); flow ends by `store()` through any path (links, named members, the top level).
  `DeclaredModel.part` is an index (also `x.water.outflow`), so many diagnostics place in O(1).
- lowering.py `_endpoint` (a side with only `proportional()` is None), `reports`; compile.py
  `Compiled.reports` (Problems at their lines/files).
- Tests: test_endpoints.py (new, 38); test_lowering.py sources of reservoir_priority/proportional,
  common_sink, one_pipe x4 (equal bytes), handle fields; test_collections.py count(this.pumps);
  test_tables.py setup reports. language 345; language+program+reference+core+locator+strict_yaml
  1434 passed; tests/commands 64 passed, 1 failed by S2-E's work in progress (see below).
- Scale: 30,000 places + 35,000 routes with directed route flows through links: compile 3.9 s,
  reports 0.05 s.

## Decisions

- R1 The setup reports refuse nothing (spec: "setup reports"; lookup_below_first_key must still pass
  finish and fail at 1 h). Ties are reported for any members, not only file rows.
- R2 `.source`/`.sink` of a flow as values stay deferred, now to S3 (no type for a store reference).
- R3 A missing store at a flow end keeps code `flow_end` and its message (tests/commands expects it).
- R4 The incidence of a priority item is the checker's rule (located at the setting's line); the
  front end types items (a declared flow or a projection of one, not `.flows`), refuses duplicates.
- R5 Endpoint settings resolve after their store (a request may read its own store: no cycle);
  only a stored number takes them; `x = priority(...)` is code `allocation`.

## For the main session

- `napkin run` prints endpoint values now (`tuners.due.outflow.request`):
  tests/commands/test_run.py::test_napkin_run_prints_every_named_value... fails with S2-E's plan.py.
- Wire `Compiled.reports` into `napkin compile`/`run` as warnings (commands are not this track's).
