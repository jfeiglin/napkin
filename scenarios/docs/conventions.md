# The conventions of the catalogue

This page gives the conventions that the models of the catalogue obey. The
[language reference](../../docs/language/README.md) gives the rules of each line, and the
[modelling guide](../../docs/modeling-guide.md) says how to write a model on any subject. This page
uses the terms of the language reference ([Terms](../../docs/language/README.md#terms)).

The compiler reads none of these conventions. Some of them are rules of the tools of the catalogue
([catalogue.md](catalogue.md)): `tools.check`, the publisher and the tests of the catalogue refuse a
package that breaks them. The authors and the reviewers check the other conventions.

## Start a package

1. Run `python -B -m tools.new PACKAGE --title "Title"`. It makes the folder `scenarios/PACKAGE/`
   with 11 files, each in its shape and with no content, and it prints the list of what to write.
2. Write the model part by part.
3. After each part, run `napkin compile scenarios/PACKAGE`. It gives the file, the line and the
   column of each diagnostic.
4. Run `napkin run scenarios/PACKAGE`. It gives the values of the default run at 0 h and at the
   horizon. Add `--run NAME` for a named run, and `--edits FILE` for an edit document.
5. Write `roles.toml` ([Who plays each part](#who-plays-each-part)). `tools.new` does not make it.
6. Write the pages with `python -B -m tools.publish --write --scenario PACKAGE`.
7. Run `python -B -m tools.check --scenario PACKAGE`, and correct the package until the check
   passes.

The run store keeps each run. Thus, after a change, only the runs that the change touches run again.
The commands are in [cli.md](../../docs/cli.md).

Write each text that a reader sees in simple, clear sentences: the text of each entity, template,
value, event, option and named run.

## Names

| Name | Rule | Example |
| --- | --- | --- |
| A package | Its folder: a lowercase letter, then lowercase letters, digits and `_` | `iv_fluid_shortage` |
| A variant | Its folder, with the same rule. The tools write `<package>:<name>`. | `water_controls_wipe:lumberton` |
| An entity, a value, an event, a flow | A small letter first, then letters, digits and `_` | `quality_review.received` |
| A template | A capital letter first | `Utility`, `Households` |
| A member of an enum | Capital letters | `FIXED`, `AFTER_REVIEW` |
| A named run | Lowercase letters, digits and `_`, with a letter first | `followup_quality_review` |
| An option and its group | A text in quotes. The name of an option occurs in one group only. | `"Fixed notice interval"` in `"Quality documentation"` |
| A `record` declaration | Lowercase letters, digits and `_`. It names what it supports. | `lumberton_storage` |
| A claim or an assumption of the evidence | An opaque ID in capital letters and hyphens. Do not change it. | `E-SC43-LUMBERTON-CITY-STORAGE`, `A-SC43-REACH` |
| A sweep or a spread of `brief.toml` | Lowercase letters, digits and `_`, with a letter first | `inspection_spacing` |

- Name a named run for the difference that it shows, not for its order: `expedited_quality_review`,
  not `run_2`.
- Name a value for what it holds. Add the unit to the name when the name alone is not clear:
  `shortage_days`, `loss_bn`.

## Units

- Write each number with its unit: `240 h`, `0.42 USD2025_m/person/year`. A bare number takes the
  declared unit of its place.
- Write a compound unit with `*` and `/`: `work_h/h`, `people/day`, `USD2025/h`.
- Write a currency with its price year: `USD2025`, not `USD`.
- The prelude of the language gives the units of time and of people: `h`, `day`, `year`, `people`,
  `fraction`, `ratio` and their plurals.
- The shared library `scenarios/library/vocabulary.json` gives the other common units of the
  catalogue, for example `L`, `Mgal/day` and `USD2025`.
- Put a unit that only one package uses in the `units.json` of that package. A unit name occurs in
  one place only: the prelude, the library or one `units.json`.

Each unit of `units.json` gives its `dimensions` and its `scale` in the base units. It can also give
a `kind`, a `label` and a `description`.

```json
{
  "staff_years": {
    "kind": "quantity",
    "dimensions": {
      "people": 1,
      "time": 1
    },
    "scale": 8760,
    "description": "Baseline-equivalent work completed by one full-time expert in one 365-day year."
  }
}
```

## Scales

Give each stock and each tally a `scale` near the largest value that it can reach in a run.

```scn
    waiting: work_h = 0 work_h in [0,] scale 100 work_h @support_exercise
```

- A scale is not a bound. The range `in [lo, hi]` is the bound.
- A scale sets the comparison band of the value and the accuracy of the integration
  ([numerics.md](../../docs/language/numerics.md)). It can also choose among answers of a solver that
  are equally good ([change 33](../../docs/design/decisions.md#change-33)).
- A value without a `scale` compares with the size of one of its units.
- The pages show a value within 10⁻⁶ of its own comparison scale as 0. A scale that is too large can
  thus hide a small value on the pages. A scale that is too small makes the integration work harder.
- A number that you write in the model is exact. It adds no comparison band of its own.

## Titles and texts

- Give each entity and each template a text on the row under its line. The text is its description.
- Give each value that a page shows a text. The text is its label.
- Give a member a `title` when its name is not clear to a reader. Reports and playback show the title.
  No hash covers it.
- In a variant, put the name of the place in the title of each member of the place.

```scn
lumberton_homes: Households
    "The people that Lumberton serves."
    title "Lumberton: homes"
    utility = lumberton
    population = 24460 people @lumberton_homes_population
```

The title of a variant is the title of its package, a colon and the title of the `variant` line:
"Water service recovery after a controls outage: Lumberton, North Carolina".

## Who plays each part

A model does not say who plays a part. The compiler refuses such a line, and it says where the
information goes ([change 23](../../docs/design/decisions.md#change-23)). Two files of the package
hold it:

| File | What it holds | Who reads it |
| --- | --- | --- |
| `roles.toml` | `[entities]`: an entity or a template, and who plays it. `[events]`: an event (`"entity.event"`), and who plays it. | The wrapper of the scenario: a publisher or a user interface. No current tool reads it. |
| `style.toml`, `[role]` | Each role, and the entities and templates that play it | `napkin draw`: the icon of a card when `[icon]` gives none, the words "who acts", and the group |

```toml
[entities]
"deliveries" = "operator"
"high_risk_patients" = "community"
"hospitals" = "responder"
"manufacturer" = "operator"

[events]
"manufacturer.stops_shipping" = "environment"
```

```toml
[role]
environment = ["heat_wave", "Buildings", "supply", "devices", "incident", "extra"]
community = ["AgeBand", "moves", "Customers", "Residents", "DeviceUsers", "Confined"]
utility = ["crews", "utility"]
```

- A role is one of `adversary`, `responder`, `operator`, `environment`, `community` and `clinician`,
  or the name of a card of the picture: an entity, a member written by hand or a table. The test `tests/evidence/test_catalogue.py` checks the
  roles of both files.
- An entity or a template plays one role at most.
- Give the same role to a part in both files.

## Evidence

Each choice of a model shows its support: a `record` declaration. The evidence rule
([evidence/README.md](evidence/README.md#the-evidence-rule)) gives the parts that need one. A
package of the catalogue has no warning of the evidence rule.

- Cite a `record` declaration by its name after the line: `@name`. A line can cite more than one.

  ```scn
      input removal_time = 240 h in [1 h, 720 h] @response_basis @removal_basis
  ```

- Write a `record` declaration at the top level, after the parts of the model. Give it a kind:
  `source`, `source_transfer`, `assumption`, `identity` or `convention`.
- Under a `record` declaration, name the claims (`claims:`) and the assumption or the convention of
  the evidence (`assumption ID`, `convention ID`).
- When a value is the number that a claim states, tie it to that datum with `datum: key`. The
  compiler then checks that the value is that number.

  ```scn
  record lumberton_storage: source "Finished water storage capacity reported in the 2025 plan, 7.5 Mgal (the 16
      Mgal of off-stream raw water storage is not counted)."
      claims:
          E-SC43-LUMBERTON-CITY-STORAGE
              datum: finished_storage
  ```

- Put the `record` declaration that supports a whole entity on the line of the entity
  (`incident: @service_incident`). A Boolean of the entity without a record of its own rests on it.
- A number or a Boolean that an option or a `change` sets needs a `record` declaration of its own.
  Without one, the model does not compile.
- Sources and claims come only through `tools.evidence.integrate`. A record of another package comes
  through `tools.evidence.adopt`.

## Options and named runs

- Put the options in groups. Name each group for what its options change: `"Cooling response"`,
  `"Stop order"`, `"Quality documentation"`.
- Give each option a text on the row under its name. The text is its menu line.
- An option sets inputs only, each by its full path. Each number or Boolean that it sets cites a
  `record` declaration.
- An option with a text and no setting keeps the values of the model. Name it for what it keeps:
  `"Usual protection"`.
- Make the options of one group differ in input values only, not in how the model works. Put a change
  of how the model works in the model, and let an input select it.
- A named run takes one option of a group at most, with `+` between the options. Two options of one
  run must not set the same input.
- Give each named run a text on the row under it. The text says what the run shows.

```scn
options "Stop order":
    "Await independent containment":
        "Reports may still arrive after the stop order until the response team contains the incident."
    "Acknowledge the stop order":
        incident.acknowledge_stop = true @inspection_exercise
```

```scn
    subpar_persistent = "Standard response" + "Additional records" + "Review needed"
        "Standard response with records and product review"
    subpar_persistent_human = "Standard response" + "Additional records" + "Clear"
        "Standard response with records review and a clear first lot"
```

- Put the response tiers of the defenders in one group. Name that group in `choice_group` of
  `brief.toml`. The publisher checks that the group exists.
- A model without named runs has one default run. A package of the catalogue declares its named runs.

## State a comparison in `brief.toml`

A comparison of two policies is two named runs and one table `[[comparison]]`
([catalogue.md](catalogue.md#named-comparisons)). The model holds no comparison. The engine runs each
named run separately, and the brief page compares the two records.

1. Write the baseline as a named run.
2. Write the second named run with the same options as the baseline, except the options that the
   comparison studies.
3. Add a table `[[comparison]]` to `brief.toml`. Write the second run in `run` and the baseline in
   `against`.
4. To show the pair first on the brief page, write `featured = ["baseline", "run"]`. The baseline
   comes first.
5. List in `show` the values that the comparison is about, the most important first.
6. Run `python -B -m tools.publish --write --scenario PACKAGE`, and read `results/brief.md`.

```toml
featured = ["subpar_persistent", "subpar_persistent_human"]
choice_group = "Response"

[[comparison]]
run = "subpar_persistent_human"
against = "subpar_persistent"
```

The brief page gives the change "run − baseline" for each value. Thus the comparison shows what the
options of `run` add to the baseline. A comparison of two runs that differ in more options does not
show which option causes the change.

## Change a model of the catalogue

`python -B -m tools.compare BASE OTHER` compares two runs by their names, their values and their
traces. A side is a model, which the tool runs now, or a capture that `--write FILE` keeps. Do these
steps:

1. Before the change, keep a capture: `python -B -m tools.compare scenarios/PACKAGE --write before.json --run NAME`.
2. Make the change.
3. Compare: `python -B -m tools.compare before.json scenarios/PACKAGE --run NAME`.
4. Make sure that each difference is one that the change must make.
5. Write the pages again, and run `python -B -m tools.check --scenario PACKAGE`.
