# Audit 3, agent F: the front end — state

Brief: `briefs/audit3.md` part F, `COMMON-B.md`; rows 12, 14, 15 (front end), 17; PLAN item 23 last.

## Where each cause acts (whole repository, listed before any change)
12 (a membership lowered as `lo <= x <= hi`, which no evaluator checks): semantic.expression,
  lowering._node, model/solvers.compare; core ops, expr.FUNCTIONS, evaluation (function, program,
  folded, lean), arrays, units, intervals, derivatives, faces, tests/core/reference; oracle
  from_program + evaluate._in; E: triggers._truth_of/_atoms_of, moment.near_ties, integrate; mine:
  sparse._conditioned, fields (compiled -> interpreted: holds); main: declared.value, draw notation.
14 (lifetime from the spelling, `own_place` = "starts at a bare name"): semantic.own_place/lifetime
  (formula, rate_setting): a parameter naming an entity was the occurrence's own; program/check had
  no rule. E: writes to a finished occurrence.
15 (recursion per link): semantic.value -> declaration -> initializer -> expression -> path ->
  name/step -> value; over_inputs; Order.walk/starts/needs/known/chosen; binding (state set before
  resolving); model/solvers.formula; lowering._columns (tree depth); quadratic: Resolver.chosen
  (select), Order walks of collection values, build._flow_units (a Resolver per template).
17: exact_value (no if, compare, and/or/not, sqrt, clip, within); support.cited_data (returned on an
  unfixed value; formulas, distributions, locals, unknowns skipped); parse:538 / nodes.Number (float,
  `written` uncompared); message numbers (12 digits).

## Rule tests (written first; failure before the fix)
- 12 tests/language/test_membership.py: 17 of 20 failed (runs finish, reads False); later cases
  (moving value in a trigger/gate, continuous rate, store cold/warm/cut, table row, occurrence)
  pass. tests/core test_evaluation, test_arrays: failed ("Unsupported function").
- 14 test_events `..._owner_of_the_target_...` (13 spellings x 8 reads): the 15 through a parameter
  failed; `..._through_a_parameter_...`, `..._built_by_hand_...` failed.
- 15 tests/model/test_deep_chains.py: 8 of 10 failed (RecursionError), keyed 9.6 s; `solved` and
  the wide sum probed before their fixes (RecursionError in solvers.py, lowering._columns).
- 17 test_evidence_rule `..._compilers_folding_...` (hypothesis), `..._cannot_fix_...`,
  `..._exact_decimal_...` failed; `..._every_kind_...` added after.

## Done (one mechanism each)
- 12: core `within(x, lo, hi)`, `ops.REVERSED`, `expr.membership`; semantic lowers a two-ended
  membership to it; in a constraint it is its two relations (lowering._relations, build.in_range);
  build.within; solvers.chain; sparse; oracle `_within`. E reads `expr.membership` in triggers.
- 14: own_place by the owner of the resolved target; program check `lifetime` (refers, own_names).
- 15: Resolver.resolved (explicit stack, `_Unresolved` with its readers, `INLINE` 4 deep inside);
  binding retry-safe; Order walks as generators on `walked`, memo `collected`; over_inputs on
  `walked`; solvers.settle; lowering._columns a loop; fixed key over instances by its floor; one
  Resolver in build.program.
- 17: nodes.Number/Quantity.exact (compared); semantic.decimal, Const.exact, `folded` (every op);
  cited_data: every value kind, unfixed and no-number warnings; exact `_number`.
- Changed expectation: tests/model/test_units.py `written` wrote 0.02 day as 28.7999...9 min (a
  Decimal quotient by a rounded 1/60): now the exact 28.8 min, as its docstring says.

## Decisions
- A membership in a solver's constraint stays two relations (spec: constraints are ==, <=, >=
  relations and bounds on sums); reversed known ends make it infeasible there ("For the owner").
- Folding follows no read of another value and no reduction: such a value citing a datum warns.
- A formula local of an occurrence that the run records is evaluated at its entry: its membership
  fails there (the run evaluates it), as the rule says.

## For E / the main session / the owner
- E (seen): `2 L/h if lo <= water <= hi else 1 L/h` on the component path fails "rates switch back
  and forth" where water rises through lo (none does); the `within` form runs right.
- Main: draw/notation._apply shows `within(x, lo, hi)` as a call: show `x in [lo, hi]` (S's files);
  tools/check.py docstring: a `datum` warning is also "computed when the model runs" / "no number".
- Main, if one mechanism in constraints is wanted: declared.value reads a `within` with unknowns as
  `expr.membership(node)[0]` after checking known ends (ops.REVERSED).
- Owner: reversed ends known only at a solve: the membership's failure or an infeasible constraint
  (now)? `tanks = big` (an alias of a collection value) is refused by the language (E's note).

## Last item (PLAN item 23), only once audit3-s/STATE.md has "For F"
- Parser refuses `role` under an entity and a template (voice of `ROLES`); drop the entity's role
  (semantic.entity); move `role` lines of tests/model/modeltest.py, tests/language/test_parse.py.
