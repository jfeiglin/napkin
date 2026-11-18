# S0-F: the front end, first slice — state (done)

Brief: `scratch/rewrite/briefs/s0-front.md` (with `COMMON-B.md`).

## Done (all in place, tests green)

- `napkin/model/language/`: `problems.py` (Problem: code, message, line, column, file; LanguageError),
  `lex.py`, `nodes.py`, `parse.py`, `format.py`, `evidence.py` (records for the evidence walkers),
  `modules.py` (role, package, `library` line, files of a model). Deleted: expressions, front,
  resolve, tables (S1 brings tables back; the old reader is in git history).
- `napkin/model/semantic.py`: the declared model (`declare(tree, units)`); typed IR Const/Read/Apply/
  Retain/Distribution/Drawn; parts have paths = program origins; later-slice parts are `Deferred`.
- `napkin/model/lowering.py`: `lower(declared)` → Builder → `finish()`; Deferred → `later_slice`;
  checker refusals mapped to the line of the part named by their origin.
- `napkin/model/compile.py`: `compile_text(text, units)`, `load_scenario(path)` → `Compiled(declared,
  program, configuration)`; `library_units`. `library.model_document` uses the new parser.
- `examples/piano_tuners/model.scn` and README migrated; loads, lowers, formatter fixed point.
- `tests/language/`: test_parse, test_format (corpus/ = 32 text blocks + 3 csv of spec.md),
  test_semantic, test_lowering (equal bytes: tank_delivery, unit_division, unit_product,
  two_junctions; inputs with draws vs builder programs; later-slice refusals; piano tuners).
- Runs: tests/language 197 passed; language+program+core+locator+strict_yaml 1094 passed (-n 2).

## Decisions

- D-1 Unit run is structural (`Quantity.unit`); the declared model splits it at the first name that
  is no unit of the library (D12: same arithmetic either way). `scale`, `none`, `is` reserved;
  `size`, `within`, `chance(`, `output`, `let`, `var`, `versus`, `share`, `report:` → code `retired`.
- D-2 Layout (comments, empty rows, range on its own row, a number's spelling) is kept, never compared.
- D-3 Formatter: `/` close and `*` spaced in units; a quantity on the right of `*` `/` bracketed, and on
  the left of a quantity or a bare name; long texts wrap at single spaces; expressions never wrap.
- D-4 Derived unit spelling: factors, equal names cancel (`tunings/year`); types flatten from the left
  (`tunings/(tuner * year)` → `tunings/tuner/year`, which the builder composes).
- D-5 An input whose default draws and has no range gets the support of a bounded family as range.
- D-6 A bare zero beside a unit is written `q(0, unit)`; a negated literal folds (`q(-3, 'L/h')`).
- D-7 Bare top-level value → `Path(ROOT, (name,))`; entity name → `Named`. Enums deferred to S4,
  status display to C, asserts and property-by-path lines to S1.
- D-8 Piano tuners: `capacity` = the request formula (old `at` was a fixed rate; D15); `done` unbounded.

## Changes wanted in napkin/program/

- `build._flow_units` spells a plain store's rate `'/h'` (no table composes it): should be `1/h`
  (lowering passes `unit='1/h'`).
- No public builders for n-ary and/or, comparison chains, `abs`/`exp`/...: lowering builds core nodes
  and wraps them with `build.X(node, reads)`; document that or add `chain`/`call`.
- Draw sites: lowering uses `Draw(dist, '?lowered<k>')`, relying on `finish` to place it.
- `refs.Distribution`: lognormal's gsd (params[1]) is plain though the tuple has one `unit`; say so.

## Not done / for the main session

- Old-path modules no longer import (old semantic/compile names): draw/*, model/{hybrid,lower,
  meaning,model,runs,views}, engine/{study,expectations,uncertainty}, session, spread, commands/common.
- No `napkin fmt` command wiring (CLI is not this track's); README lost its CLI lines.
