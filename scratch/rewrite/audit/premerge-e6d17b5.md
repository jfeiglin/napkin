# Pre-merge review of the readiness fixes

This work started at the reviewed `e6d17b5` on `codex/readiness-audit-6f297e5`. The branch was created from `claude/blissful-heisenberg-5me2hn` at `edd9025`, the performance baseline. The two decisions from review were to make fitted piece starts permanent for a request, and to compare the full diagnostic of a failed closed-pipe run with a tolerance on its time alone.

## History budgets

A breakpoint can lie inside a curve that the old recorder was still fitting. In one reproduction, the curve `exp(t/h) + offset` yielded a checkpoint at 1 h under a one-piece budget. A later change of offset made the resumed run report exhaustion at 0.625 h. In the other, with `x = t/h`, the curve `1e10*x + 0.03*exp(-100*x)` fit in one piece over 10 h. Asking for a checkpoint at 1 h made the old recorder end the same request at 0.25 h. These cases and the exact-prefix property live in `tests/engine/test_budget_rule.py`.

The independent cutoff calculation uses the complete record of the identical request and edit log. It sorts the start times of every piece of a value named by the manifest, including duplicate times. With budget B the piece at zero-based index B gives the cutoff. When there is no such piece, the run finishes. Retained formula inputs only count if the manifest also names them. The tests check the reason, the recorded prefix and whether a checkpoint was returned.

`test_budget_cutoffs_follow_the_complete_records_committed_piece_starts` covers 40 seeds, three request shapes and three budgets per request. It compares in-place and serialized resumes, including the edit trace. On the baseline, seven of its eight central seeds failed (0, 1, 2, 4, 5, 6 and 7). Seeds 5 and 7 include a one-piece request that should finish but used to exhaust its budget. The existing `test_fresh_stored_and_resumed_runs_of_a_request_have_one_outcome_and_one_set_of_values` now also checks the unlimited run's cutoff. A separate sweep compared 249 full and selected moving-solver requests, including frozen occurrence fields and edits, with their unlimited records.

The recorder tracks the pieces each producer has actually committed and the start of the next open fit. It updates the count for fields that changed. The former budget checker predicted how a formula would fit and repeatedly compacted old pieces. In `test_repeated_budget_checks_append_only_the_changed_selected_pieces`, 32 and 128 counter writes sent 2,306 and 33,794 pieces through compaction on the baseline. The new counts are 129 and 513, and each run materializes one final record.

Three earlier examples specified the mesh of an open fit. Their new expectations follow from sealing the incoming curve at each reached moment on every path.

| Current test | Changed expectation |
|---|---|
| `test_a_clock_formula_exhausts_its_budget_on_the_first_completed_span` | With hourly ticks, exp(t) takes one piece for the first hour. The next piece starts at 1 h and one tick has run. The old whole-horizon fit stopped at 0.625 h with zero ticks. With the first stage at 10 h, or no stage, the 0.625 h expectation still holds. |
| `test_a_completed_fit_stops_before_the_next_write_to_its_input` | The 1 h and 2 h stages establish the start of the second piece at 1 h. The old mesh stopped at 0.625 h after two ticks and the 5 h offset write. The new run executes one tick and leaves the offset at zero. |
| `test_a_raw_counter_and_a_curve_stop_before_the_next_input_write` | The curve and counter already use two pieces at time zero. The 1 h counter write establishes excess immediately, whether the offset would change at 2 h or 5 h. The old 5 h variant gave 0.625 h, and both variants used to execute the offset write. |

## Physical contacts

At 1 h, a 2 L/h fill switches off as a tank reaches 2 L. The drain takes 1 L/h on the falling side. At 1.25 h the stock must hold 1.75 L. Changing the drain to 1.5 L/h at the 1 h stop gives 1.625 L. MovingDeclared used the incoming fill to choose the branch and left 1.875 L in all three runs, including the in-place and serialized edit paths. `test_consumed_contacts_have_the_same_departure_in_each_engine` checks the contact origin, near-tie, incoming and outgoing rates, and stock. The bound case also runs on Lines, Family and the fixed declared engine.

Two old tests deliberately change which trace entry they select. In `test_a_clock_inside_the_comparison_band_of_a_stage_keeps_its_outgoing_rate` the declared run now attributes the clock switch to `tank.fill`. In `test_a_moving_solver_drains_at_the_incoming_rate_until_the_tank_reaches_two_litres` a switch in the drain's capacity belongs to `tank.drain`. A switch authored in the solver's constraint still belongs to `tank.share`. The same authored flow now has the same contact identity in every engine.

