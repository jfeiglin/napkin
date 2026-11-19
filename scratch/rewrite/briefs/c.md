# Briefs of stage C: results and consumers

Read `briefs/COMMON-B.md` first; then `PLAN.md`, "Changes after G0", items 10 to 14 (the owner's
priorities, reproducibility, no `delayed`, the publisher in M, tallies by use); then the STATE files
that your part reads (`b1/s6-front/`, `b1/s6-engine/`, `b1/s5-engine/`, `b1/s4b-engine/`). Your state
file is `scratch/rewrite/b1/c-<part>/STATE.md` (60 lines at most). The rules of COMMON-B hold; each
part writes only its own files, and runs its own tests and `tests/core`.

Stage C ports what reads the declared model and the results of runs onto the new forms: the declared
model (`napkin/model/semantic.py`, `compile.py`), the program (`napkin/program/`) and the record of a
run (`napkin/program/record.py`, `napkin.engine.run` and `read`). It deletes the old code that each
port replaces, and each old test file that it ports leaves `tests/dormant.txt` (the main session
edits that file). A test that reads the catalogue waits for M; say which. The publisher
(`tools/publish/`, `tests/publish/`) is not in C (change 13).

Order: C-R, the report, first, beside C-D (draw) and C-Y (dynamics), which read no report. C-S
(studies and runs), C-K (commands, API and tools) and C-E (evidence tools) start after the main
session has joined C-R.

## C-R: the report

Own: `napkin/engine/report.py` (rewritten in place, or a new module: say which); the proofs in
`napkin/program/`; the status display in `napkin/model/` (`semantic.py`, `lowering.py`) and
`tests/language/`; the marks of near-ties in `napkin/engine/timeline/` and their reading in
`record.py`; `tests/engine/` for the report; `tests/program/`.

- One report over a record. The caller selects paths and times (D10). Each value comes with its
  unit and its label, the first text under its declaration (spec, "Model text, status cases and
  evidence").
- A status display: its cases in written order, the first that matches gives the rating (`ok`,
  `degraded`, `failed`, `inactive`) and the text; the last unconditional case is the fallback. The
  front end lowers it (refused today as `later_slice`, "(C)"); the engine records the case that
  applies; the report reads it.
- A reporting lag (spec, "Formulas and the values a caller can read"; D10): a uniform lag of two to
  six hours averages the history of the window and draws nothing. It is valid only when a proof
  says that the selected value never falls over the run; otherwise the lag has a diagnostic and the
  plain read stays. The proof moves to `napkin/program/` from the old `napkin/model/analysis/values.py`
  (its invariant rules), over a program and a configuration, each conclusion with its reason. A
  tally is known by use (change 14); a shared store that another occurrence can drain needs the
  proof to cover that withdrawal (spec, "What a proof establishes").
- The evidence trail: for each reported value, the records of the parts that it read, and which of
  them the run exercised.
- Near-ties (change 10): the engine marks each firing, branch, crossing, and split of who is served
  that was decided within tolerance of its boundary, as a detail of its trace entry; the report
  lists each ("this trigger fired within tolerance of its threshold"). Detect and report; do not
  compute more precisely.
- A paused run reads up to its pause, and its report says so.
- Port: `tests/engine/test_reporting.py`, `test_timeline_reports.py`, `test_evidence_trail.py`,
  `test_run_evidence.py`, `test_paused_results.py`, `tests/model/test_categories.py`. Delete
  `tests/engine/test_timeline_derivatives.py` and `tests/test_cli_derivatives.py` (DELETE rows of
  B0 left behind). The command `napkin run` moves onto the report in C-K.

## C-D: draw

Own `napkin/draw/`, `napkin/model/views.py` and `tests/draw/`. Draw renders the declared model and
its program; it still calls the old views API. Port it over the new declared model and program, in
the new notation (no `delayed`, no `output`, no `versus`). Its property tests are heavy: run them
by file, and mark one that takes more than about 10 s `deep`. `commands/play.py`'s use of the views
is C-K's. Port the 16 rows of `tests/draw/` in the triage; list each.

## C-Y: dynamics

Own `napkin/dynamics/` and `tests/dynamics/`. `dynamics/field.py` builds its system from the old
flat form; build it from the component of a small program instead (`napkin/engine/timeline/`
`component.py`; read the engine, do not change it). Port the six rows of `tests/dynamics/`; the
tests of `scenarios/cyber_learning_loop` that use dynamics wait for M.

## C-S: studies and runs (after the join of C-R)

Own `napkin/engine/study.py`, `uncertainty.py`, `sampling.py`, `expectations.py`, `napkin/spread.py`,
`napkin/session.py`, `napkin/store.py`, `napkin/schema/` (the edit document keeps the form of S6),
`tests/test_session.py`, `test_store.py`, `test_spread.py`, and `tests/engine/`
`test_monte_carlo_study.py`, `test_admission_scope.py`, `test_public_engine.py`,
`test_decision_resolver.py`, `test_expectations.py`.

- A study is runs of one program under configurations; a Monte Carlo study samples in `sampled`
  mode with a seed for each sample; the estimators are the plain ones (no whole-run derivatives).
- Parallel samples (change 10, speed): samples run in processes; a sample alone, in a batch or in
  another process agrees within the stated tolerances (change 11), and the same run is identical.
- The session and its resolver: a person picks at a pause (`Run.resume`), and the same log gives the
  same run.
- The run store: the key covers the program, the effective configuration, the mode, the seed, the
  choices, the numerical settings and the code, and no label. A stored run serves a request that it
  covers; a request for a value or a window that it lacks runs again. The record replaces the
  `Trajectory` pickles. A paused run is not stored. New tests: a label edit reuses a stored run;
  another seed, and a window that the stored run lacks, do not.

## C-K: commands, API and tools (after the join of C-R)

Own `napkin/commands/`, `napkin/cli.py`, `napkin/__init__.py`, `napkin/package.py`, `tools/new.py`,
`tools/bench/`, `tools/compare.py`, `tests/commands/`, `tests/test_api.py`, `test_cli.py`,
`test_cli_tables.py`, `test_package.py`, `test_nested_packages.py`, `test_tools_new.py`,
`test_bench.py`, `test_compare.py` and `tests/release/`.

- Every command on the new path: `run` through the report, with `--run NAME` and `--edits FILE`
  (S6's `load_scenario(path, run=, edits=)`); `sample`; `play` over the new views and the pause;
  `new`, `fmt`, `compile`, and any other.
- The public API of `napkin/__init__.py`; `CLOSURE` of `tests/test_api.py` lists the new packages
  (`napkin/program/`, `napkin/engine/solve/`, the new engine modules).
- The templates of `commands/new.py` and `tools/new.py` in the new language.
- `tools/compare.py` rewritten small over the record: names, values, trace (G0's candidate);
  `tools/bench/families.py` over programs.

## C-E: evidence tools (after the join of C-R)

Own `tools/evidence/`, `tests/evidence/` and `tests/model/test_pages.py`. Over the records and claims
of the declared model and the report's evidence trail. Port the 11 rows of `tests/evidence/`; what
reads the catalogue waits for M.
