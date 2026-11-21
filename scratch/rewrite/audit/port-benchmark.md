# Measuring engine port readiness

The independent-pipes timing command runs the 30,000 rows, full recording, and the three analytical checks. Its `--full-record-only` switch omits the separate untimed simulation with two selected values. Invoking the original `bench.py 30000` still exercises both recordings.

Use one checkout for the benchmark scripts and a clean pinned worktree for each engine. `B` is the audited baseline, `A` is allocation only, `P` is the settlement prototype, and `F` is the final candidate. Run the benchmark on its own, with the same Python executable, power settings and machine throughout. Keep the output directory outside the engine package.

### Recreate the isolated settlement engines

Start a detached worktree at the published allocation commit `5d82538`. Cherry-pick the published commits below in order. Each step has the same stable patch ID as the isolated build actually measured. Compare `git rev-parse HEAD^{tree}` with the tree in the corresponding row. This recreates each intermediate engine using only the topic branch.

| Build | Published patch | Measured commit | Expected Git tree |
|---|---|---|---|
| P1 | `97d7ae5` | `b9834bf` | `1449334209df0238e7749e7186134b6bb9b8f9ad` |
| P2 | `31b07b0` | `d9e6e94` | `606b85531cf688883e93ed2b536f2faaaf5cfe70` |
| P3 | `51d14cd` | `ee8a22c` | `628c710ed73f50d80359f96062592872a0e2ad59` |
| P4 | `a65b6e1` | `a65f70d` | `bd3e014b407f430320bb5f8c4637032733f16182` |

For the 30,000-pipe recorder smoke, start at the published `a65b6e1` and apply the published `ee1e26a`. Its measured tree was `5104d5ee26185dfcfea5a9624d97b2d16eb179b2` at isolated commit `03c7b12`.

### Run the comparisons

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

Held and declared allocation work also has separate counters. `Family._start` chooses a rate for one held row. `Lines._solve` handles a general batch, and `Lines._downstream` propagates a batch in the acyclic local shortcut. `Former.problem` constructs a declared problem, including when the solver can reuse its previous answer. `DeclaredWay._solved` counts actual uncached solver invocations. The JSON reports each entry independently because one operation can call another.

The common driver passes `--no-phase-times` to the declared solver script on both revisions. Invoking that script directly still enables its three internal timers by default. Paired runs measure only the outer clocks. Diagnostic runs install only the counters described here.

### Physical stock materializations

`stock_materializations` reports calls to the production `Run.post_stock(store, t)` entry point and the number that actually advanced the store's accepted cursor. Their difference counts already-posted requests. Pure `Run.stock_balance` queries do not touch either counter. A revision that predates this stock writer reports `null` for the group. The `by_method` entries for accepted integral batches and leg amounts measure the methods' numerical work separately.

### Prototype counter evidence

The [fourth prototype counter samples](engine-finalized-counters.csv) include 21 executions of seven workloads on the baseline, allocation-only and fourth prototype builds. A mixed workload has a row per numerical method. Time, process peak RSS, checked-primitive count, maximum absolute amount discrepancy and the original JSON checksum describe the entire execution and repeat across its method rows. Blank primitive batch and leg counts denote an engine that predates the integral API. Timing gates use the separately measured uninstrumented runs.
