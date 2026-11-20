# Audit 3b, agent L. Round 1 DONE (merged 1564ac7). Round 2: seven items, in /home/user/napkin.
V works in /home/user/napkin-V (readers, report, session, store, commands, core): not mine.

## Round 1 (merged): what holds
- Rule tests: tests/engine/test_local_sharing_rule.py (oracle; 309 quick + 1500 deep),
  tests/engine/test_moving_solver_bounds.py (closed forms; 12 quick + 34 deep).
- Just-after rule: oracle network.solve/_after/_cached/_moving/_carried; engine Instant.settle,
  lines; no answer just after -> "switch back and forth at its bound" in both. Junction: selection
  ._exact keeps zeros. Ring after the setup: run.prepare(now). Endpoints a statement names:
  plan._name_ends. MovingDeclared: Radau by hand, `_event`, failure halving (R10, R12).

## Round 2 items (main session, after 1564ac7)
1 sparse S1-S3 (C's STATE 51-56); 20 seeds of test_clock_moments. 2 a route's fraction in [0, 1]
(spec 246, 546): both sides; item 1 of round 1 fills at 1/2 L/h. 3 a declared solver with no
answer just after stops by name. 4 plan.occurrence's formula locals in `initial`. 5 a capacity left
out, assigned: uncaught Outside. 6 moment.resume `is _SETUP`. 7 test_stale_rates.py:71-72 comment.

## 1: done
- Places: sparse peek (no far side at a step start, no end at a switch), values (no far side),
  finish/drift/rate_at (the sides of the next step), no switched_at; ways.stale (a join at a store
  that a part reads; the oracle counts it: run.py:333 round_written |= stores_of(f)).
- Rule test: test_clock_moments (C's), 20 failing before.
- Fix sparse.py: surfaces (`integrate.surfaces_of` of the settings), `deciding`; `_start` (select,
  flags, `_sides`: `integrate.far_sides`, `switched`, the signs the step holds); `_held` (the field
  reads far sides and clock); `_turn` (a step ends where a switch changes side; a step that
  straddles one is made again to it, as often as that moves it); `_reached`/`switched_at` (step
  ends, cuts). ways.stale: `store in stores or store in reads` (C's former file, one line + comment).
- test_clock_moments + test_stale_rates: 827 passed.

## In progress
- Items 2-7.
