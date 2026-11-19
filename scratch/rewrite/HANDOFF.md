# Handoff: migrate the catalogue (stage M), on a branch of its own

You take over the napkin language rewrite at gate G2. You may be a different tool or a different kind
of agent from the one that wrote this, so this file assumes nothing about your tools or your memory:
everything you need is in the repository, and this file says where. Read it all before you start.

## Where things stand

- The rewrite replaces napkin's language, compiler and engine in place. Stages S0 to S7 and C are
  done, and gate G2 passed on branch `claude/blissful-heisenberg-5me2hn` (commit `baeaaed` and
  later): every central test passes with no catalogue (5,979 passed, 2 skipped for TeX and
  Ghostscript), ruff is clean on `napkin/`, `tests/` and `tools/`.
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
   open), then "Changes after G0", items 1 to 18. These override the rest of the plan and the spec.
   The ones you will feel most: 10 (the owner's priorities: defensibility, then speed, then
   precision), 11 (reproducibility), 12 (no `delayed`), 13 (the publisher is ported in M), 15
   (breakpoints and checkpoints replace player machinery: `choose`, `sees`, controllers are gone),
   16 (the evidence rule), 18 (speedups).
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

## Ask the owner first

These came up while the migration was made ready; each changes what an author writes, so they are
the owner's. Ask before you translate the lines they touch.

1. **An empty case.** 21 old outcomes do nothing but carry a text (the reservoir's `WAIT`, the water
   model's `SKIPPED` and `STOPPED`). A `switch` case needs an action today. Allow a case with only its
   text, or drop the texts?
2. **`title` and `role`.** A member written by hand has no `title` (69 in the water variants) and an
   event has no `role` (10). The translator keeps titles in `notes:` and roles as comments. Bring
   them back as fields, or keep them there?
3. **`timescales` that name values** (two packages): the language takes times only.
4. **A cycle in the water model.** `Utility.tie_asks` reads `Tie.ask`, which reads the buyer's need,
   which reads `tie_asks`. Member by member there is no cycle, but the front end checks the
   template. Is that check too strict (a front-end fix), or should the model be restructured?

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
   never-falls proof. Repeat until it passes; declare a rename with `--rename A=B`.
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
  number: the test, the quantity, the old number, the new number, the cause (the rule of the spec or
  the change after G0), and the evidence (the trace or the check's line).
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
the oracle's coverage of `where` over an endpoint's flows (it does not run them); a check of a value
against the datum that its record cites; acceptance tests from source for each package's headline
numbers.

## Gate G3: done when

- `.venv/bin/python -B -m tools.check --all` passes.
- `tests/dormant.txt` is empty, and then the mechanism goes: the file, its reading in `conftest.py`
  and `tests/selection.py` (`dormant`).
- `.venv/bin/napkin fmt --check $(git ls-files '*.scn')` passes: every model is in its formatted form.
- Each package's `changed.md` is complete.

## Hand back for review

Open the pull request into `claude/blissful-heisenberg-5me2hn`, and do not merge it. Its description:

1. For each package: what was translated by hand and why, and the result of `check.py`.
2. The owner's answers to the four questions, and how each was applied.
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
