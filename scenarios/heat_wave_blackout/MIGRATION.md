# Heat-wave recovery comparison

The recovery calculation begins with an observed loss of service at hour zero. The published historical comparison is commit `8488047`, whose archived study ran to 1,800 hours. The new package covers utility clearance, restoration work, cooling, voluntary relocation, device outreach, clinical outcomes and costs. Incident initiation and the conduct that caused it are outside the recovery model. This port compares consequences conditional on supplied incident records.

## Incident records and work

The utility completes isolation and assessment on their own clocks. Safety checks start at assessment. The crew can switch circuits when both isolation and checks are complete. At the standard settings this releases switching at hour 25. A full crew delivers one hour of base work per hour, and the share of service returned is completed base work divided by required base work.

| Input | Effect |
|---|---|
| `incident.hold`, `hold_at`, `hold_duration` | A recorded safety hold pauses switching and inspections until release. |
| `incident.repeat_work` | Hours of repeat inspection booked when a hold begins during the outage. |
| `extra.recorded`, `recorded_at`, `hours` | An independent work order adds a priority inspection during the outage. |

Inspections take priority over repeat work, which takes priority over base switching. Inspection work earns crew wages but returns no additional service. A work order received after restoration adds no work. At the start of each uninterrupted base-switching interval the crew books the remaining work at its one-hour-per-hour rate. If a hold intervenes, the release starts a new interval. An inspection and a repeat-work order use the same one-crew clock. Each interruption changes the work-order revision, so an older scheduled completion cannot close a later job. The final dispatch checks all three physical queues again and changes the crew and supply states together. The null hold and work order describe all three named runs. A response changes the site availability, transport rate and timing of outreach. It does not change the incident record.

## Physical equivalence

The civilian stock and transfer equations derive from the translated draft. An illness or mortality transfer has an individual cap equal to its requested rate. The draft repeated the sum of these caps on a common endpoint. Summing its individual constraints already supplies that bound. The shared admission claim additionally apportions a common intake across the waiting groups, whose shares sum to at most one. The new package retains the individual and shared admission limits. This avoids a rounding-order disagreement between the repeated bounds.

Let `q` be the healthy fraction among residents waiting to relocate privately. Withdrawal is proportional to the two populations, and their death hazards are identical. While anyone remains, dividing the healthy balance by the total and differentiating gives `dq/dt = -illness_hazard × q`. At setup, `q = 1`. The model tracks that fraction directly. The moving rates use `q` and `1 − q`, and requests stop once the pool is empty. The smooth caps use those same fractions through depletion. This yields finite rates when both populations reach zero together.

## Comparisons

The portable test fixture keeps 11 civilian outputs from each corresponding archived row. The legacy publisher rounded to six significant figures and displayed magnitudes below one millionth as zero. All 33 displayed figures agree. The first two responses have no powered formal sites. For them, the separate health and population calculator also agrees at hours 0, 4, 18, 25, 30, 40, 60, 120 and 1,800 with the original numerical acceptance criteria. Powered-site admissions and the projected endpoints are checked against the third archived row.

| New named run | Archived row | Resident-hours without service | Admissions after device power loss | Admissions to powered cooling sites |
|---|---|---:|---:|---:|
| `standard` | `standard_obeys` | 1,950,000 | 23.5491 | 0 |
| `early_cooling` | `early_obeys` | 1,950,000 | 15.9787 | 0 |
| `powered_places` | `early_powered_places` | 1,950,000 | 15.9787 | 1,200 |

The piecewise-linear restoration calculation computes work and service separately from the engine. It feeds analytical cost integrals and population hazard quadrature. The health oracle covers runs with formal cooling sites closed. The historical published reports are retained in `results/`; `readings.md` there is the current model’s report.
