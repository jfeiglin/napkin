# water_controls_wipe:clayton

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Clayton County, Georgia, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water
system through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives
the mechanism, the response and the outcomes; this folder gives the place's system, its evidence, stylesheet, tests and published results.

## The place

Clayton County is in the family because a disruption of part of its operational systems led to a boil-water
advisory in July 2026. One system serves the county: the Clayton County Water Authority, with three plants of
42 Mgal a day in all, 32.2 Mgal of storage, a sale to College Park and connections with Atlanta, DeKalb and
Fayette that open on demand.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's plants, production, storage and connections come from the Authority's 2025 financial report and
2026-2027 budget, and its buyers from an SDWIS query. Its people served, value added and hospital come from the
package's evidence. The package's shared tests check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant clayton
python -B -m pytest --scenario water_controls_wipe:clayton
python -B -m tools.publish --write --scenario water_controls_wipe:clayton
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
