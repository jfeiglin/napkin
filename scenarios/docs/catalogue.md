# The catalogue's rules

The catalogue is the folder `scenarios/` of the checkout. Its tools hold its models to rules of their
own, beyond those of the language ([language.md](../../docs/language.md)): the locator (`tools/catalogue.py`),
the check (`tools/check.py`) and the publisher (`tools/publish/`). The compiler reads none of these
rules, so a model outside the catalogue need not follow them. This page and the catalogue's other
guides are in `scenarios/docs/`.

## Publishing readings from a current model

Give the publisher a package folder or an entry file to write its `results/readings.md`. The page lists
the values selected by `brief.toml` at the start and horizon of each named run, with units and the
evidence the run exercised at each time. Featured runs come first. A package with no named runs has
one default run. A value described in the model's `not_estimated` notes appears with its stated reason.

```sh
python -m tools.publish --model scenarios/cyber_learning_loop --write
python -m tools.publish --model scenarios/cyber_learning_loop --check
```

`--check` compares the generated page byte for byte. The public record and its compiler side table
supply the values, units and citations. An incomplete run or a compiler evidence diagnostic
(`no_record` or `datum`) prevents publication. A scoped `--scenario ID` check verifies the named-run readings, the
comparison brief and the current source dossier. A whole-catalogue check adds the source
manifest. [Publication scope](../../tools/publish/README.md) · [Example readings](../cyber_learning_loop/results/readings.md)

## Folders and names

- A scenario of the catalogue is a package: a folder `scenarios/<package>/` with its main file,
  `model.scn`. The name of the folder is the name of the package, such as `iv_fluid_shortage`: it
  starts with a lowercase letter and has only lowercase letters, digits and `_`. The scenario line has
  no name: the folders name the scenario. The folders `docs`, `library` and `tests` of `scenarios/` are
  the catalogue's own, and no package has their names. The tests also make packages with reserved IDs,
  `SC` and two digits (`SC97`), which no package of the catalogue has.
- A variant of a package is the folder `scenarios/<package>/variants/<name>/` with its own
  `model.scn`. Its name is `<package>:<name>` in the reports, in the tools and in `--scenario`. The
  name of a variant's folder starts with a lowercase letter and has only lowercase letters, digits and
  `_`.
- A package and each of its variants own their folders: the units (`units.json`), the evidence
  (`evidence/`), the results (`results/`), the stylesheet (`style.toml`), the brief settings
  (`brief.toml`) and the edit documents of its spreads (`spreads/`), the README and the tests
  (`tests/`). The
  evidence of a package's folder serves the package and its variants, and a variant's folder serves
  that variant only. `--scenario <package>` selects the package and its variants, and `--scenario
  <package>:<name>` one variant.
- Each main file names the shared library with `library "../library"`: the file
  `scenarios/library/vocabulary.json` of the catalogue.
- A record name or a note key holds no catalogue ID, such as `a_pilot_assumed_brief`: the folders
  name the scenario. The IDs of evidence records, such as `RT-SECTOR-SC10-2026`, are opaque keys and
  keep their IDs.

## The scope of each output

The language lets an output give no scope. The catalogue does not: `tools.check` requires a scope for
each output of each model, its own (`scope "…"` under the output) or the default scope of the
scenario line (`scope "…"` under `scenario "Title"`).

## Categories

An output's `category` is a tag that the language does not read, and the library lists no categories.
Each output of the tag `casualties` cites the convention `HAZUS-SEVERITY` of the library, which says
what a serious casualty is (a record `convention HAZUS-SEVERITY`). The pages read the tags `deaths`,
`casualties` and `loss`, which each scenario reports or marks `unestimated` with the reason, and
`exposure`, which the note `exposure` explains.

## The brief settings: brief.toml

The active brief uses `show` to select readings and `featured` to order the opening comparison.
Give each additional pair its own table. Both names must identify runs in the same model.

```toml
[[comparison]]
run = "followup_quality_review"
against = "fixed_quality_review"
```

