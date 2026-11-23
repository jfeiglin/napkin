# How to write a model

This guide is for the author of a model. It builds one small model in nine steps, and it checks each
step with the compiler. Then it gives short rules for units, evidence, solvers and checks, and a
checklist.

The [language reference](language/README.md) gives the rules of each line. The words of this guide,
such as **stock**, **run** and **record**, have the meanings that [the terms](language/README.md#terms)
give. The examples and the catalogue show good practice. After this guide, read
[`examples/piano_tuners`](../examples/piano_tuners/model.scn),
[`examples/reservoir`](../examples/reservoir/model.scn) and
[`examples/incident_response_tempo`](../examples/incident_response_tempo/model.scn).

Each command in this guide starts with `napkin`. In a checkout without the installed command, write
`.venv/bin/python -m napkin` in its place. [cli.md](cli.md) gives each command and each flag.

## Contents

1. [Start a model](#1-start-a-model)
2. [Name the question](#2-name-the-question)
3. [Add values](#3-add-values)
4. [Add a flow](#4-add-a-flow)
5. [Add an event with stages](#5-add-an-event-with-stages)
6. [Add a trigger](#6-add-a-trigger)
7. [Declare named runs](#7-declare-named-runs)
8. [Edit a run](#8-edit-a-run)
9. [Read the record](#9-read-the-record)
10. [Give an input a spread](#10-give-an-input-a-spread)
11. [Choose units and scales](#11-choose-units-and-scales)
12. [Cite evidence](#12-cite-evidence)
13. [Write a solver](#13-write-a-solver)
14. [Check a model](#14-check-a-model)
15. [The checklist](#15-the-checklist)

## 1. Start a model

`napkin new DIR` writes two files. `DIR/model.scn` is a model that compiles and runs as written.
`DIR/style.toml` is the picture of the model, which `napkin draw` reads.

1. Write the starter in the folder `clinic`:

   ```console
   $ napkin new clinic
   Wrote clinic/model.scn and its picture, clinic/style.toml.
   It compiles and runs as written: napkin run clinic

   Replace next, in clinic/model.scn:
     - the title, "A new scenario", and the lines summary, horizon and scope under it;
     - the inputs, each with its value, its range and its text: service.rate;
     - the records, which each value cites: guess. Give each value a record of its own.
   After each change, `napkin compile clinic` checks the model (docs/language/README.md describes each line).
   ```

2. Run the starter:

   ```console
   $ napkin run clinic
   A new scenario: a median run to 720 h
                               unit         0 h        720 h
   service.rate                people/day   10         10
   service.waiting             people       1000       700
   service.served              people       0          300
   service.serve.actual_rate   people/h     0.416667   0.416667
   service.serve.request       people/h     0.416667   0.416667
   people_served               people       0          300
   ```

The starter has one entity, `service`. Its flow `serve` moves people from the stock `waiting` to the
stock `served`, at the rate of the input `rate`. The formula `people_served` follows `served`. Each
value cites one `record` declaration, `guess`.

The next steps replace the starter with a model of the water tank of a clinic. Each step gives the
new lines and the output of the compiler.

## 2. Name the question

The scenario line gives the title of the model, its question, its horizon and what it covers.

1. Replace the two comment lines and the scenario line at the top of `clinic/model.scn` with these
   lines:

   ```scn
   scenario "Clinic water in an outage"
       summary "The water main to a clinic breaks. The clinic uses the water in its tank until a crew repairs the
           main. How low does the tank go?"
       horizon 3 days
       scope "One clinic and its water tank."
   ```

2. Write the unit of water in the new file `clinic/units.json`:

   ```json
   {"L": {"dimensions": {"water": 1}, "scale": 1, "description": "One litre of water."}}
   ```

The prelude gives units of time and of people, but no unit of volume (`napkin/std/units.json`). The
engine calculates time in hours, so the compiler converts `3 days` to 72 h.

## 3. Add values

A value has a name, a unit or a type, an initial value and, if necessary, a range. An **input** is a
value that a named run or an edit can set before the run.

1. Replace the entity `service`, the formula `people_served` and the `record` declaration `guess`
   with these lines:

   ```scn
   tank:
       "The water tank of the clinic."
       input start: L = 6000 L in [0 L, 10000 L]
           "Water in the tank when the main breaks"
           @assumption "The guide assumes that the tank is 60% full when the main breaks."
       water: L = this.start in [0 L, 10000 L] scale 10000 L @books
           "Water in the tank"

   clinic:
       "The clinic, which takes its water from the tank."
       input use: L/h = 150 L/h in [0 L/h, 500 L/h]
           "Water that the clinic uses in an hour"
           @assumption "The guide assumes a small clinic that uses 3600 L in a day."

   record books: identity "The model counts each litre of water once, in the place where it is."
   ```

2. In `clinic/style.toml`, replace the `[role]` table with this table, which names the new entity:

   ```toml
   [role]
   clinician = ["clinic"]
   ```

3. Compile the model:

   ```console
   $ napkin compile clinic
   clinic/model.scn: Clinic water in an outage
     run:           median, to 72 h, steps of at most 1 h
     entities:      tank, clinic
     inputs:        tank.start, clinic.use
     stores:        tank.water
     units:         L, L/h
     model hash:    4eed4a686d98c5e518574a4e893deabd6a09bb04460096e8e45f78c8a6d70e7a
   ```

Each part of these lines has one function:

| Part | What it does |
| --- | --- |
| `input start: L = 6000 L` | Declares an input in litres, with its initial value. |
| `in [0 L, 10000 L]` | Gives the range. An edit outside the range is an error. A flow cannot move a stock outside its range. |
| `water: L = this.start` | Declares a value that starts at the input `start` of the same entity (`this`). |
| `scale 10000 L` | Gives the numerical size of the value ([section 11](#11-choose-units-and-scales)). |
| The first text under a line | Gives the label of the value. The reports and the pictures show it. |
| `@assumption "…"` on its own row | Writes a `record` declaration in place: the evidence of this one value. |
| `@books` | Cites the named `record` declaration `books` at the end of the file. |

The compiler checks the unit of each number. If `use` gets `150 L` in place of `150 L/h`, the
compiler gives this error:

```console
clinic/model.scn:17:22: error: use is declared L/h, and its initializer is L [unit]
```

The compiler warns of each value that cites no `record` declaration. Without `@books`, it prints this
warning before the summary:

```console
clinic/model.scn:12: warning: tank.water: a stored value rests on no record: cite one (@name) or write one under it [no_record]
```

A model with warnings still runs. The checks of the catalogue refuse it
([section 14](#14-check-a-model)).

The `[role]` table of `style.toml` says who plays each entity in the picture. No run reads it.
`napkin compile` also checks `style.toml`. If `[role]` names an entity that the model does not have,
the compiler gives an error:

```console
clinic/style.toml: error: role.operator: service is not a template or a thing [style]
```

## 4. Add a flow

A **flow** moves a quantity per hour from one stock to another. Its `request` is the rate that it
asks for, and its `capacity` is its limit. Its `actual_rate` is the rate that it gets.

1. Add these lines to the entity `clinic`, under the input `use`:

   ```scn
       used: L = 0 L in [0,] scale 10000 L @books
           "Water that the clinic used"
       flow draw: tank.water -> this.used @books
           request = formula(this.use)
           capacity = formula(this.use)
   ```

2. Run the model:

   ```console
   $ napkin run clinic
   Clinic water in an outage: a median run to 72 h
                             unit   0 h    72 h
   tank.start                L      6000   6000
   tank.water                L      6000   0
   clinic.use                L/h    150    150
   clinic.used               L      0      6000
   clinic.draw.actual_rate   L/h    150    0
   clinic.draw.request       L/h    150    150
   clinic.draw.capacity      L/h    150    150
   ```

The tank is empty at 40 h, because 6000 L / 150 L/h = 40 h. After that time, the flow gets 0 L/h,
but its request and its capacity stay at 150 L/h. The flow touches `tank.water` and `clinic.used`,
so both are stocks. The engine keeps an exact balance of each stock.

A request is soft, and a capacity is hard. The clinic cannot take more than it asks for, so its
capacity has the same formula as its request. `formula(...)` keeps the calculation, and the engine
calculates it each time that it reads it. A plain expression keeps only its value at 0 h. Step 6
needs a formula, because the request then reads a value that an event changes.

The range `[0,]` has no upper end. It says that `used` cannot go below zero.

## 5. Add an event with stages

An **event** is an activity with stages. Each `after D:` stage runs D hours after the stage before
it. Each start of an event makes one **occurrence**.

1. Add these entities and this start line above the `record` declarations:

   ```scn
   main:
       "The water main that fills the tank."
       input supply: L/h = 400 L/h in [0 L/h, 2000 L/h]
           "Water that the main brings in an hour when it works"
           @assumption "The guide assumes that the main can bring 400 L in an hour."
       state: enum[BROKEN, REPAIRING, WORKING] = BROKEN
           "Water main"
           @assumption "The guide assumes that the main breaks when the run starts."
       flow fill: SOURCE -> tank.water @books
           request = formula(this.supply if this.state == WORKING else 0 L/h)
           capacity = formula(this.supply if this.state == WORKING else 0 L/h)

   crew:
       "The repair crew of the water company."
       input travel: h = 4 h in [0 h, 48 h]
           "Time that the crew takes to reach the main"
           @assumption "The guide assumes a local crew, four hours away."
       input work: h = 20 h in [1 h, 96 h]
           "Time that the crew takes to repair the main"
           @assumption "The guide assumes that the repair takes 20 hours of work."
       repair = event(): @call_out
           "The crew goes to the main and repairs it."
           after this.travel:
               main.state = REPAIRING
           after this.work:
               main.state = WORKING

   crew.repair.start()
   ```

2. Add this `record` declaration at the end of the file:

   ```scn
   record call_out: assumption "The water company sends the crew when the main breaks, at 0 h."
   ```

3. Read the state of the main, its rate and the water in the tank at four times:

   ```console
   $ napkin run clinic --value main.state,main.fill.actual_rate,tank.water --at 0h,4h,24h,72h
   Clinic water in an outage: a median run to 72 h
                           unit   0 h      4 h         24 h      72 h
   main.state                     BROKEN   REPAIRING   WORKING   WORKING
   main.fill.actual_rate   L/h    0        0           400       150
   tank.water              L      6000     5400        2400      10000
   ```

These are the parts of the event:

- `state: enum[BROKEN, REPAIRING, WORKING] = BROKEN` is an enum value. A bare member, such as
  `WORKING`, takes its enum from its place.
- The flow `fill` comes from `SOURCE`, which is outside the model. Its request and its capacity read
  `state`.
- The line `crew.repair.start()` at the top level starts one occurrence of `repair` at 0 h.
- The first stage runs at 4 h, after `travel`. The second stage runs 20 h later, at 24 h, after
  `work`.
- The event cites `@call_out`. An event with a stage needs a `record` declaration, as an input does.

At 72 h the tank is full. Its upper bound then limits the main to 150 L/h, the room that the clinic
makes.

## 6. Add a trigger

A **trigger** is a `when` condition that the engine monitors. When the condition becomes true, the
body of the trigger runs, and it starts the event.

1. Replace the entity `clinic` with these lines:

   ```scn
   clinic:
       "The clinic, which takes its water from the tank."
       input use: L/h = 150 L/h in [0 L/h, 500 L/h]
           "Water that the clinic uses in an hour"
           @assumption "The guide assumes a small clinic that uses 3600 L in a day."
       input reserve: L = 3000 L in [0 L, 10000 L]
           "Water in the tank at which the clinic starts to save water"
           @assumption "The guide assumes that the clinic saves water below 20 hours of its usual use."
       input cut = 0.5 in [0, 1]
           "Share of its usual use that the clinic keeps when it saves water"
           @assumption "The guide assumes that the clinic can halve its use for some hours."
       saving: bool = false
           "The clinic saves water"
           @assumption "The clinic uses its usual amount of water when the main breaks."
       used: L = 0 L in [0,] scale 10000 L @books
           "Water that the clinic used"
       flow draw: tank.water -> this.used @books
           request = formula(this.use * this.cut if this.saving else this.use)
           capacity = formula(this.use * this.cut if this.saving else this.use)
       save = event(): @water_plan
           "The tank reaches the reserve. The clinic saves water until the main works again."
           when tank.water <= this.reserve:
               this.save.start()
           after 0 h:
               this.saving = true
           until main.state == WORKING
           after 0 h:
               this.saving = false
   ```

2. Add this `record` declaration at the end of the file:

   ```scn
   record water_plan: assumption "The clinic has a plan to save water when its tank is low."
   ```

3. Read the rate of the clinic and the water at four times:

   ```console
   $ napkin run clinic --value clinic.saving,clinic.draw.actual_rate,tank.water --at 0h,20h,24h,72h
   Clinic water in an outage: a median run to 72 h
                             unit   0 h     20 h   24 h    72 h
   clinic.saving                    false   true   false   false
   clinic.draw.actual_rate   L/h    150     75     150     150
   tank.water                L      6000    3000   2700    10000
   ```

These are the parts of the trigger and of the event:

- `when tank.water <= this.reserve:` reads a stock that moves between moments. The engine finds the
  time at which the tank reaches 3000 L. That time is 20 h, because 6000 L − 150 L/h × 20 h =
  3000 L. The engine does not sample the condition at fixed times.
- The trigger has no `reset` line. So its condition must become false before the trigger can start
  the event again. `reset when false` permits one start in a run.
- `until main.state == WORKING` is a gate. The occurrence waits at the gate until the condition holds.
- The request reads `saving`, so it is 75 L/h from 20 h to 24 h. At 24 h the tank holds 2700 L,
  because 3000 L − 75 L/h × 4 h = 2700 L.

Use `<=` or `>=` in a trigger on a value that moves. A moving value has no first time at which it is
strictly below a threshold. If the trigger is `tank.water < this.reserve`, the run stops:

```console
clinic/model.scn: error: the run failed at 0 h: a strict threshold on a value that changes continuously: tank.water < clinic.reserve has no first instant; use an inclusive threshold [run]
```

## 7. Declare named runs

A **named run** is a run that the model declares under `runs:`. Each named run takes options, and each
option sets inputs.

1. Add these lines above the `record` declarations:

   ```scn
   options "Repair crew":
       "Local crew":
           crew.travel = 4 h @crews
       "Regional crew":
           crew.travel = 16 h @crews

   runs:
       local = "Local crew"
       regional = "Regional crew"
   ```

2. Add this `record` declaration at the end of the file:

   ```scn
   record crews: assumption "The guide assumes a local crew 4 hours away, and a regional crew 16 hours away."
   ```

3. Compile the model, and find the named runs in the summary:

   ```console
   $ napkin compile clinic
   clinic/model.scn: Clinic water in an outage
     run:           median, to 72 h, steps of at most 1 h
     named runs:    local, regional
     entities:      tank, clinic, main, crew
     inputs:        tank.start, clinic.use, clinic.reserve, clinic.cut, main.supply, crew.travel, crew.work
     stores:        tank.water, clinic.saving, clinic.used, main.state
     flows:         clinic.draw: tank.water -> clinic.used, main.fill: SOURCE -> tank.water
     units:         L, L/h, h
     model hash:    1a63c1f39b3dd9ffaea7a83cf2726e7378aab0f2e705fdd352f25e0700688cea
   ```

4. Run each named run:

   ```console
   $ napkin run clinic --run local --value main.state,clinic.saving,tank.water --at 0h,20h,24h,36h,72h
   Clinic water in an outage: the run local, a median run to 72 h
                   unit   0 h      20 h        24 h      36 h      72 h
   main.state             BROKEN   REPAIRING   WORKING   WORKING   WORKING
   clinic.saving          false    true        false     false     false
   tank.water      L      6000     3000        2700      5700      10000
   $ napkin run clinic --run regional --value main.state,clinic.saving,tank.water --at 0h,20h,24h,36h,72h
   Clinic water in an outage: the run regional, a median run to 72 h
                   unit   0 h      20 h        24 h        36 h      72 h
   main.state             BROKEN   REPAIRING   REPAIRING   WORKING   WORKING
   clinic.saving          false    true        true        false     false
   tank.water      L      6000     3000        2700        1800      10000
   ```

These are the rules of options and named runs:

- An option sets an input by its full path, with a constant and a `record` declaration. A setting
  without a `record` declaration is an error.
- A named run takes at most one option of each group. Two options of one run cannot set one input.
- Without `--run`, `napkin run` calculates the default run: a median run with the values of the model.
- An unknown name is an error:
  `napkin run: error: --run nowhere: no run of the model; its runs are local and regional`.

With the regional crew, the main works again at 36 h. The tank then holds 1800 L.

A named run changes inputs only. A **variant** changes the model itself, for one place or case.
`napkin new DIR --variants east,west` writes a package with two variants
([the language reference](language/README.md#variants-and-changes)).

## 8. Edit a run

An **edit** changes an input before the run, or a value at a breakpoint.

### An edit before the run

An edit document is a JSON file that sets inputs. Its shape is `napkin/schema/edits.schema.json`.

1. Find the model hash on the last line of `napkin compile clinic` (step 7).
2. Write the edit document `clinic-edits.json`:

   ```json
   {
     "schema_version": "0.0.1",
     "model_hash": "1a63c1f39b3dd9ffaea7a83cf2726e7378aab0f2e705fdd352f25e0700688cea",
     "reason": "The regional crew needs 30 hours for the repair.",
     "runs": {"regional": {"crew.work": "30 h"}}
   }
   ```

3. Run the named run with the edit document:

   ```console
   $ napkin run clinic --run regional --edits clinic-edits.json --value main.state,clinic.saving,tank.water --at 0h,36h,46h,72h
   Clinic water in an outage: the run regional, a median run to 72 h, with the edits of clinic-edits.json
                   unit   0 h      36 h        46 h      72 h
   main.state             BROKEN   REPAIRING   WORKING   WORKING
   clinic.saving          false    true        false     false
   tank.water      L      6000     1800        1050      7550
   ```

These are the rules of an edit document:

- `set` edits every run, `options` edits the runs that take an option, and `runs` edits one named
  run. The narrowest edit wins.
- An edit follows the type of its input. A JSON number is in the unit of the input. A text can give
  a number with its unit (`"30 h"`) or a member of an enum. A Boolean input takes `true` or `false`.
  An input that holds a distribution takes a distribution (`"pert(48 h, 96 h, 200 h)"`).
- The compiler checks the whole document before any run. An edit outside the range of its input is
  an error:

  ```console
  bad-edits.json: error: runs/regional/crew.work: 300 h is above the range of work [range]
  ```

- The document names one model hash. After a change of the model, the compiler refuses the document
  ([section 14](#14-check-a-model)).

### An edit at a breakpoint

`napkin play` stops the run before an event, a stage or a statement. At the stop, `PATH = VALUE`
edits a stored value. `go` continues the run, and `quit` stops it.

1. Stop before the first stage of `clinic.save`, and add 1000 L to the tank, for example from a water
   truck:

   ```console
   $ napkin play clinic --run regional --break 'clinic.save.step[0]' --value tank.water,clinic.saving
   Clinic water in an outage: the run regional, a median run to 72 h

   Stop 1 at 20 h: before clinic.save.step[0] (stage at clinic/model.scn:38), in clinic.save#0 of clinic.
   Next: clinic.save.step[0] of clinic.save#0, from its start.
     tank.water      3000 L   edit: a number        Water in the tank
     clinic.saving   false    edit: true or false   The clinic saves water
   Edit with PATH = VALUE, or: save FILE, go, quit.
   > tank.water = 4000
     tank.water: 3000 L -> 4000 L
   > go

   Stop 2 at 33.3333 h: before clinic.save.step[0] (stage at clinic/model.scn:38), in clinic.save#1 of clinic.
   Next: clinic.save.step[0] of clinic.save#1, from its start.
     tank.water      3000 L   edit: a number        Water in the tank
     clinic.saving   true     edit: true or false   The clinic saves water
   Edit with PATH = VALUE, or: save FILE, go, quit.
   > go

   The run ends at 72 h.
                   unit   0 h     72 h
   tank.water      L      6000    10000
   clinic.saving          false   false
   edit at 20 h, before clinic.save.step[0]: tank.water 3000 L -> 4000 L
   ```

These are the parts of the session:

- `clinic.save.step[0]` is the path of the first stage of `save`. `clinic.save#0` is the first
  occurrence of `save`.
- The edit puts the tank above the reserve. The tank falls to the reserve again at 33.3333 h, so the
  trigger starts a second occurrence, `clinic.save#1`.
- The engine records an edit of a stock as a transfer from outside the model, so the balance of the
  stock stays exact.
- At a stop, `save FILE` writes a checkpoint. `napkin play clinic --from FILE` continues the run from
  it, in the same process or in a new one.

An input is fixed for the run. At a stop, an edit of an input is an error:

```console
> clinic.use = 200
  error: clinic.use: an edit changes a stored value, and this is a value of kind input
```

## 9. Read the record

A run gives one **record**. `--value` selects the paths to read, and `--at` selects the times.

1. Read four values of the regional run at four times:

   ```console
   $ napkin run clinic --run regional --value tank.water,clinic.used,clinic.save#0.started,clinic.save#0.done --at 0h,20h,36h,72h
   Clinic water in an outage: the run regional, a median run to 72 h
                           unit   0 h           20 h    36 h   72 h
   tank.water              L      6000          3000    1800   10000
   clinic.used             L      0             3000    4200   9600
   clinic.save#0.started   h      unavailable   20      20     20
   clinic.save#0.done             unavailable   false   true   true
   clinic.save#0.started at 0 h: unavailable: clinic.save#0 has not started at 0 h
   clinic.save#0.done at 0 h: unavailable: clinic.save#0 has not started at 0 h
   ```

2. If necessary, give the times in other units of time:

   ```console
   $ napkin run clinic --run regional --value tank.water,clinic.used --at 1day,2days,3days
   Clinic water in an outage: the run regional, a median run to 72 h
                 unit   1 day   2 days   3 days
   tank.water    L      2700    4800     10000
   clinic.used   L      3300    6000     9600
   ```

These are the rules of a reading:

- Each named value has a path that a caller can read. The model has no report block.
- `clinic.save#0.started` is a field of the first occurrence of `save`. Before that occurrence
  starts, the field is unavailable, and the report gives the reason.
- Without `--value`, the report gives each named value. Without `--at`, it gives 0 h and the horizon.
- A time after the horizon is an error: `napkin run: error: --at 4days: the run goes from 0 h to 72 h`.
- `--json` gives one JSON document, with the unit, the label and the evidence of each value.
- `--lag PATH=FROM..TO` gives a reporting lag of a value that never falls ([cli.md](cli.md)).

This is the model of steps 2 to 7:

```scn
scenario "Clinic water in an outage"
    summary "The water main to a clinic breaks. The clinic uses the water in its tank until a crew repairs the
        main. How low does the tank go?"
    horizon 3 days
    scope "One clinic and its water tank."

tank:
    "The water tank of the clinic."
    input start: L = 6000 L in [0 L, 10000 L]
        "Water in the tank when the main breaks"
        @assumption "The guide assumes that the tank is 60% full when the main breaks."
    water: L = this.start in [0 L, 10000 L] scale 10000 L @books
        "Water in the tank"

clinic:
    "The clinic, which takes its water from the tank."
    input use: L/h = 150 L/h in [0 L/h, 500 L/h]
        "Water that the clinic uses in an hour"
        @assumption "The guide assumes a small clinic that uses 3600 L in a day."
    input reserve: L = 3000 L in [0 L, 10000 L]
        "Water in the tank at which the clinic starts to save water"
        @assumption "The guide assumes that the clinic saves water below 20 hours of its usual use."
    input cut = 0.5 in [0, 1]
        "Share of its usual use that the clinic keeps when it saves water"
        @assumption "The guide assumes that the clinic can halve its use for some hours."
    saving: bool = false
        "The clinic saves water"
        @assumption "The clinic uses its usual amount of water when the main breaks."
    used: L = 0 L in [0,] scale 10000 L @books
        "Water that the clinic used"
    flow draw: tank.water -> this.used @books
        request = formula(this.use * this.cut if this.saving else this.use)
        capacity = formula(this.use * this.cut if this.saving else this.use)
    save = event(): @water_plan
        "The tank reaches the reserve. The clinic saves water until the main works again."
        when tank.water <= this.reserve:
            this.save.start()
        after 0 h:
            this.saving = true
        until main.state == WORKING
        after 0 h:
            this.saving = false

main:
    "The water main that fills the tank."
    input supply: L/h = 400 L/h in [0 L/h, 2000 L/h]
        "Water that the main brings in an hour when it works"
        @assumption "The guide assumes that the main can bring 400 L in an hour."
    state: enum[BROKEN, REPAIRING, WORKING] = BROKEN
        "Water main"
        @assumption "The guide assumes that the main breaks when the run starts."
    flow fill: SOURCE -> tank.water @books
        request = formula(this.supply if this.state == WORKING else 0 L/h)
        capacity = formula(this.supply if this.state == WORKING else 0 L/h)

crew:
    "The repair crew of the water company."
    input travel: h = 4 h in [0 h, 48 h]
        "Time that the crew takes to reach the main"
        @assumption "The guide assumes a local crew, four hours away."
    input work: h = 20 h in [1 h, 96 h]
        "Time that the crew takes to repair the main"
        @assumption "The guide assumes that the repair takes 20 hours of work."
    repair = event(): @call_out
        "The crew goes to the main and repairs it."
        after this.travel:
            main.state = REPAIRING
        after this.work:
            main.state = WORKING

crew.repair.start()

options "Repair crew":
    "Local crew":
        crew.travel = 4 h @crews
    "Regional crew":
        crew.travel = 16 h @crews

runs:
    local = "Local crew"
    regional = "Regional crew"

record books: identity "The model counts each litre of water once, in the place where it is."
record call_out: assumption "The water company sends the crew when the main breaks, at 0 h."
record water_plan: assumption "The clinic has a plan to save water when its tank is low."
record crews: assumption "The guide assumes a local crew 4 hours away, and a regional crew 16 hours away."
```

## 10. Give an input a spread

A distribution gives an input a spread of numbers. `.draw()` takes one number from the distribution
in each run.

1. Replace the input `work` of the entity `crew` with these lines:

   ```scn
       input work: h = pert(12, 20, 48).draw() in [1 h, 96 h]
           "Time that the crew takes to repair the main"
           @assumption "The guide assumes 12 to 48 hours of work, and 20 hours as the most likely time."
   ```

2. Sample the regional run 200 times, and read the water at 40 h:

   ```console
   $ napkin sample clinic --run regional --value tank.water --at 40h --samples 200 --exceed tank.water=1500
   Clinic water in an outage: the run regional, 200 samples from the seed 0, at 40 h
                unit   central   mean      p5     p25    p50       p75       p95
   tank.water   L      1969.91   2449.08   1500   1500   1703.83   3378.54   4525.34
   tank.water: moved most by crew.work.draw[0] of crew (-0.95)
   P(tank.water > 1500) = 111/200 = 0.555 (95% from 0.483246 to 0.625099)
   ```

These are the rules of a distribution:

- The draw is the whole initializer, so the numbers of `pert(12, 20, 48)` take the unit of `work`.
- A median run takes the median of the distribution. `napkin run` gives 22.5541 h for `work`.
- The range of the input must contain the support of the distribution. An edit can give the input
  any number in its range.
- The `central` column is the median run. The other columns describe the 200 samples.
- A spread that the model chooses is an assumption, not a measured distribution. Its `record`
  declaration says so.

[values-and-types.md](language/values-and-types.md) gives each family of distributions. The rest of
this guide uses the model of step 9, in which `work` is 20 h.

## 11. Choose units and scales

Follow these rules for units:

- Give each kind of quantity its own dimension in `units.json`. This model has `water`, and
  `examples/piano_tuners` has `tunings` and `tuners`. The compiler then refuses to add litres to
  people.
- Write a compound unit with `*` and `/`: `L/h`, or `tunings/(tuner * year)`. A compound unit needs no
  entry. Put a product below the line in brackets.
- Write each number in the unit of its source, and let the compiler convert it. For example,
  `150 L/day` in an `L/h` value is 6.25 L/h. Do not convert a number by hand.
- Give money a unit that holds its price year, such as `USD2025` in `scenarios/library/vocabulary.json`.
  The compiler then refuses to add the dollars of two years.
- Put the units that several packages share in a library. The main file names the library with
  `library "../library"`, and its `vocabulary.json` holds the units.

Give each stock a `scale` near the largest value that it can reach, for example its upper bound. The
scale has these effects:

| Item | Effect |
| --- | --- |
| A value without `scale` | Its scale is one of its declared unit, for example 1 L. |
| The comparison band | Two numbers compare equal when they differ by no more than 1e-9 × max(scale, \|a\|, \|b\|). |
| The integration | The absolute tolerance of a stock is 1e-10 × its scale. |
| A number written in the model | It is exact, and it adds nothing to the comparison band. |

A scale is not a bound: a stock can go above its scale. A scale that is too small asks the
integration for more accuracy near zero than the model needs. A scale that is too large makes the
comparisons near zero coarse. With `scale 10000 L`, the comparison band of `tank.water` near 0 L is
1e-5 L.

A scale changes only these three things:

- the result of a comparison inside the comparison band;
- the accuracy of the integration;
- the choice among equal answers of a solver, for unknowns that are not flows.

A change of the units of display changes nothing. [numerics.md](language/numerics.md) gives the
rules.

## 12. Cite evidence

Each of these parts cites a `record` declaration:

- an input that is not a text, and a stored value;
- an event with a stage or a trigger;
- a case of a status display, and an assertion;
- a value that an instance gives itself, and a column of a table.

A part without a `record` declaration gives the warning `no_record`. A setting of an option or of a
`change` without a `record` declaration is an error. A formula, a link, an enum member and a text
need no `record` declaration.

Write a `record` declaration in one of two forms:

- In place: `@kind "explanation"` on its own row, under the line. Use this form for one line.
- Named: `@name` on the line, and `record name: kind "explanation"` at the end of the file. Use this
  form for several lines. The name is unique in the model.

The kind says who chose the number:

| Kind | Use it when |
| --- | --- |
| `source` | A source reports the number for this case. List its claims under `claims:`. |
| `source_transfer` | A source reports the number for another case, and the model applies it here. |
| `assumption` | The model assumes the number, and the explanation says why. |
| `identity` | The number is true by definition or by counting. |
| `convention` | The number follows a convention of the library. |

A claim with `datum: key` ties a value to one number of the claim. The heat-wave model shows the
pattern:

```scn
    input heat_death_threshold = 34 degC in [25 degC, 40 degC] @heat_curve_limits
        "Heat-related death curve: threshold"
        @source "Heat-related deaths in Phoenix rise above 34 °C (Petitti et al. 2016)."
            claims:
                E-GRONLUND26-S1-PHX
                    datum: petitti_heat_deaths_threshold
```

- The datum of the claim must be equal to 34 degC after the conversion of units. If the two numbers
  differ, the compiler gives the warning `datum` with both numbers.
- A value that only the run calculates, such as a draw, cannot be equal to a datum. The compiler
  gives the warning `datum` for it too.
- The range cites a second, named `record` declaration, `heat_curve_limits`. It says that the limits
  are a choice for a reader to explore, not a measured interval.

The claims, the sources and the assumptions with an ID are in the folder `evidence/` of the package
(`claims.json`, `sources.json`, `assumptions.json`), or in the library. In the catalogue,
`tools.evidence.integrate` is the only writer of claims and sources
([the evidence guide](../scenarios/docs/evidence/README.md)). [evidence.md](language/evidence.md)
gives the rules.

## 13. Write a solver

Use the local rule of an endpoint first. Write a solver only for a decision that no endpoint can make
alone.

### Local allocation

An endpoint shares its limit among its own flows. In the package `share` below, the tank has one
outlet of 300 L/h. The clinic and the homes each request 200 L/h, and the clinic comes first:

```scn
scenario "One tank for two users"
    summary "A clinic and a row of homes take water from one tank through one outlet. The clinic comes first."
    horizon 1 day
    scope "One tank, one clinic and the homes near it."

tank:
    "The water tank."
    water: L = 4000 L in [0 L, 10000 L] scale 10000 L @books
        "Water in the tank"
        outflow.capacity = 300 L/h
        outflow.allocation = priority(clinic.draw, homes.draw)

clinic:
    "The clinic."
    used: L = 0 L in [0,] scale 10000 L @books
        "Water that the clinic used"
    flow draw: tank.water -> this.used @books
        request = 200 L/h

homes:
    "The homes near the clinic."
    used: L = 0 L in [0,] scale 10000 L @books
        "Water that the homes used"
    flow draw: tank.water -> this.used @books
        request = 200 L/h

record books: identity "The model counts each litre of water once, in the place where it is."
```

The package uses the `units.json` of step 2. The tank is empty at 13.3333 h:

```console
$ napkin run share --value clinic.draw.actual_rate,homes.draw.actual_rate,tank.water --at 0h,12h,24h
One tank for two users: a median run to 24 h
                          unit   0 h    12 h   24 h
clinic.draw.actual_rate   L/h    200    200    0
homes.draw.actual_rate    L/h    100    100    0
tank.water                L      4000   400    0
```

Without the line `outflow.allocation`, the endpoint uses `proportional()`, and each flow gets
150 L/h. No solver is necessary for either rule.

### A solver for a joint decision

In the package `refill` below, two tanks have their own connections. The main brings at most 500 L/h
for both. No endpoint sees both connections, so the water company owns a solver:

```scn
scenario "Two tanks on one main"
    summary "The water company fills two tanks from one main. The main cannot fill both at their full rates.
        Which tank gets the water?"
    horizon 1 day
    scope "The tanks of one clinic and one school."

clinic:
    "The clinic and its water tank."
    water: L = 2000 L in [0 L, 10000 L] scale 10000 L @books
        "Water in the tank of the clinic"
    flow fill: SOURCE -> this.water @books
        request = 400 L/h
        capacity = 400 L/h

school:
    "The school and its water tank."
    water: L = 2000 L in [0 L, 10000 L] scale 10000 L @books
        "Water in the tank of the school"
    flow fill: SOURCE -> this.water @books
        request = 400 L/h
        capacity = 400 L/h

company:
    "The water company, which runs the main."
    input limit: L/h = 500 L/h in [0 L/h, 2000 L/h]
        "Water that the main brings in an hour"
        @assumption "The guide assumes that the main brings 500 L in an hour."
    refill = solver:
        inputs:
            clinic_fill = clinic.fill
            school_fill = school.fill
            most = this.limit
        solve_for:
            clinic_fill.actual_rate
            school_fill.actual_rate
        constraints:
            clinic_fill.actual_rate + school_fill.actual_rate <= most
        objective:
            minimize(max(0 L/h, clinic_fill.request - clinic_fill.actual_rate))
            minimize(max(0 L/h, school_fill.request - school_fill.actual_rate))

record books: identity "The model counts each litre of water once, in the place where it is."
```

Each fill requests 400 L/h. The clinic comes first, until its tank is full at 20 h:

```console
$ napkin run refill --value clinic.fill.actual_rate,school.fill.actual_rate,clinic.water,school.water --at 0h,12h,20h,24h
Two tanks on one main: a median run to 24 h
                          unit   0 h    12 h   20 h    24 h
clinic.fill.actual_rate   L/h    400    400    0       0
school.fill.actual_rate   L/h    100    100    400     400
clinic.water              L      2000   6800   10000   10000
school.water              L      2000   3200   4000    5600
```

Without the `objective` section, the solver shares fairly, and each fill gets 250 L/h.

Follow these rules for a solver:

- `inputs` names the values and flows that the solver reads, each under a name of its own.
- `solve_for` names each rate or value that the solver sets. A flow that the solver does not name
  keeps the local rule of its endpoints.
- `constraints` holds affine relations with `==`, `<=` and `>=`.
- `objective` ranks the answers. Each line keeps the optimum of the lines above it.
- Each rate has one writer. If two solvers compete for one hard limit, the compiler refuses the
  model. One solver must own the joint decision.
- An objective that minimizes the total shortfall can leave one claim with nothing. Put such an
  objective first only when the total is more important than the coverage.

[flows-and-solvers.md](language/flows-and-solvers.md) gives the rules of the language, and
[engine/solver.md](engine/solver.md) gives how the engine selects an answer.

## 14. Check a model

### The checks of each model

1. Compile the model, and correct each error and each warning.
2. Format the files with `napkin fmt clinic`. `napkin fmt --check clinic` lists the files that it
   would change.
3. Write an assertion for each rule that must hold.
4. Calculate one reading of each named run by hand, and compare it with the record.
5. Draw the model with `napkin draw clinic`, and examine the arrows ([draw.md](draw.md)). An arrow
   that you do not expect shows an error in the model.

This assertion reads two inputs. The engine checks it once, at 0 h:

```scn
assert clinic.reserve < tank.start @water_plan
    "The tank holds more than the reserve when the main breaks."
```

An edit that gives `clinic.reserve` the number 7000 stops the run:

```console
$ napkin run clinic --edits reserve-edits.json --value tank.water
Clinic water in an outage: a median run to 72 h, with the edits of reserve-edits.json
             unit   0 h
tank.water   L      6000
clinic/model.scn: error: the run failed at 0 h: assert[0]: the assertion does not hold [run]
```

The assertion changes the model, so it changes the model hash. The engine now refuses the edit
document of step 8:

```console
$ napkin run clinic --run regional --edits clinic-edits.json --value tank.water
clinic-edits.json: error: the edits are for another revision of the model [model_hash]
```

An assertion that reads a stock is checked after each round and between moments. The heat-wave model
checks that each hour of work is in one place:

```scn
    assert this.untouched + this.remaining + this.completed in [this.required - 1e-05 h, this.required + 1e-05 h] @counts_hour_work
```

### The checks of the catalogue

For a package in `scenarios/`, use the check of the repository:

1. Show the scope and the stages: `python -B -m tools.check --scenario ID --plan`.
2. Do the check: `python -B -m tools.check --scenario ID`.

The check has four stages: lint, the Python tests of the package and the central contracts, the
evidence, and the committed summaries. The evidence stage refuses each warning `no_record` and each
warning `datum`. `python -B -m tools.new NAME` writes the folder of a new package of the catalogue.
[CONTRIBUTING.md](../CONTRIBUTING.md#testing) gives each check.

## 15. The checklist

Confirm each item before you publish a model or a change of a model.

The question and the parts:

1. The scenario line gives the question, the horizon and what the model covers (`scope`).
2. Each entity is a real thing or a real actor, with a name that a reader understands.
3. Each value is on the entity that it describes. Other entities read it there.

The values:

4. Each number has its unit, in the unit of its source.
5. Each input has a label, a range and a `record` declaration. The range includes each number that a
   named run, an edit or a distribution can give.
6. Each stock that cannot go below zero has the range `[0,]` or a lower bound of zero.
7. Each stock has a `scale` near the largest value that it can reach.
8. Each delay and each threshold is an input with its `record` declaration, not a number in a `when`.

The flows, events and triggers:

9. Each flow has a request. A flow that cannot take more than it asks for has the same capacity.
10. A request or a capacity that must follow a changing value is a `formula(...)`.
11. Each trigger on a moving value uses `<=` or `>=`.
12. Each trigger reads only what its entity can know.

The runs and the evidence:

13. Each named run sets inputs through options, and each setting cites a `record` declaration.
14. Each `record` declaration says who chose the number: a source, the model or a definition.
15. A range that a reader can explore cites an assumption that says so.

The checks:

16. `napkin compile` gives no error and no warning. `napkin fmt --check` lists no file.
17. An assertion checks each balance and each rule between inputs.
18. One reading of each named run agrees with a calculation by hand.
