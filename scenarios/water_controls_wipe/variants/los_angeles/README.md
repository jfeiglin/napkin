# water_controls_wipe:los_angeles

[Recovery readings](results/readings.md) · [Scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Los Angeles, California. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The readings and comparison brief come from the current model. The methods page describes revision `8488047`.

## The place

Los Angeles is in the family because a study of how its water system recovers after damage shows what a finer
model would need. One system serves the city: LADWP, with its aqueduct filtration plant, 4,254 Mgal of in-city
storage and large purchases from the Metropolitan Water District. It sells no water.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's demand, purchases and storage come from its 2025 bond statement, its plant capacity from a 2023
letter, and its peak purchases from the Metropolitan Water District's budget. No source reports its highest day,
so the family median ratio applies. Its people served, value added and hospitals come from the package's evidence.
The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/los_angeles --run delayed_none --value unserved_volume
```
