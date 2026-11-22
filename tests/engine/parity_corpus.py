"""Run the independent authoring comparisons in the corpus's existing text/builder slot."""

from traceback import format_exc

from tests.engine import (
    authoring_parity_cases,
    parity_collection_cases,
    parity_lag_cases,
    parity_number_cases,
    parity_records,
    parity_records_bounds,
    parity_records_proofs,
    parity_records_studies,
    parity_solver_cases,
    parity_stage_cases,
)

CHECKS = (
    authoring_parity_cases.check_authoring_parity,
    parity_stage_cases.check_plant,
    parity_stage_cases.check_stage,
    parity_stage_cases.check_comparison,
    parity_stage_cases.check_switch,
    parity_stage_cases.check_stock,
    parity_stage_cases.check_cross_rate,
    parity_collection_cases.check_collection_scope_parity,
    parity_collection_cases.check_collection_kind_parity,
    parity_collection_cases.check_filter_history_parity,
    parity_number_cases.check_number_parity,
    parity_solver_cases.check_solver_parity,
    parity_records_bounds.check_parity_reversible,
    parity_records_bounds.check_parity_simultaneous,
    parity_records.check_parity_history,
    parity_records.check_parity_identity,
    parity_records.check_parity_numerics,
    parity_records_proofs.check_parity_network,
    parity_records_proofs.check_parity_solver,
    parity_records_proofs.check_parity_arguments,
    parity_records_proofs.check_parity_reach,
    parity_records_studies.check_parity_study,
    parity_records_studies.check_parity_selection,
    parity_lag_cases.check_lag_monotonicity_parity,
    parity_lag_cases.check_lag_bends_parity,
)


def check_authoring_parity(seed):
    """Check every family for this seed, including those following a failed comparison."""
    failures = {}
    for check in CHECKS:
        try:
            check(seed)
        except AssertionError as problem:
            failures[check.__name__] = problem.args
        except Exception:
            failures[check.__name__] = format_exc()
    assert not failures, (seed, failures)
