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
- `record.KINDS` still lists `choice` (yours). `report._Trail.cites` should call
  `model.evidence(origin, part.owner, options)`, with the options of the run (report needs them).
- An edit can make an event that `reach` proves cannot start start: a report that uses reach
  should withdraw that, as for never-falls.

## For M-prep (tools/check.py)
- The evidence warning: a `Problem` with code `no_record` (`napkin.model.support.CODE`) in
  `Compiled.reports`, beside the setup's other reports (`equal_keys`, `below_first_key`); tell it
  apart by `problem.code == 'no_record'`. Each has its file and line (a column: its table file, 1).
  `napkin compile` prints each; `--json` gives them under `warnings`.
  A number, a yes/no or a distribution that an option or a `change` sets without a record stays a
  `LanguageError` with code `record`.

## Done after M3 (coordinator's items 2 and 3)
- Evidence rule: `model/support.py` (`unsupported`, code `no_record`) in `Compiled.reports`;
  `napkin compile` lists each, other commands print one line (`common.warn`); `--json` documents
  of compile, run and sample have `warnings`. tests/language/test_evidence_rule.py; the 11 tests of
  tests/commands given records; two tests of the rules in tests/commands/test_compile.py.
- Gaps: `library.model_document` reads every file of a package; `proofs.reads` follows a stage
  that sets a flow's request or capacity (`_Index.settings`); `DeclaredModel.evidence(origin,
  member, options)`; the walker names `status.case[k]`, `assert[k]`; `language.evidence.lines`;
  `compile.placed_diagnostic` puts a library error at its file and line. Datum check: later.
- Others' live code hit: napkin/commands/play.py imports `views.actors` (gone).
