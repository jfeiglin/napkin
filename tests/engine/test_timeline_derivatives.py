"""The report of the derivatives of a run (`napkin/engine/timeline/derivatives.py`, `report`): the value of
each derivative and its class.

The oracles are closed forms, from the numbers that each test gives to its inputs. Each model is a
line or two with events, so its outputs at the horizon are sums and products of the inputs, and
their derivatives are written beside them in each test. For a block that a solver integrates, the
closed form is evaluated at 40 digits and differentiated there (mpmath). A class is checked on a
model that is made to have it: a tie that the test writes into the inputs, and the same model
with the tie taken away, which is smooth.
"""

import math

import mpmath
import numpy as np
import pytest

from napkin.core import expr
from napkin.engine import timeline
from napkin.engine.timeline import derivatives, smooth
from napkin.engine.timeline.influence import Influence
from napkin.engine.timeline.places import output_place
from napkin.model import hybrid

HEAD = """scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon {days} days
    scope "Nothing: the model is synthetic."

"""
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'
DAY = 24.0


def plan_of(tmp_path, days, body, header=None, rows=()):
    """The plan of a model with `body` after its head, and with one table, `cells.csv`, when the
    model has one."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / 'model.scn'
    path.write_text(HEAD.replace('{days}', str(days)) + body + RECORD, encoding='utf-8')
    if header is not None:
        lines = [','.join(repr(float(value)) for value in np.atleast_1d(row)) for row in rows]
        (tmp_path / 'cells.csv').write_text('\n'.join([header, *lines]) + '\n', encoding='utf-8')
    return timeline.Plan.of(hybrid.compile(path))


def classes(report, output):
    return {name: item['class'] for name, item in report['derivatives'][output].items()}


def values(report, output):
    return {name: item['value'] for name, item in report['derivatives'][output].items()}


# ---- smooth, and zero by the structure -------------------------------------------------------------

LINES = """Cell:  @shape
    "One cell with two lines that fill and one that drifts."
    input pace: fraction/day = 0.3 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    input other: fraction/day = 0.3 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    input drift: fraction/day = 0.1 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    let scale: fraction = 1  @shape
    var first: fraction = 0 size 100  @shape
    var second: fraction = 0 size 100  @shape
    var side: fraction = 0 size 100  @shape
    flow fill: -> first at pace * scale
    flow match: -> second at other * scale
    flow slide: -> side at drift

cells: Cell from "cells.csv"

output first_total: fraction = sum(Cell.first)  @shape
    "The first line of all cells"

output side_total: fraction = sum(Cell.side)  @shape
    "The drift of all cells"

output best: fraction = max(sum(Cell.first), sum(Cell.second))  @shape
    "The larger of the two lines"
    level

output mix: fraction = sum(Cell.side) + max(sum(Cell.first), sum(Cell.second))  @shape
    "The drift and the larger of the two lines"
    level
"""
SCALES = [1.0, 0.5, 2.25]
INPUTS = ('cells_1.pace', 'cells_1.other', 'cells_1.drift')


def lines_report(tmp_path, pace, other, drift=0.1):
    plan = plan_of(tmp_path, 10, LINES, 'scale: fraction @shape', SCALES)
    given = dict(zip(INPUTS, (pace, other, drift)))
    return derivatives.report(plan, given, INPUTS)


def test_a_derivative_with_no_read_from_its_input_to_its_output_is_zero_by_the_structure(tmp_path):
    """Each line of a cell reads one input: the first `pace`, the second `other`, the drift
    `drift`. So the sum of the first lines moves with `pace` alone, by the sum of the scales times
    the 10 days, and the sum of the drifts with `drift` alone, by 10 days for each cell. The other
    derivatives are zero whatever the values are: the report says so, and gives the number 0."""
    report = lines_report(tmp_path, 0.4, 0.3)
    total, days = sum(SCALES), 10.0
    assert report['outputs']['first_total'] == {
        'value': pytest.approx(0.4 * total * days),
        'unit': 'fraction',
        'label': 'The first line of all cells',
    }
    assert classes(report, 'first_total') == {
        'cells_1.pace': 'smooth',
        'cells_1.other': 'structurally zero',
        'cells_1.drift': 'structurally zero',
    }
    assert values(report, 'first_total') == pytest.approx(
        {'cells_1.pace': total * days, 'cells_1.other': 0.0, 'cells_1.drift': 0.0}, rel=1e-12
    )
    assert classes(report, 'side_total') == {
        'cells_1.pace': 'structurally zero',
        'cells_1.other': 'structurally zero',
        'cells_1.drift': 'smooth',
    }
    assert values(report, 'side_total')['cells_1.drift'] == pytest.approx(len(SCALES) * days, rel=1e-12)
    item = report['derivatives']['first_total']['cells_1.pace']
    assert item['unit'] == 'fraction per fraction/day' and item['why'] == [] and item['error'] == 0.0
    assert report['unsupported'] is None and report['inputs'] == list(INPUTS)


def test_the_graph_of_influence_has_each_output_that_an_input_can_reach(tmp_path):
    plan = plan_of(tmp_path, 10, LINES, 'scale: fraction @shape', SCALES)
    graph = Influence(plan.fast() or plan)
    assert graph.outputs({'cells_1.pace'}) == {'first_total', 'best', 'mix'}
    assert graph.outputs({'cells_1.other'}) == {'best', 'mix'}
    assert graph.outputs({'cells_1.drift'}) == {'side_total', 'mix'}
    assert graph.outputs({'cells_1.scale'}) == {'first_total', 'best', 'mix'}
    assert output_place('side_total') not in graph.after({'cells_1.pace', 'cells_1.other'})


RESTING = """tank:  @shape
    "A store that is used up, and filled once."
    input extra: fraction = 0.1 in 0 to 1  @shape
    input refill_at: h = 30 h in 0 h to 200 h  @shape
    var store: fraction = 0.5 size 1  @shape
    var used: fraction = 0 size 10  @shape
    flow use: store -> used at 0.01 fraction/h
    event refill once when t >= refill_at:  @shape
        "The store gets more."
        store = store + extra

