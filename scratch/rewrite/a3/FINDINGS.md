# A3 findings: solver numerics

Prototype A3. I took it over from a stopped agent at checkpoint 1 (see `STATE.md`). The machine has 4 cores, shared with other agents, and each timing gives its load. Software: Python 3.13, SciPy 1.18.1 with HiGHS 1.12.0, one thread.

## 1. Summary

- Every expected answer of the brief passes on one code path (`cases.py`, 17 cases). The path covers the ranks, fair sharing, both distance stages, kW, and membership on a kept instance.
- **Ranked objectives: pin by the duals.** Pinning loses 0 in every case. The added row `c.x <= optimum + tol` loses 3.1e-7 in the provider case, and it puts a dense row into the distance step.
- **Risk 2, fair sharing at scale:**
  - A go at 3,000 places: 50 to 172 programs, 1.1 to 4.4 s.
  - A no-go at 30,000 places. With no shortage: 467 programs, 128 s, 460 distinct levels. With shortage (need x1.45): failed part way, because a later program was infeasible. It also did not finish in a second run with a looser fix; I stopped that run.
  - It matches brute force on 40 random networks (8.8e-8).
  - I did not make the method of groups sound.
- **Risk 1, inequality rows in the distance step:**
  - A go for correctness: 200 random problems agree with an exact enumeration to 7e-9.
  - A no-go for cost. On the objective face it takes 0.5 s at 3,000 places. At 30,000 the three scenarios did not finish in 590 s.
  - On the face that fair sharing leaves, it does not converge at 3,000 places. HiGHS's own QP is exact there and takes 38 s.
- **Risk 3, unknowns that join and leave: a go.** Each answer equals a fresh form: 2; then 1.5 and 1.5; then 2; then nothing. 300 new flows cost 0.04 s warm against 0.23 s fresh at 3,000 places, and 0.90 s against 6.12 s at 30,000.
- **Owner ruling:** a flow with no capacity at its request can take more than it asks when an earlier objective gains from it. In a five-route bridge, unmet falls from 9.20 to 4.65. An author forbids it with `capacity = request` (R-A3-07).

## 2. What was done

All paths are under `scratch/rewrite/a3/`. Run each script with `/home/user/napkin/.venv/bin/python`.

- `solve/lp.py`: `Kept`, one HiGHS instance that keeps its program and its basis. It adds and deletes columns and rows, and carries the basis by hand.
- `solve/form.py`: `Problem`, the one problem form, and `Work`, the same problem in working units.
- `solve/ranked.py`: ranked objectives by `pin` (chosen) or by `row`. `Face` holds the feasible set as it narrows.
- `solve/fair.py`: `sequential`, the exact max-min method on the kept instance, and `brute`, the reference with one program for each claim.
- `solve/distance.py`: `nearest`, the distance step with `==`, `<=` and `>=` rows, and `exact`, an enumeration of active sets.
- `solve/select.py`: `Selector`, the whole selection order on one kept instance; `replace` handles membership.
- `network.py`: the synthetic network and the route-and-level program (from checkpoint 1).
- `cases.py` checks the expected answers: run `python cases.py`.
- `checks.py` runs the random checks: run `python checks.py 200`.
- `measure.py` makes the measured table again: `python measure.py`, or `python measure.py SECTION --share S --repeat R`. The sections are units, small, ranked, distance, join, after, fair and again.
- `explore/`: the scripts of checkpoint 1, plus `overdraw.py` and `bridge.py` (R-A3-07).

**Finished work that I mended:**
- `lp.py` `delete_rows` read `getRowEntries` as 4 values; the binding returns 3.
- `delete_rows` scanned every column for each deleted row, which was quadratic.
- An empty program (`kModelEmpty`) is now an empty answer, not an error.
- The fair-sharing failure of checkpoint 1: it fixed claims as equalities at the computed level, and the program became infeasible at 30,000 places. A fixed claim now gets the lower bound `F x >= level - 1e-7`. With that change, the run with no shortage completes. The run with shortage still fails part way.

## 3. Results

### Expected answers (`cases.py`: all pass)

- Staffing: 70 and 30, then 56 and 24.
- Provider: 6 and 2; East asking 2 gives 2 and 6.
- Pump: fill 2, clinic 2, town 0 (charge 1 W, motor 1 W). With no request, every transfer is 0.
- Two bottlenecks: (2, 2, 3) with no objective, and (4, 0, 5) with the objective first.
- Worked network:
  - 0 h: uses 4 and 4, supply 8, routes 4 and -4, levels (8/3, -4/3, -4/3).
  - Clinic first: 6 and 2.
  - 1 h: 3 and 3, supply 6.
  - 2 h with the garden route down: 6 and 0, levels (3, -3, 0).
  - Unequal claims (2 and 6, supply 4): 1 and 3.
  - In kW: 0.004 and 0.004. The answer in W differs from the answer in kW by 4.4e-16 W.