The publisher writes each pair's horizon readings to `results/brief.md` and includes units.
The readings page has the evidence exercised by each run. The historical format also used
`attack` and `choice_group` to annotate a narrative. [Publication formats and commands](../../tools/publish/README.md)

### The sweeps: `[[sweep]]`

A sweep specifies one run with alternative input values. Historical run tables used these declarations
to produce rows in `results/runs.csv` and `results/runs.json`.

| Key | What it holds |
| --- | --- |
| `id` | The name of the row: lowercase letters, digits and `_`, and a letter first. No other sweep and no run has it |
| `description` | What the sweep changes, in words |
| `run` | The run that the sweep changes |
| `set` | The new values. Each key is the name of an input in quotes, as an edit names it (`"entity.value"`). Each value is a number in the unit of the input, or `true` or `false` |

```toml
[[sweep]]
id = "removal_1d"
description = "Responders remove the credential a day after recognition"
run = "delayed_kept"
set = {"responders.removal_time" = 24}
```

The publisher reads the sweeps, and it rejects a key that it does not read, a value of another shape,
an id that two entries give, and a name that the model does not declare. The engine checks each
value as it checks every edit (docs/engine.md, "The edit document").

### The spreads: `[[spread]]`

Each `[[spread]]` table declares a seeded Monte Carlo study. Run the publisher with
`--sample-spreads` to execute it. Its edit document,
`spreads/<id>.json` in the folder of the model file, gives the inputs their distributions. It is an
edit document of version 0.0.1, for the model's revision (`schema_version`, `model_hash`, and `set`,
`options` or `runs`). The edit applies to the sampled study.

| Key | What it holds | Without it |
| --- | --- | --- |
| `id` | The name of the spread and of its edit document: lowercase letters, digits and `_`, and a letter first | Necessary |
| `description` | What the spread changes, in words | No text |
| `runs` | The runs that the spread samples, each once. The brief shows them in the order of the model file | Necessary |
| `samples`, `seed` | The number of samples, from 1 to 100,000, and the seed of the draws, from 0 to 2^63 − 1 | Necessary |
| `method` | The engine uses seeded random sampling | `random` |
| `outputs` | The outputs that the brief shows for the spread | The brief's measures |

```toml
[[spread]]
id = "tipping_corner"
runs = ["no_ai"]
samples = 100
seed = 4501
outputs = ["attacks_per_year", "share_on_attacks"]
```

The publisher rejects a key that it does not read, a value of another shape, an id that two entries
give, a name that the model does not declare and a spread without its edit document. The engine
checks the edit document when the spread runs, as it checks every edit document: a document of
another model revision stops the brief, and so does a sample that the engine rejects, so a brief
never shows part of a spread. A change to a model changes its `model_hash`, so the edit document of
each of its spreads takes the new `model_hash` too. A spread can take many minutes: its time is the
number of its samples times its runs, times the time of one run, shared among the processes.

## Notes

The language reads `notes:` as free-form notes ([language.md](../../docs/language.md), §2.11). The pages read
these keys, and they reject a note that nothing reads, such as a misspelt key:

| Note | What it holds | Who reads it |
| --- | --- | --- |
| `limitations` | Entries `ID: "statement"  @record`: the limits of the results | The brief and the methods page |
| `premises` | Entries `ID: "statement"  @record`, each with an optional `otherwise: "…"`. The premise `START` states the limits of the first move and needs no record | The methods page |
| `exposure` | How to read the output whose category is `exposure` | The pages |
| `verification`, `reachability`, `benchmark` | The consequence review, the reachability assessment and the source benchmark, each a record of notes | The pages |
| `counterfactual`, `decisive` | What a human team could equally do, and the decisive defender choice | The brief |

- An ID of an entry is a word of letters, digits and hyphens: `PR1`, `demo-one-plant`.
- The pages also reject a line under an entry other than a premise's `otherwise:`, a note of entries
  written as a text, and a copy of a claim's verification status (`verification_status`): the
  library holds it.
- The records that `benchmark` cites are the claims of the source benchmark.

## Research

The paths in the notes, such as `research: "evidence/research.md"` under `verification`, are
relative to the package's folder: the research of a variant is
`variants/<name>/evidence/research.md`.
