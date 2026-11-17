# water_controls_wipe

[Main file](model.scn) · [Shared model](water.scn) · [Research note](evidence/research.md) ·
[Shared tests](tests/)

`water_controls_wipe` is a package with one variant for each place. Each variant follows the real water systems of one
place. This folder holds what the places share: the main file `model.scn`, which uses the module
`water.scn`, and the package's evidence, units and tests. Each place's folder (`variants/<place>/`) holds
its own systems, the sales between them, its own evidence, stylesheet, brief settings, tests and
published results. The package runs as its variants: `water_controls_wipe:<place>` names the variant of a place.

## Mechanism family

Service loss from stored water; sales between systems; restoration and verification queues; causal
adversary interference.

An AI agent takes over the remote-support platform of an OT integrator and wipes the controls of the water
systems of one place at once. Each system keeps delivering from its usable stored water, then from what its
operators can produce by hand and what its sellers can still send it. A system that sells water to another
system of the place serves its own customers first. Controls engineers, field crews and replacement
controllers are finite pools that the systems of the place share. With a hidden credential that the first
cleanup misses, the AI wipes each system's restored controls again within minutes, until responders remove
the credential.

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

The package's evidence gives what every place uses: the incidents that motivate the premise, the usable share
of stored water, the pace of mutual aid, the lead times of parts, the clearance of an advisory, emergency
water and hospital reserves, and the transfer of business losses. It also gives each system's people served
(SDWIS), the value added of the counties it serves (BEA) and the hospitals in its service area (CMS and the
EPA service areas). Each place's own evidence gives its systems' plants, storage, use and sales.

The shared tests check every place: each resident is counted once, the delivered and unserved water add to
normal use, the person-days follow the unserved water, the AI adds more rework than the human team, and every
advisory ends. On places of different shapes they also check the water balance that decides when stored water
runs out, the processor sharing of the crews, the value-added loss in closed form, the capacity that bounds
emergency water and a seller that serves its own customers first.

## Run

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant washington_dc
python -B -m pytest scenarios/water_controls_wipe/tests -m "deep or not deep"
python -B -m tools.publish --write --scenario water_controls_wipe:washington_dc
```

For `tools.check` and `pytest`, `--scenario water_controls_wipe` selects every variant of the package; the publisher
takes each variant by its name. Evidence changes go through `tools.evidence.integrate`: a pack for
`water_controls_wipe` writes this folder, a pack for a place (`water_controls_wipe:<place>`) writes that place's folder.

The package's live view, a page that plays each place's runs, is in [ui/](ui/README.md).

[Shared testing rules](../../CONTRIBUTING.md#testing)
