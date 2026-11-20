# Tests of round reads, switch times and stored requests

## The rule on 678df65

Before either runtime changed, the first version of the new rule test gave **26 failed, 1 passed, 44 deselected** on `678df65`. Both runtimes stopped on the same-round read. For example, request seed 0 raised the garden's request at 2 h. The two stages should read 5 L/h and the next round and later read should get 35/9 L/h. Both runs stopped at the read of `tank.main.actual_rate`. The clinic stopped at `tank.clinic.actual_rate`, and the staffing stage at `office.staffing.care`. Replaying the expanded test file on the same unmodified commit gave **42 failed, 7 passed, 44 deselected**. [Round rule tests](../../../tests/engine/test_round_rate_reads.py)

| New test | Answer and reason |
| --- | --- |
| `test_stages_and_firings_read_the_rates_of_their_round`, `test_more_rounds_with_writes_and_changes_of_their_own` | The changing stage and its peer read the incoming share. The stage after zero hours reads the new one. Another stage reads one hour later. Seeds 0 and 1 cover each kind in the central suite. Seeds 2–45 supply 44 more cases. Requests, capacities, priorities, moves, store writes, flow starts and finishes, firings, switched and keyed requests, moving rates, legs and served fractions use hand-worked answers. Each model runs in both runtimes, straight through and with a stopped edit. The engine also reloads the edited checkpoint. |
| `test_clinic_and_garden_share_again_after_the_stages` | At 2 h the clinic still reads 4 L/h. At the next re-share it receives 6 × 4/(4 + 6) = 12/5 L/h. The zero-hour stage and the record both give that answer. |
| `test_the_next_staffing_delay_uses_56_hours` | The stage at 1 h reads 70 h from the last solve. The staff-hours cut from 100 to 80 makes the ensuing delay 0.7 × 80 = 56 h. Completion is at 57 h. |
| `test_an_endpoint_rate_in_setup_still_stops_by_name` | Setup has no previous share. Both runtimes stop at 0 h and name the endpoint or the flow supplying it. |
| `test_an_outside_pipe_reads_the_incoming_side_of_a_switch_or_key` | The SOURCE-to-SINK pipe reads 4 L/h when the stage arrives and 1 L/h after the share. Cases cover the clock, a keyed row, one moving store and two stores meeting at 102 L under strict and inclusive comparisons. Halving the slow fill at the stop leaves 102½ L at 3 h. |
| `test_the_rate_shared_when_a_switched_fill_meets_its_bound` | The tank holds 2 + 5 + 3 = 10 L at 2 h. The stage reads 3 L/h. The next round reads zero at the contact and 3 L/h in the case scheduled just before it. |
| `test_a_new_request_formula_changes_the_rate_after_this_round` | Redefining a request at 2 h leaves its arriving value 1 + 2 = 3 L/h. The next share gives 1 L/h. |
| `test_a_firing_reads_the_sharing_at_a_tanks_bound` | At a full or empty tank the firing gets the newly closed pipe's zero rate. A firing before the contact gets the rate still being carried. |

## Existing expectations changed from 678df65

The identifiers below are the current test names. The changes implement item 27. Ordinary fields still reflect earlier writes. [Rounds and Reading a result](../spec.md) · [Changes after G0](../PLAN.md)

**Flow rates and shares** · [test_stale_rates.py](../../../tests/engine/test_stale_rates.py)

