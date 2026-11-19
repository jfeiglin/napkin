# Audit 3, agent E: the engine (track b1/audit3-e)

Brief: `briefs/audit3.md` "E", `COMMON-B.md`. Before-states: new tests run on `git archive 8b3a01a`.

## Where each cause acts (listed before any change)
F14 a write to a finished occurrence: moment.target (only `.at(t)` checked), moment.assign
(allocation), occurrences.register (a flow joining a finished store; another's store never met, so
not retired), occurrences.complete (another's flow still at its store); checkpoints.checked (R,
holds); oracle `_move` and flows (not mine).
N15 a named collection: plan._step root (plan.py:1650), an event's collection local (no value:
KeyError), solver inputs; proofs.py _step root/_local and the trail (R). Holds: member, solvers.py.
R15 chains: plan._named/resolve (a chain of names), plan._where (nested tests), keyed reads
(_chosen, _fixed, _members_part, `reads`: cubic); kernels.py proofs and affine forms (by calls);
not mine: declared.value, family.at + core/arrays, component._expand, sparse.compiled, core/faces,
record._lookup (quadratic).
M12 `within`: triggers._truth_of/_atoms_of, moment.near_ties, integrate.switching_surfaces.

## Rule tests (written first; failure on the code as it was)
- test_frozen_occurrences.py (51): 25 failed (writes after the finish made; flows; retirement).
- test_named_collections.py (45): 29 failed (top level and event: Outside / KeyError).
- test_deep_engine_paths.py (5 + 5 deep + 5 strict xfail, others' files): named collections failed
  (Outside), then recursed (_named, nodes.names); keyed chain cubic (26 s at 100 links).
- test_membership_conditions.py (7): 4 failed on 8b3a01a; with `within`, trigger/gate never met.
- test_compiled_chains.py (8 deep): F's forms at 5,000 links run, read, trigger at limit 400.
- kernels.py: with component._expand iterative (a probe), proven_zero recursed, then linear.

## Done
- F14: one check `Occurrences.writable` (`frozen` its rule): target, allocation, each end of a
  joining flow, each store of a finishing occurrence met by another's flow; others' stores met.
- N15: plan._named: init resolved in its scope, once, on an explicit stack; flat where of where.
- Keyed reads: `_chosen` once per entries, `_fixed` memo, members' parts lazily, a source written
  again shares its entries, a chosen read reads its entry (`reads`), `define` clears `_members`.
- M12: a membership is evaluated (ops.REVERSED by name), then read as its chain.
- continuous/walk.py holds the driver; kernels.py walks on it.

## Decisions
- A flow at a frozen store fails the run when they meet, whatever its rate: spec "a write to it is
  an error", "A flow whose rate falls to zero stays connected for its owner's lifetime"; G0 "A
  transfer that should continue after an event finishes belongs on the entity".
- Any statement that targets a frozen value fails (a move of 0 L too), as the oracle's `_assign`.

## For R
- proofs.py `_step` root / `_local`: a named collection read as a value: a lag of
  `formula(sum(tanks.water))` refused (in place it lags: 12 for 14), the trail lists only `total`.
- record.py `formula` -> `_switches(at)`: a yes/no formula that raises inside a piece (a membership
  reversed at 1 h) escapes as an ExpressionError (`run()` raises); `firsts` catches it.
- record.py `_lookup`: a chain of n constant-key reads is n^2 holders (39 of 54 s at 2,000): read
  the chosen entry alone (`plan._chosen`), as `plan.reads` does.
- checkpoints.checked: its finished-occurrence test is `run.occurrences.frozen(name)`: use it.
## For F
- core/arrays.py values (family.py at): a rate through a chain of known formulas recurses (xfail);
  core/faces.constant_on_faces walks formulas by calls. Your chain-form rate switch: not
  reproduced (rising and falling, three spellings give 3, 5, 6, 7 L).
## For the main session
- Strict xfails in test_deep_engine_paths.py: declared.py value/_name/reads_unknown; family.py at;
  component.py _expand (iterative in a probe: then the path passes); sparse.py compiled/_group.
- Oracle tests/reference/run.py: `_move` and flows do not check a finished occurrence.
- tests/engine/test_deep_graphs.py (B's) docstring: `plan.walked` is now `walk.walked`.
- Found, not fixed (continuous/, as on 8b3a01a; F saw it): on a component, a rate that switches
  where a rising store meets its threshold at a segment's end stops ("the solver failed ... rates
  switch back and forth"): `2 L/h if water >= 3 L else 1 L/h` from 1 L fails at 2 h; `3 L <= water
  <= 5 L` from 2 L at 1 h; from 1 L with horizon 7 h it gives 4.994 L at 3 h for 5 L (4 h: right).
## For the owner
- A flow at a frozen store with a zero rate: fail when they meet (done), or only once it transfers?
