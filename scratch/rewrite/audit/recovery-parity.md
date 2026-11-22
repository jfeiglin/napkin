# Historical recovery controls

The reference is commit `8488047dbb7eafee1f5582cf59839c6bea0cf8cd`. This audit checks equivalent recovery runs and controlled replays through the public model loader, simulation and reading APIs. Every selected simulation must complete its requested horizon. Historical inputs and observed outcomes determine which comparisons apply.

| Model | Reference observations | Acceptance rule |
| --- | --- | --- |
| Water | Six observations of eight recovery outputs in each of 16 utilities, using the archived `delayed_none` run with no retained access. | Absolute tolerance 1e-8, or 1e-5 for remaining work, or relative tolerance 1e-8. |
| Heat | Eleven end-of-horizon readings per control at 1,800 h. The current runs `early_cooling`, `standard`, `powered_places` and `delayed_cooling` map to the historical rows `early_obeys`, `standard_obeys`, `early_powered_places` and `delayed_human`, respectively. | Compare at the pinned publisher’s six significant figures, allowing its display of sub-millionth values as zero. The script also checks the portable fixture against the archived run table in Git. |
| IV fluid | Seven named runs and four input edits at 17 times over 1,440 h. The fixture includes physical quantities, lagged clinical outcomes, event counts and times, and zero-stock controls for omitted holds. | Absolute tolerance 1e-6 or relative tolerance 1e-8, with relative tolerance 1e-6 for event times. Event counts and zero-stock controls match exactly. For the three outcomes with a six-hour reporting window, the candidate identifies missing prehistory at hour zero. The original reported zero. |
| Defensive response leaf | Four observed workloads at ten times over 25 years, with attention, hardening, remediation and workload read at each time. | Absolute tolerance 1e-8 or relative tolerance 1e-7. This fixture is a replay of the historical defensive equations under supplied workloads. |

## Verification results

All 8,265 observations satisfied their acceptance rules.

| Model | Observations | Exact matches | Numerical differences within tolerance | Hour-zero reporting changes |
| --- | ---: | ---: | ---: | ---: |
| Water, 16 utility models | 768 | 521 | 247 | 0 |
| Heat, `1fd5a162` | 44 | 44 | 0 | 0 |
| IV fluid, `c61ccb66` | 7,253 | 7,214 | 6 | 33 |
| Defensive response leaf, `2b261178` | 200 | 171 | 29 | 0 |
| **Total** | **8,265** | **7,950** | **282** | **33** |

In water, the largest difference in cumulative person-days lost was approximately 0.000680 person-days at hour 720. Heat matched total economic loss and the other ten endpoints for all four policies at the archived publication precision. In IV fluid, the six numerical differences were at most 5.69e-14. Each of the eleven IV cases reported three clinical readings as unavailable at hour zero because their six-hour reporting window extends before the run. The largest difference in the defensive leaf was 5.09e-11 in the pulse case's attention index at 17,520 h.

The CSV retains each observed value and the full candidate model hash. The package column distinguishes IV physical observations, lagged reported outcomes, hold controls and event counts. In the heat rows, both numbers use the archived publication precision. [Row-level observations (compressed CSV)](recovery-control-comparisons.csv.gz) · [Comparison script](../a5/recovery_parity.py)

Run from the checkout with the project's dependencies and the pinned commit available in Git.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -B -m scratch.rewrite.a5.recovery_parity /tmp/recovery-control-comparisons.csv.gz
```

The `--package` option can be repeated to select `water`, `heat`, `iv` or `defensive`. The script exits unsuccessfully if a study stops, an archived heat value fails the pin check, or an observation exceeds the declared acceptance rules. Numerical differences within tolerance may vary with the numerical environment.

[Historical heat run table](https://github.com/jfeiglin/napkin/blob/8488047dbb7eafee1f5582cf59839c6bea0cf8cd/scenarios/heat_wave_blackout/results/runs.json) · [IV archive](../../../scenarios/iv_fluid_shortage/tests/legacy-recovery.json.gz) · [Defensive replay receipt](../../../scenarios/cyber_learning_loop/defensive_response/tests/legacy-readings.json) · [Water archive](../../../scenarios/water_controls_wipe/tests/recovery-readings.json)