output used: fraction = tank.used  @shape
    "What was used"
"""


def test_what_a_step_writes_into_a_store_reaches_what_the_store_feeds_when_it_is_empty(tmp_path):
    """The store is used at a fixed rate until it is empty; then nothing more is used. A step adds
    `extra` to the store at 30 h. The rate of the use reads neither the store nor `extra`, and yet
    `extra` decides how much is used in the end: 0.6 of the 2.4 that 10 days would use, because the
    store is empty at 60 h. The graph has that path, through the fact that the store rests on its
    bound. In this run the store comes to rest, which the engine carries no derivative through:
    the class is `unsupported`, and not a zero by the structure."""
    plan = plan_of(tmp_path, 10, RESTING)
    graph = Influence(plan.fast() or plan)
    assert graph.outputs({'tank.extra'}) == {'used'} and graph.outputs({'tank.refill_at'}) == {'used'}
    report = derivatives.report(plan, None, ('tank.extra', 'tank.refill_at'))
    assert report['outputs']['used']['value'] == pytest.approx(0.6, rel=1e-12)
    assert classes(report, 'used') == {'tank.extra': 'unsupported', 'tank.refill_at': 'unsupported'}
    assert 'rest' in report['unsupported']


# ---- two pieces of an expression that meet ---------------------------------------------------------


def test_the_pairs_of_an_expression_are_the_parts_at_whose_tie_two_pieces_meet():
    """The two sides of a comparison, each two arguments of `min` or `max`, the value of `clip`
    and each limit, the argument of `abs` and zero: at each level of the expression. A written
    text (the name of a value of a status) is no number, and an expression with one piece has no
    pair."""
    node = expr.read('max(a, b, c) if x >= y else clip(z, low, high) + abs(w - 1) + min(u, 2 * v)')
    found = {(expr.text(left), expr.text(right)) for left, right in smooth.pairs(node)}
    assert found == {
        ('x', 'y'),
        ('a', 'b'),
        ('a', 'c'),
        ('b', 'c'),
        ('z', 'low'),
        ('z', 'high'),
        ('w - 1', '0'),
        ('u', '2 * v'),
    }
    assert smooth.pairs(expr.read('a + b * exp(c) / sqrt(d)')) == ()
    assert smooth.pairs(expr.read('1 if state == "on" else 0')) == ()
    # The difference of a pair with zero is its first part.
    (pair,) = smooth.pairs(expr.read('abs(q)'))
    assert expr.text(smooth.difference(*pair)) == 'q'
    assert expr.text(smooth.difference(expr.read('a'), expr.read('b'))) == 'a - b'


def test_the_larger_of_two_values_at_a_tie_has_the_derivative_of_one_side(tmp_path):
    """`best` is the larger of the two sums. With `pace` above `other` the first sum gives it: its
    derivative by `pace` is that of the first sum, by `other` it is 0, and both are smooth (a
    small change keeps the first sum above). With the two inputs equal the sums are equal: the
    value follows the first sum when `pace` goes up and the second when it goes down, so each
    derivative is that of one side. The engine gives the derivative of the first of two equal
    arguments."""
    total, days = sum(SCALES), 10.0
    apart = lines_report(tmp_path / 'apart', 0.4, 0.3)
    assert classes(apart, 'best') == {
        'cells_1.pace': 'smooth',
        'cells_1.other': 'smooth',
        'cells_1.drift': 'structurally zero',
    }
    assert values(apart, 'best') == pytest.approx(
        {'cells_1.pace': total * days, 'cells_1.other': 0.0, 'cells_1.drift': 0.0}, rel=1e-12
    )
    tied = lines_report(tmp_path / 'tied', 0.3, 0.3)
    assert classes(tied, 'best') == {
        'cells_1.pace': 'one-sided',
        'cells_1.other': 'one-sided',
        'cells_1.drift': 'structurally zero',
    }
    assert values(tied, 'best') == pytest.approx(
        {'cells_1.pace': total * days, 'cells_1.other': 0.0, 'cells_1.drift': 0.0}, rel=1e-12
    )
    assert tied['derivatives']['best']['cells_1.pace']['why'] != []
    # The sum of the first lines has no tie: it is smooth in the same run.
    assert classes(tied, 'first_total')['cells_1.pace'] == 'smooth'


def test_a_tie_that_an_input_cannot_break_leaves_its_derivative_smooth(tmp_path):
    """`mix` is the drift and the larger of the two sums. At the tie of the two sums, `drift`
    moves neither of them: the derivative of `mix` by `drift` is smooth, 10 days for each cell,
    while its derivatives by `pace` and by `other` are those of one side."""
    tied = lines_report(tmp_path, 0.3, 0.3)
    assert classes(tied, 'mix') == {
        'cells_1.pace': 'one-sided',
        'cells_1.other': 'one-sided',
        'cells_1.drift': 'smooth',
    }
    assert values(tied, 'mix')['cells_1.drift'] == pytest.approx(len(SCALES) * 10.0, rel=1e-12)


CAPPED = """Cell:  @shape
    "A cell whose water seeps, and comes in at the less of two rates."
    input inflow: fraction/day = 0.3 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    input most: fraction/day = 0.3 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    input leak: ratio/day = 0.4 ratio/day in 0 ratio/day to 2 ratio/day  @shape
    let start: fraction = 0.5  @shape
    var water: fraction = start size 1  @shape
    var seeped: fraction = 0 size 10  @shape
    flow storm: -> water at (inflow if inflow <= most else most) * (1 + water) / (1 + water)
    flow seep: water -> seeped at leak * water * (1 + water) / (1 + water)

cells: Cell from "cells.csv"

output water_total: fraction = sum(Cell.water)  @shape
    "Water of all cells"
    level
