# Audit 3b, agent L: local sharing where the engine and the oracle disagree; then R10, R12. DONE.

Brief: COMMON-B, briefs/audit3b.md part L (+ its last section: R10, R12), audit3.md rules; PLAN 10,
24-26. Worktree /home/user/napkin-L (bbfad12). Main session: item 1 and C's `t <= 2 h` case in
network.motion are one rule: the rates after a moment are those of the state just after it.

## Rule tests (written first; on bbfad12 they fail)
- tests/engine/test_local_sharing_rule.py: random networks vs the oracle (+ edit at a stop, in place,
  saved state) and 9 named cases by hand. bbfad12: 150 of 309 fail. Now 309 + deep 1500 pass.
- tests/engine/test_moving_solver_bounds.py: closed forms (oracle refuses moving solvers). bbfad12:
  9 of 12 fail (drains "cannot answer", fills SciPy ValueError). Now 12 + deep 34 pass.

## Places and fixes
- 1 (both sides): oracle settle used the instant (motion carried it) and released only for solvers;
  engine lines flagged by value and re-solved `stale` at their own next moment; sparse, declared
  already released. FIX oracle `_after` (germ settings), release for all, `_moving`/`_carried`
  (store branches); engine `Instant.settle`/`_nets`, lines begin/_solve/_lines. No answer just after
  (held: off; free: back past): both stop by name "switch back and forth at its bound".
- 2 (engine): selection._exact moved an exact zero (route at a [0,0] junction). Zeros stay.
- 3 (engine, run.py of C): sets built and settled before the setup. `prepare(now=True)`; `_start`
  calls `prepare(now=False)` (all sets wait for the setup's settling); docstrings (module item 3,
  `prepare`, `_now`). Cost: one plan.connect at the setup (20,000-store chain 2.5 -> 2.9 s).
- 4 (engine, plan.py): endpoints that statements name are declared with the plan (`_name_ends`,
  `_named_ends`), an occurrence's at its start; `end_of` after the plan makes them at once.
- R10/R12 (declared.MovingDeclared): solve_ivp per segment (failure timed at its start, record
  lost; SciPy events break at an interval's end). FIX `_held` clips trial states; `_next` steps
  Radau, `_event`/`_first` halving in each step; failure halving to the crossing tolerance.

## Changed expectations
- test_local_sharing.py NO_ANSWER + docstring: seed 40 (routes, legs) now stops at 0 h by name in
  both (no rates hold just after); before, both kept a held, moment-dependent answer.

## For the owner
- A route's claim carried against its request: served fraction below zero (both now: item 1 carries
  nothing) or zero (the route would carry 1/2 L/h forward to make room)?
- A declared solver whose release would move its store back past its bound keeps the held answer
  (moment-dependent); local sharing now stops by name there. The same for solvers?

## For the main session (C's files and others)
- moment.resume `held is _SETUP` fails after a restore: a setup stop cannot resume fresh (bbfad12).
- A branch on another store crossed at a moment from its closed side: the engine fails "switch back
  and forth" (C's item 3 shape); the oracle now gives 5 L, 8 L.
- test_stale_rates.py:71-72 says rings are found before the setup: no longer.
- plan._step: assigning a capacity left out raises an uncaught Outside (spec and oracle allow it).
- Fresh-process tests time out under parallel load (33 under two concurrent runs; pass alone).

## Final runs
tests/engine + tests/reference, not deep, -n 2: 5118 passed. Deep: 1500 + 34 passed. Ruff clean.
