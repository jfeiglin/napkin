# S7-F: the loadable program, its side table, no player machinery — state

Brief: `scratch/rewrite/briefs/s7.md` (S7-F), `PLAN.md` "Changes after G0" item 15, `COMMON-B.md`.

## M1 done: the loadable program and its side table

- `napkin/program/canonical.py`: `decode(data, records)` reads `value_bytes` back (same nodes of
  core.expr, a record's fields checked by name and order); `Malformed`.
- `napkin/program/artifact.py`: `FORMAT_VERSION = 1`, `LANGUAGE_VERSION = '0.1.0'` (moved from
  identity.py, which imports it); `Evidence`, `Location`, `SideTable`; `KINDS`, `EXECUTABLE`,
  `origins(program)`, `kind_of`; `Artifact(program, table)` with `.digest`, `.data()`, `.save()`;
  `loads`, `load`, `value_of` (any contract value), `RECORDS`; `ArtifactError(code, message)`.
- `napkin/model/lowering.py`: `side_table(model, program, file)`; `compile.py`: `Compiled.table`,
  `Compiled.artifact()`.
- Tests: tests/program/test_artifact.py (76), tests/model/test_compiled_artifact.py (4, the fresh
  process in a subprocess that never imports napkin.model).

## Decisions

- D1 File: `napkin program 1\n`, `language 0.1.0\n`, `program <size> <sha256>\n<bytes>`,
  `table <size>\n<bytes>`; both sections in the canonical encoding (one codec, no JSON).
- D2 Version rule: FORMAT_VERSION goes up with any change of the layout or of a field of a record
  of the contract; LANGUAGE_VERSION with what a program computes. Refusals: `not_a_program`,
  `format_version`, `language_version`, `damaged` (also a record whose fields are not this napkin's).
- D3 The side table covers every part with an origin (not only executable ones): kind, name, file,
  line, column (the line's first word, from 1), label (the declared part's text), evidence (a cite
  resolved to the record's content). Members and table cells are not in it.
- D4 The artifact holds no configuration: a checkpoint or a caller keeps its own (`value_of` reads
  a configuration's `value_bytes`). Engine records may hold NumPy floats, which `value_bytes`
  refuses: the test compares records through `plain` (bits kept).

## For S7-E

- Load: `from napkin.program.artifact import load, loads, value_of`; `load(path).program`,
  `.table`, `.digest` (name the program in a checkpoint by it).
- A location: `origins(program)[origin]` gives the part (Event, After, Until, Trigger, Assign, Move,
  Start, If, Switch, Case, ...); `artifact.table.location(origin)` its kind, file, line, column;
  `table.executable()` the breakpointable ones; `kind_of(part)`.
- An occurrence is named as in the record: `receiver.event#n`.
- Planned in M2 (not yet done): `Configuration.controllers`/`picks`, `Controller`, `Pick`,
  `FORECAST`/`PLAYER`, `refs.Choice`, `parts.Template.sees`, `build.choose`/`sees` leave the
  program. I remove them only after S7-E's engine stops importing them (tell me in your state file).

## M2 in progress / to do

- Language: refuse `choose(...)` and `sees` by name with the hint (store the value in a field and
  branch on it; a wrapper can pause before the branch). Oracle (tests/reference): drop choices and
  picks; add breakpoints and edits from item 15 (rerun the paused stage from its start, then apply
  the edits in order).
- examples.py: the four `dispatcher_*` become the acceptance example (forecast drawn into an
  occurrence field `order`, `switch` on it, eligibility as a case guard).
