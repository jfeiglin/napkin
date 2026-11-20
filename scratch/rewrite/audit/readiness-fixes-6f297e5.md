# Readiness audit fixes

The base is `edd90258ed649906467294ab013a458d1a1a85e4` on
`claude/blissful-heisenberg-5me2hn`. Each finding below has a named regression in this repository.
The expected numbers come from the model's equations. The owner will have the auditor run the
independent bundle separately.

## What the baseline did

| Finding | Named test | Baseline failure and expected result |
|---|---|---|
| Reservoir risk | `test_reservoir_counts_80_hours_at_its_reused_threshold` | With maximum steps of 1 and 0.15 h, the gate fired at 39.99999996432431 and 39.999999964324296 h. Both runs held 0.6999999999108105 and counted 0 h. At 0.0025 per hour, climbing from 0.6 to 0.7 takes 40 h. Equal inflow and outflow hold 0.7 for the remaining 80 h. |
| Finished occurrence | `test_finished_stock_rejects_an_authored_nonzero_move` and `test_finished_stock_limits_cumulative_computed_transfer` | A 0.02 L move escaped the guard, as did a 0.02 L/h flow for 1,000 h. They would transfer 2 L over 100 moves or 20 L over the run. The first move must fail. A flow exhausts a 1e-10 L retirement allowance after 5e-9 h. The reference interpreter also rejected a 1e-17 L/h residual even though the entire run transfers only 1e-14 L. |
| Publishing a solver result | `test_publishing_an_idle_route_preserves_its_stock` | The fitted answer published 0.9999999999989999 on a zero route beside a capped 10-million-unit supply. The 10 L (or 10 Wh) stock must still hold 10 after an hour. |
| Solver-owned boundary flows | `test_declared_solver_shares_two_source_to_sink_flows` | Construction refused a provider's first boundary-flow rate. Two 6 L/h requests sharing an 8 L/h cap get 4 L/h each. The independently shared 3 L/h pipe gets 3. |
| Replay identity | `test_cached_replay_validates_breakpoint_time` | An edit expecting the hour-3 stop failed cold and succeeded after caching an hour-2 replay. Both attempts must diagnose the same mismatch. |
| Capacity history | `test_report_follows_a_capacity_first_set_at_hour_one` | Both the pipe and its endpoint reported infinity at hours 1 and 2 after setting the cap to 1 L/h. The initially finite 5 L/h controls passed. An unbounded starting point has no ceiling. At and after the assignment Python, text and JSON must give 1. |
| Lifecycle fields | `test_report_preserves_occurrence_lifecycle_values_and_units` | Reporting raised `KeyError` for `plant.job#0.started`. The start reads 1.5 h. The active and done flags change from true/false to false/true at 2 h. |
| Evidence of a frozen formula | `test_frozen_formula_keeps_its_finish_time_evidence` | The reported 1 L survived completion but its measured input was marked unread. The branch actually taken before retirement supplies that value in full, selected and resumed records. |
| Exact decimal evidence | `test_json_evidence_preserves_the_exact_decimal` | The verifier compared the authored 34.0000000000000001 h with 34.0 h and rejected it. Both JSON spellings of the precise datum must match that value and reject 34 h, in package and shared evidence. |
| Artifact semantics | `test_old_language_artifact_requires_recompilation` | The loader accepted a 0.1.0 program under the new round semantics. The new header says 0.2.0 and the stale header receives a recompilation diagnostic. The binary format is still 3. |
| History work | `test_history_budget_stops_work_at_the_first_excess_piece` | The record stopped at hour 1, but the engine processed all ten scheduled hours. One requested counter fits at hour 0 and its first increment exhausts a one-piece budget. Only hour 1 should execute. |
| Public package loader | `test_load_scenario_accepts_a_package_folder` | Passing a folder raised `IsADirectoryError`. The folder and its entry file must compile to the same artifact and configuration, including for a variant. |
| Starter | `test_new_points_to_the_rewrite_guide`, `test_new_round_trips_backslashes_in_titles`, `test_new_leaves_no_partial_package_on_collision` | The starter advertised the retired guide, its lexer refused a Windows-style path in a title, and a file at `variants` left a new model and style behind. The generated instructions use the rewrite spec, the title compiles back to its original text, and a collision preserves the original directory contents. |

## Rules and mechanisms

