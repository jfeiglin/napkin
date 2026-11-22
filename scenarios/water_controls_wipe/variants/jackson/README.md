# water_controls_wipe:jackson

[Recovery readings](results/readings.md) · [Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Jackson, Mississippi. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The recovery readings come from this model. The historical brief and methods describe revision `8488047`.

## The place

Jackson is in the family because of the fast delivery of a replacement pump controller. One system serves the
city: JXN Water, with the O.B. Curtis and J.H. Fewell plants, 31.55 Mgal of storage and no sales or purchases.
About half of the water that its plants produce is lost from the pipes.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's production comes from the quarterly reports of its Interim Third-Party Manager. Its plants and
storage come from the 2021 survey of the Mississippi State Department of Health. Its people served, value added
and hospitals come from the package's evidence. The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/jackson --run delayed_none --value unserved_volume
```