"""


def test_a_tie_in_the_rate_of_a_block_that_a_solver_integrates_gives_derivatives_of_one_side(tmp_path):
    """The water of a cell comes in at the less of `u` and `m` and seeps at `k` times itself: it
    ends at `v/k + (w0 - v/k) e^(-k T)` with `v` the less of the two, so its derivative by the
    less one is `(1 - e^(-k T)) / k` for each cell, and by the other one 0. (The rates are written
    with a factor that is 1, so that the block has no closed form and a solver integrates it.) With
    `u` below `m` the derivatives are smooth. With the two equal, each is that of one side: the
    choice of the rate takes `u` at the tie, at each state of the run."""
    starts, leak, days = [0.5, 0.9], 0.4, 3.0
    plan = plan_of(tmp_path, 3, CAPPED, 'start: fraction @shape', starts)
    assert [(block.whole, block.linear) for block in plan.blocks] == [(False, False)]
    names = ('cells_1.inflow', 'cells_1.most', 'cells_1.leak')
    slope = len(starts) * (1 - math.exp(-leak * days)) / leak
    below = derivatives.report(plan, dict(zip(names, (0.3, 0.5, leak))), names)
    assert classes(below, 'water_total') == dict.fromkeys(names, 'smooth')
    assert values(below, 'water_total')['cells_1.inflow'] == pytest.approx(slope, rel=1e-6)
    assert values(below, 'water_total')['cells_1.most'] == pytest.approx(0.0, abs=1e-9)
    tied = derivatives.report(plan, dict(zip(names, (0.3, 0.3, leak))), names)
    assert classes(tied, 'water_total') == {
        'cells_1.inflow': 'one-sided',
        'cells_1.most': 'one-sided',
        'cells_1.leak': 'smooth',
    }
    assert values(tied, 'water_total')['cells_1.inflow'] == pytest.approx(slope, rel=1e-6)
    assert values(tied, 'water_total')['cells_1.most'] == pytest.approx(0.0, abs=1e-9)
    # By the leak: the derivative of the closed form, `d/dk [v/k + (w0 - v/k) e^(-k T)]`.
    by_leak = sum(
        -0.3 / leak**2
        + (0.3 / leak**2) * math.exp(-leak * days)
        - days * (start - 0.3 / leak) * math.exp(-leak * days)
        for start in starts
    )
    assert values(tied, 'water_total')['cells_1.leak'] == pytest.approx(by_leak, rel=1e-6)


NEARING = """tank:  @shape
    "A tank whose water comes near its cap."
    input leak: ratio/h = 1 ratio/h in 0 ratio/h to 10 ratio/h  @shape
    input cap: fraction = 0.5 in 0 to 1  @shape
    var water: fraction = 0.1 size 1  @shape
    flow fill: -> water at (leak * (cap - water) if water <= cap else 0 fraction/h)

output water: fraction = tank.water  @shape
    "Water"
    level
"""


def test_a_value_that_comes_to_the_edge_of_a_piece_and_stays_there_gives_derivatives_of_one_side(tmp_path):
    """The water fills at `k (c - w)` while it is at or below its cap `c`, and not at all above
    it: it is `c + (w0 - c) e^(-k t)`, which comes near the cap and never passes it. With `k` of
    0.05 an hour the water is 2.7% below the cap after the 3 days: the choice of the rate is far
    from its edge, and the derivatives are smooth, `1 - e^(-k T)` by the cap and
    `T (c - w0) e^(-k T)` by `k`. With `k` of 1 an hour the water is within the tolerance of the
    cap from 21 h on: the state sits on the edge of the two pieces of the rate, and each
    derivative is that of one side. The engine sees that at the states at which it reads the
    block, and not at the start of the segment, where the water is far from the cap."""
    plan = plan_of(tmp_path, 3, NEARING)
    names = ('tank.leak', 'tank.cap')
    hours, gap = 3 * DAY, 0.5 - 0.1
    far = derivatives.report(plan, {'tank.leak': 0.05, 'tank.cap': 0.5}, names, error=False)
    assert classes(far, 'water') == dict.fromkeys(names, 'smooth')
    assert values(far, 'water') == pytest.approx(
        {'tank.leak': hours * gap * math.exp(-0.05 * hours), 'tank.cap': 1 - math.exp(-0.05 * hours)},
        rel=1e-8,
    )
    near = derivatives.report(plan, {'tank.leak': 1.0, 'tank.cap': 0.5}, names, error=False)
    assert classes(near, 'water') == dict.fromkeys(names, 'one-sided')
    assert values(near, 'water')['tank.cap'] == pytest.approx(1.0, rel=1e-8)


# ---- the events of one moment ---------------------------------------------------------------------

TWO_EVENTS = """tank:  @shape
    "A tank that fills, with two events."
    input first_at: h = 30 h in 0 h to 200 h  @shape
    input second_at: h = 30 h in 0 h to 200 h  @shape
    input pace: fraction/h = 0.01 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    var level: fraction = 0 size 100  @shape
    flow fill: -> level at pace
    event double once when t >= first_at:  @shape
        "The level doubles."
        level = 2 * level
    event add once when t >= second_at:  @shape
        "One more."
        level = level + 1

output level: fraction = tank.level  @shape
    "Level"
    level
