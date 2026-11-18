# Rules for every agent of Phase B (the build)

You build part of a rewrite of the napkin language (a typed scenario language, its compiler in
`napkin/model/` and its engine in `napkin/engine/`). Read this file, then your own brief.

## What wins

1. `scratch/rewrite/g0-decisions.md`: the owner's decisions. They win over everything else.
2. `scratch/rewrite/spec.md`: the settled design, with its acceptance cases.
3. `scratch/rewrite/PLAN.md`: read "Changes after G0" first; it overrides the rest of the plan.

Where you must decide something that none of these settles, choose the simplest form that serves
the engine, the front end and the oracle, and list the decision in your last message under
"Decisions I made". Never contradict the decision record silently.

## Where you work

- The checkout is `/home/user/napkin`, on the branch `claude/blissful-heisenberg-5me2hn`. Work in it
  directly. Write only in the directories that your brief gives you, and in your state file.
  Other agents write other directories at the same time.
- Run no git command that changes the repository: no commit, add, checkout, stash or reset. The main
  session commits your work.
- Python is `/home/user/napkin/.venv/bin/python`. Run tests from `/home/user/napkin` with
  `NAPKIN_STORE=off .venv/bin/python -m pytest -q -p no:cacheprovider PATHS`, at most `-n 2`. Run
  only your own test folders and `tests/core`. Never run the whole suite.
- Lint your files with `.venv/bin/python -m ruff check FILES` and `.venv/bin/python -m ruff format FILES`
  (the settings are in `pyproject.toml`).
- Add no dependency.

## How the code is written

- Follow the house style of `napkin/core/expr.py` and `napkin/engine/allocation.py`: a module
  docstring that says in plain, short sentences what the module holds and why; a docstring on each
  public function and class; a comment where the reason for a line is not obvious. No compatibility
  layer, no dead code, no commented-out code.
- Tests take their expected values from independent mathematics: closed forms, exact fractions,
  numbers worked by hand or given by the spec. Never copy an expected value from a run of the code
  under test. Use generic names (tanks, pumps, places, routes, crews). Each test takes under about
  10 seconds; a longer one is marked `@pytest.mark.deep`.
- A test folder has the same files as its sibling folders (look at `tests/engine/`).

## Usage is short

Read what you need, not more. Do not do work again that a file already holds. Keep
`scratch/rewrite/b1/<your track>/STATE.md` (60 lines at most) up to date at each milestone: what is
done and where, each decision and why, what is in progress, the steps that remain. A fresh agent
must be able to continue from your brief, that file and your code.

## Your last message

400 words at most: what is done; the files; each test command with its counts; "Decisions I made";
what is not done. Put the design in docstrings, not in a separate report file.
