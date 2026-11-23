# How the engine is verified

A test of the engine compares the engine with something that does not depend on it: an exact
interpreter, a closed form, exact fractions, or the same run in another spelling. Agreement of two
builds of the engine is no proof of the mathematics. This page tells which checks exist, how to run
them, and how to measure the speed of the engine. The engine terms (ledger, crossing tolerance) are defined in
[README.md](README.md#engine-terms).

## The reference interpreter

`tests/reference/` holds the reference interpreter: a small, slow and exact interpreter of the rules of
the language. It shares no code with the evaluation of napkin. Where it cannot run a model exactly, it
raises `errors.NotCovered` with the reason, and never guesses an answer.

| Module | What it does |
| --- | --- |
| `model.py` | The description of a model as plain data. Numbers are exact fractions in one canonical unit for each dimension. |
| `from_program.py` | Reads a program of `napkin.program` as data and makes the interpreter's model. It calls no evaluation code of napkin. |
| `run.py` | Runs a model from moment to moment: the rounds, the re-share, the delays and the conditions, as the engine does. |
| `evaluate.py` | Evaluates an expression: at an instant, from a recorded frame, as symbols for a solve, or as a polynomial in time for the search of the next moment. |
| `network.py` | The rates and the solver results of one instant, by local sharing or by a declared solver. |
| `order.py` | The selection order on one small problem, by brute force. The linear ranks use `linprog`, and the interpreter turns their optima back into exact fractions. The least distance is calculated in fractions. |
| `exact.py`, `poly.py` | Exact linear algebra on fractions, and polynomials in time with exact coefficients. |
| `stocks.py` | Finds the stocks that a declared move or flow can reach before its first transfer. |

A test reads the interpreter through `from_program.run_of(program, configuration, stops)`, which runs it
and stops at each breakpoint in turn, and `value_at(run, program, key, t)`, which reads a value in its
declared unit. The interpreter has its own tests in `tests/reference/test_*.py`.

## The generated corpus

`tests/engine/test_port_invariance.py` checks the engine on generated models. Each seed makes a small
exact model (`tests/engine/port_cases.py`), which the test writes both as model text and through the
Python builder. A transformation changes the spelling or the execution of the model, and the readings
must not change. The test compares each transformed run with the reference interpreter and with the
original run.

| Tier | Test | Cases |
| --- | --- | --- |
| Regular | `test_port_transform` | 300 seeds. Seed `s` runs the transformation `TRANSFORMS[s % 44]`, so each seed has one transformation. |
| Deep | `test_all_port_transforms` | Every transformation on each of 2,000 seeds: 88,000 pairs of a seed and a transformation. |

The nine first transformations:

| Transformation | What it changes |
| --- | --- |
| `empty_event` | Adds an event that does nothing. |
| `named` | Writes a part of a request as a named formula in place of inline. |
| `small_unit` | Writes volumes in mL in place of L, with the same physical values. |
| `split` | Splits a `move` into two statements in one stage. |
| `builder` | Builds the program through the Python builder in place of model text. |
| `artifact` | Saves the compiled artifact and loads it again. |
| `checkpoint` | Stops at a breakpoint, saves the checkpoint as text, and resumes it. |
| `sparse` | Runs the moving set on Sparse in place of Component. |
| `roundoff` | Moves each ledger read of a decision two places each way (next section). |

The other 35 transformations each check one decision of the engine. Each family has the commit that
first recorded its failures, before the fix ([owners.md](owners.md#audit-repairs) names the owners):

| Families | Decision | Baseline |
| --- | --- | --- |
| `stage_scalar`, `stage_selection`, `stage_ordering` | S1: the definition that a statement sees. | `e449649` |
| `comparison_gap`, `comparison_range` | S2: the comparison band and the exact gap. | `caa796d` |
| `authored_units`, `authored_cells`, `authored_cli` | S6: authored numbers are exact. | `bf35dc2` |
| `switch_component`, `switch_sparse`, `switch_declared`, `switch_selection` | S3: the side of a switch by its band. | `a247a0f` |
| `stock_inventory`, `stock_capacity`, `stock_edit` | S4: the exact stock ledger. | `6222254` |
| `reversible_bounds`, `simultaneous_bounds` | S9: bounds inside a step. | `67e011b` |
| `cross_rate` | P1: a rate that reads the rate of another set. | `8106ca2` |
| `collection_scope`, `collection_kind`, `filter_history`, `authoring_parity` | S5: scopes, collections and the two authoring forms. | `222ee15` |
| `solver_scale`, `solver_flow_scale` | S7: the scales of a declared solver. | `0018df2` |
| `record_history`, `record_identity`, `record_numerics` | S8: a reader of a record. | `97a42db` |
| `proof_network`, `proof_solver`, `proof_arguments`, `proof_reach` | S10: the proofs and the evidence trail. | `14215ec` |
| `lag_monotonicity` | P4: the proof that a lagged value never falls. | `2a84c5f` |
| `lag_bends` | P6: a short bend in a recorded formula. | `4a5c4a2` |
| `path_selection` | P7: the order of the selected paths of a report. | `481fab1` |
| `study_request` | P5: the recording request of a study. | `f28abb4` |

**How the corpus compares two runs.** `T` is `atol_factor × scale + rtol × |reference|`:

- Each moment time must agree within the crossing tolerance.
- A point value must agree within 2 T. A value that a level or an integral gives must agree within 10 T.
- The stages, the firings and their order must agree exactly.
- A decision can differ only where the trace records a near-tie at it. The comparison then checks the
  moves of the stages before it at that time, and ends there.

## The roundoff probe

The ledger of a stock and the trajectory of its method agree to a few units in the last place. The
direction of that difference depends on the platform's arithmetic (the OpenBLAS kernel, Linux or
macOS). So no decision may change with those last places.

`stocks.LEDGER_PROBE` (`napkin/engine/timeline/stocks.py`) is zero in every real run. A test sets it to
`-2` or `2`. Then each ledger read that a decision makes, and each start of a new trajectory, moves
that many units in the last place (`stocks.probed`). Each case must still give its specified answer.

- `tests/engine/test_ledger_roundoff.py` runs six cases, each with `-2` and `2`. Each case once gave a
  different answer on Linux than on macOS.
- The corpus transformation `roundoff` applies the same probe, with `-2` and `2`, to the generated
  models.

## Other exact checks

| Test | What it compares |
| --- | --- |
| `tests/engine/solve/test_spec_answers.py` | Every solver answer that the language specification works out, against the selection order of the solve library. |
| `tests/engine/solve/test_random.py` | Seeded random problems against exact references: a rational simplex, brute-force fair sharing and the enumeration of active sets. |
| `tests/engine/test_random_solvers.py` | Small random programs with a declared solver, against the reference interpreter. |
| `tests/engine/test_solver_adapters.py` | Each solver adapter (`napkin/engine/solvers.py`) against closed forms. |
| `tests/engine/test_roundoff_properties.py` | Roundoff at the bounds of stocks under local sharing, against exact fractions and conservation. |
| `tests/engine/test_highs.py` | The fast path to HiGHS (`napkin/engine/continuous/highs.py`) against `linprog`, bit for bit. |

## Test tiers

The tests have two tiers. `pyproject.toml` gives pytest the option `-m 'not deep'`, so a plain run is
the regular tier.

| Tier | Command | What it runs |
| --- | --- | --- |
| Regular | `.venv/bin/python -m pytest -m 'not deep'` | Every test that has no `deep` mark. The corpus runs 300 seeds. |
| Deep | `.venv/bin/python -m pytest -m deep` | Only the tests with the `deep` mark: detailed or slow checks. The corpus runs 88,000 pairs. |

To check a change:

1. Run the tests that check the change: `python -B -m tools.check --tests PATH`. Give one
   `--tests PATH` for each test file or folder.
2. To run the matching deep tests too, add `--deep`.
3. For the complete check, run `python -B -m tools.check --all`. With `--all --deep`, the check also
   runs every deep test and runs three stored runs again, which it compares with the run store, bit
   for bit.

The deep tier is slow. Run it by hand, never in the automatic check.

## Speed benchmarks

Two tools measure speed. The paired benchmark has a gate in its summary. The benchmark of models
asserts no time: a reader of its document judges it. The measured results are in
[the measurements page](../design/measurements.md).

### The paired engine benchmark

`tools/bench/port_benchmark.py` compares the speed of two engines on fixed workloads. The workloads are
scripts in `tools/bench/port/`. Each script checks its own physical results, so a fast wrong engine
fails.

| Row | Script | What it runs | Final arguments |
| --- | --- | --- | --- |
| `component-tanks`, `sparse-tanks` | `s1-engine/bench_moving_tanks.py` | 12 independent filling tanks on one method | `--tanks 12 --hours 12 --method component` (or `sparse`) |
| `component-compartment-tanks`, `sparse-compartment-tanks` | `s1-engine/bench_moving_tanks.py` | The same 12 fills as positive linear compartments | the same with `--compartment` |
| `held-network`, `moving-network` | `s2-engine/bench.py` | A network of places and routes, held or moving | `held 30000 35000 48`, `moving 30000 35000 48` |
| `events` | `s4a-engine/bench.py` | Places whose clocks start events that own a flow | `1200 48 12` |
| `held-pipes` | `s1-engine/bench.py` | Independent held pipes that read a keyed factor | `1200 --full-record-only` |
| `declared` | `s5-engine/bench.py` | A network with one declared solver | `3000 3500 1500 --no-phase-times` |

The phase `final` runs all nine rows. The phase `guard` runs `events` with 30,000 places and
`held-pipes` with 30,000 rows, once on each engine. The phase `prototype` runs the first seven rows on
smaller networks (3,000 places) and compares the baseline `B` with the builds `A` and `P` of the
earlier accounting work.

**The rules:**

- Use one checkout for the benchmark scripts, and a clean worktree at a fixed commit for each engine.
  The script refuses an engine whose `napkin/` folder has changes.
- The baseline `B` is commit `6202824`. The candidate is `F`.
- Use the same Python, the same power settings and the same machine for all samples. Run nothing
  else that loads the machine at the same time.
- Keep the output folder outside the engine package.
- The script runs each sample in a fresh process with one thread for BLAS and the run store off.
- Each row has three paired timings in alternating order: B/F, F/B, B/F.
- For the tank rows and `held-pipes`, a calibration run on each engine sets one repeat count, so
  that each batch lasts at least 1.5 s on either engine. A batch shorter than 1 s makes the result
  invalid.
- A sample that runs longer than 2 h 55 min stops, and the script records it as incomplete.
- The gate is the median of the three paired ratios of the run-plus-record time, F/B. Its limit is
  1.05 for each row. The `events` guard has the limit 1.10. The `declared` row also checks the time of
  the build, the plan and the run together.
- Each pair must give the same sampled results on both engines.

**To compare a candidate with the baseline,** give these commands from the root of the benchmark
checkout, with the same Python for all of them:

1. Make a clean worktree of the baseline: `git worktree add ../napkin-baseline 6202824`.
2. Make a clean worktree of the candidate at its commit.
3. Run the timings:

   ```sh
   python tools/bench/port_benchmark.py campaign --phase final --out RESULTS \
       --revision B=../napkin-baseline --revision F=../napkin-candidate
   ```

4. Run the counters with the same command and `--mode diagnostics`.
5. Print the gate: `python tools/bench/port_benchmark.py summary --phase final --out RESULTS`.
   The exit status is 1 when a row fails.

Give `--rows component-tanks sparse-tanks` to limit a command to some rows. To continue after an
interruption, give the same command again: it keeps each completed sample. Give
`--worker-script PATH` to run every sample with one frozen copy of the script. Use a new output folder
for each campaign, because the script refuses a schedule or a script that changed.

**The guards.** `--phase guard --rows events` and `--phase guard --rows held-pipes` take one timing on
each engine. The full 30,000-pipe baseline at `6202824` did not finish its first run in 12,653 s, so
it has no ratio. For that row, give the cutoff to the summary:

```sh
python tools/bench/port_benchmark.py campaign --phase guard --rows held-pipes \
    --out RESULTS --revision F=../napkin-candidate
python tools/bench/port_benchmark.py summary --phase guard --rows held-pipes \
    --out RESULTS --held-baseline-cutoff-seconds 12653
```

The summary then exits 2 and labels the 1.05 gate of that row as not verified. For the `events`
guard, `--baseline-guard-run-seconds 7498.460` gives the earlier baseline time of `Run.run` in place of
a new baseline sample.

**The counters.** A diagnostic run counts `Allocation.allocated`, `Instant.values`, `Instant.settle`,
the accepted and the rejected Radau steps, the posts of stocks (`Run.post_stock`), the held and
declared allocation work, and the amounts of the legs. Timing samples have no counters.

### The benchmark of models

`python -m tools.bench` (`tools/bench/measure.py`) measures the compiler and the engine on models:

- the models of the catalogue, with `--scenario ID`;
- the examples, with `--example`;
- synthetic families made as text, with `--family NAME`, at each number of members in `--sizes`.

Three fresh processes measure each model: the cold compile, the time to the first result, and the warm
runs with their report. The warm process also shows where the time goes, by role (`analysis`,
`expressions`, `field`, `solver`, `linear_algebra`, `scheduler`, `reporting`), under cProfile. With
`--samples N` it measures a Monte Carlo study, and with `--survey` one run of each named run.

`--out FILE` writes one JSON document with the commit, the machine and the settings. Each process runs
with the run store off. A measurement that fails is a record in the document, and the harness
continues. Run `python -m tools.bench --help` for every option.
