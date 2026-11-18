# B0-5 state (take out the whole-run derivative code)

Updated 2026-11-18 18:40. Nothing is committed. This file is in the worktree: the harness refused
a write to the main checkout.

- Worktree `/home/user/napkin/.claude/worktrees/agent-a18118f79e9bec712`, branch
  `worktree-agent-a18118f79e9bec712`. It was made at 13b0969 (`origin/main`, no brief there); I
  fast-forwarded it to 1a5f8e8, so it merges onto the branch cleanly.
- Brief `scratch/rewrite/briefs/b0-derivatives.md`, plus two messages: delete `places.py` with its
  `CLOSURE` entry; a write of `apply` is a tuple of three.

## The proof (in `scratch/rewrite/b0/` of the worktree)

- `bitwise.py OUT`: 370 cases, 3 min, 231 MB. Package from PYTHONPATH, models from the worktree.
- `record_runs.py`: pytest plugin, a digest of every run that a test makes: `NAPKIN_RECORD=DIR
  PYTHONPATH=$PWD:$PWD/scratch/rewrite/b0 pytest -p record_runs ...`; `record_runs.py D1 D2` compares.
- `S=/tmp/claude-0/-home-user-napkin/e09158c7-7039-5d6d-be85-61b3a193adaf/scratchpad/b0`:
  `S/base.txt` is the base output (sha 8d0f9ce8…, in `S/base.sha256`); `S/start_pkg/` is the
  package at 1a5f8e8; `S/start_tree/` is that package with the tests of the worktree.

## Files (18:40)

- Done, ruff clean: all of `napkin/` and `tools/bench` (steps 1 and 2), and the tests (step 4):
  two test files deleted, `test_timeline.py`, `test_timeline_outcomes.py`, `test_expectations.py`,
  `test_estimators.py`, `tests/test_cli.py`, `test_bench.py`, `test_api.py` trimmed. The heat wave
  tests use none of the removed functions: untouched.
- Proved (step 3): `S/base.txt`, `S/start.txt` and `S/mine.txt` are equal (370 cases). The three
  engine test files pass (171 tests), and their 472 runs have the same digests with the old engine
  (`S/start_tree`, into `S/rec_old`) and the new one (`S/rec_new`).
- Not started: the docs and `CHANGELOG.md` (step 5); the end checks and the commit (step 6).

## Order of work, and what remains

1. `run.py` top to bottom, by the checklist of `scratch/rewrite/a4b/LAYOUT.md` section 6.
2. `plan.py`, `timeline/__init__.py`; delete `derivatives.py`, `influence.py`, `smooth.py`,
   `places.py`; `expectations.py`, `estimators.py`; `commands/derivatives.py` and `NAMES`; bench.
3. ruff; `bitwise.py` against base; the three engine test files with `record_runs`.
4. Tests: delete two files, trim the others, `CLOSURE` in `tests/test_api.py`.
5. Docs (`engine.md`, `cli.md`, `python-api.md`, one sentence in `design.md`), `CHANGELOG.md`.
6. The end checks of the brief, once; `bitwise.py` again; commit; report.

## Found, and not in the brief

- `RuleState.own` and its write in `settle` are read only for the tangent of a rule's time: they go.
- `plan.only_general` (and `why` in `Plan.made`) is read only by a refusal of a derivative: it goes.
- `Result.firings` holds tuples of four, the last the slopes of the chances (None with no
  directions). I make them tuples of three; `expectations.weighted` and one test read them.
- `taken(rule, env, name, chances, rest)` needs only `name, chances` after the removal.
- The wrappers `restart_line`, `trigger`, `fire` exist for the notes. I drop each wrapper and give
  its name to the body (`_restart_line` becomes `restart_line`); the split script skips a lost name.
- `slope` goes with the tangents. `restart_block` loses `before` (rates for the jump of tangents).
- `estimators.bandwidth` and `_kernel` go with `tail_slopes`; `control_variate` and
  `expectations.mean_of` stay, with no caller in the package.
- `docs/scoping/networks-and-found-values.md` names `influence.py` in a dated plan: left as it is.
- A report's `implementation_hash` moves with any edit of the engine: `bitwise.py` leaves it out.
- `bitwise.py` reaches no fast-tier crossing, floor or flows that move by one fraction; the record
  of `tests/engine/test_timeline.py` (both tiers) covers those.
