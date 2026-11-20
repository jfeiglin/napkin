# Audit 3b, agent C: a moment's own changes, every reader, a switch at a moment

Brief: COMMON-B, audit3b part C, audit3 "What every agent does"; PLAN 10, 24-26; spec.md:542-544.
Main session: the oracle's rates after a moment are L's rule; I do not edit tests/reference/network.py;
cases that wait for L stay in the rule test, listed below. L works in /home/user/napkin-L.

## Status
- [x] places (below) - [x] rule test tests/engine/test_clock_moments.py; on HEAD bbfad12 102 of 200
  straight fail (63 engine stale where the oracle read on; 39 values) - [x] fixes - [x] tests/engine
  (4574) and tests/reference (223) pass, not deep; ruff clean - [ ] final runs, deep census
## Places, cause 1 (the clock at a moment)
engine: run.next_moment + moment.at (marks bound, keyed, no switch); ways.stale (per set: over-
reports once reads join sets, seed 189); component rate_at/_settle (instant side); sparse rate_at,
_flags, peek (L); MovingDeclared (L, unchecked); lines/family hold rates. oracle: run.check_stale
(no clock), _advance (at_bound), network.motion stops (per moment, not per calculation).
## Places, cause 2 (every reader)
engine: run.value/_evaluated (fresh only in stages); ways.fresh (round 0 taken as the setup);
triggers.fire (captures, start args, reset after D, near-ties read after earlier firings);
occurrences.register/_enter, reach (delay read at once in conditions; oracle waits), _captured
(captured a dynamic read of rates: stale at the settle), complete (freeze); triggers.check after the
firings. oracle: evaluate.Ev.result (stages only), run._fire, _register, _frozen, _asserts after
_conditions. Not places: delays(), splits, carried, predictions, records, reports, tools/.
## Places, cause 3 (a segment that starts at a switch)
engine: continuous numerical_segment/switching_roots (disarmed at its switch, read on the near side:
Radau's FD Jacobian straddles it) at a moment or a located root (stage 0.5 h fails too); sparse peek
(L); MovingDeclared (L). oracle exact (its rates after a moment: L).
## Done
- continuous/integrate: surfaces_of, switched, at_their_switch, far_sides (any way), starting_sides;
  system.Run.switches/clock, read by fields.Field.rates. component: Component.settle (bounds, faces,
  sides; ComponentWay._settle too), Segment.switches, switched(), deciding(); ComponentWay.reached
  (within the crossing tolerance), switched_at(t) -> {(flow, text)}; saved.py keeps switches/clock.
- ways.switched -> run.next_moment -> moment.at ('switch', flow, text) -> unsettled, changed_names
  (set rebuilt), stale; stale per part (`part`: flows sharing stores; a declared set whole).
- run.UNSETTLED (stages, conditions); fresh: setup = round 0 stages; reach defers in conditions;
  _captured skips dynamic reads of rates; triggers.conditions: near-ties with the read, check()
  before acting. oracle: run._clock -> clock_of -> check_stale; Ev.result in stages and conditions;
  _asserts before acting. Docstrings updated. 13 named cases pass.
## Decisions
- A switch: any switching surface (comparison, membership end, min/max/abs/clip), as the oracle's
  stops; reached: at its switch (rtol*(|a|+|b|)) at a segment end within the crossing tolerance of
  the moment and at none at the segment's start. Structural, as a bound met is.
- Far side only for a quantity or t against a fixed side; none where it carries back (chattering).
- Assertions read a round's settled state before its firings act (spec, Rounds: "New consequences
  due at the same timestamp start a further round"); checked again after the next settling.
- Rule test compares at rel=abs=1e-7 (Radau's accuracy; PLAN 10).
## For L / the main session
- Waiting for L's rule (oracle: rates after a moment): seeds whose model crosses a comparison from
  its closed side (t: le, gt; a store rising le/gt, falling lt/ge). Traced: 16, 67, 127, 135, 147,
  189 (edit). All other failing seeds have a sparse set. Failing now (not deep), straight: 0 5 16 19
  37 43 47 54 58 61 67 70 82 99 114 118 119 124 127 135 138 139 145 147 156 161 162 165 168 177 178
  180 181 192; edit: 5 16 19 47 54 61 67 82 99 119 124 135 138 147 165 177 180 189 192.
- sparse.py (L): S1 at a step start (peek: `_select(); _flags()`) and in `_flags`: `self.sides =
  integrate.far_sides(integrate.surfaces_of(<setting nodes>, <formulas>, moving), t, y, place,
  (lower, upper), rtol, side, moving, self.field)`; `values()` reads trial[i] = number where low <=
  trial[i] <= high and t = clock[2] where clock[0] <= t <= clock[1] (as Field.rates): coincide.py
  on sparse. S2 `switched_at(t)` -> {(flow, 'a against b')} reached within the crossing tolerance
  (integrate.switched at a step's ends, as ComponentWay): seed 61. S3 end a step where a switch of
  its settings changes side (as `_switch` for a keyed read): seed 177 (COMPARE lt,ge) s0 1.000291
  at 1.5 h where it crosses 1 L exactly; seed 50 6.99999999198 at 2 h (t-switch at a step end).
## For the owner
- none
