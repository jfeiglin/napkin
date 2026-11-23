# Changes

## Unreleased (language 0.2.3)

This release replaces the language and the engine. A model of version 0.0.1 does not compile: write
it again in the new language. [docs/language/changes.md](docs/language/changes.md) gives each removed
word and form, and what replaced it. The catalogue and the examples are in the new language.
[docs/README.md](docs/README.md) lists the new documentation.

**The language, version 0.2.3** ([docs/language/README.md](docs/language/README.md)).

- A value has a type, an owner and a lifetime. `name: unit = value` declares a stored value, and
  `formula(...)` declares a calculation that the engine does each time that it reads it.
- `input` declares a value that a named run or an edit can set. An edit follows the declared type,
  and an input can hold a distribution. `.draw()` takes one number from a distribution.
- A range is `in [low, high]`, and either end can be empty: `in [0,]`. A value with no range has no
  bound. `scale` gives the numerical size of a value.
- Units use `*` and `/`: `tunings/(tuner * year)`. `48 h/2` and `48 h / 2` are both 24 h.
- An event is a value: `repair = event(...):`. Each `.start(...)` makes an occurrence with its own
  arguments, locals, flows and stages (`after D:`), and gates (`until C`).
- A trigger (`when C:`) belongs to its event, with a `reset` rule. A trigger on a value that moves
  fires at its crossing, which the engine finds between moments.
- A stage can branch with `if`, `else` and `switch`. A random outcome is a `switch` on a draw of a
  `categorical(...)` distribution.
- A flow has a `request`, which is soft, a `capacity`, which is hard, and an `actual_rate`. A route
  (`<->`) has one signed rate and two legs. A flow can have several legs at one served fraction.
- Each endpoint shares among its own flows (`priority(...)`, `proportional()`). A declared `solver`
  owns a joint decision across endpoints, with `inputs`, `solve_for`, `constraints` and `objective`.
- Collections (`Place.instances`, `where`, `by`, `.at(...)`) hold members, rows of tables, flows and
  occurrences. A row of a table has a stable ID.
- The model has no output and no report block. A caller reads any named value at any time.
- `options` and `runs:` declare the named runs. A `change` in a variant gives a value a new
  initializer. Each setting of an option or of a `change` cites a `record` declaration.
- A member can have a `title`. No part of a model has a role: `roles.toml` and the `[role]` table of
  `style.toml` say who plays each part.

**The engine** ([docs/engine/README.md](docs/engine/README.md)).

- One timeline engine calculates each run. It reads the compiled program, which a new process can
  load without the parser ([docs/compiler.md](docs/compiler.md)).
- Each connected set of stocks runs on one of six methods: Family, Lines, Component, Sparse, Declared
  and MovingDeclared ([docs/engine/methods.md](docs/engine/methods.md)).
- A rate can read a value that moves between moments, at any size of model. A large model can stop
  with a named failure of time, memory or accuracy, but its equations stay the same.
- A run that cannot answer stops with a named failure. It never gives a different answer in silence.
- The same run on one machine gives the same record. A run in another process, batch or platform
  agrees within the stated tolerances.
- Two numbers compare equal inside their comparison band. The engine reports each decision inside a
  comparison band as a near-tie ([docs/language/numerics.md](docs/language/numerics.md)).
- `max_occurrences`, `max_active` and `max_rounds` limit a run that does not stop. The configuration
  of a run can change each limit.

**Breakpoints, checkpoints and edits** replace the player machinery
([docs/language/events.md](docs/language/events.md)).

- A caller stops a run at an event, a stage or a statement. At the stop, the caller reads values and
  edits stored values.
- A checkpoint saves the stop, and a new process can continue the run from it.
- A run that stops and continues with no edit gives the record of the run with no stop.
- The trace holds each edit, with its time, its stop, its target and its old and new value.
- `napkin play` and `napkin.Session` are two clients of this machinery.

