# S3-F: the front end, fourth slice — state (done)

Brief: `scratch/rewrite/briefs/s3.md` (with `COMMON-B.md`, `s0-front.md`, `s1.md`, `s2.md`).

## Done

- semantic.py: `DeclaredRoute` (a `DeclaredFlow`: signed request, capacity on the magnitude),
  `DeclaredLegs` (legs are `DeclaredFlow`s at `owner.flow.leg`, in `DeclaredModel.part`); types
  `RouteOf` (actual_rate, request, capacity, forward, backward), `LegsOf` (served_fraction, legs),
  `FlowOf.view` (a leg of a route: actual_rate, request, source, sink; no capacity). Priority items:
  legs and route legs; a bare route or a parent → `priority_item`. `restore.actual_rate` → `type`.
  Leg names: unique (`duplicate_name`), not served_fraction/actual_rate/request/capacity (`reserved`).
- `Resolver.end`: `f.source`/`f.sink` of a flow, leg or route leg read the store at that end,
  rebased on the flow's member (`this.main.sink` → `this.water`; projections keep keys).
- lowering.py: `build.route`, `build.legs`. parse.py: SOURCE/SINK at `<->` has code `route_end`.
- Tests: test_lowering.py sources of reversible_route, legs_half_service, legs_zero_leg,
  legs_all_zero (equal bytes); test_routes_and_legs.py (new, 33); S3 rows removed from the
  later-slice tests (test_lowering, test_semantic, test_endpoints). tests/language 378;
  language+program+reference+core+locator+strict_yaml 1467; tests/commands 66.
- No triage file is PORT-FRONT for S3 (its one S3 row is S3-E's). No change to napkin/program/.

## Decisions

- T1 Tally: the language has no mark of one, so a store is a tally only by use (nothing takes from
  it). A route takes from both ends, so a store at a route's end is a stock: only SOURCE, SINK
  (`route_end`) and what is no stored number (`flow_end`) are refused there. A store filled from
  SOURCE may be a route's end (test).
- T2 `.source`/`.sink` get a type: the store at that end (its amount, the steps of a store). Ends are
  fixed for the run, so the program reads the store by its path; it never holds a `.sink` read, and
  the engine needs nothing. Refused: an end at SOURCE/SINK, a member of an endpoint's `flows`
  (`flow_end`), a projection of a named end (`collection`), a route's own `.source` (via its legs).
- T3 Two endpoints may rank the same legs in other orders (R-A2-12 is the engine's rule).

## For the main session

- S4: an assignment target through `.source`/`.sink` must be refused (`fixed_write`): the front
  end rewrites the read to the store, so a write would reach the store.
- commands/run.py `named` knows `DeclaredFlow` only: a flow with legs' fields (served_fraction,
  each leg's) and a route's leg fields print after the others, in record order.
- check.py `priority_item`: its message for a flow with legs mentions only a route's legs
  (cosmetic; the front end refuses first).
