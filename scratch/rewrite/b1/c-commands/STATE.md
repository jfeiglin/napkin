# C-K: commands, API and tools — state (in progress)

Brief: `briefs/c.md` (C-K) with `COMMON-B.md`; PLAN "Changes after G0" 10-14; C-R, C-D, S6-F STATE.
Baseline b0b1d32 (stage C report committed, 5,151 live tests).

## Order of work
1. `napkin run` on the report: --run, --edits, --lag, status displays, near-ties; the two G1 flaws.
2. `napkin draw` on `Things(compiled).runs`; `napkin compile` checks the stylesheet; the four
   stylesheet tests again in tests/commands/.
3. `napkin new` and `tools/new.py` in the new language.
4. API: `napkin/__init__.py` (no `sample_result`), `engine/__init__.py`, tests/test_api.py CLOSURE;
   `napkin/package.py`, tests/test_package.py, test_nested_packages.py.
5. `tools/compare.py` small over the record; `tools/bench/families.py` over programs.
6. `napkin sample` once C-S (`b1/c-studies/STATE.md`, "For C-K") is ready. NOT `napkin play`, nor
   anything on `choose`, `sees`, controllers or picks: they wait for S7 (PLAN change 15; the
   coordinator, twice): list them under "not done".
7. tests/release/wheel_smoke.py; the old tests/test_cli.py, test_cli_tables.py go (ported).

## Done
- `napkin run` (run.py, common.py): --run, --edits, --lag PATH=FROM..TO, displays, near-ties,
  the trail in JSON. tests/commands/test_run.py (17), test_run_report.py (21).
- Fixed outside my files (flag it): napkin/program/proofs.py `_point_parts`, a route leg's point
  keeps `at` fourth (the report crashed on `x.forward.actual_rate`).
- `napkin sample` (sample.py) on C-S's `napkin.spread.spread` -> `MonteCarlo`: --run, --edits,
  --value, --at, --samples, --seed, --jobs, --exceed, --json (every sample). tests/commands/
  test_sample.py (16). If C-S changes `spread`/`MonteCarlo`, adjust `main` and `document`.
- tools/compare.py rewritten small (capture, published runs.json, compare names/values/trace,
  renames). tests/test_compare.py (15).
- `napkin draw` (draw.py) on `Things(compiled).runs`; `napkin compile` lists named runs and the
  model hash and checks style.toml (exit 1). tests/commands/test_draw.py (11, the 4 stylesheet
  tests again as one parametrized test). `napkin new` (new.py) and tools/new.py in the new
  language: tests/commands/test_new.py (26), tests/test_tools_new.py (27, live);
  tests/test_tools_new_catalogue.py (1, new: reads the catalogue and the publisher: M, dormant).
- commands/__init__.py: NAMES compile, run, fmt, draw, new; LATER {play: S7, sample: C}; cli.py
  names each later command's stage.
- package.py: `name_of`, `entries`, `load_package(path)` (one LanguageError, each problem once);
  `combined`/`reduced`/`source_problem` gone (`Compiled.configure` does it). tests/test_package.py
  (5). tests/test_nested_packages.py (5) on C-E's tests/evidence/support.py.

## Decisions
- K1 Residue: the text shows 0 for |x| <= atol_factor (1e-10) x the largest magnitude of the
  value's history and its reported numbers; JSON keeps the record's number. (G1: 4.05538e-26 W.)
- K2 Unit: a composed spelling shows as the first name of `declared.units` with equal dimension and
  scale (Wh/h as W, text and JSON); atoms, plain numbers and ratios stay. The number is unchanged.
- K3 --edits fills `schema_version` and `model_hash` where the document has none (as the old CLI);
  a problem of the document is placed at its file. An unknown --run is a usage error (exit 2).
- K4 Times after a stop are dropped from the table; the 'run' diagnostic is the report's `stopped`.
- K5 A display is listed with its entity's values (by line); its cases' texts under the table.

## Not done / for others
- Engine (not mine): the residue makes `rate_follows_levels` false at 3 h in the worked network.
