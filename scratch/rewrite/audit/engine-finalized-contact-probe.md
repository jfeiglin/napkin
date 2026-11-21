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

## Reproduction

Set the four shell variables to the measured engine checkout, final engine checkout, frozen benchmark checkout and an empty output directory. Use the same Python environment for both engines. Each benchmark worker verifies its loaded engine path and Git SHA and uses single-threaded BLAS.

```sh
python scratch/rewrite/audit/port_contact_probe.py campaign --measured "$MEASURED" --final "$FINAL" --harness "$HARNESS" --out "$OUT" --probe
python scratch/rewrite/audit/port_contact_probe.py campaign --measured "$MEASURED" --final "$FINAL" --harness "$HARNESS" --out "$OUT" --guard-dispatch
python scratch/rewrite/audit/port_contact_probe.py campaign --measured "$MEASURED" --final "$FINAL" --harness "$HARNESS" --out "$OUT"
```
