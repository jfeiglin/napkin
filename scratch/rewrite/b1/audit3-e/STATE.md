# Audit 3, agent E: the engine (track b1/audit3-e)

Brief: `briefs/audit3.md` "E", `COMMON-B.md`; round 2: the main session's message (PLAN change 24 b,
R's horizon rate, recursion left in my files). Before-states: new tests run on `git archive` of HEAD.

## Where each cause acts (listed before any change)
F14 a write to a finished occurrence: moment.target/assign/move, occurrences.register/complete,
the ways between moments (run.next_moment), checkpoints.checked (R: edits always write, holds),
oracle `_assign`/`_move`/flows (tests/reference/run.py, mine for this). R15 chains (round 2):
timeline/component.py `_expand`, sparse.py `Vector` (its compile and each evaluation), ways.build
`level_of`; `names_in` (core expr.names) recurses by a node's depth (`expr.limited`): no path.
H (R's): at the horizon a set on curves recorded no rate from its commits (ways.finish: lines only),
and a component built at a moment read its rates before finding its bounds (`active_bounds` empty).

## Rule tests (written first; failure on the code as it was)
- test_frozen_occurrences.py (71, change 24 b): 27 failed (a move of 0 L failed; zero-rate flows
  failed when met; message; oracle: moves and flows unchecked).
- test_horizon_reads.py (7): component and sparse failed on HEAD; bare horizon (compartments) added
  after my first finish refused it. R's xfail in test_budget_rule.py is now a test.
- test_deep_engine_paths.py: chain of sets (level_of), component 1500, sparse 1000 failed on HEAD
  (RecursionError); + 5,000 deep variants. test_named_collections.py: + aliases (F's `tanks = big`).

## Done
- 24 b: `Occurrences.writable(name, writer, amount)`: an assignment always writes; a move's amount or
  a flow's rate writes beyond the store's tolerance (D8). `carried(start, end)`: flows at `watched`
  stores (kept at complete/register, found from `live` after a restore), after each settling and
  over each window of next_moment (form's steps, bisection to the crossing tolerance). Oracle:
  `_move` (amount != 0), `_frozen_flows` after each moment's motion.
- H: Run.bare (the horizon and nothing else due) -> ways.finish(t, moment); ComponentWay.finish and
  Sparse.finish record a set built there (no evaluation yet, which a checkpoint keeps), stores with
  their rates as slopes (an affine first segment's), flows held; ComponentWay._settle before a read
  of a fresh or restored set's rates.
- R15: component `_expand` on walk.walked, leaves only (callers ask for moving leaves): 5,000 links
  3 GB -> 1.3 GB. sparse `Vector`: one memo per evaluation, `Pending` on a path stack of tasks
  (template members together), the first evaluation's order replayed (1,500 links 14 s; HEAD with
  no limit 30 s). ways `level_of` on the driver. B's docstring (`walk.walked`).

## Decisions
- A move transfers the exact requested amount. A positive remainder stays in its source.
  The per-hour tolerance for a flow's rate is given by `Run.tolerate`.
- A rate that rises from zero fails at the first time beyond its tolerance (within the crossing
  tolerance of the moment); the oracle fails at the moment, but not at the horizon.
- At a horizon that is no other moment, sets hold their segments' values (a longer run's segments
  go through it); an event of a curve within the crossing tolerance of the horizon is due there
  (`moment.Clock`), so a read exactly at such a jump may differ from a longer run's.

## For R
- saved.py: keep a component's `bounded` and `state.active_bounds`; a restored one finds the bounds
  of its state (`_settle`), which differs from the straight run only where a store met its bound
  exactly at the stop (HEAD restored none). A moving solver whose two bounds tie fails "numerical in
  fair sharing, tier 0" (seen in test_horizon_reads, avoided there).
## For the main session
- Oracle vs engine (HEAD too): a stage reading a flow's actual rate at the moment its store meets a
  bound fails in the oracle (`check_stale`, every calculation) and reads the last rate in the
  engine (`ways.fresh`: declared solvers only; spec 544 says "A solver result").
- plan.py expansions keep every formula below a formula: quadratic memory in a chain (211 MB at
  3,000 links). Not fixed: a component's rate switching where a rising store meets its threshold at
  a segment's end ("rates switch back and forth"), as on 8b3a01a.
## For the owner
- None open: 24 b answered the zero-rate flow.
