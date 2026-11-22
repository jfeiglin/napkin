# water_controls_wipe:el_dorado

[Recovery readings](results/readings.md) · [Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in El Dorado County, California. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The recovery readings come from this model. The historical brief and methods describe revision `8488047`.

## The place

El Dorado County is in the family because its districts report the lead time for new pumps and the hours of
field crews. Two systems with no connection between them serve the place: the El Dorado Irrigation District,
with three plants and a sale to Placerville, and the Georgetown Divide Public Utility District, with two small
plants and no way to buy water.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The systems' peak days, use, sales, plants and storage come from the reviews of El Dorado LAFCO and the 2025
water plans of the two districts. Their people served, value added and hospital come from the package's
evidence. The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/el_dorado --run delayed_none --value unserved_volume
```
