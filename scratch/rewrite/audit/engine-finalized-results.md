# Engine port-readiness evidence

**GO for scenario porting after auditor review.** The topic branch started from the audited Claude tip `6202824`. Both full correctness suites and public execution ran on `caecf1003c980821a235f264bd10c23d052734e1`. The full speed campaign ran on `fc9a9ed7fc9c6086f2ac38b27379f2cd14e71864`. The final trigger change was checked across all nine workloads and separately timed on the event workload. The Claude branch is still at its starting SHA, and the scenario translations have no changes in the topic diff.

## Correctness and migration

| Check | Result |
|---|---|
| Complete regular suite | 11,668 passed and 1 platform skip in 160.299 s on four workers, within the 180 s budget. All 300 rotated comparisons completed. |
| Complete deep suite | 25,750 passed in 404.638 s on 9 workers. All eight transformations ran for every one of 2,000 seeds. |
| Near-tie divergences in the generated corpus | Zero of 300 regular or 16,000 deep comparisons stopped early. |
| Audit and public execution | All 31 current audit cases, six valve comparisons and 242 CLI/artifact tests passed. A fresh process recovered 5 L and both meter citations from the format-4 artifact alone. The language version is 0.2.3. The owner waived the separate rerun of the 44 auditor-held cases. |
| Migration against `8488047` | Both median cases, twelve sampled piano runs, twelve reservoir configurations and 24 independent analytical cases passed. The checker rejected both the wrong number and the failed horizon stage. The CSV contains 432 observations at intermediate and terminal times. |

Both valve models gave the same physical results through Component, Sparse, MovingDeclared and the exact reference. Actual flow went from 0 to 1 L/h across the 0.5 h opening. The stock held 0.5 L at 1 h and 1.5 L at 2 h within floating-point precision. The stage-edited tank read 10, 8 and 7.5 L. The two overlapping requests read 1, 3, 2 and 0 L/h and credited slow, both, fast and neither. The whole-stock cases drain 4,000,000 L plus ⅔ L and the large-stock refund pays 0.05 L across empty stages and resumed checkpoints. [Public audit and exact valve readings](engine-finalized-public-checks.md) · [Migration observations](engine-finalized-migration-readings.csv.gz)

The initial full regular run on `fc9a9ed` passed all 11,624 runnable tests and took 185.025 s. `d83a7dd` batches independent queries against the same reference frame and adds a scalar-versus-batch parity check. All original observations, tolerances and seeds are retained. The two harness improvements after `d83a7dd` reuse identical numerical linear programs in the independent oracle and move seven new cross-product cases to deep. All seven cases retain their original assertions. [Per-case coverage and timings](regular-suite-coverage.md)

The second regular run, on `d83a7dd`, passed 11,625 tests but took 191.340 s. Its complete deep suite passed 25,743 in 476.273 s. The final suite clocks include collection. The regular platform skip reads Linux `/proc` on macOS. The regular and deep JUnit SHA-256 digests are `e51b7031eb861b1d77acc631fab812df501cea24754d442353c8b18f707993db` and `78ecbb0d945f548c03f9bb552e04698d91a8c065a0ef44b528ae54b28cef4768`.

## Final speed and memory

The figures are medians of within-pair candidate/baseline run-and-record ratios. Each row passes a limit of 1.05. The scripts are relative to `scratch/rewrite/b1`. Short batches use the same repeat count on both builds. Memory columns are the largest process peaks across the voting samples for each build.

