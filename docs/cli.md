# The napkin command

`napkin` compiles, runs, samples, plays, formats and draws models. Each command is a module of
`napkin/commands/`. `napkin COMMAND --help` gives the arguments and an example of each command. The
words **model**, **package**, **variant**, **input**, **run**, **named run**, **edit**,
**breakpoint**, **checkpoint**, **record** and **path** have the meanings of
[the terms](language/README.md#terms).

```text
napkin [-h] [--version] COMMAND ...
```

| Command | What it does |
| --- | --- |
| [`compile`](#napkin-compile) | Compile a model. Print its diagnostics, or a summary of its program |
| [`run`](#napkin-run) | Run a model. Print the values of named paths at chosen times |
| [`sample`](#napkin-sample) | Run one run many times with drawn inputs. Print the spread of named values |
| [`play`](#napkin-play) | Run one run. Stop at breakpoints to show and edit its values |
| [`fmt`](#napkin-fmt) | Format `.scn` files |
| [`draw`](#napkin-draw) | Draw a static picture of the model as SVG |
| [`new`](#napkin-new) | Write a new package that compiles and runs as written |

MODEL is a package folder, or its `model.scn`. A variant is the folder of the variant, or its
`model.scn`: `napkin run demo/variants/east`. A MODEL that does not exist, a folder with no
`model.scn` and a file that is not a `.scn` file are usage errors.

The examples on this page ran in a folder that holds the `examples/` folder of this repository.

## Contents

1. [Diagnostics and exit codes](#diagnostics-and-exit-codes)
2. [napkin compile](#napkin-compile)
3. [napkin run](#napkin-run)
4. [napkin sample](#napkin-sample)
5. [napkin play](#napkin-play)
6. [napkin fmt](#napkin-fmt)
7. [napkin draw](#napkin-draw)
8. [napkin new](#napkin-new)
9. [The edit document](#the-edit-document)
10. [The run store](#the-run-store)

## Diagnostics and exit codes

A command writes each diagnostic on one line of the error stream:

```text
file:line:column: error: message [code]
file:line: warning: message [code]
```

The code names the rule ([compiler.md](compiler.md#diagnostics)). The file is relative to the
current folder when it is inside it. A warning refuses nothing.

Each warning `no_record` says that a part rests on no evidence
([compiler.md](compiler.md#the-evidence-gate)). `napkin compile` writes one line for each of these
warnings. Each other command writes one line that counts them:

```text
warning: 3 values have no record (napkin compile lists them) [no_record]
```

| Exit code | Meaning |
| --- | --- |
| 0 | The command did its work |
| 1 | Diagnostics: the model does not compile, the run stops before its horizon, the edit document does not hold, or the command cannot read or write a file |
| 2 | Usage: the command line is wrong, for example a MODEL, a path, a run or a time that the model does not have |
| 3 | `napkin play` only: the input ended, or `quit` came, before the end of the run |

A usage error prints the usage of the command and the message:

```text
usage: napkin run [-h] [--run NAME] [--edits FILE] [--at TIMES]
                  [--value PATHS] [--lag PATH=FROM..TO] [--json]
                  MODEL
napkin run: error: --value tunings_don: no named value of the model; did you mean tunings_done or tuners.done?
```

`napkin --help` and `napkin --version` load no compiler and no engine.

## napkin compile

```text
napkin compile [-h] [--json] MODEL
```

| Flag | What it does |
| --- | --- |
| `--json` | Print one JSON document |

The command compiles the model (`napkin.model.compile.load_scenario`). A model that does not compile
prints each problem and exits 1. A model that compiles prints a summary of its program:

- the default run: its mode, its horizon and its longest step;
- the named runs;
- the members (`entities`), each by its id;
- the inputs, the stored values (`stores`), the formulas, the distributions, the links and the
  collections, each by its path;
- the flows, each with its ends. A route is `a <-> b`. Each leg of a flow with legs has its own path;
- the units that the program spells;
- the model hash, which an edit document names.

The command also checks the stylesheet of the model: the `style.toml` of the variant, else of the
package ([draw.md](draw.md#where-the-file-is)). A problem of the stylesheet prints after the summary,
and the command exits 1.

```text
$ napkin compile examples/reservoir
examples/reservoir/model.scn: A reservoir in a storm
  run:           median, to 120 h, steps of at most 1 h
  entities:      reservoir, operator
  inputs:        reservoir.inflow, reservoir.spillway, reservoir.risk, operator.level
  stores:        reservoir.water, reservoir.gate, reservoir.spilled, reservoir.risk_time
  distributions: operator.forecast
  flows:         reservoir.storm: SOURCE -> reservoir.water, reservoir.spill: reservoir.water -> reservoir.spilled, reservoir.at_risk: SOURCE -> reservoir.risk_time
  units:         fraction, fraction/day, fraction/h, h, h/h
  model hash:    d52b453a4543108aec99dffe45966e7c02404279423a3e1af400a22bc4800dfc
```

**`--json`** prints one document with the keys `model`, `title`, `horizon` (in hours), `runs`,
`model_hash`, `entities`, `inputs` and `stores`. The other keys are `formulas`, `distributions`,
`links`, `collections`, `flows`, `units`, `diagnostics` and `warnings`. Each value has its `path`
and its `unit`. Each flow has its `path`, its `kind` (`directed`, `reversible` or `legs`), its
`source`, its `sink` and its `unit`. A flow with legs has its `legs` instead of its ends. Each
diagnostic and each warning has its `code`, `message`, `file`, `line` and `column`.

## napkin run

```text
napkin run [-h] [--run NAME] [--edits FILE] [--at TIMES] [--value PATHS] [--lag PATH=FROM..TO] [--json] MODEL
```

| Flag | What it does |
| --- | --- |
| `--run NAME` | Run the named run NAME. Without it, the command runs the default run: a median run to the horizon of the scenario line |
| `--edits FILE` | Apply the edit document FILE ([The edit document](#the-edit-document)) |
| `--at TIMES` | Report at these times, each a number and a unit of time of the model: `--at 12h,2days`. Without it, the start and the horizon. Repeatable |
| `--value PATHS` | Report these paths: `--value tank.water,clinic.delivery.actual_rate`. Without it, every named value. Repeatable |
| `--lag PATH=FROM..TO` | Report PATH as the mean of its history from TO to FROM before each time: `--lag unserved_volume=2h..6h`, or one delay, `--lag x=3h`. Repeatable |
| `--json` | Print one JSON document |

**What the table shows.** Without `--value`, the table has each named value in the order of the
file. A flow shows its actual rate, its request and its capacity under its line. A route also shows
its legs `forward` and `backward`. A flow with legs shows its `served_fraction` and then each leg.
Each value is in its declared unit, and a row of a member with a title shows the title in brackets.
A number has six significant figures. A number at most `atol_factor` times the largest magnitude of
its history shows as `0`.

A value of an occurrence, such as `tank.deliver#0.pipe.request`, is not in the default list.
`--value` names it. Before the occurrence starts, its value is `unavailable`.

**Under the table**, in this order:

1. each lag of `--lag`, with the proof that the value never falls. A value that can fall keeps its
   plain read, and a warning gives the reason;
2. the text of each case of a status display that the table shows;
3. the reason of each value that is `unavailable`;
4. the near-ties: the decisions of the run within the tolerance of their boundary
   ([docs/language/numerics.md](language/numerics.md#near-ties)). The table gives the five most
   frequent sources. `--json` gives every entry.

```text
$ napkin run examples/piano_tuners
Piano tuners: a median run to 8760 h
                          unit                 0 h        8760 h
tuners.rate               tunings/tuner/year   974.512    974.512
tuners.staff              tuner                3          3
tuners.need               tunings              5000       5000
tuners.due                tunings              5000       2076.46
tuners.done               tunings              0          2923.54
tuners.tune.actual_rate   tunings/h            0.333737   0.333737
tuners.tune.request       tunings/h            0.333737   0.333737
tuners.tune.capacity      tunings/h            0.333737   0.333737
tunings_done              tunings              0          2923.54
```

A lag needs the proof that its value never falls. Before the window reaches 0 h, the value is
`unavailable`:

```text
$ napkin run examples/piano_tuners --value tunings_done --lag tunings_done=1month..2months --at 0h,6months,1year
Piano tuners: a median run to 8760 h
                                   unit      0 h           6 months   1 year
tunings_done (lag 730 h..1460 h)   tunings   unavailable   1096.33    2558.1
tunings_done (lag 730 h..1460 h): the mean of its history from 1460 h to 730 h before each time; it never falls: what changes it adds to what it counts or moves within it: tuners.tune of tuners
tunings_done at 0 h: unavailable: the lag of tunings_done at 0 h reads it from -1460 h, before the run starts at 0 h: the record holds no value then
```

A run that stops before its horizon prints the values up to the time at which it stopped, then why,
and exits 1.

**`--json`** prints one document with the keys `model`, `title`, `run`, `edits`, `mode`, `horizon`,
`times` (in hours) and `values`. The other keys are `records`, `near_ties`, `stopped`, `violations`,
`attempts`, `placements`, `diagnostics` and `warnings`. Each entry of `values` has the `unit`, the
`label`, the member's `title`, the `values` at the times, the `lag`, the `note` and the evidence
`trail`. A value with no reading is `{"unavailable": reason}`. A status display is
`{"rating", "text", "case"}`.

## napkin sample

```text
napkin sample [-h] [--run NAME] [--edits FILE] [--value PATHS] [--at TIME] [--samples N] [--seed N] [--jobs N] [--exceed PATH=VALUE] [--json] MODEL
```

| Flag | What it does |
| --- | --- |
| `--run NAME` | Sample the named run NAME. Without it, the default run |
| `--edits FILE` | Apply the edit document FILE. An edit can give a distribution-valued input a distribution |
| `--value PATHS` | Report these paths. Without it, every named number. Repeatable |
| `--at TIME` | Report at this time. Without it, the horizon |
| `--samples N` | Run N samples (200 by default) |
| `--seed N` | The seed of the study (0 by default) |
| `--jobs N` | Run the samples on N processes. Without it, one process for each processor, and never more than the samples |
| `--exceed PATH=VALUE` | Also print the share of the samples in which PATH is above VALUE, in its unit. Repeatable |
| `--json` | Print one JSON document, with every sample |

The command runs a central run in `median` mode first. Then it runs the samples in `sampled` mode,
each with its own seed. A sample gives the same values alone, in a batch or in another process,
within the stated tolerances. For each value, the command prints:

- the central value and the mean of the samples;
- the middle 50% (p25 to p75) and the middle 90% (p5 to p95);
- from 1000 samples the 1-in-100 value (p99), and from 2000 samples the 1-in-200 value (p99.5);
- the three draws that move the value most, by rank correlation;
- for each `--exceed`, the share P(X > V) = k / n, with its 95% Clopper-Pearson interval.

```text
$ napkin sample examples/piano_tuners --value tunings_done --samples 100 --exceed tunings_done=3000
Piano tuners: the default run, 100 samples from the seed 0, at 8760 h
               unit      central   mean      p5        p25       p50       p75       p95
tunings_done   tunings   2923.54   2917.96   2356.71   2708.13   2924.74   3186.46   3394.27
tunings_done: moved most by tuners.rate.draw[0] of tuners (1.00)
P(tunings_done > 3000) = 41/100 = 0.41 (95% from 0.31262 to 0.512856)
```

A run whose samples draw nothing has no spread. The command says so and exits 0. A sample that stops
before the horizon refuses the whole study: the command exits 1, and the study leaves out no
sample.

**`--json`** prints one document with the keys `model`, `title`, `run`, `edits`, `samples`, `seed`,
`at`, `drawn`, `values`, `exceed`, `draws` and `warnings`. Each entry of `values` has the `unit`,
the `label`, the `central` value, `estimated`, `reason`, `mean`, `sd`, `sem`, `least`, `greatest`,
`percentiles`, `tails` and `drivers`. Each entry of `draws` is one sample: its `seed`, its `values`
and its `draws`. Each of its draws has its `site`, `owner` and `value` (a number in canonical
units).

## napkin play

```text
napkin play [-h] [--run NAME] [--edits FILE] [--break AT[@OWNER]] [--value PATHS] [--from FILE] MODEL
```

| Flag | What it does |
| --- | --- |
| `--run NAME` | Play the named run NAME. Without it, the default run |
| `--edits FILE` | Apply the edit document FILE before the run |
| `--break AT[@OWNER]` | Stop before this location. Repeatable |
| `--value PATHS` | Show these paths at each stop and at the end. Without it, a stop shows the values of its member and of its occurrence, and the end shows every named value |
| `--from FILE` | Go on from a checkpoint that `save FILE` wrote |

The command plays one run with a `napkin.session.Session` ([python-api.md](python-api.md#session)).
Give `--break` or `--from`. The two together are a usage error, because a checkpoint keeps its own
breakpoints.

**A location** is the origin of a part of the compiled program
([docs/language/events.md](language/events.md#breakpoints-checkpoints-and-edits)):

| Location | Example | The run stops |
| --- | --- | --- |
| An event | `operator.decide` | Before the first step of each occurrence |
| A stage | `operator.decide.step[0]` | Before the stage |
| A statement | `operator.decide.step[0].do[1]` | Before the statement, inside its stage |
| A statement of the setup | `setup[0]` | Before the statement |

`AT@OWNER` stops for one member (`@operator`) or one occurrence (`@operator.decide#0`) only. A
location that the model does not have is a usage error, with the closest names. A breakpoint in the
body of a trigger is a usage error too.

**At a stop**, the command prints the number of the stop, its time, and the location with its kind
and its place in the file. It also prints the occurrence and what runs next. Then it shows each
value, with what an edit can give it and its label. Then it reads lines after the prompt `> `:

| Line | What it does |
| --- | --- |
| `PATH = VALUE` | Edit a live stored value: a number in the value's declared unit, an enum member, `true` or `false`, or a text. The engine checks the edit. When the engine refuses it, the command prints the reason |
| `save FILE` | Write the stop, with its edits, to the checkpoint FILE |
| `go` | Go on to the next stop, or to the end |
| `quit` | Stop here. The command exits 3 |

When the input ends before the run, the command stops there and exits 3. At the end of the run, the
command prints the values at the start and at the horizon, as `napkin run` does. Then it prints each
edit that the run took.

```text
$ printf 'operator.decide#0.order = WAIT\nsave stop.checkpoint\ngo\n' | napkin play examples/reservoir --break 'operator.decide.step[0].do[1]' --value reservoir.water,reservoir.gate,operator.decide#0.order
A reservoir in a storm: a median run to 120 h

Stop 1 at 40 h: before operator.decide.step[0].do[1] (switch at examples/reservoir/model.scn:55), in operator.decide#0 of operator.
Next: operator.decide.step[0] of operator.decide#0, from its start.
Drawn in this stage before the stop: operator.decide.step[0].do[0].draw[0] = OPEN.
  reservoir.water           0.7 fraction   edit: a number         Water in the reservoir
  reservoir.gate            CLOSED         edit: CLOSED or OPEN   Spillway
  operator.decide#0.order   OPEN           edit: OPEN or WAIT
Edit with PATH = VALUE, or: save FILE, go, quit.
> operator.decide#0.order = WAIT
  operator.decide#0.order: OPEN -> WAIT
> save stop.checkpoint
  saved; go on with: napkin play examples/reservoir --from stop.checkpoint
> go

The run ends at 120 h.
                          unit       0 h           120 h
reservoir.water           fraction   0.6           0.9
reservoir.gate                       CLOSED        CLOSED
operator.decide#0.order              unavailable   WAIT
operator.decide#0.order at 0 h: unavailable: operator.decide#0 has not started at 0 h
edit at 40 h, before operator.decide.step[0].do[1]: operator.decide#0.order OPEN -> WAIT
```

The edit to `WAIT` keeps the spillway closed, so the water rises to 0.9. `--from` goes on from the
saved checkpoint, in this process or a fresh one. The command refuses by name a checkpoint of
another program, engine or run. Here the input ends with `quit`, so the command exits 3:

```text
$ printf 'reservoir.water = 0.65\nquit\n' | napkin play examples/reservoir --from stop.checkpoint --value reservoir.water
A reservoir in a storm: a median run to 120 h

Stop 1 at 40 h: before operator.decide.step[0].do[1] (switch at examples/reservoir/model.scn:55), in operator.decide#0 of operator.
Next: operator.decide.step[0] of operator.decide#0, from its start.
Drawn in this stage before the stop: operator.decide.step[0].do[0].draw[0] = OPEN.
  reservoir.water   0.7 fraction   edit: a number   Water in the reservoir
  edited here: operator.decide#0.order = WAIT
Edit with PATH = VALUE, or: save FILE, go, quit.
> reservoir.water = 0.65
  reservoir.water: 0.7 fraction -> 0.65 fraction
> quit
The run stops at its stop 1, before its end.
```

## napkin fmt

```text
napkin fmt [-h] [--check] FILE [FILE ...]
```

| Flag | What it does |
| --- | --- |
| `--check` | Write nothing. List the files that would change, and exit 1 if any |

Each FILE is a `.scn` file, or a folder. The command finds the `.scn` files below a folder, outside
the folders and files whose names start with a dot. The formatter is the language's own
([compiler.md](compiler.md#lex-parse-and-format)). It writes each line again from its parsed form, so
a formatted file does not change. The command writes only the files that change, and lists them.
A file that the parser cannot read prints its problem, and the command exits 1.

```text
$ napkin fmt --check examples/piano_tuners
1 file checked, all formatted
```

## napkin draw

```text
napkin draw [-h] [--run NAME] [--style FILE] [-o FILE] [--latex FILE] MODEL
```

| Flag | What it does |
| --- | --- |
| `--run NAME` | Draw the named run NAME. Leave out the events that cannot start in it, with their lines and arrows |
| `--style FILE` | Use FILE in place of `style.toml` |
| `-o FILE` | Write the SVG to FILE. Without it, `<package>[.<variant>][.<run>].svg` in the current folder |
| `--latex FILE` | Also write the equations, symbols and references of `[equations]` as a LaTeX fragment (amsmath, longtable, hyperref) |

Without `--run`, the command draws a model with one named run as that run. It draws a model with
several named runs with its runs joined. [draw.md](draw.md) describes the picture and `style.toml`.

```text
$ napkin draw examples/piano_tuners -o tuners.svg
tuners.svg: 1 thing, 0 arrows
```

A stylesheet with a problem prints its diagnostics, and the command writes no file (exit 1). A
picture taller than a PDF page holds prints a note.

## napkin new

```text
napkin new [-h] [--title TEXT] [--variants NAME,…] DIR
```

| Flag | What it does |
| --- | --- |
| `--title TEXT` | The title of the scenario. Without it, "A new scenario" |
| `--variants NAME,…` | Also write `variants/NAME/model.scn` for each NAME. A name is a small letter, then small letters, digits and `_` |

The command writes `DIR/model.scn` and `DIR/style.toml`. The model has one entity with an input, two
stocks and a flow between them. It also has one formula at the top level, and one `record`
declaration that each value cites. It uses the prelude's units only. The stylesheet gives the entity
its role in the picture (`[role]`), because the model has no role. Each variant changes the input to
its own value. The command writes no file when one of its files is there already (exit 2).

```text
$ napkin new demo --title "A clinic queue" --variants east,west
Wrote demo/model.scn and its picture, demo/style.toml, and the variants east and west in demo/variants/.
It compiles and runs as written: napkin run demo; napkin run demo/variants/east; napkin run demo/variants/west

Replace next, in demo/model.scn:
  - the title, "A clinic queue", and the lines summary, horizon and scope under it;
  - the inputs, each with its value, its range and its text: service.rate (each variant changes its value);
  - the records, which each value cites: guess. Give each value a record of its own.
After each change, `napkin compile demo` checks the model (docs/language/README.md describes each line).
```

## The edit document

An edit document is one JSON object. `--edits FILE` reads it for `run`, `sample` and `play`. The
schema is `napkin/schema/edits.schema.json`. `napkin/model/runs.py` applies it, and
`napkin/commands/common.py`, `edits_of`, reads the file.

| Key | Value |
| --- | --- |
| `schema_version` | `"0.0.1"`, the version of the edit document (`napkin.SCHEMA_VERSION`). Required by the schema; `--edits` adds it when the file has none |
| `model_hash` | The model hash that `napkin compile` prints. Required by the schema; `--edits` adds the hash of the model when the file has none |
| `reason` | A text: the reason for the edits |
| `set` | The edits of every run: `{input path: value}` |
| `options` | The edits of the runs that take an option: `{option name: {input path: value}}` |
| `runs` | The edits of one named run: `{run name: {input path: value}}` |

No other key is allowed. A document made for another revision of the model keeps its `model_hash`,
and the command refuses it.

**An input path** names one input:

- `member.input`: an input of an entity, of a member written by hand, or of a row of a table by its
  id (`sites.clinic.level`);
- `Template.instances.input`: the input of every member of a template;
- `input`: an input of the top level.

**A value** follows the declared type of the input:

| Type of the input | JSON value | Example |
| --- | --- | --- |
| A number | A number, in the input's own unit | `3` |
| A number | A text: a number and a unit of the same dimension | `"0.5 days"` |
| A yes/no | `true` or `false` | `true` |
| An enum | A text: a member of the enum | `"BUSY"` |
| A text | A text | `"The human team"` |
| A distribution | A text: a distribution as a model writes it | `"pert(48 h, 96 h, 200 h)"` |

A number must be in the range of the input when the bounds are numbers. The command reads JSON
numbers exactly, and refuses a key that comes twice and a number that is not finite.

**Precedence.** The first of these that gives an input its value wins:

1. an edit of the run (`runs`);
2. an edit of one of the run's options (`options`);
3. an edit of every run (`set`);
4. an option of the run;
5. the model: a `change`, then a member's own line, then the template.

At each of the first four levels, an edit of one member wins over an edit of every member of its
template. Two options of one run that set one input are an error. Two edits under `options` that meet
in one run and set one input are an error too, also when they are equal. An edit of an option that no
run takes changes no run.

**One transaction.** The command checks the document whole, in every run of the model, before any run
takes its values. Each problem names its place in the document:

| Code | Problem |
| --- | --- |
| `schema` | The document does not follow the schema |
| `model_hash` | The document is for another revision of the model |
| `reference` | An option or a run that the model does not have |
| `input` | A path that names no input. A stored value, a formula and a link are no inputs |
| `value`, `bool`, `unit`, `range` | A value of the wrong type, of an unknown unit or outside the range |
| `meeting` | Two edits of the options of one run set one input |

This document edits the incident example at three levels:

```json
{
  "reason": "Slower detection in every run; a longer containment with the rapid response",
  "set": {"response.detection_delay": "5 h"},
  "options": {"Rapid response": {"response.containment_delay": 3}},
  "runs": {"rapid_response": {"attack.work_per_attempt": "0.5 days"}}
}
```

```text
$ napkin run examples/incident_response_tempo --run rapid_response --edits edits.json --value attack.admitted,attack.blocked,queue.completed,response.phase --at 0h,6h,12h,24h
Attack tempo and incident response: the run rapid_response, a median run to 24 h, with the edits of edits.json
                  unit   0 h          6 h          12 h        24 h
attack.admitted          1            2            2           2
attack.blocked           0            0            2           5
queue.completed   h      0            1            7           19
response.phase           UNDETECTED   RESPONDING   CONTAINED   CONTAINED
Near-ties (1 total, from 0 h to 0 h)
source                            kind   count   first   last
response.first_incident.when[0]   fire   1       0 h     0 h
See near_ties in napkin run --json for every entry.
```

The command prints each problem of a document and exits 1. This document `bad.json` has five
problems:

```json
{
  "model_hash": "0000",
  "set": {"response.detection": "5 h", "attack.admitted": 3},
  "options": {"Rapid": {"response.containment_delay": true}}
}
```

```text
$ napkin run examples/incident_response_tempo --edits bad.json
bad.json: error: the edits are for another revision of the model [model_hash]
bad.json: error: options/Rapid: is no option of the model [reference]
bad.json: error: set/response.detection: response.detection names no input of the model [input]
bad.json: error: set/attack.admitted: attack.admitted is a state value: an edit sets an input [input]
bad.json: error: options/Rapid/response.containment_delay: containment_delay is h: it takes no true or false [value]
```

In Python, `napkin.engine.study.edits_for(model, edits)` adds the version and the hash to a
document, and `Compiled.configure(run, edits)` applies it ([python-api.md](python-api.md)).

## The run store

`napkin run` and `napkin sample` keep the record of each run in the run store (`napkin/store.py`).
The command reads a run that the store holds, and does not run it again. The key of a run is a
digest of these parts:

- the canonical bytes of the program;
- the configuration and its request;
- the code of the engine;
- the versions of Python, numpy and scipy, and the machine.

A label is in no key, so a new label reads the stored run.

| Variable | What it does |
| --- | --- |
| `NAPKIN_STORE` | The folder of the store, or `off` to turn the store off. Without it, `.cache/runs` in a source checkout, else `~/.cache/napkin/runs` (or under `XDG_CACHE_HOME`) |
| `NAPKIN_STORE_LIMIT` | The size limit of the store in gigabytes (4 by default). Above it, the least recently used runs go |
