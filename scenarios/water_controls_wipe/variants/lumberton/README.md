# water_controls_wipe:lumberton

[Recovery readings](results/readings.md) · [Scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Lumberton, North Carolina. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The readings and comparison brief come from the current model. The methods page describes revision `8488047`.

## The place

Lumberton is in the family because of a study of how long its businesses closed after a flood. One system serves
the city: the City of Lumberton water system, with one plant of 16 Mgal a day on the Lumber River, 7.5 Mgal of
storage and no sales or purchases.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's peak day, plant, storage and connection come from its 2025 Local Water Supply Plan, and the note on
its raw water figures from its 2018 plan. Its people served, value added and hospital come from the package's
evidence. The package's shared tests check this place with the others.

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/lumberton --run delayed_none --value unserved_volume
```

## Regional dispatch study

The `dispatch` study compares `support_recovery_rapid` against `support_recovery` over 12 paired draws using seed 17. Each pair uses the same spacing and workload draw. The published differences cover accepted and filtered notices, work completed, supplemental gallons delivered in millions, and unmet household water in millions of gallons. [Study definition](brief.toml) · [Sampling inputs](spreads/dispatch.json) · [Paired results](results/paired-spreads.json)

To check the published study, run this command from the checkout root.

```sh
python -m tools.publish --check --only dossier --sample-spreads --scenario water_controls_wipe:lumberton --jobs 2
```
