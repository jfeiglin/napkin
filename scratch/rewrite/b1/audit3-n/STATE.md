# Audit 3, agent N: a membership test in the picture — state

Brief: the main session's task (F's item 5, `audit3-f/STATE.md`), `COMMON-B.md`. Owns `napkin/draw/`,
`tests/draw/`; edits nothing else. Not committed. Done.

## Done
- `notation.In(x, low, high)` in `_CLASSES` (so `NODES`, `as_dict`/`from_dict`); `_apply` turns the
  program's call `within` into it; precedence 4 (a comparison); LaTeX `x \in \left[lo, hi\right]`
  (x an operand of a comparison, the ends as a function's arguments). Module docstring lists it.
- `typeset`: `∈` a relation (width `OPERATOR`: 0.88 em with the margin; DejaVu Sans 0.871 em,
  measured here from the font file), `brackets` like `parens` (runs `[` `]` anchored against the
  ends; paths of kind `bracket` around a tall end, `_bracket`). The SVG writes them as it writes any
  atom and rule.
- `triggers`: `within` reads "x is in [lo, hi]" (it read "within(x, lo, hi)" on the cards).
- Generic walkers need nothing (fields): `nodes`/`children`, equations `_rename`/`_key_of`/`_names`,
  panels `_clocks`/`tree_keys`, layout `_clocked`; the tests' `canonical`, `shape`, `mapped`.
- Tests: `latex_subset` reads `\in \left[…\right]` at the level of a comparison; test_notation
  (`node_of` reads `a in [b, c]` as `within`; evaluators `within`/`In`, failing by `REVERSED`;
  EVERY_CONSTRUCT `lab.inside`; random nodes and typed texts; parentheses), test_typeset (level,
  Reader, look, parentheses, ADVANCES `∈`), test_drawn_panels (random trees), test_triggers (words).
- Rule tests (failed before): test_notation `test_a_membership_is_its_node_its_latex_and_its_value_
  wherever_the_model_writes_it` (ImportError, then `Call('within')` != `In`) and `test_napkin_draw_
  writes_a_membership_as_the_model_writes_it` (read `ip⇔within(ξp,λp,ηp)`; then typeset raised);
  test_triggers `test_a_membership_test_reads_as_the_file_writes_it` ('within(x, lo, hi)').
- test_layout `test_a_bundle_of_one_arrow_is_that_arrow`: kept one arrow per card of the default
  kinds only, but its pictures bundle any kinds; it failed in the full `-n 2` run of tests/draw, also
  on a copy without this change (two `changes` arrows of c2, `bundle` with `changes`). It now keeps
  one per kind of the picture's `settings.bundle`, as `check_bundles` reads it.
- Final: tests/draw + tests/commands/test_draw.py 864 passed, 1 skipped; ruff clean on 9 files.

## Decisions
- `In` stays whole in an equation's head (no split at `∈`): an interval has no top-level `+`/`−`.
- The trigger words are in scope: a guard's and a trigger's membership reach the picture only there.
- A declared range stays the chain `lo ≤ S ≤ hi` (a bound line), not `S ∈ [lo, hi]`.

## For the main session
- docs/extending.md (steps 8, 11; "a form that is no operation", step 6) names `ARITY` and `_call` of
  draw/notation.py and `test_the_notation_knows_each_function_of_the_language`: none exists (stale
  before this change).
- The failing example of test_layout came only in the full parallel run (not the file alone, not
  under `-n 2` alone), though SHAPE derandomizes: which examples a test draws depends on the tests
  that ran before it in its worker. Not chased further.
