# Differences from the four studies at commit 8488047

This note tells how the four packages of the catalogue differ from the studies of the earlier
catalogue. It records the state of the packages at commit `05dad3c`. The rewrite of the catalogue
starts at commit `8eeffba`. The numerical comparisons use the earlier catalogue at commit
`8488047dbb7eafee1f5582cf59839c6bea0cf8cd`.

The water, heat and IV studies ask how repeated disruptions and recovery change each other. The
strategic study asks how a hypothetical AI progress changes two missions over 25 years.

| Study | What an event or a value means now | How it differs from the earlier study |
| --- | --- | --- |
| Water | A batch of regional requests takes a share of the dispatch capacity for emergency water. An input sets the share. With the fixed interval, the batches can add to the backlog. With the interval after recovery, the next interval starts only when dispatch clears the backlog. Recognition, containment, staff capacity and the available water change how much water the office delivers. | In the earlier study, the repeated event added repair work at some utilities through retained access. The current event changes the regional dispatch of relief water. A milestone of supply or of an advisory at one plant cannot start it. To see this mechanism, compare the shortfall of emergency water and the delivered volume. |
| Heat | Each accepted incident stops the crews for a time and adds work. When the source of the incidents obeys a stop order, the incidents after detection stop. Without it, incidents can arrive until containment. With the interval after clearance, the next interval starts only when all holds end and the crews finish the rework. | The earlier study followed the contractor, its order, the AI and one job on the grid. Here the conduct decides whether the repeated interruptions stop. The length of an interruption and its rework are inputs of the scenario. The heat model still calculates the protection of civilians and the health and economic results. |
| IV fluid | Each incoming notice needs a quality review, one after the other. The notices follow a fixed calendar, or each new delay starts when the last review is complete. The model of release and supply holds the shipments until the review of the backlog that it received. It keeps the transit time of the fluid that it already shipped. | The earlier study followed access, altered records and the condition of a first lot. The new policy supplies a discrepancy, and the model follows documentation, release and the downstream review. A notice brings work. It does not change records, and it does not make a compromised lot. The seven earlier run names keep the recovery comparisons, with the conditions of the lots as inputs. |
| Strategic cyber | A national workforce gives its staff to surveillance and to effects. Productivity, shared review capacity, institutional learning and defensive AI change the mission work that is complete over 25 years. | The earlier study estimated the completed operations and the probability of each objective through detailed stages, plans, channels and target sets. The current workforce model measures staff-years of baseline-equivalent work. A separate aggregate calculation estimates a count of operations from stated assumptions about workload and availability. One run name can give different values, and the effect of AI can have the other sign. |

The strategic count changes direction. Over 25 years, the earlier study reported 8,880 effects
operations with no AI progress and 5,290 with fast AI progress. The aggregate model gives about 6,587
and 7,169: an increase of 8.83%.

