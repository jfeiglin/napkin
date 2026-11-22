# Scenario catalogue

| Package | Question | Current results |
| --- | --- | --- |
| [Water service](water_controls_wipe/README.md) | How do recurring demands on emergency support interact with response, repair, water stocks and relief? The package covers 16 service areas. | [Example regional comparison](water_controls_wipe/variants/washington_dc/results/brief.md) |
| [Electricity restoration during heat](heat_wave_blackout/README.md) | How do the cadence of service interruptions, clearance of outstanding work and protection decisions change cooling and exposure during a heat wave? | [Heat comparisons](heat_wave_blackout/results/brief.md) |
| [IV-fluid supply](iv_fluid_shortage/README.md) | How do the timing of quality reviews and the capacity to clear them affect release, fluid stocks and unmet demand? | [IV-fluid comparisons](iv_fluid_shortage/results/brief.md) |
| [Strategic cyber](cyber_learning_loop/README.md) | Over 25 years, how much do different assumptions about AI productivity change the balance between surveillance and effects missions as defenders also adapt? | [AI-uplift comparisons](cyber_learning_loop/results/brief.md) |

To run a policy directly, choose its ID with `--run`. These commands read the outcomes at specific times.

```sh
python -m napkin run scenarios/water_controls_wipe/variants/lumberton --run support_recovery --value support.waiting,emergency_water_deficit --at 24h,72h
python -m napkin run scenarios/heat_wave_blackout --run acknowledged_stop --value incident.accepted,incident.prevented --at 48h
python -m napkin run scenarios/iv_fluid_shortage --run followup_quality_review --value quality_review.received,quality_review.completed --at 648h,984h
python -m napkin run scenarios/cyber_learning_loop --run ai_fast --value effects_program.completed --at 25years
```

The strategic package also includes a [defensive-response model](cyber_learning_loop/defensive_response/) that accepts an incident workload directly. Each package guide describes its inputs, units, assumptions and named runs.

The [model comparison](../scratch/rewrite/audit/catalogue-model-deviations.md) describes changes to each policy and its units. The earlier studies and their numerical results are available in the [catalogue at revision `8488047`](https://github.com/jfeiglin/napkin/tree/8488047/scenarios).
