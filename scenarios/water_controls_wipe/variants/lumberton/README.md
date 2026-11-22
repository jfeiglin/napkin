# water_controls_wipe:lumberton

[Recovery readings](results/readings.md) · [Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Lumberton, North Carolina. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The recovery readings come from this model. The historical brief and methods describe revision `8488047`.

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

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/lumberton --run delayed_none --value unserved_volume
```
