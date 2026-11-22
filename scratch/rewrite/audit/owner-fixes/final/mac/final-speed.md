# Final Mac speed table

Baseline `6202824d6d567c34ac46da7b018e66a9c28588b3`. Candidate `4b372a0a5c39fb7f1e2b9233599b0219f4d95bc7`. All four run-and-record measurements and the declared solver’s build-plus-plan-plus-run measurement passed the 1.05 limit.

Each timing cell gives baseline / candidate seconds. Pair 1 ran baseline first, pair 2 candidate first and pair 3 baseline first. Ratios were calculated from the full-precision samples before rounding. The reported median is the middle of the three candidate/baseline ratios.

| Measurement | Pair 1 (s) | Pair 2 (s) | Pair 3 (s) | Median ratio |
|---|---:|---:|---:|---:|
| Sparse tanks run and record | 1.890333 / 1.969989 | 1.901238 / 1.969667 | 1.907945 / 1.974762 | **1.035992** |
| Component tanks run and record | 1.099701 / 1.081354 | 1.104722 / 1.095021 | 1.109007 / 1.074546 | **0.983316** |
| Events run and record | 230.015056 / 223.334661 | 229.438897 / 223.089100 | 227.286352 / 222.495925 | **0.972325** |
| Declared solver run and record | 8.161493 / 6.581666 | 8.245879 / 6.604164 | 8.206208 / 6.559155 | **0.800905** |
| Declared solver total | 9.376375 / 7.798892 | 9.459093 / 7.811254 | 9.424026 / 7.772988 | **0.825793** |

## Calibrations and repeats

The tank pilots used one timed repetition on each revision. The campaign used their timings to select the repetitions per measured batch. Events and declared solver each used one repetition without a pilot.

| Workload | Calibration seconds, baseline / candidate | Repetitions per measured batch |
|---|---:|---:|
| Sparse tanks | 1.895454 / 1.969105 | 1 |
| Component tanks | 1.099358 / 1.088325 | 2 |
| Events | — | 1 |
| Declared solver | — | 1 |

Measured on macOS 15.1 arm64 with Python 3.13.16 and one thread for each configured math library. The campaign completed in 1464.8 seconds. Both the campaign and its summary exited 0.

The archive preserves all 24 measurement records, four calibration records, four schedules, the campaign lock, both stdout logs and both command receipts. The schedules identify the benchmark sources, driver and historical worker by SHA-256. [Raw benchmark files](final-speed-raw.zip)

Archive SHA-256 `e32c9df76d73c497db0f5f051bd2ff1791e9135db0347967ffa384064d5009cc`.
