# S6-E state: the engine, what is left before G1 — done

Brief: `briefs/s6.md` (S6-E) with `COMMON-B.md`, `s0-engine.md`; S5 in `b1/s5-engine/STATE.md`.
Baseline: S5 committed (7f3d902), 4,070 live tests. Owner: napkin/engine/ but solve/ (S6-S);
tests/engine/ but solve/ and the four option/run/binary files (S6-F).

## Decisions (the spec's reasons are in the docstrings of plan.py, declared.py, ways.py)
- Priority with a request in a solver: allowed (spec, "Selection order": "A preferred route has
  first access to useful requested work, up to the outstanding claim it serves"); oracle `prefs`.
- Collection assigned in a stage: refused (links fixed for the run; the front end refuses it too).
- A definition lives in the trace (detail `defines`), so any reader reads each definition's time.

## Done
- 1: declared.py: an endpoint with a request and a priority: each preferred class (cumulative)
  is a claim alone in a tier after all others (oracle `prefs`, ordered as the oracle meets the
  stores: `_first_touch`). Tests: test_solvers.py `common_sink` x4 (closed form + oracle).
- 2: plan.define/original/definitions_of/start_of/reads_ever/expanded_ever, `defined`, `version`;
  moment.Defined, Tx.defined/details (trace detail `defines` = ((name, statement origin), ...));
  run.define/write; record `_defined` (pieces per interval), reader `_Values._value`; occurrences
  freeze what is a formula at the finish; `rigid(flow, held)` reads present values. Collection
  assignment refused with the spec's reason (test_record.py). Tests: test_definitions.py (9).
- 3: plan.stepped (by t, keys fixed: Stepped holds names, reads the member's value live) /
  lookup_moves; expanded follows every keyed read (other ones stay a leaf beside their reads);
  connect: moving lookup -> SPARSE; sparse Vector `_lookup`/`_stepped`, `selection` held through
  a segment, `_switch` ends it; collections.selected; record `_lookup` (pieces from reads);
  triggers: moving lookup -> diagnostic; declared: lookup keyed by an unknown refused by name.
  Fixed on the way: `any`/`all` of moving flags were never watched (fired at the horizon); an
  enum formula of a moving value crashed the recorder (`_switches` takes texts).
- 4: ways.build groups a set with the moving sets whose rates it reads (transitive, `grouped`)
  into one Sparse with levels (`current` rates per evaluation); settle adds `moving_sources`;
  `touched_outside` (no moment for rates read inside the instance). Moving declared: by name.
- Status displays run (nothing computed: text for stage C). Refusal texts: no slice named.
- Tests: test_moving_reads.py (13).
- Scale: per-member keyed reads share their collection (plan `_collections`, `_members_part`,
  `lookup_reads`, `fixed_keys`; run `kept_of`/`_index` by shared tuples, `index_for`); 30,000 x
  30,000: plan 7.2 s, run 12.9 s (was quadratic). S1 bench 30,000: plan 7.6 s, run 15.2 s = the S5
  baseline (7.5, 14.7) measured from `git archive 7f3d902`.
- 7: tests/engine/test_runtime.py (20) and test_timeline.py (7) rewritten in place with the
  non-event closed forms (supplies get capacity = request: D15); both can leave tests/dormant.txt.
  Old cases: events already in test_runtime_events/test_timeline_events; outputs, reports, status
  displays, evidence trail -> stage C; flat/hybrid parity, pickles, snapshots, windows, while ->
  retired (D16, old forms); examples -> M.
- Engine side of S6: none needed (S6-F C1: a configuration sets inputs only; a variant or a change
  gives a program of its own).

## Not done / for others
- A where over flows (spec: "a fixed-field filter over an endpoint collection"): engine and front
  end refuse it. A moving declared solver read by another set (or reading one): refused by name.
- Status display: the run accepts it and computes nothing; naming it in a record is stage C's.
- The every-construct file could add a formula assigned in a stage and a moving keyed read.
