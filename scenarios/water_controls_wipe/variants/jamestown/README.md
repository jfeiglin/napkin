# water_controls_wipe:jamestown

[Recovery readings](results/readings.md) · [Scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Jamestown, North Carolina. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The readings and comparison brief come from the current model. The methods page describes revision `8488047`.

## The place

Jamestown is in the family because it is a small town that buys all its water. Three systems serve the place:
the Town of Jamestown, with 0.4672 Mgal of storage and no plant of its own, and Greensboro and High Point, which
sell water to the town and buy water from outside the place.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

Each system's peak day, plants, storage, purchases and sales come from its 2025 Local Water Supply Plan. The
people served, value added and hospitals come from the package's evidence. The package's shared tests check this
place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/jamestown --run delayed_none --value unserved_volume
```
