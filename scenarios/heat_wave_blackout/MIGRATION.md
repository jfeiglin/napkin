# Heat-wave recovery comparison

The recovery calculation begins with an observed loss of service at hour zero. The published historical comparison is commit `8488047`, whose archived study ran to 1,800 hours. The new package covers utility clearance, restoration work, cooling, voluntary relocation, device outreach, clinical outcomes and costs. Incident initiation and the conduct that caused it are outside the recovery model. This port compares consequences conditional on supplied incident records.

## Incident records and work

The utility completes isolation and assessment on their own clocks. Safety checks start at assessment. The crew can switch circuits when both isolation and checks are complete. At the standard settings this releases switching at hour 25. A full crew delivers one hour of base work per hour, and the share of service returned is completed base work divided by required base work.

| Input | Effect |
|---|---|
| `incident.hold`, `hold_at`, `hold_duration` | A recorded safety hold pauses switching and inspections until release. |
| `incident.repeat_work` | Hours of repeat inspection booked when a hold begins during the outage. |
| `extra.recorded`, `recorded_at`, `hours` | An independent work order adds a priority inspection during the outage. |

Inspections take priority over repeat work, which takes priority over base switching. Inspection work earns crew wages but returns no additional service. A work order received after restoration adds no work. At the start of each uninterrupted base-switching interval the crew books the remaining work at its one-hour-per-hour rate. If a hold intervenes, the release starts a new interval. An inspection and a repeat-work order use the same one-crew clock. Each interruption changes the work-order revision, so an older scheduled completion cannot close a later job. The final dispatch checks all three physical queues again and changes the crew and supply states together. The null hold and work order describe the original three named recovery runs. A response changes the site availability, transport rate and timing of outreach. It does not change the incident record.

## Physical equivalence

The civilian stock and transfer equations derive from the translated draft. An illness or mortality transfer has an individual cap equal to its requested rate. The draft repeated the sum of these caps on a common endpoint. Summing its individual constraints already supplies that bound. The shared admission claim additionally apportions a common intake across the waiting groups, whose shares sum to at most one. The new package retains the individual and shared admission limits. This avoids a rounding-order disagreement between the repeated bounds.

Let `q` be the healthy fraction among residents waiting to relocate privately. Withdrawal is proportional to the two populations, and their death hazards are identical. While anyone remains, dividing the healthy balance by the total and differentiating gives `dq/dt = -illness_hazard × q`. At setup the healthy share is one and the ill share is zero. A single flow transfers `illness_hazard × q` from the former to the latter. The two balances therefore sum to one, and the model can read a tiny ill share directly. The request and hard capacity of each group use its own balance. Requests stop once the pool is empty.

## Comparisons

The portable test fixture keeps 11 civilian outputs from each corresponding archived row. The legacy publisher rounded to six significant figures and displayed magnitudes below one millionth as zero. At hour 1,800 all 44 endpoints from the four responses agree with their archived values at that display precision. The first two responses have no powered formal sites. For them, the separate health and population calculator also agrees at hours 0, 4, 18, 25, 30, 40, 60, 120 and 1,800 with the original numerical acceptance criteria. Powered-site admissions and the projected endpoints are checked against the third archived row.

| New named run | Archived row | Resident-hours without service | Admissions after device power loss | Admissions to powered cooling sites |
|---|---|---:|---:|---:|
| `standard` | `standard_obeys` | 1,950,000 | 23.5491 | 0 |
| `early_cooling` | `early_obeys` | 1,950,000 | 15.9787 | 0 |
| `powered_places` | `early_powered_places` | 1,950,000 | 15.9787 | 1,200 |
| `delayed_cooling` | `delayed_human` | 1,950,000 | 30.5753 | 0 |

The piecewise-linear restoration calculation computes work and service separately from the engine. It feeds analytical cost integrals and population hazard quadrature. The health oracle covers runs with formal cooling sites closed. The historical run tables are retained in `results/`. Its `readings.md`, `brief.md` and `source-dossier.json` summarize the current model.

