# Audit 3, agent S: no roles in a model (PLAN change 23), draw and translator side — state
Owns napkin/draw/, napkin/commands/new.py, tools/new.py, tests/draw/, examples/piano_tuners/,
scratch/rewrite/a5/ (`napkin compile`'s stylesheet check is napkin/draw/style.py `check`). DONE.

## What read a role, and reads the stylesheet's `[role]` now
- draw/things.py `_cards` (`Card.role` from `entity.role`): `Card` has no role. style.py `icon_of`
  (`ROLE_ICONS`): by `roles_of(style, found)`. model_map.py `_Drawing.card` (the map's `role`):
  `roles_of`. layout.py `Card.role` reads the map's (unchanged). `ACTOR_NAMES`/`actor_name(role)`
  take a role word (unchanged). Others' readers: see "For the main session".
## Rule test (first; it failed): tests/draw/test_roles.py, expected tests/draw/roles.json
- roles.json from make_expected.py (this folder) on the code before the change: 13 picture models
  of tests/draw that wrote roles (works x4, cards, states, plans, wards x6), map JSON + SVG SHA-256.
- Before: 13 of 13 fail (`role: is not a key`); without `[role]`, every map differs. After: pass.
## Done
- style.py: `Style.roles`, `[role]` (`_read_roles`, shape of `[icon]`, `ROLE` a word), `check`
  (`_check_roles`), `roles_of`. tests/draw models without roles, stylesheets with them; new tests.
- new.py writes `style.toml` (`[role] operator = ["service"]`); tools/new.py names `[role]`;
  piano_tuners: role -> style.toml. Old code+files vs new (HEAD copy): same map and SVG for both.
- a5: translate.py `played`, `write_roles` (`[entities]` + `[events]`), `write_styles`/`with_roles`
  (each old style.toml of the package and variants, `[role]` after `[icon]`, tomllib self-check),
  `--compile` checks stylesheets (newmodel.py `style`); run_all.sh: no translated model has a role;
  wrong copies lost `role environment`; migration-table.md rows. Whole catalogue retranslated:
  6,939/6,960 as before, 59 entity roles moved, 0 role lines left; piano, reservoir sheets hold.
- Final: tests/draw 835 passed, 1 skipped (test_roles 14); tests/commands 144 passed, 2 failed
  (test_new's file lists, below); tests/test_tools_new.py 27 passed; run_all OK; ruff clean.
## Decisions
- A role is a stylesheet setting read with it (`roles_of`, like `icon_of`); `Things` reads the model.
- `[role]` names things and templates of the model, drawn or not (the `layout.hide` rule, not
  `[icon]`'s on-map one): who plays a part is no part of the picture, and a translated package's
  hidden things and memberless templates keep their roles. A member and a table may have their own;
  own name + template's under two roles is a problem; a name in two roles a read problem (`[icon]`).
- roles.toml: `[entities]` (name -> role) beside `[events]`, package-wide as M-prep's events.
## For F (refuse `role` under an entity and a template; lines as of 2026-11-19 23:30)
- parse.py:98 MEMBER: drop "role". :105-114: comment and voice, proposed:
  `WRAPPER = "belongs to the scenario's wrapper (roles.toml), not to the model"`, `PICTURES = 'the
  pictures take it from the [role] of style.toml, such as {role} = ["{name}"]'`; ROLES['entity'] =
  f'an entity has no role: who plays it {WRAPPER}, and {PICTURES}', ['template'] = 'a template has
  no role: who plays its members ...', ['member'] = 'a member has no role: who plays it ...' (the
  stylesheet takes a member's own); event, case, change keep their text with the new WRAPPER.
- parse.py:1083-1105 `entity`: `is_role(child)` raises `SyntaxProblem(ROLES['entity' if small(name)
  else 'template'].format(role=..., name=name), child.number, child.first.column, 'role')`; drop
  `role` from the locals and from `n.Entity(...)`. nodes.py:553-559 `Entity.role` and docstring;
  format.py:349-350 (role row); semantic.py:40-44 docstring, :979 `DeclaredEntity.role`, :4335 and
  :4347 (`entity`: `item.role`, the `role` argument).
- tests/language/test_parse.py:218 and :227 (`tank.role`); :246-264 add an entity and a template
  case and the new message; test_packages.py:434 holds. tests/model/test_build.py:94-104
  (`test_the_compiler_reads_no_role`: now a refusal); modeltest.py:39,44,80,89 (old language, read
  only by dormant tests/publish); test_pages.py:7-8 docstring.
## For the main session
- tests/commands/test_new.py:41 `[paths.ENTRY, 'style.toml']`, :84-87 add 'style.toml' (2 fail now).
- After F: tests/evidence/support.py:41 (SERVICE); tests/commands/test_draw.py:30,42;
  tests/acceptance/F5.scn:13,21,54,97,119,131; test_every_construct.py:58; tests/build.py:781 —
  drop each role or move it into a `[role]`. examples/reservoir/model.scn:39 -> its style.toml
  `[role] operator = ["operator"]` (keeps the operator's server icon).
- Stage M: tools/publish/pages.py:259-310,530 read roles.toml; tests/evidence/test_catalogue.py:
  134-143 reads `style.of(model).roles`; tests/publish/*; briefs/m.md, b1/m-prep: `[entities]`.
- Docs: draw.md:37,157,253,272,319-323 (`[role]`), language.md:63,78,99,221-228,519,527.
## For the owner
- `napkin new` writes a second file, style.toml, for the starter's role (keeps its picture); the
  alternative is one file and no role.