| Test | What it now requires |
| --- | --- |
| `test_a_rate_after_a_change_of_its_request_reads_as_the_round_began` | After changing 3 to 2 L/h, the stage reads 3 L/h. |
| `test_a_formula_reads_the_same_published_rate` | Doubling that shared rate gives 6 L/h. |
| `test_a_later_stage_of_the_round_reads_the_same_rate` | Either age order of the cut and copy stages gives 3 L/h. |
| `test_a_store_that_meets_its_bound_shares_again_after_the_stages` | At 4 h, 8 L have drained at 2 L/h. The stage reads 2 L/h and the next round reads zero. |
| `test_a_flow_that_leaves_and_its_neighbor_keep_their_round_rates` | Both pipes keep 1 L/h through the finishing round. The surviving pipe then gets 2 L/h. |
| `test_a_flow_that_joins_reads_zero_until_its_first_share` | A new flow had no share when the round began and reads zero. |
| `test_an_allocation_set_in_the_round_takes_effect_at_the_next_share` | Both pipes are active. The preferred one keeps 1 L/h during the priority change and gets 2 L/h at settlement. |
| `test_a_flow_from_source_to_sink_is_shared_again_after_the_stages_too` | The outside pipe's stage reads 3 L/h after changing its request to 2 L/h. |
| `test_a_rate_that_follows_the_time_reads_at_the_current_time` | At 2 h both stages read 2 L/h, including the stage that cuts capacity to 1 L/h. |
| `test_a_rate_that_reads_another_sets_rate_keeps_its_share` | A downstream meter still sees the previously shared 3 L/h. |
| `test_an_edit_at_a_stop_keeps_the_round_rate_in_place_and_in_a_fresh_process` | Emptying the tank at the stop leaves the arriving rate at 3 L/h on both resume paths. |
| `test_a_flow_started_by_a_firing_shares_after_the_next_rounds_stages` | The next round's stages read 2 L/h. Its re-share gives each pipe 1 L/h. |
| `test_rates_through_the_round_agree_with_the_oracle`, `test_an_edit_at_a_stop_before_the_read_is_a_change_of_the_round_in_place_and_resumed`, `test_more_rates_through_the_round_agree_with_the_oracle` | The same generated models now complete legal reads and compare the resulting fields. Reading during setup still requires a named failure. |

**Moments and firings** · [test_clock_moments.py](../../../tests/engine/test_clock_moments.py)

| Test | What it now requires |
| --- | --- |
| `test_a_branch_on_the_time_at_a_stage_s_time_changes_the_next_rounds_rate`, `test_a_keyed_read_at_its_key_time_changes_the_next_rounds_rate`, `test_a_branch_on_a_store_whose_crossing_falls_on_a_stage_s_time` | At the switch, key or level crossing, the stage gets 1 L/h. The next round gets 3 L/h. |
| `test_a_switch_that_holds_its_store_changes_its_rate_after_the_stages` | On reaching 2 L the stage reads 1 L/h. The new share holds the tank at zero flow. |
| `test_a_firing_reads_the_shared_rate_after_an_earlier_firing_started_a_flow` | Both the capture and the start argument use the preceding re-share's 2 L/h. |
| `test_a_stop_at_a_switch_keeps_the_incoming_rate_in_place_and_in_a_fresh_process` | Both resume paths give the arriving 1 L/h. |
| `test_an_assertion_reads_the_settled_state_of_its_round` | The 2 L/h case satisfies the assertion. The 3 L/h case stops on the assertion. |
| `test_a_moment_s_own_changes_and_every_reader_agree_with_the_oracle`, `test_an_edit_at_a_stop_before_the_read_agrees_in_place_and_resumed`, `test_more_moments_and_readers_agree_with_the_oracle` | The original seeds compare values, times and model failures across the full runs. Mismatches identify the path. |

**Solvers, guards and local sharing**

