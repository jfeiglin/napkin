"""A run with given outcomes (`timeline.Run(outcomes=…)`, docs/engine.md, "The outcomes of a run,
given"): the firings that go by chance take the outcomes that a caller gives, and the run keeps
each such firing with its chances.

The oracles are the rule in words (a sample takes the first outcome whose running total of the
chances is above its uniform number), written again here with exact fractions, and the closed form
of a small model: a clock that ticks each hour and adds to a total with one outcome.
"""

from fractions import Fraction
from itertools import pairwise

import pytest

from napkin.engine.timeline.run import shares
from napkin.engine.uncertainty import run_sample
from tests.build import block, compiled, document, entity, output, parameter, stock


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
    assert [name for name, _, _ in firings] == ['shop.tick'] * 6
    assert [place for _, _, place in firings] == [*places, *[1] * (6 - len(places))]
    for _, chances, _ in firings:
        assert chances == pytest.approx((0.3, 0.7), abs=1e-15)


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
