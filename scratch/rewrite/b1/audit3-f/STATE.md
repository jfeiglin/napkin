# Audit 3, agent F: the front end — state

Brief: `briefs/audit3.md` part F, `COMMON-B.md`; rows 12, 14, 15, 17; PLAN 23; round 2: the main
session's six items (after the restart).

## Round 1 (done, in 66797b7/f89831e): mechanism, rule test (failures before)
- 12: core `within`, `ops.REVERSED`, `expr.membership`; semantic lowers `x in [lo, hi]` to it; a
  constraint keeps two relations; solvers, sparse, oracle `_within` (test_membership: 17/20).
- 14: own_place by the resolved target's owner; check `lifetime` (test_events: 15 spellings).
- 15: Resolver.resolved on a stack, Order walks on `walked`, lowering._columns a loop (deep chains 8/10).
- 17: Number/Quantity.exact, semantic `folded`, cited_data warns on an unfixed value (evidence rule 3).
- PLAN 23: parse refuses `role` under entity/template/member (S's wording); nodes, format, semantic.

## Round 2
1. Checked: rule tests pass; repro 12 (read Unavailable by name; the run never reads `ok`), 14b
   `lifetime`, 15, 17 (four warn). test_evidence_rule failed only on SERVICE's role line (fixed).
2. Role lines dropped: evidence/support.py:41 (no test draws SERVICE), commands/test_draw.py:30,42
   (no assertion reads a role), acceptance/F5.scn (6, old language), test_every_construct.py:58,
   build.py:781. No other model text in tests/ has one.
3. core/arrays: handlers are generators on an explicit stack (`_Pass.value`, `ready`, `_numbers`);
   expr.names/outside with a list; core/faces on an explicit stack. Tests (failed before):
   test_arrays `..._any_height_...` (RecursionError), test_faces `..._five_thousand_formulas_...`
   (None: RecursionError swallowed), test_deep_chains `..._as_deep_as_the_language_admits_...`
   (6 formulas x 140 choices, family way: RecursionError at Python's default 1,000). Arrays on
   small nodes: same time within noise. E's FAMILY/LINES case recursed in family.Columns: R's.
4. `tanks = big`: semantic accepts a read of a named collection (declaration, member's own value);
   build._initial keeps a collection's path init. Engine, oracle, check, proofs, solvers, draw
   follow it. Tests (refused before): test_collections `..._names_another_...` (engine + oracle;
   report lag/trail vs in place, store, edit + fresh process), cycle (held), deep chains `aliases`
   (5,000 at limit 400) and its run.
5. Not done (blocked): `x in [lo, hi]` needs a node (In); typeset.py raises on an unknown node
   (`napkin draw` would fail), and tests/draw's every-node test, reader and evaluators must know it.
6. parts.Template.part, Program.root_value by an index (cached; fields alone serialize): deep
   chains `..._found_by_their_names_...` ratio 63 before (8,000 vs 1,000), now about 8.
Final: core+language+model+program+reference 2487 passed.

## Decisions
- A membership in a solver's constraint stays two relations; reversed known ends: infeasible.
- Folding follows no read of another value and no reduction: such a cited value warns.
- A named collection may name any collection that a value holds (top level, member through links,
  event local); no parameter holds one, so no other read gives a collection.
- faces keeps None on a failure it cannot prove past (conservative: the engine's general route).

## For the main session
- Item 5: notation `In(x, low, high)` in `_CLASSES`, precedence 4, LaTeX `x \in \left[low,
  high\right]`, `_apply` call `within` -> In; typeset `write` (relation, bracket delimiter like
  `parens`); latex_subset reads it; test_notation's EVERY_CONSTRUCT and evaluators gain it.
- napkin/commands/compile.py `summary`: KeyError on any link or collection value (GROUPS has four
  kinds), since 8b3a01a: `napkin compile` fails on such a model.
- tests/build.py:226,340,351 write role lines (`role=` defaults); dormant (tests/publish only).
- tools/check.py docstring: a `datum` warning is also "computed when the model runs" / "no number".
- declared.py refuses a hand-built constraint's `within`; the oracle reads it as two relations after
  checking known ends (R asked). core/intervals walks formulas by calls: no live caller.
- E: test_named_collections docstring "(A bare `tanks = big` is no collection value)" is stale.
## For the owner
- Reversed ends known only at a solve: the membership's failure or an infeasible constraint (now)?
