# The napkin command

`napkin COMMAND [ARGS] [TARGET]` compiles, runs, plays, samples, draws, starts and
formats models in `.scn` files. `python -m napkin` is the same command. `napkin --help` lists the commands,
`napkin COMMAND --help` gives the flags and an example of each command, and `napkin --version`
gives the version:

```
$ napkin --version
0.0.1
```

| Command | What it does |
| --- | --- |
| [`compile`](#napkin-compile) | Reads, checks and proves a scenario and each of its variants, and lists what it offers |
| [`run`](#napkin-run) | Runs the runs of a scenario and prints their outcomes |
| [`play`](#napkin-play) | Runs one run step by step; you, or a program with `--json`, pick the decisions |
| [`sample`](#napkin-sample) | Runs one run many times with drawn inputs, and prints the spread of each outcome |
| [`draw`](#napkin-draw) | Draws a static picture of the model as SVG |
| [`new`](#napkin-new) | Starts a scenario that compiles and runs as written |
| [`fmt`](#napkin-fmt) | Formats `.scn` files |

The examples on this page run from the root of a checkout, which holds `examples/` and `scenarios/`.

## Exit codes

| Code | When |
| --- | --- |
| 0 | The command did its work: every model compiles, the study is admitted, the play is finished, the files are formatted. |
| 1 | Diagnostics: a model that does not compile, a stylesheet with a problem, a study or an edit document that the engine refuses, a play log of another play, or a file that `fmt --check` would change. |
| 2 | The command line is wrong: an unknown flag, variant, run, option, unit of time or output of `--exceed`, a `--set` that is not `NAME=VALUE`, a path that is no TARGET, or a variant or a run that the command needs and the line does not name. |
| 3 | `play` only: the input ends before the run does. |

A usage error (exit 2) prints the command's usage line, then one line `napkin COMMAND: error: …`.
A name that names nothing gets the closest names:

```
$ napkin run scenarios/water_controls_wipe --variant juneau --run early
usage: napkin run [-h] [--variant NAME] [--run NAME] [--option [GROUP=]OPTION]
                  [--set NAME=VALUE] [--at TIME,…] [--edits FILE] [--events]
                  [--json [full]] [--no-store]
                  [TARGET]
napkin run: error: early is not a run of water_controls_wipe:juneau; did you mean early_kept?
```

Diagnostics (exit 1) go to the standard error, one line each, as a compiler writes them:
`file:line:column: severity: message (path; run NAME)`. The parentheses name the place in the model
and the run, when there are any. Here line 11 of a model from [`napkin new`](#napkin-new) has a
wrong unit, `people/dya`:

```
$ napkin compile demo
demo/model.scn:11:5: error: Unregistered unit 'people/dya' (service/rate)
```

## Targets and variants

The TARGET of `compile`, `run`, `play`, `sample` and `draw` names one package or one variant:

- a scenario folder, whose `model.scn` starts with `scenario`, or that `model.scn`;
- a variant folder, `variants/NAME/` of a package, or its `model.scn`.

Without a TARGET, the command takes the current folder, `.`. Another `.scn` file is a module of a
package, not a TARGET, and the command refuses it (exit 2). So does a path that does not exist, or a
folder without a `model.scn`.

A package with variants runs as its variants. The main file is part of each variant, and each
variant is a model of its own, `package:variant` ([language.md](language.md), §2.12). `--variant
NAME` picks one. `compile` compiles every variant when `--variant` names none. `run`, `play`,
`sample` and `draw` need one variant: without `--variant`, they list each variant with its title,
and stop (exit 2):

```
$ napkin run scenarios/water_controls_wipe
usage: napkin run [-h] [--variant NAME] [--run NAME] [--option [GROUP=]OPTION]
                  [--set NAME=VALUE] [--at TIME,…] [--edits FILE] [--events]
                  [--json [full]] [--no-store]
                  [TARGET]
napkin run: error: water_controls_wipe has 16 variants: pick one with --variant NAME
  asheville      Asheville, North Carolina
  auburn         Auburn, Washington
  …
  richmond       Richmond, Virginia
  washington_dc  Washington, DC
```

An unknown variant gets the closest names (`junea is not a variant of water_controls_wipe; did you
mean juneau?`). A variant folder as the TARGET and a `--variant` with another name is a usage error.

## Runs

`--run NAME` names a run of the model's `runs:` lines. Each command finds the runs in the files
before the model compiles. So an unknown run is a usage error (exit 2) with the closest names, and
the command compiles nothing. A model with no `runs:` and no options has one run, `base`.

- `run` runs every run, or each run that a `--run` names (repeatable).
- `play` and `sample` take one run: the run of `--run`, or the only run of the model. A model with
  several runs and no `--run` lists each run with its label, and the command stops (exit 2).
- `draw` draws the run of `--run`, or the only run. A model with several runs and no `--run` is
  drawn with every run joined.

```
$ napkin sample scenarios/water_controls_wipe --variant washington_dc --edits scenarios/water_controls_wipe/variants/washington_dc/spreads/uncertainty.json
usage: napkin sample [-h] [--variant NAME] [--run NAME]
…
napkin sample: error: water_controls_wipe:washington_dc has 6 runs: pick one with --run NAME
  early_kept             Early response · Keeps hidden access
  standard_kept          Standard response · Keeps hidden access
  delayed_kept           Delayed response · Keeps hidden access
  delayed_none           Delayed response · No hidden access
  delayed_kept_human     Delayed response · Human team keeps hidden access
  delayed_kept_aqueduct  Delayed response · Keeps hidden access · The Aqueduct only
```

**Which runs the engine checks.** `compile` checks every run of each model. `run --run X`, `play`
and `draw --run X` check the model for X only, and `sample --run X` for X and the runs that X is
compared with. Each says so: `checked for run X only; napkin compile checks every run`. `play`
always checks its one run only. `run`, `sample` and `draw` without `--run` check every run. The check
of a run is the check of its inputs and the proofs of its structure.

## napkin compile

```
usage: napkin compile [-h] [--variant NAME] [--inputs] [--outputs] [--json]
                      [TARGET]
```

`compile` reads, checks and proves each model that the TARGET names, with every run checked. It also
checks the files that only the tools read:

- the stylesheet of each model: the variant's own `style.toml`, else its package's
  ([draw.md](draw.md));
- for a package with variants, compiled whole, the records of the package's folder that no variant
  uses. Each is a diagnostic at the line of its `"id"` in its JSON file.

Then it lists what the package offers: its variants, its runs, the options of each group with their
real names, and each actor with its choices. The last line counts the values that rest on
evidence. A value is a line of a file that cites records, counted once also when several variants
read it. It is sourced when one of its records is a `source` or a `source_transfer`, and assumed
when one of them is an `assumption`. Identities and conventions count as neither.

```
$ napkin compile examples/reservoir
reservoir  A reservoir in a storm
  runs:     base (1)
  actors:   operator: operator.decide (open, wait)
  compiled · evidence: 0 sourced values, 7 assumed
```

| Flag | What it does |
| --- | --- |
| `--variant NAME` | Compiles only this variant (default: every variant). |
| `--inputs` | Also lists each input: its value or distribution, its range, the kinds of its records and its label. |
| `--outputs` | Also lists each output: its unit, its kind, its label and its scope. |
| `--json` | Prints all of it as one JSON document ([JSON documents](#json-documents)). |

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
```

Exit 0 when every model compiles and every check holds (a warning does not fail it), 1 for any
error, 2 for a wrong command line. The listing goes to the standard output, and the diagnostics to
the standard error.

## napkin run

```
usage: napkin run [-h] [--variant NAME] [--run NAME] [--option [GROUP=]OPTION]
                  [--set NAME=VALUE] [--at TIME,…] [--edits FILE] [--events]
                  [--rows NAME,…] [--json [full]] [--no-store]
                  [TARGET]
```

`run` compiles the model and runs one study: every run, or each `--run`. For each run, it prints the
run's name and label, then each outcome with its value and unit at the end of the run. An outcome
that the model does not estimate shows as `not estimated`, or `not applicable`, never as a number.
The warnings of the study go to the standard error.

| Flag | What it does |
| --- | --- |
| `--variant NAME` | The variant of the package. |
| `--run NAME` | Runs only this run (repeatable; default: every run). The model is checked for these runs only. |
| `--option [GROUP=]OPTION` | Puts this option into each run in place of the run's option of its group (repeatable; [The edit document](#the-edit-document)). |
| `--set NAME=VALUE` | Gives an input a value in its own unit, for every run (repeatable). |
| `--at TIME,…` | Also gives every outcome at these times, such as `--at 24h,7days`. |
| `--edits FILE` | Applies an edit document. |
| `--events` | Prints each event of each run with its time. |
| `--rows NAME,…` | For a model with a table: the rows whose own events and health the report gives ([A model with a table](#a-model-with-a-table)). |
| `--json [full]` | Prints the report as one line of JSON ([JSON documents](#json-documents)). |
| `--no-store` | Neither reads nor writes the run store ([The run store](#the-run-store)). |

Each time of `--at` is a number and a unit of time of the model (`h`, `day`, `days`, `week`,
`month`, `year` and the others of the prelude). It lies from 0 to the end of the run:

```
$ napkin run examples/reservoir --at 24h,3days
base
                                             at 24 h      at 72 h        at the end (120 h)
  Water let out over the spillway            0 fraction   0.2 fraction   0.5 fraction
  Time with the water above the risk level   0 h          0 h            0 h
```

A time without a unit, a unit that is not of time, and a time outside the run are usage errors:
`--at 10days: the run goes from 0 h to 120 h`. `--events` lists each event that has an outcome,
with its time, its text and its name:

```
$ napkin run examples/reservoir --events
base
                                             at the end (120 h)
  Water let out over the spillway            0.5 fraction
  Time with the water above the risk level   0 h
  events:
    40 h  The operator opens the spillway.  (operator.decide.open)
```

Exit 0 when the study is admitted. Exit 1 when the model does not compile or the engine rejects the
study: the command prints `The study is rejected:` and the diagnostics.

### A model with a table

A thing of a model can make one instance for each row of a table (`cells: Cell from "cells.csv"`,
[language.md](language.md)). A table can have very many rows. Thus the engine does not write each
row out, and the report does not list each row
([engine.md](engine.md#tables-and-tiers)).

- The outcomes print as those of any model.
- What the report says of the rows of a table is by **group**. A group is a class of rows that the
  engine runs as one family: the rows that give the same columns of the table. A group has the name
  of its first row. The command prints each group with its table and the number of its rows.
- `--events` prints, for each group, each event with its outcome: how many times it happened, in how
  many rows, and the first and the last time.
- `--rows NAME,…` names rows, such as `--rows cells_4`. The events of these rows print one by one,
  with those of the things that no table makes.

```
$ napkin run demo --events --rows cells_4 --at 30h
base
                                             at 30 h            at the end (240 h)
  Water that all cells spill                 0.1875 fraction    2.6 fraction
  Water that seeps from all cells            0.09368 fraction   0.6558 fraction
  events:
    20 h  The gate opens.  (cells_4.open.done)
    68 h  cells_4.shut.done  (cells_4.shut.done)
  groups of rows:
    cells_1: 3 rows of cells
      cells_1.open (done): 3 times in 3 rows, from 20 h to 120 h
      cells_1.shut (done): 3 times in 3 rows, from 68 h to 168 h
    cells_2: 3 rows of cells
      cells_2.open (done): 3 times in 3 rows, from 20 h to 80 h
      cells_2.shut (done): 3 times in 3 rows, from 68 h to 128 h
```

Limits of a model with a table:

- `--option`, `--set` and `--edits` are not for the groups of a table yet. With one of them, the
  command runs the model as it runs every model, with each row written out, and its first line says
  so: `note: this model runs with each row of its table written out: --set is not for the groups of
  a table yet`. This is for a small table: each row then costs as much as a thing of its own. An
  edit names an input of a row as `cells.1.leak`. `napkin sample` and `napkin play` run such a
  model in the same way.
- The run store keeps no run of the groups of a table.
- The engine does not run every table by group. A template that reads a list over its own table is
  one such model. The command then runs the model with each row written out, with the same note
  and its reason.
- `--rows` is a usage error when the model runs with each row written out, and for a model with no
  table.
- With `--json`, the note goes to the standard error: the standard output is the document only.

## napkin play

```
usage: napkin play [-h] [--variant NAME] [--run NAME] --control THING
                   [--option [GROUP=]OPTION] [--set NAME=VALUE] [--edits FILE]
                   [--picks FILE] [--save FILE] [--json]
                   [TARGET]
```

`play` runs one run and stops at each decision of a controlled actor, for your pick. The model takes
every other decision. The model is checked for that run only. Each pick goes into the log before
the engine takes it, and the run is one simulation.

| Flag | What it does |
| --- | --- |
| `--run NAME` | The run to play (default: the only run). |
| `--control THING` | An actor, or one choice of an actor (`actor.event`), whose decisions you pick (repeatable, at least one). |
| `--option`, `--set`, `--edits` | As for `run`. |
| `--save FILE` | Writes the play log ([The play log](#the-play-log)). |
| `--picks FILE` | Continues a play log. |
| `--json` | JSON lines in place of prompts ([The play protocol](#the-play-protocol)). |

At the terminal, the command shows the time, the thing that decides and its question, what it sees,
and the outcomes. It numbers each outcome that can happen now, and marks the others `(cannot happen
now)`. Type the number or the name of an outcome, then a reason, or nothing:

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
Pick 1-2 or a name: 2
Why (optional): I want to see what happens
  operator picks wait.

The run base ends at 120 h.
  Water let out over the spillway           0 fraction
  Time with the water above the risk level  40 h
1 pick.
```

The engine refuses a `--control` that names no actor and no choice (exit 1). A note then names the
actors and their choices:

```
$ napkin play examples/reservoir --control nobody
note: checked for run base only; `napkin compile` checks every run
error: nobody is not an actor of this run, nor a choice of an actor (run base)
note: the actors that --control can name, with their choices: operator (operator.decide)
```

When the input ends at a decision, the run stops there, and the command exits 3. With `--save`, the
log keeps the picks so far.

## napkin sample

```
usage: napkin sample [-h] [--variant NAME] [--run NAME]
                     [--option [GROUP=]OPTION] [--set NAME=VALUE]
                     [--samples N] [--seed N] [--jobs N] [--at TIME]
                     [--exceed NAME=VALUE] [--edits FILE] [--json]
                     [TARGET]
```

`sample` draws each input that has a distribution, in the model or in the edit document, and runs
the run once for each sample. On the same draws, it also runs the runs that the run is compared
with: the run that its `versus` names, and each run whose `versus` names it. Each sample draws its
own value of each input, and two runs compare sample by sample
([engine.md](engine.md#monte-carlo-studies)). The engine checks the edit document and every
sample before the first sample runs. A refusal is exit 1. Each diagnostic of a sample gives the
sample, the seed and the drawn values.

For each outcome of each run, at the end of the run or at `--at`, the command prints:

- the mean, the middle 50% (the 25th to the 75th percentile) and the middle 90% (the 5th to the 95th);
- the 1-in-100 value (the 99th percentile) from 1000 samples, and the 1-in-200 value (the 99.5th) from
  2000 samples, so that at least 10 samples lie beyond each;
- the three inputs that move the outcome most, by rank correlation (Spearman);
- for each `--exceed`, the chance that the outcome passes the value: the share of the samples above
  it.

```
$ napkin sample examples/piano_tuners --samples 1000 --exceed tunings_done=3200
piano_tuners: Piano tuners
1000 samples, seed 0, at the end of the run (8760 h)
  base

tunings_done: Tunings done in the year (tunings)
  base  mean 2898; middle 50%: 2674 to 3160; middle 90%: 2316 to 3400
        1-in-100 value: 3495
        inputs that move it most (rank correlation): tuners.rate +1.00
        P(tunings_done > 3200) = 0.203 (203 of 1000 samples)
```

| Flag | What it does |
| --- | --- |
| `--run NAME` | The run to sample (default: the only run). |
| `--samples N` | The number of samples (default 200). |
| `--seed N` | The seed of the draws (default 0). The same seed gives the same draws. |
| `--jobs N` | The processes that run the samples (default: the number of processors). The command never starts more processes than there are samples. |
| `--at TIME` | The spread at this one time (default: the end of the run). |
| `--exceed NAME=VALUE` | Also prints the chance that output NAME passes VALUE, a number in the output's unit (repeatable). NAME is the output's name in the file or in the report. |
| `--edits FILE` | Applies an edit document, which can give inputs distributions. |
| `--option`, `--set` | As for `run`. With `--option`, each sampled run takes the options and has a spread of its own, with the same seed. |
| `--json` | Every draw and its outcomes as one JSON document ([JSON documents](#json-documents)). |

An edit document can give inputs their distributions. The Washington, DC variant keeps one in its
folder. Its run `delayed_kept_human` is compared with `delayed_kept`, so the command samples both on
the same draws, and checks the model for these two runs only:

```
$ napkin sample scenarios/water_controls_wipe --variant washington_dc --run delayed_kept_human --edits scenarios/water_controls_wipe/variants/washington_dc/spreads/uncertainty.json --samples 40 --jobs 4 --exceed economic_loss=0.05
water_controls_wipe:washington_dc: Water systems' controls wiped through a shared remote-support platform: Washington, DC
checked for runs delayed_kept and delayed_kept_human only; `napkin compile` checks every run
40 samples, seed 0, at the end of the run (2160 h)
  delayed_kept        Delayed response · Keeps hidden access
  delayed_kept_human  Delayed response · Human team keeps hidden access
…
economic_loss: Economic loss (USD2025_bn)
  delayed_kept        mean 0.1119; middle 50%: 0.03512 to 0.1758; middle 90%: 0.03126 to 0.2647
                      inputs that move it most (rank correlation): wssc_water.manual_share -0.97, attacker.reaction_time +0.41, controls_crew.capacity -0.26
                      P(economic_loss > 0.05) = 0.6 (24 of 40 samples)
  delayed_kept_human  mean 0.06617; middle 50%: 0.01841 to 0.09118; middle 90%: 0.01535 to 0.1602
                      inputs that move it most (rank correlation): wssc_water.manual_share -0.95, attacker.reaction_time +0.42, controls_crew.capacity -0.35
                      P(economic_loss > 0.05) = 0.525 (21 of 40 samples)

deaths: Deaths (people)
  delayed_kept        not estimated
  delayed_kept_human  not estimated
…
```

When no input of the runs has a distribution, every sample is the same. The command then says that
there is no spread, and exits 0. A model with several runs and no `--run` normally lists its runs
and stops. But first, the command compiles the model with every run checked. When no input of any
run has a distribution, it says that there is no spread:

```
$ napkin sample scenarios/iv_fluid_shortage --samples 20 --jobs 2
iv_fluid_shortage: No input of the model has a distribution, in the model or in the edit document. Every sample is the same, so there is no spread. An edit document (--edits FILE) can give an input a distribution.
```

The spread is the spread of the inputs that the model or the edit document assumes, carried through
the model. It is not a measured interval. A spread takes about the time of one run, times the
samples and the runs that the command samples, shared among the processes.

## napkin draw

```
usage: napkin draw [-h] [--variant NAME] [--run NAME] [--style FILE] [-o FILE]
                   [--latex FILE]
                   [TARGET]
```

`draw` writes a static picture of the model as SVG. Each thing is a box with its stocks and flows.
Each var with named states is a small state machine. Arrows show what each thing reads, changes and
moves of the others. The stylesheet places, groups, hides and labels things, and sets their icons:
the variant's `style.toml`, else the package's, or the file of `--style`. Everything else lays itself
out, the same way each time. [draw.md](draw.md) gives the picture and the stylesheet.

| Flag | What it does |
| --- | --- |
| `--run NAME` | Draws that run: it leaves out the parts that cannot act in it. The model is checked for that run only. |
| `--style FILE` | The stylesheet to use in place of `style.toml`. |
| `-o FILE` | The SVG to write. The default is `<package>[.<variant>][.<run>].svg` in the current folder. |
| `--latex FILE` | Also writes the equations, the symbols and the references of the picture to this file, as a LaTeX fragment. |

```
$ napkin draw scenarios/water_controls_wipe --variant juneau --run delayed_kept_human
note: checked for run delayed_kept_human only; `napkin compile` checks every run
water_controls_wipe.juneau.delayed_kept_human.svg: 10 things, 27 arrows
```

A stylesheet with a problem gives its diagnostics, with its file and line (exit 1).

The LaTeX fragment of `--latex` holds the things that `[equations] things` names in the stylesheet
([draw.md](draw.md)). It has one `align*` for each block of equations, a `longtable` of the symbols
and an `enumerate` of the references. Its first lines are comments that name the packages that it
needs, in the order to load them: `amsmath`, `longtable` and `hyperref`. Without `[equations]
things`, the file holds only comments, and a note says so (exit 0).

The fragment can break across pages. Each `align*` is in a group with `\allowdisplaybreaks[1]`, so a
page can break between the lines of a long block. Outside the group, your document keeps its own
setting. The table repeats its header row on each page. LaTeX can need a second run to give the
table the same column widths on each page. In a link, `%` and `#` are written `\%` and `\#`. A `$`,
`^`, `{`, `}` or `\` is written as %XX: `$` as %24, which a server reads as `$`. `&`, `_` and `~`
stay as they are, because hyperref reads them as they are.

## napkin new

```
usage: napkin new [-h] [--title TEXT] [--variants NAME,…] DIR
```

`new` writes `DIR/model.scn`: a model that compiles and runs as written. It holds one thing with a
stock and a flow, one output, and one assumption record that each value cites. It uses only the
prelude's units and names no library, so it compiles in any folder. Then it prints what to replace
next.

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

| Flag | What it does |
| --- | --- |
| `--title TEXT` | The title of the scenario (default: "A new scenario"). A title cannot hold `"`. |
| `--variants NAME,…` | Also writes `variants/NAME/model.scn` for each NAME: a variant that gives the rate a value of its own. A NAME is a lowercase letter, then lowercase letters, digits and `_`. |

The command writes no file when one of its files is there already, or when the title or a variant
name is wrong (exit 2).

## napkin fmt

```
usage: napkin fmt [-h] [--check] [PATH ...]
```

`fmt` formats `.scn` files in place with the language's own formatter. The formatter writes each
line again from its tokens, so a file that it formatted stays the same. Each PATH is a `.scn` file,
or a folder. For a folder, the command takes the `.scn` files below it. It skips the folders and
files whose names start with a dot. Without a PATH, it formats the package that holds the current folder. The command
writes only the files that change, and lists them. A summary goes to the standard error.

```
$ napkin fmt --check demo
demo/model.scn
1 of 1 file would change
$ napkin fmt demo
demo/model.scn
formatted 1 of 1 file
```

`--check` writes no file: it lists the files that the formatter would change. The command exits 0
when every file is formatted. It exits 1 when `--check` finds a file to change, or when a file does
not read (with its file, line and column). It exits 2 for a PATH that is not a `.scn` file or a
folder. To check every package of
the catalogue and the examples, name their folders, so that the shell gives no other file:

```
$ napkin fmt --check examples/*/ scenarios/*/
23 files checked, all formatted
```

## The edit document

An edit document changes the values of a model's inputs without a change to its files. It is a
JSON object of the schema `napkin/schema/edits.schema.json`. This document is for the Juneau variant
of `water_controls_wipe`:

```json
{
  "schema_version": "0.0.1",
  "model_hash": "f847c520…",
  "reason": "Faster emergency water, and a faster removal of the credential in a delayed response",
  "set": {"relief.start_delay": 24},
  "options": {"Delayed response": {"responders.removal_time": 96}},
  "runs": {"delayed_kept_human": {"attacker.reaction_time": "pert(24 h, 48 h, 96 h)"}}
}
```

```
$ napkin run scenarios/water_controls_wipe --variant juneau --edits juneau-edits.json
…
delayed_kept: Delayed response · Keeps hidden access
                                                                at the end (2160 h)
  Replacement controllers in stock                              1050 parts
  Person-days without normal water service                      19510 person-days
…
```

- An input is `thing.field`, as `compile --inputs` lists it.
- A value is a number in the input's own unit, `true` or `false` for a bool input, a name for a named
  input, or a distribution written as in a model file, with its units.
- `set` edits every run, `options` each run that names the option, and `runs` one run. The narrower
  edit wins: the run, then the option, then every run. Each edit wins over the value that an option
  gives, and that value wins over the input's own value.
- `reason` is optional, and no result reads it.

[engine.md](engine.md) gives the rules of the document in full.

### --edits and --set

`--edits FILE` reads a document. `--set NAME=VALUE` gives one input a value for every run: an entry
of `set`, which takes the place of the file's entry of the same name. VALUE is strict JSON (no NaN,
no infinity, no key twice). A bare word, a letter followed by letters, digits, `_` and `-`, is text,
for a named input: `--set NAME=fast` gives the name `"fast"`. `--set tuners.staff=4` gives the
number 4, and `--set NAME=true` gives the JSON value `true`.

The command adds `schema_version` and `model_hash` from the model when the document has none. A
document that names another `model_hash` keeps it, and the engine refuses it. So a document for
another revision of the model never applies:

```
$ napkin run examples/piano_tuners --edits old.json
The study is rejected:
error: The edits are for a different model revision (edits)
```

The engine checks each name and each value, and names the closest input of a wrong name:

```
$ napkin run examples/piano_tuners --set tuners.staf=2
The study is rejected:
error: tuners.staf is not an input; did you mean tuners.staff, tuners.rate or tuners.need? (edits/set/tuners.staf)
$ napkin run examples/piano_tuners --set tuners.staff=20
The study is rejected:
error: tuners.staff: 20 is outside [1, 10] (edits/set/tuners.staff)
```

### --option

`--option [GROUP=]OPTION` puts an option into the run in place of the run's option of the same
group. Give the option's name as the model's menu gives it (`compile` lists them). `GROUP=` names
the group, as in `--option "Attacker=Human team"`; an option that two groups hold needs it. Each
group takes one option. The
model's runs need not make the combination: `model.combination(run, options)` checks it when you ask
for it, as the build checks a run. The run keeps its name, and its label names the new options:

```
$ napkin run scenarios/water_controls_wipe --variant juneau --run delayed_none --option "Attacker=Human team"
note: checked for run delayed_none only; `napkin compile` checks every run
delayed_none: Delayed response · No hidden access · Human team
                                                                at the end (2160 h)
  Replacement controllers in stock                              1050 parts
  Person-days without normal water service                      19510 person-days
…
```

Without `--run`, `run --option` makes the combination of each run.

### What the engine checks

An edit document is one transaction over the runs of the model.

- The engine checks the document itself, whatever runs the command names: its shape, its model
  revision, its names, each value against its input, and the edits of one level that meet.
- It resolves each run that the model admits under the document, with the checks of its inputs and
  the proofs of its structure. One failure rejects the whole study, and no run starts. Without
  `--run`, the model admits every run. With `--run X`, the document is checked on X only (for
  `sample`, on X and its compared runs; [Runs](#runs)).
- With `--option`, the engine first checks the whole document on the model, in each run that it
  admits. Then each combined run takes only the part of the document that reaches it: `set`, the
  edits of its options and the edits of its run.

Here `false` is a value of the bool input `juneau.reached`, but a check of the model refuses the
run:

```
$ napkin run scenarios/water_controls_wipe --variant juneau --run delayed_kept --set juneau.reached=false
note: checked for run delayed_kept only; `napkin compile` checks every run
The study is rejected:
error: The attack reaches at least one system of the place. (assert:/1; run delayed_kept)
```

## JSON documents

Each JSON document carries `"schema_version": "0.0.1"`, the version of napkin's documents
(`napkin.SCHEMA_VERSION`). Each document is one line of compact JSON on the standard output. A
number in it is always finite.

### napkin run --json

`--json` prints the compact document: the report of the study (`sample_result`), with its own names.

- The envelope of the report: `schema_version`, `engine_version`, `model_hash`,
  `implementation_hash`, `library_hash`, `scenario`, `variant`, `title`, `admissible`, `status`,
  `effective_edits` and `diagnostics`.
- `runs`: for each run, its `label`, `options`, `horizon` and `outcomes` (each with its label, unit,
  kind, status, scope and basis); `reporting_points`, each with its `t`, `values` and `statuses`;
  and `events`, each event with an outcome, as `{t, thing, event, outcome, text}`, with `picked`
  when a pick decided it.
- `admitted_runs`: the runs that the model was checked for, or `null` for every run.

`--json full` adds each run's `trace` and `evidence`, and the model's evidence `index`. Exit 1 when
the study is not admitted, as without `--json`.

For a [model with a table](#a-model-with-a-table), each run has two more parts, and its `events` are
those of the things that no table makes and of the rows that `--rows` names:

- `groups`: each group, as `{group, set, rows, inputs}`: its name, its table, the number of its
  rows, and the `least` and the `greatest` value of each input over its rows.
- `group_events`: for each group, each event and each outcome, as
  `{group, event, outcome, count, rows, first, last}`. An event that starts to wait has the outcome
  `null`.

`--json full` adds each run's `trace`, `evidence`, `peaks` and `health`. The `health` has, at each
time, the number of rows of each group in each status and in each value of each named state
(`groups`), and the health of each thing that no table makes and of each named row (`entities`).
A peak of an output that can fall, in a large table, can be read at fewer times than its
candidates: it then has `candidates: {read, of}` ([engine.md](engine.md), "Tables and tiers").
The document has no `index`.

```
$ napkin run examples/piano_tuners --json
{"model_hash":"f1953a24…","implementation_hash":"76e8a149…","schema_version":"0.0.1","engine_version":"0.0.1","admissible":true,"status":"accepted","library_hash":"bf98600a…","scenario":"piano_tuners","variant":null,"title":"Piano tuners","effective_edits":{},"diagnostics":[],"runs":{"base":{"label":"base","options":[],"horizon":8760.0,"outcomes":{"tunings_done":{"label":"Tunings done in the year","unit":"tunings","kind":"cumulative","status":"estimated","scope":"The pianos of one town.","basis":{"kind":"identity","explanation":"The tunings that the tuners do, each counted once."},"nonnegative":true,"expr":"tuners.done"}},"reporting_points":{"final":{"t":8760.0,"values":{"tunings_done":2923.537487392582},"statuses":{"tunings_done":"estimated"}}},"events":[]}},"admitted_runs":null}
```

### napkin compile --json

One document: `schema_version`, `package`, `title`, `models`, `diagnostics` (the records that no
variant uses) and `evidence` (`{sourced, assumed}`). Each model of `models` has `admissible`,
`title` and `diagnostics`, and, when it compiles, its `runs` (`{label, options, versus}`), its
`options` (`{group: {option: text}}`) and its `actors`. `--inputs` and `--outputs` add `inputs` and
`outputs`.

### napkin sample --json

One document: the envelope of the engine's report, `admitted_runs`, the `options`, and for each run:

- `label`, `options`, `horizon`, and `settings` (`samples`, `seed`, `method`, the reporting `point`
  and its time `t`);
- `inputs`: each drawn input, as an edit document names it, with its `label` and its `distribution`;
- `outcomes`: the label and unit of each outcome;
- `samples`: each sample, with its `draws` and the `values` and `statuses` of each outcome at the
  time;
- `summary`: for each outcome, the engine's summary (`central`, `mean`, `sd`, `sem`, `min`, `max`
  and `p5` to `p95`), the `drivers` (the rank correlation of each input), `p99` and `p99.5` when
  there are enough samples, and `exceed`, one `{value, count, samples, chance}` for each `--exceed`.

An outcome that is not estimated in every sample has the engine's statuses only, and no value.

### The play protocol

`napkin play --json` writes and reads JSON lines, one object on each line, so that a program in any
language can play. Notes go to the standard error. The lines below come from this play, which picks
`wait`:

```
$ echo '{"pick": "wait", "reason": "test the risk"}' | napkin play examples/reservoir --control operator --json
```

1. The command writes a decision:

   ```json
   {"type":"decision","schema_version":"0.0.1","t":40.00000000000081,"thing":"operator","event":"operator.decide","text":"The water reaches the level at which the operator opens the spillway.","outcomes":[{"name":"open","text":"The operator opens the spillway.","available":true},{"name":"wait","text":"The operator waits, and the spillway stays closed.","available":true}],"view":{"reservoir.water":0.7},"units":{"reservoir.water":"fraction"},"seen":[],"pick":0,"by":"reader"}
   ```

   `view` holds what the actor sees (`units` gives the unit of each value), `seen` the times of the
   events that it sees, and `pick` the number of picks before this one. An outcome can happen now
   when it is `available` ([engine.md](engine.md#play)).
2. The program writes its answer: `{"pick": OUTCOME, "reason": TEXT}`. The reason can be left out
   or `null`. A blank line is skipped.
3. A line that is not strict JSON, not such an object, or whose outcome cannot happen now gets an
   error, then the same decision again. This is the error for the line `{"pick": "close"}`:

   ```json
   {"type":"error","schema_version":"0.0.1","message":"close cannot be picked now: pick one of open, wait"}
   ```

4. The last line is the result. When the run is finished, `report` is the compact document of
   `napkin run --json`, and `picks` is the log:

   ```json
   {"type":"result","schema_version":"0.0.1","finished":true,"report":{…},"picks":[{"event":"operator.decide","outcome":"wait","t":40.00000000000081,"by":"reader","reason":"test the risk"}]}
   ```

   When the input ends first, `finished` is `false`, `report` is `null`, the result adds the
   `decision` that waits, and the command exits 3. When the engine refuses the play, the command
   writes `{"type":"error",…,"diagnostics":[…]}`, then a result with `finished` `false`, and exits
   1.

## The play log

`--save FILE` writes the log of a play. The command writes it before each decision and at the end,
so the log keeps every pick also when the input ends. The log holds the context that it replays in:
the model and implementation hashes, the run, the options, the control, the edit document and the
numerical settings. Then each pick, with its event, outcome, time, who picked it and the reason:

```json
{
  "schema_version": "0.0.1",
  "kind": "play",
  "model_hash": "ab929f70…",
  "implementation_hash": "76e8a149…",
  "scenario": "reservoir",
  "variant": null,
  "run": "base",
  "options": [],
  "control": {
    "operator": "reader"
  },
  "edits": null,
  "numerical_settings": {
    "rtol": 1e-09,
    "atol_factor": 1e-10,
    "max_step": 1.0,
    "max_evaluations": 2000000,
    "max_events": 10000,
    "max_steps": 1000
  },
  "picks": [
    {
      "event": "operator.decide",
      "outcome": "open",
      "t": 40.00000000000081,
      "by": "reader",
      "reason": "The level is reached"
    }
  ]
}
```

`--picks FILE` continues a log: each decision takes the next pick of the log, in order, and the
first decision after the last pick waits for you. Give `--save` with the same FILE to keep the new
picks. The same log gives the same run, bit for bit. The command refuses a log of another context,
and names what differs (exit 1):

```
$ napkin play examples/reservoir --control operator --picks play.json --set operator.level=0.8
note: checked for run base only; `napkin compile` checks every run
error: play.json is the log of another play: it differs in edits, so it cannot continue this one
```

## The run store

The run store keeps each simulated run on disk, so that no command simulates the same run twice.
`run`, `play` and `sample` use it. The store keys each run by the resolved run, its units, the
numerical settings, the engine's code and the computer. A change to any of them simulates the run
again ([engine.md](engine.md#the-run-store)). A store serves only the computer that wrote it. When a
study needs several runs that the store does not hold, helper processes simulate them beside the
command.

- The store is in `.cache/runs` of a source checkout, when `napkin` runs from it. For an installed
  package, it is in `~/.cache/napkin/runs`, or in `napkin/runs` under `XDG_CACHE_HOME`.
- `NAPKIN_STORE=DIR` puts the store in DIR. `NAPKIN_STORE=off` turns it off.
- `napkin run --no-store` neither reads nor writes the store.
- When the store passes `NAPKIN_STORE_LIMIT` gigabytes (4 by default), the runs used least recently
  go.
- To clear the store, delete its folder.

The store keeps only the simulations. Every check of a study still runs, and a failed run is never
stored.