| Workload | Script and arguments | Runs per sample | Median F/B | Baseline MiB | Candidate MiB |
|---|---|---:|---:|---:|---:|
| 12 moving tanks, Component | `s1-engine/bench_moving_tanks.py --tanks 12 --hours 12 --method component --repeat 2` | 2 | 0.981276 | 93.5 | 93.1 |
| 12 moving tanks, Sparse | `s1-engine/bench_moving_tanks.py --tanks 12 --hours 12 --method sparse --repeat 1` | 1 | 1.005625 | 89.0 | 89.7 |
| 12 finite-supply tanks, Component | `s1-engine/bench_moving_tanks.py --tanks 12 --hours 12 --method component --compartment --repeat 20` | 20 | 1.029747 | 88.6 | 90.1 |
| 12 finite-supply tanks, Sparse | `s1-engine/bench_moving_tanks.py --tanks 12 --hours 12 --method sparse --compartment --repeat 1` | 1 | 1.035079 | 90.0 | 89.4 |
| 1,200 independent held pipes | `s1-engine/bench.py 1200 --full-record-only` | 2 | 0.033402 | 165.1 | 169.4 |
| Held network | `s2-engine/bench.py held 30000 35000 48` | 1 | 0.025989 | 1,990.3 | 1,958.4 |
| Moving network | `s2-engine/bench.py moving 30000 35000 48` | 1 | 0.995144 | 1,909.2 | 2,093.2 |
| Event-heavy | `s4a-engine/bench.py 1200 48 12` | 1 | 0.997116 | 723.0 | 705.4 |
| Declared solver | `s5-engine/bench.py 3000 3500 1500 --no-phase-times` | 1 | 0.752002 | 762.0 | 635.9 |
| Event-heavy, final trigger correction | `s4a-engine/bench.py 1200 48 12` | 1 | 0.998763 | 722.9 | 701.6 |

The final trigger correction touched two runtime methods. Eight benchmark workloads bypassed both in the instrumented comparisons. Fifty-four separate timing samples on the nine confirmation models gave final/measured medians from 0.969835 to 1.027014. [Probe output and paired clocks](engine-finalized-contact-probe.md)

The event-heavy fixture uses a clock and a fixed phase, and it exercised the early return in `Triggers.anchor`. Its complete 1,200-place benchmark was repeated on the final build. Across the three new alternating pairs its median was 0.998763. [Final 1,200-place event pairs](engine-finalized-event-confirmation.csv)

The declared solver’s separate build + plan + run ratio was 0.785767. Both solves reproduced 3,163.7587 W initially and 3,083.5128 W at 48 h. All nine large-network sampled readings agreed across builds. Peak RSS on the voting moving-network samples grew from 1,909.2 to 2,093.2 MiB, an increase of 184.0 MiB. The 1,200-place event runs recorded 19,300 starts and 84 L. [Raw pairs, arguments, clocks, repeats and individual RSS](engine-finalized-release-timings.csv) · [Separate allocation, integration and posting counters](engine-finalized-release-counters.csv)

Both builds used the same integration work on the 30,000-place moving network. Component made 1,623,403 allocation calls and accepted 54,264 steps with 197 rejections. Sparse made 640,357 allocation calls and accepted 86,990 steps with 1,406 rejections. The candidate accumulated 2,948 directed amounts in Component and 44,457,356 in Sparse. The 1,200-place event workload started 19,300 occurrences and advanced 18,900 individual stock posting cursors. The held network completed with zero posting-cursor advances.

