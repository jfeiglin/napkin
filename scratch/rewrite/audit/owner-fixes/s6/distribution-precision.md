# Distribution parameter precision

A run of the public compiler from commit `bf35dc2bfbe3fa2619b7940bff3abbd63ce81b9a` produced these diagnostics. Each input was a top-level `input x = <distribution>.draw()` with no units.

| Authored distribution | Baseline diagnostic |
| --- | --- |
| `normal(1, 1e-325)` | sd above 0 |
| `lognormal(1, 1.00000000000000001, 0, 2)` | gsd above 1 |
| `lognormal(1e-325, 2)` | median above 0 |
| `pert(1, 1, 1.00000000000000001)` | min <= mode <= max, with min below max |
| `triangular(1, 1, 1.00000000000000001)` | min <= mode <= max, with min below max |
| `loguniform(1e-325, 2)` | 0 < min < max |
| `categorical(A: 1e-325, B: 0)` | the weights of a categorical are not all zero |

Each baseline diagnostic had code `distribution`. These cases still produce that code. The message now identifies execution precision where rounding would produce a zero divisor or an invalid logarithm. The authoring check evaluates each original parameter in its exact unit first.

The compiler also used to refuse `uniform(1, 1.00000000000000001)` with “min below max.” Its authored width is positive. A uniform draw interpolates its endpoints without dividing by their distance, so this distribution can be executed and its stored parameters retain both endpoints. A declared upper support limit of exactly 1 still refuses this distribution.
