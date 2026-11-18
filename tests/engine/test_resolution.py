"""The step cap of a numerical segment (`Numerics.max_step`, docs/engine.md "Steps").

The cap is the interval at which the engine reads a segment; the solver takes longer steps where
its control of the error allows them. A program declares no physical timescale, so nothing else
limits the solver's steps (the timescales of the old language have no spelling in a program yet).
Logistic growth has a closed form, x(t) = K / (1 + (K / x0 - 1) exp(-r t)), so a long run is
checked against it.
"""

from __future__ import annotations

import math

import pytest

import napkin.engine.continuous.integrate as integrate
from napkin.engine import read, run
from napkin.program.build import SINK, SOURCE, Builder, flow, formula, input_, q, this, value
from napkin.program.config import Configuration, Numerics, Request

YEAR_H = 8760.0
HORIZON = 20 * YEAR_H  # twenty years of hours
X0, CAPACITY = 10.0, 1000.0  # people at the start, and the most that the population reaches
GROWTH = 0.5 / YEAR_H  # per hour: half a year's growth rate


def logistic():
    """A population that grows at r x and is crowded out at r x^2 / K."""
    b = Builder({'person': {'people': 1}, 'h': {'time': 1}})
    hour = q(1, 'h')
    b.entity(
        's',
        input_('r', None, GROWTH),
        input_('cap', 'person', CAPACITY),
        value('x', 'person', X0, lower=0, scale=CAPACITY),
        flow('grow', SOURCE, this.x, request=formula(this.r * this.x / hour)),
        flow('crowd', this.x, SINK, request=formula(this.r * this.x * this.x / this.cap / hour)),
    )
    return b.finish()


def closed_form(t):
    return CAPACITY / (1 + (CAPACITY / X0 - 1) * math.exp(-GROWTH * t))


def population(cap, years, monkeypatch=None):
    """The population at the end of each of `years` in a run with the step cap `cap`, and the
    lengths of the steps of its solver."""
    lengths = []
    if monkeypatch is not None:
        original = integrate.radau

        def counted(*args, **kwargs):
            result = original(*args, **kwargs)
            lengths.extend(float(b - a) for a, b in zip(result.t, result.t[1:], strict=False))
            return result

        monkeypatch.setattr(integrate, 'radau', counted)
    program = logistic()
    record = run(program, Configuration(Request(HORIZON), numerics=Numerics(max_step=cap)))
    assert record.failure is None
    (x,) = read(record, program, ['s.x'], [years_ * YEAR_H for years_ in years])
    return x.values, lengths


def test_a_coarse_cap_follows_the_closed_form_over_twenty_years():
    years = (1, 5, 10, 15, 20)
    found, _ = population(720, years)
    assert found == pytest.approx([closed_form(y * YEAR_H) for y in years], rel=1e-7)


@pytest.mark.deep
def test_the_cap_is_the_interval_of_the_checks_and_not_the_longest_step_of_the_solver(monkeypatch):
    """With a cap of 1 h, over twenty years of slow growth the solver takes steps of many hours where
    its own control of the error allows them: far fewer steps than the hours of the run. The record
    follows the closed form at the ends of the years and between them."""
    years = (0.37, 1, 4.5, 5, 10, 13.21, 15, 20)
    found, lengths = population(1, years, monkeypatch)
    assert max(lengths) > 100 and len(lengths) < HORIZON / 20
    assert found == pytest.approx([closed_form(y * YEAR_H) for y in years], rel=1e-8)
