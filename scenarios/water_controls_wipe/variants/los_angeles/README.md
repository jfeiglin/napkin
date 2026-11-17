# water_controls_wipe:los_angeles

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Los Angeles, California, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water
system through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives
the mechanism, the response and the outcomes; this folder gives the place's system, its evidence, stylesheet, tests and published results.

## The place

Los Angeles is in the family because a study of how its water system recovers after damage shows what a finer
model would need. One system serves the city: LADWP, with its aqueduct filtration plant, 4,254 Mgal of in-city
storage and large purchases from the Metropolitan Water District. It sells no water.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's demand, purchases and storage come from its 2025 bond statement, its plant capacity from a 2023
letter, and its peak purchases from the Metropolitan Water District's budget. No source reports its highest day,
so the family median ratio applies. Its people served, value added and hospitals come from the package's evidence.
The package's shared tests check this place with the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant los_angeles
python -B -m pytest --scenario water_controls_wipe:los_angeles
python -B -m tools.publish --write --scenario water_controls_wipe:los_angeles
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