"""
TIMES = ('tank.first_at', 'tank.second_at', 'tank.pace')


def test_two_events_at_one_time_whose_times_move_apart_give_derivatives_of_one_side(tmp_path):
    """The level fills at `r`, doubles at `a` and gets 1 more at `b`. With `a` before `b` it ends
    at `r a + r T + 1`: its derivative is `r` by `a`, 0 by `b` and `a + T` by `r`. With `a` and
    `b` at one time the file puts the doubling first, and the same formula holds for `a` at or
    before `b`; with `a` after `b` the level would end 1 higher. So at the tie the derivatives by
    `a` and by `b` are those of one side. The rate moves neither time: its derivative is smooth."""
    pace, hours = 0.01, 10 * DAY
    plan = plan_of(tmp_path, 10, TWO_EVENTS)
    apart = derivatives.report(
        plan, {'tank.first_at': 30.0, 'tank.second_at': 31.0, 'tank.pace': pace}, TIMES
    )
    assert apart['outputs']['level']['value'] == pytest.approx(pace * 30.0 + pace * hours + 1, rel=1e-13)
    assert classes(apart, 'level') == dict.fromkeys(TIMES, 'smooth')
    exact = {'tank.first_at': pace, 'tank.second_at': 0.0, 'tank.pace': 30.0 + hours}
    assert values(apart, 'level') == pytest.approx(exact, rel=1e-12, abs=1e-15)
    assert apart['margins']['moments_apart_h'] == pytest.approx(1.0)
    tied = derivatives.report(plan, {'tank.first_at': 30.0, 'tank.second_at': 30.0, 'tank.pace': pace}, TIMES)
    assert tied['outputs']['level']['value'] == pytest.approx(pace * 30.0 + pace * hours + 1, rel=1e-13)
    assert classes(tied, 'level') == {
        'tank.first_at': 'one-sided',
        'tank.second_at': 'one-sided',
        'tank.pace': 'smooth',
    }
    assert values(tied, 'level') == pytest.approx(exact, rel=1e-12, abs=1e-15)


TWO_CLOCKS = TWO_EVENTS.replace(
    """    event double once when t >= first_at:  @shape
        "The level doubles."
        level = 2 * level
    event add once when t >= second_at:  @shape
        "One more."
        level = level + 1
""",
    """    event double once when t >= first_at and t >= second_at:  @shape
        "The level doubles."
        level = 2 * level
""",
)


def test_two_clocks_of_one_rule_at_one_time_give_derivatives_of_one_side(tmp_path):
    """The level doubles at the later of `a` and `b`, at `m`, and ends at `r m + r T`. With `b`
    later, the derivative is `r` by `b` and 0 by `a`, smooth. With the two at one time, the time
    of the event follows the one of the two that goes up: each derivative is that of one side.
    The engine takes the first clock of the file as the latest."""
    pace, hours = 0.01, 10 * DAY
    assert TWO_CLOCKS != TWO_EVENTS
    plan = plan_of(tmp_path, 10, TWO_CLOCKS)
    apart = derivatives.report(
        plan, {'tank.first_at': 30.0, 'tank.second_at': 41.0, 'tank.pace': pace}, TIMES
    )
    assert classes(apart, 'level') == dict.fromkeys(TIMES, 'smooth')
    assert values(apart, 'level') == pytest.approx(
        {'tank.first_at': 0.0, 'tank.second_at': pace, 'tank.pace': 41.0 + hours}, rel=1e-12, abs=1e-15
    )
    tied = derivatives.report(plan, {'tank.first_at': 30.0, 'tank.second_at': 30.0, 'tank.pace': pace}, TIMES)
    assert classes(tied, 'level') == {
        'tank.first_at': 'one-sided',
        'tank.second_at': 'one-sided',
        'tank.pace': 'smooth',
    }
    assert values(tied, 'level') == pytest.approx(
        {'tank.first_at': pace, 'tank.second_at': 0.0, 'tank.pace': 30.0 + hours}, rel=1e-12, abs=1e-15
    )


# ---- a condition at a tie, a value on its bound, two outcomes with one chance -------------------------

GATED = """tank:  @shape
    "A tank that fills, with an event behind a condition."
    input first_at: h = 30 h in 0 h to 200 h  @shape
    input dose: fraction = 0.5 in 0 to 1  @shape
    input limit: fraction = 0.5 in 0 to 1  @shape
    input pace: fraction/h = 0.01 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    var level: fraction = 0 size 100  @shape
    flow fill: -> level at pace
    event double once when t >= first_at and dose >= limit:  @shape
        "The level doubles."
        level = 2 * level

output level: fraction = tank.level  @shape
    "Level"
    level
"""
GATES = ('tank.first_at', 'tank.dose', 'tank.limit', 'tank.pace')


def test_a_condition_at_a_tie_that_an_input_can_break_gives_derivatives_of_one_side(tmp_path):
    """The level doubles at `a` when the dose is at its limit or above. With the dose above the
    limit the level ends at `r a + r T`, and a small change of the dose changes nothing: the
    derivative by the dose and by the limit is 0, smooth. With the dose at the limit, a dose that
    is a little less takes the event away: the derivatives by the dose and by the limit are those
    of one side. The time and the rate do not move the condition: their derivatives are smooth."""
    pace, hours = 0.01, 10 * DAY
    plan = plan_of(tmp_path, 10, GATED)
    point = {'tank.first_at': 30.0, 'tank.dose': 0.7, 'tank.limit': 0.5, 'tank.pace': pace}
    above = derivatives.report(plan, point, GATES)
    exact = {'tank.first_at': pace, 'tank.dose': 0.0, 'tank.limit': 0.0, 'tank.pace': 30.0 + hours}
    assert classes(above, 'level') == dict.fromkeys(GATES, 'smooth')
    assert values(above, 'level') == pytest.approx(exact, rel=1e-12, abs=1e-15)
    tied = derivatives.report(plan, {**point, 'tank.dose': 0.5}, GATES)
    assert classes(tied, 'level') == {
        'tank.first_at': 'smooth',
        'tank.dose': 'one-sided',
        'tank.limit': 'one-sided',
        'tank.pace': 'smooth',
    }
    assert values(tied, 'level') == pytest.approx(exact, rel=1e-12, abs=1e-15)


SET_LOW = """tank:  @shape
    "A tank that fills, with an event that sets its level."
    input first_at: h = 30 h in 0 h to 200 h  @shape
    input low: fraction = 0.2 in -1 to 1  @shape
    input pace: fraction/h = 0.01 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    var level: fraction = 0 size 100  @shape
    var out: fraction = 0 size 100  @shape
    flow fill: -> level at pace
    flow leave: level -> out at 0 fraction/h
    event set once when t >= first_at:  @shape
        "The level is set."
        level = low

output level: fraction = tank.level  @shape
    "Level"
    level
