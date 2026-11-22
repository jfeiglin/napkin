# water_controls_wipe:washington_dc

[Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Washington, DC. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The checked-in results describe the historical study at legacy revision `8488047`.

## The place

Washington, DC is in the family because of a study of the cost of a loss of the region's water supply. Five
systems serve the place. The Washington Aqueduct treats Potomac water and sells all of it to DC Water, Arlington
and Fairfax Water, and Fairfax Water also has its own plants. WSSC Water has its own plants and no connection to
the others in the model. The run "The Aqueduct only" follows a first move that reaches the Aqueduct alone.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The systems' peak days, sales, plants, storage and connections come from the 2025 ICPRB water supply study and
from the systems' own reports, budgets and plans. Their people served, value added and hospitals come from the
package's evidence. The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/washington_dc --run delayed_none --value unserved_volume
```
