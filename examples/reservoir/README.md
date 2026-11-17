# Reservoir

A storm fills a reservoir for five days. The operator of the dam sees the water level and decides
when to open the spillway. The water is a share of the reservoir's capacity: 1 is full.

It shows:

- an actor: `operator` sees the water level (`sees`), and nothing else;
- a choice of that actor (`choice`): when the water reaches the operator's level, open the spillway
  or wait;
- two results: the water let out over the spillway, and the time with the water above the level at
  which the valley is at risk.

The model has one run. In it, the operator opens the spillway at the level. When you play the
operator, you make that choice yourself: if you wait, no water goes over the spillway, and the water
can rise above the risk level.

Run it from the folder that holds `examples/`:

```sh
napkin run examples/reservoir
napkin play examples/reservoir --control operator
napkin run examples/reservoir --set operator.level=0.85
```

`napkin play` stops at the operator's choice, shows what the operator sees, and asks for a pick.
With `--json` it writes the choice as a line of JSON and reads the pick as one, so another program
can play the operator.
