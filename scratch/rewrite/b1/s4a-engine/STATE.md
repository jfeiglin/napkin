# S4a-E state: the engine, part one of S4 (occurrences and time)

Brief: `briefs/s4.md` (S4a-E) with `COMMON-B.md`, `s0-engine.md`, `s1.md`..`s3.md`; `b1/s3-engine`.
Baseline before S4a: `tests/engine tests/core` 1684 passed in 84 s (-n 2).

## Design (decided; the docstrings of napkin/engine/timeline/ hold it)
- plan.py: events, `Trigger` per receiver, `occurrence()` adds an occurrence's values and flows
  (`R.E#n.<name>`, a `Frame` for bare names); `Dynamic` reads (occurrences, `.at(t)`, `since`,
  endpoint flows/actual rate when events own flows); `connect(flows, moving)` reusable;
  `replay(trace)` for readers; S4b parts refused at plan time (`_refuse_parts`, "(S4)").
- ways.py: instances of the four ways; a moment rebuilds the touched sets (family/lines: one new
  instance per level, dead rows in the old; component/sparse: one per set); levels when settings
  read other sets' rates; peek/step/snap/cut interface on family, lines, ComponentWay, Sparse.
- run.py: present `value(name, t, tx)`, `next_moment` (internal events strictly before a moment
  are stepped; at the moment's time they only snap to the bound; the settle solves after stages).
- moment.py: rounds (D5), Tx, statements, commit, settle; occurrences.py: entry (D14), steps,
  retirement, freezing (D7), D6 limits; triggers.py: conditions with bands, rearm rules, contact
  prediction (closed form on lines, `_exact_root` for clocks/one store; curves only for one
  monotone store, else a diagnostic; strict thresholds diagnosed when watched).
- record.py: STATE pieces, occurrence formulas + frozen piece, dynamic reads, partial records keep
  what they need, `key_of`/`unit_of` for occurrence keys.

## Done
- 23 part-one examples in `test_programs.SUBSET`, all equal to their values and the oracle (failures
  too); `same` rel 1e-8 (falling ramp's Radau kink costs 2e-9).
- tests/engine: test_occurrences (300 random vs oracle, 2000 deep; replay; D6 limits; partial
  records), test_trigger_classes (16), test_runtime_events (7), test_timeline_events (4); ported in
  place: test_monotone_crossing, test_rearm, test_switch_at_segment_start, test_timeline_row_facts,
  test_finite_stock_boundaries, test_finite_face_kernel, test_roundoff_properties (+4); test_record
  refusals updated; prepare() returns (values, sizes, ways).
- deleted: timeline rules/steps/readers/checks/sharing/lists/segments (state.py kept for choices.py,
  part two's); tests test_ai_layer, test_moment, test_windows.
- engine+core+program+reference: 2665 passed (96 s); the 6 dormant-listed ports: 24 passed.

## Measured (once, OPENBLAS_NUM_THREADS=1; a test process ran beside it for part of the time)
- bench.py 30000 48 12: build 0.7 s, plan 1.9 s, run+record 866 s, 482,500 starts, 2.9 GB+;
  p0 stock 84 L = by hand. 3000: 41 s; 300: 3.3 s. Time goes to `predict_all` and `conditions`
  (every trigger read at each moment/round: O(N) per moment) and per-occurrence plan growth.

## Final runs
- engine+core+program+reference 2671 passed (96 s); 6 dormant-listed ports 24 passed; random
  event programs (normal + deep) 2310 passed (92 s). Last fix: a contact within the crossing
  tolerance before a known moment is that moment (seed 1533).

## Not done / later
- dirty tracking of triggers; freeing per-occurrence caches (`Occurrences._nodes`, `Moment._paths`);
  assignment of formulas, allocations, collections in stages (refused "(S4)"); endpoint settings on
  an occurrence's own store; a rate read from a moving set (refused S5).
- old test_runtime.py / test_timeline.py keep their non-event cases dormant.
