# Cleanup of the dormant tests before G2 (track b1/cleanup)

Brief: the task message of the main session (26 dormant files: 23 in `tests/model/`, plus
`tests/test_check.py`, `tests/test_scenario_ownership.py`, `tests/test_scenario_scope.py`).
Rules: `briefs/COMMON-B.md`. No git command that changes the repo. `tests/dormant.txt` not edited.

## Done (all 26 files)
- Deleted: test_desugar, test_kept_parts, test_resolved, test_start_states, test_structure (triage
  DELETE; the status first match is in tests/language/test_status.py), test_list_reductions (its
  cases are live in tests/language/test_collections.py and tests/engine/test_collections.py).
- Ported onto compile_text/load_scenario + napkin.engine.run/read, counts (passed + xfailed):
  test_analysis 14, test_bases 4, test_build 10, test_compile 8, test_continuation 9,
  test_contracts 47+2, test_copies_and_start 6, test_diagnostic_places 13, test_library 7,
  test_local_bases 8+1, test_long_expressions 38+7, test_material 10+2, test_notes 10+2,
  test_parts 5, test_shared_formulas 4, test_structure_checks 10, test_units 10.
- tests/test_check.py 66: the output-scope case deleted (outputs left, D10); the new Evidence
  stage of tools/check.py (m-prep's) stubbed in stub_stages, and tested on a synthetic catalogue.
- Wait for M: test_scenario_ownership (tools.publish, change 13), test_scenario_scope
  (scenarios/tests and tests.helpers read the catalogue).
- Joint run of the 18 kept files with -n 2: 279 passed, 14 xfailed, 6 s; ruff clean.

## Decisions
- A bug is a test with `pytest.mark.xfail(strict=True, raises=...)` naming it, so the file can
  leave the dormant list and the mark fails once the bug is fixed. A RecursionError is raised again
  as a short `Recursed` so the report stays fast under xdist.
- Kept the 15 expression and prover tests of test_contracts (no language) and the 3 face proofs of
  test_shared_formulas (the face proof is live in engine/continuous/segment.advance).

## Bugs found (none fixed; napkin/model is S7-F's, the engine S7-E's)
- parse.py recurses ~11 frames per bracket level: 150 levels of brackets, calls, choices or a
  right-nested sum end in RecursionError; semantic.py likewise for a left sum of 700 terms.
- two `record shared: ...` lines are accepted; the second replaces the first (check_names).
- a note citing no record (`checks: "x"  @missing`) is accepted by compile_text and load_scenario.
- a value before an event or a flow of its name: AttributeError (Resolver.syntax keeps the later).
- `assert s.a + s.b in [...]` over two moving stores (the spec's sum form) compiles, then the run
  stops at 0 h: "cannot be certified: it reads more than one store".

## Noted, not mine
- napkin/model/evidence.basis_digest and basis_content have no caller; tools/check.catalogue_problems
  reads outputs; tests/model/modeltest.py stays for tests/publish/test_pages.py (M).
- during the last run, napkin/engine/solve/distance.py (uncommitted, another agent) imported
  `qdldl`, which is not installed: every import of napkin.engine failed for a while.

## Remains
- rerun the 18 files once napkin.engine imports again; the last message.
