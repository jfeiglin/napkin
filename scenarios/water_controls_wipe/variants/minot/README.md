# water_controls_wipe:minot

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Minot, North Dakota, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water systems
through the remote-support platform of the OT integrator they share. The package's module (`water.scn`) gives
the mechanism, the response and the outcomes; this folder gives the place's systems, the sales between them, its
evidence, stylesheet, tests and published results.

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

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant minot
python -B -m pytest --scenario water_controls_wipe:minot
python -B -m tools.publish --write --scenario water_controls_wipe:minot
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