"""
LOWS = ('tank.first_at', 'tank.low', 'tank.pace')


def test_a_value_that_a_step_sets_on_its_bound_gives_a_derivative_of_one_side(tmp_path):
    """The level is set to `low` at `a` and ends at `low + r (T - a)`: its derivative by `low` is
    1. The level is a stock, which is never below 0. A `low` that misses 0 by less than the
    solver can tell (1e-12 below it) is taken as 0: the level cannot follow `low` further down,
    so the derivative by `low` is that of one side, and the engine gives 0 for it."""
    pace, hours = 0.01, 10 * DAY
    plan = plan_of(tmp_path, 10, SET_LOW)
    inside = derivatives.report(plan, {'tank.first_at': 30.0, 'tank.low': 0.2, 'tank.pace': pace}, LOWS)
    assert inside['outputs']['level']['value'] == pytest.approx(0.2 + pace * (hours - 30.0), rel=1e-13)
    assert classes(inside, 'level') == dict.fromkeys(LOWS, 'smooth')
    assert values(inside, 'level') == pytest.approx(
        {'tank.first_at': -pace, 'tank.low': 1.0, 'tank.pace': hours - 30.0}, rel=1e-12
    )
    on_bound = derivatives.report(plan, {'tank.first_at': 30.0, 'tank.low': -1e-12, 'tank.pace': pace}, LOWS)
    assert on_bound['outputs']['level']['value'] == pytest.approx(pace * (hours - 30.0), rel=1e-13)
    assert classes(on_bound, 'level') == {
        'tank.first_at': 'smooth',
        'tank.low': 'one-sided',
        'tank.pace': 'smooth',
    }
    assert values(on_bound, 'level') == pytest.approx(
        {'tank.first_at': -pace, 'tank.low': 0.0, 'tank.pace': hours - 30.0}, rel=1e-12, abs=1e-15
    )


CHANCE = """tank:  @shape
    "A tank that fills, with an event that doubles its level or not."
    input first_at: h = 30 h in 0 h to 200 h  @shape
    input odds: fraction = 0.7 in 0 to 1  @shape
    input pace: fraction/h = 0.01 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    var level: fraction = 0 size 100  @shape
    flow fill: -> level at pace
    event attempt once when t >= first_at:  @shape
        "The level doubles, or nothing happens."
        doubled odds:
            level = 2 * level
        nothing else:

output level: fraction = tank.level  @shape
    "Level"
    level
"""
ODDS = ('tank.first_at', 'tank.odds', 'tank.pace')


def test_two_outcomes_with_one_chance_give_a_derivative_of_one_side_by_what_moves_the_chance(tmp_path):
    """The central run takes the likelier outcome. With the odds of the doubling at 0.7 the level
    doubles and ends at `r a + r T`; the odds change nothing of that: derivative 0, smooth. With
    the odds at one half the two outcomes are as likely, and the run takes the first: odds that
    are a little less take the doubling away, so the derivative by the odds is that of one side.
    The least distance between the two chances is a margin of the run: 0.4, and 0."""
    pace, hours = 0.01, 10 * DAY
    plan = plan_of(tmp_path, 10, CHANCE)
    likely = derivatives.report(plan, {'tank.first_at': 30.0, 'tank.odds': 0.7, 'tank.pace': pace}, ODDS)
    exact = {'tank.first_at': pace, 'tank.odds': 0.0, 'tank.pace': 30.0 + hours}
    assert classes(likely, 'level') == dict.fromkeys(ODDS, 'smooth')
    assert values(likely, 'level') == pytest.approx(exact, rel=1e-12, abs=1e-15)
    assert likely['margins']['outcome'] == pytest.approx(0.4)
    even = derivatives.report(plan, {'tank.first_at': 30.0, 'tank.odds': 0.5, 'tank.pace': pace}, ODDS)
    assert classes(even, 'level') == {
        'tank.first_at': 'smooth',
        'tank.odds': 'one-sided',
        'tank.pace': 'smooth',
    }
    assert values(even, 'level') == pytest.approx(exact, rel=1e-12, abs=1e-15)
    assert even['margins']['outcome'] == 0.0


# ---- a crossing whose time its value does not decide ----------------------------------------------------

NEAR = """tank:  @shape
    "A level that comes near its mark and never passes it, and a count that starts there."
    input leak: ratio/h = 1 ratio/h in 0 ratio/h to 10 ratio/h  @shape
    input pace: fraction/h = 0.01 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    let mark: fraction = 0.5  @shape
    var level: fraction = 0 size 1  @shape
    var after: fraction = 0 size 100  @shape
    var full = false  @shape
    flow fill: -> level at leak * max(0, mark - level)
    flow tally: -> after at pace while full
    event reach once when level >= mark:  @shape
        "The level is at its mark."
        full = true

output after: fraction = tank.after  @shape
    "What was counted after the level was at its mark"
