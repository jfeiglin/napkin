"""The switching surfaces of a component (`continuous/integrate.py`, `switching_surfaces`,
`switching_roots`).

A rate with `min`, `max`, `clip`, `abs` or a comparison is smooth on each side of a surface and
has a kink or a jump on it. A numerical segment ends on such a surface, so that no step of the
solver has both sides in it. The surfaces are stated here by the rule, for one rate that has each
form; and a run whose rate has a kink at a time with a closed form ends a segment there.
"""

import math

import pytest

from napkin.core import expr
from napkin.engine import read, run
from napkin.engine.continuous.integrate import switching_surfaces
from napkin.engine.timeline import Plan, Run
from napkin.program import build
from napkin.program.build import (
    SOURCE,
    Builder,
    clip,
    flow,
    fmax,
    fmin,
    formula,
    ifelse,
    input_,
    q,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

UNITS = {'person': {'people': 1}, 'h': {'time': 1}}


def level_of(rate, *inputs, horizon=5):
    """A level that fills from outside at `rate`, a formula of the level and of the inputs."""
    b = Builder(UNITS)
    b.entity(
        's',
        *inputs,
        value('level', 'person', 0, lower=0),
        flow('fill', SOURCE, this.level, request=formula(rate)),
    )
    return b.finish(), Configuration(Request(horizon))


def test_the_surfaces_of_a_run_are_those_of_each_form_with_a_side_that_moves():
    """One rate with each form. By the rule: `min` and `max` have a surface for each pair of their
    values; `clip` has one at each end; `abs` has one where its value is zero; a comparison of order
    has one where its sides are equal, and a comparison of equality has none (`level + mid != mark`).
    A pair with no side that moves between moments is no surface: the two inputs of the last `min`
    never change."""
    hour, none = q(1, 'h'), q(0, 'person/h')
    level = this.level
    rate = (
        fmin(level, this.cap) / hour
        + clip(level, this.low, this.high) / hour
        + build._call('abs', level - this.mid) / hour  # the builder has no handle of `abs`
        + ifelse(level > this.mark, this.gain, none)
        + ifelse(level + this.mid != this.mark, this.gain, none)
        + fmax(this.low, this.mid, level) / hour
        + fmin(this.cap, this.high) / hour
    )
    people = [input_(name, 'person', number) for name, number in (('cap', 9), ('low', 1), ('high', 8))]
    people += [input_('mid', 'person', 4), input_('mark', 'person', 6), input_('gain', 'person/h', 2)]
    program, configuration = level_of(rate, *people)
    _, _, ((component, _),) = Run(Plan.of(program, configuration)).prepare()
    found = [(expr.text(a), expr.text(b_)) for a, b_ in switching_surfaces(component.system)]
    assert len(found) == len(set(found))
    assert set(found) == {
        ('s.level', 's.cap'),
        ('s.level', 's.low'),
        ('s.level', 's.high'),
        ('s.level - s.mid', '0'),
        ('s.level', 's.mark'),
        # `max` of three values: each pair with the level; the pair of the two inputs does not move.
        ('s.low', 's.level'),
        ('s.mid', 's.level'),
    }


def test_a_segment_ends_where_the_rate_changes_its_branch():
    """The level rises at `max(0.2, 1 - level)` an hour from 0. It is `1 - exp(-t)` until its rate
    falls to 0.2, at `t = ln 5`, and it rises at 0.2 an hour after that. The record has a piece that
    starts at that time, and the level at the horizon of 5 h is `0.8 + 0.2 (5 - ln 5)`."""
    rate = fmax(q(0.2, 'person/h'), (q(1, 'person') - this.level) / q(1, 'h'))
    program, configuration = level_of(rate)
    record = run(program, configuration)
    switch = math.log(5)
    starts = [piece.t for piece in record.history(Key('s', ('level',))).pieces]
    assert min(abs(t - switch) for t in starts) < 1e-6, starts
    (level,) = read(record, program, ['s.level'], [1.0, 5.0])
    assert level.values == pytest.approx((1 - math.exp(-1), 0.8 + 0.2 * (5 - switch)), rel=1e-6)