- Change 29 uses the closed comparison band `max(rtol, atol_factor) × max(scale, |a|, |b|)` in canonical units. The floor is the quantity's scale, falling back to one declared unit. An alias follows its target, a literal threshold inherits the other operand's floor, and separately declared peers use the larger floor. In-band inverted hard bounds collapse to their midpoint. Exact evidence arithmetic continues to distinguish distinct decimal datums.
- A physical crossing places a single store on the threshold, including an invertible formula of that store. A multi-store comparison refines the incoming trajectory and checks the residual at the canonical time. If a coalesced state cannot meet its comparison band, the diagnostic names the operands. A clock tolerance is measured in hours.
- Change 24b's conservation guard checks authored amounts before rounding. Computed transfers accumulate separately in and out over a stock's retirement, with the cumulative books preserved at a checkpoint. Solver publication preserves zero on an idle coordinate. The integrator's network size can inform integration accuracy. Guards and recorded values each use the protected quantity's scale.
- Spec §“Flows and routes” permits a provider to solve flows between the external endpoints. The planner includes the declared owner when it forms the connected set.
- Change 28 makes replay identity include the expected stops as well as the edits. The artifact header identifies the language semantics under change 27.
- The JSON evidence reader parses the authored token as a decimal. It retains the existing float representation when its printed decimal round-trips exactly, and keeps a Decimal for higher-precision tokens. Comparing claims uses rational magnitudes and exact unit scales. Serialization writes precise values as JSON numbers.
- A named report follows the declaration, committed pieces and actual formula reads, including the reads at retirement. The lifecycle properties belong to their event. An unbounded point followed by a finite one makes two distinct capacity states.
- Spec rule R-A4a-07 limits requested pieces. The running recorder screens prefixes by a conservative upper bound, and uses the same fit, compaction and cutoff as the final record when a prefix might exceed the allowance. The exhausted prefix terminates execution.

## Other places the rules act

The named tests in `tests/engine/test_comparison_bands.py` exercise the six relations, membership, compiler proofs, configured precision, repeated thresholds, aliases and runtime changes of definition. The baseline used exact inequalities in some evaluators and a separate tolerance for solver equalities. It skipped an inclusive guard at an in-band peer, certified a square root from a guard that admits a small negative input, and applied one template member's floor to its neighbours. Alternating member scales must give 1, 7, 1 and 7 L/h. A solver local between 0.30000000005 and 0.3 has the single feasible midpoint 0.300000000025. Initial predicates and historical aliases use the scale at the time of the read, including when the field declaring that scale appears later in the file.

`tests/engine/test_threshold_contacts.py` checks trigger and switch models at 100 and 10,000 times the reservoir inflow. They reach 0.7 L at 0.4 and 0.004 h respectively and count every remaining hour of 120 h and 8,760 h. On the baseline the switched models held 0.6999999999999997. Another case checkpoints the invertible formula `2 × water`. A two-store model with rates `v` and `2v` starts with 1 and 0 L. At `3/v` h the stores must hold 4 and 6 L. Grouping a slow crossing a nanosecond later preserves the additional 3e-9 L. At 200,000 L/h, grouping five nanoseconds later leaves a 0.003 L residual. The baseline accepted the incompatible moment. The diagnostic now names both stores and their comparison band. The draft reservoir also records the risk switch and gate at their common 40 h moment.

`tests/engine/test_audit_inventory.py` covers the same scale errors outside the original reproductions.

| Named test | Baseline failure | Hand result |
|---|---|---|
| `test_a_live_move_keeps_its_amount_when_an_upper_bound_is_large` | A 0.02 L move from 0.04 L left 0 and 0.04. | Both stores hold 0.02 L. |
| `test_authored_zero_move_into_a_finished_stock_transfers_nothing` | A zero move transferred 0.02 L. | The source retains 0.02 L. |
| `test_a_small_inward_rate_releases_an_empty_store_with_a_large_upper_bound` | Sparse gave 0.02 L and MovingDeclared gave 0 L at 1 h. | At input `p + V/(1 h)`, the empty store holds `p × (exp(t) − 1)` in model units. |
| `test_frozen_inventory_uses_its_declared_amount_scale_over_time` | All 30 pairs of scale and transfer rate disagreed with the lifetime limit. | The first excess starts at `0.5 h + 1e-10 × scale/rate`, including when opposing flows balance. |
| `test_local_sharing_keeps_an_idle_rate_zero_beside_a_large_unserved_request` | Local sharing accepted (10,000,000, 1). | The chosen answer (10,000,000, 0) preserves the idle coordinate. |
| `test_a_store_range_inverted_within_the_band_is_a_single_physical_point` | The in-band inverted interval stopped the run. | The physical store holds its midpoint, 0.3000000003 L. |
| `test_numeric_entry_inside_its_range_comparison_band_is_admitted` | Both an input override and an event argument 6e-10 L beyond 0.3 L failed admission. | Both keep 0.3000000006 L within their 1e-9 L band. |
| `test_small_curved_delivery_keeps_its_shape_beside_a_large_store_bound` | The recorded flow was 0.00044445 L/h (Component and Sparse) or 0.000495 L/h (MovingDeclared) at 0.5 h. | A request of 0.001 t² L/h delivers 0.00025 L/h then and has added 1/24,000 L. |
| `test_fitted_formula_in_picolitres_keeps_its_declared_scale` | The fitted midpoint was 0.5 pL. | A value of t² pL at half an hour is 0.25 pL. |

