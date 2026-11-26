# Numerics

This page tells how two numbers of a model compare and how a **scale** sets the **comparison
band**. It also tells what a declared scale can change, and which runs give the same numbers. The words in bold are the
[terms](README.md#terms) of the documentation. The methods of integration and of the solvers are in
[engine/methods.md](../engine/methods.md) and [engine/solver.md](../engine/solver.md).

## Contents

1. [The comparison band](#the-comparison-band)
2. [How a floor goes through an expression](#how-a-floor-goes-through-an-expression)
3. [Exact literals](#exact-literals)
4. [Intervals and bounds](#intervals-and-bounds)
5. [Scale hints](#scale-hints)
6. [What a scale can change](#what-a-scale-can-change)
7. [Contacts and placement](#contacts-and-placement)
8. [Near-ties](#near-ties)
9. [Numerical settings](#numerical-settings)
10. [Reproducibility](#reproducibility)
11. [The explicit-time rate check](#the-explicit-time-rate-check)

## The comparison band

Two numeric operands `a` and `b` compare equal when their difference is inside this band:

```text
max(rtol, atol_factor) × max(scale, |a|, |b|)
```

- The default value of `rtol` is 1e-9. The default value of `atol_factor` is 1e-10.
  The larger value, 1e-9, sets the comparison factor.
- `scale` is the floor of the comparison, in the unit of the operands. The engine compares both
  operands and their floor in the canonical unit of their dimension.
- A quantity gives its declared `scale` as its floor. A quantity with no `scale` gives the size of
  one of its declared units. A value in `h` gives 1 h, and a value in `day` gives 24 h.
- Inside the band, the operands are equal. So `==`, `<=` and `>=` hold, and `<`, `>` and `!=` do
  not.
- The same band applies in every evaluator. These are a formula, a guard, a trigger, a gate, a
  reset and an assertion. They are also the ends of a membership test and the reference interpreter
  of the tests.

This model compares values of zero with small literals, and two literals with each other. A run
gives the readings in the table below the model.

```scn
scenario "Bands"
    horizon 1 h

record fixture: assumption "A fixture."

wait: h = 0 h  @fixture
fine: h = 0 h scale 0.001 h  @fixture
long: day = 0 day  @fixture
below = formula(wait < 0.000000001 h)
fine_below = formula(fine < 0.000000001 h)
long_below = formula(long < 0.00000001 h)
wait_below = formula(wait < 0.00000001 h)
literals = formula(1 h > 0.999999999 h)
closer = formula(1 h > 0.999999998999999999 h)
```

| Reading | Value | Why |
| --- | --- | --- |
| `below` | `false` | The gap equals the band of 1e-9 h. A gap on the edge is inside the band. |
| `fine_below` | `true` | The scale is 0.001 h. The gap of 1e-9 h exceeds the band of 1e-12 h. |
| `long_below` | `false` | One day is 24 h. The gap of 1e-8 h is inside the band of 2.4e-8 h. |
| `wait_below` | `true` | The gap of 1e-8 h exceeds the band of 1e-9 h. |
| `literals` | `false` | The larger operand is 1 h. The gap equals the band of 1e-9 h. |
| `closer` | `true` | The exact decimal gap exceeds 1e-9 h. |

## How a floor goes through an expression

A formula, inline or named, takes its floor from the quantities that it reads. The floor is in the
unit of the result.

| Expression | Its floor |
| --- | --- |
| A quantity | Its declared `scale`, or one of its declared units |
| A formula with a declared `scale` | That scale. A declared scale of a result wins. |
| An authored literal, and an expression of literals only | Zero |
| `x + 5 L`, `x - 5 L` | The floor of `x`. A literal offset leaves the floor as it is. |
| `a + b`, `a - b` | The signed contributions of each quantity are added, also through its aliases. The floor is the largest absolute contribution among independent quantities. |
| `3 * x`, `x / 3` | The floor of `x`, times or divided by the literal in canonical units |
| `a * b`, `a / b` | The product or the quotient of the floors |
| `x ** n`, `sqrt(x)` | The floor raised to `n`, or its square root |
| `abs(x)`, `exp(x)` and the other functions of one plain number | The floor of `x` |
| `min`, `max`, `clip` | The largest floor of the quantities that contribute |
| `a if C else b` | The floor of the arm that the condition selects |
| `c.at(k).x` | The floor of the member that the key selects |
| A frozen formula of a finished occurrence | Its floor at the finish |

In a comparison:

- A literal threshold takes the floor of the quantity that it compares with, on either side:
  `wait < 0.000000001 h` uses the floor of `wait`.
- Two operands that the engine compares independently use the larger of their two floors.
- The relative term `factor × max(|a|, |b|)` always applies, also when both floors are zero.

## Exact literals

A number that the model writes is the exact decimal of its text. The compiler never reads it
through a float. `0.1 day` is exactly 2.4 h, and `48 people/day` is exactly 2 people/h.

- An authored literal contributes no floor to a comparison, whatever its unit. This also holds for
  an expression of literals only, and for a formula that names one.
- The compiler folds constant expressions exactly, wherever the result is rational. A range, a
  domain, the ends of a test and a fixed key use the folded value. The support of a drawn input and
  a cited datum also use it.
- The factor of a unit is exact. `0.01` in `units.json` is 1/100.
- The run calculates with the float nearest to each exact value.
- A datum of evidence is exact. A value equals its cited datum only when the two are the same
  number in the same dimension ([evidence.md](evidence.md#the-datum-rule)).

## Intervals and bounds

- An interval is reversed only when its lower end is above its upper end by more than their band.
  A reversed interval is an error of the compiler when its ends are fixed. When only the run knows
  its ends, it stops the run by name.
- The interval `[x, x]` holds the values that compare equal to `x`.
- Hard bounds that are inverted by less than their band admit one point, their midpoint.
- A stock inside its own band of a bound counts as on the bound, for sharing, comparisons and
  triggers. The residual on its books stays.
- A stock leaves a bound only when the net rate away from it is more than 10⁻¹² times its gross
  inflow plus outflow. Equality holds the stock on the bound. Every method uses the same rule.

## Scale hints

`scale` states the numerical size of a value. It stands after the range, or on its own row under
the declaration.

```scn
tuners:
    "The piano tuners of the town."
    input rate: tunings/(tuner * year) = pert(600, 1000, 1200).draw() in [500, 1500]
        "Tunings that one tuner does in a year"
        @assumption "The example assumes about four tunings in each working day, and a spread around it."
    input staff = 3 tuner in [1 tuner, 10 tuner]
        "Tuners in the town"
        @assumption "The example assumes three tuners."
    input need = 5000 tunings in [0 tunings, 20000 tunings]
        "Tunings that the pianos need in the year"
        @assumption "The example assumes 2500 pianos, each tuned twice in a year."
    due: tunings = this.need in [0,] scale 20000 tunings @counts
        "Tunings that the pianos still need"
```

- A scale helps the numerical calculation. It is no bound. An inventory bound limits a stock, and
  a `capacity` limits a rate.
- A bare number in a scale takes the declared unit.
- A new unknown of a solver can declare a scale: `level: 1 = 0 in [-30, 30] scale 10`.
- A formula can declare the scale of its result: `gap = formula(this.a - this.b) scale 1 L`.

With no `scale`, the engine infers the size of each stock for integration. The size is the largest
of these:

- one declared unit
- the starting value
- the starting values of the stocks that flows join to it
- its finite bounds.

A declared scale replaces that inference. Declare a scale when the inferred
size understates how large a value grows.

## What a scale can change

A declared scale is part of the model. It can change three things:

| What | How |
| --- | --- |
| A comparison inside the band | The floor of a comparison is the scale. A smaller scale makes the band narrower, so a comparison can change its result. |
| The accuracy of integration | The absolute tolerance of a stock is `atol_factor` times its size. |
| The choice among equally optimal answers of a solver | The final distance step divides each unknown that is no flow by its scale ([flows-and-solvers.md](flows-and-solvers.md#the-selection-order)). |

A scale never changes a hard rule. The books of a stock balance, a stock stays inside its range,
and two equal claims get equal shares, whatever the scale.

In the solver below, `x + y == 1 h` has many answers. With no declared scale, each unknown uses the
width of its domain, 10 h, and the final step selects `x = 0.5 h` and `y = 0.5 h`. With `scale 2 h` on `x` and `scale 1 h` on `y`, it selects `x = 0.8 h`
and `y = 0.2 h`.

```scn
planner:
    split = solver:
        solve_for:
            x: h in [0 h, 10 h] scale 2 h
            y: h in [0 h, 10 h] scale 1 h
        constraints:
            x + y == 1 h
```

**Units of display never change an answer.** A display unit is the unit in which a report shows a
value, or in which a caller writes an edit or a time. The engine converts it to the canonical unit
first. The final distance step divides each flow rate by one canonical unit of its dimension. So the
unit in which a model writes a rate does not change the rates that a solver selects.

The declared unit of a value is different. It is part of the model: for a value with no `scale`,
one declared unit is the floor of its comparisons. To make the floor independent of the declared
unit, declare a `scale`.

## Contacts and placement

A **contact** is the time at which a stock reaches a bound or a threshold between two scheduled
times. The engine locates it to the crossing tolerance in time.

- A contact joins a nearby **moment** only when two tests pass. Its located time is within the
  crossing tolerance of the moment. The stock at the time of the moment is within its own band of
  the threshold or the bound. Else the contact is a moment of its own, at its located time.
- An earlier contact runs before the stages that are due. A later contact waits across those stages
  when their writes keep it.
- The books always balance. A transfer posts equally at both ends. A read, a group of events or a
  located crossing moves no material.
- When the flows can put a stock exactly on its bound or threshold, the engine posts a small
  correction. It posts it on the legs that move the stock toward that value, in proportion to their
  rates. This placement is a preference. A placement can break a hard relation of the author, a
  frozen allowance, a capacity, or the range of another stock. In that case, the engine does not
  make it.
- A run fails only when a hard rule breaks by more than its band.

The engine pages give the details ([engine/README.md](../engine/README.md)).

## Near-ties

A tiny difference can change a discrete result. A trigger fires or not, a branch goes one way or
the other, a claim gets service or not. The engine does not calculate more precisely. It detects the
case and marks it.

- A decision is a near-tie when the two sides of the comparison that decides it are inside their
  band, now and an instant later.
- The trace marks a near-tie with the detail `near`: the origin, the comparison, the difference and
  the tolerance, in canonical units.
- The entry `fire` of the trace marks a firing. The entry `miss` marks a trigger that came near and
  did not fire. The entry `release` marks a gate that released.
- If a trigger fires because a comparison is inside its band, the `fire` entry also has a
  `band_entry` detail. It gives the deciding comparison, its signed difference and its band.
  The firing keeps this evidence even if the value leaves the band immediately after it fires.
  For example, a draining stock can have a small positive balance when its empty-stock trigger fires.
- Sides that cross through the boundary are no near-tie. The time of the crossing decides.
- `napkin run` gives a summary of the near-ties under its table ([cli.md](../cli.md)).

A threshold that sits at the edge of its band can decide differently under other settings, another
solver or another platform. The trace says where this can happen.

## Numerical settings

The configuration of a run holds its numerical settings. A model sets only the longest step, with
`resolution` on its scenario line.

| Setting | Default | What it sets |
| --- | ---: | --- |
| `rtol` | 1e-9 | Sets the relative tolerance for integration. It also affects the comparison factor. |
| `atol_factor` | 1e-10 | Sets the absolute tolerance for a stock as a fraction of its scale. It also affects the comparison factor. |
| `max_step` | 1 h | The longest step of integration. `resolution` sets it for the default run. |
| `max_evaluations` | 2,000,000 | The most evaluations of the rates in one run |
| `crossing` | 1e-8 h | The tolerance in time of a crossing, and the least time between two moments that the engine tells apart |

The engine chooses its own steps. A run that needs finer steps sets `max_step`.

## Reproducibility

- **The same run is deterministic.** On the same machine, repeat the run with the same code,
  configuration, seed, thread settings and breakpoints. The two records agree bit for bit.
- **Other runs agree within tolerance.** A sample alone or in a batch gives values that agree within
  the stated tolerances, not bit for bit. So do another solver and another platform.
- A threshold at the edge of its band can fire differently across those settings. The near-ties in
  the trace show where.
- If you resume from a checkpoint without an edit, the run makes the same decisions in the same
  order as the uninterrupted run. The recorded values agree closely. The solver can take different
  steps. Inside a long step, the relative difference between two readings can exceed `rtol`.
  A firing inside the band can stop a stock before it reaches a bound. In that case, only the run
  that reaches the bound records that contact and the flow switches it causes. The firing in the
  other run records the remaining difference and the band. All later decisions must agree.
  [Breakpoints, checkpoints and edits](events.md#breakpoints-checkpoints-and-edits).
- A checkpoint saves the number of rate evaluations that the run has used. After a restore, the
  solver can need more rate evaluations to prepare its next step. These evaluations use the remaining
  `max_evaluations` allowance.
- A budget of a solver counts work, never seconds. A run that succeeds on one machine succeeds on
  another ([flows-and-solvers.md](flows-and-solvers.md#budgets)).
- The draws of a sampled run are keyed by the seed, the place of the draw and its owner. Another
  step size, an extra report or a skipped branch moves no draw
  ([values-and-types.md](values-and-types.md#the-run-mode)).

## The explicit-time rate check

The engine checks requests and capacities that depend on time. They can also use fixed inputs or captured parameters.
For each numerical integration step, the engine checks how much of the rate the step could miss.
It calculates an upper bound on this amount for the mathematical formula. Then it adds an
estimate of the floating-point error. The bound and the estimate apply to each part of the step
from its start. The estimate is not a proof.

If the mathematical bound exceeds the amount tolerance, or the engine cannot calculate that bound,
the engine tries a shorter step. At the crossing tolerance or the smallest possible solver step,
the engine accepts the step and marks the interval if the bound still exceeds the tolerance.
It also marks the interval if the bound is still unavailable.

If the mathematical bound is within tolerance and only the estimate exceeds the tolerance,
the engine accepts the step and marks the interval. The amount that the step could miss
in the floating-point calculation is still uncertain.

The trace records a `rate_unresolved` entry when the run accepts that part of the step.
The entry gives the setting, the accepted interval, the amount tolerance, the reason, the bound
and the estimate. Read `mathematical_bound` for the bound of the formula. Read `bound_with_roundoff`
for that bound plus the estimate of floating-point error. It is an estimate, not a bound.
A value of `null` means that the engine could not calculate a finite value.
This check applies to the rate setting before flows share the available supply or capacity.
Use `record.entries('rate_unresolved')` in Python to read these entries.

The run also reports how many time-dependent settings read state or a lookup.
The check excludes these settings, including a state that happens to hold a constant value.
Each distinct setting counts once from the first installation where it has such a dependency.
An event occurrence has its own settings. A checkpoint retains the count for occurrences that already finished.
Read `record.rate_guard_note` in Python or `rate_guard_note` in the output of `napkin run --json`.
