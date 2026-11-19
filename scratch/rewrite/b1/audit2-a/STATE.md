# Audit2-A state: the selection order and every change to an answer after it

Brief: `briefs/audit2.md` part A, with `briefs/COMMON-B.md`; re-audit rows 05, 06, 07. Reproduced
all three on 9eaecb8 (scratchpad `repro.py`): 07 garden named -> hospital/garden 0/1 (and 0/1 also
under proportional); 06 two pipes of a 5e-7 L/h inflow request -> 0, 0 in L, mL and kL; 05 a
return pipe of capacity 0 -> "a ring of stores at their upper bound".

## Where each cause acts (listed before any change)
1. Claims' order (07): named claims first, at (0, 0, layer); every other claim (1, level, layer).
   - `declared.Former.problem`: `place()` (flow claims, legs, routes) and the endpoint claim's
     `(0, 0, 1)` / `(1, level, 1)`; the module docstring states the rule.
   - oracle `tests/reference/network.py` `assemble`: `place = (0, 0) if mine else (1, level)`;
     module docstring. Local sharing's own order (level, layer): `network.Instant._general`
     (and `_groups`/`fill`, closed forms by depth then layer) is the reference, not changed.
   - Written objectives still rank before every claim (spec order): kept, noted.
2. Changes after a solve (06): `declared.polished` (snap to bounds, projection, positive parts;
   its nets `_missed`/`_short` check rows and claims in flow units, no objective);
   `DeclaredWay._solved` clips the polished answer unchecked; `solve/solver._answer` is the only
   end check (optima KEPT, levels and rows CHECK). Local sharing: `selection.select` snaps
   (|x| <= 1e-12 units to 0, near a bound to it) unchecked before `_exact` (checked by `_holds`).
3. Structure on the declared network (05): `network.supply_depths`, `room_depths` (`_depths`)
   walk every connection; used by `Instant.depths/rooms` (`_groups`, `_general`, `lines._downstream`)
   and `declared.Former.problem`; oracle `_supply_depths`, `_room_depths`. (`plan.connect` joins a
   closed pipe's stores into one calculation: static, B's file, not changed.)

## Done (engine and oracle; all lint-clean)
- 05: `network.carrying(net, asked)`: a connection carries iff its capacity and its endpoints'
  are > 0 and a leg asks. Depths, rings, priority classes/layers (`Network.ranking/layers(carries)`,
  spec "when both are eligible"), ranked endpoints, claim clusters and each claim's level read it,
  per instant (`Instant.carries/layer`; `Former.problem`); `_groups` reads supply through carrying
  inflows; a claim that nothing can carry takes (0, layer) and reads nothing; an endpoint's claim is
  the solver's if it names every carrying connection. Oracle: `shut` (pre-pass of endpoint caps).
- 07: `network.claim_order(net, lower, upper, carries, [Claim])` for local sharing (`_general`)
  and solvers (`Former._order`): clusters = live claims linked by shared endpoints; a cluster with an
  unnamed claim keeps local sharing's (level, layer); a cluster the solver names fully gets levels
  that step at local sharing's connections and at ranked solver connections, pass on elsewhere,
  and share one level around a ring of solver connections (`_passing`, Tarjan). Oracle `_places`.
- 06: `solve.Answer.admits(x)` = the solve's end checks (`_end_checks`) + no rank worse than the
  answer replaced (objective vs KEPT of its terms + ROUNDOFF; served fraction vs CHECK).
  `declared.published`: clip(polish), else clip(raw), else raw; `_short`/`_missed` removed;
  `_starved` keeps the terms of a multi-term full claim off bounds. Local sharing: snaps and
  `_exact` are candidates (`selection._kept`). Found on the way: `Kept.set_bounds` sent a column
  twice (a flow's claim and its endpoint's), which HiGHS refuses silently: now once, status checked.
- Tests (rule, no oracle): test_claim_order.py, test_published_answers.py (sizes 1 and 1e-7 L;
  L/mL/kL), test_closed_connections.py; audit rows + variants; solve/test_membership (+1). Each
  catches 9eaecb8 except unit invariance (which held). test_random_solvers.program(unit, size).
- Final: command 4,544 passed + 10 fresh-process refusals (code changed mid-run), 50/50 alone.
  Deep (random solvers 900, local sharing 4,000, new rule sets): 11,980 passed. Against 9eaecb8,
  1,000 random solver programs: 9 change values, 4 now stop by name at a ring of empty tanks that
  an unnamed flow's endpoint reaches (the old order put named claims first, unread).

## Decisions
- Unnamed flows keep local sharing's order; the solver's own sharing only in clusters it names
  fully; a priority stops the solver merging what a lower class serves (all four named with A
  first: A 1, not thirds). Written objectives still rank before every claim (spec order).
- A request at or below ~1e-11 L/h with a claim fails by name in the library (HiGHS tolerance).
- B's "For A": the oracle already reads decimals exactly; nothing to change. C, D: none.
