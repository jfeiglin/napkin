# water_controls_wipe:auburn

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Auburn, Washington, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water system
through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives the
mechanism, the response and the outcomes; this folder gives the place's system, its evidence,
stylesheet, tests and published results.

## The place

Auburn is in the family because its water plan shows how much of a city's stored water is usable. One system
serves the city: the City of Auburn water utility, with its own wells and springs, 15.86 Mgal of storage, a
firm sale to Algona and no regular purchases.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, sales, source capacity, storage and purchases come from the City's 2024 Water System
Plan. Its people served, value added and hospital come from the package's evidence. The package's shared tests
check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant auburn
python -B -m pytest --scenario water_controls_wipe:auburn
python -B -m tools.publish --write --scenario water_controls_wipe:auburn
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
