# water_controls_wipe:juneau

[Historical scenario brief](results/brief.md) · [Model](model.scn) · [Historical methods](results/methods.md) ·
[The `water_controls_wipe` package](../../README.md)

This variant follows water service and recovery in Juneau, Alaska. The initial controls outage is an incident input. The model computes storage, deliveries, crew queues and advisory clearance over time. The checked-in results describe the historical study at legacy revision `8488047`.

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

## Run

```sh
napkin run scenarios/water_controls_wipe/variants/juneau --run delayed_none --value unserved_volume
```
