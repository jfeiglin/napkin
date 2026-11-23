# Changes from the old language

This page lists each word and each form of the old language, version 0.0.1, that version 0.2.3
removed or replaced. It says what to write now. It is the only page of the reference that names the
removed forms. The rulings D0 to D17 and the changes 1 to 29 are in
[design/decisions.md](../design/decisions.md).

The compiler refuses most removed forms by name. Its message says what to write now. The last
column gives the code of the refusal, where the compiler has one of its own.

## Contents

1. [Values and declarations](#values-and-declarations)
2. [Units and numbers](#units-and-numbers)
3. [Members, lists and tables](#members-lists-and-tables)
4. [Flows and sharing](#flows-and-sharing)
5. [Events](#events)
6. [Chance, actors and choices](#chance-actors-and-choices)
7. [Checks, outputs and reports](#checks-outputs-and-reports)
8. [Runs and the scenario line](#runs-and-the-scenario-line)
9. [The command line](#the-command-line)
10. [The Python API](#the-python-api)

## Values and declarations

| Old form | What to write now | Code |
| --- | --- | --- |
| `var n: people = 10 people` | `n: people = 10 people`: a stored value ([values-and-types.md](values-and-types.md#declare-a-value)) | `retired` |
| `let k = 2 h` | `k = 2 h`: an ordinary expression captures its value once | `retired` |
| `let f: people = a * b` (a value calculated at each read) | `f = formula(a * b)` ([values-and-types.md](values-and-types.md#formulas)) | `retired` |
| `var s: "a" \| "b" = "a"` (named states) | `s: enum[A, B] = A` | `retired` |
| `s is "a"` | `s == A`. Equality is `==` and inequality is `!=`. | `retired` |
| `input x = 6 h in 1 h to 24 h` | `input x = 6 h in [1 h, 24 h]`. Either end can be empty: `in [0,]`. | `syntax` |
| `size 100 people` | `scale 100 people`: a numerical hint and no bound (D8) | `retired`, `syntax` |
| `none` | Leave the declaration out, and say why in the documentation or the evidence (D4) | `none` |
| A stock and a tally that never go below 0 | Write the range: `in [0,]`. A quantity with no range has no bound (D8). | |
| A tally by mark | A tally is a stock that nothing drains. It has no mark (change 14). | |

`none` and `is` stay reserved words. No value can take either name.

## Units and numbers

| Old form | What to write now | Code |
| --- | --- | --- |
| `person-years` | `person * year` (D12) | `unit` |
| `L/h^2` | `L/h/h`. A value is raised with `a ** b`. | `unit` |
| `48 h / 2` and `48 h/2` with two meanings | Both are `24 h`. No unit is named `h/2` (D12). | |
| `48h` (no space) | `48 h`. A unit follows its number after one space. | `unit` |
| A unit with a text parameter (`{...}`) | A value has one dimension in every instance of its template | `retired` |
| `assert a + b is T within 0.01 L` | `assert a + b in [T - 0.01 L, T + 0.01 L]` | `retired` |

## Members, lists and tables

| Old form | What to write now | Code |
| --- | --- | --- |
| A thing `name:` | An entity `name:`. The rules are the same ([values-and-types.md](values-and-types.md#members-templates-and-instances)). | |
| `name: Template * k` (copies `name.1` to `name.k`, which read `copy`) | Write each instance (`north: Pump`), or give the rows in a table | `retired` |
| The rows of a table as `name.1` to `name.k` | A table with an `id` column names its rows `name.id`. Rows without ids have no names. | |
| A column `title` of a table | A `title` line under an entity, a template, an instance or a `change` | |
| `let zones = [near, middle]` | `zones = <near, middle>`: a collection literal | `retired` |
| `let region: Region` (a slot) | `region: Region`: a link | `retired` |
| `let regions: [Region]` | `regions: <Region>` | `retired` |
| The name of a template as the list of its instances: `sum(Zone.population)` | `sum(Zone.instances.population)` | `unknown_name` |
| `count(zones.flag)` and `any(zones.flag)` | The same, over a collection: `count(Zone.instances.flag)` | |
| `min(zones.x, 2 h)`, where the scalar takes part | `min(min(Zone.instances.x), 2 h)`. A reduction takes one projection. | `type` |
| `min` and `max` of no members with another argument | `min` and `max` of an empty collection fail when the run reads them (D4) | |
| A line `zones.e` that fires the event `e` of each member | `this.zones.e.start()` in a stage ([events.md](events.md#start-an-event-on-each-member)) | |
| `role R` under a thing, an event or an outcome | Who plays a part belongs to the wrapper of the scenario: `roles.toml`. The picture takes it from `[role]` in `style.toml` (changes 19 and 23). | `role` |

## Flows and sharing

| Old form | What to write now | Code |
| --- | --- | --- |
| `flow drain: tank -> basin at 10 L/h while valve is "open"` | `flow drain: this.tank -> this.basin` with `request` and `capacity` on rows under it, as formulas of the state: `capacity = formula(10 L/h if this.valve == OPEN else 0 L/h)` | |
| `flow fill: -> tally at rate` (an end from outside) | `flow fill: SOURCE -> this.tally` | `syntax` |
| `flow use: stock -> at need` (an end out of the model) | `flow use: this.stock -> SINK` | `syntax` |
| `flow together at rate while C:` with pairs under it | A flow with legs: `flow name:` with a `flow leg: a -> b` on each row under it, each with its own request ([flows-and-solvers.md](flows-and-solvers.md#flows-with-legs)) | |
| `share basin limit 3 L/h order pump_a, pump_b` | Under the stock: `outflow.capacity = 3 L/h` and `outflow.allocation = priority(pump_a.drain, pump_b.drain)` | `retired` |
| A `share` that every stock with two outflows needed | Each endpoint shares by its own rule. The default is `proportional()` (change 2). | |
| `x += v` and `x -= v` to add from outside the model or take out of it | The same statements in a stage, or a flow from `SOURCE` or to `SINK`. On a stock, the statement is exact. | |

## Events

| Old form | What to write now | Code |
| --- | --- | --- |
| `event name when C:` | An event with a trigger: `name = event():`, then `when C:` with `this.name.start()` under it, then a stage ([events.md](events.md#triggers)) | |
| `once` | `reset when false` on the trigger | |
| `after D` on the line of the event | A stage `after D:` in the event | |
| `while K` on the line of the event | A guard on the stage, `after D when K:`, or a gate `until C` | |
| `each W` (one firing in each window) | A capture of the value and a reset: `shift = this.shift`, then `reset when this.shift != shift` | |
| `delayed(x, D)` | An event that waits (`after D:`) and then writes (change 12) | `delayed` |
| A line that names an event to trigger it (`notify`, `thing.e`) | `this.notify.start()` in a stage | |
| `event start when t >= 0 h:` | A start of the setup scope at the top level, `plant.begin.start()`, or a trigger on `t >= 0 h` | |
| `count(e)` of an event | `count(e.occurrences)` | `type` |
| `count(e.outcome)`, `since(e.outcome)` | Start another event on the path of that case, and read its occurrences | |
| The lines of an outcome read the state before the outcome | The statements of a stage read the writes before them in the stage | |
| One firing at a time, in the order of the lines of the file | Stages commit in rounds, in the order of their occurrences ([events.md](events.md#rounds-at-one-time)) | |
| A firing that waits, and that a `while` cancels | An occurrence runs to its end. Guard its later stages, or wait with `until`. | |
| `at T:` | A trigger on `t >= T` | `syntax` |

## Chance, actors and choices

| Old form | What to write now | Code |
| --- | --- | --- |
| Outcomes with chances, `name 0.7:` and `else` | `switch categorical(A: 0.7, B: 0.3).draw():` with a case for each member (D1) | |
| `chance(A: 0.7, B: 0.3)` | `categorical(A: 0.7, B: 0.3).draw()` in a `switch` | `retired` |
| `name chance when C:` (an outcome that can happen only while `C` holds) | A case with a guard: `A when C:` | |
| Chances that must add up to 1 | Weights that the engine divides by their sum | |
| `beta(...)`, `bernoulli(p)` | The families of the language: `uniform`, `triangular`, `pert`, `loguniform`, `normal`, `lognormal`, `categorical`. A yes-or-no outcome is a `categorical` over an enum. | `syntax` |
| A distribution in an input or a `let`, drawn when the thing is created | An explicit `.draw()`: `input t = uniform(1 h, 3 h).draw()`. A distribution without `.draw()` is a value of type `distribution(T)` (D2). | |
| `sees x, y` (an actor and what it observes) | Store the value in a field and branch on it. A caller can stop before the branch, show any value and edit the field (change 15). | `sees` |
| `choice` under an event | A field that a branch reads. A caller edits the field at a breakpoint. | `syntax` |
| `actor.choose(d)` | `order = this.forecast.draw()`, then `switch order:` | `choose` |
| Controllers, picks and a play log | Breakpoints, checkpoints and edits ([events.md](events.md#breakpoints-checkpoints-and-edits)) | |
| `role` under an event or a case | `roles.toml`, read by the wrapper of the scenario | `role` |
| `.diff(...)`, the derivative of a formula | Not in this version | `not_in_v1` |

## Checks, outputs and reports

| Old form | What to write now | Code |
| --- | --- | --- |
| `output name: unit = E` | `name = formula(E)` or any named value. A caller selects the paths and the times (D10). | `retired` |
| `output x` under a thing | Nothing: every named value has readings | `retired` |
| `report:` | No report block in the model. A caller selects the paths and the times (D10). | `retired` |
| `about`, `category`, `scope` on an output | The text of the value, and the `scope` of the scenario line | |
| `level`, `signed` | The range of the value: `in [-20, 20]` admits gains and losses | |
| `distinct`, `unestimated "Reason"` | A `record` declaration and the documentation (D10) | |
| `cumulative` and `lag 2 h` on an output | A caller asks for a lag: `napkin run --lag x=2h..6h`. The compiler must prove that the value never falls (D10). | |
| A lag over a window before 0 h, which read 0 | The report gives `Unavailable` there, with the reason (change 22) | |
| `assert initially` | An assertion over the inputs that give the start | `syntax` |
| `assert x is "closed"` that read named states as start values | An assertion over a value that changes holds at every round and moment | `retired` |
| The `Partition` checks | Ordinary assertions (D16) | |
| A value without evidence, refused | A warning `no_record`. A model under exploration still runs (change 16). | |
| An option that set a number with no evidence, which was valid | An error with the code `record` (change 16) | |

## Runs and the scenario line

| Old form | What to write now | Code |
| --- | --- | --- |
| `shut = "Shut the plant" versus manual` | `shut = "Shut the plant"`. A comparison runs the engine twice and compares the records (D9). | `retired`, `syntax` |
| `timescales` on the scenario line | Nothing. The engine chooses its own steps, and a run that needs finer ones sets `max_step` (change 19). | `retired` |
| A run that a person or an agent plays | One run gives one trajectory. A caller stops it at a breakpoint and edits it. | |

## The command line

| Old flag | What to use now |
| --- | --- |
| `--variant NAME` | Give the folder of the variant, or its `model.scn`, as the model: `napkin run scenarios/x/variants/east` |
| `--set NAME=VALUE` | An edit document with `--edits FILE`. Its level `set` edits every run. |
| `--option [GROUP=]OPTION` | A named run under `runs:` that takes the option. In Python, `Compiled.configure(run, edits, options)` selects options. |
| `--control THING` | `napkin play --break AT[@OWNER]`, and an edit at each stop |
| `--picks FILE` | `napkin play --from FILE`, which goes on from a stop that `save FILE` wrote |
| `--events` | No flag. The trace of the record holds each start, finish, firing and draw (`napkin.run(...).trace` in Python). |

The commands and their arguments are in [cli.md](../cli.md).

## The Python API

| Old name | What to use now |
| --- | --- |
| `evaluate_study(model, ...)` | `napkin.study` for the named runs of a model, and `napkin.monte_carlo` for the samples of one run |
| `sample_result(study, ...)` | `napkin.report` for the readings of one run, and the summaries that `napkin.monte_carlo` gives |
| `actors(model)` | Nothing. The view of actors left with the player machinery (change 15). `napkin.instances` stays. |
| `Model.resolve(run, values)` | `napkin.load_scenario(path, run=..., edits=...)`, and the `configure` method of the compiled model |
| `engine/runtime.py` | `napkin.run(program, configuration)` |

The public names are in [python-api.md](../python-api.md).