| Tests | What they now require |
| --- | --- |
| `test_a_stage_reads_the_last_solve_after_it_changes_an_input`, `test_a_later_stage_of_the_round_reads_the_last_solve` | The direct read gets 70 h and the doubling formula gets 140 h. The copying stage gets 70 h. [Engine solver tests](../../../tests/engine/test_solvers.py) |
| `test_a_stage_reads_the_result_of_the_last_solve`, `test_a_formula_reads_the_result_of_the_last_solve`, `test_a_read_after_a_write_in_the_same_stage_uses_the_last_solve` | Direct, formula and same-stage reads all get the previous 70 h. `test_the_result_can_be_read_once_it_settles` keeps its 56 h answer with the renamed fixture. [Reference rounds](../../../tests/reference/test_rounds.py) |
| `test_a_stage_guard_reads_the_result_of_the_last_solve`, `test_a_flow_that_joins_in_the_round_is_counted_at_the_settlement`, `test_a_store_that_meets_its_bound_keeps_its_rate_until_the_settlement` | The guard sees 70 h and executes. The joining flow leaves the endpoint at its published 3 L/h. At the emptying time of 8/3 h the stage reads 3 L/h. [Reference rounds](../../../tests/reference/test_rounds.py) |
| `test_22_round_start_result` | Ruling 22 now expects the stage to copy 70 h and the record to give 56 h at that time. [Reference rulings](../../../tests/reference/test_rulings.py) |
| `test_local_sharing_at_every_moment_is_the_oracles`, `test_an_edit_at_a_stop_before_a_read_shares_as_the_oracle_does`, `test_more_networks_share_at_every_moment_as_the_oracle_does` | The shared comparison accepts a before-first-share error during setup. Legal reads elsewhere must give the shared value. The generator, conservation checks and tolerances stay the same. [Local sharing](../../../tests/engine/test_local_sharing_rule.py) |
| Added `test_a_stage_reads_the_moving_staffing_result_at_its_own_time` | The stage sees its moving 56 h result, then the next share gives 28 h. The existing watched-condition tests keep their crossing expectations. [Watched reads](../../../tests/engine/test_watched_reads.py) |
| Added `test_setup_cannot_read_a_declared_result_before_its_first_solve`, `test_a_leg_reads_its_carried_rate_at_a_switch_of_its_request` | Setup names the result it cannot yet supply. At a 3 L store crossing the leg reads 1 L/h in the stage and 2 L/h in the record. [Reference rounds](../../../tests/reference/test_rounds.py) |

## Four reduced models on 8cc9b71

Each reduced model failed before the follow-up runtime changes. The original seeded models use the same generators as on `678df65`. The quantities below are litres. The original random model and its reduction can take different numerical steps. [Switch segment tests](../../../tests/engine/test_switch_segments.py) · [Original clock generator](../../../tests/engine/test_clock_moments.py)

| Seed and reduced test | Hand-worked answer | Observed on 8cc9b71 |
| --- | --- | --- |
| 412 · `test_fill_slows_when_the_tank_reaches_one_litre` | Filling at 1 L/h gives 1 at 1 h. Another quarter hour at ½ L/h gives 9/8. | 0.9963299999999997 at 1 h. The original seed disagreed straight through and on both edited paths. |
| 597 · `test_finishing_a_drain_sends_water_back_across_the_switch` | The store has 17/3 at 2 h, returns to 6 at 20/9 h, then gains ½ L/h, giving 433/72 at 9/4 h. | 6.012851623365061 at 9/4 h. The original seed disagreed straight through. |
| 1923 · `test_an_edit_releases_a_full_tank_and_its_fill_slows_at_one_litre` | An edit empties the 8 L tank at 2 h. At 3 L/h it reaches 1 at 7/3 h. At 2 L/h it reaches 4/3 at 5/2 h. | The reduced case gave 1.3332688149149399 at 5/2 h. The original seed gave 1.321100000000677 on both edited paths. |
| 2027 · `test_the_fill_switches_when_the_drain_fires` | The store reaches 8 at 3 h. Its 2 L/h fill balances its 2 L/h drain through 7/2 h. | 7.999994754305913 at 3 h. The original seed disagreed straight through. |

On `8cc9b71`, the nine former missed-stop seeds **277, 328, 516, 541, 547, 549, 1488, 1701 and 1977** agreed straight through and on both edited paths. So did **242, 369, 1293 and 1748** on this host. Each of **412, 597, 1923 and 2027** now agrees on all three paths as well. Central seed **135** gave 7.00000077823974 L in place of 7 L at 1 h on the original and first-round implementations. Its original tolerance now passes. The chattering tank below is hand-built and has no seed.

## Added tests for switch times

The timing tests use a located switch or bound and an independently scheduled moment. Grouping includes both ends of the crossing tolerance. The direct store read gets the bound, the arriving stage gets the previous rate, and the next round gets the new one. [Changes after G0, items 10 and 27](../PLAN.md)

