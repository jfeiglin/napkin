# Engine ownership and port-readiness gates

The remote Claude tip and the audited baseline were both `6202824d6d567c34ac46da7b018e66a9c28588b3` when `engine_finalized_simple` was created. The owner will arrange the final audit and merge into Claude.

## Follow a transfer

| Decision, in order | Owner and contract |
|---|---|
| What does the authored request mean? | The compiler checks references, units and scales and lowers both authoring forms to Program. |
| Which request, capacity and sharing rule apply now? | Expression evaluation selects the active branches, including enclosing branches after a jump. Allocation owns the permitted directed rates. A declared solver owns its named unknowns. Other flows keep local sharing. |
| How much could move through a given time? | The selected numerical method maintains a held rate or a moving amount primitive. It locates roots and supplies the transferred amount through any accepted cut. |
| Which prefix can count, and which action is next? | The timeline orders coincident causes and accepts a prefix at the earliest applicable switch, bound or event. Proposals beyond that cut confer no credit. |
| What balance is spendable? | Run state owns debits, credits, remainders and last-posted time for each physical store. A stage sees its own earlier writes and commits its postings and trace together. |
| What did the run show? | The recorder retains requested history. The reporter queries that history and its evidence index. Reading a report cannot advance a posting cursor. |

Held intervals accrue rate times elapsed time. Moving intervals use the method's cumulative transferred amount through the accepted endpoint. Materialize a store only for a stage read/write, rate change, group rebuild, occurrence finish, checkpoint or run end. A moment concerning one store must have work proportional to the affected stores. Preserve gross legs for frozen-stock rules. The accounting handoff must identify every retired posting path, its replacement, and the tests that exercise reads, rollback, resume and empty moments.

One engine owner holds `continuous/{integrate,fields}.py`, `engine/allocation.py`, `timeline/{lines,family,component,sparse,declared,run,ways,moment,occurrences,checkpoints,saved}.py` and the run-state writer. Engine stage writes follow accounting. Land allocation on the topic branch before prototyping settlement. If the specification leaves a result open, park that case, collect questions for the owner and continue independent items.

## Cross-method rules

For a rule with multiple implementations, a change covers all affected implementations and a comparison test of the case in the same commit.

| Rule | Implementations or consumers | Comparison |
|---|---|---|
| Select the outgoing branches of a calculation | Component's continuous Field, Sparse's batched evaluation and MovingDeclared's evaluator supply operands to continuous.integrate.far_sides. Re-evaluate through enclosing expressions in dependency order. | tests/engine/test_valve_allocation.py forces both valve spellings, a stock-driven nested switch and a closing valve through all three methods. |
| What a stock at its bound lets through | Lines._lines, Sparse.field, and component.Held.bound_allocation through continuous.fields.Field.rates and engine.allocation.Allocation.bound_allocation | tests/engine/test_port_bound_sharing.py::test_a_store_at_its_bound_allows_equal_gross_flows compares the reference and all three local implementations and a declared solver at empty, full and [0,0] stores. |
| What a value reads | plan.Connected.reads (stage invalidation), record.Recorder.wanted (retained history), program.proofs.Proofs.reads (possible evidence) and timeline.reads.lazily (actual consulted fields) | tests/engine/test_port_read_sets.py checks generated reads against both conservative lists and credits exactly the consulted fields, including keys, predicates and occurrence-scoped fields. |
| Evaluate a numeric expression | Scalar, array and solver-backed evaluators | tests/core/test_arrays.py::test_scalar_and_array_rows_make_the_same_near_band_choices_in_mixed_units and tests/engine/test_comparison_bands.py::test_a_configured_band_applies_to_formulas_and_guards. |
| Local sharing and the scope of declared unknowns | engine/allocation.Allocation.allocated, timeline/network.Instant.settle and timeline/declared.Former.problem build locally permitted rates and declared constraints. | tests/engine/test_claim_order.py::test_a_flow_that_the_solver_does_not_name_keeps_its_local_sharing and ::test_an_outlets_rule_ranks_its_flows_whichever_a_solver_names. |
| Tolerance floors and selected operands | core/comparisons.Comparisons, core/arrays.values, core/evaluation.checked_value, model/semantic exact folding and tests/reference/evaluate.py's independent oracle. | tests/language/test_folded_comparisons.py and tests/model/test_units.py compare named/inline forms, literal offsets, selected rows and equivalent physical scales. |

## Benchmarks

Paths below are relative to scratch/rewrite/b1. Run each individual workload against its pinned baseline, single-threaded BLAS, three alternating pairs. Calibrate a fixed repeat count on short runs so each sample lasts at least one second. Report median paired run-plus-record ratios, raw pairs, separate peak RSS, allocations, accepted/rejected integration steps and physical postings. The individual limit is 1.05. Measure the allocation-only revision separately from the prototype.

| Workload | Script | Prototype arguments | Final arguments |
|---|---|---|---|
| Moving tanks, 12 independent exponential fills | s1-engine/bench_moving_tanks.py | --tanks 12 --hours 12 --method component (repeat with sparse) | same |
| Moving tanks, same 12 fill curves supplied by positive linear compartments | s1-engine/bench_moving_tanks.py | --tanks 12 --hours 12 --compartment --method component (repeat with sparse) | same |
| Independent held pipes | s1-engine/bench.py | — | 30000 |
| Held local network | s2-engine/bench.py | held 3000 3500 48 | held 30000 35000 48 |
| Moving local network | s2-engine/bench.py | moving 3000 3500 48 | moving 30000 35000 48 |
| Event-heavy | s4a-engine/bench.py | 1200 48 12 | 1200 48 12; separately 30000 48 12 once on each revision, limit 1.10 |
| Declared solver | s5-engine/bench.py | — | 3000 3500 1500 |

Production accounting requires correct Component and Sparse accepted amounts including an event cut, and passing moving, held and event prototype measurements. The final performance campaign also includes the declared solver and independent pipes.

## Verification contract

Regular corpus: 300 deterministic seeds, one of eight transformations per seed in rotation. Deep corpus: all eight for each of 2,000 seeds. The full regular suite has a 180-second budget on four workers. For each compared value, use its physical scale in T = atol_factor × own_scale + rtol × abs(reference). Compare point values within 2T and integrated values and everything derived from a level within 10T. Compare times within the crossing tolerance. Compare stages, firings and order exactly through the first decision split explicitly attributed to a matching near-tie. Record the seed and decision and stop that pair there. More than 1% divergent seeds (over 20/2,000 per deep transformation) requires generator repair. Report the first differing observation for failures.

Exercise empty event, naming/inlining, scale-preserving units, split move in an atomic stage, text/builder, source/reloaded artifact, checkpoint/resume and another eligible method. Verify each generated case against the reference domain. Final sign-off also requires the 31 audited reproductions, CLI, artifact-only reports, piano and reservoir comparisons against 8488047, both migration checker negative controls and an inventory of changed test expectations with reasons.

The owner waived the independent rerun of the 44 auditor-held cases. [Historical evidence and expectation inventory](comparison-expectations-0.2.3.md)
