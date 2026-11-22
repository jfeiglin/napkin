# water_controls_wipe:washington_dc

[Recovery readings](results/readings.md) · [Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Washington, DC. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The recovery readings come from this model. The historical brief and methods describe revision `8488047`.

## The place

Washington, DC is in the family because of a study of the cost of a loss of the region's water supply. Five
systems serve the place. The Washington Aqueduct treats Potomac water and sells all of it to DC Water, Arlington
and Fairfax Water, and Fairfax Water also has its own plants. WSSC Water has its own plants and no connection to
the others in the model. In the `delayed_aqueduct` run, only the Aqueduct experiences the initial outage. Its buyers then receive less water.

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

The ordinary runs use the stated inputs. The optional uncertainty study draws crew availability,
the share of normal production available under manual operation, and controls repair hours
once per run. The two crew draws use the Delayed capacities as their reference points. The
Early response multiplies the controls draw by 160/40 and the field draw by 200/60 to preserve
its staffing levels relative to Delayed. Their respective PERT ranges are 20–80 and 30–120 work
hours per hour under Delayed. The manual share and repair workload use the same draws across
response options. The historical spread compared two Delayed runs.

```sh
napkin sample scenarios/water_controls_wipe/variants/washington_dc \
  --run delayed_none --edits scenarios/water_controls_wipe/variants/washington_dc/spreads/uncertainty.json \
  --samples 2 --seed 0 --jobs 2 --value controls_crew.working_capacity,field_crew.working_capacity
```

Repeat with `--run early` to compare responses on matched draws. The JSON edit sets four
distribution-valued inputs. The model draws them when `uncertainty.enabled` is true. Ordinary
numeric edits can still set `controls_crew.capacity`, `field_crew.capacity`,
`wssc_water.manual_share` and `wssc_water.controls_load`.
