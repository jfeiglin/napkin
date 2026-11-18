# Brief B0-5: take out the whole-run derivative code

You work in your own git worktree of the napkin repository. Read `scratch/rewrite/PLAN.md`,
section "B0. Keel", first. This is step 5 of it.

## Why

The language is being rewritten. The engine's whole-run derivatives (the derivative of every value
of a run by an input, carried through the run as tangents) are out of the first version and are
rebuilt later. Their code is woven through `napkin/engine/timeline/run.py`. It must go now, while
the old tests still run and can prove that a run with no derivative is unchanged. Later steps
rebuild large parts of the engine and must not have to carry the tangents.

## What goes

- `napkin/engine/timeline/derivatives.py`, `influence.py` and `smooth.py`.
- In `napkin/engine/timeline/run.py`: the `directions` argument and everything that exists only
  for a run with directions. That is: the tangent arrays and their handling in lines, blocks,
  steps, writes and rules (`tangent`, `name_tangent`, `rate_tangent`, `own_tangent`, the `tangents`
  of a trial, of a result and of a write); the notes on the kind of a derivative (`note`, the
  subjects, `ties`, `jumps`, the margins, `stepped`); and each refusal whose text starts "the
  derivative of". About 140 lines of the file mention these. The module docstring loses its
  paragraphs on them.
- In `napkin/engine/timeline/plan.py`: `Plan.fast()` and `plan.optional`, which serve derivative
  runs only. `plan.others` and `Plan.made` stay, without the `optional` argument.
- In `napkin/engine/timeline/__init__.py`: the `directions` option (lines 69-71 and its docs).
- `napkin/commands/derivatives.py`, its name in `NAMES` (`napkin/commands/__init__.py:17`), and any
  mention in `napkin/cli.py` and in the command line's help.
- In `napkin/engine/expectations.py`: `controlled`, `_central_slopes`, `_reading`, `labels` and
  `derivatives`, with what only they use. `weighted` and `mean_of` stay, with what they use.
- In `napkin/engine/estimators.py`: `tail_slopes`, with what only it uses.
- The derivative slot of `tools/bench` (`tools/bench/__init__.py:78-81`, `measure.py:103`, `:740`).
- Tests: `tests/engine/test_timeline_derivatives.py` and `tests/test_cli_derivatives.py` whole; the
  tests of the removed functions in `tests/engine/test_expectations.py`, `test_estimators.py`,
  `test_timeline.py`, `test_timeline_outcomes.py`, `tests/test_cli.py`, and wherever else they are
  (search for `directions`, `tangent`, `derivatives`, `controlled`, `tail_slopes`). In
  `scenarios/heat_wave_blackout/tests/test_reference.py` and `outage.py`, only the tests and
  helpers that use the removed functions. In `tests/test_api.py`, the entry
  `engine/timeline/smooth.py` of `CLOSURE`.
- Docs: the parts that describe the removed things, in `docs/engine.md` ("Derivatives." and "The
  class of a derivative" under "Tables and tiers", "A control", "The derivative of an
  expectation", "The derivative of a tail", and the mentions in "What the engine names as outside"
  and elsewhere), `docs/cli.md`, `docs/python-api.md`, `docs/extending.md`, `docs/compiler.md`.
  Mend each link that pointed to a removed part. In `docs/design.md`, leave the history and add one
  sentence where it fits: whole-run derivatives are out for the rewrite of the language and are
  rebuilt later. Add an entry to `CHANGELOG.md` in the form of its other entries.

## What stays

- `napkin/core/derivatives.py` and `tests/core/test_derivatives.py`: the derivative of an
  expression by a name. `Plan._linear` uses it to find the blocks with a closed form
  (`plan.py:37`, `:1326`), and `run.py` uses it for the matrices of a linear block.
- `napkin/dynamics/`: its derivatives are those of the field of a model, not of a run.
- The behaviour of every run that has no directions, bit for bit.

## How

Specialize the code to "no directions". Where the code loops over the directions, the loop goes.
Where an array has one part for the values and one for each direction, it keeps the part for the
values. Take care with the copies: `np.tile(a, 1)` gives a copy, so keep a copy where one was made.
Do not tidy anything else. Do not rename. Do not move code: the next step splits `run.py` by pure
moves, and a clean diff of this step helps it.

## Checks

Use the virtual environment of the main checkout with your worktree's own package:
`PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python -m pytest -q -p no:cacheprovider ...`
(run from the root of your worktree). Use at most `-n 2`: other agents share the machine.

1. **Bit for bit.** Before you change anything, write a small script (keep it outside the
   repository's tree, or in `scratch/rewrite/b0/`) that runs some models and writes every number of
   the result: both `examples/` models through `simulate` for each of their runs;
   `tests/acceptance/F5.scn`; the default run of `scenarios/iv_fluid_shortage`; and two table
   models through the hybrid core (`napkin.model.hybrid.compile`, then
   `timeline.run(timeline.Plan.of(core))`): `scratch/networks/twolinks_model.py` shows how to
   write one, and `tools/bench/families.py` has more. Run it with the base commit
   (`PYTHONPATH=/home/user/napkin-base`) and with your worktree. The two outputs must be equal
   exactly, at the start and at the end of your work.
2. **While you work**: `tests/engine/test_timeline.py`, `tests/engine/test_moment.py`,
   `tests/engine/test_closed_form_short.py`.
3. **At the end, once**: `tests/engine tests/acceptance tests/core tests/test_api.py
   tests/test_cli.py tests/test_cli_tables.py tests/test_bench.py`, and the tests of
   `scenarios/heat_wave_blackout` (`--scenario heat_wave_blackout` or its test paths). All green.
   Then `ruff check` and `ruff format --check` on `napkin tools tests scenarios conftest.py`.
   A test that fails and that also fails at the base commit is not yours: list it.

## Exit

Commit your work in your worktree, in one commit or a few, with messages in the style of the
repository's log (a short imperative subject, then plain sentences on what changed and why). End
each message with these two lines exactly:

```
Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01YAC5JWzpvFMcmwkAXrPQet
```

Do not push. Do not open a pull request. Your last message: the name of your branch and the commit
ids; what you removed, in lines of code by file; the result of each check; anything that you left
in place and why; anything that surprised you.
