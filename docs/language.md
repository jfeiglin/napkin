# The scenario language

This page is the contract of the language, version 0.0.1: what each line of a `.scn` file means.
`napkin` reads these files: `napkin compile` checks them, and `napkin run` runs them
([cli.md](cli.md)). Words in `code` are written in the file. Every example uses invented values and
sources.

## Contents

1. [A scenario file in one page](#1-a-scenario-file-in-one-page)
2. [The rules](#2-the-rules)
3. [What the compiler rejects](#3-what-the-compiler-rejects)

The picture of a model and its file, `style.toml`, are on their own page, [draw.md](draw.md).

## 1. A scenario file in one page

A scenario is a **package**: a folder whose main file is its `model.scn`. The folders name the
scenario, so no file of it writes its name. `napkin` reads these files of the folder:

| File | What it holds |
| --- | --- |
| `model.scn` | The main file of the model, in this language |
| Other `.scn` files of the folder | The modules of the package, which `use` lines name (§2.12) |
| `variants/<name>/model.scn` | A variant: a model that reads the main file and changes it (§2.12) |
| A `.csv` file that a thing names | The table of a set of instances (§2.3) |
| `units.json` | The package's own units, beside those of the prelude and of the library (§2.12) |
| `evidence/` | The sources, claims and assumptions that the records cite (§2.10): `sources.json`, `claims.json` and `assumptions.json`, which `napkin/schema/library.schema.json` checks. [evidence/README.md](../scenarios/docs/evidence/README.md) says how the catalogue writes them |
| `style.toml` | The picture that `napkin draw` makes ([draw.md](draw.md)). `napkin compile` checks it, and no run reads it |

Each of these files except `model.scn` is optional. The catalogue in `scenarios/` adds files of its
own, which `napkin` does not read ([catalogue.md](../scenarios/docs/catalogue.md)).

**Roles.** The first declaration of a file gives it its role: `scenario "Title"` starts the main file
of a package, `variant "Title"` starts a variant, and a file that starts with any other declaration
is a module. Comments can come before the first declaration.

The main file has these parts, in this order:

| Part | What it holds |
| --- | --- |
| `scenario "Title"` | The summary, the length of a run, whom the outputs cover and the folder of the library |
| `use` | The modules of the package that the model reads (§2.12) |
| Things: `name:`, `Template:`, `name: Template` | Their fields, flows, shares, events, checks, outputs and status |
| `assert`, `output` | Checks and results that read several things |
| `options`, `runs:` | The choices that a reader can make, and the runs |
| `notes:` | The authors' and the reviewers' notes, which the calculation never reads |
| `record` | The named evidence records |

**How a file runs.** The compiler turns the file into the engine's flat structure. A run takes the
default values, then the values of its options, then the user's edits. The engine runs it, and
`napkin run` prints its outcomes. The engine adds no meaning of its own: the file says what happens.

```text
scenario "Tampered dosing at a water plant"
    summary "An attacker changes the dosing of a water plant. The operators find it and choose a response."
    horizon 48 h
    scope "The people of the two districts that the plant supplies."
    library "../library"

plant:  @plant_model
    "The water plant."
    role operator
    var dosing: "normal" | "tampered" | "manual" = "normal"  @plant_model
        "Chlorine dosing"
    var supply: "on" | "off" = "on"  @plant_model
        "Water supply"
    var unsafe_drunk: L = 0 L size 100000 L  @plant_model
        "Unsafe water that people drink"
    flow drinking: -> unsafe_drunk at 1000 L/h while dosing is "tampered" and supply is "on"  @usage
    status failed when dosing is "tampered"
        "Dosing wrong"
    status ok
        "Dosing normal"

operators:  @operators_model
    "The plant's operators."
    role operator
    sees plant.supply, find
    input find_time = 6 h in 1 h to 24 h  @detection
        "Time until the operators find the wrong dosing"
    input shut_odds: fraction = 0.3 in 0 to 1  @response
        "Chance that the operators shut the plant"
    event find once when since(plant.dosing) >= find_time and plant.dosing is "tampered":  @detection
        "The operators find the wrong dosing."
    event respond once after 2 h when count(find) > 0:  @response
        manual 1 - shut_odds:
            "They take manual control of the dosing."
            plant.dosing = "manual"
        shut shut_odds:
            "They shut the plant."
            plant.supply = "off"
            notify
    event notify:
        "The operators tell the hospital."

attacker:  @attack_model
    "The attacker."
    role adversary
    event start when t >= 0 h:  @attack_model
        "The attacker changes the dosing."
        plant.dosing = "tampered"

output unsafe_water: L = plant.unsafe_drunk  @plant_model
    "Unsafe water that people drink"

options "Response":
    "Manual control":
        "The operators take manual control."
    "Shut the plant":
        "The operators shut the plant."
        operators.shut_odds = 1  @response

runs:
    manual = "Manual control"
    shut = "Shut the plant" versus manual
        "Shut"

record plant_model: identity "The model counts the water that people drink once, by the state of the plant."
record usage: assumption "The example assumes that the districts drink 1000 L of its water in each hour."
record operators_model: assumption "The example assumes one team of operators who watch the plant."
record detection: assumption "The example assumes that the operators find the wrong dosing after 6 h."
record response: assumption "The example assumes that the operators shut the plant in 3 cases of 10."
record attack_model: assumption "The example assumes that the attacker changes the dosing at the start."
```

## 2. The rules

### 2.1 Lines and text

- Each level of nesting is four spaces. A tab is an error. A line belongs to the nearest line above
  it that has less indentation. A comment is a whole line that starts with `#`, outside a text and
  outside a bracket. No line ends with a comment.
- A line that opens a block of its own lines ends with `:` (`plant:`, `event e when C:`,
  `options "G":`). A line that gives something after its name ends with that thing.
- An expression continues on the next lines while a bracket is open, and only then; brackets never
  change its meaning. A line that ends with an operator, or a row that starts with one, is an error
  that says so: wrap the expression in `( … )`.
- The formatter, `napkin fmt`, keeps lines within 110 columns where it can. It breaks a long line
  inside its brackets or inside a text. It never moves a line: the order of the lines is part of the
  model (§2.6, one moment).
- A text is in double quotes and has no escapes: use “ and ” inside it. It can run over several
  lines, each indented deeper than the first; a line break reads as a space, and an empty line is
  one line break. The first text under a line is that line's text: the label of a field, the
  description of a thing, the card of an event or an outcome, the message of a check, the menu line
  of an option. A line has one text under it. A list of texts gives one text for each time that an
  event happens; the last one serves every later time.
- **Braces.** A text of an event, an outcome or a status can name a text value of its thing in
  braces, anywhere in the text: `"{actor} changes the dosing again."`, `"Crews of {utility} switch
  the feeders back."`.
- **Names** are words of letters, digits and `_`. A template's name starts with a capital letter;
  any other thing's name does not. The fields, flows, shares and events of a thing share one set of
  names. A name is never a word that Python keeps, such as `in` or `class`, nor a word of the
  language: `t`, `since`, `count`, `copy`, `outside`, `move`, `from`, `to`, `choice`, `each`, `in`,
  `is`, `not`, `and`, `or`, `if`, `else`, `true`, `false`.
- **Numbers** carry their unit, one word after one space: `12 h`, `1000 L/h`. A number without a
  unit, such as `0.3`, has no unit: its field writes its type (`input share: fraction = 0.3`). A unit
  is the whole word after its number; `48 h / 2` divides. Equality is `is`; a named value is in
  quotes.
- **Units.** A unit is a name that the prelude, the library or a `units.json` declares (§2.12), or a
  composition of declared units, which needs no entry: `a/b` divides, `a-b` multiplies and binds
  tighter than `/`, and `a^n` is a power with a whole exponent. So `tunings/tuner-year` is tunings per
  tuner per year, and `m^2` is the square of `m`. An entry wins over a composition: an entry of the
  whole name, of a product of its parts, or of the first parts of a quotient (`L/h` in `L/h/people`).
- **Functions.** The list is closed. `min`, `max` and `clip(x, low, high)` take values of one unit,
  `abs` keeps its unit and `sqrt` halves the powers of its unit. `exp`, `expm1`, `ln`, `log1p` and
  `erf` (the error function: `erf(z / sqrt(2))` is the chance that a normal value lies within z
  standard deviations of its mean) take a number without a unit and give one. A power `a ** b` with
  a unit needs a number for `b`. The lists have `sum`, `count`, `any` and `all` (§2.3), the clocks
  `since` and `elapsed` (§2.6), and an event has `delayed` and the distributions (§2.6).

### 2.2 The scenario line

```text
scenario "Title"
    summary "The story in a few sentences. Its first sentence is the hook."
    horizon 720 h
    timescales a.repair_time, b.delay / 2
    resolution 1 h
    scope "The people that the outputs count"
    library "../library"
```

The scenario line is the first declaration of the main file of a package. It has a title and no ID:
the folders name the scenario. The lines under it come in any order, each at most once.
`horizon` is the length of a run, and every model has one. `timescales` lists the shortest physical
times, computed from inputs, for the solver. `resolution` is the longest step of the solver, a time
from more than 0 h to the horizon: 1 h without the line. A model of slow change over years can take
`resolution 7 days`; its timescales still shorten the step ([engine.md](engine.md#the-step)).
`scope` says whom the outputs cover: it is the scope of each output that gives none of its own
(§2.8).

`library "PATH"` names the folder of the library of the model, relative to the main file: the file
`vocabulary.json` of that folder holds the units and the shared records. A main file has at most
one `library` line. Without it, a model has the units of the prelude and the files of its package
(§2.12); a caller that gives the library itself gives all of it ([python-api.md](python-api.md)).

A variant starts with `variant "Title"`, which takes the same lines under it except `library`: a
variant reads the library of its package (§2.12).

### 2.3 Things

- `name:` is a thing: an entity of the world or an actor. `Template:` is a template, which makes no
  thing by itself. `name: Template` is an instance of it, and `name: Template * k` makes k copies,
  `name.1` to `name.k`, which read their number as `copy`.
- **A table.** `name: Template from "zones.csv"` makes one instance for each row of a table, `name.1`
  to `name.k` in the order of the rows. They are a set of copies. The table is a file of the package,
  and its name is its path from the folder of the package. It is UTF-8 text with commas between its
  cells; a cell that holds a comma, a quote or a line break is in double quotes. The first row is the
  header, and one row or more comes after it.
  - A header is `member`, or `member: unit` for a column of numbers, and then the records of the
    values of the column: `population: people @census`.
  - A cell that is not empty gives its instance what the line `member = cell` gives: a number with
    the unit of its column (also below zero: `-1.5`), `true` or `false`, or the text of a text value or of a named state,
    without quotes. So each rule of that line holds for the cell. An empty cell gives nothing: the
    instance keeps the value of the template.
  - A column can name a link of the template, with one entity in each cell. A column `title` gives
    each instance its title, when the template has no member of that name.
  - The lines under the thing hold for each row. A member has one giver: a line under the thing or
    a column. A cell holds a value, so a formula goes in the template.
- Under a thing: its text, `title "…"`, `role R`, `sees …` (§2.7), its fields, flows, shares, events,
  asserts, outputs and status lines, in any order. A role is a word that says who acts, such as
  `adversary` or `operator`. The language gives it no meaning; `napkin draw` gives six roles an icon
  ([draw.md](draw.md#icon-the-icons)). An event and an outcome can have a `role` line of their own.
- An instance has its template's members, in the template's order. Its lines change them:
  `population = 24000 people  @r` gives a new value, `population:` with lines under it gives a new
  text or new records, and `input x = …` or `let x = …` gives a member a new kind of value. An
  instance adds no member, and its role and `sees` are its template's.
- **Links.** `let zones = [near, middle]` links a thing to others; `zones.x` reads each,
  `sum(zones.x)` adds them, and a line `zones.e` fires the event `e` of each. `count(zones.flag)` is
  the number of members where a yes/no holds, `any(zones.flag)` and `all(zones.flag)` whether one or
  every member's holds, and `max(zones.x)` and `min(zones.x, 2 h)` take the largest or the smallest of
  the members' values and the other arguments. A template declares a
  slot that each instance binds: `let region: Region` (or `let regions: [Region]`), with
  `region = inland` in the instance.
- **A template's name is the list of its instances**, copies included, in the order of the model,
  wherever a list goes: `sum(Zone.population)`, `let zones = Zone`, the line `Zone.alarm`, `order
  Zone.drain` and a term of a sum (§2.8). A module can then read every instance that a model
  declares without naming them.
- **An empty list.** `let regions = []` binds a list slot to no thing. A template with no instances is
  an empty list too. A sum or a count over no members is 0, `any` is false and `all` true, `max` and
  `min` need another argument, a line over no members fires nothing, and an `order`
  over no members serves nothing; the names are still checked against the template.

### 2.4 Fields

| Line | What it is |
| --- | --- |
| `input x = 6 h in 1 h to 24 h  @r` | Set before the run: a default, an option, an edit or a draw. `in lo to hi` gives the range that a reader can set, and a number input needs it |
| `input flag: bool = true  @r` | A yes/no input |
| `input actor = "The AI"` | A text value, which braces can name |
| `let k = 2 h  @r` | A value that never changes |
| `let f: people = a * b  @r` | A formula, computed whenever it is read. It writes its type |
| `var s: "a" \| "b" = "a"` | A named state: the events change it |
| `var n: people = 10 people in 0 people to 100 people size 100 people  @r` | A number that changes during the run |

- The value of an input or a `let` can be a distribution: `uniform(1 h, 9 h)`, `pert(a, m, b)`,
  `triangular`, `loguniform`, `normal`, `lognormal`, `beta`, `bernoulli(p)`, `categorical(…)`. Its
  range holds every value that it can draw.
- **What a number var is.** The compiler finds it from the file: a **stock** when a flow or a move
  takes from it (or a line lowers or sets it), a **tally** when flows and moves only fill it, a
  **number state** when no flow or move joins it. A stock and a tally never go below 0, and a var
  never goes above the high end of its range. `in` also gives the solver the var's size; `size`
  gives it where `in` has no high end.
- `output x` under a thing makes its number var `x` an output, with the lines of an output (§2.8)
  under it; the var's text is the output's label.

### 2.5 Flows and shares

```text
    flow drain: tank -> basin at 10 L/h while valve is "open"  @r
    # From outside the model:
    flow fill: -> tally at rate  @r
    # Out of the model:
    flow use: stock -> at need  @r
    # Pairs that move by one fraction:
    flow together at rate while C:  @r
        a -> b
        c -> d at other_rate
    share basin limit 3 L/h order pump_a, pump_b  @r
```

- A flow moves its rate per hour, never a negative amount, while its `while` holds. The pairs of one
  flow move by one fraction: when any source runs short, all slow together.
- When several flows take from one var, it needs a `share`: they share what it holds in proportion
  to what they ask; `order` serves the named flows first, in order; `limit` caps the total per hour.
  A share always has its `limit`.

### 2.6 Events

```text
    event find once when since(plant.dosing) >= find_time:  @r
        "The operators find the wrong dosing."
    event respond once after 2 h when count(find) > 0:  @r
        manual 1 - shut_odds:
            "They take manual control."
            plant.dosing = "manual"
        shut shut_odds:
            "They shut the plant."
            plant.supply = "off"
            notify
    event notify:
        "The operators tell the hospital."
```

1. **Trigger.** An event triggers each time its `when` becomes true; true at the start counts. An
   event without `when` triggers only when a line names it. `once`: it triggers at most once in a
   run.
2. **Delay.** With `after D`, the event fires `D` after it triggers; `D` is read when it triggers.
   An event that waits to fire does not trigger again. With `while K` (after its `when`), a firing
   that waits is cancelled at the first moment that `K` fails; the event can trigger again once its
   `when` becomes true again. A cancelled `once` event stays spent.
   **Draws and the past.** A distribution is drawn when the thing that holds it happens. An input's
   or a `let`'s distribution is drawn once, when the thing is created: once in each run or sample. A
   distribution written in an event, in its lines, chances or delay, is drawn each time the event
   fires (its delay as it triggers): `after pert(1 h, 3 h, 12 h)`, `reported = held * lognormal(1, 1.2,
   0, 10)`. The families are those of numbers (`uniform`, `triangular`, `pert`, `loguniform`,
   `normal`, `lognormal`, `beta`), with every parameter. The central run takes the median; a sample
   of a study draws from the stream of the event. `delayed(x, D)` is the value of `x` at `D` before the
   firing; before the start, its value after every step of the first moment. Neither may appear in a
   `when`, a rate, a formula or an output.
   **Window.** With `each W` (or `each W1, W2`), the event triggers at most once in each window: a
   window lasts while the value of `W` (the combination of values) stays the same, and a value seen
   earlier, after a change, opens a new window. `event review each timeline.beat when alarms > 0:`
   asks once in each decision window; `event follow each order, backlogged when backlogged:` follows
   each order again when a backlog returns. Without `when`, it triggers once in each window. `W` and
   `K` read only values that change at moments. A firing that `while K` cancels was still a trigger:
   `count(e)` and `since(e)` count it. The full line is
   `event name [once] [after D] [each W] [when C] [while K]:`.
3. **Outcomes.** The lines under an event are its one outcome, `done`. Or the event has outcomes,
   `name chance:` with their own text, role and lines. The line `choice` under an event marks an
   actor's choice (§2.7). A chance is a number, an expression, a
   condition (1 when it holds, else 0), or `else` (1 less the others); an outcome without a chance
   has the chance 1. The chances must add up to 1
   within 1e-9, or the run fails with `chances`. Exactly one outcome happens: in the central run the
   one with the largest chance, the first in the file on a tie; in a sample of a study, a draw.
   `name chance when C:` says when the outcome can happen: only while the condition `C` holds. An
   outcome that cannot happen has no chance then, or the run fails with `chances`; no run, sample or
   pick takes it. Only an event with two outcomes or more has such a condition, and a choice's
   condition reads only what its actor knows (§2.7).
4. **Lines.** `x = v`, `x += v`, `x -= v`, `move A from S to D`, and a name of an event, `e`,
   `thing.e` or `list.e`, which then triggers. A move takes `A` out of the number var `S` and puts it
   into the number var `D`; to add from outside the model or take out of it, write `x += v` or
   `x -= v`. The lines of an outcome read the values from before it; then the events that it names
   trigger, in order. One outcome sets a value once. A named state takes
   one of its states, another named state or a named input, or `a if C else b` of these, when every
   value that the right side can give is one of its states: `diversion = ordered`. A yes/no state
   takes `true`, `false` or a condition: `found = world.persistence`.
5. **Names in the engine.** The event `e` of thing `x` is `x.e`; its outcome `o` is the event
   `x.e.o`, which `since()` and `count()` can read: `count(respond.shut)`.
6. **One moment.** At a time `t`, the events go one at a time. After each firing every condition is
   read again, and the next to go is the first due event in the order of the lines of the file: the
   instances of a template's event in the order of the instances, then copies 1 to N. So an event
   reads what the events before it in the file wrote at the same moment. The step budget limits the
   firings of one moment.
7. **What a `when` may be.** An `and` of conditions over values that change at moments, clocks (`t`,
   `since(e)`, `elapsed(s)`), and at most one crossing of a continuous value. A crossing compares
   one var with a value that changes only at moments, by `>=` or `<=`: `fuel <= reserve`. The var
   needs constant rates between moments, or it only rises or only falls between them (a tally, or a
   var whose flows all go into it or all go out of it), or it is a stock that reaches zero through
   constant flows ([engine.md](engine.md)). An event that can
   trigger again on a crossing sets, in each outcome, a name that its `when` reads, so that the
   crossing is spent: `when status is "up" and level <= 0 L:` with `status = "down"`.
8. **The start** is the event `start` of one thing, `event start when t >= 0 h:`. A model has one
   start at most. It fires first, at t = 0, with one outcome.

### 2.7 Actors

A thing with `sees` is an actor; its list is what it observes: fields and events of any thing. It
inherits this list from its template, with local names and links resolved for each instance. It
also knows `t`, `copy` and its own inputs, and nothing else: a person can be infected and not know
it. An event of an actor with the line `choice` under it is a **choice**: a run can give it to a
person or an agent. A choice has two outcomes or more, and it reads only what its actor knows in its
`when`, `after`, `each`, `while`, chances and the conditions of its outcomes; the compiler refuses
any other name there (`sight`). Its chances are the model's estimate of what the actor does. Every
other event, of an actor or of a thing without `sees` (the world), is a mechanism: chance takes its
outcomes, it may read anything, and nobody plays it. The mark changes nothing in a run that nobody
plays. How a run takes the outcome of each choice, by chance (the model's chances), by a person or
by an agent, is set for each run, never in the file ([engine.md](engine.md#play)).

```text
    event decide each timeline.beat when alarm is "on":  @r
        "The operators weigh what to do."
        choice
        close 0.7:
            tank.drain = "closed"
        wait else:
```

### 2.8 Checks, status and outputs

- `assert C  @r` with its message. An `assert` that reads only inputs and named states runs before
  the run, with each state at its start value, and rejects the run when it fails. Any other `assert`
  holds at every step and stops the run when it fails; the compiler must prove it from bounds, a
  sum or a monotone comparison. `assert a + b is T within 0.01 L` checks a sum of number vars; a
  term that names a list, `Zone.held`, adds the var of each member.
- `status failed when C` lines, one under the other, give the thing's status in the report: `ok`,
  `degraded`, `failed` or `inactive`. The first line whose condition holds gives it; the last line
  has no condition. Each line has its text.
- `output name: unit = E  @r` is a result. Under it: its label, `about "…"`, `category deaths`
  (a tag, which the language does not read), `scope "…"` (whom it covers: without the line, the
  scope of the scenario line, §2.2), `level` (it can fall), `signed` (it can be below zero),
  `distinct  @r` (the people that it adds are different people), `lag 2 h` (also `uniform(a, b)` or
  `mixture([0.9, 0], [0.1, 336 h])`), or `unestimated "Reason"`. An unestimated output writes no
  `= E` on its line. An output is cumulative unless it is a `level`; only a cumulative output takes
  `lag`.

### 2.9 Options and runs

```text
options "Response":
    "Early response":
        "The operators find the problem after 2 h."
        operators.find_time = 2 h  @response
        # Every instance of a template:
        Zone.population = 100 people  @r

runs:
    early = "Early response" + "AI agent"
    early_human = "Early response" + "Human team" versus early
        "Human team"
```

- An option has its text, its line in the menu. It sets inputs, the start values of vars and text
  values; it sets no formula. A run takes one option of each group that it names; `versus` names
  the run that it is compared with, which is no comparison itself. A combination of options
  that no run makes is checked only when a caller asks for it (`combination`,
  [python-api.md](python-api.md)).
- A model with no `runs:` and no options has one run, `base`, which takes the values as the file
  writes them. A model with options names its runs.
- The order of the groups, the options and the runs is the order of the menu.

### 2.10 Evidence

Every choice of the model shows its support: a record. A record is the only way to give support.

- `@name` cites a named record; a line can cite several: `@a @b`. When they do not fit on the line,
  they go on a line of their own under it.
- A named record is `record name: kind [ID] "explanation"`, a declaration of its own, which the
  examples put at the end of the file. A record written in place is `@kind [ID] "explanation"` on
  its own line under the line that it supports.
- The kinds: `source` (a source reports it for this setting), `source_transfer` (a source reports
  it elsewhere, and the scenario applies it here), `assumption` (the scenario assumes it), `identity`
  (true by definition or by counting) and `convention` (a rule that the project follows).
- **The ID is optional.** A record without one stands on its explanation:
  `@assumption "The example assumes three tuners."`. The ID of a `convention` record names a
  convention of the library: `record casualty_levels: convention HAZUS-SEVERITY "…"`. The ID of a
  record of any other kind names an assumption of the library or of an `evidence/assumptions.json`
  (§2.12). The compiler refuses an ID that names no such record.
- Under a record, `claims:` lists the claims that it rests on, each by its ID, with `datum: key`
  under a claim for an exact figure. A value whose record names a datum equals that figure, after
  the conversion of its unit.
- A record supports the line that it ends or sits under. Nothing passes from one declaration to
  another, except that an instance rests on its template's records unless it gives its own, the
  pairs of a flow rest on the flow's, an outcome on its event's, and a status and a yes/no var on
  their thing's.
- **Required.** The compiler refuses a model where one of these has no record: an input (a text
  input needs none), a `let`, a stock, a tally, a number state, a yes/no var, an event with a `when`
  or an `after`, a status, an assert and an output (a field's output rests on the field's records).
  A flow of several pairs cites its records on its line: why the pairs move together. A new value
  that an instance or a `change` block gives has a record of its own, and so have the values of a
  column of a table, in the header of the column. The compiler requires no
  record on a flow of one pair, a share, a named-state var or a line of an option.

### 2.11 Notes

`notes:` holds the authors' and the reviewers' notes. The calculation never reads them, and the
compiler checks no name in them: a note can have any key, at any depth. The catalogue's tools read
their own keys and check them ([catalogue.md](../scenarios/docs/catalogue.md)).

- A note is `key: value`, or `key:` with notes under it; a note with a value can have notes under it
  too. A key is a word of letters, digits, `_` and hyphens: `premises`, `PR1`, `demo-one-plant`.
- A value is a text, a number, a list, or a word such as an ID or a code (`E-DEMO-CENSUS`,
  `conditional_calculation`), which needs no quotes. The numbers of the notes are not values of the
  model, so they have no unit.
- A note can cite records, `@record`, after its value or on a line of its own under it. The records
  that the notes cite are not uses in the evidence index: the scenario's references list their
  claims.
- The notes of the files of a model merge key by key (§2.12).

```text
notes:
    premises:
        START: "The calculation starts when the AI agent reaches the dosing controls."
        PR1: "The laboratory tests the water itself."  @lab_testing
            otherwise: "Without such a test, nothing finds the fault until people fall ill."
    limitations:
        demo-one-plant: "The example follows one plant and two districts only."  @district_model
    decisive: "How fast the operators close the remote-support account."
```

### 2.12 Packages, variants and modules

A model can be split across the files of its package. A **module** is a `.scn` file of the package
whose first declaration is neither a scenario line nor a variant line. `use a.b` names the module
`a/b.scn` of the folder of the package: a name is read from the folder of the package, so nothing
outside the package resolves, and an entry file, `model.scn`, is never a module.

A **variant** is the file `variants/<name>/model.scn` of a package. It starts with `variant "Title"`,
and its implicit first dependency is the package's main file: it is a model of its own, the scenario
`package:name`, that reads the main file and changes it. Each line under its `variant "Title"`
replaces the same line of the main file's scenario line (`summary`, `horizon`, `timescales`,
`resolution`, `scope`), and its title follows the main file's: `Title of the package: Title of the
variant`. A variant reads the library of its package. Several places that share most of their model
are then one package: the main file holds what they share, and each variant is a short file with
its scenario lines, the things of its own place and its changes.

```text
# water_wipe/model.scn
scenario "Wiped water controls"
    horizon 2160 h
    scope "The people that the water systems serve."
    library "../library"
use water

# water_wipe/water.scn
Utility:  @reach
    "One water system."
    role operator
    input demand = 10 Mgal/day in 0 Mgal/day to 2000 Mgal/day  @demand_basis
        "Water that the customers use in a day"
    var unserved: Mgal = 0 Mgal size 1000 Mgal  @counts
        "Water that the customers could not get"

relief:  @relief_basis
    "The emergency drinking water."
    role responder
    input approved_supply = 1 Mgal/day in 0 Mgal/day to 50 Mgal/day  @relief_basis
        "Approved emergency water available in a day"

output unserved_volume: Mgal = sum(Utility.unserved)  @counts
    "Water that customers could not get"

# water_wipe/variants/east/model.scn
variant "The east district"
    summary "An attacker wipes the controls of the east district's water system."

east_water: Utility
    demand = 130 Mgal/day  @east_demand

change relief:
    approved_supply = 2 Mgal/day  @east_relief
```

- **`use NAME`** makes the declarations of the module part of the model. The `use` lines come first
  in a file, after its scenario line. A module can use other modules of the package. A module that
  two files use is read once, and the uses form no circle.
- **One model.** The files are read dependencies first: each file after the modules that it uses,
  in the order of its `use` lines, and the entry file last. A variant's main file, with the modules
  that the main file uses, comes before the variant's own modules. The files are one model, as if
  one file held them in that order, and that order is the order of the lines everywhere (§2.6, one
  moment). Names resolve over the whole model.
- Each thing, output, run and record is declared in one file. An `options "G":` block adds its
  options to the group G of an earlier file, and `runs:` blocks add their runs. A file has one
  `runs:` block and one `notes:` block at most. The notes merge key by key: a later file's note
  replaces the same note of an earlier file, and the notes under a key, such as `limitations:`,
  merge the same way.
- **`change name:`** gives a thing of an earlier file the lines of an instance (§2.3): its text, its
  records, `title`, status lines, link bindings, new values and new kinds of values. It adds no
  member, and a new value needs a record of its own. A change of a template changes the template:
  each instance that does not set the value takes the new one. When several files change one value,
  the later file's change applies.
- **Evidence and units.** The units and the evidence of a model come from the prelude,
  `napkin/std/units.json`, which every model has; then from the library that the `library` line
  names; then from the `units.json` and `evidence/` of the package's folder; then, for a variant,
  from those of the variant's folder. Each of these files is optional. The prelude holds `h`,
  `hour`, `hours`, `day`, `days`, `week`, `weeks`, `month`, `months`, `year`, `years`, `person`,
  `people`, `fraction`, `ratio` and `percentage_points`. No file declares a name of the prelude
  again, and the prelude grows only in a major version. A unit or a record ID is in one folder only.
  Each record of a package's folder is used by its model or by one of its variants, at least.
- **Identity.** The model hash covers the merged model, the units that it uses, the records that it
  reaches and the version of the language. It covers no name or path, not the list of variants, no
  unit or record of the library that the model does not reach and not the version of the package.
  So a comment or a blank line in a module changes no saved edit, a rename keeps the hash, a new
  variant leaves the hashes of its siblings, and a unit that a later prelude adds leaves every hash.

## 3. What the compiler rejects

Each error gives its file and, where it can, its line and column, `file:line:column`. It says how to
fix it. A name or a unit that names nothing comes with the closest names of the model, when one is
close. These are the
errors that the lines of the language make easy to hit. One of them stops a run, not the compiler:
chances that do not add up to 1.

| Wrong | Why | Right |
| --- | --- | --- |
| `scenario Example "…"` | The folders name the scenario, so the line has no ID | `scenario "…"` |
| `library "…"` under `variant "…"` | A variant reads the library of its package | The line on the scenario line of the main file |
| `attack`, `swap` or `reports` under the scenario line | The scenario line has no such line | The catalogue's `brief.toml` names the attack and the group of responses ([catalogue.md](../scenarios/docs/catalogue.md)) |
| A tab before `input` | Nesting is four spaces | Four spaces |
| `"The "safe" level"` | A text ends at its second `"` | `"The “safe” level"` |
| `input delay = 4` | A number without a unit has no type to read | `input delay = 4 h`, or `input share: fraction = 0.4` |
| `input half = 48 h/2` | `h/2` is not a unit | `48 h / 2` |
| `input rate: tunings/yr = …` with no unit `yr` | A unit is declared, or composed of declared units; the error names the closest composition | `tunings/year` |
| `input delay = 4 h  @r` | A number input has the range that a reader can set | `input delay = 4 h in 1 h to 12 h  @r` |
| `area ^ 2` | A power in an expression is `**`; `^` writes the power of a unit | `area ** 2`, or the unit `m^2` |
| `when rooms == "unsafe"` | Equality is `is` | `when rooms is "unsafe"` |
| `rooms = unsafe` | A named value is in quotes | `rooms = "unsafe"` |
| `rooms is "unsfe"` | Not a value of `rooms` | One of its values |
| A name that nothing declares | No field, event or link has it | The name as declared |
| `let f = a * b` that reads values | A formula writes its type | `let f: people = a * b` |
| An input, a `let`, a number var, an event with `when` or `after`, an assert or an output with no record | Its value needs its support | Add a record |
| `@assumption A-NONE "…"` where no assumption has the ID `A-NONE` | The ID of a record names a record of the library or of `evidence/` | The ID of the record, or no ID |
| `input x = uniform(1 h, 9 h) in 1 h to 5 h` | It can draw values above its range | Widen the range |
| Two flows out of one var with no `share` | They could ask for more than it holds | Add a share |
| `move 2 L from tank to outside` | A move joins two number vars of the model | `tank -= 2 L` |
| An event that can trigger again on a crossing, with an outcome that sets nothing that its `when` reads | The crossing would hold again at once | Add `once`, or set a state that the `when` reads |
| `resolution 0 h`, `resolution 2 people` or a resolution beyond the horizon | The longest step is a time after the start, within the run | `resolution 7 days` |
| `when level >= limit and backlog <= 0 L` | A `when` watches one crossing at most | Two events |
| `when backlog > limit` on a var that flows both fill and drain at rates that read the state | No proof says when it crosses | Watch a var that only rises or only falls, or make its rates constant between moments; compare by `>=` or `<=` |
| Chances that do not add up to 1 when the event fires | Exactly one outcome happens; the run stops | Fix them, or give one `else` |
| Two outcomes with `else` | `else` is what the others leave | One `else` |
| A `choice` that reads what its actor does not see | An actor knows only what it sees | Add the fact to `sees`, read a fact that it sees, or remove `choice`: the event is then a mechanism |
| `choice` on a thing without `sees`, or on an event with one outcome | A choice is an actor's, between outcomes | An actor with two outcomes or more, or no `choice` |
| Two lines of one outcome that set one value | One value, one change | One line |
| The event `start` with `after`, two outcomes, in a template or in two things | The start fires first, at t = 0 | One outcome, in one thing |
| An `assert` that can fail and hold again between two solver points | The engine could not see the failure | A comparison that the bounds or a sum decide |
| An option with no text under it | Its text is its line in the menu | Add its text |
| A run with two options of one group | A run takes one option of each group | One option |
| `versus` that names its own run, or a run that has a `versus` | A run is compared with a run that is no comparison | Another run |
| `name: Template * 0` | A set has one copy or more | `* 1` or more |
| A column `hold: L` of a table, where the template has `held` | A column gives a member of the template, a link of it or the title | The name of the member |
| `2 * 3` in a cell of a table | A cell holds a value | The number in the cell, and the formula in the template |
| A column of numbers with no record | A new value needs its support | `held: L @survey` |
| A member that a line under the thing and a column of its table both give | A member has one giver | Remove one |
| `name: Template from "../other/zones.csv"` | A table is a file of the package | Move the file into the folder of the package |
| A model value that reads an output | The model never reads an output | Read what the output reads |
| `output x` under a thing, with a text or records under it | The field's text is the label, and its records support it | Put them on the field |
| `use watr`, with no file `watr.scn` in the package | A use names a module of the package | The module's name |
| `use other.water`, for a module of another package | Nothing outside the package resolves | A module of the package |
| `use variants.east.model` | An entry file is not a module | A module of the package |
| A `use` line after a thing | The use lines come first in a file | Move it up, under the scenario line |
| Two modules that use each other | The uses form no circle | Move the shared part into a third module |
| One name declared in a module and in the file that uses it | Each name is declared in one file of a model | Rename one, or write `change name:` |
| `change relief:` where no earlier file declares `relief` | A change gives its lines to a thing of an earlier file | Use the module, or write the lines in the thing |
| A scenario line or a variant line in a file that a `use` names | A module is part of the model of a package | Remove it |
| `variant "…"` in a file other than `variants/<name>/model.scn` | A variant is the entry file of a folder of the package's `variants/` | Move the file |
| `let xs = []` in a thing made without a template | An empty list takes its type from its slot | `let xs: [T]` in a template |
| `sum(Utility.unservd)` with no instance of `Utility` | An empty list still checks its names | The member's name |
| A cumulative output that can fall | A cumulative output never falls | `level` |