- Membership on one kept instance: 2; then 1.5 and 1.5; then 2; then nothing. Each equals a freshly formed problem.
- Pin against row, on three cases: the same answers. The largest loss of an optimum is 0 with pin and 3.1e-7 with the row.

### Fair sharing (`measure.py fair`)

The method has one program `max t`, with `F_i x >= t` for each pending claim. A claim whose row has a dual above 1e-9 is fixed with `F_i x >= t* - 1e-7`. After the first program it uses the primal simplex. It is exact by complementary slackness (`solve/fair.py:1-17`).

| Places | Scenario | Objective | Fair rank | Programs | Distinct levels | Claims below 100% |
| -: | - | -: | -: | -: | -: | -: |
| 3,000 | normal | 0.16 s | 1.06 s | 50 | 50 | 552 |
| 3,000 | need x1.45 | 0.20 s | 3.28 s | 126 | 126 | 1,356 |
| 3,000 | 100 routes down | 0.15 s | 1.32 s | 71 | 61 | 656 |
| 3,000 | need x1.7 | 0.21 s | 4.43 s | 172 | 171 | 1,880 |
| 30,000 | normal | 4.32 s | 128.1 s | 467 | 460 | 4,315 |
| 30,000 | need x1.45 | 6.2 s | failed part way: infeasible (fix slack 1e-7); did not finish with fix slack 1e-6 (stopped) | - | - | - |

- 3,000 places: best of three [load 0.4 to 0.6].
- 30,000 places: one run [load 1.0].
- Not measured: 10,000 places, 30,000 with damage or with need x1.7, several tiers at scale.
- Against brute force (`checks.py`): 40 random networks of 10 to 15 places, with and without an objective, with shortage and damage, 1 to 4 levels each. Largest difference: 8.75e-8.

### Distance step

- The spec checks pass: `4 <= x + y <= 6` gives (2, 2) from targets (0, 0) and (3, 3) from (5, 5); `x + y == 1` gives (1/2, 1/2); the worked network's levels are exact.
- 200 random problems (2 to 4 unknowns, 1 to 3 rows of every kind, boxes), against the enumeration: largest difference 7.1e-9.
- Objective face at 3,000 places, no fair rank: 0.52 s, 5 outer steps, 17 Newton steps.
- Objective face at 30,000 places: the three scenarios did not finish in 590 s. A later run on the normal case alone did not finish before I stopped it.
- Face after the fair rank, at 3,000 places:
  - The method did not converge: 1,200 Newton steps in 50 s, with a residual of 1e-4 to 1e-3, for fix slacks from 1e-7 to 1e-5.
  - With a fix slack of 1e-4 it converges (9 s, 342 Newton steps). That slack changes the answer too much.
  - HiGHS's QP on the same face: optimal in 38 s, 20,561 iterations [load about 1].
- Tried, and none of these mends it:
  - An exact line search: slower (0.80 s against 0.52 s on the objective face).
  - A Levenberg-Marquardt term tied to the residual: 4.6 to 22 s on the objective face. It is kept only as a retry when an inner solve fails; that retry mends a small case.
  - Fixing the claims below 100% as equalities.
  - Starting the dual from the answer on the objective face.
  - Pinning each fair program by its duals. It did not help, and it was 3.9e-5 off brute force on 2 of 40 networks, so it is off.

### Join and leave (`measure.py join`)

| Places | 300 flows join: warm | Formed fresh | They leave: warm | Optima |
| -: | -: | -: | -: | - |
| 3,000 | 0.04 s (806 iterations) | 0.23 s | 0.13 s (1,887 iterations) | equal to fresh |
| 30,000 | 0.90 s (6,236 iterations) | 6.12 s | 0.89 s (4,005 iterations) | equal to fresh (5738.912608, 5808.663783) |

### The same result again (3,000 places, with shortage)

- The optimum of objective 1 is 601.853501921 in all three runs: cold, warm after another problem, and as the second block of a batch.
- The fair levels differ by at most 6.4e-10 warm and 1.7e-10 in the batch, within the fix slack.
- The distance step was not compared, because it does not converge at this size.

### Small solves (provider case, about ten unknowns)

