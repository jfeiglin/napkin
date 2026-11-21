# Measuring engine port readiness

Use one checkout for the benchmark scripts and a clean pinned worktree for each engine. `B` is the audited baseline, `A` is allocation only, `P` is the settlement prototype, and `F` is the final candidate. Run the benchmark on its own, with the same Python executable, power settings and machine throughout. Keep the output directory outside the engine package.

```sh
python scratch/rewrite/audit/port_benchmark.py campaign --phase prototype --out RESULTS \
    --revision B=BASELINE --revision A=ALLOCATION --revision P=PROTOTYPE
python scratch/rewrite/audit/port_benchmark.py campaign --phase prototype --mode diagnostics --out RESULTS \
    --revision B=BASELINE --revision A=ALLOCATION --revision P=PROTOTYPE
python scratch/rewrite/audit/port_benchmark.py summary --phase prototype --out RESULTS
```

Use `--phase final --revision B=BASELINE --revision F=FINAL` for final timings and diagnostics. The full event guard uses `--phase guard`, measures each revision once, and has no second diagnostic run. `--rows component-tanks sparse-tanks` limits an invocation to those rows. Invoke the same command to resume after interruption. Each completed child writes its own sample, with its engine location and SHA, harness checksum, raw output, clock, numeric results, process peak RSS in bytes and thread settings. Separate output directories preserve earlier prototypes.

The audited baseline's earlier full event execution recorded `Run.run` separately. Its 7,498.460 seconds cover the same method call as the fresh candidate's `guard_run_only_seconds`. Reuse that single execution with `campaign --phase guard --revision F=FINAL --out RESULTS` and `summary --phase guard --out RESULTS --baseline-guard-run-seconds 7498.460`. Retain the baseline's separate observed peak of 8.840 GiB and its 482,500 starts and 84 L horizon stock alongside the candidate JSON. Both runs check the horizon observation. The historical outer clock included another planning pass.

Each ordinary row has three paired timings in alternating revision order. Tanks use identical fresh-run batch sizes across revisions, calibrated on the baseline to about 1.5 seconds. The gate compares the median *paired* ratio of run-plus-record time for each row to 1.05. The declared-solver report also enforces its historical build-plus-plan-plus-run gate. The event guard permits 1.10. Each network checks its three sampled levels across revisions. The common event script uses its prepared plan once and checks the expected starts and final inventory. Historical event logs with other clock boundaries must be identified separately.

A separate single-run diagnostic counts `Allocation.allocated`, `Instant.values`, `Instant.settle`, successful Radau steps, and rejected Radau trials. A different proposed step size starts a new trial. A Newton retry at the same step size belongs to the same trial. Timing samples have no counter wrappers. The physical-amount diagnostic counts accepted integral batches and directed leg amounts on engines exposing `MovingAmounts.accept`. A method without that API has no primitive count. The test queries each tank fill, or three network use flows, against its dedicated receiving stock at the horizon. Stages, cuts and rejected intervals are additionally checked in the prototype's small exact-transfer tests.
