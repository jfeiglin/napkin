"""Every answer that the spec states for a solver (`scratch/rewrite/spec.md`, "An entity owns its
solver", "Solver and execution contract" and the acceptance cases), from the selection order.

The expected values are the spec's, worked by hand where it gives them as prose. The library holds a
fair level to 1e-7 of each request (a held claim keeps its level as a lower bound with that slack,
`fair.FIX`), so an answer is compared within 1e-6 of the size of its request.
"""

from fractions import Fraction

import pytest

from napkin.engine.solve import FLOW, OTHER, Budget, Solver

from . import cases

TOLERANCE = 1e-6


def near(value, expected, size=1.0):
    return value == pytest.approx(float(expected), abs=TOLERANCE * size)


def solve(problem, **budget):
    return Solver(Budget(**budget) if budget else None).solve(problem)


def test_two_bottlenecks_share_fairly_with_no_objective():
    answer = solve(cases.bottlenecks(objective=False))
    assert all(near(answer[k], v, 6) for k, v in zip('abc', (2, 2, 3)))
    # fair sharing raises all three to 2 W; then the first limit binds and only c rises
    assert answer.levels == pytest.approx([1 / 3, 1 / 3, 1 / 2], abs=TOLERANCE)


def test_total_shortfall_first_leaves_b_unserved():
    answer = solve(cases.bottlenecks(objective=True))
    assert all(near(answer[k], v, 6) for k, v in zip('abc', (4, 0, 5)))
    # adding the limits gives a + b + c <= 9 - b: serving 9 W needs b = 0, total unmet 9 W
    assert near(answer.optima[0], 9, 6)
    assert near(sum(answer[('unmet', k)] for k in 'abc'), 9, 6)


@pytest.mark.parametrize(('available', 'care', 'outreach'), [(100, 70, 30), (80, 56, 24)])
def test_staffing(available, care, outreach):
    answer = solve(cases.staffing(float(available)))
    assert near(answer['care'], care, available)
    assert near(answer['outreach'], outreach, available)


def test_pump_and_battery_with_empty_stocks():
    answer = solve(cases.pump())
    # 1 W of charge runs the pump at 0.5 Wh per litre: 2 L/h, which the empty tank passes to the clinic
    expected = {'fill': 2, 'clinic': 2, 'town': 0, 'motor': 1, 'charge': 1}
    assert all(near(answer[k], v, 6) for k, v in expected.items())


def test_pump_with_no_request_leaves_every_transfer_idle():
    answer = solve(cases.pump(clinic=0.0, town=0.0))
    assert all(near(answer[k], 0, 6) for k in ('fill', 'clinic', 'town', 'motor', 'charge'))


def test_pump_with_water_in_storage_serves_both_requests_from_inventory():
    answer = solve(cases.pump(tank_empty=False))
    # the objectives leave higher rates equally optimal; the flow targets select exactly 6 L/h each
    expected = {'clinic': 6, 'town': 6, 'fill': 0, 'charge': 0, 'motor': 0}
    assert all(near(answer[k], v, 6) for k, v in expected.items())


@pytest.mark.parametrize(
    ('east', 'west', 'east_full', 'expected'),
    [(6.0, 6.0, False, (6, 2)), (2.0, 6.0, False, (2, 6)), (6.0, 6.0, True, (0, 6))],
)
def test_provider_limit_across_two_connections(east, west, east_full, expected):
    answer = solve(cases.provider(east, west, east_full))
    assert near(answer['east'], expected[0], 6)
    assert near(answer['west'], expected[1], 6)


ROWS = {
    # (needs, supply, garden route up, clinic first): clinic use, garden use, junction supply, the two routes
    '0 h': ((0, 6, 6), (8, 0, 0), True, False, (4, 4, 8, 4, -4)),
    '0 h, clinic first': ((0, 6, 6), (8, 0, 0), True, True, (6, 2, 8, 6, -2)),
    '1 h': ((0, 3, 3), (8, 0, 0), True, False, (3, 3, 6, 3, -3)),
    '2 h, garden route down': ((0, 6, 6), (8, 0, 0), False, False, (6, 0, 6, 6, 0)),
    'unequal claims': ((0, 2, 6), (4, 0, 0), True, False, (1, 3, 4, 1, -3)),
}


@pytest.mark.parametrize('row', ROWS)
def test_worked_network_rates(row):
    needs, supply, up, first, expected = ROWS[row]
    answer = solve(cases.network(needs, supply, garden_up=up, clinic_first=first))
    got = (
        answer[('use', 'clinic')],
        answer[('use', 'garden')],
        answer[('supply', 'junction')],
        answer[('carried', 'junction_clinic')],
        answer[('carried', 'garden_junction')],
    )
    assert all(near(g, e, 6) for g, e in zip(got, expected)), got


@pytest.mark.parametrize(
    ('up', 'levels'),
    [(True, (Fraction(8, 3), Fraction(-4, 3), Fraction(-4, 3))), (False, (3, -3, 0))],
)
def test_worked_network_levels(up, levels):
    answer = solve(cases.network(garden_up=up))
    got = [answer[('level', place)] for place in cases.PLACES]
    # a common offset leaves the routes unchanged; equal scales and references zero select it
    assert all(near(g, e, 30) for g, e in zip(got, levels)), got