- The whole order formed each time: 6.83 ms (147 a second).
- The whole order on a kept instance: 5.89 ms (170 a second).
- One HiGHS rerun on a kept instance with nothing changed: 19 µs [load 0.7].
- Python and the sparse factorization take most of the time, not HiGHS.

## 4. Rulings

### R-A3-01: Keeping an attained optimum  [technical]
Rule: after each objective, pin from the duals. A column whose reduced cost is above 1e-9 in working units goes to the bound it rests on. A row whose dual is above 1e-9 becomes an equality on its active side. On the final answer, check `c.x <= optimum + 1e-7 * max(1, |c|.|x|)`, and fail by name (`numerical`) if the check fails.
Alternative: add the row `c.x <= optimum + tol`.
Example: in the provider case, both methods give 6 and 2. Pin loses 0 of the first optimum; the row loses 3.1e-7. At 30,000 places the row would be dense in the distance step.
Recommendation: pin. For one optimal dual, the pinned set is exactly the optimal face, and pinning adds no row.

### R-A3-02: Tolerances  [technical]
Rule: all numerics are in working units: each column is divided by its reference scale, and each row by its largest coefficient. The tolerances are:
- A reduced cost or a dual counts as zero below 1e-9.
- A ranked optimum is kept to 1e-7 relative, the feasibility tolerance of HiGHS.
- A fixed fair claim gets `fraction >= level - 1e-7`, never an equality.
- The distance step stops when each row's residual is at most 1e-9 x (1 + the size of the row's terms).
- An ordinary formula that reads an equality which the solver enforced holds to the engine's `rtol` of 1e-9 plus 1e-7 x the size of its terms.
Alternative: one absolute tolerance. The rule of `nearest.py`, an absolute 1e-10, was too strict.
Example: with equality fixes, checkpoint 1 failed after 383 programs at 30,000 places. With lower bounds, the normal case completes (467 programs). The shortage case still failed part way, so the 1e-7 slack is not enough at that size.
Recommendation: adopt these values. Treat a solve whose fair rank becomes infeasible as the named failure `numerical`, never as a different answer.

### R-A3-03: The algorithm for each rank  [technical]
Rule:
- Hard constraints and ranked objectives: the dual simplex, cold and then warm on one kept instance, with each optimum pinned.
- Fair sharing: for each tier in declared order, the sequential exact method, with the primal simplex after the first program.
- Distance steps: a slack for each inequality row, the proximal point method for the coordinates with no weight, and a dual semismooth Newton method. The flows go first; then the other unknowns, with the flows fixed.
Alternatives: HiGHS's QP for the distance steps; one program for each member for fair sharing.
Example: the worked network gives the published rates and levels through all four ranks.
Recommendation: adopt the first two. The distance method is right but has no time guarantee after a fair rank (R-A3-05).

### R-A3-04: Fair sharing at scale  [owner]
Rule: compute the fair-sharing rank only with the sequential exact method. Give it a measured budget, and stop a solve that passes the budget with the named failure `fair-sharing budget exceeded (N levels)`. Never give another answer.
Alternative: the method of groups, many levels in one program, each certified by a connected part of the dual support. Checkpoint 1 found it unsound in general: with `a1 <= 0.3; a2 + b <= 1; b <= 0.6` it certifies b at 0.6, but the answer is 0.5. Its safe form at 3,000 places took 14 or more rounds of 33 to 143 ms each (`explore/ex6.py`), no better than the sequential method. I did not make it sound.
Example: at 3,000 places with need x1.7: 172 programs and 171 levels in 4.4 s. At 30,000 places with no shortage: 467 programs and 460 levels in 128 s. With shortage: failed part way, infeasible.
Recommendation: a **go up to 3,000 places and about 170 distinct levels**, which is what I measured: at most 4.4 s for the rank and 4.6 s with the objective. 30,000 places is a **no-go**: 128 s with no shortage, and a failure part way with shortage. The cost is roughly the number of levels times the cost of one warm program, and both grow with the size. 10,000 places was not measured. The owner should decide whether a failure by name is acceptable above 3,000 places.

