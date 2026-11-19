# The changes of the wrong copy `piano_tuners_outcome`, for the test of the check's outcomes

`run_all.sh` checks this copy twice: without this list the run step must FAIL on the run's outcome
(re-audit 19: the run fails at 8760 h, its horizon, where every value is the old one), and with it
(`--changed`) the check must PASS. The row is in the format of a package's
`b1/m-<package>/changed.md` for an outcome (`check.py`, its docstring): the new cell is the run's
outcome as the check's line writes it, its reason in full, so another failure at that time does not
pass for this one.

| test | quantity | old | new | cause | evidence |
| --- | --- | --- | --- | --- | --- |
| check run examples/piano_tuners/model.scn | outcome | finished at 8760 h | failed at 8760 h: tuners.audit.step[0].do[0]: the move of 2 from tuners.due to tuners.ledger fails: tuners.ledger would hold 2, outside its range [0, 1]; nothing is moved [stage 1 of tuners.audit#0, t = 8760 h] | no rule: a translation error made on purpose, an audit at the end of the year that moves more than its ledger holds | check.py: FAIL [run] outcome: old finished at 8760 h, new failed at 8760 h; napkin run: error: the run failed at 8760 h |
