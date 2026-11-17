# Changes

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