| New test or tests | Hand-worked observation |
| --- | --- |
| `test_a_component_trial_keeps_the_branch_and_reads_its_trial_state`, `test_sparse_template_rows_keep_their_own_branches_and_trial_values` | A trial at 4 L gives 4 L/h on the held branch. Four sparse rows at the same trial level give 4, 7, 4 and 7 L/h according to their own starting sides. [Switch segment tests](../../../tests/engine/test_switch_segments.py) |
| `test_a_located_switch_belongs_to_the_scheduled_moment_only_inside_its_time_band`, `test_a_clock_switch_and_an_independent_bound_both_reach_the_same_stage`, `test_an_internal_solver_endpoint_cannot_hide_a_bound_in_the_rest_of_the_time_band` | Offsets of −2, −1, 0, +1 and +2 tolerances distinguish the closed timing window from two separate moments. A clock switch and an independent bound both get entries. A numerical step ending at 1 + 1/64 h cannot hide a bound at 1 + 3/64 h within the 1/16 h window. [Switch segment tests](../../../tests/engine/test_switch_segments.py) |
| `test_a_segment_can_leave_a_switch_and_return_to_it`, `test_nearness_in_litres_cannot_make_a_later_switch_due`, `test_nearness_in_litres_cannot_close_a_pipe_at_an_uncrossed_bound` | The parabola 1 + t − t²/2 returns to 1 L at 2 h. After the fill changes the level is 19/32 L at 9/4 h. In the slow-fill cases a gap of 2 × 10⁻⁹ L still puts the physical event outside the timing window. [Switch segment tests](../../../tests/engine/test_switch_segments.py) |
| `test_a_falling_request_reaches_zero_without_spending_negative_water`, `test_an_authored_negative_request_on_the_new_side_still_fails` | The positive part of 1 − t delivers 3/8 L by ½ h and ½ L by 1 h, then stops. An authored switch from +1 to −1 L/h at 1 L stops the run and names the pipe. [Switch segment tests](../../../tests/engine/test_switch_segments.py) |
| `test_a_moving_solver_drains_at_the_incoming_rate_until_the_tank_reaches_two_litres` | A 4 L tank drains at 2 L/h to 2 L at 1 h, then at 1 L/h to 1 L at 2 h. Covers a solver constraint, a capacity and a keyed row, filtered recording and both resume paths. [Declared switches](../../../tests/engine/test_declared_switches.py) |
| `test_a_bound_on_either_side_of_a_scheduled_stage`, `test_a_bound_grouped_with_an_edit_keeps_the_edit_and_timing_entry`, `test_the_closed_ends_of_the_timing_window_report_an_exact_line_contact` | The six ways cover offsets −2, −½, 0, +½ and +2 tolerances. A separate gauge follows 3t. A stopped edit wins at the grouped bound on both resume paths. Exact line contacts at ±1 tolerance get a report, and the adjacent float beyond the window falls outside. [Grouped contacts](../../../tests/engine/test_grouped_contacts.py) |
| `test_two_contacts_in_one_timing_window_can_straddle_an_interior_check` | Both roots of one accepted long step are available to the scheduler when an interior check divides their timing window. [Radau tests](../../../tests/engine/test_radau.py) |

**SOURCE-to-SINK flows** · [Round rule tests](../../../tests/engine/test_round_rate_reads.py)

| New test or tests | Hand-worked observation |
| --- | --- |
| `test_an_outside_clock_switch_without_a_stage_has_its_own_rate_history`, `test_an_outside_rate_at_a_nonlinear_clock_switch_is_the_new_branch` | Both t compared to 2 h and t² compared to 4 h² switch the rate from 4 to 1 L/h at 2 h. The record has the new rate at the switch. |
| `test_an_outside_switch_within_rounding_of_a_stage_uses_that_moment`, `test_two_outside_switch_locations_on_one_pipe_are_reported_at_their_moment` | One switch within 5 × 10⁻⁹ h of the stage gives 4 L/h before and 1 afterward. Two independent switches either side of 2 h give 10 then 4 L/h, with two located times in the report. |
| `test_a_curved_store_switches_an_outside_pipe_on_its_trajectory`, `test_an_outside_table_reads_the_row_on_each_side_of_a_moving_store_key` | The levels t² and exp(t) switch the outside pipe at 1 and ln(2) h. The keyed cases follow t² upward and 2 − t downward through the 1 L key. They give 4 then 1 L/h while rising and 1 then 4 while falling. |
| `test_a_watched_condition_fires_when_an_outside_rate_changes_at_its_own_switch`, `test_a_deferred_delay_reads_the_outside_rate_just_shared_at_its_switch` | The watched condition fires at 2 h. The new 1 L/h gives a one-hour delay and completion at 3 h. |
| `test_an_outside_pipe_keeps_the_shared_side_until_a_later_contact` | A later stage and record retain the new side after a grouped switch and on either resume path. Constant requests give 1 L/h, and the moving request gives 1.01 L/h at the later read. |

