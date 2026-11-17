# How to model with napkin

This guide is for anyone who builds a model with napkin, on any subject. [language.md](language.md)
is the contract of each line. This guide is about the choices that the contract leaves open: the
parts of a model, the record of each value and the checks. Section 15 is the checklist that every new
model and every change answers.

The catalogue of this repository adds its own conventions for attackers and defenders
([scenarios/docs/conventions.md](../scenarios/docs/conventions.md)).

## Contents

1. [Start a model](#1-start-a-model)
2. [Things](#2-things)
3. [States, stocks and flows](#3-states-stocks-and-flows)
4. [Inputs](#4-inputs)
5. [Events](#5-events)
6. [Actors and what they see](#6-actors-and-what-they-see)
7. [Outputs and checks](#7-outputs-and-checks)
8. [Units](#8-units)
9. [Evidence](#9-evidence)
10. [Texts](#10-texts)
11. [A variant, an option or a run](#11-a-variant-an-option-or-a-run)
12. [The same moment](#12-the-same-moment)
13. [Check a model](#13-check-a-model)
14. [Change a model safely](#14-change-a-model-safely)
15. [The checklist](#15-the-checklist)

## 1. Start a model

`napkin new DIR` writes a model that compiles and runs as written. Then it says what to replace:

```
$ napkin new demo
Wrote demo/model.scn.
It compiles and runs as written: napkin run demo

Replace next, in demo/model.scn:
  - the title, "A new scenario", and the lines summary, horizon and scope under it;
  - the inputs, each with its value, its range and its text: service.rate;
  - the records, which each value cites: guess. Give each value a record of its own.
After each change, `napkin compile demo` checks the model (docs/language.md gives each line).
$ napkin run demo
base
                  at the end (720 h)
  People served   300 people
```

The new file has one thing, `service`. It holds a stock of the people who wait, and a flow that moves
them into a tally of the people served. It also has one output and one assumption record, `guess`,
which every value cites. `napkin new DIR --variants east,west` also writes a variant for each name
(section 11).

Write the model in this order:

1. The question and its outputs: what the model counts, in which unit, and for whom (`scope`).
2. The things: each real thing or actor (section 2).
3. Their states, stocks and flows (section 3), and their inputs (section 4).
4. The events that change the states (section 5), and what each actor sees (section 6).
5. The checks and the outputs (section 7).
6. The options and the runs (section 11).

Give each value its record when you write the value (section 9). After each part, run
`napkin compile`. Each diagnostic gives its file, line and column, and the closest names. For a
mistake in a unit:

```
$ napkin compile demo
demo/model.scn:11:5: error: unknown unit 'people/dy'; did you mean people/day, people/days or people? (service/rate)
```

`napkin fmt` formats the files of a model in place. The examples `examples/piano_tuners` and
`examples/reservoir` are two short models to read next. [cli.md](cli.md) gives every command and
flag.

## 2. Things

- Make one thing for each real thing or actor that has its own state or makes its own decisions:
  the water plant, the repair crews, the people of a district, the operator of a dam.
- Do not make bookkeeping things. A "model" thing that holds inputs, a "readiness" thing that holds
  hidden markers, or a thing that holds only a status, is a sign of a missing real thing. Put each
  part on the thing that it describes.
- Name each thing as a reader would: `repair_crews`, not `restoration_readiness`. A thing's `title`
  names it on the picture; without a title, its name in words does (`repair_crews` reads "Repair
  crews"). Its text describes it.
- Name a thing for the actor or the object, not for its work. The engineers check the plant before
  a restart; "restart checks" is their work, not a thing.
- What a thing holds or knows is a state of that thing, not a thing of its own. The crews know that
  the operators called them: `var called = false` on the crews.
- Make a thing without a template (`name:`) for one thing. Make a template (`Name:`, with a capital
  letter) for several things of one kind, and one instance of it for each thing (`north: District`).
  `name: Template * k` makes k copies, `name.1` to `name.k`.
- Give each instance its own values with lines under it, such as `population = 80000 people  @census`.
  Each new value has a record of its own.
- For many things of one kind whose values come from data, put the data in a table of the package and
  name it on the line of the thing: `zones: Zone from "zones.csv"`. Each row is one instance, and each
  column gives one member, with its unit and its record in the header:
  `population: people @census`. Keep the formulas, the flows and the events in the template; the
  table holds values only ([language.md](language.md), §2.3).
- Make a template of its own for a part that only some things have. Every instance has every flow,
  share and check of its template, and an instance cannot add a member.
- Hide only machinery that has no meaning for a reader, such as the copies that carry parcels between
  two places. To hide it on the picture, name its template, or the thing made without one, in `hide`
  under `[layout]` in `style.toml` ([draw.md](draw.md)).

```text
District:  @district_model
    "The people of one district that the plant supplies."
    role community
    let population = 50000 people  @district_model
        "People in the district"

north: District
    "The people of the northern district."
    title "Northern district"
    population = 80000 people  @census
        "People in the northern district"

south: District
    "The people of the southern district."
```

## 3. States, stocks and flows

- Name each state and each of its values for what a person would see:
  `var pressure: "normal" | "low" = "normal"`.
- Hold each state in one thing. Other things read it there (`plant.pressure`); they do not copy it.
  A state that repeats another thing's state (an echo state) goes.
- A state has no dead value, which it never takes. It also has no zero-length value, which it leaves
  at the moment that it takes it. A step that happens at one moment is an event, not a value of a
  state.
- Define nothing conditionally. An event's `when` says when it happens; the options set the states
  that the world starts in.
- Make each amount that moves a number var, and let flows move it. The compiler finds what each
  number var is from the file (language.md, §2.4):
  - a **stock**, when a flow takes from it: the people who wait, the water in a tank;
  - a **tally**, when flows only fill it: the tunings done, the hours with low pressure;
  - a **number state**, when no flow joins it and only events set it.
- A flow moves its rate per hour while its `while` holds. Write the rate in the unit of the var per
  unit of time, and let the compiler check it. When several flows take from one var, give the var a
  `share` (language.md, §2.5).
- Where items move between stocks and none is made or lost, say so with a check:
  `assert a + b is T within d`.
- Give each stock and tally a size: the high end of its range (`in`), or `size` where it has none. The
  solver reads it.

`examples/piano_tuners` holds a stock and a flow out of it:

```text
    var due: tunings = need size 20000 tunings  @counts
        "Tunings that the pianos still need"
    var done: tunings = 0 tunings size 20000 tunings  @counts
        "Tunings done"
    flow tune: due -> done at rate * staff  @counts
```

## 4. Inputs

- Each input belongs to the thing that it describes: the crews' repair time on the crews, the
  population on the district.
- An input that every instance of a template shares belongs to one thing that they all read, by
  its name or through a link. Then it stays one input.
- Write the label, the first text under a value, as a short noun phrase: "Time that the crews take
  to repair the pump". A label that names one instance only belongs under that instance's line for
  the member: `population:`, with the new text under it.
- Each input has its record, and its range too: write the range on the input's line
  (`in 1 h to 72 h`). Let the record say whether the sources give the limits or the model chooses
  them, and why the model chose the default value. A range that a reader can explore is not a
  measured interval.
- Do not write a fixed time or amount in a `when` (`since(x) >= 2 h`). It is an input that a reader
  cannot see or change, and it has no record. Make it a value, `input` or `let`, with its record.
- A yes/no input has the value `true` or `false`: `input notice = true`. Read it as a condition
  (`notice`, `not notice`), or write `1 if notice else 0` where a number is needed. A yes/no
  condition that changes during a run is a yes/no state: `var called = false`.
- Write each number with its unit, in the unit that the source gives: `input delay: h = 3 days`. The
  compiler converts it to 72 h, so do not convert it by hand.
- Input names (`thing.value`) stay stable: the options, the saved edit documents and the tests name
  them. A rename moves every one of them in the same change.

```text
    input repair_time = 6 h in 1 h to 72 h  @crew_tiers
        "Time that the crews take to repair the pump"
```

### Distributions

Give an input a distribution when its source, or the model, gives a spread and not one value
(language.md, §2.4). A run without samples takes the median; `napkin sample` draws a value for each
sample.

- Choose the family from what the source reports:
  - a lowest, a most likely and a highest value: `pert(min, mode, max)`. Use
    `triangular(min, mode, max)` when the most likely value has no more weight than the values near
    it;
  - a lowest and a highest value only: `uniform(min, max)`, or `loguniform(min, max)` when they are
    orders of magnitude apart;
  - a mean and a standard deviation: `normal(mean, sd, min=, max=)`;
  - a median and a geometric standard deviation, or a spread that grows with the value:
    `lognormal(median, gsd, min=, max=)`;
  - a share from 0 to 1, with its mean and the count behind it: `beta(a, b)`;
  - the chance that a condition holds: `bernoulli(p)`, for a yes/no input;
  - one of several values, each with its weight: `categorical(name=p, …)`, for an input with named
    values.
- Set the bounds of a normal or a lognormal to the limits that the value can take, or to the range
  that the source covers. These bounds lie within the input's range (`in low to high`).
- A distribution has a record, as every value has. Cite a `source` record when the source reports
  the spread: list its claims, and say in the explanation which parameters the source gives. A
  `datum:` names one figure that the value equals, so the record of a distribution names none. Cite
  an `assumption` record for a spread that the model chooses, and say why. A chosen spread is not a
  measured distribution.
- Two values that move together share a cause. Make the cause one input, and let both values read
  it: `median=1.5 * detection_time`. Values drawn alone can give combinations that never occur.
- Shares that add up to 1 are draws divided by their total. Shares drawn alone break a check that
  they add up to 1 in most samples, and such a sample rejects the study.
- Each copy of a set draws its own value. To give every copy the same draw, put the input on one
  thing that the copies read.

```text
    input detection_time: h = pert(1 h, 2 h, 8 h) in 0.5 h to 12 h
        "Time until the operators see the low pressure"
        @assumption "The model chooses a spread of the detection time around two hours. It is not a measured
            distribution. The limits are times that a reader can explore, not a measured interval."
```

## 5. Events

- An event says when and what. `event name once when C:` says when it happens, and the lines under
  it say what changes. Write the event's text as one sentence in the present tense: it names the
  change.
- An event with several outcomes says what can happen when it fires: `name chance:` heads each
  outcome, with its text and its lines under it. A chance is a number or an expression (the model's
  estimate), a condition (1 when it holds) or `else`. The central run takes the likeliest outcome;
  the samples of a study draw them (language.md, §2.6).
- Name each outcome for what happens: `done`, `stopped`, `skipped`, or a word of the case. An
  outcome's name is not a state: a state that a reader should see is a named state that the outcome
  sets.
- A change that several events make is an event with no `when` (`event name:`): a line of another
  event names it (`x.name`), and it fires then, after that event's step. Its text names its change.
- Every event belongs to a thing or a template. The file has no event at the top level.
- The first change of a run can be the event `start` of one thing, `event start when t >= 0 h:`. It
  fires first, at t = 0.
- An event reads the values of its own thing bare, and the values of another thing by its name
  (`plant.pressure`). In a template, read through a link each thing that differs between the
  instances, and let each instance bind it (`let district = north`). Then a second district is one
  more instance, and the template does not change.
- Make each event react to a consequence that its thing can see. The operators react to the low
  pressure that they see, not to the failure of the pump inside the plant.
- Start each clock at the first moment that its thing could know. The crews cannot start a repair
  that no one has asked for. So their clock starts when the operators call them, not at the failure.
- Use one clock for each thing. Time each delay from the event that starts it, `since(x) >= d`, and
  use `elapsed(s) >= d` for "after d hours in this state".
- An event fires each time its condition becomes true. Write `once` for an event that happens one
  time in a run. A repeatable event that watches a crossing of a continuous value sets, in each
  outcome, a named state that its condition reads; another event sets the state back, and the event
  can fire again.
- Do not add guards to a `when` that always hold when the event can happen. An example is "and the
  pump has failed" with a clock that starts at the failure.
- A line of an outcome may change another thing. The picture then shows who changes what, and the
  records of the event say why it can.
- Use `after` only for a step that takes time. When the step can be stopped or found moot while it
  waits, give the event outcomes whose chances are conditions. The engine reads them when the delay
  ends: `done` with the condition under which the step still applies, and `skipped` or `stopped`
  with `else`. An instant step has no `after`, and its condition goes in its `when`.
- A step that did not happen but that a reader expects ("the job never runs") is a milestone: an
  event with a text and no lines.

```text
    # The clock runs from the moment the pressure falls: the operators watch the pressure.
    event find once when plant.pressure is "low" and elapsed(plant.pressure) >= detection_time:  @pressure_alarm
        "The operators see the low pressure and call the crews."
        crews.called = true

    # The repair takes time, and the pump can run again before it ends.
    event repair once after repair_time when called:  @crew_tiers
        done plant.pump is "failed":
            "The crews repair the pump, and the pressure comes back."
            plant.pump = "repaired"
            plant.pressure = "normal"
        skipped else:
            "The pump already runs again, so the crews have nothing to repair."
```

## 6. Actors and what they see

- Each event reads only what its thing could know. The record on its line says how the thing knows
  it: a sensor, a report, a person who sees it.
- An actor says what it observes with `sees` (language.md, §2.7). Its choices, its events with the
  line `choice`, read only what it sees, the time and its own inputs; the compiler rejects any other
  name there. A person can be infected and not know it.
- Read the state of the thing that an event depends on, not the state of the actor that changes it.
  The plant reads whether its release path is isolated (`store.path is "isolated"`), not whether the
  operators have finished. Then a second way to isolate the path needs no change to the plant.
- An event or a flow that reads a state that its thing cannot know is a fault of the model. Fix it:
  the event or the flow reacts to what its thing can see. The same applies to a clock that starts
  before its thing could know, a fixed time in a `when`, and a record that does not say how a thing
  knows.
- Draw the model and read the picture ([draw.md](draw.md)). It shows each thing, and an arrow for
  each kind of link to another thing: what it reads, what it changes and what material it moves. If
  an arrow surprises a reader, the model is wrong.

A choice has the model's chances, so a run that nobody plays takes them. `napkin play` stops at each
choice of the actor that `--control` names, shows what the actor sees and asks for a pick
([engine.md](engine.md#play)):

```
$ napkin play examples/reservoir --control operator
note: checked for run base only; `napkin compile` checks every run

At 40 h, operator decides (operator.decide).
  The water reaches the level at which the operator opens the spillway.
  It sees:
    reservoir.water = 0.7 fraction
  It can pick:
    1.  open: The operator opens the spillway.
    2.  wait: The operator waits, and the spillway stays closed.
Pick 1-2 or a name: wait
Why (optional):
  operator picks wait.

The run base ends at 120 h.
  Water let out over the spillway           0 fraction
  Time with the water above the risk level  40 h
1 pick.
```

## 7. Outputs and checks

- An output gives one result in its unit, with its label, its record and whom it covers (`scope`, or
  the scope of the scenario line). An output is cumulative unless it is a `level`; a cumulative
  output never falls.
- A value that is not estimated is never zero: write `unestimated` with its reason, and no `= E`.
- Every setting that a reader can choose either runs or is rejected by a check that says why: an
  `assert` that reads inputs only, with its message.
- Counts of people that an output adds come from one sum (`assert a + b is T within d`), or the
  output says why they are different people (`distinct` with its record). Without one of them, the
  compiler rejects the sum.
- A `category` is a free tag that the language does not read. Tools that read the reports can use it.
- A `lag` delays a cumulative count as the reports give it, such as deaths that come some days after
  the harm ([engine.md](engine.md)). `napkin run --at` gives every output at other times too.

```text
output people: people = sum(District.population)  @district_model
    "People that the plant supplies"
    level
    distinct  @districts_apart
```

## 8. Units

- Every number has its unit, and every model has the units of the prelude (`napkin/std/units.json`):
  `h`, `hour`, `hours`, `day`, `days`, `week`, `weeks`, `month`, `months`, `year`, `years`,
  `person`, `people`, `fraction`, `ratio` and `percentage_points`. No file declares a prelude name
  again.
- A composed unit needs no entry: `a/b` divides, `a-b` multiplies and binds tighter than `/`, and
  `a^n` is a power. So `tunings/tuner-year` is tunings per tuner per year.
- Declare a unit of your own in the package's `units.json`, with its dimensions and its scale in
  execution units. `examples/piano_tuners` declares two:

  ```json
  {"tunings": {"dimensions": {"tunings": 1}, "scale": 1, "description": "One tuning of one piano."},
   "tuner": {"dimensions": {"tuners": 1}, "scale": 1, "description": "One piano tuner who works full time."}
  }
  ```

- Units that several packages share go in a library: the folder that the main file names with
  `library "PATH"`, whose `vocabulary.json` holds the units and the shared records. The units come
  from the prelude, then the library, then the package's folder, then the variant's folder
  (language.md, §2.12). A unit is declared in one folder only.
- Give each kind of count its own dimension: tunings and tuners, people and visits, an episode and
  the patient who has it. Then the compiler refuses to add them, or to move one into the other.
- Give money a unit whose dimension holds its price year, such as the `USD2025` of this repository's
  library. Then the compiler refuses to add dollars of two years. A value of another year needs a
  conversion to the model's year, with its record.
- Write each number in the unit that its source gives. The compiler converts it to the execution
  units, in which time is in hours, so the reports give `720 h` for 30 days. Do not insert a
  conversion by hand.

## 9. Evidence

Every value of the model cites a record (language.md, §2.10). A record says where the value comes
from, and the reports carry it with each outcome. The compiler rejects a value without its record.
For an input with no record:

```
$ napkin compile demo
demo/model.scn:11:5: error: an input or a fixed value has its record (service/rate)
```

- Choose the kind of the record from the support that the value has:
  - `source`: a source reports the value for this setting, with its claims under `claims:`;
  - `source_transfer`: a source reports it for another setting, and the model applies it here;
  - `assumption`: the model assumes it, and says why;
  - `identity`: it is true by definition or by counting;
  - `convention`: it follows a rule of the project, with the ID of a convention of the library.
- Write a record in place when one line uses it: `@assumption "…"` on its own line under the line.
  Name it when several lines use it: `record counts: identity "…"` at the end of the file, cited as
  `@counts`. A named record has a name that is unique in the model: no record belongs to a template.
- The claims, the sources and the assumptions with an ID live in the folder's `evidence/`
  (`claims.json`, `sources.json`, `assumptions.json`), or in the library. Their shape is
  `napkin/schema/library.schema.json`.
- Each part keeps its own records. The records on an event's line support when it happens; the
  records on an outcome's line support that outcome's chance and its change.
- The record on an event's line says how its thing knows what the `when` reads: a sensor, a report,
  a person who sees it. An `identity` record that only says how the model counts (no item is created
  or lost) does not say this.
- An option's line (`thing.x = v  @record`) carries its own record: a record that supports that
  value. The record of the input's default does not support the values of the other options.
- When two events merge into one, the records of the second move to the line that carries its claim.
  Copy a record word for word when it moves: the evidence index matches records by their content.
- Keep each support explicit. Nothing passes from one declaration to another. A template's records
  do not support an instance's new value, and a thing's records do not support its events. The one
  exception is the instance itself: its template's records support it, unless it gives records of
  its own.
- Keep the status of every value: reported, applied from elsewhere, true by definition or assumed.
  A range that the model chooses is not an empirical interval. `napkin compile` counts them:
  `evidence: 0 sourced values, 5 assumed`.

## 10. Texts

- The first text under a line is what a reader sees: the label of a value, the description of a
  thing, the card of an event or an outcome, the message of a check, the menu line of an option.
- Write a label as a short noun phrase that names one thing: "People served", "Time with low
  pressure".
- Write the text of an event or an outcome as one sentence in the present tense, with the actor
  first: "The crews repair the pump, and the pressure comes back."
- Write a status as a short, plain statement of the condition: "Dosing wrong", "Pump repaired".
- Use one word for one meaning everywhere, and put no model word in a text: say "after 15 days",
  not "at the horizon".

This repository writes its texts in ASD-STE100 Simplified Technical English, with the project
glossary ([CONTRIBUTING.md](../CONTRIBUTING.md#writing-style)).

## 11. A variant, an option or a run

Choose by what differs between the cases that you compare:

| What differs | Use | Example |
| --- | --- | --- |
| The things: another place, other systems, other people or other evidence | A **variant**: a folder of its own, `variants/<name>/` | `water_controls_wipe` has a variant for each of 16 places, such as `juneau` |
| A condition of the same things, or how they act, which a reader chooses | An **option**, in a group of options | The groups Response, Access, Attacker and Reach of `water_controls_wipe` |
| A combination of options that every reader, test and edit sees | A **run**: a named combination, compared with another run by `versus` | `delayed_kept_human = "Delayed response" + "Keeps hidden access" + "Human team" versus delayed_kept` |
| One number that a reader explores | An input with its range, which an edit sets | `napkin run examples/piano_tuners --set tuners.staff=5` |
| A value that is uncertain | A distribution, which `napkin sample` draws | The rate of `examples/piano_tuners` |

### A variant: another place or system

A variant is the file `variants/<name>/model.scn` of a package. It starts with `variant "Title"`, and
it reads the package's main file first (language.md, §2.12). It is a model of its own,
`package:name`, with its own hash, runs and results. `--variant NAME` picks it in every command.

- Make a variant when the things differ: one water system or several, other hospitals, other
  populations and the records of each. The mechanism stays in the main file.
- Put what the places share in the main file and its modules: the templates, the shared things, the
  outputs, the options and their records. Give each place its variant, with the summary and the
  scope of that place, its things and their records. Each variant then builds only its own things.
- Use a template's name where a list of its instances goes (`sum(Utility.unserved)`), so a module
  does not name the instances that each variant declares.
- A variant's lines come after its main file's lines, and the order of the lines decides the order
  of one moment (section 12). So keep the main file free of things when their order matters.
- A variant can add options to a group of the main file, and runs of its own.
- Do not switch things on and off with options to put several places in one model. Every structure
  keeps every thing, so the build of such a model is slow, and each run carries the things of every
  place.
- A new variant changes no hash of its siblings, and it needs no change to the main file.

`water_controls_wipe` has one main file and a module, `water.scn`, for the mechanism. Each of its 16
variants declares the water systems, the homes and the hospitals of one place:

```text
# scenarios/water_controls_wipe/variants/juneau/model.scn
variant "Juneau, Alaska"
    summary "An AI agent wipes the controls of the water system of Juneau, Alaska through the remote-support
        platform of the OT integrator that it uses."
…
juneau: Utility
    "City and Borough of Juneau, Alaska. Its ID in the federal inventory is AK2110342."
    title "Juneau"
…
    demand = 4.7619 Mgal/day  @juneau_demand
```

The variant `washington_dc` adds the option "The Aqueduct only" to the group Reach, and the run
`delayed_kept_aqueduct` that takes it.

`napkin new` writes a package with variants. With several variants, `napkin run` asks you to pick
one:

```
$ napkin new towns --variants east,west
Wrote towns/model.scn, and the variants east and west in towns/variants/.
It compiles and runs as written: napkin run towns --variant east
…
$ napkin run towns
…
napkin run: error: towns has 2 variants: pick one with --variant NAME
  east  east
  west  west
```

### An option: a choice that a run can make

An option sets inputs, the start values of vars and text values (language.md, §2.9). Each line that
sets an input or a start value cites its record. The options sit in groups: `options "Response":`. A
run takes one option of each group that it names; a group that it does not name keeps the values
that the file writes.

- Make an option when a reader chooses between named conditions of the same things: how fast the
  crews respond, what the world holds at the start, who acts.
- Split the options into groups that do not overlap. No option repeats the values of another, and
  two groups never set the same value.
- Name each group for what its options are, and each option for what it is.
- An option with no lines keeps the values that the file writes. In `water_controls_wipe`, "Delayed
  response" has no lines: the inputs' own values are the delayed response.
- Behaviour that only some options reach sits in events that cannot happen with the others. Its
  evidence then shows as possible, not used, in those runs.
- When the support for an event differs by option, write one event for each case. The `when` of
  each tests the start state that the options set, and each has its own record.
- An option that sets the start value of a var gives the runs that take it a structure of their
  own. The compiler builds one structure for each set of start states that the runs use, so keep
  these options few.

`--option` puts an option into a run in place of its group's choice. The tool checks that combination
when you ask for it, and only for that run:

```
$ napkin run scenarios/water_controls_wipe --variant juneau --run early_kept --option "Delayed response"
note: checked for run early_kept only; `napkin compile` checks every run
early_kept: Delayed response · Keeps hidden access
                                                                at the end (2160 h)
  Replacement controllers in stock                              1050 parts
  Person-days without normal water service                      93900 person-days
…
```

napkin refuses a combination whose start states no run takes: "No run of the model starts from the
start states of these options". To explore such a combination, declare a run that takes it.

### A run: a named combination

A run names one option of each group that it uses: `early_kept = "Early response" + "Keeps hidden
access"`. A model with no options and no runs has one run, `base`.

- Declare the runs that readers compare, and that the tests and the edits must hold for. The engine
  checks each edit on every declared run, as one transaction. So each run is a promise: every edit
  holds in it.
- napkin checks a combination that no run makes only when a caller asks for it: `--option` on the
  command line, or `model.combination(run, options)` in Python ([python-api.md](python-api.md)).
- A run that is the matched comparison of another run says so with `versus`. `napkin sample` then
  samples both on the same draws.
- Without a text of its own, a run's label is the names of its options, joined by " · ". Give a run
  of three options a text that reads as one.
- Each run is simulated, so each run adds time to `napkin run` and to the tests. The run store keeps
  each simulated run ([engine.md](engine.md#the-run-store)).

```text
runs:
    early_kept = "Early response" + "Keeps hidden access"
    standard_kept = "Standard response" + "Keeps hidden access"
    delayed_kept = "Delayed response" + "Keeps hidden access"
    delayed_none = "Delayed response" + "No hidden access"
    delayed_kept_human = "Delayed response" + "Keeps hidden access" + "Human team" versus delayed_kept
        "Delayed response · Human team keeps hidden access"
```

## 12. The same moment

- The events due at one moment fire one at a time, in the order of their lines in the model: the
  things in their order, and within a thing its events in theirs. After each one, every condition is
  read again, so the next event reads what the earlier ones wrote (language.md, §2.6).
- Design the model so that the result of a moment does not depend on that order. Where two events can
  meet and the result does depend on which goes first, put the thing that goes first earlier in the
  file, and say why in a comment. The order is a claim about the world ("when the repair ends as
  the alarm sounds, the repair goes first").
- Prefer the order of the lines to a guard. A guard that keeps two steps from meeting reads a value
  that the thing may not know, and it adds a record to every run.
- The compiler does not look for pairs of events that meet. Read the events of a run with
  `napkin run --events`, and check each moment that holds two.

```
$ napkin run examples/reservoir --events
base
                                             at the end (120 h)
  Water let out over the spillway            0.5 fraction
  Time with the water above the risk level   0 h
  events:
    40 h  The operator opens the spillway.  (operator.decide.open)
```

## 13. Check a model

The commands check a model at each step ([cli.md](cli.md)):

- `napkin compile` reads, checks and proves the model, each variant and each run, and lists its
  runs and options. `--inputs` and `--outputs` add each input, with its unit, range and record kind,
  and each output.
- `napkin run` runs the runs and prints each outcome at the end. `--run NAME` runs one run, `--set
  NAME=VALUE` gives an input another value, `--at TIME,…` gives the outcomes at other times too, and
  `--events` lists the events.
- `napkin sample` draws every input that has a distribution and prints the spread of each outcome.
- `napkin draw` draws the picture as SVG ([draw.md](draw.md)).
- `napkin fmt --check` reports each file that is not formatted.
- `napkin play` gives the choices of an actor to you, or to a program with `--json`.

```
$ napkin compile examples/piano_tuners --inputs --outputs
piano_tuners  Piano tuners
  runs:     base (1)
  inputs (3):
    tuners.rate    pert(600 tunings/tuner-year, 1000 tunings/tuner-year, 1200 tunings/tuner-year)   500 to 1500 tunings/tuner-year   assumption   Tunings that one tuner does in a year
    tuners.staff   3 tuner                                                                          1 to 10 tuner                    assumption   Tuners in the town
    tuners.need    5000 tunings                                                                     0 to 20000 tunings               assumption   Tunings that the pianos need in the year
  outputs (1):
    tunings_done   tunings   cumulative   Tunings done in the year   The pianos of one town.
  compiled · evidence: 0 sourced values, 3 assumed
$ napkin run examples/piano_tuners --set tuners.staff=5 --at 6months
base
                             at 4380 h      at the end (8760 h)
  Tunings done in the year   2436 tunings   4873 tunings
$ napkin sample examples/piano_tuners --samples 50
piano_tuners: Piano tuners
50 samples, seed 0, at the end of the run (8760 h)
  base

tunings_done: Tunings done in the year (tunings)
  base  mean 2904; middle 50%: 2702 to 3171; middle 90%: 2396 to 3364
        inputs that move it most (rank correlation): tuners.rate +1.00
```

### Tests

A model's tests check what the model means, with mathematics of their own. Write them with pytest
and the Python API ([python-api.md](python-api.md)): `load_package`, `evaluate_study` and
`sample_result`.

- Test a property, not a number that the model gave once: a balance, a bound, a value that doubles
  when its cause doubles, an order of events.
- Compute the expected value from the inputs that the test sets or reads, with mathematics that is
  independent of the engine. Do not copy the value from a run, and do not compute it by hand from a
  default that the model file writes.
- Test a counterexample too: an edit that a check must reject, or a case at a bound.

This test of the model from `napkin new demo` sets the rate twice and checks the property:

```python
from pathlib import Path

import pytest

import napkin

FOLDER = Path(__file__).resolve().parents[1]


def served(rate):
    """The people served at the end of the run, with the rate set to `rate` people a day."""
    (model,) = napkin.load_package(FOLDER).values()
    edits = {
        'schema_version': napkin.SCHEMA_VERSION,
        'model_hash': model.model_hash,
        'set': {'service.rate': rate},
    }
    study = napkin.evaluate_study(model, edits)
    assert study.admissible, study.diagnostics
    final = napkin.sample_result(study)['runs']['base']['reporting_points']['final']
    return final['values']['people_served']


def test_twice_the_rate_serves_twice_the_people_while_people_wait():
    assert served(20) == pytest.approx(2 * served(10))
```

```
$ python -m pytest -q demo/tests/test_demo.py
.                                                                        [100%]
1 passed in 0.95s
```

The tests of this repository follow the rules in [CONTRIBUTING.md](../CONTRIBUTING.md#testing).

## 14. Change a model safely

A change moves only what it means to move. Prove it, do not assume it.

1. **Record the results first.** Keep the report of each run that the change can reach:
   `napkin run TARGET --json > before.json` (`--json full` adds the trace). It holds every outcome
   with its status, and every event with its time. Where the change can move what an edit admits,
   also keep the results of a few edits: some near the defaults, some that a check rejects, and some
   with round times that make steps meet at one moment.
2. **Say what the change should move** before the first comparison: the outcomes, events, statuses
   and records that it means to change, and why.
3. **Compare.** Every other outcome within 1e-6 × max(1, |value|) with the same status; every other
   event time within 1e-6 h; the same statuses; the same edits admitted and rejected. Never loosen
   the tolerance, and never edit the model to fit a result.
4. **Explain each difference.** List each one that the change means to make, with its size; any
   other is a fault of the change.
5. **Count the evidence.** Every claim and assumption that a run used is still cited, unless the
   change removes it on purpose and says so.
6. **Keep names stable,** or rename a name everywhere in the same change.

A change of meaning changes the model's hash. Then napkin refuses the saved edit documents and play
logs of the old model, so make them again. A comment, a blank line or a rename keeps the hash
(language.md, §2.12).

## 15. The checklist

Answer each question with yes, or change the model.

1. Can you name each thing's states, and their values, in words that a person would use?
2. Is every thing a real thing or actor, with no bookkeeping thing?
3. Is each state held in one thing only, with no echo state, and no dead or zero-length value?
4. Is each input on the thing that it describes?
5. Does each event react to something that its thing can see?
6. Does the record on each event's line say how its thing knows what the `when` reads?
7. Does every event say how often it happens: `once`, or a condition that becomes true again only
   when the world changes?
8. Is every guard needed, with none that always holds when the event can happen?
9. Do the groups of options not overlap, with no option that repeats the values of another?
10. Where two events can meet at one moment, does the order of their lines put first the one that
    goes first in the world, and does a comment say why?
11. Does the picture tell the story with no other explanation?
12. Does every flow, event and outcome that a reader sees have a text of one sentence?
13. Is every value that is not estimated marked `unestimated`, with its reason?
14. Is every part and line of the files read by the calculation, the picture or a reviewer?
15. Does each clock start at the first moment that its thing could know?
16. Is every time and amount in a `when` a value with a record, and not a number in the expression?
17. Does each event read the state of the thing that it depends on, and not the state of another
    actor?
18. Does each actor's `sees` list what it can observe, and nothing that it cannot?
19. Is each place or system that has things of its own a variant, and each choice of a reader an
    option?
20. Does each value have its unit, in the unit of its source, with no conversion by hand?
