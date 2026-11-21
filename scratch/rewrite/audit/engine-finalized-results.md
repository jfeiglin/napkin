# Engine port-readiness evidence

## Branch and milestones

The audited baseline and the verified remote Claude tip at branching were both `6202824d6d567c34ac46da7b018e66a9c28588b3`. The branch for this work is `engine_finalized_simple`. The allocation milestone was published separately at `5d82538` before settlement work started. The first settlement prototype was published at `97d7ae5`. The second was published at `31b07b0`. Isolated builds `b9834bf` and `d9e6e94` contain the corresponding prototypes on top of allocation alone.

[Responsibilities and workload specifications](engine-finalized-simple.md) · [Accounting write sites](accounting-write-sites.md) · [Changed expectations](comparison-expectations-0.2.3.md) · [Paired timing commands](port-benchmark.md)

## Allocation and evidence

Each row gives the actual rate in L/h at 0.49 and 0.51 h, then the delivered volume in L at 1 and 2 h. Both valve forms were compared with the reference interpreter.

| Method | Valve | Rate at 0.49 h | Rate at 0.51 h | Volume at 1 h | Volume at 2 h |
|---|---|---:|---:|---:|---:|
| Component | Explicit | 0 | 1 | 0.5 | 1.5 |
| Component | Formula minimum | 0 | 1 | 0.5 | 1.5 |
| Sparse | Explicit | 0 | 1 | 0.5 | 1.5 |
| Sparse | Formula minimum | 0 | 1 | 0.5 | 1.5 |
| MovingDeclared | Explicit | 0 | 1 | 0.5 | 1.5 |
| MovingDeclared | Formula minimum | 0 | 1 | 0.5 | 1.5 |

The original checkout failed seven of the twelve new switch cases. All twelve passed on the published allocation revision. The public CLI also returned a request of 2 L/h and an actual rate of 1 L/h at both hours 1 and 2.

An overlapping pair of pipes produced live request/evidence readings of 1/slow, 3/slow and fast, 2/fast and 0/no citations. A fresh Python process given only a format-4 program file recovered the 5 L meter total and both source descriptions. A citation-only edit hit the run cache and a reordered selective query recovered the new description. Both public report paths now use the same scoped evidence index.

## Settlement experiments

The first prototype passed the named ramp and balanced linear cycle on both Component and Sparse. A half-hour event cut a longer proposal. The measured accepted quantities were 1/80 L at the cut and 1/20 L at the hour. A stronger zero-net cycle with each leg carrying t⁶ L/h exposed insufficient control of gross integral error while both stocks remained flat. The first prototype gave 0.1428959670803935 L against the analytical 1/7 L. Its checkpoint also lost cumulative amounts before the stop.

The second prototype recovers 1/7 L, integrates the reciprocal-clock cycle to log(2) L, and resumes through a serialized stage checkpoint. The half-hour prefixes are 1/896 L and log(1.5) L. A signed route that reverses contributes 4.5 L to each direction. Separate checkpoint, frozen-stock, valve, cut and route controls passed (127 checks).

The first prototype's instrumented development measurements follow. The timings include counting overhead, and concurrent work was in progress. The formal ratio gate uses its own alternating uninstrumented samples.

| Diagnostic | Baseline time / peak MiB | Allocation time / peak MiB | First prototype time / peak MiB |
|---|---:|---:|---:|
| Held local, 3,000 places / 3,500 routes / 48 h | 9.834 s / 290.5 | 9.556 s / 311.2 | 9.160 s / 276.8 |
| Moving local, 3,000 places / 3,500 routes / 48 h | 44.475 s / 345.7 | 39.405 s / 370.2 | 35.516 s / 357.9 |

All three builds had the same measured moving-network work. Component made 153,615 allocation calls with 5,139 accepted and 13 rejected solver steps. Sparse made 69,345 allocation calls with 9,413 accepted and 148 rejected steps. The held network made one call to Instant.values and used zero Radau steps. The pinned 1,200-place event pilot ran for 282.064 s with counting enabled, peaked at 547.6 MiB, started 19,300 occurrences and ended the first stock at 84 L.

## Paired prototype timings

The corrected prototype (`d9e6e94`) missed the held-network gate. These are per-run seconds, divided by the common repeat count for short batches. Ratios are medians of the three within-pair ratios.

