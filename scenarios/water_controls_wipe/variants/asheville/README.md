# water_controls_wipe:asheville

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Asheville, North Carolina, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water
system through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives
the mechanism, the response and the outcomes; this folder gives the place's system, its evidence,
stylesheet, tests and published results.

## The place

Asheville is in the family because of its hospital water and the end of its boil-water notice after Hurricane
Helene. One system serves the city: the City of Asheville water system, with three plants of 44 Mgal a day in
all, 27.356 Mgal of storage, sales to three other systems and no purchases.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, sales, plants and storage come from its 2025 Local Water Supply Plan, and its record of
the 2022 freeze from its 2022 plan. Its people served, value added and hospitals come from the package's evidence.
The package's shared tests check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant asheville
python -B -m pytest --scenario water_controls_wipe:asheville
python -B -m tools.publish --write --scenario water_controls_wipe:asheville
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
