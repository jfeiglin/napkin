# water_controls_wipe:camden

[Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Camden, New Jersey. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The checked-in results describe the historical study at legacy revision `8488047`.

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

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/camden --run delayed_none --value unserved_volume
```
