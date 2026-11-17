# water_controls_wipe:lumberton

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Lumberton, North Carolina, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water
system through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives
the mechanism, the response and the outcomes; this folder gives the place's system, its evidence, stylesheet, tests and published results.

## The place

Lumberton is in the family because of a study of how long its businesses closed after a flood. One system serves
the city: the City of Lumberton water system, with one plant of 16 Mgal a day on the Lumber River, 7.5 Mgal of
storage and no sales or purchases.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, plant, storage and connection come from its 2025 Local Water Supply Plan, and the note on
its raw water figures from its 2018 plan. Its people served, value added and hospital come from the package's
evidence. The package's shared tests check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant lumberton
python -B -m pytest --scenario water_controls_wipe:lumberton
python -B -m tools.publish --write --scenario water_controls_wipe:lumberton
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