### R-A3-05: Inequality rows in the distance step  [technical]
Rule: give each `<=` or `>=` row a slack inside its interval. Give each coordinate with no weight a proximal weight of 1e-3 around its last value, and stop when those centres stop moving. Solve each subproblem with a dual semismooth Newton method: an Armijo line search, a regularization of 1e-14, and a Levenberg-Marquardt retry.
Alternative: HiGHS's QP. It is exact, and it takes 38 s at 3,000 places after a fair rank.
Example: `4 <= x + y <= 6` gives (2, 2) and (3, 3). 200 random problems agree with the enumeration to 7e-9. The objective face takes 0.5 s at 3,000 places. At 30,000 places it did not finish in 590 s.
Recommendation: a go for correctness and a no-go for cost. After a fair rank, the method did not converge at 3,000 places. The likely cause is a face that is feasible only to 1e-7 and has no width in many directions. Until a better method is found, use HiGHS's QP up to 3,000 places and refuse by name above that (`distance step: no answer within budget`). Never loosen the fix: a looser fix changes the answer.

### R-A3-06: Unknowns that join and leave  [technical]
Rule: one kept instance per run. A joining flow is added with `addCols`, and the basis stays valid. A leaving flow is removed with `deleteCols`, and the basis is set again by hand. After each solve, every bound, cost, row and column that the ranks added is restored or deleted.
Alternative: form the program again at each change.
Example: a 3 L/h limit with 2 L/h per occurrence gives 2; then 1.5 each; then 2; then nothing. Each equals a fresh form. At 30,000 places, 300 flows join in 0.90 s against 6.12 s formed fresh.
Recommendation: go.

### R-A3-07: A flow may take more than its request  [owner]
Rule: as the spec says, a flow with no capacity at its request "may carry more than its own request" when an earlier objective gains from it. Under the route law, a place that takes more than it asked can shift the levels so that more reaches another place. An author who forbids this writes `capacity = this.request`, or `capacity = formula(this.request)` when the request changes.
Alternative: make every request a cap on its flow in the language.
Example (`explore/bridge.py`):
- Places: J (supply 10), X (asks 0.1), Y (asks 0), B (asks 10).
- Routes and strengths: J-X 2, J-Y 1, X-B 1, Y-B 2, and the bridge X-Y 1 with capacity 0.1.
- With `minimize(sum(unmet))`, X takes 4.65 and B gets 5.35: unmet 4.65.
- With `capacity = request`, X takes 0.1 and B gets 0.8: unmet 9.20.
- At 30,000 places with need x1.45: unmet 5808.66 against 5812.58 (`explore/ex1.py`).
Recommendation: keep the spec's rule, document it with this example, and tell authors to write the capacity when they want "never more than asked".

### R-A3-08: The zero reference of a solver-local unknown  [owner]
Rule: keep the spec's rule. A solver-local unknown with no initializer prefers zero in its unit. Its scale is the declared scale, else the declared width, else one canonical unit. A unit has a scale and no offset (`napkin-base/napkin/core/units.py:28-31`), so zero is the same in every spelling of the unit.
Alternative: prefer the midpoint of the unknown's interval.
Example: `spare: h in [10 h, 50 h]`, decided by nothing else, is 10 h under the rule and 30 h under the alternative. The worked network gives the same answer in W and in kW (0.004 kW).
Recommendation: keep zero. An author who wants another value writes an initializer.

### R-A3-09: Fast paths of `Allocation.ration` that stay  [technical]
Rule: these closed forms in `allocation.py:96-182` stay right under the new rules:
- (a) A proportional group whose flows are in no other binding group (lines 129-148). Its water-filling with local caps is the exact max-min for one sum row with bounds.
- (b) A priority group with no ties (lines 149-153).
These cases go to the solve library:
- (c) A flow in two binding groups, such as a request at the flow and at its source or sink.
- (d) Ties within a priority order.
- (e) Coupled transactions (lines 156-181): taking the minimum over the legs frees capacity that nobody else gets.
A leg that asks nothing (an error today at line 165) has no claim, and the one fraction covers the legs that ask.
Alternative: drop every fast path.
Example: two flows ask 2 each from a 3 L/h limit. Path (a) gives 1.5 each. If one of them is also capped at 1 by its source, one group after another gives 1 and 1.5, while max-min gives 1 and 2.
Recommendation: keep (a) and (b), behind a check that the groups are disjoint. A small solve costs 6 to 7 ms.

## 5. Not covered

- The method of groups was not made sound.
- Not measured at 30,000 places: several priority tiers, damage, need x1.7. 10,000 places was not measured at all.
- The distance step at scale did not finish. HiGHS's QP was not run at 30,000 places.
- The whole order with the distance step at scale, and the cold, warm and batch comparison for the distance step.
- kW on the 30,000-place network: only the worked network was checked in kW.
- `changeCoeff` was not used.
- `measure.py` with no arguments runs the full table, including the 30,000-place runs that are known to be long or to fail. Stop it at 10 minutes.
