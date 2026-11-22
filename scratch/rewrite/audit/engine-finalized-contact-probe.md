# Benchmark coverage of the final stock-contact correction

The full performance campaign used `fc9a9ed7fc9c6086f2ac38b27379f2cd14e71864`. The final production correction is `caecf1003c980821a235f264bd10c23d052734e1`. The only production file that differs is `napkin/engine/timeline/triggers.py`. The probe checked that the Python syntax trees agree after removing two methods, `Triggers.anchor` and `Triggers._continued_root`. They decide whether a watched comparison qualifies at a common time and which physical stocks supply the incoming continuation. [Production diff](https://github.com/jfeiglin/napkin/compare/fc9a9ed7fc9c6086f2ac38b27379f2cd14e71864...caecf1003c980821a235f264bd10c23d052734e1)

## Public readings and executed paths

The two engines ran the same five workload scripts from `0f0fcb2a933fdf71a0458a101a4377e1ccb0f44a`. The probe intercepted their public reads in a separate process and hashed the paths, times and returned values. Each digest below is identical on the two engines. Python's code-object-local monitoring counted method entries and executed source lines. The CSV retains full physical digests, engine revisions, source paths and SHA-256 hashes, exact arguments, probe hashes, and the SHA-256 of each original JSON receipt. [Probe source](port_contact_probe.py) · [Receipts](engine-finalized-contact-probe.csv)

| Workload | Arguments used for path checks | Physical readings | Digest prefix | Entries into `anchor` on either build | Entries into `_continued_root` on either build |
|---|---|---:|---|---:|---:|
| Component tanks | 12 tanks, 12 h | 36 | `87b85154f9d6` | 0 | 0 |
| Sparse tanks | 12 tanks, 12 h | 36 | `25d9ef780352` | 0 | 0 |
| Component finite-donor tanks | 12 tanks, 12 h, `--compartment` | 36 | `2a6633ed5e37` | 0 | 0 |
| Sparse finite-donor tanks | 12 tanks, 12 h, `--compartment` | 36 | `94fe1ae73369` | 0 | 0 |
| Independent held pipes | 300 places, full records | 12 | `69ca1663f356` | 0 | 0 |
| Held local network | 300 places, 350 routes, 48 h | 9 | `a25f98cc881c` | 0 | 0 |
| Moving local network | 300 places, 350 routes, 48 h | 9 | `eaa78f5eff03` | 0 | 0 |
| Event-heavy | 60 places, 48 h, 12 phases | 1 | `2283ba83bb8e` | 55 | 0 |
| Declared solver | 300 places, 350 routes, 150 sources | 612 | `9f9bd789c1c8` | 0 | 0 |

All nine final runs made zero qualified stock reads at `triggers.py:691` and zero continuation previews at `triggers.py:627`. The event workload also produced 965 starts and the analytical 84 L terminal stock. Each template uses a fixed input in its sole guard, `t >= this.phase`. Place count changes how many copies exist. The 12 quarter-hour phases and three-hour reset stay the same. Positive-phase sites cross once. Phase-zero sites already satisfy their guard when the run starts. Reset firings follow the period with the same guard still true. This gives 55 initial pure-clock crossings at 60 places and 27,500 at 30,000 places.

The tank and local-network models have no watched conditions. The held-pipe workload selects a rate from a time-keyed table and filters stock for its report. Its copied rows introduce no mixed stock-and-clock predicate. The solver changes supply at a scheduled 24 h stage. Its constraints and derived reports perform the same calculations as the population grows. This source inspection supplies the reason for extending the reduced path check to the full populations. [Frozen workload sources](https://github.com/jfeiglin/napkin/tree/0f0fcb2a933fdf71a0458a101a4377e1ccb0f44a/scratch/rewrite/b1)

The positive control fills a 1 L-scale stock at 2 L/h and watches a threshold that increases at 1 L/h. The final engine fires at 0.999999995 h, before the 1 h stage. The measured engine groups the fire at 1 h. A second control caps the stock at 2 L and observes the inclusive, in-band continuation at 1 h. Together they entered the final `anchor` five times and `_continued_root` once. They read the stock at its located time three times and previewed its continuation once. [Positive controls](port_contact_probe.py)

## Paired measurements after the production correction

The 1,200-place event benchmark used baseline `6202824` and final `caecf100`. All six measurements used the frozen worker, 48 h, 12 phases and single-threaded BLAS. They began after the final test suites finished. The only other benchmark running during this campaign was the earlier 30,000-place event guard. Each run produced 19,300 starts and an 84 L final stock.

| Pair | Order | Baseline run+record (s) | Final run+record (s) | Final / baseline | Baseline / final peak RSS (MiB) |
|---:|---|---:|---:|---:|---:|
| 1 | B/F | 240.920 | 241.404 | 1.002010 | 722.9 / 701.6 |
| 2 | F/B | 242.351 | 242.051 | 0.998763 | 691.6 / 698.5 |
| 3 | B/F | 241.967 | 241.373 | 0.997546 | 702.3 / 686.3 |

The median of the three paired ratios was **0.998763**, against a limit of 1.05. The frozen program SHA-256 is `6a5aacf6db89e2c87fa910f40ab346fd5a7d4f40e6cf07f93a94a79f0b2dde08`. The raw receipts are identified below.

```text
events.1.B.json 8f40c36d659a8e3163608a99420dc4a0162dcc7021b2891eb7fdbf7c8283adb4
events.1.F.json cf02e0cae969d1d5a4ccc846320952b0852fef13ba43342e738680f2a42fe7b9
events.2.B.json 26f0b3c64bc1802cc714d942c2ddadfdd195aa83901563e9245dd20e5f273682
events.2.F.json 49f0e84c66aea2fe3fa690c72133f04554a2be2703a445b466355f511b9df019
events.3.B.json bbe14b5d060b2cc41321b4e6f8b6a83587892f44224133566e342936d72f1c76
events.3.F.json 0844175e1aea6d0e677b3f39ece706a0eb6c46a551642d7de2398c7c0049d7a8
```

### Dispatching every predicate at full population

The probe built the frozen 30,000-place event model in a fresh process per timed sample on `fc9a9ed7` and `caecf100`. Each process called `anchor` on every actual predicate once cold, then once warm. The probe also checked that each predicate reads only the model clock. Each row includes 30,000 calls per pass. Model construction and the separate read-set assertions were outside both clocks.

| Pair | Order | Cold measured (s) | Cold final (s) | Warm measured (s) | Warm final (s) |
|---:|---|---:|---:|---:|---:|
| 1 | M/F | 0.1635 | 0.1557 | 0.1373 | 0.1302 |
| 2 | F/M | 0.1648 | 0.1591 | 0.1405 | 0.1317 |
| 3 | M/F | 0.1665 | 0.1651 | 0.1514 | 0.1359 |

The median paired change for a cold pass across the full population was -0.0057 seconds. The direct benchmark above measures end-to-end 1,200-place performance on the final engine. The 30,000-place end-to-end guard ran on `fc9a9ed7` in 7,522.483178 s against 7,498.460000 s on baseline, a ratio of 1.003204 within the 1.10 limit. Both recorded 482,500 starts and 84 L. The measured engine peaked at 8.835 GiB. The full-run JSON receipt SHA-256 is `a3e17fd70043fc4f12a70f0add9dc7f48d12c7465b5e70142fb1ffcb81820d3c`. The predicate timings describe the affected operation in isolation and are insufficient to give an exact total for `caecf100`.

### Reduced end-to-end comparisons

These short comparisons used the arguments in the public readings table and compared final `caecf100` with measured `fc9a9ed7`. Each pair used the same repeat count on both revisions. The two time columns are medians of run+record times per invocation, and the ratio is the median of the three within-pair ratios. These exploratory clocks complement the independent full-workload votes.

| Workload | Repeats per batch | Measured (s) | Final (s) | Final / measured |
|---|---:|---:|---:|---:|
| component-tanks | 2 | 1.1196 | 1.1208 | 1.001099 |
| sparse-tanks | 1 | 2.0588 | 2.0283 | 0.981005 |
| component-compartment-tanks | 24 | 0.0702 | 0.0701 | 0.999561 |
| sparse-compartment-tanks | 1 | 2.0160 | 2.0409 | 1.012357 |
| held-pipes | 8 | 0.1302 | 0.1329 | 1.018650 |
| held-network | 8 | 0.1040 | 0.1074 | 1.027014 |
| moving-network | 1 | 3.3235 | 3.3302 | 1.006889 |
| events | 1 | 10.3184 | 9.8377 | 0.969835 |
| declared | 3 | 0.3923 | 0.3956 | 1.004749 |

The CSV includes the three raw pairs for every reduced comparison and full predicate pass, including the UTC capture times and SHA-256 of each receipt. [Raw comparisons](engine-finalized-contact-probe.csv)

## Reproduction

Set the four shell variables to the measured engine checkout, final engine checkout, frozen benchmark checkout and an empty output directory. Use the same Python environment for both engines. Each benchmark worker verifies its loaded engine path and Git SHA and uses single-threaded BLAS.

```sh
python scratch/rewrite/audit/port_contact_probe.py campaign --measured "$MEASURED" --final "$FINAL" --harness "$HARNESS" --out "$OUT" --probe
python scratch/rewrite/audit/port_contact_probe.py campaign --measured "$MEASURED" --final "$FINAL" --harness "$HARNESS" --out "$OUT" --guard-dispatch
python scratch/rewrite/audit/port_contact_probe.py campaign --measured "$MEASURED" --final "$FINAL" --harness "$HARNESS" --out "$OUT"
```
