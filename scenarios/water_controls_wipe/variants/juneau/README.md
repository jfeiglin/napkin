# water_controls_wipe:juneau

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

Juneau, Alaska, as a place of the `water_controls_wipe` family: an AI agent wipes the controls of the place's water system through
the remote-support platform of the OT integrator it uses. The package's module (`water.scn`) gives the mechanism,
the response and the outcomes; this folder gives the place's system, its evidence, stylesheet, tests and
published results.

## The place

Juneau is in the family because one water system serves the whole city. That system is the City and Borough of
Juneau water utility, with the Last Chance Basin wellfield, the Salmon Creek filtration plant and 11 Mgal of
storage. On its peak day, which comes with the cruise ships, it produces only a little more than it needs.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) ·
[Oracle inputs](tests/oracle-inputs.json) · [Expected orders](tests/expected-orders.json)

The system's supply and storage come from its 2012 supply plan, its peak day from a 2013 news report, the
wellfield's output from a 2014 news report, and its plant and outages from the utility's own pages. Its people
served, value added and hospital come from the package's evidence. The package's shared tests check this place with
the others.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/water_controls_wipe --variant juneau
python -B -m pytest --scenario water_controls_wipe:juneau
python -B -m tools.publish --write --scenario water_controls_wipe:juneau
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`.