The regular package check runs through hour 1.01 at constant temperature. It moves private relocation to hour zero and device outreach to hour one, and checks both event times, delivered transfers and the opening service loss. Private relocation stands down on an actual restoration occurrence, so the initial pre-outage service value cannot cancel a response that starts at hour zero. The deep tier retains all nine full-horizon property cases and the endpoint comparisons with archived results, alongside the existing work, health and cost oracles. The edited runs include empty cohorts, universal backup, temperatures below the cap and changed hospital parameters. Run both tiers with `python -m pytest -m 'deep or not deep' scenarios/heat_wave_blackout/tests`.

## Inspection schedules

`standard`, `early_cooling` and `powered_places` retain their supplied-incident behavior. `delayed_cooling` uses the historical outreach and site-opening times of 36 hours and the transport rate of 150 people per hour. Its three protection variants enable powered sites, access through the compound's gates, or greater household backup and private moves. These variants use the supplied outage and keep the physical switching workload constant. The historical initiating actions and autonomous interference are outside these runs.

The four delayed-response runs below share the same 1,950,000 resident-hours without service. The facilities open at hour 36, four hours before electricity returns. At 150 people per hour they admit 600 people when powered. Opening the gates makes places available to confined residents within that same transport capacity.

| Delayed-response run | Powered-site admissions | Thermal exposure (resident-hours) | Expected deaths |
|---|---:|---:|---:|
| `delayed_cooling` | 0 | 1,681,100 | 34.0916 |
| `delayed_cooling_with_power` | 600 | 1,680,990 | 34.0888 |
| `delayed_cooling_with_access` | 600 | 1,680,990 | 34.0888 |
| `delayed_cooling_with_backup` | 0 | 1,310,100 | 26.2137 |

| Run | First inspection | Further inspections | Containment |
|---|---|---|---|
| `fixed_inspections` | 26 h | Every 4 h, until the exercise window ends or switching completes | 4 h to detect and another 8 h to contain |
| `clearance_inspections` | 26 h | 4 h after the preceding hold ends and accrued reinspection work clears | Same as the fixed schedule |
| `acknowledged_stop` | 26 h | Same calendar up to the stop order | Stop order acknowledged at detection, 30 h |
| `rapid_fixed_inspections` | 26 h | Same as the fixed schedule | 1 h to detect and another 3 h to contain |

The example window closes at 48 h. The schedule also ends after `report_limit` reports (eight by default, configurable from zero to 64), including any report prevented by containment. An acknowledged stop order withdraws follow-up reports from the detection time. In the unconfirmed case reports can continue until containment. In every case the crews finish the work already admitted. The clock reads `incident.first_report`, `window_end` and `interval` in hours. `inspection_duration` sets the length of a safety hold and `inspection_work` sets the additional crew-hours for each admitted report. Detection and containment are configurable delays from the first scheduled report. A report exactly at containment is prevented. A report exactly at the window end or after switching finishes is omitted.

A hold suspends new switching while preserving service already restored. Overlapping holds count separately. When the last hold ends crews inspect the remaining work and can resume. A clearance-based follow-up waits for the actual work queue to empty before starting its clock. The calendar can tick while that work is still underway. Completed work and work remaining must add to the hours of reinspection that have entered the queue.

The named runs use a four-hour interval. The `inspection_spacing` spread draws three PERT inputs once per realization. Minimum, mode, and maximum are 2, 4, and 6 hours for the interval, 1, 2, and 3 hours for the hold, and 0.5, 1, and 1.5 crew-hours for the inspection workload. Four paired draws, starting from seed 41, reuse all three values across ordinary containment, expedited containment, and acknowledgement of the stop order. The spread settings and distribution are in `brief.toml` and `spreads/inspection_spacing.json`. These are illustrative exercise conditions.

Private relocation support counts people away once for both its rate and capacity, with a physical lower bound of zero. On the previous model, perturbing empty ledgers down two floating-point steps could turn that count into a negative subnormal. The overlap regression runs both signs of the ledger probe.
