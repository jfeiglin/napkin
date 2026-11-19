# S2-E state: the engine, third slice (flow network, local sharing) — IN PROGRESS

Brief: `briefs/s2.md` (S2-E), with `COMMON-B.md`, `s0-engine.md`, `s1.md`.

## Design (decided)
- Sharing semantics = the oracle's (`tests/reference/network.py`): hard rows (caps, endpoint caps,
  bound rows), claims in tiers (supply depth, priority layer), max-min per tier, prefs of a priority
  endpoint with a request, least squares to the requests. Requests soft: an uncapped flow can be
  pulled above its request.
- The solve library leaves ~1e-7 errors (fixed fair levels with slack): not used for local sharing.
  `timeline/selection.py`: the same order in floats, HiGHS LPs (`continuous/highs.py`), claims fixed
  by equality, an active-set least squares: exact to roundoff on small coupled parts.
- `timeline/network.py`: the network of a set (incidence, endpoints, classes, layers), the coupled
  parts of an instant (bound stores, multi-flow endpoints with cap/request), closed forms (single
  flow; groups processed in supply order with water-filling by tier when every inflow of a bound
  store is rigid, cap <= request), else `selection`. Ring of empty stores / two full stores: failure
  naming the stores (oracle NotCovered).
- Ways of a set: family (one flow, nothing moving, no endpoint settings); `lines.py` (rates held
  between moments, any size, local updates); component (moving, S1-shaped, <= 150 stores); `sparse.py`
  (moving otherwise: sparse Radau, sharing at each evaluation).

## Done
- `selection.py`, `network.py`, `lines.py`; plan: `End`, `ends`, `rankings`, `.outflow/.inflow`
  paths, `.flows`, count of flows, cross-template flows, `Connected.way`; run: `classes_of`, lines.
- `test_programs.py` SUBSET + the 8 S2 examples, against expected values and the oracle.
- `test_local_sharing.py` (new): random networks vs the oracle, 300 normal + 2000 deep, all pass.
  Lines hold a store's flags until the next moment (the horizon is one), as the oracle does.
- `sparse.py` written (Vector: settings as arrays by shape; Radau step by step, bound/release events
  by bisection on the dense output; records kept stores/flows). Component kept for moving sets with
  <= 1 flow per store side and no endpoint settings; `component.Held` fails by name where a cut at a
  bound could differ from local sharing (a non-rigid flow on the other side of the store).
- Mended: test_collections (cross-template flow runs), test_cumulative_integration (fixture: one
  flow per account), test_record (S2 refusals removed; reading an actual rate in a request is S4).

- Rewritten: `test_rationing.py` (RULES: water-filling vs fractions, endpoint classes, ties, the
  R-A3-09 two-group case, empty-store cascade, soft request; coupled-transaction tests of
  `Allocation.ration` kept for S3). Ported: `test_priority_at_a_face.py` (fill capped at its request).
- Benchmark `bench.py held 30000 35000`: build 3.0 s, plan 7.5 s, run+record 87 s (lines, one set of
  52,038 stores, 113,009 line starts). `moving`: see the last message (sparse).

## Steps
1. selection.py  2. network.py  3. plan (endpoints, priority, cross-template, sets)  4. lines.py +
run  5. examples + oracle  6. random networks vs oracle  7. sparse.py  8. ports  9. benchmark
