# S7-F: the loadable program, its side table, no player machinery — state
Brief: `scratch/rewrite/briefs/s7.md` (S7-F), `PLAN.md` "Changes after G0" items 15-16, `COMMON-B.md`.

## Done
- M1: `program/canonical.py` `decode`; `program/artifact.py` (format, loader, side table, digest,
  `LANGUAGE_VERSION`); `model/lowering.py` `side_table`; `Compiled.table`, `.artifact()`. Tests:
  tests/program/test_artifact.py, tests/model/test_compiled_artifact.py (fresh process).
- M2: oracle breakpoints and edits (tests/reference run.py, model.py, from_program.py,
  test_breakpoints.py); examples.py `pump_dispatch`, `PAUSES`, `Stop`, `pump_dispatch_unattended`;
  the language refuses `choose(...)` (`choose`) and `sees` (`sees`) with the hint
  (semantic.py `CHOOSE`, `SEES`). tests/draw, tests/acceptance and napkin/draw rewritten to match.
- M3 of the contract (coordinator, after S7-E's bc46b19): gone `refs.Choice`, `Template.sees`,
  config `Controller`/`Pick`/`controllers`/`picks`/`FORECAST`/`PLAYER` (with the two RECORDS lines
  of checkpoint.py, approved), `build.choose`/`sees`, `views.actors`, the four `dispatcher_*`;
  the oracle's choices; `FORMAT_VERSION = 2`. Oracle tests of a person's choice deleted or turned
  into breakpoints (test_branches.py, test_rulings.py test_14).

## Decisions
- D1 File: `napkin program 2`, `language 0.1.0`, `program <size> <sha256>`+bytes, `table <size>`+
  bytes, canonical encoding. Version rule: FORMAT_VERSION up with any change of the layout or of a
  field of a contract record; LANGUAGE_VERSION with what a program computes. Refusals:
  `not_a_program`, `format_version`, `language_version`, `damaged`.
- D2 Side table: every part with an origin; column of the line's first word; cites with content.
- D3 Oracle edits: stored values of members and occurrence locals; before a stage commit at once.
- D4 Evidence rule (`model/support.py`): see its docstring; per status case; a yes/no and a status
  rest on their thing's records; a column's warning at line 1 of its table file.

## For S7-E
- `load(path).program/.table/.digest`; `origins(program)[origin]`; `table.location(origin)`.
- `LEFT` in tests/engine/test_programs.py is dead now (no example reads `choose`): yours to drop.
- `record.KINDS` still lists `choice` (yours). `report._Trail.cites` should call the front end's
  `DeclaredModel.evidence(origin, member, options)` once it exists (item 3, in progress).
- An edit can make an event that `reach` proves cannot start start: a report that uses reach
  should withdraw that, as for never-falls.

## For M-prep (tools/check.py)
- The evidence warning: a `Problem` with code `no_record` (`napkin.model.support.CODE`) in
  `Compiled.reports`, beside the setup's other reports (`equal_keys`, `below_first_key`); tell it
  apart by `problem.code == 'no_record'`. Each has its file and line (a column: its table file, 1).
  A number, a yes/no or a distribution that an option or a `change` sets without a record stays a
  `LanguageError` with code `record`.

## In progress
- Item 2: wire `support.unsupported` into `compile._compiled` reports; tests.
- Item 3 (c-evidence gaps): `library.model_document` reads all a package's files; `proofs.reads`
  follows a stage that assigns a flow's request or capacity; `DeclaredModel.evidence(origin, member,
  options)` for the trail; provenance diagnostics with a line and no list indexes
  (`language/evidence.py` paths). The datum check is left for later.
- Others' live code hit: napkin/commands/play.py imports `views.actors` (C-K).
