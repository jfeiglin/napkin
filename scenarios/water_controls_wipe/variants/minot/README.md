# water_controls_wipe:minot

[Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Minot, North Dakota. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The checked-in results describe the historical study at legacy revision `8488047`.

## The place

Minot is in the family because ransomware at the city cut the link to the controls of a regional water supply in
March 2026. Two systems serve the place: the City of Minot, with the only treatment plant, 18 Mgal a day, and
14 Mgal of storage, and the Northwest Area Water Supply (NAWS), which buys all its water from Minot and sells it
to nine towns and districts.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The systems' peak day, sales, plant, storage and connection come from the reports and meeting packets of the
Department of Water Resources, the city's plans and news reports. Their people served, value added and hospital come
from the package's evidence. The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/minot --run delayed_none --value unserved_volume
```
