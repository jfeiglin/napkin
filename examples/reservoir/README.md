# Reservoir

A five-day storm adds 6% of the reservoir's capacity each day. It starts 60% full. When it reaches the operator's opening level of 70%, the default decision opens the spillway and releases 15% of capacity per day. The model records the water remaining, the total spilled, and the hours with water at or above the valley's risk level.

Run these commands from the repository root.

```sh
napkin run examples/reservoir --at 0h,40h,120h \
    --value reservoir.water,reservoir.spilled,reservoir.risk_time
```

The spillway opens at 40 h. At 120 h the reservoir is 40% full, half its capacity has gone over the spillway, and the water has spent zero hours at or above the 80% risk level.

To play the operator, pause after the forecast is drawn and before the choice takes effect.

```sh
napkin play examples/reservoir --break 'operator.decide.step[0].do[1]' \
    --value reservoir.water,reservoir.spilled,reservoir.risk_time
```

Type `go` to accept the forecast. To keep the spillway closed, enter these two lines at the prompt.

```text
operator.decide#0.order = WAIT
go
```

With this decision the reservoir ends 90% full, has spilled no water, and spends 40 hours at or above the risk level.
