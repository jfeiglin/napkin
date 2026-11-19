# E1 state: the solver's scope and three flow bugs (audit after G2)

Brief: the main session's message (items 1-4), with `briefs/COMMON-B.md`; PLAN.md change 19.
Baseline: G2 passed; solver/sharing folders 1,241 passed (34 s, -n 2).

## Plan
1. Solver scope: unnamed flows of a solver's set keep local sharing (engine `declared.py`, oracle
   `tests/reference/network.py`); example `two_junctions_upstream_solver` in examples.py.
2. Two full tanks in series: room levels in local sharing (`network.py`, `family.py`, oracle).
3. Polish snap relative to each unknown's own size (`declared.polished`).
4. Idle pipe with a small capacity starts: find and fix.

## Done
(nothing yet)