Clock seed 305 caught an intermediate regression. The stock arrived at 4 L and an edit replaced it with 10 L. The shared selector initially applied the old 4 L contact to the new state and reported chattering. `test_an_edit_above_a_located_switch_leaves_the_replacement_stock_on_its_side` requires 9.5 L at 2.25 h on both resume paths. The store hash fixture in `test_the_run_store_reads_the_same_engine_files_as_before_the_api` also loses one entry. MovingDeclared no longer imports the symbolic derivative library to make a private branch decision.

Sparse and MovingDeclared now share the code that locates a switch on their dense trajectories. MovingDeclared keeps its incoming fit private until the solve at the endpoint succeeds. Comparing the cleanup with `8bfcb59` gave 108 byte-identical complete records, including 135 contact entries, and five identical failure records. Twelve instrumented runs across four budgets and three execution paths fitted every incoming span exactly once.

## Comparison scales

At 1e-12 mol/m³ with a declared scale of 1e-12 mol/m³, the equality band against zero is 1e-21 mol/m³. On `e6d17b5` both the engine and the reference interpreter read the bare concentration as positive, then read it as equal to zero after adding zero or naming that sum. `test_a_fine_concentration_keeps_its_scale_in_inline_and_named_arithmetic` requires all three expressions to be positive. It also checks a reversed comparison, an explicit coarse output scale and a coarse independent quantity on either side of a sum.

| Rule test | What the baseline did and what the rule requires |
|---|---|
| `test_a_rescaled_quantity_and_its_literal_threshold_keep_the_same_band` | Both readers treated a 2e-15 L signal as zero after multiplication by 0.001 or division by 1000. Both writings give a band of 1e-15 L, including when the threshold is written in mL. |
| `test_repeated_reads_of_one_quantity_have_the_same_floor_as_a_literal_multiple` | Both readers called `2*x` and `x + alias` positive. Their shared 2e-9 L band contains the result, 1.5e-9 L. In `x + y - alias` the two contributions from x cancel, leaving y positive. The baseline called this zero. |
| `test_a_power_transforms_the_floor_in_the_results_units` | For x and scale both 1e-12, powers 1, 2 and 3 compared equal to zero. Each result exceeds its own band by a factor of 1e9. The square-root control already passed. |
| `test_a_named_choice_reads_only_its_selected_scale_at_the_requested_time` | At 1, 0 and 1 h both readers returned false three times. The selected arm changes from coarse to fine at 1 h. The answers are true, false, true, and the unused division by zero is never evaluated. |
| `test_sparse_expression_uses_the_selected_rows_scale` and `test_sparse_template_filters_each_member_at_its_own_scale` | The array comparison lost the fine rows' floors. Four rows at 5e-11 L give false, true, true, false for its selected arms. In the added Sparse template case, four requests started at 1 L/h. The existing hand-worked rates are 1, 7, 1 and 7 L/h for both the direct and named-formula cases. |
| `test_a_table_key_forwards_the_selected_rows_comparison_scale` | The engine returned false at 1, 0 and 2 h. The selected row changes at 1 h, giving true, false, true. The reference interpreter already gave those answers. |
| `test_an_indexed_occurrence_keeps_the_selected_scale_when_its_formula_freezes` | Both engine paths and the interpreter called the sample zero at every requested time on the baseline. The 1e-12 L sample freezes its fine floor at 1 h. It stays positive after the live source switches to the coarse arm at 2 h, including across a serialized checkpoint. |

The compiler's fixed-input proof made the same scale error. `test_a_never_falls_proof_compares_an_expression_at_its_inputs_scale` caught it certifying that a draining 2 L stock was constant. In `test_a_membership_proof_uses_the_scale_of_every_possible_selected_end`, the lower end holds 2e-12 and the upper end holds zero. The coarse scale admits that interval. The old proof also certified the fine scale and a choice whose selected scale was unknown. `test_a_fixed_gate_selects_the_operand_of_a_reachability_comparison` preserves the analyser's existing conclusion for a closed gate.

The independent expression walk in `tests/core/reference.py` now derives the expected floor from the same authored quantities. In `test_the_values_for_many_instances_are_the_value_of_each_instance`, with `p.b = 10`, the walk previously counted `p.b * 1e-300` as equal to `q(1e-300, 'days')`. In canonical hours the values are 1e-299 and 2.4e-299. Their difference exceeds the new band of 2.4e-308. The random generators keep their seeds.

