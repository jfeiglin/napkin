"""Eligibility of an outcome (spec, "Choosing actions inside a stage" and "Actor decisions and
observations"; D1; `chance.py`).

A case's guard says whether its outcome can happen: an outcome that a false guard bars is taken by
no median run, no sampled run and no pick. The guards are read once, before the selector, and a draw
is made among the eligible outcomes with their weights scaled to sum to one. With no eligible
outcome the `else` body runs and nothing is drawn. Eligibility and probability are independent: a
player may pick an eligible outcome whose weight is zero. The expected values come from the spec's
dispatcher and from the rules themselves.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    Builder,
    add,
    after,
    case,
    categorical,
    choose,
    dist_of,
    draw,
    event,
    named,
    q,
    start,
    switch,
    this,
    value,
)
from napkin.program.config import PLAYER, SAMPLED, Configuration, Controller, Pick, Request

UNITS = {'h': {'time': 1}}
SITE = 'guard.decide.step[0].do[0].draw[0]'
CHOICE = 'guard.decide.step[0].do[0].choice[0]'


def guard(weights, valve=0, chooser=False):
    """A guard that decides at 1 h between SHUT, which needs the valve open (at 1 or more), and WAIT,
    which needs it not broken (at 0 or more); `chooser` makes the actor `operator` choose with the
    forecast `weights`, else the guard draws from them. Each case counts, and so does the `else`."""
    b = Builder(UNITS)
    action = b.enum('enum[SHUT, WAIT]', 'SHUT', 'WAIT')
    forecast = categorical(action, **weights)
    if chooser:
        operator = b.entity('operator', value('forecast', dist_of(action), forecast))
        selector = choose(operator, operator.forecast)
    else:
        selector = draw(forecast)
    b.entity(
        'guard',
        value('open', '', valve),
        value('shut', '', 0),
        value('waited', '', 0),
        value('neither', '', 0),
        event(
            'decide',
            after(
                q(1, 'h'),
                switch(
                    selector,
                    case(action.SHUT, add(this.shut, 1), when=this.open >= 1),
                    case(action.WAIT, add(this.waited, 1), when=this.open >= 0),
                    orelse=(add(this.neither, 1),),
                ),
            ),
        ),
    )
    b.setup(start(named('guard').decide))
    return b.finish()


def counts(program, configuration):
    record = run(program, configuration)
    assert record.failure is None, record.failure
    found = read(record, program, ['guard.shut', 'guard.waited', 'guard.neither'], [2])
    return tuple(reading.values[0] for reading in found), record


def test_a_median_run_takes_the_likeliest_eligible_outcome():
    """SHUT is the likelier, but the closed valve bars it: the median run waits."""
    program = guard({'SHUT': 0.9, 'WAIT': 0.1})
    assert counts(program, Configuration(Request(2)))[0] == (0, 1, 0)
    assert counts(guard({'SHUT': 0.9, 'WAIT': 0.1}, valve=1), Configuration(Request(2)))[0] == (1, 0, 0)


def test_a_sampled_run_never_takes_an_outcome_that_a_guard_bars():
    program = guard({'SHUT': 0.9, 'WAIT': 0.1})
    for seed in range(40):
        assert counts(program, Configuration(Request(2), mode=SAMPLED, seed=seed))[0] == (0, 1, 0)


def test_the_weights_of_the_eligible_outcomes_are_scaled_to_sum_to_one():
    """With the valve open, SHUT and WAIT are drawn 9 to 1: over 400 seeds the share of SHUT is 0.9
    within three standard deviations of a binomial share."""
    program = guard({'SHUT': 0.9, 'WAIT': 0.1}, valve=1)
    shut = sum(
        counts(program, Configuration(Request(2), mode=SAMPLED, seed=seed))[0][0] for seed in range(400)
    )
    assert abs(shut / 400 - 0.9) <= 3 * (0.9 * 0.1 / 400) ** 0.5


@pytest.mark.parametrize('chooser', [False, True])
def test_with_no_eligible_outcome_the_else_body_runs_and_nothing_is_drawn(chooser):
    """A broken valve (-1) bars both outcomes: the `else` body runs, with no draw and no choice."""
    found, record = counts(
        guard({'SHUT': 0.5, 'WAIT': 0.5}, valve=-1, chooser=chooser), Configuration(Request(2))
    )
    assert found == (0, 0, 1)
    assert record.entries('draw') == record.entries('choice') == ()


def test_eligible_outcomes_with_no_weight_have_no_draw():
    """WAIT is the only eligible outcome, and its weight is zero: there is nothing to draw."""
    record = run(guard({'SHUT': 1, 'WAIT': 0}), Configuration(Request(2), mode=SAMPLED, seed=1))
    # With SHUT barred, only WAIT is eligible, with no weight.
    assert record.failure is not None
    assert 'no eligible outcome has a weight to draw (eligible: WAIT)' in record.failure.detail('message')


def played(pick, **options):
    program = guard({'SHUT': 0, 'WAIT': 1}, chooser=True, **options)
    configuration = Configuration(
        Request(2),
        controllers=(Controller('operator', PLAYER),),
        picks=(Pick(CHOICE, 'guard.decide#0', pick),),
    )
    return program, configuration


def test_a_player_may_pick_an_eligible_outcome_whatever_its_weight():
    """The forecast never shuts; with the valve open a player can."""
    assert counts(*played('SHUT', valve=1))[0] == (1, 0, 0)
    (choice,) = counts(*played('SHUT', valve=1))[1].entries('choice')
    assert (choice.detail('by'), choice.detail('options'), choice.detail('value')) == (
        'player',
        ('SHUT', 'WAIT'),
        'SHUT',
    )


def test_a_pick_of_an_outcome_that_a_guard_bars_fails_the_run():
    record = run(*played('SHUT'))
    assert record.failure.t == 1
    assert 'the pick SHUT of guard.decide#0 is not available (available: WAIT)' in record.failure.detail(
        'message'
    )
    assert counts(*played('WAIT'))[0] == (0, 1, 0)


def test_the_forecast_takes_only_eligible_outcomes_too():
    """With no controller, the operator's choice is the forecast's draw: it waits, and with the valve
    open a forecast that always shuts shuts."""
    program = guard({'SHUT': 0, 'WAIT': 1}, chooser=True, valve=1)
    found, record = counts(program, Configuration(Request(2)))
    assert found == (0, 1, 0)
    (choice,) = record.entries('choice')
    assert (choice.part, choice.owner, choice.detail('by')) == (CHOICE, 'guard.decide#0', 'forecast')
    assert counts(guard({'SHUT': 1, 'WAIT': 0}, chooser=True, valve=1), Configuration(Request(2)))[0] == (
        1,
        0,
        0,
    )


@pytest.mark.parametrize('chooser', [False, True])
def test_the_guards_are_read_once_before_the_selector(chooser):
    """The selector's site is traced after the guards' reads: a draw of a barred case never happens,
    and a draw outside a switch takes every outcome as eligible."""
    record = run(guard({'SHUT': 0.5, 'WAIT': 0.5}, chooser=chooser), Configuration(Request(2)))
    entries = record.entries('choice' if chooser else 'draw')
    assert [entry.part for entry in entries] == [CHOICE if chooser else SITE]
    assert entries[0].detail('value') == 'WAIT'
