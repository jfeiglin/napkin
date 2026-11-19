# M-prep: the translator, the check, the evidence refusal and the handover of stage M — state
Task: PLAN.md "Changes after G0" item 17 (and 16). Rules: briefs/COMMON-B.md. Writes only in
scratch/rewrite/a5/, scratch/rewrite/briefs/m.md, tools/check.py, tests/test_check_evidence.py.

## Plan
1. a5/translate.py to the language of now; test on examples/reservoir and water jamestown into
   a5/translated/auto/; compile with load_scenario; share and error codes by count.
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

## Decisions
(none yet)

## In progress
- step 1
