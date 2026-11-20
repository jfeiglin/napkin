# Audit 3, agent T: change 25 (a stale rate is an error for every flow); the oracle's membership

Brief: the main session's message, COMMON-B, audit3; PLAN 10, 15, 24, 25; spec.md:544. DONE.

## Places (listed before any change)
1 ways.fresh: declared sets only. 2 ways.rate: a flow that left read its old rate (spec: 0), one
that joined read 0. 3 run._evaluated: a SOURCE->SINK rate is min(request, capacity), unchecked.
4 the setup read pre-setup rates. 5 next_moment/moment.at: the ways' names mixed into run.changed
(a moving set gives all stores and rates at each segment end: too wide), met bounds not told apart.
6 _publish: an allocation marked only its store. 7 messages without the advice. 8 complete's freeze
(consistent after). 9 firings (not changed, owner). 10 oracle round_written reset at a round's start.
11 keyed reads at their key time (engine yes, oracle no). 12 saved.py. Not places: checkpoint
State, record, report, commands, tools.

## Rule test: tests/engine/test_stale_rates.py (first; HEAD 6ef42a2: 235 of 413 failed)
Random networks (5 store kinds, SOURCE->SINK, routes between stocked stores, legs, capacities,
priorities) + stages that set a request/capacity/allocation/store, move, start (join), finish
(leave), a firing's start; reads in the stage, a later stage, the next round, later, the setup;
vs the oracle, and with a stop before the read and a store edit (in place, saved state). 14 named
cases by hand (message words, values, a subprocess resume). Census of 200: 77 stale, 107 pass.

## Done
- One check (ways.fresh -> stale): Run.unsettled (commits' names, written, tx.writes, dynamic reads
  of changed collections, keyed reads; marks bound/allocation) against Connected.reads, the set's
  stores (set_of), flows joined/left at them, then BFS through Connected.rates (giver). Setup
  fails; joined fails; left reads 0. plan.outside: SOURCE->SINK rates, checked in _evaluated, join
  ('joined' mark) and freeze at 0 with their occurrence. run.moved: the ways' names (settle only);
  each snap gives (names, met); component Segment.reached. waiting_names gone. Run.classes_of ranks
  the network's own flows (a lines set restored after a join raised KeyError).
- Oracle: round_written reset at each settlement; message with the advice.
- tests/reference/test_solver_memberships.py (5): the oracle already has the rule (Ev._within,
  66797b7); it passes on HEAD too.
- Counts: test_stale_rates 2414 (deep incl.); see the final message for the rest.

## Decisions
- Every rate read in the setup fails (nothing has settled; the oracle's rule).
- What a rate depends on is static (Connected.reads): an untaken branch's value counts (the
  oracle's deps are the branch taken; no random case has a branch).
- A flow that left reads 0 with no failure; the rates it shared at its stores are stale.
- A keyed read at its key time counts (the engine did for solvers); a branch on t of a moving
  rate does not; the oracle counts neither (For the owner).

## For the main session
- The xfail of test_solver_memberships names model/lowering.py `_relations` (F): build the
  constraint from `item.test`, drop `_relations`; checked in a copy: the xfail passes, and F's
  tests/language/test_solvers.py::test_a_range_test_in_a_constraint_is_the_chain_of_its_two_relations
  pins the old program bytes (update with it).
- Local sharing, not change 25, on HEAD too: (1) s0 10 in [0,10], SOURCE->s0 0.5 L/h cap 4, route
  s0<->s1 request -2 cap 1, s1 0 in [0,100], any stage at 2 h: s1 at 2.5 h is 1.0 (oracle, which
  stops the route at 2 h) and 1.25 (engine); (2) a [0,0] junction between a route and legs into a
  full store: the engine fails "local sharing moves it past its bound at 0 h" (seed 752 of an
  earlier generator). (3) The engine fails a ring at its start, before the setup; the oracle after.
- An endpoint that only a stage's allocation names (no setting) has no request in a run with
  occurrence flows: "has no value yet" (plan.end_of at run time).

## For the owner
- Firings: a capture or a start argument read after an earlier firing of the same conditions
  started a flow is not checked (change 25 names stages): engine and oracle agree.
- A change by the clock at a moment (a key time, a branch on t): stale or not (above)?
