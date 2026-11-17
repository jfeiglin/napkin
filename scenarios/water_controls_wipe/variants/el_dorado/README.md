# water_controls_wipe:el_dorado

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

El Dorado County, California, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water
systems through the remote-support platform of the OT integrator they share. The package's module (`water.scn`)
gives the mechanism, the response and the outcomes; this folder gives the place's systems, their evidence,
stylesheet, tests and published results.

## The place

El Dorado County is in the family because its districts report the lead time for new pumps and the hours of
field crews. Two systems with no connection between them serve the place: the El Dorado Irrigation District,
with three plants and a sale to Placerville, and the Georgetown Divide Public Utility District, with two small
plants and no way to buy water.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The systems' peak days, use, sales, plants and storage come from the reviews of El Dorado LAFCO and the 2025
water plans of the two districts. Their people served, value added and hospital come from the package's
evidence. The package's shared tests check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant el_dorado
python -B -m pytest --scenario water_controls_wipe:el_dorado
python -B -m tools.publish --write --scenario water_controls_wipe:el_dorado
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
