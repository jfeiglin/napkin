# Events

An **event** is a declared activity with stages. Each start of an event is an **occurrence**, with
its own arguments, locals, flows and stages. This page gives the parts of an event, the statements
of a stage, triggers, time, the history of occurrences, assertions, and breakpoints, checkpoints and
edits. The words in bold are the [terms](README.md#terms) of the documentation.

## Contents

1. [Declare an event](#declare-an-event)
2. [Start an event](#start-an-event)
3. [State of an occurrence](#state-of-an-occurrence)
4. [Stages and gates](#stages-and-gates)
5. [Statements](#statements)
6. [Triggers](#triggers)
7. [Rounds at one time](#rounds-at-one-time)
8. [Occurrences](#occurrences)
9. [History of an event](#history-of-an-event)
10. [A finished occurrence](#a-finished-occurrence)
11. [Limits of a run](#limits-of-a-run)
12. [Assertions](#assertions)
13. [Breakpoints, checkpoints and edits](#breakpoints-checkpoints-and-edits)

## Declare an event

An event is a value of an entity or a template: `name = event(parameters):`, with its body under
it.

```scn
tank:
    delivered: L = 0
    record_delivery = event(amount: L):
        after 0 h:
            this.delivered += amount
```

The body of an event holds these lines, in this order of kinds:

1. Its text (its card) and its evidence.
2. Its locals and its flows. They stand before the first timing step.
3. Its triggers (`when C:`). A trigger can stand among the locals or among the steps.
4. Its timing steps, in written order: stages (`after D:`, `after D when C:`), waits (`after D`) and
   gates (`until C`).

- An event belongs to an entity or a template, never to the top level or to another event.
- An event is read-only by default. `readonly refill = event(...)` means the same.
- An event has no `input` and no `status` display. A field of its own progress is a local:
  `status: enum[WEIGHING, ADDED] = WEIGHING`.
- An event with a stage or a trigger needs a `record` ([evidence.md](evidence.md#the-evidence-rule)).

### Parameters

Each parameter declares its type: `event(amount: L, setup: h)`. An event with no parameters is
`event()`.

- A parameter has no default value. Each start gives every argument.
- A parameter can have a range: `event(amount: L in [0 L,])`. The engine checks each argument at
  the start.
- A number, a Boolean, an enum or a text parameter is a copy. A statement that assigns it changes
  only the copy of this occurrence. The record keeps the original argument.
- A parameter whose type is a template names a member: `event(source: Tank)`. The event reaches the
  values of the member through it: `source.water`.
- Pass a quantity for an amount, and a member for access to its values. With `amount: L`, a caller
  that passes the 8 L of a tank passes a number. Nothing that the event does to `amount` changes
  the tank. A parameter is never a stock.

## Start an event

`e.start(arguments)` starts one occurrence of the event `e`. It gives no value, so it stands on a
line of its own.

| Where | Example | When the occurrence starts |
| --- | --- | --- |
| A statement of a stage | `this.repair.start()` | When the stage commits |
| The body of a trigger | `this.refill.start(50 g)` | When the trigger fires |
| The top level (the setup scope) | `grinder.refill.start(50 g)` | In round zero, before the first reading at 0 h |

- The engine evaluates the arguments once, at the caller, from the left, when the statement runs.
- The receiver stays the owner of the event. `this` in the occurrence is `grinder`, also when
  another entity starts it.
- A new start makes a new occurrence, also while an earlier occurrence is active. The two
  occurrences share the values of the receiver and have separate parameters, locals, flows and
  stages.
- `.start(...)` gives no handle. Reach the occurrence through `e.occurrences`.

### Start an event on each member

A start on a collection starts one occurrence on each member.

```scn
after 2 h:
    this.machines.repair.start(this.repair_times.draw())
```

- The engine captures the members and evaluates the arguments once, at the caller. Each member gets
  the same values: here, the same duration. For a duration of its own, each member draws inside its
  own occurrence: a `repair = event():` that draws, started by `this.machines.repair.start()`.
- An empty collection still evaluates the arguments and starts no occurrence.
- A skipped branch or a false stage guard skips the start and its arguments.
- The occurrences start in the order of the keys of the collection. Members with equal keys start
  in the order of their creation.

## State of an occurrence

The locals and the flows of an event belong to each occurrence. Declare them at the start of the
event, before its timing steps.

```scn
deliver = event(amount: L, setup: h):
    batch: L = 0 L in [0 L, amount]
    flow delivery: batch -> this.customer.water
        request = formula(this.delivery_request)

    after setup:
        move amount from this.supply to batch

    until batch <= 0 L
```

- Inside the event, a bare name is a parameter or a local of this occurrence. `this.water` is the
  water of the receiver, and `this.customer.water` follows a link.
- A local initializer runs once, in written order, when the occurrence starts. `doubled = amount * 2`
  needs `amount` above it. A plain property of a local flow is also an initializer:
  `request = left / (2 h)` needs `left` above the flow.
- A `formula(...)` local can read a local below it, because the engine evaluates it when it is read.
- A local of a stored number can be a stock: the batch above fills by a `move` and drains by the
  flow.
- A local stock can hold the settings of its endpoints under it: `outflow.capacity = limit`. A plain
  setting reads only the locals above the stock. A `formula(...)` setting can read a local below it.
- A stage declares no names of its own. A value that several statements of a stage need is a
  local, declared at the start of the event and assigned in the stage.
- A local can hold a reference to an occurrence of another event:
  `job = this.repair.occurrences.at(t)`. The engine sets it when its own occurrence starts, and no
  statement assigns it. `job.crew_size` reads that occurrence, also after later starts.
- A formula installed in an entity must not read a local that dies before the entity. Store the
  calculated number instead.

## Stages and gates

An occurrence goes through its timing steps in written order.

```scn
inspect = event(delay: h):
    after delay:
        delay = 2 h

    after delay when this.safe:
        this.inspect_equipment.start()

    until this.clearance_received

    after 0 h:
        this.record_clearance.start()
```

A start with `3 h` runs the first stage at 3 h and the second stage at 5 h. The guard `this.safe`
is read once, at 5 h. A loss of safety before 5 h has no effect on that check.

| Step | What it does |
| --- | --- |
| `after D:` | A **stage**. It runs its statements `D` after the step before it. |
| `after D when C:` | A stage with a guard. When the stage comes due, the engine reads `C` once. If `C` is false, it skips the statements and goes to the next step. |
| `after D` | A wait, with no colon and no statements. |
| `until C` | A gate. If `C` holds, the occurrence goes on at once. Else it waits, with its locals and flows, until `C` holds. |

- The engine captures each delay `D` when it reaches the step. `D` is a finite duration, not below
  zero.
- A delay after a gate is captured when the gate releases.
- `after 0 h:` is a separate stage at the same time. Other work that is due can run before it.
- The first rows under a stage can hold its text and its evidence.
- Timing steps stand at the level of the event, never inside a branch.
- There is no absolute `at T:` step. A trigger on `t >= T` says the same.
- An occurrence runs to its end. There is no interruption, cancellation or join. Stop its later
  work with a guard or a gate.

An occurrence finishes when it passes its last step. It is then `done`, also when a guard skipped
a stage. To record a success, start another event on the path of success:
`this.service_restored.start()`.

## Statements

A stage runs its statements in order. Each statement reads the writes of the statements before it.
The stage commits at its end: its writes, its moves and its starts then take effect together. If a
statement fails, the run stops, and the stage commits nothing.

| Statement | What it does |
| --- | --- |
| `x = v` | Assigns a value |
| `x += v`, `x -= v` | Adds to or takes from a value |
| `e.start(...)` | Starts an occurrence when the stage commits |
| `move a from s to d` | Moves an amount from one stock to another |
| `if C:` and `else:` | Runs one of two bodies |
| `switch E:` | Runs the case of the value of an enum |

### Assign a value

`=`, `+=` and `-=` assign a declared, writable target:

- a stored value, a local, or the copy of a parameter;
- a formula, with another formula and `=` only;
- a distribution, with another distribution and `=` only;
- the `request`, `capacity` or `allocation` of a flow, a leg or an endpoint
  ([flows-and-solvers.md](flows-and-solvers.md#request-capacity-and-actual-rate));
- a writable local of a live occurrence: `this.repair.occurrences.at(t).crew_size = 3`.

| Target | Result |
| --- | --- |
| An input, a link, an event, the ends of a flow | Error: it is fixed for the run |
| A `readonly` value | Error: no statement assigns it. A flow or a `move` can still change a stock. |
| An actual rate, a served fraction, `started`, `done`, `active` | Error: the run calculates it |
| A value that a solver determines | Error: the value has two writers |
| A value of a finished occurrence | The run stops: a finished occurrence is frozen |

On a stock, `=`, `+=` and `-=` are exact. The engine calculates the new balance in exact rational
arithmetic and checks it against the range of the stock. A new balance outside the range by more
than the tolerance of the stock stops the run.

A number assigned to a `request` or a `capacity` replaces a formula. A later stage can give it a
formula again with `=`. After the `=` of an assignment, a bare `in` is an error: write
`ok = (x in [lo, hi])`.

### Move an amount

`move amount from source to destination` moves an amount from one stock to another at once.

```scn
left:
    readonly water: L = 8 in [0,]

right:
    readonly water: L = 0 in [0, 4]

mover:
    shift = event(amount: L):
        after 0 h:
            move amount from left.water to right.water
```

- The engine evaluates the amount once. It is finite and not below zero, in a unit of both stocks.
- The engine checks both new balances against their ranges first. Then it debits and credits the
  exact amount together.
- A move that fails a check moves nothing, and the run stops with the stock and the amount.
- Either end can be `readonly`. A formula or an input is no end.
- A move of a nonzero amount at a stock of a finished occurrence is a write, and the run stops. A
  move of nothing goes on.

`mover.shift.start(3 L)` leaves 5 L and 3 L. `mover.shift.start(5 L)` fails, because the right
stock would hold 5 L, outside `[0, 4]`. The stocks keep 8 L and 0 L.

### Branch with `if`

`if C:` runs its body when `C` holds. An optional `else:` at the level of the `if` runs otherwise.
The stage then goes on after the branch.

```scn
after 0 h:
    if this.passes_test:
        this.operational = true
        this.service_restored.start()
    else:
        this.failed_tests += 1
    this.inspections += 1
```

A branch has one condition. There is no `elif`: write an `if` inside the `else:`.

### Branch with `switch`

`switch E:` evaluates a value of an enum once, runs the case of its member, and goes on after the
branch. An optional `else:` case runs for the other members. With no case and no `else:`, the
stage goes on at once.

```scn
after 2 h:
    switch categorical(FIXED: 0.7, FAILED: 0.3).draw():
        FIXED:
            this.operational = true
        FAILED:
            this.repair.start()
```

- A case is a member of the enum and a colon. The type of the selector gives the enum.
- A case can have a guard: `SEND when this.spares >= 1:`. A case whose guard is false is not
  eligible.
- A case can be empty, with or without its text. The text of a case is its card.
- `else:` is the last case.

**A random outcome.** When the selector is a draw of a `categorical`, the engine reads the guards
first, then draws among the eligible outcomes, with their weights divided by their sum. A median run
takes the most likely eligible outcome, the first declared of them on a tie. With no eligible case,
the `else:` body runs, if there is one, and the engine draws nothing. A sampled run draws `FIXED`
with a probability of 0.7.

**A decision.** Store a value in a field and branch on it. A caller who wants another value stops
the run before the branch and edits the field ([Breakpoints](#breakpoints-checkpoints-and-edits)).

```scn
dispatcher:
    forecast = categorical(SEND: 0, WAIT: 1)

depot:
    spares = 1 in [0,]
    waits = 0
    request_pump = event():
        order: enum[SEND, WAIT] = WAIT
        after 0 h:
            order = dispatcher.forecast.draw()
            switch order:
                SEND when this.spares >= 1:
                    this.send_pump.start()
                WAIT:
                    this.waits += 1
    send_pump = event():
        after 0 h:
            this.spares -= 1
```

The forecast always waits. A caller can stop before the `switch`, edit `order` to `SEND`, and the
send case runs while a spare is there. With no spare, the send case is not eligible for the forecast
or for an edit.

## Triggers

A **trigger** is a `when C:` line in an event. The engine monitors `C`, and the trigger starts its
own event when `C` becomes true.

```scn
refill = event(amount: g):
    status: enum[WEIGHING, ADDED] = WEIGHING

    when this.low_on_beans:
        this.refill.start(50 g)
        reset when this.beans >= 30 g

    after 0.5 h:
        this.beans += amount
        status = ADDED
```

- A trigger belongs to its event on one receiver. It exists for the whole run, also before the
  event first starts. Each grinder has its own trigger, with its own state.
- A trigger has no occurrence. Its condition reads the receiver (`this`), the top level and its own
  captures. It cannot read `amount` or `status`.
- The body of a trigger has, in this order: its captures (`name = value`), one start of its own
  event or more (`this.refill.start(...)`), and an optional reset as its last line.
- A trigger can have its text and its evidence on rows of its body.
- A start by hand (`grinder.refill.start(20 g)`) does not use or reset the trigger. A trigger and a
  start by hand on a grinder at 8 g give two refills: 108 g.

| Reset | When the trigger can fire again |
| --- | --- |
| No reset | After its condition is false |
| `reset when C` | After `C` holds |
| `reset when false` | Never: the trigger fires once in the run |
| `reset after D` | `D` after it fired, while its condition holds. The engine captures `D` at the firing. |

```scn
inspect = event():
    when t >= 3 h:
        this.inspect.start()
        reset after 3 h

    after 0 h:
        this.inspections += 1
```

This clock fires at 3 h, 6 h, 9 h and later while its condition holds. A cooldown measures from
the firing: an alarm that fires at 4 h with `reset after 3 h` is ready again at 7 h.

A capture keeps a value of the firing for the reset:

```scn
plant:
    shift = 1
    water: L = 20 in [0,]
    notes = 0
    note = event():
        when this.shift > 0:
            shift = this.shift
            ready_at = t + 3 h
            this.note.start()
            reset when t >= ready_at and this.water >= 12 L and this.shift != shift
        after 0 h:
            this.notes += 1
```

The captures run in written order, before the start. The reset reads them.

### When the engine reads a condition

| Where | When the engine reads it |
| --- | --- |
| `after D when C:` | Once, when the stage comes due |
| `when C`, `until C`, `reset when C`, on a value that changes at moments | At each committed change, and at the start |
| The same lines, on a value that changes between moments | At the first contact with the boundary, also between scheduled times |

A trigger fires when its condition first becomes true. A tank at 11 L that drains at 1 L/h reaches
`this.water <= 10 L` at 1 h, and the trigger fires then. The same holds for a condition that reads
a rate that a solver publishes.

- A strict comparison (`<`, `>`) on a value that changes between moments has no first instant. The
  run stops with a diagnostic: use an inclusive threshold (`<=`, `>=`).
- A condition whose first contact the engine cannot certify stops the run by name. The engine never
  polls at fixed times.
- When a flow joins or leaves a stock, the engine calculates the time of a contact again. A tank at
  10 L that fills at 1 L/h, with 2 L/h more drained from 2 h to 4 h, reaches 16 L at 10 h, not 6 h.
- A trigger that fires inside the comparison band of its threshold is a near-tie. The trace marks
  it ([numerics.md](numerics.md#near-ties)).

## Rounds at one time

At one time, the engine runs the stages that are due in rounds.

1. The stages due in the round commit one after another. The stage of the occurrence that started
   first goes first. Occurrences that started together go in the order of their `.start` statements.
2. A later stage reads the direct writes of an earlier stage. From 20 g, a stage that sets 8 g and a
   later stage that adds 4 g leave 12 g.
3. After the stages, the engine shares the flows again and settles each solver once, in dependency
   order.
4. The engine reads the triggers, the resets, the gates and the assertions on that settled state.
5. The firings and the released gates make the next round at the same time.

**A rate in a stage.** A stage reads the rates and the solver results of the last re-share,
directly or through a formula.

- The first round at a new time reads the incoming rate at that time.
- Writes, moves, allocations, edits, starts, finishes, bounds and keyed steps reach the rates at the
  re-share after the stages.
- A flow that joins reads zero until the re-share. A flow that leaves keeps its share until the
  re-share.
- A stage after `after 0 h:` reads the new share of the round before it.

For example, a tank can deliver 6 L/h. A clinic asks for 4 L/h and a garden for 2 L/h. At 2 h a
stage raises the request of the garden to 6 L/h and reads the rate of the clinic: 4 L/h. A stage
`after 0 h:` later reads 2.4 L/h, the share of the clinic in the ratio 4 to 6. The record gives
2.4 L/h from 2 h.

- A delay that reads a result waits for the re-share.
- Setup has no rate or result to read. A read of one at setup stops the run by name.

**The horizon.** The horizon is an inclusive cutoff. The engine settles the work due at the
horizon, then records the committed state, also the quantities in occurrences that have not
finished. The end of the run makes no completion.

## Occurrences

`e.occurrences` is the collection of every occurrence of the event `e`, active or finished. Its key
is the start time.

| Field | Type | What it gives |
| --- | --- | --- |
| `started` | A time | The start time of the occurrence |
| `active` | A Boolean | Whether the occurrence runs now |
| `done` | A Boolean | Whether the occurrence finished at its last step |
| A parameter, a local, a flow | As declared | The value of this occurrence |

| Question | Expression |
| --- | --- |
| How many refills started? | `count(grinder.refill.occurrences)` |
| How many refills finished? | `count(grinder.refill.occurrences.done)` |
| Does a refill run now? | `any(grinder.refill.occurrences.active)` |
| What does the newest refill report? | `grinder.refill.occurrences.at(t).status` |
| How long since the latest start? | `since(grinder.refill)` |

- `.at(x)` selects the occurrence with the greatest start time at or before `x`. At equal start
  times, the occurrence that the engine created later wins.
- A lookup fails before the first start. Guard it: `count(grinder.refill.occurrences) > 0`.
- An older occurrence can still be active after the newest one finishes.
- A stage can write a writable local of a live occurrence through `.at(...)`. Mark the local
  `readonly` to bar it. No other rule limits who writes it.
- A record names an occurrence by its event and its start number from 0: `tank.deliver#0` is the
  first start. Its values have paths such as `tank.deliver#0.pipe.request`. Before the start, such a
  value is unavailable.

## History of an event

| Function | What it gives |
| --- | --- |
| `since(e)` | The time since the latest start of the event `e`. A read before the first start fails. |
| `elapsed(x)` | The time since the value `x` last changed at a commit |

- `elapsed` restarts only when a stage commits a value that differs from the value before the
  stage. A stage that writes a value away and back leaves it running.
- `elapsed` takes a stored value, not an unknown of a solver.
- For a condition that is false before the first start, write
  `count(this.service_restored.occurrences) > 0 and since(this.service_restored) >= 3 h`. `and`
  stops at its first false term, so the read of `since` does not fail.
- The latest start and the latest finish of an event can belong to different occurrences.

## A finished occurrence

A finished occurrence is a stable record of its start. It keeps its identity, its parameters, its
locals and the last result of each of its formulas.

- A formula that read 14 at the finish reads 14 after it, whatever changes later.
- A formula that cannot be evaluated at the finish keeps the reason. The occurrence still finishes.
  A report can show the reason, and a read of the frozen value by the model fails with it.
- A write to a finished occurrence stops the run: an assignment to its value, a `move` of a nonzero
  amount at its stock, or a flow that carries a nonzero rate into or out of its stock. A connected
  flow at a zero rate writes nothing.
- A saved reference to an occurrence keeps naming it after later starts.

**The stocks of an occurrence.** Each stock that an occurrence owns must be empty when the
occurrence finishes, within the conservation tolerance of the stock. The author can wait for it to
drain, `move` the rest to a stock of an entity, or send it to `SINK` through a declared flow. An
occurrence that tries to finish with 8 L in its batch stops the run. The diagnostic names the stock,
the amount, the occurrence and the time.

## Limits of a run

Three limits protect a run against a loop. The configuration of a run can set each one.

| Limit | Default | What it counts |
| --- | ---: | --- |
| `max_occurrences` | 1,000,000 | The starts of one event over the run |
| `max_active` | 100,000 | The occurrences of one event that are active at once |
| `max_rounds` | 1,000 | The rounds at one time |

When a run reaches a limit, the diagnostic names the limit and the event. For `max_active`, it also
names the oldest occurrence that waits and the step at which it waits.

## Assertions

`assert C` states a condition that must hold. It stands at the top level, in an entity or in a
template, with an optional text as its message.

```scn
assert plant.rate <= 5 L/h  @fixture
    "The plant fills slowly."
```

| What the assertion reads | When the engine checks it |
| --- | --- |
| Only inputs and other values fixed for the run | Once, after the engine assembles the inputs |
| A value that changes | After every round, after every moment, and at each contact between moments |

- A stock that leaves its asserted interval between two scheduled times fails the run at the time
  that it leaves.
- A tolerance is a closed interval: `assert hours + used in [total - 0.001 work_h, total + 0.001 work_h]`.
- An assertion reads values inside their comparison band as equal ([numerics.md](numerics.md)).
- An assertion makes no draw.
- Between moments, the engine watches an assertion as it watches a trigger. A strict comparison is
  valid in an assertion, because the first instant at which it fails exists.
- An assertion needs a `record` ([evidence.md](evidence.md#the-evidence-rule)).

## Breakpoints, checkpoints and edits

A caller can stop a run at a place of the compiled program, look at its state, change values, and
go on. The model needs no line for this. `napkin play` does it on the command line
([cli.md](../cli.md)), and `napkin.Session` does it in Python ([python-api.md](../python-api.md)).

### Breakpoints

A **breakpoint** is a place where a run stops. It names a part of the program by its origin:

| Origin | Where the run stops |
| --- | --- |
| `depot.request_pump` | Before the first step of each occurrence of the event |
| `depot.request_pump.step[0]` | Before the stage `step[0]`, the first timing step |
| `depot.request_pump.step[0].do[1]` | Before the second statement of that stage |
| `...do[1].then[0]`, `...do[1].else[0]` | Before a statement of a branch of an `if` |
| `...do[1].SEND.do[0]`, `...do[1].else[0]` | Before a statement of a case of a `switch` |
| `setup[0]` | Before the first start of the setup scope |

A breakpoint holds for every occurrence, or for one member or one occurrence:
`operator.decide.step[0]@operator`, or `depot.request_pump#0` for the first occurrence.

A breakpoint alone never changes the run. A run that stops and goes on gives the same values, draws,
event times and event order as the run straight through.

### Checkpoints

A **checkpoint** is the saved state of a run at a breakpoint. It holds:

- why and where the run stopped, the member and the occurrence, and what runs next;
- each stored value, input, link and draw, the occurrences and where each waits, and the state of
  each trigger;
- the record so far;
- the program and the engine version that it ran with, and the configuration;
- every edit so far.

A fresh process can load a checkpoint, look at it, edit it and resume it. A checkpoint of another
program or engine version is refused by name.

### Edits

An **edit** at a breakpoint gives a live stored value a new value. It is the action of a caller:
the model has no other channel for a decision.

- An edit names a stored value of a member or of an occurrence, by its path:
  `depot.request_pump#0.order`. It cannot edit a parameter, a built-in field of an occurrence, an
  input, a link or a formula.
- The type and the range of the value still hold. A finished occurrence stays frozen.
- The engine calculates the rates that depend on the value again.
- An edit of a stock is a transfer from or to outside. The record holds, beside the stock, the
  history `external` (`tank.water.external`).
- An edit that lowers a value takes away, for that run, a proof that the value never falls.
- An edit before a statement joins the writes of its stage. An edit before a stage commits at once.
- The trace holds each edit: the time, the breakpoint, the target, and the old and the new value.

This session stops the reservoir example before its `switch` and opens the spillway:

```text
$ napkin play examples/reservoir --break 'operator.decide.step[0].do[1]' --value reservoir.water,reservoir.gate
Stop 1 at 40 h: before operator.decide.step[0].do[1] (switch at examples/reservoir/model.scn:55), in operator.decide#0 of operator.
Next: operator.decide.step[0] of operator.decide#0, from its start.
Drawn in this stage before the stop: operator.decide.step[0].do[0].draw[0] = OPEN.
  reservoir.water   0.7 fraction   edit: a number         Water in the reservoir
  reservoir.gate    CLOSED         edit: CLOSED or OPEN   Spillway
Edit with PATH = VALUE, or: save FILE, go, quit.
> reservoir.gate = OPEN
  reservoir.gate: CLOSED -> OPEN
> go
```