The original event median was **1.172899**, exceeding the gate. Two candidate samples overlapped seven deep-suite workers while their baselines did not. Before the subsequent results, the release declared three pairs with zero deep-suite overlap for each of the two affected comparisons. The original moving-network median was 1.033394. The table uses the matched votes. All original samples and their overlaps are retained. [Fixed comparison protocol](port-benchmark.md#matching-background-load-on-the-release-event-and-moving-network-runs)

| Single full-size confirmation | Baseline | Candidate | Result |
|---|---:|---:|---|
| `s4a-engine/bench.py 30000 48 12` | 7,498.460 s, 8.840 GiB | 7,522.483 s, 8.835 GiB | F/B 1.003204 on the matched inner run clock, below 1.10. Both finished 482,500 starts and the first stock held 84 L. |
| `s1-engine/bench.py 30000 --full-record-only` | >75 s certified inside the first run | 30.846494 s, 1,406.9 MiB | F/B < 0.411287, below 1.05. The candidate passed all twelve physical checks. The old full record never completed, so its exact time, peak and terminal readings are unavailable. |

The 30,000-place predicate sweep verified that each of the 30,000 event guards reads only the clock on both revisions. Three fresh passes over all predicates took 0.16350/0.15571, 0.16484/0.15913 and 0.16649/0.16510 s on the measured/final builds. Together with the six 1,200-place measurements, this checks the only reachable change at full population. The 48 h full-size simulation itself ran on `fc9a9ed`. [Cross-revision coverage and control](engine-finalized-contact-probe.md)

The earlier full held-pipe baseline process was stopped after 3 h 30 min 53 s. A bounded replay observed 75.003919458 s inside the first run and conservatively certified 75 s on the same clock. Neither observation is used as a completed baseline time. [Timing certificate](held-pipe-baseline-bound.md)

## Grouping and physical ownership

The timeline admits a stock contact to a nearby moment only if both its time and its stock reading qualify. The 1 h stage in the falling-cap example reads the accepted 1 L. A receipt of 1.000000005 L lies outside its band and occurs at its own later time if the flow continues. The regression saves at 0.99999 h, serializes, resumes, and compares the direct and empty-stage runs on all three moving methods. A run ending at 1 h finishes before that threshold.

Earlier rulings requiring a failure or an exact placement based on time proximity alone have been superseded. Conflicting targets that actually qualify still retain the incoming transfers and report a near-tie. Proportional posting on approaching legs, frozen gross allowances, ordered diagnostics and the release threshold of 10⁻¹² of gross traffic still apply. Earlier accepted balances are protected. Only the final connected portion of the incoming trajectory inside both bands can fund a correction. Room before the stock left and re-entered its band is excluded. Each donor and hard constraint is tested at its own scale. When a numerical method cannot certify enough room for an in-band correction, the books retain the accepted transfers and the trace identifies the constraint. An in-band posting at a moment can affect the difference of adjacent dense readings. Allocation supplies the reported physical rate.

Mixed clocks and stocks follow the same admission rule. Across six methods a 2 L/h stock compared with a threshold rising at 1 L/h fired at 0.999999995 or 1.000000005 h when outside its band, and grouped the in-band 0.9999999999 h contact at 1 h. A reported rate can supply a threshold without placing its underlying stock. An independently true inclusive guard fires once while it stays true. Changing constrained rates for which the method cannot certify a first contact retain the existing named diagnostic. [Mixed contact controls](../../../tests/engine/test_contact_group_distance.py)

Across 32 engine files the refactor added 4,346 lines and removed 815. The six numerical contact adapters and two trial-state checks retain method-specific numerical work. Physical posting, exact-placement decisions and bound classification are shared. All 131 changed package and test Python files on the final runtime revision passed Ruff lint and format checks. The transfer trace names the owner of each decision through the recorded balance, and the register identifies the remaining copies with their comparison tests. [Posting and removal inventory](accounting-write-sites.md) · [Changed assertions and superseded rulings](comparison-expectations-0.2.3.md) · [Rule register and comparative tests](engine-finalized-simple.md#cross-method-rules)

## Branch and milestones

The audited baseline and the verified remote Claude tip at branching were both `6202824d6d567c34ac46da7b018e66a9c28588b3`. The branch for this work is `engine_finalized_simple`. The allocation milestone was published separately at `5d82538` before settlement work started. The first settlement prototype was published at `97d7ae5`. The second was published at `31b07b0`. Isolated builds `b9834bf` and `d9e6e94` contain the corresponding prototypes on top of allocation alone.

[Responsibilities and workload specifications](engine-finalized-simple.md) · [Accounting write sites](accounting-write-sites.md) · [Changed expectations](comparison-expectations-0.2.3.md) · [Paired timing commands](port-benchmark.md)

## Earlier development candidates

Porting was on hold at this stage. At `4ed5afa` the shared departure and placement rules passed all 1,000 random solver cases and the 50 historical local-sharing cases. Its 3,000-place declared-solver benchmark passed both clocks. A separate computed-capacity check found a placement above the integrated capacity on Component and Sparse. With capacity rising from zero to 1 L/h over 1 h, the integral is 0.5 L. Both methods posted an extra 10⁻¹⁰ L to reach a nearby threshold. The long release benchmarks were parked when this was reproduced. The first repair at `2f787c1` made the rising-cap example retain 0.5 L, and tested both endpoint capacities, a declared inequality and checkpoint replay. An additional cut at 0.99999 h revealed unequal treatment of earlier unused capacity on two equivalent runs.

The full regular suite at `4ed5afa` took 175.515 s with four workers. It passed 11,419 tests, with 12 failures and one macOS skip. All 300 generated transformations passed with zero truncated pairs. Six failed tests used a recorder-budget observer that did not forward the new accepted coordinates. Updating it preserved every assertion. Three early-stage fixtures had required a placement that breached a hard cap outside the stock’s band. Two seeded cases exposed intermediate histories that remained flat while their physical balances changed, and one large-stock root had been checked twice under different numerical criteria. [Expectation changes and controls](comparison-expectations-0.2.3.md)

At `beefe67` the physical-history repair passes all 58 focused stock-departure and roundoff tests. Five methods now compare interior readings against the incidence of the very same constant-rate legs through the horizon. The test at the 54.00746897494162 h depletion of a 100-million-person stock also passes. Its root falls between adjacent representable times, and the numerical check keeps that proof while the stock writer carries the accepted transfers. [Cross-method histories](../../../tests/engine/test_stock_departure_rule.py) · [Depletion and scale controls](../../../tests/engine/test_sizes.py)

A capacity can have room over a full hour and still leave too little room since a certified reading. With `request = 1 L/h` and capacity falling linearly from 2 to 1 L/h, the analytical balance at 0.99999 h is 0.99999 L. Through 1 h the remaining capacity is 0.00001000005 L. Exact placement at 1.000000005 L would exceed that interval’s allowance by 0.00000000495 L. On the first repair Sparse posted that target in a direct run and reported a failure after an empty or serialized event. The amended change 27 addresses this case by testing both distances before the timeline admits a target.

Earlier candidate `e027caa` passed all 31 audit cases, 242 CLI/artifact tests, 12 independent piano and 12 independent reservoir checks, the paired piano and reservoir migrations and both checker rejection controls. The audit report includes each case and the underlying migration readings. [Public checks and migration data](engine-finalized-public-checks.md)

The 30,000-pipe candidate completed its full record in 24.019215 s and peaked at 1,511.9 MiB. All twelve physical readings at 6, 30 and 48 h matched the analytical values, with 330,012 histories and 933,955 pieces. The 30,000-pipe baseline was stopped. A separate bounded measurement certifies F/B < 0.320257 for this candidate. [Full-size timing bound](held-pipe-baseline-bound.md)

| Candidate | Declared solver baseline / candidate run-and-record pairs, seconds | Median run-and-record ratio | Median build + plan + run ratio | Baseline / candidate peak MiB |
|---|---|---:|---:|---:|
| `e027caa` | 10.505619 / 10.936673, 9.815588 / 10.600330, 9.662884 / 10.206901 | 1.056300 | 1.059701 | 742.7 / 752.5 |
| `08d3353` | 10.051769 / 11.229520, 9.433569 / 10.012055, 9.482748 / 9.926159 | 1.061322 | 1.054384 | 743.5 / 758.0 |
| `4ed5afa` | 8.691072 / 6.482258, 9.426436 / 6.668535, 9.378575 / 7.271729 | 0.745853 | 0.776104 | 762.3 / 668.9 |

The first two candidates exceeded the 1.05 solver limit. All three candidates produced the expected power readings. The long event guard on `e027caa` was stopped once that candidate failed the shorter gate.

The four-worker regular run at `e027caa` passed 11,190 tests. One macOS skip requires Linux `/proc`. The remaining test, declared-solver seed 96, repeatedly settled at 8/3 h until its worker was stopped. The 300 scheduled port comparisons passed with zero truncated pairs. A separate bounded check of all 1,000 random solver cases found the same repeated contact in seeds 188 and 853 and a rejected placement in seed 875. The development run does not satisfy the 180-second full-suite gate.

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
