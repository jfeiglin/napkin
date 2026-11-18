# A3 state (checkpoint 2, taken over by a second agent; update at each milestone)

## Checkpoint 2 (second agent)
- Written and passing: `solve/ranked.py` (pin and row), `solve/fair.py` (sequential exact with lower-bound fixes, `brute` reference), `solve/distance.py` (slacks + proximal point + dual semismooth Newton; `exact` enumeration), `solve/select.py` (whole order, restores the kept instance after each solve, `replace` for join/leave), `cases.py` (16 cases pass: all expected answers, kW, membership).
- Mended in `lp.py`: `getRowEntries` returns 3 values; an empty program (`kModelEmpty`) is an empty answer.
- Explore scripts are in `a3/explore/` (not the tmp folder). No FINDINGS.md draft existed.
- `checks.py`: distance 200 random problems vs enumeration (7e-9); fair 40 random networks vs brute force (8.8e-8).
- Distance at 3,000 (0.1): objective face 0.5 s (5 outer, 17 Newton, Armijo, delta 1e-14). AFTER the fair rank it does not converge (1,200 Newton, residual 1e-4..1e-3) for FIX 1e-7..1e-5; converges at FIX 1e-4 in 9 s (342 Newton). Tried and rejected: exact line search (slower), LM delta from residual (much slower; kept as a retry only), equality fix of claims below 100%, warm dual start, pinning each fair program by duals (no help, and 3.9e-5 off brute force on 2 of 40). HiGHS QP on the after-fair face: optimal, 38 s, 20,561 iterations (exact fallback).
- Over-request example: `explore/bridge.py` (Wheatstone bridge, unmet 4.65 with use unbounded vs 9.20 with use <= need).
- 30,000 (1.0), measure.py: fair normal: objective 4.32 s + fair 128.1 s, 467 programs, 460 distinct levels, 4,315 claims below 100%, completes [load 1.0]. Fair shortage (x1.45) with FIX 1e-7: infeasible part way (SolveError). Join 300 flows: warm 0.90 s vs fresh 6.12 s, optima equal; leave warm 0.89 s. Distance on the objective face at 30k: 3 scenarios did not finish in 590 s (output lost).
- 3,000: again cold/warm/batch: objective equal to 1e-9, fair levels within 6.4e-10. Small: whole order 6.8 ms (147/s), kept 5.9 ms; one LP rerun 19 us.
- FINDINGS.md: the harness refused the Write ("subagents return findings as text"); its full text went into the final report for the main session to save.
- Final runs stopped on request of the main session: fair shortage at 30k with FIX 1e-6 did not finish (stopped after objective 6.2 s); distance flows stage at 30k normal did not finish (stopped). No further measurement.
- DONE: findings text sent in the final report (FINDINGS.md write refused by harness); main session to save it.
- Row method loses an optimum by 3.1e-7 in the provider case; pin loses 0 (cases.py).


## Done, and where
- `solve/lp.py`: `Kept`, one HiGHS instance that keeps its program and basis (costs, bounds, add/delete columns and rows, basis repair after a delete). Works.
- `solve/form.py`: `Problem` (the one problem form) and `Work` (working units: column / scale, row / largest coefficient). Written, not yet run.
- `network.py`: the synthetic network (copied from `scratch/networks/net.py`, strengths x100, route capacities 2..12) and `program()`, the route-and-level program of the spec (columns level, supply, use, carried, short). Works.
- Exploration scripts (not deliverables) are in `/tmp/claude-0/-home-user-napkin/e09158c7-7039-5d6d-be85-61b3a193adaf/scratchpad/a3/`: `probe1.py`, `ex1.py` .. `ex6.py`. Run as `python exN.py SHARE SCENARIO` (SHARE 1.0 = 30,000 places; SCENARIO normal|high|damaged|global).
- Not started: `solve/ranked.py`, `solve/fair.py`, `solve/distance.py`, `solve/select.py`, `solve/exact.py`, `cases.py`, `measure.py`. `FINDINGS.md` is a first draft with TODO marks.