Fast AI and slow AI both reach the ceiling of the available demand of the base scenario, 288
operations per year. The new count depends on an assumed mean burden of each case and on the
availability. The earlier model could change the mix of cases and use resources over time. The
measure in staff-years and the count answer different questions.
[Current strategic results](../cyber_learning_loop/results/brief.md) ·
[Earlier results](https://github.com/jfeiglin/napkin/blob/8488047/scenarios/cyber_learning_loop/results/brief.md)

## Which event starts the next clock?

| Study | Fixed interval | Interval after recovery | Stop and overlap |
| --- | --- | --- | --- |
| Water | The time since the last batch of regional support | The time since dispatch cleared the regional backlog | Fixed batches can add up. Containment filters the new requests, also a request at the time of containment. The window of the event and its maximum count limit the exercise. |
| Heat | The time since the last report of an incident | The time since all holds ended **and** the crews finished the rework that they caused | Fixed holds can overlap. Detection stops the reports when the stop order is acknowledged. Without the acknowledgement, the reports arrive until containment. A held crew starts work again after its last hold ends. |
| IV | The time since the previous notice | The time since the review of the previous notice finished | The notices wait in a queue, and the reviewers do them in order. The cutoff of the intake refuses a notice that arrives at the cutoff. Work that the office already received can finish after the cutoff. |

One sampled draw can set the timing and the workload of a full exercise. A change of the defender
policy keeps the same seed. The briefs of the packages give the distributions, the numbers of samples
and the pairs of policies. [Water example](../water_controls_wipe/variants/lumberton/brief.toml) ·
[Heat](../heat_wave_blackout/brief.toml) · [IV](../iv_fluid_shortage/brief.toml) ·
[Strategic cyber](../cyber_learning_loop/brief.toml)

## Earlier run names and their current counterparts

| Package | Earlier runs | Current runs |
| --- | --- | --- |
| Water | `delayed_none` | The same named recovery run in all 16 variants. The numerical comparison covers eight readings at six times. |
| Water | `early_kept`, `standard_kept`, `delayed_kept`, `delayed_kept_human` | The pairs `support_single`, `support_daily`, `support_frequent` and `support_recovery` compare the burden of regional dispatch under the standard and the rapid response. These pairs use a different mechanism of service. No numerical pair matches the persistent access to the utilities. |
| Heat | `standard_obeys`, `early_obeys`, `early_powered_places`, `delayed_human` | The archived endpoints that compare go to `standard`, `early_cooling`, `powered_places` and `delayed_cooling`, in this order. |
| Heat | `early_refuses`, `standard_refuses`, `delayed_refuses`, `delayed_obeys` | Compare `fixed_inspections` with `acknowledged_stop` for the effect of conduct under the same defender response. Compare with `rapid_fixed_inspections` for the timing of the response, and with `clearance_inspections` for arrivals after clearance. The intervals, the durations and the rework are new assumptions of the scenario. |
| Heat | `delayed_more_protection`, `delayed_powered_places`, `delayed_open_gates` | Delayed cooling with backup, powered places and open access are still separate options. Their response assumptions can combine with the new policies of interruptions. |
| IV | `near_ideal`, `subpar`, `minimal`, `near_ideal_persistent`, `subpar_persistent`, `minimal_persistent`, `subpar_persistent_human` | All seven names remain. The recovery runs supply the records workload and the condition of the first lot. Three more named runs change the timing of the notices and the staff. |
| Strategic cyber | All 12 earlier run names | The AI path, the government funds, the allocation of the workforce, the defensive adoption and the learning are aggregate scenarios. The guide of the package gives the current assumption of each name and each important difference in meaning. [Strategic guide](../cyber_learning_loop/README.md) |

## How to examine one difference

The interface inventory compares all 19 earlier entries of the catalogue with their current
counterparts, also each of the 16 water variants. It lists the names that are absent and the names
that are new. When a shared name changed, it gives the earlier and the current metadata. It covers
entities, declared fields and the bounds of inputs, root readings, named runs, options and their
settings, sweeps, spreads and pairs of comparisons.

A shared name or an equal default of an input does not show that two equations are the same. The
inventory describes the declarations that the authors wrote. It does not run a simulation. The
inventory is `scratch/rewrite/audit/catalogue-interface-differences.csv` at commit `ARCHIVE_SHA`.

The recovery comparison checks the observations whose definitions agree. It is
`scratch/rewrite/audit/recovery-parity.md` at commit `ARCHIVE_SHA`, and
[recovery-ports.md](recovery-ports.md) gives its results. The earlier studies and their briefs are
at the [pinned revision](https://github.com/jfeiglin/napkin/tree/8488047dbb7eafee1f5582cf59839c6bea0cf8cd/scenarios).

Each current package publishes the values of its named runs in `results/readings.md` and its
comparisons in `results/brief.md` ([catalogue.md](catalogue.md#the-publisher)). A sampled comparison
gives the differences between runs on the same random draws. Its percentiles describe the results
under the chosen distributions of the inputs.

To make the interface inventory again, do these steps:

1. Make a clean checkout of the earlier commit:
   `git worktree add /path/to/8488047 8488047dbb7eafee1f5582cf59839c6bea0cf8cd`.
2. Make a checkout of the archive commit: `git worktree add /path/to/archive ARCHIVE_SHA`.
3. In the checkout of the archive commit, run the script with the Python environment of the current
   repository:

```sh
python scratch/rewrite/audit/catalogue_interface_inventory.py /path/to/8488047 > catalogue-interface-differences.csv
```
