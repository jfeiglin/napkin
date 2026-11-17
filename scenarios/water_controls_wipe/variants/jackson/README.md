# water_controls_wipe:jackson

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Jackson, Mississippi, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water system
through the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives the
mechanism, the response and the outcomes; this folder gives the place's system, its evidence, stylesheet, tests and published results.

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

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant jackson
python -B -m pytest --scenario water_controls_wipe:jackson
python -B -m tools.publish --write --scenario water_controls_wipe:jackson
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
