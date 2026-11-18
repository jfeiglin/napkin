# Brief S0-E: the engine, first slice

Read `briefs/COMMON-B.md` first. State file: `scratch/rewrite/b1/s0-engine/STATE.md`.

## Why

Stage S0 runs the first model from source to report with the new language. The engine stops
reading the old compiled forms and reads programs (`napkin/program/`) only. You re-aim it, for the
subset of this slice, and give it one entry point and the record of a run. Another agent writes
the front end at the same time; engine tests build programs in Python and never parse.

## You own

`napkin/engine/` except `napkin/engine/solve/` (another agent's), new and ported files in
`tests/engine/`, and `key` in `napkin/store.py`. Do not change `napkin/model/`, `napkin/program/` or
`napkin/core/`. If the contract in `napkin/program/` lacks something that you need, work around it
and list the change in your last message. A ported test file replaces its old file in place; list
each, and the main session takes it off `tests/dormant.txt`.

## Read

- `scratch/rewrite/g0-decisions.md`, and in `scratch/rewrite/spec.md`: "Values have owners" (the
  declarations), "Flows and algebraic solvers" up to "Local allocation", and "Acceptance cases".
- `scratch/rewrite/PLAN.md`: "Changes after G0", choices 2 and 3, and S0.
- `scratch/rewrite/a4a/FINDINGS.md` (the layout note, the record R-A4a-07, the key R-A4a-08) and
  `scratch/rewrite/a4b/LAYOUT.md` (the map of the timeline engine after its split into modules).
- The module docstrings of `napkin/program/` and `tests/program/examples.py`.
- `docs/engine.md`: "Between moments: the solver", "Flows, allocation and coupling", "Tables and
  tiers"; then the code of `napkin/engine/timeline/` and `napkin/engine/continuous/`.

## What to build

1. **The engine reads programs.** Every module of the new path imports nothing of `napkin.model`:
   the constants it takes from `napkin/model/ir.py` move into the engine, and what the continuous
   engine reads of a typed structure today it reads of a program or of the engine's own plan.
   Modules of the old path that a later stage replaces (`study.py`, `report.py`, `uncertainty.py`,
   `expectations.py`) may keep their old imports for now.
2. **`Plan.of(program, configuration)`** for the subset of this slice: inputs, stored values with
   bounds, formulas, stores, directed flows with `request` and `capacity` (a value or a formula)
   between stores and from `SOURCE` or to `SINK`. Each connected set of stores and flows runs as one
   component of the continuous engine (today's general tier). Reuse the kept modules: `state.py`,
   `segments.py`, `readers.py`, `checks.py`, `component.py`, `trees.py` and `napkin/engine/continuous/`.
3. **One entry point**, `napkin.engine.run(program, configuration)`, that gives a record
   (`napkin/program/record.py`): for each recorded value its history as pieces, and the trace. Modes
   `median` and `sampled`; a draw for an input's default is keyed by its site, and a median run takes
   the median of the distribution (`napkin/distributions.py`).
4. **A reader** of a record: the values of named paths at chosen times, in their units. The main
   session builds `napkin run` on it.
5. **The key of a stored run** (`key` in `napkin/store.py`): the canonical bytes of the program and of
   the configuration (`napkin/program/canonical.py`), the code and the environment; no label and no
   request.
6. **Delete** what only the old compiled forms used: `Plan.flat` and the flat entry points of
   `timeline/__init__.py` (`trajectory`, `result`, `_plan`, `_digest`, `flat_plan`), and the old path of
   `runtime.simulate`. Keep what a later slice reuses.
7. **Tests**: each example of `tests/program/examples.py` in this slice's subset (`tank_delivery`: 3 L/h
   until the tank is empty at 2 h 40 min, then 0; the unit examples; others in the subset) runs and
   gives its expected results. Where `tests/reference/from_program.py` exists (another agent is
   writing it now), also compare with the oracle. Port the engine tests of slice S0 in
   `scratch/rewrite/tests-triage.csv` that your subset covers (such as `test_cumulative_integration.py`,
   `test_resolution.py`, `test_sizes.py`, `test_switching_surfaces.py`, and the two tests of
   `test_radau.py` that build from source), keeping their closed-form expected values.

## Exit

The new tests and the ported ones pass, with `tests/core`, `tests/program`, `tests/engine/test_highs.py`,
`test_rationing.py`, `test_sampling.py` and `test_solver_adapters.py`. Your last message lists the
entry points, what runs and what is refused for a later slice, the deleted code, the ported files,
and each change that you need in `napkin/program/`.