| Workload | Baseline seconds, in pair order | Prototype seconds, in pair order | Allocation / baseline | Prototype / baseline | Baseline / prototype peak MiB |
|---|---|---|---:|---:|---:|
| 12 tanks, Component | 1.2161, 1.1968, 1.2137 | 1.2840, 1.2184, 1.2600 | 1.0169 | 1.0382 | 121.8 / 120.1 |
| 12 tanks, Sparse | 2.1470, 2.1120, 2.1497 | 2.1169, 2.1724, 2.2000 | 1.0042 | 1.0234 | 116.1 / 112.3 |
| Held network, 3,000 places / 3,500 routes / 48 h | 6.7846, 5.8007, 6.3713 | 7.2931, 6.0574, 6.8220 | 1.0100 | **1.0707** | 305.7 / 309.9 |
| Moving network, 3,000 places / 3,500 routes / 48 h | 31.9474, 31.0112, 31.1998 | 32.3740, 32.7707, 32.0266 | 1.0005 | 1.0265 | 381.1 / 399.1 |

On the moving network the second prototype performed the same number of allocations and Radau steps as the baseline. It accumulated 4,460,992 directed amounts in Sparse and 275 in Component. Three sampled outflows matched their independent receiving balances. On the 12 tanks both methods made 30,390 allocation evaluations and took 1,205 accepted Radau steps with zero rejections. Component closed 12 cumulative batches and Sparse 1,205. The largest difference between a measured leg and its receiving stock was 1.28e-13 L.

The third prototype was published at `51d14cd`, isolated timing build `ee8a22c`. Both held methods retain one pending rectangle per changed row. At its first rate change a row stores the two endpoints and the rate. Only the next change, read or checkpoint needs the subtotal. A checksum over 2,000 rows and three changes per row took 35.4 ms for the second prototype and 11.9 ms for the third, including reading every total. Forty local controls passed. The physical cutover requires the workload timings as well.

| Third prototype workload | Baseline seconds, in pair order | Prototype seconds, in pair order | Allocation / baseline | Prototype / baseline | Baseline / prototype peak MiB |
|---|---|---|---:|---:|---:|
| Held network, 3,000 places / 3,500 routes / 48 h | 6.4627, 6.6871, 6.6020 | 6.4318, 6.5533, 6.4237 | 1.0028 | 0.9800 | 290.9 / 293.4 |
| 12 finite-supply tanks, Component (19 runs per batch) | 0.075406, 0.075167, 0.075138 | 0.077306, 0.073972, 0.076668 | 0.9935 | 1.0204 | 90.0 / 89.7 |

The original 12-tank benchmark reaches its analytical exponential curve using Radau on both methods. A second benchmark uses the same capacity and time constants with each fill drawn from a finite supply. The baseline Component kernel then took zero Radau steps and 80.6 ms, and Sparse took 1,224 steps and 2.274 s. Both produced 95.0212931632 L in the first tank. Both models are included in the paired campaign.

The full baseline event guard measured 7,498.460 s inside `Run.run()`, with a process peak of 8.840 GiB. All 482,500 starts completed by 48 h and the first stock held the hand-calculated 84 L. The script's older 7,500.0 s aggregate clock included a second planning pass. The full-sized candidate uses the matching run-only clock. The repeated event comparisons use 1,200 places.

## Follow the refund through the fourth prototype

At branch revision `a65b6e1` (isolated build `a65f70d`), a donor starts with 1 L and the receiving pool with 10,000,000 L. The compiler binds the delivery's request to the authored clock formula, and the allocator permits a rate rising from zero to 0.1 L/h in one hour. The timeline cuts the proposal at a half-hour event. Component and Sparse each supply precisely 1/80 L at that cut and 1/20 L at the hour. Inspecting a half-hour checkpoint twice in opposite query orders preserved the serialized checkpoint and accepted amount. The second half supplies the difference, 3/80 L.

At the horizon the first stage stops the pipe and moves 10,000,000 L from the pool. The second stage asks the pool to pay the donor's 0.05 L loss. At this prototype the legacy balance path can report a deficit of 1e-9 L and reject payment. All six controls (both methods, uninterrupted, empty event and serialized resume) expose that gap before the run-state cutover. The authoritative-accounting gate requires a successful payment, pool balance zero and matching move trace.