## Decisions so far (one line each)
- Keep an attained optimum by fixing from the duals: a column with a reduced cost goes to the bound it rests on, a row with a dual becomes an equality on its active side. Reason: by complementary slackness this is exactly the optimal face, and it adds no dense row. Threshold 1e-9 in working units. Check `c.x <= optimum + tolerance` on the final answer; fall back to the row `c.x <= optimum + tolerance` if the check fails.
- Tolerances: 1e-9 relative to the size of the terms of a row (the engine's `rtol` is 1e-9, `docs/engine.md:324`), with a floor of one scale unit of the row.
- Fair sharing: one program for each level is ruled out as the main path (numbers below). Chosen: many groups in one program (`max sum of t_g`, `rate_i/request_i >= t_g`), each group certified by its connected part of the dual support; freeze certified groups; merge groups whose part mixes levels; split what is left over. The sequential method (one group) stays as the exact fallback.
- Fairness structure on the kept instance: one floor column and one row for each claim, one column for each group; only `addCols` and bound changes during the rounds (the basis stays valid); delete all of it at the end of the solve and restore the saved basis.
- Start the fairness program with each t at its upper bound 1: no shortage then costs 0 iterations.
- A fixed claim is an equality `rate == level * request` below 100% and `rate >= request` at 100% in the distance step.
- Distance step: extend `nearest.py` (dual semismooth Newton): a slack for each `<=`/`>=` row, a small proximal weight for coordinates with no weight, a relative stop rule, then a polish on the final active set. Two stages: flows, then the other unknowns with the flows fixed.
- Unit spelling: all numerics in working units, so W or kW changes only rounding. Units in napkin have a scale and no offset (`napkin-base/napkin/core/units.py:28-31`), so "zero in its unit" is the same in every spelling.

## Numbers measured so far (4 cores, other agents running; load in brackets)
- `probe1.py`: HiGHS 1.12.0. `addCol` and `addRow` keep the basis valid. `deleteCols` and `deleteRows` mark it invalid; the status arrays are trimmed, so it can be set again by hand. Row dual is <= 0 on an upper side, >= 0 on a lower side; reduced cost d = c - A'y.
- `ex1.py 1.0` [0.6]: cold LP of `min sum(short)`, shortfall form (95,000 rows, 140,000 columns, 280,000 nonzeros): 4.09 s normal, 5.28 s need x1.45, 3.68 s with 1,000 routes down (87,000 to 105,000 iterations). Form with `use <= need` and no shortfall unknown (65,000 x 110,000): 2.65, 3.45, 2.42 s. Unmet total: 1164.10 normal (1,255 places short); 5808.66 against 5812.58 at x1.45; 1687.89 against 1688.03 damaged.
- `ex2.py 0.1 normal` [low]: sequential levels at 3,000 places: 50 programs, 49 levels below 1, 552 claims short, 2.37 s with the dual simplex (300 to 4,100 iterations for each level).
- `ex3.py 0.1 normal`: the same with the primal simplex after the first level: 1.03 s, 5 to 40 iterations and 10 to 20 ms for each level.
- `ex3.py 1.0 normal` [2.4]: 383 programs in 75.8 s, 110 to 300 ms each, 376 distinct levels, then HiGHS said infeasible with 26,563 claims pending (claims were fixed as equalities at computed levels). Eight programs at level 0 fixed one claim each (a stall).
- `ex4.py 1.0` [2.1]: one more `run()` of a kept instance with nothing changed: 23 to 31 ms and 0 iterations; reading the solution arrays 9 ms. Cold: 4.55 s dual simplex, 52 s primal simplex.
- `ex5.py 0.1 SCEN` (after objective 1 is fixed): connected parts of the dual support of `max sum of fractions` that hold claims: 36 (normal, 552 claims with a dual), 54 (damaged, 656), 61 (need x1.7, 1,880; largest part 177). No giant part, because the fixed columns cut the graph.
- `ex6.py 0.1 normal`: groups with the global rule "freeze only up to the lowest level that has leftovers": 14+ rounds (round 1: 586 iterations, 38 ms; round 2: 3,844 iterations, 143 ms; later 33 to 54 ms). The script then stopped on a bookkeeping error, not on the method.
- After objective 1 at 0.1: 2,632 columns and 1,160 rows fixed; no dual between 1e-12 and 1e-7.

## In the middle of
Writing `solve/` in this order: `ranked.py` (pin and row methods), `fair.py`, `select.py`, then `cases.py` for the small examples, then `distance.py`.

## Remaining, in order
1. `ranked.py`, `select.py`, small cases: staffing 70/30 and 56/24, provider 6/2, pump 2/2/0, two bottlenecks (2,2,3) and (4,0,5).
2. `fair.py`: parallel groups (eager, with the two checks below), safe mode, single group; `exact.py` brute force with one program for each member; random small networks.
3. `distance.py` with `<=`/`>=` rows; (2,2), (3,3), (1/2,1/2); worked network levels (8/3,-4/3,-4/3), (3,-3,0); enumeration over active sets; measure at scale.
4. Join and leave (membership 2, 1.5/1.5, 2, nothing); units (0.004 kW); cold against warm against batch; ten-unknown solve rate; `Allocation.ration` fast paths.
5. `measure.py` (whole table), `FINDINGS.md` with rulings R-A3-01.., final message.

## Facts in no file yet
- `use` with no upper bound differs from `use <= need`: under the route law, taking more than a request at one place can raise the total served elsewhere (5808.66 against 5812.58). The spec allows it ("may carry more than its own request").
- The binding has no batch change of row bounds (`changeRowBounds` is one row a call). `changeCoeff` cost is not measured; avoided.
- Soundness of the group method (proved on paper): the dual restricted to a connected part (rows with a dual, joined through columns that are not fixed) is a dual of `max sum of t_g` over that part alone, so a part whose claims with a dual all sit at one level v is fixed at v. This needs: (V1) held claims that the part leans on have levels <= v; (V2) each leftover claim ends at or above the level of the group it was left over from. A group at 100% is frozen only at the very end.
- Counterexample that forbids freezing higher groups blindly: a1 <= 0.3; a2 + b <= 1; b <= 0.6; group {a1, a2} and group {b}. The program gives b = 0.6 with its own bound as certificate, but the answer is a2 = b = 0.5.
- The part criterion alone cannot certify a nested pair (a <= 0.3, a + b <= 1): the parts of a and b join. Freezing the lower level first resolves it.
- Expected slow case, not yet measured: fair sharing with no objective before it and a global shortage, where one part holds every claim; the method then goes level by level.
- Ruled out: HiGHS's own QP (73 s at one tenth, earlier measurement); primal simplex cold; one program for each member; one program for each level as the main path.
