# Audit 3b, agent C: a moment's own changes, every reader, a switch at a moment; review R03 R06 R08 R09

Brief: COMMON-B, audit3b part C (+ its last section), audit3 rules; PLAN 10, 24-26. Main session: the
oracle's rates after a moment are L's rule (not my network.py); waiting cases stay, listed below.

## Status: all items done; final runs at the bottom
## Item 1-3 places (all searched; L's files under For L)
1 clock: run.next_moment/moment.at (no switch mark); ways.stale (per set, over-reports: seed 189);
  component rate_at/_settle (instant side); oracle check_stale (no clock), motion stops (per moment).
2 readers: run.value/_evaluated (stages only); ways.fresh (round 0 taken as setup); triggers.fire
  (captures, args, reset, near-ties after earlier firings); occurrences._enter, reach (delay read at
  once in conditions), _captured (dynamic read of rates), complete; triggers.check after firings;
  oracle Ev.result (stages only), _fire, _register, _frozen, _asserts after _conditions.
3 switch at a start: integrate numerical_segment/switching_roots (disarmed, read near side: Radau's
  FD Jacobian straddles), at a moment or a located root; sparse peek (L); MovingDeclared (L).
## Item 1-3 done
- integrate: surfaces_of, switched, at_their_switch, far_sides (any way), starting_sides; Run.
  switches/clock read by Field.rates; component settle/switched/deciding/switched_at, saved.py.
- ways.switched -> next_moment -> moment.at ('switch', flow, text); stale per sharing part.
- UNSETTLED (stages, conditions); fresh setup = round 0 stages; reach defers in conditions;
  _captured skips rate reads; conditions: near-ties with the read, check() before acting. Oracle:
  run._clock -> clock_of -> check_stale; Ev.result in stages+conditions; _asserts before acting.
- tests/engine/test_clock_moments.py: HEAD bbfad12 102/200 straight fail; 13 named cases pass.
## Review items
- R03: occurrences._enter evaluated formula locals (plan.occurrence lists them in `initial`, L's
  file); fix: the entry gives a formula no value. tests/engine/test_formula_locals.py: 163/184 fail
  before, all pass after.
- R06: oracle from_program.event (names only), model.Event, run._register; fix: Event.ranges,
  _register checks each argument (_range). tests/reference/test_parameter_ranges.py: 27/81 failed.
- R08: moment.checked, move (amount, ends), occurrences._enter, complete (kept), carried (kept),
  _schedule and triggers' reset (durations), checkpoints.checked (edit), run.start (input). Fix: one
  writer moment.in_unit/quantity/span. Not places: near-ties (canonical by design), counts.
  tests/engine/test_message_units.py: 21/24 failed before.
- R09: triggers._window, _linear, _forms classed a read by its spelling (rsplit), so a solver's
  unknown read as a held line; fix: Triggers._giver (store, flow, result_of). It now stops with the
  named diagnostic; to fire on time MovingDeclared (declared.py, L) must give its results a form
  (`motion`/`breaks`, as a component does). tests/engine/test_watched_reads.py: 3/11 failed.
## Decisions
- A switch: any switching surface (comparison, membership end, min/max/abs/clip), as the oracle's
  stops; reached: at its switch (rtol*(|a|+|b|)) at a segment end within the crossing tolerance,
  at none at its start. Far side only for a quantity or t against a fixed side; none where it
  carries back (chattering). Staleness per sharing part (a declared set whole).
- Assertions read a round's settled state before its firings act (spec, Rounds: "New consequences
  due at the same timestamp start a further round"). Rule test compares at 1e-7 (Radau; PLAN 10).
## For L / the main session
- Waiting for L's rule (oracle rates after a moment): seeds crossing a comparison from its closed
  side; traced 16 67 127 135 147 189(edit); every other failing seed has a sparse set. Failing
  now, straight: 0 5 16 19 37 43 47 54 58 61 67 70 82 99 114 118 119 124 127 135 138 139 145 147 156
  161 162 165 168 177 178 180 181 192; edit: 5 16 19 47 54 61 67 82 99 119 124 135 138 147 165 177
  180 189 192.
- sparse.py (L): S1 at a step start (peek, `_flags`): `integrate.far_sides(integrate.surfaces_of(
  <setting nodes>, <formulas>, moving), t, y, place, (lower, upper), rtol, side, moving,
  self.field)`; `values()` reads trial[i] = number in [low, high], t = clock[2] in [clock[0],
  clock[1]] (as Field.rates): coincide.py on sparse. S2 `switched_at(t)` -> {(flow, text)} within
  the crossing tolerance (integrate.switched at step ends): seed 61. S3 end a step where a switch
  changes side (as `_switch`): seed 177 (COMPARE lt,ge) 1.000291 at 1.5 h, exact 1.
- I changed tests/reference/{from_program,model}.py for R06 (no owner listed): Event.ranges.
## Final (a71773b + this tree)
- tests/engine + tests/reference not deep: 5457 passed, 53 failed (the waiting seeds above only).
  Deep: test_formula_locals 1000 passed; test_clock_moments 1454/2000 pass, 546 wait for L. Ruff clean.
