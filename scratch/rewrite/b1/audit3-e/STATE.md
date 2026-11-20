# Audit 3, agent E: the engine (track b1/audit3-e)

Brief: `briefs/audit3.md` "E", `COMMON-B.md`; round 2: the main session's message (PLAN change 24 b,
R's horizon rate, recursion left in my files). Before-states: new tests run on `git archive` of HEAD.

## Where each cause acts (listed before any change)
F14 a write to a finished occurrence: moment.target/assign/move, occurrences.register/complete (a
flow at a frozen store), ways between moments (run.next_moment), checkpoints.checked (R: edits,
holds), oracle `_assign`/`_move`/flows (tests/reference/run.py, mine for this). N15 named
collections: plan._step root, an event's collection local, solver inputs; proofs (R). R15 chains:
plan._named/_where, keyed reads; kernels.py; component._expand, sparse.compiled/_group (mine now);
not mine: declared.py, family.py (R), core/arrays.py, core/faces.py (F). `names_in`: core
expr.names recurses by a node's depth, bounded by `expr.limited`: not on a chain's path.
M12 `within`: triggers._truth_of/_atoms_of, moment.near_ties, integrate.switching_surfaces.
H (R's): at the horizon a set on curves records no rate from its commits: ways.finish (lines only),
component/sparse (no piece at the horizon); a new component reads its rates before finding its
bounds (`active_bounds` empty: a starved flow reads its request after a rebuild).

## Rule tests (written first; failure on the code as it was)
- test_frozen_occurrences.py (71, change 24 b): 27 failed (a move of 0 L failed; zero-rate flows
  failed when met; message; oracle: moves and flows unchecked).
- test_horizon_reads.py (6 ways): component and sparse failed (2/6). R's xfail now passes.
- test_named_collections.py (45), test_membership_conditions.py (7), test_compiled_chains.py
  (8 deep), test_deep_engine_paths.py (5 + 5 deep + 5 strict xfail): round 1, as recorded.

## Done
- 24 b: `Occurrences.writable(name, writer, amount)`: an assignment always; a move's amount or a
  flow's rate beyond the store's tolerance (D8). Flows: `carried(start, end)` over `watched` stores
  (kept at complete/register, found from `live` after a restore): after each settling, and in
  next_moment over each window, sampled at the form's steps, bisected to the crossing tolerance.
  Oracle: `_move` (amount != 0), `_frozen_flows` after each moment's motion.
- H: ways.finish -> ComponentWay.finish / Sparse.finish record the state at the horizon on its
  bounds; ComponentWay._settle finds the bounds of a fresh or restored state before a read.
- Round 1: F14 statements, N15, keyed reads, M12, continuous/walk.py (see code docstrings).

## In progress / next
- Item 3: component._expand, sparse.compiled/_group on `walk.walked`; xfails -> tests.
- Item 4: B's docstring (test_deep_graphs.py). Item 5: checks and final runs.

## Decisions
- "Nonzero" is beyond the store's tolerance, for a move's amount (after the rule that a move leaving
  less than the source's tolerance moves all) and a flow's rate (per hour, as `Run.tolerate`): the
  resolution of D8 at which a run tells two values apart. The oracle is exact.
- A rate that rises from zero fails at the first time beyond its tolerance (within the crossing
  tolerance of the moment); the oracle fails at the moment, or not at the horizon.
- Curves: an event within the crossing tolerance of the horizon is due there (`moment.Clock`), so a
  read exactly at a jump of a curve may differ from a longer run's; the test avoids such times.

## For R
- proofs.py `_step`/`_local` (named collection lag), record.py `formula`/`_switches`, `_lookup`
  (n^2), checkpoints `frozen`: as in round 1. Solver: a degenerate tie of two bounds of a moving
  solver fails "numerical in fair sharing, tier 0" (seen in test_horizon_reads, avoided there).
## For F
- core/arrays.py values (family.py at), core/faces.constant_on_faces: recursion, as in round 1.
## For the main session
- Strict xfails left in test_deep_engine_paths.py: declared.py (R), family.py + core/arrays (F/R).
- Found, not fixed: a component's rate switching where a rising store meets its threshold at a
  segment's end ("rates switch back and forth"), as on 8b3a01a.
## For the owner
- None open: 24 b answered the zero-rate flow.
