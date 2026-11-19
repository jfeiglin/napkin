# E1 state: the solver's scope and three flow bugs (audit after G2)

Brief: the main session's message (items 1-4), with `briefs/COMMON-B.md`; PLAN.md change 19.
Baseline: G2 passed; solver/sharing folders 1,241 passed (34 s, -n 2). Old code for checks:
`git archive 858bc1c napkin tests` into the scratchpad, run without the editable finder.

## Done
1. Solver scope (engine `declared.py` Former tiers; oracle `tests/reference/network.py` assemble):
   the solver's claims (named flows; an endpoint all of whose connections it names) on one level
   first, every other claim at its tier of local sharing after them. A relation or objective that
   reads a flow the solver does not name is refused by name (engine `Unsupported`, oracle
   `Diagnostic`). Example `two_junctions_upstream_solver` (examples.py): 1/2, 1/4, 1/4.
   - Found by random seed 5: with flag-dependent levels the answer at a bound can move the store
     off; the oracle re-solved at its next stop (any store anywhere), the engine at its own event.
     Now both release such a store at once and solve again (`DeclaredWay._settled`, oracle `solve`),
     rejecting a release whose answer pushes a released store past its bound; one traced solve;
     both caches hold the settled problem and recognize it again (`ways.last` keeps its shape).
2. Room levels: `network.room_depths` / oracle `_room_depths`; level = max(supply depth of the
   source, room depth of the sink). One full store keeps depth 0 (no answer of today changes);
   [0, 0] stores pass no room. Refusals of two full stores removed (network, family, oracle); a
   ring of full stores fails: "a ring of stores at their upper bound passes room around".
   Tests: oracle test_flows (series, mirror junctions 1/2 1/4 1/4, pipe full->full 0, ring).

## For F1 (tests/language/test_solvers.py SOURCES; verified to lower to the same bytes)
'two_junctions_upstream_solver': JUNCTIONS up to '    provider:' + provider: / upstream = solver: /
inputs: feed = first.feed / solve_for: feed.actual_rate.

3. Polish (`declared.polished`): own size of an unknown = its reference scale at most its width
   (`_sizes`); a flow served in full keeps its request, not a bound (`_served`); rows by own terms,
   equalities always; least change in the distance metric (reference scales: a request-weighted one
   broke a projection, seed 496); safety net on bounds/rows (`_missed`) and claims (`_short`, in flow
   units: a level of 1.8e-6 of 0.5 L/h is slack, seed 593).
4. Idle pipe: both bounds within NEAR of a 5e-7 capacity, the upper snap overwrote the lower; the
   width cap fixes it.
- Local sharing (`selection._exact`): rank 4's answer put exactly on its held plain rows (a part of
  5 L/h gave 2.999999999999999 for 3 and moved an event time; deep local-sharing seed 1067).
- E2's oracle fixes (tests/reference/run.py): self-move writes nothing; a failed commit is discarded
  whole (`_commit` snapshot, trace from the stage/fire entry). Tests in test_events.py.
- Tests: engine test_solvers.py (+8), new test_full_stores.py (4); oracle test_flows (+5),
  test_solvers (+2), test_events (+2). 10 of 11 first engine tests fail on 858bc1c.
- Against 858bc1c (17 examples, 1,000 random solver programs): examples unchanged; 14 programs
  change values (unnamed claims after the solver's); seed 858 now runs; 41 now stop by name on a
  ring (31 supply, 10 room) among unnamed flows (oracle NotCovered); the message says to name them.
- Deep sets (once): random solvers 900, solve sweep, occurrences 2,000, local sharing 4,000: pass.

## Remaining
- The final command; the last message.
- Leftover: `family.wanted` now only saved/restored by saved.py (not mine).
