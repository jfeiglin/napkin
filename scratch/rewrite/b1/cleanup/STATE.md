# Cleanup of the dormant tests before G2 (track b1/cleanup)

Brief: the task message of the main session (26 dormant files: 23 in `tests/model/`, plus
`tests/test_check.py`, `tests/test_scenario_ownership.py`, `tests/test_scenario_scope.py`).
Rules: `briefs/COMMON-B.md`. No git command that changes the repo. Do not edit `tests/dormant.txt`.

## Done
- Deleted (triage DELETE): test_desugar, test_kept_parts, test_resolved, test_start_states,
  test_structure (status first match is in tests/language/test_status.py).
- test_check.py: the output-scope case deleted (outputs left, D10); 65 cases pass on stubs.
- Wait for M: test_scenario_ownership (tools.publish, change 13), test_scenario_scope
  (scenarios/tests and tests.helpers read the catalogue).

## Plan per file (port = rewrite on compile_text/load_scenario + napkin.engine.run/read)
- delete test_list_reductions (live: tests/language/test_collections.py, tests/engine/test_collections.py)
- test_shared_formulas: keep the 3 face proofs (fix imports), port the diamond (DeclaredAssert.fixed)
- test_structure_checks: places that take yes/no / a time / one dimension; a circle of formulas
- test_analysis: formulas in any order = their definition; a bound that reads an input
- test_contracts: keep the expression tests; nonfinite numbers, all faults, ODE, evidence checks
- the others: see their docstrings once written

## Decisions
- A bug is a test with `pytest.mark.xfail(strict=True, raises=...)` naming it, so the file can
  leave the dormant list and the mark fails once the bug is fixed.

## Bugs found (napkin/model, S7-F's)
- parser recursion: about 11 frames per bracket level; `(((... x ...)))` 150 deep, a nest of
  150 calls or choices: RecursionError at parse. semantic.py: a left sum of 700 terms likewise.
- two `record shared: ...` lines in one model: no problem, the second replaces the first.

## In progress
- writing the ports
