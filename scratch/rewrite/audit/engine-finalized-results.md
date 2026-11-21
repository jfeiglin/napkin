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

The physical accounting cutover remains gated on a passing revision for all prototype workloads.

## Migration

The median piano and reservoir examples passed on `31b07b0` against `8488047`. With matched piano draws, all 144 point readings and 24 interval rates agreed exactly. On the reservoir, all 252 readings over 12 configurations passed. The largest differences were 6.11e-16 for water, 9.44e-16 for spilled volume, and 5.54e-8 h for time at risk. The checker rejected the deliberately wrong output and the failure at the horizon. [Protocol and results](paired-migrations-31b07b0.md)

## Audit coverage

The owner waived rerunning the 44 cases retained by the earlier auditor. Their earlier result is historical. The current 31-case bundle is available in this checkout and remains part of the gate. The interim integration run at `9a984c6` passed 23 of those 31. Three refunds, the whole-stock retirement and four first-capacity writes through occurrence selections failed at that revision.