## Existing expectations

- In `tests/test_store.py`, `test_the_key_of_a_log_covers_its_breakpoints_its_edits_and_the_code_that_plays_it` expects removal of recorded stops to change an edited replay's key. In `tests/test_api.py`, the file inventory in `test_the_run_store_reads_the_same_engine_files_as_before_the_api` includes the shared comparison module so changes to the rule invalidate stored records.
- In `test_near_tie_kinds.py`, `test_a_guard_reads_an_in_band_level_as_equal_and_marks_the_decision` now distinguishes inclusive and strict guards. `test_a_discrete_trigger_uses_the_same_band_on_firing_and_rearming` follows that distinction through both firings and resets. `test_only_the_terms_that_decide_an_answer_are_marked` expects the first in-band equality to decide an OR. `test_a_gate_released_within_tolerance_is_marked_in_its_occurrence` and `test_a_split_of_who_is_served_within_tolerance_is_marked_at_its_settling` expect the quantity's reported band. `test_near_ties.py::test_a_firing_within_tolerance_of_its_threshold_is_marked` and `test_report.py::test_the_report_lists_each_near_tie_of_the_run` now expect a 1e-9 band at unit scale.
- In `test_run_report.py::test_the_text_counts_five_near_tie_sources_and_the_json_keeps_every_entry`, the inclusive guard commits twice, at 1 and 2 h. A gap of −1e-11 L is equal at that guard. The test still checks singular, plural and truncation.
- In `test_intervals.py`, `test_a_guard_narrows_its_branch` and `test_a_formula_has_the_interval_of_its_definition_and_a_circle_ends` include the comparison band in the proven inclusive bound. In `test_solvers.py`, `test_a_formula_that_reads_an_enforced_equality_holds_within_the_solvers_tolerance` still requires each equality to hold, and checks its comparison node under the shared rule.
- In `test_monotone_crossing.py`, `test_a_store_that_only_approaches_its_value_triggers_within_its_tolerance` uses rtol × 100 people. In `test_turning_values.py`, `test_a_value_that_touches_its_level_within_tolerance_fires_there_as_a_near_tie` uses rtol × 12 L. In `test_contract.py`, `test_the_engine_locates_a_change_to_the_crossing_tolerance_of_the_configuration` uses the inclusive Boolean's band-entry time, (8 − 5.5/(1 − rtol))/3 h.
- In `solve/test_ranks.py`, `test_a_change_that_moves_the_delivery_onto_the_idle_pipe_is_not_admitted` rejects a perturbation that gives an idle flow a nonzero rate, even at 1e-12 of the problem scale. `test_no_alternative_farther_from_the_targets_takes_the_answers_place` and `test_the_alternatives_are_farther_on_most_problems` use the same unchanged generated candidates and require their idle coordinates to stay zero.
- In `test_frozen_occurrences.py`, `test_a_flow_that_carries_a_rate_at_a_store_of_a_finished_occurrence_fails_then_and_one_at_zero_goes_on` and `test_a_flow_that_joins_a_finished_occurrences_store_fails_when_it_has_carried_the_allowance` now stop a unit rate when it has carried 1e-10 L. `test_a_run_stopped_before_the_write_fails_by_name_when_it_resumes_three_ways`, `test_an_edit_at_a_stop_that_enables_the_write_gives_the_failure_three_ways` and `test_a_shorter_request_finishes_before_the_write_that_fails` use 3 + 1e-10 h for their flow case. `test_a_flow_opened_between_moments_fails_at_its_time_after_a_resume_three_ways` uses that time for a unit flow and 3 + √(20e-10) h for a rate rising as (t − 3)/10. Authored writes still fail at the statement.

