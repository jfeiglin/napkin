# M-prep: the translator, the check, the evidence refusal and the handover of stage M — state
Task: PLAN.md "Changes after G0" item 17 (and 16). Rules: briefs/COMMON-B.md. Writes only in
scratch/rewrite/a5/, scratch/rewrite/briefs/m.md, tools/check.py, tests/test_check_evidence.py.
Plan, all done: 1 a5/translate.py; 2 a5/check.py by meaning; 3 the evidence stage; 4 briefs/m.md.

## Facts found
- `Compiled.reports` holds the evidence warnings (`no_record`). New language: `in [0,]`; a case needs
  an action; a conditional of bare members is no selector; categorical weights are numbers in place;
  no `role` under an event; no `about`/`category`/`scope` under a value; braces in texts mean nothing.

## Done
- 1: a5/translate.py (old compiler) writes a5/translated/now/ (A5's translated/auto and hand drafts
  keep A5's spelling); a5/newmodel.py (compiler of now) compiles. Reservoir 47/49 lines, compiles.
- 2: a5/check.py OLD NEW (old side oldmodel.py in a subprocess under napkin-base): groups compile,
  number, text, kind, flow, cumulative (and run, below); `--rename`. `sh a5/run_all.sh` runs it all.
- 3: tools/check.py `unsupported`, `evidence`, the stage 'Evidence' (not with --tests alone);
  tests/test_check_evidence.py 5 passed (stub packages SC97/SC98 in tmp_path).
- 4: briefs/m.md (setup, scripts, measured state, order and needs of each package, dormant tests,
  b1/m-<package>/changed.md, owner decisions); a5/migration-table.md in the language of now.
- Whole catalogue (translate.py --compile): 6,918/6,960 lines (99.4%); 42 left (21 empty cases, 11
  since(e.outcome), 9 option values/starts that are calculations, 1 share). Compile: piano, reservoir
  OK; cyber 79 (units 76, timescales 3); heat 5; iv 8 (readers of hand-left states); each water
  variant 7-9 (cycle, units). 32 composed units whose parts are no unit (translate.py lists them).

## Decisions
- What the language has no place for goes into notes: `reporting`, `not_estimated` (D4),
  `comparisons` (D9), `titles`, `roles`. Event roles become comments; `sees` is dropped.
- Old `at R`: request and capacity (S0's D-8). Legs: request only, named target or owner_target.
- An empty outcome cannot be a case: left for a person, its text kept. Outcomes by condition: local
  `outcome` + switch. A state that an option sets starts from a new input `x_start` (R-A5-04); a value
  `status` beside status lines is renamed `state`.

## The run step (check.py group `run`), 2026-11-19
- Gap closed: the other groups read declarations only, so a copy of the piano tuners whose yearly
  result is zero passed. Now each check also runs each run of the old default study under the old
  engine (oldmodel.runs_of: evaluate_study, evaluate_outputs with the old lags) and the run of the same
  name of the new model under the new one (newmodel.outcomes: napkin.run in mode `median`,
  napkin.report with the same Lag, D10), to the horizon; it compares each old output with an estimate
  (D4) with the new value of its name (`--rename`: by its path or its template's) at 0 h, the horizon,
  each `--at` time and each time that a row of the list names.
- Tolerance: 1e-6 of the larger value, floor 1e-8 of the old output's unit. Why: both engines
  integrate to rtol 1e-9 (atol 1e-10 of a store's scale) and a run adds its pieces' and event times'
  errors; a translation error moves a result by 1e-4 or more (numbers of four digits or fewer); the
  old report itself took 1e-8 of a unit below zero for zero.
- A model that draws: its old central run (medians, likeliest outcomes) against the new median run
  only; the check's `runs:` line says so.
- The list: b1/m-<package>/changed.md (or `--changed`), table `| test | quantity | old | new | cause |
  evidence |`, test `check run ENTRY[:RUN]`, quantity `OUTPUT at T h`, numbers in the old output's unit
  or `unavailable`/a status. Fails on: an unlisted difference, numbers that disagree, a stale row, a row
  that does not read, an empty cause or evidence. Rows of other tests are left alone.
- Shown (run_all.sh: OK, 16 s): piano tuners PASS; translated/wrong/piano_tuners_run (due starts at 0)
  FAILS `1 run`, PASSES with its own changed.md; the number and cumulative copies fail in run too.
- Reservoir translation: FAILED 2 run, 1 text. The new run fails at 0 h: the trigger water >= level
  cannot be certified on a curve (the at_risk flow's rate reads the water); spilled (old 0.5) and
  risk_time (old 0 h) at 120 h are unavailable. A scratch copy without at_risk gives 0.5. Not fixed.

## Not done
- No package migrated (by design). The run step met no lag or named run in a compiled model (iv,
  water); both tried on crafted facts only. `timescales` left the language (change 19): newmodel
  reads horizon and resolution only; translate.py still writes `timescales` lines (heat, cyber).
