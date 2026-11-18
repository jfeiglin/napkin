# Brief B0-4: triage of the existing tests

Read-only work on the tests, for a rewrite of the napkin language. You classify test files. You
change no test and run none.

## Read first

- `scratch/rewrite/PLAN.md`: "The approach in six choices", "The slices" (S0 to S6), "Existing
  tests" and "Not in this plan".
- `scratch/rewrite/spec.md`: the first table ("What changes for a model author"), "Reference
  behavior in the current compiler", and enough of the rest to know what the new language keeps
  and what it drops.

In short: the old language is replaced in place. A model becomes templates and members; each start
of an event is a separate occurrence with stages (`after`, `until`) and attached triggers; flows
have a `capacity`, a `request` and an `actual_rate`, with sharing at endpoints; one collection type;
solvers; `sampled` or `median` runs. The old compiled forms (the flat structure, the hybrid core,
the per-option start structures) go. Whole-run derivatives go. The old events go: one pending
firing for each rule, rearming, windows, the cancel on `while`, outcomes in their old form.
`versus` and the `output` settings go. The numerical core stays: expressions and units
(`napkin/core/`), the continuous engine (bounds, faces, floors, roundoff, integration, switching,
closed forms), sampling and plain estimators.

New engine tests will build a program in Python and never parse. New front-end tests go from
source to a program and never simulate.

## What you produce

One CSV file, at the path that your prompt gives you, with a header and one row for each test file
(`test_*.py`) of your list. Helper files (`helpers.py`, `models.py`, a `conftest.py`) get a row
too, with class `HELPER`. Columns:

| Column | Value |
| --- | --- |
| `path` | from the root of the checkout |
| `lines` | of the file |
| `tests` | the count of test functions (a parametrized one counts once) |
| `needs` | `none` (no model text and no compiler), `source` (compiles model text), `catalogue` (reads `scenarios/` or `examples/`) |
| `class` | one of the classes below; for a mixed file, the class of the larger part |
| `slice` | where the work falls: `S0` values, a store and one flow; `S1` templates, tables, collections; `S2` the flow network and sharing; `S3` reversible flows and flows with legs; `S4` occurrences, time, draws, choices; `S5` solvers; `S6` packages, options, edits; `C` consumers; `M` catalogue; `B0` now; `-` none |
| `delete_share` | for a mixed file, the rough share of its tests that are `DELETE`, in percent; else empty |
| `oracle` | where the expected values come from: `closed-form`, `property`, `independent-code` (a second calculation in the test), `pinned-run` (numbers that look copied from a run), `message-text`, `structure` (compares compiled structures), or two of these with `+` |
| `note` | 20 words at most: what the file tests, and what decides its class |

Classes:

- `KEEP`: tests a module whose behaviour stays, and needs no language. It runs unchanged.
- `RULES`: needs no language, but the rules that it tests change (for example the rationing of
  flows).
- `PORT-ENGINE`: tests numerics or run behaviour that stays, but builds its model from old source
  text. It is written again on program builders.
- `PORT-FRONT`: tests the front end for something that survives (units, modules, packages, tables,
  identity, diagnostics, formatting). It is written again in the slice that brings the construct.
- `PORT-CONSUMER`: tests a consumer of models and runs (reports, studies, the store, the command
  line, drawing, publishing, evidence tools).
- `DELETE`: tests a feature that the rewrite removes.
- `HELPER`: no test of its own.

Judge by what a file asserts, not by its name. Open each file. For a long file, read the module
docstring, the names and docstrings of the tests, and enough bodies to know the oracle. Where you
are not sure, say so in the note and choose the class that keeps the test.

## Last message

200 words at most: the count of files in each class, the files that surprised you, and the path of
your CSV.
