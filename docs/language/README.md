# The napkin language

This reference gives the rules of the napkin language, version 0.2.3. It tells what each line of a
`.scn` file means and what the engine does with it. Every rule here is the rule of the compiler and
the engine in this repository. Each example is a model, or a part of a model, that compiles.

`napkin compile` checks a model, and `napkin run` runs it ([cli.md](../cli.md)). The Python API
gives the same steps to a program ([python-api.md](../python-api.md)). For a guided start, read
[modeling-guide.md](../modeling-guide.md) first.

## Contents

1. [What a model is](#what-a-model-is)
2. [The files of a package](#the-files-of-a-package)
3. [The language on one page](#the-language-on-one-page)
4. [Terms](#terms)
5. [The pages of this reference](#the-pages-of-this-reference)

## What a model is

A **model** is the text that the compiler reads: a `model.scn` file and the files beside it. The
model says:

- which members exist and which values they hold;
- which flows move quantities between them;
- which events change them;
- which evidence supports each number.

The compiler reads the model and makes a program. The program is a versioned file that the
engine runs without the parser ([compiler.md](../compiler.md)). One **run** calculates the program
from time 0 to the horizon and gives one **record**. A caller then reads any value of the record at
any time. The model has no report block: the caller selects the paths and the times.

A model has these parts:

| Part | What it says | Page |
| --- | --- | --- |
| Values and types | What each member holds, in which unit, in which range | [values-and-types.md](values-and-types.md) |
| Flows and solvers | How quantities move per hour, and who decides the rates | [flows-and-solvers.md](flows-and-solvers.md) |
| Events | What happens at a time, and what starts it | [events.md](events.md) |
| Numerics | How two numbers compare, and what a scale changes | [numerics.md](numerics.md) |
| Evidence | Which `record` supports each number | [evidence.md](evidence.md) |

## The files of a package

A **package** is a folder that holds a model, its tables, `units.json`, `style.toml`, `roles.toml`
and its variants. The name of the folder is the name of the scenario. No file of the package writes
that name.

| File | What it holds | What reads it |
| --- | --- | --- |
| `model.scn` | The main file. Its first declaration is `scenario "Title"`. | The compiler |
| Other `.scn` files | The modules of the package. A `use` line names each one. | The compiler |
| `variants/<name>/model.scn` | A variant. Its first declaration is `variant "Title"`. | The compiler |
| A `.csv` file | The rows of a table (`sites: Place from "places.csv"`) | The compiler |
| `units.json` | The units of the package, beside the units of the prelude and of the library | The compiler |
| `evidence/sources.json`, `evidence/claims.json`, `evidence/assumptions.json` | The sources, claims and assumptions that the `record` declarations name | The compiler |
| `style.toml` | The picture of the model, and the `[role]` of each member in the picture | `napkin draw`, and `napkin compile` checks it |
| `roles.toml` | Who plays each part of the scenario | The wrapper of the scenario (a publisher or a user interface) |

Each file except `model.scn` is optional. No run reads `style.toml` or `roles.toml`.

### The role of each file

The first declaration of a `.scn` file gives the file its role. Comments can come before it.

- `scenario "Title"` starts the main file of a package.
- `variant "Title"` starts a variant. A variant reads the main file of its package first.
- A file that starts with any other declaration is a **module**.

A module stands in the package folder or in a folder of it. The line `use parts` reads
`parts.scn`, and `use water.pumps` reads `water/pumps.scn`. The compiler reads each module once,
after the modules that it uses. A circle of `use` lines is an error. All the files of a model are
one model: a line in one file can name a member of another file.

### The scenario line

The scenario line names the model and holds the lines of the default run under it.

```scn
scenario "Piano tuners"
    summary "The tuners of a town tune the pianos that need a tuning."
    horizon 1 year
    scope "The pianos of one town."
    resolution 1 day
```

| Line | What it gives |
| --- | --- |
| `summary "…"` | One or two sentences about the model |
| `horizon D` | The end of the default run, a time such as `30 days`. A package needs it. |
| `scope "…"` | Whom or what the values cover |
| `library "PATH"` | The folder of a shared library of units and evidence (its `vocabulary.json`), from the folder of the main file |
| `resolution D` | The longest step of the integration (`max_step`) in the default run |

A variant writes its own scenario line. Each line that it writes replaces the line of the main
file. A variant cannot name a library: it reads the library of its package. The title of a variant
is the title of its package, a colon and its own title (`Every construct: Wet`).

### Options and named runs

An option sets inputs. A **named run** takes options. The main file declares both.

```scn
options "Fill":
    "Usual fill":
        "The plant fills at its own rate."
    "Quick fill":
        "The plant fills at 4 L/h."
        plant.rate = 4 L/h  @fixture

runs:
    usual = "Usual fill"
    quick = "Quick fill"
        "The quick fill"
```

- `options "Group":` holds a group of options. Each option is `"Name":`, with its text and the
  inputs that it sets under it. An option sets only an **input**, by its full path. The path
  `Pump.instances.rate` sets the input of each member of the template `Pump`.
- `runs:` holds the named runs. A run takes one option of a group at most, with `+` between the
  options: `both = "Quick fill" + "Large tank"`.
- Two options of one run must not set the same input.
- A number or a Boolean that an option sets needs a `record`. Without one, the model does not
  compile ([evidence.md](evidence.md#values-that-an-option-or-a-change-sets)).

The default run is a median run to the horizon of the scenario line. It takes no option. The
order of precedence of edits, options and the model is in
[values-and-types.md](values-and-types.md#where-a-value-comes-from).

### Variants and changes

A variant is a model for one place or case. It reads the main file of its package, and then its own
lines. A `change` line in a variant gives a member of an earlier file a new value or a new link.

```scn
variant "Wet"

change reservoir:
    water = 30 L  @fixture
```

- `change name:` names an entity, a template or a member that an earlier file declares.
- A line under it gives a new initializer, of the same kind and type as the declaration.
- A `change` of a template gives the template a new initializer. A member whose own line gives
  the value keeps its own line. A `change` of a member replaces its own line.
- A `change` can also give a new text, a new `title` and new evidence.
- Two `change` lines for one value are an error, in any order of the files.
- A variant has its own program. An option or an edit only configures a run of a program.

### Notes

`notes:` holds the notes of the authors and the reviewers. No calculation reads them. A note is
`key: value`, where the value is a text, a number with no unit, a word or a list in brackets. A
note can hold other notes under it, and evidence. The notes of several files merge key by key.

```scn
notes:
    by: "The fixture"
```

## The language on one page

This model is complete. It compiles and runs as written, with a `units.json` that defines `L`.

```scn
scenario "A clinic tank"
    summary "A pump fills a tank and a clinic draws water from it. An operator brings more water when the tank is low."
    horizon 12 h
    scope "One tank and one clinic."

tank:
    "The water tank of the clinic."
    water: L = 40 L in [0 L, 100 L]  @survey
        "Water in the tank"
    low = formula(this.water <= 10 L)
        "The tank is low"
    refill = event(amount: L):  @operator
        "The operator brings water by truck."
        when this.low:
            this.refill.start(30 L)
        after 1 h:
            this.water += amount

pump:
    input rate: L/h = 4 L/h in [0 L/h, 10 L/h]  @survey
        "Rate of the pump"
    flow fill: SOURCE -> tank.water
        request = formula(this.rate)

clinic:
    flow use: tank.water -> SINK
        request = 8 L/h

refills = formula(count(tank.refill.occurrences))
    "Refills started"

record survey: assumption "The example assumes these sizes and rates."
record operator: assumption "The example assumes that the operator brings water when the tank is low."
```

The tank loses 4 L/h net: the pump puts in 4 L/h and the clinic takes 8 L/h. At 7.5 h the water
reaches 10 L, and the trigger starts the event. One hour later the stage adds 30 L. This is the
output of `napkin run` for the package, with `--at 0h,7.5h,8.5h,12h`:

```text
A clinic tank: a median run to 12 h
                         unit   0 h     7.5 h   8.5 h   12 h
tank.water               L      40      10      36      22
tank.low                        false   true    false   false
pump.rate                L/h    4       4       4       4
pump.fill.actual_rate    L/h    4       4       4       4
pump.fill.request        L/h    4       4       4       4
clinic.use.actual_rate   L/h    8       8       8       8
clinic.use.request       L/h    8       8       8       8
refills                         0       1       1       1
```

### The lines of a file

| Where | Line | Page |
| --- | --- | --- |
| Top level | `scenario "…"`, `variant "…"`, `use a.b` | This page |
| Top level | `name:` (an entity), `Name:` (a template), `name: Template` (an instance) | [values-and-types.md](values-and-types.md#members-templates-and-instances) |
| Top level | `name: Template from "file.csv"` (a table) | [values-and-types.md](values-and-types.md#tables) |
| Top level, entity, template | `name = value`, `name: type = value`, `readonly …`, `input …` | [values-and-types.md](values-and-types.md#declare-a-value) |
| Top level | `a.b.request = value` (an initializer of the setup scope) | [values-and-types.md](values-and-types.md#initializers-of-the-setup-scope) |
| Top level | `tank.fill.start(5 L)` (a start of the setup scope) | [events.md](events.md#start-an-event) |
| Top level, entity, template | `assert C` | [events.md](events.md#assertions) |
| Entity, template | `flow name: a -> b`, `flow name: a <-> b`, `flow name:` with legs | [flows-and-solvers.md](flows-and-solvers.md) |
| Entity, template | `name = event(…):` | [events.md](events.md) |
| Entity, template | `name = solver:` | [flows-and-solvers.md](flows-and-solvers.md#declared-solvers) |
| Entity, template | `status ok when C` (a status display) | [values-and-types.md](values-and-types.md#status-displays) |
| Entity, template, instance | `"Text"`, `title "Text"` | [values-and-types.md](values-and-types.md#text-and-titles) |
| Top level | `record name: kind "…"` | [evidence.md](evidence.md) |
| Top level | `options "…":`, `runs:`, `notes:`, `change name:` | This page |

### Lines and text

- A level of nesting is four spaces. A tab is an error.
- A `#` outside a text starts a comment. The comment runs to the end of the row.
- A text is in double quotes. Its only escapes are `\"` and `\\`. A text can continue on rows that
  are indented deeper than its first row.
- An expression continues on the next row only inside `(` or `[`.
- The name of a value starts with a small letter. A name with a capital first letter is a template
  or a member of an enum.
- These words name nothing else: `true`, `false`, `this`, `t`, `SOURCE`, `SINK`, `and`, `or`,
  `not`, `if`, `else`, `in`, `from`, `to`, `when`, `after`, `until`, `reset`, `switch`, `move`,
  `assert`, `flow`, `record`, `readonly`, `input`, `formula`, `event`, `solver`, `enum`, `bool`
  and `scale`. Two more words are reserved because the old language used them
  ([changes.md](changes.md)). The keywords of Python are free names.
- `napkin fmt` writes a file in the layout of the formatter. The layout keeps each order that
  changes the meaning of the model.

## Terms

Each term below has one meaning in the napkin documentation. The other pages use these terms in
these meanings, and only these terms for these concepts.

| Term | Meaning |
| --- | --- |
| **model** | The text that the compiler reads: a `model.scn` file and the files beside it. |
| **package** | A folder that holds a model, its tables, `units.json`, `style.toml`, `roles.toml` and variants. |
| **variant** | A folder inside a package that holds a model for one place or case. |
| **entity** | A named member at the top level of a model (`tank:`, or `north: Utility`). |
| **template** | A declared type of member (`Place:`). Its members are **instances**. |
| **instance** | A member of a template: a member written by hand (`north: Utility`) or a row of a table. |
| **value** | A named quantity, Boolean or enum that a member holds. |
| **input** | A value that a named run or an edit can set before the run (`input rate = …`). |
| **formula** | A value that the engine calculates from other values when it reads it (`formula(…)`). |
| **stock** | A value that a flow or a `move` touches. The engine keeps an exact balance for each stock. |
| **flow** | A transfer of a quantity per time between two stocks, or between a stock and `SOURCE` or `SINK`. |
| **route** | A flow in both directions (`<->`). A route has two **legs**, one for each direction. |
| **leg** | One direction of a route (`forward`, `backward`), or one transfer of a flow with legs. |
| **request** | The rate that a flow asks for. A request is soft. |
| **capacity** | The limit of the rate of a flow. A capacity is hard. |
| **actual rate** | The rate that a flow gets (`actual_rate`). |
| **solver** | A declared solver that an entity owns. It sets the rates and values that it names in `solve_for`. |
| **event** | A declared activity with stages. |
| **occurrence** | One start of an event. |
| **stage** | A block of statements in an event that runs at one time (`after D:`). |
| **trigger** | A `when` condition that the engine monitors and that starts an event or a stage. |
| **moment** | A time at which the engine stops the continuous calculation to run stages or to process a contact. |
| **run** | One calculation of a model from time 0 to the horizon. |
| **named run** | A run that the model declares under `runs:`. |
| **configuration** | The horizon, the named run, the edits and the numerical settings of a run. |
| **record** | The result of a run. |
| **reading** | The value of a path at a time in a record. |
| **path** | The dotted name of a value, for example `plant.water`. |
| **scale** | The numerical size of a value (`scale`). It sets the comparison band and the integration accuracy. |
| **comparison band** | The interval inside which two numbers compare equal. |
| **edit** | A change of an input or a value that a run applies at a breakpoint or before the run. |
| **breakpoint** | A place where a run stops. |
| **checkpoint** | The saved state of a run at a breakpoint. |
| **method** | The engine part that calculates one connected set of stocks (a `Way` in the code: Lines, Family, Component, Sparse, Declared, MovingDeclared). |
| **study** | A group of runs, for example the samples of a Monte Carlo calculation. |

The keyword `record` also declares evidence (`record survey: assumption "…"`). This reference always
writes that declaration in code type, as a `record` declaration. The word record alone means the
result of a run.

These words name parts of the language. Each page uses them in these meanings.

| Word | Meaning |
| --- | --- |
| member | An entity, an instance, an event, a flow or an occurrence: a thing with values of its own. |
| link | A value that names one member (`origin: Place`). It is fixed for the run. |
| collection | A group of distinct members of one type, each with a numeric key (`<Place>`). |
| key | The number by which a collection orders and finds its members. |
| projection | A field of each member of a collection (`Place.instances.need`). |
| reduction | `sum`, `count`, `any`, `all`, `min` or `max` of a projection. |
| endpoint | The `outflow` or the `inflow` of a stock: the flows that leave it or enter it. |
| allocation | The rule by which an endpoint shares a limit among its flows (`priority(…)`, `proportional()`). |
| distribution | A description of a random number or enum member (`uniform(1 h, 3 h)`). |
| draw | One value that `.draw()` takes from a distribution. |
| contact | The time at which a stock reaches a bound or a threshold between two scheduled times. |
| near-tie | A decision that two numbers inside their comparison band made. The trace marks it. |

## The pages of this reference

| Page | What it holds |
| --- | --- |
| [values-and-types.md](values-and-types.md) | Declarations, types, units, members, links, titles, collections, formulas, distributions, scopes, tables and status displays |
| [flows-and-solvers.md](flows-and-solvers.md) | Flows, endpoints, routes and legs, `SOURCE` and `SINK`, requests and capacities, local allocation and declared solvers |
| [events.md](events.md) | Events, stages, triggers, occurrences, time, `move`, assignments, assertions, breakpoints, checkpoints and edits |
| [numerics.md](numerics.md) | The comparison band, exact literals, scales, near-ties and reproducibility |
| [evidence.md](evidence.md) | `record` declarations, citations, the datum rule and the warnings of the evidence rule |
| [changes.md](changes.md) | Each word and form of the old language, and what replaced it |

Other pages of the documentation:

- [docs/README.md](../README.md): the start of the documentation.
- [modeling-guide.md](../modeling-guide.md): how to write a model, step by step.
- [engine/README.md](../engine/README.md), [engine/methods.md](../engine/methods.md) and
  [engine/solver.md](../engine/solver.md): how the engine calculates a run.
- [compiler.md](../compiler.md): the program and its side table.
- [cli.md](../cli.md) and [python-api.md](../python-api.md): the commands and the Python API.
- [design/decisions.md](../design/decisions.md): the rulings D0 to D17 and the changes 1 to 29.
