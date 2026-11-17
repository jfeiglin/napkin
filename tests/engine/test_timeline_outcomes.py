"""A run with given outcomes (`timeline.Run(outcomes=…)`, docs/engine.md, "The outcomes of a run,
given"): the firings that go by chance take the outcomes that a caller gives, and the run keeps
each such firing with its chances.

The oracles are the rule in words (a sample takes the first outcome whose running total of the
chances is above its uniform number), written again here with exact fractions, and closed forms
of small models: a clock that ticks each hour and adds to a total with one outcome, and a tank
that fills at a constant pace and doubles its level at one time or not.
"""

from fractions import Fraction
from itertools import pairwise

import numpy as np
import pytest

from napkin.engine import timeline
from napkin.engine.timeline.run import shares
from napkin.engine.uncertainty import run_sample
from napkin.model import hybrid
from tests.build import block, compiled, document, entity, output, parameter, stock

HEAD = """scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon 10 days
    scope "Nothing: the model is synthetic."

"""
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'


def taken_by_a_sample(chances, u):
    """The place that a sample with the uniform number u takes: the first outcome with a chance
    whose running total is above u, and the last outcome with a chance when no total is."""
    total, last = Fraction(0), None
    for place, chance in enumerate(chances):
        if chance <= 0:
            continue
        total, last = total + chance, place
        if u < total:
            return place
    return last


@pytest.mark.parametrize(
    'chances',
    [
        (Fraction(3, 10), Fraction(7, 10)),
        (Fraction(1, 4), Fraction(0), Fraction(1, 2), Fraction(1, 4)),
        # The chances add up to 1 within a tolerance only: a little less, and a little more.
        (Fraction(1, 3), Fraction(1, 3), Fraction(1, 3) - Fraction(1, 10**10)),
        (Fraction(1, 2), Fraction(1, 2) + Fraction(1, 10**10), Fraction(0)),
        (Fraction(1), Fraction(1, 10**10)),
        (Fraction(0), Fraction(1)),
    ],
)
def test_the_share_of_each_outcome_is_the_part_of_the_uniform_numbers_that_takes_it(chances):
    """The uniform number of a sample is anywhere from 0 to 1. The part of that range in which
    the rule takes an outcome is found here from the ends of the pieces: between two ends the rule
    takes one place. `shares` gives the same parts, and they add up to 1."""
    ends = sorted(
        {Fraction(0), Fraction(1), *(min(Fraction(1), sum(chances[: k + 1])) for k in range(len(chances)))}
    )
    exact = [Fraction(0)] * len(chances)
    for low, high in pairwise(ends):
        exact[taken_by_a_sample(chances, (low + high) / 2)] += high - low
    found = shares([float(chance) for chance in chances])
    assert found == pytest.approx([float(part) for part in exact], abs=1e-15)
    assert sum(found) == pytest.approx(1.0, abs=1e-15)


def ticks(odds='odds', hit=('next += 1 h', 'total += gain'), horizon=6):
    """A clock that ticks at each hour from 1 h: with the chance `odds` a tick is a hit, which
    adds `gain` (2 people) to the total."""
    return document(
        'Ticks',
        entity(
            'shop',
            parameter('odds', 0.3, 'fraction', 0, 1),
            parameter('gain', 2, 'people', 0, 10),
            stock('next', 1, 'h', minimum=None, maximum=50, size=None, kind='state'),
            stock('total', 0, 'people', size=1000),
            block(
                'event tick when t >= next:  @fixture',
                '"A tick."',
                block(f'hit {odds}:', *hit),
                block('miss else:', 'next += 1 h'),
            ),
        ),
        output('total', 'shop.total', 'people'),
        horizon=horizon,
    )


def total_of(model, places):
    found = run_sample(model, 'a', {}, None, [6.0], None, outcomes=places)
    assert not found['failures'], found['failures']
    return found['rows'][0]['values']['total'], found['firings']


@pytest.mark.parametrize('places', [(), (0,), (1, 0, 0), (0, 1, 0, 1, 0, 0), (0, 0, 0, 0, 0, 0)])
def test_a_run_takes_the_given_outcomes_and_then_the_likeliest(places):
    """The clock ticks six times to the horizon of 6 h. A tick whose outcome is given takes it
    (place 0 is a hit); a later tick takes the likelier outcome, a miss with the chance 0.7. So
    the total is 2 people for each hit among the given places. The run keeps each of the six
    firings: its event, the chances 0.3 and 0.7, and the place that it took."""
    total, firings = total_of(compiled(ticks()), places)
    assert total == 2 * places.count(0)
    assert [name for name, _, _, _ in firings] == ['shop.tick'] * 6
    assert [place for _, _, place, _ in firings] == [*places, *[1] * (6 - len(places))]
    for _, chances, _, slopes in firings:
        assert chances == pytest.approx((0.3, 0.7), abs=1e-15)
        assert slopes is None  # the run carries no derivative


