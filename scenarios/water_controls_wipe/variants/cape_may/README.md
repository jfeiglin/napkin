# water_controls_wipe:cape_may

[Recovery readings](results/readings.md) · [Scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Cape May County, New Jersey. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The readings and comparison brief come from the current model. The methods page describes revision `8488047`.

## The place

Cape May County is in the family because two of its systems lost their remote monitoring in July 2026, and
staff ran them by hand. Two systems with no connection between them serve the place: the City of Cape May, with
a reverse osmosis plant, 1.75 Mgal of storage and sales to three nearby systems, and the Borough of Woodbine,
with two wells and one water tower.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The systems' peak days, sales, plants and storage come from the City's water plant narrative and master plan
reexamination, NJDEP's water supply pages, an SDWIS query and Woodbine's master plan and water quality report.
Their people served and value added come from the package's evidence. The package's shared tests check this place
with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/cape_may --run delayed_none --value unserved_volume
```