def test_worked_network_in_kilowatts():
    watts = solve(cases.network())
    kilowatts = solve(cases.network(unit=1000.0))
    assert near(kilowatts[('use', 'clinic')], 0.004, 1e-3)
    assert near(kilowatts[('use', 'garden')], 0.004, 1e-3)
    assert near(kilowatts[('level', 'junction')], Fraction(8, 3), 30)
    # the working units are the same, so the answers agree but for rounding
    for key, value in zip(watts.keys, watts.x):
        factor = 1.0 if key[0] in ('level',) else 1000.0
        assert kilowatts[key] * factor == pytest.approx(value, abs=1e-9 * (1 + abs(value)))


def test_reordered_network_changes_no_named_result():
    plain = solve(cases.network())
    reordered = solve(cases.network(order=(2, 0, 1)))
    for key, value in zip(plain.keys, plain.x):
        assert reordered[key] == pytest.approx(value, abs=1e-8 * (1 + abs(value)))


@pytest.mark.parametrize('kind', [OTHER, FLOW])
def test_band_in_the_distance_step(kind):
    low, high = solve(cases.band(0.0, kind)), solve(cases.band(5.0, kind))
    assert (low['x'], low['y']) == pytest.approx((2.0, 2.0), abs=1e-9)
    assert (high['x'], high['y']) == pytest.approx((3.0, 3.0), abs=1e-9)


@pytest.mark.parametrize('kind', [OTHER, FLOW])
def test_sum_of_one_in_the_distance_step(kind):
    answer = solve(cases.sum_one(kind))
    assert (answer['x'], answer['y']) == pytest.approx((0.5, 0.5), abs=1e-9)


def test_the_distance_cases_by_the_exact_fallback():
    # no Newton step: the QP of HiGHS answers
    for problem, expected in ((cases.band(0.0), 2.0), (cases.band(5.0), 3.0), (cases.sum_one(), 0.5)):
        answer = solve(problem, newton_steps=0)
        assert answer.work.methods == ['qp']
        assert (answer['x'], answer['y']) == pytest.approx((expected, expected), abs=1e-7)


def test_bridge_flow_takes_more_than_its_request():
    unbounded, need = cases.bridge(capped=False)
    capped, _ = cases.bridge(capped=True)
    free, held = solve(unbounded), solve(capped)
    # worked by hand: with use unbounded, X takes 4.65 and B gets 5.35; capped, X 0.1 and B 0.8
    assert near(free[('use', 'X')], Fraction(93, 20), 10)
    assert near(free[('use', 'B')], Fraction(107, 20), 10)
    assert near(held[('use', 'X')], Fraction(1, 10), 10)
    assert near(held[('use', 'B')], Fraction(4, 5), 10)
    for answer, total in ((free, Fraction(93, 20)), (held, Fraction(46, 5))):
        unmet = sum(max(0.0, need[name] - answer[('use', name)]) for name in need)
        assert near(unmet, total, 10)
        assert near(answer.optima[0], total, 10)


def test_one_solver_over_two_junctions_serves_a_third_each():
    answer = solve(cases.junctions())
    for name in ('to_a', 'to_b', 'to_c'):
        assert near(answer[name], Fraction(1, 3))
    assert near(answer['onward'], Fraction(2, 3))


@pytest.mark.parametrize(('cap', 'rate'), [(None, 10.0), (7.0, 7.0)])
def test_one_pipe_with_three_requests(cap, rate):
    answer = solve(cases.one_pipe(cap))
    # the least transfer that serves all three claims; capped, the shortfalls are 3, 1 and 0
    assert near(answer['pipe'], rate, 10)
    shortfalls = [max(0.0, request - answer['pipe']) for request in (10, 8, 6)]
    expected = (0, 0, 0) if cap is None else (3, 1, 0)
    assert all(near(s, e, 10) for s, e in zip(shortfalls, expected))


@pytest.mark.parametrize(
    ('labor', 'work', 'limit', 'fraction'),
    [(4.0, 8.0, 2.0, 0.5), (0.0, 8.0, float('inf'), 1.0), (0.0, 0.0, float('inf'), 0.0)],
)
def test_one_served_fraction_for_a_flow_with_legs(labor, work, limit, fraction):
    answer = solve(cases.legs(labor, work, limit))
    served = answer['served fraction']
    assert near(served, fraction)
    # each leg carries the fraction of its own request: 2 and 4 at half service, 0 and 8 in full
    assert near(served * labor, fraction * labor, 8)
    assert near(served * work, fraction * work, 8)


@pytest.mark.parametrize(('tiers', 'expected'), [((0, 1), (8, 2)), ((0, 0), (4, 6))])
def test_priority_tiers(tiers, expected):
    # the first tier is served first; one tier shares proportionally to the requests
    answer = solve(cases.reservoir(tiers))
    assert near(answer['first'], expected[0], 12)
    assert near(answer['second'], expected[1], 12)


@pytest.mark.parametrize(
    'build',
    [
        lambda: cases.bottlenecks(objective=False),
        lambda: cases.bottlenecks(objective=True),
        cases.pump,
        cases.provider,
    ],
)
def test_the_exact_fallback_gives_the_same_answers(build):
    # with no Newton step, every distance stage is the QP of HiGHS, on the faces that fair sharing
    # leaves. (On the worked network's face that QP cycles to its iteration limit, and the solve
    # stops by name instead: `distance` says so.)
    method, fallback = solve(build()), solve(build(), newton_steps=0)
    assert set(fallback.work.methods) == {'qp'}
    assert fallback.x == pytest.approx(method.x, abs=TOLERANCE * 10)
