# Audit after G2, engine and report: state (track b1/audit-e2)

Brief: the coordinator's task message (seven bugs) with `briefs/COMMON-B.md`; PLAN "Changes after G0"
10, 11, 15, 16, 19. Owns: engine/timeline/{moment,occurrences,run,record,chance,checkpoints,saved}.py,
engine/report.py, program/{proofs,record,checkpoint}.py, new files in tests/engine/.

## Done
- Failing tests first: `tests/engine/test_audit_after_g2.py` (one group per bug), all seven reproduced.

## In progress
- The fixes, bug by bug (see "Plan").

## Plan
1. moment.move: one store at both ends: the debit and the credit cancel, nothing is written.
2. moment.commit: a savepoint from the tx (trace length at the end of execute, pieces, `changes`,
   definitions, transfers); a failure in the commit discards it; the record holds only the
   occurrences whose start its trace holds.
3. chance: a draw, `outcomes`, `described` read the stage's own writes (tx).
4. occurrences.due: the first round of a moment takes the steps due within `crossing` after it,
   in the order of their occurrences (D5).
5. report._Trail.moved: a flow whose rate the record does not hold: exercised None, "not recorded".
6. proofs.never_falls(key, changes): an edit is a writer of known sign in `check`.
7. Record.end/stopped; Record.value and timeline.read give Unavailable after the end.

## For E1 (the oracle, tests/reference/run.py)
