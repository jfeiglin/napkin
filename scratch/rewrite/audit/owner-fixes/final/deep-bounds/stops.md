# for the owner: stop near simultaneous bounds, fix or diagnostic?

The deep corpus contributed two additional stopped variants. Both reached the physical reversal, then the integrator restarted at the same time. The [original 300-seed report](../../s9/stops.md) retains its 146 stopped variants, their individual minimized models and diagnostic classifications. Neither case hit the declared solver’s evaluation limit.

| Seed | Variant | Reduced model | Original stop at `7eb6dae` | Corrected at `c9762e9` |
| ---: | --- | --- | ---: | --- |
| 437 | `component.event` | [437-minimized.scn](437-minimized.scn) | 1.6250000000000002 h | Reached 3.25 h and both terminal inventories met the analytic solution |
| 1553 | `component.plain` | [1553-minimized.scn](1553-minimized.scn) | 1.7500000000000002 h | Reached 3.5 h and both terminal inventories met the analytic solution |

The outgoing field drains the full stock after the reversal. The dense curve first protruded about 9.45 × 10⁻³³ L above the starting face, then fell a representable 1.25 × 10⁻⁸ L inward in the first numerical step. Treating that leading fluctuation as another upper-bound arrival stopped both runs with `Integration made no progress at a boundary`. Waiting for the first distinct stock coordinate preserved the later return clock in direct polynomial controls. The spelling with the opposite empty-event configuration passed for each seed before and after the correction. Both [original deep IDs](deep-failed-ids-verified.jsonl) passed on `c9762e9dd2f3854f8b814d21228b29ad8d8f5e96`.

[Original and minimized failures](models-red.jsonl) and [terminal readings against the analytic solution](models-green.jsonl) retain the source digest, method, time, and inventories of each run.

Both S9 owner families passed all [600 original case IDs](owner-cases-verified.jsonl.gz) in a clean detached checkout at the same revision, with matching generator digests.
