# Audit F1: the owner's language decisions after the audit, and two validation bugs — state

Brief: the coordinator's (2026-11-19) with `COMMON-B.md`; PLAN "Changes after G0" 16, 19.
Owns: napkin/model/, tests/language/, tests/model/, napkin/program/artifact.py (+ tests/program/
test_artifact.py), napkin/session.py, napkin/commands/play.py, tests/test_session.py, tests/commands/test_play.py.

## Plan (each: a failing test first, then the fix)
1. Empty case: parse.py `switch` takes a case with no actions (text or not); side table label = card.
2. Titles: member written by hand `title "…"`; change keeps it; DeclaredMember.title,
   DeclaredModel.title(member); Location.title + member locations in side table (FORMAT_VERSION 3);
   session Shown.title; play lines name `member (Title)`.
3. Roles: `role` under an event, a case, a member by hand, or in a change: refused (`role`).
4. Timescales: refused (`retired`); gone from nodes/semantic/format/compile.
5. Cycles: resolver gives a provisional value (declared type) on a template-level recursion;
   Order reports the member chain `a.total reads b.total reads a.total`.
6. Ranges compared in one unit (finish, unknown domain).
7. Distribution parameters checked by family (`distribution`).

## Done
- 1 empty case: parse.py `switch` (tests/language/test_events.py, 3 tests, the reservoir run).
- 4 timescales: parse.py `TIMESCALES` (`retired`), gone from nodes/semantic/format/compile;
  tests/model/test_copies_and_start.py.
- 6 ranges: semantic `Resolver.reversed` (range, unknown domain, parameter); test_semantic.py.
- 7 distributions: semantic `_broken`, `_mass`, `PARAMETERS` (code `distribution`, message
  `uniform(5 h, 2 h): uniform(min, max) needs min below max`); test_chance_and_actors.py.
- 5 cycles: `Resolver.provisional` (declared type), chained messages; `Order.decided`/`linked`
  (a where over links is decided at compile time), one problem per cycle shape; test_collections.py.

## Decisions
- A value that reads itself through its template, with no declared type, is refused (`cycle`) with
  its chain and "declare its type": its type is not known before its value.
- Order evaluates a where's test that compares links (==, !=, and, or, not); any other test keeps
  every member (only a run knows). One cycle problem per shape (set of template values).
- Distribution rules: the old checker's (`napkin.distributions.problems`), with the unbounded
  normal/lognormal; a bounded lognormal may start at 0; uniform(2 h, 2 h) is refused.
- Parameter ranges of events are checked for reversal too.

## For E1 / E2
