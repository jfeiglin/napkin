# S6-F: the front end, packages and configurations — state (done)

Brief: `scratch/rewrite/briefs/s6.md` (S6-F), with `COMMON-B.md`, `s0-front.md`, `s1.md`..`s5.md`.

## Done

- parse/nodes/format: an option has its text (menu line) and evidence; a run line its text; a
  `change` its text, `title`, `role`. Round trip kept.
- language/modules.py: `files(path)`: role, package, files in read order, problems of `use` (no
  module, not a module, circle), of a module as entry, of a variant outside `variants/` or with no
  main file. language/evidence.py walks options, settings and runs.
- compile.py: `load_scenario(path, run=, edits=)` parses each file with its lines numbered after the
  file before (blank-line prefix), merges the trees (no `use`; the main's scenario line overlaid by
  the variant's, title `Main: Variant`, a variant's `library` refused), declares once with `files`,
  maps problems back to (file, line). `compile_text(..., run=, edits=)`. `Compiled.model_hash`,
  `.base`, `.configure(run, edits, options)`.
- semantic.py: `Files`; `DeclaredSetting/Option/Run`; `DeclaredModel.options/runs/files/place/option/
  run`; changes (`register_changes`, `change_line`, `changed` via `own`, hand members, labels);
  `recorded` (R-A5-05); `declared_options`, `setting`, `member_template`, `constant`,
  `declared_runs`; module `choice_problem`, `merged_notes`, `constant`. Refusals: `use` in a text
  alone (`use`), a variant alone (`scenario`), a value set by its path (`property`).
- runs.py (rewritten): `options_of`, `configuration`, `check` (one transaction: schema, model_hash,
  reference, input/bool/value/unit/range, meeting). identity.py (rewritten): `LANGUAGE_VERSION =
  '0.1.0'`, `model_hash`. schema/edits.schema.json rewritten. program/canonical.py: `value_bytes`.
- Tests: tests/language/test_packages.py (28, with the join), test_runs.py (66),
  tests/acceptance/test_every_construct.py (6, source to `napkin.engine.run`). Updated
  test_lowering.py and tests/commands/test_compile.py. Deleted the 12 ported files (see last message).
- Brief's command: 1871 passed (+ test_programs/acceptance/locator/strict_yaml: 218 passed).

## Decisions

- C1 A Configuration has no start values: only inputs are configured (R-A5-04, D2); a start value
  follows its initializer, and a `change` that sets one gives a program of its own.
- C2 A change of a template changes its declaration; a member's own line keeps its value.
- C3 A change names an entity, a template or a hand member of an earlier file; it sets declared
  values and links only, once each; its kind is kept (formula by formula, R-A5-07).
- C4 model_hash: program, options/runs (groups by place), default configuration and horizon,
  language version; no labels, notes, records/evidence, places, file or group names.
- C5 Option and edit values are constants (no calculation), in the input's unit, range-checked when
  the bounds are numbers; a JSON number is in the input's unit, a string has its unit.
- C6 A record is needed for a number, yes/no or distribution set by an option or change; not for a
  text, an enum member, a link, a formula.
- C7 A value set by its path has no form (`property`): the override is `change`.
- C8 Within a level, a member's line beats `Template.instances`; across options too (no conflict).
- C9 The default run (no name) takes no option; `set` edits reach it.

## Not done / for others

- ir.LANGUAGE_VERSION (old, unread) stays in ir.py, not mine.
- Instance values need no record yet (spec: "as an instance value does").
- Dormant S0 files with S6 parts: tests/model/test_build.py, test_diagnostic_places.py,
  test_library.py. Dormant importers of deleted fixtures: tests/test_package.py,
  tests/test_nested_packages.py, tests/evidence/test_adopt.py (stage C).
