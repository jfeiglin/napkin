# Brief: verify the merged branch on macOS

Check out `claude/blissful-heisenberg-5me2hn` at the commit that adds this file. It is
`34bf6d5` plus this file only. Verify it on macOS and report back. Do not change any code or
test. If a check fails, stop there and report it (below). The owner decides what happens next.

## What is on the branch

- The engine rewrite and the scenario ports, up to `6f4134a`.
- The Linux review's fixes, up to `8eeffba`: five decisions that read the last places of a
  stock's ledger, `stocks.LEDGER_PROBE` and its corpus transformation `roundoff`, `napkin draw`
  on every model, and readings at six significant figures.
- Two engine fixes from this round, both new to macOS:
  - **The capacity check** (`18a4e7e`). `Stocks._over_capacity` reads a moving capacity on the
    branches its segment ran on (`Way.held_value`), and the halving search
    (`transfers._bisected`) is gone.
  - **The solver guard** (`ae7344c`). `ranked.exact` re-solves before a pin when the answer
    misses a row by more than 10⁻¹⁰ in working units, as the ranks after it measure.
- Two tests that now assert their invariant, not a roundoff sign (`7de8b95`).
- The four packages' new models and results, the named-comparison publisher, and the
  dormant list removed. These were merged from `codex/restore-attack-models-and-retire-dormant-list`
  at `0cc0433` (merge `34bf6d5`). The tests that were dormant now run with the rest.

The owner audits the scenarios separately. This brief checks only that everything runs and
agrees.

Linux runs the same checks in a cloud container at the same time. Don't run Docker for Linux.

## Setup

```bash
git fetch origin claude/blissful-heisenberg-5me2hn
git checkout claude/blissful-heisenberg-5me2hn
git log --oneline -2
.venv/bin/python -m pip install -q -r requirements.lock
.venv/bin/python -m pip install -q --no-deps -e .
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
```

`git log` must show this brief's commit on top of `34bf6d5`.

## 1. The whole check, in one command

```bash
.venv/bin/python -B -m tools.check --all --deep
```

This one command runs, in order:
1. lint;
2. every test, regular and deep (`tests/`, `scenarios/`, `examples/`);
3. the evidence check of every package;
4. the stored-run replays;
5. the publication check (`tools.publish --check`): every brief, readings page, source dossier
   and the source manifest, rendered fresh and compared byte for byte with the committed files.

It stops at the first failure. Don't run the stages again separately; this covers them all.
Expect it to take one to two hours.

## 2. What needs a screen

- **The water dashboard.** It needs Node.js 20 or later.

  ```bash
  .venv/bin/python -B -m scenarios.water_controls_wipe.ui setup
  ```

  ```bash
  .venv/bin/python -B -m scenarios.water_controls_wipe.ui serve
  ```

  Open http://localhost:8765/. Pick two or three places and each named run. The chart, the
  playback and **Read** at a fractional hour should show values with no errors in the page or
  the terminal.
- **The heat notebook.** Open `scenarios/heat_wave_blackout/explore.ipynb` in Jupyter and run all
  cells. Every cell should finish without an error.

## Report back

- The commit you tested (`git log --oneline -1`).
- For step 1: each stage's result line and the total time. On a failure, give:
  - the stage;
  - the test id or the file that differs;
  - the full error, or the diff lines the publication check prints;
  - whether it fails again when you run only that test
    (`.venv/bin/python -B -m pytest --no-focused -q -m 'deep or not deep' '<test id>'`).
- For step 2: what you opened, and any error, with a screenshot if a page looks wrong.