def test_more_given_outcomes_than_firings_change_nothing():
    total, firings = total_of(compiled(ticks()), (0, 0, 0, 0, 0, 0, 1, 0))
    assert total == 12 and len(firings) == 6


@pytest.mark.parametrize(('odds', 'places'), [('0', (0,)), ('1', (1,)), ('odds', (2,)), ('odds', (-1,))])
def test_a_given_outcome_that_no_sample_takes_stops_the_run(odds, places):
    """A hit with the chance 0, a miss with the chance 0 (`else` of 1), and a place that the event
    has not: no sample takes such an outcome, so no path of the outcomes has it."""
    with pytest.raises(ValueError, match='no sample takes the outcome'):
        run_sample(compiled(ticks(odds)), 'a', {}, None, [6.0], None, outcomes=places)


def test_a_run_with_no_given_outcomes_keeps_no_firing_and_is_the_central_run():
    """`outcomes=None` is a run as before: the central run, which keeps no firing. With `()` the
    run takes the likeliest outcome of each firing too, and keeps the firings."""
    model = compiled(ticks())
    plain = run_sample(model, 'a', {}, None, [6.0], None)
    given = run_sample(model, 'a', {}, None, [6.0], None, outcomes=())
    assert 'firings' not in plain and len(given['firings']) == 6
    assert plain['rows'] == given['rows']
    assert plain['events'] == given['events'] == {'shop.tick': {'hit': 0, 'miss': 6}}


CHANCE = """tank:  @shape
    "A tank that fills, with an event that doubles its level or not."
    input first_at: h = 30 h in 0 h to 200 h  @shape
    input odds: fraction = 0.7 in 0 to 1  @shape
    input pace: fraction/h = 0.01 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    var level: fraction = 0 size 100  @shape
    flow fill: -> level at pace
    event attempt once when t >= first_at:  @shape
        "The level doubles, or nothing happens."
        doubled odds * (1 - level):
            level = 2 * level
        nothing else:

output level: fraction = tank.level  @shape
    "Level"
    level
"""
INPUTS = ('tank.first_at', 'tank.odds', 'tank.pace')


def test_a_run_with_directions_keeps_the_derivative_of_each_chance_and_of_each_path(tmp_path):
    """The tank has the level `r a` at the time a of its event (pace r). The chance of the
    doubling is `p (1 - r a)`, and that of nothing is the rest, so the derivatives of the first
    chance by (a, p, r) are `(-p r, 1 - r a, -p a)` and those of the second the same with the
    other sign. At the horizon T the level is `r a + r T` with the doubling and `r T` without:
    the derivatives by (a, p, r) are `(r, 0, a + T)` and `(0, 0, T)`."""
    path = tmp_path / 'model.scn'
    path.write_text(HEAD + CHANCE + RECORD, encoding='utf-8')
    plan = timeline.Plan.of(hybrid.compile(path))
    a, p, r, hours = 30.0, 0.7, 0.01, 240.0
    values = {'tank.first_at': a, 'tank.odds': p, 'tank.pace': r}
    chance = p * (1 - r * a)
    for place, level, exact in (
        (0, r * a + r * hours, (r, 0.0, a + hours)),
        (1, r * hours, (0.0, 0.0, hours)),
    ):
        made = timeline.run(plan, values, directions=INPUTS, outcomes=(place,))
        ((name, chances, took, slopes),) = made.firings
        assert (name, took) == ('tank.attempt', place)
        assert chances == pytest.approx((chance, 1 - chance), rel=1e-12)
        assert slopes[0] == pytest.approx((-p * r, 1 - r * a, -p * a), rel=1e-12)
        assert slopes[1] == pytest.approx((p * r, -(1 - r * a), p * a), rel=1e-12)
        assert made.outputs['level'] == pytest.approx(level, rel=1e-12)
        found = [made.tangents[name]['level'] for name in INPUTS]
        assert found == pytest.approx(exact, rel=1e-12, abs=1e-15)
        # The outcome is given: the run does not note that two outcomes are as likely.
        assert not [note for note in made.notes if note[0] == 'outcome']
    # The central run takes the likelier outcome: the doubling, with the chance 0.49, is not it.
    assert timeline.run(plan, values).outputs['level'] == pytest.approx(r * hours, rel=1e-12)
    assert np.isclose(chance, 0.49)
