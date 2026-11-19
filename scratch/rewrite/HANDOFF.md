# Handoff: migrate the catalogue (stage M), on a branch of its own

You take over the napkin language rewrite at gate G2. You may be a different tool or a different kind
of agent from the one that wrote this, so this file assumes nothing about your tools or your memory:
everything you need is in the repository, and this file says where. Read it all before you start.

## Where things stand

- The rewrite replaces napkin's language, compiler and engine in place. Stages S0 to S7 and C are
  done, gate G2 passed on branch `claude/blissful-heisenberg-5me2hn`, and the fixes of two audits
  after it (changes 19 to 22, below) are in: every central test passes with no catalogue
  (7,263 passed, 2 skipped for TeX and Ghostscript), every deep test passes (14,984), and ruff is
  clean on `napkin/`, `tests/` and `tools/`.
- What is left is the catalogue: the five model packages under `scenarios/` and `examples/` (all
  but `examples/piano_tuners`) are still in the old language, and so are their tests. That is your
  work, stage M, and it ends at gate G3. Stage F (docs, deleting `scratch/`) comes after, not now.

## How to work

1. Branch from the rewrite branch, and work only there:
   `git fetch origin claude/blissful-heisenberg-5me2hn && git checkout -b <your-branch> FETCH_HEAD`.
   Do not push to `claude/blissful-heisenberg-5me2hn` and do not merge into it.
2. Commit small and often, each commit with one subject; push your branch as you go.
3. When G3 holds (end of this file), open a pull request from your branch into
   `claude/blissful-heisenberg-5me2hn` (not into `main`), described as "Hand back for review"
   below, and stop: the owner has it reviewed before it merges.
4. The owner decides anything that changes what a model author writes or sees. When such a question
   comes up, ask the owner; do not decide it silently. Technical choices are yours: write each down
   (see "Hand back for review").

## Setup

