# M-prep: the translator, the check, the evidence refusal and the handover of stage M — state
Task: PLAN.md "Changes after G0" items 16, 17, 19 and 20. Rules: briefs/COMMON-B.md. Writes only in
scratch/rewrite/a5/, scratch/rewrite/briefs/m.md, tools/check.py, tests/test_check_evidence.py.
All done: 1 a5/translate.py; 2 a5/check.py by meaning (and its run step); 3 the evidence stage;
4 briefs/m.md; then the owner's answers of change 19 in the translator (2026-11-19).

## Done
- 1: a5/translate.py (old compiler) writes a5/translated/now/ (A5's translated/auto and hand drafts
  keep A5's spelling); a5/newmodel.py (compiler of now) compiles; `--compile` prints the refusals.
- 2: a5/check.py OLD NEW (old side oldmodel.py in a subprocess under napkin-base): groups compile,
  number, text, kind, flow, cumulative, run; `--rename`, `--changed`, `--at`. `sh a5/run_all.sh`.
- 3: tools/check.py `unsupported`, `evidence`, the stage 'Evidence' (not with --tests alone);
  tests/test_check_evidence.py 5 passed (stub packages SC97/SC98 in tmp_path).
- 4: briefs/m.md (setup, scripts, measured state, order and needs of each package, dormant tests,
  b1/m-<package>/changed.md, owner items); a5/migration-table.md in the language of now.
- Change 19 in the translator: an empty outcome is a case with its text alone; a member keeps its
  `title`; `timescales` are not written, the old hint goes into the main file's notes
  (`timescales: "..."`) and the run lists them; event and case roles go into `roles.toml` beside the
  package's model files. The old reader of roles: tools/publish/pages.py `Pages.cards` (a card's
  actor), shown by the water UI (ui/web/src/App.tsx); nothing reads them in the new layout yet.
  oldmodel.py no longer counts the numbers of a retired timescales line.
- Whole catalogue (translate.py --compile): 6,939/6,960 lines (99.7%); 21 left (11 since(e.outcome),
  5 option values that are calculations, 4 states that options start from calculations, 1 share).
  Compile: piano, reservoir OK; cyber 76 (units operation, access, target, yr); heat 3 (units
  customer, case); iv 8 (readers of hand-left states); each water variant 2-4 (units facility,
  min, yr, acre): the template cycle is gone (cycles member by member). 32 composed units whose
  parts are no unit (translate.py lists them).
- Reservoir translation: the whole check PASSES, run included (change 20 certifies its trigger).

## The run step (check.py group `run`, by the run-step agent)
- Each run of the old default study under the old engine (oldmodel.runs_of) against the new run of
  the same name (newmodel.outcomes: napkin.run in mode `median`, napkin.report with the old lags),
  to the horizon; each old output with an estimate (D4) at 0 h, the horizon, `--at` times and the
  times that rows name. Tolerance 1e-6 of the larger, floor 1e-8 of the old unit. A model that
  draws: its old central run against the new median run only.
- The list: b1/m-<package>/changed.md (or `--changed`), table `| test | quantity | old | new | cause |
  evidence |`, test `check run ENTRY[:RUN]`, quantity `OUTPUT at T h`. Fails on an unlisted
  difference, numbers that disagree, a stale row, a row that does not read, an empty cause.

## Decisions
- What the language has no place for goes into notes: `reporting`, `not_estimated` (D4),
  `comparisons` (D9), `timescales` (change 19); `sees` is dropped.
- Old `at R`: request and capacity (S0's D-8). Legs: request only, named target or owner_target.
- Outcomes by condition: local `outcome` + switch. A state that an option sets starts from a new input
  `x_start` (R-A5-04); a value `status` beside status lines is renamed `state`.
- Roles go into `roles.toml` (`[events]`, `"Utility.strike_again" = "adversary"`, a case as
  `"event.CASE"`) and not into `brief.toml`: water's roles are its module's, shared by 16 variants,
  each with its own `brief.toml`, and the package folder has none.

## Not done
- No package migrated (by design). The run step met no lag or named run in a compiled model yet.
