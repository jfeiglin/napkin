# The changes of the wrong copy `piano_tuners_run`, for the test of the check's run step

`run_all.sh` checks this copy twice: without this list the run step must FAIL on the yearly result,
and with it (`--changed`) the check must PASS. The row is in the format of a package's
`b1/m-<package>/changed.md` (`check.py`, its docstring).

| test | quantity | old | new | cause | evidence |
| --- | --- | --- | --- | --- | --- |
| check run examples/piano_tuners/model.scn | tunings_done at 8760 h | 2923.537487 tunings | 0 tunings | no rule: a translation error made on purpose, the tunings due start at zero and not at the need | check.py: FAIL [run] tunings_done at 8760 h: old 2923.537487 tunings, new 0 tunings |
