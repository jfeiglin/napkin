# M-prep: the translator, the check, the evidence refusal and the handover of stage M — state
Task: PLAN.md "Changes after G0" item 17 (and 16). Rules: briefs/COMMON-B.md. Writes only in
scratch/rewrite/a5/, scratch/rewrite/briefs/m.md, tools/check.py, tests/test_check_evidence.py.

## Plan
1. a5/translate.py to the language of now; test on examples/reservoir and water jamestown into
   a5/translated/now/; compile with load_scenario; share and error codes by count.
2. a5/check.py by meaning (numbers with units, texts, kinds, never-falls by program/proofs.py),
   old side in a subprocess under napkin-base; pass on examples/piano_tuners, refuse bad copies.
3. tools/check.py: a stage that refuses a package with a `no_record` report (S7-F's
   napkin/model/support.py, wired in compile.py); tests/test_check_evidence.py.
4. briefs/m.md handover.

## Facts found
- S7-F's evidence warning landed: `Compiled.reports` holds Problems with code `no_record`.
- New language: `in [0,]` (no `none`); a case of a switch needs an action under it; a conditional
  of bare members is no switch selector (`enum_member`); categorical weights are numbers in place;
  no `role` under an event; no `about`/`category`/`scope` under a value; braces in texts mean nothing.

## Done
- Step 1: a5/translate.py (old compiler) writes a5/translated/now/ (A5's translated/auto and hand
  drafts stay as they were: A5's spelling); a5/newmodel.py (compiler of now) compiles. Measured:
  reservoir 47/49 lines (95.9%), compiles, no warning; water model+water+jamestown 1216/1220
  (99.7%); jamestown refused: cycle 1 (Utility.tie_asks, template level), unit 2 (`facility-hours`:
  library units whose parts are no unit), depends 4.

## Decisions
- What the language has no place for goes into notes, by what it was: `reporting` (about, scope,
  category, lag of outputs), `not_estimated` (D4), `comparisons` (versus, D9), `titles`, `roles`
  (of members written by hand). Event roles become comments; `sees` is dropped.
- Old `at R`: request and capacity (S0's D-8). Legs: request only, named target or owner_target.
- An empty outcome cannot be a case (a case needs an action): left for a person, its text kept.
- Outcomes by condition: local `outcome` + switch (a conditional of bare members is no selector).
- A state that an option sets starts from a new input `x_start` (R-A5-04); a value `status`
  beside status lines is renamed `state`.

- Step 2: a5/check.py OLD NEW (by meaning; old side oldmodel.py in a subprocess under napkin-base,
  new side newmodel.facts): groups compile, number, text, kind, flow, cumulative; `--rename`.
  piano_tuners (hand) PASSES; translated/wrong/piano_tuners_{number,text,kind,cumulative} each
  FAIL in exactly its group; the reservoir translation FAILS 1 text (its empty WAIT case).
  `sh a5/run_all.sh` runs it all: OK (6 s).
- Step 3: tools/check.py `unsupported`, `evidence` and the stage 'Evidence' (not with --tests
  alone); S7-F's warning had landed (compile.py reports `support.CODE`). tests/test_check_evidence.py
  5 passed (stub packages SC97/SC98 in tmp_path).

- Step 4: briefs/m.md (setup, scripts, measured state, order and needs of each package, dormant
  tests, the owner's list of changed numbers in b1/m-<package>/changed.md, owner decisions);
  a5/migration-table.md rows brought to the language of now (table_check: 401 keys covered).
- Whole catalogue (translate.py --compile, no PATH): 6,918/6,960 lines (99.4%); 42 left (21 empty
  cases, 11 since(e.outcome), 9 option values/starts that are calculations, 1 share). Compile:
  piano, reservoir OK; cyber 79 (units 76, timescales 3); heat 5 (timescales 2, units 3); iv 8
  (readers of hand-left states); each water variant 7-9 (cycle, units). 32 composed units whose
  parts are no unit (translate.py lists them). a5/newreader.py deleted (A5's reader, now dead).

## Not done
- No package migrated (by design); the hand lines and the compile problems are stage M's.
- check.py has run only on models that compile (piano tuners, reservoir); its comparison of kinds
  and flows on a large model waits for the first water variant that compiles.
