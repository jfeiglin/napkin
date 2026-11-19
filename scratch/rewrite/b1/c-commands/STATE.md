# C-K: commands, API and tools — state (done but play: S7)

Brief: `briefs/c.md` (C-K) with `COMMON-B.md`; PLAN changes 10-15; C-R, C-D, S6-F, C-S STATE.
Coordinator: do not port `napkin play` nor anything on choose/sees/controllers/picks (S7, change 15).

## Done
- `napkin run` (commands/run.py, common.py) through `engine.report`: --run, --edits (envelope
  filled, problems at the file), --value, --at, --lag PATH=FROM..TO (warning when refused),
  status displays (rating in the table, case texts under it), near-ties, trail and records in JSON,
  the run store (`common.stored`). tests/commands/test_run.py (18), test_run_report.py (21).
- `napkin sample` (sample.py) on C-S's `napkin.spread.spread`: --run, --edits, --value, --at,
  --samples, --seed, --jobs, --exceed, --json. tests/commands/test_sample.py (16).
- `napkin draw` (draw.py) on `Things(compiled).runs`; `napkin compile` lists named runs and the
  hash and checks style.toml. tests/commands/test_draw.py (11; the 4 stylesheet tests again).
- `napkin new` and tools/new.py in the new language. tests/commands/test_new.py (26),
  tests/test_tools_new.py (27); tests/test_tools_new_catalogue.py (1, new, reads catalogue: M).
- commands/__init__.py NAMES compile, run, sample, fmt, draw, new; LATER {play: S7}; cli.py.
- package.py: name_of, entries, load_package(path). tests/test_package.py (5),
  tests/test_nested_packages.py (5, on C-E's tests/evidence/support.py).
- API napkin/__init__.py: load_scenario, load_package, run, read, report, Lag, study,
  monte_carlo, spread (module), instances, dynamics. tests/test_api.py (18; CLOSURE = closure now,
  with S7's checkpoint modules: recheck after S7). engine/__init__.py is C-S's.
- tools/compare.py small (capture, published runs.json, names/values/trace, renames);
  tests/test_compare.py (15). tools/bench: families.py in the new language, measure.py over
  programs and records; tests/test_bench.py (54, 20 s with -n 2).
- tests/release/wheel_smoke.py: new commands; steps 3-5 need examples/reservoir and the catalogue (M).
- Deleted (ported): tests/test_cli.py, tests/test_cli_tables.py.
- Outside my files: napkin/program/proofs.py `_point_parts`, a route leg's point keeps `at` fourth.

## Decisions
- K1 Residue: text shows 0 for |x| <= atol_factor x the largest magnitude of the value's history
  and of its shown numbers; JSON keeps the record's number (G1: 4.05538e-26 W).
- K2 Unit: a composed spelling shows as the first name of declared.units with the same dimension and
  scale (Wh/h as W, text and JSON); atoms, plain numbers and ratios stay.
- K3 --edits fills schema_version/model_hash where absent; an unknown --run is a usage error.
- K4 Times after a stop are dropped; the `run` diagnostic is the report's `stopped`.
- K5 A display is listed with its entity's values; its cases' texts are under the table.
- K6 A variant is the MODEL of its own folder (no --variant); `napkin draw` names its file by
  package.name_of; compile exits 1 on a stylesheet problem; JSON documents carry no schema_version.
- K7 API: no sample_result, evaluate_study, evaluate_uncertainty, uncertainty_report; Session and
  actors wait for S7.
- K8 Bench: no hybrid core (shape_classes, classes task); report = report of every named value;
  a SOURCE flow of a family has capacity = request (D15: a request is soft).

## Not done / for others
- `napkin play` (play.py, old) waits for S7's checkpoints; so do Session and views.actors.
- tests/commands/test_draw.py failed (9) while draw/things.py named `semantic.Chosen` (S7 removed
  it); another agent fixed draw/things.py, and it passes again.
- Engine (not mine): the solver residue makes `rate_follows_levels` false at 3 h (worked network);
  sparse.py `compiled` float()s an enum read by a moving rate (ValueError 'CLOSED'); a linear
  chain of 3 compartments runs 9 s (old: matrix exponential).
- dormant.txt: can leave: test_api, test_bench, test_compare, test_nested_packages,
  test_package, test_tools_new (test_cli, test_cli_tables deleted). Add test_tools_new_catalogue.py
  (M); tests/release/ stays (M).
