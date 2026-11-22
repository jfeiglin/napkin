# water_controls_wipe:austin

[Recovery readings](results/readings.md) · [Scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Austin, Texas. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The readings and comparison brief come from the current model. The methods page describes revision `8488047`.

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

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/austin --run delayed_none --value unserved_volume
```
