# Values and types

This page tells how a model declares, reads and changes a value, and which types a value can have.
It also gives the rules of units, members, links, collections, formulas, distributions, scopes,
tables, text and status displays. The words in bold are the [terms](README.md#terms) of the
documentation.

## Contents

1. [Declare a value](#declare-a-value)
2. [Read a value](#read-a-value)
3. [Change a value](#change-a-value)
4. [Types](#types)
5. [Units and quantities](#units-and-quantities)
6. [Ranges](#ranges)
7. [Expressions](#expressions)
8. [Members, templates and instances](#members-templates-and-instances)
9. [Collections, keys and projections](#collections-keys-and-projections)
10. [Formulas](#formulas)
11. [Distributions and draws](#distributions-and-draws)
12. [What each scope can see](#what-each-scope-can-see)
13. [Tables](#tables)
14. [Text and titles](#text-and-titles)
15. [Status displays](#status-displays)

## Declare a value

A declaration is one line: a name, an optional type, an optional initializer, and then the optional
range, scale and citations.

```text
[readonly | input] name[: type] [= initializer] [in [lo, hi]] [scale s] [@record ...]
```

```scn
grinder:
    beans: g = 8
    readonly low_on_beans: formula(bool) = formula(this.beans <= 10 g)
    refill = event(amount: g):
        after 0.5 h:
            this.beans += amount
```

- `beans: g = 8` declares a stored **value** of 8 g. The declared unit gives the bare number `8`
  its unit. `beans: g = 8 g` is the same declaration.
- `readonly` bars a direct assignment to the value through every path: `=`, `+=` and `-=` are
  errors. A flow or a `move` can still change a `readonly` **stock**
  ([flows-and-solvers.md](flows-and-solvers.md), [events.md](events.md#move-an-amount)).
- `input` marks an **input**: a value that a named run or an edit can set before the run. An input
  is fixed during the run. No statement assigns it.
- A value with no type takes the type of its initializer: `water = 20 L` is a volume.
- A type alone checks the value and gives no initial value. A value of a template with a type and
  no initializer must get its value from each member ([Members](#members-templates-and-instances)).
- The range and the scale can stand on rows of their own under the declaration:

```scn
input delay: h = 3
    in [0.5, 12]
    @timing
```

A declaration stands at the top level, in an entity, in a template, or at the start of an event (a
local of the occurrence, [events.md](events.md#state-of-an-occurrence)). An event has no `input`:
its parameters take its arguments.

### The kinds of a declared value

The compiler gives each declaration a kind. The kind decides what can change the value.

| Kind | How the model writes it | What can change it during the run |
| --- | --- | --- |
| Input | `input rate: L/h = 2 L/h` | Nothing. An edit or an option sets it before the run. |
| Stored value | `water: L = 8 L`, `gate: enum[OPEN, CLOSED] = OPEN` | A stage, and for a number a flow, a `move` or a solver |
| Formula | `low = formula(this.water < 5 L)` | It follows the values that it reads. A stage can give it another formula. |
| Distribution | `speeds = uniform(1 L/h, 3 L/h)` | A stage can give it another distribution. |
| Link | `origin: Place` | Nothing. A link is fixed for the run. |
| Collection | `pumps: <Pump> = <this.primary, this.backup>` | Nothing, when its members are fixed |

A stored number that a flow or a `move` touches is a **stock**. The engine keeps an exact balance
for each stock. A stock that nothing drains is a tally. A tally has no mark of its own.

### Where a value comes from

An input can get its value from several places. The first of these places that gives a value
wins:

1. An edit of the run in the edit document.
2. An edit of one of the options of the run.
3. An edit of every run (`set` in the edit document).
4. An option of the run.
5. The program: a `change` of a variant, then the own line of a member, then the template.

At each of the first four places, a line for one member wins over a line for every member of its
template (`Pump.instances.rate`). Two options of one run that set one input are an error. The order
of the files never decides. The edit document is in [cli.md](../cli.md) and
[python-api.md](../python-api.md).

An override follows the declared type. A duration input takes a duration in its range. A number
for an input whose default is a draw skips the draw ([Distributions](#distributions-and-draws)).

### Initializers of the setup scope

A line at the top level can give a value its initializer by the full path. The line has the same
meaning as the initializer under the declaration.

```scn
tank:
    readonly water: L = 8 in [0, 20]

clinic:
    flow delivery: tank.water -> SINK

clinic.delivery.request = 3 L/h
```

- The path can name a value of an entity, a setting of a flow, a leg or an endpoint of an entity,
  or the own value of a member.
- A path has one initializer. A second initializer is an error that names both lines.
- A `readonly` value can take an initializer here. `readonly` bars an assignment, not an
  initializer.
- The setup scope has no other statement. A top-level start of an event is the only action
  ([events.md](events.md#start-an-event)).

### The order of starting values

Starting values at the top level and in members follow their dependencies, not the order of the
file. If `clinic.water` reads `supply.initial_water`, the engine calculates the second value first.

- A cycle among starting values is an error. The message gives the chain:
  `a.total reads b.total reads a.total`.
- Two members can link to each other. Mutual links are no cycle.
- The compiler checks cycles on the actual links of the members. A template whose value reads the
  same value of other members (`total = this.demand + sum(this.children.total)`) is no cycle when
  the links make no circle. Such a value must declare its type.
- The locals of an event start in written order ([events.md](events.md#state-of-an-occurrence)).

## Read a value

An expression reads a value by its **path**.

| Path | What it reads |
| --- | --- |
| `this.water` | The value `water` of the member that owns the line |
| `tank.water` | The value `water` of the entity `tank` |
| `limit` | A value at the top level, or a parameter or a local inside an event |
| `this.origin.power` | The value `power` of the member that the link `origin` names |
| `sites.clinic.need` | The value `need` of the row `clinic` of the table `sites` |
| `t` | The time of the run, in hours from 0 |

`this` always names the member that owns the declaration, the event or the trigger. A link or a
start from another entity does not change it. A path that names nothing is an error.

A **reading** is the value of a path at a time in a **record**. Any named value has readings: a
stored value, a formula, a rate, a setting of an endpoint, a status display. The caller selects the
paths and the times ([cli.md](../cli.md)).

## Change a value

| How | Where | Page |
| --- | --- | --- |
| `x = v`, `x += v`, `x -= v` | A statement of a stage | [events.md](events.md#assign-a-value) |
| `move a from s to d` | A statement of a stage | [events.md](events.md#move-an-amount) |
| A flow | Between two stocks, or a stock and `SOURCE` or `SINK` | [flows-and-solvers.md](flows-and-solvers.md) |
| A solver | The values that its `solve_for` names | [flows-and-solvers.md](flows-and-solvers.md#declared-solvers) |
| An edit | Before the run, or at a breakpoint | [events.md](events.md#breakpoints-checkpoints-and-edits) |

A statement assigns only a declared, writable target. A misspelled target is an error. An input, a
link, an event and the ends of a flow are fixed. What the run calculates is never a target: an
actual rate, a served fraction, and the `started`, `done` and `active` fields of an occurrence.

## Types

| Type | How to write it | Example |
| --- | --- | --- |
| Boolean | `bool` | `ready: bool = true` |
| Enum | `enum[A, B, ...]` | `gate: enum[OPEN, CLOSED] = OPEN` |
| Plain number | `number`, or `1` | `count: number = 3` |
| Quantity | A unit: `L`, `L/h`, `person * year` | `water: L = 8` |
| Text | `text` | `input label: text = "north"` |
| Formula | `formula(T)` | `ready: formula(bool) = formula(this.water > 2 L)` |
| Distribution | `distribution(T)` | `input spread: distribution(h) = uniform(1 h, 5 h)` |
| Collection | `<Template>` | `pumps: <Pump> = <this.primary, this.backup>` |
| Link | A template name | `origin: Place` |

- A Boolean is not a number. `ready + 1` is an error. Write `1 if ready else 0` for a numeric
  reading of a Boolean.
- An enum lists its members by name, each with a capital first letter. Two declarations of
  `enum[OPEN, CLOSED]` are one type. Two enum values compare only when they have the same enum.
- A bare member such as `OPEN` takes its enum from its place: a declared type, the other side of a
  comparison, an assignment target, a parameter, a case of a `switch` or a column of a table.
  `gate = OPEN` alone is an error. Write `gate: enum[OPEN, CLOSED] = OPEN`.
- A text has `==` and `!=` and no other operation.
- A link compares by identity with `==` and `!=`.
- There is no empty value. A model declares what it can state and leaves out what it cannot. The
  documentation or a `record` declaration explains a value that the model does not estimate.

## Units and quantities

A number with a unit is a quantity: `8 g`, `2 h`, `4 L/h`. The unit follows the number after one
space. A quantity is its dimension and its exact value in the canonical unit, not its spelling:
`1 day` and `24 h` are the same quantity.

### Where units come from

The units of a model come from the prelude (`napkin/std/units.json`), from the library that the
scenario line names, and from `units.json` in the package and in a variant. The prelude has the
units of time (`h`, `hour`, `day`, `week`, `month`, `year` and their plurals) and `fraction`,
`ratio`, `percentage_points`, `person` and `people`. A name of the prelude cannot be defined again.
Each unit has a dimension and an exact factor: the size of one unit in the canonical unit of its
dimension.

### Units multiply and divide

A compound unit uses `*` and `/`, and it means what the arithmetic says.

- `48 h/2` and `48 h / 2` are both `24 h`. The 2 is a number, and no unit is named `h/2`.
- `(3 person) * (2 year)` is `6 person * year`. `(6 L) / (2 h)` is `3 L/h`.
- After a number, the unit continues through `*` and `/` while the next factor is the name of a
  unit. It stops at a number, a bracket, a dotted path or a name that is no unit.
- `2 h * this.crews` stops before `this.crews`. To multiply by a value whose name is also a unit,
  put the quantity in brackets: `(2 h) * hour`.
- `*` and `/` group from the left. A product below the line needs brackets:
  `tunings / (tuner * year)`.
- A square is `m * m`. A rate of a rate is `L/h/h`. A unit has no hyphen and no power.

The compiler derives the dimension of each product and quotient. It checks the dimension against
the place that receives the value:

- `+`, `-`, a comparison, `min`, `max`, `clip` and the two sides of `if ... else` need one
  dimension.
- A value has one dimension in every instance of its template.
- `L/h` and `m * m * m/day` convert. A mass rate cannot stand in a field of volume rate.
- `**` raises a value. `sqrt` and `**` multiply the powers of the dimension, and each power must
  stay whole: `sqrt(24 h * 1 day)` is a time, and the square root of a plain ratio is a plain number.

### A bare number

A bare number takes the declared unit in these places:

- the whole initializer of a declaration: `beans: g = 8`;
- a bare end of the range of the declaration: `water: L = 8 in [0, 20]`;
- the scale of the declaration;
- the value arguments of a distribution, when the distribution or its draw is the whole
  initializer: `input repair_time: h = uniform(1, 3).draw()` draws from 1 h to 3 h;
- the own value of a member, and a cell of a table.

A bare zero takes the unit of the other side: `max(0, need - use_rate)`. In `2 * this.delay` the 2
is a plain number.

## Ranges

A trailing `in [lo, hi]` on a declaration gives the allowed range of the value. Both ends are
included.

```scn
water: L = 8 in [0,]
```

- Either side can be empty. `in [0,]` is never below zero and has no upper end. `in [, 10 L]` has
  only an upper end.
- A quantity with no range has no bound. A stock that must not go below zero needs `in [0,]`.
- A reversed range is an error: `[2 L, 1 L]`. An end that only the run knows is checked when the
  run evaluates it.
- A starting value outside its range is an error.
- The range of an input limits its overrides. The range must hold the support of a default draw:
  `uniform(1 h, 3 h).draw() in [1 h, 12 h]` admits an override of 5 h.
- A range is a bound. A `scale` is not ([numerics.md](numerics.md#scale-hints)).

In an expression, `x in [lo, hi]` tests membership. To keep the result in a value, put the test in
brackets: `ok = (x in [lo, hi])`. Without brackets, `in` after the `=` of a declaration starts the
range of the value. After the `=` of a statement, a bare `in` is an error.

```scn
assert total in [initial - tolerance, initial + tolerance]
```

The tested value is evaluated once. For an exclusive upper end, write `lo <= x and x < hi`, or the
chain `lo <= x < hi`. There is no `not in`: write `not (x in [lo, hi])`.

## Expressions

The operators bind from the loosest to the tightest:

1. `a if C else b`
2. `or`
3. `and`
4. `not`
5. A comparison (`<`, `<=`, `>`, `>=`, `==`, `!=`) or `x in [lo, hi]`
6. `+` and `-`
7. `*` and `/`
8. A sign (`-a`)
9. `**`
10. A dot: a member or an operation (`a.b`, `c.where(...)`)

- A chain of comparisons points one way: `lo <= x < hi`. `a < b > c` is an error.
- `and` and `or` read their terms from the left and stop at the term that decides. A conditional
  reads only the side that it selects.
- `=` assigns or declares. Equality inside an expression is `==`.

| Function | What it gives |
| --- | --- |
| `min(a, b, ...)`, `max(a, b, ...)` | The smallest or the largest argument, or of a projection |
| `clip(x, lo, hi)` | `x` held inside `[lo, hi]` |
| `abs(x)` | The magnitude of `x` |
| `sqrt(x)` | The square root of `x`, with half the powers of its dimension |
| `exp`, `expm1`, `ln`, `log1p`, `erf` | The function of a plain number |
| `sum`, `count`, `any`, `all` | A reduction of a collection ([Collections](#collections-keys-and-projections)) |
| `since(e)` | The time since the latest start of the event `e` ([events.md](events.md#history-of-an-event)) |
| `elapsed(x)` | The time since the value `x` last changed at a commit |
| `priority(...)`, `proportional()` | An allocation ([flows-and-solvers.md](flows-and-solvers.md#local-allocation)) |

The distributions (`uniform`, `triangular`, `pert`, `loguniform`, `normal`, `lognormal`,
`categorical`) are in [Distributions](#distributions-and-draws).

## Members, templates and instances

A **member** is a thing with values of its own. The top level declares members in these forms.

| Line | What it declares |
| --- | --- |
| `tank:` | An **entity**: one member, which is the only member of its own type |
| `Place:` | A **template**: a declared type of member. It makes no member alone. |
| `clinic: Place` | An **instance** of `Place`, written by hand, with its own lines under it |
| `sites: Place from "places.csv"` | One instance of `Place` for each row of a table ([Tables](#tables)) |

A template gives each instance its values, flows, events, solvers, assertions and status display.
The lines under an instance give its own values. They can give a new initializer of a value, a new
formula (with `formula(...)`), a new link, a text, a `title` and evidence. An instance adds no
value that its template does not declare.

```scn
Place:
    input need: L = 1 L in [0 L,]
    input rank = 0
    big = formula(this.need >= 2 L)

d: Place
    need = 4 L  @fixture
    rank = 4  @fixture
```

- A value of a template with no initializer needs a value from each member. A member that gives
  no value is an error.
- A member replaces a formula of its template only with another formula: `big = formula(...)`.
- A member gives values and links only. The template gives the settings of its flows and endpoints:
  `out.capacity = 2 L/h` under a member is an error.

### Links

A link is a value that names one member. A link is fixed for the run.

```scn
Pump:
    home: Place
    home_need = formula(this.home.need)

pump_one: Pump
    home = places.c
```

- `home: Place` declares a link. Each member sets it, or the declaration gives it an initializer:
  `home: Place = clinic`.
- A member that sets no link is an error, because there is no empty value.
- A path follows a link: `this.home.need`.
- A flow can end at a stock through a link: `this.origin.power`
  ([flows-and-solvers.md](flows-and-solvers.md#endpoints)).
- No stage assigns a link. A `change` in a variant can give a link a new member.

### Event parameters that name members

A parameter whose type is a template names a member. The event reaches the values of the member
through it. A parameter with a unit gets a copy of a number ([events.md](events.md#parameters)).

## Collections, keys and projections

A **collection** holds distinct members of one type: entities and instances, flows, or occurrences.
Each member has a numeric **key**. The type of a collection is `<T>`.

| Collection | What it holds | Natural key |
| --- | --- | --- |
| `Place.instances` | Every instance of `Place`: members written by hand and rows of tables | The creation number, from 0 |
| `<places.a, places.c>` | The members that the literal names | The creation number |
| `this.refill.occurrences` | Every occurrence of the event, active or finished | The start time |
| `tank.water.outflow.flows` | The flows that leave the stock now | The creation number of the flow |

- A literal names each member once. `<a, a>` is an error.
- An empty literal needs a declared type: `idle_pumps: <Pump> = <>`.
- The creation numbers follow the order of the model: the members written by hand and the rows of
  each table in the order of the text. The rows of a table with ids follow the order of their ids.
- A collection can be the value of a member: `machines = <a, b>`, `places = Place.instances`.

```scn
readonly pumps: <Pump> = <this.primary, this.backup>
readonly idle_pumps: <Pump> = <>
```

### Projections and reductions

A **projection** reads one field of each member: `Place.instances.need`. A projection carries the
key of each member with its value. Only a reduction, a `solve_for` entry, a `priority(...)` or a
start on each member reads a projection. A projection is no list of values: `x = Place.instances.need`
is an error. Put the calculation on the member, then reduce the field.

| Reduction | What it gives | On an empty collection |
| --- | --- | --- |
| `sum(c.f)` | The total of a numeric field | Zero in the unit of the field |
| `count(c)` | The number of members | 0 |
| `count(c.done)` | The number of true values of a Boolean field | 0 |
| `any(c.f)` | Whether one Boolean value is true | `false` |
| `all(c.f)` | Whether every Boolean value is true | `true` |
| `min(c.f)`, `max(c.f)` | The smallest or the largest value | The read fails |

`count(c.amount)` of a numeric field is an error, also on an empty collection. Use `sum(c.amount)`
for the total, or `count(c)` for the number of members.

```scn
total_need = sum(Place.instances.need)
big_count = count(Place.instances.big)
any_big = any(Place.instances.big)
all_big = all(Place.instances.big)
least = min(Place.instances.need)
most = max(Place.instances.need)
first_ranked = Place.instances.by(rank).at(1).need
ranked_need = sum(Place.instances.where(rank >= 2).need)
pair_need = sum(<places.a, places.c>.need)
```

### `where`, `.by` and `.at`

| Operation | What it gives |
| --- | --- |
| `c.where(test)` | The members for which the test holds, with their keys |
| `c.by(field)` | The same members, with the numeric field `field` as their new key |
| `c.at(x)` | The member with the greatest key at or below `x` |

**Names inside `where`.** A bare name on the left of a comparison is a field of the member. The
expression on the right resolves in the enclosing scope. In `Route.instances.where(destination ==
this)`, `destination` is a link of each route and `this` is the member that owns the line.

- `where` tests only what is fixed for each member: its inputs and its links, and the parameters
  of an occurrence. A test of a live value is an error (`where_live`). For a live test,
  put a Boolean formula on the member and reduce it: `count(c.big)`.
- A `where` over flows can test their ends: `count(tank.water.outflow.flows.where(sink ==
  clinic.water))`. In that test, `source` and `sink` are the ends of each flow. They compare by
  identity with a stock.

**Keys.** `by(field)` keeps the identities of the members. It only gives them another key.

- `c.at(x)` reads the member with the greatest key at or below `x`. Of members with equal keys, it
  reads the member that the model creates later.
- `x` must be of the dimension of the key. The engine converts it before the comparison.
- Above the last key, the last member applies. A lookup in an empty collection, or below the first
  key, fails when the run evaluates it.
- `.at(x)` is a step. It does not interpolate.
- `Reading.instances.by(hour).at(t).factor` holds the 10:00 reading at 10:40 and changes at 11:00.

The compiler reports two cases and refuses neither:

- Equal keys in a keyed view that `.at(...)` reads, at the row that wins. A `where` limits the check
  to the rows that pass it. Equal ranks in a view that only `priority(...)` reads are valid.
- A lookup below the first key, when the argument has a known lower bound.

## Formulas

`formula(expression)` keeps a calculation. Each read evaluates it with the values that it reads at
that time. An ordinary expression captures its value once, when the engine evaluates it.

```scn
captured = this.water / (2 h)
readonly draining = formula(this.water / (2 h))
readonly ready: formula(bool) = formula(this.water >= this.minimum)
```

When the water changes, `draining` changes and `ready` can change. `captured` keeps the rate that
it read at the start.

- A formula cannot draw, change a value, start an event, or read itself through a cycle.
- `formula(T)` in a type describes a formula with a result of type `T`.
- A stage can give a writable formula another formula with `=`. A number or `+=` cannot replace a
  formula.
- `formula(this.draining)` reads `draining` and follows a later replacement of it. Nothing copies a
  definition.
- In an event, a formula local can read a local below it, because it evaluates when it is read.
- The `request` and the `capacity` of a flow or an endpoint take a number or a formula. No other
  value has both forms ([flows-and-solvers.md](flows-and-solvers.md#request-capacity-and-actual-rate)).
- A formula of an occurrence keeps its last result when the occurrence finishes
  ([events.md](events.md#a-finished-occurrence)).
- A formula that a stage installs may read only what lives as long as its own place. An entity
  formula that reads a parameter of an occurrence is an error.

Name a calculation with an ordinary declaration to read it in a record. The two values below answer
different questions:

```scn
Utility:
    input demand: L/h = 2 L/h
    flow delivery: tank.water -> SINK
        request = formula(this.demand)
    unserved_rate = formula(max(0 L/h, this.demand - this.delivery.actual_rate))
    unserved: L = 0 in [0,]
    flow count_unserved: SOURCE -> this.unserved
        request = formula(this.unserved_rate)

initial_unserved = sum(Utility.instances.unserved)
unserved_volume = formula(sum(Utility.instances.unserved))
unserved_now = formula(sum(Utility.instances.unserved_rate))
```

`initial_unserved` reads the tallies once, at the start. `unserved_volume` follows them, and
`unserved_now` follows the rates. When service returns at hour 5, the rate falls to zero. The volume
at hour 6 still holds the water that the customers did not get before hour 5.

A caller can ask for a reporting lag of a value that never falls, such as `unserved_volume`. The
compiler must prove that the value never falls. `unserved_now` can fall, so it takes no lag
([cli.md](../cli.md)).

## Distributions and draws

A distribution describes a random number or a random member of an enum.

| Distribution | Parameters, in order |
| --- | --- |
| `uniform(min, max)` | The lowest and the highest value |
| `triangular(min, mode, max)` | The lowest, the most likely and the highest value |
| `pert(min, mode, max)` | The lowest, the most likely and the highest value |
| `loguniform(min, max)` | The lowest and the highest value |
| `normal(mean, sd)`, `normal(mean, sd, min, max)` | The mean and the standard deviation, and the bounds |
| `lognormal(median, gsd)`, `lognormal(median, gsd, min, max)` | The median and the geometric standard deviation, and the bounds |
| `categorical(A: w, B: w, ...)` | The members of an enum, each with its weight |

- The parameters follow the rule of their family. `uniform(5 h, 2 h)` is an error.
- The compiler converts the parameters to one unit and reads them exactly.
- The geometric standard deviation of `lognormal` is a plain number.
- The bounded forms of `normal` and `lognormal` cut the distribution at `min` and `max`. Their moments
  are those of the cut distribution.
- A `categorical` takes the enum of its place, or the enum of its outcomes. A weight can be zero.
  The engine divides the weights by their sum.

### Read and draw

`d.mean` and `d.std` read the mean and the standard deviation of a numeric distribution. They make
no draw. A categorical has no mean.

`d.draw()` takes one value from the distribution. It draws each time that the engine executes it.

- A draw stands where the engine captures a value once: an initializer, a statement of a stage, a
  capture of a trigger, an argument of a start, the delay of a stage.
- A formula, a gate, a trigger, a reset and an assertion are read again, so they make no draw.
- A branch that the engine does not take makes no draw.
- Store a draw to read it twice. Two draws are independent. Correlated draws are not in the language.

```scn
machine:
    operational: bool = false
    input repair_times = uniform(1 h, 3 h)
    repair = event():
        duration: h = this.repair_times.draw()
        after duration:
            this.operational = true
```

`repair_times` is an input whose value is a distribution. A run can give it another distribution,
such as `uniform(2 h, 4 h)`. Each repair still draws its own duration.

An input can draw its default. Each instance draws once in a run.

```scn
input repair_time = uniform(1 h, 3 h).draw() in [1 h, 12 h]
```

A number override of `repair_time` skips the draw. Without the explicit range, the input admits
overrides from 1 h to 3 h, the support of the distribution.

### The run mode

| Mode | A numeric draw | A categorical draw |
| --- | --- | --- |
| `median` | The median of the distribution | The most likely eligible outcome, the first declared of them on a tie |
| `sampled` | A sample, keyed by the seed | A sample among the eligible outcomes |

The default run is a median run. A median run has no seed. A sampled run needs a whole-number seed.
The key of each draw is the seed, the place of the draw in the model and the member, the
occurrence or the firing that executes it. A read of a distribution, an extra report, another step
size or a branch that the engine does not take moves no other draw. The eligible outcomes of a
`switch` are in [events.md](events.md#branch-with-switch).

## What each scope can see

A name resolves in the scope of its line. The run itself has no path: a model cannot read its mode
or its seed.

| Scope | `this` | Bare names | Other names |
| --- | --- | --- | --- |
| Top level | No member | Values at the top level, entities, tables, templates | Paths through them |
| Entity or template | The member | Values at the top level, entities, tables, templates | `this.x` for the own values of the member |
| Event (locals and stages) | The receiver of the occurrence | The parameters and the locals of the occurrence, and the names of the top level | `this.x`, links, entity parameters |
| Trigger | The receiver | The captures of the trigger, and the names of the top level | `this.x`. A trigger has no occurrence, so it reads no parameter and no local. |
| Solver | The member that owns the solver | The bindings of `inputs:` and the unknowns of `solve_for:` | `this.x` |
| `where` test | The member that owns the line | A bare name on the left is a field of each member | The right side resolves in the enclosing scope |
| Flow property | The member that owns the flow | As for its owner | The flow by its path: `this.delivery.source` |

- A bare name inside an entity does not name a value of the entity. Write `this.water`.
- A path can read a value and assign a writable value across members.
- The properties of flows, routes, legs, endpoints and solvers are in
  [flows-and-solvers.md](flows-and-solvers.md#what-each-flow-scope-can-see).
- The fields of an occurrence are in [events.md](events.md#occurrences).

## Tables

`name: Template from "file.csv"` makes one instance of the template for each row of a table. The
table is a file of the package.

```scn
Place:
    input need: L = 1 L in [0 L,]
    input rank = 0
    big = formula(this.need >= 2 L)

places: Place from "places.csv"
```

```text
id,need,rank
a,1,2
b,2,1
c,3,3
```

- A table is UTF-8 text with commas between its cells. A cell that holds a comma, a quote or a line
  break is in double quotes.
- The first row is the header. Each row after it is one member.
- A header cell is `name` or `name: unit`, and then the citations of the column:
  `base_need: W @survey`. The name is a value of the template, or `id`.
- The column `id` gives each row a stable name: the row `sites.clinic`. A reordered file names the
  same members. An id is unique in its table, and it is not empty.
- A table name is no collection. `sum(sites.need)` is an error. `Place.instances.need` reads every
  member.
- The rows of a table without ids have no names.

A cell gives its row what the line `column = cell` gives a member written by hand:

| Cell | What it gives |
| --- | --- |
| A number | A number in the unit of the column. A cell can write its unit when the header writes no unit: `2 L/h`. |
| `true`, `false` | A Boolean |
| A word | A member of an enum, or a text for a text value |
| A member name | A link: a member written by hand (`east`) or a row (`sites.junction`) |
| An empty cell | Nothing: the row keeps the value of the template |

A cell holds a value, so a formula stays in the template. Two link columns of one row can name rows
of one table, and a flow of a row can end at stocks of other rows. The worked network in
[flows-and-solvers.md](flows-and-solvers.md#a-solver-over-collections) uses both.

## Text and titles

A text on its own row under a line describes that line.

| Under | The text is |
| --- | --- |
| A value | Its label |
| An entity or a template | Its description |
| An event, or a case of a `switch` | Its card |
| An option | Its menu line |
| An assertion | Its message |
| A status case | The text of the case |

A line has one text. Reports, playback and pictures show the text. No calculation reads it, and
the hash of the model does not change with it.

`title "Text"` under an entity, a template, an instance or a `change` gives a name that reports and
playback show for the member. A title is no part of the identity of the program, and no hash covers
it.

```scn
plant:
    "A plant with one tank."
    title "The plant"
    input rate: L/h = 2 L/h in [0 L/h, 10 L/h]  @fixture
        "Fill rate"
```

## Status displays

A status display rates a member with `ok`, `degraded`, `failed` or `inactive`, and gives a text for
each case. Write it under an entity or a template.

```scn
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

- The cases stand in written order. The first case whose condition holds gives the rating and the
  text.
- The last case has no condition. It is the fallback, and only it has no condition.
- Two cases can share a rating and have different texts.
- A condition is a Boolean that makes no draw.
- The display has the path `crew.status`. Its reading is the case that applies (`case[2]`), with its
  rating and text. The owner of a display declares no value named `status`.
- A display gives a rating to a reader. It does not change the run. For a state of its own work, a
  model declares an enum value.
