# The six methods

Between two moments, each connected set runs on one method. A method is a `Way` in the code
(`napkin/engine/timeline/way.py`). `Ways` (`napkin/engine/timeline/ways.py`) holds the instances of
a run and gives the timeline the same operations for every method:

- the value of a stock and the rate of a flow at a time inside the present window of an instance;
- `peek()`, the time of the next event inside an instance, and `step()`, which commits it;
- `cut(t)`, which commits a segment that went past a moment up to that moment;
- `build(sets, values, t)` and `retire(ids)`.

The engine terms on this page (connected set, segment, contact, ledger, near-tie) are defined in
[README.md](README.md#engine-terms). The other terms are in
[the terms of the language](../language/README.md#terms).

## How the plan chooses a method

`Plan.connect` (`napkin/engine/timeline/plan.py`) makes the connected sets. A rate "moves" when a
request or a capacity reads a moving stock or the time, through formulas, reductions or dynamic
reads. The plan gives each set its method by these rules, in this order:

1. A set that a declared solver owns runs on Declared. When its problem reads a moving stock or the
   time, it runs on MovingDeclared.
2. A pipe with no stock at either end runs on Sparse when its inputs move, else on Lines.
3. A set whose rates do not move runs on Family when it has one directed flow and no endpoint
   settings. Any other such set runs on Lines.
4. A set whose rates move runs on Component when all of these hold:
   - all its flows are directed (no route, no flow with legs);
   - no endpoint of its stocks has a setting;
   - no keyed read that it reads moves;
   - it has at most 150 stocks (`plan.LIMIT`);
   - each stock meets at most one flow on each side.
5. Any other set whose rates move runs on Sparse.

An endpoint setting is a capacity or a request of an `outflow` or an `inflow` of a stock, or a
statement of a stage that sets one (`Plan.settled`).

A moment that changes a set builds it again (`ways.py`): a flow that joins or leaves, a stage that
writes a value that a rate reads, or a rate of another set that changes. The new set can have
another method. Every other set continues in its instance.

This package has one set of each method. Its `units.json` declares the litre:

```json
{"L": {"kind": "volume", "dimensions": {"volume": 1}, "scale": 1}}
```

```scn
scenario "Six methods"
    horizon 10 h

pipe:
    water: L = 20 in [0, 20]
    flow drain: this.water -> SINK
        request = 3 L/h

junction:
    water: L = 20 in [0, 20]
        outflow.capacity = 4 L/h
    flow a: this.water -> SINK
        request = 3 L/h
    flow b: this.water -> SINK
        request = 3 L/h

tank:
    water: L = 20 in [0, 40]
    flow leak: this.water -> SINK
        request = formula(this.water / (5 h))

basin:
    water: L = 20 in [0, 40]
        outflow.capacity = 3 L/h
    flow out_a: this.water -> SINK
        request = formula(this.water / (5 h))
    flow out_b: this.water -> SINK
        request = 1 L/h

provider:
    store: L = 30 in [0, 30]
    flow serve: this.store -> SINK
        request = 4 L/h
    plan = solver:
        solve_for:
            this.serve.actual_rate
        constraints:
            this.serve.actual_rate <= 2 L/h

mover:
    store: L = 30 in [0, 30]
    flow serve: this.store -> SINK
        request = 4 L/h
    plan = solver:
        solve_for:
            this.serve.actual_rate
        constraints:
            this.serve.actual_rate <= this.store / (10 h)
```

The plan lists each set with its method:

```python
import napkin
from napkin.engine.timeline import Plan

model = napkin.load_scenario('six')  # the folder of the package
for found in Plan.of(model.program, model.configuration).sets:
    print(found.way, found.moves, found.flows)
```

| Entity | Method | Why |
| --- | --- | --- |
| `pipe` | Family | One directed flow, a constant request, no endpoint settings. |
| `junction` | Lines | Two flows share an endpoint with a capacity. |
| `tank` | Component | The request reads the moving stock. |
| `basin` | Sparse | The request moves, and the stock has an endpoint setting and two outflows. |
| `provider` | Declared | A solver owns the flow, and its problem reads nothing that moves. |
| `mover` | MovingDeclared | The solver's constraint reads the moving stock. |

The `found.way` of a MovingDeclared set is `declared` with `found.moves` true.

## Family

`napkin/engine/timeline/family.py`. All sets of one directed flow whose rates do not move run
together, as rows of arrays. Such a flow asks `min(request, capacity)` from moment to moment, so its
stocks are straight lines.

- `begin(t)` evaluates the rates of every row as columns and starts their lines.
- `advance(until)` takes, in time order, each row whose stock reaches its bound before `until`. The
  stock is put exactly on the bound, and the flow stops.
- `refresh(t)` evaluates the rates again at a key time and starts again the lines whose rate changed.

A formula that the members of a template share is evaluated once over the rows. The recorder takes
exact pieces at each change of a line.

## Lines

`napkin/engine/timeline/lines.py`. A set whose rates do not move runs on one network
(`napkin/engine/timeline/network.py`), with any number of stocks. Its rates hold from moment to moment, and each
stock is a straight line.

- Local sharing at an instant (`network.Instant.settle`) gives the rates that hold just after the
  instant. A stock stays on a bound while its sharing keeps it there.
- A moment solves again only the coupled parts that a change reaches: the flows at the stock that met
  its bound, the flows whose requests or capacities changed, and the stocks that left a bound.
- A part has a closed form where one holds (one flow, or groups in supply order). Else
  `selection.select` applies the selection order of local sharing: the hard rows, fair sharing tier
  by tier, the preferred routes, then the values nearest their targets.
- Where every flow is directed and rigid and no endpoint has a capacity or a request, a moment solves
  only the groups downstream of the change, upstream first.

Where local sharing has no defined answer, the run stops and names the stocks: a ring of empty
stocks that feed one another, or a ring of full stocks that pass room around.

## Component

`napkin/engine/timeline/component.py` gives one connected set to the continuous engine
(`napkin/engine/continuous/`). The set makes its segments one after the other. A segment ends at the
horizon, where a stock reaches or leaves a bound, or where a rate changes its branch.
`kernels.Classifier` chooses the form of each segment:

1. **Affine.** When every rate, request and capacity stays constant through the segment, each stock is
   a straight line, exactly.
2. **Compartments.** When the moving stocks form a positive linear system of compartments, the
   segment is the matrix exponential of the system (`kernels.MatrixExponential`), exactly. A stock
   whose rate reads no stock is a line.
3. **Numerical.** Else the Radau method integrates the segment with dense output
   (`integrate.numerical_segment`). The engine takes the Radau steps itself (`integrate.radau`).

The continuous engine evaluates the formulas of a component with one generated program
(`napkin/expressions.py` `compile_program`). Where that program fails, each formula is evaluated
where a rate reads it, so a formula on a side that a rate does not take fails nothing.

After a numerical segment, the engine samples the dense solution at each step cap from the start of
the segment (`integrate.hidden_excursion`). When a sample crosses a watched threshold and no root
ended the segment, the run stops: the value crossed the threshold and came back inside one step. A
shorter `resolution` makes the samples closer.

At bounds, `Held.bound_allocation` and `engine/allocation.py` cut a flow to what the stock can pass:
a flow out of an empty stock gets what comes in, and a flow into a full stock is cut. Where local
sharing would let a flow carry more than its request, the run stops and names the stock.

Four parts of Component remove roundoff at a bound. `tests/engine/test_roundoff_properties.py` tries
to break them with many seeded cases:

- **A residual goes to a leg** (`Allocation.balance`). When what comes into a stock on a bound equals
  what goes out but for roundoff, the residual is no rate. The engine moves it to a material leg, so
  the total does not change and the stock stays on its bound.
- **A short path of the closed form** (`Allocation.served_in_full`). It gives the same fractions from
  the same doubles as the closed form, and it answers yes only when every unit is served in full.
- **A face that runs out within one ulp of the time** (`continuous/bounds.py` `rounded_faces`). Before
  the numerical stage, the engine puts such a stock on its lower bound, with its balancing leg.
- **A face that departs** (`continuous/bounds.py` `depart_faces`). A stock on its zero face with a
  positive rate departs. The engine calculates the field again one ulp above zero, with the bound
  released. When that field does not point up, the run stops: the face would chatter.

## Sparse

`napkin/engine/timeline/sparse.py`. A set whose rates move runs here when it is no Component, with
any number of stocks ([change 3](../design/decisions.md#change-3)). Sets whose settings read the moving rates of
another set integrate together, level by level.

- The state is the vector of its stocks. Its rates at a time and a state are the local sharing of the
  network there (`network.Instant`).
- SciPy's Radau integrates it, with the sparse pattern of its Jacobian.
- The flags of the bounds hold through a segment. A segment ends where a stock reaches a bound, where
  a stock leaves a bound, or where a keyed read selects another member.
- A failure of the solver, or 1,000 accepted steps in a row each shorter than the crossing tolerance,
  stops the run. Where a setting reads a stock through a condition, the message says that the rates
  chatter, and names the stocks and the flows.

## Declared

`napkin/engine/timeline/declared.py`, `DeclaredWay`. A declared solver owns the set. Its problem reads
nothing that moves, so its answer holds between moments, its rates are constant and each stock is a
line. The problem is solved once in a round, after the stages commit. A problem equal to the last one
is not solved again. Each solve is a `solve` entry of the trace.

A stock that reaches a bound is put on it, and the problem is solved again with the row of that
bound. A stock whose answer moves it away from its bound is released at once, and the problem is
solved again without the bound (`DeclaredWay._settled`). [solver.md](solver.md) tells how the solver
selects its answer.

## MovingDeclared

`napkin/engine/timeline/declared.py`, `MovingDeclared`. The problem of the solver reads a moving stock
or the time, so its rates follow the state. SciPy's Radau integrates the stocks. At each trial state
of a step, the rates are the answer of the selection order there, on the solver's kept instance. The
engine does not trace these trial solves.

- The flags of the bounds hold through a segment. A segment ends where a stock reaches a bound, where
  the answer would move a stock off its bound, or where a comparison changes branch.
- The engine locates each contact on the incoming dense trajectory, and solves the problem there with
  the new flags.
- A failure of an evaluation is placed at its time: the steps become shorter, by halves, until the
  failure lies within the crossing tolerance of the last step that answered.

Each evaluation of the rates is a whole solve. So a set of more than 20 stocks (`declared.MOVING`)
stops the run when the engine builds it. The message names the solver and tells the author to read
values that hold between moments, or to split the set.

## Integration tolerances

| Method | Absolute tolerance of a stock | Relative tolerance |
| --- | --- | --- |
| Component | `atol_factor` times the integration size of the stock | `rtol` |
| Sparse, MovingDeclared | `atol_factor` times the scale of the stock | `rtol` |

The integration size of a stock is its declared `scale`. A stock with no `scale` takes the largest of: 1 in its
unit, its start value, its finite bounds, and the largest start value of the stocks that flows connect
it to, directly or through other stocks (`Run.sizes_of`). The scale of a stock is its declared `scale`, or else 1 in its unit.

**The step cap** is `max_step`, 1 h by default, or the `resolution` of the scenario. It is the interval
at which a numerical method reads its roots and its field. It does not limit the steps of the solver,
which its own control of the error decides. Inside a step longer than the cap:

1. At each half of the cap, the engine compares the field with the rate of the dense solution
   (`integrate.departure`). When their difference times the step is outside the solver's tolerance,
   the engine does not use the step, and tries again from its start with a shorter limit.
2. At each whole cap, the engine reads the roots.

After a fall to the cap, the solver waits before it tries a longer step again. The wait doubles with
each fall in a row, to 32 steps of the cap at most (`integrate.Limit`). A pulse of a rate that lasts
less than half a cap can fall between two reads and stay unseen. A model with such a pulse sets a
`resolution` shorter than the pulse.

## Branches and the comparison band

Each comparison other than `==` and `!=`, each pair of operands of `min`, `max` and `clip`, `abs`, and
the two ends of a membership, is a switching surface when one side moves
(`integrate.switching_surfaces`). One step never mixes two branches:

- At the start of a segment, the engine classifies each surface by its comparison band
  (`integrate.comparison_side`): a gap inside the band is zero, else its sign.
- A segment that starts at a switch starts on its far side (`integrate.far_sides`). The method
  supplies the velocity: the rates of its allocated field, so a stock held on a bound uses its
  physical net rate.
- Between switches, each formula keeps the branch that its segment departed on
  (`integrate.branch_expression`). A held zero makes the strict comparisons false and the inclusive
  comparisons true through the whole segment, also at the trial states of the solver.
- A held equality arms a root where its operands leave the band (`integrate.switching_roots`). A
  departed contact arms a root for a later return.
- Only a located switch changes a branch. A check over an accepted window reads the held branches
  (`Way.held_value`), never a fresh decision at each time.

Component, Sparse and MovingDeclared supply the same information to these functions. Family, Lines
and Declared have no moving rate, so their branches change only at moments.

## Bounds inside a step

A stock can cross a bound and come back inside one step. So the engine reads the whole step, not only
its two ends:

- **On a Radau step** (`continuous/dense.py`, `bound_crossings`). The dense output is a cubic in time.
  The engine cuts each candidate cubic at its turns and finds the first outward arrival at each bound.
  An exact touch from inside counts. A stationary stock on its bound, or an inward departure, does not.
- **From a bound.** A step that starts on a bound must reach a different float before the engine
  records that bound again (`dense._distinct_turn`). A release watches the next distinct level in the
  release direction (`StockFaces.armed`).
- **On a held line** (`engine/allocation.py`, `StockFaces.contact`). The time of the next physically
  distinct bound. A residue inside the band, already on its bound, cannot give the same root again.
  Family, Lines, Declared and Component use it for a stock on a line.

The numerical Component checks a truncated trial against the limits of a held stock. When the trial
breaks them, it integrates again to the located contact before it publishes the segment.

## Release from a bound

A stock on a bound leaves it only when its net rate away from the bound is strictly more than 10⁻¹²
of its gross traffic: the sum of its incoming and outgoing rates (`engine/departure.py`). Equality
keeps the bound.

- Near that boundary, the engine compares the individual rates in exact arithmetic before they cancel
  (`departure.refined`).
- When numerical uncertainty still covers the boundary, the stock keeps its bound and the trace gets
  a `settle` entry with a near-tie (`departure.record_tie`).

The ledger keeps what the legs carried. In this package an inlet of 1 L/h and an outlet of
0.999999999999 L/h meet an empty stock:

```scn
scenario "A stock that stays on its bound"
    horizon 2 h

tank:
    water: L = 0 in [0, 10]
    flow inlet: SOURCE -> this.water
        request = 1 L/h
        capacity = 1 L/h
    flow outlet: this.water -> SINK
        request = 0.999999999999 L/h
        capacity = 0.999999999999 L/h
```

The stock reads 1e-12 L at 1 h and 2e-12 L at 2 h. Each leg carries its full rate. The net rate,
1e-12 L/h, is less than 10⁻¹² of the traffic, about 2e-12 L/h, so the stock keeps its lower bound. The
balance stays inside its comparison band, 1e-9 L.

## Contacts and moments

A contact can fall near a scheduled moment. It joins that moment only when both tests pass (amended
[change 27](../design/decisions.md#change-27)):

1. Its located time is within the crossing tolerance of the moment's time, on either side.
2. At the moment's time, the stock on its incoming trajectory is inside its own comparison band of
   the bound or threshold (`Way.separate_contacts`).

Else the contact is a moment of its own, at its located time. An earlier contact runs before the
scheduled stages. A later contact stays pending across those stages when their writes keep its
trajectory. A run whose horizon comes before the contact ends at the horizon.

For a comparison of several moving stocks, each stock that the condition reads directly must be inside
its own band of its reading at the located time, and the whole comparison must qualify too
(`Triggers.anchor`). A rate that a condition reads can give a threshold, but it gives the condition no
claim on its stock. A contact that joins a moment has a `contact` entry in the trace, with its located
time and its signed difference from the moment, in hours.

In this package the stock fills at 1 L/h until its capacity, `2 - t` L/h, falls below the request at
1 h. A stage is due at 1 h, and a trigger watches 1.000000005 L:

```scn
scenario "A contact near a stage"
    horizon 1.5 h

tank:
    water: L = 0 in [0, 10]
    seen: h = 0 h
    flow fill: SOURCE -> this.water
        request = 1 L/h
        capacity = formula(2 L/h - t / (1 h) * 1 L/h)
    check = event():
        when t >= 1 h:
            this.check.start()
        after 0 h:
            this.seen = t
    full = event():
        when this.water >= 1.000000005 L:
            this.full.start()
        after 0 h:
            this.seen = t
```

| Time (h) | Trace entries |
| --- | --- |
| 1.0 | `contact` of `tank.fill` (the switch of its capacity, difference 0), then the firing and the stage of `tank.check` |
| 1.0000000050000009 | the firing and the stage of `tank.full` |

The trigger's contact is 5e-9 h after the stage, inside the crossing tolerance. But at 1 h the stock is
1 L, 5e-9 L from its threshold, outside its band of about 1e-9 L. So the contact is a moment of its own.

## Placement at a contact

The books always balance. Only a posted transfer changes a balance. At a contact that the engine
admits, it can put the stock exactly on its bound or threshold. That placement is a preference
(the owner's ruling on physical balances, [change 29](../design/decisions.md#change-29)):

1. The engine calculates the signed difference between the incoming trajectory and the target.
2. It posts that correction to the legs that move the stock toward the target, in proportion to their
   rates just before the contact. Each leg's other end gets the matching post.
3. When no leg moved toward the target, it keeps the amounts that the legs carried.
4. It applies a connected placement together, or not at all (`Stocks.faces`).
5. When the correction would break a hard equation of a solver, a frozen allowance, a capacity or the
   limit of another stock, it keeps the delivered amounts. When the affected stocks are inside their
   bands, it skips the correction and reports the tied targets. A breach beyond a band stops the run.

Independent placements in the same moment can still commit. The run continues from the outcome that
the ledger accepted: each method rebases its trajectory there (`Stocks.install`).

## The exact stock ledger

`napkin/engine/timeline/stocks.py` keeps, for each stock, its exact balance, the signed amount already
posted, and the time of the last post.

- **The method supplies amounts.** Each method gives the cumulative amount that each leg carried from
  the start of its instance (`Way.transferred`). Family, Lines and Declared use `HeldAmounts`: rate
  times time. Component, Sparse and MovingDeclared integrate each leg's rate on the accepted dense
  output (`continuous/transfers.py`). Trial states of the solver never post.
- **A read does not post.** `Stocks.stock_balance` calculates a balance at a time without a change.
  `Stocks.post_stock` posts it once at a time. The engine posts a stock at these events: a stage
  reads or writes it, a rate changes, a set is built again, an occurrence finishes, a checkpoint
  saves, or the run ends.
- **An accepted prefix only.** A reader sees only the transfers up to the accepted time of the
  method (`MovingTransfers._transferred`). A segment that went past a moment gives no credit for its
  tail.
- **A stage.** A stage sees its own earlier writes (`Moment.stage_balance`). `=`, `+=` and `-=` on a
  stock calculate on its exact balance ([change 31](../design/decisions.md#change-31)). An
  assignment that misses a bound by less than the tolerance of the stock puts the stock on the bound.
- **A move.** A `move` debits and credits exactly the amount that it writes
  ([change 32](../design/decisions.md#change-32)). It checks both resulting balances against their
  exact bounds before it posts either end. When a result is outside a range, the move fails and moves
  nothing. A move whose amount is the source stock itself moves the full balance of that stock.
- **A new instance.** When a set is built again, the old instance closes its posts, and the new one
  starts from the exact balance (`Stocks.release_stock`).

The ledger and a method's trajectory agree to a few units in the last place. The direction of that
difference depends on the platform. So no decision may change with those last places.
[verification.md](verification.md#the-roundoff-probe) tells how the tests check it.

## External transfers

An edit of a stock at a stop is a transfer from or to outside (`Stocks.external`). The ledger posts
the signed difference from the stock's balance just before the edit, also after earlier statements of
the same stage. The record gives the sum of these transfers as the history `external` of the stock
(`tank.water.external`, in the stock's unit). The history has a piece at each edit, from the first. A
stock with no edit has no such history, and its ledger reads 0. A request can name the ledger alone.

## Retirement and frozen occurrences

When an occurrence finishes, each of its stocks that a flow or a move met must be empty within its
conservation allowance (`atol_factor` times its scale). Else the run stops and names the occurrence,
the stock, the amount, the unit and the time.

A finished occurrence is frozen ([change 24](../design/decisions.md#change-24)). An assignment to it,
or a `move` of a nonzero amount into or out of its stock, stops the run (`Occurrences.writable`). For a
flow, `Occurrences.carried` adds the amounts that pass through each side of the stock after
retirement, over all connections and segments. The first amount over the allowance stops the run. The
message lists every leg that adds to the violation, by stock name, outflow before inflow, then the
order of declaration. The text names the first five and counts the rest.