`test_old_language_artifact_requires_recompilation` now checks that an artifact bearing the previous 0.2.0 language header receives the recompilation diagnostic. The baseline loader accepted it. Language 0.2.1 identifies the changed comparison results. The artifact format version stays the same.

The central suite's unchanged 1,500-expression generator, `test_a_program_gives_what_each_evaluation_gives_on_random_expressions`, exposed a missing input in the first implementation. A Boolean such as `mode == 'open'` can act as a numeric coefficient. The generated evaluator omitted the current mode when resolving its floor and raised `UnresolvedScale`. `test_a_coefficient_used_by_a_comparison_reads_the_current_mode` reproduced it for multiplication, a denominator and a numerator. All three failed on `869f4c7`. The compiler now includes predicates whose values are needed to scale a comparison. The numerical value is identically zero in two of the tests, so only the floor can change the answer.

An additional arithmetic check exposed a failure even at x = 1. The reciprocal `(x - x + 1) ** -1` gave 1, but testing whether it was positive stopped with division by zero. Cancellation had left a zero contribution to the floor. The corresponding division already passed. An exactly cancelled contribution now stays zero through a defined reciprocal. For very large or small scales the code retains the exponent until the band can be evaluated in the result's units. This also preserves a retired formula's floor through a saved checkpoint.

| Additional test | Before and after on the comparison fix |
|---|---|
| `test_finite_comparisons_keep_the_scale_through_large_and_small_intermediates` | The comparison could raise on the reciprocal, raise on a positive or negative power, or lose the floor before a later operation brought it back into range. The scalar, generated and array evaluators now agree on the finite result. |
| `test_a_product_with_a_large_intermediate_floor_can_be_rescaled` | Two large scales overflowed during multiplication and stayed infinite after division. The rational reference interpreter already gave the hand-worked result. The engine now agrees. |
| `test_a_large_floor_gives_a_finite_band_before_comparing` | A floor of 1e310 overflowed before multiplication by 1e-9. Its band is 1e301. |
| `test_a_frozen_formula_keeps_a_large_intermediate_floor_through_checkpoint` | The frozen floor lost its exponent. Restoring and rescaling the formula now gives the original comparison. |
| `test_a_gap_and_band_outside_float_range_compare_at_their_own_magnitudes` | The finite inputs are 3.4e308 apart. They differ with a band of 2e308 and compare equal with a band of 4e308. The difference and band used to overflow before they could be compared. |

Sixteen of the 18 range cases failed on `869f4c7`. The two passing controls and all 16 regressions pass together. The reference model's rational arithmetic covers the product and division forms. Its existing test-language subset excludes the power operator, which the scalar, generated and array tests exercise.

`test_a_trigger_and_its_near_trace_distinguish_extreme_finite_values` and `test_contact_refinement_certifies_an_extreme_finite_gap_against_its_band` extend the same example to triggers and crossing certification. Before the shared comparison, a 2e308 band suppressed the firing and certified an out-of-band contact. A 4e308 band gave the correct trigger outcome but reported an infinite gap and tolerance. The trace now records the actual canonical magnitudes, using decimal text for values outside float range, and retains them through the record codec. Physical crossing searches still use the directed sign of the trajectory.

Collection expressions had another route to the unit-size fallback. For two cells holding 2e-12 and 3e-12 L at a scale of 1e-12 L, the engine and oracle both said their collection sum, minimum and maximum were equal to zero. Writing the same expressions with explicit members gave three nonzero answers. Ten cases in `test_reduction_scales.py` failed on `869f4c7`. The engine now builds the scale expression from the members selected by the same filter, projection and reduction as the value. The oracle independently follows the selected references.

| Collection rule test | Required result |
|---|---|
| `test_a_reduction_compares_with_the_same_scale_as_its_members` | All three reductions differ from zero in both spellings. Excluding a third coarse cell preserves that result. |
| `test_subtracting_a_member_cancels_its_scale_in_a_sum` | Subtracting a coarse member from the sum cancels its contribution, leaving the fine member distinguishable from zero. |
| `test_occurrence_sum_uses_the_members_present_at_the_read` | A sum uses the occurrences present at the requested time, including a frozen field and a later join. |
| `test_an_endpoint_reduction_uses_only_its_present_filtered_flows` | A coarse temporary flow widens the band from 1 h until 2 h. A coarse flow removed by the filter contributes at no time. At 3, 0, 1 and 2 h the comparison returns false, false, true, false. |

