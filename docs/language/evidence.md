# Evidence

Each number of a model shows its support. A `record` declaration states that support once, and a
line cites it with `@name`. This page gives the form of a `record` declaration, the citations, the
library that the declarations name, the datum rule and the evidence rule. The words in bold are the
[terms](README.md#terms) of the documentation.

The keyword `record` declares evidence. This page always writes it in code type, as a `record`
declaration. The word record alone means the result of a run.

## Contents

1. [A `record` declaration](#a-record-declaration)
2. [Citations](#citations)
3. [A `record` declaration in place](#a-record-declaration-in-place)
4. [The library](#the-library)
5. [The datum rule](#the-datum-rule)
6. [The evidence rule](#the-evidence-rule)
7. [Values that an option or a change sets](#values-that-an-option-or-a-change-sets)
8. [Assumptions and values that a model leaves out](#assumptions-and-values-that-a-model-leaves-out)
9. [The evidence of a reading](#the-evidence-of-a-reading)

## A `record` declaration

`record name: kind "explanation"` stands at the top level. Its kind says how it supports the line
that cites it. The lines under it name what it rests on.

```scn
record timing: source_transfer "Applied from another setting."
    assumption A-TIMING
    claims:
        E-REPAIR-STUDY
```

| Kind | What the `record` declaration states |
| --- | --- |
| `source` | A source supports the number. |
| `source_transfer` | A source from another setting supports the number, applied to this setting. |
| `assumption` | The author assumes the number. |
| `identity` | The number follows from a definition or a count, such as "each tuning counts once". |
| `convention` | The number follows a convention that models share. |

The lines under a `record` declaration:

- `assumption ID` names an assumption of the library by its ID. `convention ID` names a convention
  of the library.
- `claims:` holds one claim ID on each row under it. Each row names a claim of the library.
- `datum: key` under a claim ties the value that cites the declaration to one datum of the claim
  ([The datum rule](#the-datum-rule)).

The kind follows the colon on the line of the declaration. An ID such as `A-TIMING` is one word,
with no space in it. The explanation of a `record` declaration does not change the hash of the
model.

## Citations

A line cites a `record` declaration with `@name`, at the end of the line or on a row of its own
under it. A line can cite several declarations: `@survey @count`.

```scn
reservoir:
    "The reservoir."
    water: fraction = 0.6 in [0,] scale 1
        "Water in the reservoir"
        @assumption "The example assumes that the reservoir is 60% full when the storm starts."
    spilled: fraction = 0 scale 1  @counts
        "Water let out over the spillway"

record counts: identity "The model counts the water that comes in and goes out, each share once."
```

Most lines take a citation at the end of the line or on a row under it: a value, an input, a flow,
an event, a trigger, a stage, a case of a `switch`, a solver, a status case, an assertion, an
entity, a template, a table, the own value of a member, an option setting, a `change` and a note.
Three places differ:

| Line | Where its citation stands |
| --- | --- |
| An assignment or a `move` in a stage | Only at the end of its line |
| A column of a table | In its header cell: `base_need: W @survey` |
| A stored Boolean, a case of a status display | On its own line, or on its entity or template ([The evidence rule](#the-evidence-rule)) |

- `@name` names a `record` declaration of the model. A name that names no declaration is an error.
- Text and evidence stand on rows of their own under the line. A text never stands on the line
  itself.

## A `record` declaration in place

A row `@kind "explanation"` under a line is a `record` declaration with no name, for that line
alone. Its IDs and its claims stand under it, as under a named declaration.

```scn
tuners:
    "The piano tuners of the town."
    input rate: tunings/(tuner * year) = pert(600, 1000, 1200).draw() in [500, 1500]
        "Tunings that one tuner does in a year"
        @assumption "The example assumes about four tunings in each working day, and a spread around it."
```

A declaration in place stands on a row of its own. It cannot stand at the end of a line.

## The library

The IDs that a `record` declaration names belong to the library of the model. The library holds
sources, claims, assumptions and conventions.

| Where | What it holds |
| --- | --- |
| `vocabulary.json` in the folder that `library "PATH"` names | A shared library of units and evidence |
| `evidence/sources.json` of the package or the variant | The sources of the package |
| `evidence/claims.json` | The claims of the package. A claim can hold data: each datum has a key, a number and a unit. |
| `evidence/assumptions.json` | The assumptions of the package |

- Every ID that a `record` declaration names must resolve in the library. An unknown assumption,
  convention, claim or datum is an error at the line that names it (`provenance`).
- Each record of the package folder must be in use. A record that no model of the package reaches
  is an error (`unused_evidence`).
- A claim has a verification record with a digest of the claim. A claim that changes without a new
  review fails.
- An ID is in one folder only.

`napkin/schema/library.schema.json` gives the form of these files.

## The datum rule

A value whose `record` declaration names a datum (`datum: key` under a claim) must be that number.

- The compiler folds the initializer of the value exactly. A number token is the exact decimal of
  its text ([numerics.md](numerics.md#exact-literals)).
- The value and the datum must have the same dimension and the same exact value in canonical units. `0.1 day` is the
  datum 2.4 h. `48 people/day` is the datum 2 people/h. `sqrt(34 h * 34 h)` is the datum 34 h.
- A datum states a number and a unit, and no precision. A value near a datum is not the datum:
  34.04 h is not the datum 34.0 h. Such a value needs a derivation, a transfer or an assumption.
- A difference is a warning with the code `datum`. The warning gives both numbers:
  `service.end: @timing cites the datum delay of C-ACTION, 34 h, and 99 h differs from it`.
- A value that the compiler cannot fold also gets the warning: a draw, or a read of another value.
  So does a value that is no number: a distribution, a Boolean, a link.

The rule covers the values of entities, templates and the top level, the parameters and locals of
events, the unknowns of solvers, the own values of members, the cells of tables, and the settings of
options.

## The evidence rule

The compiler warns of each part of these kinds that cites no `record` declaration:

- an input, except a text input;
- a stored number or Boolean of an entity, a template or the top level;
- an event that acts at a time: an event with a stage or a trigger;
- a case of a status display;
- an assertion;
- a number, a Boolean or a distribution that a member written by hand gives as its own value;
- a column of a table that holds such values. The citations of a column are in its header.

A part can rest on the declarations of its entity or template:

- A stored Boolean with no citation of its own rests on the citations of its entity or template.
- A case of a status display rests on the citations of its entity or template.
- An entity, a template and a member need no citation for themselves. Their parts do.

These parts need no citation: a text, a member of an enum, a link, a collection and a formula.

Each warning has the code `no_record`, at the line of the part. A warning of a column is at the
header of the file of its table.

```text
plant.water: a stored value rests on no record: cite one (@name) or write one under it
```

- A model with a warning still compiles and runs. A model under exploration needs no evidence yet.
- `tools.check` and the publisher refuse a scenario package with a `no_record` warning.
  `tools.check` also refuses one with a `datum` warning.
- `napkin run` gives the warnings as one line that counts them, and `--json` gives each one
  ([cli.md](../cli.md)).

## Values that an option or a change sets

A number, a Boolean or a distribution that an option or a `change` sets needs a citation. Without
one, the model does not compile: this is an error with the code `record`, not a warning.

```scn
options "Fill":
    "Usual fill":
        "The plant fills at its own rate."
    "Quick fill":
        "The plant fills at 4 L/h."
        plant.rate = 4 L/h  @fixture
```

- A value that an option or a `change` sets can cite an assumption for a case that the author
  supposes.
- A `record` declaration that the model uses again for the new value must support the new value.
- An argument of an event needs no citation. It is a value that the model calculates, and its
  evidence is on the declaration that it comes from.

## Assumptions and values that a model leaves out

An `assumption` declaration states what the author supposes. A model cites it like any other
`record` declaration.

```scn
record survey: assumption "The example assumes these sizes and rates."
record operator: assumption "The example assumes that the operator brings water when the tank is low."
```

A model declares what it can state. A model that cannot estimate a value leaves the declaration out
and says why in its documentation or its evidence. The language has no empty value for a missing
estimate. For example, a water model can calculate the volume of water that its customers did not
get. It cannot tell how many people went a whole week without water, because equal daily totals can
be the same people each day or different people. It declares the volume, and its documentation
explains why it has no weekly count of people.

A citation documents an interpretation. It proves no numeric rule. A proof that a value never falls
comes from the compiler, not from a `record` declaration.

## The evidence of a reading

A report gives the evidence trail of each value that it shows. The trail of a value of a member, in
a run, holds in this order:

1. the citations of the declaration in its template;
2. the citations of the own line of the member, or of the column of its table;
3. the citations of the settings of the options that the run takes.

`napkin run --json` gives the trail of each path, and the `record` declarations that the trails
cite ([cli.md](../cli.md)).