A separate frozen-store control has one incoming polynomial leg and a reciprocal-rate neighbor on the same group. The third prototype's gross integral at its 0.1 L allowance was high by 5.55e-18 L on Component and low by 3.99e-18 L on Sparse. The fourth returns exactly 1/10 L on both. It uses the actually allocated integral when a bound or pipe ceiling limits the request. Its mixed-leg, accepted-cut, resume and allocation controls passed 188 focused checks.

## Production accounting gate

All 63 samples for the fourth prototype passed the per-workload timing gate. The numerical settings, model arguments and fixed repeat count were identical within each paired row. All nine event samples completed 19,300 starts and held 84 L at the first store. The first baseline and allocation-only samples were carried into the fourth-prototype event campaign with their original timestamps, hashes and alternating order. The third prototype had produced no timed event sample when the candidate changed. [Raw timing samples, arguments and revisions](engine-finalized-timings.csv)

| Workload | Allocation / baseline | Prototype / baseline | Prototype / allocation | Baseline / prototype peak MiB |
|---|---:|---:|---:|---:|
| Component, 12 finite-supply tanks | 0.999131 | 1.011007 | 1.008656 | 89.7 / 116.2 |
| Component, 12 general fills | 1.004715 | 1.005757 | 1.001037 | 93.9 / 119.3 |
| Sparse, 12 finite-supply tanks | 1.012420 | 1.005634 | 0.997118 | 90.5 / 116.5 |
| Sparse, 12 general fills | 1.004340 | 1.008304 | 1.007444 | 90.4 / 118.0 |
| Held network, 3,000 places / 3,500 routes | 1.005397 | 0.979967 | 1.005380 | 292.5 / 309.5 |
| Moving network, 3,000 places / 3,500 routes | 1.018748 | 1.023129 | 1.004300 | 368.1 / 397.9 |
| Events, 1,200 places / 48 h / 12 phases | 1.012905 | 1.007426 | 0.996992 | 607.1 / 628.2 |

On the 3,000-place moving network every build made 153,615 Component allocations with 5,139 accepted and 13 rejected steps. Sparse made 69,345 allocation evaluations with 9,413 accepted and 148 rejected steps. The fourth prototype accumulated 275 Component leg amounts and 4,460,992 Sparse leg amounts in 9,413 Sparse vector batches. The nonzero sampled outflow measured 125.06198903199099 L against 125.06198903199093 L at its independent sink. The other two sampled legs and sinks each held zero.

All 21 B/A/P diagnostic runs are complete. The 1,200-place event model made exactly 19,300 held-row allocation decisions and took zero Radau steps on each build. The finite-supply Component shortcut made 888 allocations and took zero Radau steps. On the same curves Sparse made 30,834 allocation evaluations and took 1,224 accepted steps with zero rejections. [Per-method counters, transfer checks and sample digests](engine-finalized-counters.csv)

## Held-pipe recording

On the pinned baseline, the history-budget check at each independent pipe exhaustion rebuilt moving collection histories. A profile at 300 and 600 places spent 2.55 and 9.55 s in this check. The optimization in `ee1e26a` counts how much eligible held-line histories, aliases and sums can grow. While that upper bound fits the piece budget the exact recount can wait. Where the bound cannot certify headroom, the recorder performs its original exact check.

Across 741 separate-process comparisons with the baseline, the complete or partial history, trace, first budget-failure time and visited pipe boundaries matched. The 30,000-place optimized smoke ran and recorded in 20.510343 s, with 330,012 histories, 929,461 pieces and a process peak of 1.443 GiB. The analytically checked total stock at 6, 30 and 48 h was 777,172.59, 302,565.772 and 134,151.7 L. This smoke used the isolated tree `03c7b12`. The final paired campaign repeats the measurement on the completed candidate. [Recorder budget controls](../../../tests/engine/test_held_history_budgets.py)

## Migration

The median piano and reservoir examples passed on `31b07b0` against `8488047`. With matched piano draws, all 144 point readings and 24 interval rates agreed exactly. On the reservoir, all 252 readings over 12 configurations passed. The largest differences were 6.11e-16 for water, 9.44e-16 for spilled volume, and 5.54e-8 h for time at risk. The checker rejected the deliberately wrong output and the failure at the horizon. [Protocol and results](paired-migrations-31b07b0.md)

## Audit coverage

The owner waived rerunning the 44 cases retained by the earlier auditor. Their earlier result is historical. The current 31-case bundle is available in this checkout and remains part of the gate. The interim integration run at `9a984c6` passed 23 of those 31. Three refunds, the whole-stock retirement and four first-capacity writes through occurrence selections failed at that revision.

