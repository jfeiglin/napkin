# S6-E state: the engine, what is left before G1 — in progress

Brief: `briefs/s6.md` (S6-E) with `COMMON-B.md`, `s0-engine.md`; S5 in `b1/s5-engine/STATE.md`.
Baseline: S5 committed (7f3d902), 4,070 live tests. Owner: napkin/engine/ but solve/ (S6-S);
tests/engine/ but solve/ and the four option/run/binary files (S6-F).

## Plan (in this order)
1. Priority endpoint with a request in a declared solver: the spec allows it ("A preferred route
   has first access to useful requested work, up to the outstanding claim it serves"); the oracle's
   `prefs` = claims in tiers after all others (declared.py). Tests vs oracle + 4/2 L/h.
2. Formula assignment in a stage ("definitions"): plan.define replaces a value's kind/node at a
   commit; history in plan.defined; trace details `defines` on commit/fire (setup: a commit entry
   'setup' only when it defines); reader takes definitions from the trace; recorder per interval.
   Fixes found: a scalar assigned to a formula request was ignored (silent); `rigid` read stale nodes.
3. Keyed reads of moving keys/values: a keyed read that is not by the time is followed through its
   reads (also fixes: a stage write of its key did not touch the sets that read it); moving ones run
   on the sparse integrator; triggers diagnose (no certified crossing); recorder pieces fitted.
4. A setting that reads a moving rate of another set: the sets integrate together in one sparse
   instance, level by level.
5. Collection assignment in a stage: refused with the spec's reason (links fixed; front end refuses).
6. Refusals naming a slice: none left; "(a later slice)" texts get the spec's reason.
7. Port the non-event cases of test_runtime.py / test_timeline.py.

## Done
- 1: declared.py: an endpoint with a request and a priority: each preferred class (cumulative)
  is a claim alone in a tier after all others (oracle `prefs`, ordered as the oracle meets the
  stores: `_first_touch`). Tests: test_solvers.py `common_sink` x4 (closed form + oracle).
- 2: plan.define/original/definitions_of/start_of/reads_ever/expanded_ever, `defined`, `version`;
  moment.Defined, Tx.defined/details (trace detail `defines` = ((name, statement origin), ...));
  run.define/write; record `_defined` (pieces per interval), reader `_Values._value`; occurrences
  freeze what is a formula at the finish; `rigid(flow, held)` reads present values. Collection
  assignment refused with the spec's reason (test_record.py). Tests: test_definitions.py (9).
- Full command after 1-2: 3214 passed.