That last test also compares two distinct destination stores holding the same amount and checks a temporary flow to `SINK`. On `e2490c1` the engine passed both. The reference evaluator returned true four times for the equal-level stores and raised a type error for `SINK`. It now compares endpoint identities before reading the inventories when a flow filter uses `item.source` or `item.sink`.

## Closed connections

`test_more_closed_pipes_change_nothing[local-routes-144]` reported a supply-ring failure at 2.8846153846153846 h and 2.884615384615385 h. Adding a zero-capacity pipe altered the order of arithmetic by one representable time step. The shared helper for this test and `test_a_closed_pipe_changes_nothing` now compares failure times with the configured absolute crossing tolerance, and the round, kind, owner, part and all details exactly. Successful-run readings keep their existing absolute and relative tolerances of 1e-9. The closed pipe must carry exactly zero. All 2,400 deep closed-connection cases passed this stronger diagnostic check.

## Size

These counts use `git diff --numstat` through the tested code at `83cb8b2`. They include comments and docstrings.

| Directory | Starting revision | Added | Deleted | Net |
|---|---|---:|---:|---:|
| `napkin/engine` | `e6d17b5` | 810 | 796 | +14 |
| `napkin/engine` | `678df65` | 3,546 | 1,593 | +1,953 |
| Rest of `napkin` | `e6d17b5` | 467 | 121 | +346 |
| Rest of `napkin` | `678df65` | 944 | 296 | +648 |
| `tests` | `e6d17b5` | 1,097 | 106 | +991 |

The first budget commit removes five net engine lines. Sharing the departure decision removes 39. The checkpoint and column-read cleanup removes another 22. It returns the already-bounded record when a checkpoint exhausts its budget, uses one append path for lists of pieces, and shares the handling of a pending or failed read between scalar and column evaluation. Sharing the switch locator and simplifying publication removes 16 more. The final engine is 14 lines larger than the review baseline. The extra code resolves selected collection quantities, retains their scales through occurrence retirement and handles large gaps in traces and contacts.

## Performance

Each pair ran `scratch/rewrite/b1/s5-engine/bench.py 3000 3500 1500` on the same machine, with the store disabled and one BLAS and OpenMP thread. The benchmark ran on its own before pytest. Only the printed timing precision was extended. The table gives seconds for build, plan, run and record, and their sum.

| Pair, in execution order | Revision | Build | Plan | Run and record | Total |
|---|---|---:|---:|---:|---:|
| 1 | `edd9025` | 0.192775 | 1.199376 | 9.045283 | 10.437434 |
| 1 | `83cb8b2` | 0.189357 | 1.100930 | 8.652199 | 9.942486 |
| 2 | `83cb8b2` | 0.188387 | 1.129285 | 8.648529 | 9.966201 |
| 2 | `edd9025` | 0.192847 | 1.193907 | 9.078549 | 10.465303 |
| 3 | `edd9025` | 0.200639 | 1.240447 | 9.081376 | 10.522462 |
| 3 | `83cb8b2` | 0.188286 | 1.100444 | 8.701455 | 9.990185 |

The median paired total ratio was **0.9523** against a limit of 1.05. Build took 2.31% less time (0.9769), planning 8.21% less (0.9179), and run and record 4.35% less (0.9565). Both revisions solved at 0 h in round 0 and at 24 h in round 1. The sampled places agreed in every pair, with total service of 3163.7587 W at 0 h and 3083.5128 W at 48 h.

## Verification

The final checks used code revision `83cb8b2` on macOS with Python 3.13.16. Pytest used `NAPKIN_STORE=off`, one BLAS and OpenMP thread, `--no-focused --scenario-selection '' -p no:cacheprovider` and no seed exclusions. The central suite used four workers and the deep runs used `-n auto`.

| Check | Result |
|---|---|
| Central suite, `-m 'not deep' tests` | 10,400 passed, one skipped in 162.89 s. The existing process-pool test reads Linux `/proc`. |
| Selected deep suite, 27 test files | 9,129 passed in 214.98 s. |
| Whole deep suite, `-m deep tests` | 23,547 passed in 833.85 s. Zero failures, skips or seed exemptions. |
| Ruff lint and format, `napkin tests tools` | Lint passed. All 476 files passed the format check. |

The selected deep run covers the round-read selection, the switch and grouped-contact files, the inventory, named-value, comparison-band and threshold-contact audit cases, and the budget, departure, closed-pipe and reduction-scale files. The full deep run uses `-m deep tests` across the repository.
