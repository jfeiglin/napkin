# S1-F: the front end, second slice — state (done)

Brief: `scratch/rewrite/briefs/s1.md` (with `COMMON-B.md`, `s0-front.md`).

## Done

- `napkin/model/language/tables.py` (new): the form of a CSV table (header `name`, `name: unit`,
  `@record`; rows with their lines; RFC 4180), readers `in_folder`, `in_memory`, `no_tables`.
- `semantic.py`: types `Ent`, `Many(of, key)`, `FlowOf`; `Read(start, steps, type, fixed, formula)`
  with starts this/named/root/time/item/instances/literal/where/by/lookup; `Reduced`. Declared
  `DeclaredTemplate`, `DeclaredMember` (+`Given`), `DeclaredTable`, `DeclaredAssert`; `Order`
  (starting values across members, cycles → `cycle`). `declare(tree, units, tables_reader)`.
- `lowering.py`: templates, links, collections, members (`Builder.member`, `Builder.table`), asserts.
- `compile.py`: `compile_text(..., tables=)` (mapping or reader); `load_scenario` reads the folder.
- `parse.py`: copies `name: T * 3` → `retired`.
- Tests: test_tables.py, test_collections.py, sources in test_lowering.py (keyed_lookup; water
  model minus its event; reordered ids), copies in test_parse.py. tests/language 294 passed;
  language+program+commands+core+locator+strict_yaml 1256 passed (-n 2).
- Scale: 30,000 places + 35,000 routes: declare 2.1 s; whole compile 47 s, of which 45 s is
  `program/check.py` `unique` (quadratic `list.count`); 5.5 s with a linear one.

## Decisions

- D1 water_service_returns has an event (S4, still refused): its source without `restore` equals
  the example's program minus the event and the unit `h` that only the event spells.
- D2 Member values keep column (or property) order; rows with ids are sorted by the builder.
- D3 A table name alone names nothing (`sites.clinic` names a row; `Place.instances` the members).
- D4 In a `where` test a bare field of the member is the member's; it must be an input or a link.
- D5 An assert lowers when it reads only inputs/links, also through formulas (each looked at once);
  over state, or through a formula that an instance replaces → S4.
- D6 A template's flow ends at `this.<store>`, SOURCE or SINK; through a link or a named entity → S2.
- D7 A property by its path (`tank.x = 3`) is re-deferred to S6 (a `change` of the setup).
- D8 Flow units stay the builder's (a literal's unit, else the store's per hour).
- D9 A starting value, a member's value or a cell outside its range → `range`.
- D10 Collection values are literal/instances/where/by; a projection only feeds a reduction.

## For the main session (napkin/program, tests/program)

- `check._Checker.unique`: use a Counter (quadratic now).
- `examples.network_program`: flows `unit=power` ('W') vs a source's `Wh/h`; READINGS factor
  `F(1, 2)` vs a CSV cell `0.5` (a float, as a model text writes it): the bytes differ.
- `Builder.member(template, id, **values)`: a value named `id` or `template` cannot be passed.
- Old tests to delete: tests/model/test_tables.py, test_template_lists.py, the copies tests of
  test_copies_and_start.py, the two assert tests of test_shared_formulas.py.

## Not done

- `.at` coverage at a known lower bound, and the flag for equal keys in a keyed view (spec).
- lookup_below_first_key (its lookup is in an event stage, S4); `title` under an instance.
