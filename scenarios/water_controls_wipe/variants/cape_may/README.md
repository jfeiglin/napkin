# water_controls_wipe:cape_may

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Cape May County, New Jersey, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water
systems through the remote-support platform of the OT integrator they share. The package's module (`water.scn`)
gives the mechanism, the response and the outcomes; this folder gives the place's systems, their evidence,
stylesheet, tests and published results.

## The place

Cape May County is in the family because two of its systems lost their remote monitoring in July 2026, and
staff ran them by hand. Two systems with no connection between them serve the place: the City of Cape May, with
a reverse osmosis plant, 1.75 Mgal of storage and sales to three nearby systems, and the Borough of Woodbine,
with two wells and one water tower.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The systems' peak days, sales, plants and storage come from the City's water plant narrative and master plan
reexamination, NJDEP's water supply pages, an SDWIS query and Woodbine's master plan and water quality report.
Their people served and value added come from the package's evidence. The package's shared tests check this place
with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant cape_may
python -B -m pytest --scenario water_controls_wipe:cape_may
python -B -m tools.publish --write --scenario water_controls_wipe:cape_may
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
