# Napkin prerelease rewrite: the specification

> This file is the owner's last pasted version of the rewrite proposal, word for word. The
> implementation plan (`PLAN.md`) builds against it. The appendix at the end is not the owner's
> text: it lists the open items that the plan adds. The rulings of gate G0 are written in
> `rulings.md` first and then edited into this file. This folder is deleted before the branch
> merges; the lasting text is the rewritten `docs/`.

Napkin’s prerelease rewrite gives each model value a type, an owner and a lifetime. It replaces implicit recalculation with `formula(...)`, treats each event start as a separate occurrence, and gives transfers named flows with observable actual rates. A provider can coordinate many flows with an algebraic solver. The same solver can allocate ordinary quantities such as staff hours. A run produces one trajectory. Scenario code chooses what to report or compare.

**Agreed** identifies a decision for the rewrite. **Proposed** or **recommended** identifies a design choice still open to revision. Examples describe the rewrite unless labeled **current compiler**. The final section distinguishes observed behavior in the pinned compiler, standalone solver experiments and results the rewrite must still demonstrate. [Compiler at commit 13b0969](https://github.com/jfeiglin/napkin/tree/13b0969bdfa30a1ae2d74cc083ba066424fd3f84)

# What changes for a model author

| Area | How to write or interpret the rewrite |
| - | - |
| Values and units | `beans: g = 8` declares stock. An ordinary expression captures a value once. `formula(...)` recalculates. `readonly` bars direct assignment to the binding. Flows can change its inventory, as can a checked `move` under the proposed transfer rule. A trailing `in [lo, hi]` declares a closed range. |
| Groups and table rows | Use one keyed collection type for entities, flows and occurrences. `Route.instances` selects all routes. `where` narrows members, `by` supplies a key and `at` looks up a member. |
| Events | `grinder.refill.start(50 g)` creates an occurrence with its own arguments, locals, flows and stages. A trigger belongs to its event. Occurrences keep history. An endpoint lists its current connections. |
| Transfers | `->` moves a quantity in one direction. `<->` gives a reversible route one signed rate. A flow with several legs serves all legs at one common fraction. Stocks and endpoints impose bounds and sharing rules. |
| Coordination | The engine honors physical balance and endpoint sharing, even when it must calculate several rates together. An entity declares a solver for an additional joint constraint or objective. Every supported feasible problem with finite ranked optima has a selection rule. |
| Runs and reports | Choose `sampled` or `median` for one execution. Model declarations carry their text, ranges and evidence. Any named value can be reported, and an experiment compares runs externally. |

# Values have owners and can refer to one another

| Scope | What it owns | Example |
| - | - | - |
| Run | One effective setup, its entity identities, simulation time and history | Two runs of the same scenario have independent grinders. |
| Entity instance | Its fields, links, formulas, flows and bound events | `grinder.beans`, `grinder.refill` |
| Bound event | Its parameter signature, attached triggers and the history of starts and completions on this receiver | `grinder.refill.start(50 g)` |
| Trigger | Eligibility, reset state and captures for this receiver | A low-beans trigger can already be armed before the first refill. |
| Occurrence | This start’s parameter copies, locals, flows and scheduled stages | `grinder.refill.occurrences.at(t).status` if the model declares `status` and a refill has started |
| Flow | One transfer, a reversible route or an activity with named transfer legs | `pump.fill.actual_rate` |
| Source and sink | The outgoing or incoming connections of one quantity | `tank.water.outflow.flows` |
| Solver | Inputs in scope, quantities to determine, added constraints and optional objectives | `provider.charging` chooses two existing rates. `clinic.staffing` owns two new results. |

## How to declare, read and change a value

In a declaration area, `name = expression` introduces a value. Add `: type` to check the type and `readonly` to protect its binding from direct reassignment. `input` admits a configuration override before the run starts. Its selected value is fixed during that execution. **Agreed.** A declared flow can fill or drain a `readonly` stock. Direct assignments to that stock, including `+=` and `-=`, are errors through every reference. **Proposed for `move`.** An instantaneous transfer may also debit or credit a `readonly` stock. It checks both inventories and records the transfer. Within an action, `name = expression` assigns to an already declared, writable target. A misspelled target is an error. An ordinary numeric expression captures its value at evaluation time. `formula(...)` explicitly retains a calculation.

```text
grinder:
    beans: g = 8
    readonly low_on_beans: formula(bool) = formula(this.beans <= 10 g)
    refill = event(amount: g):
        after 0.5 h:
            this.beans += amount
```

`beans: g = 8 g` spells the initial amount explicitly. Both declarations give the grinder 8 g. After `grinder.refill.start(50 g)` and half an hour, it has 58 g and `low_on_beans` reads false. The formula kept its definition throughout. The event binding is read-only by default. Starting the event is one of its operations. A read-only reference to the grinder still designates the same grinder as its state changes.

### Primitive and composite types

Start with `bool`, named states such as `enum[OPEN, CLOSED]`, and an unbounded dimensionless number. **Recommendation.** Give Boolean expressions their own type. `1 if ready else 0` makes the numeric interpretation explicit. Enum declarations and cases use bare member names such as `OPEN`. A quoted string is text. A quantity can add a physical unit, bounds, or both. A bounded quantity may expose its declared limits. A distribution exposes parameters and `.draw()`. A formula retains a typed calculation and may support `.diff(...)`. A flow exposes its endpoints and realized rate. The model can set a throughput capacity and a request. A collection holds distinct members of a single entity, flow or occurrence type, each with a numeric key. Entities, events, triggers and occurrences also have types and lifetimes. Describing a property in the type establishes whether it can be read or written.

Infer unambiguous initializers such as `water = 20 L`. Event parameters always declare types. An annotation checks or supplies a type and by itself supplies no initial value for stored state. A numeric field has one physical dimension across every instance of its template. L/h and m³/day convert. A mass rate cannot occupy a volume-rate field. Named states, text, reference types and unit conversion rules still need a complete type specification. [Current unit-parameterized template](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/tests/model/test_runs.py#L74)

Model-level initializers follow their value dependencies. If `clinic.water` reads `supply.initial_water`, initialize the latter first regardless of file order. Mutual entity references are valid. Cycles among required starting-value calculations are errors. Quantities with known initial values may influence each other’s subsequent rates. Ordinary invocation-local initializers follow written order.

A template describes a shared schema and behavior. Instantiation gives those declarations an owner and storage in a particular run. An entity link refers to that identity. The run is the conceptual root. Exposing a `run` keyword or path in source is an open naming choice. **Proposed scope rule.** `this` always designates the owning entity in a member initializer, an event on that entity and a trigger attached to the event. Bare parameters and occurrence locals belong to that invocation. Following a link or starting the event from another entity never changes its receiver. Ownership gives each value a home. Links can be shared or cyclic. An ordinary reference lets model code read the value and assign to its writable fields. `readonly` protects a binding from direct assignment through any path. Lexical scope determines how names resolve.

### Units, comparisons and layout

A declared unit supplies the unit of a direct numeric literal, as in `beans: g = 8`. A bare endpoint of a declaration range inherits the declared quantity’s unit. Extending that convenience to distribution arguments with a known dimensional role is recommended. In `2 * this.delay`, the multiplier is dimensionless. Prefer `==` and `!=` for equality and inequality of numbers, Booleans and enum members. Use `=` for declarations or assignments according to context.

**Agreed.** v1 uses closed numeric intervals. An unparenthesized trailing `in [lo, hi]` on a declaration gives that value’s allowed range. It may continue on an indented line. A solver unknown can also declare a domain without a stored initializer. In an assertion or guard, `x in [lo, hi]` tests membership. To initialize a Boolean with that test, enclose the entire expression in parentheses.

```text
input delay: h = 3
    in [0.5, 12]
    @timing

assert total in [initial - tolerance, initial + tolerance]
```

Both endpoints are included. Endpoints and the tested value must have compatible units. Reversed bounds are an error and `[x, x]` contains exactly `x`. Evaluate the tested expression once. For example, `ok = (samples.draw() in [lo, hi])` evaluates one draw. For an exclusive upper limit in a condition, write `lo <= x and x < hi`.

Here `@timing` identifies the supporting evidence record. The current compiler also accepts bare zero in expressions such as `max(0, need - use_rate)` where the other operand determines the unit. The rewrite retains that unit inference. [Existing model](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/scenarios/iv_fluid_shortage/model.scn#L425)

The proposed notation allows wrapped clauses, escaped quotes and trailing `#` comments. A `#` inside quoted text stays literal. Formatting preserves any order that affects the model’s meaning. Unit arithmetic still has an open parsing question. Today `48 h / 2` and `48 h/2` parse differently, `-` multiplies units, `^` raises a unit to a power and `**` raises an expression to a power. [Current notation](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L129)

## Collections, keys and projections

**Agreed.** `<T>` is one collection type for entity instances (including table rows), flows and event occurrences. Each collection contains distinct members of one type. Every member has a numeric key. An entity or flow has its creation number as its natural key. An occurrence has its start time. `Route.instances`, `grinder.refill.occurrences` and `water.outflow.flows` expose collections on their owners. An author can also construct a literal or narrow an existing collection. A populated literal can infer its type. An empty literal needs an expected element type.

```text
readonly pumps: <Pump> = <this.primary, this.backup>
readonly idle_pumps: <Pump> = <>
```

`routes.limit` projects one field from each member. A projection feeds a reduction, a `solve_for` entry or a broadcast call such as `machines.repair.start()`. A projection cannot be stored as an independent list. Put the per-member calculation on the member, then reduce the field. The reductions are `sum`, `count`, `any`, `all`, `min` and `max`. `count(c)` counts members. `count(c.done)` counts true values when `done` is Boolean. A numeric projection such as `count(c.amount)` is a type error, even on an empty collection. Use `sum(c.amount)` for the total or `count(c)` for the number of members. On an empty collection, `sum` produces zero in the field’s unit, `count` produces zero, `any` is false and `all` is true. Reading a member with `.at(...)` requires a matching member. The empty cases for scalar `min` and `max` still need a ruling.

`Route.instances.where(destination == this)` selects the routes that end at the enclosing entity. `Place.instances.where(critical)` selects rows with the fixed `critical` flag. `where` preserves the keys of the surviving members. Projecting a field carries each originating member’s key with its projected value. Thus `customers.by(rank).delivery` ranks flows by the customer’s rank. Inside `where`, the field on the left belongs to the member and the expression on the right resolves in the enclosing scope. The first version filters on links, inputs and data columns fixed for each member. For members created during a run, a fixed filter can be evaluated when the member is added. For a live test on members, put a Boolean formula on the member and reduce it. **Agreed.** A run can add both event occurrences and flows. A committed invocation creates an occurrence and one flow instance for each flow it declares. Each directed connection appears in its source’s `outflow.flows` and its sink’s `inflow.flows` wherever those endpoints are modeled stocks. Both endpoints refer to the same connection. A reversible route contributes a leg for each direction. A flow with several simultaneous legs contributes each named leg to its own endpoints. On completion the occurrence remains in the event’s history and its flows leave both endpoint collections. A fixed-field filter over an endpoint collection follows these membership changes. Starting the same event again creates a distinct occurrence and distinct flows.

`by(field)` gives the same members under a new numeric key taken from that field. The members keep their identities. `c.at(x)` reads the member with the greatest key at or below `x`. `x` must have a unit compatible with the key and is converted before comparison. Of members with equal keys it selects the later-created member. `Reading.instances.by(hour).at(t).factor` therefore holds the 10:00 reading at 10:40 and switches at 11:00. `tiers.by(threshold).at(volume).price` uses the same lookup on a quantity. For file rows, setup reports equal keys within a keyed view only if the model reads that view with `.at(...)`. This diagnostic explains which row wins the creation-order tie. A `where` filter limits the check to surviving rows. Equal ranks in a view used only for `priority(...)` are valid. Simultaneous occurrence starts follow the same lookup tie rule. When the lookup argument has a known lower bound, setup also checks coverage at that bound. At execution, a lookup on an empty collection or below its first key fails if evaluated. For example, a first sample at 2 h cannot supply a reading at 1 h. Beyond the last key, the last entry still applies. For priority, lower keys are served first and members at equal rank share proportionally. An explicit key can therefore govern service independently of file order. General lists of scalar values are deferred.

**Current compiler.** Square-bracket entity lists preserve repetitions and file order. `let machines = Machine` collects existing instances and `machines.2` names a generated copy. In the pinned compiler, `count(machines.failed)` counts true fields, and the extra scalar argument to `min` or `max` participates even on a populated list. The rewrite spells the full collection `Machine.instances`. [Current collections](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L203)

## Formulas and the values a caller can read

`formula(expression)` constructs a pure calculation. `formula(bool)` in a type annotation describes a formula with a Boolean result. Reading the bound name in an ordinary expression evaluates the calculation against its current dependencies. An ordinary scalar binding captures that result. A formula’s operations can still address its definition.

```text
captured = this.water / (2 h)
readonly draining = formula(this.water / (2 h))
readonly ready: formula(bool) = formula(this.water >= this.minimum)
```

Changing the water changes `draining` and can change `ready`. `captured` keeps the rate it read at initialization. Formulas cannot draw, mutate state, start events or contain an evaluation cycle. **Recommended type rule.** A writable `formula(T)` binding can accept another compatible formula. A scalar assignment or `+=` cannot turn that binding into a scalar. A property such as a flow’s `.request` can explicitly accept either a stored rate or a live rate formula. The type system still needs a spelling for that contract and a rule for intentionally copying a formula definition.

**Agreed.** Name a reportable calculation with an ordinary binding. For a collection of utilities, the first declaration below measures water at the start. The second follows the member tallies over time.

```text
initial_unserved = sum(Utility.instances.unserved)
unserved_volume = formula(sum(Utility.instances.unserved))
```

`Utility.instances` includes every instance of `Utility`. A caller can select the calculated `unserved_volume`, a stored tally such as `reservoir.spilled`, or another named value, together with the times to retain. This replaces the computational `output` declaration. A reporting lag is valid only when the compiler can prove that the selected value never falls over the run. An accumulating tally with nonnegative additions can qualify. Current unserved volume can fall when service returns. If monotonicity cannot be proved, diagnose the lag selection and allow the ordinary unlagged read. A uniform two-to-six-hour lag averages that history from six hours ago to two hours ago and consumes no draw. A delayed observation that changes a player’s decision belongs in the model. [Current reporting declarations](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L390)

### Model text, status cases and evidence

Quoted text stays under the declaration it describes. The first text under a field supplies its label, under an entity its description, under an event or outcome its card, under an option its menu line, and under a check its message. Playback, reports and diagrams can reuse the same text. A status display evaluates its cases in written order, uses the first match, and takes both the rating and the text from that case. The final unconditional case is the fallback. The display ratings `ok`, `degraded`, `failed` and `inactive` belong to the status display. A model can declare an enum for its own work state. An event occurrence can also declare a field describing its progress.

```text
crew:
    work_state: enum[WAITING, WORKING, DONE] = WAITING
        "Crew work state"
    status ok when this.work_state == DONE
        "Repairs are complete."
    status degraded when this.work_state == WORKING
        "Crews are carrying out repairs."
    status degraded
        "Crews are waiting for access."
```

The last two cases share a rating and give different explanations. A report can select this entity’s status display. Whether a package can save a default selection in a `report:` block remains open. The model already owns the text and the decision about which case applies. [Two degraded cases in the heat-wave model](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/scenarios/heat_wave_blackout/model.scn#L408)

**Agreed.** Any named value can be reported. For a numeric value, its interval specifies whether it can be negative. For example, `net_change: L = 0 in [-20, 20]` admits gains and losses. An ordinary `@record` on a formula can document why the groups in a sum are disjoint. The modeler supplies the evidence for that interpretation.

A typed declaration can state `= none` when there is no estimate. A report shows the value as unavailable and can show the reason from its cited record. A measured zero and a missing estimate have different meanings. In the example, the model can calculate the current volume shortfall, but weekly counts of people would require tracking who remained without service.

```text
unserved_volume = formula(sum(Utility.instances.unserved))
    "Volume currently unserved"

weekly_unserved: people = none @no_cohorts
    "People continuously without service for a week"

record no_cohorts: assumption "Daily totals do not identify the same people across days."
```

## Distributions and explicit draws

Under the proposed constructor syntax, `normal(2, 3)` describes a distribution. Its read-only `.mean` and `.std` describe that distribution without consuming randomness. Each executed `.draw()` evaluates the distribution under the run’s chosen mode. Store its result to reuse it. Replacing a descriptor leaves previously stored samples intact. Repeatedly evaluated formulas and conditions may read a stored sample. A skipped branch performs no draw.

**Agreed.** A numeric input can draw its default explicitly. Each instance evaluates its default once per run. A numeric override supplies the value and skips the draw in either mode.

```text
input repair_time = uniform(1 h, 3 h).draw() in [1 h, 12 h]
```

Without the explicit interval, a direct draw from this bounded distribution admits overrides from 1 to 3 hours. The wider range admits overrides up to 12 hours and leaves the distribution unchanged. An explicit range must contain the distribution’s support. Rules for unbounded distributions, transformed draws and fixed defaults remain open, as do distribution-valued overrides, constructor signatures, other result types and correlations.

**Agreed.** The run mode is `sampled` or `median`. In a sampled run each executed `.draw()` samples the distribution, and a chance outcome is sampled from the eligible probabilities. In a median run `.draw()` returns the distribution’s median and a chance selects the most likely eligible outcome. Equal largest chances use the first declared eligible outcome. A plain reference run uses `median` and requires no seed. Both modes honor explicit player or controller choices. Replaying a sampled run uses its seed, effective setup and choices. A different numerical step size, an extra report or an unexecuted branch consumes no extra draws for the same model executions. A median run gives a deterministic example trajectory. A median of reported outcomes across many trajectories is a separate statistic. [Pinned chance behavior](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L330)

# Flows and algebraic solvers

A directed flow has a source and a sink. A reversible flow connects two endpoints with one signed rate. A flow with several legs gives each transfer the same service fraction. A stored quantity gains an `outflow` scope when it supplies a flow and an `inflow` scope when it receives one. An entity that makes a centrally coordinated decision owns an explicit `solver` value. The same construct can choose transfer rates, divide staff hours or determine other numeric quantities. The run accounts for transfers. A local allocation that has all the information it needs stays at its endpoint.

```text
tank:
    readonly water: L = 8 in [0, 20]

clinic:
    flow delivery: tank.water -> SINK
        capacity = 5 L/h
        request = 3 L/h
```

This complete local example delivers 3 L/h until the tank empties at 2 hours 40 minutes. At that instant the rate becomes zero. `clinic.delivery.capacity` is still 5 L/h and `clinic.delivery.request` is still 3 L/h. The flow can drain `tank.water` even though an assignment such as `tank.water = 10 L` is an error. The arrow gives direction. The quantity in the tank has units of volume. All three rate fields have units of volume per time.

Write `flow name: source -> sink` in an entity or event declaration area. Both endpoints are paths to stored numeric quantities or the appropriate external boundary. A flow declared inside an event can transfer while its owning occurrence is running. When it finishes, the occurrence retains the flow’s identity and its last evaluated request on each connection. An indented `property = expression` initializes a property relative to the value above it. `clinic.delivery.request = 3 L/h` in the setup scope that wires the model is the same initializer. Specify a given property once per effective definition. In an event stage, assigning to a writable property changes it for subsequent execution. The keyword `this` refers to the receiving or owning entity. Endpoint identities remain fixed for that flow’s lifetime. Two directed flows can represent independent transfers in opposite directions. Within a directed flow, `source` and `sink` are its endpoint references. A rule may capture typed scalar controls and invocation arguments from its enclosing scope, subject to the same transitive dependency checks.

**Agreed for v1.** `flow link: west.water <-> east.water` declares one signed `link.actual_rate`. Positive transfers go west to east and negative transfers go east to west. The nonnegative capacity limits the magnitude. Both endpoints must be stocks that can supply and receive the quantity. A tally can only receive. `SOURCE`, `SINK` and tallies are invalid at either end of `<->`. Use separate directed flows to model imports and exports across an external boundary.

| Endpoint collection | Member contributed by `link` | Member’s nonnegative `actual_rate` |
| - | - | - |
| `west.water.outflow.flows` and `east.water.inflow.flows` | `link.forward` | `max(link.actual_rate, 0 L/h)` |
| `east.water.outflow.flows` and `west.water.inflow.flows` | `link.backward` | `max(-link.actual_rate, 0 L/h)` |

Each collection contains the incident leg. When `link.actual_rate` is −3 L/h, the forward leg reads 0 L/h and the backward leg reads 3 L/h. At zero both read zero. Both legs keep their identity and endpoint membership for the route’s lifetime. The engine debits and credits the transfer once. **Proposed priority syntax.** Name the directional leg explicitly, for example `priority(link.forward, backup)` on `west.water.outflow`. A bare `link` or a leg outside that endpoint’s direction is an error. In `solve_for`, name `link.actual_rate` for the route’s one decision variable. Its directional rates are derived. An explicit solver expression using a directional rate must satisfy the same supported-constraint rules as any other expression.

## What each scope can see

An author writes a relationship at the narrowest scope with the necessary information. The following paths name built-in properties. A scalar assignment captures a value. `formula(...)` explicitly installs a live calculation.

| Scope | Read-only properties | Configurable properties |
| - | - | - |
| Directed flow `X` | `.source`, `.sink`, `.actual_rate` | `.capacity`, `.request` for this connection |
| Reversible route `link` | Signed `.actual_rate`, `.forward` and `.backward` | `.capacity` and signed `.request` on the route |
| Flow with several legs `restore` | `.served_fraction` and the `.actual_rate` on each named leg | Each leg’s `.request` gives its own full-service rate |
| Source `Y.outflow` | `.flows`, `.actual_rate` summed over outgoing flows | `.capacity`, `.request` for the outgoing total, and `.allocation` |
| Sink `Z.inflow` | `.flows`, `.actual_rate` summed over incoming flows | `.capacity`, `.request` for the incoming total, and `.allocation` |
| Solver `provider.charging` | Scoped input references and published results | `inputs`, `solve_for`, `constraints`, and optional `objective` |

A directed connection can read its own controls and its two endpoint identities, quantities, units and bounds. A source sees the incident outgoing flows. A sink sees the incident incoming flows. An endpoint can inspect the far end of one of those flows, for example `main.sink` when `main` is a member of its outgoing set. Its read-only `.flows` collection contains current connections, including closed or starved ones, and uses connection creation numbers as natural keys. Each directional or named leg has its own stable number. `sum(water.outflow.flows.actual_rate)` is valid and equals `water.outflow.actual_rate`. Allocation follows the endpoint’s sharing rule. Two pipes with the same endpoints have distinct identities.

### Flows created during a run

An entity-owned connection belongs to its modeled endpoints’ `.flows` collections for the whole run. An occurrence-owned connection joins those collections at its start and leaves them atomically when its occurrence finishes. A flow whose rate falls to zero stays connected for its owner’s lifetime. On completion, the event keeps the occurrence as a record. A directed flow or reversible route keeps its key and endpoints, reads `actual_rate` as zero and exposes its last evaluated `request` as read-only. For a flow with several legs, apply those reads to each leg and set the activity’s `served_fraction` to zero. All memberships of a retiring flow are removed together. A later occurrence gets fresh identities.

Suppose each `deliver` occurrence owns one flow called `pipe`. It requests 2 L/h from the tank and receives its full request while running. The table assumes no other outgoing flows. `count(deliver.occurrences)` counts deliveries started. `count(tank.water.outflow.flows)` counts connections currently present, including any waiting for water.

| Moment | `count(deliver.occurrences)` | `count(tank.water.outflow.flows)` | `sum(tank.water.outflow.flows.request)` | `tank.water.outflow.actual_rate` |
| - | -: | -: | -: | -: |
| Before the first delivery | 0 | 0 | 0 L/h | 0 L/h |
| Delivery A is running | 1 | 1 | 2 L/h | 2 L/h |
| A has finished | 1 | 0 | 0 L/h | 0 L/h |
| Delivery B is running | 2 | 1 | 2 L/h | 2 L/h |

After A finishes and before B starts, `deliver.occurrences.at(t).pipe.request` gives A’s final 2 L/h. The value is frozen when A finishes, even if its request was a formula. Once B starts, the same expression selects B, the newest start. The sum at the tank includes only the requests on current connections. A report asking which flows ever used this tank across several owners would need to collect their history. The endpoint collection supplies the current view.

The enclosing scope wires flows to endpoints and imports values into a solver. Model code can follow ordinary references. The engine may evaluate several rates together to honor endpoint capacities, stock bounds, conservation and sharing. When a provider supplies a joint objective or an additional cross-site constraint, the provider owns the explicit solver that declares it.

**Capacity, request and bounds.** `capacity` is a hard nonnegative rate ceiling. Omission imposes no extra throughput limit. For a directed flow or an endpoint, `request` is a soft nonnegative desired rate and defaults to zero. On a reversible route, the sign of its request expresses the desired direction. The forward leg exposes the positive part of that request and the backward leg exposes the positive part of its negation. The two leg views introduce no extra claims. For a flow with simultaneous legs, each leg’s request sets its pace at full service as described under “Shared resources and competing invocations”. A request on a scope applies to its measured total. The same transferred litre can simultaneously satisfy a flow request, its source’s outflow request and its sink’s inflow request. Each preference measures the realized amount on its own scope. An edge may carry more than its own request to meet another request. Set `capacity = 0 L/h` to close it. Setting `request = 0 L/h` withdraws that particular claim. `capacity = none` clears an explicit ceiling. Use `none` as the ordinary absent value for this optional property. Explicit capacities and requests must be finite and unit-compatible.

**One pipe and three requests.** Suppose the source, pipe and sink request 10, 8 and 6 L/h respectively, with no other connections, ample stock and room, and no other objectives. With no binding cap the pipe carries 10 L/h, the least transfer serving all three claims. The flow and sink may receive more than their own requests. A hard cap of 7 L/h at any of the three scopes makes the actual rate 7 L/h. The respective shortfalls are 3, 1 and 0 L/h. The source loses and the sink gains the same 7 L/h. With several connections, the source and sink requests apply to their total rates and can be served by different combinations of incident flows.

A quantity’s own interval is an inventory bound. At its lower bound, total withdrawals can use simultaneous inflow. At its upper bound, arrivals can use room freed by simultaneous withdrawals. At `[0, 0]` both conditions apply continuously, so total inflow equals total outflow. A junction can carry 8 W through a stock held at 0 Wh. The same physical transfer debits and credits its endpoints exactly once. A stored numeric field initialized from a scalar, such as `remaining: L = amount`, can hold stock. A bare expression result has no storage identity to debit or credit. A configurable input stays fixed for the run. A stored `readonly` quantity can be either endpoint. Declared flows and, under the proposed `move` rule, instantaneous transfers update its inventory subject to its bounds. A read-only entity reference can also identify a stock on its target. Declare operational inventory bounds explicitly.

`SOURCE` and `SINK` are predefined, unit-polymorphic model boundaries. Use `SOURCE` on the left and `SINK` on the right. External material is limited only by the declared controls and connected resources. Neither boundary makes a request. The modeled endpoint determines the unit. A direct `SOURCE -> SINK` flow needs a unit-bearing rate initializer to establish its type. These tokens are shared spellings for external access, with separate accounting by flow and resource dimension. They do not connect unrelated water and electrical systems.

## Local allocation

```text
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

The source can perform this allocation using its own 10 L/h limit and its two outgoing claims. `priority(a, b)` gives `a` first access when both are eligible and gives `b` the available remainder. The result is 8 and 2 L/h. The default `proportional()` instead gives 4 and 6 L/h. Proportional sharing equalizes the fraction of each positive claim that is served, redistributing unused shares when a cap binds. Both examples empty the reservoir in two hours. Neither needs a coordinating solver.

`priority(...)` and `proportional()` are ordinary allocation values. Use `proportional()` to restore the default. `priority(a, b)` orders distinct named incident connections from first to last. A reversible route contributes `link.forward` or `link.backward`. An activity with several legs contributes the named leg incident at that endpoint. To rank table rows, `priority(customers.by(rank).delivery)` uses their projected incident flows. The projection preserves each customer’s rank on its delivery flow. Lower ranks are served first. Customers with equal rank share proportionally. Unlisted eligible flows share the remainder proportionally to known claims. A router can list one high-priority local flow and leave the ordinary flows unlisted, including connections created by later invocations. With one aggregate request and multiple otherwise equivalent routes that carry no individual claims, the local default splits equally among eligible routes, redistributing at caps. Where the model specifies a rank, that rank governs service. An allocation belongs to the endpoint and ranks useful requested work. A preference or a free route alone generates no traffic.

A common sink makes a request once. Suppose `main` and `backup` feed `clinic.water`. Set `clinic.water.inflow.request = 6 L/h`, `clinic.water.inflow.allocation = priority(main, backup)` and `main.capacity = 4 L/h`. Given sufficient supply and room, the two rates are 4 and 2 L/h. Stating a 6 L/h request on each pipe would express two separate claims. A desired inventory can be modeled using `inflow.request = formula(max(0 L, 15 L - this.water) / (2 h))` on the tank’s water. The two-hour recovery time makes this a rate with an explicit response speed.

**When a solver is required.** Declaring the flows, stores and endpoint policies is sufficient for ordinary transfers. The engine enforces those rules even when an empty store, a full store or connected capacities make several rates interdependent. The author declares an entity-owned solver for an additional joint decision, such as a provider’s combined limit across sites, a route law linking two unknown levels, or a clinic-first objective. The compiler can diagnose missing participants in that declared decision. Reaching an inventory bound during an otherwise valid run does not itself require a new solver declaration.

## An entity owns its solver

A `solver` has four sections. `inputs` brings existing values or references into scope. These bindings track their sources, including collections such as `routes = Route.instances`. `solve_for` names exactly which eligible existing fields the solver determines, or declares new typed unknowns on the solver. A projected `solve_for` entry such as `routes.carried.actual_rate` selects the field on every member. `constraints` adds simultaneous relations to the domains already declared by the inputs. `objective` ranks feasible answers. It can be omitted. The inherited sharing and final selection rules below resolve remaining choices. The distinction between a known parameter, a decision variable, a domain and an objective also appears in established algebraic modeling languages. [MiniZinc handbook](https://docs.minizinc.dev/en/stable/modelling.html) · [CVXPY introduction](https://www.cvxpy.org/tutorial/intro/index.html)

Importing a charger brings its present capacity, request, units, storage bounds and endpoint restrictions into the problem. An input with a current value of 8 W and range `[0 W, 10 W]` contributes 8 W. Its range does not authorize a solver to choose 10 W. A `solve_for` entry grants responsibility for that specific result only. Resolve aliases to the underlying field and reject competing writers. A solver-local unknown is read-only to callers. A formula of known inputs supplies a current coefficient. A formula that reads an unknown contributes its expression evaluated at the candidate solution. In a `constraints` section, `==`, `<=` and `>=` are relations enforced during selection. An `assert` checks a result.

### Using collections in a solver

The following network has three places, two reversible routes and hourly readings. Each place’s stock is fixed at 0 Wh, so supply and imports must balance use and exports. Only the junction can supply power. On an available route, the signed rate equals its strength multiplied by the difference between its origin and destination levels. The levels are dimensionless unknowns with declared reference value zero. Setting a route’s known coefficient to zero forces its rate to zero, including when that route remains in the collection.

```text
Reading:
    input hour: h = 0
    input factor = 1

Place:
    input base_need: W = 0
    input supply_limit: W = 0
    input critical: bool = false
    level = 0 in [-30, 30]
    power: Wh = 0 in [0, 0]
    flow supply: SOURCE -> this.power
        capacity = this.supply_limit
    flow use: this.power -> SINK
        request = formula(this.base_need * Reading.instances.by(hour).at(t).factor)
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

The proposed constraint language accepts affine `==`, `<=` and `>=` relations, conjunction, `all(...)` and bounds on sums. Diagnose a strict inequality, disjunction, `any(...)`, `not`, `!=` or a lookup with a solver unknown as its key when used in this constraint language. A Boolean formula can still use these operations in ordinary model logic. For a reversible route, the signed parent rate is affine. A directional leg’s `max(...)` may make a proposed constraint nonaffine. The comparison inside `rate_follows_levels` becomes an affine equality in the solver because `pull` is known for the current solve. How an ordinary read of the same equality should handle rounding at the published solution remains open.

### Worked network data and expected rates

The following are the complete input rows. In this proposal, a table with an `id` header gives each row a stable name qualified by the table name. For example, `sites.clinic` identifies the same place wherever its row appears. Each route has its own ID and two links into the places table. The readings table uses its numeric `hour` column for `.at(t)`. It needs no named links.

**places.csv**

```csv
id,supply_limit: W,base_need: W,critical
junction,8,0,false
clinic,0,6,true
garden,0,6,false
```

**routes.csv**

```csv
id,origin,destination,closes_at_two
junction_clinic,sites.junction,sites.clinic,false
garden_junction,sites.garden,sites.junction,true
```

**readings.csv**

```csv
hour: h,factor
0,1
1,0.5
2,1
```

The factor changes only at the three reading times. At 2 h the garden route’s trigger starts its `close` event. Read the last row of results after the closure settles. In this one-bottleneck network, minimizing total unmet demand permits any split of the available 8 W between the two 6 W claims that serves all 8 W. The inherited fair-sharing rank then selects 4 W for each. For the clinic-first variation, put `minimize(sum(places.where(critical).unmet))` before `minimize(sum(places.unmet))`. The garden route points toward the junction, so delivery to the garden has a negative signed rate.

| Case | Clinic use | Garden use | Junction supply | Junction → clinic | Garden → junction |
| - | -: | -: | -: | -: | -: |
| 0 h, equally ranked 6 W claims | 4 W | 4 W | 8 W | 4 W | −4 W |
| 0 h, clinic-first variation | 6 W | 2 W | 8 W | 6 W | −2 W |
| 1 h, both routes open, demands fall to 3 W | 3 W | 3 W | 6 W | 3 W | −3 W |
| 2 h, demands back at 6 W, garden route down | 6 W | 0 W | 6 W | 6 W | 0 W |

At 0 h all three levels could shift by the same constant while leaving route flows unchanged. With equal scales and declared level targets of zero, the selected levels `(junction, clinic, garden)` are `(8/3, −4/3, −4/3)`. In the outage row they are `(3, −3, 0)`, including zero for the isolated garden. As an unequal-claim check, change the requests to 2 W and 6 W and the supply limit to 4 W. Proportional service gives 1 W and 3 W. Reorder either CSV, or both, without editing a link cell. `links.junction_clinic.carried` and `links.garden_junction.carried` must keep their original endpoints and signed rates in every row of the results. With inputs expressed in kW the two baseline deliveries are each 0.004 kW.

The service and route balances in the table were independently checked with linear programs, and the level references with a least-squares calculation. These expected results apply both to named instances and to table rows. The pinned table engine cannot run this example. It rejects two links from a route row into the same place table, and a route-owned flow between stocks on those place rows. The rewrite requires both relationships to work with stable row identities. [Pinned table restrictions](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/engine.md#L1289)

### Acceptance case with two bottlenecks

The provider binds its three consumers as `consumers`. Each requests 6 W. Let `a`, `b` and `c` be their delivered rates, each between 0 and 6 W. The provider enforces `a + b <= 4 W` and `b + c <= 5 W`. Each consumer defines `unmet = formula(max(0 W, this.use.request - this.use.actual_rate))`.

| Solver objective | a | b | c | Total unmet |
| - | -: | -: | -: | -: |
| Omit `objective` and use equal-priority fair sharing | 2 W | 2 W | 3 W | 11 W |
| Put `minimize(sum(consumers.unmet))` first | 4 W | 0 W | 5 W | 9 W |

Fair sharing raises all three rates to 2 W. The first limit then binds and only `c` can rise, to 3 W. With the total-shortfall objective first, adding the two limits gives `a + b + c <= 9 W - b`. Serving the maximum 9 W therefore requires `b = 0 W`. **An explicit total-shortfall objective can leave a member entirely unserved.** Choose that objective when reducing the aggregate shortfall takes precedence over coverage. A later fairness rank can choose only among solutions that retain the earlier optimum.

### Allocating staff hours

```text
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

With 100 available hours, `clinic.staffing.care` is 70 h and `clinic.staffing.outreach` is 30 h. If available staffing falls to 80 h, the live minimum becomes 24 h and care receives 56 h. These results describe an allocation. Reading them spends no staff time.

### Water and electricity in one coordinated decision

The pump and battery declare ordinary flows. Removing the power coupling would leave a water pump governed by its local capacity and downstream requests. The provider introduces the physical relationship that makes the water and electrical rates one decision. The example starts with empty stocks to expose the pass-through behavior at both boundaries.

```text
tank:
    water: L = 0 in [0, 20]

battery:
    energy: Wh = 0 in [0, 4]
    flow charge: SOURCE -> this.energy
        capacity = 1 W

pump:
    flow fill: SOURCE -> tank.water
        capacity = 4 L/h
    flow power: battery.energy -> SINK

clinic:
    flow delivery: tank.water -> SINK
        request = 6 L/h

town:
    flow delivery: tank.water -> SINK
        request = 6 L/h

provider:
    distribution = solver:
        inputs:
            charge = battery.charge
            motor = pump.power
            fill = pump.fill
            clinic_use = clinic.delivery
            town_use = town.delivery
        solve_for:
            charge.actual_rate
            motor.actual_rate
            fill.actual_rate
            clinic_use.actual_rate
            town_use.actual_rate
        constraints:
            motor.actual_rate == fill.actual_rate * (0.5 Wh/L)
        objective:
            minimize(max(0 L/h, clinic_use.request - clinic_use.actual_rate))
            minimize(max(0 L/h, town_use.request - town_use.actual_rate))
            minimize(fill.actual_rate)
            minimize(charge.actual_rate)
```

The charger can supply 1 W. The pump needs 0.5 Wh per litre, so its actual fill rate reaches 2 L/h. The empty tank passes those 2 L/h to the clinic under the provider’s clinic-first objective. The town receives zero. This result uses the empty tank as a binding constraint. With 10 L already in storage, the written objectives can satisfy both 6 L/h requests using inventory and leave higher instantaneous delivery rates equally optimal. Once higher-ranked objectives have been met, the final flow targets select exactly 6 L/h per destination with zero fill and charge at that instant. In the original empty-tank case, withdrawing both requests leaves every transfer idle. `pump.power.actual_rate` and `pump.fill.actual_rate` remain separately observable in W and L/h.

### A provider limit across separate connections

Two chargers at different sites each have their own connection and buffer. A provider contract limits their combined draw. Neither site has the information needed to enforce that contract on its own. The provider imports the two electrical flows by name and states the restriction once.

```text
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

The ordered objectives first minimize East’s unmet request, then West’s, and finally any surplus draw. With room in both batteries, that gives 6 W to East and 2 W to West. If East asks for 2 W and West for 6 W, they receive 2 W and 6 W. Once East fills with no discharge, its actual rate is zero even if its capacity and request both remain 6 W. West can draw 6 W. A request such as `formula(min(6 W, (10 Wh - this.energy) / (1 h)))` would deliberately taper as the battery fills. The assumed one-hour recovery time converts headroom in Wh to a rate in W.

## Solver and execution contract

A solver coordinates only its declared decision. One writer determines each result. A new staffing unknown lives on the solver. An existing flow rate keeps its path on the flow. Publish the results of one solve together. **Agreed.** At a discrete timestamp, one settlement round takes the stages already due for that round and commits them in deterministic order. Once their writes, occurrence starts and flow additions or removals are registered, evaluate each affected solver once, in dependency order, and publish its results together. Then evaluate dependent trigger conditions. New consequences due at the same timestamp start a further round. Crossing an inventory bound can also require fresh rates between scheduled stages. Continuous integration can evaluate a solver at trial states. Those evaluations are separate from the once-per-round rule. Ordinary expressions within a stage see earlier direct writes. A computed result whose dependencies were changed in that same stage can be read after the stage commits and the solver settles. A dirty read, including one through a formula, gets a diagnostic. If the solve is infeasible, the run reports the failure before a dependent trigger or report can see a partial result.

**Selection order.** First enforce domains, capacities, stock balance and every declared hard constraint. Optimize explicit objective lines in written order, preserving each attained optimum. Next apply inherited service and endpoint preferences on the remaining feasible choices. A positive request measures its fulfilled fraction up to 100%. In the same priority tier, proportional sharing maximizes the smallest fulfilled fraction, then the next smallest, until no remaining claim can improve without worsening an earlier one. Assign local priority classes in their declared order. Across endpoints, equal-priority claims share that tier. A preferred route has first access to useful requested work, up to the outstanding claim it serves. A preference alone creates no circulation. Each request uses its scope’s own realized rate. A zero request creates no claim. A simultaneous multi-leg activity has one fulfilled fraction at a given tier, even though several resources can constrain it. Endpoint policies can rank the individual incident legs. When feasible, requests need no excess transfer to satisfy them. Equally ranked and otherwise equivalent routes share an aggregate claim equally, subject to their caps.

**Final targets for flows and other unknowns.** Among the answers that preserve all preceding ranks, select the flow rates nearest their requests. A signed route uses its signed request and a flow with no request has target zero. For a simultaneous multi-leg activity, the single independent flow coordinate is its unitless `served_fraction`. Its target is one if at least one leg requests service and zero when every leg requests zero. With the physical rates fixed, choose the remaining nonflow unknowns nearest their declared reference values. For a place declared as `level = 0 in [-30, 30]`, zero is the reference in every solve. Feasible levels can differ from that value when the route equations require it. A target is a preference inside the feasible set.

**Proposed numerical convention.** At each final distance step, minimize the sum of squared deviations divided by the square of a positive, unit-compatible reference scale for each independent coordinate. Equivalent flow rates of the same dimension share a physical reference scale. A `served_fraction` uses scale one. For nonflow unknowns, use a declared scale if available, a positive finite declared width otherwise, and a fixed canonical unit of the dimension as fallback. Exclude fixed coordinates, aliases, derived legs and internal solver variables. A solver-local unknown without a declared target uses zero in its unit as a preference, including when its feasible interval excludes zero. Writing an explicit initializer gives that unknown its preferred value. For positive scales the distance is strictly convex over those coordinates. On a nonempty closed convex optimal set this selects a unique published answer, including a common offset of otherwise free network levels. A numerical tolerance may approximate the answer. Changing display units must preserve it.

The proposed language accepts continuous unknowns and affine hard constraints and written objectives, including positive-part shortfall objectives that can be expressed with linear inequalities. The final distance step is convex quadratic and must preserve every hard relation and attained rank. The existing distance prototype accepts equality constraints and scalar intervals. Its behavior with general affine inequalities remains unverified. Diagnose unsupported nonlinear or discrete models, infeasible hard constraints, unbounded written objectives and numerical failure. Multiple feasible optima at an earlier rank proceed to the next rank.

**Scenario check.** The same flow rules apply to handwritten and table-backed models. The Jamestown water model gives local customers first access and apportions the remaining supply among buyers. The observable consequence is the shortage for each town. Two allocations can have the same regional total and give different towns the water. [Jamestown allocation assumptions](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/scenarios/water_controls_wipe/water.scn#L1218) · [Earlier network scoping study](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/scoping/networks-and-found-values.md)

# Events, triggers and occurrences

An event is a typed value declared on a receiver. `refill = event(amount: g):` gives it the binding name `refill` and a signature requiring an amount measured in mass. `readonly refill = event(amount: g):` is also valid. The event is read-only by default during the run. Reading `grinder.refill` selects that bound event. `grinder.refill.start(50 g)` starts one occurrence. The receiver stays `grinder` when another entity initiates the start. A distribution likewise has an explicit operation, `.draw()`. [Current receiver resolution](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/language/resolve.py#L2057)

```text
tank:
    delivered: L = 0
    record_delivery = event(amount: L):
        after 0 h:
            this.delivered += amount
```

`tank.record_delivery.start(20 L)` starts a fresh invocation even while an earlier one is active. Two invocations share the same receiver’s `delivered` tally and have separate parameters, locals, flows and stages. This event has no model-defined `status`. Its starts and normal completions can still be counted.

Check declared parameter types, units and entry bounds. Numeric, Boolean and text parameters are local value copies. Reassigning one changes only that invocation’s copy. Retain the original argument values for provenance. If object parameters are admitted, they retain the identity of the referenced object. Events perform actions and may schedule later work. Parameterized pure calculations would be a separate feature. A setup-time event replacement, if introduced, must preserve argument names, types, bounds accepted at the call site and the fields readers can access on its occurrences. The same signature alone cannot guarantee the same effects. The proposal keeps shared event bodies on the template.

### Choosing actions inside a stage

Here `action` has type `enum[REPAIR, RESUME]`. The expected type resolves the bare member names in its cases. Evaluate a typed selector once, run its matching case, and continue after the branch. An optional `else` handles other valid values. With no matching case or fallback, continue directly. Only the selected body executes. An invalid value from a producer is an error. The `switch` spelling below is illustrative.

```text
after 0 h:
    switch this.action:
        REPAIR:
            this.repair.start()
        RESUME:
            this.resume.start()
    this.inspections += 1
```

A Boolean expression, an explicit draw, a reported observation or an actor’s choice can supply the selector. The producer defines how the value is obtained. A player can choose an available action with forecast probability zero. A computed condition is fixed by the model. The case body contains immediate actions. Save a selected delay or flag in a local when the decision affects a later stage. Decision and reporting APIs and optional Boolean shorthand remain open. [Reviewed outcome rules](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L330)

### Calling an event on a collection

```text
after 2 h:
    this.machines.repair.start(this.repair_times.draw())
```

When this statement executes, capture its receiver identities and evaluate the arguments once at the caller, left to right in written order. Each member’s fresh invocation receives the same captured values. In this example all machines get the same duration. To model separate durations, define a zero-parameter repair event that draws inside each machine’s invocation, then use `this.machines.repair.start()`. Capturing the recipients leaves their state live. A broadcast over entities uses a collection of one entity type.

An empty collection still evaluates the caller’s arguments and starts zero invocations. A skipped branch or stage guard skips the call and its arguments altogether. An error in one argument fails the run before later arguments execute. Capture all arguments before a receiving invocation initializes. An issued call keeps the receiver identities it captured. The order in which members’ invocations run at the same time remains open.

### State owned by an invocation

Declare persistent locals and flows at the start of the event, before its timing steps. A bare parameter or local name belongs to this invocation. Use `this.water` for the receiving entity’s water and `this.customer.water` to follow its customer link. Built-ins are available. The setup scope resolves top-level entity names for wiring. Runtime access through the receiver, an admitted argument or a declared link is explicit. A resolvable reference can be used to read a field or assign to a writable one, including across entity boundaries.

Ordinary local initializers execute once in written order, so `doubled = amount * 2` requires an already initialized `amount`. Model-level starting values follow dependency order. Creating a `formula(...)` retains a calculation for later reads. Forward references in retained local formulas and the precise point at which declared flows may refer to later locals remain open.

A declared flow is present from entry and can transfer as soon as its rate and endpoints permit. Set its capacity to zero if transfer must wait. Keep conditional actions and draws in the stage that selects them. Locals and their flows survive waits. When the occurrence finishes, its flows cease transferring. A temporarily starved flow can resume while the occurrence is still running. An entity-owned flow that an event enables can continue after that event finishes. Reject a live formula installed in a longer-lived entity if reading it would require a retired local. Storing the calculated scalar is safe. The need for short-lived calculation names inside a stage remains open.

## Time, waiting and completion

An invocation advances through top-level timing steps in written order. Each `after D:` captures a finite, nonnegative duration when the step is reached and executes its stage that duration later. Within a stage, statements and branches execute in order and see earlier writes. Commit the stage atomically relative to other invocations. Each `.start(...)` captures its arguments when its statement runs and queues a child occurrence. A successful commit publishes the stage’s writes and registers its queued occurrences with their initial fields. The parent captures ordinary next-delay inputs at its commit. If that delay depends on a solver result changed in the round, finish evaluating it using the newly settled result before any newly queued child action runs. For example, if available staff hours fall from 100 h to 80 h, a delay of `this.staffing.care` uses 56 h. Independent stages already due can contribute to that round’s solve. If the stage fails, its writes and queued starts are discarded. The reviewed compiler instead evaluates assignments from the pre-outcome state. [Reviewed execution order](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L341)

```text
inspect = event(delay: h):
    after delay:
        delay = 2 h

    after delay when this.safe:
        this.inspect_equipment.start()

    until this.clearance_received

    after 0 h:
        this.record_clearance.start()
```

A call with `3 h` reaches the first stage at hour three after the call and the second at hour five. Its entrance guard reads `this.safe` once when the second stage comes due. If false, skip its body and proceed to the gate. A temporary loss of safety before the due time does not affect that check. Current event-header `while` cancels a pending firing when its condition fails during the wait. General interruption, cancellation, joining and concurrency limits remain open. [Current delayed firing](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L309)

`until C` is a standalone gate. If C already holds, continue immediately. Otherwise the invocation keeps its locals and flows until the live condition holds. A subsequent delay is captured when the gate releases. `after 0 h:` is a separate stage at the same simulation time and can interleave with other due work. Put invocation stage actions inside `after` blocks and keep timing steps outside branches. An attached trigger has its own firing body. A possible absolute `at T:` remains open. Execution errors fail the run with the expression, invocation and simulation time.

**Recommended retirement rule.** Each occurrence-owned physical store must have zero residual inventory at normal completion, within the conservation tolerance in that store’s unit. The author can wait for the inventory to drain, move the remainder to a named persistent stock, or explicitly dispose of it through a declared flow to `SINK`. For example, a final stage can use `move batch from batch to this.supply` to return the remaining contents of `batch` to a stock with room. If 20 L enters a batch and only 12 L is delivered, its remaining 8 L must stay in an active batch or have a recorded destination. Attempting to finish with those 8 L unaccounted for fails the run and reports the stock, amount, unit, occurrence and time. An explicit sink transfer is recorded as external outflow. Numerical roundoff is recorded within tolerance. Scalar counters and quotas have no material to retire. A successful body end records `.done`, including when a guard skipped an action. Model a successful repair separately with `this.repair_succeeded.start()` on its success path.

Treat the horizon as an inclusive observation cutoff. Settle work due at the horizon under the same timestamp rules, then report the committed state, including inventory held by unfinished invocations. Stopping observation creates no completion or disposal. For the 20 L delivery in the worked example, an hour-one horizon shows 7.5 L delivered, 12.5 L in transit, one start and zero completions. At hour two, the transfer and its final gate can settle before the report, giving 20 L delivered and one normal completion. An unanswered controlled decision due at the horizon can still pause the run.

### Monitoring a threshold

| Where the condition appears | When the engine reads it | Water-level example |
| - | - | - |
| `after D when C:` | Once when the stage comes due. All ordinary comparisons apply. | `after 2 h when this.water < 10 L:` runs only if the water is below 10 L then. |
| `when C`, `until C` or `reset when C` over a discrete value | At eligible committed changes, including the initial check. | A stored measurement updated hourly may be compared using `<`. |
| The same bindings over a continuously changing quantity | At the first contact with a supported inclusive boundary, including a touch, a committed jump into the region, or a value already in the region. | `when this.water <= 10 L:` fires when a draining tank reaches 10 L. |

**Agreed.** At 1 L/h, a tank starting at 11 L reaches 10 L in one hour. There is no earliest instant strictly below 10 L during a smooth descent. Diagnose strict continuous thresholds and predicates whose first contact the engine cannot locate. An author can use an inclusive threshold or explicitly schedule inspections. Ordinary interval tests include both endpoints. Numerical contact tolerances and the continuous predicates that can be certified belong to the engine contract. [Current crossing guarantees](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L356)

### A trigger belongs to its event

A trigger is a composite value attached to a bound event. It exists once per receiver and run, including before that event has ever started. The event’s type and declaration are shared across instances. Each grinder’s refill trigger has its own eligibility and reset state. Its condition observes the receiver. A firing can capture values and explicitly start the bound event with checked arguments. There is one start in the example below. The `when` clause is an illustrative layout for attachment and does not run once per occurrence. The declaration below is a separate version of the opening example. If its automatic trigger and a manual 50 g start both fire on a grinder starting at 8 g, two independent refills can bring it to 108 g.

```text
refill = event(amount: g):
    status: enum[WEIGHING, ADDED] = WEIGHING

    when this.low_on_beans:
        this.refill.start(50 g)
        reset when this.beans >= 30 g

    after 0.5 h:
        this.beans += amount
        status = ADDED
```

Here the trigger observes `this.low_on_beans` on the grinder. A visit to 10 g or below starts a refill and disarms the trigger. Reaching 30 g or above rearms it. A separate `grinder.refill.start(20 g)` can overlap the automatic refill. That explicit start does not itself consume or reset the trigger. Inside an occurrence, `amount` and `status` belong to that start alone. Inside the trigger neither name has an occurrence to refer to. The trigger may use its own firing captures and the receiver’s fields. Without an explicit reset, the condition must become false before the next visit. `reset when false` permits one firing per run.

```text
inspect = event():
    when t >= 3 h:
        this.inspect.start()
        reset after 3 h

    after 0 h:
        this.inspections += 1
```

This clock fires at hours 3, 6 and 9 while its firing condition stays true. A three-hour cooldown on a conditional alarm behaves differently. If the alarm becomes eligible at hour three but actually fires at hour four, its next eligibility is hour seven. The duration is captured at firing. Use a mutable setting if the cooldown should change during a run.

A binding may capture a prefix of local values before calling events. For example, `shift = this.shift` with `reset when this.shift != shift` enables another firing after the shift changes. An observed A → B → A can rearm the binding. Temporary values written inside one atomic stage are invisible to the binding. For a combined time and recovery condition, capture `ready_at = t + 3 h` and use `reset when t >= ready_at and this.water >= 12 L`. Only one reset directive is allowed, at the end. [Current window rules](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L306)

### History and optional domain status

An event owns its `.occurrences` collection. Each occurrence has the built-in fields `started`, `done` and `active`. `started` records its start time, `active` describes whether it is running, and `done` records normal completion, even if a guard skipped an action. The model can also declare its own `status`, such as `WEIGHING` or `ADDED`. Overlapping invocations keep independent values and may finish in a different order from their starts. Reading `.status` requires the occurrence type to declare it.

| Question | Expression |
| - | - |
| How much is in the grinder now? | `grinder.beans` |
| How many refills have started? | `count(grinder.refill.occurrences)` |
| How many refills have finished normally? | `count(grinder.refill.occurrences.done)` counts the true completion flags. |
| Is any refill running? | `any(grinder.refill.occurrences.active)` |
| What status does the newest refill report? | `grinder.refill.occurrences.at(t).status` after at least one start |
| How long since the latest start? | `since(grinder.refill)` after at least one start |
| Did a refill succeed? | Read the occurrence’s declared field or count the occurrences of an event started on success. |

For occurrences, v1 supports `.at(t)` to read the newest start. Two simultaneous starts are distinct members and both count. A lookup at `t` returns the later-created one. An older occurrence can still be active after the newest one finishes. Guard a lookup before the first start with `count(grinder.refill.occurrences) > 0`. Reading an empty collection with `.at(t)` fails the run. Reads at earlier times and positional indexing are deferred. Counts and activity reductions cover every occurrence, including one whose start predates the newest occurrence.

A repair illustrates why a successful outcome and normal completion both matter. The repair attempt below finishes after two hours in either case. Only a successful test records restoration.

```text
repair = event():
    after 2 h when this.passes_test:
        this.operational = true
        this.service_restored.start()
```

Here `service_restored` is an ordinary event declared on the equipment. The call dispatches after the stage commits. An unsuccessful attempt can complete and leave the restoration count unchanged. The IV-fluid model has the same dependency. Its follow-up clock starts only if a particular change actually occurred. [Scenario example](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/scenarios/iv_fluid_shortage/model.scn#L105)

`since(e)` is an ordinary duration after the first occurrence. Evaluating it sooner fails that run. For a condition that should initially be false, write `count(this.service_restored.occurrences) > 0 and since(this.service_restored) >= 3 h`. Boolean operators short-circuit left to right and a conditional expression evaluates only its selected side. Counts start at zero. The `started` field records the entry time of an occurrence. The most recent start and most recent completion of an event can belong to different invocations. [Current history lowering](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/lower/expressions.py#L115)

## Shared resources and competing invocations

Two invocation-local flows drawing from `this.supply` make independent requests. A shared limit belongs on `this.supply.outflow.capacity`. A receiving limit belongs on the destination’s `inflow.capacity`. Each constraint applies once to the total for its direction.

To keep water available to competing deliveries, leave it in the shared source. Each invocation can track its remaining quota and reduce it by the amount actually transferred. **Agreed for v1.** A flow with several legs represents one activity. Each leg has a full-service rate in its own unit. Scarcity on any positive leg reduces the service fraction for the whole activity. Each instance can use this rule directly without declaring its own solver.

```text
flow restore:
    flow labor: this.crew.hours -> this.crew.used
        request = 4 crew_h/h
    flow work: this.controls_work -> this.controls_done
        request = 8 work_unit/h
```

**Proposed syntax and reads.** Here `crew_h` measures crew time and `work_unit` measures completed work. Each nested directed `flow` names one leg. Give each leg its own finite nonnegative `request`, as a rate or a live formula such as `formula(this.crew.pace_now)`. `restore.served_fraction` is dimensionless, from zero to one. At fraction `f`, each leg’s `actual_rate` is `f` times that leg’s current request. If labor is limited to 2 crew_h/h and everything else permits full service, `restore.served_fraction` is 0.5, `restore.labor.actual_rate` is 2 crew_h/h and `restore.work.actual_rate` is 4 work_unit/h. A leg requesting zero transfers zero. If every leg requests zero, the fraction is defined as zero.

The parent has no `request` or `actual_rate`, even when its legs happen to use the same unit. An unqualified `restore.actual_rate` is a type error. Read the named leg for a physical rate or read `restore.served_fraction` for progress relative to the requested pace. A leg joins its own endpoints’ `.flows` collections and can be named in their `priority(...)`. Its capacity limits the common fraction. A coordinating solver can select `restore.served_fraction` and refer to the resulting leg rates. The leg rates have no independent solver writers. [Water restoration scenario](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/scenarios/water_controls_wipe/water.scn#L375)

Water is consumed or transferred, a technician is occupied and later released, and a pump has throughput that several jobs can share. A job needing several resources requires a policy for granting them together. Flows of conserved quantities have the syntax above. A dedicated type for occupying and releasing a technician remains open. The distinction matters because holding a technician for a shift does not consume that technician.

## Actor decisions and observations

A deterministic condition gets its answer from the model. A chance mechanism uses the run mode to select an outcome. An actor’s choice offers available actions to a controller. During human playback, `sees` selects which observations to display to the player. All three decision producers can supply a value to the same branch syntax. The choice producer’s exact spelling remains open.

An available action with a forecast probability of zero can still be chosen by a person. An unavailable action cannot. Evaluating alternatives for display consumes no draw and makes no choice. When the decision occurs, capture the alternatives and probabilities, along with the displayed observations for a human player. Store the selected value locally if later stages need it. World state can continue changing after the decision. [Current actor and choice rules](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L369) · [Pausing for a decision](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/engine.md#L220)

**Authoring convention.** The occurrence and timing of a prompt tell the operator something. Suppose a pump has a hidden fault. If an audible alarm summons the operator, show the alarm and attach the detection evidence to that trigger. A manual start that reaches the same decision has its own explanation. If the operator learns about damage during a routine inspection, offer the inspection on schedule in both healthy and faulty cases and expose the finding when it becomes available.

`sees reservoir.water` shows the person playing the dam operator the water reading. The model can use `reservoir.gate` in formulas and decision logic, and an event can set the gate if it is writable. Guards determine which actions are available. `sees` affects only what human playback presents. [Current compiler visibility examples](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/tests/model/test_sight.py#L91) · [Evidence at the trigger](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/modeling-guide.md#L401)

# Worked models and supporting language

### Reserving a delivery

Suppose a delivery needs setup time before it can start. In this proposed event, the invocation starts with an empty batch. Other consumers can use the shared supply during setup. When setup finishes, the move reserves the requested amount and the local flow begins delivering it. The final gate keeps the invocation alive while the batch drains. Assume nonnegative amounts and a typed rate field `delivery_request` on the receiver.

```text
deliver = event(amount: L, setup: h):
    batch: L = 0 L in [0 L, amount]
    flow delivery: batch -> this.customer.water
        request = formula(this.delivery_request)

    after setup:
        move amount from this.supply to batch

    until batch <= 0 L
```

To reserve water at the outset, move it in the first stage and set the flow’s capacity to zero during setup. The customer receives the water later. The source has already given it up.

```text
deliver = event(amount: L, target_rate: L/h, setup: h):
    batch: L = 0 L in [0 L, amount]
    flow delivery: batch -> this.customer.water
        capacity = 0 L/h
        request = target_rate

    after 0 h:
        move amount from this.supply to batch

    after setup:
        delivery.capacity = none

    until batch <= 0 L
```

Each overlapping delivery has its own batch and rate. To evaluate a distribution for the rate when setup ends, that stage could assign `delivery.request = speeds.draw()` from a previously declared distribution. A shared throughput limit, supply shortage or full destination raises a separate allocation question. These examples assume sufficient supply and receiving capacity.

### Delivering at a changing rate

```text
receive = event(amount: L, starting_rate: L/h, rate_change: L/h^2):
    remaining: L = amount in [0 L, amount]
    readonly started_at: h = t
    flow delivery: remaining -> this.water
        request = formula(max(0 L/h, starting_rate + rate_change * (t - started_at)))

    until remaining <= 0 L
```

This example assumes an externally delivered batch of `amount` litres at invocation entry. The scalar argument supplies its size. Copying a reading from a modeled tank never debits that tank. The rewrite still needs to specify how an external opening balance is declared or recorded so the conservation trace distinguishes those cases. A delivery from an existing tank would reserve that water by moving it, as above. The captured start time belongs to this invocation. A later delivery can begin while the first is still running.

For `tank.receive.start(20 L, 5 L/h, 5 L/h^2)`, the requested rate rises from 5 to 10 L/h during the first hour. Its average over that hour is 7.5 L/h, so the tank receives 7.5 L. At the one-hour horizon 12.5 L still belong to the active invocation. At the end of the second hour the full 20 L have arrived and the invocation completes. A different ramp can leave the gate waiting indefinitely. Starting at 5 L/h and decreasing by 2 L/h each hour delivers only 6.25 L by the time the rate reaches zero at 2.5 hours. The pinned engine reproduced both trajectories with predeclared state.

## Optional formula differentiation

Under this proposal, `y.diff(z)` produces a live formula for how `y` changes with a named numeric quantity `z`, with other independent stored values held fixed. Its units are those of `y` divided by those of `z`. A member such as `this.pressure` can be a target.

```text
x = formula(2 * z)
y = formula(x + z)
dy_dz = y.diff(z)
```

Here `dy_dz` evaluates to 3. If `x = 2 * z` stored a value when assigned, the derivative is 1. The recommended behavior is to follow the current formula definition, including replacements. At a genuine kink or discontinuity the derivative is undefined. Sensitivity of a whole simulation to an input involves additional effects, including event timing, accumulated state and allocation, and is a separate capability.

## Assertions and their timing

**Recommendation.** An `assert` states a condition that must hold wherever it applies. An assertion over fixed inputs, such as `assert repair_threshold < failure_threshold @policy`, needs checking only after the effective inputs have been assembled. If an assertion reads mutable state, specify where the engine checks it or how it proves the condition throughout continuous evolution. Reject assertions whose promised guarantee the engine cannot provide.

Today `assert tank.gate is "closed"` can pass at startup even when the gate opens later, because the current compiler treats named states as startup values for this check. An author validating imported starting conditions might genuinely want every patient to begin untreated. An assertion over a starting input can already express many such requirements. A separate `assert initially` form remains deferred. [Current assertion rules](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L390)

A separate issue affects tolerance. In the reviewed compiler, `assert 1 + 1 is 2.05 within 0.1` fails on exact equality, while `assert true within undefined_name` can pass without resolving the name. These cases motivate the switch to interval checks.

The rewrite expresses numeric tolerance through a closed interval. The two `within` cases above are current compiler bugs. The proposed language has no `within` synonym. [Assertion parser](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/language/parse.py#L1278) and [resolution](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/language/resolve.py#L1702).

## Evidence at the point of use

**Recommendation.** Keep `@timing` as the short reference at a declaration and put the explanation in a reusable record. A record marked `source` should link to a supporting claim through `claims:`, or the report should identify the missing support. Preserve the distinctions among a source, a transfer from another setting, an assumption, an identity and a convention. [Current record syntax](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L437)

The current optional ID after the record kind can look like a source citation even when it identifies an assumption. One candidate labels the relationship at its definition.

```text
record timing: source_transfer "Applied from another setting."
    assumption A-TIMING
    claims:
        E-REPAIR-STUDY
```

A column citation suffices when one dataset supports the whole column. When rows or cells come from different sources, preserve the mapping from each imported value to the claim supporting it. The same distinction matters when the default and its allowed range have different justifications.

## Numerical scale hints

**Recommendation.** Let the engine infer numerical scale where possible and allow an override when the inferred scale understates how large a quantity can grow. The current `size` hint sets the magnitude used to calculate numerical tolerance. An inventory bound limits the stored amount, for example 20 L. A flow’s `capacity` limits throughput, for example 4 L/h. `scale` is a candidate replacement spelling. [Numerical sizing](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/engine.md#L331)

The pinned language reference calls `resolution` the longest solver step, while the engine describes an inspection interval within a numerical step. The rewrite needs separate guarantees for inspection spacing and integration error before choosing a new control. [Language reference](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L187) · [Engine step rules](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/engine.md#L338)

## Reference behavior in the current compiler

The examples here describe the pinned compiler. In an outcome, assignment expressions read the pre-outcome state. Setting `x = 2` and then `y = x` when x starts at 1 leaves y at 1. In a rewrite stage, y reads the new 2. Separate current events at the same time execute in file order under the current scheduling rules. A formatter must preserve ordering that affects results. [Current execution order](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L341)

The current single-pending-firing rule and event-header `while` can suppress or cancel a pending firing. Its trigger history can include a firing that was later cancelled. A named outcome can carry its own history. The rewrite assigns independent identities to overlapping invocations and uses ordinary domain events to record specific occurrences. [Current event timeline](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L306)

A fixed 20 L batch moving at 10 L/h delivers 5 L at half an hour and 20 L after two hours if unconstrained. Enabling an external 10 L/h source for exactly two hours happens to give the same result under those conditions. If the receiving end is constrained, the batch can finish later, while the timed supply stops at two hours. An event that simply waits two hours and adds 20 L produces a single jump at the end. [Current flow semantics](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L268)

Current distribution-valued inputs produce one scalar per sample and the central run uses a median. The four-argument `normal(mean, sd, min, max)` is a truncated Gaussian. Its actual moments can differ from the parameters of the underlying Gaussian. Future statistical properties must report the moments of the distribution they describe. [Current distribution definitions](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/distributions.py#L34)

## Expressions and instantaneous transfers

Keep the closed arithmetic and Boolean vocabulary, including `and`, `or`, `not`, conditional expressions, `min`, `max`, `clip` and `sqrt`. Retain `count`, `since`, `elapsed` and `delayed` with documented domains. How `elapsed` treats several writes to one state in a stage, and what a zero-delay historical read sees within that stage, still need examples.

The instantaneous transfer `move amount from source to destination` names both endpoints. `move(source, destination, amount)` is a candidate shorthand. **Proposed rule.** Either or both stored endpoints may be `readonly`. Evaluate the amount once and require a finite, nonnegative quantity compatible with both stocks. Check both resulting inventories against their bounds, then commit and account for the equal debit and credit together. A failed check fails the move without a partial transfer. A formula or fixed input cannot serve as a stored endpoint. Instantaneous moves have amounts. Per-hour capacities govern continuous flow rates. For example, moving 3 L from a `readonly` stock containing 8 L into an empty `readonly` stock capped at 4 L leaves 5 L and 3 L. Trying to move 5 L from the original state fails the destination bound and leaves 8 L and 0 L. `from` and `to` are reserved. Use `origin` and `destination` for route columns. Restricting other reserved names to Napkin’s own words is also a candidate, subject to what the evaluator can support. [Current call and move syntax](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/language/parse.py#L1126) · [Reserved names](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/language/resolve.py#L236)

## How templates compose into a run

Templates fix the types, dimensions and behavior shared by their instances. A repair team can configure input values, receiver links and stage guards to select inspection or remote reset. Instances share their template’s behavior. Event bindings are read-only by default at runtime. Keep differentiated behavior expressible through configuration or separate templates. A future setup-time replacement would require a compatible event and occurrence interface plus a rule for behavioral commitments. A table may identify a row by position. **Proposed spelling for stable links.** An `id` column supplies a nonempty identifier unique within that table. A cell such as `sites.clinic` names the row by this identifier. A missing target or a repeated identifier is a setup error because a link must resolve to exactly one row. This identity is independent of the numeric key used by `by`, `at` or `priority`. Several rows may have the same numeric key. Formula configuration, structural flow changes and reference contracts remain open.

Retain `use` to assemble shared declarations, `variant` for a model derived from the package base, and `change` for an explicit override. A change can rebind a connection or edit metadata as well as assign a value. Options bundle settings. The current package applies later-file changes last. Specify precedence and diagnose conflicting settings when forming an effective configuration. [Packages and variants](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L545)

**Open recommendation.** Require equivalent evidence for equivalent numeric overrides. Today an instance or `change` value needs a record, while an option assignment is exempt. A hypothetical value could cite an assumption, and a reused record should support the new value. How external overrides carry support, and how evidence applies to event arguments, remain open. [Evidence requirements](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L453)

### A run produces one trajectory

Resolve one effective configuration and supply the run mode, any sampled-run seed and controller choices to one execution. To compare early and delayed repairs, an experiment wrapper runs each configuration and compares the resulting trajectories. If both policies should experience the same weather, the wrapper can generate one weather realization and pass it to both calls. Equal seeds alone do not guarantee matching draws after the policies take different branches. Repeated sampling and exact weighting of alternative outcomes can also live in an analysis tool. The rewrite removes the `versus` declaration. A report chooses named values, times, layout and reporting transformations. A trace can identify the receiver, invocation, source location and evidence for a reading. [Current options and runs](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/language.md#L408)

# Open design questions

**Value types and ownership.** Reference parameters still need a spelling that distinguishes a stock from a copy of its numeric value. Other open choices include name shadowing, enum names without an expected type, how a property declares support for both a scalar and a live formula, and when a formula replacement is valid. The run already owns the trajectory. An author-visible `run` path remains optional.

**Events and collections.** The collection examples use `where`, `by`, `at`, `instances`, `occurrences` and `flows`. Open details include where a collection declares a reusable key, diagnostics for duplicate members in a literal, dispatch order for simultaneous starts, and which fields of the newest retired occurrence remain readable. Flows and occurrences can be added during a run. The archived flow’s key, endpoint identities, zero current rate and frozen final request are defined. What a historical reference to an occurrence-local stock can expose remains open. Other event decisions include the receiver meaning of `this`, names and multiplicity of attached triggers, which events they can start and whether a start returns a stable handle. Distribution constructors, distribution-valued overrides, shared uncertainty and bounds for transformed or unbounded draws remain open.

**Solver guarantees.** Numerical tolerances for ranked optima and for reading a solver-enforced equality in an ordinary formula remain open. The solver experiments below give the measured scope for fair sharing and the outstanding questions about affine inequalities and changing membership. Nonlinear route laws and types that distinguish different substances with the same physical dimensions remain extensions.

**Execution and composition.** Conflicting writes from independent stages, reset-cycle diagnostics, local temporaries, controller choice syntax and one-time setup order still need precise engine or authoring rules. The timing matters when a due stage changes beans from 8 g to 12 g before the round’s trigger check. A newly evaluated `beans <= 10 g` is false. An occurrence already queued by an earlier check follows the normal start rules. Configuration precedence, model identity and evidence for overrides also remain open.

### Allocation, timing and presentation

**Allocation and inventory.** Changing only the spelling of units must preserve allocations and level references, including on an isolated place. A completed occurrence must account for returned or disposed material under the proposed retirement rule. Inventory in an active occurrence at the horizon still belongs to that occurrence. The zero reference for a solver-local unknown without an initializer remains a proposed default.

**Continuously changing inputs.** A keyed hourly reading changes at known times. A request depending on a draining tank may change throughout integration. The supported scale for continuously changing coefficients and for threshold detection on solver results remains unmeasured. An unsupported condition requires a diagnostic. The discrete once-per-round settlement rule applies to all backends.

**Presentation.** The spelling for a package’s default report selection, references to status displays, and how reports show an unavailable history read remain open. Labels, cards, menu text, per-case status explanations and evidence stay with their model declarations.

## Scenario cases and remaining decisions

**Reference identity.** A model may assign to `reservoir.gate` directly when the field is writable. `readonly` on the gate protects it through every reference. `sees reservoir.water` governs the human player’s display. A separate type-design question is how an author asserts that two configured links identify distinct instances. [Reservoir operator example](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/examples/reservoir/model.scn#L37)

**Human choices within a stage.** The parent–child rule settles when a queued start becomes visible. For example, if `count(child.occurrences)` starts at zero and the stage queues one start, it stays zero for the rest of that stage and reads as one in the parent’s next delay expression. One question remains for interactive runs. If the stage requests a human choice after queuing the start, where does execution pause? [Current decision pause behavior](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/engine.md#L231)

**History and observation.** `since(refill)` before the first refill already has defined behavior inside a model. Decide how a caller handles the same invalid read in a report, so choosing an extra chart cannot change the modeled trajectory. Decide whether saving an occurrence reference pins its identity across later starts. A different history problem appears in the water scenario. Equal daily outage counts could describe the same people every day or different people each day. Counting people without service for a continuous week needs identity-preserving cohorts or individual histories. Declare `weekly_unserved: people = none @no_cohorts` until the model carries that information. [Water scenario](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/scenarios/water_controls_wipe/water.scn#L792)

**External inputs over time.** A wrapper can pass the same weather readings to two runs. `Reading.instances.by(hour).at(t).factor` holds the most recent observation, including after the final row. Give the key and its lookup argument compatible time units. The weather field has its own unit. If the queried time precedes the first row, the read fails. A pair of deliveries at the same instant creates two occurrences and both count. Reading one level and counting events ask different questions of the same collection type. [Heat-wave weather input](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/scenarios/heat_wave_blackout/model.scn#L22)

# Proofs and experimental evidence

## What a proof establishes

A compiler proof covers all permitted ways a value can change. A tally with only nonnegative additions can qualify for a reporting lag. A shared store that another occurrence can drain needs a proof covering that withdrawal too. Without proof that the value never falls, the lag is invalid. An evidence record can document disjoint populations or explain an absent estimate. Its citation does not prove a numeric invariant. [Current check semantics](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/docs/engine.md#checks) · [invariant proof rules](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/analysis/values.py#L716) · [partition use in output counting](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/analysis/structure.py#L719)

Conservation concerns physical inventory. For each internal transfer, the source loses the amount the destination gains. Material in active occurrences still counts at the horizon. A model can conserve every unit while a delivery waits indefinitely. Finite completion is a separate property.

## Fair sharing at 30,000 places

The reviewers’ synthetic network has 30,000 places, 35,000 routes and 15,000 sources. The measured path included a linear program and a squared-distance step. The reported distance step took about 0.1 s without shortage and 0.4–2.7 s in hours with sustained shortage, with one case at 5.9 s. Those measurements omit the middle rank that maximizes the smallest served fraction, then the next smallest.

A separate transport-only experiment uses the same counts and 15,000 unit claims. It has 5,000 groups on a ring, each with sources A, B, C of capacity 0.50, 0.60, 0.95 and consumers X, Y, Z. X can receive at most 0.35. In group `j`, A connects to local X, Y and Z. B connects to X and Z one group ahead and Y two groups ahead. C connects to local Z. Group indices wrap. The common service fractions are 0.35 for X, 0.75 for Y and 0.95 for Z. X reaches its cap first. X and Y can draw only from A and B, totaling 1.10 per group, and C can supply Z. Sending A’s 0.35 to X and 0.15 to Y, B’s 0.60 to Y and C’s 0.95 to Z attains all three bounds.

| Method on the transport-only graph | Work per run | Measured time |
| - | - | -: |
| Maximize total service | One cold linear program, three runs | 0.94–1.12 s |
| Max-min fairness, continuous formulation | Three cold linear programs, two runs | 12.93–13.38 s |
| Max-min fairness, specialized integer transport calculation | 18 max-flow calls, four runs | 0.084–0.115 s |

Both fairness methods returned the three fractions above. The continuous formulation used the ring’s symmetry to identify consumers fixed at each fraction. The transport calculation identified them from residual capacity and searched at one-percentage-point increments, exact for this case. Timings used an Intel Xeon Platinum 8573C, SciPy 1.18.1 and HiGHS 1.12.0, with a single solver thread. They include the search for successive fractions and exclude initial topology construction, startup and simulation.

**Scope of the evidence.** Fair sharing took about 13 s with repeated continuous linear programs on this three-tier transport instance. The faster result depends on its transport structure. The complete ranked solve on the reviewers’ route-and-level network, with signed routes, arbitrary affine constraints, changing claims and potentially many tiers, remains unmeasured. The timings above cannot establish a throughput guarantee for that workload.

## Two solver cases with no measurement yet

**Inequalities in the final squared-distance step.** The current prototype takes equalities and per-coordinate intervals. The proposed language also admits coupled `<=` and `>=` constraints. With equal scales and `4 <= x + y <= 6` expressed as two constraints, targets `(0, 0)` should select `(2, 2)` and targets `(5, 5)` should select `(3, 3)`. The distance step must preserve both the feasible region and all earlier optima. Its general inequality behavior and cost remain unverified.

**Unknowns that enter and leave a running solve.** The bundled solver exposes operations for changing the variable set. Their correctness and cost in a live Napkin solve remain unmeasured. For example, with a 3 L/h shared limit and 2 L/h requested per occurrence, A alone should receive 2 L/h. A and B together should receive 1.5 L/h each. After A retires, only B remains at the endpoint and receives 2 L/h. After B retires the endpoint is empty. At each moment, the published rates and active membership should match a freshly formed problem for that moment.

## Delivery experiments on the pinned engine

At commit `13b0969`, the in-memory delivery experiments used predeclared channels and a gate for the delayed start. Both deliveries requested 10 L/h. The recorded figures are litres per delivery and hours to finish.

| Setup | Delivered at 1 h, A / B | Completion, A / B |
| - | - | - |
| Separate 20 L batches | 10 / 10 L | 2 / 2 h |
| Shared 40 L supply with 10 L/h total throughput | 5 / 5 L | 4 / 4 h |
| Same shared supply with B starting at 1 h | 10 / 0 L | 3 / 4 h |

For the delayed start, A/B totals at hours 2, 3 and 4 were 15/5, 20/10 and 20/20 L. Conservation checks passed and completion traces matched. These results establish delivery behavior with predeclared flows. Dynamic flow creation and solver throughput were outside the experiment’s scope.

The pinned compiler’s proofs and timeline readers assume a fixed model structure. Its general continuous path builds a dense stock-by-flow matrix. These constraints matter when interpreting the measured delivery results and the proposed dynamic-flow examples. [Current proof assumptions](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/model/analysis/values.py#L716) · [Fixed rule state](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/engine/timeline/run.py#L253) · [Continuous system matrix](https://github.com/jfeiglin/napkin/blob/13b0969bdfa30a1ae2d74cc083ba066424fd3f84/napkin/engine/continuous/system.py#L152)

# Appendix: open items that the implementation plan adds

These items are not part of the proposal's text. Gate G0 rules on each of them, with every item
that the proposal itself calls open.

1. **`none` in arithmetic.** A formula can read a value that is declared `= none`. The proposal
   does not say what `none + 1 L` gives, what a comparison with `none` gives, or what a reduction
   over a collection gives when one member's field is `none`. (Prototype A2)
2. **A flow with legs that two endpoints rank differently.** A flow with several legs has one
   served fraction at a given tier. Its legs can be named in `priority(...)` at two endpoints, with
   different ranks. The proposal does not say in which tier the one fraction is decided.
   (Prototype A2)
3. **Occurrences that never finish.** An `until` gate can wait for ever, and a trigger can start
   occurrences without limit. The proposal gives no budget and no message. (Prototype A2)
4. **The fair-sharing measurement.** The 13 s figure for max-min fairness used the symmetry of the
   ring to find the consumers that are fixed at each fraction. A general network has no such
   symmetry. The cost on the route-and-level network is not measured. (Prototype A3)

## A known error, for the owner to correct at G0

The `unserved_volume` example (under "Formulas and the values a caller can read" and "Model text,
status cases and evidence") calls the quantity a current volume that "can fall when service
returns". In the water model the rate falls and the volume does not: `unserved_rate` (Mgal/h) goes
to zero when service returns, and `unserved` (Mgal) accumulates that rate and keeps the loss
(`scenarios/water_controls_wipe/water.scn:264`, `:374`, `:701`).