"""


def test_a_crossing_that_its_value_reaches_with_no_rate_has_no_derivative_of_its_time(tmp_path):
    """The level is `m (1 - e^(-k t))`: it comes near its mark `m` and never passes it. The event
    is due where the level is within its tolerance of the mark, with a rate that is next to
    nothing: the time of the event follows from the tolerance, and no derivative says how it
    moves with `k`. The count after the event is `r (T - τ)`: its derivative by `k` is not
    defined, and no number is given. The rate `r` does not move the event: the derivative by `r`
    is `T - τ`, smooth, with the time of the event of the run."""
    plan = plan_of(tmp_path, 10, NEAR)
    names = ('tank.leak', 'tank.pace')
    report = derivatives.report(plan, {'tank.leak': 1.0, 'tank.pace': 0.01}, names)
    # The level is within half of its tolerance (1e-10) of the mark at `ln(m / 0.5e-10) / k`, 23 h:
    # the run with the derivatives and the run with none have the event there, to a part in 1e4
    # (a time that the tolerance decides has no more digits).
    result = timeline.run(plan, {'tank.leak': 1.0, 'tank.pace': 0.01}, directions=names)
    ((at, rule, _),) = result.trace
    assert rule == 'tank.reach' and at == pytest.approx(math.log(0.5 / 0.5e-10), rel=1e-4)
    ((plain, _, _),) = timeline.run(plan, {'tank.leak': 1.0, 'tank.pace': 0.01}).trace
    assert plain == pytest.approx(at, rel=1e-4)
    assert classes(report, 'after') == {'tank.leak': 'undefined', 'tank.pace': 'smooth'}
    assert report['derivatives']['after']['tank.leak']['value'] is None
    assert report['derivatives']['after']['tank.leak']['error'] is None
    assert values(report, 'after')['tank.pace'] == pytest.approx(10 * DAY - at, rel=1e-12)
    # The time in which the value decides its crossing only within its tolerance: far more than a cap.
    assert report['margins']['crossing_time_h'] > 1.0


# ---- a part through which the engine carries no derivative ------------------------------------------------

DRAWN = TWO_EVENTS.replace(
    '    event add once when t >= second_at:  @shape',
    '    event add once after uniform(1 h, 3 h) when t >= second_at:  @shape',
)


def test_a_run_with_a_part_that_carries_no_derivative_names_the_part_and_keeps_the_zeros(tmp_path):
    """An event waits a time that the run draws: the engine carries no derivative through a drawn
    value. Each derivative of the level has the class `unsupported` and no number, with the name
    of the part; the outputs still have their values. A second tank that no read joins to the
    first keeps its zeros, which need no run."""
    assert DRAWN != TWO_EVENTS
    aside = """
aside:  @shape
    "A tank that no part of the first one reads."
    input gain: fraction/h = 0.02 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    var held: fraction = 0 size 100  @shape
    flow gather: -> held at gain
"""
    body = DRAWN.replace(
        '\noutput level:', aside + '\noutput held: fraction = aside.held  @shape\n    "Held"\n\noutput level:'
    )
    plan = plan_of(tmp_path, 10, body)
    names = ('tank.first_at', 'tank.pace', 'aside.gain')
    report = derivatives.report(plan, {'tank.first_at': 30.0, 'tank.pace': 0.01}, names)
    assert report['unsupported'] is not None and 'draw' in report['unsupported']
    assert classes(report, 'level') == {
        'tank.first_at': 'unsupported',
        'tank.pace': 'unsupported',
        'aside.gain': 'structurally zero',
    }
    assert report['derivatives']['level']['tank.pace']['value'] is None
    assert report['derivatives']['level']['tank.pace']['why'] == [report['unsupported']]
    assert classes(report, 'held') == {
        'tank.first_at': 'structurally zero',
        'tank.pace': 'structurally zero',
        'aside.gain': 'unsupported',
    }
    # The level doubles at 30 h and gets 1 more at 30 h and the central 2 h: `r a + r T + 1`.
    assert report['outputs']['level']['value'] == pytest.approx(0.01 * 30.0 + 0.01 * 10 * DAY + 1, rel=1e-12)
    assert report['outputs']['held']['value'] == pytest.approx(0.02 * 10 * DAY, rel=1e-12)


STARTED = """tank:  @shape
    "A tank that starts at a level and fills."
    input begin: fraction = 0.2 in 0 to 1  @shape
    input wait: h = 30 h in 0 h to 200 h  @shape
    input pace: fraction/day = 0.24 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    var level: fraction = begin size 100  @shape
    flow fill: -> level at pace

output level: fraction = tank.level  @shape
    "Level"

output wait: days = tank.wait  @shape
    "The wait"
    level
"""


def test_a_start_value_is_a_path_and_a_derivative_is_in_the_units_that_the_file_writes(tmp_path):
    """The level starts at `b` and fills at `r` for 10 days: it ends at `b + 10 r`, so its
    derivative by `b` is 1 (the start is the one path from `b` to the level) and by `r`, which the
    file writes for a day, 10. The output `wait` is the input of that name in days: 1.25 days for
    30 h, and 1/24 of a day for each hour of the input."""
    plan = plan_of(tmp_path, 10, STARTED)
    names = ('tank.begin', 'tank.wait', 'tank.pace')
    report = derivatives.report(plan, None, names)
    assert report['outputs']['level']['value'] == pytest.approx(0.2 + 2.4, rel=1e-13)
    assert report['outputs']['wait'] == {'value': pytest.approx(1.25), 'unit': 'days', 'label': 'The wait'}
    assert classes(report, 'level') == {
        'tank.begin': 'smooth',
        'tank.wait': 'structurally zero',
        'tank.pace': 'smooth',
    }
    assert values(report, 'level') == pytest.approx(
        {'tank.begin': 1.0, 'tank.wait': 0.0, 'tank.pace': 10.0}, rel=1e-12
    )
    assert classes(report, 'wait') == {
        'tank.begin': 'structurally zero',
        'tank.wait': 'smooth',
        'tank.pace': 'structurally zero',
    }
    item = report['derivatives']['wait']['tank.wait']
    assert item['value'] == pytest.approx(1 / 24, rel=1e-12) and item['unit'] == 'days per h'
    assert report['derivatives']['level']['tank.pace']['unit'] == 'fraction per fraction/day'
    # No crossing, one moment and no chance in this run: it has none of the three margins.
    assert report['margins'] == {'crossing_time_h': None, 'moments_apart_h': None, 'outcome': None}


def test_an_input_that_is_no_input_of_the_model_is_an_error(tmp_path):
    plan = plan_of(tmp_path, 10, TWO_EVENTS)
    with pytest.raises(KeyError):
        derivatives.report(plan, None, ('tank.level',))


# ---- the error of a derivative of a block that a solver integrates ----------------------------------------

SEEP = """Cell:  @shape
    "One cell."
    input inflow: fraction/day = 0.3 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    input leak: ratio/day = 0.4 ratio/day in 0 ratio/day to 2 ratio/day  @shape
    input keep: fraction = 0.25 in 0 to 1  @shape
    input mark: fraction = 0.3 in 0 to 5  @shape
    let shift: fraction = 0  @shape
    var water: fraction = 0.5 size 1  @shape
    var seeped: fraction = 0 size 1  @shape
    flow storm: -> water at inflow
    flow seep: water -> seeped at leak * water
    event drain once when seeped >= mark + shift:  @shape
        "A part of the water is let out."
        water = keep * water

