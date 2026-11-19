# S7-F: the loadable program, its side table, no player machinery — state
Brief: `scratch/rewrite/briefs/s7.md` (S7-F), `PLAN.md` "Changes after G0" item 15, `COMMON-B.md`.

## M1 done: the loadable program and its side table

- `program/canonical.py`: `decode(data, records)` (inverse of `value_bytes`), `Malformed`.
- `program/artifact.py`: `FORMAT_VERSION = 1`, `LANGUAGE_VERSION` (moved from identity.py);
  `Evidence`, `Location`, `SideTable`, `KINDS`, `EXECUTABLE`, `origins`, `kind_of`; `Artifact`
  (`.digest`, `.data()`, `.save()`), `loads`, `load`, `value_of`, `RECORDS`, `ArtifactError`.
- `model/lowering.py` `side_table`; `compile.py` `Compiled.table`, `Compiled.artifact()`.
- Tests: tests/program/test_artifact.py (76), tests/model/test_compiled_artifact.py (4, a
  subprocess that never imports napkin.model).

## Decisions

- D1 File: `napkin program 1\n`, `language 0.1.0\n`, `program <size> <sha256>\n<bytes>`,
  `table <size>\n<bytes>`; both sections in the canonical encoding (one codec, no JSON).
- D2 Version rule: FORMAT_VERSION goes up with any change of the layout or of a field of a record
  of the contract; LANGUAGE_VERSION with what a program computes. Refusals: `not_a_program`,
  `format_version`, `language_version`, `damaged` (also a record whose fields are not this napkin's).
- D3 The side table covers every part with an origin (not only executable ones): kind, name, file,
  line, column (the line's first word, from 1), label (the declared part's text), evidence (a cite
  resolved to the record's content). Members and table cells are not in it.
- D4 No configuration in the artifact (`value_of` reads one's `value_bytes`). Engine records hold
  NumPy floats, which `value_bytes` refuses: the test compares them through `plain`.

## For S7-E

- Load: `from napkin.program.artifact import load, loads, value_of`; `load(path).program`,
  `.table`, `.digest` (name the program in a checkpoint by it).
- A location: `origins(program)[origin]` gives the part; `artifact.table.location(origin)` its kind,
  file, line, column; `table.executable()` the breakpointable ones; `kind_of(part)`.
- Acceptance example (examples.py): `pump_dispatch(spares)`, `pump_dispatch_unattended`, `PAUSES`
  {untouched, sends, no_spare, two_stops}: (spares, stops, expected); `Stop(at, occurrence, edits)`,
  edits `(Key, value in declared unit)`; `DISPATCH_SWITCH`, `DISPATCH` (`depot.request_pump#0`).
- Oracle: `run_of(program, configuration, stops)`, stops `(origin, occurrence|None, edits)`; or
  `Run.breakpoints`, `run()`, `paused` {why, at, time, member, occurrence, next, inside}, `edit(owner,
  name, value)`, `resume()`, `edit_log`, trace kind `edit` (origin = the breakpoint). Breakpoint origins: a statement (stops before it, inside its stage), a stage (before
  its guard; an edit there commits at once), an event (its first stage). Edits: stored values of
  members and occurrence locals (not params, built-ins, inputs, formulas, links); type and range
  kept; a finished occurrence refused; a store's edit is a ledger `('edit', t, cell, delta)`.
- The removals of "M2 to do" land only once the engine stops importing them (say so in your state
  file); then `SUBSET` in test_programs.py names `pump_dispatch_unattended` for the `dispatcher_*`.

## M2 done so far

- Oracle (tests/reference model.py, run.py, from_program.py): stops, edits, resume;
  tests/reference/test_breakpoints.py (10). examples.py: `pump_dispatch`, `PAUSES`, `Stop`,
  `pump_dispatch_unattended` (its text in tests/language/test_events.py `SOURCES`).
- Language: `choose(...)` (code `choose`) and `sees` (code `sees`) refused by name with the hint
  (semantic.py `CHOOSE`, `SEES`); `Chosen`, `DeclaredSees` and their lowering removed. At the
  coordinator's request: tests/draw, tests/acceptance rewritten; napkin/draw lost the choice words
  and the actor badge (card key `actor`, legend "Decides"). examples/reservoir is old language.

## M2 to do (waits for S7-E's M3)

- Program: remove `refs.Choice`, `Template.sees`, `build.choose`/`sees`, config `Controller`,
  `Pick`, `controllers`, `picks`, `FORECAST`/`PLAYER`, check.py/proofs.py uses, `views.actors`;
  the four `dispatcher_*` examples; the oracle's choices (run.py `choose`, `answers`, Config
  `controllers`/`choices`); bump `FORMAT_VERSION` to 2 (records change).
