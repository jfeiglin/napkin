# Review of round reads and coincident switches

This work is on `codex/freeze-rates`, branched from `claude/blissful-heisenberg-5me2hn` at `678df65`. The first implementation was `8cc9b71`. The test appendix identifies the affected expectations, the hand calculations and the failures seen before the fixes. [Changed tests](freeze-rates-tests.md)

## Four clock seeds

| Seed | What happened | Hand-worked answer |
| --- | --- | --- |
| 1923 | The unedited store is already full at 8 L. Editing it to zero at 2 h releases it. The fill changes from 3 to 2 L/h after the first litre. The incoming dense integration had already evaluated the slower branch before the root. | The edited store has 1 L at 7/3 h and 1 + 2 × (5/2 − 7/3) = 4/3 L at 5/2 h. Both resume paths agree. |
| 2027 | The rising store starts with 2 L and gains 2 L/h. Its 8 L switch meets the drain firing at 3 h. The comparison between the located switch time and the firing time used to depend on rounding. | The store has 8 L at 3 h. The drain then balances the incoming 2 L/h and the store still has 8 L at 3½ h. |
| 412 | The tank fills at 1 L/h up to its first litre and then at ½ L/h. A trial stage had used the slower field before the incoming trajectory reached 1 L. | 1 L at 1 h and 1 + ¼ × ½ = 9/8 L at 1¼ h. |
| 597 | Finishing a drain reverses the motion. The returning store crosses 6 L for the second time, at 20/9 h. | 17/3 L at 2 h, then 6 L at the return crossing. At 9/4 h it has 6 + (9/4 − 20/9) × ½ = 433/72 L. |

All four use the existing generator and ordinary engine–interpreter comparison. The named reductions exercise the same contacts separately. The laptop's original `s1.water` value for 1923 was reported as 1.3111 L. This checkout of the reviewed commit gave 1.321100000000677 L. Both differ from the same rational answer. [Clock models](../../../tests/engine/test_clock_moments.py) · [Named switch cases](../../../tests/engine/test_switch_segments.py)

The empty-tank case at **105/13 h** is `tests/engine/test_chattering.py::test_a_tank_that_empties_stops_with_chattering_at_the_time_that_it_empties`. It is a hand-built case with **no seed**. The tank begins with 50,000 people. Just above zero its outflows exceed inflow by 130,000/21 people/h. At zero they shut off and the positive inflow would refill it. The failure names the tank and both outflows. Seed 135 is a separate clock-model regression. [Chattering tests](../../../tests/engine/test_chattering.py)

## Timing entries

The inventory gives each returned timeline record's near-ties, including the path through a stop, grouped by test node and run number within that test. Each timing entry includes the original located time, the canonical moment, the origin, the comparison and the signed gap and tolerance in hours. An entry can occur in the checkpoint prefix and again in the resumed record. The compressed file is tab-separated text. [Near-tie inventory](freeze-rates-near-ties.tsv.gz)

The rounding-sensitive clock cases had these contact entries. The signed differences are in hours. The complete inventory includes stopped prefixes as well.

| Seed | Execution | Physical contact | Moment (h) | Located minus moment (h) |
| ---: | --- | --- | ---: | ---: |
| 242 | straight, edited in place, edited and restored | switch of f2.pipe | 2 | 8.881784197001252e-16 |
| 369 | straight, edited in place, edited and restored | switch of f1.pipe | 1 | 0.0 |
| 369 | straight, edited in place, edited and restored | switch of f2.pipe | 2 | 0.0 |
| 369 | straight, edited in place, edited and restored | switch of f0.pipe | 3 | 0.0 |
| 369 | straight | lower bound of s0.water | 4 | 8.881784197001252e-16 |
| 2027 | straight | switch of f0.pipe | 3 | 1.7763568394002505e-15 |

Seed 2027 has no contact at 3 h on its edited paths. Its edited store has 10 L there. The exact comparison also passes for seeds 277, 328, 516, 541, 547, 549, 1488, 1701, 1977, 1293 and 1748.

## Decisions and removals

