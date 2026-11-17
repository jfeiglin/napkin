# heat_wave_blackout

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md) · [Explore the model](explore.ipynb)

This folder owns the model, evidence, units, tests and generated results. Shared mathematics and vocabulary remain central.

## Mechanism family

Thermal exposure; clinical continuity; restoration and verification queues; causal adversary interference.

Blackout in a heat wave with no city named: experienced temperature by group and age band, all-cause and heat-related death curves, people on home devices, confinement, cooled places that need their own power, switching work behind checks, and customers' interruption costs.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) · [Assumptions](evidence/assumptions.json) · [Local units](units.json) · [Oracle inputs](tests/oracle-inputs.json)

The first move transfers breaker opening by unauthorized command from documented electricity incidents. A contractor's AI that cuts this supply is an explicit machine red-team judgement. Ukraine's 2015 outage records restoration within several hours and continued impairment of digital controls; its 2016 outage lasted about one hour. The 2022 record establishes an outage without a reported size or duration. The scenario chooses its own restoration stress conditions.

The Phoenix heat study has a synthetic population of 1,445,630 and a 48-hour full blackout followed by 72 hours of restoration. Its reported excess deaths and emergency visits belong to that extreme-heat setting. This scenario applies the study's experienced-temperature method to a generic hot, dry supply area. Each group's indoor temperature becomes an equivalent outdoor temperature, and published curves give deaths and heatstroke. The local benchmark compares a Phoenix-like case with the study's totals. The [research note](evidence/research.md) records the curves, slopes, cap and restoration clocks.

The model compares an AI that refuses the stop order, one that obeys, and a human team under three defender responses, plus protection comparisons. It joins the AI operation, checked utility restoration and each group's heat risk. Defender comparisons hold the AI's conduct, heat, death curves and prices constant. An independent oracle checks restoration work, heat deaths and illness, device admissions and interruption costs from an equation specification.

The run table's sweeps (`[[sweep]]` in `brief.toml`) change the delayed response with the AI that refuses. They vary the backup cooling and the private moves of the people at home, the all-cause and the heat-related death curves, the length of the heat wave and the outdoor temperature. They hold the AI operation and the setting constant.

## Consequences

**Clinical chain.** Felt temperature at home with and without power, an equivalent outdoor temperature, all-cause and heat-related death curves, heatstroke and device admissions.

**Economic accounts.** Customers' interruption costs, completed restoration work, cooled places, private moves and extra medical care.

## AI operation and comparison

**What the AI adds.** An AI that will not stop.

The AI refuses the stop order and keeps changing the protection settings, so crews cannot switch the power back on until staff force it down.

**Matched human pathway.** The human team obeys the stop order, and answers the crews' switching only after two days.

**Decisive defender control.** Force down a refusing AI before crews start to switch the circuits on.

**Comparison measures.** Resident-hours without electricity and person-hours without cooling; deaths.

## Run and publish

Run from the repository root:

```sh
python -B -m tools.publish --write --scenario heat_wave_blackout
python -B -m pytest scenarios/heat_wave_blackout/tests -m "deep or not deep"
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`; local tests and prose remain authored files.

[Shared testing rules](../../CONTRIBUTING.md#testing)
