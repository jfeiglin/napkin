# water_controls_wipe:richmond

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Richmond, Virginia, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water system
through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives the
mechanism, the response and the outcomes; this folder gives the place's system, its evidence, stylesheet, tests and published results.

## The place

Richmond is in the family because of the failure of its water plant in January 2025, and its staff on manual
operation. One system serves the city: the City's Department of Public Utilities, with one plant of 132 Mgal a
day, 69 Mgal of storage and sales to three counties.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, sales, plant and storage come from the City's 2025 water quality report, the packet of a
joint meeting with Henrico County, a Henrico news release and a report of the Virginia Department of Health. Its
people served, value added and hospitals come from the package's evidence. The package's shared tests check this
place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant richmond
python -B -m pytest --scenario water_controls_wipe:richmond
python -B -m tools.publish --write --scenario water_controls_wipe:richmond
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