- **Stages and firings** read the previous sharing's numeric flow rates, carried leg rates, endpoint totals, served fractions and solver results. The setup’s missing first result still stops by name. An ordinary write is visible within its stage and to later stages. Two writes in a round still produce one settled solve. In the clinic model the first read is 4 L/h and the zero-delay round and record give 2.4 L/h. In the staffing model 80 staff hours give a 56 h next delay. [Rounds and reading a result](../spec.md) · [Change 27 and change 10](../PLAN.md#changes-after-g0)
- **Arriving at a moment** keeps the numerical segment installed through the opening stages. A grouped bound supplies its exact value to direct reads. An edit of that store wins at settlement. A stopped run serializes numerical prefix data and keeps the held stage's opening answer. Post-stage settlement installs the pending physical state on resume. [Checkpoint handling](../../../napkin/engine/timeline/saved.py) · [Spec](../spec.md)
- **Coalescence** uses the same inclusive time window around an independently due moment in Component, Sparse, Family, Lines and declared solver ways. A located switch or bound alone retains its own instant. The human report shows the two times and their signed difference in hours. A grouped clock switch stays consumed during subsequent short waits and rebuilds. Tests check the reported location, the bounds of the window, and the rates on both sides. [Clock](../../../napkin/engine/timeline/moment.py) · [Change 10](../PLAN.md#changes-after-g0)
- **Trial states** hold the active comparisons and keyed rows until the located contact. The remaining arithmetic reads trial time and store levels. Dense output locates the contact from its physical operands. An authored clock root retains its written time. If a strictly later physical root rounds to the start of a step, the locator works in elapsed time to preserve the positive interval. Grouping still uses the configured time tolerance. A genuine reversal on both sides of an empty tank still reports chattering. The sparse batched evaluator, numerical Jacobians and moving LP retries follow the same branch as their scalar evaluations. A moving LP whose continuation is infeasible beyond a switch shortens its step to an estimated crossing and locates the actual crossing on the accepted trajectory. A one-sided Jacobian can use the feasible side of a trial coordinate. Equilibrium and continuation analyses evaluate the field at independent requested points. [Switch handling](../../../napkin/engine/continuous/integrate.py) · [Moving declared solver](../../../napkin/engine/timeline/declared.py) · [Vector field](../../../napkin/dynamics/field.py)
- **Outside flows** publish the numeric answer even for a SOURCE-to-SINK pipe. A switch can occur independently of a stage. Physical store trajectories and the clock supply the located time. The record keeps the outgoing rate at the event, including moving arithmetic on the chosen side and the zero rate when its occurrence finishes. A watched condition and a deferred delay can read the same publication. [Outside rates](../../../napkin/engine/timeline/reads.py) · [Rule tests](../../../tests/engine/test_round_rate_reads.py)
- **The run store** keys horizon, selection, mode and piece budget as well as the program, options, seed, implementation, processor and edit log. Selected keys are sorted in the identity, including duplicates. A hit returns the caller's selected-key order in its manifest. A deterministic piece-budget stop can be reused on the same request. Changes to the horizon or selection run afresh. [Change 28](../PLAN.md#changes-after-g0) · [Store](../../../napkin/store.py)
- **Removed code** includes `Ways.fresh`, `Ways.stale` and their diagnostic marks, the reference stale check, `Shared` and its old-input/member overrides, `Ways.incoming`, `Ways.store_side`, the checkpoint incoming-read reconstruction, Sparse’s incoming-piece replay, and `reads.on_side` and `reads.side_level`. Rebuild dependencies still pass through `changed_names`. The interpreter keeps the exact motion and after-moment logic that it uses independently of stale checking. Store coverage, widening and shorter-record cutting (`covers`, `served`, `_cut`, `_widened`) and the special case in change 24a are gone. [Timeline](../../../napkin/engine/timeline/run.py) · [Reference runtime](../../../tests/reference/run.py) · [Change 28](../PLAN.md#changes-after-g0)

## Planner profile

The wide reductions contain 3,000 and 3,500 members. When a dependency was missing, the stack walker expanded that one child and restarted the parent's enumeration. The initial members of the two arrays were revisited quadratically. This happened on `8b3a01a`, before the rate-read work. Profiling on this machine counted 10,685,755 calls to `Plan.expanded`. Retaining the reduction iterator across a yielded dependency cut the count to 77,505 in the profile of the correction. The membership, order, dependency union and cycle checks are preserved. The deterministic regression counts member visits rather than measuring wall time. [Planner](../../../napkin/engine/timeline/plan.py) · [Reduction test](../../../tests/engine/test_collections.py)

## Verification

The tests ran on macOS arm64 with CPython 3.13.16, NumPy 2.5.3 and SciPy 1.18.1. The central selection used four workers and the deep selection used pytest’s automatic worker count. The store was off. OpenBLAS and OpenMP used one thread. An observer recorded the near-ties of each returned record.

| Check | Result |
| --- | --- |
| Central suite | 10201 passed, 1 skipped in 218.33s (0:03:38) |
| Full deep selection | 6631 passed in 223.05s (0:03:43) |
| Ruff check and format | Passed, 467 Python files formatted |
| Git whitespace check | Passed |

The central skip reads the Linux process filesystem. All seeds in the requested deep selection ran under its existing comparison rules. The three existing random network generators have identical syntax trees to their versions at 678df65.

The central inventory contains 2,185 near-tie entries across returned records, including 1,201 physical timing contacts.
The deep inventory contains 8,116 near-tie entries across returned records, including 6,534 physical timing contacts.

## Three paired runs of the 3,000-place benchmark

Each rotation ran the three revisions with the locked environment on the same machine. The benchmark took 3,000 places, 3,500 routes and 1,500 sources. The only change to the benchmark script for measurement was printing more decimal places. Each run solved at 0 h in round 0 and at 24 h in round 1. All served 3,163.7587 W at 0 h and 3,083.5128 W at 48 h. [Benchmark](../b1/s5-engine/bench.py)

| Revision | Rotation | Build (s) | Plan (s) | Run and record (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 678df65 | 1 | 0.191 | 4.212 | 8.886 | 13.289 |
| 678df65 | 2 | 0.192 | 4.200 | 8.879 | 13.270 |
| 678df65 | 3 | 0.197 | 4.295 | 9.082 | 13.574 |
| **678df65** | **Median** | 0.192 | 4.212 | 8.886 | 13.289 |
| 8cc9b71 | 1 | 0.189 | 4.191 | 8.916 | 13.295 |
| 8cc9b71 | 2 | 0.191 | 4.288 | 9.553 | 14.032 |
| 8cc9b71 | 3 | 0.196 | 4.268 | 9.261 | 13.725 |
| **8cc9b71** | **Median** | 0.191 | 4.268 | 9.261 | 13.725 |
| Final source | 1 | 0.191 | 1.156 | 8.943 | 10.290 |
| Final source | 2 | 0.202 | 1.265 | 9.306 | 10.773 |
| Final source | 3 | 0.190 | 1.154 | 8.875 | 10.219 |
| **Final source** | **Median** | 0.191 | 1.156 | 8.943 | 10.290 |

Median ratios within a rotation against 678df65 were 0.999 for build, 0.274 for planning, 1.006 for run and record, and 0.774 overall.

## Engine line count

Against 678df65, `napkin/engine/` adds 2,146 lines and removes 902, for **+1,244 net lines**. The reviewed 8cc9b71 was +301. The branch exceeds the requested size aim. The old read reconstruction accounted for 285 removed lines of helpers, including docstrings. Most replacement code is for holding smooth fields on trial states, locating and reporting physical contacts across all ways, fitting moving outside-pipe histories, and preserving pending physical state across a serialized stop.

A straight stage read of a moving Component or Sparse rate samples its installed set on first access. Local sets with no reader take no capture at an unrelated moment. A checkpoint materializes outstanding samples. A moving declared solver prepares the incoming record prefix before its inputs can change. An outside pipe with moving arithmetic evaluates that arithmetic at the moment on its installed branch. Ordinary re-shares publish the affected sets and dependent outside pipes. The 3,000-place fixed-solver benchmark and the sample-count regression measure different parts of this cost.
