# water_controls_wipe:asheville

[Recovery readings](results/readings.md) · [Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Asheville, North Carolina. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The recovery readings come from this model. The historical brief and methods describe revision `8488047`.

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

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/asheville --run delayed_none --value unserved_volume
```
