# water_controls_wipe:washington_dc

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Washington, DC, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water systems
through the remote-support platform of the OT integrator they share. The package's module (`water.scn`) gives
the mechanism, the response and the outcomes; this folder gives the place's systems, the sales between them, its
evidence, stylesheet, tests and published results.

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

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant washington_dc
python -B -m pytest --scenario water_controls_wipe:washington_dc
python -B -m tools.publish --write --scenario water_controls_wipe:washington_dc
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
