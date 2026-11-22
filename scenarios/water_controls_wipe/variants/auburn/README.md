# water_controls_wipe:auburn

[Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Auburn, Washington. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The checked-in results describe the historical study at legacy revision `8488047`.

## The place

Auburn is in the family because its water plan shows how much of a city's stored water is usable. One system
serves the city: the City of Auburn water utility, with its own wells and springs, 15.86 Mgal of storage, a
firm sale to Algona and no regular purchases.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, sales, source capacity, storage and purchases come from the City's 2024 Water System
Plan. Its people served, value added and hospital come from the package's evidence. The package's shared tests
check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/auburn --run delayed_none --value unserved_volume
```
