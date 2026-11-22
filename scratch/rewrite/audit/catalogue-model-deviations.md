# What changed from the four studies at 8488047

The new branch starts at `8eeffba`. Numerical comparisons use the earlier catalogue at `8488047dbb7eafee1f5582cf59839c6bea0cf8cd`. The water, heat and IV studies ask how repeated disruptions interact with recovery. The strategic study asks how hypothetical AI progress affects two missions over 25 years.

| Study | What an event or output means now | Difference from the earlier study |
| --- | --- | --- |
| Water | A burst of regional requests takes a configurable share of emergency-water dispatch capacity. The fixed policy can add to the backlog. The recovery-linked policy waits for dispatch to clear the backlog before counting the next interval. Recognition, containment, staff capacity and available water affect what gets through. | Historically the repeat event added repair work at particular utilities through retained access. The current event affects regional relief dispatch. A supply or advisory milestone at an individual plant cannot trigger it. Compare emergency water shortfall and delivered volume to see this mechanism. |
| Heat | Each accepted incident pauses crews and adds work. Following a stop order can cut off subsequent incidents at detection. Continued incidents can arrive until containment. The recovery-linked policy waits for all holds to lift and rework to clear before starting its next interval. | The original followed the contractor, its order, the AI and a particular grid job. Here conduct determines whether the repeated interruptions stop. Interruption length and rework are scenario inputs. Civilian protection and the health and economic outcomes are still computed by the heat model. |
| IV fluid | Incoming notices demand serial quality review. Arrivals can follow a fixed calendar or start a new delay when the last review finishes. The release and supply model gates shipments on the backlog already received and preserves the transit time of fluid already shipped. | The original traced access, altered records and the condition of a first lot. The new policy supplies a discrepancy and follows documentation, release and downstream review. A notice carries work. It does not change records or generate a compromised lot. The seven older run names preserve the recovery comparisons with supplied lot conditions. |
| Strategic cyber | A national workforce allocates staff to surveillance and effects. Productivity, shared review capacity, institutional learning and defensive AI affect completed mission work over 25 years. | The historical study estimated completed operations and objective probabilities through detailed stages, plans, channels and target sets. The current workforce model measures baseline-equivalent staff-years. A separate aggregate calculation estimates an operation count using explicit assumptions about workload and availability. The same run name can yield different values and a different sign of the AI effect. |

The strategic count changes direction. Over 25 years, the historical study reported 8,880 effects operations with no AI progress and 5,290 with fast AI progress. The aggregate model gives approximately 6,587 and 7,169 respectively, an 8.83% increase. Fast and slow AI both reach the base scenario’s available-demand ceiling of 288 operations per year. The new count depends on an assumed average burden per case and availability. The historical machinery could change the mix of cases and consume resources over time. The staff-year and count measures answer different questions. [Current strategic results](../../../scenarios/cyber_learning_loop/results/brief.md) · [Historical results](https://github.com/jfeiglin/napkin/blob/8488047/scenarios/cyber_learning_loop/results/brief.md)

## Which event starts the next clock?

| Study | Fixed interval | Recovery-linked interval | Stop and overlap |
| --- | --- | --- | --- |
| Water | Time since the last regional support batch | Time since the regional dispatch backlog cleared | Fixed batches can accumulate. Containment filters new requests, including a request at the containment instant. The event window and maximum count bound the exercise. |
| Heat | Time since the last incident report | Time since all holds lifted **and** crews finished the resulting rework | Fixed holds can overlap. Detection stops an acknowledged policy, while an unconfirmed order allows reports until containment. A held crew resumes after its final hold lifts. |
| IV | Time since the previous notice | Time since review of the previous notice finished | Notices queue and reviewers process them in order. The intake cutoff excludes a notice arriving at the cutoff. Work already received can finish after the cutoff. |

One sampled draw can set the timing and workload for a whole exercise. The same seed is reused when a defender policy changes. See the authored distributions, sample counts and policy pairs in the package briefs. [Water example](../../../scenarios/water_controls_wipe/variants/lumberton/brief.toml) · [Heat](../../../scenarios/heat_wave_blackout/brief.toml) · [IV](../../../scenarios/iv_fluid_shortage/brief.toml) · [Strategic cyber](../../../scenarios/cyber_learning_loop/brief.toml)

## Historical run names and current counterparts

| Package | Historical runs | Current coverage |
| --- | --- | --- |
| Water | `delayed_none` | Same named recovery control in all 16 variants. The numerical comparison covers eight readings at six times. |
| Water | `early_kept`, `standard_kept`, `delayed_kept`, `delayed_kept_human` | The new `support_single`, `support_daily`, `support_frequent` and `support_recovery` pairs compare regional dispatch burden under standard and rapid response. These pairs exercise a different service mechanism. There is no numerical one-to-one pairing with persistent utility access. |
| Heat | `standard_obeys`, `early_obeys`, `early_powered_places`, `delayed_human` | Comparable archived endpoints map to `standard`, `early_cooling`, `powered_places`, and `delayed_cooling`, respectively. |
| Heat | `early_refuses`, `standard_refuses`, `delayed_refuses`, `delayed_obeys` | Compare `fixed_inspections` with `acknowledged_stop` for the effect of conduct at the same defender response. Compare with `rapid_fixed_inspections` for response timing and `clearance_inspections` for recovery-linked arrivals. The intervals, duration and rework are new scenario assumptions. |
| Heat | `delayed_more_protection`, `delayed_powered_places`, `delayed_open_gates` | Delayed cooling with backup, powered places and open access remain separately selectable. Their response assumptions can be combined with the new interruption policies. |
| IV | `near_ideal`, `subpar`, `minimal`, `near_ideal_persistent`, `subpar_persistent`, `minimal_persistent`, `subpar_persistent_human` | All seven IDs remain. Records workload and first-lot condition are supplied in the recovery controls. Three additional named runs vary notice timing and staffing. |
| Strategic cyber | All 12 historical run IDs | AI path, government funding, workforce allocation, defensive adoption and learning are aggregate scenarios. The package guide maps every ID to its current assumption and identifies each material difference in meaning. [Strategic guide](../../../scenarios/cyber_learning_loop/README.md) |

## How to inspect a particular difference

The [interface inventory](catalogue-interface-differences.csv) compares all 19 historical catalogue entries with their current counterparts, including each of the 16 water variants. It lists absent and added names, plus the previous and current metadata when a shared name changed. It covers entities, declared fields and input bounds, root readings, named runs, options and their settings, sweeps, spreads, and comparison pairs. A shared name or identical input default does not establish that two equations are the same. The inventory describes authored declarations and does not run a simulation.

The [recovery comparison](recovery-parity.md) checks observations with compatible definitions. The archived studies and their original briefs remain available at the [pinned source revision](https://github.com/jfeiglin/napkin/tree/8488047dbb7eafee1f5582cf59839c6bea0cf8cd/scenarios). Each current package publishes named-run values in `results/readings.md` and side-by-side comparisons in `results/brief.md`. A sampled comparison reports differences between runs on the same random draws. Its percentiles describe outcomes under the chosen input distributions.

To rebuild the interface inventory, use a clean checkout of the historical commit and the current repository's Python environment.

```sh
python scratch/rewrite/audit/catalogue_interface_inventory.py /path/to/8488047 > scratch/rewrite/audit/catalogue-interface-differences.csv
```
