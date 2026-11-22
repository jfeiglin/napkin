"""Three independent counterexamples to a proof that a reported value never falls."""

from tests.engine.lag_monotonicity_cases import check_lag_monotonicity


def test_a_transfer_does_not_preserve_the_minimum_of_its_endpoints():
    check_lag_monotonicity(0, ('minimum',))


def test_later_occurrences_can_change_the_value_selected_at_a_fixed_cutoff():
    check_lag_monotonicity(0, ('cutoff',))


def test_a_transfer_between_overlapping_occurrences_can_debit_the_first():
    check_lag_monotonicity(0, ('overlap',))
