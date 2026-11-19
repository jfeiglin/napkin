# S4-F: the front end, fifth slice — state (done)

Brief: `scratch/rewrite/briefs/s4.md` (with `COMMON-B.md`, `s0-front.md`, `s1.md`, `s2.md`, `s3.md`).

## Done

- parse.py: a top-level start line is a setup statement (`setup_start`); the formatter writes it.
- semantic.py: types EnumOf/EventOf/Occ; Chosen/History/Drawn-of-a-value; Scope.event/captures/
  trigger; event params+locals in `syntax` under the event path (owner = event path, `scopes`);
  `event`, `local_order` (D14), `timing`, statements (assign/move/start/if/switch), `trigger`,
  `through_end` (write through .source/.sink = fixed_write), categorical, drawn, chosen, history,
  `.mean/.std`, sees, setup starts, assertions over state (`DeclaredAssert.fixed`), enum cells.
- lowering.py: `_enums` (sorted by spelling), `event_of`, `_statement`, triggers, setup, sees.
- views.py rewritten on `Compiled`: `actors` (sees, choice sites, outcomes, case cards), `instances`.
- napkin/program/reach.py (new, D16): `reach(program, configuration)`: events that can start,
  values of each enum/bool state, each with its reason; conservative fixed point. Docstring of
  napkin/program/__init__.py lists it. No other change to napkin/program/.
- tests/language/test_events.py (75): the 32 S4 examples give equal bytes; features; refusals.
  tests/language/test_chance_and_actors.py (24): ports. tests/program/test_reach.py (6).
- Old S4 refusal tests updated (test_lowering, test_collections, test_semantic).
- Runs: language+program+reference+core+locator+strict_yaml 1566 passed; tests/commands 66 passed,
  1 failed (below).

## Decisions

- E1 An enum is its members in written order; the program names it `enum[A, B]`. A categorical
  takes the enum of its place, else its outcomes' enum. examples.py: 3 enum names renamed.
- E2 Setup statements are top-level start lines.
- E3 examples.py `_inspect` takes literal times (4.5 h is a float, as grinder's 0.5 h); `_pinned`
  param `to` -> `customer` (`to` is reserved).
- E4 A distribution's parameters are numbers in place: value arguments refused (`distribution`).
- E5 Draws/choices in any once-evaluated place; refused in formulas, gates, triggers, resets,
  assertions (`formula_draws`).
- E6 `.at(t)` is the only keyed read of occurrences; `where`/`by` on them refused (`collection`).
- E7 A local holds no entity (`link`): an entity reaches an event as a parameter (D13).
- E8 `.source`/`.sink` of an occurrence's flow are read only inside its event.
- E9 Reach states are per template (union over members): conservative, cheap at 30,000 rows.
- Ports: test_distribution_contracts, test_named_arguments, test_sight, test_views,
  test_state_assignment -> new files above. test_initiation.py: DELETE (old incident start:
  premises, instant first move, admission; setup starts commit at round zero, covered by examples).

## For the main session

- tests/commands/test_compile.py::test_a_part_of_a_later_slice_is_refused_by_name uses
  `state = OPEN` as an S4 part; it is now `enum_member`. Use a solver (S5).
- Delete the ported old files (dormant): tests/model/test_distribution_contracts.py,
  test_named_arguments.py, test_sight.py, test_state_assignment.py, test_views.py,
  tests/engine/test_initiation.py.
- views.py's consumers (draw/, commands/play.py, test_cli, test_session) used the old API.
