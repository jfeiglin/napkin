# water_controls_wipe:lehigh

[Recovery readings](results/readings.md) · [Scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Lehigh County and Erie, Pennsylvania. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The readings and comparison brief come from the current model. The methods page describes revision `8488047`.

## The place

Lehigh County and Erie are in the family because their utilities helped each other after Superstorm Sandy. Two
systems with no connection between them serve the place: Lehigh County Authority, which runs the Allentown water
system and sells water to its Suburban Division, and Erie Water Works, with two plants on Lake Erie.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The systems' peak days, sales, plants and storage come from their financial reports, plans, newsletters, a rate
study and the City of Allentown's concession report. Their people served and value added come from the package's
evidence. The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/lehigh --run delayed_none --value unserved_volume
```