cells: Cell from "cells.csv"

output water_total: fraction = sum(Cell.water)  @shape
    "Water of all cells"
    level
"""


def seep_total(inflow, leak, keep, mark, shifts, days=10):
    """The water of all cells at the horizon, at the precision of mpmath: before its event the
    water of a cell is `u/k + (w0 - u/k) e^(-k t)` and what seeped is `u t - (water - w0)`; the
    event is at the root of `seeped = mark + shift`; then the water goes on from `keep` times its
    value."""
    start = mpmath.mpf('0.5')
    rest = inflow / leak
    total = mpmath.mpf(0)
    for shift in shifts:

        def water(t):
            return rest + (start - rest) * mpmath.exp(-leak * t)

        at = mpmath.findroot(lambda t: inflow * t - (water(t) - start) - (mark + shift), 1)
        total += rest + (keep * water(at) - rest) * mpmath.exp(-leak * (days - at))
    return total


def test_the_error_of_a_derivative_through_a_solver_is_of_the_size_of_its_true_error(tmp_path):
    """The crossing is of a value that a solver integrates, and its step sets a state of the
    block. Each derivative is smooth, and its value is that of the closed form at 40 digits. With
    tolerances a hundred thousand times looser than those of a run, the error that the report
    gives (the distance to a second run with tolerances a hundred times tighter) is the true
    error of each derivative to a factor of two."""
    shifts = [0.0, 0.25, 0.6]
    point = {'inflow': 0.3, 'leak': 0.4, 'keep': 0.25, 'mark': 0.3}
    plan = plan_of(tmp_path, 10, SEEP, 'shift: fraction @shape', shifts)
    names = tuple(f'cells_1.{name}' for name in point)
    given = {f'cells_1.{name}': value for name, value in point.items()}
    report = derivatives.report(plan, given, names)
    loose = derivatives.report(plan, given, names, settings={'rtol': 1e-4, 'atol_factor': 1e-5})
    none = derivatives.report(plan, given, names, error=False)
    assert classes(report, 'water_total') == dict.fromkeys(names, 'smooth')
    with mpmath.workdps(40):
        exact = {name: mpmath.mpf(repr(value)) for name, value in point.items()}
        for name in point:
            slope = float(
                mpmath.diff(lambda x, name=name: seep_total(shifts=shifts, **{**exact, name: x}), exact[name])
            )
            item = report['derivatives']['water_total'][f'cells_1.{name}']
            assert item['value'] == pytest.approx(slope, rel=1e-9), name
            assert item['error'] <= 1e-9 * abs(slope), name
            rough = loose['derivatives']['water_total'][f'cells_1.{name}']
            true = abs(rough['value'] - slope)
            assert true > 1e-9 * abs(slope)  # far above the roundoff of the two
            assert true / 2 <= rough['error'] <= 2 * true, name
            assert none['derivatives']['water_total'][f'cells_1.{name}']['error'] is None


def test_the_derivatives_through_an_event_are_those_of_an_independent_implementation(tmp_path):
    """The cell of the test above, written again for CasADi with nothing of the engine: the two
    rates as symbols, the time to the event as an unknown that a root finder solves (the water
    that seeped is at its mark there), the reset, and the rest of the 10 days. CasADi integrates
    with CVODES and differentiates by its own rules (the sensitivities of the integrator, and the
    implicit function of the root). Its derivatives of the water at the horizon by the four inputs
    are those of the report."""
    ca = pytest.importorskip('casadi')
    point = {'inflow': 0.3, 'leak': 0.4, 'keep': 0.25, 'mark': 0.3}
    plan = plan_of(tmp_path, 10, SEEP, 'shift: fraction @shape', [0.0])
    names = tuple(f'cells_1.{name}' for name in point)
    report = derivatives.report(plan, {f'cells_1.{name}': value for name, value in point.items()}, names)

    inputs, state, span = ca.MX.sym('p', 4), ca.MX.sym('x', 2), ca.MX.sym('span')
    inflow, leak, keep, mark = inputs[0], inputs[1], inputs[2], inputs[3]
    # One unit of the integrator's time is `span` days: the state after `span` days of the cell.
    rates = ca.vertcat(inflow - leak * state[0], leak * state[0])
    problem = {'x': state, 'p': ca.vertcat(inputs, span), 'ode': span * rates}
    after = ca.integrator('after', 'cvodes', problem, 0.0, 1.0, {'abstol': 1e-12, 'reltol': 1e-12})

    def flow(start, days):
        return after(x0=start, p=ca.vertcat(inputs, days))['xf']

    at = ca.MX.sym('at')
    seeped = ca.Function('seeped', [at, inputs], [flow(ca.DM([0.5, 0.0]), at)[1] - mark])
    event = ca.rootfinder('event', 'newton', seeped)(1.0, inputs)
    before = flow(ca.DM([0.5, 0.0]), event)
    end = flow(ca.vertcat(keep * before[0], before[1]), 10.0 - event)
    water = ca.Function('water', [inputs], [end[0], ca.jacobian(end[0], inputs), event])
    value, slopes, time = water(ca.DM(list(point.values())))
    assert report['outputs']['water_total']['value'] == pytest.approx(float(value), rel=1e-8)
    # The event of the two is at one time (in days).
    ((found, _, _),) = timeline.run(plan, {f'cells_1.{name}': v for name, v in point.items()}).trace
    assert found / DAY == pytest.approx(float(time), rel=1e-8)
    for place, name in enumerate(names):
        item = report['derivatives']['water_total'][name]
        assert item['class'] == 'smooth'
        assert item['value'] == pytest.approx(float(slopes[place]), rel=2e-6), name


# ---- what can make an output jump (the finer graph) --------------------------------------------------

MARKED = """Cell:  @shape
    "A cell with a line, and a formula that is 1 where its pace is above a mark."
    input mark: fraction/day = 0.3 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    input pace: fraction/day = 0.5 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    let scale: fraction = 1  @shape
    let hit: fraction = (1 if pace * scale > mark else 0)  @shape
    var plain: fraction = 0 size 100  @shape
    flow slide: -> plain at pace * scale

