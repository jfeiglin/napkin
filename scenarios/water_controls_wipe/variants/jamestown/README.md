# water_controls_wipe:jamestown

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Jamestown, North Carolina, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water
systems through the remote-support platform of the OT integrator they share. The package's module (`water.scn`)
gives the mechanism, the response and the outcomes; this folder gives the place's systems, the sales between
them, its evidence, stylesheet, tests and published results.

## The place

Jamestown is in the family because it is a small town that buys all its water. Three systems serve the place:
the Town of Jamestown, with 0.4672 Mgal of storage and no plant of its own, and Greensboro and High Point, which
sell water to the town and buy water from outside the place.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

Each system's peak day, plants, storage, purchases and sales come from its 2025 Local Water Supply Plan. The
people served, value added and hospitals come from the package's evidence. The package's shared tests check this
place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant jamestown
python -B -m pytest --scenario water_controls_wipe:jamestown
python -B -m tools.publish --write --scenario water_controls_wipe:jamestown
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
