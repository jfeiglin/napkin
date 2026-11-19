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
- The 9 examples of the subset pass (`scratchpad ex_check.py`).

## Steps
1. selection.py  2. network.py  3. plan (endpoints, priority, cross-template, sets)  4. lines.py +
run  5. examples + oracle  6. random networks vs oracle  7. sparse.py  8. ports  9. benchmark