- In `test_sizes.py::test_a_large_stock_that_the_solver_drains_takes_its_own_size`, both scale choices now reach zero and satisfy the stock’s closed form, max(0, 1e8 − 2e6 × (t − ln(1 + t))). The physical contact lies between consecutive representable times at 54.007468975618686 h, with amounts on either side of zero. Only that proved crossing admits the correction at an explicitly small scale.

`test_live_and_frozen_reports_at_the_same_time_follow_their_own_reads` exercises a frozen formula and a live report reading the same intermediate formula at 2 h. A zero-hour stage changes its branch after the occurrence finishes. The baseline marked the frozen measured input unread. Both query orders now report the earlier 1 L measurement and the live 9 L fallback with their respective evidence.

`test_a_bounded_move_preserves_both_inventories` exercises both sides of an authored transfer. The baseline accepted a 0.02 L move with zero or 0.01 L available at a source or destination, including a full billion-litre destination where only the source was debited. The move now fails atomically. The two cases with sufficient material and space still move 1,000,000,000 L and 0.02 L respectively. The latter exercises room obtained by subtracting two billion-scale numbers.

### When the history cutoff becomes knowable

A clock-only formula has its full fit on the requested horizon. In `test_a_clock_formula_exhausts_its_budget_on_its_original_fit_before_the_next_stage`, the one-piece record of exp(t/h) ends at 0.625 h and the independent counter stays at zero, whether its first stage was scheduled at 1 or 10 h. On the audit base all stages ran. Fitting separately at each check also gives the wrong mesh. For a mutable input, a write closes its fitting interval. `test_an_unclosed_fit_waits_for_its_inputs_next_write` preserves the cutoff set by that interval. A raw counter can establish exhaustion before it can establish the exact cutoff of a combined request. For example, the same increment at 1 h can accompany an exponential curve whose first excess piece is at 1 or 0.625 h, depending on whether its next input write is at 2 or 5 h. The engine ends work when the committed histories establish the cutoff. This can require executing the write that closes a mutable fit.

The local-sharing sweep caught a publication regression while implementing the rule. With a request of zero, the optimizer left a 1.0622504247956744e-16 L/h numerical residual into a zero-volume junction. Its own declared rate unit supplies the floor that permits correction to zero. The named case is `test_withdrawn_junction_request_publishes_zero_while_other_flows_share` (seed 1094). The same mechanism affected seeds 507, 1047, 1494 and 1598. All 1,500 deep local-sharing seeds now pass. A separately selected exact zero must still be published exactly.

An immutable checkpoint test exposed another intermediate regression. Reconstructing a moving solver at a nonzero inventory changed its absolute integration tolerance and moved a switch from 1.2500000000194236 to 1.249999995163897 h. Sparse and MovingDeclared now use the stable absolute allowance of the quantity and the integrator’s ordinary relative term. `test_a_resumed_run_is_the_run_straight_through_three_ways[tapering]` requires the same state, history and trace in the fresh process.

Two contract-test expectations also follow from the closed band. In `tests/model/test_contracts.py::test_refined_alias_memo_keeps_effective_bounds_nonzero_facts_and_failures_separate`, an inclusive `x >= 0` admits small negative values, so it cannot prove that sqrt(x) exists. The strict comparison can. An inclusive `x >= 1` admits `1 − 1e-9`, so the limits for ln(x) and 1/x include ln(1 − 1e-9) and 1/(1 − 1e-9). `test_refined_alias_memo_keeps_expression_guards_and_impossible_branches` applies the same reciprocal limit to x − y.

The whole-store move tests keep their original zero-inventory expectation. For seven authored transfers of 10/7 L, independent float subtractions can leave the last requested piece 1.332e-15 L short. `test_seven_moves_empty_their_source_across_a_checkpoint` requires exactly 0 L left and 10 L delivered with either resume path. The transaction now accounts for its observed subtraction roundoff across moves. Assignments, edits and reaching the bound reset that allowance. `test_a_positive_shortage_in_the_first_move_is_not_cumulative_roundoff` refuses 0.01000000000001 L from an untouched 0.01 L stock even at a billion-litre declared scale.