cells: Cell from "cells.csv"

output hits: fraction = sum(Cell.hit)  @shape
    "The cells whose pace is above their mark"
    level

output plains: fraction = sum(Cell.plain)  @shape
    "The lines of all cells"
"""


def test_a_comparison_in_a_member_of_a_list_can_make_the_output_that_reads_the_list_jump(tmp_path):
    """The output `hits` reads a list, and each member of the list has a comparison of the pace
    with the mark: the output can jump when one of the two changes by a little. The output
    `plains` is a line in the pace, and the mark does not reach it."""
    plan = plan_of(tmp_path, 10, MARKED, 'scale: fraction @shape', SCALES)
    graph = Influence(plan.fast() or plan, paths=True)
    jump = ['a comparison that the input can change, in hits']
    assert graph.breaks('cells_1.mark', 'hits') == jump
    assert graph.breaks('cells_1.pace', 'hits') == jump
    assert graph.breaks('cells_1.pace', 'plains') == []
    assert graph.between('cells_1.mark', 'plains') == set()
    assert output_place('plains') in graph.between('cells_1.pace', 'plains')


# ---- a rate that jumps at a time that an input moves ------------------------------------------------

JUMPING = """tank:  @shape
    "A tank that fills at one rate, then at another, at a time that the inputs set."
    input stop: h = 3 h in 0 h to 100 h  @shape
    input pace: fraction/h = 0.5 fraction/h in 0 fraction/h to 2 fraction/h  @shape
    var level: fraction = 0 size 100  @shape
    var filled: fraction = 0 size 100  @shape
    flow rise: -> level at pace
    flow fill: -> filled at {rate}

output filled: fraction = tank.filled  @shape
    "What the tank filled"
    level
"""
JUMPS = ('tank.stop', 'tank.pace')


@pytest.mark.parametrize(
    'rate',
    [
        '(1 fraction/h if t < stop else 0 fraction/h)',
        '1 fraction/h while t < stop',
        '(1 fraction/h if level < pace * stop else 0 fraction/h)',
    ],
)
def test_a_rate_that_jumps_at_a_time_that_an_input_moves_has_no_derivative(tmp_path, rate):
    """`filled` rises at 1 an hour until a switch and is flat after it: at the horizon of 10 h it is
    the time of the switch, `stop` (the level `pace t` reaches `pace stop` at `stop` too). Its
    derivative by `stop` is 1 and its value at 10 h is 3. A tangent along the run is 0 on each side
    of the switch, and the rate jumps there by 1 an hour: the tangents of the block carry no such
    jump, so the derivative is not given, with the comparison named."""
    plan = plan_of(tmp_path, 10 / DAY, JUMPING.replace('{rate}', rate))
    report = derivatives.report(plan, inputs=JUMPS, error=False)
    assert report['outputs']['filled']['value'] == pytest.approx(3.0, rel=1e-6)
    found = report['derivatives']['filled']['tank.stop']
    assert found['class'] == 'unsupported' and found['value'] is None
    assert found['why'] and all('change their order' in why for why in found['why'])


def test_a_rate_that_jumps_at_a_time_that_no_input_moves_keeps_its_derivative(tmp_path):
    """The rate jumps at 3 h, which no input moves, and `filled` adds `pace` an hour on top: at
    10 h it is `3 + 10 pace`. Its derivative by `pace` is 10, smooth; by `stop` it is 0, which the
    structure gives (nothing reads `stop`)."""
    body = JUMPING.replace('{rate}', '(1 fraction/h if t < 3 h else 0 fraction/h) + pace')
    report = derivatives.report(plan_of(tmp_path, 10 / DAY, body), inputs=JUMPS, error=False)
    assert report['outputs']['filled']['value'] == pytest.approx(3.0 + 10 * 0.5, rel=1e-6)
    assert classes(report, 'filled') == {'tank.stop': 'structurally zero', 'tank.pace': 'smooth'}
    assert values(report, 'filled')['tank.pace'] == pytest.approx(10.0, rel=1e-6)


def test_a_kink_at_a_time_that_an_input_moves_keeps_its_derivative(tmp_path):
    """`min(t, stop)` is continuous: `filled` is the integral of `min(t, stop)` an hour, at 10 h
    `stop^2 / 2 + stop (10 - stop)`, whose derivative by `stop` is `10 - stop` = 7. The pieces
    meet without a jump, so the derivative is given."""
    body = JUMPING.replace('{rate}', 'min(t, stop) / 1 h * 1 fraction/h')
    report = derivatives.report(plan_of(tmp_path, 10 / DAY, body), inputs=JUMPS, error=False)
    assert report['outputs']['filled']['value'] == pytest.approx(9 / 2 + 3 * 7, rel=1e-6)
    found = report['derivatives']['filled']['tank.stop']
    assert found['class'] in ('smooth', 'one-sided')
    assert found['value'] == pytest.approx(7.0, rel=1e-4)


def test_the_jumps_of_an_expression_are_the_sides_of_its_comparisons():
    read = expr.read
    node = read('min(a, b) + (c if d < e else f) + abs(g) + (1 if h >= i else 0)')
    assert set(smooth.jumps(node)) == {(read('d'), read('e')), (read('h'), read('i'))}
    assert len(smooth.jumps(node)) == 2
    assert set(smooth.jumps(node)) < set(smooth.pairs(node))
    assert smooth.jumps(read('max(a, b) + clip(c, d, e)')) == ()
