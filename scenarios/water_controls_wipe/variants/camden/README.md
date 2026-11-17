# water_controls_wipe:camden

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Camden, New Jersey, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water system
through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives the
mechanism, the response and the outcomes; this folder gives the place's system, its evidence,
stylesheet, tests and published results.

## The place

Camden is in the family because it is the seat of American Water, whose business systems an attacker disrupted
in 2024. The place's system is the company's Raritan system, its largest in New Jersey, with two surface water
plants, 69 wells, sales to nine bulk customers and a transfer to the company's Passaic Basin system.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's capacity comes from the state's water supply record, its average day and sales from the company's
filings and a Board order, its highest day from a 2025 plant tour, and its storage from rate-case testimony,
which gives one site only. Its people served, value added and hospitals come from the package's evidence. The
package's shared tests check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant camden
python -B -m pytest --scenario water_controls_wipe:camden
python -B -m tools.publish --write --scenario water_controls_wipe:camden
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
