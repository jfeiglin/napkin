"""Fully feasible requests can be many orders of magnitude apart in one sharing problem."""

import numpy as np
import pytest

from napkin.engine.timeline.selection import Rows, select


def test_extremely_different_requests_retain_their_amounts_when_all_can_be_served():
    tiny = 1e-38
    rows = Rows(3)
    rows.equal_to([0, 1, -1], 0)
    rows.with_parts([0, 0, 0], [(1, 1.0), (2, -1.0)], tiny)
    observations = []
    result = select(
        rows,
        [0, 0, 0],
        [1, tiny, tiny],
        [[([1, 0, 0], 1)], [([0, 1, 0], tiny)]],
        [],
        [1, tiny, tiny],
        measure=lambda raw, published: observations.append((raw.tolist(), published.tolist())),
    )
    assert result.tolist() == [1, tiny, tiny]
    assert observations == [([1, tiny, tiny], [1, tiny, tiny])]


@pytest.mark.parametrize('rule', ['upper', 'equality', 'positive part', 'bound', 'claim', 'preference'])
def test_conflicting_rows_claims_and_priorities_keep_the_general_solution(rule):
    rows = Rows(2)
    limits = [3, 3]
    tiers = [[([1, 0], 1), ([0, 1], 1)]]
    prefs = []
    expected = [1.0, 1.0]
    if rule == 'upper':
        rows.at_most([1, 1], 1)
        expected = [0.5, 0.5]
    elif rule == 'equality':
        rows.equal_to([1, -1], 1)
        expected = [2, 1]
    elif rule == 'positive part':
        rows.with_parts([0, 0], [(0, 1.0), (1, 1.0)], 1)
        expected = [0.5, 0.5]
    elif rule == 'bound':
        limits = [0.5, 3]
        expected = [0.5, 1]
    elif rule == 'claim':
        tiers = [[([1, 0], 2)]]
        expected = [2, 1]
    else:
        rows.at_most([1, 1], 2)
        tiers = [[([1, 1], 2)]]
        prefs = [([1, 0], 2)]
        expected = [2, 0]
    assert np.asarray(select(rows, [0, 0], limits, tiers, prefs, [1, 1])) == pytest.approx(expected)
