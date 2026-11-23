# The catalogue

The catalogue is the folder `scenarios/` of the checkout. It holds the packages that the project
publishes. The catalogue has rules of its own, in addition to the rules of the
[language](../../docs/language/README.md). The compiler does not read these rules. A model outside
the catalogue does not have to obey them. This page uses the terms of the language reference
([Terms](../../docs/language/README.md#terms)).

These tools apply the rules of the catalogue:

| Tool | What it does |
| --- | --- |
| `tools/catalogue.py` | Finds the entries, the owners and the files of each owner. The other tools ask it. |
| `python -m tools.check` | Checks a change: the lint, the tests, the evidence rule and the published files. |
| `python -m tools.publish` | Writes and checks the pages and the evidence files in `results/`, and the source manifest. |
| `python -m tools.new` | Makes the folder of a new package ([conventions.md](conventions.md#start-a-package)). |
| `python -m tools.compare` | Compares two runs by their names, their values and their traces. |
| `tools/evidence/` | Gets, checks and writes the evidence ([evidence/README.md](evidence/README.md)). |

The other pages of `scenarios/docs/`:

- [conventions.md](conventions.md): how to write a model of the catalogue.
- [capabilities.md](capabilities.md): what the language and the engine can model today, and what they
  cannot.
- [ai-operations.md](ai-operations.md): how a model shows an AI agent or an attacker, and how a page
  compares it with a human team.
- [deviations.md](deviations.md) and [recovery-ports.md](recovery-ports.md): how the packages differ
  from the earlier catalogue at commit `8488047`.

## The entries

An entry is an owner that runs as a model of its own. `entries()` in `tools/catalogue.py` gives the
entries in this order: each package without variants, then each variant, by the names of their
folders. The catalogue has 19 entries.

| Entry | Title on the scenario line | Named runs |
| --- | --- | ---: |
| `cyber_learning_loop` | AI uptake and a national cyber workforce | 12 |
| `heat_wave_blackout` | Electricity restoration during a heat wave | 11 |
| `iv_fluid_shortage` | IV-fluid supply and recovery | 10 |
| `water_controls_wipe:<place>` | Water service recovery after a controls outage, one variant for each place | 11 in each |

The 16 variants of `water_controls_wipe` are `asheville`, `auburn`, `austin`, `camden`, `cape_may`,
`clayton`, `el_dorado`, `jackson`, `jamestown`, `juneau`, `lehigh`, `los_angeles`, `lumberton`,
`minot`, `richmond` and `washington_dc`.

A package with variants runs as its variants. Its main file is a part of the model of each variant,
so the main file is not an entry. The folder of the package is still an owner: it holds the units
and the evidence that its variants read.

The main file of `cyber_learning_loop` uses the module `defensive_response/response.scn`. The folder
`defensive_response/` also holds a model of its own. That model is not an entry, and the catalogue
tools do not publish it.

## Folders and names

- A package is a folder `scenarios/<package>/` with its main file, `model.scn`. The name of the
  folder is the name of the package. It starts with a lowercase letter, and it has only lowercase
  letters, digits and `_`.
- The folders `docs`, `library` and `tests` of `scenarios/` belong to the catalogue itself. No
  package has one of these names.
- The tests make synthetic packages with reserved names: `SC` and two digits, for example `SC97`. No
  package of the catalogue has such a name.
- A variant is a folder `scenarios/<package>/variants/<name>/` with its own `model.scn`. The tools
  name it `<package>:<name>`, for example `water_controls_wipe:lumberton`. The name of its folder
  obeys the rule for the name of a package.
- `--scenario <package>` selects the package and all its variants. `--scenario <package>:<name>`
  selects one variant.

## The files of a package

```text
scenarios/<package>/
    model.scn              the main file; its first declaration is scenario "Title"
    <module>.scn           a module that the main file uses (use <module>)
    units.json             the units of the package
    style.toml             the picture of napkin draw
    roles.toml             who plays each part
    brief.toml             the settings of the pages
    spreads/<id>.json      the edit document of each spread of brief.toml
    evidence/              sources.json, claims.json, assumptions.json and research.md
    results/               the files that the publisher writes
    tests/                 expected-orders.json, oracle-inputs.json and the tests of the package
    README.md              the guide of the package
    variants/<name>/       a variant: its own model.scn and its own files
```

| File | Who writes it | Who reads it |
| --- | --- | --- |
| `model.scn` and the modules | The author | The compiler |
| `units.json` | The author | The compiler, as a part of the library of the model |
| `style.toml` | The author | `napkin draw`. `napkin compile` checks it. |
| `roles.toml` | The author | No current tool. A test checks its words ([conventions.md](conventions.md#who-plays-each-part)). |
| `brief.toml` and `spreads/` | The author | The publisher |
| `evidence/sources.json`, `evidence/claims.json` | `tools.evidence.integrate` and `tools.evidence.adopt` only | The compiler and the evidence tools |
| `evidence/assumptions.json` | `tools.evidence.integrate`, with an assumption pack | The compiler and the evidence tools |
| `evidence/research.md` | The author | People |
| `results/` | The publisher | People |
| `tests/` | The author | pytest |

- The scenario line of each main file names the shared library: `library "../library"`. This is
  the file `scenarios/library/vocabulary.json`.
- The model of a variant is the main file and the modules of its package, then the `model.scn` of
  the variant. The file of a variant starts with `variant "Title"`.
- A variant has its own `evidence/` and `results/`. The evidence of the folder of a package serves
  the package and all its variants. The evidence of the folder of a variant serves that variant only.
- A variant can have its own `style.toml`, `roles.toml` and `brief.toml`. A file of the variant
  replaces the file of its package. The two files do not merge.
- The edit documents of the spreads are in the folder `spreads/` beside the `brief.toml` that the
  model uses.
- A package can have no `evidence/` folder, when all its `record` declarations are in its model and
  cite no source. `cyber_learning_loop` is such a package.
- A `results/` folder can also hold files of the earlier catalogue: `methods.md`, `runs.csv`,
  `runs.json`, `assumption-review.json` and `source-verification.json`. No current tool writes or
  checks these files.

## The publisher

`python -m tools.publish` writes the files below from the current models and their records. It
reads each run from the run store when the store holds it.

| File | Format (`--only`) | What it holds |
| --- | --- | --- |
| `results/brief.md` | `briefs` | The readings at the horizon of each named comparison, side by side, with the change |
| `results/readings.md` | `readings` | The readings at 0 h and at the horizon of each named run, with the evidence that the run exercised |
| `results/source-dossier.json` | `dossier` | The model hash, the sources and claims of the folder of the owner, their verification records, and the claims that the model reaches |
| `scenarios/docs/evidence/source-manifest.json` | `manifest` | The sources of the shared library and of each owner, with their retrieval records |
| `results/paired-spreads.json` | `--sample-spreads` | The paired results of each spread that holds both runs of a named comparison |

Do these steps to publish one package:

1. Run `python -m tools.publish --write --scenario PACKAGE`.
2. Read the new `results/brief.md` and `results/readings.md`.
3. Run `python -m tools.publish --check --scenario PACKAGE`. It must report no difference.

```sh
python -m tools.publish --check
python -m tools.publish --write --scenario iv_fluid_shortage
python -m tools.publish --check --scenario water_controls_wipe:lumberton
python -m tools.publish --model scenarios/cyber_learning_loop --check
```

| Option | What it does |
| --- | --- |
| `--check` | Makes each file again and compares it byte for byte with the committed file. It fails for a difference. It also fails for a file in a location of the publisher that the publisher no longer makes. |
| `--write` | Writes each file. It deletes each file in its locations that it no longer makes. |
| `--scenario ID` | Selects one owner. Repeat it for more owners. A package selects all its variants. A selection does not make the source manifest. |
| `--only FORMAT` | Selects one format: `briefs`, `readings`, `dossier` or `manifest`. Repeat it for more formats. |
| `--model PATH` | Writes or checks only `results/readings.md`, for a model inside or outside the catalogue. For a package with variants, it does this for each variant. |
| `--jobs N` | Sets the number of worker processes (4 if you do not give it). |
| `--sample-spreads` | Also runs each spread of the selection, and writes or checks `results/paired-spreads.json` ([Spreads](#spreads-and-their-edit-documents)). |

The publisher makes all the selected files before it writes or compares a file. It stops, and
writes nothing, in each of these conditions:

- A named run stops before its horizon.
- The model has a warning of the evidence rule: `no_record` or `datum`
  ([evidence/README.md](evidence/README.md#the-evidence-rule)).
- `brief.toml` has a problem ([brief.toml](#the-settings-of-the-pages-brieftoml)).
- `--only` names `assumptions`, `html`, `methods` or `runs`. These are formats of the earlier
  catalogue at commit `8488047`.

`python -m tools.check --scenario ID` runs the same check for its selection. `tools.check --spreads`
and `tools.check --release` also run the spreads. [Publication scope](../../tools/publish/README.md)
· [Example readings](../cyber_learning_loop/results/readings.md)

### The readings page: `results/readings.md`

- The page has one table for each named run. The runs of `featured` come first. The other named runs
  follow in the order of the model. A model without named runs has one table, for its default run.
- Each table gives each path of `show` at 0 h and at the horizon. Without `show`, the table gives the
  paths that the notes `reporting` and `not_estimated` name. Without these notes, it gives each named
  value of the run.
- A path with a `not_estimated` note shows "Not estimated" and the reason of the note.
- The column "Evidence" names the `record` declarations that the run exercised for the value at that
  time. A list at the end of the page gives the kind and the text of each one.
- A reading is instantaneous. The page applies no reporting lag.
- A number has six significant figures. A value within 10⁻⁶ of its own comparison scale shows as 0.
  Thus the page is the same on each computer.

### The brief page: `results/brief.md`

- The page starts with the title, the summary and the scope of the scenario line.
- The first table is the pair of `featured`, or its one run. Then the page has one table for each
  other `[[comparison]]`, in the order of the file.
- Without `featured` and without comparisons, the page has one table, for the first named run.
- The columns of a pair are: Reading, Unit, the baseline (`against`), the run (`run`),
  "Change (run − baseline)" and "Change (%)".
- The page gives "Change (%)" only when the baseline is more than zero and the unit is not a
  temperature in °C or °F. A change within 10⁻⁶ of the larger of the two scales shows as 0.
- All the readings are at the horizon.

## The settings of the pages: `brief.toml`

`brief.toml` is an optional TOML file of the package or of a variant. The model and its runs do not
read it. The publisher reads it. It refuses a key that it does not know, a value of another shape and
a name that the model does not declare.

| Key | What it holds | Who reads it | Without it |
| --- | --- | --- | --- |
| `show = [p, …]` | The paths that the pages give, in order | Both pages | The paths of the notes, else each named value |
| `featured = [r]` or `[b, r]` | One run, or a baseline and a run | Both pages | The first named run |
| `[[comparison]]` | A run (`run`) and its baseline (`against`) | The brief page | The `comparisons` notes of the model |
| `[[spread]]` | A spread: runs sampled under an edit document | `--sample-spreads` | No spread |
| `[[sweep]]` | One run with other values of some inputs | The notebook of `heat_wave_blackout` | No sweep |
| `drivers = [p, …]` | The inputs that the story turns on | No current page | The inputs that the options set |
| `attack = "…"` | The name of the attack | No current page | No name |
| `choice_group = "…"` | The group of options that holds the responses of the defenders | No current page | No group |

The publisher checks each key, also a key that no current page shows:

- Each path of `show` and of the `outputs` of a spread is a value that a record holds, or a path with
  a `not_estimated` note.
- Each path of `drivers` is an input.
- Each name of `featured`, of a comparison, of a sweep and of a spread is a named run.
- `choice_group` names a group of the options of the model.

### Named comparisons

A named comparison is a table `[[comparison]]` with two named runs. The brief page gives the
readings of `against` and of `run` side by side, and the change from `against` to `run`.

```toml
featured = ["standard", "early_cooling"]

[[comparison]]
run = "early_cooling"
against = "standard"

[[comparison]]
run = "delayed_cooling"
against = "standard"
```

- `run` and `against` are two different named runs. A pair can occur only once.
- `featured = [b, r]` puts the comparison of `r` against `b` first. That comparison must be a
  `[[comparison]]` of the file. The baseline comes first in `featured`.
- When the file has no `[[comparison]]`, the publisher reads the note `comparisons` of the model: a
  note `comparisons: run: against` under `notes:` gives one pair.

[conventions.md](conventions.md#state-a-comparison-in-brieftoml) says how to select the two runs.

### Spreads and their edit documents

A table `[[spread]]` declares a seeded Monte Carlo study of some named runs.

| Key | What it holds | Without it |
| --- | --- | --- |
| `id` | The name of the spread and of its edit document: lowercase letters, digits and `_`, with a letter first | Necessary |
| `description` | What the spread changes, in words | No text |
| `runs` | The named runs that the spread samples | Necessary |
| `samples` | The number of samples of each run, from 1 to 100,000 | Necessary |
| `seed` | The seed of the study, from 0 to 2⁶³ − 1 | Necessary |
| `method` | `random`, the one method of the engine | `random` |
| `outputs` | The paths that the spread reports | The paths of `show` |

```toml
[[spread]]
id = "inspection_spacing"
description = "Inspection interval, hold duration and work sampled once per seed and shared by the response and stop-order choices."
runs = ["fixed_inspections", "rapid_fixed_inspections", "acknowledged_stop"]
samples = 4
seed = 41
method = "random"
outputs = ["incident.accepted", "crews.rework_done", "supply.resident_hours"]
```

The edit document of a spread is `spreads/<id>.json`, in the folder of the `brief.toml`. It is a JSON
object with these keys:

| Key | What it holds |
| --- | --- |
| `schema_version` | `"0.0.1"`, the version of the edit document |
| `model_hash` | The hash of the model that the document is for. `napkin compile` prints it. |
| `set` | Edits of every run of the spread |
| `options` | Edits of the runs that take an option, by the name of the option |
| `runs` | Edits of one named run, by its name |
| `reason` | Why the document makes these edits, in words |

Each edit gives an input by its full path. The value is one of these:

- a number in the unit of the input;
- `true` or `false`;
- a number with its unit, as a text (`"3 days"`);
- a member of an enum, or a text for a text input;
- a distribution, as a text (`"pert(2 h, 4 h, 6 h)"`).

This is the edit document of the spread above:

```json
{
  "schema_version": "0.0.1",
  "model_hash": "cee3575356ec75a1c9216f91ceddfbbfc64ec55abb2b24900577850263c382f8",
  "set": {
    "incident.sample_reports": true,
    "incident.interval_range": "pert(2 h, 4 h, 6 h)",
    "incident.duration_range": "pert(1 h, 2 h, 3 h)",
    "incident.work_range": "pert(0.5 h, 1 h, 1.5 h)"
  }
}
```

- The publisher refuses a spread without its edit document.
- The engine checks the edit document when the spread runs, as it checks every edit document. A
  document for another model hash stops the spread. Thus, when you change a model, write its new
  `model_hash` in the edit document of each of its spreads.
- With `--sample-spreads`, the publisher runs each run of each spread at its `samples` and `seed`.
  A refused document, a stopped sample or an incomplete study stops the command before it writes.
- For each named comparison whose two runs are in one spread, the publisher writes a receipt in
  `results/paired-spreads.json`. The receipt gives the mean and the 5th and 95th percentiles of each
  value, and of the difference in each pair of samples. The publisher pairs the samples of the two
  runs by their sample seed.
- A spread takes time: the number of its samples, times the number of its runs, times the time of one
  run. The `--jobs` processes share this work.

### Sweeps

A table `[[sweep]]` names one run with other values of some inputs. It has four keys, each necessary:

| Key | What it holds |
| --- | --- |
| `id` | The name of the sweep: lowercase letters, digits and `_`, with a letter first. No other sweep and no named run has it. |
| `description` | What the sweep changes, in words |
| `run` | The named run that the sweep changes |
| `set` | The new values. Each key is the path of an input in quotes (`"entity.value"`). Each value is a finite number in the unit of the input, or `true` or `false`. |

```toml
[[sweep]]
id = "heat_wave_48"
description = "A heat wave of 48 hours"
run = "standard"
set = {"heat_wave.length" = 48}
```

No current page shows a sweep. The notebook `heat_wave_blackout/explore.ipynb` runs the sweeps of its
package.

## Notes that the tools read

The language reads `notes:` as free notes. It gives them no meaning, and no run reads them
([language reference](../../docs/language/README.md#notes)). These tools read these notes:

| Note | What it holds | Who reads it |
| --- | --- | --- |
| `reporting: <path>: scope:` | Whom or what the value covers | `tools.check` ([Scope](#the-scope-of-each-value-on-the-pages)) |
| `reporting: <path>: about:` | What the value measures, in words | The publisher: the path goes on the pages when `show` is not given |
| `reporting: <path>: category:` | `deaths`, `casualties`, `loss` or `exposure` | The tests of the catalogue ([Categories](#categories)) |
| `reporting: <path>: lag:` | The reporting lag of the earlier pages | The publisher: the path goes on the pages when `show` is not given. No page applies the lag. |
| `not_estimated: <path>: reason:` | Why the model gives no value for the path, with its `record` declarations | Both pages and `--sample-spreads` |
| `not_estimated: <path>: label:` | The name of the value in words | The publisher: the path goes on the pages when `show` is not given |
| `comparisons: <run>: <against>` | A named comparison | The brief page, when `brief.toml` has no `[[comparison]]` |

A path under `reporting` or `not_estimated` can name a template. Then the note applies to each
instance of the template.

The models of the catalogue also keep these notes for their reviewers:

- `premises` and `limitations`;
- `verification`, with `research`, the path of the research note from the folder of the package;
- `counterfactual` and `decisive`.

No current tool reads their text. The evidence tools follow the `record` declarations that a note
cites, as they follow every other citation.

## The scope of each value on the pages

The language lets a value have no scope. The catalogue does not. `tools.check` requires one of these
two for each model:

- a `scope "…"` on the scenario line, or on the `variant` line of the variant;
- a note `reporting: <path>: scope: "…"` for each path on the pages. These are the paths of `show`,
  and the paths that the notes `reporting` and `not_estimated` name.

## Categories

A note `reporting: <path>: category:` gives a value a category. The language does not read it, and
the library lists no categories.

| Category | What the value counts | Check |
| --- | --- | --- |
| `deaths` | Deaths that the scenario causes | Finite and not negative at the horizon of each named run |
| `casualties` | Serious casualties, deaths included | Finite and not negative. Not less than the deaths of the same run. |
| `loss` | Economic loss | Finite and not negative |
| `exposure` | The people that the study follows | No check |

The test `scenarios/tests/test_catalogue.py` does these checks. It does not check a path with a
`not_estimated` note, because the model gives no value for it. The `record` declaration of a
casualty value cites the convention `HAZUS-SEVERITY` of the library, which says what a serious
casualty is (`convention HAZUS-SEVERITY`). No tool checks this citation.

## Research notes

A path in a note, such as `research: "evidence/research.md"` under `verification`, starts at the
folder of the package. Thus the research note of a variant is
`variants/<name>/evidence/research.md`.
