# Audit 3, agent F: the front end — state

Brief: `briefs/audit3.md` part F, `COMMON-B.md`; rows 12, 14, 15 (front end), 17. Owns napkin/core/,
napkin/model/, program/{parts,refs,build,check,canonical}.py, fields.py and sparse.py (row 12 only),
tests/core, tests/language, tests/model, tests/reference (row 12 only).

## Where each cause acts (whole repository, listed before any change)
12 (a membership is lowered as the chain `lo <= x <= hi`, which no evaluator checks):
- front end: semantic.expression (`n.Within`), lowering._node; model/solvers.compare (a chain).
- core: ops (no operation), expr.FUNCTIONS, evaluation.TABLE (function, program, folded, lean),
  arrays.TABLE, units.TABLE, intervals.TABLE, derivatives (partials), faces; tests/core/reference.py.
- oracle: from_program.node (Compare le,le -> E('in')), evaluate._in (no check).
- engine, E: triggers._truth_of, _atoms_of (bands, crossings), moment.near_ties.decided,
  continuous/integrate switch points; mine: sparse._conditioned, fields (compiled -> interpreted).
- main: engine/timeline/declared.value (a solver's rows); draw/notation._apply (shows a call).
14 (a place's lifetime from its spelling: `own_place` = "starts at a bare name"):
- semantic.own_place/lifetime (assignment of a formula, rate_setting of a flow or endpoint):
  a parameter of an entity (`target.rate`) counts as the occurrence's own place. program/check.py
  has no lifetime rule for a hand-built program. E: moment.py writes to a finished occurrence.
15 (recursion per link): semantic.value -> declaration -> initializer -> expression -> path ->
  name/step -> value (top level, entity, link, local, stored initializer); over_inputs (an
  assertion over a chain); Order.walk/known (a chain of collection values). Iterative already:
  Order.cycles, lowering, check, solvers, identity, side_table. Slow: semantic.select (linear per
  lookup: a keyed chain of 5,000 is quadratic, 30 s).
17 (a datum compared only for plain arithmetic, and a token read through a float):
- semantic.exact_value/_EXACT (no if, compare, and/or/not, sqrt, clip, within); support.cited_data
  (returns on an unfixed value: silent; formulas, distributions skipped); parse.primary:538 and
  quantity (float(written)); semantic.literal/Const (float); tables' cells (_cell_number).

## Rule tests (written first; failure before the fix)
- 12: tests/language/test_membership.py (stage, guard, trigger, gate, assertion, rate on lines and
  between moments, formula read and report, edit at a stop in place and fresh, the oracle, fixed
  ends): 17 of 20 fail (runs finish, reads give False). tests/core: test_evaluation (function,
  program folded/lean, walk), test_arrays: fail ("Unsupported function").
- 14: test_events `test_a_place_lives_as_long_as_the_owner_...` (13 spellings x 8 reads): the 15
  through a parameter fail (compile); `..._through_a_parameter_...` fails.
- 15: tests/model/test_deep_chains.py (top, entity, linked, local, stored, asserted, keyed,
  collections, table; a closed ring): 8 of 10 fail (RecursionError); keyed passes in 9.6 s.
- 17: test_evidence_rule `..._compilers_folding_...` (hypothesis over every operation),
  `..._cannot_fix_...`, `..._exact_decimal_...`: all fail (no warning).

## Last item (coordinator, PLAN item 23), only once audit3-s/STATE.md has "For F"
- Parser refuses `role` under an entity and a template (voice of `ROLES`: the wrapper's, pictures
  from style.toml [role]); drop the entity's role (semantic.entity); move `role` lines out of
  tests/model/modeltest.py, tests/language/test_parse.py:218 and others. Not before S's list.

## Done
- (pending)

## Decisions
- (pending)

## For E
- (pending)
## For R
## For the main session
## For the owner