The commands assume the checkout's root is the current folder, and Python 3.12 or later (`pyproject.toml`; the rewrite ran on 3.13).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.lock
.venv/bin/python -m pip install -q --no-deps -e .
git worktree add --detach ../napkin-base 8488047
export NAPKIN_BASE="$(cd ../napkin-base && pwd)"
```

- The worktree at commit `8488047` is the old compiler, which reads the old model files. It is
  outside the checkout. The migration scripts look for it at `/home/user/napkin-base` unless
  `NAPKIN_BASE` says where it is.
- The old and the new compiler are both the Python package `napkin`, so they never share a process.
  The scripts handle that: what reads an old model runs with `PYTHONPATH` set to the worktree; what
  reads a new one runs with the checkout's own package and no `PYTHONPATH`.
- `requirements.lock` holds `qdldl` since G2 (a sparse factorization the solver uses).

## Read, in this order

1. `scratch/rewrite/PLAN.md`: the progress list at the top (the last entries say what G2 left
   open), then "Changes after G0", items 1 to 22. These override the rest of the plan and the spec.
   The ones you will feel most: 10 (the owner's priorities: defensibility, then speed, then
   precision), 11 (reproducibility), 12 (no `delayed`), 13 (the publisher is ported in M), 15
   (breakpoints and checkpoints replace player machinery: `choose`, `sees`, controllers are gone),
   16 (the evidence rule), 18 (speedups), 19 to 22 (the owner's answers after two audits, below).
2. `scratch/rewrite/g0-decisions.md`: the owner's decisions. They win over everything else.
3. `scratch/rewrite/briefs/m.md`: the detailed brief of stage M: the scripts, the measured state of
   the translation, each package's needs, the tests each one unlocks, and the rule that no change is
   silent. It was written for a session that hands packages to helpers; where it says "the main
   session" or "a subagent", read "you". Where it and this file differ, this file wins.
4. The language of now: `scratch/rewrite/spec.md` as the changes after G0 amend it, the docstrings of
   `napkin/model/semantic.py`, `compile.py` and `support.py`, and the worked examples in
   `tests/language/`. `examples/piano_tuners` is a finished package in the new language: copy its
   shape.
5. As needed: `scratch/rewrite/b1/m-prep/STATE.md` (how the migration tools were made ready) and
   the other `scratch/rewrite/b1/*/STATE.md` files (what each part of the rewrite built and decided).

## Decided by the owner since G2 (`PLAN.md`, changes 19 and 20)

An audit after G2 raised five questions and a list of bugs. The owner answered, and the bugs are
fixed on the rewrite branch, each with its failing example as a test. What this means for you:

1. **A solver decides only what it names.** A connected flow that a solver does not name in
   `solve_for` keeps its endpoints' local sharing; the solver sees it only through the limits it
   imposes. A model whose provider must decide who is served names those rates.
2. **A `switch` case may be empty**, with or without a text: an old outcome that only carried a
   text keeps it as a case with no action.
3. **A member may have a `title`** ("DC Water"), shown by reports and playback. An event's `role` is
   refused by the model: it belongs to the scenario's wrapper (its UI or `brief.toml`).
4. **`timescales` is retired** and refused. For the heat-wave and cyber models, confirm that their
   results meet their accuracy without the hint (run them with and without a small `max_step` in
   the configuration, and compare); report it either way.
5. **Cycles are checked on the members' actual connections**, so the water model's
   `Utility.tie_asks` compiles; a real cycle is reported as its chain.
6. **Triggers on values that rise and fall between events are certified step by step** (change
   20), so the reservoir's `water >= level` runs: its spillway opens at 40 h.

The translator (`scratch/rewrite/a5/translate.py`) follows these decisions. It writes an old
`timescales` hint into the package's `notes:` as text, and the event roles into a `roles.toml`
beside the model's files (7 for the heat wave, 4 for the IV model, 4 for the water model): the old
publisher read them as the actor of each timeline card (`tools/publish/pages.py`, `Pages.cards`),
which the water UI shows, so read them from there when you port the publisher and the UI. Anything
else that changes what a model author writes or sees is still the owner's: ask.

## What the re-audit changed (`PLAN.md`, changes 21 and 22)

A second audit found that fixes had cured the cases named and left their causes. Each cause is now
fixed in one mechanism, with a test of its rule (`briefs/audit2.md`; the state files
`scratch/rewrite/b1/audit2-*/STATE.md`). What you will meet in the catalogue:

1. **A quantity is its dimension and an exact scale**, however it is spelled: `0.1 day` is `2.4 h`
   in a range, a bound, a membership test, a `sqrt` or a power; a reversed interval in a test is an
   error. Durations add exactly, so `0.1 h` three times is `0.3 h`, and a horizon in days is the
   same time in hours. A units file's scale is read as the number that its float stands for with
   the fewest digits: the library's units per day (1/24, written as 0.041666666666666664) and per
   year (1/8760) are their ratios, a decimal such as 3785411.784 is itself
   (`napkin/core/units.py`, `scale_of`).
2. **A value that cites a datum equals it**, in dimension and scale, read exactly: a datum states a
   number and a unit and no precision. A difference is a `datum` warning with both numbers, and the
   evidence stage of `tools.check` refuses it as it refuses a value without a record. The old
   compiler refused such a model outright, so a `datum` warning in a translation most likely means
   a number or a unit changed on the way.
3. **A value has a lifetime.** An occurrence reference is a local of its type, set once, whose
   fields read its occurrence; a formula may read only what lives as long as it does (`lifetime`):
   copy an invocation's local into a field instead of capturing it.
4. **An endpoint's rule ranks all its flows, whether or not a solver names them.** Where a flow
   that the solver does not name reaches a ring of empty stores, local sharing cannot rank it and
   the run stops by name; the message says to name those flows in `solve_for`. No answer is
   published worse on any rank than the solver's own.
5. **A record gives only what it holds**: anything else is `unavailable`, with the reason, never 0
   or a guess. A reporting lag whose window reaches before 0 h is `unavailable` there (change 22),
   where the old engine gave 0: `iv_fluid_shortage` lags `deaths` and `serious_survivors` by
   `harm_delay` (6 h), so its check will find them `unavailable` at 0 h, where the old report has 0.
   List that in its `changed.md`, with change 22 as the cause. A lag of a yes/no or a text is
   refused by name, and a history budget that a run would exceed stops it by name.
6. **The checker compares how each run ended** before its values (below, "No change is silent").

## The work, in order

For each package, in this order (the brief `m.md`, "The order, and what each package needs", has the
details and the known hand work of each):

1. `examples/reservoir` first, then the migration guide (a short page for model authors, from
   `scratch/rewrite/a5/migration-table.md`, corrected by the rules of today).
2. `scenarios/iv_fluid_shortage`, `scenarios/heat_wave_blackout` (with its notebook
   `explore.ipynb`), `scenarios/cyber_learning_loop` (3,200 lines: work in sections) and
   `scenarios/water_controls_wipe` with its 16 variants. Its UI (`ui/server.py`, `ui/view.py`)
   becomes a client of the engine's checkpoints, as `napkin play` is (`napkin/session.py`).
3. The publisher (`tools/publish/`, change 13), once every package compiles and runs.

For each package:

1. Translate with the old compiler:
   `PYTHONPATH=$NAPKIN_BASE .venv/bin/python scratch/rewrite/a5/translate.py --compile <path>`.
   It writes into `scratch/rewrite/a5/translated/now/`, never over a model. Copy the result over the
   package's files, then finish the lines it leaves for a person.
2. Check the meaning, under the new compiler and with no `PYTHONPATH`:
   `.venv/bin/python scratch/rewrite/a5/check.py <old entry> <new entry>`. It compares numbers with
   units, texts, the kind of each name, flows, and the old cumulative outputs against the new
   never-falls proof, and it **runs both models** (its group `run`): the old one under the old
   engine, the new one under the new engine in `median` mode, to the horizon, comparing each old
   output with the new value of its name at 0 h, at the horizon and at each `--at` time, within
   1e-6 of the larger and a floor of 1e-8 in its unit. A difference fails unless the package's
   `changed.md` lists it (below). Repeat until it passes; declare a rename with `--rename A=B`.
3. Compile and run it: `.venv/bin/napkin compile <package>` (it lists every value without a record)
   and `.venv/bin/napkin run <package>`.
4. Port its tests, with `oracle-inputs.json`, `expected-orders.json`, its evidence index,
   `style.toml` and spread files. Take each file you port off `tests/dormant.txt` (you edit that
   file on your branch).
5. Add one behaviour test for each headline quantity, which shows what kind of quantity it is. For
   the water model: when service returns, the unserved rate is zero and the unserved volume keeps its
   value.
6. `.venv/bin/python -B -m tools.check --scenario <id> --skip-summaries`, and nothing wider. Its
   evidence stage refuses a package that has a value without a record (change 16): every input,
   stored value, timed event, status case, assert and member's own value cites a record.

Then the publisher, and last, once: `.venv/bin/python -B -m tools.publish --write` for all, which
remakes the 110 committed outputs (`results/brief.md`, `methods.md`, `runs.csv`, `runs.json` and two
review files of each scenario and variant); read every changed brief.

## No change is silent

Parity with the old numbers is not required, but every change is traced.

- A test that fails after the migration is traced to its cause. A translation error is fixed in the
  translation. A change that follows from the new semantics goes on the owner's list.
- **No expected value is edited to make a test pass.**
- Keep the owner's list in `scratch/rewrite/b1/m-<package>/changed.md`, one row for each changed
  number, as a table `| test | quantity | old | new | cause | evidence |`: the test is
  `check run ENTRY[:RUN]` for a difference that the checker's run finds, the quantity
  `OUTPUT at T h`, the cause the rule of the spec or the change after G0, and the evidence the
  trace or the check's line. The checker fails on an unlisted difference, on numbers that do not
  match, on a stale row and on an empty cause or evidence.
- The run step compares first how each run ended: `finished at T h`, `failed at T h: WHY` or
  `paused at T h: WHY`. A new failure or pause, or one at another time or for another reason,
  fails the step even when every value agrees, unless a row lists it with `outcome` as its
  quantity and the run's outcome, its reason in full, as its new cell:
  `| check run ENTRY | outcome | finished at 8760 h | failed at 8760 h: WHY | cause | evidence |`.
  The docstring of `scratch/rewrite/a5/check.py` has the whole format. Run `napkin run` on the
  package as well: it exits 1 on a run that failed.
- If you find a bug in `napkin/`, fix it only if the fix is small and plainly a bug, with a test that
  failed before it; otherwise write it down with a failing example. Do not change the language, the
  engine's rules or a tolerance to make a model fit: that is the owner's.
- Add no dependency without asking the owner.

## Tests and how to run them

- While you work, the files in hand, with the run store off:
  `NAPKIN_STORE=off .venv/bin/python -m pytest -q -p no:cacheprovider <paths>`.
- `tests/dormant.txt` lists the files that a session skips (`conftest.py` reads it). A path that the
  command line names runs all the same. Today it holds exactly the tests that read the catalogue:
  `scenarios/`, `tests/draw/test_catalogue.py`, `tests/publish/`, `tests/evidence/test_catalogue.py`,
  `tests/evidence/test_scientific_spec.py`, `tests/release/`,
  `tests/engine/test_distributions_deep.py`, `tests/test_examples.py`,
  `tests/test_scenario_ownership.py`, `tests/test_scenario_scope.py`,
  `tests/test_tools_new_catalogue.py`. (`m.md` lists a few more that were done since.)
- The central suite, as at G2: `NAPKIN_STORE=off .venv/bin/python -m pytest -n 4 --no-focused
  --scenario-selection '' -m 'not deep' -p no:cacheprovider -q tests`. Run it before each push of a
  finished package; it must stay green.
- Tests that start a fresh process to resume a checkpoint refuse "a checkpoint made by another version
  of the engine" when engine code changes during the run. Rerun them alone.
- A new test takes its expected values from closed forms, from the spec, or by hand, never from a run
  of the code under test. A test that takes more than about 10 s gets `@pytest.mark.deep`. Three
  existing tests take 12 to 13 s without the mark (`tests/engine/test_timeline_long_steps.py`, two;
  `tests/engine/test_estimators.py`, one): mark them.
- Ruff on what you change: `.venv/bin/ruff check FILES` and `.venv/bin/ruff format FILES`.
  `scratch/` is not linted.

## Additional tests

Beyond the ports and the behaviour tests above, the owner may ask for more; take them from the owner.
Candidates that the rewrite left open (see the end of the progress list in `PLAN.md`): a near-tie
for a split of who is served decided between moments, inside the integration (not marked today);
the oracle's coverage of `where` over an endpoint's flows (it does not run them); acceptance tests
from source for each package's headline numbers. A run that re-integrates after a new trigger moment costs time (a 10,000 h test went from
3.1 s to 5.9 s): watch the catalogue's run times, and report a model that becomes slow.

## Gate G3: done when

- `.venv/bin/python -B -m tools.check --all` passes.
- `tests/dormant.txt` is empty, and then the mechanism goes: the file, its reading in `conftest.py`
  and `tests/selection.py` (`dormant`).
- `.venv/bin/napkin fmt --check $(git ls-files '*.scn')` passes: every model is in its formatted form.
- Each package's `changed.md` is complete.

## Hand back for review

Open the pull request into `claude/blissful-heisenberg-5me2hn`, and do not merge it. Its description:

1. For each package: what was translated by hand and why, and the result of `check.py`.
2. How each decision of changes 19 to 22 applied to the packages, and the heat-wave and cyber
   models' accuracy without `timescales`.
3. The changed numbers: a link to each `changed.md`, and the five largest changes in a table.
4. Every decision you made that the owner did not, one line each.
5. Every bug found in `napkin/`: fixed (with its test) or written down (with its failing example).
6. The commands of G3 and their results, with counts.
7. What is not done.

## Do not

- Delete `scratch/` (that is stage F, after the review), or rewrite `docs/` beyond the migration guide.
- Push to or merge into `claude/blissful-heisenberg-5me2hn`, or open a pull request into `main`.
- Edit an expected value to pass, change a tolerance, or change the language to fit a model.
- Run `tools.publish --write` before every package is migrated, or more than once at the end.
