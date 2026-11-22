# water_controls_wipe:richmond

[Recovery readings](results/readings.md) · [Scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Richmond, Virginia. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The readings and comparison brief come from the current model. The methods page describes revision `8488047`.

## The place

Richmond is in the family because of the failure of its water plant in January 2025, and its staff on manual
operation. One system serves the city: the City's Department of Public Utilities, with one plant of 132 Mgal a
day, 69 Mgal of storage and sales to three counties.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, sales, plant and storage come from the City's 2025 water quality report, the packet of a
joint meeting with Henrico County, a Henrico news release and a report of the Virginia Department of Health. Its
people served, value added and hospitals come from the package's evidence. The package's shared tests check this
place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/richmond --run delayed_none --value unserved_volume
```