## Existing expectations and fixtures changed from 8cc9b71

The run store now answers an identical request from its own entry. A different horizon, selected set of values or piece budget runs independently. A hit restores the caller's manifest order. [Changes after G0, item 28](../PLAN.md)

| Test or tests | Reason for the change |
| --- | --- |
| `test_two_builds_of_one_request_have_one_key_and_a_different_request_has_its_own` | The request belongs in the run key. A change to its horizon or recorded values gives a different key. [Keys](../../../tests/engine/test_key.py) |
| `test_a_window_that_the_stored_run_lacks_runs_again`, `test_each_selected_value_and_the_full_record_have_their_own_entries`, `test_a_shorter_request_runs_to_its_own_horizon` | Each changed request misses once. A 2 h record excludes the 3 h event and a single-value record holds only its own selection. [Run store](../../../tests/test_store.py) |
| `test_a_new_budget_runs_once_and_keeps_its_stop` | Replaces both `test_a_request_with_a_budget_is_cut_from_the_stored_run_as_a_fresh_run_would_be` and `test_a_record_that_its_budget_cuts_is_not_stored_and_a_wider_cut_run_gives_way_to_the_request`. The changed budget misses once, stores its named failure and hits on repetition. [Run store](../../../tests/test_store.py) |
| Added `test_only_the_same_request_hits_with_its_requested_manifest_order` | Each distinct horizon, selection, budget, “everything” flag or duplicate-key request gets its own first miss. Reordering an identical selection hits and returns the requested order. [Run store](../../../tests/test_store.py) |
| `test_fresh_stored_and_resumed_runs_of_a_request_have_one_outcome_and_one_set_of_values`, `test_an_edit_after_the_horizon_of_a_request_adds_no_ledger` | Compare fresh, cold, warm and resumed executions of the identical request. A 1 h record holds 8 L and a zero edit ledger in two pieces. The later withdrawal appears only in the longer run. [Budget rule](../../../tests/engine/test_budget_rule.py) |
| `test_a_narrow_record_agrees_with_the_full_one_and_holds_nothing_else`, `test_a_ledger_reads_the_books_of_the_store_whatever_the_request_names`, `test_a_record_holds_at_most_its_budget_and_agrees_with_the_whole_run_before_its_end` | Each actual request checks its own selected paths, ledgers, unavailable values and piece budget. The cross-request cache-cut comparisons are gone. The edited ledger still reads 0 and −1 L. [Record claims](../../../tests/engine/test_record_claims.py) |
| `test_the_run_store_gives_the_same_values_cold_and_warm_at_each_horizon`, `test_the_run_store_gives_the_same_failure_cold_and_warm_at_each_horizon` | Each horizon is run and hit separately. Formula values, unavailable intervals and named membership failures match the corresponding fresh run. [Formula failures](../../../tests/engine/test_formula_failures.py) · [Membership](../../../tests/language/test_membership.py) |
| `test_a_shorter_request_finishes_before_the_write_that_fails` | The 2.5 h request completes and can be read again. The longer request still fails on the protected write at 3 h. [Frozen occurrences](../../../tests/engine/test_frozen_occurrences.py) |
| `test_a_record_of_a_keyed_read_alone_reads_as_a_record_of_every_value` | Each single-value request warms its own entry before checking its independently worked row values. [Keyed records](../../../tests/engine/test_keyed_records.py) |
| `test_the_endpoint_of_a_store_that_only_the_flows_of_an_event_meet_is_a_value_of_every_run`, `test_an_endpoint_that_a_flow_meets_through_a_parameter_and_a_distribution_of_an_event` | Each endpoint and distribution is read from its single-value warm entry as well as its other run paths. The delivery rates and distribution answers are unchanged. [Named values](../../../tests/engine/test_named_values.py) |
| `test_a_request_has_one_outcome_cold_warm_and_with_a_later_edit`, `test_a_stop_of_the_log_at_or_after_the_end_that_the_budget_gives_need_not_come` | Both compare a request with its own warm hit after also storing a wider request. Earlier-budget endings still precede later stops and edits. [Acceptance across paths](../../../tests/acceptance/test_rules_across_paths.py) · [Session](../../../tests/test_session.py) |
| `test_the_run_store_reads_the_same_engine_files_as_before_the_api` | The expected code closure now includes the derivative functions and region planning code used by the engine. The original case-insensitive file lookup pulled in nonexistent module names `Problem.py` and `Solver.py` on this host. [API](../../../tests/test_api.py) |
| `test_a_tank_that_empties_stops_with_chattering_at_the_time_that_it_empties` | This hand-built tank empties at exactly 105/13 h. The two opposing sides repeatedly reverse its drift. Both earlier commits finished without the diagnostic on this host. The test now requires the tank and both outflows by name in the failure. [Chattering](../../../tests/engine/test_chattering.py) |
| `test_a_run_of_steps_too_short_to_tell_apart_stops_the_run_as_stalled` | The independent three-short-steps diagnostic uses three known accepted steps of half a crossing tolerance and checks their timestamp and names. The empty-tank case above exercises physical chattering directly. [Chattering](../../../tests/engine/test_chattering.py) |
| `test_a_material_bound_violation_stops_the_run_at_once` | Its nonswitching case injects the violation at the actual 200 h cutoff when the forecast looks one tolerance farther. The named failure and single injection remain required. [Cumulative integration](../../../tests/engine/test_cumulative_integration.py) |
| Added `test_planning_a_sum_visits_its_members_once` | Expanding a sum visits each reduction once, finds the 80 underlying stocks and gives 80 × 2 = 160 L. [Collections](../../../tests/engine/test_collections.py) |

