# water_controls_wipe:clayton

[Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Clayton County, Georgia. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The checked-in results describe the historical study at legacy revision `8488047`.

## The place

Clayton County is in the family because a disruption of part of its operational systems led to a boil-water
advisory in July 2026. One system serves the county: the Clayton County Water Authority, with three plants of
42 Mgal a day in all, 32.2 Mgal of storage, a sale to College Park and connections with Atlanta, DeKalb and
Fayette that open on demand.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's plants, production, storage and connections come from the Authority's 2025 financial report and
2026-2027 budget, and its buyers from an SDWIS query. Its people served, value added and hospital come from the
package's evidence. The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/clayton --run delayed_none --value unserved_volume
```
