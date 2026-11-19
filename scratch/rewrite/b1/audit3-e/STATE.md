# Audit 3, agent E: the engine (track b1/audit3-e)

Brief: `briefs/audit3.md` "E, the engine", `COMMON-B.md`. Owns engine/timeline/{moment,occurrences,
plan,collections,triggers,run,pools,chance}.py, engine/continuous/ but fields.py, new tests/engine.

## Where each cause acts (listed before any change)
F14, a write to a finished occurrence (spec.md:632, D7, G0 "Allow writes to live occurrences"):
- moment.target (assign, `move` ends): only a dynamic `.occurrences.at(t)` target is checked; a saved
  reference (`job.x`, plan._referred), a reference of a reference, a bare local: no check.
- moment.assign, an allocation (`job.batch.inflow = priority(...)`): no check.
- flows: occurrences.register marks met only the new occurrence's own stores (another's store that
  its flow meets is skipped by retirement); run.flow_joins/_present: a flow that joins at a store of a
  finished occurrence; occurrences.complete: a finishing occurrence's store that another's present
  flow meets keeps receiving (probe: 2 L into a finished batch, no failure).
- checkpoints.checked (R): an edit of a finished occurrence's value, refused (CheckpointError): holds.
- run.write / moment._publish: where the above land; no check of their own (none needed once
  every writer is checked).
- oracle tests/reference/run.py (not mine): `_assign` and `_editable` check; `_move` and flows do not.
N15, a named collection (`tanks = Tank.instances`): a path that steps into it reads its init.
- plan._step 'root' (plan.py:1650): `('value', name)` for a collection; then any step fails.
- plan.occurrence frame names / plan._start Local / plan._step 'occurrence': an event's collection
  local is `('value', name)`, a name with no value (KeyError at the run).
- plan._step 'member': resolves the init (holds). Solver inputs (plan._declare_solver) resolve
  through the same `resolve`, so a root collection named in inputs failed too.
- proofs.py _step 'root' and _local (R): the same cause in the never-falls/start proofs.
- model/solvers.py walk (F): root and member collections resolved (holds).
R15, recursion on a chain of 5,000 links, limit 400 (paths `plan.walked` may not cover):
- (to probe) plan.resolve/_step through a chain of named collections; keyed reads (_keyed,
  lookup_reads, _members_part, _chosen); triggers' conditions; declared.value/_name (not mine) over
  formulas that read unknowns; component._expand, sparse.values, ways.build.level_of (not mine);
  continuous/kernels.py dynamic, _proven_zero, compartment_solution (mine).
M, F's membership operation in a trigger's or a gate's condition: waiting for F's "For E".

## Rule tests (written first, failure on the code as it was)
- F14 `tests/engine/test_frozen_occurrences.py` (49): before the fix 25 failed (19 random writes after
  the finish made silently, through `job`, `other = job`, `.at(t)`; the flows present at the finish,
  in and out; a flow started at a finished store; another's flow retired as none; stop+resume and
  edit-at-stop runs that finish).
- N15 `tests/engine/test_named_collections.py` (44): before the fix 29 failed (every top-level and
  event read over a name: Outside / KeyError; a name of a name; broadcasts; priority over a named
  collection of flows; a solver input naming one; a trigger and a gate); in place, all held.
- (Before-states are run on `git archive HEAD` in the scratchpad, with the new test files copied.)

## Done
- F14: one check, `Occurrences.writable(name, writer)`, called where each write and transfer lands:
  moment.target (every assignment and both ends of a move, whatever spells the target), an
  allocation, each end of a flow as it joins (register), each store of a finishing occurrence that
  another's flow still meets (complete). register marks another occurrence's store met (retired).
- N15: plan._named: a named collection (root, member, event local) is its init resolved in its
  declaring scope; _step root/member/occurrence and _start Local through it (`_bare`); an event's
  collection local enters with no value.

## Decisions
- A flow present at a store of a finished occurrence fails the run when they meet (the finish, or the
  start of the flow's owner), whatever its rate: spec "A flow whose rate falls to zero stays
  connected for its owner's lifetime", "a write to it is an error"; G0 "A transfer that should
  continue after an event finishes belongs on the entity". A rate watched for leaving zero would
  need the integrators to report it; this is never later than a write (owner asked, below).
- A move of 0 L, and an assignment of the value held, to a finished occurrence fail as any write:
  the statement targets the frozen value (the oracle's `_assign` fails any assignment so).

## For F
## For R
- proofs.py `_step` 'root' (and `_local` for an event's collection local) give a named collection as
  a value: a lag of `formula(sum(tanks.water))` is refused ("it reads tanks.water, a setting or a
  property of a value"; in place it lags), and the trail lists only `total` (in place: both
  waters and flows). Resolve the init in its scope, as plan._named does.
## For the main session
- oracle tests/reference/run.py: `_move` and flows do not check a finished occurrence (`_assign`
  and `_editable` do).
- (F) the language refuses a bare alias `tanks = big` of a named collection ("a collection value is
  a literal, the instances..."); `big.where(...)` passes. Spec silent; not changed.
## For the owner
- A flow at a frozen store with a zero rate: fail when they meet (done), or only once it transfers?
