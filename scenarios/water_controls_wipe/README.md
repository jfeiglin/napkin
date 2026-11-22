# water_controls_wipe

[Main file](model.scn) · [Shared model](water.scn) · [Research note](evidence/research.md) ·
[Shared tests](tests/)

`water_controls_wipe` is a package with one variant for each place. Each variant follows the real water systems of one
place. This folder holds what the places share: the main file `model.scn`, which uses the module
`water.scn`, and the package's evidence, units and tests. Each place's folder (`variants/<place>/`) holds
its own systems, the sales between them, its own evidence, stylesheet, brief settings, tests and
published results. The package runs as its variants: `water_controls_wipe:<place>` names the variant of a place.

## How service recovers

The initial incident time and each participating system's exposure determine when its controls stop
responding. Operators draw on usable storage and start manual production after their activation
delay. Sellers serve their own customers before exporting water. Shared crews and replacement parts
work through the outstanding jobs. A utility restores automatic operation when those jobs finish.
If storage runs out, the advisory stays in force until control and supply return and its laboratory
clearance period ends.

`incident.begins` sets the time of the initial report. Each utility accepts a further field report
through `has_setback`, `setback_at` and `setback_work`. The report posts additional controls work
at that instant. An authored stage may also start `utility.observed_setback.start(work)` for each
observed interruption. The model computes subsequent service and restoration from its current stocks.
The historical study also generated interruptions from an attacker policy. The recovery runs accept
those interruptions as observations. The checked-in historical results use the original policy.

## Regional emergency dispatch

The `support_*` runs exercise one regional office. A batch represents supplemental emergency-water requests
and creates a specified number of work-hours. Relief dispatch reserves a share of its capacity while the
queue is open. The remaining capacity serves hospitals and households in their existing priority order.
Each processed work-hour delivers a measured volume from the common water supply. When the backlog clears,
regular deliveries regain all dispatch slots. The dashboard reports the amount still waiting, completed
work, supplemental water delivered, the accepted and filtered notifications, and the ordinary household
water deficit. The exercise clock reads the region's dispatch backlog.

| Regional workload | Standard response | Early response |
| --- | --- | --- |
| Single batch | `support_single` | `support_single_rapid` |
| Daily batches | `support_daily` | `support_daily_rapid` |
| Batches eight hours apart | `support_frequent` | `support_frequent_rapid` |
| Eight hours after the regional dispatch queue clears | `support_recovery` | `support_recovery_rapid` |

`support.first_delay` and `support.window` count hours from the initial incident report. The window includes
its endpoint. `support.limit` caps all batch notifications, including filtered ones. `support.interval`
sets the spacing in hours and `support.severity` sets the work-hours per accepted batch. A notification at
containment is filtered. The existing early and standard response choices supply their recognition and
containment times and their relief resources. The exercise assumes a 25% dispatch reservation, 2 work-hours
processed per hour and 100 US gallons per work-hour. These are illustrative capacity-planning assumptions.

Lumberton’s `dispatch` spread compares the recovery-linked response policies under the same 12 draws of spacing and workload, using seed 17. The distribution inputs are `support.interval_factor` and `support.severity_factor`. [Lumberton study](variants/lumberton/README.md#regional-dispatch-study)
The original three response runs leave the regional exercise off.

## The places

Each place is one where a part of the package's evidence comes from. The places are not a sample of the
country.

| Place | Why it is here | Water systems |
| --- | --- | --- |
| [Washington, DC](variants/washington_dc/README.md) | The cost of losing the region's water supply | The Washington Aqueduct, DC Water, Arlington, Fairfax Water, WSSC Water |
| [Cape May County, New Jersey](variants/cape_may/README.md) | Two systems lost their remote monitoring, and staff ran them by hand, July 2026 | Cape May, Woodbine |
| [Clayton County, Georgia](variants/clayton/README.md) | A disruption of operational systems led to a boil-water advisory, July 2026 | Clayton County Water Authority |
| [Minot, North Dakota](variants/minot/README.md) | Ransomware at the city cut the link to a regional water supply's controls, March 2026 | Minot, NAWS |
| [Asheville, North Carolina](variants/asheville/README.md) | Hospital water and the end of the boil-water notice after Hurricane Helene | Asheville |
| [Richmond, Virginia](variants/richmond/README.md) | The failure of the water plant, and its staff on manual operation, January 2025 | Richmond |
| [Lehigh County and Erie, Pennsylvania](variants/lehigh/README.md) | Utilities that helped each other after Superstorm Sandy | Lehigh County Authority, Erie Water Works |
| [Jamestown, North Carolina](variants/jamestown/README.md) | The stored water of a small town that buys its water | Jamestown, Greensboro, High Point |
| [Lumberton, North Carolina](variants/lumberton/README.md) | How long businesses closed after a flood | Lumberton |
| [Jackson, Mississippi](variants/jackson/README.md) | The fast delivery of a replacement pump controller | JXN Water |
| [El Dorado County, California](variants/el_dorado/README.md) | The lead time for new pumps, and the hours of field crews | El Dorado, Georgetown Divide |
| [Auburn, Washington](variants/auburn/README.md) | How much stored water a city can use | Auburn |
| [Austin, Texas](variants/austin/README.md) | How storage refilled after the 2021 freeze | Austin Water |
| [Juneau, Alaska](variants/juneau/README.md) | A city that one water system serves | Juneau |
| [Camden, New Jersey](variants/camden/README.md) | A cyberattack on the largest US water company, 2024 | The Raritan system |
| [Los Angeles, California](variants/los_angeles/README.md) | A study of how a water system recovers after damage | LADWP |

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Assumptions](evidence/assumptions.json) · [Local units](units.json)

[Historical evidence](historical/evidence/) retains 11 sources, 11 claims and four assumptions specific to the archived study. [Historical run orders](historical/expected-orders.json) retains the comparisons that the 16 variants shared at `8488047`.

The package's evidence gives what every place uses: the incidents that motivate the premise, the usable share
of stored water, the pace of mutual aid, the lead times of parts, the clearance of an advisory, emergency
water and hospital reserves, and the transfer of business losses. It also gives each system's people served
(SDWIS), the value added of the counties it serves (BEA) and the hospitals in its service area (CMS and the
EPA service areas). Each place's own evidence gives its systems' plants, storage, use and sales.

## Run

From the checkout:

```sh
napkin run scenarios/water_controls_wipe/variants/jamestown --run delayed_none --at 24h,2160h --value unserved_volume
python -m tools.publish --model scenarios/water_controls_wipe --check --jobs 4
```

Each place offers early, standard and delayed response settings. Washington, DC also offers
`delayed_aqueduct`, which changes the initial exposure. For a package's historical inputs and
publication, see its variant folder. The [recovery dashboard](ui/README.md) reads service levels and advisories at the selected hour from the run.
