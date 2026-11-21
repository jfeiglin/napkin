# Accounting performance before stage integration

The first production accounting commit `ab955777663e087c56d388b1d606f2372a74c13c` ran the 100-place event workload at 1.0021 times the audited baseline `6202824d6d567c34ac46da7b018e66a9c28588b3`. Both held local networks exceeded 1.05 at development scale. All five workloads retained their expected observations. These development measurements shared the machine with other engineering work. The final gate uses alternating pairs on the completed stage candidate.

| Workload, 48 h | Baseline → accounting seconds, in paired order | Median paired ratio |
|---|---|---:|
| Events, 100 places / 12 phases | 19.0111 → 19.1076, 18.7818 → 18.8207, 19.1702 → 19.0638 | 1.002071 |
| Held network, 300 places / 350 routes | 0.1336 → 0.1607, 0.1377 → 0.1608, 0.1348 → 0.1588 | 1.177402 |
| Moving network, 300 / 350 | 3.4033 → 3.5698, 3.3656 → 3.4935, 3.4533 → 3.8463 | 1.048918 |
| Held network, 3,000 / 3,500 | 6.2818 → 6.9039, 6.9305 → 6.8556, 7.9336 → 8.4755 | 1.068298 |
| Moving network, 3,000 / 3,500 | 38.8513 → 39.7281, 35.0042 → 35.9625, 34.7570 → 33.5901 | 1.022566 |

Each event run completed 1,609 starts, with 84 L in the first place at hour 48. Every network pair agreed on first, middle and last stock at 0, 24 and 48 h within `rel_tol=1e-8` and `abs_tol=1e-6`. The [raw clock samples](accounting-preflight.csv) identify both revisions, the order of each pair and the original sample digests.

Two counters timed `Stocks.faces` and `Stocks.project` in separate held runs. At 300 places, face reconciliation used 9.30 ms across 160 calls and terminal history projection took 8.41 ms. Together they account for 17.71 ms of the approximately 24 ms difference. At 3,000 places, the corresponding costs were 134.84 ms across 1,603 calls and 89.27 ms for a single projection. A separate `cProfile` run at 300 places counted 761 `Stocks.stock_balance` queries, 1,862 `HeldAmounts.amount` queries, 2,833 rectangle calculations and 159 contact equation solves. Both endpoints can reuse one leg's amount at the common cutoff. Isolated faces also offer an opportunity to avoid assembling a coupled equation system when its only coefficient is known exactly.

## Reproduction

Use fresh processes from the same virtual environment, with `PYTHONPATH` set to each clean engine checkout and `NAPKIN_STORE=off`. Set `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, `NUMEXPR_NUM_THREADS` and `BLIS_NUM_THREADS` to 1. Use the scripts from `e2347a1` under `scratch/rewrite/b1`. Run each row in baseline/accounting, accounting/baseline and baseline/accounting order. The clock includes constructing `Run(plan)` and running it with recording. Model construction, planning, validation and reading follow separate clocks.

```sh
python "$HARNESS/s4a-engine/bench.py" 100 48 12
python "$HARNESS/s2-engine/bench.py" held 300 350 48
python "$HARNESS/s2-engine/bench.py" moving 300 350 48
python "$HARNESS/s2-engine/bench.py" held 3000 3500 48
python "$HARNESS/s2-engine/bench.py" moving 3000 3500 48
```
