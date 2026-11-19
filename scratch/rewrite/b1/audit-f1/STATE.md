# Audit F1: the owner's language decisions after the audit, and two validation bugs — state (done)

Brief: the coordinator's (2026-11-19) with `COMMON-B.md`; PLAN "Changes after G0" 16, 19.
Owns: napkin/model/, tests/language/, tests/model/, napkin/program/artifact.py (+ tests/program/
test_artifact.py), napkin/session.py, napkin/commands/play.py, tests/test_session.py, tests/commands/test_play.py.

## Done (each a failing test first)
- 1 empty case: parse.py `switch` (a case's text alone, or nothing); tests/language/test_events.py
  (the reservoir's WAIT: compiles, card in the side table, runs; format round trip).
- 2 titles: parse.py `is_title`, `title_line` (member by hand; one title); nodes.Declaration.title;
  format.py; semantic `DeclaredMember.title`, a change keeps it, `DeclaredModel.title(member)`;
  artifact `Location.title`, `SideTable.title`, `MEMBER` locations (members by hand),
  FORMAT_VERSION 3; lowering.side_table; session `Session.title`, `View.title`, `Shown.title`;
  play.py `titled` (stop line, rows, edit lines). Tests: test_parse, test_packages,
  test_compiled_artifact (no hash moves), test_artifact, test_session, test_play.
- 3 roles: parse.py `ROLES`, `is_role`: under an event, a case, a member by hand, in a change:
  code `role`, "... belongs to the scenario's wrapper (its UI or brief.toml), not to the model".
  `Change.role` gone. An entity's or a template's own role stays (napkin draw's icons).
- 4 timescales: parse.py `TIMESCALES` (`retired`); gone from nodes/semantic/format/compile.
- 5 cycles: `Resolver.provisional`; `Order.decided`/`linked`; chain messages; one per shape.
- 6 ranges: `Resolver.reversed` (range, unknown's domain, parameter's range).
- 7 distributions: `_broken`, `_mass`, `PARAMETERS` (code `distribution`).

## Decisions
- A role stands only under an entity or a template; a change sets none (refused, not kept).
- Titles: on a member by hand and an entity/template; a table row has none; not inherited.
- A template value read through its own members with no declared type: `cycle`, "declare its type".
- Order decides a where that compares links (==, !=, and, or, not); others keep every member.
- One cycle problem per shape (set of template values), so a table of self-reads is one problem.
- Distribution rules = the old checker's, plus the unbounded normal/lognormal; uniform(a, a) refused;
  a bounded lognormal may start at 0; a bounded normal/lognormal keeps some probability.

## For E2
- report.py: show a member's title where the report names one (`Reported.path`, `Used.owner`,
  `NearTie.owner`): `model.title(member)` (`DeclaredModel.title`), the member of an occurrence
  being its receiver. commands/run.py's table (row names) could follow (`SideTable.title`).
- FYI: scratch/rewrite/a5/translated/now/examples/reservoir with its WAIT case restored compiles,
  and its run fails at 0 h: "the first contact of reservoir.water >= operator.level cannot be
  certified: it reads a value that moves on a curve".

## For others
- K1 (a5 translator): a member's `title` is a field now; an event's role stays a comment.
- napkin draw could show member titles (`DeclaredModel.title`); program/check.py could check the
  parameter rules of a hand-built program's distributions.
