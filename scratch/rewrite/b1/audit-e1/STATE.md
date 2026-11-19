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

## In progress / remaining
3. Polish snap relative to each unknown's size (bug 3), idle pipe (bug 4: both bounds within NEAR,
   the upper snap overwrote the lower) in `declared.polished`.
- Engine tests (test_solvers.py, new test_full_stores.py), E2's "For E1", deep sets, final command.
- Leftover: `family.wanted` now only saved/restored by saved.py (not mine).
