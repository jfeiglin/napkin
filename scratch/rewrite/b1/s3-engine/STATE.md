# S3-E state: the engine, fourth slice (reversible routes, flows with legs) — DONE

Brief: `briefs/s3.md` (S3-E), with `COMMON-B.md`, `s0-engine.md`, `s1.md`, `s2.md`; `b1/s2-engine`.

## Carry-over A (moving bench failed at 41.94 h): DONE
- Cause: parts with tiny rates (stores flagged within atol of empty; requests read the stock):
  (1) HiGHS's absolute tolerance (1e-7) is larger than the rates (1e-6..1e-13 L/h); (2) its start
  violates full-service rows within that tolerance; the primal active set of rank 4 then keeps
  the violation ("break a hard row") or cycles at the degenerate vertex ("did not settle").
- `selection.py`: programs in units of the part (`units`: part size for rates, 1 for fractions),
  claim rows in served fractions; rank 4 = primal from a feasible LP vertex (keeps the vertex's
  exact numbers, so event times stay exact), else dual Goldfarb-Idnani (no feasible start,
  per-row relative tolerances with a roundoff floor `NOISE`). Rows with positive parts
  (`Rows.convex`) for route legs: aux columns in LPs, linear pieces at x in rank 4.
- `sparse.py`: a flagged store is read at its bound. `network._general`: a failure names the part.
- Bench `moving 30000 35000` now runs to 48 h: build 3.6 s, plan 21.4 s, run+record 297.7 s.

## Routes and legs: DONE (core)
- `network.py`: flows (unknowns: DIRECTED rate, ROUTE signed rate in [-cap, cap], LEGS fraction
  in [0, 1]) over connections (DIRECT, FORWARD, BACKWARD, LEG); `carried` gives connection rates;
  `network_of(run, sets, stores)` builds it for lines and sparse. Endpoint request with a route leg:
  failure naming the endpoint (oracle NotCovered). Plain networks keep the S2 fast paths.
- `plan.py`: `Connection`, `Flow.kind/legs/connections`, `plan.connections`, `_parts`,
  `_numbers` (creation numbers from 1, as the oracle: a flow, then its legs); values: route
  actual_rate RATE (signed), `forward|backward.actual_rate|request` FORMULA max(+-x, 0); legs
  `served_fraction` RATE, leg `actual_rate` FORMULA fraction * request; `.source/.sink` of a
  directed flow, a leg or a route's leg name the store at that end (SOURCE/SINK: type error);
  routes and legs -> LINES or SPARSE, never FAMILY or COMPONENT.
- `lines.py`, `sparse.py`, `run.py` on connections; `asked_of` (signed route requests may cross 0).
- The 4 S3 examples run, equal to their values and the oracle; in `test_programs.SUBSET`.
- `test_record.py`: the S3 refusal case removed (a route runs).

## Carry-over B (lines 87 s): DONE, run+record 7.7 s (build 3.5, plan 9.1)
- Time went to re-solving the whole coupled part at each moment (parts of ~500 flows through
  empty stores: `_groups` 3.3 ms, `part` x2-4 per moment). Mends: `Lines._downstream` (closed
  sets: plain, all flows rigid, no settled endpoint, no `_general` yet, no store on its upper bound
  with inflows): a moment solves only the groups downstream of the changed stores, same arithmetic
  (`Instant.fill`, factored out of `_groups`); `part` goes through each coupling store once; the
  seed's ends flagged first; `carried(which=)`; `run._compute` reads a bare Ref without compiling.
- Same result but roundoff: at 3,000 places 2,928 of 71e6 read values differ, by <= 5.7e-14 (a
  store snapped to its bound at its own event, not flagged at another's).

## Tests and ports: DONE
- `test_local_sharing.py`: + routes and legs (300 normal, 2000 deep; vs oracle; all pass, also the
  2300 directed) + `chain`: downstream moments = whole parts = hand values = oracle.
- New `test_routes_and_legs.py` (9): request crossing zero (sparse), capacity + bound, priority on
  route and legs legs, R-A2-12, `.source/.sink`, SOURCE end refused, route-endpoint request fails
  by name, a "tally" as a route end, a moving leg request.
- Ported (were dormant): `test_coupled_queue_boundaries.py` (7 tests, + oracle), `test_chattering.py`
  (5; sparse: `_count` stall rule + chattering message), `test_closed_form_short.py` (18: `_groups`
  vs `_general` + closed forms), `test_roundoff_properties.py` (5; moves/events/timers dropped: S4).
- `allocation.Allocation.ration`: a leg that asks nothing moves nothing (no error); `test_rationing`.
- `selection._share/_prefer`: a level is the program's optimum value (noise test).
- Docstrings: plan, timeline `__init__`, collections.Entries, network, lines, sparse, selection.
- Run: tests/engine tests/core tests/program tests/reference tests/commands + 4 ports: 2319 passed.
## Benchmarks (alone, OPENBLAS_NUM_THREADS=1), final
- held 30000 35000: build 3.5 s, plan 9.2 s, run+record 8.1 s (was 87 s).
- moving 30000 35000: build 3.6 s, plan 22.2 s, run+record 299 s, to 48 h. Where it goes (profile
  at 10,000): ~3/4 in the 2,948 two-store components (a place with only `use`), each a numerical
  segment of the continuous engine with its pieces fitted (`record.segment`); sparse sets ~1/4.