### Additional regressions during final verification

| Test | Hand-worked observation |
| --- | --- |
| `test_a_grouped_clock_switch_stays_consumed_through_two_short_subsequent_waits` and `test_rebuilding_a_moving_solver_keeps_a_clock_switch_that_the_previous_moment_grouped` | A switch grouped just before 2 h lowers a rate from 4 to 1 L/h. Two positive waits remain before its raw 2 h contact. The four reads give 4, 1, 1 and 1. No-op request writes and a checkpoint between the waits preserve the single trace entry. [Component and Sparse](../../../tests/engine/test_switch_segments.py) · [Declared solver](../../../tests/engine/test_declared_switches.py) |
| `test_a_declared_limit_falls_to_zero_on_its_incoming_segment` | A clock or a 1 L/h metering store lowers a limit from 1 L/h to zero over the first hour. Integrating the triangle gives 3/8 L at ½ h and ½ L at 1 and 2 h. Trial evaluations and the numerical Jacobian can approach the switch from the feasible side. [Declared solver](../../../tests/engine/test_declared_switches.py) |
| `test_a_new_switched_request_keeps_its_moving_arithmetic_in_the_record` | Replacing a smooth request with a switched moving expression gives 6.5 L/h at 1.5 h. The test checks six observation times against both the hand calculation and the exact interpreter. [Outside flows](../../../tests/engine/test_round_rate_reads.py) |
| `test_one_read_samples_only_its_moving_set_and_a_stop_keeps_the_samples` | Two independent sets move. One reader at 2 h and the other at 3 h require two samples in a straight run. A breakpoint materializes the unread set for its saved state. Both resume paths then require only the 3 h sample. The eager version took eight. [Publication cost](../../../tests/engine/test_switch_segments.py) |
| `test_a_departed_moving_flow_counts_in_the_opening_total_and_its_next_delay` | A flow finishing in the round still contributes to its opening endpoint total of 5 L/h. The settled endpoint gives 2 L/h and the result-dependent delay completes at 4 h. The same values hold straight through and on either resume path. [Membership and delay](../../../tests/engine/test_switch_segments.py) |