The first full clock selection found five disagreements caused by a level switch or bound landing a few floating-point places from an internal clock switch. Seeds 538 and 1732 differed by 0.125 L at 2.25 h. In seed 700 the new drain reverses the store's direction at 3 h, giving 1.625 L at 3.25 h. In seed 1187 both fills switch, giving 3 L at 3.25 h. In seed 1319 the drained tank stays at zero after 1 h. The first implementation gave 1.75, 2.75 and −0.25 L respectively. The shared timeline now groups those independently located contacts at the authored clock, and its departure calculation uses the outgoing clock branch. Three named models in `test_switch_segments.py` cover these outcomes. Each also keeps its original generated seed.

The whole-deep run found a pre-existing bit-for-bit comparison in `tests/engine/test_closed_connections.py::test_more_closed_pipes_change_nothing[local-routes-144]`. Both `edd9025` and the audit branch report the same supply-ring failure when s2.water and s1.water reach their lower bounds. Adding the closed pipe changes the stopping time from 2.8846153846153846 to 2.884615384615385 h on both revisions, one representable time step. The test and its expected equality are unchanged.

## Where the rules live

There are two different comparisons at a contact. `core/comparisons.py` decides the truth of a model predicate in the units of its operands. `Clock.within` compares two times in hours to decide which events belong to one moment. Then the engine must decide the physical branch for the segment leaving that moment. Component, Sparse and MovingDeclared share the bracketed root locator. Component and Sparse also share the calculation of the outgoing branch. MovingDeclared computes a velocity from a solver answer and still selects some branches in its own stepping code. A good review question is whether the timeline supplies the same set of consumed contacts to each of those paths, including after edits and resume. The reference interpreter implements the rules independently so agreement tests exercise both implementations.

The history budget has a similar implementation boundary. `Record.within` decides the cutoff from actual pieces. During execution the recorder must establish that those pieces are final. Adaptive fits whose right endpoint comes from a later write require more care than raw counters or a clock-only curve. The implementation still models parts of the fitter's work in the early budget check. A fitter that directly exposes its committed pieces and its open interval could remove that duplication.

The final grouped-clock cases exercise stages scheduled on either side of an authored switch at 2 h. When the stage is due at 2.0000000001 h, it reads the incoming 1 L/h, the next round reads 3 L/h, and the stock holds 4.9999999998 L at 3 h. An intermediate implementation left Component and Sparse at 1 L/h and delivered only 3 L. Both directions and the MovingDeclared control now pass against the hand result. Independent sets also coalesce a bound with the clock without a scheduled stage.

## Verification

The final engine revision is `cb29d3dbb083d153336e1feae4a024f5b049116a`. The final central and selected deep suites ran in a fixed checkout. Its 1,118 tracked source, test, configuration and rewrite files matched that revision byte for byte.

- Central suite, four workers, store off, `-m 'not deep'`: 10,321 passed, one skipped.
- Last-round deep selection plus the new audit rule files, auto workers: 6,675 passed, in 3 min 46 s. Every seed ran.
- Whole deep suite, auto workers, store off, `-m deep tests`: 23,492 passed, one failed, in 17 min 12 s. This run preceded the last grouped-clock adjustment. Its only failure, local-routes seed 144, reproduced with identical numbers on the base and final engine. The selected suite on the final engine re-exercises the changed clock paths.
- Ruff lint passed. Ruff format checked all 474 files.

### 3,000-place benchmark

The benchmark used 3,500 routes and 1,500 sources in the same environment, with one OpenBLAS and OMP thread, and alternating order. Each pair produced the same sampled values and two solves, at 0 and 24 h. Total service was 3,163.7587 W at 0 h and 3,083.5128 W at 48 h.

| Pair | Order | Base total (s) | Final total (s) |
|---|---|---:|---:|
| 1 | Base, final | 10.554 | 9.952 |
| 2 | Final, base | 10.599 | 9.826 |
| 3 | Base, final | 10.627 | 10.032 |

The median paired total-time ratio was **0.9430**, within the 1.05 limit. The phase ratios were 1.0437 for build, 0.9830 for plan, and 0.9349 for run and record. Build rose by about eight milliseconds in the median pair.

### Lines against edd9025

The count uses `git diff --numstat` and includes this report.

| Area | Added | Removed | Net |
|---|---:|---:|---:|
| Production (`napkin/` and `tools/`) | 1677 | 552 | +1125 |
| Tests and reference interpreter | 2085 | 160 | +1925 |
| Rewrite documents and report | 156 | 8 | +148 |
| **Total** | **3918** | **720** | **+3198** |