**The run store** keeps the record of each run on disk
([docs/engine/README.md](docs/engine/README.md#the-run-store)). The key of a run is a digest of its
program, its configuration and its request. The key also holds the code of the engine, the machine
and the log of edits. An identical request reads the stored record. Any other request calculates a
new run. `NAPKIN_STORE=off` stops the store, and `NAPKIN_STORE=DIR` puts it in another folder.

**Exact stocks and moves** ([docs/engine/methods.md](docs/engine/methods.md#the-exact-stock-ledger)).
A stock is each value that a flow or a `move` touches. The engine keeps an exact balance for each
stock, and it posts each transfer equally at both ends. `move amount from a to b` moves exactly the
amount that it writes, or it fails and moves nothing. An assignment to a stock is exact too.

**The evidence rule** ([docs/language/evidence.md](docs/language/evidence.md)). The compiler gives
the warning `no_record` for each part that cites no `record` declaration: an input, a stored value,
a timed event, a status case, an assertion, an own value of an instance or a table column. It gives
the warning `datum` for a value that differs from the datum of the claim that it cites. A model with
these warnings still runs. `tools.check` and the publisher refuse a package of the catalogue with any
of them.

**The publisher** ([tools/publish/README.md](tools/publish/README.md)).

- `python -m tools.publish` writes `results/brief.md`, `results/readings.md` and
  `results/source-dossier.json` for each package or variant, and the source manifest of the catalogue.
- A `brief.toml` names the comparisons of two runs (`[[comparison]]`) and the pair to show first
  (`featured`). A brief shows the signed difference of each reading of a pair.
- `--sample-spreads` samples each declared spread and writes `results/paired-spreads.json`, with the
  differences of each pair of draws.
- `--model PATH` writes the readings of any model.
- The publisher no longer writes `methods.md`, `runs.csv`, `runs.json` or the review files. The files
  of the earlier studies stay in the catalogue as history.

**Removed flags of the `napkin` command** ([docs/cli.md](docs/cli.md)).

| Removed flag | What to use now |
| --- | --- |
| `--option` of `run`, `sample` and `play` | A named run under `runs:` that takes the option, and `--run NAME` |
| `--set NAME=VALUE` of `run`, `sample` and `play` | An edit document with `--edits FILE`. Its level `set` edits every run. |
| `napkin run --events` | No flag. The trace of the record holds each event (`napkin.run(...).trace` in Python). |
| `napkin run --rows` | `--value` with the paths of the rows, for example `sites.clinic.water` |
| `napkin run --no-store` | `NAPKIN_STORE=off` |
| `napkin play --control` | `napkin play --break AT[@OWNER]`, and an edit at each stop |
| `napkin play --picks FILE` | `napkin play --from FILE`, from a checkpoint that `save FILE` wrote at a stop |
| `napkin play --save FILE` | `save FILE` at a stop |
| `napkin play --json` | `napkin.Session` in Python |
| `napkin compile --inputs` and `--outputs` | The summary of `napkin compile`, which lists the inputs, the stores and the formulas |

The new flags are `--value` and `--lag` of `napkin run`, `--value` of `napkin sample`, and
`--break`, `--value` and `--from` of `napkin play`.

**Removed names of the Python API** ([docs/python-api.md](docs/python-api.md)).

| Removed name | What to use now |
| --- | --- |
| `evaluate_study` | `napkin.study` for the named runs of a model, then `napkin.report` for each record |
| `sample_result` | `napkin.report` or `napkin.read` for the readings of one record |
| `evaluate_uncertainty` | `napkin.monte_carlo` for the samples of one run, or the module `napkin.spread` for a model file |
| `uncertainty_report` | The summaries that `napkin.monte_carlo` gives, or `napkin sample --json` |
| `actors` | Nothing. A model has no actors. `napkin.instances` stays. |

The new names are `run`, `read`, `report`, `Lag`, `study`, `monte_carlo` and `spread`. `Session` now
plays one run through breakpoints, checkpoints and edits.

**Edit documents.** The shape of an edit document stays at `schema_version` 0.0.1, but each document
names the model hash of its model. A document for a model of the old language names an old hash, so
the compiler refuses it. Write each saved edit document again.

## 0.0.1

The first release of napkin: a small typed language for simulation models, its engine, and the
`napkin` command. napkin comes from the package `cyber_scenarios` (releases 2.2.0 to 5.0.1). It is a
fresh start: it has no reader or schema of an earlier version, and saved edits and reports of
`cyber_scenarios` must be made again.

- **The language, version 0.0.1** (docs/language.md). A package is a folder with a `model.scn`; a
  variant is `variants/<name>/model.scn` in it, named `<package>:<name>`. `library "PATH"` names a
  folder of shared units and records. Every model has the prelude's units (`napkin/std/units.json`),
  and a composed unit such as `tunings/tuner-year` needs no entry. The model hash covers what a model
  means and reaches, and the language's version; it covers no name, path or package version.
- **The `napkin` command** (docs/cli.md): `compile`, `run`, `play`, `sample`, `draw`, `new` and
  `fmt`. `run --run`, `play` and `sample --run` check the model for the runs that they use only, and say
  so; `compile` checks every run.
- **The Python API** (docs/python-api.md): `load_scenario`, `load_package`, `evaluate_study`,
  `sample_result`, `evaluate_uncertainty`, `uncertainty_report`, `Session`, `actors`, `instances`
  and `napkin.dynamics`. Everything else is internal and can change in a later version.
- **Session and play** (docs/engine.md, "Play"): a person or a program picks the outcomes of an
  actor's decisions, and a saved log replays the run exactly.
- **`napkin draw`** (docs/draw.md): one self-contained SVG of a model, with light and dark themes,
  laid out from the model and its `style.toml`.
- **Two examples:** `examples/piano_tuners` and `examples/reservoir`.
- **The showcase catalogue** (scenarios/README.md): `iv_fluid_shortage`, `heat_wave_blackout`,
  `water_controls_wipe` (16 variants) and `cyber_learning_loop`. The other cases of
  `cyber_scenarios` left this repository.
- **Removed:** the web workbench and its front end; the research layer (`studies.json` and the
  research packages); the aggregate dossiers; the commands `python -m cyber_scenarios.try`,
  `.play` and `.new`, which the `napkin` command replaces.
- **The wheel** `napkin-sim` holds the engine only. Install it from a checkout (`pip install .`) or
  from the release wheel; PyPI's `napkin` is a different tool.
- **The tag** `v0.0.1` sorts below `v2.2.0`, `v5.0.0` and `v5.0.1`, the tags of `cyber_scenarios`,
  which stay as its history.

**Removed: the derivatives of a whole run.** The language is being rewritten, and the derivatives
that a run carried by its inputs are out of its first version; they are rebuilt later. `napkin
derivatives`, `timeline.derivatives.report`, the option `directions` of `timeline.run`,
`expectations.controlled`, `expectations.derivatives` and `estimators.tail_slopes` are gone. A run
gives the same numbers as before, bit for bit. The derivative of an expression by a name
(`napkin/core/derivatives.py`) and the derivatives of the field (`napkin.dynamics`) stay.

**A notebook to explore `heat_wave_blackout`** (`scenarios/heat_wave_blackout/explore.ipynb`). A
reader runs two pathways side by side with values of their own, and sees the outcomes, the charts of
the supply, the deaths and the status of each part, and the edit document that gives the same
pathways. It needs jupyterlab, ipywidgets and plotly beside the checkout's own requirements.

**Fixed: the supply of `heat_wave_blackout` read "Power partly restored" before any circuit was
back.** Its share restored read the crews' work done, and a solver remainder of about 1e-27 hours of
work counted as power from half an hour on. While the supply is off, the share is now 0. The
reported values stay the same at the six figures of the run table; only the model's version changes.

**Known issues and possible future features** (docs/known-issues.md): one page with a table of
each.

**Other estimators of a study** (docs/engine.md, "Estimators"). A caller asks for each by name, and
no study, report or published file changes unless it asks.

- `SamplingSettings(method='sobol')`: scrambled Sobol' points in independent blocks. The standard
  error of a summary is that of the means of the blocks. A `[[spread]]` of a brief can name the
  method.
- `napkin.engine.estimators`: the interval of a quantile from two order statistics, a rule that
  makes a study larger until that interval is narrow and keeps its confidence, the interval of
  independent blocks, and a control with a known mean.
- A run can take the outcomes of its chance events from its caller. `expectations.weighted` runs
  every path of those outcomes and adds them with their weights: the outcomes make no sampling
  error.
- `expectations.controlled`: the mean of a finished study with the linear form at the central run
  as a control, with no bias.
- `expectations.derivatives`: the derivative of the mean of each outcome by an input, with a label
  for each pair. The mean of the derivatives of the samples is given only where the structure of
  the model shows that it is the derivative of the mean; a chance that the input changes is
  weighted over the paths; each other case is named as unsupported, with its reason. The
  derivative of the chance to pass a value and of a quantile are estimated with a kernel where
  they need a density, and say that they converge more slowly.

**Fixed: an expression with many operations one inside the other.** A sum of 40 terms or more that
an author writes by hand, and a sum over 45 or more copies of a template in a model with no table,
compiled, and the report of the model failed with an error of Python. Such a model now runs and
reports. An expression can have 150 operations one inside the other; a deeper one is refused with a
diagnostic (at its line, when the author wrote it), where it ended in an error of Python before.

**The instances of a template from a table.** `name: Template from "file.csv"` makes one instance of
the template for each row of a table of the package. A header is `member`, or `member: unit`, and then
the records of its values; each cell that is not empty gives its instance what the line
`member = cell` gives. A column can also give a link or the title. The model hash covers what the
table holds, not the name of its file. No model that has no table changes its meaning, its hash or
its results (docs/language.md, §2.3).

A clearer `napkin draw` (docs/draw.md). Nothing in the language, the engine or a model's results
changes: no model hash, implementation hash or stored run changes.

- **Arrows.** Five kinds: reads, follows (a read of when an event happened), changes, fires (a line
  that makes another thing's event happen) and moves. Each kind has its own line and head, so they
  differ without colour. Reads and follows are drawn light and share one trunk from each card; the
  tracks between the columns are as few as they can be. `[arrows]` gives each kind a look (full,
  light or hidden) and names the kinds that bundle.
- **Cards.** The subtitle names the run, its options, the run that it is compared with, how long a
  run lasts and what is hidden. The thing of the start event has a ▶. A card's tooltip names its
  file and lists its connections; pointing at a card in a browser lights its arrows. `[stocks]`,
  `[layout] stocks`, `cards_per_column` and `card_width` choose its rows and the columns.
- **Events.** `[triggers]` shows, on a card, what makes its events happen, in plain words from the
  model: a count, the names, or the shortened rules, with the full rules in the tooltip.
- **Equations, symbols and references.** `[equations]` adds panels under the map: the balances, the
  rates and the formulas of the things that it names, as math from the model's own expressions; a
  table of the symbols with their values and chosen ranges; and, with `[references] show`, a
  numbered list of the sources, conventions, identities and assumptions behind them. `[symbol.<thing>]`
  and `[subscript]` set symbols. `napkin draw --latex FILE` writes the same equations as LaTeX, in a
  fragment that breaks across pages. A yes/no formula is written with ⇔, a jump names its event, and
  a start that a formula sets shows as math. A wide picture puts its panels in two columns, and
  `napkin draw` says when a picture is taller than a PDF page holds.
- **Text that fits.** Bold text is measured as bold, so a title fits its card and the picture in the
  common fonts.
- **The catalogue's pictures.** Each package and example has a new `style.toml`: columns in the order
  of the story, frames, the events of the key things, and the panels of the 1 to 3 things whose stocks
  carry the story. `water_controls_wipe` has one stylesheet for the places that differ only in their
  numbers.

**Fixed: a proof that read a branch that no state reaches.** The check of the domains of a run could
stop with `ZeroDivisionError` for an expression such as `x if x == 0 or 1 / (x + y) > 0 else 10`
when `x` and `y` are fixed at 0. The branch after `x != 0` holds no state, and the check now reads
nothing in it.

**A new engine: one timeline** (docs/engine.md). The engine holds the times at which something can
happen on one timeline, and reads a rule only when its answer can have changed. Between moments it
moves the quantities with the solver, the exact segments and the allocation that it had. When the
new engine took the place of the old one, every run, sweep and edit set of the catalogue, the
examples and the acceptance fixture had the results that it had, bit for bit. Since then the solver
takes longer steps (below): the events are the same, and each value agrees within the tolerance of
a comparison, one part in a million. Where a result has two equal peaks, the time of the peak can
be that of the other one. No model hash changes; the implementation hash changes, so stored runs
are simulated again.

- **Steps.** The step cap (1 h, or the `resolution` of the scenario) is how often the engine reads
  a numerical segment: its roots, and its rates against the solution. It no longer limits the step
  of the solver, which takes the steps that its error allows (docs/engine.md, "Steps"). A quiet
  part of a run takes far fewer steps. A value between two steps has the accuracy that the
  tolerances ask; before, the short steps made it more exact than that.

- **When a crossing is due.** At its own time: the time at which its quantity reaches its value. It
  is no longer due only because its quantity is inside its tolerance band at a moment of another
  rule, and a crossing whose time is within 1e-8 h after a moment is due in that moment, as a clock
  is (docs/engine.md, "When a crossing is due"). A model can see a shift of the time of an event by
  less than the time that the quantity takes to cross its tolerance; no model of the catalogue does.
- **The rows of a table.** The engine also reads the hybrid core of a model, which does not write
  the rows of a table out (docs/engine.md, "Tables and tiers"): its cost grows as the number of
  rows. `napkin run` runs a model with a table in this way, and its report says what it says of
  the things of a table by group: one class of rows that the engine runs together (docs/cli.md,
  "A model with a table"). `--rows` names rows that have their own lines. With `--set`, `--option`
  or `--edits` the command writes each row out, as before, and says so.
- **Derivatives.** A run can carry the derivative of each outcome by each input. `napkin
  derivatives` and `timeline.derivatives.report` give each derivative with its class (smooth,
  one-sided, undefined, unsupported, or zero by the structure of the model), the reason of the
  class, and an estimate of its numerical error (docs/engine.md, "The class of a derivative").
- **Fixed.** A stock that rests on its upper bound, with an inflow that equals its outflows but
  for roundoff, no longer stops the run. A model with a table whose quantity has a bound that
  reads an input has its run.
- **Moved.** `napkin.engine.scheduler` is gone. `SimulationError` is in `napkin.engine.errors` (and
  still in `napkin.engine.runtime`), and `initial_store` is in `napkin.engine.continuous.system`.