At interim integration commit `9a984c6`, the regular suite excluding the new port corpus had 10,559 passes, 24 failures and one skip. The corresponding deep run had 23,729 passes and 14 failures, all at the study API's evidence-table call site. The 14 affected deep cases passed on the subsequent integrated branch. Final suite counts must come from the completed engine revision.

All 2,000 seed models compiled and finished under the independent interpreter, with every intermediate reading, two integrated transfer windows and the original 1.25 h firing exercised. The corpus contained 491 opening and 492 closing formula caps, and 520 opening and 497 closing explicit caps. This check establishes eligibility independently of the engine comparison results.

The first preflight of authoritative stock accounting passed 300 regular pairs in 19.89 s including six comparator controls, and all 16,000 deep transformed pairs in 266.16 s. Every compared pair reached its terminal outcome. This was a development snapshot on 2026-11-21 during implementation of checkpoint edits, bound contacts, cutoff records and stage targets. The final gates rerun both tiers on one committed candidate.

The physical cutover landed in `ab95577`. The current audit bundle passed 27 of 31 on that revision. All four outstanding cases concern setting a first capacity on another occurrence. The previously failing 0.05 L refunds and full-balance retirement now pass. Sixty-five additional frozen report, physical cutoff and CLI checks passed, including the raw history of a ref-only alias. Rebuilding the measured fourth prototype from the four patches published on the topic branch reproduced Git tree `bd3e014b407f430320bb5f8c4637032733f16182`. [Production transfer trace and removed paths](accounting-write-sites.md)

Stage-target commit `343ff5d` passed all 31 current audit cases and 27 related controls. The audited tank read 10, 8 and 7.5 L at hours 0, 1 and 2. A subsequent integration run of the legacy comparisons passed all 144 sampled piano readings, 24 interval rates and 252 reservoir readings. Its two negative controls both failed as required. The physical accounting follow-ups are `adeab28` and `69d9ba1`. The former keeps both sides of grouped placements in balance, preserves inlet and outlet totals on resting stocks, and restarts co-integrated producers when their reader leaves. The latter checks the incoming trajectory before treating a stock as stationary, including the third compartment in the analytical chain that starts with zero slope.

## Full-size baseline pilots

These are single measurements on `6202824`. The formal comparisons use alternating paired runs.

| Workload and arguments | Build | Plan | Run and record | Peak MiB | Physical check |
|---|---:|---:|---:|---:|---|
| `s2-engine/bench.py held 30000 35000 48` | 2.121 s | 6.797 s | 847.231 s | 1,926.66 | Sampled final stocks 0, 19.415 and 213.794912 L. |
| `s2-engine/bench.py moving 30000 35000 48` | 2.328 s | 14.199 s | 399.099 s | 2,035.63 | Sampled final stocks 0.010815, 41.963914 and 204.061494 L. |
| `s5-engine/bench.py 3000 3500 1500` | 0.202 s | 1.194 s | 9.210 s | 742.97 | Served power 3,163.7587 W at 0 h and 3,083.5128 W at 48 h. |

At `adeab28` the full-only 30,000-pipe run took 26.921 s. Its 330,012 histories occupied 933,955 pieces and the process peaked at 1,443.16 MiB. The total stock at 6, 30 and 48 h was 777,172.59, 302,565.772 and 134,151.7 L.

The 30,000-pipe baseline process on `6202824` was stopped after 3 h 30 min 53 s of observed process elapsed time. Planning had finished and the first full record was still computing. This gives neither a completed run-plus-record time nor a peak RSS or paired ratio. The repeated comparison uses 1,200 pipes for three alternating baseline/candidate pairs, with a separate full-size candidate run. The 26.921 s result above belongs to the earlier candidate.

## Held-network recorder

At 3,000 places the held network spent most of its time recounting the same history pieces. The profiler counted 1,610 full counts across 1,609 moments. Commit `8f1b34e` uses a conservative bound on the number of new pieces until the next exact count for eligible held rows and step-held sums. The development run needed seven exact counts and retained the same 57,696 histories and 81,206 pieces. Eleven budget tests cover full and selective recording, tight limits and the boundary between a successful run and a budget failure. Commit `8dd1c25` compares both sides of a serialized checkpoint with eager counting.
