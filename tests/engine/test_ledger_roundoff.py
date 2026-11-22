"""A decision must not turn on the last places of a ledger read.

A stock's accepted ledger balance and the trajectory of its numerical method agree to a few
units in the last place, and which way they differ depends on the platform's arithmetic (the
OpenBLAS kernel, Linux or macOS). Each case below once gave a different answer on Linux than on
macOS. Here every ledger read that a decision makes is moved two places each way
(`stocks.LEDGER_PROBE`), and each case must still give its specified answer. The generated
corpus applies the same probe (`test_port_invariance.py`, transformation `roundoff`).
"""

from dataclasses import replace

import pytest

from napkin.engine.timeline import Plan, stocks
from tests.engine import (
    test_clock_moments,
    test_declared_stock_faces,
    test_declared_switches,
    test_moving_reads,
    test_turning_values,
)


def declared_faces_moving(monkeypatch):
    connect = Plan.connect

    def moving(plan, *args, **kwargs):
        groups = connect(plan, *args, **kwargs)
        return [replace(group, moves=True) if group.way == 'declared' else group for group in groups]

    monkeypatch.setattr(Plan, 'connect', moving)
    test_declared_stock_faces.test_a_declared_face_with_balanced_through_flow_keeps_its_stock(True)


CASES = {
    'a turning sum fires once at each crossing': lambda _: (
        test_turning_values.test_a_weighted_sum_of_two_stores_that_turns_crosses_its_level()
    ),
    'an edit at a stop agrees with the reference': lambda _: (
        test_clock_moments.test_an_edit_at_a_stop_before_the_read_agrees_in_place_and_resumed(37)
    ),
    'a keyed rate switches at the exact crossing': lambda _: (
        test_moving_reads.test_a_rate_keyed_by_a_moving_store_steps_where_the_store_crosses_a_key(False)
    ),
    'a stepping capacity is integrated': lambda _: (
        test_declared_switches.test_a_moving_solver_drains_at_the_incoming_rate_until_the_tank_reaches_two_litres(
            'capacity', False, -0.5
        )
    ),
    'a residue at a capped face stays in its band': declared_faces_moving,
}


@pytest.mark.parametrize('units', [-2, 2])
@pytest.mark.parametrize('case', sorted(CASES))
def test_a_decision_does_not_turn_on_the_last_places_of_a_ledger_read(case, units, monkeypatch):
    monkeypatch.setattr(stocks, 'LEDGER_PROBE', units)
    CASES[case](monkeypatch)
