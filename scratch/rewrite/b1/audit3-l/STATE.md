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

## 2: done (spec 246, 546)
- Places: oracle order._maxmin; engine selection._share and _kept's served; solve fair._tier,
  constant levels, solver end checks (served clipped), declared.polished (level groups); the
  solve tests' exact reference (tests/engine/solve/exact.py).
- Rule: a fraction counts from zero; at a zero level, a claim that no answer serves is held from
  above (served <= 0) and the rest go on; where each can be served alone but not together, the
  tier goes on as before (signed). fair: `_unserved` on a fresh instance, `_hold_zero`.
- Expectations changed: test_local_sharing_rule named case (round 1 item 1: now 1/2 L/h, 1.25 L
  at 2.5 h); tests/engine/solve/exact.py levels from zero (test_random seed 2: -4/3 -> 0).

## 8 (V's find): done. plan.settled read the start node: a stage-set endpoint request left a set
  on FAMILY (3 L/h, oracle 5) and a solver ignored it. Fix: `_named_ends` marks the endpoints whose
  request or capacity a statement sets (`_set_ends`), settled from the start (edits change stores
  only). Rule test: named case (both ways), fails on 1564ac7.
## 3: done. declared._settled, MovingDeclared._settle, oracle network.solve: no answer just after
  (free: back past its bound) stops by name ("switch back and forth at its bound"), as local
  sharing. Rule tests: property over test_claim_order solver networks + named seed 40 (fails before).
## 4: done. plan.occurrence lists no formula local in `initial`; occurrences._enter (C's former)
  loses its exception. test_formula_locals: 163 of 184 fail without the mechanism, all pass with it.
## 6: done. moment.resume `held == _SETUP`. tests/engine/test_setup_stops.py (3 ways, edits): fails
  on 1564ac7 (TypeError), passes. The ring case resumes from the saved state again.
## 7: done. test_stale_rates.py comment: both refuse where the flows first settle.

## 5: done. plan._open_capacities/_open_capacity/_open_end_capacity (+ `_set_capacities`): a
  capacity left out that a statement sets is a CAPTURE of no limit (inf; a checkpoint holds it),
  patched into its flow, leg or endpoint before their connections are indexed. Rule test: named
  case (flow, endpoint; stop and resume); fails on 1564ac7.

## Final (stopped by the main session)
- Not deep, engine + reference: 5899 passed. Deep rule tests: 3 failed of 1534 (381, 1005: the
  conflict fallback held at zero, infeasible -> keep the signed level; 1167: a bound a roundoff past
  the horizon -> lines reach it at the horizon); fixed, test_local_sharing_rule 373 passed after.
- Deep test_clock_moments stopped at 68%: about 10 failures, not examined (seeds unknown).
