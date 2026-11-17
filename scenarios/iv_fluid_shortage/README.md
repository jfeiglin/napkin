# iv_fluid_shortage

[Scenario brief](results/brief.md) · [Model](model.scn) · [Methods](results/methods.md)

This folder owns the model, evidence, units, tests and generated results. Shared mathematics and vocabulary remain central.

## Mechanism family

Supply and funding; clinical continuity; causal adversary interference.

Supply, allocation and finite clinical episodes.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) · [Assumptions](evidence/assumptions.json) · [Local units](units.json) · [Oracle inputs](tests/oracle-inputs.json)

The first move disrupts pharmaceutical manufacture and order fulfilment. Historical evidence includes continued shipments after a manufacturing attack and clinical-product shortages after blood-supplier attacks. Applying those mechanisms to an IV-fluid shortage is an explicit machine red-team judgement.

The model pairs three defender responses with the two access conditions: the attacker loses access or keeps a hidden credential. The acceptance tests use independent mathematics for the supply and clinical mechanisms.

## Consequences

**Clinical chain.** Actual unmet complete courses, severe-dehydration mix, finite effective rescue and progression.

**Economic accounts.** Supplier and procedure value added, restoration and received qualified supply.

## AI operation and comparison

**What the AI adds.** Adaptation on the spot.

The AI within minutes of release restarting, it alters every released lot's records to fit the checks it meets only then, so the lots ship and are later held.

**Matched human pathway.** The human team needs about two days to work out such changes; the credentials are reset first.

**Decisive defender control.** Reset the record credentials at the restart, not a day later.

**Comparison measures.** Days without fluid for other essential care, and qualification work to redo.

## Run and publish

Run from the repository root:

```sh
python -B -m tools.publish --write --scenario iv_fluid_shortage
python -B -m pytest scenarios/iv_fluid_shortage/tests -m "deep or not deep"
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`; local tests and prose remain authored files.

[Shared testing rules](../../CONTRIBUTING.md#testing)
