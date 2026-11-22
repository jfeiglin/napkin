# Dormant-file disposition

At `8eeffba`, ten entries in `tests/dormant.txt` covered 41 tracked files. The current
suite has no dormant exclusions. Each row below names a former entry or a file it covered.
The suite still honors explicit scenario selections.

## Central tests

| File | Disposition |
| --- | --- |
| `tests/test_tools_new_catalogue.py` | Re-enabled the existing new-package contract. |
| `tests/test_scenario_ownership.py` | Ported pruning and ownership checks to published readings. |
| `tests/test_scenario_scope.py` | Kept source selection and edit-discovery coverage, using the shared source-file helper. |
| `tests/engine/test_distributions_deep.py` | Ported the million-draw CDF checks to named streams and the two-sample catalogue study to the Monte Carlo API. Removed the Latin-sampling test with the retired method. |
| `tests/evidence/test_catalogue.py` | Ported catalogue roles, owner evidence collections, variant identities and dossier checks. |
| `tests/evidence/test_scientific_spec.py` | Removed the obsolete scientific-spec format tests. |
| `tests/release/wheel_smoke.py` | Removed the suppression. This script runs against an installed wheel in the release check. |

## scenarios/tests

| File | Disposition |
| --- | --- |
| `__init__.py` | Retained the package marker. |
| `oracle_common.py` | Retained the independent oracle support. |
| `sources.py` | Retained oracle inputs and shared edit precedence for order checks. |
| `test_assumption_review.py` | Checks the owned review records in the composed library and retains the independent-reference check. Supersedes the archived assumption-review artifact checks. |
| `test_catalogue.py` | Checks current completed runs, reports, edits, expected orders and shared evidence. The check fails if the fixture names a missing run or output. |
| `test_library_integrity.py` | Checks each composed library and manifest ownership counts. |
| `test_scenario_files.py` | Checks current source files, package settings and spread edits with the current parser and configuration APIs. |
| `test_limits.py` | Removed the old publication limits-page contract. |
| `test_methods_links.py` | Removed the retired methods-page link contract. |

## tests/publish

| File | Disposition |
| --- | --- |
| `__init__.py` | Retained the package marker. |
| `test_limits.py` | Re-enabled the existing limits-section tests. |
| `test_brief_spreads.py` | Replaced historical output-format checks with a test of the current publisher sampling each authored run. |
| `test_identity.py` | Ported model revision, run-store identity and dossier reachability coverage. |
| `test_owned_evidence.py` | Ported selected-build and dossier ownership coverage. |
| `test_publish_drift.py` | Ported drift checks for current artifacts. |
| `test_publish_selection.py` | Ported builder selection and evaluation scope checks. |
| `test_brief.py`, `test_briefs.py` | Removed checks of the historical brief renderer. The current renderer has its own comparison tests. |
| `test_builder_robustness.py`, `test_display_metadata.py` | Removed contracts of historical builders and display metadata. |
| `test_evidence_relations.py`, `test_formatting.py` | Removed historical artifact layout and formatting checks. |
| `test_methods.py`, `test_pages.py` | Removed tests of retired page builders. |

## scenarios/cyber_learning_loop/tests

The six historical files were checked individually before migration. With all markers, five
collected 180 cases. The noise file’s three functions could not collect because its old
uncertainty API was gone. The catalogue now models workforce, learning and defensive response
at an organizational level. The retired checks for individual operations and their detailed
equilibria cannot validate these aggregate outputs. Their original assertions and numbers are
preserved in the [test tree at 8eeffba](https://github.com/jfeiglin/napkin/tree/8eeffba0cfc0627772b4b9629f6171ef26c778f2/scenarios/cyber_learning_loop/tests).

| File | Disposition |
| --- | --- |
| `test_calibration.py` | Tests role-specific productivity gains under baseline, uptake and reversal against their declared workforce assumptions. The five historical checks of work per operation, operation counts, duration, tactical automation share and attribution probability require observations the aggregate model does not produce. Capacity per staff member is a different measure. |
| `test_capabilities.py` | Ported the defensive remediation sensitivity across adoption trajectories. The 36 old cases also tested capability inventory, its origins and use-specific loss routes. The aggregate model has no corresponding stocks or flow measurements. |
| `test_doctrine.py` | Ported decision formation and lapse to the current service-standard review. Tests cover equality at the threshold, the score’s memory and the accumulated observations needed for a decision to change. The old 20 cases also tested correlated individual plan outcomes and consecutive military planning votes, which the workforce model does not produce. |
| `test_loops.py` | Ported bounded defensive attention and the timing and cost of temporary staffing. The 89 old cases also tested detailed queues, operational stage durations, reassignments, and returns from individual activities. The current model updates aggregate work on a budget calendar. Its separate aggregate tests cover that update and learning. |
| `test_noise.py` | Replaced the old uncertainty API with Monte Carlo checks of the median, deterministic replay under one seed and variation across samples. The active random quantity is the staffing reserve. The old error floor for assessments of individual outcomes has no direct counterpart. |
| `test_rest_points.py` | Ported workforce conservation at different staffing levels and the steady-state defensive response under constant observed workload. The 30 old cases also relied on a root solve over granular inventories, mission-specific staffing, value slopes and whole-system equilibrium. The active model has a discrete budget cycle. |
| `conftest.py` | Replaced the old trajectory fixture with a shared compiled model for current tests. |
| `rest_point.py`, `oracle-inputs.json` | Archived the independent solver and its 180-name map together under `historical/tests/`. The active map is empty. Current tests use separately pinned reference observations and the aggregate model’s own contracts. |
| `expected-orders.json` | The central catalogue test checks this entry’s own named-run orders. The earlier detailed expectations are retained at `historical/expected-orders.json`. |

The dormant list, its lookup helpers, suppression branch and dedicated tests were removed.
The collection hook still implements explicit scenario selection.

## Dependencies retired with the ports

The replacement suites use current model fixtures, parser output, records and dossiers. The old
`tests/build.py`, `tests/owned.py`, `tests/model/modeltest.py` and `tests/acceptance/helpers.py`
have no remaining test callers. The unused acceptance files `F5.scn` and `F5.expect.yaml` went
with their old-language loader. The current acceptance suite exercises language constructs
independently (`tests/acceptance/test_every_construct.py`). The superseded publisher modules
`assumptions.py`, `methods.py`, `pages.py` and `runs.py` lost their remaining callers with these
ports. The engine's old `runtime.py` and its `NumericalSettings` export were removed after
the last package and test imports were retired. Historical probes under `scratch/` that load
an older checkout still use its runtime.
