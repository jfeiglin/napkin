# The evidence of the catalogue

This page tells where the evidence of the catalogue is, which rule the models obey, and which tools
get, check and write the evidence. [evidence.md](../../../docs/language/evidence.md) gives the rules
of a `record` declaration in a model. This page uses the terms of the language reference
([Terms](../../../docs/language/README.md#terms)).

## Where the evidence is

| Place | What it holds | Who writes it |
| --- | --- | --- |
| `scenarios/<owner>/evidence/sources.json` | The sources of the owner: each document, its locator, its verification and its retrieval records | `tools.evidence.integrate`, `tools.evidence.adopt` |
| `scenarios/<owner>/evidence/claims.json` | The claims of the owner: each with its source, its locator, its excerpts, its data and its verification record | `tools.evidence.integrate`, `tools.evidence.adopt` |
| `scenarios/<owner>/evidence/assumptions.json` | The assumptions of the owner: the condition that the model takes, the claims that support it, and its review status | `tools.evidence.integrate` with an assumption pack, `tools.evidence.adopt` |
| `scenarios/<owner>/evidence/research.md` | The research note: how the model uses each value, its limits, and the measurements that it still needs | The author |
| The `record` declarations of the model | The kind of each support, its explanation, and the claims, assumptions and conventions that it names | The author |
| `scenarios/library/vocabulary.json` | The shared units and the conventions of the project, for example `HAZUS-SEVERITY`. It holds no sources, claims or assumptions today. | The author |
| `scenarios/<owner>/results/source-dossier.json` | The model hash, the sources and claims of the owner, their verification records, and the claims that the model reaches | The publisher |
| [source-manifest.json](source-manifest.json) | The sources of the shared library and of each owner of the catalogue, with their retrieval records | The publisher (`--only manifest`) |

- The evidence of the folder of a package serves the package and all its variants. The evidence of the
  folder of a variant serves that variant only.
- A package with only `record` declarations that name no source needs no `evidence/` folder.
  `cyber_learning_loop` is such a package.
- The [consequence guide](consequences/README.md) gives the common rules for deaths, serious
  casualties and economic loss.

## The evidence rule

Each choice of a model shows its support: a `record` declaration. Cite it with `@name` after the
line, or write an inline `@kind "explanation"` on its own row under the line. The compiler warns of
each of these parts when it has no support:

- an input, except a text input;
- a stored number or Boolean of an entity, a template or the top level: a stock, a tally or a state.
  A Boolean with no `record` declaration of its own rests on the declarations of its entity;
- an event that acts at a time, with a stage or a trigger;
- a case of a status display. A case with no `record` declaration of its own rests on the
  declarations of its entity;
- an assertion;
- a number, a Boolean or a distribution that a member written by hand gives as its own value;
- a column of a table that holds such values. Its `record` declarations are in the header of the
  column.

A text, a member of an enum, a link, a collection and a formula need no support. The warning has the
code `no_record`, at the line of the part:

```text
model.scn:5: warning: queue.serve_rate: an input rests on no record: cite one (@name) or write one under it [no_record]
```

A `record` declaration can tie a value to a datum of a claim (`claims:`, then `datum: key` under the
claim). The value must then be that number exactly, in the same dimension, after the conversion of
its unit. For example, `0.1 day` is the datum `2.4 h`. Each of these gives a warning with the code
`datum`:

- a value that differs from the datum, with both numbers;
- a value that the compiler cannot fix, because the run calculates it (a draw, or a read of another
  value);
- a value that is not a number: a distribution, a Boolean or a link.

A number, a Boolean or a distribution that an option or a `change` sets needs a `record`
declaration. Without one, the model does not compile.

A model with a `no_record` or `datum` warning still runs, so that an author can explore it. `napkin
run` prints one line about the warnings, and `napkin compile` lists each one. A package of the
catalogue has no such warning:

- The evidence stage of `python -m tools.check` compiles each selected package. It fails for each
  warning, at its file and line.
- The publisher refuses to make the brief page and the readings page of a model with such a warning.

## Reproduce the evidence checks

Use Python 3.14 and Ghostscript 10.07.1. The extraction records of the claims name these versions.
Put `gs` on the `PATH`, or set `EVIDENCE_GHOSTSCRIPT` to the path of the Ghostscript program.

```sh
python -m tools.evidence.manifest --check
python -m tools.evidence.manifest --restore-project
python -m tools.evidence.manifest --acquire SOURCE_ID
python -m tools.evidence.manifest --acquire-all
python -m tools.evidence.manifest --import SOURCE_ID=/path/to/raw-document
python -m tools.evidence.integrate --check --complete --report complete-evidence-check.json
```

- `manifest` and `integrate --check` accept `--root PATH`.
- `manifest --scenario ID` selects one owner for the acquisition of its sources.
- `integrate --check --scenario ID` checks one owner. Repeat it for more owners.
- `--acquire-all` restores every source. It uses again the cached bytes whose hash matches. Its
  report names each source that needs an import of archived bytes.
- `--import` accepts bytes only when their SHA-256 and their size match the record.

The cache of raw bytes is shared by content hash. `EVIDENCE_CACHE` sets its folder. Without it, the
tools find the main checkout through the common folder of Git, else the root of the repository. Thus
a linked worktree uses the same bytes as the main checkout.

The complete check (`integrate --check --complete`) needs a retrieval record and cached raw bytes for
each source and claim. It extracts the text of the original bytes again, checks the extraction
identifiers and the text digests, and matches each excerpt. Its report gives the coverage, the
acquisition checks, the bytes that are not in the cache and the result of each claim. No automatic check runs it.

## Status and dependencies

| Status | What it records |
| --- | --- |
| `verified` (claim, source) | A review of the full text of the primary source, with each excerpt matched again |
| `partial` (claim, source) | The part that the review checked, and how it got the document |
| `unverified` (claim, source) | An attempt that did not open the document, and the work that is still necessary |
| `unreviewed` (assumption) | An assumption that no person confirmed. A result of a run does not change this status. |

The digest of the content of a claim binds that content to its verification record. Thus a claim
that changes without a new review fails the checks.

The evidence of a model is each claim, assumption and convention that its `record` declarations name,
also in its notes. It also includes the claims that support each assumption (`supports`), the related
claims (`related`), recursively, and the sources of all these claims. The dossier, the checks and the
tools use this one set (`napkin.model.evidence.dependencies`).

The numbers of a model have different bases. A basis is a reported value, a transfer from another
setting, an identity, a convention of the project or an assumption. A transfer states the source population, the
endpoint and the exposure. The support of a mechanism and the choice of a coefficient are separate
claims. The research note of each owner tells how the model applies each value, its bounds, and the
measurements that it still needs.

## Relations in the library

The library links its records: a claim to the claims related to it (`related`), and an assumption to
the claims that support it (`supports`). Each link has a relation. A note on the link can say how the
claim applies. A model does not repeat these links. Its `record` declaration names the claims, and its
explanation says how they support the part.

| Relation | The claim |
| --- | --- |
| `mechanism_support` | Shows that the mechanism works as the record says |
| `mechanism_precedent` | Reports an earlier event in which the mechanism occurred |
| `specifies_component` | Describes a part that the record uses: a device, a step or a time |
| `reports_value` | Reports a figure that the record uses |
| `calibrates` | Gives the reference from which the record sets its value |
| `defines_conditions` | Sets the conditions in which the record applies |
| `accounting_rule` | Gives a rule to count a quantity or a cost |
| `consistent_with` | Agrees with the record, but does not establish it |
| `bounds` | Gives a limit of the value. It does not support the value. |
| `context_limitations` | Limits the setting in which the record applies |
| `contradicts` | Argues against the record |
| `adopts` | Gives a definition or a convention that the project adopts |

## Write and copy evidence

`tools.evidence.integrate` is the only tool that writes the sources and the claims from evidence
packs. Do these steps to add evidence to one owner:

1. Get the raw bytes of the document: `python -m tools.evidence.fetch URL --out retrieval.json`. The
   tool keeps the bytes in the cache and writes their retrieval record.
2. Extract the text of the cached bytes: `python -m tools.evidence.fetch --extract PATH`.
3. Write a pack for the owner. The schema of a pack is `tools/evidence/evidence-pack.schema.json`.
4. Run `python -m tools.evidence.integrate --scenario OWNER`. This is a dry run. It reports each
   problem and writes nothing.
5. Correct the pack until the dry run reports no problem.
6. Run `python -m tools.evidence.integrate --scenario OWNER --write`.
7. Write the dossier again: `python -m tools.publish --write --scenario OWNER --only dossier`.

```sh
python -m tools.evidence.fetch URL --out retrieval.json
python -m tools.evidence.fetch --extract .evidence-cache/sha256/ab/SHA256.pdf
python -m tools.evidence.integrate --help
python -m tools.evidence.integrate --coverage
python -m tools.evidence.adopt --from SOURCE_OWNER --to TARGET_OWNER --id RECORD_ID
python -m tools.evidence.adopt --from SOURCE_OWNER --to TARGET_OWNER --id RECORD_ID --write
python -m tools.evidence.trail scenarios/iv_fluid_shortage/model.scn high_risk_patients.deaths --run subpar
python -m tools.publish --write --only dossier --only manifest
```

- A pack names the folder that it writes (`"scenario"`). `"scenario": "water_controls_wipe:lumberton"`
  writes the records of that variant only, in `scenarios/water_controls_wipe/variants/lumberton/`.
  `"scenario": "water_controls_wipe"` writes the records of the folder of the package, which the
  package and all its variants read.
- A batch writes one folder. It cannot change a record of another folder.
- A model can cite a record before a pack adds it. `integrate` checks each citation of the models that
  read the folder against the library that the packs make. It refuses, also in a dry run, while a
  citation has no record.
- A model or a variant must use each record of the folder of a package. The dry run reports a record
  that no model reaches. `--prune` removes such records, with the sources that only they reach.
- `adopt` shows a record and its dependencies by default. `--write` copies them through the same
  checks as `integrate`. It refuses a destination record with another meaning. A copy is
  independent: a later change in one folder does not change the other.
- `integrate --coverage` prints what each entity and template rests on, and the claims that no model
  reaches.
- `trail MODEL PATH…` runs the model and prints the evidence of each value. It gives the `record`
  declarations that the run exercised and the claims with their status. It also names each claim and
  assumption that no person confirmed.
- Each mode of a command refuses the options of its other modes.
- `--only manifest` makes the source manifest of the whole catalogue. A selection with `--scenario`
  cannot make it.

## Review a model

Review each step of the causal chain of the model:

1. the access;
2. the action;
3. the loss of service;
4. the people exposed;
5. the protection;
6. the conversion to clinical or economic harm;
7. the recovery;
8. the final accounts.

Write the identity of the reviewer, the context, the methods and the
conclusion. Put them in the notes of the model, or in the assumption that the review assesses.

## Evidence beside the declarations

- Write a `record` declaration that several parts use at the top level of the model, and cite it by
  its name (`@name`). A `record` declaration is not part of an entity or a template.
- Write a support that one part uses on its own row under that part:

  ```scn
      input interval = 4 h in [0.25 h, 24 h]
          @assumption "Attempts recur every four hours in the standard exercise."
  ```

- The two forms have the same fields. Each part cites its own support.
- The digest of a `record` declaration covers its authored content only. Its name and its place in
  the file are not part of the digest. Thus a move of a `record` declaration does not change its
  content.
