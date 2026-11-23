# Flows and solvers

A **flow** moves a quantity per time between two stocks, or between a stock and `SOURCE` or `SINK`.
This page gives the three forms of a flow, the endpoints of a stock, the rules of a request and a
capacity, local allocation, and declared solvers. The words in bold are the
[terms](README.md#terms) of the documentation. How the engine calculates the rates is in
[engine/README.md](../engine/README.md) and [engine/solver.md](../engine/solver.md).

## Contents

1. [Directed flows](#directed-flows)
2. [Endpoints](#endpoints)
3. [`SOURCE` and `SINK`](#source-and-sink)
4. [Request, capacity and actual rate](#request-capacity-and-actual-rate)
5. [Stocks at their bounds](#stocks-at-their-bounds)
6. [Routes and legs](#routes-and-legs)
7. [Flows with legs](#flows-with-legs)
8. [What each flow scope can see](#what-each-flow-scope-can-see)
9. [Flows that events create](#flows-that-events-create)
10. [Local allocation](#local-allocation)
11. [Declared solvers](#declared-solvers)
12. [What a solver decides](#what-a-solver-decides)
13. [The selection order](#the-selection-order)
14. [A solver over collections](#a-solver-over-collections)

## Directed flows

Write `flow name: source -> sink` in an entity, a template or an event. Write its properties on the
rows under it.

```scn
tank:
    readonly water: L = 8 in [0, 20]

clinic:
    flow delivery: tank.water -> SINK
        capacity = 5 L/h
        request = 3 L/h
```

The clinic gets 3 L/h until the tank is empty at 2 h 40 min. Then the **actual rate** is zero. The
**request** is still 3 L/h and the **capacity** is still 5 L/h. The flow drains `tank.water`, though
`readonly` bars a statement such as `tank.water = 10 L`.

- An end is `SOURCE`, `SINK` or the path of a stored number: `this.water`, `this.origin.power`
  through a link, `tank.water` of a named entity, a value at the top level, or a local of an
  occurrence.
- An input, a formula, a link and a parameter are no ends. A flow ends at a stored value.
- The ends of a flow are fixed for the run.
- The unit of the rates is the unit of the stock per time. A flow from `L` stocks has rates in
  `L/h` or any unit of the same dimension.
- Two directed flows can move a quantity in opposite directions between the same stocks. Each is a
  transfer of its own.
- Two flows between the same ends are two flows with two identities.
- The line of a flow holds its two ends and its citations. The properties go on rows under it.

## Endpoints

A stored number that a flow meets has two endpoints: `outflow`, the flows that leave it, and
`inflow`, the flows that enter it. Write the settings of an endpoint under the stock.

```scn
reservoir:
    water: L = 20 L in [0 L,]
        outflow.capacity = 10 L/h
        outflow.allocation = priority(hospital.delivery, garden.delivery)
```

| Setting | What it does |
| --- | --- |
| `outflow.capacity`, `inflow.capacity` | A hard limit on the total rate in that direction |
| `outflow.request`, `inflow.request` | A soft request on the total rate in that direction |
| `outflow.allocation`, `inflow.allocation` | The rule that shares a limit among the flows: `priority(...)` or `proportional()` |

| Read | What it gives |
| --- | --- |
| `x.outflow.actual_rate`, `x.inflow.actual_rate` | The sum of the actual rates of the flows in that direction |
| `x.outflow.request`, `x.outflow.capacity` | The setting of the endpoint |
| `x.outflow.flows`, `x.inflow.flows` | The collection of the flows that leave or enter the stock now |

- A setting can read its own stock: `inflow.request = formula(max(0 L, 15 L - this.water) / (2 h))`.
- A setting can also stand at the top level by its full path: `tank.water.outflow.capacity = 2 L/h`.
- `sum(water.outflow.flows.actual_rate)` equals `water.outflow.actual_rate`.
- The key of a member of `flows` is the creation number of the connection. Each leg has its own
  number.
- The `flows` of an endpoint hold the current connections, also a flow that is closed or that gets
  no quantity.
- A flow of the endpoint can read its far end: `main.sink`, when `main` is a member of the outgoing
  flows.

## `SOURCE` and `SINK`

`SOURCE` and `SINK` are the boundaries of the model. `SOURCE` supplies a quantity from outside, and
`SINK` takes it out.

- `SOURCE` stands on the left of `->`, and `SINK` on the right.
- Neither boundary makes a request. Only the declared settings and the connected stocks limit the
  quantity.
- The stock at the other end gives the unit. One spelling serves every dimension: a water flow from
  `SOURCE` and a power flow from `SOURCE` do not join.
- A direct `SOURCE -> SINK` flow needs a request or a capacity written with its unit, to give it a
  dimension.
- A route cannot end at `SOURCE` or `SINK`. Use two directed flows for an import and an export.

## Request, capacity and actual rate

Keep the three rates apart. The request says what a flow asks for. The capacity says what it may
carry. The actual rate says what it carries.

| Property | Kind | When the model leaves it out |
| --- | --- | --- |
| `request` | Soft: a preference of service | Zero: the flow makes no claim |
| `capacity` | Hard: a limit on the rate | No limit of its own. A report gives it as unavailable. |
| `actual_rate` | The result of the run | The run always calculates it |

- A request and a capacity take a number or a formula. A number captures the rate once. A formula
  follows the values that it reads, also a stock that moves between moments.
- `capacity = 0 L/h` closes a flow. `request = 0 L/h` withdraws its claim.
- To open or close a flow during the run, a stage assigns its request or its capacity
  ([events.md](events.md#assign-a-value)).
- A request and a capacity must be finite, of the right dimension, and not below zero. A negative
  rate of a directed flow stops the run.
- A request is soft. A higher objective of a solver can make a rate above the request useful,
  inside every hard limit. A consumer that cannot take more than it asks for says so with a
  capacity: `capacity = formula(this.use.request)`.
- A plain `capacity = this.use.request` captures the request at the start only.

A request on an endpoint applies to its total. The same litre can serve the request of a flow, of
its source and of its sink. Each request measures the actual rate on its own scope.

```scn
source:
    water: L = 100 L in [0,]
        outflow.request = 10 L/h

sink:
    water: L = 0 L in [0,]
        inflow.request = 6 L/h

pipe:
    flow carry: source.water -> sink.water
        request = 8 L/h
```

The pipe carries 10 L/h: the least rate that serves all three requests. With `capacity = 7 L/h` on
the pipe, it carries 7 L/h. The shortfalls are then 3 L/h at the source, 1 L/h at the pipe and 0 at
the sink.

## Stocks at their bounds

The range of a stock is its inventory bound. A flow never takes a stock outside its range.

- At its lower bound, the outflows of a stock can use what flows in at the same time.
- At its upper bound, the inflows can use the room that the outflows make.
- A stock held at `[0, 0]` is a junction: its total inflow equals its total outflow at each
  instant. A junction can carry 8 W through a stock of 0 Wh.
- A stock inside its own **comparison band** of a bound counts as on that bound
  ([numerics.md](numerics.md#the-comparison-band)).
- A stock leaves its bound only when the net rate away from it is more than 10⁻¹² times the sum of
  its gross inflow and outflow. Equality holds the stock on the bound.
- The books of each stock balance. The engine posts each transfer equally at both ends.

## Routes and legs

A **route** is a flow in both directions: `flow link: west.water <-> east.water`. It has one signed
actual rate. A positive rate moves the quantity from west to east, and a negative rate from east to
west.

```scn
west:
    water: L = 10 L in [0 L, 20 L]

east:
    water: L = 10 L in [0 L, 20 L]

channel:
    flow link: west.water <-> east.water
        request = -3 L/h
    backward = formula(this.link.backward.actual_rate)
```

- The `request` of a route is signed. Its sign gives the direction that the route asks for.
- The `capacity` of a route limits the magnitude of its rate, and it is not below zero.
- Both ends are stocks that can give and take the quantity. A stock at the end of a route is a stock
  by use.
- A route has two **legs**. The engine posts the transfer once.

| Endpoint collections | Leg | `actual_rate` of the leg |
| --- | --- | --- |
| `west.water.outflow.flows`, `east.water.inflow.flows` | `link.forward` | `max(link.actual_rate, 0 L/h)` |
| `east.water.outflow.flows`, `west.water.inflow.flows` | `link.backward` | `max(-link.actual_rate, 0 L/h)` |

At an actual rate of −3 L/h, the forward leg reads 0 L/h and the backward leg reads 3 L/h. The
request of a leg is the positive part of the request in its direction. The legs add no claim of
their own.

- Name a leg, not the route, in a `priority(...)` of an end: `priority(link.forward, backup)` on
  `west.water.outflow`. A bare route, or a leg in the wrong direction for that end, is an error.
- In `solve_for`, name `link.actual_rate`, the one decision of the route. The rates of the legs
  follow from it.

## Flows with legs

A flow with legs moves several quantities as one activity. Each leg is a directed flow in its own
unit. All the legs share one served fraction.

```scn
site:
    crew: Crew = team
    controls_work: work_unit = 40 work_unit in [0,]
    controls_done: work_unit = 0 work_unit in [0,]
    flow restore:
        flow labor: this.crew.hours -> this.crew.used
            request = 4 crew_h/h
        flow work: this.controls_work -> this.controls_done
            request = 8 work_unit/h
```

- Each leg has its own request, the rate at full service, and its own capacity.
- `restore.served_fraction` is a plain number from 0 to 1. At the fraction `f`, the actual rate of
  each leg is `f` times its request.
- A shortage on any leg with a positive request lowers the fraction of the whole activity.
- A leg with a zero request moves nothing. When every leg requests zero, the fraction is zero.
- The parent has no request, no capacity and no actual rate. `restore.actual_rate` is an error.
  Read a leg (`restore.labor.actual_rate`) or the fraction.
- A leg is a member of the `flows` of its own ends, and the `priority(...)` of its end can name it.

With labor limited to 2 crew_h/h, the fraction is 0.5. Labor then moves 2 crew_h/h and work moves
4 work_unit/h.

## What each flow scope can see

| Scope | What it reads | What the model sets |
| --- | --- | --- |
| Directed flow `x` | `.source`, `.sink`, `.actual_rate`, `.request`, `.capacity` | `.request`, `.capacity` |
| Route `link` | The signed `.actual_rate` and `.request`, `.capacity`, `.forward`, `.backward` | `.request` (signed), `.capacity` |
| Leg of a route `link.forward` | `.actual_rate`, `.request`, `.source`, `.sink` | Nothing |
| Flow with legs `restore` | `.served_fraction`, and each leg as a directed flow | The `.request` and `.capacity` of each leg |
| Endpoint `y.outflow`, `z.inflow` | `.flows`, `.actual_rate`, `.request`, `.capacity` | `.request`, `.capacity`, `.allocation` |
| Solver `provider.charging` | Its unknowns by their paths | Its sections only |

- `f.source` and `f.sink` read the stock at that end, with its amount and its bounds. An end at
  `SOURCE` or `SINK` has no stock to read.
- The ends are fixed, so no statement assigns a value through `f.source` or `f.sink`. Assign the
  stock by its own path.
- No statement assigns an actual rate or a served fraction.

## Flows that events create

A flow that an event declares belongs to each occurrence of the event.

- The flow joins the `flows` of its endpoints when its occurrence starts.
- It can move the quantity as soon as its rate and its ends allow. Set its capacity to zero if it
  must wait.
- It leaves both endpoints together when its occurrence finishes. It keeps its key and its ends.
  Its actual rate reads zero, and its last request and capacity stay as read-only values.
- A finished flow with legs reads a served fraction of zero.
- A later occurrence gets a new flow with a new identity. No key is used again.
- A flow of an entity stays connected for the whole run, also at a rate of zero.

```scn
tank:
    water: L = 100 L in [0,]

depot:
    deliver = event():
        flow pipe: tank.water -> SINK
            request = 2 L/h
        after 2 h
    started = formula(count(this.deliver.occurrences))
    connected = formula(count(tank.water.outflow.flows))
    asked = formula(sum(tank.water.outflow.flows.request))
    last_request = formula(this.deliver.occurrences.at(t).pipe.request)
    late = event():
        when t >= 3 h:
            this.late.start()
            reset when false
        after 0 h:
            this.deliver.start()

depot.deliver.start()
```

Delivery A runs from 0 h to 2 h. Delivery B starts at 3 h and runs to 5 h. The readings of a run to
6 h:

| Time | `depot.started` | `depot.connected` | `depot.asked` | `tank.water.outflow.actual_rate` | `depot.last_request` |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 h, A runs | 1 | 1 | 2 L/h | 2 L/h | 2 L/h |
| 2.5 h, A has finished | 1 | 0 | 0 L/h | 0 L/h | 2 L/h |
| 4 h, B runs | 2 | 1 | 2 L/h | 2 L/h | 2 L/h |

At 2.5 h, `last_request` reads the frozen request of A. From 3 h it reads B, the newest start. A
transfer that must continue after its event finishes belongs to the entity, where the event can
open it.

An occurrence must account for the quantity in its own stocks before it finishes
([events.md](events.md#a-finished-occurrence)).

## Local allocation

Each endpoint shares among its own flows by its own rule. This is the default, and it needs no
solver.

```scn
reservoir:
    water: L = 20 in [0, 20]
        outflow.capacity = 10 L/h
        outflow.allocation = priority(hospital.delivery, garden.delivery)

hospital:
    flow delivery: reservoir.water -> SINK
        request = 8 L/h

garden:
    flow delivery: reservoir.water -> SINK
        request = 12 L/h
```

`priority(a, b)` gives `a` the first access, and `b` the remainder. The hospital gets 8 L/h and the
garden 2 L/h. The default, `proportional()`, gives 4 L/h and 6 L/h. Both empty the reservoir in two
hours. This is the output of `napkin run` for the model, with `horizon 3 h`:

```text
                                      unit   0 h   1 h   2 h   3 h
reservoir.water                       L      20    10    0     0
hospital.delivery.actual_rate         L/h    8     8     0     0
hospital.delivery.request             L/h    8     8     8     8
garden.delivery.actual_rate           L/h    2     2     0     0
garden.delivery.request               L/h    12    12    12    12
reservoir.water.outflow.actual_rate   L/h    10    10    0     0
reservoir.water.outflow.capacity      L/h    10    10    10    10
reservoir.water.outflow.request       L/h    0     0     0     0
```

### The rules of an allocation

- `proportional()` serves the same fraction of each positive claim. It gives what a capped claim
  cannot use to the others. Write it to set the default again.
- `priority(a, b, ...)` orders distinct connections of the endpoint, from the first to the last.
- A route gives `link.forward` or `link.backward`. A flow with legs gives the leg at that endpoint.
- A projection ranks the rows of a table: `priority(customers.by(rank).delivery)`. A lower rank is
  served first. Members with equal ranks share in proportion.
- The flows that a `priority(...)` does not name share the remainder in proportion to their
  requests. A new flow of an event is such a flow.
- With one request on the endpoint and several equal flows that make no claim of their own, the
  endpoint splits the rate equally among them, and gives what a capped flow cannot carry to the
  others.
- An allocation ranks useful requested work. A preference alone moves no quantity.
- A stage can assign an allocation with `=`: `this.water.outflow.allocation = proportional()`.

A sink makes its request once:

```scn
supply:
    water: L = 100 L in [0,]

clinic:
    water: L = 0 L in [0, 50 L]
        inflow.request = 6 L/h
        inflow.allocation = priority(this.main, this.backup)
    flow main: supply.water -> this.water
        capacity = 4 L/h
    flow backup: supply.water -> this.water
```

The two rates are 4 L/h and 2 L/h. A request of 6 L/h on each pipe would make two claims.

### Sharing is local

Each endpoint decides with what it sees: its own inflow, and the claims on its own outflow. Nothing
makes service equal across endpoints unless a solver does it.

```scn
first:
    water: L = 0 in [0, 0]
    flow feed: SOURCE -> this.water
        capacity = 1 L/h
    flow to_a: this.water -> SINK
        request = 1 L/h
    flow onward: this.water -> second.water
        request = 1 L/h

second:
    water: L = 0 in [0, 0]
    flow to_b: this.water -> SINK
        request = 1 L/h
    flow to_c: this.water -> SINK
        request = 1 L/h
```

The first junction sends half down each pipe. A gets 1/2 L/h, and B and C get 1/4 L/h each. A
solver that names the four outgoing rates gives each of A, B and C 1/3 L/h. A solver that names only
`feed` leaves 1/2, 1/4 and 1/4.

The engine honors the stock bounds, the junctions and the local rules also when several rates depend
on one another. An empty or a full stock alone needs no solver.

## Declared solvers

A **solver** is a declared solver that an entity owns. It sets the rates and the values that it
names in `solve_for`. Declare a solver for a joint decision that no endpoint can make alone: a limit
across sites, a law that links two unknown levels, equal service across endpoints, or an order of
objectives.

```scn
clinic:
    staff_hours: h = 100 h
    outreach_minimum = formula(0.30 * this.staff_hours)

    staffing = solver:
        inputs:
            available = this.staff_hours
            minimum_outreach = this.outreach_minimum
        solve_for:
            care: h in [0 h, available]
            outreach: h in [minimum_outreach, available]
        constraints:
            care + outreach == available
        objective:
            maximize(care)
```

With 100 h, `clinic.staffing.care` is 70 h and `clinic.staffing.outreach` is 30 h. With 80 h, care
gets 56 h and outreach 24 h. These results describe an allocation. A read of them spends no staff
time.

| Section | What it holds |
| --- | --- |
| `inputs:` | Bindings `name = path`: a value, a flow, a member or a collection, read in the scope of the owner |
| `solve_for:` | The fields that the solver determines, and its new unknowns |
| `constraints:` | Hard relations that each answer satisfies |
| `objective:` | `minimize(...)` and `maximize(...)` lines, in their order of rank. The section is optional. |

- A solver belongs to an entity or a template. Each member of a template has its own solver.
- Inside the solver, a bare name is a binding of `inputs:` or an unknown of `solve_for:`.
- A binding brings the present value of its source, with its units, bounds and restrictions. An
  input of 8 W with a range `[0 W, 10 W]` gives 8 W. Its range does not let the solver choose
  10 W.
- `solve_for:` names stored numbers, actual rates of flows and routes, and served fractions. A
  projection names a field on each member: `routes.carried.actual_rate`.
- A new unknown is `name: type`, with an optional preferred value (`= v`), domain (`in [lo, hi]`) and
  scale. It is a number. A Boolean unknown is an error.
- A caller reads an unknown by its path, `this.staffing.care`. No statement assigns it.
- A value that a solver determines has one writer. A stage that also writes it is an error.
- A formula of known values gives a coefficient. A formula that reads an unknown gives its
  expression at the candidate answer.

### The language of a solver

A solver accepts a convex problem:

- relations `==`, `<=` and `>=` that are affine in the unknowns;
- their conjunction with `and` and `all(...)`, and a membership `x in [lo, hi]`;
- sums of unknowns, and products and quotients of unknowns by known numbers;
- objectives that are affine, or sums of positive parts to minimize:
  `minimize(max(0 W, east.request - east.actual_rate))`.

The compiler refuses each other form by name:

| Code | What it refuses |
| --- | --- |
| `solver_form` | A strict inequality, `!=`, `or`, `any(...)` or `not` of a relation, a relation under a condition, a choice or a lookup that an unknown keys, and a domain, preferred value or scale that reads an unknown |
| `nonlinear` | A product of two unknowns, a division by an unknown, a power or another function of one, `min` of one, and a positive part that is negated, maximized or on the large side of a relation |
| `participant` | A rate that a relation reads and that the solver does not determine, and a relation that reads nothing that the solver determines |
| `two_solvers` | Two solvers whose rates lie in one connected set of flows and stocks |

A Boolean formula of ordinary model logic can still use `or`, `not` and `!=`.

### One owner for a joint decision

When two solvers would choose rates that compete in one connected set, the model is refused with
both solvers named. One coordinating solver must own the joint decision. Ordinary flows that share
an endpoint use its local rule and need no solver.

```scn
east_site:
    energy: Wh = 0 in [0, 10]
    flow charge: SOURCE -> this.energy
        capacity = 6 W
        request = 6 W

west_site:
    energy: Wh = 0 in [0, 10]
    flow charge: SOURCE -> this.energy
        capacity = 6 W
        request = 6 W

provider:
    contract_limit: W = 8 W
    charging = solver:
        inputs:
            east = east_site.charge
            west = west_site.charge
            limit = this.contract_limit
        solve_for:
            east.actual_rate
            west.actual_rate
        constraints:
            east.actual_rate + west.actual_rate <= limit
        objective:
            minimize(max(0 W, east.request - east.actual_rate))
            minimize(max(0 W, west.request - west.actual_rate))
            minimize(east.actual_rate + west.actual_rate)
```

The objectives minimize the unmet request of East first, then of West, then the total draw. With
room in both batteries, East gets 6 W and West 2 W. When East is full and takes nothing, West draws
6 W.

## What a solver decides

A solver decides only the rates and the values that its `solve_for` names.

- A flow that the solver does not name keeps the local sharing of its endpoints. The solver sees
  it only through the limits that it puts on the named rates, so the books still balance.
- A relation or an objective that reads the rate of such a flow is an error (`participant`). To
  decide who gets the quantity, the solver names those rates.
- The engine settles each solver once in each round, after the stages of the round. It publishes
  the results of one solve together ([events.md](events.md#rounds-at-one-time)).
- An infeasible problem, an unbounded objective or a numerical failure stops the run with a
  diagnostic. No dependent trigger or report sees a partial answer.

## The selection order

A solver selects one answer in this order. The order is the same for three places and for thirty
thousand.

1. **Hard constraints.** The answer respects the domains, the capacities, the stock balances and
   every relation of `constraints:`.
2. **Objectives in their order.** The solver optimizes each objective line in written order, and
   keeps each optimum that it attains. A later objective chooses only among the answers that keep
   the earlier optima.
3. **Fair sharing by tier.** Among the answers that remain, the solver serves the claims. A positive
   request measures its served fraction, up to 100%. In one tier, the solver raises the smallest
   served fraction, then the next smallest, until no claim can rise without lowering an earlier
   one. The `priority(...)` of the endpoints orders the tiers. A zero request makes no claim. A flow
   with legs has one fraction.
4. **The final distance step.** Among the answers that keep all the earlier ranks, the solver
   selects the flow rates nearest their requests. A signed route uses its signed request, and a flow
   with no request has the target zero. With the rates fixed, it selects the other unknowns nearest
   their preferred values.

The final step minimizes the sum of the squared distances, each divided by the square of a scale:

- A flow rate uses one canonical unit of its dimension. So the units in which the model writes its
  rates do not change the answer.
- A served fraction uses the scale 1.
- Another unknown uses its declared `scale`, else the finite width of its domain, else one canonical
  unit of its dimension.
- An unknown with no preferred value prefers zero. A stored number that a solver determines prefers
  its initializer.

The distance is strictly convex, so the solver publishes one answer. The common offset of free
levels in a network is part of that answer.

### Two bottlenecks

Three consumers each request 6 W and have a capacity of 6 W. The provider enforces
`a + b <= 4 W` and `b + c <= 5 W`.

| Objective | a | b | c | Total unmet |
| --- | ---: | ---: | ---: | ---: |
| None: fair sharing | 2 W | 2 W | 3 W | 11 W |
| `minimize(sum(consumers.unmet))` first | 4 W | 0 W | 5 W | 9 W |

Fair sharing raises the three rates to 2 W. Then the first limit binds, and only `c` can rise, to
3 W. With the total shortfall first, the solver serves 9 W, and that needs `b = 0 W`. An objective
of total shortfall can leave a member with nothing. A later rank of fairness cannot undo an earlier
objective.

### Budgets

The fair-sharing step and the final distance step can be costly on a large problem that is short of
supply. Each has a budget that counts work, not seconds: linear programs, Newton steps and
iterations. When a step cannot give an answer within its budget and its tolerances, the run stops
with a diagnostic that names the step. The engine never gives another allocation in its place. The
configuration of a run holds the budgets ([engine/solver.md](../engine/solver.md)).

## A solver over collections

A solver can bind collections and name a field on each member. The model below has three places, two
routes and hourly readings, in three tables. The stock of each place is held at 0 Wh, so supply and
imports balance use and exports.

```scn
Reading:
    input hour: h = 0
    input factor = 1

Place:
    input base_need: W = 0
    input supply_limit: W = 0
    input critical: bool = false
    level = 0 in [-30, 30]
    power: Wh = 0 in [0, 0]
    need = formula(this.base_need * Reading.instances.by(hour).at(t).factor)
    flow supply: SOURCE -> this.power
        capacity = this.supply_limit
    flow use: this.power -> SINK
        request = formula(this.need)
        capacity = formula(this.need)
    unmet = formula(max(0 W, this.use.request - this.use.actual_rate))

Route:
    origin: Place
    destination: Place
    input strength: W = 1
    input closes_at_two: bool = false
    up: bool = true
    pull = formula(this.strength if this.up else 0 W)
    flow carried: this.origin.power <-> this.destination.power
    rate_follows_levels = formula(this.carried.actual_rate == this.pull * (this.origin.level - this.destination.level))
    close = event():
        when this.closes_at_two and t >= 2 h:
            this.close.start()
            reset when false
        after 0 h:
            this.up = false

sites: Place from "places.csv"
links: Route from "routes.csv"
readings: Reading from "readings.csv"

provider:
    dispatch = solver:
        inputs:
            places = Place.instances
            routes = Route.instances
        solve_for:
            places.level
            places.supply.actual_rate
            places.use.actual_rate
            routes.carried.actual_rate
        constraints:
            all(routes.rate_follows_levels)
        objective:
            minimize(sum(places.unmet))
```

`places.csv`:

```text
id,supply_limit: W,base_need: W,critical
junction,8,0,false
clinic,0,6,true
garden,0,6,false
```

`routes.csv`:

```text
id,origin,destination,closes_at_two
junction_clinic,sites.junction,sites.clinic,false
garden_junction,sites.garden,sites.junction,true
```

`readings.csv`:

```text
hour: h,factor
0,1
1,0.5
2,1
```

- `rate_follows_levels` is an affine equality in the solver, because `pull` is known at each solve.
- Each level is a plain unknown with the preferred value zero.
- At 2 h the trigger of the garden route closes it.

| Time | Clinic use | Garden use | Junction supply | Junction to clinic | Garden to junction |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 h | 4 W | 4 W | 8 W | 4 W | −4 W |
| 1 h, the needs fall to 3 W | 3 W | 3 W | 6 W | 3 W | −3 W |
| 2 h, the garden route is closed | 6 W | 0 W | 6 W | 6 W | 0 W |

At 0 h, the objective lets any split of 8 W between the two claims of 6 W serve 8 W. Fair sharing
then selects 4 W for each. The levels of the junction, the clinic and the garden are 8/3, −4/3 and
−4/3. For a clinic first, put `minimize(sum(places.where(critical).unmet))` before
`minimize(sum(places.unmet))`: the clinic then gets 6 W and the garden 2 W. A reordered file
changes no named result, because the rows keep their ids.
