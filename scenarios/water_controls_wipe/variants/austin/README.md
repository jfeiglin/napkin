# water_controls_wipe:austin

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Austin, Texas, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water system
through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives the
mechanism, the response and the outcomes; this folder gives the place's system, its evidence,
stylesheet, tests and published results.

## The place

Austin is in the family because its storage records show how the reservoirs refilled after the 2021 freeze. One
system serves the city: Austin Water, with three treatment plants of 335 Mgal a day in all, 176 Mgal of storage,
sales to wholesale customers and no purchases.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, sales, plants, storage and purchases come from the City's 2024 water conservation plan
and the preliminary statement for its 2026 water bonds. Its people served, value added and hospitals come from
the package's evidence. The package's shared tests check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant austin
python -B -m pytest --scenario water_controls_wipe:austin
python -B -m tools.publish --write --scenario water_controls_wipe:austin
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
